"""No1--3 entry safeguards; synthetic data only, isolated from mutable band wrappers."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "解析プログラム/Phase4_脳波解析"
MODULE = "Phase4_No123_sub_TopographySensitivity"


def run_code(body: str) -> dict:
    setup = f"""
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import h5py
sys.path.insert(0, {str(SCRIPTS)!r})
import {MODULE} as m

def session(sid, factor=1.0, missing=()):
    sets = {{}}
    for n in range(1, 7):
        if n not in missing:
            sets[n] = SimpleNamespace(psd_band_mean=np.ones((180, 32)) * (1 if n==1 else factor),
                                     relative_seconds_center=np.arange(180.))
    source = SimpleNamespace(session_id=str(sid), channel_names=m.PARENT.EXPECTED_CHANNEL_NAMES,
                             sets=sets)
    return m.engine.make_change_session(source)

def item(pair, product, eye_factor=1., control_factor=1., eye_missing=()):
    a, b = pair.split('-')
    return {{'spec': SimpleNamespace(pair_id=pair), 'product_dir': product,
            'eye_drop': session(a, eye_factor, eye_missing), 'control':session(b,control_factor)}}
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


def test_band_signatures_paths_and_shared_engine_remain_unchanged() -> None:
    actual = run_code("""
before = m.PARENT.analysis_configuration()
hashes = [m.expected_cache_hash(c, [{'fake': 'synthetic'}]) for c in m.CONFIGS]
assert before == m.PARENT.analysis_configuration()
legacy=dict(before);legacy.pop('analysis_stem');legacy.pop('focus_channel')
expected_legacy=m.hashlib.sha256(json.dumps({'configuration':legacy,'inputs':[{'fake':'synthetic'}]},
                                          sort_keys=True,separators=(',',':')).encode()).hexdigest()
assert hashes[0]==expected_legacy
print(json.dumps({'stems':[c.output_analysis_stem for c in m.CONFIGS],
 'cache_paths':[str(m.cache_root(c)) for c in m.CONFIGS],
 'hashes':hashes, 'outputs':[str(p) for p in m.generated_paths()],
 'freqs':m.PARENT.INCLUDED_FREQUENCIES_HZ.tolist(), 'stem':m.engine.ANALYSIS_STEM,
 'bands':{k:list(v[1]) for k,v in m.BAND_SETTINGS.items()}}))
""")
    assert actual["freqs"] == [4, 5, 6, 7]
    assert actual["stem"] == "No1_sub_FmThetaChange"
    assert actual["bands"] == {"No1": [4, 5, 6, 7], "No2": list(range(8, 16)), "No3": [1, 2, 3]}
    assert len(set(actual["hashes"])) == 3
    assert len(actual["outputs"]) == 12
    assert all(path.endswith("PSDTimeSeries") for path in actual["cache_paths"])
    assert all("BeforeOutlierExclusion" not in p for p in actual["outputs"])
    assert all("No10" not in p for p in actual["outputs"])


def test_imported_mutable_wrapper_is_rejected() -> None:
    actual = run_code("""
m.PARENT.ANALYSIS_STEM = 'No10_FzLowAlpha'
try:
    m.expected_cache_hash(m.CONFIGS[0], [])
except ValueError as error:
    print(json.dumps({'error':str(error)}))
else:
    raise AssertionError('mutable shared context accepted')
""")
    assert "dedicated process" in actual["error"]


def test_mask_exactness_and_v2_subset_not_count_only() -> None:
    actual = run_code("""
a = {('900-901',2,0), ('902-903',3,1)}
b = {('900-901',2,0), ('904-905',3,1)}
assert m.mask_digest(a) != m.mask_digest(b)
m.APPROVED = {'No1':(2,m.mask_digest(a))}
ok = m.approved_mask_check(m.CONFIGS[0],a)
failed=[]
for f in (lambda:m.approved_mask_check(m.CONFIGS[0],b), lambda:m.verify_v2_component(a,b)):
    try:f()
    except ValueError:failed.append(True)
assert len(failed)==2
retained=m.verify_v2_component({('900-901',2,0)},a)
print(json.dumps({'ok':ok,'retained':retained}))
""")
    assert actual["ok"]["exact_approved_set_match"]
    assert actual["retained"]["all_v2_component_cells_retained"]
    assert not actual["retained"]["old_no123_sustained_mask_used"]


