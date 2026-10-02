from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

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


def test_prominence_threshold_uses_median_plus_ten_robust_sd():
    signal = _set_signal(1, [])
    values = np.array([0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 10.0, 0.0])
    for channel in signal.filtered_uv:
        signal.filtered_uv[channel] = values.copy()
    thresholds, _ = MODULE.calculate_session_thresholds({1: signal})
    threshold = thresholds["Fp1_Fp2_mean"]
    expected_median = 2.5
    expected_mad = 1.0
    expected = expected_median + 10.0 * 1.4826 * expected_mad
    assert np.isclose(threshold["prominence_median_uv"], expected_median)
    assert np.isclose(threshold["prominence_mad_uv"], expected_mad)
    assert np.isclose(threshold["prominence_uv"], expected)


def test_prominence_threshold_accepts_explicit_comparison_multiplier():
    signal = _set_signal(1, [])
    values = np.array([0.0, 1.0, 0.0, 2.0, 0.0, 3.0, 0.0, 10.0, 0.0])
    for channel in signal.filtered_uv:
        signal.filtered_uv[channel] = values.copy()
    thresholds, _ = MODULE.calculate_session_thresholds(
        {1: signal}, prominence_mad_multiplier=8.0
    )
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


def test_grand_y_axis_uses_mean_plus_sd_and_eighty_seven_point_five_percent():
    assert MODULE.grand_figure_y_upper_limit(np.array([20.0, 43.0])) == 50.0


def test_detection_html_uses_eye_blink_component_signal_labels(tmp_path):
    signal = _set_signal(1, [])
    result = MODULE.SessionResult(
        "101",
        "Eye Drop",
        {
            "Fp1_Fp2_mean": {
                "height_uv": None,
                "prominence_uv": 1.0,
                "prominence_mad_multiplier": 10.0,
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
