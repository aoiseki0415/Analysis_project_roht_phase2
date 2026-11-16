#!/usr/bin/env python3
"""Retire only No10_sub's reviewed-and-rejected specified-pair extra results.

The existing primary cohort already contains every restored eligible pair, so
neither PSD nor figures are recalculated. Delete exactly six obsolete PNGs only
after archiving/verifying nine CSVs and one run summary. All other Phase 4 result
files and the No10 source cache are protected by before/after SHA-256 manifests.
No11's unchanged specified-pair results and topography sensitivity are protected.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from Phase4_No10_FzLowAlpha import engine
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
PHASE_ROOT = engine.DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
STEM = "No10_sub_FzLowAlphaChange"
ROOT = PHASE_ROOT / STEM
CACHE = engine.DEFAULT_CACHE_ROOT
SUFFIX = "SpecifiedPairsExcluded"
PRODUCTS = ("CCube", "VRohtoPremium")
VERSION = "20261116_no10_sub_pair_exclusion_retired_v1"
ARCHIVE_NAME = "RetiredSpecifiedPairsExcluded_20261116"
RECORD_NAME = "No10_sub_SpecifiedPairsRetirement_20261116.json"
ATTENTION = REPO / "docs/解析上の注意事項.md"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def legacy_paths(root: Path) -> list[Path]:
    """Explicit allowlist, not glob-based deletion; no Topography paths."""
    paths = []
    for product in PRODUCTS:
        paths.extend(
            [
                root / product / "GrandAverage" / f"{STEM}_GrandAverage_{product}_{SUFFIX}.png",
                root
                / product
                / "SetQuantification"
                / SUFFIX
                / f"{STEM}_SetQuantification_{product}_{SUFFIX}.png",
                root
                / product
                / "SetQuantification"
                / SUFFIX
                / f"{STEM}_AllSetsQuantification_{product}_{SUFFIX}.png",
                root
                / product
                / "SetQuantification"
                / SUFFIX
                / f"{STEM}_SetQuantification_Statistics_{product}_{SUFFIX}.csv",
                root
                / "Sub/tables/GrandAverage"
                / f"{STEM}_GrandAverage_Values_{product}_{SUFFIX}.csv",
                root
                / "Sub/tables/SetQuantification"
                / f"{STEM}_Quantification_Values_{product}_{SUFFIX}.csv",
                root
                / "Sub/tables/SetQuantification"
                / f"{STEM}_AllSetsQuantification_Statistics_{product}_{SUFFIX}.csv",
            ]
        )
    paths.extend(
        [
            root / "Sub/tables/SetQuantification" / f"{STEM}_CohortSelection_{SUFFIX}.csv",
            root / "Sub/logs" / f"{STEM}_{SUFFIX}_RunSummary.json",
        ]
    )
    return paths


def current_legacy_files(root: Path) -> set[Path]:
    return {
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.name != ".DS_Store"
        and "history" not in path.relative_to(root).parts
        and (SUFFIX in path.name or SUFFIX in path.relative_to(root).parts)
    }


def assert_safe_file(path: Path, root: Path) -> None:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Expected existing regular file: {path}")
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escaped permitted subtree: {path}")
    for parent in path.parents:
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError(f"Symlinked path is not allowed: {path}")


def reviewed_policy(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    heading = "## Phase 4 sub被験者除外の現行指定（2026-11-16）"
    if text.count(heading) != 1:
        raise ValueError("A unique current canonical exclusion section is required")
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| No10_sub（")]
    if len(rows) != 1:
        raise ValueError("A unique current No10_sub row is required")
    cells = rows[0].split("|")
    if not all("なし" in cell for cell in cells[2:4]):
        raise ValueError("Current canonical No10_sub exclusions must be none in both products")
    if not any(word in rows[0] for word in ("検討", "再検討", "見直", "再評価")):
        raise ValueError("Policy must explicitly record a reviewed no-exclusion decision")
    return {"path": str(path), "sha256": digest(path), "canonical_row": rows[0]}


def verify_primary(root: Path, legacy_selection: Path) -> dict:
    """Check the retained primary cohort and all six current group PNGs."""
    with legacy_selection.open(encoding="utf-8-sig", newline="") as stream:
        selection = list(csv.DictReader(stream))
    result = {}
    for product, expected_count in (("CCube", 20), ("VRohtoPremium", 19)):
        values = (
            root / "Sub/tables/SetQuantification" / f"{STEM}_Quantification_Values_{product}.csv"
        )
        assert_safe_file(values, root)
        with values.open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.DictReader(stream))
        pair_ids = {row["PairID"] for row in rows}
        former = {row["PairID"] for row in selection if row["Product"] == product}
        restored = {
            row["PairID"]
            for row in selection
            if row["Product"] == product and row["Included"].lower() == "false"
        }
        if pair_ids != former or len(pair_ids) != expected_count:
            raise ValueError(f"Primary cohort differs from full eligible cohort: {product}")
        if not restored.issubset(pair_ids):
            raise ValueError(f"Primary results do not include restored pairs: {product}")
        if any(
            {row["Set"] for row in rows if row["PairID"] == pair}
            != {"1", "2", "3", "4", "5", "6", "All Sets"}
            for pair in pair_ids
        ):
            raise ValueError(f"Primary quantification Set coverage is incomplete: {product}")
        paths = [
            root / product / folder / f"{STEM}_{kind}_{product}.png"
            for folder, kind in (
                ("GrandAverage", "GrandAverage"),
                ("SetQuantification", "SetQuantification"),
                ("SetQuantification", "AllSetsQuantification"),
            )
        ]
        for image in paths:
            assert_safe_file(image, root)
            with Image.open(image) as handle:
                handle.verify()
        result[product] = {
            "eligible_pairs": len(pair_ids),
            "included_formerly_excluded_pairs": sorted(restored),
            "primary_values": str(values),
            "primary_values_sha256": digest(values),
            "primary_group_pngs": {str(path): digest(path) for path in paths},
            "validation_scope": "Existing eligible cohort and PNG readback; no numerical rerun",
        }
    return result


def inventory(roots: list[Path], ignored: set[Path]) -> dict:
    files = {}
    for root in roots:
        if not root.is_dir():
            raise ValueError(f"Protected root missing: {root}")
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.name == ".DS_Store" or path in ignored:
                continue
            assert_safe_file(path, root)
            files[str(path)] = {"bytes": path.stat().st_size, "sha256": digest(path)}
    return files


def build_plan(root: Path, cache: Path, attention: Path) -> dict:
    expected = set(legacy_paths(root))
    if current_legacy_files(root) != expected:
        raise ValueError("Current legacy file set differs from the exact 16-file allowlist")
    archive = root / "Sub/history" / ARCHIVE_NAME
    record = root / "Sub/logs" / RECORD_NAME
    if archive.exists() or record.exists():
        raise ValueError("Retirement evidence already exists; verify it, do not overwrite")
    for path in expected:
        assert_safe_file(path, root)
    selection = root / "Sub/tables/SetQuantification" / f"{STEM}_CohortSelection_{SUFFIX}.csv"
    primary = verify_primary(root, selection)
    policy = reviewed_policy(attention)
    entries = []
    for path in sorted(expected):
        png = path.suffix == ".png"
        entries.append(
            {
                "source": str(path),
                "sha256": digest(path),
                "bytes": path.stat().st_size,
                "action": "delete_obsolete_png" if png else "archive_non_png",
                "destination": None if png else str(archive / path.relative_to(root)),
            }
        )
    return {
        "version": VERSION,
        "status": "planned",
        "scope": "No10_sub representative-Fz groups only",
        "reason": "Reviewed absolute PSD did not justify participant exclusion; all eligible "
        "pairs retained. This is an affirmative reviewed decision, not an unassessed exclusion.",
        "root": str(root),
        "cache_root": str(cache),
        "archive_root": str(archive),
        "record": str(record),
        "policy": policy,
        "primary_validation": primary,
        "planned_files": entries,
        "delete_png_count": 6,
        "archive_non_png_count": 10,
        "unchanged": "Primary results, individual figures, all topographies, No10 absolute, "
        "No11 and No11_sub including their sensitivity outputs, other Phase4 outputs, PSD caches",
        "record_layers": "The existing primary RunSummary records its original generation "
        "and may reference the then-active sensitivity outputs. It is retained unchanged as "
        "historical execution evidence; this retirement record defines the current inventory.",
        "finder_metadata": ".DS_Store is ignored and never changed or deleted; a directory "
        "containing only this Finder metadata is kept rather than recursively removed.",
        "cloud_sync": "Local OneDrive folder only; server sync not independently verified",
    }


def save_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if json.loads(path.read_text(encoding="utf-8")) != record:
        raise RuntimeError("Retirement log readback mismatch")


def execute_plan(plan: dict) -> dict:
    """Recheck all exact hashes, stage non-PNG history, then remove old exposure."""
    root, cache = Path(plan["root"]), Path(plan["cache_root"])
    record_path = Path(plan["record"])
    archive = Path(plan["archive_root"])
    expected = set(legacy_paths(root))
    entries = plan["planned_files"]
    if (
        plan.get("status") != "planned"
        or len(entries) != 16
        or {Path(entry["source"]) for entry in entries} != expected
        or current_legacy_files(root) != expected
        or archive.exists()
        or record_path.exists()
    ):
        raise ValueError("Retirement plan is stale, tampered, or already applied")
    if (
        record_path != root / "Sub/logs" / RECORD_NAME
        or archive != root / "Sub/history" / ARCHIVE_NAME
    ):
        raise ValueError("Retirement record/history path mismatch")
    for entry in entries:
        path = Path(entry["source"])
        assert_safe_file(path, root)
        expected_action = "delete_obsolete_png" if path.suffix == ".png" else "archive_non_png"
        expected_dest = None if path.suffix == ".png" else str(archive / path.relative_to(root))
        if (
            digest(path) != entry["sha256"]
            or path.stat().st_size != entry["bytes"]
            or entry["action"] != expected_action
            or entry["destination"] != expected_dest
        ):
            raise ValueError(f"Retirement file changed or plan tampered: {path}")
    if reviewed_policy(Path(plan["policy"]["path"])) != plan["policy"]:
        raise ValueError("Canonical policy changed after planning")
    protected_before = inventory([root.parent, cache], expected)
    record = {
        **plan,
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "protected_before": protected_before,
        "operations": [],
    }
    # Log creation must succeed before any existing output is changed.
    save_record(record_path, record)
    archive_files = set()
    try:
        for entry in entries:
            if entry["action"] != "archive_non_png":
                continue
            source, target = Path(entry["source"]), Path(entry["destination"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if digest(target) != entry["sha256"]:
                raise RuntimeError(f"Archive readback failed: {source}")
            archive_files.add(target)
        if len(archive_files) != 10:
            raise RuntimeError("Exactly 10 verified non-PNG history files are required")
        record["archive_verified"] = True
        save_record(record_path, record)
        # No removals occur before all non-PNG audit evidence is recoverable.
        for entry in entries:
            source = Path(entry["source"])
            if digest(source) != entry["sha256"]:
                raise RuntimeError(f"Source changed before removal: {source}")
            source.unlink()
            record["operations"].append(entry)
            save_record(record_path, record)
        for product in PRODUCTS:
            folder = root / product / "SetQuantification" / SUFFIX
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()
        if current_legacy_files(root):
            raise RuntimeError("Retired sensitivity files remain exposed")
        protected_after = inventory([root.parent, cache], archive_files | {record_path})
        if protected_before != protected_after:
            raise RuntimeError("Protected results or cache changed during retirement")
        record.update(
            status="completed",
            protected_unchanged=True,
            protected_file_count=len(protected_before),
            deleted_png_count=sum(entry["action"] == "delete_obsolete_png" for entry in entries),
            archived_non_png_count=len(archive_files),
            psd_recomputed=False,
            primary_figures_rerendered=False,
            no11_results_recomputed=False,
        )
    except Exception as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["finished_at"] = datetime.now().astimezone().isoformat()
        save_record(record_path, record)
    return record


def verify_retirement(root: Path, cache: Path, attention: Path) -> dict:
    """Read-only verification of an already completed retirement and its evidence."""
    record_path = root / "Sub/logs" / RECORD_NAME
    archive = root / "Sub/history" / ARCHIVE_NAME
    assert_safe_file(record_path, root)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if (
        record.get("status") != "completed"
        or record.get("version") != VERSION
        or record.get("root") != str(root)
        or record.get("cache_root") != str(cache)
        or record.get("archive_root") != str(archive)
        or record.get("record") != str(record_path)
        or record.get("deleted_png_count") != 6
        or record.get("archived_non_png_count") != 10
        or not record.get("protected_unchanged")
    ):
        raise ValueError("Retirement record is incomplete or inconsistent")
    entries = record["planned_files"]
    if len(entries) != 16 or {Path(item["source"]) for item in entries} != set(legacy_paths(root)):
        raise ValueError("Recorded retirement scope differs from the exact allowlist")
    if current_legacy_files(root):
        raise ValueError("Retired sensitivity files are exposed in current results")
    archive_files = set()
    for entry in entries:
        source = Path(entry["source"])
        if source.exists():
            raise ValueError(f"Retired source still exists: {source}")
        if source.suffix == ".png":
            if entry["destination"] is not None or entry["action"] != "delete_obsolete_png":
                raise ValueError("Obsolete PNG must not have an archived destination")
            continue
        target = archive / source.relative_to(root)
        if entry["destination"] != str(target) or entry["action"] != "archive_non_png":
            raise ValueError("Recorded archive destination is inconsistent")
        assert_safe_file(target, archive)
        if digest(target) != entry["sha256"] or target.stat().st_size != entry["bytes"]:
            raise ValueError(f"Archived evidence differs: {target}")
        archive_files.add(target)
    actual_archive = {
        path for path in archive.rglob("*") if path.is_file() and path.name != ".DS_Store"
    }
    if len(archive_files) != 10 or actual_archive != archive_files:
        raise ValueError("Archive must contain exactly the ten non-PNG evidence files")
    protected_now = inventory([root.parent, cache], archive_files | {record_path})
    if protected_now != record["protected_before"]:
        raise ValueError("Protected result/cache snapshot has changed since retirement")
    policy = reviewed_policy(attention)
    selection = archive / "Sub/tables/SetQuantification" / f"{STEM}_CohortSelection_{SUFFIX}.csv"
    primary = verify_primary(root, selection)
    if primary != record["primary_validation"]:
        raise ValueError("Primary cohort or PNGs differ from retirement validation")
    return {
        "status": "verified_completed",
        "record": str(record_path),
        "read_only": True,
        "archived_non_png_count": len(archive_files),
        "current_retired_file_count": 0,
        "protected_file_count": len(protected_now),
        "protected_no11_file_count": sum(
            Path(path).relative_to(root.parent).parts[0].startswith(("No11_", "No11_sub_"))
            for path in protected_now
            if Path(path).is_relative_to(root.parent)
        ),
        "primary_validation": primary,
        "current_policy": policy,
        "validation_scope": "Exact retirement-time protected snapshot, archived evidence, "
        "current policy and existing primary results; no analysis or output writes",
        "cloud_sync": record["cloud_sync"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--plan", action="store_true", help="Read-only exact-path/hash preflight")
    modes.add_argument("--execute", action="store_true", help="Apply the exact scoped retirement")
    modes.add_argument("--verify", action="store_true", help="Read-only completed-state audit")
    args = parser.parse_args()
    actual_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=REPO, text=True
    ).strip()
    actual_origin = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=REPO, text=True
    ).strip()
    if Path(actual_root) != REPO or actual_origin != ORIGIN:
        raise RuntimeError("Repository boundary mismatch")
    if args.verify:
        print(json.dumps(verify_retirement(ROOT, CACHE, ATTENTION), ensure_ascii=False, indent=2))
        return 0
    plan = build_plan(ROOT, CACHE, ATTENTION)
    if args.plan:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
    else:
        plan["command"] = [sys.executable, str(Path(__file__)), *sys.argv[1:]]
        plan["git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip()
        plan["script_sha256"] = digest(Path(__file__))
        result = execute_plan(plan)
        print(
            json.dumps(
                {
                    key: result[key]
                    for key in (
                        "status",
                        "record",
                        "deleted_png_count",
                        "archived_non_png_count",
                        "protected_file_count",
                    )
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