def test_independent_group_calculation_direction_pair_or_and_missing() -> None:
    actual = run_code("""
items=[item('900-901','CCube',3,1),item('902-903','CCube',2,1,eye_missing=(4,)),
       item('904-905','VRohtoPremium',1,2),item('906-907','VRohtoPremium',1,3)]
causes={('900-901',2,0):[], ('902-903',4,0):[], ('904-905',3,1):[]}
groups,eligible,excluded,_,applied=m.prior.group_topographies(m.CONFIGS[0],items,causes)
m.verify_excluded_group(items,causes,groups)
assert ('902-903',4,0) not in applied
print(json.dumps({'cc':groups['CCube']['group'][1,0],
 'v':groups['VRohtoPremium']['group'][2,1], 'excluded':excluded,
 'n':groups['CCube']['valid_n'][3,0].item(),
 'baseline_max':max(abs(v['group'][0]).max() for v in groups.values())}))
""")
    assert actual == {"cc": 100.0, "v": -200.0, "excluded": 2, "n": 1, "baseline_max": 0.0}


def test_archive_exact_hash_immutable_and_old_records_retired() -> None:
    actual = run_code("""
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary); source=root/'Sub/tables/old.csv'; source.parent.mkdir(parents=True)
    source.write_text('value\\n1\\n')
    history=root/'Sub/history/old'
    first=m.archive_records(root,history,[source])
    again=m.archive_records(root,history,[source])
    assert first==again
    m.retire_old_records(root,history)
    assert not source.exists()
    assert m.verify_archive(history)==first
    assert m.archive_records(root,history,[source])==first
    (history/'Sub/tables/old.csv').write_text('changed')
    try:m.verify_archive(history)
    except ValueError:failed=True
    else:failed=False
    print(json.dumps({'files':first['files'],'tampering_rejected':failed}))
""")
    assert actual == {"files": 1, "tampering_rejected": True}


def test_archive_refuses_png_and_changed_current_record() -> None:
    actual = run_code("""
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary); png=root/'old.png'; png.write_bytes(b'png')
    failed=[]
    try:m.archive_records(root,root/'history',[png])
    except ValueError:failed.append('png')
    source=root/'old.json'; source.write_text('{}')
    m.archive_records(root,root/'history',[source])
    source.write_text('{"changed":true}')
    try:m.archive_records(root,root/'history',[source])
    except ValueError:failed.append('changed')
    print(json.dumps({'rejected':failed}))
""")
    assert actual["rejected"] == ["png", "changed"]


def test_review_gate_requires_all_figures_six_observations_and_evidence() -> None:
    actual = run_code("""
from copy import deepcopy
outputs=[{'path':f'/fake/{n}.png','sha256':str(n)} for n in range(12)]
summary={'outputs':outputs}
review={'checked_at':'now','reviewed_pngs':[{**p,'reviewed':True} for p in outputs],
        'observations':{c.key:{p:'observed residuals, not proof of effect' for p in m.PRODUCTS}
                        for c in m.CONFIGS},
        'tests':'passed synthetic checks','notion_pages':['page'],
        'git':{'head':'abc','remote_head':'abc','remote_verified':True}}
m.validate_review_record(review,summary,'abc')
bad=[]
r=deepcopy(review);r['reviewed_pngs'].pop();bad.append(r)
r=deepcopy(review);r['reviewed_pngs'][-1]=r['reviewed_pngs'][0];bad.append(r)
r=deepcopy(review);r['reviewed_pngs'][0]['reviewed']=False;bad.append(r)
r=deepcopy(review);r['observations']['No2'].pop('CCube');bad.append(r)
r=deepcopy(review);r['git']['remote_verified']=False;bad.append(r)
r=deepcopy(review);r['notion_pages']=[];bad.append(r)
r=deepcopy(review);r['tests']=[];bad.append(r)
failures=0
for r in bad:
    try:m.validate_review_record(r,summary,'abc')
    except ValueError:failures+=1
print(json.dumps({'rejected':failures,'attempted':len(bad)}))
""")
    assert actual == {"rejected": 7, "attempted": 7}


