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
    fields = ('ratio', 'ratio_residual_log2', 'ratio_spatial_z', 'ratio_residual_log2_cohort_z',
              'ratio_support', 'median_residual_log2', 'median_spatial_z',
              'median_residual_log2_cohort_z', 'median_cohort_z', 'median_support',
              'top_share', 'mean_median', 'mean_median_cohort_z')
    result = {{key: np.zeros(32) for key in fields}}
    for key in ('ratio_strict_neighbor_isolation', 'median_strict_neighbor_isolation',
                'ratio_extension_neighbor_isolation', 'ratio_extension_strong_neighbor_isolation'):
        result[key] = np.zeros(32, dtype=bool)
    result.update(pair_id='900-901', session_id='900', condition='Eye Drop',
                  product='CCube', set=set_number)
    return result

def spatial(r, ch, kind='ratio', sign=1):
    r[kind+'_residual_log2'][ch] = sign*3
    r[kind+'_spatial_z'][ch] = sign*5
    r[kind+'_residual_log2_cohort_z'][ch] = sign*5
    r[kind+'_support'][ch] = 3
    r[kind+'_strict_neighbor_isolation'][ch] = True
    if kind == 'median':
        r['median_cohort_z'][ch] = sign*5
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


def test_no10_context_current_parameters_and_scoped_paths() -> None:
    actual = run_code("""
print(json.dumps({'frequencies': m.PARENT.INCLUDED_FREQUENCIES_HZ.tolist(),
    'stem': m.engine.ANALYSIS_STEM, 'parameters': m.asdict(m.qc.PARAMETERS),
    'alternate': m.engine.ALTERNATE_GROUP_EXCLUSIONS,
    'paths': [str(p) for p in m.supplement_paths()]}))
""")
    assert actual["frequencies"] == [8.0, 9.0, 10.0]
    assert actual["stem"] == "No10_sub_FzLowAlphaChange"
    assert actual["alternate"] == {}
    assert actual["parameters"]["scaled_mad_floor"] == 0.15
    assert actual["parameters"]["change_spatial_z"] == 4.5
    assert actual["parameters"]["absolute_level_z"] == 4.0
    assert actual["parameters"]["change_extension_own_ratio_factor"] == 2.0
    assert actual["parameters"]["change_extension_neighbor_factor"] == 1.8
    assert actual["parameters"]["change_extension_cohort_z"] == 6.0
    assert actual["parameters"]["change_extension_spatial_z"] == 3.0
    assert actual["parameters"]["change_extension_strong_neighbor_factor"] == 3.0
    assert len(set(actual["paths"])) == 6
    assert sum("ExploratorySpatialTemporalExcluded" in p for p in actual["paths"]) == 2
    assert sum("BeforeOutlierExclusion" in p for p in actual["paths"]) == 2


def test_scaled_mad_floor_and_nan_reference() -> None:
    actual = run_code("""
a = m.qc.robust_z(np.array([0., .01, .02, np.nan]))
b = m.qc.robust_z(np.array([0., 1., 2.]))
print(json.dumps({'a': a[:3].tolist(), 'missing': bool(np.isnan(a[3])), 'b': b.tolist()}))
""")
    assert actual["a"] == [-0.01 / 0.15, 0.0, 0.01 / 0.15]
    assert actual["missing"] is True
    assert abs(actual["b"][0] + 1 / 1.4826) < 1e-12


def test_strict_twofold_and_three_of_four_support() -> None:
    actual = run_code("""
neighbors = np.array([[1,2,3,4]])
def flag(v):
    return bool(m.qc.strict_neighbor_isolation(np.array(v), neighbors)[0])
print(json.dumps({'equal_high': flag([2,1,1,1,8]), 'above': flag([2.01,1,1,1,8]),
 'equal_low': flag([.5,.1,1,1,1]), 'below': flag([.49,.1,1,1,1]),
 'two_only': flag([4,1,1,4,4])}))
""")
    assert actual == dict(equal_high=False, above=True, equal_low=False, below=True, two_only=False)


def test_set1_absolute_or_temporal_propagates_but_change_cannot() -> None:
    actual = run_code("""
r = row(1)
spatial(r, 4, 'median', -1)
spatial(r, 5)
r['top_share'][6] = .5
r['mean_median'][6] = 3
r['mean_median_cohort_z'][6] = 3.5
flags, causes = m.qc.evaluate_flags([r], m.PARENT.EXPECTED_CHANNEL_NAMES)
print(json.dumps({'flags': len(flags), 'keys': sorted([list(k) for k in causes]),
 'propagated': all(e['baseline_propagated'] for es in causes.values() for e in es)}))
""")
    assert actual["flags"] == 2
    assert actual["keys"] == [["900-901", n, ch] for n in range(2, 7) for ch in (4, 6)]
    assert actual["propagated"]


