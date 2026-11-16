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
import validate_phase4_sub_specified_pairs as independent  # noqa: E402


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
        "no2": {"CCube": 5, "VRohtoPremium": 2},
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


@pytest.fixture
def previous_product_run(tmp_path):
    stem = runner.ANALYSES["no2"][0]
    selected = {p: [{"spec": participant(801 + index, p)}]
                for index, p in enumerate(runner.PRODUCTS)}
    excluded = {p: {f"{811 + index}-{911 + index}"}
                for index, p in enumerate(runner.PRODUCTS)}
    record = {"analysis_stem": stem, "protected_unchanged": True, "version": "old-version",
              "code_hashes": {"synthetic.py": "old-code-hash"},
              "completed_at": "2026-01-01T00:00:00+09:00",
              "implementation_base_commit": "old-commit", "output_files": [],
              "plots": [], "outputs": {}}
    for product in selected:
        paths = runner.output_paths(tmp_path, stem, product)
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("synthetic artifact")
            row = {"path": str(path), "sha256": runner.digest(path)}
            record["output_files"].append(row)
            if path.suffix == ".png":
                record["plots"].append(row)
        record["outputs"][product] = {
            "paths": {name: str(path) for name, path in paths.items()},
            "retained_pair_ids": [selected[product][0]["spec"].pair_id],
            "excluded_pair_ids": sorted(excluded[product]), "grand_y_limit": 80,
            "grand_y_ticks": [-80, -40, 0, 40, 80]}
    support = runner.support_paths(tmp_path, stem)
    runner.write_json(support["record"], record)
    support["selection"].parent.mkdir(parents=True, exist_ok=True)
    support["selection"].write_text("synthetic old selection")
    runner.write_json(runner.verification_path(tmp_path, stem), {"status": "passed"})
    return tmp_path, stem, selected, excluded, record


def test_scoped_plan_keeps_other_product_when_common_axis_unchanged(previous_product_run):
    root, stem, selected, excluded, previous = previous_product_run
    plan = runner.product_update_plan(
        root, stem, selected, excluded, "CCube", 80, np.array([-80, -40, 0, 40, 80]))
    assert plan["regenerated_products"] == ["CCube"]
    assert plan["axis_only_refreshed_products"] == []
    assert len(plan["preserved_product_artifacts"]) == 7
    assert len(plan["retained_plots"]) == 3
    assert plan["retained_outputs"] == {"VRohtoPremium": previous["outputs"]["VRohtoPremium"]}
    assert plan["preserved_product_provenance"]["VRohtoPremium"]["version"] == "old-version"


def test_scoped_plan_refreshes_only_other_ga_when_common_axis_changes(previous_product_run):
    root, stem, selected, excluded, _ = previous_product_run
    plan = runner.product_update_plan(
        root, stem, selected, excluded, "VRohtoPremium", 40, np.array([-40, -20, 0, 20, 40]))
    assert plan["regenerated_products"] == ["VRohtoPremium"]
    assert plan["axis_only_refreshed_products"] == ["CCube"]
    assert len(plan["preserved_product_artifacts"]) == 6
    assert len(plan["retained_plots"]) == 2
    ga = runner.output_paths(root, stem, "CCube")["grand_png"]
    assert str(ga) not in plan["preserved_product_artifacts"]


@pytest.mark.parametrize("case", ["cohort", "bytes", "paths", "metadata", "unknown"])
def test_scoped_plan_refuses_unverified_other_product(previous_product_run, case):
    root, stem, selected, excluded, prior = previous_product_run
    requested = "CCube"
    if case == "cohort":
        excluded["VRohtoPremium"].add("899-999")
    elif case == "bytes":
        runner.output_paths(root, stem, "VRohtoPremium")["values"].write_text("modified")
    elif case == "paths":
        prior["outputs"]["VRohtoPremium"]["paths"]["grand_png"] = "wrong"
    elif case == "metadata":
        prior["plots"] = []
    else:
        requested = "unavailable"
    runner.write_json(runner.support_paths(root, stem)["record"], prior)
    with pytest.raises(ValueError):
        runner.product_update_plan(root, stem, selected, excluded, requested, 80,
                                   np.array([-80, -40, 0, 40, 80]))


