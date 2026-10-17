#!/usr/bin/env python3
"""Draw PSD-Change Grand-average topographies after condition-wise QC.

This sensitivity analysis reuses the validated Phase 4 PSD caches.  It does
not recompute Welch PSD and does not overwrite the primary No1_sub-No3_sub
figures.  Abnormality is judged separately in Eye Drop and Control sessions;
the paired comparison cell is then removed when either condition is flagged.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import warnings
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import Phase4_No1_FmTheta as phase4
import Phase4_No1_sub_FmThetaChange as change
import Phase4_PSDChange500OutlierExcludedTopography as common

SCRIPT_VERSION = "phase4-psd-change-conditionwise-bidirectional-qc-2026-10-17.3"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SUPPLEMENTAL_ANALYSIS_DIR = "補足分析（被験者除外あり）"
BLOCK_SECONDS = 60.0
EPS = np.finfo(float).tiny
MAD_NORMAL_CONSISTENCY = 1.4826

# Direction 1: high absolute Set-1 PSD.
SET1_LOG_ROBUST_Z = 4.5
SET1_COHORT_FACTOR = 2.5
SET1_NEIGHBOR_FACTOR = 2.0

# Direction 2a: sustained positive change.
POSITIVE_LOG_ROBUST_Z = 3.5
POSITIVE_MEDIAN_RATIO = 2.5
POSITIVE_Q75_RATIO = 3.0
POSITIVE_CENTRAL_OCCUPANCY = 0.50
POSITIVE_UPPER_OCCUPANCY = 0.40
POSITIVE_MIN_CONSECUTIVE_BLOCKS = 2

# Direction 2b: sustained negative change corroborated by low absolute PSD.
NEGATIVE_ABSOLUTE_LOG_ROBUST_Z = -4.0
NEGATIVE_COHORT_FACTOR = 0.35
NEGATIVE_NEIGHBOR_FACTOR = 0.45
NEGATIVE_MEDIAN_RATIO = 0.30
NEGATIVE_BLOCK_RATIO = 0.50
NEGATIVE_OCCUPANCY = 0.60
NEGATIVE_MIN_CONSECUTIVE_BLOCKS = 2

DEFAULT_PHASE4_CACHE_ROOT = common.DEFAULT_PHASE4_CACHE_ROOT
DEFAULT_OUTPUT_ROOT = common.DEFAULT_OUTPUT_ROOT
ANALYSES = common.ANALYSES

QUALITATIVE_REVIEW = {
    "No1": {
        "CCube": (
            "Major isolated channel peaks were reduced; the remaining pattern is "
            "predominantly broad and spatially continuous."
        ),
        "VRohtoPremium": (
            "The later-Set positive field is broad rather than a single-electrode peak; "
            "no dominant isolated channel remains."
        ),
    },
    "No2": {
        "CCube": (
            "The negative field is broadly distributed and the original isolated extremes "
            "are reduced."
        ),
        "VRohtoPremium": (
            "Large isolated extremes are reduced, but peripheral alternating red/blue "
            "structure remains; interpretation should remain cautious."
        ),
    },
    "No3": {
        "CCube": (
            "The prior focal F4 Set-4 peak is reduced; some local structure remains but no "
            "longer reflects that single dominant contributor."
        ),
        "VRohtoPremium": (
            "The later-Set field forms a broad anterior-positive/posterior-negative "
            "gradient rather than a single-electrode extreme."
        ),
    },
}


@dataclass(frozen=True)
class MethodParameters:
    block_seconds: float = BLOCK_SECONDS
    set1_log_robust_z: float = SET1_LOG_ROBUST_Z
    set1_cohort_factor: float = SET1_COHORT_FACTOR
    set1_neighbor_factor: float = SET1_NEIGHBOR_FACTOR
    positive_log_robust_z: float = POSITIVE_LOG_ROBUST_Z
    positive_median_ratio: float = POSITIVE_MEDIAN_RATIO
    positive_q75_ratio: float = POSITIVE_Q75_RATIO
    positive_central_occupancy: float = POSITIVE_CENTRAL_OCCUPANCY
    positive_upper_occupancy: float = POSITIVE_UPPER_OCCUPANCY
    positive_min_consecutive_blocks: int = POSITIVE_MIN_CONSECUTIVE_BLOCKS
    negative_absolute_log_robust_z: float = NEGATIVE_ABSOLUTE_LOG_ROBUST_Z
    negative_cohort_factor: float = NEGATIVE_COHORT_FACTOR
    negative_neighbor_factor: float = NEGATIVE_NEIGHBOR_FACTOR
    negative_median_ratio: float = NEGATIVE_MEDIAN_RATIO
    negative_block_ratio: float = NEGATIVE_BLOCK_RATIO
    negative_occupancy: float = NEGATIVE_OCCUPANCY
    negative_min_consecutive_blocks: int = NEGATIVE_MIN_CONSECUTIVE_BLOCKS


PARAMETERS = MethodParameters()


def repository_commit() -> str:
    """Return the checked-out commit so external audit logs remain traceable."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPOSITORY_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except OSError, subprocess.CalledProcessError:
        return "unavailable"
    return result.stdout.strip()


