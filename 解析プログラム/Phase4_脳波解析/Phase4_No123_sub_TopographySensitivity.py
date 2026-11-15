#!/usr/bin/env python3
"""No1--3 supplementary topographies using the approved No10 spatial/temporal v3.

Dedicated process only. Read existing band-specific PSD caches; never recompute
PSD or modify the primary analyses. Old sustained-rule exclusions are not reused.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import Phase4_No1_sub_FmThetaChange as engine
import phase4_no10_topography_spatiotemporal as qc
import Phase4_PSDChangeConditionwiseBidirectionalOutlierTopography as prior
from PIL import Image

VERSION = "20261115_no123_topography_spatiotemporal_sensitivity_v3"
PARENT = engine.no1
COMMON = prior.common
REPOSITORY = Path(__file__).resolve().parents[2]
EXPECTED_REPOSITORY = Path("/Users/aoiseki/GitHub/Analysis_project_roht_phase2")
EXPECTED_ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
PHASE_ROOT = PARENT.DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
CACHE_PHASE_ROOT = COMMON.DEFAULT_PHASE4_CACHE_ROOT
MANIFEST = PHASE_ROOT / "No10_FzLowAlpha/Sub/tables/ParticipantManifest.csv"
GLOBAL_TABLE_ROOT = PHASE_ROOT / "Sub/tables/No123TopographySensitivity"
PROTECTION_PATH = GLOBAL_TABLE_ROOT / "ProtectedInputOutputInventory.json"
LOG_PATH = PHASE_ROOT / "Sub/logs/No123_sub_TopographySensitivity_RunSummary.json"
REVIEW_PATH = PHASE_ROOT / "Sub/logs/No123_sub_TopographySensitivity_Review_20261115_v3.json"
INDEPENDENT_AUDIT_PATH = (
    PHASE_ROOT / "Sub/logs/No123_sub_TopographySensitivity_IndependentAudit_20261115_v3.json"
)
OLD_GLOBAL_LOG = (
    PHASE_ROOT
    / "Sub/logs/Phase4_PSDChange_ConditionwiseBidirectionalOutlierExclusion_RunSummary.json"
)
GLOBAL_HISTORY_ROOT = PHASE_ROOT / "Sub/history/BeforeNo123TopographySpatialTemporalV3_20261115"
HISTORY_NAME = "BeforeTopographySpatialTemporalV3_20261115"
CONFIGS = tuple(COMMON.ANALYSES.values())
PRODUCTS = ("CCube", "VRohtoPremium")
APPROVED = {
    "No1": (311, "cebc8568c1353baaa3c06aef0bb61066047daa8b761aa9a1322331fe4aa58e10"),
    "No2": (245, "2e9c46c4b73d8ab940d4e3c1f3bd8f65711f090cae567bb7466ce99825e8d329"),
    "No3": (435, "c532e19782b87357680f65f88989454a5813f12c3dfb39adff234b11b9955c0c"),
}
BAND_SETTINGS = {
    "No1": ("Fz", (4.0, 5.0, 6.0, 7.0), "phase4-no1-fmtheta-2026-10-04.3"),
    "No2": ("Oz", tuple(float(n) for n in range(8, 16)), "phase4-no2-occipital-alpha-2026-10-04.1"),
    "No3": ("Fz", (1.0, 2.0, 3.0), "phase4-no3-frontal-delta-2026-10-04.1"),
}
TABLE_NAMES = (
    "session_flags",
    "excluded_cells",
    "group_audit",
    "all_condition_metrics",
    "large_scale_individual_benchmark",
    "v2_component_comparison",
)
OLD_TABLE_PREFIX = "ExploratorySet1AbsolutePSD_SustainedChange"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")
    if path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"JSON readback mismatch: {path}")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Empty audit table: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with path.open(encoding="utf-8", newline="") as stream:
        if len(list(csv.DictReader(stream))) != len(rows):
            raise RuntimeError(f"CSV readback mismatch: {path}")


def verify_repository() -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(REPOSITORY), *args], text=True).strip()

    if REPOSITORY != EXPECTED_REPOSITORY or git("rev-parse", "--show-toplevel") != str(REPOSITORY):
        raise ValueError("Unexpected repository root")
    if git("remote", "get-url", "origin") != EXPECTED_ORIGIN:
        raise ValueError("Unexpected origin")
    return git("rev-parse", "HEAD")


def sub_root(config: COMMON.AnalysisConfig) -> Path:
    return PHASE_ROOT / config.output_analysis_stem


def cache_root(config: COMMON.AnalysisConfig) -> Path:
    return CACHE_PHASE_ROOT / config.cache_root_name / "PSDTimeSeries"


def table_root(config: COMMON.AnalysisConfig) -> Path:
    return sub_root(config) / "Sub/tables/TopographySensitivity"


def analysis_log(config: COMMON.AnalysisConfig) -> Path:
    return (
        sub_root(config)
        / f"Sub/logs/{config.output_analysis_stem}_TopographySensitivity_RunSummary.json"
    )


def history_root(config: COMMON.AnalysisConfig) -> Path:
    return sub_root(config) / "Sub/history" / HISTORY_NAME


def original_path(config: COMMON.AnalysisConfig, product: str) -> Path:
    return prior.unexcluded_output_path(PARENT.DEFAULT_OUTPUT_ROOT, config, product)


def output_path(config: COMMON.AnalysisConfig, product: str) -> Path:
    original = original_path(config, product)
    return original.with_stem(original.stem + "_ExploratorySpatialTemporalExcluded")


def comparison_path(config: COMMON.AnalysisConfig, product: str, stage: str) -> Path:
    return prior.supplemental_output_path(PARENT.DEFAULT_OUTPUT_ROOT, config, product, stage)


def legacy_png(config: COMMON.AnalysisConfig, product: str) -> Path:
    return prior.output_paths(PARENT.DEFAULT_OUTPUT_ROOT, config, product)


def old_audit_paths(config: COMMON.AnalysisConfig) -> list[Path]:
    directory = sub_root(config) / "Sub/tables"
    return [
        directory / f"{OLD_TABLE_PREFIX}_{suffix}"
        for suffix in ("SessionFlags.csv", "ExcludedCells.csv", "GroupAudit.csv", "RunSummary.json")
    ]


def generated_paths() -> list[Path]:
    return [
        path
        for config in CONFIGS
        for product in PRODUCTS
        for path in (output_path(config, product), comparison_path(config, product, "After"))
    ]


def input_png_preflight() -> None:
    for config in CONFIGS:
        for product in PRODUCTS:
            original, before = (
                original_path(config, product),
                comparison_path(config, product, "Before"),
            )
            if not original.is_file() or not before.is_file():
                raise FileNotFoundError(f"Original and Before are mandatory: {original}")
            if digest(original) != digest(before):
                raise ValueError(
                    f"Before is not byte-identical to the protected original: {before}"
                )
            for directory, allowed in (
                (
                    original.parent,
                    {original, output_path(config, product), legacy_png(config, product)},
                ),
                (before.parent, {before, comparison_path(config, product, "After")}),
            ):
                if set(directory.glob("*.png")) - allowed:
                    raise ValueError(
                        f"Unexpected PNGs; refusing to infer deletion targets: {directory}"
                    )


def expected_cache_hash(config: COMMON.AnalysisConfig, fingerprints: list[dict]) -> str:
    """Build each band's original cache signature without mutating shared globals."""
    if PARENT.ANALYSIS_STEM != "No1_FmTheta" or engine.ANALYSIS_STEM != "No1_sub_FmThetaChange":
        raise ValueError("Run in a dedicated process; another band mutated shared engine globals")
    settings = PARENT.analysis_configuration()
    focus, bins, version = BAND_SETTINGS[config.key]
    settings.update(
        analysis_stem=config.cache_analysis_stem,
        focus_channel=focus,
        frequencies_hz=list(bins),
        script_version=version,
    )
    if config.key == "No1":
        # The immutable No1 caches were created by Git 3c7c25b (writer .7),
        # before these two metadata keys entered the configuration signature.
        # Their actual band/identity attributes are validated independently below.
        settings.pop("analysis_stem")
        settings.pop("focus_channel")
    payload = {"configuration": settings, "inputs": fingerprints}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verify_saved_log_mask(handle: h5py.File) -> None:
    """Independently verify saved 3SD thresholds/masks/counts; no PSD recomputation."""
    groups = {n: handle[f"sets/Set{n}"] for n in range(1, 7) if f"sets/Set{n}" in handle}
    # Reproduce the cache creator's dtype for its saved threshold (often float32).
    # Downstream means/ratios independently use the normal float64 session loader.
    values = {n: group["psd_band_mean"][:] for n, group in groups.items()}
    valid = {
        n: np.isfinite(v) & (v > 0) & (groups[n]["ica_training_mask_fraction"][:][:, None] < 0.01)
        for n, v in values.items()
    }
    means, sds = [], []
    for ch in range(32):
        pooled = np.concatenate([v[valid[n][:, ch], ch] for n, v in values.items()])
        if pooled.size < 2:
            means.append(np.nan)
            sds.append(np.nan)
        else:
            logged = np.log10(pooled)
            means.append(float(logged.mean()))
            sds.append(float(logged.std(ddof=1)))
    means, sds = np.asarray(means), np.asarray(sds)
    threshold = means + 3.0 * sds
    for name, expected in (
        ("mean", means),
        ("sd", sds),
        ("threshold_log", threshold),
        ("threshold_linear", 10.0**threshold),
    ):
        np.testing.assert_allclose(
            handle[f"qc/log3sd_{name}_by_channel"][:],
            expected,
            rtol=1e-12,
            atol=1e-12,
            equal_nan=True,
        )
    counts = np.zeros((6, 32), dtype=int)
    valid_counts = np.zeros((6, 32), dtype=int)
    rates = np.full((6, 32), np.nan)
    for n, v in values.items():
        logged = np.full(v.shape, np.nan)
        logged[valid[n]] = np.log10(v[valid[n]])
        mask = valid[n] & (logged > threshold)
        np.testing.assert_array_equal(groups[n]["log3sd_outlier_mask"][:].astype(bool), mask)
        counts[n - 1] = mask.sum(axis=0)
        valid_counts[n - 1] = valid[n].sum(axis=0)
        np.divide(
            counts[n - 1], valid_counts[n - 1], out=rates[n - 1], where=valid_counts[n - 1] > 0
        )
    for name, expected in (
        ("excluded_count", counts),
        ("valid_count", valid_counts),
        ("excluded_rate", rates),
    ):
        np.testing.assert_allclose(
            handle[f"qc/log3sd_{name}_by_set_ch"][:],
            expected,
            rtol=1e-12,
            atol=1e-12,
            equal_nan=True,
        )