def test_revision_archive_keeps_only_replaced_nonpng_evidence(previous_product_run):
    root, stem, _, _, _ = previous_product_run
    before = runner.inventory(root)
    result = runner.archive_scoped_previous(root, stem, ["CCube"])
    manifest = json.loads(Path(result["manifest"]).read_text())
    assert len(manifest["files"]) == 7  # four numbers + selection + execution + verification
    assert all(Path(row["archived_to"]).suffix != ".png" for row in manifest["files"])
    assert all("VRohtoPremium" not in row["old"] for row in manifest["files"])
    assert all(runner.digest(Path(row["archived_to"])) == row["sha256"]
               for row in manifest["files"])
    assert all(runner.digest(Path(path)) == row["sha256"] for path, row in before.items())
    again = runner.archive_scoped_previous(root, stem, ["CCube"])
    assert again["reused"]
    assert again["sha256"] == result["sha256"]


def test_revision_archive_rejects_conflicting_history(previous_product_run):
    root, stem, _, _, _ = previous_product_run
    result = runner.archive_scoped_previous(root, stem, ["CCube"])
    manifest = json.loads(Path(result["manifest"]).read_text())
    Path(manifest["files"][0]["archived_to"]).write_text("history modified")
    with pytest.raises(ValueError, match="hash/scope"):
        runner.archive_scoped_previous(root, stem, ["CCube"])


@pytest.fixture
def scoped_record(previous_product_run):
    root, stem, selected, excluded, _ = previous_product_run
    plan = runner.product_update_plan(root, stem, selected, excluded, "CCube", 80,
                                      np.array([-80, -40, 0, 40, 80]))
    archive = runner.archive_scoped_previous(root, stem, ["CCube"])
    support = runner.support_paths(root, stem)
    allowed = set(support.values()) | set(runner.output_paths(root, stem, "CCube").values())
    record = {**plan, "requested_product": "CCube", "shared_axis_products": list(selected),
              "strict_run_scope_unchanged": True,
              "allowed_write_paths": [str(path) for path in allowed],
              "generated_output_files": [{"path": str(path), "sha256": runner.digest(path)}
                                         for path in allowed if path != support["record"]],
              "previous_nonpng_archive": archive}
    return root / "Phase4_脳波解析" / stem, record


def test_independent_scoped_audit_accepts_exact_contract(scoped_record):
    root, record = scoped_record
    hashes = {}
    independent.audit_scoped_record(root, record, set(runner.PRODUCTS), hashes)
    assert len(hashes) == 7


@pytest.mark.parametrize("case", ["unexpected_write", "changed_preserved", "lost_provenance",
                                  "lost_scope_check", "archive_changed"])
def test_independent_scoped_audit_rejects_scope_or_provenance_failures(scoped_record, case):
    root, record = scoped_record
    if case == "unexpected_write":
        record["allowed_write_paths"].append(str(root / "Individual/unexpected.png"))
    elif case == "changed_preserved":
        Path(next(iter(record["preserved_product_artifacts"]))).write_text("changed")
    elif case == "lost_provenance":
        record["preserved_product_provenance"] = {}
    elif case == "lost_scope_check":
        record["strict_run_scope_unchanged"] = False
    else:
        Path(record["previous_nonpng_archive"]["manifest"]).write_text("modified")
    with pytest.raises(ValueError):
        independent.audit_scoped_record(root, record, set(runner.PRODUCTS), {})


@pytest.mark.parametrize("key,target,axis_change", [
    ("no2", "CCube", False), ("no2-pz", "VRohtoPremium", True)])
