"""Synthetic tests: no participant-identifying production data."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

SCRIPT_DIR = Path(__file__).parents[1] / "解析プログラム/Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))
import phase4_iaf_grand_average as ga  # noqa: E402


def synthetic_manifest(count=40):
    return {
        f"{10001 + i}-{20001 + i}": {
            "first_session_id": str(10001 + i),
            "second_session_id": str(20001 + i),
            "drops_session_id": str(10001 + i if i % 2 else 20001 + i),
            "product": ga.PRODUCTS[i // 20] if count == 40 else ga.PRODUCTS[i % 2],
            "Eye Drop": str(10001 + i if i % 2 else 20001 + i),
            "Control": str(20001 + i if i % 2 else 10001 + i),
        }
        for i in range(count)
    }


def synthetic_estimates(number, manifest):
    rows = []
    for index, (pair, person) in enumerate(manifest.items()):
        for ci, condition in enumerate(ga.CONDITIONS):
            for position, label in enumerate(ga.interval_labels(number), 1):
                rows.append(
                    {
                        "pair_id": pair,
                        "session_id": person[condition],
                        "condition": condition,
                        "product": person["product"],
                        "analysis_number": number,
                        "channel": ga.ANALYSES[number][0],
                        "set_number": int(label[0]),
                        "interval": "whole",
                        "position": position,
                        "frequency_hz": 9 + ci + index / 10 + (position - 1) / 10,
                        "quality": "ok",
                        "peak_input_dataset": "smoothed_mean_psd_uv2_hz",
                        "smoothing_points": 5,
                        "smoothing_passes": 1,
                    }
                )
    return pd.DataFrame(rows)


def synthetic_selection(manifest):
    return pd.DataFrame(
        [
            {
                "analysis_number": number,
                "channel": ga.ANALYSES[number][0],
                "product": person["product"],
                "pair_id": pair,
                ga.ADOPTION: "する",
                "採否確定状態": "確定",
                "利用者指定追加除外": "なし",
                "採否理由": "synthetic",
            }
            for number in ga.ANALYSES
            for pair, person in manifest.items()
        ]
    )


def set_missing(frame, pair, condition, position):
    mask = (frame.pair_id == pair) & (frame.condition == condition) & (frame.position == position)
    frame.loc[mask, "frequency_hz"] = np.nan
    frame.loc[mask, "quality"] = "all_windows_invalid"


@pytest.mark.parametrize("number", [8, 9])
def test_own_condition_baselines_and_exact_zero(number):
    manifest = synthetic_manifest(2)
    estimates = synthetic_estimates(number, manifest)
    validated = ga.validate_estimates(estimates, number, manifest)
    participants, groups, inclusion = ga.compute_tables(
        validated, synthetic_selection(manifest), number
    )
    expected = (participants.position - 1) / 10
    np.testing.assert_allclose(participants.iaf_change_hz, expected, atol=2e-15)
    assert participants.loc[participants.position == 1, "iaf_change_hz"].eq(0).all()
    assert inclusion.included.all()
    assert groups.n.eq(1).all()
    assert groups.sem_iaf_change_hz.isna().all()
    assert groups.sd_iaf_change_hz.isna().all()
    assert set(groups.baseline_interval) == {"1"}


@pytest.mark.parametrize("number", [8, 9])
def test_paired_baseline_missing_excludes_whole_pair_only_for_this_no(number):
    manifest = synthetic_manifest(2)
    estimates = synthetic_estimates(number, manifest)
    pair = next(iter(manifest))
    set_missing(estimates, pair, "Control", 1)
    _, groups, inclusion = ga.compute_tables(estimates, synthetic_selection(manifest), number)
    excluded = inclusion.loc[inclusion.pair_id == pair]
    assert not excluded.included.any()
    assert excluded.exclusion_reason.str.contains("paired_baseline_missing").all()
    assert groups.loc[groups["product"] == manifest[pair]["product"], "n"].eq(0).all()
    assert inclusion.loc[inclusion.pair_id != pair, "included"].all()


@pytest.mark.parametrize("number", [8, 9])
def test_later_missing_pairs_only_that_interval_without_collapsing_grid(number):
    manifest = synthetic_manifest(2)
    estimates = synthetic_estimates(number, manifest)
    pair = next(iter(manifest))
    set_missing(estimates, pair, "Eye Drop", 3)
    participants, groups, inclusion = ga.compute_tables(
        estimates, synthetic_selection(manifest), number
    )
    pp = participants.loc[participants.pair_id == pair]
    assert not pp.loc[pp.position == 3, "included_all_available"].any()
    assert pp.loc[pp.position != 3, "included_all_available"].all()
    assert np.isfinite(
        pp.loc[(pp.position == 3) & (pp.condition == "Control"), "iaf_change_hz"]
    ).all()
    assert (
        groups.loc[(groups["product"] == manifest[pair]["product"]) & (groups.position == 3), "n"]
        .eq(0)
        .all()
    )
    assert len(inclusion) == 2 * 2 * len(ga.interval_labels(number))


def test_selected_mask_does_not_change_all_available_or_original():
    manifest = synthetic_manifest(2)
    estimates = synthetic_estimates(8, manifest)
    original = estimates.copy(deep=True)
    selection = synthetic_selection(manifest)
    pair = next(iter(manifest))
    selection.loc[(selection.analysis_number == 8) & (selection.pair_id == pair), ga.ADOPTION] = (
        "しない"
    )
    participants, groups, inclusion = ga.compute_tables(estimates, selection, 8)
    assert participants.included_all_available.all()
    assert not participants.loc[
        participants.pair_id == pair, "included_selected_participants"
    ].any()
    assert (
        inclusion.loc[
            (inclusion.pair_id == pair) & (inclusion.cohort == "SelectedParticipants"),
            "exclusion_reason",
        ]
        .eq("not_in_final_selected_cohort")
        .all()
    )
    assert groups.loc[groups.cohort == "AllAvailable", "n"].eq(1).all()
    pd.testing.assert_frame_equal(original, estimates)


def test_mean_sample_sd_and_sem_equal_participant_weight():
    manifest = synthetic_manifest(4)
    estimates = synthetic_estimates(8, manifest)
    pairs = [p for p in manifest if manifest[p]["product"] == "CCube"]
    for pair, change in zip(pairs, (1.0, 3.0), strict=True):
        for condition in ga.CONDITIONS:
            baseline = estimates.loc[
                (estimates.pair_id == pair)
                & (estimates.condition == condition)
                & (estimates.position == 1),
                "frequency_hz",
            ].iloc[0]
            estimates.loc[
                (estimates.pair_id == pair)
                & (estimates.condition == condition)
                & (estimates.position == 2),
                "frequency_hz",
            ] = baseline + change
    _, groups, _ = ga.compute_tables(estimates, synthetic_selection(manifest), 8)
    row = groups.loc[(groups["product"] == "CCube") & (groups.position == 2)].iloc[0]
    assert row.n == 2
    assert row.mean_iaf_change_hz == 2
    assert row.sd_iaf_change_hz == pytest.approx(np.sqrt(2))
    assert row.sem_iaf_change_hz == pytest.approx(1)


@pytest.mark.parametrize(
    "alteration",
    [
        "duplicate",
        "swap_condition",
        "product",
        "range",
        "infinite",
        "offgrid",
        "quality",
        "smoothing",
        "interval",
        "analysis",
    ],
)
def test_saved_estimate_rejects_corruption(alteration):
    manifest = synthetic_manifest(2)
    frame = synthetic_estimates(9, manifest)
    if alteration == "duplicate":
        frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    elif alteration == "swap_condition":
        frame.loc[0, "session_id"] = frame.loc[12, "session_id"]
    elif alteration == "product":
        frame.loc[0, "product"] = "VRohtoPremium"
    elif alteration == "range":
        frame.loc[0, "frequency_hz"] = 7.9
    elif alteration == "infinite":
        frame.loc[0, "frequency_hz"] = np.inf
    elif alteration == "offgrid":
        frame.loc[0, "frequency_hz"] = 10.05
    elif alteration == "quality":
        frame.loc[0, "quality"] = "missing_set"
    elif alteration == "smoothing":
        frame.loc[0, "smoothing_passes"] = 2
    elif alteration == "interval":
        frame.loc[0, "interval"] = "b"
    else:
        frame.loc[0, "analysis_number"] = 11
    with pytest.raises(ValueError):
        ga.validate_estimates(frame, 9, manifest)


@pytest.fixture
def frozen_selection(tmp_path):
    manifest = synthetic_manifest()
    frame = synthetic_selection(manifest)
    for number in ga.ANALYSES:
        for product in ga.PRODUCTS:
            mask = (frame.analysis_number == number) & (frame["product"] == product)
            selected_indices = frame.loc[mask].index[ga.SELECTED_COUNTS[number][product] :]
            frame.loc[selected_indices, ga.ADOPTION] = "しない"
    frame = frame.astype(str)
    json_path, csv_path = tmp_path / "selection.json", tmp_path / "selection.csv"
    record = {
        "schema": ga.SELECTION_SCHEMA,
        "active_analyses": ga.ACTIVE_SELECTION_ANALYSES,
        "status": "final",
        "decisions": frame.to_dict("records"),
        "manual_exclusions": {str(n): dict.fromkeys(ga.PRODUCTS, []) for n in ga.ANALYSES},
    }
    json_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return manifest, json_path, csv_path


def test_frozen_json_csv_match_counts(frozen_selection):
    manifest, json_path, csv_path = frozen_selection
    selection = ga.load_selection(json_path, csv_path, manifest)
    assert len(selection) == 80
    assert selection[ga.ADOPTION].eq("する").sum() == 44


@pytest.mark.parametrize("alteration", ["notfinal", "duplicate", "mismatch", "manual", "counts"])
def test_selection_rejects_corrupt_or_unfinalized(frozen_selection, alteration):
    manifest, json_path, csv_path = frozen_selection
    record = json.loads(json_path.read_text())
    if alteration == "notfinal":
        record["status"] = "draft"
    elif alteration == "duplicate":
        record["decisions"].append(record["decisions"][0])
    elif alteration == "mismatch":
        record["decisions"][0]["採否理由"] = "changed"
    elif alteration == "manual":
        record["manual_exclusions"]["8"]["CCube"] = [next(iter(manifest))]
    else:
        record["decisions"][0][ga.ADOPTION] = "しない"
        pd.DataFrame(record["decisions"]).to_csv(csv_path, index=False)
    json_path.write_text(json.dumps(record, ensure_ascii=False))
    with pytest.raises((ValueError, AssertionError)):
        ga.load_selection(json_path, csv_path, manifest)


def test_manifest_complete_and_conditional_mapping(tmp_path):
    manifest = synthetic_manifest()
    path = tmp_path / "manifest.csv"
    pd.DataFrame(
        [{k: v for k, v in p.items() if k not in ga.CONDITIONS} for p in manifest.values()]
    ).to_csv(path, index=False)
    assert ga.read_manifest(path) == manifest
    frame = pd.read_csv(path, dtype=str)
    frame.loc[1, "second_session_id"] = frame.loc[0, "second_session_id"]
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError):
        ga.read_manifest(path)


def test_output_boundary_rejects_escape_and_symlink(tmp_path):
    root = tmp_path / "base"
    allowed = root / ga.ANALYSES[8][2]
    allowed.mkdir(parents=True)
    ga.assert_output_path(allowed / "CCube/GrandAverage/test.png", root)
    with pytest.raises(ValueError):
        ga.assert_output_path(root / "No1/figure.png", root)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (allowed / "link").symlink_to(elsewhere, target_is_directory=True)
    with pytest.raises(ValueError):
        ga.assert_output_path(allowed / "link/figure.png", root)


def test_protected_input_hash_detects_changes(tmp_path):
    path = tmp_path / "protected.csv"
    path.write_text("synthetic")
    fingerprints = {str(path): ga.sha256_file(path)}
    ga.assert_hashes(fingerprints)
    path.write_text("modified")
    with pytest.raises(ValueError, match="Protected input changed"):
        ga.assert_hashes(fingerprints)


@pytest.mark.parametrize("number", [8, 9])
def test_table_roundtrip_preserves_labels_missingness_and_numerical_values(
    tmp_path, monkeypatch, number
):
    manifest = synthetic_manifest(4)
    estimates = synthetic_estimates(number, manifest)
    set_missing(estimates, next(iter(manifest)), "Control", 3)
    tables = ga.compute_tables(estimates, synthetic_selection(manifest), number)
    monkeypatch.setattr(ga, "assert_output_path", lambda path: None)
    for name, frame in zip(ga.TABLE_NAMES, tables, strict=True):
        ga.write_table(tmp_path / "Sub/tables/GrandAverage" / name, frame)
    hashes = ga._verify_saved_tables(tmp_path, tables)
    assert len(hashes) == 3
    ga.assert_hashes(hashes)


def test_read_cache_uses_stored_attributes_and_never_peak_reestimation(tmp_path, monkeypatch):
    import phase4_iaf

    def forbidden(*args, **kwargs):
        raise AssertionError("Numerical re-estimation is forbidden")

    monkeypatch.setattr(phase4_iaf, "select_peak", forbidden)
    monkeypatch.setattr(phase4_iaf, "compute_periodograms", forbidden)
    monkeypatch.setattr(phase4_iaf, "smooth_mean_psd", forbidden)
    manifest = synthetic_manifest(2)
    paths = []
    for pair, person in manifest.items():
        for condition in ga.CONDITIONS:
            path = tmp_path / f"synthetic_{person[condition]}.h5"
            with h5py.File(path, "w") as handle:
                handle.attrs.update(
                    {
                        "schema": ga.SCHEMA,
                        "calc_config_sha256": ga.config_hash(),
                        "complete": True,
                        "pair_id": pair,
                        "session_id": person[condition],
                        "condition": condition,
                        "product": person["product"],
                        **{
                            k: person[k]
                            for k in ("first_session_id", "second_session_id", "drops_session_id")
                        },
                    }
                )
                for set_number in range(1, 7):
                    for interval in ("whole", "a", "b"):
                        for channel in ("Pz", "Fz"):
                            peak = handle.create_group(
                                f"Set{set_number}/{interval}/peaks/{channel}"
                            )
                            peak.attrs.update(frequency_hz=10.3, quality="ok")
            paths.append(path)
    before = {str(p): ga.sha256_file(p) for p in paths}
    rows = ga.read_stored_cache_iaf(paths, manifest)
    assert len(rows[8]) == 24 and len(rows[9]) == 24
    assert rows[9].frequency_hz.eq(10.3).all()
    ga.assert_hashes(before)
    with h5py.File(paths[0], "r+") as handle:
        handle.attrs["schema"] = "obsolete"
    with pytest.raises(ValueError, match="schema"):
        ga.read_stored_cache_iaf(paths, manifest)


@pytest.mark.parametrize("field", ["schema", "active_analyses", "manual_exclusions"])
def test_selection_rejects_legacy_numbering(frozen_selection, field):
    manifest, json_path, csv_path = frozen_selection
    record = json.loads(json_path.read_text())
    if field == "schema":
        record[field] = "old-v1"
    elif field == "active_analyses":
        record[field] = {"8": "Pz", "9": "Pz", "10": "Fz", "11": "Fz"}
    else:
        record[field]["10"] = dict.fromkeys(ga.PRODUCTS, [])
    json_path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Selection schema/active"):
        ga.load_selection(json_path, csv_path, manifest)
