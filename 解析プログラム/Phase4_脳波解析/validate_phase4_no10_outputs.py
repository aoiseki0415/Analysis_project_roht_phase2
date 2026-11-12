#!/usr/bin/env python3
"""Independently audit No10/main + sub caches and numerical output tables.

Read-only except for the explicitly requested JSON report. PSD generation is
covered by the independent SciPy Welch unit test; this audit starts with every
saved, unsmoothed, pre-exclusion 32-channel PSD cache. It never regenerates data.
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
from Phase4_No10_FzLowAlpha import engine
from PIL import Image
from scipy import stats
from statsmodels.stats.multitest import multipletests

SUB_STEM = "No10_sub_FzLowAlphaChange"
CHANNELS = engine.EXPECTED_CHANNEL_NAMES
FZ = CHANNELS.index("Fz")


def equal(actual, expected, label: str) -> None:
    np.testing.assert_allclose(
        actual, expected, rtol=1e-8, atol=1e-8, equal_nan=True, err_msg=label
    )


def compare_csv(path: Path, expected: pd.DataFrame, keys: list[str], report: dict) -> None:
    actual = pd.read_csv(path, dtype={key: str for key in keys})
    expected = expected.copy()
    for key in keys:
        expected[key] = expected[key].astype(str)
    actual, expected = (frame.set_index(keys).sort_index() for frame in (actual, expected))
    pd.testing.assert_index_equal(actual.index, expected.index)
    for column in expected:
        equal(actual[column].to_numpy(float), expected[column].to_numpy(float), f"{path}: {column}")
    report["tables"].append({"path": str(path), "rows": len(expected), "status": "passed"})


def read_cache(path: Path, sid: str, report: dict) -> dict:
    engine.validate_cache(path)  # Source fingerprints, manifest identity, numerical configuration.
    with h5py.File(path, "r") as handle:
        for key, expected in {
            "participant_id": sid,
            "sampling_frequency_hz": 256,
            "fmin_hz": 8,
            "fmax_hz": 11,
            "step_samples": 256,
            "n_fft": 256,
            "n_per_seg": 256,
            "n_overlap": 0,
            "time_smoothing": "none",
        }.items():
            if handle.attrs[key] != expected:
                raise ValueError(f"{path}: {key} mismatch")
        groups = {int(name[3:]): group for name, group in handle["sets"].items()}
        if set(range(1, 7)) - groups.keys() != engine.EXPECTED_MISSING_SETS.get(sid, set()):
            raise ValueError(f"{path}: unexpected missing set")
        raw = {s: group["psd_band_mean"][:] for s, group in groups.items()}
        overlap = {s: group["ica_training_mask_fraction"][:] for s, group in groups.items()}
        if any(np.any((value < 0) | (value > 1)) for value in overlap.values()):
            raise ValueError(f"{path}: invalid Phase 1 overlap fraction")
        valid = {s: np.isfinite(x) & (x > 0) & (overlap[s][:, None] < 0.01) for s, x in raw.items()}
        moments = np.full((2, 32), np.nan)
        for ch in range(32):
            values = np.concatenate([x[valid[s][:, ch], ch] for s, x in sorted(raw.items())])
            if values.size >= 2:
                logged = np.log10(values)  # Preserve the cache's float32 transform semantics.
                moments[:, ch] = np.mean(logged), np.std(logged, ddof=1)
        threshold = moments[0] + 3 * moments[1]
        for name, value in (
            ("mean", moments[0]),
            ("sd", moments[1]),
            ("threshold_log", threshold),
            ("threshold_linear", 10.0**threshold),
        ):
            equal(handle[f"qc/log3sd_{name}_by_channel"][:], value, f"{path}: {name}")
        counts, valid_counts = np.zeros((6, 32), int), np.zeros((6, 32), int)
        output = {}
        for s, x in raw.items():
            group = groups[s]
            centers = group["source_center_sample"][:]
            n_samples = int(group.attrs["source_n_samples"])
            expected_centers = np.unique(np.r_[np.arange(0, n_samples, 256), n_samples - 1])
            equal(centers, expected_centers, f"{path}: centers Set{s}")
            progress = centers / (n_samples - 1) * 100.0
            equal(group["set_progress_pct"][:], progress, f"{path}: progress Set{s}")
            equal(group["relative_seconds_center"][:], centers / 256, f"{path}: time Set{s}")
            equal(
                group["global_progress_pct"][:], progress + (s - 1) * 100, f"{path}: global Set{s}"
            )
            logged = np.full(x.shape, np.nan)
            logged[valid[s]] = np.log10(x[valid[s]])
            excluded = valid[s] & (logged > threshold)
            equal(group["log3sd_outlier_mask"][:], excluded, f"{path}: log mask Set{s}")
            counts[s - 1], valid_counts[s - 1] = excluded.sum(axis=0), valid[s].sum(axis=0)
            masked = x.astype(float)
            masked[overlap[s] >= 0.01] = np.nan
            masked[excluded] = np.nan
            output[s] = (masked, progress)
        rates = np.divide(
            counts, valid_counts, out=np.full((6, 32), np.nan), where=valid_counts > 0
        )
        for name, value in (
            ("excluded_count", counts),
            ("valid_count", valid_counts),
            ("excluded_rate", rates),
        ):
            equal(handle[f"qc/log3sd_{name}_by_set_ch"][:], value, f"{path}: {name}")
        report["caches"].append(
            {
                "path": str(path),
                "sets": sorted(output),
                "psd_windows": sum(len(values) for values in raw.values()),
                "phase1_excluded_windows": sum(
                    int(np.count_nonzero(values >= 0.01)) for values in overlap.values()
                ),
                "phase1_valid_positive_cells": int(valid_counts.sum()),
                "log3sd_excluded_cells": int(counts.sum()),
                "status": "passed",
            }
        )
    return output


def smooth_interpolate(values: np.ndarray, progress: np.ndarray) -> np.ndarray:
    """Centered 60-point nanmean, then interpolation within finite runs only."""
    finite = np.isfinite(values)
    numerator = np.convolve(np.where(finite, values, 0.0), np.ones(60), "full")[
        29 : 29 + len(values)
    ]
    count = np.convolve(finite.astype(float), np.ones(60), "full")[29 : 29 + len(values)]
    smooth = np.divide(numerator, count, out=np.full(len(values), np.nan), where=count > 0)
    finite_indices = np.flatnonzero(np.isfinite(smooth))
    result, target = np.full(100, np.nan), np.arange(100, dtype=float)
    for run in np.split(finite_indices, np.where(np.diff(finite_indices) > 1)[0] + 1):
        if not run.size:
            continue
        if run.size == 1:
            matching = np.isclose(target, progress[run[0]])
            result[matching] = smooth[run[0]]
        else:
            inside = (target >= progress[run[0]]) & (target <= progress[run[-1]])
            result[inside] = np.interp(target[inside], progress[run], smooth[run])
    return result


def paired_test(eye: np.ndarray, control: np.ndarray) -> dict:
    valid = np.isfinite(eye) & np.isfinite(control)
    difference = eye[valid] - control[valid]
    n = len(difference)
    mean = float(difference.mean()) if n > 1 else np.nan
    sd = float(difference.std(ddof=1)) if n > 1 else np.nan
    t, p, dz, margin = np.nan, np.nan, np.nan, np.nan
    if n > 1:
        if sd == 0:
            t, p, dz = (
                (0.0, 1.0, 0.0)
                if mean == 0
                else (np.sign(mean) * np.inf, 0.0, np.sign(mean) * np.inf)
            )
        else:
            test = stats.ttest_rel(eye[valid], control[valid])
            t, p, dz = test.statistic, test.pvalue, mean / sd
        margin = stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)
    return {
        "Paired_N": n,
        "T_statistic": t,
        "Degrees_of_freedom": max(0, n - 1),
        "P_value_raw": p,
        "Mean_difference_EyeDrop_minus_Control": mean,
        "Difference_SD": sd,
        "Difference_CI95_lower": mean - margin,
        "Difference_CI95_upper": mean + margin,
        "Cohen_dz": dz,
    }


def audit_group(items: list, root: Path, product: str, change: bool, report: dict) -> None:
    stem, unit = root.name, "PSDChange_pct" if change else "PSD_uV2_per_Hz"
    selected = [
        (spec, sessions)
        for spec, sessions in items
        if engine.normalize_product(spec.product)[0] == product
    ]
    rows, topographies, grand = [], [], [[], []]
    for spec, sessions in selected:
        common = sessions[0].keys() & sessions[1].keys()
        topo, curves = np.full((6, 32), np.nan), np.full((2, 6, 100), np.nan)
        for s in range(1, 7):
            means = [
                np.nanmean(session[s][0], axis=0) if s in common else np.full(32, np.nan)
                for session in sessions
            ]
            rows.append(
                {
                    "PairID": spec.pair_id,
                    "Set": str(s),
                    f"EyeDrop_{unit}": means[0][FZ],
                    f"Control_{unit}": means[1][FZ],
                }
            )
            topo[s - 1] = means[0] - means[1]
            if s in common:
                for i, session in enumerate(sessions):
                    values, progress = session[s]
                    curves[i, s - 1] = smooth_interpolate(values[:, FZ], progress)
        pooled = [
            np.nanmean(np.concatenate([session[s][0][:, FZ] for s in sorted(common)]))
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
        topographies.append(topo)
        for i in range(2):
            grand[i].append(curves[i].ravel())
    tables = root / "Sub" / "tables"
    quant = pd.DataFrame(rows)
    tag = "Quantification" if change else "SetQuantification"
    compare_csv(
        tables / "SetQuantification" / f"{stem}_{tag}_Values_{product}.csv",
        quant,
        ["PairID", "Set"],
        report,
    )
    tested = []
    for s in [str(n) for n in range(1, 7)] + ["All Sets"]:
        frame = quant.loc[quant.Set == s]
        result = paired_test(
            frame[f"EyeDrop_{unit}"].to_numpy(), frame[f"Control_{unit}"].to_numpy()
        )
        tested.append({"Set": s, **result})
    overall = pd.DataFrame(tested[-1:])
    statistics = pd.DataFrame(tested[:-1])
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
        statistics.loc[finite, column] = multipletests(
            statistics.loc[finite, "P_value_raw"], method=method
        )[1]
    compare_csv(
        root / product / "SetQuantification" / f"{stem}_SetQuantification_Statistics_{product}.csv",
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
    for name, values in zip(("EyeDrop", "Control"), grand, strict=True):
        values = np.asarray(values)
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
    topographies = np.stack(topographies)
    paired_valid = np.isfinite(topographies).all(axis=2)
    channel_n = np.isfinite(topographies).sum(axis=0)
    common_n = paired_valid.sum(axis=0)
    channel_n_difference = channel_n - common_n[:, None]
    values = np.full((6, 32), np.nan)
    for s in range(6):
        if paired_valid[:, s].any():
            values[s] = topographies[paired_valid[:, s], s].mean(axis=0)
    topo = pd.DataFrame(values, columns=CHANNELS)
    topo.insert(0, "Set", np.arange(1, 7))
    topo.insert(1, "Valid_N", paired_valid.sum(axis=0))
    compare_csv(
        tables / "Topography" / f"{stem}_Topography_GrandAverage_Values_{product}.csv",
        topo,
        ["Set"],
        report,
    )
    report["groups"].append(
        {
            "analysis": stem,
            "product": product,
            "pairs": len(selected),
            "topography_n_by_set": common_n.tolist(),
            "topography_channel_names": CHANNELS,
            "topography_channel_n_by_set": channel_n.tolist(),
            "topography_channel_n_differs_from_common": bool(np.any(channel_n_difference)),
            "topography_channel_n_max_difference": int(channel_n_difference.max()),
        }
    )


def run(args, report: dict) -> None:
    specs = engine.load_manifest(args.manifest)
    engine.validate_participant_specs(specs, production_batch=True)
    items, changed, baseline_rows = [], [], []
    for spec in specs:
        sessions = [
            read_cache(engine.cache_path(args.cache_root, spec, sid), sid, report)
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
                raise ValueError("Invalid Set1 baseline")
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
                    "Product": engine.normalize_product(spec.product)[0],
                    "Channel": ch,
                    "Set1Baseline_PSD_uV2_per_Hz": value,
                }
                for ch, value in zip(CHANNELS, baseline, strict=True)
            )
        changed.append((spec, converted))
    expected_caches = {
        engine.cache_path(args.cache_root, spec, sid).resolve()
        for spec in specs
        for sid in (spec.first_session_id, spec.second_session_id)
    }
    if {path.resolve() for path in args.cache_root.glob("*.h5")} != expected_caches:
        raise ValueError("Missing or extra cache files")
    subroot = args.output_root / "Phase4_脳波解析" / SUB_STEM
    compare_csv(
        subroot / "Sub/tables/Set1Baseline" / f"{SUB_STEM}_Set1Baseline_AllAnalysablePairs.csv",
        pd.DataFrame(baseline_rows),
        ["PairID", "SessionID", "Condition", "Product", "Channel"],
        report,
    )
    for stem, cohort, change in ((engine.ANALYSIS_STEM, items, False), (SUB_STEM, changed, True)):
        root = args.output_root / "Phase4_脳波解析" / stem
        expected_png = set()
        for product in sorted({engine.normalize_product(spec.product)[0] for spec, _ in cohort}):
            audit_group(cohort, root, product, change, report)
            for folder, name in (
                ("GrandAverage", "GrandAverage"),
                ("SetQuantification", "SetQuantification"),
                ("SetQuantification", "AllSetsQuantification"),
                ("Topography/GrandAverage", "Topography_GrandAverage"),
            ):
                expected_png.add(root / product / folder / f"{stem}_{name}_{product}.png")
        for spec, _ in cohort:
            product_root = root / engine.normalize_product(spec.product)[0]
            expected_png.add(
                product_root / "Individual" / f"ID{spec.pair_id}_{stem}_Individual.png"
            )
            expected_png.add(
                product_root / "Topography/Individual" / f"ID{spec.pair_id}_{stem}_Topography.png"
            )
            if not change:
                for stage in ("Before", "After"):
                    expected_png.add(
                        product_root
                        / f"Individual/Unsmoothed/{stage}ThresholdExclusion"
                        / (
                            f"ID{spec.pair_id}_{stem}_Individual_Unsmoothed_"
                            f"{stage}ThresholdExclusion.png"
                        )
                    )
        if set(root.rglob("*.png")) != expected_png:
            raise ValueError(f"{stem}: missing or unexpected PNG filenames")
        for path in sorted(expected_png):
            with Image.open(path) as image:
                image.verify()
        report["png_counts"][stem] = len(expected_png)
    report["main_pairs"], report["sub_pairs"] = len(items), len(changed)
    report["cache_count"] = len(report["caches"])
    report["available_sets"] = sum(len(item["sets"]) for item in report["caches"])
    report["arial_font"] = font_manager.findfont(
        font_manager.FontProperties(family="Arial"), fallback_to_default=False
    )
    phase_root = args.output_root / "Phase4_脳波解析"
    console = phase_root / engine.ANALYSIS_STEM / "Sub/logs/ProductionConsole_20261112.log"
    started = console.stat().st_birthtime
    siblings = [
        path
        for folder in phase_root.iterdir()
        if folder.is_dir() and folder.name not in (engine.ANALYSIS_STEM, SUB_STEM)
        for path in folder.rglob("*")
        if path.suffix.lower() in (".png", ".csv", ".json")
    ]
    modified = [str(path) for path in siblings if path.stat().st_mtime > started]
    report["existing_result_write_check"] = {
        "files_checked": len(siblings),
        "modified_since_console_creation": modified,
        "scope": "mtime check only; not a pre-run content-hash comparison",
        "reference_console": str(console),
        "reference_birthtime": started,
    }
    if modified:
        raise ValueError("Existing sibling result files were modified during this run")
    report["status"] = "passed"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=engine.DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=engine.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    allowed = [
        args.output_root / "Phase4_脳波解析" / stem / "Sub/logs"
        for stem in (engine.ANALYSIS_STEM, SUB_STEM)
    ]
    if not any(args.report.resolve().is_relative_to(path.resolve()) for path in allowed):
        parser.error("--report must be inside a No10/main or sub Sub/logs directory")
    report = {
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "scope": (
            "Independent saved-PSD numerical audit; "
            "no raw EEG recomputation or visual interpretation"
        ),
        "caches": [],
        "tables": [],
        "groups": [],
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
