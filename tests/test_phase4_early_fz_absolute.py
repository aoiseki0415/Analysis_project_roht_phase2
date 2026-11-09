from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))

import phase4_early_fz_absolute as module  # noqa: E402


def _session(values_by_set: dict[int, list[float]]) -> SimpleNamespace:
    progress = np.array([0.0, 25.0, 50.0, 75.0, 100.0])
    return SimpleNamespace(
        channel_names=["Fz"],
        sets={
            number: SimpleNamespace(
                set_progress_pct=progress,
                psd_band_mean=np.array(values, dtype=float)[:, None],
            )
            for number, values in values_by_set.items()
        },
    )


def _item(eye: SimpleNamespace, control: SimpleNamespace) -> dict:
    return {
        "spec": SimpleNamespace(pair_id="101-201"),
        "product": "VRohtoPremium",
        "eye": eye,
        "control": control,
    }


def test_early_absolute_psd_uses_unsmoothed_progress_windows() -> None:
    eye = _session({1: [10, 20, 30, 40, 50]})
    control = _session({1: [5, 10, 15, 20, 25]})
    rows = [row for row in module.quantify_set(_item(eye, control)) if row["Set"] == 1]
    by_window = {row["Window"]: row for row in rows}
    assert by_window["FullSetQC"]["EyeDrop_PSD_uV2_per_Hz"] == 30
    assert by_window["FirstHalf"]["EyeDrop_PSD_uV2_per_Hz"] == 15
    assert by_window["FirstQuarter"]["EyeDrop_PSD_uV2_per_Hz"] == 10
    assert by_window["FirstHalf"]["EyeDrop_TotalWindows"] == 2
    assert by_window["FirstQuarter"]["EyeDrop_TotalWindows"] == 1


def test_transition_is_next_first_minus_previous_last() -> None:
    eye = _session({1: [10, 20, 30, 40, 50], 2: [60, 70, 80, 90, 100]})
    control = _session({1: [5, 10, 15, 20, 25], 2: [30, 35, 40, 45, 50]})
    rows = [row for row in module.quantify_boundary(_item(eye, control)) if row["ToSet"] == 2]
    by_window = {row["Window"]: row for row in rows}
    assert by_window["BoundaryHalf"]["EyeDrop_Transition_uV2_per_Hz"] == 25
    assert by_window["BoundaryQuarter"]["EyeDrop_Transition_uV2_per_Hz"] == 15
    assert by_window["BoundaryHalf"]["Control_Transition_uV2_per_Hz"] == 12.5
    assert by_window["BoundaryQuarter"]["Control_Transition_uV2_per_Hz"] == 7.5


def test_missing_set_removes_only_pairwise_set_and_adjacent_transition() -> None:
    eye = _session({1: [10, 20, 30, 40, 50], 3: [20, 20, 20, 20, 20]})
    control = _session({1: [5, 10, 15, 20, 25], 2: [30, 35, 40, 45, 50], 3: [5] * 5})
    item = _item(eye, control)
    missing = [row for row in module.quantify_set(item) if row["Set"] == 2]
    assert all(not row["PairedSetAvailable"] for row in missing)
    assert all(np.isnan(row["EyeDrop_PSD_uV2_per_Hz"]) for row in missing)
    assert all(np.isnan(row["Control_PSD_uV2_per_Hz"]) for row in missing)
    later = [row for row in module.quantify_set(item) if row["Set"] == 3]
    assert all(row["PairedSetAvailable"] for row in later)
    boundary = [row for row in module.quantify_boundary(item) if row["ToSet"] in (2, 3)]
    assert all(not row["PairedTransitionAvailable"] for row in boundary)
    assert all(np.isnan(row["EyeDrop_Transition_uV2_per_Hz"]) for row in boundary)
