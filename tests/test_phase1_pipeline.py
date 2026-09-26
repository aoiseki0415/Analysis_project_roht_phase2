from __future__ import annotations

import sys
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

MODULE_DIR = Path(__file__).parents[1] / "解析プログラム" / "Phase1_脳波前処理"
sys.path.insert(0, str(MODULE_DIR))

from phase1_pipeline import (  # noqa: E402
    ASR_BURST_CRITERION,
    CHANNELS,
    EYE_BLINK_PROBABILITY_THRESHOLD,
    FLATLINE_MINIMUM_SECONDS,
    ICA_AFTER_COLOR,
    ICA_BEFORE_COLOR,
    ICA_EXCLUSION_REVIEW_CODE,
    ICA_QC_GROUPS,
    PIPELINE_SPEC_VERSION,
    QC_FIGURE_STYLE_VERSION,
    RANDOM_SEED,
    RANSAC_AUTO_EXCLUSION_BAD_TIME_FRACTION,
    RANSAC_CANDIDATE_BAD_TIME_FRACTION,
    RANSAC_MIN_CORRELATION,
    SPLIT_EXCLUSIONS,
    SPLIT_PART_SETS,
    EegPart,
    ProjectPaths,
    SetBoundary,
    _set_markers_for_part,
    absolute_amplitude_intervals,
    build_ica_channel_exclusion_records,
    derive_boundaries,
    detect_flatlines,
    extract_blink_analysis_signal,
    infomax_convergence_diagnostics,
    merge_ica_cleaned_channels,
    save_blink_signal_figure,
    save_ica_exclusion_review_html,
    save_interactive_html,
    save_set_hdf5,
    select_ica_channel_exclusion_candidates,
    validate_hdf5,
    write_audit_outputs,
)


def test_derive_boundaries_uses_original_timestamp() -> None:
    timestamp = 1_700_000_000 + np.arange(2_000) / 256
    part = EegPart(
        part=1,
        path=Path("input.csv"),
        metadata="",
        original_timestamp=timestamp,
        interpolated=np.zeros(2_000, dtype=np.float32),
        data_uv=np.zeros((32, 2_000), dtype=np.float32),
    )
    rows = []
    for set_number in range(1, 7):
        start = float(timestamp[100 + set_number * 200] * 1000)
        end = float(timestamp[199 + set_number * 200] * 1000)
        rows.extend(
            [
                {"SysUnixTime(ms)": start, "Event": "block_start", "Detail": set_number},
                {"SysUnixTime(ms)": end, "Event": "block_end", "Detail": set_number},
            ]
        )
    boundaries = derive_boundaries("101", [part], pd.DataFrame(rows))
    assert [boundary.set_number for boundary in boundaries] == list(range(1, 7))
    assert all(boundary.usable and boundary.part == 1 for boundary in boundaries)
    assert boundaries[0].start_sample == 300
    assert boundaries[0].end_sample == 400


