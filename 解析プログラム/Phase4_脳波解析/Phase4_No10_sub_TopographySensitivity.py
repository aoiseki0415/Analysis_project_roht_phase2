#!/usr/bin/env python3
"""Additional No10_sub topographies using approved spatial/temporal QC v2.

Run in a dedicated process. Existing No10 outputs and 8--10 Hz caches are
read-only; only this supplementary analysis and comparison copies are written.
The 800-unit individual colour range is an audit benchmark, never a detector.
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

import numpy as np
import phase4_no10_topography_spatiotemporal as qc
import Phase4_PSDChangeConditionwiseBidirectionalOutlierTopography as prior
from Phase4_No10_sub_FzLowAlphaChange import engine
from PIL import Image

VERSION = "20261114_no10_topography_spatiotemporal_sensitivity_v2"
APPROVED_MASK_SHA256 = "0a85ed2933cc3c3207b349e1cc1a3075bfe00c2526404e6c6ddf1f8114360248"
APPROVED_MASK_COUNT = 215
REPOSITORY = Path(__file__).resolve().parents[2]
EXPECTED_REPOSITORY = Path("/Users/aoiseki/GitHub/Analysis_project_roht_phase2")
EXPECTED_ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
PARENT = engine.no1
PHASE_ROOT = PARENT.DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
MAIN_ROOT = PHASE_ROOT / "No10_FzLowAlpha"
SUB_ROOT = PHASE_ROOT / "No10_sub_FzLowAlphaChange"
CACHE_ROOT = PARENT.DEFAULT_CACHE_ROOT
MANIFEST = MAIN_ROOT / "Sub/tables/ParticipantManifest.csv"
TABLE_ROOT = SUB_ROOT / "Sub/tables/TopographySensitivity"
LOG_PATH = SUB_ROOT / "Sub/logs/No10_sub_FzLowAlphaChange_TopographySensitivity_RunSummary.json"
REVIEW_PATH = SUB_ROOT / "Sub/logs/No10_sub_TopographySensitivity_Review_20261114_v2.json"
HISTORY_ROOT = SUB_ROOT / "Sub/history/BeforeTopographySpatialTemporalV2_20261114"
TABLE_NAMES = (
    "session_flags",
    "excluded_cells",
    "group_audit",
    "all_condition_metrics",
    "large_scale_individual_benchmark",
)
CONFIG = prior.common.AnalysisConfig(
    "No10", "Fz low-alpha (8-10 Hz)", "No10_FzLowAlpha", "No10_sub_FzLowAlphaChange"
)
PRODUCTS = ("CCube", "VRohtoPremium")


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_repository() -> str:
    def git(*args: str) -> str:
        return subprocess.check_output(["git", "-C", str(REPOSITORY), *args], text=True).strip()

    if REPOSITORY != EXPECTED_REPOSITORY or git("rev-parse", "--show-toplevel") != str(
        EXPECTED_REPOSITORY
    ):
        raise ValueError("Unexpected repository root")
    if git("remote", "get-url", "origin") != EXPECTED_ORIGIN:
        raise ValueError("Unexpected Git origin")
    return git("rev-parse", "HEAD")


def electrode_geometry() -> tuple[np.ndarray, np.ndarray]:
    info = PARENT._topomap_info()
    if list(info["ch_names"]) != list(PARENT.EXPECTED_CHANNEL_NAMES):
        raise ValueError("Montage channel order differs from PSD channels")
    positions = np.array([channel["loc"][:3] for channel in info["chs"]])
    return positions, qc.nearest_four(positions)


def collect_condition_metrics(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return qc.collect_condition_metrics(items, electrode_geometry()[1])


def independent_pair_values(item: dict[str, Any]) -> np.ndarray:
    """Independent means/ratios from already mask-applied absolute PSD."""
    output = np.full((6, 32), np.nan)
    eye = item["eye_drop"].source
    control = item["control"].source
    eye_baseline = np.nanmean(eye.sets[1].psd_band_mean, axis=0)
    control_baseline = np.nanmean(control.sets[1].psd_band_mean, axis=0)
    for number in eye.sets.keys() & control.sets.keys():
        eye_mean = np.nanmean(eye.sets[number].psd_band_mean, axis=0)
        control_mean = np.nanmean(control.sets[number].psd_band_mean, axis=0)
        output[number - 1] = 100.0 * (eye_mean / eye_baseline - control_mean / control_baseline)
    return output


def check_original_group_values(
    items: list[dict[str, Any]], before: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Compare unsmoothed pair differences and unexcluded GA against originals."""
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
            SUB_ROOT
            / "Sub/tables/Topography"
            / (f"{CONFIG.output_analysis_stem}_Topography_GrandAverage_Values_{product}.csv")
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
    return {
        "all_pairs_independently_checked": len(items),
        "maximum_original_ga_error": maximum_error,
    }


