"""Synthetic current-cohort tests; source engines are isolated from wrapper globals."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "解析プログラム/Phase4_脳波解析"
sys.path.insert(0, str(SCRIPTS))

import run_phase4_sub123_sensitivity as runner  # noqa: E402


def test_isolated_variants_preserve_band_channel_hash_configuration_and_colors():
    engines = {key: runner.build_engine(key) for key in runner.ANALYSES}
    expected = {
        "no1": ("Fz", [4, 5, 6, 7]), "no2": ("Oz", list(range(8, 16))),
        "no2-pz": ("Pz", list(range(8, 16))), "no3": ("Fz", [1, 2, 3]),
    }
    for key, (channel, frequencies) in expected.items():
        engine = engines[key]
        assert engine.FOCUS_CHANNEL == channel
        assert engine.no1.INCLUDED_FREQUENCIES_HZ.tolist() == frequencies
        assert engine.INCLUDE_TOPOGRAPHY is False
        assert engine.ALTERNATE_GROUP_EXCLUSIONS == {}
        assert engine.SMOOTHING_SECONDS == 60
        assert engine.SIGNIFICANCE_STAR_FACTOR_OVERRIDE == 1.08
        assert engine.SIGNIFICANCE_STAR_FONTSIZE_OVERRIDE == 42
    assert engines["no2-pz"].no1.FOCUS_CHANNEL == "Oz"  # cache source remains Oz
    assert engines["no2-pz"].DEFAULT_CACHE_ROOT == engines["no2"].DEFAULT_CACHE_ROOT
    assert engines["no1"].no1.normalize_product("CCube")[2] == "#A94F2D"
    assert engines["no2"].no1.normalize_product("CCube")[2] == "#C23B8A"
    assert engines["no3"].no1.normalize_product("CCube")[2] == "#8F7300"


def test_current_document_selection_counts_without_embedding_participant_ids():
    actual = runner.documented_exclusions()
    assert {key: {p: len(v) for p, v in groups.items()} for key, groups in actual.items()} == {
        "no1": {"CCube": 0, "VRohtoPremium": 1},
        "no2": {"CCube": 4, "VRohtoPremium": 2},
        "no2-pz": {"CCube": 3, "VRohtoPremium": 2},
        "no3": {"CCube": 0, "VRohtoPremium": 1},
    }


def test_document_parser_rejects_missing_current_heading(tmp_path):
    path = tmp_path / "attention.md"
    path.write_text("old table only")
    with pytest.raises(ValueError, match="current exclusion"):
        runner.documented_exclusions(path)


def participant(first, product):
    return SimpleNamespace(pair_id=f"{first}-{first + 100}", product=product,
                           drops_session_id=str(first), control_session_id=str(first + 100))


@pytest.fixture
def cohort():
    specs = [participant(number, product) for number, product in (
        (801, "VRohtoPremium"), (802, "VRohtoPremium"),
        (803, "CCube"), (804, "VRohtoPremium"),
    )]
    items = [{"spec": spec, "product_dir": spec.product} for spec in specs[:-1]]
    exclusions = {"CCube": set(), "VRohtoPremium": {specs[0].pair_id}}
    return specs, items, exclusions


def test_selection_pairs_baseline_and_unchanged_product_are_distinct(cohort):
    specs, items, exclusions = cohort
    selected, audit = runner.select_items(items, specs, exclusions)
    assert list(selected) == ["VRohtoPremium"]
    assert selected["VRohtoPremium"] == [items[1]]
    assert len(items) == 3
    assert audit["SpecifiedPairExcluded"].sum() == 1
    assert audit["Included"].sum() == 1
    baseline = audit.loc[audit["PairID"] == specs[-1].pair_id].iloc[0]
    assert not baseline["PrimaryAnalysisEligible"]
    assert not baseline["SpecifiedPairExcluded"]
    assert baseline["AdditionalProductRequested"]


def test_selection_rejects_duplicate_unknown_and_wrong_product(cohort):
    specs, items, exclusions = cohort
    with pytest.raises(ValueError, match="Duplicate"):
        runner.select_items([*items, items[0]], specs, exclusions)
    with pytest.raises(ValueError, match="absent or product"):
        runner.select_items(items[1:], specs, exclusions)
    altered = [{**items[0], "product_dir": "CCube"}, *items[1:]]
    with pytest.raises(ValueError, match="product mismatch"):
        runner.select_items(altered, specs, exclusions)


def test_output_contract_has_three_additional_figures_no_topography(tmp_path):
    for stem, *_ in runner.ANALYSES.values():
        paths = runner.output_paths(tmp_path, stem, "VRohtoPremium")
        assert len(paths) == 7
        assert len([p for p in paths.values() if p.suffix == ".png"]) == 3
        assert paths["set_png"].parent.name == runner.SUFFIX
        assert paths["all_png"].parent.name == runner.SUFFIX
        assert all("Individual" not in str(p) and "Topography" not in str(p)
                   for p in paths.values())


def test_axis_is_based_only_on_generated_remaining_products():
    engine = runner.build_engine("no1")
    frame = pd.DataFrame({"EyeDrop_Mean_PSDChange_pct": [1., 8.],
                          "Control_Mean_PSDChange_pct": [1., 6.]})
    limit, _ = engine.grand_average_axis([frame])
    assert limit >= 8 / .70
    assert limit < 20


def test_allsets_keeps_baseline_and_window_weighting_with_paired_missing():
    engine = runner.build_engine("no1")

    def session(sid, scales):
        sets = {number: SimpleNamespace(psd_band_mean=np.full((n, 32), scale))
                for number, (n, scale) in scales.items()}
        source = SimpleNamespace(session_id=sid, channel_names=engine.no1.EXPECTED_CHANNEL_NAMES,
                                 sets=sets)
        return engine.make_change_session(source)

    item = {"spec": SimpleNamespace(pair_id="801-901"), "product_dir": "VRohtoPremium",
            "eye_drop": session("801", {1: (2, 1.), 2: (6, 3.), 3: (4, 100.)}),
            "control": session("901", {1: (2, 2.), 2: (6, 4.)})}
    values = engine.build_quantification([item], "VRohtoPremium")
    allsets = values.loc[values["Set"] == "All Sets"].iloc[0]
    assert allsets["EyeDrop_PSDChange_pct"] == 150.
    assert allsets["Control_PSDChange_pct"] == 75.
    assert values.loc[values["Set"] == 3, "EyeDrop_PSDChange_pct"].isna().all()


@pytest.fixture
def audit_file(tmp_path):
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("synthetic")
    exclusions = {key: {"CCube": set(), "VRohtoPremium": {"801-901"}}
                  for key in runner.ANALYSES}
    audit = {"matched_pairs": 40, "matched_sessions": 80, "mismatches": 0,
             "checked_at": datetime.now(runner.TOKYO).isoformat(),
             "manifest_sha256": runner.digest(manifest),
             "explicit_exclusions": {runner.ANALYSES[key][0]: {p: sorted(v) for p, v in g.items()}
                                     for key, g in exclusions.items()}}
    path = tmp_path / "audit.json"
    path.write_text(json.dumps(audit))
    return path, manifest, exclusions, audit


def test_audit_accepts_current_exact_mapping(audit_file):
    path, manifest, exclusions, audit = audit_file
    assert runner.verify_source_audit(path, manifest, exclusions) == audit


@pytest.mark.parametrize("case", ["old", "hash", "cohort", "mismatch"])
def test_audit_rejects_stale_or_different_inputs(audit_file, case):
    path, manifest, exclusions, audit = audit_file
    if case == "old":
        audit["checked_at"] = (datetime.now(runner.TOKYO) - timedelta(days=1)).isoformat()
    elif case == "hash":
        audit["manifest_sha256"] = "changed"
    elif case == "cohort":
        audit["explicit_exclusions"] = {}
    else:
        audit["mismatches"] = 1
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError):
        runner.verify_source_audit(path, manifest, exclusions)


def test_legacy_discovery_cannot_target_other_analysis_or_main(tmp_path):
    stem = runner.ANALYSES["no2"][0]
    root = tmp_path / "Phase4_脳波解析" / stem
    folder = root / "VRohtoPremium/GrandAverage"
    folder.mkdir(parents=True)
    old = folder / f"{stem}_GrandAverage_VRohtoPremium_ExcludePair801-901.png"
    old.write_text("legacy")
    main = folder / f"{stem}_GrandAverage_VRohtoPremium.png"
    main.write_text("main")
    assert runner.legacy_paths("no2", tmp_path) == [old]
    assert runner.legacy_paths("no1", tmp_path) == []
