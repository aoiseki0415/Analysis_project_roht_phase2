"""No10's mutable shared engine is isolated in subprocesses for every test."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "解析プログラム/Phase4_脳波解析"
MODULE = "Phase4_No10_sub_TopographySensitivity"


def run_code(body: str) -> dict:
    setup = f"""
import json, sys
from types import SimpleNamespace
from pathlib import Path
import numpy as np
sys.path.insert(0, {str(SCRIPTS)!r})
import {MODULE} as m

def session(sid, factor=1.0, missing=()):
    sets = {{}}
    for number in range(1, 7):
        if number in missing:
            continue
        data = np.ones((180, 32)) * (1.0 if number == 1 else factor)
        sets[number] = SimpleNamespace(psd_band_mean=data, relative_seconds_center=np.arange(180.))
    source = SimpleNamespace(
        session_id=str(sid), channel_names=m.PARENT.EXPECTED_CHANNEL_NAMES, sets=sets)
    return m.engine.make_change_session(source)

def item(pair, product='CCube', eye_factor=1.0, control_factor=1.0,
         eye_missing=(), control_missing=()):
    a, b = pair.split('-')
    return {{'spec': SimpleNamespace(pair_id=pair), 'product_dir': product,
            'eye_drop': session(a, eye_factor, eye_missing),
            'control': session(b, control_factor, control_missing)}}

def row(set_number=2):
    fields = ('absolute', 'neighbor_factor', 'median_ratio', 'q75_ratio', 'fraction_ge2',
              'longest_ge2', 'fraction_low', 'longest_low', 'absolute_z', 'cohort_factor',
              'median_ratio_z', 'q75_ratio_z', 'absolute_factor')
    result = {{key: np.ones(32) for key in fields}}
    result.update(pair_id='900-901', session_id='900', condition='Eye Drop',
                  product='CCube', set=set_number)
    result['absolute_z'][:] = 0
    result['median_ratio_z'][:] = 0
    result['q75_ratio_z'][:] = 0
    result['fraction_ge2'][:] = 0
    result['fraction_low'][:] = 0
    return result
"""
    completed = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(setup) + textwrap.dedent(body)],
        cwd=ROOT,
        env={**os.environ, "MPLBACKEND": "Agg"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_no10_context_and_unchanged_prior_thresholds() -> None:
    actual = run_code("""
print(json.dumps({'frequencies': m.PARENT.INCLUDED_FREQUENCIES_HZ.tolist(),
    'stem': m.engine.ANALYSIS_STEM, 'parameters': m.asdict(m.prior.PARAMETERS),
    'alternate': m.engine.ALTERNATE_GROUP_EXCLUSIONS,
    'paths': [str(p) for p in m.supplement_paths()]}))
""")
    assert actual["frequencies"] == [8.0, 9.0, 10.0]
    assert actual["stem"] == "No10_sub_FzLowAlphaChange"
    assert actual["alternate"] == {}
    parameters = actual["parameters"]
    assert parameters["set1_log_robust_z"] == 4.5
    assert parameters["positive_log_robust_z"] == 3.5
    assert parameters["negative_absolute_log_robust_z"] == -4.0
    assert parameters["positive_median_ratio"] == 2.5
    assert parameters["negative_median_ratio"] == 0.30
    assert len(set(actual["paths"])) == 6
    assert all("No10_sub_FzLowAlphaChange" in path for path in actual["paths"])
    assert sum("BeforeOutlierExclusion" in path for path in actual["paths"]) == 2


def test_set1_high_propagates_only_same_pair_channel_sets2_6() -> None:
    actual = run_code("""
r = row(1)
r['absolute_z'][4] = 4.5001
r['cohort_factor'][4] = 2.5
r['neighbor_factor'][4] = 2.0
flags, causes = m.prior.evaluate_flags(m.CONFIG, [r], [])
print(json.dumps({'flags': len(flags), 'keys': [list(k) for k in causes]}))
""")
    assert actual["flags"] == 1
    assert actual["keys"] == [["900-901", number, 4] for number in range(2, 7)]


def test_paired_or_counts_cell_once_and_does_not_remove_other_channels() -> None:
    actual = run_code("""
r = row(4)
for key, value in [('median_ratio_z', 4), ('median_ratio', 3),
                   ('fraction_ge2', .6), ('longest_ge2', 2)]:
    r[key][5] = value
c = {**r, 'session_id': '901', 'condition': 'Control'}
flags, causes = m.prior.evaluate_flags(m.CONFIG, [], [r, c])
items = [item('900-901', eye_factor=2), item('902-903'), item('904-905', 'VRohtoPremium')]
products, eligible, excluded, _, applied = m.prior.group_topographies(m.CONFIG, items, causes)
m.verify_excluded_group(items, causes, products)
print(json.dumps({'flags': len(flags), 'keys': [list(k) for k in causes],
    'excluded': excluded, 'eligible': eligible,
    'n_affected': int(products['CCube']['valid_n'][3, 5]),
    'n_other': int(products['CCube']['valid_n'][3, 6]),
    'n_baseline': int(products['CCube']['valid_n'][0, 5])}))
