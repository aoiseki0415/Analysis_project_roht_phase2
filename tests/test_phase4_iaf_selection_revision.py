"""Synthetic selection revision and scoped output tests; no research data used."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "解析プログラム/Phase4_脳波解析"))
import phase4_iaf_grand_average as ga  # noqa: E402
import phase4_iaf_selection_revision as revision  # noqa: E402
from test_phase4_iaf_grand_average import (  # noqa: E402
    synthetic_estimates,
    synthetic_manifest,
    synthetic_selection,
)


@pytest.fixture
def layout(tmp_path):
    manifest = synthetic_manifest()
    base = tmp_path / "results"
    root = base / ga.ANALYSES[8][2]
    manifest_path = tmp_path / "manifest.csv"
    pd.DataFrame(
        [
            {
                k: person[k]
                for k in ("first_session_id", "second_session_id", "drops_session_id", "product")
            }
            for person in manifest.values()
        ]
    ).to_csv(manifest_path, index=False)
    frame = synthetic_selection(manifest)
    for number in ga.ANALYSES:
        for product in ga.PRODUCTS:
            mask = (frame.analysis_number == number) & frame["product"].eq(product)
            frame.loc[
                frame.loc[mask].index[revision.OLD_COUNTS[number][product] :], ga.ADOPTION
            ] = "しない"
    frame = frame.astype(str)
    record = {
        "schema": revision.OLD_SCHEMA,
        "active_analyses": ga.ACTIVE_SELECTION_ANALYSES,
        "status": "final",
        "decisions": frame.to_dict("records"),
        "manual_exclusions": {str(n): {p: [] for p in ga.PRODUCTS} for n in ga.ANALYSES},
    }
    review = root / revision.REVIEW
    review.mkdir(parents=True)
    (review / "GrandAverageSelection_Final.json").write_text(json.dumps(record))
    frame.to_csv(review / "GrandAverageSelection_Final.csv", index=False)
    (review / "GrandAverageSelection_Final.md").write_text("old description")
    frame.assign(eye_grades="CAUCAM", control_grades="CCAUAC").to_csv(
        review / "ParticipantReview.csv", index=False
    )
    pd.DataFrame(
        [
            {"analysis_number": n, "product": p, "observation_count": 123, "adopted_pairs": count}
            for n, groups in revision.OLD_COUNTS.items()
            for p, count in groups.items()
        ]
    ).to_csv(review / "GroupSummary.csv", index=False)
    frozen = root / revision.FROZEN
    frozen.parent.mkdir(parents=True)
    frozen.write_text(
        json.dumps(
            {
                "outputs_sha256": {
                    str(root / p): ga.sha256_file(root / p) for p in revision.EDITABLE[:4]
                }
            }
        )
    )
    pair = frame.loc[
        (frame.analysis_number == "8")
        & frame["product"].eq("VRohtoPremium")
        & frame[ga.ADOPTION].eq("する"),
        "pair_id",
    ].iloc[0]
    return base, manifest_path, pair, manifest


def call(layout, apply=False, **kwargs):
    base, manifest_path, pair, _ = layout
    args = dict(
        base=base,
        manifest_path=manifest_path,
        number=8,
        product="VRohtoPremium",
        pair=pair,
        reason="Synthetic quality review; no amplitude threshold",
        revision_key="test",
        apply=apply,
    )
    args.update(kwargs)
    return revision.revise_selection(**args)


def test_preflight_does_not_write(layout):
    base = layout[0]
    before = {str(p): ga.sha256_file(p) for p in base.rglob("*") if p.is_file()}
    result = call(layout)
    assert result["writes"] == 0
    assert before == {str(p): ga.sha256_file(p) for p in base.rglob("*") if p.is_file()}


def test_revision_only_changes_one_adoption_and_preserves_observations(layout):
    base, _, pair, manifest = layout
    root = base / ga.ANALYSES[8][2]
    review = root / revision.REVIEW
    before = revision.read_csv(review / "ParticipantReview.csv")
    report = call(layout, apply=True)
    after = revision.read_csv(review / "ParticipantReview.csv")
    assert sum(before[ga.ADOPTION] != after[ga.ADOPTION]) == 1
    pd.testing.assert_frame_equal(
        before[["eye_grades", "control_grades"]], after[["eye_grades", "control_grades"]]
    )
    selection = ga.load_selection(
        review / "GrandAverageSelection_Final.json",
        review / "GrandAverageSelection_Final.csv",
        manifest,
    )
    assert selection[ga.ADOPTION].eq("する").sum() == 43
    assert (
        selection.loc[
            (selection.analysis_number == 8) & selection.pair_id.eq(pair), ga.ADOPTION
        ].item()
        == "しない"
    )
    ga.assert_hashes(report["outputs_sha256"])
    archive = Path(report["archive"]) / "before"
    for relative, digest in report["before_sha256"].items():
        assert ga.sha256_file(archive / relative) == digest
    assert not list(archive.rglob("*.png"))
    assert call(layout, apply=True) == report


def test_resume_uses_snapshot_after_interrupted_write(layout, monkeypatch):
    original = revision.atomic_bytes
    calls = 0

    def interrupted(path, data):
        nonlocal calls
        calls += 1
        if calls == 4:
            raise OSError("synthetic interruption")
        original(path, data)

    monkeypatch.setattr(revision, "atomic_bytes", interrupted)
    with pytest.raises(OSError, match="interruption"):
        call(layout, apply=True)
    monkeypatch.setattr(revision, "atomic_bytes", original)
    report = call(layout, apply=True)
    ga.assert_hashes(report["outputs_sha256"])
    assert report["status"] == "selection_revised_grand_average_pending"


def test_reject_wrong_product_tampered_source_and_completed_drift(layout):
    with pytest.raises(ValueError, match="No/pair/product"):
        call(layout, product="CCube")
    report = call(layout, apply=True)
    path = Path(next(iter(report["outputs_sha256"])))
    path.write_text("bad")
    with pytest.raises(ValueError, match="Protected"):
        call(layout, apply=True)


def test_scoped_tables_allow_only_target_selection_and_no_iaf_change():
    manifest = synthetic_manifest()
    estimates = synthetic_estimates(8, manifest)
    selection = synthetic_selection(manifest)
    before = ga.compute_tables(estimates, selection, 8)
    changed = selection.copy()
    target = changed.index[(changed.analysis_number == 8) & changed["product"].eq("VRohtoPremium")][
        0
    ]
    changed.loc[target, ga.ADOPTION] = "しない"
    changed.loc[target, "採否理由"] = "synthetic revision"
    after = ga.compute_tables(estimates, changed, 8)
    ga.validate_scoped_tables(before, after, ("VRohtoPremium",), ("SelectedParticipants",))
    with pytest.raises(AssertionError):
        ga.validate_scoped_tables(before, after, ("CCube",), ("SelectedParticipants",))
    corrupted = tuple(t.copy() for t in after)
    corrupted[0].loc[0, "iaf_change_hz"] += 0.1
    with pytest.raises(AssertionError):
        ga.validate_scoped_tables(before, corrupted, ("VRohtoPremium",), ("SelectedParticipants",))


def test_scoped_render_writes_only_requested_png(tmp_path, monkeypatch):
    import phase4_iaf_grand_average_figures as figures

    monkeypatch.setattr(ga, "BASE", tmp_path)
    monkeypatch.setattr(ga, "assert_output_path", lambda path: None)
    written = []

    def fake_plot(**kwargs):
        path = kwargs["output_path"]
        written.append(path)
        path.write_bytes(b"synthetic PNG")
        return {"synthetic": True}

    monkeypatch.setattr(figures, "plot_grand_average", fake_plot)
    manifest = synthetic_manifest()
    groups = ga.compute_tables(synthetic_estimates(8, manifest), synthetic_selection(manifest), 8)[
        1
    ]
    outputs = ga.render_groups(groups, 8, ("VRohtoPremium",), ("SelectedParticipants",))
    assert len(outputs) == len(written) == 1
    assert "VRohtoPremium_SelectedParticipants.png" in written[0].name
