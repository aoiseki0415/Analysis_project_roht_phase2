"""Unit checks for the independent sub sensitivity read-back auditor."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PATH = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム/Phase4_脳波解析/validate_phase4_sub_specified_pairs.py"
)
SPEC = importlib.util.spec_from_file_location("independent_sub_audit", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def segment(values):
    values = np.asarray(values, float)
    return values, np.linspace(0, 100, len(values))


def test_percent_change_has_own_session_baseline():
    result = audit.make_change({1: segment([1, 3, np.nan]), 2: segment([4, 6])})
    np.testing.assert_allclose(result[1][0], [-50, 50, np.nan], equal_nan=True)
    np.testing.assert_allclose(result[2][0], [100, 200])


def test_smoothing_matches_centered_nanmean_then_interpolates_without_gap_bridge():
    values = np.arange(500, dtype=float)
    values[80:200] = np.nan
    progress = np.linspace(0, 100, len(values))
    smooth = pd.Series(values).rolling(60, center=True, min_periods=1).mean().to_numpy()
    target, expected = np.arange(100), np.full(100, np.nan)
    valid = np.flatnonzero(np.isfinite(smooth))
    runs = np.split(valid, np.flatnonzero(np.diff(valid) > 1) + 1)
    for run in runs:
        inside = (target >= progress[run[0]]) & (target <= progress[run[-1]])
        expected[inside] = np.interp(target[inside], progress[run], smooth[run])
    np.testing.assert_allclose(audit.smooth_interpolate(values, progress), expected, equal_nan=True)
    assert np.isnan(expected[25])


def test_paired_statistics_use_paired_complete_rows_and_two_sides():
    eye, control = np.array([2, 3, 4, np.nan, 6]), np.array([1, 3, 2, 4, np.nan])
    result = audit.paired_test(eye, control)
    expected = stats.ttest_rel(eye[:3], control[:3])
    assert result["Paired_N"] == 3
    np.testing.assert_allclose(result["T_statistic"], expected.statistic)
    np.testing.assert_allclose(result["P_value_raw"], expected.pvalue)


def test_allsets_weights_finite_windows_and_pairs_missing_sets():
    # Synthetic full set maps avoid all-NaN statistic warnings elsewhere.
    sessions = [{i: segment([0, 0]) for i in range(1, 7)} for _ in range(2)]
    sessions[0][2], sessions[1][2] = segment([100] * 6), segment([50] * 6)
    sessions[0][3] = segment([900] * 2)
    del sessions[1][3]
    tables = audit.expected_tables([("synthetic-a", sessions), ("synthetic-b", sessions)])
    values = tables["values"].set_index(["PairID", "Set"])
    assert np.isnan(values.loc[("synthetic-a", "3"), "EyeDrop_PSDChange_pct"])
    assert values.loc[("synthetic-a", "All Sets"), "EyeDrop_PSDChange_pct"] == 600 / 14
    assert tables["set_stats"].iloc[0]["N"] == 2
    assert np.isnan(tables["set_stats"].iloc[0]["P_value_raw"])


def test_documented_selection_counts_are_independent_per_analysis():
    result = audit.canonical_exclusions(audit.REPO / "docs/解析上の注意事項.md")
    assert {name: {p: len(v) for p, v in groups.items()} for name, groups in result.items()} == {
        "No1_sub": {"CCube": 0, "VRohtoPremium": 1},
        "No2_sub": {"CCube": 5, "VRohtoPremium": 2},
        "No2-2_sub": {"CCube": 3, "VRohtoPremium": 2},
        "No3_sub": {"CCube": 0, "VRohtoPremium": 1},
    }
