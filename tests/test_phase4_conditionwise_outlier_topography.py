from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム"
    / "Phase4_脳波解析"
    / "Phase4_PSDChangeConditionwiseBidirectionalOutlierTopography.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("phase4_conditionwise_outlier", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_final_figure_is_saved_in_primary_and_supplemental_locations(tmp_path):
    config = MODULE.ANALYSES["No1"]

    primary = MODULE.output_paths(tmp_path, config, "CCube")
    supplemental = MODULE.supplemental_output_path(tmp_path, config, "CCube")

    assert primary.name == supplemental.name
    assert "No1_sub_FmThetaChange/CCube/Topography/GrandAverage" in primary.as_posix()
    assert (
        "補足分析（被験者除外あり）/No1_sub_FmThetaChange/CCube/GrandAverage"
        in supplemental.as_posix()
    )
    assert primary.name.endswith(
        "_ExploratorySet1AbsolutePSD_SustainedChangeExcluded.png"
    )
