from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

SCRIPT = (
    Path(__file__).parents[1]
    / "解析プログラム"
    / "Phase2_行動データ解析"
    / "Phase2_No1_ReactionTime.py"
)
SPEC = importlib.util.spec_from_file_location("phase2_no1", SCRIPT)
assert SPEC and SPEC.loader
phase2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phase2
SPEC.loader.exec_module(phase2)


def test_gaussian_moving_average_preserves_length_and_constant_values() -> None:
    values = np.full(320, 500.0)
    values[100] = np.nan
    smoothed = phase2.gaussian_moving_average(values)
    assert len(smoothed) == 320
    assert np.allclose(smoothed, 500.0)


def test_gaussian_moving_average_uses_fixed_edge_support() -> None:
    values = np.arange(1.0, 321.0)
    sigma = phase2.GAUSSIAN_SIGMA
    expected_first = np.average(values[:10], weights=np.exp(-0.5 * (np.arange(10) / sigma) ** 2))
    expected_eleventh = np.average(
        values[:20], weights=np.exp(-0.5 * ((np.arange(20) - 10) / sigma) ** 2)
    )
    result = phase2.gaussian_moving_average(values)
    assert result[0] == pytest.approx(expected_first)
    assert result[10] == pytest.approx(expected_eleventh)


def _write_results(path: Path, set_number: int, rt: np.ndarray) -> None:
    onset = np.arange(320, dtype=float) * 2_000.0
    frame = pd.DataFrame(
        {
            "Trial": np.arange(1, 321),
            "TiltOnset(ms)": onset,
            "KeyPress(ms)": onset + rt,
            "RT(ms)": rt,
            "ResponseType": "correct",
            "Block": set_number,
        }
    )
    frame.to_csv(path, index=False)


def test_process_session_recomputes_rt_and_keeps_outlier_position(tmp_path: Path) -> None:
    session = tmp_path / "101"
    session.mkdir()
    for set_number in range(1, 7):
        rt = np.full(320, 500.0)
        if set_number == 3:
            rt[49] = 5_000.0
        _write_results(session / f"101_block{set_number}_results.csv", set_number, rt)

    result = phase2.process_session(tmp_path, "101", "目薬あり", "VRohtoPremium")
    assert len(result.trials) == 1920
    assert result.outlier_count == 1
    target = result.trials.loc[(result.trials["Set"] == 3) & (result.trials["Trial"] == 50)].iloc[0]
    assert np.isnan(target["RT_clean_ms"])
    assert np.isfinite(target["RT_smoothed_ms"])
    assert result.rt_match == "一致"
    assert phase2.OUTLIER_SD == 2.0
    assert result.lower_2sd_ms < result.mean_rt_ms < result.upper_2sd_ms


def test_parse_participant_and_product_aliases() -> None:
    spec = phase2.parse_participant("101:201:101:Vロート")
    assert spec.first_session_id == "101"
    assert spec.second_session_id == "201"
    assert spec.pair_id == "101-201"
    assert spec.drops_session_id == "101"
    assert spec.control_session_id == "201"
    assert spec.eye_drops_visit == "1回目"
    assert phase2.normalize_product(spec.product)[0] == "VRohtoPremium"


def test_outputs_are_grouped_by_participant_pair(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    for session_id in ("101", "201"):
        session = raw_root / session_id
        session.mkdir(parents=True)
        for set_number in range(1, 7):
            _write_results(
                session / f"{session_id}_block{set_number}_results.csv",
                set_number,
                np.full(320, 500.0 + int(session_id)),
            )
    spec = phase2.parse_participant("101:201:101:VRohtoPremium")
    result = phase2.run_participant(raw_root, tmp_path / "output", spec)
    output_dir = Path(result["outputs"]["directory"])
    assert output_dir.name == "ID101-201"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "ID101-201_No1_RT_Individual.png",
        "ID101-201_No1_RT_QC.csv",
        "ID101-201_No1_RT_RunSummary.json",
        "ID101-201_No1_RT_TrialData.csv",
    ]
