import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム"
    / "Phase5_相関・その他"
    / "Phase5_No1_DEQS_RT_EyeDropEffect.py"
)
SPEC = importlib.util.spec_from_file_location("phase5_no1", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_deqs_formula_uses_valid_count(tmp_path):
    path = tmp_path / "deqs.csv"
    pd.DataFrame(
        [{"ParticipantID": 101, "DegreeScoreSum": 30, "ValidItemCount": 15}]
    ).to_csv(path, index=False)
    spec = SimpleNamespace(
        first_session_id="101",
        second_session_id="201",
        drops_session_id="101",
        control_session_id="201",
        pair_id="101-201",
        product="VRohtoPremium",
    )
    result = MODULE.load_deqs_scores(path, [spec])
    assert result.loc[0, "DEQS_score"] == 50.0


def test_canonical_deqs_snapshot_can_be_reused(tmp_path):
    path = tmp_path / "deqs_snapshot.csv"
    pd.DataFrame(
        [{
            "Product": "VRohtoPremium", "Pair_ID": "101-201",
            "Participant_ID": "101", "First_session_ID": "101",
            "Second_session_ID": "201", "EyeDrop_session_ID": "101",
            "Control_session_ID": "201", "Degree_score_sum": 30,
            "Valid_item_count": 15, "DEQS_score": 50.0,
        }]
    ).to_csv(path, index=False)
    spec = SimpleNamespace(
        first_session_id="101", second_session_id="201", drops_session_id="101",
        control_session_id="201", pair_id="101-201", product="VRohtoPremium",
    )
    result = MODULE.load_deqs_scores(path, [spec])
    assert result.loc[0, "Pair_ID"] == "101-201"
    assert result.loc[0, "DEQS_score"] == 50.0


def test_eye_drop_effect_is_difference_in_set6_over_set1_ratios():
    deqs = pd.DataFrame(
        [{
            "Product": "CCube", "Pair_ID": "102-202", "Participant_ID": "102",
            "First_session_ID": "102", "Second_session_ID": "202",
            "EyeDrop_session_ID": "102", "Control_session_ID": "202",
            "Degree_score_sum": 15, "Valid_item_count": 15, "DEQS_score": 25.0,
        }]
    )
    values = pd.DataFrame([
        {"Product": "CCube", "Pair_ID": "102-202", "Set": 1,
         "EyeDrop_set_mean_RT_ms": 100.0, "Control_set_mean_RT_ms": 100.0,
         "EyeDrop_valid_trial_count": 320, "Control_valid_trial_count": 320},
        {"Product": "CCube", "Pair_ID": "102-202", "Set": 6,
         "EyeDrop_set_mean_RT_ms": 110.0, "Control_set_mean_RT_ms": 130.0,
         "EyeDrop_valid_trial_count": 320, "Control_valid_trial_count": 320},
    ])
    result = MODULE.build_analysis_dataset(deqs, values)
    assert np.isclose(result.loc[0, "Eye_Drop_Effect_au"], 0.2)
    assert bool(result.loc[0, "Included_in_correlation"])


def test_phase2_comparison_accepts_matching_nan_and_rejects_difference():
    row = {
        "Product": "CCube", "Pair_ID": "102-202", "Set": 1,
        "EyeDrop_set_mean_RT_ms": np.nan, "Control_set_mean_RT_ms": np.nan,
        "EyeDrop_valid_trial_count": 0, "Control_valid_trial_count": 0,
    }
    matched = MODULE.compare_phase2_values(pd.DataFrame([row]), pd.DataFrame([row]))
    assert bool(matched.loc[0, "All_values_match"])
    changed = dict(row)
    changed["Control_valid_trial_count"] = 1
    try:
        MODULE.compare_phase2_values(pd.DataFrame([row]), pd.DataFrame([changed]))
    except ValueError:
        pass
    else:
        raise AssertionError("A Phase 2 mismatch must abort the analysis")
