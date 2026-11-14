"""No11 additive cohort and rendering safeguards, using synthetic data only."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム/Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import run_phase4_no11_sensitivity as runner  # noqa: E402


def spec(first, product):
    first = str(first)
    return runner.primary.source.ParticipantSpec(first, str(int(first) + 100), first, product)


@pytest.fixture
def cohort():
    specs = [spec(number, product) for product, numbers in (
        ("CCube", (102, 120, 132, 140, 141)),
        ("VRohtoPremium", (101, 109, 131)),
    ) for number in numbers]
    items = [{"spec": value, "product_dir": value.product} for value in specs]
    return items, specs


def test_selection_removes_requested_whole_pairs_and_preserves_input(cohort):
    items, specs = cohort
    selected, audit = runner.select_items(items, specs)
    assert {item["spec"].pair_id for item in selected} == {
        "102-202", "120-220", "101-201", "109-209"
    }
    assert len(items) == 8
    assert audit["SpecifiedPairExcluded"].sum() == 4
    assert audit["Included"].sum() == 4
    assert audit["PrimaryAnalysisEligible"].all()


def test_existing_baseline_absence_is_not_conflated_with_new_exclusion(cohort):
    items, specs = cohort
    items = [item for item in items if item["spec"].pair_id != "109-209"]
    _, audit = runner.select_items(items, specs)
    row = audit.set_index("PairID").loc["109-209"]
    assert not row["Included"] and not row["PrimaryAnalysisEligible"]
    assert not row["SpecifiedPairExcluded"]
    assert "baseline" in row["Reason"]


def test_selection_rejects_missing_excluded_pair_and_product_mismatch(cohort):
    items, specs = cohort
    with pytest.raises(ValueError, match="Specified pair absent"):
        runner.select_items(items[:-1], specs)
    items[-1] = {**items[-1], "product_dir": "CCube"}
    with pytest.raises(ValueError, match="product mismatch"):
        runner.select_items(items, specs)


def test_selection_rejects_duplicate(cohort):
    items, specs = cohort
    with pytest.raises(ValueError, match="Duplicate"):
        runner.select_items([*items, items[0]], specs)


@pytest.fixture
def source_audit(tmp_path, monkeypatch, cohort):
    _, specs = cohort
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("synthetic source manifest\n")
    monkeypatch.setattr(runner, "MANIFEST", manifest)
    audit = {
        "checked_at": datetime.now(runner.TOKYO).isoformat(),
        "matched_pairs": 40, "matched_sessions": 80, "mismatches": 0,
        "manifest_sha256": runner.primary.digest(manifest),
        "request_normalization": {"original": "14-240", "canonical": "140-240",
                                  "verified": True, "evidence": "synthetic unique pairing"},
        "explicit_requested_exclusions": [
            {"first_session_id": value.first_session_id,
             "second_session_id": value.second_session_id,
             "drops_session_id": value.drops_session_id, "product": value.product}
            for value in specs
            if value.pair_id in runner.EXCLUDED_PAIRS_BY_PRODUCT[value.product]
        ],
    }
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(audit))
    return path, audit, specs


def test_source_gate_accepts_fresh_audit(source_audit):
    path, audit, specs = source_audit
    assert runner.verify_source_audit(path, specs) == audit


@pytest.mark.parametrize("mutation,match", [
    ("old", "today"), ("unconfirmed", "Live confirmation"),
    ("hash", "Manifest hash"), ("mismatch", "mapping audit"),
])
def test_source_gate_rejects_invalid_audit(source_audit, mutation, match):
    path, audit, specs = source_audit
    if mutation == "old":
        audit["checked_at"] = (datetime.now(runner.TOKYO) - timedelta(days=1)).isoformat()
    elif mutation == "unconfirmed":
        audit["request_normalization"]["verified"] = False
    elif mutation == "hash":
        audit["manifest_sha256"] = "changed"
    else:
        audit["mismatches"] = 1
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match=match):
        runner.verify_source_audit(path, specs)


def test_source_gate_checks_unique_manifest_partner(source_audit):
    path, _, specs = source_audit
    duplicate = SimpleNamespace(first_session_id="144", second_session_id="240",
                                pair_id="144-240", product="CCube")
    with pytest.raises(ValueError, match="uniquely"):
        runner.verify_source_audit(path, [*specs, duplicate])


def test_source_gate_rejects_wrong_condition_or_exclusion_set(source_audit):
    path, audit, specs = source_audit
    audit["explicit_requested_exclusions"][0]["drops_session_id"] = "999"
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="conditions differ"):
        runner.verify_source_audit(path, specs)
    audit["explicit_requested_exclusions"] = audit["explicit_requested_exclusions"][1:]
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match="exclusion set"):
        runner.verify_source_audit(path, specs)


def test_output_contract_only_new_group_artifacts(tmp_path):
    for stem in runner.primary.STEMS:
        for product in runner.PRODUCTS:
            paths = runner.output_paths(stem, product, tmp_path)
            assert len(paths) == 7
            assert len([path for path in paths.values() if path.suffix == ".png"]) == 3
            assert all(path.name.endswith(f"_{runner.SUFFIX}{path.suffix}")
                       for path in paths.values())
            assert paths["set_png"].parent.name == runner.SUFFIX
            assert all("Individual" not in str(path) and "Topography" not in str(path)
                       for path in paths.values())
    with pytest.raises(ValueError, match="Unknown"):
        runner.output_paths("No10_FzLowAlpha", "CCube", tmp_path)


def test_capture_uses_actual_artist_metadata_and_restores_savefig(tmp_path):
    plt.rcParams.update({"font.family": "Arial"})
    path = tmp_path / "synthetic.png"
    records = []
    original = runner.matplotlib.figure.Figure.savefig
    figure, axis = plt.subplots()
    axis.set_ylim(-2, 4)
    axis.set_yticks([-2, 0, 2, 4])
    axis.text(.5, .8, "Set 1", fontsize=26)
    with runner.capture_plot_metadata(records, {path}):
        figure.savefig(path)
    plt.close(figure)
    assert runner.matplotlib.figure.Figure.savefig is original
    assert records[0]["axes"][0]["ylim"] == [-2, 4]
    assert records[0]["axes"][0]["texts"][0]["fontsize"] == 26
    assert records[0]["font_families"] == ["Arial"]


def test_capture_refuses_out_of_scope_figure_and_restores(tmp_path):
    original = runner.matplotlib.figure.Figure.savefig
    figure, _ = plt.subplots()
    try:
        with pytest.raises(ValueError, match="unexpected sensitivity"):
            with runner.capture_plot_metadata([], {tmp_path / "allowed.png"}):
                figure.savefig(tmp_path / "primary.png")
    finally:
        plt.close(figure)
    assert runner.matplotlib.figure.Figure.savefig is original
    assert not (tmp_path / "primary.png").exists()


def test_axes_recomputed_from_remaining_cohort_not_primary():
    engine = runner.adapter.build_absolute_engine()
    frame = pd.DataFrame({
        "EyeDrop_Mean_PSD_uV2_per_Hz": [1., 2.],
        "EyeDrop_SEM_PSD_uV2_per_Hz": [.2, .3],
        "Control_Mean_PSD_uV2_per_Hz": [1., 1.5],
        "Control_SEM_PSD_uV2_per_Hz": [.1, .2],
    })
    upper, ticks = runner.absolute_grand_axis(engine, [frame, frame * 2])
    expected, _ = engine._nice_upper(np.array([4.6]), .75)
    assert upper == expected and ticks[-1] == upper
    assert upper < 100


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    import validate_phase4_no11_sensitivity_outputs as validator

    repo = tmp_path / "repo"
    repo.mkdir()
    code, document = repo / "analysis.py", repo / "spec.md"
    code.write_text("# synthetic analysis\n")
    document.write_text("# synthetic specification\n")
    record_path, validation_path = tmp_path / "execution.json", tmp_path / "validation.json"
    delivery_path, review_path = tmp_path / "delivery.json", tmp_path / "review.json"
    images = [tmp_path / f"plot{index}.png" for index in range(12)]
    for path in images:
        path.write_bytes(b"synthetic artifact")
    test_report = tmp_path / "tests.xml"
    test_report.write_text(
        '<testsuites><testsuite><testcase name="pass"/></testsuite></testsuites>'
    )
    validation_path.write_text('{"status":"passed"}')
    record = {
        "status": "generated_pending_independent_and_visual_verification",
        "code_hashes": {"analysis.py": runner.primary.digest(code)},
        "output_files": [{"path": str(path), "sha256": runner.primary.digest(path)}
                         for path in images],
        "protected_before": {}, "cloud_sync": "synthetic local test",
    }
    review = {
        "status": "passed", "tests_passed": True,
        "test_report": {"path": str(test_report), "sha256": runner.primary.digest(test_report)},
        "independent_validation": {"path": str(validation_path),
                                   "sha256": runner.primary.digest(validation_path)},
        "visual_checks": [{"path": str(path), "sha256": runner.primary.digest(path),
                           "status": "passed"} for path in images],
        "document_checks": [{"path": str(document), "sha256": runner.primary.digest(document),
                             "status": "passed"}],
        "notion_checks": [{"page": "synthetic", "status": "passed"}],
    }
    record_path.write_text(json.dumps(record))
    review_path.write_text(json.dumps(review))
    saved, reconstructed = [], []
    monkeypatch.setattr(runner, "RECORD", record_path)
    monkeypatch.setattr(runner, "VALIDATION", validation_path)
    monkeypatch.setattr(runner, "DELIVERY", delivery_path)
    monkeypatch.setattr(runner, "TESTS", tmp_path / "durable_tests.xml")
    monkeypatch.setattr(runner, "protected_snapshot", lambda: {})
    monkeypatch.setattr(runner, "allowed_outputs", lambda: {*images, record_path})
    monkeypatch.setattr(runner.primary, "REPO", repo)
    monkeypatch.setattr(runner.primary, "git_check", lambda: "remoteverifiedsha")
    monkeypatch.setattr(
        runner.primary, "save", lambda path, value: saved.append((path, value.copy()))
    )

    def git_output(command, **kwargs):
        if command[:2] == ["git", "ls-remote"]:
            return "remoteverifiedsha\trefs/heads/main\n"
        if command[:2] == ["git", "show"]:
            return (repo / command[2].split(":", 1)[1]).read_bytes()
        raise AssertionError(f"Unexpected command {command}")

    def reconstruct(args, report):
        reconstructed.append(args)
        report["status"] = "passed"

    monkeypatch.setattr(runner.primary.subprocess, "check_output", git_output)
    monkeypatch.setattr(validator, "run", reconstruct)
    return SimpleNamespace(review_path=review_path, review=review, record=record,
                           record_path=record_path, images=images, code=code, document=document,
                           saved=saved, reconstructed=reconstructed)


def test_final_gate_accepts_verified_delivery(delivery):
    result = runner.complete(delivery.review_path)
    assert result["status"] == "completed"
    assert result["final_git_commit"] == "remoteverifiedsha"
    assert len(delivery.reconstructed) == 1
    assert len(delivery.saved) == 2


def test_final_gate_rejects_missing_visual(delivery):
    delivery.review["visual_checks"] = delivery.review["visual_checks"][:-1]
    delivery.review_path.write_text(json.dumps(delivery.review))
    with pytest.raises(RuntimeError, match="all 12"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_final_gate_rejects_changed_numeric_code(delivery):
    delivery.code.write_text("# changed\n")
    with pytest.raises(RuntimeError, match="Executed code changed"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_final_gate_rejects_changed_output(delivery):
    delivery.images[0].write_bytes(b"changed")
    with pytest.raises(RuntimeError, match="Generated artifact changed"):
        runner.complete(delivery.review_path)
    assert not delivery.saved


def test_final_gate_rejects_changed_protected_source(delivery, monkeypatch):
    monkeypatch.setattr(runner, "protected_snapshot", lambda: {"changed": True})
    with pytest.raises(RuntimeError, match="Protected inputs"):
        runner.complete(delivery.review_path)
    assert not delivery.saved
