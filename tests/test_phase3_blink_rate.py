from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

import numpy as np


SCRIPT = (
    Path(__file__).parents[1]
    / "解析プログラム"
    / "Phase3_瞬き解析"
    / "Phase3_No1_BlinkRate.py"
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


def test_progress_maps_each_set_to_one_hundred_units():
    signal = _set_signal(100, [20])
    signal.set_number = 3
    frame = MODULE.calculate_blink_rate(signal)
    assert frame.iloc[0]["ExperimentalProgressPercent"] == 200
    assert np.isclose(frame.iloc[-1]["ExperimentalProgressPercent"], 300)


def test_no_minimum_peak_distance_is_applied():
    values = np.zeros(100)
    values[[40, 42]] = [10, 9]
    peaks, _ = MODULE.find_peaks(values, height=5, prominence=5)
    assert peaks.tolist() == [40, 42]