def cache_preflight(config: COMMON.AnalysisConfig, specs: list) -> dict:
    paths = sorted(cache_root(config).glob("*.h5"))
    if len(paths) != 80:
        raise ValueError(f"{config.key}: expected 80 immutable cache files")
    by_session = {
        sid: spec for spec in specs for sid in (spec.first_session_id, spec.second_session_id)
    }
    seen = set()
    missing = {}
    checks = []
    for path in paths:
        with h5py.File(path, "r") as handle:
            attrs = handle.attrs
            sid = str(attrs["participant_id"])
            if sid in seen or sid not in by_session:
                raise ValueError(f"Unexpected/duplicate session: {sid}")
            seen.add(sid)
            spec = by_session[sid]
            condition = "Eye Drop" if sid == spec.drops_session_id else "Control"
            if (
                str(attrs["pair_id"]) != spec.pair_id
                or COMMON._normalise_condition(str(attrs["condition"])) != condition
            ):
                raise ValueError(f"ID/condition mismatch against manifest: {path}")
            if (
                PARENT.normalize_product(str(attrs["product"]))[0]
                != PARENT.normalize_product(spec.product)[0]
            ):
                raise ValueError(f"Product mismatch: {path}")
            if int(attrs["session_order"]) != (1 if sid == spec.first_session_id else 2):
                raise ValueError(f"Session order mismatch: {path}")
            bins = BAND_SETTINGS[config.key][1]
            np.testing.assert_array_equal(json.loads(str(attrs["included_frequencies_hz"])), bins)
            numeric = {
                "sampling_frequency_hz": 256.0,
                "window_samples": 256,
                "step_samples": 256,
                "n_fft": 256,
                "n_per_seg": 256,
                "n_overlap": 0,
                "fmin_hz": min(bins),
                "fmax_hz": max(bins),
                "log3sd_multiplier": 3.0,
            }
            for key, value in numeric.items():
                if float(attrs[key]) != value:
                    raise ValueError(f"Cache parameter mismatch: {path}, {key}")
            texts = {
                "input_signal_unit": "V",
                "psd_unit": "uV^2/Hz",
                "window_function": "hann",
                "psd_method": "mne.time_frequency.psd_array_welch",
                "time_smoothing": "none",
                "log3sd_transform": "log10",
                "log3sd_sides": "upper_only",
                "log3sd_scope": "session_id_x_channel_across_all_available_sets",
                "interval_mask_policy": "retain_all_samples_store_window_overlap_fraction",
                "channel_mask_policy": "retain_all_32_channels_store_phase1_ica_mask",
                "script_version": (
                    "phase4-no1-fmtheta-2026-10-04.7"
                    if config.key == "No1"
                    else BAND_SETTINGS[config.key][2]
                ),
            }
            for key, value in texts.items():
                if str(attrs[key]) != value:
                    raise ValueError(f"Cache parameter mismatch: {path}, {key}")
            expected_hash = expected_cache_hash(
                config, json.loads(str(attrs["input_fingerprints_json"]))
            )
            PARENT.validate_cache(path, expected_hash=expected_hash)
            absent = {n for n in range(1, 7) if f"sets/Set{n}" not in handle}
            if absent != PARENT.EXPECTED_MISSING_SETS.get(sid, set()):
                raise ValueError(f"Unexpected missing Set(s): {path}, {absent}")
            if absent:
                missing[sid] = sorted(absent)
            verify_saved_log_mask(handle)
        checks.append(
            {"path": str(path), "sha256": digest(path), "configuration_hash": expected_hash}
        )
    if seen != set(by_session):
        raise ValueError("Cache/manifest session coverage differs")
    return {
        "sessions": 80,
        "missing_by_session": missing,
        "cache_checks": checks,
        "frequency_bins_hz": list(BAND_SETTINGS[config.key][1]),
        "stored_log3sd_threshold_masks_counts_independently_verified": True,
    }