def test_saved_log_mask_independent_reconstruction_and_tampering() -> None:
    actual = run_code("""
with tempfile.TemporaryDirectory() as temporary:
    path=Path(temporary)/'cache.h5'
    sets={}
    for n in (1,2,3,5,6):
        values=np.ones((100,32),dtype=np.float32)*(n+1)
        values[99,0]=1e8
        fractions=np.zeros(100);fractions[0]=.01
        sets[n]=SimpleNamespace(psd_band_mean=values,ica_training_mask_fraction=fractions)
    expected=m.PARENT.calculate_log3sd_exclusion(sets)
    with h5py.File(path,'w') as h:
        for n,result in sets.items():
            g=h.create_group(f'sets/Set{n}')
            g['psd_band_mean']=result.psd_band_mean
            g['ica_training_mask_fraction']=result.ica_training_mask_fraction
            g['log3sd_outlier_mask']=expected['masks'][n]
        q=h.create_group('qc')
        for field,key in [('mean','mean'),('sd','sample_sd'),('threshold_log','threshold_log'),
                          ('threshold_linear','threshold_linear')]:
            q[f'log3sd_{field}_by_channel']=expected[key]
        for field in ('excluded_count','valid_count','excluded_rate'):
            q[f'log3sd_{field}_by_set_ch']=expected[f'{field}_by_set_ch']
    with h5py.File(path,'r') as h:m.verify_saved_log_mask(h)
    with h5py.File(path,'a') as h:h['sets/Set1/log3sd_outlier_mask'][1,0]=True
    try:
        with h5py.File(path,'r') as h:m.verify_saved_log_mask(h)
    except AssertionError:failed=True
    else:failed=False
    print(json.dumps({'tampering_rejected':failed}))
""")
    assert actual["tampering_rejected"]


def test_png_preflight_preserves_before_and_rejects_unknown_outputs() -> None:
    actual = run_code("""
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary)
    m.CONFIGS=m.CONFIGS[:1];m.PRODUCTS=('CCube',)
    m.original_path=lambda c,p:root/'primary/original.png'
    m.output_path=lambda c,p:root/'primary/latest.png'
    m.legacy_png=lambda c,p:root/'primary/obsolete.png'
    m.comparison_path=lambda c,p,s:root/f'comparison/{s}.png'
    (root/'primary').mkdir();(root/'comparison').mkdir()
    (root/'primary/original.png').write_bytes(b'same')
    (root/'comparison/Before.png').write_bytes(b'same')
    m.input_png_preflight()
    (root/'primary/unexpected.png').write_bytes(b'do not delete')
    try:m.input_png_preflight()
    except ValueError:unknown=True
    else:unknown=False
    (root/'primary/unexpected.png').unlink()
    (root/'comparison/Before.png').write_bytes(b'different')
    try:m.input_png_preflight()
    except ValueError:before=True
    else:before=False
    print(json.dumps({'unknown_rejected':unknown,'before_changed_rejected':before}))
""")
    assert actual == {"unknown_rejected": True, "before_changed_rejected": True}


