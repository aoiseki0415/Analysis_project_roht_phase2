from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))

import phase4_early_fz_change as module  # noqa: E402


def test_early_windows_use_original_set_progress_without_smoothing(monkeypatch) -> None:
    progress = np.array([0.0, 25.0, 50.0, 75.0, 100.0])
    sets = {number: SimpleNamespace(set_progress_pct=progress) for number in range(1, 7)}
    eye = SimpleNamespace(session_id="101", channel_names=["Fz"], source=SimpleNamespace(sets=sets))
    control = SimpleNamespace(
        session_id="201", channel_names=["Fz"], source=SimpleNamespace(sets=sets)
    )
    values = {
        "101": np.array([-20.0, -10.0, 0.0, 10.0, 20.0]),
        "201": np.array([-10.0, -5.0, 0.0, 5.0, 10.0]),
    }
    monkeypatch.setattr(
        module.change_engine,
        "set_change_values",
        lambda session, set_number, channel: values[session.session_id],
    )
    item = {
        "spec": SimpleNamespace(pair_id="101-201"),
        "product_dir": "VRohtoPremium",
        "eye_drop": eye,
        "control": control,
    }
    rows = module.quantify_item(item)
    set1 = {row["Window"]: row for row in rows if row["Set"] == 1}
    assert set1["FullSet"]["EyeDrop_PSDChange_pct"] == 0.0
    assert set1["FirstHalf"]["EyeDrop_PSDChange_pct"] == -15.0
    assert set1["FirstQuarter"]["EyeDrop_PSDChange_pct"] == -20.0
    assert set1["FirstHalf"]["EyeDrop_TotalWindows"] == 2
    assert set1["FirstQuarter"]["EyeDrop_TotalWindows"] == 1
    assert set1["FullSet"]["EyeDrop_TotalWindows"] == 5


def test_missing_set_is_paired_nan(monkeypatch) -> None:
    progress = np.array([0.0, 50.0, 100.0])
    eye_sets = {1: SimpleNamespace(set_progress_pct=progress)}
    control_sets = {
        1: SimpleNamespace(set_progress_pct=progress),
        2: SimpleNamespace(set_progress_pct=progress),
    }
    eye = SimpleNamespace(
        session_id="101", channel_names=["Fz"], source=SimpleNamespace(sets=eye_sets)
    )
    control = SimpleNamespace(
        session_id="201", channel_names=["Fz"], source=SimpleNamespace(sets=control_sets)
    )
    monkeypatch.setattr(
        module.change_engine,
        "set_change_values",
        lambda session, set_number, channel: np.array([-1.0, 0.0, 1.0]),
    )
    item = {
        "spec": SimpleNamespace(pair_id="101-201"),
        "product_dir": "VRohtoPremium",
        "eye_drop": eye,
        "control": control,
    }
    set2_rows = [row for row in module.quantify_item(item) if row["Set"] == 2]
    assert len(set2_rows) == 3
    assert all(not row["PairedSetAvailable"] for row in set2_rows)
    assert all(np.isnan(row["EyeDrop_PSDChange_pct"]) for row in set2_rows)
    assert all(np.isnan(row["Control_PSDChange_pct"]) for row in set2_rows)