def robust_z(values: np.ndarray, *, log10: bool) -> np.ndarray:
    """Return median/MAD robust z, optionally after log10 transformation."""
    values = np.asarray(values, dtype=float)
    result = np.full(values.shape, np.nan, dtype=float)
    valid = np.isfinite(values)
    if log10:
        valid &= values > EPS
    if valid.sum() < 8:
        return result
    transformed = np.log10(values[valid]) if log10 else values[valid]
    center = float(np.median(transformed))
    mad = float(np.median(np.abs(transformed - center)))
    scale = MAD_NORMAL_CONSISTENCY * mad
    if not np.isfinite(scale) or scale <= np.finfo(float).eps:
        return result
    result[valid] = (transformed - center) / scale
    return result


def longest_run(mask: np.ndarray) -> int:
    maximum = current = 0
    for value in np.asarray(mask, dtype=bool):
        if value:
            current += 1
            maximum = max(maximum, current)
        else:
            current = 0
    return maximum


def block_medians(set_psd: phase4.SetPSD) -> np.ndarray:
    values = np.asarray(set_psd.psd_band_mean, dtype=float)
    times = np.asarray(set_psd.relative_seconds_center, dtype=float)
    if values.ndim != 2 or times.shape != (values.shape[0],):
        raise ValueError("Unexpected PSD cache shape")
    block_index = np.floor((times - times[0]) / BLOCK_SECONDS).astype(int)
    medians: list[np.ndarray] = []
    for index in np.unique(block_index):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            medians.append(np.nanmedian(values[block_index == index], axis=0))
    return np.vstack(medians)


def neighbor_factors(values: np.ndarray) -> np.ndarray:
    output = np.full(values.shape, np.nan, dtype=float)
    for channel_index, nearest in enumerate(common.spatial_neighbor_indices()):
        neighbors = values[np.asarray(nearest, dtype=int)]
        neighbors = neighbors[np.isfinite(neighbors) & (neighbors > EPS)]
        if neighbors.size and np.isfinite(values[channel_index]):
            local_median = float(np.median(neighbors))
            if local_median > EPS:
                output[channel_index] = values[channel_index] / local_median
    return output


