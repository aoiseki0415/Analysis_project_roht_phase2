"""Pure, condition-wise No10_sub v2 QC; no file writes or mutable engine imports."""

from __future__ import annotations

import warnings
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class Parameters:
    scaled_mad_floor: float = 0.15
    neighbors: int = 4
    change_residual_factor: float = 1.5
    change_spatial_z: float = 4.5
    change_cohort_z: float = 4.5
    change_support_factor: float = 1.25
    absolute_residual_log2: float = 2.0
    absolute_spatial_z: float = 4.0
    absolute_cohort_z: float = 3.5
    absolute_level_z: float = 4.0
    absolute_support_factor: float = 2.0
    minimum_support: int = 3
    strict_neighbor_factor: float = 2.0
    top_fraction: float = 0.10
    temporal_share: float = 0.50
    temporal_mean_median: float = 3.0
    temporal_cohort_z: float = 3.5


PARAMETERS = Parameters()


def robust_z(values: np.ndarray, axis: int = 0) -> np.ndarray:
    """Floor the *scaled* MAD, not the raw MAD or input PSD."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        median = np.nanmedian(values, axis=axis, keepdims=True)
        scale = 1.4826 * np.nanmedian(np.abs(values - median), axis=axis, keepdims=True)
    return (values - median) / np.maximum(scale, PARAMETERS.scaled_mad_floor)


def positive_log2(values: np.ndarray) -> np.ndarray:
    output = np.full(np.shape(values), np.nan, dtype=float)
    np.log2(values, out=output, where=np.isfinite(values) & (values > 0))
    return output


def ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
    return np.divide(
        numerator,
        denominator,
        out=np.full(np.shape(numerator), np.nan, dtype=float),
        where=np.isfinite(numerator) & np.isfinite(denominator) & (denominator > 0),
    )


def nearest_four(positions: np.ndarray) -> np.ndarray:
    positions = np.asarray(positions, dtype=float)
    if positions.ndim != 2 or positions.shape[1] != 3 or not np.isfinite(positions).all():
        raise ValueError("Finite three-dimensional electrode positions are required")
    distances = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
    if len(positions) < 5 or np.any((distances == 0).sum(axis=1) != 1):
        raise ValueError("At least five distinct electrode positions are required")
    return np.argsort(distances, axis=1)[:, 1:5]


def strict_neighbor_isolation(values: np.ndarray, neighbors: np.ndarray) -> np.ndarray:
    """More than twofold away in one direction from at least three of four."""
    nearby = np.sort(values[neighbors], axis=1)
    return (values > PARAMETERS.strict_neighbor_factor * nearby[:, -2]) | (
        values < nearby[:, 1] / PARAMETERS.strict_neighbor_factor
    )


def spatial_metrics(values: np.ndarray, neighbors: np.ndarray, factor: float) -> dict:
    logged = positive_log2(values)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        residual = logged - np.nanmedian(logged[neighbors], axis=1)
    support = (
        np.sign(residual)[:, None] * (logged[:, None] - logged[neighbors]) >= np.log2(factor)
    ).sum(axis=1)
    return {
        "residual_log2": residual,
        "spatial_z": robust_z(residual),
        "support": support,
        "strict_neighbor_isolation": strict_neighbor_isolation(values, neighbors),
    }


def power_metrics(values: np.ndarray, baseline: np.ndarray) -> dict:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(values, axis=0)
        median = np.nanmedian(values, axis=0)
    counts = np.isfinite(values).sum(axis=0)
    share = np.full(values.shape[1], np.nan)
    top_counts = np.zeros(values.shape[1], dtype=int)
    for channel in range(values.shape[1]):
        finite = values[np.isfinite(values[:, channel]), channel]
        if finite.size and np.sum(finite) > 0:
            top_counts[channel] = int(np.ceil(PARAMETERS.top_fraction * finite.size))
            share[channel] = np.sort(finite)[-top_counts[channel] :].sum() / finite.sum()
    return {
        "mean": mean,
        "median": median,
        "baseline_mean": baseline.copy(),
        "ratio": ratio(mean, baseline),
        "mean_median": ratio(mean, median),
        "top_share": share,
        "finite_count": counts,
        "top_count": top_counts,
    }


def collect_condition_metrics(items: list[dict[str, Any]], neighbors: np.ndarray) -> list[dict]:
    rows = []
    for item in items:
        for condition, change in (("Eye Drop", item["eye_drop"]), ("Control", item["control"])):
            session = change.source
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                baseline = np.nanmean(session.sets[1].psd_band_mean, axis=0)
            for number, data in sorted(session.sets.items()):
                row = {
                    "pair_id": item["spec"].pair_id,
                    "session_id": session.session_id,
                    "condition": condition,
                    "product": item["product_dir"],
                    "set": number,
                    **power_metrics(data.psd_band_mean, baseline),
                }
                for key, factor in (
                    ("ratio", PARAMETERS.change_support_factor),
                    ("median", PARAMETERS.absolute_support_factor),
                ):
                    row.update(
                        {
                            f"{key}_{name}": value
                            for name, value in spatial_metrics(row[key], neighbors, factor).items()
                        }
                    )
                rows.append(row)
    if not rows:
        raise ValueError("No eligible condition metrics")
    for number in sorted({row["set"] for row in rows}):
        selected = [row for row in rows if row["set"] == number]
        # One frozen reference pool: both products and conditions, same Set and channel.
        for key, logged in (
            ("ratio_residual_log2", False),
            ("median_residual_log2", False),
            ("median", True),
            ("mean_median", True),
        ):
            values = np.stack([row[key] for row in selected])
            z = robust_z(positive_log2(values) if logged else values, axis=0)
            for row, scores in zip(selected, z, strict=True):
                row[f"{key}_cohort_z"] = scores
    return rows


def pathway_masks(row: dict) -> dict[str, np.ndarray]:
    p = PARAMETERS
    change = (
        (row["set"] > 1)
        & (np.abs(row["ratio_residual_log2"]) >= np.log2(p.change_residual_factor))
        & (np.abs(row["ratio_spatial_z"]) >= p.change_spatial_z)
        & (np.abs(row["ratio_residual_log2_cohort_z"]) >= p.change_cohort_z)
        & (row["ratio_support"] >= p.minimum_support)
        & row["ratio_strict_neighbor_isolation"]
    )
    absolute = (
        (np.abs(row["median_residual_log2"]) >= p.absolute_residual_log2)
        & (np.abs(row["median_spatial_z"]) >= p.absolute_spatial_z)
        & (np.abs(row["median_residual_log2_cohort_z"]) >= p.absolute_cohort_z)
        & (np.abs(row["median_cohort_z"]) >= p.absolute_level_z)
        & (row["median_support"] >= p.minimum_support)
        & row["median_strict_neighbor_isolation"]
    )
    temporal = (
        (row["top_share"] >= p.temporal_share)
        & (row["mean_median"] >= p.temporal_mean_median)
        & (row["mean_median_cohort_z"] >= p.temporal_cohort_z)
    )
    return {"spatial_change": change, "spatial_absolute": absolute, "temporal": temporal}


def evaluate_flags(rows: list[dict], channels: list[str]) -> tuple[list[dict], dict]:
    flags = []
    causes = defaultdict(list)
    for row in rows:
        masks = pathway_masks(row)
        for name, mask in masks.items():
            row[f"flag_{name}"] = mask
        for channel, name in enumerate(channels):
            reasons = [reason for reason, mask in masks.items() if mask[channel]]
            if not reasons:
                continue
            flag = {key: value for key, value in row.items() if not isinstance(value, np.ndarray)}
            flag.update(channel=name, reason="+".join(sorted(reasons)))
            flag.update(
                {
                    key: value[channel].item()
                    for key, value in row.items()
                    if isinstance(value, np.ndarray)
                }
            )
            flags.append(flag)
            numbers = range(2, 7) if row["set"] == 1 else (row["set"],)
            for number in numbers:
                causes[(row["pair_id"], number, channel)].append(
                    {
                        "condition": row["condition"],
                        "session_id": row["session_id"],
                        "reason": flag["reason"],
                        "source_set": row["set"],
                        "baseline_propagated": row["set"] == 1,
                    }
                )
    return flags, dict(causes)