def electrode_geometry() -> tuple[np.ndarray, np.ndarray]:
    info = PARENT._topomap_info()
    if list(info["ch_names"]) != list(PARENT.EXPECTED_CHANNEL_NAMES):
        raise ValueError("Montage/channel order mismatch")
    positions = np.array([ch["loc"][:3] for ch in info["chs"]])
    return positions, qc.nearest_four(positions)


def independent_pair_values(item: dict) -> np.ndarray:
    output = np.full((6, 32), np.nan)
    eye, control = item["eye_drop"].source, item["control"].source
    baselines = [np.nanmean(session.sets[1].psd_band_mean, axis=0) for session in (eye, control)]
    if not all(np.all(np.isfinite(b) & (b > 0)) for b in baselines):
        raise ValueError("Invalid Set 1 baseline outside known excluded pair")
    for n in eye.sets.keys() & control.sets.keys():
        output[n - 1] = 100.0 * (
            np.nanmean(eye.sets[n].psd_band_mean, axis=0) / baselines[0]
            - np.nanmean(control.sets[n].psd_band_mean, axis=0) / baselines[1]
        )
    return output


def check_original_group_values(config: COMMON.AnalysisConfig, items: list, before: dict) -> dict:
    for item in items:
        np.testing.assert_allclose(
            engine.pair_topography_values(item),
            independent_pair_values(item),
            rtol=1e-10,
            atol=1e-8,
            equal_nan=True,
        )
    maximum_error = 0.0
    for product in PRODUCTS:
        path = (
            sub_root(config)
            / "Sub/tables/Topography"
            / (f"{config.output_analysis_stem}_Topography_GrandAverage_Values_{product}.csv")
        )
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        if [int(row["Set"]) for row in rows] != list(range(1, 7)):
            raise ValueError(f"Unexpected Set rows: {path}")
        values = np.array(
            [[float(row[ch]) for ch in PARENT.EXPECTED_CHANNEL_NAMES] for row in rows]
        )
        n = np.array([int(row["Valid_N"]) for row in rows])
        np.testing.assert_allclose(before[product]["group"], values, rtol=1e-10, atol=1e-8)
        np.testing.assert_array_equal(before[product]["valid_n"], np.repeat(n[:, None], 32, axis=1))
        maximum_error = max(maximum_error, float(np.max(np.abs(before[product]["group"] - values))))
    return {"independently_checked_pairs": len(items), "maximum_original_ga_error": maximum_error}


