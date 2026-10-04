from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import h5py
import numpy as np

SCRIPT = Path(__file__).parents[1] / "解析プログラム" / "Phase4_脳波解析" / "Phase4_No1_FmTheta.py"
SPEC = importlib.util.spec_from_file_location("phase4_fmtheta", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _source_hdf5(path: Path, session_id: str, set_number: int, *, frequency: float = 6.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = 513
    time = np.arange(n_samples) / MODULE.SFREQ
    signal_uv = np.sin(2 * np.pi * frequency * time)[:, None]
    weights = np.linspace(1.0, 2.0, len(MODULE.EXPECTED_CHANNEL_NAMES))[None, :]
    signal_v = signal_uv * weights * 1e-6
    utf8 = h5py.string_dtype("utf-8")
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            {
                "participant_id": session_id,
                "set_number": set_number,
                "data_kind": "brain_activity_eeg",
                "sampling_frequency_hz": MODULE.SFREQ,
                "signal_unit": "V",
            }
        )
        signal = handle.create_group("signal")
        signal.create_dataset("data", data=signal_v.astype(np.float32))
        signal.create_dataset(
            "channel_names", data=np.asarray(MODULE.EXPECTED_CHANNEL_NAMES, dtype=utf8)
        )
        times = handle.create_group("time")
        times.create_dataset("relative_seconds", data=time)
        times.create_dataset("OriginalTimestamp", data=1_000.0 + time)
        qc = handle.create_group("qc")
        mask = np.zeros(n_samples, dtype=bool)
        mask[100:200] = True
        qc.create_dataset("ica_training_excluded_mask", data=mask)
        qc.create_dataset(
            "ica_channel_excluded_mask",
            data=np.zeros(len(MODULE.EXPECTED_CHANNEL_NAMES), dtype=bool),
        )
        qc.create_dataset("ica_excluded_channel_records_json", data="[]", dtype=utf8)
        qc.create_dataset("ica_training_exclusions_json", data="[]", dtype=utf8)


def test_participant_mapping_and_cache_name_preserve_visit_order(tmp_path: Path):
    spec = MODULE.ParticipantSpec("101", "201", "201", "CCube")
    assert spec.control_session_id == "101"
    assert MODULE.cache_path(tmp_path, spec, "101").name.startswith("Pair101-201_01_ID101")
    assert MODULE.cache_path(tmp_path, spec, "201").name.startswith("Pair101-201_02_ID201")


def test_window_centers_include_both_set_edges():
    assert MODULE.window_centers(513).tolist() == [0, 256, 512]
    assert MODULE.window_centers(500).tolist() == [0, 256, 499]


def test_set_psd_uses_exact_bins_units_progress_and_mask_fraction():
    n_samples = 513
    time = np.arange(n_samples) / MODULE.SFREQ
    signal = np.sin(2 * np.pi * 6.0 * time)[:, None]
    data_v = np.repeat(signal, len(MODULE.EXPECTED_CHANNEL_NAMES), axis=1) * 1e-6
    mask = np.zeros(n_samples, dtype=bool)
    mask[:129] = True
    result = MODULE.calculate_set_psd(data_v, time, 10_000 + time, mask, 3)
    assert result.psd_band_mean.shape == (3, 32)
    assert np.all(result.psd_band_mean >= 0)
    assert result.source_center_sample.tolist() == [0, 256, 512]
    assert np.allclose(result.set_progress_pct, [0, 50, 100])
    assert np.allclose(result.global_progress_pct, [200, 250, 300])
    assert np.isclose(result.relative_seconds_center[-1], 2.0)
    assert result.ica_training_mask_fraction[1] > 0


def test_centered_nanmean_ignores_nan_and_preserves_all_nan_windows():
    values = np.array([1.0, np.nan, 3.0, np.nan, np.nan, np.nan, 7.0])
    smoothed = MODULE.centered_nanmean(values, 3)
    assert np.allclose(smoothed[:3], [1.0, 2.0, 3.0], equal_nan=True)
    assert np.isnan(smoothed[4])
    assert np.isclose(smoothed[-1], 7.0)


def test_timecourse_uses_sixty_seconds_and_grand_axis_override_is_explicit():
    assert MODULE.TIMECOURSE_SMOOTHING_SECONDS == 60
    assert MODULE.DEFAULT_GRAND_AVERAGE_TARGET_FRACTION == 0.75
    standard = MODULE.downstream_configuration()
    current_rerender = MODULE.downstream_configuration(0.95, "mean")
    assert standard["timecourse_smoothing"]["seconds"] == 60
    assert standard["quantification_smoothing"] == "none"
    assert standard["topography_smoothing"] == "none"
    assert standard["grand_average_y_axis"]["target_fraction"] == 0.75
    assert standard["grand_average_y_axis"]["basis"] == "maximum_mean_plus_sem"
    assert current_rerender["grand_average_y_axis"]["target_fraction"] == 0.95
    assert current_rerender["grand_average_y_axis"]["basis"] == "maximum_mean"
    upper, ticks = MODULE._nice_upper(np.array([46.78]), 0.95)
    assert upper == 50.0
    assert ticks[-1] == 50.0
    exact_upper = 26.803261 / 0.95
    exact_ticks = MODULE._nice_ticks_below_upper(exact_upper)
    assert np.isclose(26.803261 / exact_upper, 0.95)
    assert exact_ticks[-1] == 25.0


def test_progress_interpolation_does_not_bridge_all_nan_gap():
    source_x = np.array([0.0, 20.0, 40.0, 60.0, 80.0, 100.0])
    source_y = np.array([1.0, 2.0, np.nan, np.nan, 5.0, 6.0])
    target_x = np.arange(0.0, 101.0, 10.0)
    result = MODULE._interpolate_finite_runs(source_x, source_y, target_x)
    assert np.isfinite(result[:3]).all()
    assert np.isnan(result[3:8]).all()
    assert np.isfinite(result[8:]).all()


def test_preflight_accepts_only_the_declared_missing_set(tmp_path: Path):
    spec = MODULE.ParticipantSpec("109", "209", "109", "CCube")
    for session_id in ("109", "209"):
        for set_number in range(1, MODULE.N_SETS + 1):
            if session_id == "109" and set_number == 1:
                continue
            _source_hdf5(
                MODULE.input_path(tmp_path, session_id, set_number), session_id, set_number
            )
    result = MODULE.preflight_inputs([spec], tmp_path)
    assert result["checked_files"] == 11
    assert result["missing_by_session"] == {"109": [1]}


def test_cache_roundtrip_and_hash_validation(tmp_path: Path):
    input_root = tmp_path / "input"
    cache_root = tmp_path / "cache"
    spec = MODULE.ParticipantSpec("101", "201", "101", "VRohtoPremium")
    for set_number in range(1, MODULE.N_SETS + 1):
        _source_hdf5(MODULE.input_path(input_root, "101", set_number), "101", set_number)
    record = MODULE.compute_session_cache(spec, "101", input_root, cache_root)
    assert record["status"] == "computed"
    destination = Path(record["path"])
    validation = MODULE.validate_cache(destination, record["hash"])
    assert validation["ok"]
    loaded = MODULE.load_session_cache(destination)
    assert loaded.session_id == "101"
    assert loaded.condition == "Eye Drop"
    assert sorted(loaded.sets) == [1, 2, 3, 4, 5, 6]
    excluded = (
        loaded.sets[1].ica_training_mask_fraction >= MODULE.PSD_MASK_OVERLAP_THRESHOLD
    )
    assert excluded.any()
    assert np.isnan(loaded.sets[1].psd_band_mean[excluded]).all()
    assert np.isfinite(loaded.sets[1].psd_band_mean[~excluded]).all()
    with h5py.File(destination, "r") as handle:
        assert handle["sets/Set1/psd_band_mean"].dtype == np.dtype("float32")
        assert np.isfinite(handle["sets/Set1/psd_band_mean"][:]).all()
        assert json.loads(handle.attrs["included_frequencies_hz"]) == [4.0, 5.0, 6.0, 7.0]
    reused = MODULE.compute_session_cache(spec, "101", input_root, cache_root)
    assert reused["status"] == "reused"


def test_missing_set_is_symmetric_for_group_but_not_individual():
    channels = MODULE.EXPECTED_CHANNEL_NAMES

    def session(session_id: str, missing: set[int]) -> object:
        sets = {}
        for set_number in range(1, 7):
            if set_number in missing:
                continue
            progress = np.array([0.0, 100.0])
            sets[set_number] = MODULE.SetPSD(
                set_number,
                np.full((2, len(channels)), float(set_number)),
                np.array([0.0, 1.0]),
                np.array([0.0, 1.0]),
                progress,
                (set_number - 1) * 100.0 + progress,
                np.array([0, 256]),
                np.zeros(2),
            )
        return MODULE.SessionPSD(
            session_id, "", "109-209", "CCube", channels, sets, np.zeros(32, dtype=bool)
        )

    spec = MODULE.ParticipantSpec("109", "209", "109", "CCube")
    item = {
        "spec": spec,
        "product_dir": "CCube",
        "eye_drop": session("109", {1}),
        "control": session("209", set()),
    }
    individual_control = MODULE.interpolate_session_progress(item["control"])
    assert np.isfinite(individual_control[0]).all()
    symmetric_missing = {1}
    grouped_control = MODULE.interpolate_session_progress(
        item["control"], symmetrically_missing_sets=symmetric_missing
    )
    assert np.isnan(grouped_control[0]).all()
    topology = MODULE.pair_topography_values(item)
    assert np.isnan(topology[0]).all()


def test_all_sets_quantification_pools_windows_not_set_means():
    channels = MODULE.EXPECTED_CHANNEL_NAMES
    fz = channels.index("Fz")

    def make_session(session_id: str, condition: str, first: float, second: float):
        sets = {}
        for set_number, values in ((1, [first]), (2, [second, second, second])):
            matrix = np.zeros((len(values), len(channels)))
            matrix[:, fz] = values
            progress = np.linspace(0, 100, len(values)) if len(values) > 1 else np.array([0.0])
            sets[set_number] = MODULE.SetPSD(
                set_number,
                matrix,
                progress,
                progress,
                progress,
                (set_number - 1) * 100 + progress,
                np.arange(len(values)),
                np.zeros(len(values)),
            )
        return MODULE.SessionPSD(
            session_id, condition, "101-201", "CCube", channels, sets, np.zeros(32, bool)
        )

    spec = MODULE.ParticipantSpec("101", "201", "101", "CCube")
    item = {
        "spec": spec,
        "product_dir": "CCube",
        "eye_drop": make_session("101", "Eye Drop", 1.0, 5.0),
        "control": make_session("201", "Control", 2.0, 6.0),
    }
    frame = MODULE.build_quantification([item], "CCube")
    overall = frame.loc[frame["Set"] == "All Sets"].iloc[0]
    assert np.isclose(overall["EyeDrop_PSD_uV2_per_Hz"], 4.0)
    assert np.isclose(overall["Control_PSD_uV2_per_Hz"], 5.0)


def test_topography_is_channelwise_set_mean_eye_drop_minus_control():
    channels = MODULE.EXPECTED_CHANNEL_NAMES
    n_channels = len(channels)

    def make_session(session_id: str, condition: str, offset: float):
        base = np.arange(n_channels, dtype=float)
        matrix = np.vstack([base + offset, base + offset + 2.0, np.full(n_channels, np.nan)])
        set_data = MODULE.SetPSD(
            1,
            matrix,
            np.array([0.0, 0.5, 1.0]),
            np.array([1_000.0, 1_000.5, 1_001.0]),
            np.array([0.0, 50.0, 100.0]),
            np.array([0.0, 50.0, 100.0]),
            np.array([0, 128, 256]),
            np.array([0.0, 0.0, 1.0]),
        )
        return MODULE.SessionPSD(
            session_id,
            condition,
            "101-201",
            "CCube",
            channels,
            {1: set_data},
            np.zeros(n_channels, dtype=bool),
        )

    item = {
        "spec": MODULE.ParticipantSpec("101", "201", "101", "CCube"),
        "product_dir": "CCube",
        "eye_drop": make_session("101", "Eye Drop", 5.0),
        "control": make_session("201", "Control", 1.0),
    }
    values = MODULE.pair_topography_values(item)
    assert np.allclose(values[0], np.full(n_channels, 4.0))
    assert np.isnan(values[1:]).all()
    assert MODULE._nice_symmetric_topography_limit(np.array([-28.33, 12.0])) == 40.0


def test_complete_figure_and_table_outputs_are_generated_from_cached_values(tmp_path: Path):
    channels = MODULE.EXPECTED_CHANNEL_NAMES

    def make_session(session_id: str, condition: str, pair_id: str, offset: float):
        sets = {}
        for set_number in range(1, 7):
            progress = np.array([0.0, 50.0, 100.0])
            base = np.linspace(1.0, 2.0, len(channels)) + offset + set_number * 0.1
            matrix = np.vstack([base, base * 1.1, base * 0.9])
            sets[set_number] = MODULE.SetPSD(
                set_number,
                matrix,
                progress,
                1_000.0 + progress,
                progress,
                (set_number - 1) * 100.0 + progress,
                np.array([0, 128, 256]),
                np.zeros(3),
            )
        return MODULE.SessionPSD(
            session_id,
            condition,
            pair_id,
            "CCube",
            channels,
            sets,
            np.zeros(32, dtype=bool),
        )

    items = []
    for pair_number in (1,):
        first = str(100 + pair_number)
        second = str(200 + pair_number)
        spec = MODULE.ParticipantSpec(first, second, first, "CCube")
        items.append(
            {
                "spec": spec,
                "product_dir": "CCube",
                "eye_drop": make_session(first, "Eye Drop", spec.pair_id, 0.2 + pair_number),
                "control": make_session(second, "Control", spec.pair_id, float(pair_number)),
            }
        )
    individual = MODULE.write_individual_outputs(items[0], tmp_path)
    group = MODULE.write_group_outputs(items, tmp_path)
    assert all(Path(path).is_file() for path in individual.values())
    assert Path(individual["individual_unsmoothed"]).parent.name == "Unsmoothed"
    assert all(Path(path).is_file() for path in group["CCube"].values())
    statistics = (
        tmp_path
        / "Phase4_脳波解析"
        / "No1_FmTheta"
        / "CCube"
        / "SetQuantification"
        / "No1_FmTheta_SetQuantification_Statistics_CCube.csv"
    )
    frame = MODULE.pd.read_csv(statistics)
    assert frame["Set"].tolist() == [1, 2, 3, 4, 5, 6]
    assert {
        "P_value_raw",
        "P_value_Bonferroni",
        "P_value_Holm",
        "P_value_FDR_BH",
    }.issubset(frame.columns)
    grand_average = MODULE.pd.read_csv(
        tmp_path
        / "Phase4_脳波解析"
        / "No1_FmTheta"
        / "Sub"
        / "tables"
        / "GrandAverage"
        / "No1_FmTheta_GrandAverage_Values_CCube.csv"
    )
    assert (grand_average["EyeDrop_N"] == 1).all()
    assert grand_average["EyeDrop_SEM_PSD_uV2_per_Hz"].isna().all()