def test_scoped_execution_preserves_other_results_and_refreshes_shared_axis(
    tmp_path, monkeypatch, key, target, axis_change
):
    """Exercise the actual writer only with synthetic cohorts and a fake engine."""
    import matplotlib.pyplot as plt

    stem = runner.ANALYSES[key][0]
    other = next(p for p in runner.PRODUCTS if p != target)
    specs = [participant(801 + i, p) for i, p in enumerate([target] * 3 + [other] * 3)]
    for spec, number in zip(specs, [0, 10, 30, 0, 5, 5], strict=True):
        spec.value = number
    if not axis_change:
        specs[-2].value = specs[-1].value = 50
    items = [{"spec": spec, "product_dir": spec.product} for spec in specs]
    excluded = {target: {specs[0].pair_id}, other: {specs[3].pair_id}}

    def grand(cohort, product):
        mean = np.mean([item["spec"].value for item in cohort])
        return pd.DataFrame({"EyeDrop_Mean_PSDChange_pct": [mean],
                             "Control_Mean_PSDChange_pct": [mean / 2],
                             "EyeDrop_SEM_PSDChange_pct": [1],
                             "Control_SEM_PSDChange_pct": [1]}), {}

    def axis(frames):
        limit = 2 * max(frame.EyeDrop_Mean_PSDChange_pct.max() for frame in frames)
        return limit, np.array([-limit, 0, limit])

    def quantification(cohort, product):
        return pd.DataFrame([{"Set": number, "PairID": item["spec"].pair_id,
                              "EyeDrop_PSDChange_pct": item["spec"].value,
                              "Control_PSDChange_pct": item["spec"].value / 2}
                             for item in cohort for number in [1, 2, 3, 4, 5, 6, "All Sets"]])

    def draw(path, limit=100):
        with plt.rc_context({"font.family": "Arial"}):
            figure, axes = plt.subplots(figsize=(3, 2))
            axes.plot([0, 1], [0, 1])
            axes.set_ylim(-limit, limit)
            figure.savefig(path)
            plt.close(figure)

    engine = SimpleNamespace(
        DEFAULT_OUTPUT_ROOT=tmp_path, ANALYSIS_STEM=stem, DEFAULT_CACHE_ROOT=tmp_path,
        FOCUS_CHANNEL=runner.ANALYSES[key][3],
        no1=SimpleNamespace(load_manifest=lambda _: specs, normalize_product=lambda x: (x,),
                            INCLUDED_FREQUENCIES_HZ=np.arange(8, 16)),
        preflight=lambda *_: (items, {}), build_grand_average=grand, grand_average_axis=axis,
        build_quantification=quantification,
        quantification_statistics=lambda _: (pd.DataFrame({"p": [.5]}), pd.DataFrame({"p": [.5]})),
        plot_grand_average=lambda frame, p, path, **kw: draw(path, kw["common_limit"]),
        plot_quantification=lambda frame, stats, p, path: draw(path),
        plot_overall_quantification=lambda frame, stats, p, path: draw(path),
    )
    monkeypatch.setattr(runner, "build_engine", lambda _: engine)
    monkeypatch.setattr(runner, "cache_provenance", lambda *_: [])
    monkeypatch.setattr(runner, "documented_exclusions", lambda: {key: excluded})
    manifest = tmp_path / "manifest.csv"
    manifest.write_text("synthetic only")
    initial = runner.execute_analysis(key, manifest, {}, excluded,
                                      preflight_only=False, replace=False)
    runner.write_json(runner.verification_path(tmp_path, stem), {"status": "passed"})
    old_other = {name: runner.digest(path)
                 for name, path in runner.output_paths(tmp_path, stem, other).items()}
    excluded[target].add(specs[2].pair_id)
    before_preflight = runner.inventory(tmp_path)
    preflight = runner.execute_analysis(key, manifest, {}, excluded, preflight_only=True,
                                       replace=True, product=target)
    assert runner.inventory(tmp_path) == before_preflight  # no preflight archive/write
    assert preflight["regenerated_products"] == [target]
    assert preflight["axis_only_refreshed_products"] == ([other] if axis_change else [])
    result = runner.execute_analysis(key, manifest, {}, excluded, preflight_only=False,
                                    replace=True, product=target)
    assert result["requested_product"] == target
    assert result["regenerated_products"] == [target]
    assert result["strict_run_scope_unchanged"]
    assert result["previous_nonpng_archive"]["file_count"] == 7
    assert len(result["plots"]) == 6
    for name, path in runner.output_paths(tmp_path, stem, other).items():
        if axis_change and name == "grand_png":
            assert runner.digest(path) != old_other[name]
        else:
            assert runner.digest(path) == old_other[name]
    assert result["outputs"][other]["retained_pair_ids"] == initial["outputs"][other][
        "retained_pair_ids"]
    independent.audit_scoped_record(tmp_path / "Phase4_脳波解析" / stem, result,
                                    set(runner.PRODUCTS), {})
