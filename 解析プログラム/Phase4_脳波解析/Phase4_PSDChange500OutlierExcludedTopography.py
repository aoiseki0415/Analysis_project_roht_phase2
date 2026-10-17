#!/usr/bin/env python3
"""Draw PSD-Change Grand-average topographies after the fixed 500% exclusion.

This sensitivity analysis reuses the validated Phase 4 No1/No2/No3 PSD
caches.  It never recomputes Welch PSD and never overwrites the primary
No1_sub/No2_sub/No3_sub figures.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import Phase4_No1_FmTheta as phase4
import Phase4_No1_sub_FmThetaChange as change

SCRIPT_VERSION = "phase4-psd-change-500pct-outlier-excluded-topography-2026-10-17.1"
PSD_CHANGE_THRESHOLD_PCT = 500.0
PERSISTENT_MIN_SETS = 2
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


def group_topography(
    items: list[dict[str, Any]], records: list[OutlierRecord], product: str
) -> tuple[np.ndarray, np.ndarray, set[tuple[str, str]]]:
    pair_values: list[np.ndarray] = []
    persistent: set[tuple[str, str]] = set()
    by_pair: dict[str, list[OutlierRecord]] = defaultdict(list)
    for record in records:
        by_pair[record.pair_id].append(record)
    for item in items:
        if item["product_dir"] != product:
            continue
        values, pair_persistent = masked_pair_topography(
            item, by_pair.get(item["spec"].pair_id, [])
        )
        pair_values.append(values)
        persistent.update(pair_persistent)
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
    return group, valid_n, persistent


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


def run_analysis(
    config: AnalysisConfig, cache_base: Path, output_root: Path
) -> dict[str, Any]:
    cache_root = cache_base / config.cache_root_name / "PSDTimeSeries"
    items = load_items(cache_root)
    records = [record for item in items for record in find_outliers(item, config)]
    outputs: dict[str, str] = {}
    valid_n_ranges: dict[str, dict[str, int]] = {}
    persistent_all: set[tuple[str, str]] = set()
    for product in ("CCube", "VRohtoPremium"):
        group, valid_n, persistent = group_topography(items, records, product)
        path = output_path(output_root, config, product)
        change.plot_topography(group, path)
        outputs[product] = str(path)
        valid_n_ranges[product] = {
            "minimum": int(valid_n.min()),
            "maximum": int(valid_n.max()),
        }
        persistent_all.update(persistent)
    return {
        "analysis": config.key,
        "label": config.label,
        "outlier_count": len(records),
        "persistent_session_channels": [
            {"session_id": session_id, "channel": channel}
            for session_id, channel in sorted(
                persistent_all, key=lambda value: (int(value[0]), value[1])
            )
        ],
        "valid_n_ranges": valid_n_ranges,
        "outputs": outputs,
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
        "psd_recomputed": False,
        "analyses": [
            run_analysis(ANALYSES[key], args.cache_base, args.output_root) for key in keys
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