def test_paired_or_counts_once_no_other_channels() -> None:
    actual = run_code("""
r = row(4)
spatial(r, 5)
c = {**r, 'session_id': '901', 'condition': 'Control'}
flags, causes = m.qc.evaluate_flags([r, c], m.PARENT.EXPECTED_CHANNEL_NAMES)
items = [item('900-901', eye_factor=2), item('902-903'), item('904-905', 'VRohtoPremium')]
products, eligible, excluded, _, applied = m.prior.group_topographies(m.CONFIG, items, causes)
m.verify_excluded_group(items, causes, products)
print(json.dumps({'flags': len(flags), 'keys': [list(k) for k in causes],
 'excluded': excluded, 'eligible': eligible, 'n_affected': int(products['CCube']['valid_n'][3,5]),
 'n_other': int(products['CCube']['valid_n'][3,6]),
 'n_base': int(products['CCube']['valid_n'][0,5])}))
""")
    assert actual["flags"] == 2
    assert actual["keys"] == [["900-901", 4, 5]]
    assert actual["excluded"] == 1
    assert actual["eligible"] == 3 * 5 * 32
    assert actual["n_affected"] == 1
    assert actual["n_other"] == actual["n_base"] == 2


def test_known_missing_set_not_new_exclusion_or_whole_pair_drop() -> None:
    actual = run_code("""
items = [item('900-901', eye_factor=2, eye_missing=(6,)), item('902-903'),
 item('904-905', 'VRohtoPremium')]
causes = {('900-901', 6, 3): [{'reason': 'example'}]}
products, eligible, excluded, _, applied = m.prior.group_topographies(m.CONFIG, items, causes)
print(json.dumps({'eligible': eligible, 'excluded': excluded, 'applied': len(applied),
 'n_set5': int(products['CCube']['valid_n'][4,3]),
 'n_set6': int(products['CCube']['valid_n'][5,3])}))
""")
    assert actual["eligible"] == 3 * 5 * 32 - 32
    assert actual["excluded"] == actual["applied"] == 0
    assert actual["n_set5"] == 2
    assert actual["n_set6"] == 1


def test_mean_baseline_finite_top_ceil_and_both_conditions_reference() -> None:
    actual = run_code("""
x = item('900-901')
source = x['eye_drop'].source
source.sets[1].psd_band_mean[:60] = 4
source.sets[2].psd_band_mean[:] = 4
source.sets[2].psd_band_mean[60:120] = np.nan
rows = m.collect_condition_metrics([x])
r = next(r for r in rows if r['condition']=='Eye Drop' and r['set']==2)
small = np.arange(1.,12.)[:,None]
metric = m.qc.power_metrics(small, np.ones(1))
print(json.dumps({'baseline': float(r['baseline_mean'][0]), 'ratio': float(r['ratio'][0]),
 'count': int(r['finite_count'][0]), 'top': int(metric['top_count'][0]),
 'share': float(metric['top_share'][0]), 'rows': len(rows)}))
""")
    assert actual["baseline"] == 2.0
    assert actual["ratio"] == 2.0
    assert actual["count"] == 120
    assert actual["top"] == 2
    assert actual["share"] == 21 / 66
    assert actual["rows"] == 12


def test_positive_and_negative_spatial_paths_need_final_neighbor_gate() -> None:
    actual = run_code("""
r = row(3)
spatial(r, 3, sign=1)
spatial(r, 4, sign=-1)
spatial(r, 5, 'median', sign=-1)
spatial(r, 6)
r['ratio_support'][6] = 2
spatial(r, 7)
r['ratio_strict_neighbor_isolation'][7] = False
flags, causes = m.qc.evaluate_flags([r], m.PARENT.EXPECTED_CHANNEL_NAMES)
print(json.dumps({'channels': [k[2] for k in causes]}))
""")
    assert actual["channels"] == [3, 4, 5]


def test_temporal_independent_of_spatial_and_broad_change_not_flagged() -> None:
    actual = run_code("""
items = [item('900-901', eye_factor=50), item('902-903', 'VRohtoPremium')]
rows = m.collect_condition_metrics(items)
flags, causes = m.qc.evaluate_flags(rows, m.PARENT.EXPECTED_CHANNEL_NAMES)
r = row(3)
r['top_share'][1]=.5
r['mean_median'][1]=3
r['mean_median_cohort_z'][1]=3.5
temporal, selected = m.qc.evaluate_flags([r], m.PARENT.EXPECTED_CHANNEL_NAMES)
print(json.dumps({'broad': len(flags), 'temporal': len(temporal),
 'keys': [list(k) for k in selected]}))
""")
    assert actual["broad"] == 0
    assert actual["temporal"] == 1
    assert actual["keys"] == [["900-901", 3, 1]]


