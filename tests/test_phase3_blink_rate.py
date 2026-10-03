from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

SCRIPT = (
    Path(__file__).parents[1] / "解析プログラム" / "Phase3_瞬き解析" / "Phase3_No1_BlinkRate.py"
)
SPEC = importlib.util.spec_from_file_location("phase3_blink", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _set_signal(duration_seconds: int, peak_seconds: list[float]):
    n_samples = int(duration_seconds * MODULE.SFREQ)
    times = np.arange(n_samples) / MODULE.SFREQ
    signal = MODULE.SetSignal(
        "101",
        1,
        Path("dummy.h5"),
        times,
        times * 1000,
        {
            "Fp1": np.zeros(n_samples),
            "Fp2": np.zeros(n_samples),
            "Fp1_Fp2_mean": np.zeros(n_samples),
        },
        {
            "Fp1": np.zeros(n_samples),
            "Fp2": np.zeros(n_samples),
            "Fp1_Fp2_mean": np.zeros(n_samples),
        },
        {
            "Fp1": np.array([], dtype=int),
            "Fp2": np.array([], dtype=int),
            "Fp1_Fp2_mean": (np.array(peak_seconds) * MODULE.SFREQ).astype(int),
        },
    )
    return signal


def test_participant_mapping_keeps_pair_and_conditions():
    spec = MODULE.parse_participant("101:201:101:VRohtoPremium")
    assert spec.pair_id == "101-201"
    assert spec.drops_session_id == "101"
    assert spec.control_session_id == "201"


def test_manifest_validation_rejects_excluded_and_duplicate_sessions():
    with pytest.raises(ValueError, match="Excluded session IDs"):
        MODULE.validate_participant_specs(
            [MODULE.ParticipantSpec("130", "230", "130", "CCube")]
        )
    with pytest.raises(ValueError, match="reuses a session ID"):
        MODULE.validate_participant_specs(
            [
                MODULE.ParticipantSpec("101", "201", "101", "VRohtoPremium"),
                MODULE.ParticipantSpec("102", "201", "102", "CCube"),
            ]
        )


def test_production_manifest_requires_forty_balanced_pairs():
    with pytest.raises(ValueError, match="requires 40 participant pairs"):
        MODULE.validate_participant_specs(
            [MODULE.ParticipantSpec("101", "201", "101", "VRohtoPremium")],
            production_batch=True,
        )


def test_blink_rate_uses_actual_edge_window_duration():
    signal = _set_signal(120, [5, 10, 20, 40, 90])
    frame = MODULE.calculate_blink_rate(signal)
    at_zero = frame.iloc[0]
    assert at_zero["WindowDurationSeconds"] == 30
    assert at_zero["BlinkCountInWindow"] == 3
    assert at_zero["BlinkRateBlinksPerMin"] == 6
    at_sixty = frame.loc[frame["SetTimeSeconds"] == 60].iloc[0]
    assert at_sixty["WindowDurationSeconds"] == 60
    assert at_sixty["BlinkCountInWindow"] == 1
    assert "BlinkRateSmoothed15sBlinksPerMin" in frame.columns


def test_progress_maps_each_set_to_one_hundred_units():
    signal = _set_signal(100, [20])
    signal.set_number = 3
    frame = MODULE.calculate_blink_rate(signal)
    assert frame.iloc[0]["ExperimentalProgressPercent"] == 200
    assert np.isclose(frame.iloc[-1]["ExperimentalProgressPercent"], 300)


def test_peak_detection_applies_minimum_distance_and_width():
    values = np.zeros(300)
    values[45:56] = np.array([0, 2, 4, 6, 8, 10, 8, 6, 4, 2, 0])
    values[65:76] = np.array([0, 2, 4, 6, 8, 9, 8, 6, 4, 2, 0])
    values[150:170] = np.r_[np.linspace(0, 12, 10), np.linspace(12, 0, 10)]
    peaks = MODULE.detect_blink_peaks(values, prominence_uv=5)
    assert peaks.tolist() == [50, 159]


def test_peak_detection_uses_prominence_without_height_threshold():
    signal = _set_signal(1, [])
    values = np.array([-10.0, -8.0, -10.0, -9.0, -10.0])
    for channel in signal.filtered_uv:
        signal.filtered_uv[channel] = values.copy()
    thresholds, distributions = MODULE.calculate_session_thresholds({1: signal})
    assert thresholds["Fp1_Fp2_mean"]["height_uv"] is None
    assert distributions["Fp1_Fp2_mean"].tolist() == [2.0, 1.0]
    peaks = MODULE.detect_blink_peaks(
        values,
        prominence_uv=thresholds["Fp1_Fp2_mean"]["prominence_uv"],
    )
    assert peaks.tolist() == []


def test_auxiliary_all_nan_channel_is_allowed_but_has_no_threshold():
    signal = _set_signal(1, [])
    signal.filtered_uv["Fp2"][:] = np.nan
    signal.filtered_uv["Fp1"] = np.array(
        [0.0, 1.0, 0.0] + [0.0] * (signal.filtered_uv["Fp1"].size - 3)
    )
    signal.filtered_uv["Fp1_Fp2_mean"] = signal.filtered_uv["Fp1"].copy()
    thresholds, distributions = MODULE.calculate_session_thresholds({1: signal})
    assert thresholds["Fp2"]["prominence_uv"] is None
    assert thresholds["Fp2"]["prominence_candidate_count"] == 0
    assert distributions["Fp2"].size == 0


def test_prominence_threshold_uses_median_plus_twelve_robust_sd():
    signal = _set_signal(1, [])
    values = np.array([0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 10.0, 0.0])
    for channel in signal.filtered_uv:
        signal.filtered_uv[channel] = values.copy()
    thresholds, _ = MODULE.calculate_session_thresholds({1: signal})
    threshold = thresholds["Fp1_Fp2_mean"]
    expected_median = 2.5
    expected_mad = 1.0
    expected = expected_median + 12.0 * 1.4826 * expected_mad
    assert np.isclose(threshold["prominence_median_uv"], expected_median)
    assert np.isclose(threshold["prominence_mad_uv"], expected_mad)
    assert np.isclose(threshold["prominence_uv"], expected)


def test_prominence_threshold_accepts_explicit_comparison_multiplier():
    signal = _set_signal(1, [])
    values = np.array([0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 10.0, 0.0])
    for channel in signal.filtered_uv:
        signal.filtered_uv[channel] = values.copy()
    thresholds, _ = MODULE.calculate_session_thresholds({1: signal}, prominence_mad_multiplier=8.0)
    threshold = thresholds["Fp1_Fp2_mean"]
    assert np.isclose(threshold["prominence_uv"], 2.5 + 8.0 * 1.4826)
    assert threshold["prominence_mad_multiplier"] == 8.0


def test_rate_smoothing_is_centered_and_keeps_raw_rate():
    signal = _set_signal(120, [5, 10, 20, 40, 90])
    frame = MODULE.calculate_blink_rate(signal)
    expected = frame["BlinkRateBlinksPerMin"].rolling(window=15, center=True, min_periods=1).mean()
    assert np.allclose(frame["BlinkRateSmoothed15sBlinksPerMin"], expected)
    assert not np.shares_memory(
        frame["BlinkRateBlinksPerMin"].to_numpy(),
        frame["BlinkRateSmoothed15sBlinksPerMin"].to_numpy(),
    )


def test_session_file_prefix_sorts_sessions_within_pair():
    spec = MODULE.parse_participant("101:201:101:VRohtoPremium")
    assert MODULE.session_file_prefix(spec, "101") == "Pair101-201_01_ID101"
    assert MODULE.session_file_prefix(spec, "201") == "Pair101-201_02_ID201"


def test_detection_reset_scale_matches_html_formula():
    signal = _set_signal(1, [])
    values = np.linspace(-20.0, 20.0, signal.relative_seconds.size)
    signal.filtered_uv["Fp1_Fp2_mean"] = values
    result = MODULE.SessionResult(
        "101",
        "Eye Drop",
        {"Fp1_Fp2_mean": {"prominence_uv": 1.0}},
        {"Fp1_Fp2_mean": np.array([1.0])},
        {1: signal},
    )
    absolute = np.sort(np.abs(values))
    expected = max(10.0, float(absolute[int(np.floor(absolute.size * 0.995))]) * 1.60)
    assert np.isclose(MODULE.detection_reset_scale_uv(result), expected)


def test_individual_y_axis_places_maximum_near_seventy_percent():
    assert MODULE.individual_figure_y_upper_limit(np.array([10.0, 34.0])) == 50.0


def test_grand_y_axis_uses_mean_plus_sem_and_seventy_five_percent():
    assert MODULE.grand_figure_y_upper_limit(np.array([20.0, 43.0])) == 60.0


def test_focused_grand_y_axis_is_common_and_has_horizontal_grid():
    figure, axis = MODULE.plt.subplots()
    MODULE.configure_grand_average_y_axis(
        axis, np.array([12.0, 28.0]), focused_y_axis=True
    )
    assert axis.get_ylim() == (10.0, 30.0)
    assert axis.get_yticks().tolist() == [10.0, 15.0, 20.0, 25.0, 30.0]
    assert any(line.get_visible() for line in axis.get_ygridlines())
    MODULE.plt.close(figure)


def test_grand_average_statistics_use_sample_sem_and_valid_n():
    values = np.array([[1.0, 2.0, np.nan], [3.0, 4.0, 9.0], [5.0, np.nan, np.nan]])
    result = MODULE.calculate_grand_average_statistics(values)
    assert np.allclose(result["mean"][:2], [3.0, 3.0])
    assert np.allclose(result["sample_sd"][:2], [2.0, np.sqrt(2.0)])
    assert np.allclose(result["sem"][:2], [2.0 / np.sqrt(3.0), 1.0])
    assert result["valid_n"].tolist() == [3, 2, 1]
    assert np.isnan(result["sample_sd"][2])
    assert np.isnan(result["sem"][2])


def test_group_quantification_uses_between_participant_values_and_paired_missing_set():
    items = []
    for first, second, eye_value, control_value, missing_control in (
        ("101", "201", 10.0, 20.0, False),
        ("103", "203", 30.0, 40.0, True),
    ):
        spec = MODULE.ParticipantSpec(first, second, first, "VRohtoPremium")
        summary_rows = []
        rates = {}
        for session_id, condition, value in (
            (first, "Eye Drop", eye_value),
            (second, "Control", control_value),
        ):
            sets = [1] if not (missing_control and condition == "Control") else []
            rates[session_id] = MODULE.pd.DataFrame(
                {
                    "Set": sets,
                    "ExperimentalProgressPercent": [0.0] * len(sets),
                    "BlinkRateSmoothed15sBlinksPerMin": [value] * len(sets),
                }
            )
            if sets:
                summary_rows.append(
                    {
                        "SessionID": session_id,
                        "Condition": condition,
                        "Set": 1,
                        "BlinkRateBlinksPerMin": value,
                    }
                )
        items.append(
            {
                "spec": spec,
                "product_dir": "VRohtoPremium",
                "summary": MODULE.pd.DataFrame(summary_rows),
                "rate_frames": rates,
            }
        )
    frame = MODULE._group_quantification_frame(items, "VRohtoPremium")
    set_one = frame.loc[frame["Set"] == 1]
    pair_two = set_one.loc[set_one["PairID"] == "103-203"]
    assert pair_two["BlinkRateBlinksPerMin"].isna().all()
    pair_one = set_one.loc[set_one["PairID"] == "101-201"]
    assert pair_one["BlinkRateBlinksPerMin"].tolist() == [10.0, 20.0]


def test_additional_exclusion_removes_both_conditions_for_the_paired_sets():
    spec = MODULE.ParticipantSpec("133", "233", "133", "VRohtoPremium")
    summary = MODULE.pd.DataFrame(
        [
            {
                "SessionID": session_id,
                "Condition": condition,
                "Set": set_number,
                "BlinkRateBlinksPerMin": float(set_number * factor),
            }
            for session_id, condition, factor in (
                ("133", "Eye Drop", 1),
                ("233", "Control", 2),
            )
            for set_number in range(1, 7)
        ]
    )
    rates = {
        session_id: MODULE.pd.DataFrame(
            {
                "Set": np.repeat(np.arange(1, 7), 2),
                "ExperimentalProgressPercent": np.concatenate(
                    [
                        np.array([(set_number - 1) * 100.0, set_number * 100.0])
                        for set_number in range(1, 7)
                    ]
                ),
                "BlinkRateSmoothed15sBlinksPerMin": np.repeat(
                    np.arange(1, 7) * factor, 2
                ),
            }
        )
        for session_id, factor in (("133", 1), ("233", 2))
    }
    item = {
        "spec": spec,
        "product_dir": "VRohtoPremium",
        "summary": summary,
        "rate_frames": rates,
    }
    exclusions = {"133-233": {1, 2, 3}}
    frame = MODULE._group_quantification_frame(
        [item], "VRohtoPremium", excluded_pair_sets=exclusions
    )
    assert frame.loc[
        frame["Set"].isin([1, 2, 3]), "BlinkRateBlinksPerMin"
    ].isna().all()
    assert frame.loc[
        frame["Set"].isin([4, 5, 6]), "BlinkRateBlinksPerMin"
    ].notna().all()
    matrices, _, _ = MODULE._group_rate_matrices(
        [item], "VRohtoPremium", excluded_pair_sets=exclusions
    )
    for condition in ("Eye Drop", "Control"):
        assert np.isnan(
            matrices[condition][0, : 3 * MODULE.GROUP_PROGRESS_POINTS_PER_SET]
        ).all()
        assert np.isfinite(
            matrices[condition][0, 3 * MODULE.GROUP_PROGRESS_POINTS_PER_SET :]
        ).all()


def test_all_sets_blink_rate_uses_total_count_over_total_duration():
    frame = MODULE.pd.DataFrame(
        [
            {
                "PairID": "101-201",
                "Condition": condition,
                "Set": set_number,
                "BlinkRateBlinksPerMin": count / duration,
                "BlinkCount": count,
                "SetDurationMinutes": duration,
            }
            for condition, values in {
                "Eye Drop": ((10.0, 1.0), (30.0, 3.0)),
                "Control": ((12.0, 1.0), (24.0, 3.0)),
            }.items()
            for set_number, (count, duration) in enumerate(values, start=1)
        ]
    )
    result = MODULE.build_all_sets_blink_values(frame).iloc[0]
    assert result["IncludedSetCount"] == 2
    assert result["EyeDrop_all_sets_blink_rate"] == 10.0
    assert result["Control_all_sets_blink_rate"] == 9.0


def test_blink_setwise_statistics_include_both_adjustments():
    frame = MODULE.pd.DataFrame(
        [
            {
                "PairID": f"P{participant}",
                "Condition": condition,
                "Set": set_number,
                "BlinkRateBlinksPerMin": 10.0 + participant + (condition == "Control"),
            }
            for set_number in range(1, 7)
            for participant in range(8)
            for condition in ("Eye Drop", "Control")
        ]
    )
    statistics = MODULE.build_setwise_paired_statistics(frame)
    assert len(statistics) == 6
    assert statistics["P_value_Bonferroni"].between(0, 1).all()
    assert statistics["P_value_Holm"].between(0, 1).all()
    assert statistics["P_value_FDR_BH"].between(0, 1).all()


def test_production_threshold_basis_is_explicitly_exploratory_not_literature():
    assert "exploratory" in MODULE.PROMINENCE_MULTIPLIER_BASIS
    assert "not a literature" in MODULE.PROMINENCE_MULTIPLIER_BASIS
    assert "similar" in MODULE.PERCENTILE_THRESHOLD_REJECTION_REASON


def test_detection_html_uses_eye_blink_component_signal_labels(tmp_path):
    signal = _set_signal(1, [])
    result = MODULE.SessionResult(
        "101",
        "Eye Drop",
        {
            "Fp1_Fp2_mean": {
                "height_uv": None,
                "prominence_uv": 1.0,
                "prominence_mad_multiplier": 12.0,
            }
        },
        {"Fp1_Fp2_mean": np.array([1.0])},
        {1: signal},
    )
    output = tmp_path / "blink_detection.html"
    MODULE.save_detection_html(result, output)
    html = output.read_text(encoding="utf-8")
    assert "Eye Blink Component Signal" in html
    assert "Amplitude (µV)" in html
    assert "Filtered amplitude (µV)" not in html


def test_condition_blink_count_balance_uses_only_paired_available_sets():
    spec = MODULE.ParticipantSpec("101", "201", "101", "VRohtoPremium")
    summaries = MODULE.pd.DataFrame(
        [
            {"SessionID": "101", "Set": 1, "Status": "使用", "MeanSignalBlinkCount": 10},
            {"SessionID": "101", "Set": 2, "Status": "使用", "MeanSignalBlinkCount": 100},
            {"SessionID": "201", "Set": 1, "Status": "使用", "MeanSignalBlinkCount": 25},
            {"SessionID": "201", "Set": 2, "Status": "欠測", "MeanSignalBlinkCount": np.nan},
        ]
    )
    balance = MODULE.condition_blink_count_balance(summaries, spec)
    assert balance["paired_sets"] == [1]
    assert balance["eye_drop_total_blinks"] == 10
    assert balance["control_total_blinks"] == 25
    assert balance["larger_to_smaller_ratio"] == 2.5
    assert balance["balance_status"] == "要確認"
    assert balance["use_for_exclusion"] is False
