#!/usr/bin/env python3
"""Run and verify only No11/Pz low-alpha and its Set-1 change analysis.

Cache-only orchestration: no source EEG, existing cache, or earlier result is
written. The same two analysis entry points process the pilot and every pair.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from Phase4_No10_FzLowAlpha import engine as source

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = Path(__file__).resolve().parent
ORIGIN = "https://github.com/aoiseki0415/Analysis_project_roht_phase2.git"
PHASE = source.DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
STEMS = ("No11_PzLowAlpha", "No11_sub_PzLowAlphaChange")
ROOTS = tuple(PHASE / stem for stem in STEMS)
LOGS = ROOTS[0] / "Sub/logs"
RECORD = LOGS / "No11_ExecutionAndVerification.json"
SOURCE_MANIFEST = PHASE / "No10_FzLowAlpha/Sub/tables/ParticipantManifest.csv"
ENTRIES = ("Phase4_No11_PzLowAlpha.py", "Phase4_No11_sub_PzLowAlphaChange.py")


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
            result.update(inventory(folder))
    result.update(inventory(source.DEFAULT_CACHE_ROOT.parent.parent))
    return result


def save(path: Path, record: dict) -> None:
    if not any(path.resolve().is_relative_to(root.resolve()) for root in ROOTS):
        raise ValueError("Output outside No11 result trees")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path.write_text(payload, encoding="utf-8")
    if json.loads(path.read_text(encoding="utf-8")) != record:
        raise RuntimeError("Record readback failed")


def prepare(audit_path: Path) -> dict:
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
    for root in ROOTS:
        folders = ["Sub/logs", "Sub/tables/GrandAverage", "Sub/tables/SetQuantification"]
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
        code = process.wait()
    current.update(
        returncode=code,
        completed_at=datetime.now().astimezone().isoformat(),
        console=str(console),
        console_sha256=digest(console),
    )
    save(RECORD, record)
    if code:
        raise RuntimeError(f"{name} failed ({code}); see {console}")


def execute(audit_path: Path) -> None:
    head = git_check()
    if RECORD.exists():
        previous = json.loads(RECORD.read_text(encoding="utf-8"))
        if previous.get("status") == "completed":
            raise RuntimeError("Completed run already exists; no implicit replacement")
        attempt = datetime.now().strftime("%Y%m%dT%H%M%S")
        save(LOGS / "attempts" / attempt / RECORD.name, previous)
        for old_stage in previous.get("stages", []):
            if "console" in old_stage:
                console = Path(old_stage["console"])
                archived = LOGS / "attempts" / attempt / console.name
                if console.is_file():
                    archived.write_bytes(console.read_bytes())
    audit = prepare(audit_path)
    record = {
        "status": "running",
        "started_at": datetime.now().astimezone().isoformat(),
        "implementation_base_commit": head,
        "focus_channel": "Pz",
        "frequencies_hz": [8, 9, 10],
        "source_manifest_audit": audit,
        "stages": [],
        "source_cache_before": inventory(source.DEFAULT_CACHE_ROOT, hashes=True),
        "protected_before": protected_inventory(),
        "code_hashes": {str(p.relative_to(REPO)): digest(p) for p in SCRIPTS.glob("*no11*.py")},
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
        for index, script in enumerate(ENTRIES):
            stage(f"Production_{index + 1}", script, [*common, "--all"], record)
        validation = LOGS / "No11_IndependentValidation.json"
        stage(
            "IndependentValidation",
            "validate_phase4_no11_outputs.py",
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
    import validate_phase4_no11_outputs as validator

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
    save(LOGS / "No11_DeliveryVerification.json", report)
    record.update(
        status="completed",
        final_git_commit=head,
        delivery_verification=str(LOGS / "No11_DeliveryVerification.json"),
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
    args = parser.parse_args()
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
            execute(args.manifest_source_audit)
    return 0


if __name__ == "__main__":
    sys.exit(main())
