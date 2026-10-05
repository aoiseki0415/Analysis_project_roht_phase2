from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = (
    Path(__file__).parents[1]
    / "解析プログラム"
    / "Phase2_行動データ解析"
    / "Phase2_No2_Mistouch.py"
)
SPEC = importlib.util.spec_from_file_location("phase2_no2", SCRIPT)
assert SPEC and SPEC.loader
phase2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = phase2
SPEC.loader.exec_module(phase2)


def frame(types: list[str], times: list[float], rts: list[float] | None = None) -> pd.DataFrame:
    if rts is None:
        rts = [np.nan] * len(types)
    return pd.DataFrame({"ResponseType_norm": types, "KeyPress_num": times, "Correct_RT_ms": rts})


def test_consecutive_50ms_rule_is_inclusive() -> None:
    result = phase2.count_mistouch_events(frame(["mistouch", "mistouch", "mistouch"], [0, 50, 101]))
    assert result["raw_mistouch_rows"] == 3
    assert result["mistouch_count"] == 2
    assert result["consecutive_links_50ms"] == 1


def test_correct_bridge_rule_requires_one_fast_correct() -> None:
    merged = phase2.count_mistouch_events(
        frame(["mistouch", "correct", "mistouch"], [0, 40, 100], [np.nan, 40, np.nan])
    )
    separate = phase2.count_mistouch_events(
        frame(["mistouch", "correct", "mistouch"], [0, 40, 100], [np.nan, 51, np.nan])
    )
    assert merged["mistouch_count"] == 1
    assert merged["correct_bridge_links_100ms"] == 1
    assert separate["mistouch_count"] == 2


def test_more_than_one_correct_is_not_merged() -> None:
    result = phase2.count_mistouch_events(
        frame(
            ["mistouch", "correct", "correct", "mistouch"],
            [0, 20, 40, 80],
            [np.nan, 20, 20, np.nan],
        )
    )
    assert result["mistouch_count"] == 2


def test_time_reversal_is_recorded_and_not_merged() -> None:
    result = phase2.count_mistouch_events(frame(["mistouch", "mistouch"], [100, 90]))
    assert result["mistouch_count"] == 2
    assert result["time_reversal_links"] == 1


def test_pairwise_eeg_missing_set_masks_both_conditions(monkeypatch) -> None:
    participant = phase2.no1.parse_participant("109:209:109:VRohtoPremium")

    def fake_process(_root: Path, session_id: str):
        return [
            phase2.SetCount(i, 4, 3.0, 1, 0, 0, 0, "x", session_id == "109" and i == 1)
            for i in range(1, 7)
        ]

    monkeypatch.setattr(phase2, "process_session", fake_process)
    rows = phase2.analyse_participant(Path("."), participant)
    assert np.isnan(rows[0]["EyeDrop_mistouch_count"])
    assert np.isnan(rows[0]["Control_mistouch_count"])
    assert rows[1]["EyeDrop_mistouch_count"] == 3


def test_fixed_figure_style() -> None:
    assert phase2.BAR_WIDTH == 0.42
    assert phase2.DOT_SIZE == 150.0
    assert phase2.CONTROL_COLOR == "#402B5D"
    assert phase2.PRODUCTS["CCube"][1] == "#5F7890"


def test_ccube_sensitivity_masks_only_target_pair_and_set() -> None:
    rows = []
    for pair_id in ("132-232", "134-234"):
        for set_number in range(1, 7):
            rows.append(
                {
                    "Product": "CCube",
                    "Pair_ID": pair_id,
                    "Set": set_number,
                    "EyeDrop_mistouch_count": 10.0,
                    "Control_mistouch_count": 20.0,
                }
            )
    values = pd.DataFrame(rows)
    sensitivity = phase2.build_ccube_sensitivity_values(values)
    target = sensitivity["Pair_ID"].eq("132-232") & sensitivity["Set"].eq(1)
    assert sensitivity.loc[target, "EyeDrop_mistouch_count"].isna().all()
    assert sensitivity.loc[target, "Control_mistouch_count"].isna().all()
    assert sensitivity.loc[~target, "EyeDrop_mistouch_count"].eq(10.0).all()
    assert sensitivity.loc[~target, "Control_mistouch_count"].eq(20.0).all()


def test_support_outputs_are_written_to_sub(monkeypatch, tmp_path: Path) -> None:
    values = pd.DataFrame(
        [
            {
                "Product": product,
                "Pair_ID": pair_id,
                "Set": set_number,
                "EyeDrop_mistouch_count": 1.0,
                "Control_mistouch_count": 2.0,
            }
            for product in phase2.PRODUCTS
            for pair_id in ("132-232", "134-234")
            for set_number in range(1, 7)
        ]
    )
    summary = phase2.build_summary(values)
    monkeypatch.setattr(phase2, "plot_product", lambda *args, **kwargs: 10.0)
    outputs = phase2.write_outputs(tmp_path, values, summary)
    root = tmp_path / "Phase2_行動データ解析" / "No2_Mistouch"
    assert (root / "Sub" / "No2_Mistouch_CCube_ParticipantValues.csv").exists()
    assert (root / "Sub" / "No2_Mistouch_VRohtoPremium_RunSummary.json").exists()
    assert (root / "No2_Mistouch_BatchSummary.json").exists()
    assert all(Path(item["setwise_figure"]).parent.name in {
        "SetQuantification", "SensitivityAnalysis_ExcludeID132-232_Set1"
    } for item in outputs)
    assert all(Path(item["all_sets_figure"]).exists() for item in outputs)


def test_all_sets_mistouch_sums_only_paired_available_sets() -> None:
    values = pd.DataFrame(
        [
            {
                "Product": "CCube",
                "Pair_ID": "101-201",
                "Set": set_number,
                "EyeDrop_mistouch_count": np.nan if set_number == 2 else float(set_number),
                "Control_mistouch_count": np.nan if set_number == 2 else float(set_number + 1),
            }
            for set_number in range(1, 7)
        ]
    )
    result = phase2.build_all_sets_mistouch_values(values, "CCube").iloc[0]
    assert result["Included_set_count"] == 5
    assert result["EyeDrop_all_sets_mistouch_count"] == 19.0
    assert result["Control_all_sets_mistouch_count"] == 24.0
