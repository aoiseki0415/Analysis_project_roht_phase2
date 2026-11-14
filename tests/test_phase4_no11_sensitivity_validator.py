"""Synthetic coverage for the independent supplemental Pz audit."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import validate_phase4_no11_sensitivity_outputs as audit  # noqa: E402


def _items():
    items = []
    for person, pair in enumerate(("132-232", "Synthetic1", "Synthetic2", "Synthetic3")):
        spec = SimpleNamespace(pair_id=pair, product="CCube")
        sessions = []
        for condition in range(2):
            sets = {}
            for s in range(1, 7):
                if person == 3 and condition == 0 and s == 6:
                    continue
                values = np.full((s * 50 + 1, 32), 9999.0)
                values[:, audit.PZ] = (person + 1) * s + condition * (person + 0.5)
                sets[s] = values, np.linspace(0, 100, len(values))
            sessions.append(sets)
        items.append((spec, sessions))
    return items


def test_filters_pair_not_individual_condition_and_uses_pz():
    tables = audit.expected_tables(_items(), "CCube", change=False)
    values = tables["values"]
    assert set(values.PairID) == {"Synthetic1", "Synthetic2", "Synthetic3"}
    row = values[(values.PairID == "Synthetic1") & (values.Set == "1")].iloc[0]
    assert row.EyeDrop_PSD_uV2_per_Hz == 2
    assert row.Control_PSD_uV2_per_Hz == 3.5
    missing = values[(values.PairID == "Synthetic3") & (values.Set == "6")].iloc[0]
    assert np.isnan(missing.EyeDrop_PSD_uV2_per_Hz)
    assert np.isnan(missing.Control_PSD_uV2_per_Hz)
    assert tables["set_stats"].Paired_N.tolist() == [3, 3, 3, 3, 3, 2]
    assert tables["grand_csv"].EyeDrop_N.iloc[-1] == 2
    assert tables["grand_csv"].Control_N.iloc[-1] == 2


def test_all_sets_pools_windows_not_set_means():
    tables = audit.expected_tables(_items(), "CCube", change=False)
    row = tables["values"].query("PairID == 'Synthetic1' and Set == 'All Sets'").iloc[0]
    expected = np.average(np.arange(1, 7) * 2, weights=np.arange(1, 7) * 50 + 1)
    assert row.EyeDrop_PSD_uV2_per_Hz == pytest.approx(expected)
    assert row.EyeDrop_PSD_uV2_per_Hz != pytest.approx(np.mean(np.arange(1, 7) * 2))


def test_change_baseline_zero_five_corrections_and_first_set_in_pool():
    changed = []
    for spec, sessions in _items():
        converted = []
        for session in sessions:
            baseline = np.mean(session[1][0], axis=0)
            converted.append(
                {
                    s: ((values / baseline - 1) * 100, progress)
                    for s, (values, progress) in session.items()
                }
            )
        changed.append((spec, converted))
    tables = audit.expected_tables(changed, "CCube", change=True)
    values, stats = tables["values"], tables["set_stats"]
    assert values.loc[values.Set == "1", "EyeDrop_PSDChange_pct"].eq(0).all()
    assert stats.P_value_raw.notna().sum() == 5
    assert np.isnan(stats.iloc[0].P_value_FDR_BH)
    assert stats.iloc[0].N == 3
    row = values.query("PairID == 'Synthetic1' and Set == 'All Sets'").iloc[0]
    expected = np.average((np.arange(1, 7) - 1) * 100, weights=np.arange(1, 7) * 50 + 1)
    assert row.EyeDrop_PSDChange_pct == pytest.approx(expected)


def test_expected_names_additive_only_and_same_cohort_suffix():
    for stem in (audit.MAIN_STEM, audit.SUB_STEM):
        paths = audit.output_paths(Path(stem), "CCube")
        assert len(paths) == 7
        assert len([p for p in paths.values() if p.suffix == ".png"]) == 3
        assert all(audit.SUFFIX in p.name for p in paths.values())
        assert paths["set_png"].parent.name == audit.SUFFIX
        assert paths["grand_png"].parent.name == "GrandAverage"
        assert not any("Individual" in str(p) or "Topography" in str(p) for p in paths.values())


def test_independent_axes_use_mean_plus_sem_or_mean_only():
    absolute = pd.DataFrame(
        {
            "EyeDrop_Mean_PSD_uV2_per_Hz": [3.0, 4.0],
            "Control_Mean_PSD_uV2_per_Hz": [2.0, 3.0],
            "EyeDrop_SEM_PSD_uV2_per_Hz": [1.0, 2.0],
            "Control_SEM_PSD_uV2_per_Hz": [1.0, 1.0],
        }
    )
    limits, ticks = audit.grand_axis([absolute, absolute], False)
    assert limits == [0.0, 8.0]
    assert ticks.tolist() == [0.0, 2.0, 4.0, 6.0, 8.0]
    change = pd.DataFrame(
        {
            "EyeDrop_Mean_PSDChange_pct": [7.0, -3.0],
            "Control_Mean_PSDChange_pct": [2.0, -4.0],
            "EyeDrop_SEM_PSDChange_pct": [500.0, 500.0],
        }
    )
    limits, ticks = audit.grand_axis([change], True)
    assert limits == [-10.0, 10.0]
    assert 0 in ticks
    assert len(ticks) == 5


def test_quantification_recomputes_axis_from_remaining_values():
    values = pd.DataFrame(
        {
            "Set": ["1", "2", "All Sets"],
            "EyeDrop_PSD_uV2_per_Hz": [10.0, 20.0, 15.0],
            "Control_PSD_uV2_per_Hz": [5.0, 18.0, 12.0],
        }
    )
    assert audit.quant_axis(values, False, False) == pytest.approx([0.0, 27.4])
    assert audit.quant_axis(values, False, True) == pytest.approx([0.0, 20.55])
    values = values.rename(
        columns={
            "EyeDrop_PSD_uV2_per_Hz": "EyeDrop_PSDChange_pct",
            "Control_PSD_uV2_per_Hz": "Control_PSDChange_pct",
        }
    )
    values.loc[0, "EyeDrop_PSDChange_pct"] = -100
    assert audit.quant_axis(values, True, False) == pytest.approx([-100.0, 200.0])


def test_actual_artist_metadata_mismatch_is_detected(tmp_path):
    import hashlib

    path = tmp_path / "test.png"
    path.write_bytes(b"synthetic image")
    plot = {
        "path": str(path),
        "panel_count": 1,
        "axes": [{"ylim": [0, 8], "yticks": [0, 2, 4, 6, 8]}],
        "font_families": ["Arial"],
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    report = {"plot_metadata": []}
    audit.audit_plot_metadata(
        {"plots": [plot]}, {str(path): ([0, 8], 1, np.arange(0, 9, 2))}, report
    )
    assert report["plot_metadata"][0]["status"] == "passed"
    with pytest.raises(AssertionError):
        audit.audit_plot_metadata({"plots": [plot]}, {str(path): ([0, 10], 1, None)}, report)


def test_preservation_checks_all_primary_and_source_fingerprints(tmp_path):
    import hashlib

    png, cache = tmp_path / "primary.png", tmp_path / "source.h5"
    png.write_bytes(b"unchanged png")
    cache.write_bytes(b"unchanged cache")

    def fingerprint(path):
        stat = path.stat()
        return {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }

    execution = {
        "protected_before": {
            "primary_no11": {str(png): fingerprint(png)},
            "source_cache": {str(cache): fingerprint(cache)},
            "other_analyses": {},
        }
    }
    report = {}
    audit.audit_preservation(execution, {png}, {cache}, report)
    assert report["preservation"]["source_cache"]["status"] == "unchanged"
    with pytest.raises(ValueError, match="incomplete"):
        audit.audit_preservation(execution, {png, tmp_path / "missing.png"}, {cache}, report)
    png.write_bytes(b"modified png")
    with pytest.raises(ValueError, match="changed"):
        audit.audit_preservation(execution, {png}, {cache}, report)


def test_scope_guards_prevent_other_output_and_overwriting_execution_record():
    root = audit.source_engine.DEFAULT_OUTPUT_ROOT
    logs = root / "Phase4_脳波解析" / audit.MAIN_STEM / "Sub/logs"
    args = SimpleNamespace(
        output_root=root,
        cache_root=audit.source_engine.DEFAULT_CACHE_ROOT,
        report=logs / "SensitivityAudit.json",
        execution_report=logs / "SensitivityRun.json",
    )
    audit.validate_locations(args)
    args.report = args.execution_report
    with pytest.raises(ValueError, match="overwrite"):
        audit.validate_locations(args)
    args.report = root / "Phase4_脳波解析/No10_FzLowAlpha/Sub/logs/audit.json"
    with pytest.raises(ValueError, match="No11"):
        audit.validate_locations(args)


def test_cohort_selection_rejects_one_sided_or_wrong_product(tmp_path):
    path = tmp_path / "selection.csv"
    spec = SimpleNamespace(
        pair_id="140-240", product="CCube", drops_session_id="240", control_session_id="140"
    )
    frame = pd.DataFrame(
        [
            {
                "PairID": "140-240",
                "Product": "CCube",
                "EyeDropSessionID": "240",
                "ControlSessionID": "140",
                "PrimaryAnalysisEligible": True,
                "SpecifiedPairExcluded": True,
                "Included": False,
                "Reason": "user specified",
            }
        ]
    )
    frame.to_csv(path, index=False)
    report = {"tables": []}
    audit.audit_cohort_selection(path, [spec], False, report)
    frame.loc[0, "Included"] = True
    frame.to_csv(path, index=False)
    with pytest.raises(ValueError, match="Included"):
        audit.audit_cohort_selection(path, [spec], False, report)
