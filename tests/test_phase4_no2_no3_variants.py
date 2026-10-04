from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "解析プログラム" / "Phase4_脳波解析"


def _inspect(module: str) -> dict[str, object]:
    code = f"""
import json, sys
sys.path.insert(0, {str(SCRIPT_DIR)!r})
import {module} as wrapper
engine = wrapper.engine
payload = {{
    'analysis_stem': engine.ANALYSIS_STEM,
    'focus_channel': engine.FOCUS_CHANNEL,
    'cache_root': str(engine.DEFAULT_CACHE_ROOT),
    'frequencies': getattr(engine, 'INCLUDED_FREQUENCIES_HZ', []).tolist()
        if hasattr(getattr(engine, 'INCLUDED_FREQUENCIES_HZ', []), 'tolist')
        else [],
    'focus_index': getattr(engine, 'FOCUS_CHANNEL_INDEX', None),
    'absolute_color_limit': getattr(engine, 'ABSOLUTE_PSD_COLOR_LIMIT', None),
    'absolute_color_ticks': getattr(engine, 'ABSOLUTE_PSD_COLOR_TICKS', []).tolist()
        if hasattr(getattr(engine, 'ABSOLUTE_PSD_COLOR_TICKS', []), 'tolist') else [],
    'difference_color_limit': getattr(engine, 'DIFFERENCE_COLOR_LIMIT', None),
    'difference_color_ticks': getattr(engine, 'DIFFERENCE_COLOR_TICKS', []).tolist()
        if hasattr(getattr(engine, 'DIFFERENCE_COLOR_TICKS', []), 'tolist') else [],
    'standard_significance_style': getattr(engine, 'USE_STANDARD_SIGNIFICANCE_STYLE', None),
    'ccube_color': engine.PRODUCTS['ccube'][2] if hasattr(engine, 'PRODUCTS')
        and len(engine.PRODUCTS['ccube']) == 4 else None,
    'vrohto_color': engine.PRODUCTS['vrohtopremium'][2] if hasattr(engine, 'PRODUCTS')
        and len(engine.PRODUCTS['vrohtopremium']) == 4 else None,
}}
print(json.dumps(payload))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_no2_main_configuration() -> None:
    actual = _inspect("Phase4_No2_OccipitalAlpha")
    assert actual["analysis_stem"] == "No2_OccipitalAlpha"
    assert actual["focus_channel"] == "Oz"
    assert actual["frequencies"] == list(range(8, 16))
    assert actual["ccube_color"] == "#C23B8A"
    assert actual["vrohto_color"] == "#E36A8D"
    assert "/No2_OccipitalAlpha/PSDTimeSeries" in actual["cache_root"]


def test_no2_sub_and_add_configuration() -> None:
    sub = _inspect("Phase4_No2_sub_OccipitalAlphaChange")
    add = _inspect("Phase4_No2_add_OzTimeFrequencyMap")
    assert sub["analysis_stem"] == "No2_sub_OccipitalAlphaChange"
    assert sub["focus_channel"] == "Oz"
    assert add["analysis_stem"] == "No2_add_OzTimeFrequencyMap"
    assert add["focus_channel"] == "Oz"
    assert add["focus_index"] == 17
    assert add["absolute_color_limit"] == 20.0
    assert add["absolute_color_ticks"] == [0.0, 5.0, 10.0, 15.0, 20.0]
    assert add["difference_color_limit"] == 15.0
    assert add["difference_color_ticks"] == [-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0]
    assert "/No2_add_OzTimeFrequencyMap/TimeFrequencySeries" in add["cache_root"]


def test_no3_main_configuration() -> None:
    actual = _inspect("Phase4_No3_FrontalDelta")
    assert actual["analysis_stem"] == "No3_FrontalDelta"
    assert actual["focus_channel"] == "Fz"
    assert actual["frequencies"] == [1.0, 2.0, 3.0]
    assert actual["ccube_color"] == "#8F7300"
    assert actual["vrohto_color"] == "#C29A00"
    assert "/No3_FrontalDelta/PSDTimeSeries" in actual["cache_root"]


def test_no3_sub_and_add_configuration() -> None:
    sub = _inspect("Phase4_No3_sub_FrontalDeltaChange")
    add = _inspect("Phase4_No3_add_FzTimeFrequencyMap")
    assert sub["analysis_stem"] == "No3_sub_FrontalDeltaChange"
    assert sub["focus_channel"] == "Fz"
    assert sub["standard_significance_style"] is True
    assert add["analysis_stem"] == "No3_add_FzTimeFrequencyMap"
    assert add["focus_channel"] == "Fz"
    assert add["focus_index"] == 1
    assert "/No3_add_FzTimeFrequencyMap/TimeFrequencySeries" in add["cache_root"]