def test_large_colour_scale_benchmark_is_only_audit() -> None:
    actual = run_code("""
items = [item('900-901', eye_factor=6.2), item('902-903', 'VRohtoPremium')]
print(json.dumps({'rows': m.benchmark_rows(items, set()),
 'source_value': float(m.engine.pair_topography_values(items[0])[1,0])}))
""")
    assert len(actual["rows"]) == 1
    assert actual["rows"][0]["original_colour_limit"] == 800.0
    assert actual["rows"][0]["largest_cell_excluded"] is False
    assert abs(actual["source_value"] - 520.0) < 1e-8


def test_independent_mean_formula_and_montage_geometry() -> None:
    actual = run_code("""
x = item('900-901', eye_factor=2.3, control_factor=1.2)
v = m.independent_pair_values(x)
np.testing.assert_allclose(v, m.engine.pair_topography_values(x), atol=1e-8)
positions, neighbors = m.electrode_geometry()
assert neighbors.shape == (32,4)
for i, row_indices in enumerate(neighbors):
    assert i not in row_indices
print(json.dumps({'baseline': float(np.abs(v[0]).max()), 'later': float(v[1,0])}))
""")
    assert actual["baseline"] == 0
    assert abs(actual["later"] - 110) < 1e-8


def test_source_audit_and_approved_set_gate_before_writes() -> None:
    actual = run_code("""
messages = []
for action in (lambda:m.validate_source_audit(None),lambda:m.approved_mask_check(set())):
    try:
        action()
    except ValueError as exc:
        messages.append(str(exc))
print(json.dumps({'messages':messages}))
""")
    assert "--source-audit" in actual["messages"][0]
    assert "simulation mask mismatch" in actual["messages"][1]


def test_zero_remaining_channel_rejected() -> None:
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


def test_archive_idempotent_and_hash_protected() -> None:
    actual = run_code("""
import tempfile
with tempfile.TemporaryDirectory() as td:
    m.SUB_ROOT=Path(td)
    m.TABLE_ROOT=m.SUB_ROOT/'Sub/tables/TopographySensitivity'
    m.LOG_PATH=m.SUB_ROOT/'Sub/logs/old.json'
    m.HISTORY_ROOT=m.SUB_ROOT/'Sub/history/v1'
    m.write_json(m.LOG_PATH, {'script_version':'v1'})
    m.write_json(m.TABLE_ROOT/'ProtectedInputOutputInventory.json', {})
    for name in m.TABLE_NAMES:
        m.write_csv(m.TABLE_ROOT/(name+'.csv'),[{'synthetic':1}])
    first=m.archive_prior_records()
    m.write_json(m.LOG_PATH, {'script_version':m.VERSION})
    second=m.archive_prior_records()
    assert first==second
    m.write_json(m.HISTORY_ROOT/'Sub/logs/old.json', {'script_version':'changed'})
    try:
        m.verify_archive()
    except ValueError as exc:
        print(json.dumps({'files':first['files'],'message':str(exc)}))
""")
    assert actual["files"] == 7
    assert "preserved prior" in actual["message"]


def test_extension_strict_factor_boundaries_support_and_missing_neighbors() -> None:
    actual = run_code("""
neighbors = np.tile(np.array([[1,2,3,4]]), (5,1))
def flag(v, factor):
    return bool(m.qc.strict_neighbor_isolation_at_factor(np.array(v), neighbors, factor)[0])
records = {}
for factor in (1.8,3.0):
    records[str(factor)] = {
      'equal_high':flag([factor,1,1,1,10],factor),
      'above_high':flag([np.nextafter(factor,np.inf),1,1,1,10],factor),
      'equal_low':flag([1/factor,.1,1,1,1],factor),
      'below_low':flag([np.nextafter(1/factor,-np.inf),.1,1,1,1],factor),
      'two_only':flag([10,1,1,10,10],factor),
      'missing_center':flag([np.nan,1,1,1,1],factor),
      'two_finite':flag([.01,1,1,np.nan,np.nan],factor),
      'three_finite':flag([10,1,1,1,np.nan],factor),
      'zero_not_support':flag([10,0,1,1,10],factor)}
print(json.dumps(records))
""")
    expected = dict(equal_high=False, above_high=True, equal_low=False, below_low=True,
                    two_only=False, missing_center=False, two_finite=False, three_finite=True,
                    zero_not_support=False)
    assert actual == {"1.8": expected, "3.0": expected}