def verify_excluded_group(items: list, causes: dict, products: dict) -> None:
    for product in PRODUCTS:
        arrays = []
        for item in items:
            if item["product_dir"] != product:
                continue
            values = independent_pair_values(item)
            for pair, n, ch in causes:
                if n == 1:
                    raise ValueError("Baseline map cannot be masked")
                if pair == item["spec"].pair_id:
                    values[n - 1, ch] = np.nan
            arrays.append(values)
        stack = np.stack(arrays)
        n = np.isfinite(stack).sum(axis=0)
        if np.any(n == 0):
            raise ValueError("Zero residual paired N")
        np.testing.assert_array_equal(n, products[product]["valid_n"])
        np.testing.assert_allclose(
            np.nanmean(stack, axis=0), products[product]["group"], rtol=1e-10, atol=1e-8
        )


def mask_digest(applied: set[tuple]) -> str:
    cells = sorted(
        [str(pair), int(n), PARENT.EXPECTED_CHANNEL_NAMES[ch]] for pair, n, ch in applied
    )
    return hashlib.sha256(
        json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def approved_mask_check(config: COMMON.AnalysisConfig, applied: set[tuple]) -> dict:
    count, checksum = APPROVED[config.key]
    actual = mask_digest(applied)
    if len(applied) != count or actual != checksum:
        raise ValueError(
            f"{config.key} approved mask mismatch: count={len(applied)}, sha256={actual}"
        )
    return {"cells": count, "sha256": actual, "exact_approved_set_match": True}


def verify_v2_component(previous: set[tuple], applied: set[tuple]) -> dict:
    if previous - applied:
        raise ValueError("v3 dropped an unchanged v2-pathway exclusion")
    return {
        "v2_component_cells": len(previous),
        "v2_component_sha256": mask_digest(previous),
        "all_v2_component_cells_retained": True,
        "newly_added_cells": len(applied - previous),
        "old_no123_sustained_mask_used": False,
    }


def flattened_metrics(rows: list[dict]) -> list[dict]:
    output = []
    for row in rows:
        scalars = {k: v for k, v in row.items() if not isinstance(v, np.ndarray)}
        for ch, name in enumerate(PARENT.EXPECTED_CHANNEL_NAMES):
            output.append(
                {
                    **scalars,
                    "channel": name,
                    **{k: v[ch].item() for k, v in row.items() if isinstance(v, np.ndarray)},
                }
            )
    return output


def benchmark_rows(items: list, applied: set[tuple]) -> list[dict]:
    rows = []
    for item in items:
        values = engine.pair_topography_values(item)
        limit = engine._topography_limit(values)
        if limit < 800:
            continue
        index = np.unravel_index(np.nanargmax(np.abs(values)), values.shape)
        n, ch = int(index[0]) + 1, int(index[1])
        rows.append(
            {
                "pair_id": item["spec"].pair_id,
                "product": item["product_dir"],
                "original_colour_limit": limit,
                "largest_set": n,
                "largest_channel": PARENT.EXPECTED_CHANNEL_NAMES[ch],
                "largest_difference_pp": float(values[index]),
                "largest_cell_excluded": (item["spec"].pair_id, n, ch) in applied,
            }
        )
    return rows


def prepare_analysis(config: COMMON.AnalysisConfig, specs: list) -> dict:
    preflight = cache_preflight(config, specs)
    items = COMMON.load_items(cache_root(config))
    if len(items) != 39 or any(item["spec"].pair_id == "109-209" for item in items):
        raise ValueError("Unexpected baseline-eligible pair set")
    positions, neighbors = electrode_geometry()
    metrics = qc.collect_condition_metrics(items, neighbors)
    _, v2_causes = qc.evaluate_flags(
        metrics,
        list(PARENT.EXPECTED_CHANNEL_NAMES),
        include_change_extension=False,
        annotate_rows=False,
    )
    v2_products, _, _, _, v2_applied = prior.group_topographies(config, items, v2_causes)
    flags, causes = qc.evaluate_flags(metrics, list(PARENT.EXPECTED_CHANNEL_NAMES))
    before, eligible_before, _, _, _ = prior.group_topographies(config, items, {})
    products, eligible, excluded, group_audit, applied = prior.group_topographies(
        config, items, causes
    )
    if eligible != eligible_before or eligible != 6144:
        raise ValueError("Original eligible denominator changed")
    original_check = check_original_group_values(config, items, before)
    verify_excluded_group(items, causes, products)
    simulation_check = approved_mask_check(config, applied)
    retention_check = verify_v2_component(v2_applied, applied)
    for row in group_audit:
        product, n, ch = (
            row["product"],
            row["set"] - 1,
            PARENT.EXPECTED_CHANNEL_NAMES.index(row["channel"]),
        )
        row.update(
            before_difference_pp=float(before[product]["group"][n, ch]),
            before_valid_n=int(before[product]["valid_n"][n, ch]),
            removed_paired_cells=int(before[product]["valid_n"][n, ch]) - row["valid_n"],
            v2_component_difference_pp=float(v2_products[product]["group"][n, ch]),
            v2_component_valid_n=int(v2_products[product]["valid_n"][n, ch]),
        )
    pair_products = {item["spec"].pair_id: item["product_dir"] for item in items}
    exclusions = [
        {
            "pair_id": pair,
            "product": pair_products[pair],
            "set": n,
            "channel": PARENT.EXPECTED_CHANNEL_NAMES[ch],
            "trigger_conditions": ";".join(sorted({entry["condition"] for entry in entries})),
            "trigger_sessions": ";".join(sorted({entry["session_id"] for entry in entries})),
            "reasons": ";".join(sorted({entry["reason"] for entry in entries})),
            "trigger_source_sets": ";".join(
                str(s) for s in sorted({entry["source_set"] for entry in entries})
            ),
            "baseline_propagated": any(entry["baseline_propagated"] for entry in entries),
            "paired_or_applied": True,
            "applied_to_original_finite_cell": (pair, n, ch) in applied,
        }
        for (pair, n, ch), entries in sorted(causes.items())
    ]
    comparison = [
        {
            "pair_id": pair,
            "product": pair_products[pair],
            "set": n,
            "channel": PARENT.EXPECTED_CHANNEL_NAMES[ch],
            "excluded_v2_component": (pair, n, ch) in v2_causes,
            "excluded_v3": True,
            "status": "retained_v2_component" if (pair, n, ch) in v2_causes else "added_v3",
            "applied_to_original_finite_cell": (pair, n, ch) in applied,
        }
        for pair, n, ch in sorted(causes)
    ]
    ranges = {}
    for product in PRODUCTS:
        selected = [item for item in items if item["product_dir"] == product]
        denominator = sum(
            int(np.isfinite(engine.pair_topography_values(item)[1:]).sum()) for item in selected
        )
        removed = sum(pair_products[pair] == product for pair, _, _ in applied)
        ranges[product] = {
            "baseline_eligible_pairs": len(selected),
            "eligible_postbaseline_pair_channel_set_cells": denominator,
            "excluded_pair_channel_set_cells": removed,
            "exclusion_rate_pct": 100.0 * removed / denominator,
            "minimum_postbaseline_n": int(products[product]["valid_n"][1:].min()),
            "maximum_postbaseline_n": int(products[product]["valid_n"][1:].max()),
            "before_colour_limit": engine._topography_limit(before[product]["group"]),
            "after_colour_limit": engine._topography_limit(products[product]["group"]),
            "before_max_abs_difference_pp": float(np.abs(before[product]["group"]).max()),
            "after_max_abs_difference_pp": float(np.abs(products[product]["group"]).max()),
            "before_max_abs_local_residual_pp": before[product][
                "max_abs_local_neighbor_residual_pct"
            ],
            "after_max_abs_local_residual_pp": products[product][
                "max_abs_local_neighbor_residual_pct"
            ],
        }
    summary = {
        "analysis": config.output_analysis_stem,
        "preflight": preflight,
        "approved_simulation_check": simulation_check,
        "v2_component_retention_check": retention_check,
        "original_numerical_check": original_check,
        "independent_masked_group_check": "passed",
        "eligible_pair_channel_set_cells_sets2_6": eligible,
        "excluded_pair_channel_set_cells_sets2_6": excluded,
        "exclusion_rate_pct": 100.0 * excluded / eligible,
        "session_flag_count": len(flags),
        "cause_cell_count_including_already_missing": len(causes),
        "products": ranges,
        "frequency_bins_hz": list(BAND_SETTINGS[config.key][1]),
        "electrode_geometry": {
            "montage": "colin27_1020",
            "distance": "3D Euclidean nearest four",
            "channels": list(PARENT.EXPECTED_CHANNEL_NAMES),
            "positions_m": positions.tolist(),
            "neighbor_indices": neighbors.tolist(),
        },
        "nonfinite_condition_metric_cells": int(
            sum(np.sum(~np.isfinite(row["ratio"]) | ~np.isfinite(row["median"])) for row in metrics)
        ),
    }
    return {
        "config": config,
        "products": products,
        "summary": summary,
        "tables": {
            "session_flags": flags,
            "excluded_cells": exclusions,
            "group_audit": group_audit,
            "all_condition_metrics": flattened_metrics(metrics),
            "large_scale_individual_benchmark": benchmark_rows(items, applied),
            "v2_component_comparison": comparison,
        },
    }


def inventory(root: Path, *, hashes: bool, excluded: set[Path] | None = None) -> dict:
    output = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store" or path in (excluded or set()):
            continue
        stat = path.stat()
        record = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if hashes:
            record["sha256"] = digest(path)
        output[str(path)] = record
    return output


def protected_inventory() -> dict:
    writable = set(generated_paths()) | {
        LOG_PATH,
        REVIEW_PATH,
        INDEPENDENT_AUDIT_PATH,
        PROTECTION_PATH,
        OLD_GLOBAL_LOG,
    }
    writable.update(p for p in GLOBAL_HISTORY_ROOT.rglob("*") if p.is_file())
    target_roots = set()
    own, caches = {}, {}
    for config in CONFIGS:
        target_roots.add(sub_root(config))
        writable.add(analysis_log(config))
        writable.update(old_audit_paths(config))
        writable.update(table_root(config) / f"{name}.csv" for name in TABLE_NAMES)
        writable.update(legacy_png(config, p) for p in PRODUCTS)
        writable.update(p for p in history_root(config).rglob("*") if p.is_file())
        own.update(inventory(sub_root(config), hashes=True, excluded=writable))
        caches.update(inventory(cache_root(config), hashes=True))
    others = {}
    for directory in PHASE_ROOT.iterdir():
        if directory.is_dir() and directory not in target_roots:
            others.update(inventory(directory, hashes=False, excluded=writable))
    other_caches = {}
    target_cache_roots = {cache_root(config).parent for config in CONFIGS}
    for directory in CACHE_PHASE_ROOT.iterdir():
        if directory.is_dir() and directory not in target_cache_roots:
            other_caches.update(inventory(directory, hashes=False))
    # The comparison Before files live outside target roots; protect their bytes explicitly.
    before = {
        str(comparison_path(c, p, "Before")): digest(comparison_path(c, p, "Before"))
        for c in CONFIGS
        for p in PRODUCTS
    }
    return {
        "existing_no123_files": own,
        "no123_cache_hashes": caches,
        "comparison_before_sha256": before,
        "other_phase4_file_inventory": others,
        "other_band_cache_inventory": other_caches,
    }


def archive_records(root: Path, history: Path, candidates: list[Path]) -> dict:
    manifest = history / "ArchiveManifest.json"
    if manifest.is_file():
        archive = verify_archive(history)
        saved = json.loads(manifest.read_text(encoding="utf-8"))
        for record in saved["files"]:
            source = root / record["source_relative_path"]
            if source.exists() and digest(source) != record["sha256"]:
                raise ValueError(f"An obsolete current record changed after migration: {source}")
        return archive
    records = []
    for source in candidates:
        if not source.is_file():
            raise FileNotFoundError(f"Prior audit record required for migration: {source}")
        if source.suffix not in {".csv", ".json", ".log"}:
            raise ValueError("Only exact non-PNG audit records may be archived")
        relative = source.relative_to(root)
        destination = history / relative
        checksum = digest(source)
        if destination.exists() and digest(destination) != checksum:
            raise ValueError("Preserved history must never be overwritten")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        if digest(destination) != checksum:
            raise RuntimeError("History copy checksum mismatch")
        records.append({"source_relative_path": str(relative), "sha256": checksum})
    write_json(
        manifest,
        {
            "status": "obsolete_no123_sustained_method_history_only",
            "replacement_version": VERSION,
            "created_at": datetime.now().astimezone().isoformat(),
            "files": records,
        },
    )
    return verify_archive(history)


def verify_archive(history: Path) -> dict:
    manifest = history / "ArchiveManifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    expected = {manifest}
    for record in payload["files"]:
        path = history / record["source_relative_path"]
        if not path.is_relative_to(history) or ".." in path.parts:
            raise ValueError("Invalid archive path")
        if digest(path) != record["sha256"]:
            raise ValueError("Archived record changed")
        expected.add(path)
    actual = {p for p in history.rglob("*") if p.is_file() and p.name != ".DS_Store"}
    if actual != expected:
        raise ValueError("Unexpected archive contents")
    return {
        "manifest_path": str(manifest),
        "manifest_sha256": digest(manifest),
        "files": len(payload["files"]),
        "verified": True,
    }


def retire_old_records(root: Path, history: Path) -> None:
    payload = json.loads((history / "ArchiveManifest.json").read_text(encoding="utf-8"))
    for record in payload["files"]:
        source = root / record["source_relative_path"]
        if source.is_file():
            if digest(source) != record["sha256"]:
                raise ValueError("Cannot retire changed audit record")
            source.unlink()


def validate_source_audit(path: Path | None) -> dict:
    if path is None:
        raise ValueError("--execute requires --source-audit")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("participant_manifest_sha256") != digest(MANIFEST):
        raise ValueError("Source audit/manifest hash mismatch")
    if (
        record.get("notion_verified") is not True
        or not record.get("checked_at")
        or not record.get("source_pages")
    ):
        raise ValueError("Current Notion method review is incomplete")
    if record.get("analysis_scope") is not None and set(record["analysis_scope"]) != {
        "No1",
        "No2",
        "No3",
    }:
        raise ValueError("Source audit scope mismatch")
    return {"path": str(path), "sha256": digest(path), "content": record}


def source_hashes() -> dict:
    files = [
        Path(__file__),
        Path(qc.__file__),
        Path(prior.__file__),
        Path(COMMON.__file__),
        Path(engine.__file__),
        Path(PARENT.__file__),
    ]
    return {str(path.relative_to(REPOSITORY)): digest(path) for path in files}


def assert_input_hashes(prepared: list[dict]) -> None:
    for data in prepared:
        for record in data["summary"]["preflight"]["cache_checks"]:
            if digest(Path(record["path"])) != record["sha256"]:
                raise ValueError("An input cache changed during processing")


def check_output_layout() -> None:
    for config in CONFIGS:
        for product in PRODUCTS:
            primary = {original_path(config, product), output_path(config, product)}
            comparison = {comparison_path(config, product, stage) for stage in ("Before", "After")}
            if set(original_path(config, product).parent.glob("*.png")) != primary:
                raise ValueError("Primary folder must contain original plus latest only")
            if set(comparison_path(config, product, "Before").parent.glob("*.png")) != comparison:
                raise ValueError("Comparison folder must contain Before and After only")
            if digest(output_path(config, product)) != digest(
                comparison_path(config, product, "After")
            ):
                raise ValueError("After copy is not identical to the latest figure")
            if digest(original_path(config, product)) != digest(
                comparison_path(config, product, "Before")
            ):
                raise ValueError("Protected original and Before differ")


def run(*, execute: bool, source_audit: Path | None = None) -> dict:
    revision = verify_repository()
    started = datetime.now().astimezone().isoformat()
    source_review = validate_source_audit(source_audit) if execute else None
    manifest_checksum = digest(MANIFEST)
    specs = PARENT.load_manifest(MANIFEST)
    PARENT.validate_participant_specs(specs, production_batch=True)
    input_png_preflight()
    sources = source_hashes()
    protected = protected_inventory() if execute else None
    prepared = [prepare_analysis(config, specs) for config in CONFIGS]
    assert_input_hashes(prepared)
    if digest(MANIFEST) != manifest_checksum or source_hashes() != sources:
        raise ValueError("Manifest or analysis source changed during numerical preflight")
    summary = {
        "script_version": VERSION,
        "aggregation_helper_version": prior.SCRIPT_VERSION,
        "repository_commit": revision,
        "source_sha256": sources,
        "command": [sys.executable, *sys.argv],
        "started_at": started,
        "source_review": source_review,
        "manifest_path": str(MANIFEST),
        "manifest_sha256": manifest_checksum,
        "status": "dry_run_validated" if not execute else "numerical_audit_passed_before_output",
        "parameters": asdict(qc.PARAMETERS),
        "method": "conditionwise_v2_pathways_OR_guarded_change_extension_paired_OR_v3",
        "reference_pool": (
            "each band independently: original 78 eligible sessions, both products and conditions"
        ),
        "old_no123_sustained_mask_used": False,
        "specified_pair_exclusions_used": False,
        "baseline": (
            "post-Phase1/log3SD-mask unsmoothed Set1 arithmetic mean, per session and channel"
        ),
        "set1_propagation": (
            "spatial absolute or temporal flags propagate same channel to Sets2-6; "
            "Set1 map retained"
        ),
        "paired_or": (
            "either condition flagged removes the pair x channel x Set from both conditions"
        ),
        "posthoc_colour_benchmark": (
            "individual range >=800 is audit only, never a detection criterion"
        ),
        "psd_recomputed": False,
        "cache_modified": False,
        "analyses": {data["config"].key: data["summary"] for data in prepared},
        "visual_review": "pending; image readback and numerical audit are not visual review",
        "cloud_sync": "OneDrive server-side synchronisation not independently verified",
        "limitations": (
            "Exploratory post-hoc sensitivity, not confirmed noise diagnosis or evidence of "
            "product/anatomical specificity."
        ),
    }
    if not execute:
        return summary
    if protected_inventory() != protected:
        raise ValueError("Protected files changed before output generation")
    archives = {
        config.key: archive_records(sub_root(config), history_root(config), old_audit_paths(config))
        for config in CONFIGS
    }
    archives["global"] = archive_records(PHASE_ROOT, GLOBAL_HISTORY_ROOT, [OLD_GLOBAL_LOG])
    for data in prepared:
        config = data["config"]
        for product in PRODUCTS:
            destination = output_path(config, product)
            destination.parent.mkdir(parents=True, exist_ok=True)
            engine.plot_topography(data["products"][product]["group"], destination)
            after = comparison_path(config, product, "After")
            after.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(destination, after)
            if digest(destination) != digest(after):
                raise RuntimeError("After copy hash mismatch")
    for path in generated_paths():
        with Image.open(path) as image:
            image.verify()
    # Delete precisely named obsolete PNGs only after all 12 replacements read back.
    removed = []
    for config in CONFIGS:
        for product in PRODUCTS:
            old = legacy_png(config, product)
            if old.is_file():
                removed.append({"path": str(old), "sha256": digest(old)})
                old.unlink()
    check_output_layout()
    table_records = {}
    for data in prepared:
        config = data["config"]
        records = {}
        for name, rows in data["tables"].items():
            path = table_root(config) / f"{name}.csv"
            write_csv(path, rows)
            records[name] = {"path": str(path), "sha256": digest(path), "rows": len(rows)}
        table_records[config.key] = records
        retire_old_records(sub_root(config), history_root(config))
    retire_old_records(PHASE_ROOT, GLOBAL_HISTORY_ROOT)
    assert_input_hashes(prepared)
    if protected_inventory() != protected:
        raise RuntimeError("A protected original/cache/other-analysis file changed")
    for config in CONFIGS:
        if verify_archive(history_root(config)) != archives[config.key]:
            raise RuntimeError("Prior archive changed")
    if verify_archive(GLOBAL_HISTORY_ROOT) != archives["global"]:
        raise RuntimeError("Global prior archive changed")
    if source_hashes() != sources or digest(MANIFEST) != manifest_checksum:
        raise RuntimeError("Source or manifest changed during output generation")
    if digest(Path(source_review["path"])) != source_review["sha256"]:
        raise RuntimeError("Source review changed during output generation")
    write_json(PROTECTION_PATH, protected)
    summary.update(
        status="generated_and_numerically_verified_visual_review_pending",
        completed_at=datetime.now().astimezone().isoformat(),
        outputs=[{"path": str(path), "sha256": digest(path)} for path in generated_paths()],
        tables=table_records,
        prior_history=archives,
        removed_legacy_pngs=removed,
        protection={
            "unchanged": True,
            "inventory_path": str(PROTECTION_PATH),
            "inventory_sha256": digest(PROTECTION_PATH),
            "target_files_hash_checked": len(protected["existing_no123_files"]),
            "cache_files_hash_checked": len(protected["no123_cache_hashes"]),
            "before_pngs_hash_checked": 6,
            "other_files_stat_checked": len(protected["other_phase4_file_inventory"]),
        },
    )
    for config in CONFIGS:
        write_json(
            analysis_log(config),
            {
                **summary["analyses"][config.key],
                "script_version": VERSION,
                "status": summary["status"],
                "global_summary_path": str(LOG_PATH),
                "source_sha256": sources,
                "tables": table_records[config.key],
                "outputs": [
                    entry
                    for entry in summary["outputs"]
                    if config.output_analysis_stem in entry["path"]
                ],
                "prior_history": archives[config.key],
                "visual_review": summary["visual_review"],
            },
        )
    summary["analysis_logs"] = {
        config.key: {"path": str(analysis_log(config)), "sha256": digest(analysis_log(config))}
        for config in CONFIGS
    }
    write_json(LOG_PATH, summary)
    return summary


def validate_review_record(review: dict, summary: dict, revision: str) -> None:
    expected = {entry["path"]: entry["sha256"] for entry in summary["outputs"]}
    reviewed = review.get("reviewed_pngs", [])
    actual = {entry["path"]: entry["sha256"] for entry in reviewed}
    if (
        len(reviewed) != len(expected)
        or actual != expected
        or any(entry.get("reviewed") is not True for entry in reviewed)
    ):
        raise ValueError(
            "Visual review must cover all 12 latest and After-copy PNGs, without duplicates"
        )
    if not review.get("checked_at"):
        raise ValueError("Review time is required")
    observations = review.get("observations", {})
    if any(
        not observations.get(config.key, {}).get(product)
        for config in CONFIGS
        for product in PRODUCTS
    ):
        raise ValueError("Observations required for all six analysis/product figures")
    if not review.get("tests") or not review.get("notion_pages"):
        raise ValueError("Tests and verified Notion references required")
    git = review.get("git", {})
    if (
        git.get("head") != revision
        or git.get("remote_head") != revision
        or git.get("remote_verified") is not True
    ):
        raise ValueError("Review requires current local and remotely verified Git commit")


def verify_git_delivery(revision: str) -> dict:
    """Verify the current branch against the live remote and a clean working tree."""

    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(REPOSITORY), *args], text=True).rstrip(
            "\n"
        )

    branch = git("symbolic-ref", "--short", "HEAD")
    status = git("status", "--porcelain=v1", "--untracked-files=all", "-z")
    for entry in status.split("\0"):
        if not entry:
            continue
        # Renames/deletions are rejected too; only existing unrelated .DS_Store is tolerated.
        name = entry[3:]
        if name != ".DS_Store" and not name.endswith("/.DS_Store"):
            raise ValueError("Commit all scoped code/doc/test changes before final review")
    remote = git("ls-remote", "origin", f"refs/heads/{branch}")
    lines = [line.split() for line in remote.splitlines() if line]
    if len(lines) != 1 or lines[0] != [revision, f"refs/heads/{branch}"]:
        raise ValueError("Live remote branch does not match current local HEAD")
    return {
        "head": revision,
        "remote_head": lines[0][0],
        "branch": branch,
        "remote_verified": True,
        "working_tree_clean_except_ds_store": True,
    }


