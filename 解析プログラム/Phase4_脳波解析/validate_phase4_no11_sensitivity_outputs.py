#!/usr/bin/env python3
"""Independent audit of additive No11 Pz specified-pair-excluded outputs.

Reconstructs source masks, Pz baseline, smoothing, progress, quantification and
statistics from immutable No10 cache, without using production group builders.
Only the explicitly requested JSON report under No11 Sub/logs may be written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib import font_manager
from PIL import Image
from statsmodels.stats.multitest import multipletests
from validate_phase4_no10_outputs import compare_csv, equal, paired_test, smooth_interpolate
from validate_phase4_no11_outputs import (
    MAIN_STEM,
    PRODUCTS,
    PZ,
    SUB_STEM,
    expected_png_paths,
    reconstruct_masked_cache,
    source_engine,
)

SUFFIX = "SpecifiedPairsExcluded"
EXCLUDED = {
    "CCube": frozenset({"132-232", "140-240", "141-241"}),
    "VRohtoPremium": frozenset({"131-231"}),
}


def output_paths(root: Path, product: str) -> dict[str, Path]:
    """Independently fix paths; do not rely on the production filename builder."""
    stem = root.name
    table_root = root / "Sub/tables"
    quant = root / product / "SetQuantification" / SUFFIX
    quant_tables = table_root / "SetQuantification" / SUFFIX
    return {
        "grand_png": root
        / product
        / "GrandAverage"
        / f"{stem}_GrandAverage_{product}_{SUFFIX}.png",
        "grand_csv": table_root
        / "GrandAverage"
        / f"{stem}_GrandAverage_Values_{product}_{SUFFIX}.csv",
        "set_png": quant / f"{stem}_SetQuantification_{product}_{SUFFIX}.png",
        "all_png": quant / f"{stem}_AllSetsQuantification_{product}_{SUFFIX}.png",
        "set_stats": quant / f"{stem}_SetQuantification_Statistics_{product}_{SUFFIX}.csv",
        "all_stats": quant_tables
        / f"{stem}_AllSetsQuantification_Statistics_{product}_{SUFFIX}.csv",
        "values": quant_tables / f"{stem}_Quantification_Values_{product}_{SUFFIX}.csv",
    }


def expected_tables(items: list, product: str, change: bool) -> dict[str, pd.DataFrame]:
    """Rebuild participant-level and aggregate values, including paired missingness."""
    unit = "PSDChange_pct" if change else "PSD_uV2_per_Hz"
    selected = [
        (spec, sessions)
        for spec, sessions in items
        if source_engine.normalize_product(spec.product)[0] == product
        and spec.pair_id not in EXCLUDED[product]
    ]
    if not selected:
        raise ValueError("No remaining participants")
    rows, grand = [], [[], []]
    for spec, sessions in selected:
        common = sessions[0].keys() & sessions[1].keys()
        curves = np.full((2, 6, 100), np.nan)
        for s in range(1, 7):
            means = [
                np.nanmean(session[s][0][:, PZ]) if s in common else np.nan for session in sessions
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
                for condition, session in enumerate(sessions):
                    values, progress = session[s]
                    curves[condition, s - 1] = smooth_interpolate(values[:, PZ], progress)
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
        for condition in range(2):
            grand[condition].append(curves[condition].ravel())
    quant = pd.DataFrame(rows)
    tested = []
    for set_name in [str(s) for s in range(1, 7)] + ["All Sets"]:
        frame = quant.loc[quant.Set == set_name]
        tested.append(
            {
                "Set": set_name,
                **paired_test(
                    frame[f"EyeDrop_{unit}"].to_numpy(), frame[f"Control_{unit}"].to_numpy()
                ),
            }
        )
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
    ga = pd.DataFrame(
        {
            "Set": np.repeat(np.arange(1, 7), 100),
            "SetProgressPercent": np.tile(np.arange(100, dtype=float), 6),
            "GlobalProgressPercent": np.arange(600),
        }
    )
    for name, series in zip(("EyeDrop", "Control"), grand, strict=True):
        values = np.asarray(series)
        n = np.isfinite(values).sum(axis=0)
        mean, sd = np.nanmean(values, axis=0), np.nanstd(values, axis=0, ddof=1)
        ga[f"{name}_Mean_{unit}"], ga[f"{name}_SD_{unit}"] = mean, sd
        ga[f"{name}_SEM_{unit}"], ga[f"{name}_N"] = sd / np.sqrt(n), n
    return {"values": quant, "set_stats": statistics, "all_stats": overall, "grand_csv": ga}


def grand_axis(frames: list[pd.DataFrame], change: bool) -> tuple[list[float], np.ndarray]:
    """Reimplement documented No1/No1_sub common-axis rules independently."""
    if change:
        maximum = max(
            float(np.nanmax(np.abs(frame[f"{cond}_Mean_PSDChange_pct"])))
            for frame in frames
            for cond in ("EyeDrop", "Control")
        )
        raw = max(maximum / 0.70, 1.0)
        exponent = math.floor(math.log10(raw))
        limit = min(
            m * 10.0**e
            for e in range(exponent - 2, exponent + 2)
            for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 8.5, 9, 10)
            if m * 10.0**e >= raw
        )
        choices = []
        for e in range(exponent - 2, exponent + 2):
            for m in (1, 2, 2.5, 4, 5, 10):
                step = m * 10.0**e
                ticks = np.arange(
                    math.ceil(-limit / step) * step,
                    math.floor(limit / step) * step + step * 0.01,
                    step,
                )
                if 3 <= len(ticks) <= 7 and np.any(np.isclose(ticks, 0)):
                    choices.append((abs(len(ticks) - 5), step, ticks))
        ticks = (
            min(choices, key=lambda x: (x[0], x[1]))[2]
            if choices
            else np.linspace(-limit, limit, 5)
        )
        return [-float(limit), float(limit)], ticks

    def upper(values):
        raw = max(float(np.nanmax(values)) / 0.75, np.finfo(float).eps)
        exponent, choices = math.floor(math.log10(raw)), []
        for e in range(exponent - 2, exponent + 2):
            for m in (1, 2, 2.5, 5):
                step = m * 10.0**e
                limit = math.ceil(raw / step) * step
                ticks = np.arange(0, limit + step * 0.01, step)
                if 3 <= len(ticks) <= 6:
                    choices.append((abs(len(ticks) - 5), limit, ticks))
        if not choices:
            return raw, np.linspace(0, raw, 5)
        _, limit, ticks = min(choices, key=lambda x: (x[0], x[1]))
        return limit, ticks

    proposed = [
        upper(
            np.concatenate(
                [
                    frame[f"{cond}_Mean_PSD_uV2_per_Hz"].to_numpy()
                    + frame[f"{cond}_SEM_PSD_uV2_per_Hz"].fillna(0).to_numpy()
                    for cond in ("EyeDrop", "Control")
                ]
            )
        )
        for frame in frames
    ]
    maximum = max(item[0] for item in proposed)
    _, ticks = upper(np.array([maximum * 0.75]))
    if ticks[-1] != maximum:
        step = ticks[1] - ticks[0]
        ticks = np.arange(0, maximum + step * 0.01, step)
    return [0.0, float(maximum)], ticks


def quant_axis(frame: pd.DataFrame, change: bool, all_sets: bool) -> list[float]:
    unit = "PSDChange_pct" if change else "PSD_uV2_per_Hz"
    frame = frame.loc[(frame.Set == "All Sets") if all_sets else (frame.Set != "All Sets")]
    values = frame[[f"EyeDrop_{unit}", f"Control_{unit}"]].to_numpy().ravel()
    values = values[np.isfinite(values)]
    if change:
        reference = max(float(values.max()), 2 * abs(min(float(values.min()), 0)) / 1.54, 1)
        return [-1.54 * reference / 2, 1.54 * reference]
    maximum = max(float(values.max()), np.finfo(float).eps)
    return [0.0, 1.37 * maximum]


def audit_plot_metadata(execution: dict, expected: dict[str, tuple], report: dict) -> None:
    plots = execution["plots"]
    actual = {item["path"]: item for item in plots}
    if len(actual) != len(plots) or set(actual) != set(expected):
        raise ValueError("Plot metadata path inventory mismatch")
    for path, (ylim, panels, yticks) in expected.items():
        plot = actual[path]
        if plot["font_families"] != ["Arial"]:
            raise ValueError(f"{path}: non-Arial figure text")
        if plot["sha256"] != hashlib.sha256(Path(path).read_bytes()).hexdigest():
            raise ValueError(f"{path}: figure changed after artist metadata capture")
        if plot["panel_count"] != panels or len(plot["axes"]) != panels:
            raise ValueError(f"{path}: wrong panel count")
        for axis in plot["axes"]:
            equal(axis["ylim"], ylim, f"{path}: recomputed y limits")
            if yticks is not None:
                equal(axis["yticks"], yticks, f"{path}: recomputed y ticks")
            elif not 3 <= len(axis["yticks"]) <= 6:
                raise ValueError(f"{path}: quantification requires 3–6 ticks")
        report["plot_metadata"].append(
            {"path": path, "ylim": ylim, "panels": panels, "status": "passed"}
        )


def audit_preservation(
    execution: dict, expected_primary: set[Path], expected_caches: set[Path], report: dict
) -> None:
    """Check saved pre-run fingerprints without regenerating or repairing outputs."""
    before = execution["protected_before"]
    primary = before["primary_no11"]
    caches = before["source_cache"]
    if not {str(path.resolve()) for path in expected_primary} <= set(primary):
        raise ValueError("Primary PNG fingerprint snapshot incomplete")
    if set(caches) != {str(path.resolve()) for path in expected_caches}:
        raise ValueError("Source cache fingerprint snapshot incomplete")
    checked = {}
    for category, rows in before.items():
        for name, fingerprint in rows.items():
            path = Path(name)
            stat = path.stat()
            if stat.st_size != fingerprint["size"] or stat.st_mtime_ns != fingerprint["mtime_ns"]:
                raise ValueError(f"Protected file metadata changed: {path}")
            if "sha256" in fingerprint:
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != fingerprint["sha256"]:
                    raise ValueError(f"Protected file contents changed: {path}")
        checked[category] = {
            "files": len(rows),
            "status": "unchanged",
            "check": "SHA256+size+mtime" if category != "other_analyses" else "size+mtime",
        }
    report["preservation"] = checked


def audit_cohort_selection(path: Path, specs: list, change: bool, report: dict) -> None:
    actual = pd.read_csv(
        path, dtype={"PairID": str, "EyeDropSessionID": str, "ControlSessionID": str}
    )
    if len(actual) != len(specs) or actual.PairID.duplicated().any():
        raise ValueError(f"{path}: expected one cohort decision per manifest pair")
    actual = actual.set_index("PairID")
    if set(actual.index) != {spec.pair_id for spec in specs}:
        raise ValueError("Cohort selection manifest mismatch")
    for spec in specs:
        row = actual.loc[spec.pair_id]
        product = source_engine.normalize_product(spec.product)[0]
        baseline = not change or not any(
            1 in source_engine.EXPECTED_MISSING_SETS.get(sid, set())
            for sid in (spec.drops_session_id, spec.control_session_id)
        )
        excluded = spec.pair_id in EXCLUDED[product]
        for name, expected in (
            ("Product", product),
            ("EyeDropSessionID", spec.drops_session_id),
            ("ControlSessionID", spec.control_session_id),
            ("PrimaryAnalysisEligible", baseline),
            ("SpecifiedPairExcluded", excluded),
            ("Included", baseline and not excluded),
        ):
            if row[name] != expected:
                raise ValueError(f"{path}: {spec.pair_id} {name} mismatch")
        if not isinstance(row.Reason, str) or not row.Reason.strip():
            raise ValueError("Missing cohort decision reason")
    report["tables"].append({"path": str(path), "rows": len(actual), "status": "passed"})


def run(args, report: dict) -> None:
    for key in ("caches", "tables", "groups", "images", "plot_metadata"):
        report.setdefault(key, [])
    report.setdefault("png_counts", {})
    specs = source_engine.load_manifest(args.manifest)
    source_engine.validate_participant_specs(specs, production_batch=True)
    by_product = {
        product: {
            spec.pair_id
            for spec in specs
            if source_engine.normalize_product(spec.product)[0] == product
        }
        for product in PRODUCTS
    }
    if any(not EXCLUDED[product] <= by_product[product] for product in PRODUCTS):
        raise ValueError("Specified exclusion is absent or in the wrong product")
    items, changed = [], []
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
        for session in sessions:
            baseline = np.nanmean(session[1][0], axis=0)
            if not np.all(np.isfinite(baseline) & (baseline > np.finfo(float).tiny)):
                raise ValueError("Invalid baseline")
            transformed = {
                s: ((values / baseline - 1) * 100, progress)
                for s, (values, progress) in session.items()
            }
            equal(np.nanmean(transformed[1][0], axis=0), np.zeros(32), "Set 1 change zero")
            converted.append(transformed)
        changed.append((spec, converted))
    expected_cache_paths = {
        source_engine.cache_path(args.cache_root, spec, sid).resolve()
        for spec in specs
        for sid in (spec.first_session_id, spec.second_session_id)
    }
    if {path.resolve() for path in args.cache_root.glob("*.h5")} != expected_cache_paths:
        raise ValueError("Missing or extra source No10 cache files")
    all_pngs, primary_pngs, plot_expectations = set(), set(), {}
    for stem, cohort, change in ((MAIN_STEM, items, False), (SUB_STEM, changed, True)):
        root = args.output_root / "Phase4_脳波解析" / stem
        tables = {product: expected_tables(cohort, product, change) for product in PRODUCTS}
        grand_ylim, grand_ticks = grand_axis(
            [entry["grand_csv"] for entry in tables.values()], change
        )
        added_pngs = set()
        for product in PRODUCTS:
            paths, frames = output_paths(root, product), tables[product]
            for key, keys in (
                ("values", ["PairID", "Set"]),
                ("set_stats", ["Set"]),
                ("all_stats", ["Set"]),
                ("grand_csv", ["Set", "SetProgressPercent"]),
            ):
                compare_csv(paths[key], frames[key], keys, report)
            for key, ylim, panels, ticks in (
                ("grand_png", grand_ylim, 1, grand_ticks),
                ("set_png", quant_axis(frames["values"], change, False), 6, None),
                ("all_png", quant_axis(frames["values"], change, True), 1, None),
            ):
                added_pngs.add(paths[key])
                plot_expectations[str(paths[key])] = (ylim, panels, ticks)
            quant = frames["values"]
            group = {
                "analysis": stem,
                "product": product,
                "cohort": SUFFIX,
                "pairs": int(quant.PairID.nunique()),
                "set_paired_n": [
                    int(quant.loc[quant.Set == str(s)].dropna().shape[0]) for s in range(1, 7)
                ],
                "all_sets_paired_n": int(frames["all_stats"].iloc[0].Paired_N),
                "all_sets_p_raw": float(frames["all_stats"].iloc[0].P_value_raw),
                "correction_family_tests": int(frames["set_stats"].P_value_raw.notna().sum()),
                "grand_ylim": grand_ylim,
            }
            unit = "PSDChange_pct" if change else "PSD_uV2_per_Hz"
            group["sem_points_outside_ylim"] = {
                condition: int(
                    np.count_nonzero(
                        (
                            frames["grand_csv"][f"{condition}_Mean_{unit}"]
                            + frames["grand_csv"][f"{condition}_SEM_{unit}"]
                            > grand_ylim[1]
                        )
                        | (
                            frames["grand_csv"][f"{condition}_Mean_{unit}"]
                            - frames["grand_csv"][f"{condition}_SEM_{unit}"]
                            < grand_ylim[0]
                        )
                    )
                )
                for condition in ("EyeDrop", "Control")
            }
            report["groups"].append(group)
        audit_cohort_selection(
            root / "Sub/tables" / f"{stem}_{SUFFIX}_CohortSelection.csv", specs, change, report
        )
        original = expected_png_paths(root, cohort, change)
        primary_pngs |= original
        expected = original | added_pngs
        actual = set(root.rglob("*.png"))
        if actual != expected:
            raise ValueError(
                f"{stem}: PNG inventory mismatch: missing={expected - actual}, "
                f"extra={actual - expected}"
            )
        all_pngs |= added_pngs
        report["png_counts"][stem] = {
            "primary": len(expected - added_pngs),
            "additional": len(added_pngs),
        }
    for path in sorted(all_pngs):
        with Image.open(path) as image:
            if image.format != "PNG" or min(image.size) < 1000:
                raise ValueError(f"{path}: invalid PNG")
            dimensions = list(image.size)
            image.verify()
        report["images"].append(
            {
                "path": str(path),
                "size_pixels": dimensions,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    if [(g["pairs"], g["all_sets_paired_n"]) for g in report["groups"]] != [
        (17, 17),
        (19, 19),
        (17, 17),
        (18, 18),
    ]:
        raise ValueError("Unexpected sensitivity cohort size")
    if len(report["tables"]) != 18 or len(report["images"]) != 12:
        raise ValueError("Unexpected sensitivity output count")
    execution = json.loads(args.execution_report.read_text(encoding="utf-8"))
    audit_plot_metadata(execution, plot_expectations, report)
    audit_preservation(execution, primary_pngs, expected_cache_paths, report)
    report["main_pairs"], report["sub_pairs"] = 36, 35
    report["cache_count"] = len(report["caches"])
    report["arial_font"] = font_manager.findfont(
        font_manager.FontProperties(family="Arial"), fallback_to_default=False
    )
    report["status"] = "passed"


def validate_locations(args) -> None:
    if args.output_root.resolve() != source_engine.DEFAULT_OUTPUT_ROOT.resolve():
        raise ValueError("Expected authorized OneDrive output root")
    if args.cache_root.resolve() != source_engine.DEFAULT_CACHE_ROOT.resolve():
        raise ValueError("Expected immutable No10 cache root")
    allowed = args.output_root / "Phase4_脳波解析" / MAIN_STEM / "Sub/logs"
    for path in (args.report, args.execution_report):
        if not path.resolve().is_relative_to(allowed.resolve()) or path.suffix != ".json":
            raise ValueError("Audit JSON must be within No11 Sub/logs")
    if args.report.resolve() == args.execution_report.resolve():
        raise ValueError("Audit cannot overwrite the execution report")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, default=source_engine.DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=source_engine.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--execution-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    validate_locations(args)
    report = {
        "status": "running",
        "created_at": datetime.now().astimezone().isoformat(),
        "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        "focus_channel": "Pz",
        "frequencies_hz": [8, 9, 10],
        "cohort": SUFFIX,
        "caches": [],
        "tables": [],
        "groups": [],
        "images": [],
        "png_counts": {},
        "plot_metadata": [],
        "scope": (
            "Saved-PSD numerical reconstruction and PNG integrity; "
            "no raw EEG Welch or visual inspection"
        ),
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
