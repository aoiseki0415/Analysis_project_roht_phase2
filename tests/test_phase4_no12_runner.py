"""Synthetic delivery-gate tests: no production or OneDrive writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import run_phase4_no12 as runner  # noqa: E402
import validate_phase4_no12_outputs as validator  # noqa: E402


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    roots = (tmp_path / "results/main", tmp_path / "results/sub")
    for root in roots:
        root.mkdir(parents=True)
    logs = roots[0] / "Sub/logs"
    logs.mkdir(parents=True)
    record_path, review_path = logs / "execution.json", tmp_path / "review.json"
    numerical_code = repo / "analysis.py"
    numerical_code.write_text("# synthetic numerical engine\n")
    orchestration = repo / "run_phase4_no12.py"
    orchestration.write_text("# strengthened completion gate\n")
    document = repo / "spec.md"
    document.write_text("# synthetic current specification\n")
    junit = tmp_path / "tests.xml"
    junit.write_text('<testsuites><testsuite><testcase name="passed"/></testsuite></testsuites>')
    image_paths = []
    for root in roots:
        for n in range(6):
            path = root / f"Group{n}.png"
            path.write_bytes(b"synthetic image fixture")
            image_paths.append(path)
        for n in range(2):
            path = root / f"IDSynthetic{n}.png"
            path.write_bytes(b"synthetic individual fixture")
            image_paths.append(path)
    validation_path = logs / "validation.json"
    validation_path.write_text(
        json.dumps(
            {
                "status": "passed",
                "images": [
                    {"path": str(path), "sha256": runner.digest(path)} for path in image_paths
                ],
            }
        )
    )
    record = {
        "status": "numerical_execution_and_output_audit_passed",
        "code_hashes": {
            "analysis.py": runner.digest(numerical_code),
            # Only the completion orchestrator may change after numerical execution.
            "run_phase4_no12.py": "older-orchestration-hash",
        },
        "validation": str(validation_path),
        "validation_sha256": runner.digest(validation_path),
        "protected_before": {},
        "source_cache_before": {},
        "cloud_sync": "synthetic local-only test",
    }
    record_path.write_text(json.dumps(record))
    review = {
        "status": "passed",
        "tests_passed": True,
        "test_report": {"path": str(junit), "sha256": runner.digest(junit)},
        "visual_checks": [
            {"path": str(path), "sha256": runner.digest(path), "status": "passed"}
            for path in image_paths
        ],
        "document_checks": [
            {"path": str(document), "sha256": runner.digest(document), "status": "passed"}
        ],
        "notion_checks": [{"status": "passed", "page": "synthetic-readback"}],
    }
    review_path.write_text(json.dumps(review))
    saved, reconstructions = [], []
    monkeypatch.setattr(runner, "REPO", repo)
    monkeypatch.setattr(runner, "ROOTS", roots)
    monkeypatch.setattr(runner, "LOGS", logs)
    monkeypatch.setattr(runner, "RECORD", record_path)
    monkeypatch.setattr(runner, "__file__", str(orchestration))
    monkeypatch.setattr(runner, "protected_inventory", lambda: {})
    monkeypatch.setattr(runner, "inventory", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "git_check", lambda: "verifiedsha")
    monkeypatch.setattr(
        runner, "save", lambda path, value: saved.append((path, json.loads(json.dumps(value))))
    )

    def git_output(command, **kwargs):
        if command[:2] == ["git", "ls-remote"]:
            return "verifiedsha\trefs/heads/main\n"
        if command[:2] == ["git", "show"]:
            return (repo / command[2].removeprefix("HEAD:")).read_bytes()
        raise AssertionError(f"Unexpected subprocess: {command}")

    def reconstruct(args, report):
        reconstructions.append(args)
        report["status"] = "passed"

    monkeypatch.setattr(runner.subprocess, "check_output", git_output)
    monkeypatch.setattr(validator, "run", reconstruct)
    return SimpleNamespace(
        review_path=review_path,
        review=review,
        record=record,
        record_path=record_path,
        numerical_code=numerical_code,
        orchestration=orchestration,
        validation_path=validation_path,
        images=image_paths,
        junit=junit,
        saved=saved,
        reconstructions=reconstructions,
    )


def test_complete_accepts_all_gates_and_records_orchestration_revision(delivery):
    runner.complete(delivery.review_path)
    assert len(delivery.reconstructions) == 1
    assert delivery.saved[-1][1]["status"] == "completed"
    report = delivery.saved[0][1]
    assert report["delivery_time_independent_reconstruction"] == "passed"
    assert report["orchestration_execution_sha256"] == "older-orchestration-hash"
    assert report["orchestration_delivery_sha256"] == runner.digest(delivery.orchestration)


def test_complete_rejects_changed_numerical_code(delivery):
    delivery.numerical_code.write_text("# changed numerical result definition\n")
    with pytest.raises(RuntimeError, match="Numerical/validation code changed"):
        runner.complete(delivery.review_path)
    assert not delivery.reconstructions
    assert not delivery.saved


def test_complete_rejects_changed_validation_record(delivery):
    delivery.validation_path.write_text('{"status":"passed","images":[]}')
    with pytest.raises(RuntimeError, match="Independent validation record changed"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_complete_rejects_post_audit_png_change(delivery):
    delivery.images[-1].write_bytes(b"modified individual image")
    with pytest.raises(RuntimeError, match="PNG changed after independent validation"):
        runner.complete(delivery.review_path)
    assert not delivery.reconstructions
    assert not delivery.saved


def test_complete_propagates_post_audit_csv_mismatch(delivery, monkeypatch):
    def reject_changed_csv(args, report):
        raise AssertionError("synthetic quantification CSV mismatch")

    monkeypatch.setattr(validator, "run", reject_changed_csv)
    with pytest.raises(AssertionError, match="quantification CSV mismatch"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_complete_rejects_missing_group_visual_review(delivery):
    delivery.review["visual_checks"] = delivery.review["visual_checks"][1:]
    delivery.review_path.write_text(json.dumps(delivery.review))
    with pytest.raises(RuntimeError, match="all 12 group plots"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_complete_rejects_failed_junit_even_with_matching_hash(delivery):
    delivery.junit.write_text(
        '<testsuites><testsuite><testcase name="failed"><failure/></testcase>'
        "</testsuite></testsuites>"
    )
    delivery.review["test_report"]["sha256"] = runner.digest(delivery.junit)
    delivery.review_path.write_text(json.dumps(delivery.review))
    with pytest.raises(RuntimeError, match="JUnit report"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_complete_rejects_uncommitted_numerical_code(delivery, monkeypatch):
    original = runner.subprocess.check_output

    def uncommitted(command, **kwargs):
        if command == ["git", "show", "HEAD:analysis.py"]:
            return b"# prior committed calculation\n"
        return original(command, **kwargs)

    monkeypatch.setattr(runner.subprocess, "check_output", uncommitted)
    with pytest.raises(RuntimeError, match="Executed code is not committed"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


@pytest.fixture
def pilot_tables(tmp_path, monkeypatch):
    phase = tmp_path / "Phase4"
    roots = tuple(phase / stem for stem in runner.STEMS)
    monkeypatch.setattr(runner, "PHASE", phase)
    monkeypatch.setattr(runner, "ROOTS", roots)
    pairs = []
    for number, (index, relative) in enumerate(runner.PILOT_TABLE_RELATIVE_PATHS):
        original = roots[index] / "Sub/tables" / relative
        archived = roots[index] / "Sub/history/Pilot" / relative
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_text(f"synthetic,table\n{number},pilot\n")
        pairs.append((original, archived, runner.digest(original)))
    untouched = []
    for root in roots:
        for relative in (
            "Sub/tables/ROIQuality/Production_AllParticipants.csv",
            "Sub/tables/ROIQuality/Unlisted_ID101-201.csv",
            "CCube/GrandAverage/Production.png",
        ):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"untouched production or unlisted fixture")
            untouched.append((path, runner.digest(path)))
    return SimpleNamespace(roots=roots, pairs=pairs, untouched=untouched)


def test_archive_exact_seven_pilot_tables_preserves_hash_and_other_files(pilot_tables):
    report = runner.archive_pilot_tables()
    assert report["count"] == len(report["records"]) == 7
    assert {item["status"] for item in report["records"]} == {"archived"}
    for original, archived, expected in pilot_tables.pairs:
        assert not original.exists()
        assert runner.digest(archived) == expected
    for path, expected in pilot_tables.untouched:
        assert runner.digest(path) == expected
    repeated = runner.archive_pilot_tables()
    assert {item["status"] for item in repeated["records"]} == {"already_archived"}
    assert [row["sha256"] for row in repeated["records"]] == [
        row["sha256"] for row in report["records"]
    ]


def test_archive_unequal_existing_target_rejects_before_any_move(pilot_tables):
    original, archived, _ = pilot_tables.pairs[-1]
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_bytes(b"different archive")
    with pytest.raises(RuntimeError, match="Existing pilot archive differs"):
        runner.archive_pilot_tables()
    assert all(path.exists() for path, _, _ in pilot_tables.pairs)
    assert not any(path.exists() for _, path, _ in pilot_tables.pairs[:-1])
    assert archived.read_bytes() == b"different archive"


def test_archive_identical_existing_copy_and_partial_previous_move_are_safe(pilot_tables):
    source, destination, _ = pilot_tables.pairs[0]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    source2, destination2, _ = pilot_tables.pairs[1]
    destination2.parent.mkdir(parents=True, exist_ok=True)
    source2.rename(destination2)
    report = runner.archive_pilot_tables()
    assert report["records"][0]["status"] == "identical_archive_source_removed"
    assert report["records"][1]["status"] == "already_archived"
    for original, archived, expected in pilot_tables.pairs:
        assert not original.exists() and runner.digest(archived) == expected


@pytest.mark.parametrize("where", ["source", "target", "target_parent"])
def test_archive_rejects_symlink_paths_before_moving_other_tables(pilot_tables, tmp_path, where):
    original, archived, _ = pilot_tables.pairs[-1]
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_file = outside / "data.csv"
    outside_file.write_bytes(b"outside fixture")
    if where == "source":
        original.unlink()
        original.symlink_to(outside_file)
    elif where == "target":
        archived.parent.mkdir(parents=True, exist_ok=True)
        archived.symlink_to(outside_file)
    else:
        archived.parent.parent.mkdir(parents=True, exist_ok=True)
        archived.parent.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="Unsafe|Symlink"):
        runner.archive_pilot_tables()
    assert all(path.exists() for path, _, _ in pilot_tables.pairs)
    assert outside_file.read_bytes() == b"outside fixture"


def test_archive_missing_table_rejects_before_any_move(pilot_tables):
    pilot_tables.pairs[-1][0].unlink()
    with pytest.raises(FileNotFoundError, match="both absent"):
        runner.archive_pilot_tables()
    assert all(path.exists() for path, _, _ in pilot_tables.pairs[:-1])
    assert not any(path.exists() for _, path, _ in pilot_tables.pairs)


def test_archive_rejects_file_in_destination_ancestor_before_any_move(pilot_tables):
    blocked = pilot_tables.roots[1] / "Sub/history"
    blocked.write_bytes(b"not a directory")
    with pytest.raises(ValueError, match="Non-directory ancestor"):
        runner.archive_pilot_tables()
    assert all(path.exists() for path, _, _ in pilot_tables.pairs)
    assert not any(path.exists() for _, path, _ in pilot_tables.pairs)


def test_archive_rejects_unsafe_allowlist_and_wrong_roots(pilot_tables, monkeypatch):
    entries = runner.PILOT_TABLE_RELATIVE_PATHS
    monkeypatch.setattr(
        runner, "PILOT_TABLE_RELATIVE_PATHS", entries[:-1] + ((1, "../escape.csv"),)
    )
    with pytest.raises(ValueError, match="Unsafe pilot table"):
        runner.archive_pilot_tables()
    monkeypatch.setattr(runner, "PILOT_TABLE_RELATIVE_PATHS", entries)
    monkeypatch.setattr(runner, "ROOTS", (pilot_tables.roots[0], pilot_tables.roots[0]))
    with pytest.raises(ValueError, match="Unexpected No12 roots"):
        runner.archive_pilot_tables()
    assert all(path.exists() for path, _, _ in pilot_tables.pairs)


def test_execute_archives_after_both_pilots_before_production(tmp_path, monkeypatch):
    calls, saved = [], []
    monkeypatch.setattr(runner, "git_check", lambda: "synthetic-head")
    monkeypatch.setattr(runner, "RECORD", tmp_path / "execution.json")
    monkeypatch.setattr(runner, "prepare", lambda path: {})
    monkeypatch.setattr(runner, "inventory", lambda *args, **kwargs: {})
    monkeypatch.setattr(runner, "protected_inventory", lambda: {})
    monkeypatch.setattr(runner, "digest", lambda path: "synthetic-sha")
    monkeypatch.setattr(
        runner, "save", lambda path, value: saved.append(json.loads(json.dumps(value)))
    )
    monkeypatch.setattr(runner, "stage", lambda name, *args: calls.append(name))

    def archive():
        calls.append("ArchivePilotTables")
        return {"count": 7, "records": []}

    monkeypatch.setattr(runner, "archive_pilot_tables", archive)
    runner.execute(tmp_path / "audit.json")
    assert calls == [
        "Preflight_1",
        "Preflight_2",
        "Pilot_1",
        "Pilot_2",
        "ArchivePilotTables",
        "Production_1",
        "Production_2",
        "IndependentValidation",
    ]
    assert saved[-1]["pilot_table_archive"]["count"] == 7