def validate_independent_audit(review: dict, summary: dict) -> dict:
    """An external implementation must independently match masks, values, and paired N."""
    entry = review.get("independent_audit", {})
    if entry.get("path") != str(INDEPENDENT_AUDIT_PATH):
        raise ValueError("Review must identify the canonical independent audit")
    if entry.get("sha256") != digest(INDEPENDENT_AUDIT_PATH):
        raise ValueError("Independent audit hash mismatch")
    audit = json.loads(INDEPENDENT_AUDIT_PATH.read_text(encoding="utf-8"))
    if audit.get("status") != "passed" or not audit.get("checked_at"):
        raise ValueError("Independent audit has not passed")
    if audit.get("source_cache_hashes_match") is not True:
        raise ValueError("Independent audit must verify the unchanged source caches")
    if set(audit.get("analyses", {})) != {config.key for config in CONFIGS}:
        raise ValueError("Independent audit must cover all three bands")
    for config in CONFIGS:
        actual = audit["analyses"][config.key]
        expected = summary["analyses"][config.key]["approved_simulation_check"]
        if actual.get("mask_sha256") != expected["sha256"]:
            raise ValueError("Independent mask differs from the approved production mask")
        if actual.get("group_values_match") is not True or actual.get("valid_n_match") is not True:
            raise ValueError("Independent group values/paired N do not match")
    return {
        "path": str(INDEPENDENT_AUDIT_PATH),
        "sha256": digest(INDEPENDENT_AUDIT_PATH),
        "status": "passed",
        "analysis_scope": [config.key for config in CONFIGS],
    }