def test_all_four_split_ids_use_fixed_five_set_mapping() -> None:
    expected = {
        "109": {2: 2, 3: 2, 4: 2, 5: 2, 6: 2},
        "120": {1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
        "135": {1: 1, 3: 2, 4: 2, 5: 2, 6: 2},
        "225": {1: 1, 2: 1, 3: 1, 5: 2, 6: 2},
    }
    assert SPLIT_PART_SETS == expected
    assert SPLIT_EXCLUSIONS == {
        "109": {1},
        "120": {6},
        "135": {2},
        "225": {4},
    }
    assert all(len(mapping) == 5 for mapping in SPLIT_PART_SETS.values())


def test_pipeline_reproducibility_identifiers_are_fixed() -> None:
    assert PIPELINE_SPEC_VERSION == "phase1-parameter-update-2026-09-26.1"
    assert RANDOM_SEED == 97
    assert QC_FIGURE_STYLE_VERSION == "phase1-qc-v2"
    assert ICA_BEFORE_COLOR == "#1261a0"
    assert ICA_AFTER_COLOR == "#d1495b"


def test_audit_can_write_onedrive_only_without_local_manifest(tmp_path: Path) -> None:
    paths = ProjectPaths(
        raw_root=tmp_path / "raw",
        eeg_root=tmp_path / "raw" / "eeg",
        behavior_root=tmp_path / "raw" / "behavior",
        processed_root=tmp_path / "processed",
        onedrive_root=tmp_path / "onedrive",
    )
    audit = {
        "manifest": {
            "parts": [{"part": 1, "sample_count": 256}],
            "sets": [{"set_number": 1, "usable": True}],
        }
    }
    local_path, qc_path = write_audit_outputs(
        paths,
        "102",
        audit,
        save_local_manifest=False,
    )
    assert local_path is None
    assert qc_path.exists()
    assert not paths.processed_root.exists()


def test_flatline_requires_five_seconds() -> None:
    rng = np.random.default_rng(97)
    data = rng.normal(size=(32, 10 * 256)) * 1e-6
    data[0, : 4 * 256] = 0
    data[1, : 6 * 256] = 0
    candidates = detect_flatlines(data)
    assert [candidate["channel"] for candidate in candidates] == [CHANNELS[1]]


def test_channel_notification_is_more_conservative_than_exploratory_detection() -> None:
    exploratory = [
        {
            "channel": "PO9",
            "reason": "ransac_correlation_below_0.75_for_over_40pct",
            "recording_fraction": 0.45,
        },
        {
            "channel": "O2",
            "reason": "line_noise_above_4sd",
            "z_score": 4.5,
        },
        {
            "channel": "F7",
            "reason": "ransac_correlation_below_0.75_for_over_40pct",
            "recording_fraction": 0.65,
        },
    ]
    notified = select_ica_channel_exclusion_candidates(exploratory)
    assert [item["channel"] for item in notified] == ["F7"]


def test_updated_artifact_detection_parameters_are_fixed() -> None:
    assert FLATLINE_MINIMUM_SECONDS == 5.0
    assert RANSAC_MIN_CORRELATION == 0.75
    assert RANSAC_CANDIDATE_BAD_TIME_FRACTION == 0.40
    assert RANSAC_AUTO_EXCLUSION_BAD_TIME_FRACTION == 0.60
    assert ASR_BURST_CRITERION == 15.0


def test_bad_channel_candidates_are_automatically_excluded_from_ica_only() -> None:
    candidates = [
        {"channel": "PO9", "reason": "clear_record_wide_problem"},
        {"channel": "O2", "reason": "clear_record_wide_problem"},
    ]
    excluded, records = build_ica_channel_exclusion_records(candidates)
    assert excluded == ["PO9", "O2"]
    assert [record["channel"] for record in records] == excluded
    assert all(
        record["decision"] == "automatically_excluded_from_ica_training_only" for record in records
    )


def test_qc_channel_groups_have_fixed_order_and_blink_group() -> None:
    assert ICA_QC_GROUPS == (
        ("QC01_BlinkCheck", ("Fp1", "Fp2")),
        ("QC02_Frontal", ("Fz", "F3", "F4")),
        ("QC03_CentralTemporal", ("Cz", "T7", "T8")),
        ("QC04_ParietalOccipital", ("Pz", "O1", "O2")),
    )


def test_split_set_markers_are_assigned_independently_to_each_part() -> None:
    part1 = EegPart(
        1,
        Path("part1.csv"),
        "",
        np.linspace(100.0, 110.0, 2561),
        np.zeros(2561),
        np.zeros((32, 2561)),
    )
    part2 = EegPart(
        2,
        Path("part2.csv"),
        "",
        np.linspace(120.0, 130.0, 2561),
        np.zeros(2561),
        np.zeros((32, 2561)),
    )
    events = pd.DataFrame(
        [
            {"SysUnixTime(ms)": 105_000, "Event": "block_start", "Detail": 2},
            {"SysUnixTime(ms)": 125_000, "Event": "block_end", "Detail": 2},
        ]
    )
    assert [marker["label"] for marker in _set_markers_for_part(events, part1)] == ["Set2 start"]
    assert [marker["label"] for marker in _set_markers_for_part(events, part2)] == ["Set2 end"]


def test_blink_signal_marks_ica_excluded_fp_channel_as_nan() -> None:
    included = [channel for channel in CHANNELS if channel != "Fp2"]
    contribution = np.ones((len(included), 128), dtype=float)
    blink = extract_blink_analysis_signal(contribution, included)
    assert np.isfinite(blink[0]).all()
    assert np.isnan(blink[1]).all()
    assert np.array_equal(blink[2], blink[0])


def test_interactive_html_contains_working_navigation_controls(tmp_path: Path) -> None:
    output = tmp_path / "qc.html"
    data = np.zeros((32, 512), dtype=float)
    save_interactive_html(
        output,
        "101",
        1,
        data,
        data,
        CHANNELS,
        ("Fp1", "Fp2"),
        100.0,
        [{"time_s": 1.0, "label": "Set1 start", "kind": "start", "usable": True}],
    )
    html = output.read_text(encoding="utf-8")
    assert 'id="zoomIn"' in html
    assert 'id="zoomOut"' in html
    assert 'id="yZoomIn"' in html
    assert 'id="yZoomOut"' in html
    assert 'id="yReset"' in html
    assert 'id="yScale"' in html
    assert 'id="reset"' in html
    assert 'id="staticFallback"' in html
    assert 'id="waveformPayload" type="application/json"' in html
    assert "JSON.parse(document.getElementById('waveformPayload').textContent)" in html
    assert "JavaScript initialization error:" in html
    assert '<svg role="img"' in html
    assert "Time from Part start (s)" in html
    assert "EEG amplitude (µV)" in html
    assert "document.getElementById('staticFallback').style.display='none'" in html
    assert "addEventListener('wheel'" in html
    assert "addEventListener('pointermove'" in html
    assert "addEventListener('keydown'" in html
    assert "addEventListener('keyup'" in html
    assert "setInterval(()=>pan(direction),80)" in html
    assert '"before"' in html
    assert '"after"' in html
    assert '"bin_samples"' not in html
    assert "256 Hzの元波形を保持" in html
    assert "baseSharedMax" in html
    assert "sharedYScale" in html
    assert "共通縦軸" in html
    assert '"shared_scale_uv":100.0' in html
    assert '"channels":["Fp1","Fp2"]' in html
    assert "Set1 start" in html
    assert "P.set_markers.forEach" in html
    assert ICA_BEFORE_COLOR in html
    assert ICA_AFTER_COLOR in html
    assert "__BEFORE_COLOR__" not in html
    assert "__AFTER_COLOR__" not in html
    assert "x軸の表示範囲を変えても縦軸は自動変更しません" in html
    assert "表示準備完了" in html
    assert html.endswith("</body></html>")


def test_ica_exclusion_review_html_shows_all_channels_intervals_and_channels(
    tmp_path: Path,
) -> None:
    output = tmp_path / "exclusion_review.html"
    data = np.zeros((32, 512), dtype=float)
    part = EegPart(
        part=1,
        path=Path("input.csv"),
        metadata="",
        original_timestamp=1_700_000_000 + np.arange(512) / 256,
        interpolated=np.zeros(512),
        data_uv=np.zeros((32, 512)),
    )
    save_ica_exclusion_review_html(
        output,
        "101",
        part,
        data,
        [
            {
                "part": 1,
                "start_sample": 128,
                "end_sample": 256,
                "reason": "AbsoluteAmplitude_500uV",
                "affected_channel_count": 1,
            }
        ],
        ["PO9"],
        [{"time_s": 1.0, "label": "Set1 start", "kind": "start"}],
    )
    html = output.read_text(encoding="utf-8")
    assert ICA_EXCLUSION_REVIEW_CODE == "QC05_ICAExclusionReview"
    assert '"channels":' in html
    assert all(f'"{channel}"' in html for channel in CHANNELS)
    assert '"before_only":true' in html
    assert '"excluded_channels":["PO9"]' in html
    assert '"reason":"AbsoluteAmplitude_500uV"' in html
    assert "ICA学習除外区間" in html
    assert "ICA学習除外ch" in html
    assert "[ICA除外]" in html
    assert '"after":' not in html


def test_absolute_amplitude_exclusion_adds_one_second_padding() -> None:
    data = np.zeros((32, 10 * 256), dtype=float)
    data[0, 5 * 256 : 5 * 256 + 2] = 0.001
    intervals = absolute_amplitude_intervals(data)
    assert intervals == [(4 * 256, 6 * 256 + 2, "AbsoluteAmplitude_200uV", 1)]


def test_eye_blink_probability_threshold_is_point_eight() -> None:
    assert EYE_BLINK_PROBABILITY_THRESHOLD == 0.80


def test_blink_signal_figure_uses_set_level_three_channel_input(tmp_path: Path) -> None:
    n_samples = 4 * 256
    boundary = SetBoundary(1, 0.0, 4_000.0, 1, 0, n_samples, True, "使用")
    output = tmp_path / "blink.png"
    signal_v = (
        np.vstack(
            [
                np.linspace(-20, 20, n_samples),
                np.linspace(-10, 10, n_samples),
                np.linspace(-15, 15, n_samples),
            ]
        )
        * 1e-6
    )
    save_blink_signal_figure(
        output,
        "101",
        boundary,
        signal_v,
        [
            {
                "part": 1,
                "start_sample": 100,
                "end_sample": 200,
                "reason": "test",
                "affected_channel_count": 1,
            }
        ],
    )
    assert output.exists()
    assert output.stat().st_size > 0


def test_hdf5_contains_signal_times_and_behavior(tmp_path: Path) -> None:
    n_samples = 512
    boundary = SetBoundary(1, 1.0, 3.0, 1, 0, n_samples, True, "使用")
    output = tmp_path / "ID101_Set1_brain_activity.h5"
    results_csv = "Trial,TiltOnsetSys(ms),KeyPressSys(ms)\n1,1000,1200\n"
    save_set_hdf5(
        output,
        participant_id="101",
        boundary=boundary,
        source_file=Path("source.csv"),
        data_v=np.zeros((32, n_samples)),
        channel_names=CHANNELS,
        original_timestamp=1_700_000_000 + np.arange(n_samples) / 256,
        results_csv=results_csv,
        results_rows=1,
        bad_intervals=[
            {
                "part": 1,
                "start_sample": 100,
                "end_sample": 200,
                "reason": "test",
                "affected_channel_count": 1,
            }
        ],
        original_channel_names=CHANNELS,
        ica_excluded_channels=[],
        ica_excluded_channel_records=[],
        data_kind="brain_activity_eeg",
    )
    result = validate_hdf5(output, expected_channel_names=CHANNELS, expected_behavior_rows=1)
    assert result["ok"] is True
    assert result["signal_shape"] == (512, 32)
    assert result["ica_training_excluded_mask_rows"] == 512
    assert result["channel_names_match"] is True
    assert result["ica_channel_excluded_mask_matches"] is True
    assert result["ica_excluded_channel_records_match"] is True
    assert result["fixed_channel_layout_ok"] is True


def test_ica_excluded_channel_is_retained_in_fixed_32_channel_hdf5(tmp_path: Path) -> None:
    n_samples = 256
    excluded_channel = "PO9"
    kept_channels = [channel for channel in CHANNELS if channel != excluded_channel]
    full_detrended = np.arange(32, dtype=float)[:, None] * np.ones((1, n_samples))
    reduced_cleaned = np.ones((len(kept_channels), n_samples), dtype=np.float64) * -1
    merged = merge_ica_cleaned_channels(full_detrended, reduced_cleaned, kept_channels, CHANNELS)
    excluded_index = CHANNELS.index(excluded_channel)
    assert merged.shape == (32, n_samples)
    assert np.array_equal(merged[excluded_index], full_detrended[excluded_index])
    assert np.isfinite(merged).all()

    output = tmp_path / "fixed_layout.h5"
    boundary = SetBoundary(1, 1.0, 2.0, 1, 0, n_samples, True, "使用")
    removed_records = [
        {
            "channel": excluded_channel,
            "decision": "automatically_excluded_from_ica_training_only",
            "reasons": [{"reason": "continuous_zero_or_exact_flatline"}],
        }
    ]
    save_set_hdf5(
        output,
        participant_id="test",
        boundary=boundary,
        source_file=Path("source.csv"),
        data_v=merged,
        channel_names=CHANNELS,
        original_timestamp=1_700_000_000 + np.arange(n_samples) / 256,
        results_csv="Trial\n",
        results_rows=0,
        bad_intervals=[],
        original_channel_names=CHANNELS,
        ica_excluded_channels=[excluded_channel],
        ica_excluded_channel_records=removed_records,
        data_kind="brain_activity_eeg",
    )
    result = validate_hdf5(output, CHANNELS, 0)
    assert result["ok"] is True
    assert result["signal_shape"] == (n_samples, 32)
    assert result["ica_channel_excluded_mask_matches"] is True
    assert result["ica_excluded_channel_records_match"] is True
    assert result["fixed_channel_layout_ok"] is True
    with h5py.File(output, "r") as handle:
        mask = handle["qc/ica_channel_excluded_mask"][:]
        saved = handle["signal/data"][:]
    assert mask.shape == (32,)
    assert bool(mask[excluded_index]) is True
    assert np.array_equal(saved[:, excluded_index], full_detrended[excluded_index])

    blink_output = tmp_path / "blink_with_excluded_fp2.h5"
    blink_signal = np.vstack([np.ones(n_samples), np.full(n_samples, np.nan), np.ones(n_samples)])
    fp2_record = [
        {
            "channel": "Fp2",
            "decision": "automatically_excluded_from_ica_training_only",
            "reasons": [{"reason": "continuous_zero_or_exact_flatline"}],
        }
    ]
    save_set_hdf5(
        blink_output,
        participant_id="test",
        boundary=boundary,
        source_file=Path("source.csv"),
        data_v=blink_signal,
        channel_names=["Fp1", "Fp2", "Fp1_Fp2_mean"],
        original_timestamp=1_700_000_000 + np.arange(n_samples) / 256,
        results_csv="Trial\n",
        results_rows=0,
        bad_intervals=[],
        original_channel_names=CHANNELS,
        ica_excluded_channels=["Fp2"],
        ica_excluded_channel_records=fp2_record,
        data_kind="removed_eye_component_signal",
    )
    blink_result = validate_hdf5(blink_output, ["Fp1", "Fp2", "Fp1_Fp2_mean"], 0)
    assert blink_result["ok"] is True
    with h5py.File(blink_output, "r") as handle:
        assert bool(handle["qc/ica_channel_excluded_mask"][CHANNELS.index("Fp2")]) is True


def test_infomax_weight_change_stop_is_recognized_when_mne_reports_max_iter() -> None:
    log = (
        "step 331 - lrate 0.000001, wchange 0.00000120, angledelta 1.0 deg\n"
        "step 332 - lrate 0.000001, wchange 0.00000087, angledelta 1.0 deg\n"
    )
    result = infomax_convergence_diagnostics(
        log,
        reported_n_iter=1000,
        max_iter=1000,
        weight_change_threshold=1e-6,
    )
    assert result["converged"] is True
    assert result["stop_reason"] == "weight_change"
    assert result["actual_iterations"] == 332
    assert result["final_weight_change"] == 8.7e-7


def test_infomax_max_iteration_without_threshold_is_not_converged() -> None:
    result = infomax_convergence_diagnostics(
        "step 1000 - lrate 0.000100, wchange 0.00001000, angledelta 1.0 deg\n",
        reported_n_iter=1000,
        max_iter=1000,
        weight_change_threshold=1e-6,
    )
    assert result["converged"] is False
    assert result["stop_reason"] == "max_iterations"
