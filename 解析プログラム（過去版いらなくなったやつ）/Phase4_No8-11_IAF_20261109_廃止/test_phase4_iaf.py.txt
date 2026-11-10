from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
from scipy.signal import get_window, welch

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))

import phase4_iaf as module  # noqa: E402


def _spectrum(*peaks: float) -> np.ndarray:
    """Known alpha bumps over a deterministic power-law background."""
    frequencies = module.FREQUENCIES
    log_bumps = sum(3 * np.exp(-0.5 * ((frequencies - peak) / 0.35) ** 2) for peak in peaks)
    return frequencies**-1.7 * np.exp(log_bumps)


def _eeg(seconds: int = 60) -> np.ndarray:
    time = np.arange(seconds * 256) / 256
    return np.column_stack(
        [10e-6 * np.sin(2 * np.pi * 10.3 * time), 6e-6 * np.sin(2 * np.pi * 11.2 * time)]
    )


def test_exact_power_law_has_no_artificial_iaf() -> None:
    result = module.select_peak(module.FREQUENCIES, _spectrum())
    assert result["quality"] == "no_local_peak"
    assert np.isnan(result["frequency_hz"])
    assert result["raw_band_max_hz"] == 8.0


@pytest.mark.parametrize("peak", [8.0, 10.3, 15.0])
def test_known_peak_and_inclusive_band_edges_are_recovered(peak: float) -> None:
    result = module.select_peak(module.FREQUENCIES, _spectrum(peak))
    assert result["quality"] == "ok"
    assert result["frequency_hz"] == pytest.approx(peak, abs=0.1)
    assert result["z_score"] >= 1.75
    assert not result["multiple_peaks"]


@pytest.mark.parametrize("peak", [7.0, 16.0])
def test_out_of_band_peak_is_not_forced_onto_alpha_boundary(peak: float) -> None:
    result = module.select_peak(module.FREQUENCIES, _spectrum(peak))
    assert np.isnan(result["frequency_hz"])
    assert result["quality"] != "ok"


def test_comparable_separated_peaks_are_flagged_without_cog_fallback() -> None:
    result = module.select_peak(module.FREQUENCIES, _spectrum(10.0, 13.0))
    assert result["multiple_peaks"]
    assert result["frequency_hz"] in (10.0, 13.0)
    assert result["frequency_hz"] != 11.5


@pytest.mark.parametrize("bad_value", [0.0, -1.0, np.nan, np.inf])
def test_invalid_spectrum_is_rejected(bad_value: float) -> None:
    power = _spectrum(10.3)
    power[100] = bad_value
    result = module.select_peak(module.FREQUENCIES, power)
    assert result["quality"] == "invalid_spectrum"
    assert np.isnan(result["frequency_hz"])


def test_peak_quality_reference_has_83_points_and_sample_sd() -> None:
    power = _spectrum(10.3)
    result = module.select_peak(module.FREQUENCIES, power)
    corrected = module.corrected_spectrum(module.FREQUENCIES, power)
    peak_index = int(round((result["candidate_hz"] - 1) * 10))
    offsets = np.arange(len(module.FREQUENCIES)) - peak_index
    reference = ((np.abs(offsets) >= 10) & (np.abs(offsets) <= 50)) | (offsets == 0)
    assert reference.sum() == 83
    values = corrected[reference]
    expected = (corrected[peak_index] - values.mean()) / values.std(ddof=1)
    assert result["z_score"] == pytest.approx(expected, abs=1e-12)


def test_background_removal_is_log_log_and_scale_invariant() -> None:
    power = _spectrum(10.3)
    result = module.corrected_spectrum(module.FREQUENCIES, power)
    scaled = module.corrected_spectrum(module.FREQUENCIES, power * 1e9)
    np.testing.assert_allclose(result, scaled, atol=1e-12)
    assert np.ptp(module.corrected_spectrum(module.FREQUENCIES, _spectrum())) < 1e-10


def test_periodograms_have_requested_grid_units_positions_and_welch_mean() -> None:
    data = _eeg()
    result = module.compute_periodograms(data, np.zeros(len(data), dtype=bool))
    assert result["psd"].shape == (11, 2, 391)
    np.testing.assert_array_equal(result["starts"], np.arange(11) * 1280)
    np.testing.assert_allclose(result["freqs"], np.arange(10, 401) / 10, atol=1e-12)
    assert result["valid"].all()
    frequencies, independently_averaged = welch(
        data[:, 0] * 1e6,
        fs=256,
        window=get_window("hann", 2560, fftbins=True),
        nperseg=2560,
        noverlap=1280,
        nfft=2560,
        detrend="constant",
        return_onesided=True,
        scaling="density",
        average="mean",
    )
    np.testing.assert_allclose(frequencies[10:401], result["freqs"], atol=1e-12)
    np.testing.assert_allclose(result["psd"][:, 0].mean(axis=0), independently_averaged[10:401])
    for channel, amplitude in enumerate([10, 6]):
        # Integral of density is the variance of the sinusoid in microvolts squared.
        powers = np.sum(result["psd"][:, channel], axis=1) * 0.1
        np.testing.assert_allclose(powers, amplitude**2 / 2, rtol=1e-12, atol=1e-10)


def test_single_artifact_sample_rejects_exact_overlapping_segments_without_time_compression() -> (
    None
):
    data = _eeg()
    mask = np.zeros(len(data), dtype=bool)
    mask[2560] = True
    result = module.compute_periodograms(data, mask)
    expected = np.ones((11, 2), dtype=bool)
    expected[[1, 2]] = False
    np.testing.assert_array_equal(result["valid"], expected)
    np.testing.assert_array_equal(result["starts"], np.arange(11) * 1280)
    assert np.isnan(result["psd"][[1, 2]]).all()
    assert np.isfinite(result["psd"][0]).all()


