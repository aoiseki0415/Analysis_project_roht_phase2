#!/usr/bin/env python3
"""Independent saved-PSD audit of No11 Pz low-alpha/main and Set 1 change.

Reads the existing No10 all-channel cache without running Welch, rendering or
altering that cache. Reconstructs masks, Pz curves, paired quantification and
statistics from saved pre-mask PSD. The only write is the requested JSON report
under the authorized No11/main or sub Sub/logs directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from matplotlib import font_manager
from Phase4_No10_FzLowAlpha import engine as source_engine
from PIL import Image
from statsmodels.stats.multitest import multipletests
from validate_phase4_no10_outputs import compare_csv, equal, paired_test, smooth_interpolate

MAIN_STEM = "No11_PzLowAlpha"
SUB_STEM = "No11_sub_PzLowAlphaChange"
CHANNELS = source_engine.EXPECTED_CHANNEL_NAMES
PZ = CHANNELS.index("Pz")
PRODUCTS = ("CCube", "VRohtoPremium")


def reconstruct_masked_cache(path: Path, sid: str, report: dict) -> dict:
    """Recompute source masks independently; do not call a PSD calculation."""
    source_engine.validate_cache(path)
    with h5py.File(path, "r") as handle:
        expected_attrs = {
            "participant_id": sid,
            "sampling_frequency_hz": 256,
            "fmin_hz": 8,
            "fmax_hz": 10,
            "step_samples": 256,
            "n_fft": 256,
            "n_per_seg": 256,
            "n_overlap": 0,
            "time_smoothing": "none",
        }
        for key, expected in expected_attrs.items():
            if handle.attrs[key] != expected:
                raise ValueError(f"{path}: {key} mismatch")
        if json.loads(handle.attrs["included_frequencies_hz"]) != [8, 9, 10]:
            raise ValueError(f"{path}: expected 8, 9, 10 Hz")
        groups = {int(name[3:]): group for name, group in handle["sets"].items()}
        missing = set(range(1, 7)) - groups.keys()
        if missing != source_engine.EXPECTED_MISSING_SETS.get(sid, set()):
            raise ValueError(f"{path}: unexpected missing set")
        raw = {s: group["psd_band_mean"][:] for s, group in groups.items()}
        overlap = {s: group["ica_training_mask_fraction"][:] for s, group in groups.items()}
        if any(value.ndim != 2 or value.shape[1] != 32 for value in raw.values()):
            raise ValueError(f"{path}: expected window by 32-channel PSD")
        if any(np.any((value < 0) | (value > 1)) for value in overlap.values()):
            raise ValueError(f"{path}: invalid Phase 1 overlap fraction")
        valid = {
            s: np.isfinite(values) & (values > 0) & (overlap[s][:, None] < 0.01)
            for s, values in raw.items()
        }
        moments = np.full((2, 32), np.nan)
        for ch in range(32):
            values = np.concatenate(
                [values[valid[s][:, ch], ch] for s, values in sorted(raw.items())]
            )
            if values.size >= 2:
                # No10 masks were computed after cache float32 storage.
                logged = np.log10(values)
                moments[:, ch] = np.mean(logged), np.std(logged, ddof=1)
        threshold = moments[0] + 3 * moments[1]
        for name, expected in (
            ("mean", moments[0]),
            ("sd", moments[1]),
            ("threshold_log", threshold),
            ("threshold_linear", 10.0**threshold),
        ):
            equal(handle[f"qc/log3sd_{name}_by_channel"][:], expected, f"{path}: {name}")
        counts, valid_counts = np.zeros((6, 32), int), np.zeros((6, 32), int)
        output = {}
        for s, values in raw.items():
            group = groups[s]
            centers = group["source_center_sample"][:]
            n_samples = int(group.attrs["source_n_samples"])
            expected_centers = np.unique(np.r_[np.arange(0, n_samples, 256), n_samples - 1])
            equal(centers, expected_centers, f"{path}: centers Set{s}")
            progress = centers / (n_samples - 1) * 100.0
            equal(group["set_progress_pct"][:], progress, f"{path}: progress Set{s}")
            equal(group["relative_seconds_center"][:], centers / 256, f"{path}: time Set{s}")
            equal(
                group["global_progress_pct"][:],
                progress + (s - 1) * 100,
                f"{path}: global progress Set{s}",
            )
            logged = np.full(values.shape, np.nan)
            logged[valid[s]] = np.log10(values[valid[s]])
            excluded = valid[s] & (logged > threshold)
            equal(group["log3sd_outlier_mask"][:], excluded, f"{path}: log mask Set{s}")
            counts[s - 1] = excluded.sum(axis=0)
            valid_counts[s - 1] = valid[s].sum(axis=0)
            masked = values.astype(float)
            masked[overlap[s] >= 0.01] = np.nan
            masked[excluded] = np.nan
            output[s] = (masked, progress)
        rates = np.divide(
            counts, valid_counts, out=np.full((6, 32), np.nan), where=valid_counts > 0
        )
        for name, expected in (
            ("excluded_count", counts),
            ("valid_count", valid_counts),
            ("excluded_rate", rates),
        ):
            equal(handle[f"qc/log3sd_{name}_by_set_ch"][:], expected, f"{path}: {name}")
        report["caches"].append(
            {
                "path": str(path),
                "source_configuration_hash": str(handle.attrs["configuration_hash"]),
                "sets": sorted(output),
                "psd_windows": sum(len(values) for values in raw.values()),
                "phase1_excluded_windows": sum(
                    int(np.count_nonzero(values >= 0.01)) for values in overlap.values()
                ),
                "phase1_valid_positive_cells": int(valid_counts.sum()),
                "log3sd_excluded_cells": int(counts.sum()),
                "pz_valid_positive_windows": int(valid_counts[:, PZ].sum()),
                "pz_log3sd_excluded_windows": int(counts[:, PZ].sum()),
                "status": "passed",
            }
        )
    return output


def audit_group(items: list, root: Path, product: str, change: bool, report: dict) -> None:
    """Independent Pz quantification and 60-point/progress Grand-average."""
    stem, unit = root.name, "PSDChange_pct" if change else "PSD_uV2_per_Hz"
    selected = [
        (spec, sessions)
        for spec, sessions in items
        if source_engine.normalize_product(spec.product)[0] == product
    ]
    if not selected:
        raise ValueError(f"{stem}/{product}: no analysable participants")
    rows, grand = [], [[], []]
    for spec, sessions in selected:
        common = sessions[0].keys() & sessions[1].keys()
        curves = np.full((2, 6, 100), np.nan)
        for s in range(1, 7):
            means = [
                np.nanmean(session[s][0][:, PZ]) if s in common else np.nan
                for session in sessions
            ]
            rows.append(
                {
                    "PairID": spec.pair_id,
                    "Set": str(s),
                    f"EyeDrop_{unit}": means[0],
                    f"Control_{unit}": means[1],
                }
            )
            if s in common:
                for index, session in enumerate(sessions):
                    values, progress = session[s]
                    curves[index, s - 1] = smooth_interpolate(values[:, PZ], progress)
        pooled = [
            np.nanmean(np.concatenate([session[s][0][:, PZ] for s in sorted(common)]))
            for session in sessions
        ]
        rows.append(
            {
                "PairID": spec.pair_id,
                "Set": "All Sets",
                f"EyeDrop_{unit}": pooled[0],
                f"Control_{unit}": pooled[1],
            }
        )
        for index in range(2):
            grand[index].append(curves[index].ravel())
    tables = root / "Sub" / "tables"
    quant_directory = root / product / "SetQuantification"
    quant = pd.DataFrame(rows)
    tag = "Quantification" if change else "SetQuantification"
    compare_csv(
        tables / "SetQuantification" / f"{stem}_{tag}_Values_{product}.csv",
        quant,
        ["PairID", "Set"],
        report,
    )
    tested = []
    for set_name in [str(n) for n in range(1, 7)] + ["All Sets"]:
        frame = quant.loc[quant.Set == set_name]
        result = paired_test(
            frame[f"EyeDrop_{unit}"].to_numpy(), frame[f"Control_{unit}"].to_numpy()
        )
        tested.append({"Set": set_name, **result})
    overall, statistics = pd.DataFrame(tested[-1:]), pd.DataFrame(tested[:-1])
    if change:
        statistics.loc[0, statistics.columns != "Set"] = np.nan
        statistics.loc[0, "N"] = len(selected)
    finite = np.isfinite(statistics.P_value_raw.to_numpy())
    for method, column in (
        ("bonferroni", "P_value_Bonferroni"),
        ("holm", "P_value_Holm"),
        ("fdr_bh", "P_value_FDR_BH"),
    ):
        statistics[column] = np.nan
        if finite.any():
            statistics.loc[finite, column] = multipletests(
                statistics.loc[finite, "P_value_raw"], method=method
            )[1]
    compare_csv(
        quant_directory / f"{stem}_SetQuantification_Statistics_{product}.csv",
        statistics,
        ["Set"],
        report,
    )
    compare_csv(
        tables / "SetQuantification" / f"{stem}_AllSetsQuantification_Statistics_{product}.csv",
        overall,
        ["Set"],
        report,
    )
    ga = pd.DataFrame(
        {
            "Set": np.repeat(np.arange(1, 7), 100),
            "SetProgressPercent": np.tile(np.arange(100, dtype=float), 6),
            "GlobalProgressPercent": np.arange(600),
        }
    )
    for name, series in zip(("EyeDrop", "Control"), grand, strict=True):
        values = np.asarray(series)
        count = np.isfinite(values).sum(axis=0)
        mean, sd = np.nanmean(values, axis=0), np.nanstd(values, axis=0, ddof=1)
        ga[f"{name}_Mean_{unit}"], ga[f"{name}_SD_{unit}"] = mean, sd
        ga[f"{name}_SEM_{unit}"], ga[f"{name}_N"] = sd / np.sqrt(count), count
    compare_csv(
        tables / "GrandAverage" / f"{stem}_GrandAverage_Values_{product}.csv",
        ga,
        ["Set", "SetProgressPercent"],
        report,
    )
    report["groups"].append(
        {
            "analysis": stem,
            "focus_channel": "Pz",
            "product": product,
            "cohort": "AllAvailable",
            "pairs": len(selected),
            "set_paired_n": [int(item["Paired_N"]) for item in tested[:-1]],
            "all_sets_paired_n": int(overall.iloc[0].Paired_N),
            "all_sets_p_raw": float(overall.iloc[0].P_value_raw),
            "correction_family_tests": int(finite.sum()),
        }
    )


def expected_png_paths(root: Path, cohort: list, change: bool) -> set[Path]:
    expected = set()
    stem = root.name
    for product in PRODUCTS:
        for folder, name in (
            ("GrandAverage", "GrandAverage"),
            ("SetQuantification", "SetQuantification"),
            ("SetQuantification", "AllSetsQuantification"),
        ):
            expected.add(root / product / folder / f"{stem}_{name}_{product}.png")
    for spec, _ in cohort:
        product_root = root / source_engine.normalize_product(spec.product)[0]
        expected.add(product_root / "Individual" / f"ID{spec.pair_id}_{stem}_Individual.png")
        if not change:
            for stage in ("Before", "After"):
                expected.add(
                    product_root
                    / f"Individual/Unsmoothed/{stage}ThresholdExclusion"
                    / f"ID{spec.pair_id}_{stem}_Individual_Unsmoothed_{stage}ThresholdExclusion.png"
                )
    return expected


def additional_png_paths(root: Path) -> set[Path]:
    """Only the explicitly authorized 2026-11-14 supplement may coexist.

    Its numerical validation belongs to the separate sensitivity validator;
    these paths are never counted as part of the original 171 primary PNGs.
    """
    return {
        root / product / folder
        / f"{root.name}_{name}_{product}_SpecifiedPairsExcluded.png"
        for product in PRODUCTS
        for folder, name in (
            ("GrandAverage", "GrandAverage"),
            ("SetQuantification/SpecifiedPairsExcluded", "SetQuantification"),
            ("SetQuantification/SpecifiedPairsExcluded", "AllSetsQuantification"),
        )
    }


def primary_png_inventory(root: Path) -> tuple[set[Path], set[Path]]:
    actual = set(root.rglob("*.png"))
    authorized = additional_png_paths(root)
    supplement = actual & authorized
    if supplement and supplement != authorized:
        raise ValueError(f"{root.name}: incomplete specified-pair supplement")
    return actual - supplement, supplement


def audit_pngs(root: Path, cohort: list, change: bool, report: dict) -> None:
    expected = expected_png_paths(root, cohort, change)
    actual, supplement = primary_png_inventory(root)
    if actual != expected:
        raise ValueError(
            f"{root.name}: PNG inventory mismatch; missing={sorted(expected - actual)}; "
            f"unexpected={sorted(actual - expected)}"
        )
    forbidden = {"Topography"}
    forbidden_paths = [
        str(path) for path in root.rglob("*") if path.is_dir() and path.name in forbidden
    ]
    if forbidden_paths:
        raise ValueError(f"{root.name}: forbidden result folders: {forbidden_paths}")
    image_rows = []
    for path in sorted(expected):
        with Image.open(path) as image:
            dimensions = list(image.size)
            if image.format != "PNG" or min(dimensions) < 1000:
                raise ValueError(f"{path}: unexpected PNG format/dimensions")
            image.verify()
        image_rows.append(
            {
                "path": str(path),
                "size_pixels": dimensions,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    report["images"].extend(image_rows)
    report["png_counts"][root.name] = len(expected)
    report.setdefault("additional_png_counts_not_validated_here", {})[root.name] = len(supplement)


def run(args, report: dict) -> None:
    specs = source_engine.load_manifest(args.manifest)
    source_engine.validate_participant_specs(specs, production_batch=True)
    items, changed, baseline_rows = [], [], []
    for spec in specs:
        sessions = [
            reconstruct_masked_cache(
                source_engine.cache_path(args.cache_root, spec, sid), sid, report
            )
            for sid in (spec.drops_session_id, spec.control_session_id)
        ]
        items.append((spec, sessions))
        if not all(1 in session for session in sessions):
            continue
        converted = []
        for sid, condition, session in zip(
            (spec.drops_session_id, spec.control_session_id),
            ("Eye Drop", "Control"),
            sessions,
            strict=True,
        ):
            baseline = np.nanmean(session[1][0], axis=0)
            if not np.all(np.isfinite(baseline) & (baseline > np.finfo(float).tiny)):
                raise ValueError(f"{sid}: invalid Set 1 baseline")
            transformed = {
                s: ((value / baseline - 1) * 100, progress)
                for s, (value, progress) in session.items()
            }
            equal(np.nanmean(transformed[1][0], axis=0), np.zeros(32), "Set1 change zero")
            converted.append(transformed)
            baseline_rows.extend(
                {
                    "PairID": spec.pair_id,
                    "SessionID": sid,
                    "Condition": condition,
                    "Product": source_engine.normalize_product(spec.product)[0],
                    "Channel": ch,
                    "Set1Baseline_PSD_uV2_per_Hz": value,
                }
                for ch, value in zip(CHANNELS, baseline, strict=True)
            )
        changed.append((spec, converted))
    expected_caches = {
        source_engine.cache_path(args.cache_root, spec, sid).resolve()
        for spec in specs
        for sid in (spec.first_session_id, spec.second_session_id)
    }
    if {path.resolve() for path in args.cache_root.glob("*.h5")} != expected_caches:
        raise ValueError("Missing or extra source No10 cache files")
    subroot = args.output_root / "Phase4_脳波解析" / SUB_STEM
    compare_csv(
        subroot / "Sub/tables/Set1Baseline" / f"{SUB_STEM}_Set1Baseline_AllAnalysablePairs.csv",
        pd.DataFrame(baseline_rows),
        ["PairID", "SessionID", "Condition", "Product", "Channel"],
        report,
    )
    for stem, cohort, change in ((MAIN_STEM, items, False), (SUB_STEM, changed, True)):
        root = args.output_root / "Phase4_脳波解析" / stem
        for product in PRODUCTS:
            audit_group(cohort, root, product, change, report)
        audit_pngs(root, cohort, change, report)
    if (len(items), len(changed)) != (40, 39):
        raise ValueError("Unexpected full-production cohort size")
    if report["png_counts"] != {MAIN_STEM: 126, SUB_STEM: 45}:
        raise ValueError("Unexpected full-production PNG counts")
    report["main_pairs"], report["sub_pairs"] = len(items), len(changed)
    report["cache_count"] = len(report["caches"])
    report["available_sets"] = sum(len(item["sets"]) for item in report["caches"])
    report["arial_font"] = font_manager.findfont(
        font_manager.FontProperties(family="Arial"), fallback_to_default=False
    )
    report["status"] = "passed"


def validate_locations(args) -> None:
    if args.output_root.resolve() != source_engine.DEFAULT_OUTPUT_ROOT.resolve():
        raise ValueError("--output-root must be the authorized OneDrive result root")
    if args.cache_root.resolve() != source_engine.DEFAULT_CACHE_ROOT.resolve():
        raise ValueError("--cache-root must be the existing No10 PSDTimeSeries root")
    allowed = [
        args.output_root / "Phase4_脳波解析" / stem / "Sub/logs"
        for stem in (MAIN_STEM, SUB_STEM)
    ]
    if not any(args.report.resolve().is_relative_to(path.resolve()) for path in allowed):
        raise ValueError("--report must be within an authorized No11/main or sub Sub/logs")
    if args.report.suffix.lower() != ".json":
        raise ValueError("--report must be a JSON file")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=source_engine.DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=source_engine.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_locations(args)
    except ValueError as error:
        parser.error(str(error))
    report = {
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "scope": (
            "Read-only No10 saved-PSD reconstruction of masks, Pz baseline, centered "
            "60-point smoothing, Set progress, individual quantification, paired "
            "t tests with three corrections, Grand-average mean/SD/SEM/N and PNG "
            "integrity; no source-EEG Welch recalculation, rendering or visual QA"
        ),
        "focus_channel": "Pz",
        "included_frequencies_hz": [8, 9, 10],
        "caches": [],
        "tables": [],
        "groups": [],
        "images": [],
        "png_counts": {},
    }
    try:
        run(args, report)
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {key: report[key] for key in ("status", "main_pairs", "sub_pairs", "png_counts")},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
