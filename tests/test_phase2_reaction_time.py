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
    first_set = result.trials.loc[result.trials["Set"] == 1]
    sixth_set = result.trials.loc[result.trials["Set"] == 6]
    assert first_set["Progress_within_set_pct"].iloc[0] == pytest.approx(1.0)
    assert first_set["Progress_within_set_pct"].iloc[-1] == pytest.approx(100.0)
    assert sixth_set["Global_progress_pct"].iloc[-1] == pytest.approx(600.0)


def test_figure_y_upper_limit_places_maximum_near_seventy_percent() -> None:
    upper = phase2.figure_y_upper_limit(np.array([400.0, 1_350.0]))
    assert upper == 2_000.0
    assert 0.65 <= 1_350.0 / upper <= 0.70


def test_grand_figure_y_upper_limit_places_upper_sd_near_eighty_seven_percent() -> None:
    upper = phase2.grand_figure_y_upper_limit(
        np.array([400.0, 1_750.0]), "VRohtoPremium"
    )
    assert upper == 2_000.0
    assert 0.85 <= 1_750.0 / upper <= 0.90


def test_ccube_grand_figure_has_at_least_two_thousand_ms_headroom() -> None:
    upper = phase2.grand_figure_y_upper_limit(np.array([400.0, 1_350.0]), "CCube")
    assert upper == 2_000.0


def test_set_mean_figure_layout_is_fixed_and_centered() -> None:
    assert phase2.SET_MEAN_BAR_WIDTH == pytest.approx(0.42)
    assert phase2.SET_MEAN_BAR_CENTERS.tolist() == pytest.approx([-0.28, 0.28])
    assert phase2.SET_MEAN_DOT_SIZE == pytest.approx(150.0)
    assert phase2.SET_MEAN_JITTER_HALF_WIDTH == pytest.approx(0.055)
    assert phase2.SET_MEAN_X_LIMITS == pytest.approx((-0.90, 0.90))


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
    ]


def test_run_batch_can_record_and_skip_invalid_participant(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    valid = phase2.parse_participant("101:201:101:CCube")
    invalid = phase2.parse_participant("102:202:102:CCube")
    for session_id in ("101", "201"):
        session = raw_root / session_id
        session.mkdir(parents=True)
        for set_number in range(1, 7):
            _write_results(
                session / f"{session_id}_block{set_number}_results.csv",
                set_number,
                np.full(320, 500.0),
            )
    results, exclusions = phase2.run_batch(
        raw_root,
        tmp_path / "output",
        [valid, invalid],
        skip_invalid_participants=True,
    )
    assert [result["participant"].pair_id for result in results] == ["101-201"]
    assert exclusions[0]["pair_id"] == "102-202"
    assert "Behavior directory not found" in exclusions[0]["reason"]


def _synthetic_session(session_id: str, condition: str, values: np.ndarray) -> object:
    trials = pd.DataFrame(
        {
            "Set": np.repeat(np.arange(1, 7), 320),
            "Trial": np.tile(np.arange(1, 321), 6),
            "Global_progress_pct": np.concatenate(
                [
                    set_number * 100.0 + np.linspace(1.0, 100.0, 320)
                    for set_number in range(6)
                ]
            ),
            "RT_smoothed_ms": values,
        }
    )
    return phase2.SessionResult(
        session_id=session_id,
        condition=condition,
        product="VRohtoPremium",
        trials=trials,
        mean_rt_ms=float(np.mean(values)),
        sd_rt_ms=float(np.std(values, ddof=1)),
        lower_2sd_ms=0.0,
        upper_2sd_ms=0.0,
        outlier_count=0,
        outlier_trials="なし",
        valid_rt_count=len(values),
        rt_match="一致",
        source_notes="synthetic",
        eeg_missing_set=None,
    )


def test_grand_average_uses_individual_smoothed_values_and_writes_outputs(
    tmp_path: Path,
) -> None:
    values_a = np.full(1920, 500.0)
    values_b = np.full(1920, 700.0)
    specs = [
        phase2.parse_participant("101:201:101:VRohtoPremium"),
        phase2.parse_participant("102:202:102:VRohtoPremium"),
    ]
    results = [
        {
            "participant": specs[0],
            "drops": _synthetic_session("101", "目薬あり", values_a),
            "control": _synthetic_session("201", "コントロール", values_b),
        },
        {
            "participant": specs[1],
            "drops": _synthetic_session("102", "目薬あり", values_b),
            "control": _synthetic_session("202", "コントロール", values_a),
        },
    ]
    grand = phase2.build_grand_average(results, "VRohtoPremium")
    assert np.allclose(grand["EyeDrop_mean_RT_ms"], 600.0)
    assert np.allclose(grand["Control_mean_RT_ms"], 600.0)
    assert np.allclose(grand["EyeDrop_SD_RT_ms"], np.sqrt(20_000.0))
    assert np.all(grand["EyeDrop_N"] == 2)

    outputs = phase2.write_grand_average_outputs(tmp_path, results, "VRohtoPremium")
    output_dir = Path(outputs["directory"])
    assert output_dir.name == "GrandAverage"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "No1_RT_GrandAverage_VRohtoPremium.png",
        "No1_RT_GrandAverage_VRohtoPremium_RunSummary.json",
        "No1_RT_GrandAverage_VRohtoPremium_Values.csv",
    ]
    summary = pd.read_json(outputs["summary"], typ="series")
    assert summary["figure_y_axis_upper_ms"] == 900.0
    # At this deliberately low synthetic scale, 100-ms rounding is coarse.
    assert 0.80 <= summary["max_upper_sd_band_axis_ratio"] <= 0.90


