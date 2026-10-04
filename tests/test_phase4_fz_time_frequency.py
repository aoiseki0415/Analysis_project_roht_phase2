from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム"
    / "Phase4_脳波解析"
    / "Phase4_No1_add_FzTimeFrequencyMap.py"
)
SPEC = importlib.util.spec_from_file_location("phase4_no1_add", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_calculate_set_tfm_has_fixed_frequency_bins_and_progress() -> None:
    samples = 768
    time = np.arange(samples) / MODULE.SFREQ
    signal_v = 20e-6 * np.sin(2.0 * np.pi * 10.0 * time)
    result = MODULE.calculate_set_tfm(
        signal_v,
        time,
        1_000.0 + time,
        np.zeros(samples, dtype=bool),
        2,
    )
    assert result.raw_psd.shape[1] == 30
    assert np.isclose(result.set_progress_pct[0], 0.0)
    assert np.isclose(result.set_progress_pct[-1], 100.0)
    assert np.isclose(result.global_progress_pct[0], 100.0)
    dominant = MODULE.FREQUENCIES_HZ[np.argmax(result.raw_psd.mean(axis=0))]
    assert dominant == 10.0


def test_broadband_mask_is_session_wide_upper_only() -> None:
    def make_set(number: int, broadband: np.ndarray) -> object:
        raw = np.repeat(broadband[:, None], 30, axis=1)
        size = broadband.size
        return MODULE.SetTFM(
            set_number=number,
            raw_psd=raw,
            relative_seconds_center=np.arange(size, dtype=float),
            original_timestamp_center=np.arange(size, dtype=float) + 1000.0,
            set_progress_pct=np.linspace(0.0, 100.0, size),
            global_progress_pct=(number - 1) * 100.0 + np.linspace(0.0, 100.0, size),
            source_center_sample=np.arange(size),
            phase1_mask_fraction=np.zeros(size),
            broadband_psd=broadband,
            broadband_outlier_mask=np.zeros(size, dtype=bool),
        )

    baseline = np.ones(200, dtype=float)
    first = make_set(1, baseline.copy())
    second_values = baseline.copy()
    second_values[-1] = 1e6
    second = make_set(2, second_values)
    result = MODULE.calculate_broadband_mask({1: first, 2: second})
    assert not first.broadband_outlier_mask.any()
    assert second.broadband_outlier_mask[-1]
    assert result["threshold_linear"] > 1.0


def test_centered_nanmean_and_interpolation_preserve_gaps() -> None:
    values = np.array([[1.0, np.nan], [np.nan, np.nan], [3.0, 5.0]])
    smoothed = MODULE.centered_nanmean_2d(values, 3)
    assert np.isclose(smoothed[1, 0], 2.0)
    assert np.isclose(smoothed[1, 1], 5.0)
    target = np.arange(5, dtype=float)
    interpolated = MODULE.interpolate_finite_runs(
        np.arange(5, dtype=float),
        np.array([1.0, 2.0, np.nan, 4.0, 5.0]),
        target,
    )
    assert np.isnan(interpolated[2])
    assert np.allclose(interpolated[[0, 1, 3, 4]], [1.0, 2.0, 4.0, 5.0])


def test_missing_sets_are_pairwise_removed_before_group_average() -> None:
    assert MODULE.EXPECTED_MISSING_SETS["109"] == {1}
    assert MODULE.EXPECTED_MISSING_SETS["120"] == {6}
    assert MODULE.EXPECTED_MISSING_SETS["135"] == {2}
    assert MODULE.EXPECTED_MISSING_SETS["225"] == {4}