""")
    assert actual["flags"] == 2
    assert actual["keys"] == [["900-901", 4, 5]]
    assert actual["excluded"] == 1
    assert actual["eligible"] == 3 * 5 * 32
    assert actual["n_affected"] == 1
    assert actual["n_other"] == actual["n_baseline"] == 2


def test_known_missing_set_not_new_exclusion_and_no_whole_pair_drop() -> None:
    actual = run_code("""
items = [item('900-901', eye_factor=2, eye_missing=(6,)), item('902-903'),
         item('904-905', 'VRohtoPremium')]
causes = {('900-901', 6, 3): [{'reason': 'example'}]}
products, eligible, excluded, _, applied = m.prior.group_topographies(m.CONFIG, items, causes)
print(json.dumps({'eligible': eligible, 'excluded': excluded, 'applied': len(applied),
    'n_set5': int(products['CCube']['valid_n'][4, 3]),
    'n_set6': int(products['CCube']['valid_n'][5, 3])}))
""")
    assert actual["eligible"] == 3 * 5 * 32 - 32
    assert actual["excluded"] == actual["applied"] == 0
    assert actual["n_set5"] == 2
    assert actual["n_set6"] == 1


def test_metrics_keep_median_qc_separate_from_mean_change_and_nan_occupancy() -> None:
    actual = run_code("""
x = item('900-901')
source = x['eye_drop'].source
source.sets[1].psd_band_mean[:60] = 4
# Set-1 median=1 and mean=2. Set2 finite blocks=4,NaN,4.
source.sets[2].psd_band_mean[:] = 4
source.sets[2].psd_band_mean[60:120] = np.nan
x['eye_drop'] = m.engine.make_change_session(source)
first, later = m.collect_condition_metrics([x])
r = next(r for r in later if r['condition']=='Eye Drop' and r['set']==2)
print(json.dumps({'qc_baseline': float(first[0]['absolute'][0]),
    'change_baseline': float(x['eye_drop'].baseline_by_channel[0]),
    'ratio': float(r['median_ratio'][0]), 'occupancy': float(r['fraction_ge2'][0]),
    'run': int(r['longest_ge2'][0]), 'blocks': int(r['block_count'][0]),
    'finite_blocks': int(r['finite_block_count'][0])}))
""")
    assert actual["qc_baseline"] == 1.0
    assert actual["change_baseline"] == 2.0
    assert actual["ratio"] == 4.0
    assert actual["occupancy"] == 2 / 3
    assert actual["run"] == 1
    assert actual["blocks"] == 3
    assert actual["finite_blocks"] == 2


def test_large_scale_benchmark_is_only_audit_and_uses_nice_colour_range() -> None:
    actual = run_code("""
items = [item('900-901', eye_factor=6.2), item('902-903', 'VRohtoPremium')]
rows = m.benchmark_rows(items, set())
value = float(m.engine.pair_topography_values(items[0])[1,0])
print(json.dumps({'rows': rows, 'source_value': value}))
""")
    assert len(actual["rows"]) == 1
    assert actual["rows"][0]["original_colour_limit"] == 800.0
    assert actual["rows"][0]["largest_cell_excluded"] is False
    assert abs(actual["source_value"] - 520.0) < 1e-8


def test_negative_change_alone_is_not_excluded_without_absolute_low_support() -> None:
    actual = run_code("""
r = row(3)
r['median_ratio'][3] = .2
r['fraction_low'][3] = 1
r['longest_low'][3] = 3
flags0, _ = m.prior.evaluate_flags(m.CONFIG, [], [r])
r['absolute_z'][3] = -4.01
r['absolute_factor'][3] = .35
r['neighbor_factor'][3] = .45
flags1, causes = m.prior.evaluate_flags(m.CONFIG, [], [r])
print(json.dumps({'before': len(flags0), 'after': len(flags1), 'keys': [list(k) for k in causes]}))
""")
    assert actual["before"] == 0
    assert actual["after"] == 1
    assert actual["keys"] == [["900-901", 3, 3]]


def test_unexcluded_values_match_independent_original_mean_formula() -> None:
    actual = run_code("""
x = item('900-901', eye_factor=2.3, control_factor=1.2)
v = m.independent_pair_values(x)
np.testing.assert_allclose(v, m.engine.pair_topography_values(x), atol=1e-8)
print(json.dumps({'baseline_max': float(np.abs(v[0]).max()), 'later': float(v[1,0])}))
""")
    assert actual["baseline_max"] == 0.0
    assert abs(actual["later"] - 110.0) < 1e-8


def test_execute_requires_matching_live_source_audit_before_writes() -> None:
    actual = run_code("""
try:
    m.validate_source_audit(None)
except ValueError as exc:
    print(json.dumps({'message': str(exc)}))
""")
    assert "--source-audit" in actual["message"]


def test_zero_remaining_channel_is_rejected_instead_of_silent_missing_figure() -> None:
    actual = run_code("""
items = [item('900-901'), item('904-905', 'VRohtoPremium')]
causes = {('900-901', 2, 0): [{'reason': 'example'}]}
products, *_ = m.prior.group_topographies(m.CONFIG, items, causes)
try:
    m.verify_excluded_group(items, causes, products)
except ValueError as exc:
    print(json.dumps({'message': str(exc)}))
""")
    assert "no remaining paired" in actual["message"]
