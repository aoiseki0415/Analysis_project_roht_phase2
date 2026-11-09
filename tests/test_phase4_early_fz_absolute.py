from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

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


def _saved_pair_values(*, boundary: bool) -> pd.DataFrame:
    rows = []
    for product in ("CCube", "VRohtoPremium"):
        for subject in range(20):
            pair_id = (
                "101-201"
                if product == "VRohtoPremium" and subject == 0
                else f"{300 if product == 'CCube' else 400 + subject}-{500 + subject}"
            )
            for window in (
                module.BOUNDARY_WINDOWS if boundary else {"FullSetQC": 100.0, **module.SET_WINDOWS}
            ):
                for number in range(2 if boundary else 1, 7):
                    row = {"PairID": pair_id, "Product": product, "Window": window}
                    if boundary:
                        row.update({"FromSet": number - 1, "ToSet": number})
                    else:
                        row["Set"] = number
                    suffix = "Transition_uV2_per_Hz" if boundary else "PSD_uV2_per_Hz"
                    row[f"EyeDrop_{suffix}"] = float(subject + number + 2)
                    row[f"Control_{suffix}"] = float(subject + number)
                    rows.append(row)
    return pd.DataFrame(rows)


@pytest.mark.parametrize("boundary", [False, True])
def test_saved_pair_validation_rejects_incomplete_duplicate_and_wrong_product(
    boundary: bool,
) -> None:
    frame = _saved_pair_values(boundary=boundary)
    module._validate_saved_pair_values(frame, boundary=boundary)  # noqa: SLF001
    with pytest.raises(ValueError):
        module._validate_saved_pair_values(frame.iloc[:-1], boundary=boundary)  # noqa: SLF001
    with pytest.raises(ValueError):
        module._validate_saved_pair_values(  # noqa: SLF001
            pd.concat([frame, frame.iloc[[0]]], ignore_index=True), boundary=boundary
        )
    wrong_product = frame.copy()
    wrong_product.loc[wrong_product["PairID"] == "101-201", "Product"] = "CCube"
    with pytest.raises(ValueError):
        module._validate_saved_pair_values(wrong_product, boundary=boundary)  # noqa: SLF001


def test_no7_sensitivity_writes_only_additional_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    band = module.BANDS[7]
    source_bytes = {}
    for folder_name, pair_stem, group_stem, boundary in (
        ("SetQuantification", "PairSetWindowValues", "GroupSetWindowSummary", False),
        ("BetweenSetQuantification", "PairSetTransitionValues", "GroupSetTransitionSummary", True),
    ):
        folder = tmp_path / "Sub" / "tables" / folder_name
        folder.mkdir(parents=True)
        frame = _saved_pair_values(boundary=boundary)
        for stem, values in (
            (pair_stem, frame),
            (group_stem, module.summarize(frame, boundary=boundary)),
        ):
            path = folder / f"{band.stem}_{stem}.csv"
            values.to_csv(path, index=False)
            source_bytes[path] = path.read_bytes()

    drawn = []

    def fake_plot(
        frame: pd.DataFrame, product: str, window: str, band: object, path: Path, **kwargs: object
    ) -> None:
        assert product == "VRohtoPremium"
        assert frame["PairID"].nunique() == 19
        assert "101-201" not in set(frame["PairID"])
        assert "Excluding Pair 101-201" in str(kwargs["title_suffix"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"test-png")
        drawn.append(path)

    monkeypatch.setattr(module, "plot_quantification", fake_plot)
    assert module.run_excluded_pair_sensitivity(tmp_path, band, SimpleNamespace()) == 0
    assert len(drawn) == 4
    assert all("ExcludePair101-201" in path.name for path in drawn)
    assert all(path.read_bytes() == data for path, data in source_bytes.items())
    for folder_name, group_stem in (
        ("SetQuantification", "GroupSetWindowSummary"),
        ("BetweenSetQuantification", "GroupSetTransitionSummary"),
    ):
        path = (
            tmp_path
            / "Sub"
            / "tables"
            / folder_name
            / f"{band.stem}_{group_stem}_ExcludePair101-201_VRohtoPremium.csv"
        )
        assert set(pd.read_csv(path)["Paired_N"]) == {19}