def test_eeg_missing_set_is_masked_before_two_sd_and_smoothing(tmp_path: Path) -> None:
    session = tmp_path / "109"
    session.mkdir()
    for set_number in range(1, 7):
        rt = np.full(320, 500.0)
        if set_number == 1:
            rt[:] = 4_000.0
        _write_results(session / f"109_block{set_number}_results.csv", set_number, rt)

    result = phase2.process_session(tmp_path, "109", "目薬あり", "VRohtoPremium")
    missing = result.trials["Set"] == 1
    retained = result.trials["Set"] != 1
    assert result.eeg_missing_set == 1
    assert result.mean_rt_ms == pytest.approx(500.0)
    assert result.sd_rt_ms == pytest.approx(0.0)
    assert result.outlier_count == 0
    assert result.valid_rt_count == 1_600
    assert result.trials.loc[missing, "EEG_missing_set"].all()
    assert result.trials.loc[missing, "RT_raw_ms"].isna().all()
    assert result.trials.loc[missing, "RT_smoothed_ms"].isna().all()
    assert result.trials.loc[retained, "RT_smoothed_ms"].notna().all()


def test_grand_average_masks_both_conditions_for_pairwise_eeg_missing_set() -> None:
    values_a = np.full(1920, 500.0)
    values_b = np.full(1920, 700.0)
    spec_a = phase2.parse_participant("109:209:109:VRohtoPremium")
    spec_b = phase2.parse_participant("111:211:211:VRohtoPremium")
    drops_a = _synthetic_session("109", "目薬あり", values_a)
    control_a = _synthetic_session("209", "コントロール", values_b)
    drops_a.eeg_missing_set = 1
    drops_b = _synthetic_session("211", "目薬あり", values_b)
    control_b = _synthetic_session("111", "コントロール", values_a)
    results = [
        {"participant": spec_a, "drops": drops_a, "control": control_a},
        {"participant": spec_b, "drops": drops_b, "control": control_b},
    ]

    grand = phase2.build_grand_average(results, "VRohtoPremium")
    set1 = grand["Set"] == 1
    set2 = grand["Set"] == 2
    assert np.all(grand.loc[set1, "EyeDrop_N"] == 1)
    assert np.all(grand.loc[set1, "Control_N"] == 1)
    assert np.all(grand.loc[set2, "EyeDrop_N"] == 2)
    assert np.all(grand.loc[set2, "Control_N"] == 2)


def _synthetic_clean_session(
    session_id: str,
    condition: str,
    clean_values: np.ndarray,
    *,
    product: str = "VRohtoPremium",
    eeg_missing_set: int | None = None,
) -> object:
    trials = pd.DataFrame(
        {
            "Set": np.repeat(np.arange(1, 7), 320),
            "Trial": np.tile(np.arange(1, 321), 6),
            "RT_clean_ms": clean_values,
            "RT_smoothed_ms": np.full(1920, 9_999.0),
        }
    )
    return phase2.SessionResult(
        session_id=session_id,
        condition=condition,
        product=product,
        trials=trials,
        mean_rt_ms=float(np.nanmean(clean_values)),
        sd_rt_ms=float(np.nanstd(clean_values, ddof=1)),
        lower_2sd_ms=0.0,
        upper_2sd_ms=0.0,
        outlier_count=int(np.isnan(clean_values).sum()),
        outlier_trials="synthetic",
        valid_rt_count=int(np.isfinite(clean_values).sum()),
        rt_match="一致",
        source_notes="synthetic",
        eeg_missing_set=eeg_missing_set,
    )


