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


def test_before_and_after_figures_have_explicit_supplemental_names(tmp_path):
    config = MODULE.ANALYSES["No1"]

    primary = MODULE.output_paths(tmp_path, config, "CCube")
    original = MODULE.unexcluded_output_path(tmp_path, config, "CCube")
    supplemental_before = MODULE.supplemental_output_path(
        tmp_path, config, "CCube", "Before"
    )
    supplemental_after = MODULE.supplemental_output_path(
        tmp_path, config, "CCube", "After"
    )

    assert "No1_sub_FmThetaChange/CCube/Topography/GrandAverage" in primary.as_posix()
    assert original.name.endswith("_GrandAverage_CCube.png")
    assert (
        "補足分析（被験者除外あり）/No1_sub_FmThetaChange/CCube/GrandAverage"
        in supplemental_before.as_posix()
    )
    assert primary.name.endswith(
        "_ExploratorySet1AbsolutePSD_SustainedChangeExcluded.png"
    )
    assert supplemental_before.name.endswith("_BeforeOutlierExclusion.png")
    assert supplemental_after.name.endswith("_AfterOutlierExclusion.png")


def test_supplemental_stage_is_restricted(tmp_path):
    config = MODULE.ANALYSES["No1"]

    try:
        MODULE.supplemental_output_path(tmp_path, config, "CCube", "Unknown")
    except ValueError as error:
        assert "Unexpected supplemental stage" in str(error)
    else:
        raise AssertionError("Unknown stage must not be accepted")
