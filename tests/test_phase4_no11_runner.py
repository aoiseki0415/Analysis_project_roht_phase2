"""Synthetic delivery-gate tests: no production or OneDrive writes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import run_phase4_no11 as runner  # noqa: E402
import validate_phase4_no11_outputs as validator  # noqa: E402


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
    orchestration = repo / "run_phase4_no11.py"
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
            "run_phase4_no11.py": "older-orchestration-hash",
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
            return document.read_bytes()
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
