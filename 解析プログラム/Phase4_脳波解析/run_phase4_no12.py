#!/usr/bin/env python3
"""Run and verify only No12/frontal ROI low-alpha and its Set-1 change analysis.

Cache-only orchestration: no source EEG, existing cache, or earlier result is
written. The same two analysis entry points process the pilot and every pair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from Phase4_No10_FzLowAlpha import engine as source
from phase4_no12_cached_analysis import ROI_CHANNELS

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
PHASE = source.DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
STEMS = ("No12_FrontalROILowAlpha", "No12_sub_FrontalROILowAlphaChange")
ROOTS = tuple(PHASE / stem for stem in STEMS)
LOGS = ROOTS[0] / "Sub/logs"
RECORD = LOGS / "No12_ExecutionAndVerification.json"
SOURCE_MANIFEST = PHASE / "No10_FzLowAlpha/Sub/tables/ParticipantManifest.csv"
ENTRIES = ("Phase4_No12_FrontalROILowAlpha.py", "Phase4_No12_sub_FrontalROILowAlphaChange.py")
OLD_ROI_CHANNELS = ["F3", "Fz", "F4", "FC1", "FC2"]
REPLACEMENT_HISTORY = Path("Sub/history/BeforeROI10_20261116")
PILOT_TABLE_RELATIVE_PATHS = (
    (0, "Log3SDThresholdExclusion/No12_FrontalROILowAlpha_Log3SDThresholdExclusion_ID101-201.csv"),
    (0, "ROIQuality/No12_FrontalROILowAlpha_ROIWindowQuality_ID101-201.csv"),
    (0, "ROIQuality/No12_FrontalROILowAlpha_ROISetQuality_ID101-201.csv"),
    (0, "ROIQuality/No12_FrontalROILowAlpha_ROIChannelCoverage_ID101-201.csv"),
    (1, "ROIQuality/No12_sub_FrontalROILowAlphaChange_ROIWindowQuality_ID101-201.csv"),
    (1, "ROIQuality/No12_sub_FrontalROILowAlphaChange_ROISetQuality_ID101-201.csv"),
    (1, "ROIQuality/No12_sub_FrontalROILowAlphaChange_ROIChannelCoverage_ID101-201.csv"),
)


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def git_check() -> str:
    root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], cwd=REPO, text=True
    ).strip()
    remote = subprocess.check_output(
        ["git", "remote", "get-url", "origin"], cwd=REPO, text=True
    ).strip()
    if Path(root).resolve() != REPO or remote != ORIGIN:
        raise RuntimeError("Repository boundary mismatch")
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()


def inventory(root: Path, *, hashes: bool = False) -> dict:
    result = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == ".DS_Store":
            continue
        stat = path.stat()
        entry = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
        if hashes:
            entry["sha256"] = digest(path)
        result[str(path)] = entry
    return result


def protected_inventory() -> dict:
    result = {}
    for folder in PHASE.iterdir():
        if folder.is_dir() and folder not in ROOTS:
            result.update(inventory(folder, hashes=True))
    result.update(inventory(source.DEFAULT_CACHE_ROOT.parent.parent, hashes=True))
    return result


def save(path: Path, record: dict) -> None:
    if not any(path.resolve().is_relative_to(root.resolve()) for root in ROOTS):
        raise ValueError("Output outside No12 result trees")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(payload, encoding="utf-8")
    if json.loads(path.read_text(encoding="utf-8")) != record:
        raise RuntimeError("Record readback failed")


def _checked_pilot_path(path: Path, root: Path) -> None:
    """Reject symlinks/non-files before touching an explicit pilot-table path."""
    if not path.is_relative_to(root) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Unsafe pilot archive path: {path}")
    for component in (path, *path.parents):
        if component.is_symlink():
            raise ValueError(f"Symlink in pilot archive path: {component}")
        if component != path and component.exists() and not component.is_dir():
            raise ValueError(f"Non-directory ancestor in pilot archive path: {component}")
        if component == root:
            break
    if path.exists() and not path.is_file():
        raise ValueError(f"Pilot archive path is not a regular file: {path}")


def archive_pilot_tables() -> dict:
    """Move only seven named pilot CSVs to history; never alter production files.

    All seven source/target pairs are checked before any mutation. Copying to an
    exclusively created target, verifying its SHA, then unlinking the source
    avoids replacing a concurrently created archive. Repeated calls accept
    identical archived files but reject any unequal target.
    """
    if ROOTS != tuple(PHASE / stem for stem in STEMS):
        raise ValueError("Unexpected No12 roots for pilot archive")
    if len(PILOT_TABLE_RELATIVE_PATHS) != 7 or len(set(PILOT_TABLE_RELATIVE_PATHS)) != 7:
        raise ValueError("Pilot archive requires exactly seven distinct allowed tables")
    plan = []
    for index, relative_name in PILOT_TABLE_RELATIVE_PATHS:
        relative = Path(relative_name)
        if (
            index not in (0, 1)
            or relative.is_absolute()
            or ".." in relative.parts
            or len(relative.parts) != 2
            or relative.parts[0] not in ("ROIQuality", "Log3SDThresholdExclusion")
            or not relative.name.startswith(f"{STEMS[index]}_")
            or not relative.name.endswith("_ID101-201.csv")
        ):
            raise ValueError(f"Unsafe pilot table allowlist entry: {relative_name}")
        root = ROOTS[index]
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"Invalid No12 pilot root: {root}")
        source_path = root / "Sub/tables" / relative
        destination = root / "Sub/history/Pilot" / relative
        _checked_pilot_path(source_path, root)
        _checked_pilot_path(destination, root)
        source_hash = digest(source_path) if source_path.exists() else None
        destination_hash = digest(destination) if destination.exists() else None
        if source_hash is None and destination_hash is None:
            raise FileNotFoundError(f"Pilot table and archive both absent: {source_path}")
        if source_hash is not None and destination_hash not in (None, source_hash):
            raise RuntimeError(f"Existing pilot archive differs: {destination}")
        plan.append((root, source_path, destination, source_hash or destination_hash))

    records = []
    for root, source_path, destination, expected_hash in plan:
        _checked_pilot_path(source_path, root)
        _checked_pilot_path(destination, root)
        source_present = source_path.exists()
        if source_present and digest(source_path) != expected_hash:
            raise RuntimeError(f"Pilot source changed after preflight: {source_path}")
        if destination.exists():
            if digest(destination) != expected_hash:
                raise RuntimeError(f"Existing pilot archive differs: {destination}")
            status = "identical_archive_source_removed" if source_present else "already_archived"
        else:
            if not source_present:
                raise RuntimeError(f"Pilot source disappeared after preflight: {source_path}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            _checked_pilot_path(destination, root)
            with source_path.open("rb") as original, destination.open("xb") as archived:
                shutil.copyfileobj(original, archived)
            status = "archived"
        if digest(destination) != expected_hash:
            raise RuntimeError(f"Pilot archive hash verification failed: {destination}")
        if source_present:
            if digest(source_path) != expected_hash:
                raise RuntimeError(f"Pilot source changed during archive: {source_path}")
            source_path.unlink()
        records.append(
            {
                "source": str(source_path),
                "destination": str(destination),
                "sha256": expected_hash,
                "status": status,
            }
        )
    return {
        "policy": "exact_seven_pilot_csv_to_history_sha256_verified",
        "count": 7,
        "records": records,
    }


def read_audit(audit_path: Path) -> dict:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if (audit.get("matched_pairs"), audit.get("matched_sessions"), audit.get("mismatches")) != (
        40,
        80,
        0,
    ):
        raise RuntimeError("A current complete source-mapping audit is required")
    if digest(SOURCE_MANIFEST) != audit.get("manifest_sha256"):
        raise RuntimeError("Source manifest changed after mapping audit")
    source.validate_participant_specs(source.load_manifest(SOURCE_MANIFEST), production_batch=True)
    return audit


def prepare(audit_path: Path) -> dict:
    audit = read_audit(audit_path)
    for root in ROOTS:
        folders = [
            "Sub/logs",
            "Sub/tables/GrandAverage",
            "Sub/tables/SetQuantification",
            "Sub/tables/ROIQuality",
        ]
        folders.append(
            "Sub/tables/Log3SDThresholdExclusion" if root == ROOTS[0] else "Sub/tables/Set1Baseline"
        )
        for product in ("CCube", "VRohtoPremium"):
            folders += [
                f"{product}/{name}" for name in ("Individual", "GrandAverage", "SetQuantification")
            ]
            if root == ROOTS[0]:
                folders += [
                    f"{product}/Individual/Unsmoothed/{stage}ThresholdExclusion"
                    for stage in ("Before", "After")
                ]
        for folder in folders:
            (root / folder).mkdir(parents=True, exist_ok=True)
        target = root / "Sub/tables/ParticipantManifest.csv"
        target.write_bytes(SOURCE_MANIFEST.read_bytes())
        if digest(target) != audit["manifest_sha256"]:
            raise RuntimeError("Manifest copy mismatch")
        save(root / "Sub/logs/ManifestSourceAudit.json", audit)
    return audit


def archive_five_channel_outputs(audit_path: Path) -> dict:
    """Explicit, recoverable replacement of completed five-channel audit records.

    All old non-PNG tables/logs, including the old pilot tables, are moved into
    one clearly named generation. PNGs are not archived or deleted: the same
    validated production filenames are subsequently overwritten by ten-channel
    rendering. The fresh live-source audit is retained as the new run input.
    """
    audit_path = audit_path.resolve()
    if ROOTS != tuple(PHASE / stem for stem in STEMS):
        raise ValueError("Unexpected No12 roots for ROI replacement")
    old_record = ROOTS[0] / REPLACEMENT_HISTORY / RECORD.relative_to(ROOTS[0])
    previous_path = RECORD if RECORD.exists() else old_record
    previous = json.loads(previous_path.read_text(encoding="utf-8"))
    if previous.get("status") != "completed" or previous.get("roi_channels") != OLD_ROI_CHANNELS:
        raise RuntimeError("Replacement requires the completed five-channel generation")
    plans, old_pngs = [], {}
    for root in ROOTS:
        if not root.is_dir() or root.is_symlink():
            raise ValueError(f"Invalid replacement root: {root}")
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if relative.is_relative_to(REPLACEMENT_HISTORY):
                continue
            if relative.is_relative_to("Sub/history") and not relative.is_relative_to(
                "Sub/history/Pilot"
            ):
                continue
            if path.name == ".DS_Store" or path == audit_path:
                continue
            if path.is_symlink():
                raise ValueError(f"Symlink in replacement source: {path}")
            if not path.is_file():
                continue
            _checked_pilot_path(path, root)
            if path.suffix == ".png":
                old_pngs[str(path)] = digest(path)
                continue
            allowed = (
                relative.is_relative_to("Sub/logs")
                or relative.is_relative_to("Sub/tables")
                or relative.is_relative_to("Sub/history/Pilot")
            )
            allowed |= relative.is_relative_to(
                "CCube/SetQuantification"
            ) or relative.is_relative_to("VRohtoPremium/SetQuantification")
            if not allowed or path.suffix not in {".csv", ".json", ".log", ".xml"}:
                raise ValueError(f"Unexpected file in replacement scope: {path}")
            destination = root / REPLACEMENT_HISTORY / relative
            _checked_pilot_path(destination, root)
            expected = digest(path)
            if destination.exists() and digest(destination) != expected:
                raise RuntimeError(f"Different previous-generation archive: {destination}")
            plans.append((root, path, destination, expected))
    records = []
    for root, path, destination, expected in plans:
        _checked_pilot_path(path, root)
        _checked_pilot_path(destination, root)
        if digest(path) != expected:
            raise RuntimeError("Previous-generation source changed during archive")
        if not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            with path.open("rb") as original, destination.open("xb") as archived:
                shutil.copyfileobj(original, archived)
        if digest(destination) != expected or digest(path) != expected:
            raise RuntimeError("Previous-generation archive verification failed")
        path.unlink()
        records.append({"source": str(path), "destination": str(destination), "sha256": expected})
    if any(digest(Path(path)) != value for path, value in old_pngs.items()):
        raise RuntimeError("PNG changed during non-PNG archive")
    report = {
        "status": "passed",
        "policy": "old_five_channel_non_png_to_history_png_overwrite_by_production",
        "archived_count": len(records),
        "records": records,
        "old_png_sha256": old_pngs,
        "old_roi_channels": OLD_ROI_CHANNELS,
        "new_roi_channels": list(ROI_CHANNELS),
        "source_psd_recomputed": False,
        "timestamp": datetime.now().astimezone().isoformat(),
    }
    save(LOGS / "No12_ROI10Replacement.json", report)
    return report


def stage(name: str, script: str, arguments: list[str], record: dict) -> None:
    command = [str(REPO / ".venv/bin/python"), str(SCRIPTS / script), *arguments]
    console = LOGS / f"{name}.log"
    current = {
        "name": name,
        "command": command,
        "started_at": datetime.now().astimezone().isoformat(),
    }
    record["stages"].append(current)
    save(RECORD, record)
    # Cloud-file providers can time out on thousands of per-line flushes. Keep
    # this short stage's console in memory, then publish once in the same
    # authorized log directory. No local fallback result/log file is created.
    process = subprocess.run(
        command,
        cwd=REPO,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env={**os.environ, "MPLBACKEND": "Agg"},
        check=False,
    )
    console.write_text(process.stdout, encoding="utf-8")
    if console.read_text(encoding="utf-8") != process.stdout:
        raise RuntimeError(f"{name}: console readback mismatch")
    code = process.returncode
    if name == "IndependentValidation" and code == 0:
        print(f"{name} passed; full report saved at {console}", flush=True)
    else:
        print(process.stdout, end="", flush=True)
    current.update(
        returncode=code,
        completed_at=datetime.now().astimezone().isoformat(),
        console=str(console),
        console_sha256=digest(console),
    )
    save(RECORD, record)
    if code:
        raise RuntimeError(f"{name} failed ({code}); see {console}")


def execute(audit_path: Path, *, replace_five_channel_version: bool = False) -> None:
    head = git_check()
    replacement = None
    if replace_five_channel_version:
        # Validate the new live-source audit before moving any previous records.
        read_audit(audit_path)
        replacement = archive_five_channel_outputs(audit_path)
    if RECORD.exists():
        previous = json.loads(RECORD.read_text(encoding="utf-8"))
        if previous.get("status") == "completed":
            raise RuntimeError("Completed run already exists; no implicit replacement")
        if "protected_before" in previous and protected_inventory() != previous["protected_before"]:
            raise RuntimeError("Protected inputs/results changed since the previous attempt")
        if (
            "source_cache_before" in previous
            and inventory(source.DEFAULT_CACHE_ROOT, hashes=True) != previous["source_cache_before"]
        ):
            raise RuntimeError("Source cache changed since the previous attempt")
        replacement = previous.get("previous_generation_archive")
        attempt = datetime.now().strftime("%Y%m%dT%H%M%S")
        save(LOGS / "attempts" / attempt / RECORD.name, previous)
        for old_stage in previous.get("stages", []):
            console = Path(old_stage.get("console", LOGS / f"{old_stage['name']}.log"))
            archived = LOGS / "attempts" / attempt / console.name
            if console.is_file():
                archived.write_bytes(console.read_bytes())
        previous_validation = LOGS / "No12_IndependentValidation.json"
        if previous_validation.is_file():
            (LOGS / "attempts" / attempt / previous_validation.name).write_bytes(
                previous_validation.read_bytes()
            )
    audit = prepare(audit_path)
    record = {
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "implementation_base_commit": head,
        "focus_channel": "FrontalROI",
        "roi_channels": list(ROI_CHANNELS),
        "previous_generation_archive": replacement,
        "frequencies_hz": [8, 9, 10],
        "source_manifest_audit": audit,
        "stages": [],
        "source_cache_before": inventory(source.DEFAULT_CACHE_ROOT, hashes=True),
        "protected_before": protected_inventory(),
        "code_hashes": {str(p.relative_to(REPO)): digest(p) for p in SCRIPTS.glob("*.py")},
        "cloud_sync": (
            "Saved/read back in authorized local OneDrive sync tree; "
            "server sync not independently verified"
        ),
    }
    record["code_hashes"].update(
        {str((SCRIPTS / name).relative_to(REPO)): digest(SCRIPTS / name) for name in ENTRIES}
    )
    save(RECORD, record)
    manifest = ROOTS[0] / "Sub/tables/ParticipantManifest.csv"
    common = ["--manifest", str(manifest), "--production-batch"]
    try:
        for index, script in enumerate(ENTRIES):
            stage(f"Preflight_{index + 1}", script, [*common, "--preflight-only"], record)
        for index, script in enumerate(ENTRIES):
            stage(
                f"Pilot_{index + 1}",
                script,
                ["--participant", "101:201:101:VRohtoPremium", "--all"],
                record,
            )
        record["pilot_table_archive"] = archive_pilot_tables()
        save(RECORD, record)
        for index, script in enumerate(ENTRIES):
            stage(f"Production_{index + 1}", script, [*common, "--all"], record)
        validation = LOGS / "No12_IndependentValidation.json"
        stage(
            "IndependentValidation",
            "validate_phase4_no12_outputs.py",
            ["--manifest", str(manifest), "--report", str(validation)],
            record,
        )
        if inventory(source.DEFAULT_CACHE_ROOT, hashes=True) != record["source_cache_before"]:
            raise RuntimeError("No10 input caches changed")
        if protected_inventory() != record["protected_before"]:
            raise RuntimeError("Existing results or processed-data siblings changed")
        record.update(
            status="numerical_execution_and_output_audit_passed",
            numerical_completed_at=datetime.now().astimezone().isoformat(),
            validation=str(validation),
            validation_sha256=digest(validation),
            source_cache_unchanged=True,
            protected_unchanged=True,
            outputs={root.name: inventory(root, hashes=False) for root in ROOTS},
            protected_file_count=len(record["protected_before"]),
        )
    except Exception as error:
        record.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        save(RECORD, record)


def complete(review_path: Path) -> None:
    record = json.loads(RECORD.read_text(encoding="utf-8"))
    if record["status"] != "numerical_execution_and_output_audit_passed":
        raise RuntimeError("Production and numerical verification must pass first")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    if review.get("status") != "passed" or not review.get("tests_passed"):
        raise RuntimeError("Completed tests and visual/document review required")
    test_report = Path(review["test_report"]["path"])
    if digest(test_report) != review["test_report"]["sha256"]:
        raise RuntimeError("Test report changed")
    suites = ET.parse(test_report).getroot()
    if not list(suites.iter("testcase")) or any(
        list(suites.iter(tag)) for tag in ("failure", "error")
    ):
        raise RuntimeError("JUnit report does not confirm a passing test run")
    for relative, executed_hash in record["code_hashes"].items():
        path = REPO / relative
        # This orchestration's completion gate may be strengthened after the run;
        # numerical engines and the independent validator must be byte-identical.
        if path.resolve() != Path(__file__).resolve() and digest(path) != executed_hash:
            raise RuntimeError(f"Numerical/validation code changed after execution: {relative}")
    validation_path = Path(record["validation"])
    if digest(validation_path) != record["validation_sha256"]:
        raise RuntimeError("Independent validation record changed")
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation.get("status") != "passed":
        raise RuntimeError("Independent validation did not pass")
    for item in validation["images"]:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("PNG changed after independent validation")
    # Reconstruct every audited CSV again; this catches post-audit table edits.
    import validate_phase4_no12_outputs as validator

    repeated = {"caches": [], "tables": [], "groups": [], "images": [], "png_counts": {}}
    validator.run(
        SimpleNamespace(
            manifest=ROOTS[0] / "Sub/tables/ParticipantManifest.csv",
            cache_root=source.DEFAULT_CACHE_ROOT,
            output_root=source.DEFAULT_OUTPUT_ROOT,
        ),
        repeated,
    )
    if repeated.get("status") != "passed":
        raise RuntimeError("Delivery-time independent reconstruction failed")
    group_pngs = {p for root in ROOTS for p in root.rglob("*.png") if not p.name.startswith("ID")}
    reviewed = {Path(item["path"]) for item in review["visual_checks"]}
    if len(group_pngs) != 12 or not group_pngs <= reviewed or len(reviewed) < 16:
        raise RuntimeError("Review all 12 group plots and at least four individual plots")
    for item in review["visual_checks"]:
        path = Path(item["path"])
        if not any(path.resolve().is_relative_to(root.resolve()) for root in ROOTS):
            raise RuntimeError("Visual review path outside scope")
        if item["status"] != "passed" or digest(path) != item["sha256"]:
            raise RuntimeError("Visual review evidence changed")
    for key in ("document_checks", "notion_checks"):
        if not review.get(key) or any(item["status"] != "passed" for item in review[key]):
            raise RuntimeError("Incomplete document readback")
    if (
        protected_inventory() != record["protected_before"]
        or inventory(source.DEFAULT_CACHE_ROOT, hashes=True) != record["source_cache_before"]
    ):
        raise RuntimeError("Protected inputs/results changed before delivery")
    head = git_check()
    remote = subprocess.check_output(
        ["git", "ls-remote", "origin", "refs/heads/main"], cwd=REPO, text=True
    ).split()[0]
    if head != remote:
        raise RuntimeError("Final Git SHA is not verified on origin/main")
    for relative, executed_hash in record["code_hashes"].items():
        path = REPO / relative
        expected_hash = (
            digest(path) if path.resolve() == Path(__file__).resolve() else executed_hash
        )
        committed = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=REPO)
        if hashlib.sha256(committed).hexdigest() != expected_hash:
            raise RuntimeError(f"Executed code is not committed: {relative}")
    for item in review["document_checks"]:
        path = Path(item["path"]).resolve()
        if not path.is_relative_to(REPO) or digest(path) != item["sha256"]:
            raise RuntimeError("Reviewed repository file changed")
        committed = subprocess.check_output(
            ["git", "show", f"HEAD:{path.relative_to(REPO).as_posix()}"], cwd=REPO
        )
        if hashlib.sha256(committed).hexdigest() != item["sha256"]:
            raise RuntimeError("Reviewed repository file is not committed")
    report = {
        **review,
        "completed_at": datetime.now().astimezone().isoformat(),
        "git_commit": head,
        "verified_remote_commit": remote,
        "source_cache_unchanged": True,
        "protected_unchanged": True,
        "cloud_sync": record["cloud_sync"],
        "delivery_time_independent_reconstruction": "passed",
        "orchestration_execution_sha256": record["code_hashes"][
            str(Path(__file__).relative_to(REPO))
        ],
        "orchestration_delivery_sha256": digest(Path(__file__)),
        "png_sha256": {str(p): digest(p) for root in ROOTS for p in root.rglob("*.png")},
    }
    save(LOGS / "No12_DeliveryVerification.json", report)
    record.update(
        status="completed",
        final_git_commit=head,
        delivery_verification=str(LOGS / "No12_DeliveryVerification.json"),
    )
    save(RECORD, record)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare-only", action="store_true")
    modes.add_argument("--execute", action="store_true")
    modes.add_argument("--complete-verification", action="store_true")
    parser.add_argument("--manifest-source-audit", type=Path)
    parser.add_argument("--review-manifest", type=Path)
    parser.add_argument("--replace-five-channel-version", action="store_true")
    args = parser.parse_args()
    if args.replace_five_channel_version and not args.execute:
        parser.error("--replace-five-channel-version is only valid with --execute")
    git_check()
    if args.complete_verification:
        if not args.review_manifest:
            parser.error("--review-manifest required")
        complete(args.review_manifest)
    else:
        if not args.manifest_source_audit:
            parser.error("--manifest-source-audit required")
        if args.prepare_only:
            prepare(args.manifest_source_audit)
        else:
            execute(
                args.manifest_source_audit,
                replace_five_channel_version=args.replace_five_channel_version,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
