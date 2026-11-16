"""Frontocentral ROI low-alpha views of immutable, provenance-checked No10 caches.

Mask each source channel first, average the finite values of the ten-channel ROI,
then (for sub) normalise that ROI by its own unsmoothed Set-1 mean. Existing
No1/No11 rendering, smoothing, paired missingness and statistics are reused
in isolated module namespaces. No PSD cache is computed or written here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd
from phase4_band_variant_config import configure_band_engine, configure_change_engine
from Phase4_No10_FzLowAlpha import engine as source_engine
from phase4_no11_cached_analysis import _isolated_engine, _sha256

MAIN_STEM = "No12_FrontalROILowAlpha"
CHANGE_STEM = "No12_sub_FrontalROILowAlphaChange"
MAIN_VERSION = "20261116_frontocentral_roi10_lowalpha_cached_v2"
CHANGE_VERSION = "20261116_frontocentral_roi10_lowalpha_change_cached_v2"
ROI_CHANNELS = ("F3", "Fz", "F4", "FC5", "FC1", "FC2", "FC6", "C3", "Cz", "C4")
ROI_LABEL = "FrontalROI"
SCRIPT_DIR = Path(__file__).resolve().parent


@dataclass
class ROISession(source_engine.SessionPSD):
    """A one-column computational ROI, with its unchanged source for audit only."""

    source_session: source_engine.SessionPSD | None = None


def _forbidden_generation(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("No12 is cache-only and does not generate PSD caches or topography")


def _checked_roots(args: argparse.Namespace) -> None:
    if args.cache_root.resolve() != source_engine.DEFAULT_CACHE_ROOT.resolve():
        raise ValueError("No12 must read the authorized current No10 PSD cache root")
    if args.output_root.resolve() != source_engine.DEFAULT_OUTPUT_ROOT.resolve():
        raise ValueError("No12 outputs must use the authorized OneDrive result root")


def roi_indices(session: source_engine.SessionPSD) -> list[int]:
    names = session.channel_names
    if len(names) != 32 or len(set(names)) != len(names):
        raise ValueError(f"ID{session.session_id}: expected 32 unique source channels")
    missing = set(ROI_CHANNELS) - set(names)
    if missing:
        raise ValueError(f"ID{session.session_id}: missing ROI channels {sorted(missing)}")
    return [names.index(channel) for channel in ROI_CHANNELS]


def finite_channel_mean(values: np.ndarray) -> np.ndarray:
    """Equal weights among finite channels; one is sufficient, zero gives NaN."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(ROI_CHANNELS):
        raise ValueError("ROI input must be a time-by-ten-channel array")
    finite = np.isfinite(values)
    count = finite.sum(axis=1)
    total = np.where(finite, values, 0.0).sum(axis=1)
    result = np.full(len(values), np.nan)
    np.divide(total, count, out=result, where=count > 0)
    return result


def aggregate_roi_session(source: source_engine.SessionPSD) -> ROISession:
    """Aggregate only the already Phase1/log3SD-masked source channel values."""
    indices = roi_indices(source)
    sets = {}
    for number, item in sorted(source.sets.items()):
        after = np.asarray(item.psd_band_mean, dtype=float)
        before = item.psd_before_log3sd_exclusion
        if before is None or after.ndim != 2 or after.shape[1] != 32:
            raise ValueError(f"ID{source.session_id} Set{number}: source masks/schema absent")
        before = np.asarray(before, dtype=float)
        if before.shape != after.shape:
            raise ValueError(f"ID{source.session_id} Set{number}: source mask shape mismatch")
        for field in (
            "relative_seconds_center",
            "original_timestamp_center",
            "set_progress_pct",
            "global_progress_pct",
            "source_center_sample",
            "ica_training_mask_fraction",
        ):
            if np.asarray(getattr(item, field)).shape != (after.shape[0],):
                raise ValueError(f"ID{source.session_id} Set{number}: invalid {field} shape")
        excluded = item.ica_training_mask_fraction >= source_engine.PSD_MASK_OVERLAP_THRESHOLD
        if np.isfinite(before[excluded]).any() or np.isfinite(after[excluded]).any():
            raise ValueError(f"ID{source.session_id} Set{number}: Phase1 mask not applied")
        if np.any(np.isfinite(after) & ~np.isfinite(before)):
            raise ValueError(f"ID{source.session_id} Set{number}: masks restore source data")
        if item.log3sd_outlier_mask is None or item.log3sd_outlier_mask.shape != after.shape:
            raise ValueError(f"ID{source.session_id} Set{number}: log3SD mask absent")
        if np.isfinite(after[item.log3sd_outlier_mask]).any():
            raise ValueError(f"ID{source.session_id} Set{number}: log3SD mask not applied")
        sets[number] = source_engine.SetPSD(
            set_number=number,
            psd_band_mean=finite_channel_mean(after[:, indices])[:, None],
            relative_seconds_center=item.relative_seconds_center.copy(),
            original_timestamp_center=item.original_timestamp_center.copy(),
            set_progress_pct=item.set_progress_pct.copy(),
            global_progress_pct=item.global_progress_pct.copy(),
            source_center_sample=item.source_center_sample.copy(),
            ica_training_mask_fraction=item.ica_training_mask_fraction.copy(),
            psd_before_log3sd_exclusion=finite_channel_mean(before[:, indices])[:, None],
            # No threshold is fitted to the ROI; masks remain on the source channels.
            log3sd_outlier_mask=None,
        )
    return ROISession(
        session_id=source.session_id,
        condition=source.condition,
        pair_id=source.pair_id,
        product=source.product,
        channel_names=[ROI_LABEL],
        sets=sets,
        channel_excluded_mask=np.zeros(1, dtype=bool),
        source_session=source,
    )