def verify_excluded_group(
    items: list[dict[str, Any]], causes: dict, products: dict[str, dict[str, Any]]
) -> None:
    """Independent paired-OR masking and channel-specific means/N."""
    for product in PRODUCTS:
        arrays = []
        for item in items:
            if item["product_dir"] != product:
                continue
            values = independent_pair_values(item)
            for pair, number, channel in causes:
                if pair == item["spec"].pair_id:
                    if number == 1:
                        raise ValueError("Supplement must not mask the baseline map")
                    values[number - 1, channel] = np.nan
            arrays.append(values)
        stack = np.stack(arrays)
        n = np.isfinite(stack).sum(axis=0)
        if np.any(n == 0):
            raise ValueError("A topography channel has no remaining paired observations")
        np.testing.assert_array_equal(n, products[product]["valid_n"])
        np.testing.assert_allclose(
            np.nanmean(stack, axis=0), products[product]["group"], rtol=1e-10, atol=1e-8
        )


def benchmark_rows(items: list[dict[str, Any]], applied: set[tuple]) -> list[dict[str, Any]]:
    """Audit large-scale individual maps, without using this benchmark to select."""
    rows = []
    for item in items:
        values = engine.pair_topography_values(item)
        limit = engine._topography_limit(values)
        if limit < 800.0:
            continue
        index = np.unravel_index(np.nanargmax(np.abs(values)), values.shape)
        number, channel = int(index[0]) + 1, int(index[1])
        rows.append(
            {
                "pair_id": item["spec"].pair_id,
                "product": item["product_dir"],
                "original_colour_limit": limit,
                "largest_set": number,
                "largest_channel": PARENT.EXPECTED_CHANNEL_NAMES[channel],
                "largest_difference_pp": float(values[index]),
                "largest_cell_excluded": (item["spec"].pair_id, number, channel) in applied,
            }
        )
    return rows


