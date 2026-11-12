#!/usr/bin/env python3
"""One-time, explicitly authorized No10 8–11 -> 8–10 Hz replacement.

Archive old non-image evidence, then run the same production entry points for
all participants and independently audit outputs. No raw input or other No is
modified. This is an execution/recordkeeping wrapper, not an analysis method.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from Phase4_No10_FzLowAlpha import engine

REPO = Path(__file__).resolve().parents[2]
ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
SCRIPT_DIR = Path(__file__).resolve().parent
PHASE_ROOT = engine.DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
MAIN_ROOT = PHASE_ROOT / "No10_FzLowAlpha"
SUB_ROOT = PHASE_ROOT / "No10_sub_FzLowAlphaChange"
LOG_ROOT = MAIN_ROOT / "Sub/logs"
RUN_NAME = "BandRevision_20261112_8to10Hz"
RECORD = LOG_ROOT / f"{RUN_NAME}.json"
MANIFEST = MAIN_ROOT / "Sub/tables/ParticipantManifest.csv"


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inventory(root: Path, *, hash_files: bool = False) -> dict:
    entries = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        stat = path.stat()
        entry = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if hash_files:
            entry["sha256"] = digest(path)
        entries[str(path)] = entry
    return entries


def protected_inventory() -> dict:
    entries = {}
    for folder in PHASE_ROOT.iterdir():
        if folder.is_dir() and folder not in (MAIN_ROOT, SUB_ROOT):
            entries.update(inventory(folder))
    # Existing processed-data siblings are read-only for this revision.
    for folder in engine.DEFAULT_CACHE_ROOT.parent.parent.iterdir():
        if folder.is_dir() and folder != engine.DEFAULT_CACHE_ROOT.parent:
            entries.update(inventory(folder))
    return entries


def save_record(record: dict) -> None:
    RECORD.parent.mkdir(parents=True, exist_ok=True)
    RECORD.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if json.loads(RECORD.read_text(encoding="utf-8")) != record:
        raise RuntimeError("Execution record readback mismatch")


def run_stage(name: str, script: str, arguments: list[str], console: Path, record: dict) -> None:
    command = [str(REPO / ".venv/bin/python"), str(SCRIPT_DIR / script), *arguments]
    stage = {
        "stage": name,
        "command": command,
        "started_at": datetime.now().astimezone().isoformat(),
    }
    record["stages"].append(stage)
    save_record(record)
    with console.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(
            command,
            cwd=REPO,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env={**os.environ, "MPLBACKEND": "Agg"},
        )
        assert process.stdout is not None
        for line in process.stdout:
            stream.write(line)
            stream.flush()
            print(line, end="", flush=True)
        returncode = process.wait()
    stage.update(
        returncode=returncode,
        completed_at=datetime.now().astimezone().isoformat(),
        console=str(console),
        console_sha256=digest(console),
    )
    save_record(record)
    if returncode:
        raise RuntimeError(f"{name} exited with {returncode}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.add_argument("--manifest-source-audit", type=Path, required=True)
    args = parser.parse_args()
    actual_root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=REPO, text=True
    )
    actual_origin = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=REPO, text=True
    )
    if Path(actual_root.strip()) != REPO or actual_origin.strip() != ORIGIN:
        raise RuntimeError("Repository boundary mismatch")
    if RECORD.exists():
        raise RuntimeError("Revision record already exists; inspect it before an explicit rerun")
    source_audit = json.loads(args.manifest_source_audit.read_text(encoding="utf-8"))
    if source_audit.get("mismatches") != 0 or source_audit.get("matched_pairs") != 40:
        raise RuntimeError("Source manifest audit not passed")
    if source_audit.get("manifest_sha256") != digest(MANIFEST):
        raise RuntimeError("Manifest changed since source-sheet audit")
    specs = engine.load_manifest(MANIFEST)
    engine.validate_participant_specs(specs, production_batch=True)
    preflight = engine.preflight_inputs(specs, engine.DEFAULT_INPUT_ROOT)
    print("All-input preflight passed", flush=True)
    before = protected_inventory()
    record = {
        "status": "running",
        "revision": RUN_NAME,
        "started_at": datetime.now().astimezone().isoformat(),
        "git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
        ).strip(),
        "source_band_hz": [8, 9, 10, 11],
        "current_band_hz": [8, 9, 10],
        "manifest_sha256": digest(MANIFEST),
        "manifest_source_audit": source_audit,
        "input_preflight": preflight,
        "protected_inventory_before": before,
        "protected_check_scope": "Exact path/size/mtime_ns inventory, not full content hashes",
        "old_cache_inventory": inventory(engine.DEFAULT_CACHE_ROOT, hash_files=True),
        "old_current_files": {},
        "archived_nonimage_files": [],
        "stages": [],
        "cloud_sync": "Local OneDrive path only; server-side sync not independently verified",
    }
    for root in (MAIN_ROOT, SUB_ROOT):
        record["old_current_files"].update(inventory(root, hash_files=True))
        history = root / "Sub/history/Before8to10Hz_20261112"
        if history.exists():
            raise RuntimeError(f"History destination already exists: {history}")
        for source in sorted(root.rglob("*")):
            if not source.is_file() or source.suffix not in (".csv", ".json", ".log"):
                continue
            relative = source.relative_to(root)
            if "history" in relative.parts:
                continue
            target = history / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            if digest(source) != digest(target):
                raise RuntimeError(f"History copy verification failed: {source}")
            if relative.parts[:2] == ("Sub", "logs"):
                source.unlink()  # Recovered from the verified, explicitly old-band archive.
            record["archived_nonimage_files"].append(str(target))
    save_record(record)
    shared = ["--manifest", str(MANIFEST), "--production-batch"]
    try:
        run_stage(
            "No10: recompute 80 PSD caches and replace full-cohort figures",
            "Phase4_No10_FzLowAlpha.py",
            [*shared, "--all", "--force-recompute"],
            LOG_ROOT / "ProductionConsole_20261112_8to10Hz.log",
            record,
        )
        run_stage(
            "No10_sub: replace full cohort, then add specified-pair sensitivity",
            "Phase4_No10_sub_FzLowAlphaChange.py",
            [*shared, "--all"],
            SUB_ROOT / "Sub/logs/ProductionConsole_20261112_8to10Hz.log",
            record,
        )
        run_stage(
            "Independent numerical/output audit",
            "validate_phase4_no10_outputs.py",
            [
                "--manifest",
                str(MANIFEST),
                "--report",
                str(LOG_ROOT / "ValidationSummary_20261112_8to10Hz.json"),
            ],
            LOG_ROOT / "ValidationConsole_20261112_8to10Hz.log",
            record,
        )
        after = protected_inventory()
        if before != after:
            raise RuntimeError("Protected sibling output/cache inventory changed")
        record["protected_inventory_unchanged"] = True
        record["new_cache_inventory"] = inventory(engine.DEFAULT_CACHE_ROOT, hash_files=True)
        if len(record["new_cache_inventory"]) != 80:
            raise RuntimeError("Expected exactly 80 new No10 cache files")
        for path, current in record["new_cache_inventory"].items():
            if current["sha256"] == record["old_cache_inventory"][path]["sha256"]:
                raise RuntimeError(f"Cache was not replaced: {path}")
        started_ns = int(datetime.fromisoformat(record["started_at"]).timestamp() * 1e9)
        current_pngs = [path for root in (MAIN_ROOT, SUB_ROOT) for path in root.rglob("*.png")]
        if len(current_pngs) != 260 or any(
            path.stat().st_mtime_ns < started_ns for path in current_pngs
        ):
            raise RuntimeError("Expected 260 newly rendered current PNGs")
        record["current_pngs_regenerated"] = len(current_pngs)
        record["status"] = "numerical_execution_and_output_audit_passed"
        record["visual_and_document_checks"] = "Pending separate final verification"
    except Exception as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        record["completed_at"] = datetime.now().astimezone().isoformat()
        save_record(record)
    print(record["status"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
