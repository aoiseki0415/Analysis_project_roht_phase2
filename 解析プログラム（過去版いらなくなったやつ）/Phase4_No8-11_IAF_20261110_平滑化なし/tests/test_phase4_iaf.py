"""Independent checks for the v2 setwise / half-set local-peak IAF contract."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np
import pytest
from scipy.signal import get_window, periodogram, welch

SCRIPT_DIR = Path(__file__).parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))
SPEC = importlib.util.spec_from_file_location("phase4_iaf_v2_tested", SCRIPT_DIR / "phase4_iaf.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FS = 256
NWIN = 2560
HOP = 1280
FREQUENCIES = np.arange(10, 401, dtype=float) / 10


def _signals(n_samples: int, frequencies: tuple[float, float] = (10.2, 11.7)) -> np.ndarray:
    times = np.arange(n_samples, dtype=float) / FS
    return np.column_stack(
        [
            2.0 * np.sin(2 * np.pi * frequencies[0] * times),
            3.0 * np.sin(2 * np.pi * frequencies[1] * times),
        ]
    )


def _power(*peaks: tuple[float, float]) -> np.ndarray:
    spectrum = np.ones(len(FREQUENCIES))
    for frequency, value in peaks:
        spectrum[np.argmin(np.abs(FREQUENCIES - frequency))] = value
    return spectrum


def test_periodogram_grid_and_mean_are_independently_equal_to_scipy_welch() -> None:
    rng = np.random.default_rng(2921)
    samples = _signals(34 * FS + 37) + rng.normal(0, 0.2, (34 * FS + 37, 2))
    result = MODULE.estimate_interval(samples, np.zeros(len(samples), bool))
    freq, expected = welch(
        samples,
        fs=FS,
        window=get_window("hann", NWIN, fftbins=True),
        nperseg=NWIN,
        noverlap=NWIN - HOP,
        nfft=NWIN,
        detrend="constant",
        return_onesided=True,
        scaling="density",
        average="mean",
        axis=0,
    )
    np.testing.assert_allclose(result["freqs"], FREQUENCIES, rtol=0, atol=1e-12)
    np.testing.assert_allclose(result["freqs"], freq[10:401], rtol=0, atol=1e-12)
    np.testing.assert_allclose(result["mean_psd"], expected[10:401].T, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(result["starts"], np.arange(0, 25 * FS, HOP))
    np.testing.assert_array_equal(result["ends"], result["starts"] + NWIN)
    assert result["psd"].shape == (5, 2, 391)
    assert np.isclose(result["tail_unused_seconds"], 4 + 37 / FS)


def test_sine_amplitude_units_are_microvolt_squared_per_hz_not_volts() -> None:
    samples = _signals(NWIN)
    result = MODULE.estimate_interval(samples, np.zeros(NWIN, bool))
    # Integral of one-sided density of a 2 µV sine is A²/2 = 2 µV².
    assert np.isclose(np.sum(result["mean_psd"][0]) * 0.1, 2.0, rtol=1e-10)
    assert np.isclose(np.sum(result["mean_psd"][1]) * 0.1, 4.5, rtol=1e-10)
    assert result["peaks"][0]["frequency_hz"] == 10.2
    assert result["peaks"][1]["frequency_hz"] == 11.7


def test_odd_sample_halves_use_original_time_and_independent_origin() -> None:
    n_samples = 43 * FS + 1
    intervals = MODULE.estimation_intervals(n_samples)
    midpoint = (n_samples + 1) // 2
    assert intervals == {"whole": (0, n_samples), "a": (0, midpoint), "b": (midpoint, n_samples)}
    samples = _signals(n_samples)
    starts_all = []
    for interval_name in ("a", "b"):
        start, stop = intervals[interval_name]
        result = MODULE.compute_periodograms(
            samples[start:stop],
            np.zeros(stop - start, bool),
            start_sample=start,
        )
        expected_starts = np.arange(start, stop - NWIN + 1, HOP)
        np.testing.assert_array_equal(result["starts"], expected_starts)
        assert result["starts"][0] == start
        assert np.all(result["ends"] <= stop)
        starts_all.extend(result["starts"])
    assert midpoint in starts_all
    assert midpoint % HOP != 0  # Not a classification of the whole-Set grid.


def test_one_bad_sample_excludes_every_overlapping_window_and_does_not_close_gaps() -> None:
    samples = _signals(30 * FS)
    mask = np.zeros(len(samples), bool)
    mask[10 * FS] = True
    result = MODULE.compute_periodograms(samples, mask)
    expected = np.array([True, False, False, True, True])
    np.testing.assert_array_equal(result["valid"][:, 0], expected)
    np.testing.assert_array_equal(result["valid"][:, 1], expected)
    np.testing.assert_array_equal(result["starts"], [0, 1280, 2560, 3840, 5120])
    assert np.isnan(result["psd"][~result["valid"]]).all()


def test_nonfinite_target_channel_only_excludes_that_channel() -> None:
    samples = _signals(20 * FS)
    samples[0, 0] = np.nan
    result = MODULE.compute_periodograms(samples, np.zeros(len(samples), bool))
    np.testing.assert_array_equal(result["valid"][:, 0], [False, True, True])
    assert result["valid"][:, 1].all()
    assert result["rejection_code"][0, 0] != 0
    assert result["rejection_code"][0, 1] == 0


def test_one_remaining_valid_window_is_sufficient_without_coverage_gate() -> None:
    samples = _signals(40 * FS)
    mask = np.zeros(len(samples), bool)
    mask[10 * FS :] = True
    result = MODULE.estimate_interval(samples, mask)
    np.testing.assert_array_equal(result["n_valid_segments"], [1, 1])
    np.testing.assert_allclose(result["usable_seconds"], [10, 10])
    np.testing.assert_allclose(result["coverage_fraction"], [0.25, 0.25])
    assert np.isfinite(result["mean_psd"]).all()
    assert [peak["quality"] for peak in result["peaks"]] == ["ok", "ok"]


def test_unique_coverage_is_union_not_sum_of_overlapping_window_durations() -> None:
    samples = _signals(20 * FS)
    result = MODULE.estimate_interval(samples, np.zeros(len(samples), bool))
    np.testing.assert_array_equal(result["n_valid_segments"], [3, 3])
    np.testing.assert_allclose(result["usable_seconds"], [20, 20])
    np.testing.assert_allclose(result["coverage_fraction"], [1, 1])


@pytest.mark.parametrize("n_samples, all_bad", [(9 * FS, False), (20 * FS, True)])
def test_no_valid_windows_returns_nan_not_padding_or_imputation(
    n_samples: int, all_bad: bool
) -> None:
    result = MODULE.estimate_interval(_signals(n_samples), np.full(n_samples, all_bad))
    np.testing.assert_array_equal(result["n_valid_segments"], [0, 0])
    assert np.isnan(result["mean_psd"]).all()
    assert all(np.isnan(peak["frequency_hz"]) for peak in result["peaks"])
    assert all(peak["quality"] != "ok" for peak in result["peaks"])


def test_masked_mean_averages_psd_before_peak_not_individual_peak_frequencies() -> None:
    # Non-overlapping accepted 0–10 s and 15–25 s windows; amplitudes differ.
    samples = _signals(25 * FS, (9.0, 9.0))
    times = np.arange(10 * FS) / FS
    samples[15 * FS : 25 * FS] = 8 * np.sin(2 * np.pi * 13 * times)[:, None]
    mask = np.zeros(len(samples), bool)
    mask[10 * FS : 15 * FS] = True
    result = MODULE.estimate_interval(samples, mask)
    valid_spectra = result["psd"][result["valid"][:, 0], 0]
    np.testing.assert_allclose(result["mean_psd"][0], valid_spectra.mean(axis=0))
    assert result["peaks"][0]["frequency_hz"] == 13.0
    assert result["peaks"][0]["frequency_hz"] != 11.0


@pytest.mark.parametrize("frequency", [8.0, 15.0])
def test_alpha_endpoints_are_local_peaks_using_neighbors_outside_alpha(frequency: float) -> None:
    result = MODULE.select_peak(FREQUENCIES, _power((frequency, 20)))
    assert result["quality"] == "ok"
    assert result["frequency_hz"] == frequency
    assert result["n_candidates"] == 1


def test_local_peak_selection_ignores_higher_outside_band_peak_and_uses_original_height() -> None:
    result = MODULE.select_peak(
        FREQUENCIES, _power((7.9, 1000), (10.2, 4), (12.1, 6), (15.1, 2000))
    )
    assert result["frequency_hz"] == 12.1
    assert result["selected_peak_psd"] == 6
    np.testing.assert_allclose(result["candidate_frequencies_hz"], [10.2, 12.1])
    np.testing.assert_allclose(result["candidate_psd"], [4, 6])


def test_equal_height_peaks_choose_lowest_frequency_and_have_no_distance_cutoff() -> None:
    result = MODULE.select_peak(FREQUENCIES, _power((9.0, 4), (9.2, 4), (13.0, 4)))
    assert result["frequency_hz"] == 9.0
    assert result["n_candidates"] == 3


def test_even_plateau_uses_scipy_middle_floor() -> None:
    spectrum = _power()
    spectrum[(FREQUENCIES >= 10.0) & (FREQUENCIES <= 10.3)] = 3
    result = MODULE.select_peak(FREQUENCIES, spectrum)
    assert result["frequency_hz"] == 10.1


@pytest.mark.parametrize(
    "spectrum", [np.ones(391), np.linspace(1, 100, 391), np.linspace(100, 1, 391)]
)
def test_flat_or_monotone_spectrum_is_not_band_argmax(spectrum: np.ndarray) -> None:
    result = MODULE.select_peak(FREQUENCIES, spectrum)
    assert result["quality"] == "no_local_peak"
    assert np.isnan(result["frequency_hz"])
    assert result["n_candidates"] == 0


def test_tiny_local_peak_is_not_rejected_by_prominence_or_z() -> None:
    result = MODULE.select_peak(FREQUENCIES, _power((10.0, 1 + 1e-10)))
    assert result["quality"] == "ok"
    assert result["frequency_hz"] == 10


def test_nonfinite_spectrum_is_explicitly_invalid() -> None:
    spectrum = _power((10.0, 2))
    spectrum[15] = np.nan
    result = MODULE.select_peak(FREQUENCIES, spectrum)
    assert result["quality"] == "invalid_spectrum"
    assert np.isnan(result["frequency_hz"])


def test_rejects_wrong_sampling_rate_and_misaligned_mask() -> None:
    samples = _signals(NWIN)
    with pytest.raises(ValueError):
        MODULE.compute_periodograms(samples, np.zeros(NWIN, bool), sfreq=250)
    with pytest.raises(ValueError):
        MODULE.compute_periodograms(samples, np.zeros(NWIN - 1, bool))


def test_internal_periodogram_uses_constant_detrend_and_periodic_hann() -> None:
    samples = _signals(NWIN) + 1000.0
    result = MODULE.compute_periodograms(samples, np.zeros(NWIN, bool))
    _, expected = periodogram(
        samples[:, 0],
        fs=FS,
        window=get_window("hann", NWIN, fftbins=True),
        nfft=NWIN,
        detrend="constant",
        return_onesided=True,
        scaling="density",
    )
    np.testing.assert_allclose(result["psd"][0, 0], expected[10:401], rtol=1e-12, atol=1e-12)


def _source_hdf5(path: Path, session: str, set_number: int, *, units: str = "V") -> None:
    """Synthetic Phase 1 artifact; no participant EEG is used in tests."""
    from Phase4_No1_FmTheta import EXPECTED_CHANNEL_NAMES

    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = 25 * FS + 1
    relative_time = np.arange(n_samples) / FS
    data_uv = np.zeros((n_samples, len(EXPECTED_CHANNEL_NAMES)), float)
    data_uv[:, EXPECTED_CHANNEL_NAMES.index("Pz")] = _signals(n_samples)[:, 0]
    data_uv[:, EXPECTED_CHANNEL_NAMES.index("Fz")] = _signals(n_samples)[:, 1]
    data = data_uv * (1e-6 if units == "V" else 1)
    utf8 = h5py.string_dtype("utf-8")
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            {
                "participant_id": session,
                "set_number": set_number,
                "data_kind": "brain_activity_eeg",
                "sampling_frequency_hz": FS,
                "signal_unit": units,
            }
        )
        handle.create_dataset("signal/data", data=data)
        handle.create_dataset(
            "signal/channel_names", data=np.asarray(EXPECTED_CHANNEL_NAMES, dtype=utf8)
        )
        handle.create_dataset("time/relative_seconds", data=relative_time)
        handle.create_dataset("time/OriginalTimestamp", data=1000 + relative_time)
        handle.create_dataset("qc/ica_training_excluded_mask", data=np.zeros(n_samples, bool))
        excluded = np.zeros(len(EXPECTED_CHANNEL_NAMES), bool)
        excluded[EXPECTED_CHANNEL_NAMES.index("Fz")] = True
        handle.create_dataset("qc/ica_channel_excluded_mask", data=excluded)
        handle.create_dataset("qc/ica_excluded_channel_records_json", data="[]", dtype=utf8)
        handle.create_dataset("qc/ica_training_exclusions_json", data="[]", dtype=utf8)


def _synthetic_session(tmp_path: Path, *, session: str = "101", units: str = "V") -> tuple:
    spec = MODULE.ParticipantSpec("101", "201", "201", "CCube")
    source = tmp_path / "source"
    cache = tmp_path / "cache"
    for set_number in range(1, 7):
        _source_hdf5(
            MODULE.input_path(source, session, set_number), session, set_number, units=units
        )
    return spec, source, cache


def test_cache_round_trip_halves_units_provenance_and_readonly_hash(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    cache_file, created = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    assert created
    assert cache_file.name.startswith("Pair101-201_01_ID101")
    fingerprint = MODULE.sha256_file(cache_file)
    MODULE.validate_cache(cache_file)
    with h5py.File(cache_file, "r") as handle:
        assert handle.attrs["schema"] == "phase4-iaf-localpeak-2026-11-10-v2"
        assert handle.attrs["condition"] == "Control"
        assert handle.attrs["product"] == "CCube"
        assert handle.attrs["calc_config_json"] == MODULE.config_json()
        assert handle.attrs["calc_config_sha256"] == MODULE.config_hash()
        assert len(json.loads(handle.attrs["sources_json"])) == 6
        np.testing.assert_allclose(handle["frequencies_hz"][:], FREQUENCIES)
        for number in range(1, 7):
            whole, first, second = [handle[f"Set{number}/{name}"] for name in ("whole", "a", "b")]
            assert first.attrs["stop_sample"] == second.attrs["start_sample"] == 3201
            assert second["starts"][0] == 3201
            assert whole.attrs["stop_sample"] == 6401
            assert whole["peaks/Pz"].attrs["frequency_hz"] == 10.2
            assert whole["peaks/Fz"].attrs["frequency_hz"] == 11.7
            assert np.isclose(whole["mean_psd"][0].sum() * 0.1, 2)
    same_file, created = MODULE.prepare_cache(spec, "101", source, cache, read_only=True)
    assert same_file == cache_file
    assert not created
    assert MODULE.sha256_file(cache_file) == fingerprint


def test_cache_accepts_microvolt_input_without_double_conversion(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path, units="µV")
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    with h5py.File(cache_file, "r") as handle:
        assert np.isclose(handle["Set1/whole/mean_psd"][0].sum() * 0.1, 2)


def test_figures_only_requires_existing_cache(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    with pytest.raises(FileNotFoundError):
        MODULE.prepare_cache(spec, "101", source, cache, read_only=True)
    assert not cache.exists()


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("schema", "phase4-iaf-2026-11-09.1"),
        ("calc_config_sha256", "invalid-digest"),
        ("complete", 0),
    ],
)
def test_cache_rejects_legacy_configuration_and_incomplete_files(
    tmp_path: Path, attribute: str, value: object
) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    with h5py.File(cache_file, "r+") as handle:
        handle.attrs[attribute] = value
    with pytest.raises((ValueError, AssertionError)):
        MODULE.validate_cache(cache_file)


def test_cache_rejects_changed_source_before_reuse(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    cache_hash = MODULE.sha256_file(cache_file)
    with h5py.File(MODULE.input_path(source, "101", 1), "r+") as handle:
        handle["signal/data"][0, 1] = 1e-4
    with pytest.raises(ValueError):
        MODULE.prepare_cache(spec, "101", source, cache, read_only=True)
    assert MODULE.sha256_file(cache_file) == cache_hash


@pytest.mark.parametrize("target", ["psd", "mean_psd", "n_valid_segments", "peak"])
def test_cache_rejects_corrupted_numerical_contents(tmp_path: Path, target: str) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    with h5py.File(cache_file, "r+") as handle:
        group = handle["Set1/whole"]
        if target == "psd":
            group["psd"][0, 0, 92] = -1.0
        elif target == "mean_psd":
            group["mean_psd"][0, 92] = 1e6
        elif target == "n_valid_segments":
            group["n_valid_segments"][0] = 999
        else:
            group["peaks/Pz"].attrs["frequency_hz"] = 14.9
    with pytest.raises((ValueError, AssertionError)):
        MODULE.validate_cache(cache_file)


@pytest.mark.parametrize(
    "bad_field", ["sampling_frequency_hz", "signal_unit", "time", "backward_original_time"]
)
def test_input_invalid_fs_units_or_time_are_not_silently_assumed(
    tmp_path: Path, bad_field: str
) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    with h5py.File(MODULE.input_path(source, "101", 1), "r+") as handle:
        if bad_field == "sampling_frequency_hz":
            handle.attrs[bad_field] = 250
        elif bad_field == "signal_unit":
            handle.attrs[bad_field] = "arbitrary"
        elif bad_field == "time":
            handle["time/relative_seconds"][5] += 0.01
        else:
            handle["time/OriginalTimestamp"][5] -= 0.01
    with pytest.raises((ValueError, AssertionError)):
        MODULE.prepare_cache(spec, "101", source, cache, read_only=False)


def test_wireless_timestamp_jitter_does_not_replace_verified_sample_clock(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    with h5py.File(MODULE.input_path(source, "101", 1), "r+") as handle:
        timestamp = handle["time/OriginalTimestamp"][:]
        timestamp[500:] += 0.25
        handle["time/OriginalTimestamp"][:] = timestamp
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    with h5py.File(cache_file, "r") as handle:
        assert handle["Set1/b"].attrs["start_sample"] == 3201
        assert handle["Set1/whole"].attrs["duration_seconds"] == 6401 / FS
        assert handle["Set1/whole/peaks/Pz"].attrs["frequency_hz"] == 10.2


def test_ica_excluded_flag_is_retained_without_excluding_available_signal(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    rows = MODULE.rows_from_cache(cache_file)
    assert [len(rows[number]) for number in (8, 9, 10, 11)] == [6, 12, 6, 12]
    assert all(not row["ica_channel_excluded"] for row in rows[8])
    assert all(row["ica_channel_excluded"] for row in rows[10])
    assert all(row["quality"] == "ok" and row["frequency_hz"] == 11.7 for row in rows[10])
    assert [row["position"] for row in rows[9]] == list(range(1, 13))
    assert [row["interval"] for row in rows[9]] == ["a", "b"] * 6
    assert MODULE.validate_rows(rows[10], 10, 1)["retained_ica_excluded_channel_rows"] == 6


def test_missing_set_only_blanks_affected_session_not_its_paired_control(tmp_path: Path) -> None:
    spec = MODULE.ParticipantSpec("109", "209", "109", "VRohtoPremium")
    source, cache = tmp_path / "source", tmp_path / "cache"
    for session in ("109", "209"):
        for number in range(1, 7):
            if session == "109" and number == 1:
                continue
            _source_hdf5(MODULE.input_path(source, session, number), session, number)
    first_path, _ = MODULE.prepare_cache(spec, "109", source, cache, read_only=False)
    second_path, _ = MODULE.prepare_cache(spec, "209", source, cache, read_only=False)
    first, second = MODULE.rows_from_cache(first_path), MODULE.rows_from_cache(second_path)
    for number in (8, 9, 10, 11):
        first_set = [row for row in first[number] if row["set_number"] == 1]
        partner_set = [row for row in second[number] if row["set_number"] == 1]
        assert len(first_set) == (1 if number in (8, 10) else 2)
        assert all(row["quality"] == "missing_set" for row in first_set)
        assert all(np.isnan(row["frequency_hz"]) for row in first_set)
        assert all(row["quality"] == "ok" for row in partner_set)
        assert all(np.isfinite(row["frequency_hz"]) for row in partner_set)
        MODULE.validate_rows(first[number] + second[number], number, 2)


def test_unknown_missing_set_is_not_silently_accepted(tmp_path: Path) -> None:
    spec = MODULE.ParticipantSpec("101", "201", "201", "CCube")
    source, cache = tmp_path / "source", tmp_path / "cache"
    for number in range(2, 7):
        _source_hdf5(MODULE.input_path(source, "101", number), "101", number)
    with pytest.raises(ValueError, match="unexpected missing Sets"):
        MODULE.prepare_cache(spec, "101", source, cache, read_only=False)


def test_code_provenance_change_alone_does_not_invalidate_calculation_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    cache_file, _ = MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    before_hash = MODULE.sha256_file(cache_file)
    before_config = MODULE.config_hash()
    monkeypatch.setattr(MODULE, "VERSION", "figure-only-change-for-test")
    assert MODULE.config_hash() == before_config
    same_path, created = MODULE.prepare_cache(spec, "101", source, cache, read_only=True)
    assert same_path == cache_file and not created
    assert MODULE.sha256_file(cache_file) == before_hash


def test_cache_rejects_wrong_condition_mapping(tmp_path: Path) -> None:
    spec, source, cache = _synthetic_session(tmp_path)
    MODULE.prepare_cache(spec, "101", source, cache, read_only=False)
    swapped_spec = MODULE.ParticipantSpec("101", "201", "101", "CCube")
    with pytest.raises(ValueError, match="cache attribute"):
        MODULE.prepare_cache(swapped_spec, "101", source, cache, read_only=True)
