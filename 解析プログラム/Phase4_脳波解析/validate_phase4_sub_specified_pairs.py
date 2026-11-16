#!/usr/bin/env python3
"""Independent read-back audit of No1/2/2-2/3 sub sensitivity outputs.

No production analysis module is imported. Reconstruct the representative-channel
change, 60-point smoothing, finite-run interpolation, paired statistics and three
corrections from the original immutable PSD cache. No PSD is recomputed. Only an
explicit report destination under the authorised OneDrive Sub/logs can be written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
from PIL import Image
from scipy import stats
from statsmodels.stats.multitest import multipletests

REPO = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = Path(
    "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/"
    "SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_本解析"
)
CACHE_PHASE = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/Phase4_脳波解析"
)
SUFFIX = "SpecifiedPairsExcluded"
ANALYSES = {
    "No1_sub": ("No1_sub_FmThetaChange", "No1_FmTheta", "FmTheta", "Fz", (4, 7)),
    "No2_sub": (
        "No2_sub_OccipitalAlphaChange",
        "No2_OccipitalAlpha",
        "OccipitalAlpha",
        "Oz",
        (8, 15),
    ),
    "No2-2_sub": (
        "No2-2_sub_OccipitalAlphaChange_Pz",
        "No2_OccipitalAlpha",
        "OccipitalAlpha",
        "Pz",
        (8, 15),
    ),
    "No3_sub": ("No3_sub_FrontalDeltaChange", "No3_FrontalDelta", "FrontalDelta", "Fz", (1, 3)),
}
PRODUCTS = ("CCube", "VRohtoPremium")


def sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def canonical_exclusions(path: Path) -> dict[str, dict[str, set[str]]]:
    """Read the authorised current exception table, without a second ID list."""
    text = path.read_text()
    heading = "## Phase 4 sub被験者除外の現行指定（2026-11-16）"
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    result = {}
    for name in ANALYSES:
        rows = [row for row in section.splitlines() if row.startswith(f"| {name}（")]
        if len(rows) != 1:
            raise ValueError(f"Ambiguous exclusion row for {name}")
        fields = rows[0].split("|")
        result[name] = {}
        for product, field in (("VRohtoPremium", fields[2]), ("CCube", fields[3])):
            result[name][product] = {
                f"{first}-{second}" for first, second in re.findall(r"(\d+)\s*[–−-]\s*(\d+)", field)
            }
    return result


def equal(actual, expected, label: str) -> None:
    np.testing.assert_allclose(
        actual, expected, rtol=1e-8, atol=1e-8, equal_nan=True, err_msg=label
    )


def compare_csv(path: Path, expected: pd.DataFrame, keys: list[str], report: dict) -> None:
    actual = pd.read_csv(path, dtype={key: str for key in keys})
    expected = expected.copy()
    for key in keys:
        expected[key] = expected[key].astype(str)
    actual, expected = [frame.set_index(keys).sort_index() for frame in (actual, expected)]
    pd.testing.assert_index_equal(actual.index, expected.index)
    for column in expected:
        equal(actual[column].to_numpy(float), expected[column].to_numpy(float), f"{path}: {column}")
    report["tables"].append({"path": str(path), "rows": len(expected), "sha256": sha256(path)})


def read_session(path: Path, row: dict, sid: str, channel: str, band: tuple) -> dict:
    """Read only the selected ch; apply persisted masks in the specified order."""
    with h5py.File(path, "r") as handle:
        pair = f"{row['first_session_id']}-{row['second_session_id']}"
        condition = "Eye Drop" if sid == row["drops_session_id"] else "Control"
        for name, expected in (
            ("participant_id", sid),
            ("pair_id", pair),
            ("condition", condition),
            ("product", row["product"]),
            ("fmin_hz", band[0]),
            ("fmax_hz", band[1]),
            ("sampling_frequency_hz", 256),
            ("step_samples", 256),
            ("time_smoothing", "none"),
        ):
            if handle.attrs[name] != expected:
                raise ValueError(f"{path}: {name} differs")
        names = handle["signal/channel_names"].asstr()[:].tolist()
        if len(names) != 32 or names.count(channel) != 1:
            raise ValueError(f"{path}: invalid channel names")
        ch = names.index(channel)
        result = {}
        for key, group in handle["sets"].items():
            number = int(key.removeprefix("Set"))
            values = group["psd_band_mean"][:, ch].astype(float)
            values[group["ica_training_mask_fraction"][:] >= 0.01] = np.nan
            values[group["log3sd_outlier_mask"][:, ch].astype(bool)] = np.nan
            progress = group["set_progress_pct"][:]
            samples = group["source_center_sample"][:]
            equal(progress, 100 * samples / (group.attrs["source_n_samples"] - 1), "progress")
            result[number] = (values, progress)
        return result


def make_change(session: dict) -> dict:
    baseline = float(np.nanmean(session[1][0]))
    if not np.isfinite(baseline) or baseline <= 0:
        raise ValueError("Invalid Set 1 baseline")
    output = {
        number: ((values / baseline - 1) * 100, progress)
        for number, (values, progress) in session.items()
    }
    equal(np.nanmean(output[1][0]), 0, "Set 1 change")
    return output


def smooth_interpolate(values: np.ndarray, progress: np.ndarray) -> np.ndarray:
    """Independent centred 60-point nanmean via convolution, finite-run interp."""
    finite = np.isfinite(values)
    sums = np.convolve(np.where(finite, values, 0), np.ones(60), "full")[29 : 29 + len(values)]
    counts = np.convolve(finite.astype(float), np.ones(60), "full")[29 : 29 + len(values)]
    smooth = np.divide(sums, counts, out=np.full(len(values), np.nan), where=counts > 0)
    indices = np.flatnonzero(np.isfinite(smooth))
    target, result = np.arange(100, dtype=float), np.full(100, np.nan)
    for run in np.split(indices, np.flatnonzero(np.diff(indices) > 1) + 1):
        if run.size == 1:
            result[np.isclose(target, progress[run[0]])] = smooth[run[0]]
        elif run.size > 1:
            inside = (target >= progress[run[0]]) & (target <= progress[run[-1]])
            result[inside] = np.interp(target[inside], progress[run], smooth[run])
    return result


def paired_test(eye: np.ndarray, control: np.ndarray) -> dict:
    valid = np.isfinite(eye) & np.isfinite(control)
    differences = eye[valid] - control[valid]
    n = len(differences)
    mean = float(differences.mean()) if n > 1 else np.nan
    sd = float(differences.std(ddof=1)) if n > 1 else np.nan
    t, p, dz, margin = np.nan, np.nan, np.nan, np.nan
    if n > 1:
        if sd == 0:
            t, p, dz = (
                (0.0, 1.0, 0.0)
                if mean == 0
                else (np.sign(mean) * np.inf, 0.0, np.sign(mean) * np.inf)
            )
        else:
            t = mean / (sd / np.sqrt(n))
            p, dz = 2 * stats.t.sf(abs(t), n - 1), mean / sd
        margin = stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)
    return {
        "Paired_N": n,
        "T_statistic": t,
        "Degrees_of_freedom": max(n - 1, 0),
        "P_value_raw": p,
        "Mean_difference_EyeDrop_minus_Control": mean,
        "Difference_SD": sd,
        "Difference_CI95_lower": mean - margin,
        "Difference_CI95_upper": mean + margin,
        "Cohen_dz": dz,
    }


def expected_tables(items: list[tuple[str, list[dict]]]) -> dict[str, pd.DataFrame]:
    rows, curves = [], [[], []]
    for pair, sessions in items:
        common = sessions[0].keys() & sessions[1].keys()
        pair_curves = np.full((2, 6, 100), np.nan)
        for number in range(1, 7):
            row = {"PairID": pair, "Set": str(number)}
            for index, label in enumerate(("EyeDrop", "Control")):
                row[f"{label}_PSDChange_pct"] = (
                    np.nanmean(sessions[index][number][0]) if number in common else np.nan
                )
                if number in common:
                    pair_curves[index, number - 1] = smooth_interpolate(*sessions[index][number])
            rows.append(row)
        pooled = {"PairID": pair, "Set": "All Sets"}
        for index, label in enumerate(("EyeDrop", "Control")):
            pooled[f"{label}_PSDChange_pct"] = np.nanmean(
                np.concatenate([sessions[index][s][0] for s in sorted(common)])
            )
            curves[index].append(pair_curves[index].ravel())
        rows.append(pooled)
    quant = pd.DataFrame(rows)
    tests = []
    for name in [str(i) for i in range(1, 7)] + ["All Sets"]:
        frame = quant.loc[quant.Set == name]
        result = paired_test(
            frame.EyeDrop_PSDChange_pct.to_numpy(), frame.Control_PSDChange_pct.to_numpy()
        )
        tests.append({"Set": name, **result})
    set_stats, all_stats = pd.DataFrame(tests[:-1]), pd.DataFrame(tests[-1:])
    set_stats.loc[0, set_stats.columns != "Set"] = np.nan
    set_stats["N"] = np.nan
    set_stats.loc[0, "N"] = len(items)
    for method, column in (
        ("bonferroni", "P_value_Bonferroni"),
        ("holm", "P_value_Holm"),
        ("fdr_bh", "P_value_FDR_BH"),
    ):
        set_stats[column] = np.nan
        set_stats.loc[1:, column] = multipletests(set_stats.loc[1:, "P_value_raw"], method=method)[
            1
        ]
    grand = pd.DataFrame(
        {
            "Set": np.repeat(np.arange(1, 7), 100),
            "SetProgressPercent": np.tile(np.arange(100, dtype=float), 6),
            "GlobalProgressPercent": np.arange(600),
        }
    )
    for label, arrays in zip(("EyeDrop", "Control"), curves, strict=True):
        matrix = np.asarray(arrays)
        n = np.isfinite(matrix).sum(axis=0)
        mean, sd = np.nanmean(matrix, axis=0), np.nanstd(matrix, axis=0, ddof=1)
        grand[f"{label}_Mean_PSDChange_pct"] = mean
        grand[f"{label}_SD_PSDChange_pct"] = sd
        grand[f"{label}_SEM_PSDChange_pct"] = sd / np.sqrt(n)
        grand[f"{label}_N"] = n
    return {"values": quant, "set_stats": set_stats, "all_stats": all_stats, "grand": grand}


def output_paths(root: Path, product: str) -> dict[str, Path]:
    stem = root.name
    quant = root / product / "SetQuantification" / SUFFIX
    tables = root / "Sub/tables/SetQuantification"
    return {
        "grand": root
        / "Sub/tables/GrandAverage"
        / f"{stem}_GrandAverage_Values_{product}_{SUFFIX}.csv",
        "values": tables / f"{stem}_Quantification_Values_{product}_{SUFFIX}.csv",
        "set_stats": quant / f"{stem}_SetQuantification_Statistics_{product}_{SUFFIX}.csv",
        "all_stats": tables / f"{stem}_AllSetsQuantification_Statistics_{product}_{SUFFIX}.csv",
        "grand_png": root
        / product
        / "GrandAverage"
        / f"{stem}_GrandAverage_{product}_{SUFFIX}.png",
        "set_png": quant / f"{stem}_SetQuantification_{product}_{SUFFIX}.png",
        "all_png": quant / f"{stem}_AllSetsQuantification_{product}_{SUFFIX}.png",
    }


def grand_axis(frames: list[pd.DataFrame]) -> tuple[float, np.ndarray]:
    maximum = max(
        float(np.nanmax(np.abs(frame[f"{condition}_Mean_PSDChange_pct"])))
        for frame in frames
        for condition in ("EyeDrop", "Control")
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
    for exponent_delta in range(exponent - 2, exponent + 2):
        for multiplier in (1, 2, 2.5, 4, 5, 10):
            step = multiplier * 10.0**exponent_delta
            ticks = np.arange(
                math.ceil(-limit / step) * step, math.floor(limit / step) * step + step * 0.01, step
            )
            if 3 <= len(ticks) <= 7 and np.any(np.isclose(ticks, 0)):
                choices.append((abs(len(ticks) - 5), step, ticks))
    ticks = (
        min(choices, key=lambda x: (x[0], x[1]))[2] if choices else np.linspace(-limit, limit, 5)
    )
    return limit, ticks


def audit_scoped_record(root: Path, record: dict, products: set[str],
                        verified_hashes: dict[str, str]) -> None:
    """Independently check the limited-write contract and unchanged-product bytes."""
    requested = record.get("requested_product")
    if requested is None:
        return
    if requested not in products or record.get("regenerated_products") != [requested]:
        raise ValueError("Scoped regeneration product differs")
    others = products - {requested}
    axis_only = set(record["axis_only_refreshed_products"])
    if not axis_only.issubset(others) or set(record["shared_axis_products"]) != products:
        raise ValueError("Scoped shared-axis products differ")
    if not record.get("strict_run_scope_unchanged"):
        raise ValueError("Strict within-run scope protection is missing")
    record_path = root / "Sub/logs" / f"{root.name}_{SUFFIX}_RunSummary.json"
    selection = (root / "Sub/tables/SetQuantification"
                 / f"{root.name}_CohortSelection_{SUFFIX}.csv")
    allowed = {str(record_path), str(selection)}
    allowed.update(str(path) for path in output_paths(root, requested).values())
    allowed.update(str(output_paths(root, p)["grand_png"]) for p in axis_only)
    if set(record["allowed_write_paths"]) != allowed:
        raise ValueError("Scoped allowed paths differ from the exact output contract")
    generated = {row["path"]: row["sha256"] for row in record["generated_output_files"]}
    if set(generated) != allowed - {str(record_path)}:
        raise ValueError("Scoped generated-file list differs")
    for filename, fingerprint in generated.items():
        if sha256(Path(filename)) != fingerprint:
            raise ValueError("Scoped generated artifact changed")
    preserved = {str(path) for p in others for name, path in output_paths(root, p).items()
                 if not (p in axis_only and name == "grand_png")}
    if set(record["preserved_product_artifacts"]) != preserved:
        raise ValueError("Unrequested-product preservation list is incomplete")
    for filename, before in record["preserved_product_artifacts"].items():
        path = Path(filename)
        if not path.is_file() or path.stat().st_size != before["size"]:
            raise ValueError("Unrequested-product file missing or size changed")
        verified_hashes[filename] = sha256(path)
        if verified_hashes[filename] != before["sha256"]:
            raise ValueError("Unrequested-product bytes changed")
    provenance = record["preserved_product_provenance"]
    if set(provenance) != others or any(
        not entry.get("version") or not entry.get("code_hashes")
        or not entry.get("previous_run_summary_sha256") for entry in provenance.values()
    ):
        raise ValueError("Preserved-product numerical provenance is missing")
    archive = record["previous_nonpng_archive"]
    archive_path = Path(archive["manifest"])
    if (not archive_path.resolve().is_relative_to((root / "Sub/history").resolve())
            or sha256(archive_path) != archive["sha256"]):
        raise ValueError("Previous-run archive manifest mismatch")
    archived = json.loads(archive_path.read_text())
    if archived["analysis_stem"] != root.name or archived["products"] != [requested]:
        raise ValueError("Previous-run archive scope differs")
    if len(archived["files"]) != archive["file_count"]:
        raise ValueError("Previous-run archive count differs")
    for row in archived["files"]:
        path = Path(row["archived_to"])
        if (not path.resolve().is_relative_to(archive_path.parent.resolve())
                or path.suffix == ".png" or sha256(path) != row["sha256"]):
            raise ValueError("Previous-run archive bytes/scope differ")
    if not archive["reused"]:
        original_record = next(row for row in archived["files"] if row["old"] == str(record_path))
        if original_record["sha256"] != record["previous_run_summary_sha256"]:
            raise ValueError("Previous execution record archive differs")


def audit_execution(
    root: Path,
    expected_groups: dict,
    excluded: dict,
    report: dict,
    verified_hashes: dict[str, str],
) -> None:
    """Read back saved metadata: cohort, paired N, axis rules and font placement."""
    record_path = root / "Sub/logs" / f"{root.name}_{SUFFIX}_RunSummary.json"
    record = json.loads(record_path.read_text())
    if record.get("topography_modified") is not False or not record.get("protected_unchanged"):
        raise ValueError("Production preservation checks are not confirmed")
    audit_scoped_record(root, record, set(expected_groups), verified_hashes)
    # Independently re-read preserved output and cache bytes, not just the runner flag.
    for filename, before in record["protected_before"].items():
        path = Path(filename)
        if not path.is_file() or path.stat().st_size != before["size"]:
            raise ValueError(f"Protected file missing or size changed: {path}")
        if filename not in verified_hashes:
            verified_hashes[filename] = sha256(path)
        if verified_hashes[filename] != before["sha256"]:
            raise ValueError(f"Protected file bytes changed: {path}")
    for source in record["source_cache"]:
        filename = source["path"]
        if filename not in verified_hashes:
            verified_hashes[filename] = sha256(Path(filename))
        if verified_hashes[filename] != source["sha256"]:
            raise ValueError(f"PSD cache changed: {filename}")
    expected_limit, expected_ticks = grand_axis([x["grand"] for x in expected_groups.values()])
    plots = {x["path"]: x for x in record["plots"]}
    if len(plots) != 3 * len(expected_groups):
        raise ValueError("Unexpected number of recorded figures")
    for product, expected in expected_groups.items():
        paths = output_paths(root, product)
        quant = expected["values"]
        group = record["outputs"][product]
        if set(group["retained_pair_ids"]) != set(quant.PairID):
            raise ValueError("Recorded included cohort differs")
        if set(group["excluded_pair_ids"]) != excluded[product]:
            raise ValueError("Recorded excluded cohort differs")
        equal(group["grand_y_limit"], expected_limit, "Grand-average shared axis limit")
        equal(group["grand_y_ticks"], expected_ticks, "Grand-average shared ticks")
        for kind in ("grand_png", "set_png", "all_png"):
            plot = plots[str(paths[kind])]
            if plot["font_families"] != ["Arial"]:
                raise ValueError("Figure font family differs from Arial")
            if sha256(paths[kind]) != plot["sha256"]:
                raise ValueError("Figure differs from captured drawing metadata")
            if kind == "grand_png":
                equal(plot["axes"][0]["ylim"], [-expected_limit, expected_limit], "Grand axis")
                equal(plot["axes"][0]["yticks"], expected_ticks, "Grand ticks")
                continue
            subset = quant.loc[
                (quant.Set == "All Sets") if kind == "all_png" else (quant.Set != "All Sets")
            ]
            values = subset[["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]].to_numpy().ravel()
            values = values[np.isfinite(values)]
            reference = max(float(values.max()), 2 * abs(min(float(values.min()), 0)) / 1.54, 1)
            if len(plot["axes"]) != (1 if kind == "all_png" else 6):
                raise ValueError("Wrong quantification panel count")
            for axis in plot["axes"]:
                equal(axis["ylim"], [-1.54 * reference / 2, 1.54 * reference], "Quant axis")
                if not 3 <= len(axis["yticks"]) <= 6:
                    raise ValueError("Quantification tick count outside specification")
                for text in axis["texts"]:
                    label = text["text"]
                    if label.startswith("Set ") or label == "All Sets":
                        equal(text["position"][1], 1.42 * reference, "Set label position")
                        equal(text["fontsize"], 26, "Set label font size")
                    elif label == "n.s.":
                        equal(text["position"][1], 1.20 * reference, "n.s. position")
                        equal(text["fontsize"], 26, "n.s. font size")
                    elif label and set(label) == {"*"}:
                        equal(text["position"][1], 1.08 * reference, "Star position")
                        equal(text["fontsize"], 42, "Star font size")
    report.setdefault("execution_records", []).append(
        {
            "path": str(record_path),
            "cohort_and_axes": "passed",
            "independent_protection_hashes": "passed",
            "protected_output_files": len(record["protected_before"]),
            "protected_source_cache_files": len(record["source_cache"]),
        }
    )


def run_audit(manifest: Path, analyses: list[str], *, source_only: bool = False) -> dict:
    frame = pd.read_csv(manifest, dtype=str)
    if len(frame) != 40 or frame.first_session_id.nunique() != 40:
        raise ValueError("Expected the full 40-pair manifest")
    if frame.groupby("product").size().to_dict() != {p: 20 for p in PRODUCTS}:
        raise ValueError("Unexpected manifest product balance")
    exclusions = canonical_exclusions(REPO / "docs/解析上の注意事項.md")
    report = {
        "method": "independent immutable cache reconstruction",
        "timestamp": datetime.now().astimezone().isoformat(),
        "tables": [],
        "images": [],
        "groups": [],
        "manifest_sha256": sha256(manifest),
    }
    verified_hashes: dict[str, str] = {}
    for analysis in analyses:
        stem, cache_stem, tag, channel, band = ANALYSES[analysis]
        root, cache = (
            OUTPUT_ROOT / "Phase4_脳波解析" / stem,
            CACHE_PHASE / cache_stem / "PSDTimeSeries",
        )
        items = {product: [] for product in PRODUCTS}
        baseline_missing = []
        for row in frame.to_dict("records"):
            pair = f"{row['first_session_id']}-{row['second_session_id']}"
            sessions = {}
            for order, field in ((1, "first_session_id"), (2, "second_session_id")):
                sid = row[field]
                path = cache / f"Pair{pair}_{order:02d}_ID{sid}_{tag}_AllChannelsPSD.h5"
                sessions[sid] = read_session(path, row, sid, channel, band)
            if any(1 not in session for session in sessions.values()):
                baseline_missing.append(pair)
                continue
            eye = row["drops_session_id"]
            control = next(sid for sid in sessions if sid != eye)
            items[row["product"]].append(
                (pair, [make_change(sessions[eye]), make_change(sessions[control])])
            )
        if len(baseline_missing) != 1:
            raise ValueError("Expected one existing baseline-missing pair")
        expected_groups = {}
        for product in PRODUCTS:
            # Original saved participant quantities are a second independent checkpoint.
            expected_main = expected_tables(items[product])
            main_path = (
                root
                / "Sub/tables/SetQuantification"
                / f"{stem}_Quantification_Values_{product}.csv"
            )
            compare_csv(main_path, expected_main["values"], ["PairID", "Set"], report)
            main_grand_path = (
                root / "Sub/tables/GrandAverage" / f"{stem}_GrandAverage_Values_{product}.csv"
            )
            compare_csv(
                main_grand_path, expected_main["grand"], ["Set", "SetProgressPercent"], report
            )
            excluded = exclusions[analysis][product]
            if not excluded:
                if output_paths(root, product)["grand_png"].exists():
                    raise ValueError("Unexpected duplicate no-exclusion Grand-average")
                continue
            if not excluded.issubset({pair for pair, _ in items[product]}):
                raise ValueError("Specified exclusions not in the baseline-eligible product cohort")
            selected = [item for item in items[product] if item[0] not in excluded]
            expected = expected_tables(selected)
            expected_groups[product] = expected
            paths = output_paths(root, product)
            if not source_only:
                for name, keys in (
                    ("grand", ["Set", "SetProgressPercent"]),
                    ("values", ["PairID", "Set"]),
                    ("set_stats", ["Set"]),
                    ("all_stats", ["Set"]),
                ):
                    compare_csv(paths[name], expected[name], keys, report)
                for name in ("grand_png", "set_png", "all_png"):
                    with Image.open(paths[name]) as image:
                        image.load()
                        if image.width < 1000 or image.height < 500:
                            raise ValueError(f"Unexpected image resolution: {paths[name]}")
                        report["images"].append(
                            {
                                "path": str(paths[name]),
                                "pixels": image.size,
                                "sha256": sha256(paths[name]),
                            }
                        )
            n_by_set = (
                expected["values"]
                .groupby("Set")
                .apply(
                    lambda x: int(
                        (
                            np.isfinite(x.EyeDrop_PSDChange_pct)
                            & np.isfinite(x.Control_PSDChange_pct)
                        ).sum()
                    ),
                    include_groups=False,
                )
                .to_dict()
            )
            means = (
                expected["values"]
                .groupby("Set")[["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]]
                .mean()
            )
            sem = (
                expected["values"]
                .groupby("Set")[["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]]
                .sem(ddof=1)
            )
            main_all = expected_main["values"].loc[
                expected_main["values"].Set == "All Sets",
                ["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"],
            ]
            report["groups"].append(
                {
                    "analysis": analysis,
                    "product": product,
                    "remaining_pairs": len(selected),
                    "paired_n": n_by_set,
                    "mean_values": means.to_dict("index"),
                    "sem_values": sem.to_dict("index"),
                    "main_all_sets": {
                        "N": len(main_all),
                        "mean": main_all.mean().to_dict(),
                        "SEM": main_all.sem(ddof=1).to_dict(),
                        "p_raw": float(expected_main["all_stats"].P_value_raw.iloc[0]),
                    },
                    "set_p_raw": expected["set_stats"].P_value_raw.tolist(),
                    "all_sets_p_raw": float(expected["all_stats"].P_value_raw.iloc[0]),
                    "baseline_missing_pairs_count": len(baseline_missing),
                }
            )
        if not source_only:
            audit_execution(root, expected_groups, exclusions[analysis], report, verified_hashes)
    if not source_only:
        report["independent_protection"] = {
            "status": "passed",
            "unique_verified_files": len(verified_hashes),
            "scope": "existing protected output and source-cache bytes; no added-file claim",
        }
    report["status"] = "source_checked" if source_only else "passed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--analysis", action="append", choices=list(ANALYSES))
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.report:
        destination = args.report.resolve()
        if (
            not destination.is_relative_to(OUTPUT_ROOT.resolve())
            or "Sub/logs" not in destination.as_posix()
        ):
            raise ValueError("Reports must remain in authorised OneDrive Sub/logs")
    report = run_audit(args.manifest, args.analysis or list(ANALYSES), source_only=args.source_only)
    # Replace unavailable baseline statistics with standard JSON null, not NaN.
    encoded = json.dumps(report, ensure_ascii=False, indent=2)
    encoded = re.sub(r"\bNaN\b", "null", encoded)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(encoded)
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
