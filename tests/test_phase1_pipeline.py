from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

MODULE_DIR = Path(__file__).parents[1] / "解析プログラム" / "Phase1_脳波前処理"
sys.path.insert(0, str(MODULE_DIR))

from phase1_pipeline import (  # noqa: E402
    CHANNELS,
    EegPart,
    SetBoundary,
    derive_boundaries,
    detect_flatlines,
    infomax_convergence_diagnostics,
    resolve_bad_channel_decisions,
    save_interactive_html,
    save_set_hdf5,
    select_notification_candidates,
    validate_hdf5,
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


def test_flatline_requires_thirty_seconds() -> None:
    rng = np.random.default_rng(97)
    data = rng.normal(size=(32, 40 * 256)) * 1e-6
    data[0, : 29 * 256] = 0
    data[1, : 31 * 256] = 0
    candidates = detect_flatlines(data)
    assert [candidate["channel"] for candidate in candidates] == [CHANNELS[1]]


def test_channel_notification_is_more_conservative_than_exploratory_detection() -> None:
    exploratory = [
        {
            "channel": "PO9",
            "reason": "ransac_correlation_below_0.80_for_over_50pct",
            "recording_fraction": 0.55,
        },
        {
            "channel": "O2",
            "reason": "line_noise_above_4sd",
            "z_score": 4.5,
        },
        {
            "channel": "F7",
            "reason": "ransac_correlation_below_0.80_for_over_50pct",
            "recording_fraction": 0.85,
        },
    ]
    notified = select_notification_candidates(exploratory)
    assert [item["channel"] for item in notified] == ["F7"]


def test_unapproved_channel_candidate_is_retained_without_stopping() -> None:
    decisions = resolve_bad_channel_decisions(
        [{"channel": "PO9", "reason": "clear_record_wide_problem"}], [], []
    )
    assert decisions["automatically_retained"] == ["PO9"]
    assert decisions["effective_retained"] == ["PO9"]
    assert decisions["per_channel"] == {"PO9": "retained_without_removal_approval"}


def test_bad_channel_decisions_are_independent_per_channel() -> None:
    candidates = [
        {"channel": "PO9", "reason": "clear_record_wide_problem"},
        {"channel": "O2", "reason": "clear_record_wide_problem"},
    ]
    decisions = resolve_bad_channel_decisions(candidates, ["O2"], ["PO9"])
    assert decisions["automatically_retained"] == []
    assert decisions["per_channel"] == {
        "O2": "removed_with_user_approval",
        "PO9": "retained_after_user_review",
    }


def test_interactive_html_contains_working_navigation_controls(tmp_path: Path) -> None:
    output = tmp_path / "qc.html"
    data = np.zeros((32, 512), dtype=float)
    save_interactive_html(output, "101", 1, data, data, CHANNELS)
    html = output.read_text(encoding="utf-8")
    assert 'id="zoomIn"' in html
    assert 'id="zoomOut"' in html
    assert 'id="reset"' in html
    assert "addEventListener('wheel'" in html
    assert "addEventListener('pointermove'" in html
    assert '"bin_samples":8' in html
    assert '"before_low"' in html
    assert '"before_high"' in html
    assert "表示準備完了" in html
    assert html.endswith("</body></html>")


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
        bad_intervals=[],
        data_kind="brain_activity_eeg",
    )
    result = validate_hdf5(output, expected_channels=32, expected_behavior_rows=1)
    assert result["ok"] is True
    assert result["signal_shape"] == (512, 32)


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
