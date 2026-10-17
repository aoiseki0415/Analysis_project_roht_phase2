#!/usr/bin/env python3
"""Draw PSD-Change Grand-average topographies after the fixed 500% exclusion.

This sensitivity analysis reuses the validated Phase 4 No1/No2/No3 PSD
caches.  It never recomputes Welch PSD and never overwrites the primary
No1_sub/No2_sub/No3_sub figures.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import Phase4_No1_FmTheta as phase4
import Phase4_No1_sub_FmThetaChange as change

SCRIPT_VERSION = "phase4-psd-change-500pct-spatial-outlier-excluded-topography-2026-10-17.2"
PSD_CHANGE_THRESHOLD_PCT = 500.0
PERSISTENT_MIN_SETS = 2
SPATIAL_NEIGHBOR_COUNT = 4
SPATIAL_MIN_FINITE_NEIGHBORS = 3
SPATIAL_ROBUST_Z_THRESHOLD = 5.0
MAD_NORMAL_CONSISTENCY = 1.4826
SET1_MISSING_PAIR_ID = "109-209"

DEFAULT_PHASE4_CACHE_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/"
    "Phase4_脳波解析"
)
DEFAULT_OUTPUT_ROOT = phase4.DEFAULT_OUTPUT_ROOT


@dataclass(frozen=True)
class AnalysisConfig:
    key: str
    label: str
    cache_analysis_stem: str
    output_analysis_stem: str

    @property
    def cache_root_name(self) -> str:
        return self.cache_analysis_stem


@dataclass(frozen=True)
class CacheEntry:
    path: Path
    pair_id: str
    session_id: str
    condition: str
    product: str


@dataclass(frozen=True)
class OutlierRecord:
    analysis: str
    pair_id: str
    session_id: str
    condition: str
    product: str
    set_number: int
    channel: str
    psd_change_pct: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis,
            "pair_id": self.pair_id,
            "session_id": self.session_id,
            "condition": self.condition,
            "product": self.product,
            "set": self.set_number,
            "channel": self.channel,
            "psd_change_pct": self.psd_change_pct,
        }


@dataclass(frozen=True)
class SpatialOutlierRecord:
    analysis: str
    pair_id: str
    product: str
    set_number: int
    channel: str
    pair_difference_pct: float
    neighbor_median_pct: float
    spatial_residual_pct: float
    residual_center_pct: float
    residual_mad_pct: float
    robust_z: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "analysis": self.analysis,
            "pair_id": self.pair_id,
            "product": self.product,
            "set": self.set_number,
            "channel": self.channel,
            "pair_difference_pct": self.pair_difference_pct,
            "neighbor_median_pct": self.neighbor_median_pct,
            "spatial_residual_pct": self.spatial_residual_pct,
            "residual_center_pct": self.residual_center_pct,
            "residual_mad_pct": self.residual_mad_pct,
            "robust_z": self.robust_z,
        }


ANALYSES = {
    "No1": AnalysisConfig(
        "No1", "Fm theta (4-7 Hz)", "No1_FmTheta", "No1_sub_FmThetaChange"
    ),
    "No2": AnalysisConfig(
        "No2",
        "Occipital alpha (8-15 Hz)",
        "No2_OccipitalAlpha",
        "No2_sub_OccipitalAlphaChange",
    ),
    "No3": AnalysisConfig(
        "No3", "Frontal delta (1-3 Hz)", "No3_FrontalDelta", "No3_sub_FrontalDeltaChange"
    ),
}


def _normalise_condition(value: str) -> str:
    key = value.strip().lower().replace(" ", "").replace("_", "")
    if key in {"eyedrop", "drops"}:
        return "Eye Drop"
    if key == "control":
        return "Control"
    raise ValueError(f"Unknown condition in PSD cache: {value}")


def discover_cache_entries(cache_root: Path) -> dict[str, list[CacheEntry]]:
    """Discover the two validated session caches belonging to every pair."""
    entries: dict[str, list[CacheEntry]] = defaultdict(list)
    for path in sorted(cache_root.glob("*.h5")):
        phase4.validate_cache(path)
        with h5py.File(path, "r") as handle:
            entry = CacheEntry(
                path=path,
                pair_id=str(handle.attrs["pair_id"]),
                session_id=str(handle.attrs["participant_id"]),
                condition=_normalise_condition(str(handle.attrs["condition"])),
                product=str(handle.attrs["product"]),
            )
        entries[entry.pair_id].append(entry)
    if len(entries) != phase4.PRODUCTION_PARTICIPANT_COUNT:
        raise ValueError(
            f"{cache_root}: expected {phase4.PRODUCTION_PARTICIPANT_COUNT} pairs, "
            f"found {len(entries)}"
        )
    for pair_id, pair_entries in entries.items():
        if len(pair_entries) != 2:
            raise ValueError(f"Pair {pair_id}: expected two session caches")
        if {entry.condition for entry in pair_entries} != {"Eye Drop", "Control"}:
            raise ValueError(f"Pair {pair_id}: Eye Drop/Control mapping is incomplete")
        if len({entry.product for entry in pair_entries}) != 1:
            raise ValueError(f"Pair {pair_id}: product differs between sessions")
    return dict(entries)


def load_items(cache_root: Path) -> list[dict[str, Any]]:
    """Load Phase-1-mask and log3SD-mask applied PSD without recomputation."""
    items: list[dict[str, Any]] = []
    entries = discover_cache_entries(cache_root)
    for pair_id in sorted(entries, key=lambda value: int(value.split("-")[0])):
        if pair_id == SET1_MISSING_PAIR_ID:
            continue
        pair_entries = entries[pair_id]
        first_id, second_id = pair_id.split("-")
        by_session = {entry.session_id: entry for entry in pair_entries}
        if set(by_session) != {first_id, second_id}:
            raise ValueError(f"Pair {pair_id}: cache IDs do not match pair label")
        drops = next(entry for entry in pair_entries if entry.condition == "Eye Drop")
        product = pair_entries[0].product
        spec = phase4.ParticipantSpec(first_id, second_id, drops.session_id, product)
        sessions = {
            session_id: change.make_change_session(
                phase4.load_session_cache(by_session[session_id].path)
            )
            for session_id in (first_id, second_id)
        }
        items.append(
            {
                "spec": spec,
                "product_dir": phase4.normalize_product(product)[0],
                "eye_drop": sessions[spec.drops_session_id],
                "control": sessions[spec.control_session_id],
            }
        )
    expected = phase4.PRODUCTION_PARTICIPANT_COUNT - 1
    if len(items) != expected:
        raise ValueError(f"Expected {expected} analysable pairs, found {len(items)}")
    return items


def find_outliers(
    item: dict[str, Any], config: AnalysisConfig
) -> list[OutlierRecord]:
    records: list[OutlierRecord] = []
    for condition, session in (
        ("Eye Drop", item["eye_drop"]),
        ("Control", item["control"]),
    ):
        means = change.set_channel_means(session)
        for set_number in range(2, phase4.N_SETS + 1):
            if set_number not in means:
                continue
            for channel_index, value in enumerate(means[set_number]):
                if np.isfinite(value) and value >= PSD_CHANGE_THRESHOLD_PCT:
                    records.append(
                        OutlierRecord(
                            analysis=config.key,
                            pair_id=item["spec"].pair_id,
                            session_id=session.session_id,
                            condition=condition,
                            product=item["product_dir"],
                            set_number=set_number,
                            channel=session.channel_names[channel_index],
                            psd_change_pct=float(value),
                        )
                    )
    return records


def masked_pair_topography(
    item: dict[str, Any], records: list[OutlierRecord]
) -> tuple[np.ndarray, set[tuple[str, str]]]:
    """Apply paired cell removal and the fixed persistent-channel rule."""
    values = change.pair_topography_values(item)
    channel_index = {
        channel: index for index, channel in enumerate(phase4.EXPECTED_CHANNEL_NAMES)
    }
    by_session_channel: dict[tuple[str, str], set[int]] = defaultdict(set)
    for record in records:
        index = channel_index[record.channel]
        values[record.set_number - 1, index] = np.nan
        by_session_channel[(record.session_id, record.channel)].add(record.set_number)
    persistent = {
        key
        for key, set_numbers in by_session_channel.items()
        if len(set_numbers) >= PERSISTENT_MIN_SETS
    }
    for _, channel in persistent:
        values[1:, channel_index[channel]] = np.nan
    return values, persistent


@lru_cache(maxsize=1)
def spatial_neighbor_indices() -> tuple[tuple[int, ...], ...]:
    """Return the four nearest montage electrodes for every channel."""
    info = phase4._topomap_info()
    positions = np.asarray([channel["loc"][:3] for channel in info["chs"]], dtype=float)
    if positions.shape != (len(phase4.EXPECTED_CHANNEL_NAMES), 3):
        raise ValueError("Unexpected montage coordinate shape")
    if not np.isfinite(positions).all():
        raise ValueError("Montage contains non-finite channel coordinates")
    distance = np.linalg.norm(positions[:, None, :] - positions[None, :, :], axis=2)
    return tuple(
        tuple(
            int(index)
            for index in np.argsort(distance[row])[1 : SPATIAL_NEIGHBOR_COUNT + 1]
        )
        for row in range(distance.shape[0])
    )


def apply_spatial_outlier_mask(
    values: np.ndarray,
    item: dict[str, Any],
    config: AnalysisConfig,
) -> tuple[np.ndarray, list[SpatialOutlierRecord]]:
    """Mask isolated paired-condition channel values within each participant Set.

    The detector is applied after the fixed 500% rule.  For every post-baseline
    Set and channel, it subtracts the median of the four nearest montage
    electrodes.  Those 32 local residuals are then standardized with their
    median and 1.4826 x MAD.  Only cells with |robust z| > 5 are removed.
    """
    output = values.copy()
    neighbors = spatial_neighbor_indices()
    records: list[SpatialOutlierRecord] = []
    for set_index in range(1, phase4.N_SETS):
        row = output[set_index].copy()
        residuals = np.full(row.shape, np.nan, dtype=float)
        neighbor_medians = np.full(row.shape, np.nan, dtype=float)
        for channel_index, nearest in enumerate(neighbors):
            if not np.isfinite(row[channel_index]):
                continue
            nearest_values = row[np.asarray(nearest, dtype=int)]
            finite = nearest_values[np.isfinite(nearest_values)]
            if finite.size < SPATIAL_MIN_FINITE_NEIGHBORS:
                continue
            neighbor_medians[channel_index] = float(np.median(finite))
            residuals[channel_index] = row[channel_index] - neighbor_medians[channel_index]

        finite_residuals = residuals[np.isfinite(residuals)]
        if finite_residuals.size < 8:
            continue
        center = float(np.median(finite_residuals))
        mad = float(np.median(np.abs(finite_residuals - center)))
        robust_scale = MAD_NORMAL_CONSISTENCY * mad
        if not np.isfinite(robust_scale) or robust_scale <= np.finfo(float).eps:
            continue
        robust_z = (residuals - center) / robust_scale
        flagged = np.flatnonzero(np.abs(robust_z) > SPATIAL_ROBUST_Z_THRESHOLD)
        for channel_index in flagged:
            records.append(
                SpatialOutlierRecord(
                    analysis=config.key,
                    pair_id=item["spec"].pair_id,
                    product=item["product_dir"],
                    set_number=set_index + 1,
                    channel=phase4.EXPECTED_CHANNEL_NAMES[channel_index],
                    pair_difference_pct=float(row[channel_index]),
                    neighbor_median_pct=float(neighbor_medians[channel_index]),
                    spatial_residual_pct=float(residuals[channel_index]),
                    residual_center_pct=center,
                    residual_mad_pct=mad,
                    robust_z=float(robust_z[channel_index]),
                )
            )
            output[set_index, channel_index] = np.nan
    return output, records


def group_topography(
    items: list[dict[str, Any]],
    records: list[OutlierRecord],
    product: str,
    config: AnalysisConfig,
) -> tuple[
    np.ndarray,
    np.ndarray,
    set[tuple[str, str]],
    list[SpatialOutlierRecord],
]:
    pair_values: list[np.ndarray] = []
    persistent: set[tuple[str, str]] = set()
    spatial_records: list[SpatialOutlierRecord] = []
    by_pair: dict[str, list[OutlierRecord]] = defaultdict(list)
    for record in records:
        by_pair[record.pair_id].append(record)
    for item in items:
        if item["product_dir"] != product:
            continue
        values, pair_persistent = masked_pair_topography(
            item, by_pair.get(item["spec"].pair_id, [])
        )
        values, pair_spatial_records = apply_spatial_outlier_mask(values, item, config)
        pair_values.append(values)
        persistent.update(pair_persistent)
        spatial_records.extend(pair_spatial_records)
    stacked = np.stack(pair_values)
    valid_n = np.isfinite(stacked).sum(axis=0)
    sums = np.nansum(stacked, axis=0)
    group = np.divide(
        sums,
        valid_n,
        out=np.full(sums.shape, np.nan, dtype=float),
        where=valid_n > 0,
    )
    if not np.isfinite(group).all():
        raise ValueError(f"{product}: outlier exclusion left a non-finite group cell")
    return group, valid_n, persistent, spatial_records


def output_path(output_root: Path, config: AnalysisConfig, product: str) -> Path:
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
        "PSDChange500pctOutlierExcluded.png"
    )


def write_audit_tables(
    output_root: Path,
    config: AnalysisConfig,
    absolute_records: list[OutlierRecord],
    spatial_records: list[SpatialOutlierRecord],
    valid_n_ranges: dict[str, dict[str, int]],
) -> dict[str, str]:
    directory = (
        output_root
        / "Phase4_脳波解析"
        / config.output_analysis_stem
        / "Sub"
        / "tables"
        / "PSDChange500pctAndSpatialMAD5OutlierExclusion"
    )
    directory.mkdir(parents=True, exist_ok=True)
    absolute_path = directory / f"{config.output_analysis_stem}_Absolute500pctOutliers.csv"
    spatial_path = directory / f"{config.output_analysis_stem}_SpatialMAD5Outliers.csv"
    summary_path = directory / f"{config.output_analysis_stem}_RunSummary.json"

    absolute_fields = [
        "analysis",
        "pair_id",
        "session_id",
        "condition",
        "product",
        "set",
        "channel",
        "psd_change_pct",
    ]
    with absolute_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=absolute_fields)
        writer.writeheader()
        writer.writerows(record.as_dict() for record in absolute_records)

    spatial_fields = [
        "analysis",
        "pair_id",
        "product",
        "set",
        "channel",
        "pair_difference_pct",
        "neighbor_median_pct",
        "spatial_residual_pct",
        "residual_center_pct",
        "residual_mad_pct",
        "robust_z",
    ]
    with spatial_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=spatial_fields)
        writer.writeheader()
        writer.writerows(record.as_dict() for record in spatial_records)

    summary = {
        "script_version": SCRIPT_VERSION,
        "analysis": config.key,
        "absolute_threshold_pct": PSD_CHANGE_THRESHOLD_PCT,
        "persistent_min_sets": PERSISTENT_MIN_SETS,
        "spatial_neighbor_count": SPATIAL_NEIGHBOR_COUNT,
        "spatial_min_finite_neighbors": SPATIAL_MIN_FINITE_NEIGHBORS,
        "spatial_robust_z_threshold": SPATIAL_ROBUST_Z_THRESHOLD,
        "mad_normal_consistency": MAD_NORMAL_CONSISTENCY,
        "absolute_outlier_count": len(absolute_records),
        "spatial_outlier_count": len(spatial_records),
        "valid_n_ranges": valid_n_ranges,
        "psd_recomputed": False,
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "absolute_outliers_csv": str(absolute_path),
        "spatial_outliers_csv": str(spatial_path),
        "run_summary_json": str(summary_path),
    }


def run_analysis(
    config: AnalysisConfig, cache_base: Path, output_root: Path
) -> dict[str, Any]:
    cache_root = cache_base / config.cache_root_name / "PSDTimeSeries"
    items = load_items(cache_root)
    records = [record for item in items for record in find_outliers(item, config)]
    outputs: dict[str, str] = {}
    valid_n_ranges: dict[str, dict[str, int]] = {}
    persistent_all: set[tuple[str, str]] = set()
    spatial_all: list[SpatialOutlierRecord] = []
    for product in ("CCube", "VRohtoPremium"):
        group, valid_n, persistent, spatial_records = group_topography(
            items, records, product, config
        )
        path = output_path(output_root, config, product)
        change.plot_topography(group, path)
        outputs[product] = str(path)
        valid_n_ranges[product] = {
            "minimum": int(valid_n.min()),
            "maximum": int(valid_n.max()),
        }
        persistent_all.update(persistent)
        spatial_all.extend(spatial_records)
    audit_paths = write_audit_tables(
        output_root, config, records, spatial_all, valid_n_ranges
    )
    return {
        "analysis": config.key,
        "label": config.label,
        "outlier_count": len(records),
        "spatial_outlier_count": len(spatial_all),
        "persistent_session_channels": [
            {"session_id": session_id, "channel": channel}
            for session_id, channel in sorted(
                persistent_all, key=lambda value: (int(value[0]), value[1])
            )
        ],
        "valid_n_ranges": valid_n_ranges,
        "outputs": outputs,
        "audit_paths": audit_paths,
        "outliers": [record.as_dict() for record in records],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis",
        action="append",
        choices=sorted(ANALYSES),
        help="Analysis to draw; repeat as needed. Default: all three.",
    )
    parser.add_argument(
        "--cache-base", type=Path, default=DEFAULT_PHASE4_CACHE_ROOT
    )
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keys = args.analysis or list(ANALYSES)
    summary = {
        "script_version": SCRIPT_VERSION,
        "threshold_pct": PSD_CHANGE_THRESHOLD_PCT,
        "persistent_min_sets": PERSISTENT_MIN_SETS,
        "spatial_neighbor_count": SPATIAL_NEIGHBOR_COUNT,
        "spatial_min_finite_neighbors": SPATIAL_MIN_FINITE_NEIGHBORS,
        "spatial_robust_z_threshold": SPATIAL_ROBUST_Z_THRESHOLD,
        "mad_normal_consistency": MAD_NORMAL_CONSISTENCY,
        "psd_recomputed": False,
        "analyses": [
            run_analysis(ANALYSES[key], args.cache_base, args.output_root) for key in keys
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
