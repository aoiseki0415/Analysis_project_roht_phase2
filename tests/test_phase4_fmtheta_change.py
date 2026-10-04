from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム"
    / "Phase4_脳波解析"
    / "Phase4_No1_sub_FmThetaChange.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("phase4_no1_sub", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_percent_change_uses_ratio_to_set1_baseline() -> None:
    values = np.array([5.0, 10.0, 15.0])
    result = module.to_percent_change(values, 10.0)
    np.testing.assert_allclose(result, [-50.0, 0.0, 50.0])


def test_percent_change_rejects_nonpositive_baseline() -> None:
    for baseline in (0.0, -1.0, np.nan):
        try:
            module.to_percent_change(np.array([1.0]), baseline)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid baseline was accepted")


def test_symmetric_limit_contains_positive_and_negative_values() -> None:
    limit, ticks = module._nice_symmetric_limit(np.array([-12.0, 4.0, 10.0]), 0.75)
    assert limit >= 12.0 / 0.75
    assert np.isclose(ticks[0], -ticks[-1])
    assert np.any(np.isclose(ticks, 0.0))


def test_quantification_statistics_does_not_test_set1() -> None:
    rows = []
    for pair in ("101-201", "102-202", "103-203"):
        for set_number in range(1, 7):
            rows.append(
                {
                    "PairID": pair,
                    "Set": set_number,
                    "EyeDrop_PSDChange_pct": 0.0 if set_number == 1 else float(set_number),
                    "Control_PSDChange_pct": 0.0 if set_number == 1 else float(set_number - 1),
                }
            )
        rows.append(
            {
                "PairID": pair,
                "Set": "Sets 2-6",
                "EyeDrop_PSDChange_pct": 3.0,
                "Control_PSDChange_pct": 2.0,
            }
        )
    import pandas as pd

    set_statistics, overall = module.quantification_statistics(pd.DataFrame(rows))
    baseline = set_statistics.loc[set_statistics["Set"] == 1].iloc[0]
    assert np.isnan(baseline["P_value_raw"])
    assert baseline["Note"] == "Baseline; no test"
    assert overall.iloc[0]["Set"] == "Sets 2-6"


def test_output_tree_is_separate_from_no1() -> None:
    paths = module.output_directories(Path("/tmp/results"), "CCube")
    assert "No1_sub_FmThetaChange" in str(paths["root"])
    assert str(paths["individual"]).endswith("CCube/Individual")
    assert str(paths["baseline_tables"]).endswith("Sub/tables/Set1Baseline")