def flattened_metrics(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        scalars = {key: value for key, value in row.items() if not isinstance(value, np.ndarray)}
        for channel, name in enumerate(PARENT.EXPECTED_CHANNEL_NAMES):
            output.append(
                {
                    **scalars,
                    "channel": name,
                    **{
                        key: value[channel].item()
                        for key, value in row.items()
                        if isinstance(value, np.ndarray)
                    },
                }
            )
    return output


def original_path(product: str) -> Path:
    return prior.unexcluded_output_path(PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, product)


def output_path(product: str) -> Path:
    original = original_path(product)
    return original.with_stem(original.stem + "_ExploratorySpatialTemporalExcluded")


def supplement_paths() -> list[Path]:
    paths = []
    for product in PRODUCTS:
        paths.append(output_path(product))
        paths.extend(
            prior.supplemental_output_path(PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, product, stage)
            for stage in ("Before", "After")
        )
    return paths


def inventory(root: Path, *, hashes: bool, excluded: set[Path] | None = None) -> dict:
    entries = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store" or path in (excluded or set()):
            continue
        stat = path.stat()
        record = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if hashes:
            record["sha256"] = digest(path)
        entries[str(path)] = record
    return entries


def protected_inventory() -> dict:
    writable = set(supplement_paths()) | {LOG_PATH, REVIEW_PATH}
    writable.update(prior.output_paths(PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, p) for p in PRODUCTS)
    writable.update(TABLE_ROOT / f"{name}.csv" for name in TABLE_NAMES)
    writable.add(TABLE_ROOT / "ProtectedInputOutputInventory.json")
    # Only this explicit migration archive is separately protected by its manifest.
    writable.update(path for path in HISTORY_ROOT.rglob("*") if path.is_file())
    own = {}
    own.update(inventory(MAIN_ROOT, hashes=True))
    own.update(inventory(SUB_ROOT, hashes=True, excluded=writable))
    caches = inventory(CACHE_ROOT, hashes=True)
    others = {}
    for directory in PHASE_ROOT.iterdir():
        if directory.is_dir() and directory not in {MAIN_ROOT, SUB_ROOT}:
            others.update(inventory(directory, hashes=False, excluded=writable))
    for directory in CACHE_ROOT.parent.parent.iterdir():
        if directory.is_dir() and directory != CACHE_ROOT.parent:
            others.update(inventory(directory, hashes=False))
    return {
        "existing_no10_files": own,
        "no10_cache_hashes": caches,
        "other_analysis_inventory": others,
    }


def archive_prior_records() -> dict:
    """Copy exact v1 audit records once; keep history immutable on reruns."""
    manifest = HISTORY_ROOT / "ArchiveManifest.json"
    if manifest.is_file():
        return verify_archive()
    if not LOG_PATH.is_file():
        raise FileNotFoundError("Previous sensitivity log is required for v1 migration")
    old = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    if old.get("script_version") == VERSION:
        raise ValueError("v2 output exists without the required v1 migration archive")
    candidates = {LOG_PATH, TABLE_ROOT / "ProtectedInputOutputInventory.json"}
    candidates.update(TABLE_ROOT / f"{name}.csv" for name in TABLE_NAMES)
    for name in (old.get("review_record_path"), (old.get("source_review") or {}).get("path")):
        if name:
            candidate = Path(name)
            if candidate.is_relative_to(SUB_ROOT) and candidate.is_file():
                candidates.add(candidate)
    records = []
    for source in sorted(candidates):
        if not source.is_file():
            raise FileNotFoundError(f"Expected v1 audit file is absent: {source}")
        if source.suffix not in {".csv", ".json", ".log"}:
            raise ValueError("Only non-PNG audit records may enter the migration archive")
        relative = source.relative_to(SUB_ROOT)
        destination = HISTORY_ROOT / relative
        checksum = digest(source)
        if destination.exists() and digest(destination) != checksum:
            raise ValueError("Existing history must not be overwritten")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copy2(source, destination)
        if digest(destination) != checksum:
            raise RuntimeError("History copy checksum mismatch")
        records.append({"source_relative_path": str(relative), "sha256": checksum})
    write_json(
        manifest,
        {
            "status": "obsolete_v1_history_only",
            "source_version": old.get("script_version"),
            "replacement_version": VERSION,
            "created_at": datetime.now().astimezone().isoformat(),
            "files": records,
        },
    )
    return verify_archive()


def verify_archive() -> dict:
    manifest = HISTORY_ROOT / "ArchiveManifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    expected = {manifest}
    for record in payload["files"]:
        path = HISTORY_ROOT / record["source_relative_path"]
        if not path.is_relative_to(HISTORY_ROOT) or ".." in path.parts:
            raise ValueError("Invalid history path")
        if digest(path) != record["sha256"]:
            raise ValueError("A preserved v1 audit record changed")
        expected.add(path)
    actual = {p for p in HISTORY_ROOT.rglob("*") if p.is_file() and p.name != ".DS_Store"}
    if actual != expected:
        raise ValueError("Unexpected file in exact v1 migration archive")
    return {
        "manifest_path": str(manifest),
        "manifest_sha256": digest(manifest),
        "files": len(payload["files"]),
        "verified": True,
    }


def approved_mask_check(applied: set[tuple]) -> dict:
    cells = sorted(
        [str(pair), int(number), PARENT.EXPECTED_CHANNEL_NAMES[channel]]
        for pair, number, channel in applied
    )
    checksum = hashlib.sha256(
        json.dumps(cells, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if len(cells) != APPROVED_MASK_COUNT or checksum != APPROVED_MASK_SHA256:
        raise ValueError(
            f"Approved simulation mask mismatch: {len(cells)} cells, SHA256 {checksum}"
        )
    return {"cells": len(cells), "sha256": checksum, "exact_approved_set_match": True}


def validate_source_audit(path: Path | None) -> dict:
    if path is None:
        raise ValueError("--execute requires --source-audit from the current Notion review")
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("participant_manifest_sha256") != digest(MANIFEST):
        raise ValueError("Source audit does not match the current manifest")
    if record.get("notion_verified") is not True:
        raise ValueError("Live Notion review has not been verified")
    if not record.get("checked_at") or not record.get("source_pages"):
        raise ValueError("Source audit must identify the review time and source pages")
    return {"path": str(path), "sha256": digest(path), "content": record}


def source_hashes() -> dict[str, str]:
    files = [
        Path(__file__),
        Path(qc.__file__),
        Path(prior.__file__),
        Path(prior.common.__file__),
        Path(engine.__file__),
        Path(PARENT.__file__),
        Path(__file__).with_name("Phase4_No10_FzLowAlpha.py"),
        Path(__file__).with_name("Phase4_No10_sub_FzLowAlphaChange.py"),
        Path(__file__).with_name("phase4_band_variant_config.py"),
        Path(__file__).with_name("phase4_no10_cache_guard.py"),
    ]
    return {str(path.relative_to(REPOSITORY)): digest(path) for path in files}


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write an empty audit table: {path}")
    fields = sorted({key for row in rows for key in row})
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with path.open(encoding="utf-8", newline="") as stream:
        if len(list(csv.DictReader(stream))) != len(rows):
            raise RuntimeError(f"CSV readback row count mismatch: {path}")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(text, encoding="utf-8")
    if path.read_text(encoding="utf-8") != text:
        raise RuntimeError(f"JSON readback mismatch: {path}")


def run(*, execute: bool, source_audit: Path | None = None) -> dict:
    revision = verify_repository()
    started = datetime.now().astimezone().isoformat()
    source_review = validate_source_audit(source_audit) if execute else None
    specs = PARENT.load_manifest(MANIFEST)
    items, preflight = engine.preflight(specs, CACHE_ROOT, production=True)
    if len(list(CACHE_ROOT.glob("*.h5"))) != 80:
        raise ValueError("Expected exactly 80 No10 session caches")
    if any(not original_path(product).is_file() for product in PRODUCTS):
        raise FileNotFoundError("Original Grand-average topography is required")
    positions, neighbors = electrode_geometry()
    metric_rows = qc.collect_condition_metrics(items, neighbors)
    flags, causes = qc.evaluate_flags(metric_rows, list(PARENT.EXPECTED_CHANNEL_NAMES))
    before, eligible_before, _, _, _ = prior.group_topographies(CONFIG, items, {})
    products, eligible, excluded, group_audit, applied = prior.group_topographies(
        CONFIG, items, causes
    )
    if eligible_before != eligible:
        raise AssertionError("Exclusion changed the original eligible denominator")
    original_check = check_original_group_values(items, before)
    verify_excluded_group(items, causes, products)
    simulation_check = approved_mask_check(applied)
    for row in group_audit:
        product, number = row["product"], row["set"] - 1
        channel = PARENT.EXPECTED_CHANNEL_NAMES.index(row["channel"])
        row["before_difference_pp"] = float(before[product]["group"][number, channel])
        row["before_valid_n"] = int(before[product]["valid_n"][number, channel])
        row["removed_paired_cells"] = row["before_valid_n"] - row["valid_n"]
    pair_products = {item["spec"].pair_id: item["product_dir"] for item in items}
    exclusion_rows = [
        {
            "pair_id": pair,
            "product": pair_products[pair],
            "set": number,
            "channel": PARENT.EXPECTED_CHANNEL_NAMES[channel],
            "trigger_conditions": ";".join(sorted({entry["condition"] for entry in entries})),
            "trigger_sessions": ";".join(sorted({entry["session_id"] for entry in entries})),
            "reasons": ";".join(sorted({entry["reason"] for entry in entries})),
            "trigger_source_sets": ";".join(
                str(n) for n in sorted({entry["source_set"] for entry in entries})
            ),
            "baseline_propagated": any(entry["baseline_propagated"] for entry in entries),
            "paired_or_applied": True,
            "applied_to_original_finite_cell": (pair, number, channel) in applied,
        }
        for (pair, number, channel), entries in sorted(causes.items())
    ]
    benchmark = benchmark_rows(items, applied)
    ranges = {}
    for product in PRODUCTS:
        selected = [item for item in items if item["product_dir"] == product]
        original_count = sum(
            int(np.isfinite(engine.pair_topography_values(item)[1:]).sum()) for item in selected
        )
        removed = sum(pair_products[pair] == product for pair, _, _ in applied)
        ranges[product] = {
            "baseline_eligible_pairs": len(selected),
            "eligible_postbaseline_pair_channel_set_cells": original_count,
            "excluded_pair_channel_set_cells": removed,
            "exclusion_rate_pct": 100.0 * removed / original_count,
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
        "script_version": VERSION,
        "aggregation_helper_version": prior.SCRIPT_VERSION,
        "repository_commit": revision,
        "source_sha256": source_hashes(),
        "command": [sys.executable, *sys.argv],
        "started_at": started,
        "analysis": CONFIG.output_analysis_stem,
        "frequency_bins_hz": PARENT.INCLUDED_FREQUENCIES_HZ.tolist(),
        "status": "dry_run_validated" if not execute else "numerical_audit_passed_before_output",
        "source_review": source_review,
        "manifest_path": str(MANIFEST),
        "manifest_sha256": digest(MANIFEST),
        "preflight": preflight,
        "parameters": asdict(qc.PARAMETERS),
        "method": "conditionwise_spatial_isolation_OR_temporal_concentration_paired_OR_v2",
        "approved_simulation_check": simulation_check,
        "electrode_geometry": {
            "montage": "colin27_1020",
            "coordinate_frame": "MNE Info head coordinates",
            "distance": "3D Euclidean; nearest four excluding self",
            "channels": list(PARENT.EXPECTED_CHANNEL_NAMES),
            "positions_m": positions.tolist(),
            "neighbor_indices": neighbors.tolist(),
            "neighbor_names": [
                [PARENT.EXPECTED_CHANNEL_NAMES[i] for i in row] for row in neighbors
            ],
        },
        "method_notes": {
            "qc_baseline": "post-mask unsmoothed Set 1 arithmetic mean, session x channel",
            "change_baseline": "post-mask unsmoothed Set 1 arithmetic mean, session x channel",
            "reference_pool": (
                "all eligible sessions across both products and conditions; "
                "channel-specific; later metrics also Set-specific"
            ),
            "spatial": "log2 ratio/median local residual; within-row and same-Set/ch cohort z",
            "strict_neighbors": "greater than twofold in one direction from at least 3/4 neighbors",
            "temporal": "top ceil(10% finite windows) share >=0.5 AND mean/median >=3 AND z>=3.5",
            "no_sustained_block_rule": True,
            "paired_or": "either condition flags same pair x channel x Set in both conditions",
            "set1_propagation": (
                "Set 1 spatial absolute or temporal flag removes same pair x channel in Sets 2-6; "
                "baseline map retained"
            ),
            "benchmark": (
                "individual colour limit >=800 is a post-hoc audit guide only, "
                "not an exclusion threshold or desired-map optimisation"
            ),
            "specified_pair_exclusion": (
                "not applied; separate Fz-only specified-pair sensitivity is untouched"
            ),
        },
        "eligible_pair_channel_set_cells_sets2_6": eligible,
        "excluded_pair_channel_set_cells_sets2_6": excluded,
        "exclusion_rate_pct": 100.0 * excluded / eligible,
        "session_flag_count": len(flags),
        "products": ranges,
        "large_scale_individual_benchmark": benchmark,
        "original_numerical_check": original_check,
        "independent_masked_group_check": "passed",
        "psd_recomputed": False,
        "cache_modified": False,
        "visual_review": "pending; numerical and image-readback checks are not visual review",
        "cloud_sync": "server-side synchronisation not independently verified",
        "limitations": (
            "Post-hoc exploratory quality sensitivity. A flagged channel is not a confirmed "
            "noise diagnosis, and anatomical specificity or product effects are not "
            "established by exclusion."
        ),
        "warnings": {
            "nonfinite_condition_metric_cells": int(
                sum(
                    np.sum(~np.isfinite(row["ratio"]) | ~np.isfinite(row["median"]))
                    for row in metric_rows
                )
            ),
            "missing_handling": (
                "No imputation; original missing cells do not count as new exclusions"
            ),
            "statistical_inference": (
                "No statistical test of anatomical specificity or product effect"
            ),
        },
    }
    if not execute:
        return summary

    protected = protected_inventory()
    archive = archive_prior_records()
    generated = []
    for product in PRODUCTS:
        after = output_path(product)
        engine.plot_topography(products[product]["group"], after)
        for stage, source in (("Before", original_path(product)), ("After", after)):
            destination = prior.supplemental_output_path(
                PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, product, stage
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if digest(source) != digest(destination):
                raise RuntimeError("Supplemental comparison copy differs from source")
            generated.append(destination)
        generated.append(after)
    for path in generated:
        with Image.open(path) as image:
            image.verify()
    # Only the explicitly superseded PNGs are removed, after all replacements read back.
    removed_legacy = []
    for product in PRODUCTS:
        old = prior.output_paths(PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, product)
        if old.is_file():
            removed_legacy.append({"path": str(old), "sha256": digest(old)})
            old.unlink()
        expected = {original_path(product), output_path(product)}
        if set(output_path(product).parent.glob("*.png")) != expected:
            raise RuntimeError(
                "Topography folder must contain original plus latest sensitivity only"
            )
        comparison = prior.supplemental_output_path(
            PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, product, "Before"
        ).parent
        expected_copies = {
            prior.supplemental_output_path(PARENT.DEFAULT_OUTPUT_ROOT, CONFIG, product, stage)
            for stage in ("Before", "After")
        }
        if set(comparison.glob("*.png")) != expected_copies:
            raise RuntimeError("Comparison folder must contain only current Before/After")
    tables = {
        "session_flags": flags,
        "excluded_cells": exclusion_rows,
        "group_audit": group_audit,
        "all_condition_metrics": flattened_metrics(metric_rows),
        "large_scale_individual_benchmark": benchmark,
    }
    table_paths = {}
    for name, rows in tables.items():
        path = TABLE_ROOT / f"{name}.csv"
        write_csv(path, rows)
        table_paths[name] = {"path": str(path), "sha256": digest(path), "rows": len(rows)}
    # Own new output paths are excluded from this inventory; everything else is protected.
    current = protected_inventory()
    if current != protected:
        raise RuntimeError("A protected original/cache/other-analysis file changed")
    if verify_archive() != archive:
        raise RuntimeError("Archived v1 evidence changed during execution")
    protection_path = TABLE_ROOT / "ProtectedInputOutputInventory.json"
    write_json(protection_path, protected)
    summary.update(
        {
            "status": "generated_and_numerically_verified_visual_review_pending",
            "completed_at": datetime.now().astimezone().isoformat(),
            "outputs": [{"path": str(path), "sha256": digest(path)} for path in generated],
            "tables": table_paths,
            "v1_history": archive,
            "removed_legacy_pngs": removed_legacy,
            "protection": {
                "no10_original_files_hash_checked": len(protected["existing_no10_files"]),
                "no10_caches_hash_checked": len(protected["no10_cache_hashes"]),
                "other_analysis_files_size_mtime_checked": len(
                    protected["other_analysis_inventory"]
                ),
                "unchanged": True,
                "inventory_path": str(protection_path),
                "inventory_sha256": digest(protection_path),
            },
        }
    )
    write_json(LOG_PATH, summary)
    return summary


def record_review(path: Path) -> dict:
    """Finalize externally performed visual/document/Git review without rerunning."""
    revision = verify_repository()
    summary = json.loads(LOG_PATH.read_text(encoding="utf-8"))
    if summary["status"] not in {
        "generated_and_numerically_verified_visual_review_pending",
        "delivery_verified",
    }:
        raise ValueError("The supplementary output run has not passed numerical validation")
    review = json.loads(path.read_text(encoding="utf-8"))
    expected = {entry["path"]: entry["sha256"] for entry in summary["outputs"]}
    actual = {entry["path"]: entry["sha256"] for entry in review.get("reviewed_pngs", [])}
    if actual != expected or any(
        entry.get("reviewed") is not True for entry in review["reviewed_pngs"]
    ):
        raise ValueError("Visual review must identify all six supplementary/comparison PNGs")
    if not review.get("checked_at") or any(
        not review.get("observations", {}).get(product) for product in PRODUCTS
    ):
        raise ValueError("Visual review time and product-specific observations are required")
    if not review.get("tests") or not review.get("notion_pages"):
        raise ValueError("Test evidence and updated Notion page references are required")
    git = review.get("git", {})
    if git.get("head") != revision or git.get("remote_head") != revision:
        raise ValueError("The review must identify the current local and verified remote commit")
    if git.get("remote_verified") is not True:
        raise ValueError("Remote Git verification is not recorded")
    if source_hashes() != summary["source_sha256"]:
        raise ValueError("Analysis sources changed since execution; review numerical impact first")
    for name, checksum in expected.items():
        if digest(Path(name)) != checksum:
            raise ValueError(f"An output changed after generation: {name}")
    protection = json.loads(
        Path(summary["protection"]["inventory_path"]).read_text(encoding="utf-8")
    )
    if protection != protected_inventory():
        raise ValueError("Protected original files differ since execution")
    if verify_archive() != summary["v1_history"]:
        raise ValueError("Archived v1 evidence changed since execution")
    summary.update(
        {
            "status": "delivery_verified",
            "visual_review": review,
            "review_record_sha256": digest(path),
            "review_record_path": str(path),
            "verified_repository_commit": revision,
            "finalized_at": datetime.now().astimezone().isoformat(),
            "finalization_command": [sys.executable, *sys.argv],
        }
    )
    write_json(LOG_PATH, summary)
    return {"status": summary["status"], "log": str(LOG_PATH), "repository_commit": revision}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run", action="store_true", help="Validate and report; write no analysis output"
    )
    mode.add_argument(
        "--execute", action="store_true", help="Write only the supplementary No10_sub outputs"
    )
    mode.add_argument("--record-review", type=Path, help="Finalize verified external review only")
    parser.add_argument("--source-audit", type=Path)
    args = parser.parse_args()
    result = (
        record_review(args.record_review)
        if args.record_review
        else run(execute=args.execute, source_audit=args.source_audit)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