def test_nonfinite_eeg_rejects_only_affected_channel_segments() -> None:
    data = _eeg()
    data[2560, 0] = np.nan
    result = module.compute_periodograms(data, np.zeros(len(data), dtype=bool))
    assert not result["valid"][[1, 2], 0].any()
    assert result["valid"][:, 1].all()
    assert result["valid"][0, 0]


def test_input_validation_and_short_set_do_not_pad() -> None:
    with pytest.raises(ValueError, match="sampling rate"):
        module.compute_periodograms(_eeg(), np.zeros(60 * 256), sfreq=128)
    with pytest.raises(ValueError, match="two EEG channels"):
        module.compute_periodograms(np.zeros((10, 1)), np.zeros(10))
    with pytest.raises(ValueError, match="time-aligned"):
        module.compute_periodograms(_eeg(), np.zeros(20))
    result = module.compute_periodograms(_eeg(9), np.zeros(9 * 256))
    assert result["psd"].shape == (0, 2, 391)
    assert len(result["starts"]) == 0


@pytest.mark.parametrize(
    ("starts_seconds", "expected_seconds"),
    [([], 0), ([0], 10), ([0, 5], 15), ([0, 5, 20], 25), ([20, 0, 5, 5], 25), ([0, 15], 20)],
)
def test_unique_coverage_counts_union_not_overlap(
    starts_seconds: list[int], expected_seconds: float
) -> None:
    starts = np.array(starts_seconds, dtype=int) * 256
    assert module.unique_coverage_seconds(starts) == expected_seconds


def test_moving_estimate_uses_six_segment_gate_and_unique_seconds() -> None:
    starts = np.arange(11) * 1280
    spectra = np.tile(_spectrum(10.3), (11, 1))
    valid = np.arange(11) < 5
    result = module.estimate(spectra, starts, valid, moving=True)
    assert result["quality"] == "insufficient_data"
    assert result["usable_seconds"] == 30
    valid[5] = True
    result = module.estimate(spectra, starts, valid, moving=True)
    assert result["quality"] == "ok"
    assert result["n_valid_segments"] == 6
    assert result["n_possible_segments"] == 11
    assert result["usable_seconds"] == 35


def test_setwise_estimate_requires_sixty_unique_seconds() -> None:
    starts = np.arange(11) * 1280
    spectra = np.tile(_spectrum(10.3), (11, 1))
    valid = np.arange(11) < 10
    result = module.estimate(spectra, starts, valid, moving=False)
    assert result["quality"] == "insufficient_data"
    assert result["usable_seconds"] == 55
    valid[-1] = True
    result = module.estimate(spectra, starts, valid, moving=False)
    assert result["quality"] == "ok"
    assert result["usable_seconds"] == 60


def test_linear_psd_is_averaged_before_peak_estimation(monkeypatch: pytest.MonkeyPatch) -> None:
    spectra = np.vstack([_spectrum(10.3) * scale for scale in range(1, 12)])
    starts = np.arange(11) * 1280
    valid = np.ones(11, dtype=bool)
    observed = []
    original = module.select_peak

    def capture(frequencies: np.ndarray, power: np.ndarray) -> dict:
        observed.append(power.copy())
        return original(frequencies, power)

    monkeypatch.setattr(module, "select_peak", capture)
    module.estimate(spectra, starts, valid, moving=False)
    np.testing.assert_allclose(observed[0], spectra.mean(axis=0))
    assert not np.allclose(observed[0], np.exp(np.log(spectra).mean(axis=0)))


def test_cached_rows_keep_channel_mapping_missing_sets_real_time_and_progress(
    tmp_path: Path,
) -> None:
    path = tmp_path / "synthetic_spectra.h5"
    starts = np.arange(12) * 1280
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            pair_id="synthetic", session_id="session", condition="Control", product="CCube"
        )
        handle.create_dataset("frequencies_hz", data=module.FREQUENCIES)
        group = handle.create_group("Set2")
        group.attrs.update(duration_seconds=65.0, n_samples=65 * 256)
        group.create_dataset(
            "psd", data=np.tile(np.vstack([_spectrum(10.3), _spectrum(11.2)]), (12, 1, 1))
        )
        group.create_dataset("starts", data=starts)
        group.create_dataset("valid", data=np.ones((12, 2), dtype=bool))
        group.create_dataset("ica_channel_excluded", data=[False, True])
    rows = module.rows_from_cache(path)
    for number, channel, expected_peak in [(8, "Pz", 10.3), (10, "Fz", 11.2)]:
        assert len(rows[number]) == 6
        assert [row["set_number"] for row in rows[number]] == list(range(1, 7))
        assert rows[number][0]["quality"] == "missing_set"
        assert rows[number][1]["channel"] == channel
        assert rows[number][1]["frequency_hz"] == expected_peak
    for number, channel, expected_peak in [(9, "Pz", 10.3), (11, "Fz", 11.2)]:
        present = [row for row in rows[number] if row["set_number"] == 2]
        assert len(present) == 2
        assert [row["center_seconds"] for row in present] == [30, 35]
        assert [row["frequency_hz"] for row in present] == [expected_peak, expected_peak]
        assert all(row["channel"] == channel for row in present)
        np.testing.assert_allclose(
            [row["progress"] for row in present], 100 + 100 * np.array([30, 35]) / 65
        )
        assert all(row["ica_channel_excluded"] == (channel == "Fz") for row in present)