def record_review(path: Path) -> dict:
    revision = verify_repository()
    if path.resolve() != REVIEW_PATH.resolve():
        raise ValueError(f"Save final review at the canonical path: {REVIEW_PATH}")
    summary = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    if summary.get("script_version") != VERSION or summary.get("status") not in {
        "generated_and_numerically_verified_visual_review_pending",
        "delivery_verified",
    }:
        raise ValueError("Current numerical run is not ready for review")
    review = json.loads(path.read_text(encoding="utf-8"))
    validate_review_record(review, summary, revision)
    independent_audit = validate_independent_audit(review, summary)
    live_git = verify_git_delivery(revision)
    if source_hashes() != summary["source_sha256"]:
        raise ValueError("Analysis source changed since numerical run")
    if digest(MANIFEST) != summary["manifest_sha256"]:
        raise ValueError("Manifest changed after run")
    records = list(summary["outputs"])
    records.extend(entry for tables in summary["tables"].values() for entry in tables.values())
    records.extend(summary["analysis_logs"].values())
    records.append(summary["source_review"])
    for entry in records:
        if digest(Path(entry["path"])) != entry["sha256"]:
            raise ValueError(f"Output/audit/source evidence changed: {entry['path']}")
    protection_path = Path(summary["protection"]["inventory_path"])
    if digest(protection_path) != summary["protection"]["inventory_sha256"]:
        raise ValueError("Protected inventory record changed")
    if json.loads(protection_path.read_text(encoding="utf-8")) != protected_inventory():
        raise ValueError("Protected files changed since execution")
    for config in CONFIGS:
        if verify_archive(history_root(config)) != summary["prior_history"][config.key]:
            raise ValueError("Preserved history changed")
    if verify_archive(GLOBAL_HISTORY_ROOT) != summary["prior_history"]["global"]:
        raise ValueError("Global history changed")
    check_output_layout()
    summary.update(
        status="delivery_verified",
        visual_review=review,
        review_record_path=str(path),
        review_record_sha256=digest(path),
        verified_repository_commit=revision,
        independent_audit=independent_audit,
        live_git_delivery_check=live_git,
        finalized_at=datetime.now().astimezone().isoformat(),
        finalization_command=[sys.executable, *sys.argv],
    )
    # Per-analysis logs remain immutable execution evidence; final status is centralized.
    write_json(LOG_PATH, summary)
    return {"status": summary["status"], "log": str(LOG_PATH), "repository_commit": revision}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="Read/validate all three bands; write nothing"
    )
    mode.add_argument(
        "--execute", action="store_true", help="Replace only No1--3 supplementary topographies"
    )
    mode.add_argument(
        "--record-review", type=Path, help="Finalize verified external review without recomputing"
    )
    parser.add_argument("--source-audit", type=Path)
    parser.add_argument("--full-json", action="store_true", help="Print full audit JSON to stdout")
    args = parser.parse_args()
    result = (
        record_review(args.record_review)
        if args.record_review
        else run(execute=args.execute, source_audit=args.source_audit)
    )
    if not args.full_json and "analyses" in result:
        result = {
            "status": result["status"],
            "script_version": result["script_version"],
            "log": str(LOG_PATH) if args.execute else None,
            "analyses": {
                key: {
                    "approved_simulation_check": value["approved_simulation_check"],
                    "products": value["products"],
                }
                for key, value in result["analyses"].items()
            },
        }
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
