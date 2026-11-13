"""Pz low-alpha views of immutable, provenance-checked No10 all-channel caches.

The source engine retains its Fz/No10 identity for cache hash validation. Separate
module namespaces reuse the established numerical and plotting functions with
Pz and No11 labels. This module never computes or writes a PSD cache.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import logging
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import h5py
import numpy as np
from phase4_band_variant_config import configure_band_engine, configure_change_engine
from Phase4_No10_FzLowAlpha import engine as source_engine

MAIN_STEM = "No11_PzLowAlpha"
CHANGE_STEM = "No11_sub_PzLowAlphaChange"
MAIN_VERSION = "20261113_pz_lowalpha_cached_v1"
CHANGE_VERSION = "20261113_pz_lowalpha_change_cached_v1"
SCRIPT_DIR = Path(__file__).resolve().parent


def _isolated_engine(filename: str, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT_DIR / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load existing engine: {filename}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _forbidden_generation(*args: Any, **kwargs: Any) -> None:
    raise RuntimeError("No11 is cache-only and does not generate PSD caches or topography")


def _checked_roots(args: argparse.Namespace) -> None:
    if args.cache_root.resolve() != source_engine.DEFAULT_CACHE_ROOT.resolve():
        raise ValueError("No11 must read the authorized current No10 PSD cache root")
    if args.output_root.resolve() != source_engine.DEFAULT_OUTPUT_ROOT.resolve():
        raise ValueError("No11 outputs must use the authorized OneDrive result root")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def cache_provenance(specs: list[Any], cache_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for participant in specs:
        for sid in (participant.first_session_id, participant.second_session_id):
            path = source_engine.cache_path(cache_root, participant, sid)
            with h5py.File(path, "r") as handle:
                records.append(
                    {
                        "pair_id": participant.pair_id,
                        "session_id": sid,
                        "path": str(path),
                        "sha256": _sha256(path),
                        "configuration_hash": str(handle.attrs["configuration_hash"]),
                        "source_script_version": str(handle.attrs["script_version"]),
                        "focus_channel_selected_by_name": "Pz",
                        "source_cache_modified": False,
                    }
                )
    return records


def _target_configuration(engine: ModuleType) -> dict[str, Any]:
    return {
        "analysis_stem": engine.ANALYSIS_STEM,
        "script_version": engine.SCRIPT_VERSION,
        "focus_channel": "Pz",
        "frequencies_hz": [8.0, 9.0, 10.0],
        "cache_policy": "read_only_current_No10_all32_cache_no_PSD_recomputation",
        "topography": False,
        "additional_subject_exclusions": [],
        "ccube_colors": list(engine.normalize_product("CCube")[2:]),
        "vrohto_colors": list(engine.normalize_product("VRohtoPremium")[2:]),
        "control_colors": [engine.CONTROL_COLOR, engine.CONTROL_QUANTIFICATION_COLOR],
    }


def build_absolute_engine() -> ModuleType:
    if (
        source_engine.ANALYSIS_STEM != "No10_FzLowAlpha"
        or source_engine.FOCUS_CHANNEL != "Fz"
        or not np.array_equal(source_engine.INCLUDED_FREQUENCIES_HZ, [8.0, 9.0, 10.0])
        or source_engine.SFREQ != 256.0
        or source_engine.WINDOW_SAMPLES != 256
        or source_engine.STEP_SAMPLES != 256
        or source_engine.PAD_SAMPLES != 128
    ):
        raise ValueError("No11 requires the unchanged No10 all-channel 8–10 Hz cache contract")
    engine = _isolated_engine("Phase4_No1_FmTheta.py", "_phase4_no11_absolute_engine")
    configure_band_engine(
        engine,
        analysis_stem=MAIN_STEM,
        cache_file_tag=source_engine.CACHE_FILE_TAG,
        focus_channel="Pz",
        frequencies_hz=(8, 9, 10),
        script_version=MAIN_VERSION,
        cache_version=source_engine.CACHE_CONFIGURATION_VERSION,
        ccube_color="#476975",
        ccube_quantification_color="#7B949D",
        vrohto_color="#789BA3",
        vrohto_quantification_color="#A0B8BD",
    )
    engine.DEFAULT_CACHE_ROOT = source_engine.DEFAULT_CACHE_ROOT
    # These functions must retain the source engine's globals and Fz/No10 hash.
    for name in (
        "cache_path",
        "validate_cache",
        "load_session_cache",
        "load_pair_item",
        "validate_participant_specs",
    ):
        setattr(engine, name, getattr(source_engine, name))
    original_directories = engine._output_directories
    engine._output_directories = lambda root, product: {
        key: path
        for key, path in original_directories(root, product).items()
        if not key.startswith("topography")
    }
    for name in (
        "compute_session_cache", "calculate_set_psd", "_write_cache", "plot_topography_grid"
    ):
        setattr(engine, name, _forbidden_generation)
    engine.write_individual_outputs = lambda item, root: write_absolute_individual(
        engine, item, root
    )
    engine.write_group_outputs = lambda items, root: write_absolute_groups(engine, items, root)
    engine.main = lambda: absolute_main(engine)
    return engine


def write_absolute_individual(
    engine: ModuleType, item: dict[str, Any], output_root: Path
) -> dict[str, str]:
    paths = engine._output_directories(output_root, item["product_dir"])
    prefix = f"ID{item['spec'].pair_id}_{MAIN_STEM}_Individual"
    variants = (
        ("individual", "individual", "", {"smoothing_seconds": 60}),
        (
            "individual_unsmoothed_before_threshold",
            "individual_unsmoothed_before",
            "_Unsmoothed_BeforeThresholdExclusion",
            {"before_log3sd_exclusion": True},
        ),
        (
            "individual_unsmoothed_after_threshold",
            "individual_unsmoothed_after",
            "_Unsmoothed_AfterThresholdExclusion",
            {},
        ),
    )
    outputs: dict[str, str] = {}
    for key, directory, suffix, kwargs in variants:
        path = paths[directory] / f"{prefix}{suffix}.png"
        engine.plot_individual_timecourse(
            item["spec"], item["eye_drop"], item["control"], path, **kwargs
        )
        outputs[key] = str(path)
    return outputs


def write_absolute_groups(
    engine: ModuleType, items: list[dict[str, Any]], output_root: Path
) -> dict[str, Any]:
    """Existing No1 mean+SEM group rendering, without the topography branch."""
    products = sorted({item["product_dir"] for item in items})
    grand_by_product = {}
    upper_candidates = []
    fraction = engine.DEFAULT_GRAND_AVERAGE_TARGET_FRACTION
    for product in products:
        grand, _ = engine.build_grand_average(items, product)
        grand_by_product[product] = grand
        displayed = np.concatenate(
            [
                grand[f"{condition}_Mean_PSD_uV2_per_Hz"]
                + grand[f"{condition}_SEM_PSD_uV2_per_Hz"].fillna(0.0)
                for condition in ("EyeDrop", "Control")
            ]
        )
        upper_candidates.append(engine._nice_upper(displayed, fraction)[0])
    common_upper = max(upper_candidates)
    _, common_ticks = engine._nice_upper(np.array([common_upper * fraction]), fraction)
    if common_ticks[-1] != common_upper:
        step = common_ticks[1] - common_ticks[0]
        common_ticks = np.arange(0.0, common_upper + step * 0.01, step)
    outputs = {}
    for product in products:
        paths = engine._output_directories(output_root, product)
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        grand = grand_by_product[product]
        grand_png = paths["grand"] / f"{MAIN_STEM}_GrandAverage_{product}.png"
        grand_csv = paths["grand_tables"] / f"{MAIN_STEM}_GrandAverage_Values_{product}.csv"
        engine.plot_grand_average(
            grand, product, grand_png, common_upper=common_upper, common_ticks=common_ticks
        )
        grand.to_csv(grand_csv, index=False)
        values = engine.build_quantification(items, product)
        set_stats, all_stats = engine.quantification_statistics(values)
        set_png = paths["quantification"] / f"{MAIN_STEM}_SetQuantification_{product}.png"
        all_png = paths["quantification"] / f"{MAIN_STEM}_AllSetsQuantification_{product}.png"
        engine.plot_set_quantification(values, set_stats, product, set_png)
        engine.plot_all_sets_quantification(values, all_stats, product, all_png)
        set_stats.to_csv(
            paths["quantification"] / f"{MAIN_STEM}_SetQuantification_Statistics_{product}.csv",
            index=False,
        )
        values.to_csv(
            paths["quantification_tables"] / f"{MAIN_STEM}_SetQuantification_Values_{product}.csv",
            index=False,
        )
        all_stats.to_csv(
            paths["quantification_tables"]
            / f"{MAIN_STEM}_AllSetsQuantification_Statistics_{product}.csv",
            index=False,
        )
        outputs[product] = {
            "grand_average": str(grand_png),
            "set_quantification": str(set_png),
            "all_sets_quantification": str(all_png),
        }
    return outputs


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
    for item in items:
        for condition in ("eye_drop", "control"):
            engine._channel_index(item[condition], "Pz")
    provenance = cache_provenance(specs, args.cache_root)
    logging.info("%s cache preflight passed: %d pairs", MAIN_STEM, len(items))
    if args.preflight_only:
        return 0
    scope = "AllParticipants" if args.production_batch else "_".join(
        f"ID{spec.pair_id}" for spec in specs
    )
    paths = engine._output_directories(args.output_root, "CCube")
    threshold_path = paths["threshold_tables"] / f"{MAIN_STEM}_Log3SDThresholdExclusion_{scope}.csv"
    threshold_path.parent.mkdir(parents=True, exist_ok=True)
    engine.build_threshold_diagnostics(items).to_csv(threshold_path, index=False)
    individual_outputs = {}
    if args.individual_only or args.all:
        for item in items:
            individual_outputs[item["spec"].pair_id] = engine.write_individual_outputs(
                item, args.output_root
            )
    group_outputs = {}
    if args.group_outputs_only or args.all:
        group_outputs = engine.write_group_outputs(items, args.output_root)
    mode = (
        "all" if args.all else "individual-only" if args.individual_only else "group-outputs-only"
    )
    summary = {
        "script_version": engine.SCRIPT_VERSION,
        "git_commit": engine.git_revision(),
        "completed_at": datetime.now().astimezone().isoformat(),
        "mode": mode,
        "target_configuration": _target_configuration(engine),
        "source_cache_configuration": source_engine.analysis_configuration(),
        "source_cache_records": provenance,
        "downstream_configuration": engine.downstream_configuration(),
        "participants": [asdict(spec) | {"pair_id": spec.pair_id} for spec in specs],
        "preflight": {"requested_pairs": len(specs), "analysable_pairs": len(items)},
        "log3sd_threshold_diagnostics": str(threshold_path),
        "individual_outputs": individual_outputs,
        "group_outputs": group_outputs,
    }
    summary["downstream_configuration"]["topography_smoothing"] = "not_applicable_no_topography"
    suffix = "IndividualSummary" if args.individual_only else "RunSummary"
    path = paths["logs"] / f"{MAIN_STEM}_{suffix}.json"
    engine._write_log(path, summary)
    logging.info("%s completed: %s", MAIN_STEM, path)
    return 0


def build_change_engine(parent: ModuleType) -> ModuleType:
    engine = _isolated_engine("Phase4_No1_sub_FmThetaChange.py", "_phase4_no11_change_engine")
    configure_change_engine(
        engine,
        parent,
        analysis_stem=CHANGE_STEM,
        focus_channel="Pz",
        script_version=CHANGE_VERSION,
        include_topography=False,
    )
    original_directories = engine.output_directories
    engine.output_directories = lambda root, product: {
        key: path
        for key, path in original_directories(root, product).items()
        if not key.startswith("topography")
    }
    original_parser = engine.parse_args
    original_preflight = engine.preflight
    original_write_log = engine.write_log
    provenance: list[dict[str, Any]] = []

    def parse_args() -> argparse.Namespace:
        args = original_parser()
        _checked_roots(args)
        return args

    def preflight(specs: list[Any], cache_root: Path, production: bool) -> tuple[Any, Any]:
        items, summary = original_preflight(specs, cache_root, production)
        for item in items:
            for condition in ("eye_drop", "control"):
                parent._channel_index(item[condition].source, "Pz")
        provenance[:] = cache_provenance(specs, cache_root)
        return items, summary

    def write_log(path: Path, payload: dict[str, Any]) -> None:
        original_write_log(
            path,
            payload
            | {
                "target_configuration": _target_configuration(parent)
                | {"analysis_stem": CHANGE_STEM, "script_version": CHANGE_VERSION},
                "source_cache_configuration": source_engine.analysis_configuration(),
                "source_cache_records": provenance,
            },
        )

    engine.parse_args = parse_args
    engine.preflight = preflight
    engine.write_log = write_log
    engine.plot_topography = _forbidden_generation
    return engine