def load_roi_session(path: Path) -> ROISession:
    return aggregate_roi_session(source_engine.load_session_cache(path))


def load_roi_pair(spec: Any, cache_root: Path) -> dict[str, Any]:
    item = source_engine.load_pair_item(spec, cache_root)
    return item | {
        condition: aggregate_roi_session(item[condition]) for condition in ("eye_drop", "control")
    }


def _source_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for item in items:
        sessions = {}
        for condition in ("eye_drop", "control"):
            session = item[condition]
            if not isinstance(session, ROISession):
                session = session.source  # ChangeSession -> its unnormalised ROI.
            if not isinstance(session, ROISession) or session.source_session is None:
                raise ValueError("ROI source provenance is absent")
            sessions[condition] = session.source_session
        result.append(item | sessions)
    return result


def roi_quality_tables(items: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    windows, summaries, coverage = [], [], []
    # Ten channels require bits 0..9; uint8 would silently lose Cz/C4.
    weights = (1 << np.arange(len(ROI_CHANNELS))).astype(np.uint16)
    for item in _source_items(items):
        for condition in ("eye_drop", "control"):
            session = item[condition]
            indices = roi_indices(session)
            for number, values in sorted(session.sets.items()):
                before = np.isfinite(values.psd_before_log3sd_exclusion[:, indices])
                after = np.isfinite(values.psd_band_mean[:, indices])
                count_before, count_after = before.sum(axis=1), after.sum(axis=1)
                n = len(after)
                identity = {
                    "PairID": item["spec"].pair_id,
                    "SessionID": session.session_id,
                    "Condition": session.condition,
                    "Product": item["product_dir"],
                    "Set": number,
                }
                phase1 = (
                    values.ica_training_mask_fraction >= source_engine.PSD_MASK_OVERLAP_THRESHOLD
                )
                windows.append(
                    pd.DataFrame(
                        identity
                        | {
                            "WindowIndex": np.arange(n),
                            "RelativeSecondsCenter": values.relative_seconds_center,
                            "OriginalTimestampCenter": values.original_timestamp_center,
                            "SetProgressPercent": values.set_progress_pct,
                            "GlobalProgressPercent": values.global_progress_pct,
                            "SourceCenterSample": values.source_center_sample,
                            "Phase1Excluded": phase1,
                            "ValidChannelCountBeforeLog3SD": count_before,
                            "ValidChannelBitsBeforeLog3SD": (before * weights).sum(
                                axis=1, dtype=np.uint16
                            ),
                            "ValidChannelCount": count_after,
                            "ValidChannelBits": (after * weights).sum(axis=1, dtype=np.uint16),
                        }
                    )
                )
                summary = identity | {"WindowCount": n, "Phase1ExcludedCount": int(phase1.sum())}
                for label, counts in (("BeforeLog3SD", count_before), ("AfterLog3SD", count_after)):
                    for k in range(len(ROI_CHANNELS) + 1):
                        nk = int(np.count_nonzero(counts == k))
                        summary[f"{label}_Valid{k}_Count"] = nk
                        summary[f"{label}_Valid{k}_Proportion"] = nk / n if n else np.nan
                summaries.append(summary)
                for offset, channel in enumerate(ROI_CHANNELS):
                    nb, na = int(before[:, offset].sum()), int(after[:, offset].sum())
                    coverage.append(
                        identity
                        | {
                            "Channel": channel,
                            "WindowCount": n,
                            "ValidBeforeLog3SD": nb,
                            "ValidAfterLog3SD": na,
                            "ValidBeforeLog3SDProportion": nb / n if n else np.nan,
                            "ValidAfterLog3SDProportion": na / n if n else np.nan,
                            "Log3SDExcludedCount": nb - na,
                            "ICAExcludedFromLearningOnly": bool(
                                session.channel_excluded_mask[indices[offset]]
                            ),
                        }
                    )
    return {
        "ROIWindowQuality": pd.concat(windows, ignore_index=True) if windows else pd.DataFrame(),
        "ROISetQuality": pd.DataFrame(summaries),
        "ROIChannelCoverage": pd.DataFrame(coverage),
    }


def write_roi_quality(
    items: list[dict[str, Any]], root: Path, stem: str, scope: str
) -> dict[str, str]:
    folder = root / "Phase4_脳波解析" / stem / "Sub" / "tables" / "ROIQuality"
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for key, table in roi_quality_tables(items).items():
        path = folder / f"{stem}_{key}_{scope}.csv"
        table.to_csv(path, index=False)
        paths[key] = str(path)
    return paths


def cache_provenance(specs: list[Any], root: Path) -> list[dict[str, Any]]:
    records, seen = [], set()
    for spec in specs:
        for sid in (spec.first_session_id, spec.second_session_id):
            if sid in seen:
                raise ValueError(f"Duplicate source session ID: {sid}")
            seen.add(sid)
            path = source_engine.cache_path(root, spec, sid)
            # validate_cache checks source configuration/hash and raw-file fingerprints.
            details = source_engine.validate_cache(path)
            records.append(
                {
                    "pair_id": spec.pair_id,
                    "session_id": sid,
                    "path": str(path),
                    "sha256": _sha256(path),
                    "source_validation": details,
                    "roi_channels_selected_by_name": list(ROI_CHANNELS),
                    "source_cache_modified": False,
                }
            )
    return records


def target_configuration(engine: ModuleType, *, change: bool = False) -> dict[str, Any]:
    scripts = [
        "Phase4_No1_FmTheta.py",
        "Phase4_No1_sub_FmThetaChange.py",
        "phase4_no11_cached_analysis.py",
        Path(__file__).name,
    ]
    return {
        "analysis_stem": CHANGE_STEM if change else MAIN_STEM,
        "script_version": CHANGE_VERSION if change else MAIN_VERSION,
        "source_analysis": "No10_FzLowAlpha",
        "frequencies_hz": [8.0, 9.0, 10.0],
        "roi_channels": list(ROI_CHANNELS),
        "roi_valid_channel_bitweights": {
            channel: 1 << index for index, channel in enumerate(ROI_CHANNELS)
        },
        "roi_valid_channel_bitmask_dtype": "uint16",
        "computational_channel": ROI_LABEL,
        "roi_policy": "equal_finite_channel_mean_minimum_one_all_missing_is_nan",
        "processing_order": ["Phase1_per_window_mask", "per_ID_channel_log3SD", "ROI_mean"]
        + (["own_ID_ROI_Set1_baseline_percent_change"] if change else [])
        + ["within_set_60_point_centered_nanmean_min1_for_plots", "progress_conversion"],
        "cache_policy": "read_only_current_No10_all32_cache_no_new_PSD_cache",
        "baseline": "unsmoothed_post_mask_ROI_Set1_finite_mean" if change else "none",
        "quantification": "unsmoothed_ROI_finite_window_mean_common_available_sets",
        "topography": False,
        "additional_subject_exclusions": [],
        "ccube_colors": list(engine.normalize_product("CCube")[2:]),
        "vrohto_colors": list(engine.normalize_product("VRohtoPremium")[2:]),
        "control_colors": [engine.CONTROL_COLOR, engine.CONTROL_QUANTIFICATION_COLOR],
        "source_script_sha256": {name: _sha256(SCRIPT_DIR / name) for name in scripts},
    }


def configuration_hash(configuration: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()


def _directories(original: Any, root: Path, product: str, stem: str) -> dict[str, Path]:
    paths = {
        key: path
        for key, path in original(root, product).items()
        if not key.startswith("topography")
    }
    paths["roi_quality_tables"] = root / "Phase4_脳波解析" / stem / "Sub" / "tables" / "ROIQuality"
    return paths


def build_absolute_engine() -> ModuleType:
    if (
        source_engine.ANALYSIS_STEM != "No10_FzLowAlpha"
        or source_engine.FOCUS_CHANNEL != "Fz"
        or not np.array_equal(source_engine.INCLUDED_FREQUENCIES_HZ, [8.0, 9.0, 10.0])
        or (
            source_engine.SFREQ,
            source_engine.WINDOW_SAMPLES,
            source_engine.STEP_SAMPLES,
            source_engine.PAD_SAMPLES,
        )
        != (256.0, 256, 256, 128)
    ):
        raise ValueError("No12 requires the unchanged No10 8–10 Hz all-channel source contract")
    engine = _isolated_engine("Phase4_No1_FmTheta.py", "_phase4_no12_absolute_engine")
    configure_band_engine(
        engine,
        analysis_stem=MAIN_STEM,
        cache_file_tag=source_engine.CACHE_FILE_TAG,
        focus_channel=ROI_LABEL,
        frequencies_hz=(8, 9, 10),
        script_version=MAIN_VERSION,
        cache_version=source_engine.CACHE_CONFIGURATION_VERSION,
        ccube_color="#4B4B4B",
        ccube_quantification_color="#787878",
        vrohto_color="#909090",
        vrohto_quantification_color="#B0B0B0",
    )
    engine.DEFAULT_CACHE_ROOT = source_engine.DEFAULT_CACHE_ROOT
    for name in ("cache_path", "validate_cache", "validate_participant_specs"):
        setattr(engine, name, getattr(source_engine, name))
    engine.load_session_cache = load_roi_session
    engine.load_pair_item = load_roi_pair
    original_directories = engine._output_directories
    engine._output_directories = lambda root, product: _directories(
        original_directories, root, product, MAIN_STEM
    )
    for name in (
        "compute_session_cache",
        "calculate_set_psd",
        "_write_cache",
        "plot_topography_grid",
    ):
        setattr(engine, name, _forbidden_generation)
    renderer = _isolated_engine("phase4_no11_cached_analysis.py", "_phase4_no12_renderer")
    renderer.MAIN_STEM = MAIN_STEM
    engine.write_individual_outputs = lambda item, root: renderer.write_absolute_individual(
        engine, item, root
    )
    engine.write_group_outputs = lambda items, root: renderer.write_absolute_groups(
        engine, items, root
    )
    engine.main = lambda: absolute_main(engine)
    return engine


def absolute_main(engine: ModuleType) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", action="append", type=engine.parse_participant, default=[])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cache-root", type=Path, default=engine.DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=engine.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--production-batch", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ("preflight-only", "individual-only", "group-outputs-only", "all"):
        modes.add_argument(f"--{mode}", action="store_true")
    args = parser.parse_args()
    _checked_roots(args)
    specs = list(args.participant)
    if args.manifest:
        specs.extend(engine.load_manifest(args.manifest))
    if not specs:
        raise SystemExit("Provide --participant or --manifest")
    engine.validate_participant_specs(specs, production_batch=args.production_batch)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items = [engine.load_pair_item(spec, args.cache_root) for spec in specs]
    provenance = cache_provenance(specs, args.cache_root)
    logging.info("%s cache/ROI preflight passed: %d pairs", MAIN_STEM, len(items))
    if args.preflight_only:
        return 0
    scope = (
        "AllParticipants" if args.production_batch else "_".join(f"ID{s.pair_id}" for s in specs)
    )
    paths = engine._output_directories(args.output_root, "CCube")
    threshold = source_engine.build_threshold_diagnostics(_source_items(items))
    threshold = threshold[threshold.Channel.isin(ROI_CHANNELS)]
    threshold_path = paths["threshold_tables"] / f"{MAIN_STEM}_Log3SDThresholdExclusion_{scope}.csv"
    threshold_path.parent.mkdir(parents=True, exist_ok=True)
    threshold.to_csv(threshold_path, index=False)
    quality = write_roi_quality(items, args.output_root, MAIN_STEM, scope)
    individual = {}
    if args.individual_only or args.all:
        for item in items:
            individual[item["spec"].pair_id] = engine.write_individual_outputs(
                item, args.output_root
            )
    groups = (
        engine.write_group_outputs(items, args.output_root)
        if args.group_outputs_only or args.all
        else {}
    )
    config = target_configuration(engine)
    downstream = engine.downstream_configuration()
    downstream["topography_smoothing"] = "not_applicable_no_topography"
    summary = {
        "script_version": engine.SCRIPT_VERSION,
        "git_commit": engine.git_revision(),
        "completed_at": datetime.now().astimezone().isoformat(),
        "mode": "all"
        if args.all
        else "individual-only"
        if args.individual_only
        else "group-outputs-only",
        "target_configuration": config,
        "target_configuration_hash": configuration_hash(config),
        "source_cache_configuration": source_engine.analysis_configuration(),
        "source_cache_records": provenance,
        "downstream_configuration": downstream,
        "participants": [asdict(spec) | {"pair_id": spec.pair_id} for spec in specs],
        "preflight": {"requested_pairs": len(specs), "analysable_pairs": len(items)},
        "log3sd_threshold_diagnostics": str(threshold_path),
        "roi_quality_tables": quality,
        "individual_outputs": individual,
        "group_outputs": groups,
    }
    suffix = "IndividualSummary" if args.individual_only else "RunSummary"
    engine._write_log(paths["logs"] / f"{MAIN_STEM}_{suffix}.json", summary)
    return 0


def build_change_engine(parent: ModuleType) -> ModuleType:
    engine = _isolated_engine("Phase4_No1_sub_FmThetaChange.py", "_phase4_no12_change_engine")
    engine.__doc__ = "Phase 4 No12_sub: own-ID Set-1-relative frontal ROI low-alpha change."
    configure_change_engine(
        engine,
        parent,
        analysis_stem=CHANGE_STEM,
        focus_channel=ROI_LABEL,
        script_version=CHANGE_VERSION,
        include_topography=False,
    )
    original_directories = engine.output_directories
    engine.output_directories = lambda root, product: _directories(
        original_directories, root, product, CHANGE_STEM
    )
    original_parser, original_preflight = engine.parse_args, engine.preflight
    original_write_log, original_baseline = engine.write_log, engine.baseline_table
    state: dict[str, Any] = {}

    def parse_args() -> argparse.Namespace:
        args = original_parser()
        _checked_roots(args)
        state["args"] = args
        return args

    def preflight(specs: list[Any], root: Path, production: bool) -> tuple[Any, Any]:
        items, summary = original_preflight(specs, root, production)
        state["provenance"] = cache_provenance(specs, root)
        state["items"] = items
        state["scope"] = (
            "AllAnalysablePairs" if production else "_".join(f"ID{s.pair_id}" for s in specs)
        )
        summary["baseline_definition"] = (
            "own_ID_unsmoothed_finite_ROI_Set1_mean_after_channel_average"
        )
        summary["roi_channels"] = list(ROI_CHANNELS)
        return items, summary

    def baseline_table(items: list[dict[str, Any]]) -> pd.DataFrame:
        table = original_baseline(items)
        counts = {}
        for item in items:
            for condition in ("eye_drop", "control"):
                session = item[condition].source
                values = session.sets[1].psd_band_mean[:, 0]
                counts[session.session_id] = (int(np.isfinite(values).sum()), len(values))
        table["Set1FiniteROIWindowCount"] = [counts[sid][0] for sid in table.SessionID]
        table["Set1TotalWindowCount"] = [counts[sid][1] for sid in table.SessionID]
        return table

    def write_log(path: Path, payload: dict[str, Any]) -> None:
        args = state["args"]
        quality = write_roi_quality(state["items"], args.output_root, CHANGE_STEM, state["scope"])
        config = target_configuration(parent, change=True)
        downstream = parent.downstream_configuration(0.70, "absolute_mean")
        downstream["topography_smoothing"] = "not_applicable_no_topography"
        original_write_log(
            path,
            payload
            | {
                "target_configuration": config,
                "target_configuration_hash": configuration_hash(config),
                "source_cache_configuration": source_engine.analysis_configuration(),
                "source_cache_records": state["provenance"],
                "downstream_configuration": downstream,
                "roi_quality_tables": quality,
            },
        )

    engine.parse_args, engine.preflight = parse_args, preflight
    engine.baseline_table, engine.write_log = baseline_table, write_log
    engine.plot_topography = _forbidden_generation
    return engine