def test_source_audit_rejects_hash_and_unverified_notion() -> None:
    actual = run_code("""
with tempfile.TemporaryDirectory() as temporary:
    root=Path(temporary);m.MANIFEST=root/'manifest.csv';m.MANIFEST.write_text('synthetic')
    audit=root/'source.json';checks=[]
    valid={'participant_manifest_sha256':m.digest(m.MANIFEST),'notion_verified':True,
           'checked_at':'now','source_pages':['page'],'analysis_scope':['No1','No2','No3']}
    audit.write_text(json.dumps(valid));m.validate_source_audit(audit)
    for key,value in [('notion_verified',False),('participant_manifest_sha256','wrong'),
                      ('analysis_scope',['No10'])]:
        audit.write_text(json.dumps({**valid,key:value}))
        try:m.validate_source_audit(audit)
        except ValueError:checks.append(key)
    print(json.dumps({'checks':checks}))
""")
    assert len(actual["checks"]) == 3


def test_entry_never_imports_no10_mutating_runner_or_band_wrapper() -> None:
    actual = run_code("""
for name in ('Phase4_No10_sub_TopographySensitivity','Phase4_No10_sub_FzLowAlphaChange',
             'Phase4_No2_OccipitalAlpha','Phase4_No3_FrontalDelta'):
    assert name not in sys.modules, name
print(json.dumps({'pure_helper':m.qc.__name__,'source_files':list(m.source_hashes())}))
""")
    assert actual["pure_helper"] == "phase4_no10_topography_spatiotemporal"
    assert len(actual["source_files"]) == 6


def test_live_git_gate_checks_clean_paths_and_actual_remote() -> None:
    actual = run_code("""
state={'status':' M .DS_Store\\0','remote':'abc\\trefs/heads/main\\n'}
def fake_git(command,text):
    if 'symbolic-ref' in command:return 'main\\n'
    if 'status' in command:return state['status']
    if 'ls-remote' in command:return state['remote']
    raise AssertionError(command)
m.subprocess.check_output=fake_git
ok=m.verify_git_delivery('abc')
failures=[]
state['status']=' M docs/example.md\\0'
try:m.verify_git_delivery('abc')
except ValueError:failures.append('dirty')
state['status']='';state['remote']='different\\trefs/heads/main\\n'
try:m.verify_git_delivery('abc')
except ValueError:failures.append('remote')
print(json.dumps({'ok':ok['remote_verified'],'failures':failures}))
""")
    assert actual == {"ok": True, "failures": ["dirty", "remote"]}


def test_independent_audit_requires_scope_hash_and_actual_agreement() -> None:
    actual = run_code("""
with tempfile.TemporaryDirectory() as temporary:
    m.INDEPENDENT_AUDIT_PATH=Path(temporary)/'audit.json'
    summary={'analyses':{c.key:{'approved_simulation_check':{'sha256':m.APPROVED[c.key][1]}}
                         for c in m.CONFIGS}}
    audit={'status':'passed','checked_at':'now','source_cache_hashes_match':True,
           'analyses':{c.key:{'mask_sha256':m.APPROVED[c.key][1],
                    'group_values_match':True,'valid_n_match':True} for c in m.CONFIGS}}
    m.INDEPENDENT_AUDIT_PATH.write_text(json.dumps(audit))
    review={'independent_audit':{'path':str(m.INDEPENDENT_AUDIT_PATH),
                               'sha256':m.digest(m.INDEPENDENT_AUDIT_PATH)}}
    ok=m.validate_independent_audit(review,summary)
    audit['analyses']['No2']['valid_n_match']=False
    m.INDEPENDENT_AUDIT_PATH.write_text(json.dumps(audit))
    review['independent_audit']['sha256']=m.digest(m.INDEPENDENT_AUDIT_PATH)
    try:m.validate_independent_audit(review,summary)
    except ValueError:failed=True
    else:failed=False
    print(json.dumps({'ok':ok['status'],'disagreement_rejected':failed}))
""")
    assert actual == {"ok": "passed", "disagreement_rejected": True}
