"""Synthetic-only checks of qualitative report aggregation, never real data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT_DIR = Path(__file__).parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))
import phase4_iaf_clarity_review as review  # noqa: E402


@pytest.fixture
def synthetic_run(tmp_path):
    base, caches = tmp_path / "results", tmp_path / "caches"
    caches.mkdir()
    manifest_rows = []
    for index in range(40):
        first, second = str(10001 + index), str(20001 + index)
        manifest_rows.append(
            {
                "first_session_id": first,
                "second_session_id": second,
                "drops_session_id": first if index % 2 else second,
                "product": review.PRODUCTS[index // 20],
            }
        )
        for sid in (first, second):
            (caches / f"synthetic_{sid}.h5").write_bytes(b"synthetic-source-no-human-data")
    assessment_paths, review_outputs = [], []
    for number, (channel, kind, folder) in review.ANALYSES.items():
        root = base / folder
        tables = root / "Sub/tables"
        reviews = root / "Sub/PeakClarityReview"
        tables.mkdir(parents=True)
        reviews.mkdir(parents=True)
        pd.DataFrame(manifest_rows).to_csv(tables / "ParticipantManifest.csv", index=False)
        entries, rows = [], []
        labels = review.interval_labels(number)
        for index, person in enumerate(manifest_rows):
            pair = f"{person['first_session_id']}-{person['second_session_id']}"
            conditions = {}
            for condition in review.CONDITIONS:
                sid = (
                    person["drops_session_id"]
                    if condition == "Eye Drop"
                    else next(
                        person[k]
                        for k in ("first_session_id", "second_session_id")
                        if person[k] != person["drops_session_id"]
                    )
                )
                grades = "C" * len(labels)
                if index == 0:
                    grades = "A" * len(labels)  # No C is not equivalent to all U.
                if index == 1 and condition == "Control":
                    grades = "U" * len(labels)
                if index == 2 and condition == "Eye Drop":
                    grades = "M" + grades[1:]  # Missing baseline.
                if index == 3 and condition == "Control":
                    grades = grades[:2] + "M" + grades[3:]  # Later missing interval.
                conditions[condition] = {"grades": grades, "note": "合成データの定性メモ"}
                for position, (lab, grade) in enumerate(zip(labels, grades, strict=True), 1):
                    missing = grade == "M"
                    rows.append(
                        {
                            "pair_id": pair,
                            "session_id": sid,
                            "condition": condition,
                            "product": person["product"],
                            "analysis_number": number,
                            "channel": channel,
                            "set_number": int(lab[0]),
                            "interval": "whole" if kind == "setwise" else lab[1],
                            "position": position,
                            "frequency_hz": np.nan if missing else 10 + position / 10,
                            "quality": "missing_set" if missing else "ok",
                            "n_valid_segments": 0 if missing else 12,
                            "n_possible_segments": 0 if missing else 13,
                            "ica_channel_excluded": False,
                            "smoothing_points": 5,
                            "smoothing_passes": 1,
                            "peak_input_dataset": "smoothed_mean_psd_uv2_hz",
                        }
                    )
            entries.append({"pair_id": pair, "analysis_number": number, "conditions": conditions})
            fig = reviews / person["product"] / f"Pair{pair}_No{number}_AlphaReview.png"
            fig.parent.mkdir(exist_ok=True)
            fig.write_bytes(b"synthetic-review-not-real-png")
            review_outputs.append(str(fig))
            tag = "SetwiseIAF" if kind == "setwise" else "HalfSetIAF"
            original = (
                root
                / person["product"]
                / "Individual"
                / (f"Pair{pair}_No{number}_{channel}_{tag}_ThreePanel.png")
            )
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(b"synthetic-original-not-real-png")
        frame = pd.DataFrame(rows)
        frame.to_csv(reviews / "SavedEstimateInventory.csv", index=False)
        frame.to_csv(tables / f"No{number}_IAF_Estimates.csv", index=False)
        assessment = tmp_path / f"synthetic_No{number}.json"
        assessment.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
        assessment_paths.append(assessment)
    logs = base / review.ANALYSES[8][2] / "Sub/logs"
    logs.mkdir()
    preparation = {
        "input_sha256": {str(p): review.sha256_file(p) for p in caches.glob("*.h5")},
        "manifest_sha256": review.sha256_file(
            base / review.ANALYSES[8][2] / "Sub/tables/ParticipantManifest.csv"
        ),
        "cache_unchanged": True,
        "review_sheet_count": 80,
        "outputs": review_outputs,
    }
    (logs / "PeakClarityReview_Preparation.json").write_text(
        json.dumps(preparation), encoding="utf-8"
    )
    return base, caches, assessment_paths


def test_finalization_counts_baselines_observations_and_source_integrity(synthetic_run):
    base, caches, paths = synthetic_run
    record = review.finalize(paths, base=base, cache_root=caches)
    assert record["participant_review_rows"] == 80
    assert record["interval_review_rows"] == 960
    assert record["group_summary_rows"] == 4
    assert record["selection_finalized"] is False
    assert record["grand_average_executed"] is False
    assert record["exclusions_applied"] is False
    assert len(record["input_cache_sha256"]) == 80
    review.assert_hashes(record["input_cache_sha256"])
    review.assert_hashes(record["source_file_sha256"])
    root = base / review.ANALYSES[8][2] / "Sub/PeakClarityReview"
    pairs = pd.read_csv(root / "ParticipantReview.csv", dtype={"baseline_interval": str})
    groups = pd.read_csv(root / "GroupSummary.csv")
    no9 = pairs.loc[pairs.analysis_number == 9].reset_index(drop=True)
    assert no9.iloc[0].observation_class == "両条件Cなし"
    assert bool(no9.iloc[0].contains_ambiguous_interval)
    assert no9.iloc[0].eye_drop_U_count == 0
    assert no9.iloc[1].observation_class == "片条件Cあり"
    assert no9.iloc[2].baseline_interval == "1"
    assert not bool(no9.iloc[2].both_baselines_finite)
    assert no9.iloc[2].paired_finite_interval_count == 5
    assert no9.iloc[2].baseline_valid_paired_interval_count == 0
    assert bool(no9.iloc[3].both_baselines_finite)
    assert no9.iloc[3].baseline_valid_paired_interval_count == 5
    assert (
        groups.both_conditions_C + groups.one_condition_C + groups.neither_condition_C == 20
    ).all()
    md = (root / "PeakClarityReview.md").read_text()
    assert "採否は未確定" in md and "全区間Uとは断定できない" in md
    assert md.count("### Cキューブ") == 2 and md.count("### Vロートプレミアム") == 2
    assert md.count("・[元図]") == 80
    assert len(json.loads((root / "AssessmentInput.json").read_text())) == 80


def _edit_json(path, mutate):
    contents = json.loads(path.read_text())
    mutate(contents)
    path.write_text(json.dumps(contents), encoding="utf-8")


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda rows: rows[0]["conditions"]["Eye Drop"].update(grades="CC"), "grade sequence"),
        (lambda rows: rows[0]["conditions"]["Eye Drop"].update(grades="ZZZZZZ"), "grade sequence"),
        (lambda rows: rows[0]["conditions"].update(Other={}), "exactly Eye Drop"),
        (lambda rows: rows[0].update(pair_id=rows[1]["pair_id"]), "duplicate assessment pair"),
        (lambda rows: rows[0].update(product="VRohtoPremium"), "Assessment product mismatch"),
        (
            lambda rows: rows[0]["conditions"]["Eye Drop"].update(session_id="999999"),
            "session ID mismatch",
        ),
        (lambda rows: rows[0]["conditions"]["Eye Drop"].update(grades="MAAAAA"), "Grade M/PSD"),
    ],
)
def test_bad_assessment_is_rejected_before_output(synthetic_run, mutate, match):
    base, caches, paths = synthetic_run
    _edit_json(paths[0], mutate)
    with pytest.raises(ValueError, match=match):
        review.finalize(paths, base=base, cache_root=caches)
    assert not (
        base / review.ANALYSES[8][2] / "Sub/PeakClarityReview/ParticipantReview.csv"
    ).exists()


def test_cache_changed_since_preparation_is_rejected(synthetic_run):
    base, caches, paths = synthetic_run
    next(caches.glob("*.h5")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Source SHA mismatch"):
        review.finalize(paths, base=base, cache_root=caches)


def test_changed_cache_during_finalization_is_rejected(synthetic_run, monkeypatch):
    base, caches, paths = synthetic_run
    original_render = review.render_report

    def mutate_during_render(*args):
        next(caches.glob("*.h5")).write_bytes(b"unexpected concurrent change")
        return original_render(*args)

    monkeypatch.setattr(review, "render_report", mutate_during_render)
    with pytest.raises(ValueError, match="Source SHA mismatch"):
        review.finalize(paths, base=base, cache_root=caches)
    assert not (
        base / review.ANALYSES[8][2] / "Sub/logs/PeakClarityReview_Finalization.json"
    ).exists()


@pytest.mark.parametrize(
    "column,value,match",
    [
        ("product", "VRohtoPremium", "condition/ID/product"),
        ("session_id", "999999", "condition/ID/product"),
        ("quality", "missing_set", "PSD missing reason"),
        ("interval", "b", "Set/half/position"),
        ("frequency_hz", 30.0, "quality/range"),
    ],
)
def test_inventory_mismatch_is_rejected(synthetic_run, column, value, match):
    base, caches, paths = synthetic_run
    inventory = base / review.ANALYSES[8][2] / "Sub/PeakClarityReview/SavedEstimateInventory.csv"
    frame = pd.read_csv(inventory, dtype={"session_id": str})
    frame.loc[0, column] = value
    frame.to_csv(inventory, index=False)
    with pytest.raises(ValueError, match=match):
        review.finalize(paths, base=base, cache_root=caches)


def test_no_local_peak_is_not_missing_psd(synthetic_run):
    base, caches, paths = synthetic_run
    root = base / review.ANALYSES[8][2]
    for path in (
        root / "Sub/PeakClarityReview/SavedEstimateInventory.csv",
        root / "Sub/tables/No8_IAF_Estimates.csv",
    ):
        frame = pd.read_csv(path)
        frame.loc[0, "frequency_hz"] = np.nan
        frame.loc[0, "quality"] = "no_local_peak"
        frame.to_csv(path, index=False)
    review.finalize(paths, base=base, cache_root=caches)
    intervals = pd.read_csv(root / "Sub/PeakClarityReview/IntervalReview.csv")
    row = intervals.iloc[0]
    assert row.clarity_grade == "A" and bool(row.psd_available) and not bool(row.iaf_finite)


def test_duplicate_inventory_interval_and_missing_analysis_fail(synthetic_run):
    base, _, paths = synthetic_run
    with pytest.raises(ValueError, match="two distinct"):
        review.load_assessments(paths[:1])
    manifest_path = base / review.ANALYSES[8][2] / "Sub/tables/ParticipantManifest.csv"
    manifest = review.read_manifest(manifest_path)
    inventory = base / review.ANALYSES[8][2] / "Sub/PeakClarityReview/SavedEstimateInventory.csv"
    frame = pd.read_csv(inventory)
    frame.iloc[1] = frame.iloc[0]
    frame.to_csv(inventory, index=False)
    with pytest.raises(ValueError, match="Duplicate inventory"):
        review.validated_inventory(inventory, 8, manifest)


def test_finalized_selection_prevents_provisional_overwrite(synthetic_run):
    base, caches, paths = synthetic_run
    selection = (
        base / review.ANALYSES[8][2] / "Sub/PeakClarityReview/GrandAverageSelection_Final.json"
    )
    selection.write_text('{"status":"final"}')
    before = selection.read_bytes()
    with pytest.raises(ValueError, match="Finalized selection exists"):
        review.finalize(paths, base=base, cache_root=caches)
    assert selection.read_bytes() == before


@pytest.mark.parametrize("number", [10, 11])
def test_retired_review_number_is_not_silently_remapped(number):
    with pytest.raises(ValueError, match="Only current"):
        review.interval_labels(number)