def collect_metrics(
    config: common.AnalysisConfig, cache_base: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build condition-wise Set-1 and Set2-6 metrics from saved PSD caches."""
    cache_root = cache_base / config.cache_root_name / "PSDTimeSeries"
    items = common.load_items(cache_root)
    set1_rows: list[dict[str, Any]] = []
    set_rows: list[dict[str, Any]] = []

    for item in items:
        for condition, change_session in (
            ("Eye Drop", item["eye_drop"]),
            ("Control", item["control"]),
        ):
            session = change_session.source
            set1_absolute = np.nanmedian(session.sets[1].psd_band_mean, axis=0)
            set1_rows.append(
                {
                    "pair_id": item["spec"].pair_id,
                    "session_id": session.session_id,
                    "condition": condition,
                    "product": item["product_dir"],
                    "absolute": set1_absolute,
                    "neighbor_factor": neighbor_factors(set1_absolute),
                }
            )
            for set_number in range(2, phase4.N_SETS + 1):
                set_psd = session.sets.get(set_number)
                if set_psd is None:
                    continue
                absolute = np.nanmedian(set_psd.psd_band_mean, axis=0)
                block_ratio = block_medians(set_psd) / set1_absolute[None, :]
                positive_mask = block_ratio >= 2.0
                negative_mask = block_ratio <= NEGATIVE_BLOCK_RATIO
                set_rows.append(
                    {
                        "pair_id": item["spec"].pair_id,
                        "session_id": session.session_id,
                        "condition": condition,
                        "product": item["product_dir"],
                        "set": set_number,
                        "absolute": absolute,
                        "neighbor_factor": neighbor_factors(absolute),
                        "median_ratio": np.nanmedian(block_ratio, axis=0),
                        "q75_ratio": np.nanpercentile(block_ratio, 75, axis=0),
                        "fraction_ge2": np.nanmean(positive_mask, axis=0),
                        "longest_ge2": np.asarray(
                            [
                                longest_run(positive_mask[:, i])
                                for i in range(positive_mask.shape[1])
                            ]
                        ),
                        "fraction_low": np.nanmean(negative_mask, axis=0),
                        "longest_low": np.asarray(
                            [
                                longest_run(negative_mask[:, i])
                                for i in range(negative_mask.shape[1])
                            ]
                        ),
                    }
                )

    set1_matrix = np.stack([row["absolute"] for row in set1_rows])
    set1_median = np.nanmedian(set1_matrix, axis=0)
    for channel_index in range(set1_matrix.shape[1]):
        scores = robust_z(set1_matrix[:, channel_index], log10=True)
        for row_index, row in enumerate(set1_rows):
            row.setdefault("absolute_z", np.full(set1_matrix.shape[1], np.nan))[channel_index] = (
                scores[row_index]
            )
            row.setdefault("cohort_factor", np.full(set1_matrix.shape[1], np.nan))[
                channel_index
            ] = row["absolute"][channel_index] / set1_median[channel_index]

    for set_number in range(2, phase4.N_SETS + 1):
        selected = [row for row in set_rows if row["set"] == set_number]
        for key in ("absolute", "median_ratio", "q75_ratio"):
            matrix = np.stack([row[key] for row in selected])
            cohort_median = np.nanmedian(matrix, axis=0)
            for channel_index in range(matrix.shape[1]):
                scores = robust_z(matrix[:, channel_index], log10=True)
                for row_index, row in enumerate(selected):
                    row.setdefault(f"{key}_z", np.full(matrix.shape[1], np.nan))[channel_index] = (
                        scores[row_index]
                    )
                    row.setdefault(f"{key}_factor", np.full(matrix.shape[1], np.nan))[
                        channel_index
                    ] = matrix[row_index, channel_index] / cohort_median[channel_index]
    return items, set1_rows, set_rows


def evaluate_flags(
    config: common.AnalysisConfig,
    set1_rows: list[dict[str, Any]],
    set_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[tuple[str, int, int], list[dict[str, str]]]]:
    """Judge each condition, then form a paired OR exclusion mask."""
    channels = phase4.EXPECTED_CHANNEL_NAMES
    flags: list[dict[str, Any]] = []
    causes: dict[tuple[str, int, int], list[dict[str, str]]] = defaultdict(list)

    for row in set1_rows:
        for channel_index, channel in enumerate(channels):
            flagged = (
                row["absolute_z"][channel_index] > SET1_LOG_ROBUST_Z
                and row["cohort_factor"][channel_index] >= SET1_COHORT_FACTOR
                and row["neighbor_factor"][channel_index] >= SET1_NEIGHBOR_FACTOR
            )
            if not flagged:
                continue
            flag = {
                "analysis": config.key,
                "pair_id": row["pair_id"],
                "session_id": row["session_id"],
                "condition": row["condition"],
                "product": row["product"],
                "set": 1,
                "channel": channel,
                "reason": "Set1AbsoluteHigh",
                "set1_absolute_psd": row["absolute"][channel_index],
                "set1_log_robust_z": row["absolute_z"][channel_index],
                "set1_cohort_factor": row["cohort_factor"][channel_index],
                "set1_neighbor_factor": row["neighbor_factor"][channel_index],
            }
            flags.append(flag)
            for set_number in range(2, phase4.N_SETS + 1):
                causes[(row["pair_id"], set_number, channel_index)].append(
                    {
                        "condition": row["condition"],
                        "session_id": row["session_id"],
                        "reason": flag["reason"],
                    }
                )

    for row in set_rows:
        for channel_index, channel in enumerate(channels):
            positive_central = (
                row["median_ratio_z"][channel_index] > POSITIVE_LOG_ROBUST_Z
                and row["median_ratio"][channel_index] >= POSITIVE_MEDIAN_RATIO
                and row["fraction_ge2"][channel_index] >= POSITIVE_CENTRAL_OCCUPANCY
                and row["longest_ge2"][channel_index] >= POSITIVE_MIN_CONSECUTIVE_BLOCKS
            )
            positive_upper = (
                row["q75_ratio_z"][channel_index] > POSITIVE_LOG_ROBUST_Z
                and row["q75_ratio"][channel_index] >= POSITIVE_Q75_RATIO
                and row["fraction_ge2"][channel_index] >= POSITIVE_UPPER_OCCUPANCY
                and row["longest_ge2"][channel_index] >= POSITIVE_MIN_CONSECUTIVE_BLOCKS
            )
            positive_spatial = (
                row["median_ratio"][channel_index] >= POSITIVE_MEDIAN_RATIO
                and row["fraction_ge2"][channel_index] >= POSITIVE_CENTRAL_OCCUPANCY
                and row["longest_ge2"][channel_index] >= POSITIVE_MIN_CONSECUTIVE_BLOCKS
                and row["absolute_factor"][channel_index] >= SET1_COHORT_FACTOR
                and row["neighbor_factor"][channel_index] >= SET1_NEIGHBOR_FACTOR
            )
            negative = (
                row["median_ratio"][channel_index] <= NEGATIVE_MEDIAN_RATIO
                and row["fraction_low"][channel_index] >= NEGATIVE_OCCUPANCY
                and row["longest_low"][channel_index] >= NEGATIVE_MIN_CONSECUTIVE_BLOCKS
                and row["absolute_z"][channel_index] < NEGATIVE_ABSOLUTE_LOG_ROBUST_Z
                and row["absolute_factor"][channel_index] <= NEGATIVE_COHORT_FACTOR
                and row["neighbor_factor"][channel_index] <= NEGATIVE_NEIGHBOR_FACTOR
            )
            reasons = []
            if positive_central:
                reasons.append("SustainedPositiveCentral")
            if positive_upper:
                reasons.append("SustainedPositiveUpper")
            if positive_spatial:
                reasons.append("SustainedPositiveSpatial")
            if negative:
                reasons.append("SustainedNegativeAbsoluteLow")
            if not reasons:
                continue
            reason = "+".join(reasons)
            flag = {
                "analysis": config.key,
                "pair_id": row["pair_id"],
                "session_id": row["session_id"],
                "condition": row["condition"],
                "product": row["product"],
                "set": row["set"],
                "channel": channel,
                "reason": reason,
                "set_median_ratio_to_set1": row["median_ratio"][channel_index],
                "set_q75_block_ratio_to_set1": row["q75_ratio"][channel_index],
                "median_ratio_log_robust_z": row["median_ratio_z"][channel_index],
                "q75_ratio_log_robust_z": row["q75_ratio_z"][channel_index],
                "fraction_60s_blocks_ge2x_set1": row["fraction_ge2"][channel_index],
                "longest_consecutive_60s_blocks_ge2x_set1": int(row["longest_ge2"][channel_index]),
                "fraction_60s_blocks_le0_5x_set1": row["fraction_low"][channel_index],
                "longest_consecutive_60s_blocks_le0_5x_set1": int(
                    row["longest_low"][channel_index]
                ),
                "set_absolute_psd": row["absolute"][channel_index],
                "set_absolute_log_robust_z": row["absolute_z"][channel_index],
                "set_absolute_cohort_factor": row["absolute_factor"][channel_index],
                "set_absolute_neighbor_factor": row["neighbor_factor"][channel_index],
            }
            flags.append(flag)
            causes[(row["pair_id"], row["set"], channel_index)].append(
                {"condition": row["condition"], "session_id": row["session_id"], "reason": reason}
            )
    return flags, dict(causes)


def group_topographies(
    config: common.AnalysisConfig,
    items: list[dict[str, Any]],
    causes: dict[tuple[str, int, int], list[dict[str, str]]],
) -> tuple[dict[str, dict[str, Any]], int, int, list[dict[str, Any]], set[tuple[str, int, int]]]:
    products: dict[str, dict[str, Any]] = {}
    eligible = excluded = 0
    audit: list[dict[str, Any]] = []
    applied_keys: set[tuple[str, int, int]] = set()
    neighbors = common.spatial_neighbor_indices()
    for product in ("CCube", "VRohtoPremium"):
        pair_arrays: list[np.ndarray] = []
        for item in items:
            if item["product_dir"] != product:
                continue
            values = change.pair_topography_values(item)
            for set_index in range(1, phase4.N_SETS):
                for channel_index in range(len(phase4.EXPECTED_CHANNEL_NAMES)):
                    if np.isfinite(values[set_index, channel_index]):
                        eligible += 1
                    key = (item["spec"].pair_id, set_index + 1, channel_index)
                    if key in causes and np.isfinite(values[set_index, channel_index]):
                        values[set_index, channel_index] = np.nan
                        excluded += 1
                        applied_keys.add(key)
            pair_arrays.append(values)
        stack = np.stack(pair_arrays)
        valid_n = np.isfinite(stack).sum(axis=0)
        group = np.divide(
            np.nansum(stack, axis=0),
            valid_n,
            out=np.full(valid_n.shape, np.nan, dtype=float),
            where=valid_n > 0,
        )
        product_residuals: list[float] = []
        for set_index in range(phase4.N_SETS):
            for channel_index, nearest in enumerate(neighbors):
                local = group[set_index, np.asarray(nearest, dtype=int)]
                local = local[np.isfinite(local)]
                residual = np.nan
                if local.size >= 3 and np.isfinite(group[set_index, channel_index]):
                    residual = float(group[set_index, channel_index] - np.median(local))
                    if set_index >= 1:
                        product_residuals.append(abs(residual))
                audit.append(
                    {
                        "analysis": config.key,
                        "product": product,
                        "set": set_index + 1,
                        "channel": phase4.EXPECTED_CHANNEL_NAMES[channel_index],
                        "grand_average_difference_pct": group[set_index, channel_index],
                        "valid_n": int(valid_n[set_index, channel_index]),
                        "local_neighbor_residual_pct": residual,
                    }
                )
        products[product] = {
            "group": group,
            "valid_n": valid_n,
            "p95_abs_local_neighbor_residual_pct": float(np.percentile(product_residuals, 95)),
            "max_abs_local_neighbor_residual_pct": float(np.max(product_residuals)),
        }
    return products, eligible, excluded, audit, applied_keys


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    if not fields:
        raise ValueError(f"No rows to write: {path}")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def output_paths(output_root: Path, config: common.AnalysisConfig, product: str) -> Path:
    directory = (
        output_root
        / "Phase4_脳波解析"
        / config.output_analysis_stem
        / product
        / "Topography"
        / "GrandAverage"
    )
    return directory / (
        f"{config.output_analysis_stem}_Topography_GrandAverage_{product}_"
        "ExploratorySet1AbsolutePSD_SustainedChangeExcluded.png"
    )


def unexcluded_output_path(
    output_root: Path, config: common.AnalysisConfig, product: str
) -> Path:
    """Return the original Grand-average topography generated before this exclusion."""
    return output_paths(output_root, config, product).with_name(
        f"{config.output_analysis_stem}_Topography_GrandAverage_{product}.png"
    )


def supplemental_output_path(
    output_root: Path,
    config: common.AnalysisConfig,
    product: str,
    stage: str,
) -> Path:
    """Return a clearly named before/after copy in the supplemental result tree."""
    if stage not in {"Before", "After"}:
        raise ValueError(f"Unexpected supplemental stage: {stage}")
    return (
        output_root
        / "Phase4_脳波解析"
        / SUPPLEMENTAL_ANALYSIS_DIR
        / config.output_analysis_stem
        / product
        / "GrandAverage"
        / (
            f"{config.output_analysis_stem}_Topography_GrandAverage_{product}_"
            f"{stage}OutlierExclusion.png"
        )
    )


def table_directory(output_root: Path, config: common.AnalysisConfig) -> Path:
    return output_root / "Phase4_脳波解析" / config.output_analysis_stem / "Sub" / "tables"


def run_analysis(
    config: common.AnalysisConfig, cache_base: Path, output_root: Path
) -> dict[str, Any]:
    items, set1_rows, set_rows = collect_metrics(config, cache_base)
    flags, causes = evaluate_flags(config, set1_rows, set_rows)
    products, eligible, excluded, group_audit, applied_keys = group_topographies(
        config, items, causes
    )
    outputs: dict[str, str] = {}
    supplemental_outputs: dict[str, dict[str, str]] = {}
    valid_ranges: dict[str, dict[str, int]] = {}
    for product, data in products.items():
        path = output_paths(output_root, config, product)
        change.plot_topography(data["group"], path)
        before_path = unexcluded_output_path(output_root, config, product)
        if not before_path.is_file():
            raise FileNotFoundError(
                f"Original topography required for comparison is missing: {before_path}"
            )
        supplemental_before = supplemental_output_path(
            output_root, config, product, "Before"
        )
        supplemental_after = supplemental_output_path(
            output_root, config, product, "After"
        )
        supplemental_before.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(before_path, supplemental_before)
        shutil.copy2(path, supplemental_after)
        outputs[product] = str(path)
        supplemental_outputs[product] = {
            "before_outlier_exclusion": str(supplemental_before),
            "after_outlier_exclusion": str(supplemental_after),
        }
        postbaseline_n = data["valid_n"][1:]
        valid_ranges[product] = {
            "minimum": int(np.nanmin(postbaseline_n)),
            "maximum": int(np.nanmax(postbaseline_n)),
            "p95_abs_local_neighbor_residual_pct": data["p95_abs_local_neighbor_residual_pct"],
            "max_abs_local_neighbor_residual_pct": data["max_abs_local_neighbor_residual_pct"],
        }

    directory = table_directory(output_root, config)
    flags_path = directory / "ExploratorySet1AbsolutePSD_SustainedChange_SessionFlags.csv"
    excluded_path = directory / "ExploratorySet1AbsolutePSD_SustainedChange_ExcludedCells.csv"
    audit_path = directory / "ExploratorySet1AbsolutePSD_SustainedChange_GroupAudit.csv"
    summary_path = directory / "ExploratorySet1AbsolutePSD_SustainedChange_RunSummary.json"
    excluded_rows = []
    item_product = {item["spec"].pair_id: item["product_dir"] for item in items}
    for (pair_id, set_number, channel_index), entries in sorted(
        causes.items(), key=lambda pair: (int(pair[0][0].split("-")[0]), pair[0][1], pair[0][2])
    ):
        excluded_rows.append(
            {
                "analysis": config.key,
                "pair_id": pair_id,
                "product": item_product[pair_id],
                "set": set_number,
                "channel": phase4.EXPECTED_CHANNEL_NAMES[channel_index],
                "trigger_conditions": ";".join(sorted({entry["condition"] for entry in entries})),
                "trigger_sessions": ";".join(
                    sorted({entry["session_id"] for entry in entries}, key=int)
                ),
                "reasons": ";".join(sorted({entry["reason"] for entry in entries})),
                "paired_or_applied": True,
                "applied_to_finite_pair_cell": (pair_id, set_number, channel_index) in applied_keys,
            }
        )
    _write_csv(flags_path, flags)
    _write_csv(excluded_path, excluded_rows)
    _write_csv(audit_path, group_audit)
    reason_counts: dict[str, int] = defaultdict(int)
    for flag in flags:
        for reason in str(flag["reason"]).split("+"):
            reason_counts[reason] += 1
    summary = {
        "script_version": SCRIPT_VERSION,
        "repository_commit": repository_commit(),
        "analysis": config.key,
        "label": config.label,
        "method": "conditionwise_set1_absolute_and_bidirectional_sustained_change",
        "parameters": asdict(PARAMETERS),
        "condition_judgment": "Eye Drop and Control are judged separately",
        "pairing_rule": (
            "paired OR: a flag in either condition excludes both conditions for that pair "
            "x channel x Set"
        ),
        "eligible_pair_channel_set_cells_sets2_6": eligible,
        "excluded_pair_channel_set_cells_sets2_6": excluded,
        "exclusion_rate_pct": 100.0 * excluded / eligible,
        "session_flag_count": len(flags),
        "reason_counts": dict(sorted(reason_counts.items())),
        "valid_n_ranges": valid_ranges,
        "qualitative_review": QUALITATIVE_REVIEW[config.key],
        "qualitative_scope": (
            "visual review of all six Set panels in each product figure; descriptive, not "
            "a statistical test"
        ),
        "psd_recomputed": False,
        "outputs": outputs,
        "supplemental_outputs": supplemental_outputs,
        "audit_files": {
            "session_flags": str(flags_path),
            "excluded_cells": str(excluded_path),
            "group_audit": str(audit_path),
        },
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    summary["audit_files"]["run_summary"] = str(summary_path)
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis",
        action="append",
        choices=sorted(ANALYSES),
        help="Repeat as needed; default is all.",
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--cache-base", type=Path, default=DEFAULT_PHASE4_CACHE_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keys = args.analysis or list(ANALYSES)
    analyses = [run_analysis(ANALYSES[key], args.cache_base, args.output_root) for key in keys]
    eligible = sum(item["eligible_pair_channel_set_cells_sets2_6"] for item in analyses)
    excluded = sum(item["excluded_pair_channel_set_cells_sets2_6"] for item in analyses)
    summary = {
        "script_version": SCRIPT_VERSION,
        "repository_commit": repository_commit(),
        "method": "conditionwise_set1_absolute_and_bidirectional_sustained_change",
        "parameters": asdict(PARAMETERS),
        "eligible_cells": eligible,
        "excluded_cells": excluded,
        "exclusion_rate_pct": 100.0 * excluded / eligible,
        "minimum_valid_n": min(
            values["minimum"]
            for analysis in analyses
            for values in analysis["valid_n_ranges"].values()
        ),
        "psd_recomputed": False,
        "analyses": analyses,
    }
    combined = (
        args.output_root
        / "Phase4_脳波解析"
        / "Sub"
        / "logs"
        / "Phase4_PSDChange_ConditionwiseBidirectionalOutlierExclusion_RunSummary.json"
    )
    combined.parent.mkdir(parents=True, exist_ok=True)
    combined.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