def test_extension_own_ratio_strict_and_z_inclusive_boundaries() -> None:
    actual = run_code("""
r=row(2)
r['ratio'][:12]=[2,.5,np.nextafter(2,np.inf),np.nextafter(.5,-np.inf),
                 3,.3,3,.3,3,.3,np.nan,0]
r['ratio_extension_neighbor_isolation'][:12]=True
r['ratio_residual_log2_cohort_z'][:12]=6
r['ratio_spatial_z'][:12]=3
r['ratio_residual_log2_cohort_z'][4]=np.nextafter(6,-np.inf)
r['ratio_residual_log2_cohort_z'][5]=-6
r['ratio_spatial_z'][6]=np.nextafter(3,-np.inf)
r['ratio_spatial_z'][7]=-3
r['ratio_extension_neighbor_isolation'][8]=False
r['ratio_residual_log2_cohort_z'][9]=np.nan
masks=m.qc.pathway_masks(r)
r['set']=1
print(json.dumps({'selected':np.flatnonzero(masks['spatial_change_extension']).tolist(),
 'set1_selected':int(m.qc.pathway_masks(r)['spatial_change_extension'].sum())}))
""")
    assert actual["selected"] == [2, 3, 5, 7]
    assert actual["set1_selected"] == 0


def test_extension_strong_neighbors_bypass_spatial_z_not_cohort_or_own_ratio() -> None:
    actual = run_code("""
r=row(6)
r['ratio'][:5]=[3,.3,3,.3,1]
r['ratio_extension_neighbor_isolation'][:5]=True
r['ratio_extension_strong_neighbor_isolation'][:5]=True
r['ratio_residual_log2_cohort_z'][:5]=[6,-6,5.99,-5.99,6]
r['ratio_spatial_z'][:5]=[.1,-.1,100,-100,100]
print(json.dumps({'selected':np.flatnonzero(
 m.qc.pathway_masks(r)['spatial_change_extension']).tolist()}))
""")
    assert actual["selected"] == [0, 1]


def test_v3_is_union_and_v2_audit_is_nonmutating_and_independent_of_stale_flags() -> None:
    actual = run_code("""
import copy
r=row(4)
spatial(r,1)
spatial(r,2,'median',-1)
r['top_share'][3]=.5
r['mean_median'][3]=3
r['mean_median_cohort_z'][3]=3.5
r['ratio'][4]=3
r['ratio_extension_neighbor_isolation'][4]=True
r['ratio_residual_log2_cohort_z'][4]=6
r['ratio_spatial_z'][4]=3
old_masks=m.qc.pathway_masks_v2(r)
new_masks=m.qc.pathway_masks(r)
for key in old_masks:
    np.testing.assert_array_equal(old_masks[key],new_masks[key])
new_flags,new_causes=m.qc.evaluate_flags([r],m.PARENT.EXPECTED_CHANNEL_NAMES)
snapshot=copy.deepcopy(r)
old_flags,old_causes=m.qc.evaluate_flags([r],m.PARENT.EXPECTED_CHANNEL_NAMES,
 include_change_extension=False,annotate_rows=False)
assert r.keys()==snapshot.keys()
for key in r:
    if isinstance(r[key],np.ndarray):
        np.testing.assert_array_equal(r[key],snapshot[key])
    else:
        assert r[key]==snapshot[key]
print(json.dumps({'new':sorted(k[2] for k in new_causes),
 'old':sorted(k[2] for k in old_causes),'old_retained':set(old_causes)<=set(new_causes),
 'new_reason':next(f['reason'] for f in new_flags
                   if f['channel']==m.PARENT.EXPECTED_CHANNEL_NAMES[4]),
 'no_stale_flag':all('flag_spatial_change_extension' not in f for f in old_flags)}))
""")
    assert actual == dict(new=[1, 2, 3, 4], old=[1, 2, 3], old_retained=True,
                         new_reason="spatial_change_extension", no_stale_flag=True)


def test_collects_extension_metrics_without_changing_frozen_cohort_references() -> None:
    actual = run_code("""
items=[item('900-901'),item('902-903','VRohtoPremium')]
items[0]['eye_drop'].source.sets[2].psd_band_mean[:,0]=20
rows=m.collect_condition_metrics(items)
_,neighbors=m.electrode_geometry()
snapshot=[{k:v.copy() for k,v in r.items() if isinstance(v,np.ndarray)} for r in rows]
for r in rows:
    np.testing.assert_array_equal(r['ratio_extension_neighbor_isolation'],
      m.qc.strict_neighbor_isolation_at_factor(r['ratio'],neighbors,1.8))
    np.testing.assert_array_equal(r['ratio_extension_strong_neighbor_isolation'],
      m.qc.strict_neighbor_isolation_at_factor(r['ratio'],neighbors,3.0))
m.qc.evaluate_flags(rows,m.PARENT.EXPECTED_CHANNEL_NAMES)
for r,original in zip(rows,snapshot,strict=True):
    for key,value in original.items():
        np.testing.assert_array_equal(r[key],value)
print(json.dumps({'unchanged':True,'rows':len(rows)}))
""")
    assert actual == {"unchanged": True, "rows": 24}