def test_set_mean_quantification_uses_clean_trial_rt_not_smoothed_rt() -> None:
    drops_values = np.repeat(np.arange(1, 7, dtype=float) * 100.0, 320)
    control_values = drops_values + 50.0
    spec = phase2.parse_participant("101:201:101:VRohtoPremium")
    results = [
        {
            "participant": spec,
            "drops": _synthetic_clean_session("101", "目薬あり", drops_values),
            "control": _synthetic_clean_session("201", "コントロール", control_values),
        }
    ]

    participant_values, summary = phase2.build_set_mean_quantification(
        results, "VRohtoPremium"
    )
    assert participant_values.loc[
        participant_values["Set"] == 3, "EyeDrop_set_mean_RT_ms"
    ].iloc[0] == pytest.approx(300.0)
    assert participant_values.loc[
        participant_values["Set"] == 3, "Control_set_mean_RT_ms"
    ].iloc[0] == pytest.approx(350.0)
    assert summary.loc[summary["Set"] == 3, "EyeDrop_N"].iloc[0] == 1
    assert not np.isclose(
        participant_values["EyeDrop_set_mean_RT_ms"].iloc[0], 9_999.0
    )


def test_set_mean_quantification_masks_both_conditions_for_missing_set() -> None:
    values = np.full(1920, 500.0)
    spec_missing = phase2.parse_participant("109:209:109:VRohtoPremium")
    spec_complete = phase2.parse_participant("111:211:211:VRohtoPremium")
    results = [
        {
            "participant": spec_missing,
            "drops": _synthetic_clean_session(
                "109", "目薬あり", values, eeg_missing_set=1
            ),
            "control": _synthetic_clean_session("209", "コントロール", values),
        },
        {
            "participant": spec_complete,
            "drops": _synthetic_clean_session("211", "目薬あり", values),
            "control": _synthetic_clean_session("111", "コントロール", values),
        },
    ]

    participant_values, summary = phase2.build_set_mean_quantification(
        results, "VRohtoPremium"
    )
    missing_pair_set1 = (participant_values["Pair_ID"] == "109-209") & (
        participant_values["Set"] == 1
    )
    assert participant_values.loc[
        missing_pair_set1, "EyeDrop_set_mean_RT_ms"
    ].isna().all()
    assert participant_values.loc[
        missing_pair_set1, "Control_set_mean_RT_ms"
    ].isna().all()
    assert summary.loc[summary["Set"] == 1, "EyeDrop_N"].iloc[0] == 1
    assert summary.loc[summary["Set"] == 1, "Control_N"].iloc[0] == 1
    assert summary.loc[summary["Set"] == 2, "EyeDrop_N"].iloc[0] == 2


def test_quantification_outputs_do_not_replace_existing_no1_outputs(
    tmp_path: Path,
) -> None:
    values_a = np.full(1920, 500.0)
    values_b = np.full(1920, 700.0)
    specs = [
        phase2.parse_participant("101:201:101:CCube"),
        phase2.parse_participant("102:202:102:CCube"),
    ]
    results = [
        {
            "participant": specs[0],
            "drops": _synthetic_clean_session(
                "101", "目薬あり", values_a, product="CCube"
            ),
            "control": _synthetic_clean_session(
                "201", "コントロール", values_b, product="CCube"
            ),
        },
        {
            "participant": specs[1],
            "drops": _synthetic_clean_session(
                "102", "目薬あり", values_b, product="CCube"
            ),
            "control": _synthetic_clean_session(
                "202", "コントロール", values_a, product="CCube"
            ),
        },
    ]
    no1 = tmp_path / "Phase2_行動データ解析" / "No1_ReactionTime" / "CCube"
    individual = no1 / "Individual"
    grand = no1 / "GrandAverage"
    individual.mkdir(parents=True)
    grand.mkdir()
    individual_sentinel = individual / "existing.txt"
    grand_sentinel = grand / "existing.txt"
    individual_sentinel.write_text("keep", encoding="utf-8")
    grand_sentinel.write_text("keep", encoding="utf-8")

    outputs = phase2.write_set_mean_quantification_outputs(tmp_path, results, "CCube")

    assert individual_sentinel.read_text(encoding="utf-8") == "keep"
    assert grand_sentinel.read_text(encoding="utf-8") == "keep"
    output_dir = Path(outputs["directory"])
    assert output_dir.name == "SetMeanQuantification"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "No1_RT_SetMeanQuantification_CCube.png",
        "No1_RT_SetMeanQuantification_CCube_ParticipantValues.csv",
        "No1_RT_SetMeanQuantification_CCube_RunSummary.json",
        "No1_RT_SetMeanQuantification_CCube_SetSummary.csv",
    ]
