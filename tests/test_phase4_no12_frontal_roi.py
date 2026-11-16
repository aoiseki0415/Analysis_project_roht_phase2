"""No12 cache-only adapters preserve source contracts and ROI calculation order."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "解析プログラム" / "Phase4_脳波解析"


def _run(body: str) -> dict[str, object]:
    if body.startswith(FIXTURE):
        body = FIXTURE + textwrap.dedent(body[len(FIXTURE) :])
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import json,sys\nsys.path.insert(0, {str(SCRIPT_DIR)!r})\n" + textwrap.dedent(body),
        ],
        cwd=ROOT,
        env={**os.environ, "MPLBACKEND": "Agg", "MPLCONFIGDIR": "/tmp/mplconfig-roht"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return json.loads(result.stdout)


FIXTURE = """
import numpy as np
import Phase4_No12_FrontalROILowAlpha as absolute
import Phase4_No12_sub_FrontalROILowAlphaChange as sub
import phase4_no12_cached_analysis as helper
a,b = absolute.engine,sub.engine
def source(sid='101',condition='Eye Drop',missing=()):
    sets = {}
    for number in range(1,7):
        if number in missing:
            continue
        t = np.arange(121,dtype=float)
        progress = t/120*100
        data = np.full((121,32),900.0)
        for j,ch in enumerate(helper.ROI_CHANNELS):
            data[:,a.EXPECTED_CHANNEL_NAMES.index(ch)] = number*(j+1)*2+t/120
        before = data.copy()
        mask = np.zeros(data.shape,bool)
        sets[number] = a.SetPSD(number,data,t,10000+t,progress,
             (number-1)*100+progress,(t*256).astype(int),np.zeros(121),before,mask)
    return a.SessionPSD(sid,condition,'101-201','VRohtoPremium',
                       a.EXPECTED_CHANNEL_NAMES.copy(),sets,np.zeros(32,bool))
"""


def test_identity_colors_paths_and_source_engines_remain_unchanged() -> None:
    result = _run("""
        import Phase4_No10_FzLowAlpha as source
        import Phase4_No11_PzLowAlpha as pz
        from pathlib import Path
        source_config=source.engine.analysis_configuration()
        source_hash=source.engine.configuration_hash([])
        pz_config=pz.engine.analysis_configuration()
        import Phase4_No12_FrontalROILowAlpha as absolute
        import Phase4_No12_sub_FrontalROILowAlphaChange as sub
        import phase4_no12_cached_analysis as helper
        a,b=absolute.engine,sub.engine
        assert source.engine.analysis_configuration()==source_config
        assert source.engine.configuration_hash([])==source_hash
        assert pz.engine.analysis_configuration()==pz_config
        assert a is not source.engine and a is not pz.engine
        assert a.FOCUS_CHANNEL==b.FOCUS_CHANNEL=='FrontalROI'
        assert a.validate_cache is source.engine.validate_cache
        assert a.DEFAULT_CACHE_ROOT==b.DEFAULT_CACHE_ROOT==source.engine.DEFAULT_CACHE_ROOT
        assert a.normalize_product('CCube')[2:]==('#4B4B4B','#787878')
        assert a.normalize_product('VRohtoPremium')[2:]==('#909090','#B0B0B0')
        assert (a.CONTROL_COLOR,a.CONTROL_QUANTIFICATION_COLOR)==('#402B5D','#66547D')
        assert not b.INCLUDE_TOPOGRAPHY and b.ALTERNATE_GROUP_EXCLUSIONS=={}
        assert b.ALTERNATE_GROUP_SUFFIX is None
        for paths in (a._output_directories(Path('/tmp/synthetic'),'CCube'),
                      b.output_directories(Path('/tmp/synthetic'),'CCube')):
            assert not any(k.startswith('topography') for k in paths)
            assert all('No12' in str(p) and 'No11' not in str(p) for p in paths.values())
            assert 'roi_quality_tables' in paths
        for function in (a.compute_session_cache,a.calculate_set_psd,a._write_cache,
                         a.plot_topography_grid,b.plot_topography):
            try: function()
            except RuntimeError: pass
            else: raise AssertionError('cache or topography generation allowed')
        config=helper.target_configuration(a)
        assert config['roi_channels']==['F3','Fz','F4','FC5','FC1','FC2','FC6','C3','Cz','C4']
        assert config['roi_valid_channel_bitmask_dtype']=='uint16'
        assert config['roi_valid_channel_bitweights']['Cz']==256
        assert config['roi_valid_channel_bitweights']['C4']==512
        assert a.SCRIPT_VERSION=='20261116_frontocentral_roi10_lowalpha_cached_v2'
        assert b.SCRIPT_VERSION=='20261116_frontocentral_roi10_lowalpha_change_cached_v2'
        assert helper.configuration_hash(config)==helper.configuration_hash(config)
        assert len(config['source_script_sha256'])==4
        print(json.dumps({'ok':True}))
    """)
    assert result["ok"] is True


def test_roi_finite_mean_and_masks_preserve_every_source_value() -> None:
    result = _run(
        FIXTURE
        + """
        original=source()
        idx=helper.roi_indices(original)
        values=original.sets[1]
        values.ica_training_mask_fraction[0]=.01
        values.psd_band_mean[0,:]=np.nan
        values.psd_before_log3sd_exclusion[0,:]=np.nan
        for k in range(1,11):
            values.psd_band_mean[k,idx[k:]]=np.nan
            values.log3sd_outlier_mask[k,idx[k:]]=True
        snapshot=values.psd_band_mean.copy()
        roi=helper.aggregate_roi_session(original)
        expected=[]
        for row in snapshot[:,idx]:
            finite=row[np.isfinite(row)]
            expected.append(finite.mean() if len(finite) else np.nan)
        np.testing.assert_allclose(roi.sets[1].psd_band_mean[:,0],expected,equal_nan=True)
        np.testing.assert_array_equal(original.sets[1].psd_band_mean,snapshot)
        assert roi.channel_names==['FrontalROI']
        assert np.isnan(roi.sets[1].psd_band_mean[0,0])
        assert np.isfinite(roi.sets[1].psd_band_mean[1,0])
        spec=a.ParticipantSpec('101','201','101','VRohtoPremium')
        control=helper.aggregate_roi_session(source('201','Control'))
        item=dict(spec=spec,product_dir='VRohtoPremium',eye_drop=roi,control=control)
        tables=helper.roi_quality_tables([item])
        rows=tables['ROIWindowQuality'].query('SessionID=="101" and Set==1')
        assert rows.ValidChannelCount.iloc[:11].tolist()==list(range(11))
        assert rows.ValidChannelBits.iloc[:11].tolist()==[2**k-1 for k in range(11)]
        assert rows.ValidChannelCountBeforeLog3SD.iloc[:11].tolist()==[0]+[10]*10
        assert rows.ValidChannelBits.dtype==np.dtype('uint16')
        assert rows.ValidChannelBitsBeforeLog3SD.dtype==np.dtype('uint16')
        assert rows.ValidChannelBitsBeforeLog3SD.iloc[1]==1023
        summary=tables['ROISetQuality'].query('SessionID=="101" and Set==1').iloc[0]
        assert sum(summary[f'AfterLog3SD_Valid{k}_Count'] for k in range(11))==121
        assert summary.AfterLog3SD_Valid10_Count==111
        coverage=tables['ROIChannelCoverage']
        assert len(coverage)==2*6*10
        assert coverage.Log3SDExcludedCount.sum()==45
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True


def test_roi_baseline_and_smoothing_order_not_average_of_channel_changes() -> None:
    result = _run(
        FIXTURE
        + """
        original=source()
        idx=helper.roi_indices(original)
        baseline_channels=np.array([1,10,100,10,1,2,20,200,20,2])
        later_channels=np.array([10,10,100,10,1,2,20,200,20,2])
        original.sets[1].psd_band_mean[:,idx]=baseline_channels
        original.sets[2].psd_band_mean[:,idx]=later_channels
        # Missing a different contributor over part of the interval.
        original.sets[2].psd_band_mean[30:45,idx[2]]=np.nan
        original.sets[2].log3sd_outlier_mask[30:45,idx[2]]=True
        for number in (1,2):
            original.sets[number].psd_before_log3sd_exclusion[:]=original.sets[number].psd_band_mean
        roi=helper.aggregate_roi_session(original)
        change=b.make_change_session(roi)
        baseline=baseline_channels.mean()
        np.testing.assert_allclose(change.baseline_by_channel,[baseline],rtol=1e-14)
        expected=(roi.sets[2].psd_band_mean[:,0]/baseline-1)*100
        np.testing.assert_allclose(b.set_change_values(change,2,0),expected)
        assert not np.isclose(expected[0],np.mean((later_channels/baseline_channels-1)*100))
        plotted=b.set_change_values(change,2,0,smoothing_seconds=60)
        np.testing.assert_allclose(plotted,a.centered_nanmean(expected,60))
        raw=original.sets[2].psd_band_mean[:,idx]
        smooth_before_roi=np.mean(np.stack([a.centered_nanmean(raw[:,i],60)
                                            for i in range(10)],axis=1),axis=1)
        assert not np.allclose(a.centered_nanmean(roi.sets[2].psd_band_mean[:,0],60),
                               smooth_before_roi)
        assert abs(b.set_change_values(change,1,0).mean())<1e-10
        item=dict(spec=a.ParticipantSpec('101','201','101','VRohtoPremium'),
                  product_dir='VRohtoPremium',eye_drop=change,
                  control=b.make_change_session(helper.aggregate_roi_session(source('201','Control'))))
        baseline_table=b.baseline_table([item])
        assert set(baseline_table.Channel)=={'FrontalROI'}
        assert set(baseline_table.Set1FiniteROIWindowCount)=={121}
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True


def test_roi_names_not_column_positions_and_upper_bits_remain_independent() -> None:
    result = _run(
        FIXTURE
        + """
        original=source()
        indices=helper.roi_indices(original)
        piece=original.sets[1]
        piece.psd_band_mean[0,indices[:8]]=np.nan
        piece.log3sd_outlier_mask[0,indices[:8]]=True
        expected=helper.aggregate_roi_session(original)
        assert expected.sets[1].psd_band_mean[0,0]==19
        permutation=np.roll(np.arange(32),7)
        original.channel_names=[original.channel_names[j] for j in permutation]
        original.channel_excluded_mask=original.channel_excluded_mask[permutation]
        for piece in original.sets.values():
            for name in ('psd_band_mean','psd_before_log3sd_exclusion','log3sd_outlier_mask'):
                setattr(piece,name,getattr(piece,name)[:,permutation].copy())
            # Excluded ROI candidates must not leak into the ten-channel mean.
            for ch in ('F7','F8'):
                column=original.channel_names.index(ch)
                piece.psd_band_mean[:,column]=1e12
                piece.psd_before_log3sd_exclusion[:,column]=1e12
        actual=helper.aggregate_roi_session(original)
        for number in range(1,7):
            np.testing.assert_array_equal(actual.sets[number].psd_band_mean,
                                          expected.sets[number].psd_band_mean)
        item=dict(spec=a.ParticipantSpec('101','201','101','VRohtoPremium'),
                  product_dir='VRohtoPremium',eye_drop=actual,
                  control=helper.aggregate_roi_session(source('201','Control')))
        table=helper.roi_quality_tables([item])['ROIWindowQuality']
        row=table.query('SessionID=="101" and Set==1 and WindowIndex==0').iloc[0]
        assert row.ValidChannelCount==2 and row.ValidChannelBits==768
        for ch in ('FC5','FC6','C3','Cz','C4'):
            malformed=source()
            malformed.channel_names[malformed.channel_names.index(ch)]='unknown'
            try: helper.aggregate_roi_session(malformed)
            except ValueError as error: assert 'missing ROI channels' in str(error)
            else: raise AssertionError('accepted missing '+ch)
        for malformed in (np.zeros((3,5)),np.zeros(10),np.zeros((3,32))):
            try: helper.finite_channel_mean(malformed)
            except ValueError as error: assert 'ten-channel' in str(error)
            else: raise AssertionError('accepted stale ROI shape')
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True


def test_pair_mask_and_quantification_reuse_unsmoothed_roi_windows() -> None:
    result = _run(
        FIXTURE
        + """
        eye=helper.aggregate_roi_session(source())
        control=helper.aggregate_roi_session(source('201','Control',missing=(3,)))
        item=dict(spec=a.ParticipantSpec('101','201','101','VRohtoPremium'),
                  product_dir='VRohtoPremium',eye_drop=eye,control=control)
        values=a.build_quantification([item],'VRohtoPremium')
        assert np.isnan(values[values.Set==3].iloc[0].EyeDrop_PSD_uV2_per_Hz)
        for number in (1,2,4,5,6):
            actual=values[values.Set==number].iloc[0].EyeDrop_PSD_uV2_per_Hz
            assert np.isclose(actual,np.nanmean(eye.sets[number].psd_band_mean[:,0]))
        grand,_=a.build_grand_average([item],'VRohtoPremium')
        assert grand.loc[grand.Set==3,'EyeDrop_Mean_PSD_uV2_per_Hz'].isna().all()
        assert len(grand)==600
        change_item=item|dict(eye_drop=b.make_change_session(eye),control=b.make_change_session(control))
        subvalues=b.build_quantification([change_item],'VRohtoPremium')
        assert abs(subvalues[subvalues.Set==1].iloc[0].EyeDrop_PSDChange_pct)<1e-8
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True


def test_rejects_missing_duplicate_channels_unmasked_input_and_wrong_source_band() -> None:
    result = _run(
        FIXTURE
        + """
        for corruption in ('missing','duplicate','phase1','log3sd','length'):
            s=source()
            if corruption=='missing': s.channel_names[s.channel_names.index('F3')]='unknown'
            if corruption=='duplicate': s.channel_names[0]=s.channel_names[1]
            if corruption=='phase1': s.sets[1].ica_training_mask_fraction[0]=.5
            if corruption=='log3sd': s.sets[1].log3sd_outlier_mask[0,0]=True
            if corruption=='length': s.sets[1].set_progress_pct=np.ones(120)
            try: helper.aggregate_roi_session(s)
            except ValueError: pass
            else: raise AssertionError(corruption)
        helper.source_engine.INCLUDED_FREQUENCIES_HZ=np.array([8.,9.,10.,11.])
        try: helper.build_absolute_engine()
        except ValueError: pass
        else: raise AssertionError('accepted stale 8–11 Hz source')
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True


def test_no12_cli_only_allows_existing_cache_and_authorized_output_roots() -> None:
    result = _run("""
        import argparse
        from pathlib import Path
        import phase4_no12_cached_analysis as helper
        source=helper.source_engine
        helper._checked_roots(argparse.Namespace(cache_root=source.DEFAULT_CACHE_ROOT,
                                                output_root=source.DEFAULT_OUTPUT_ROOT))
        for key in ('cache_root','output_root'):
            args=argparse.Namespace(cache_root=source.DEFAULT_CACHE_ROOT,
                                    output_root=source.DEFAULT_OUTPUT_ROOT)
            setattr(args,key,Path('/tmp/not-authorized'))
            try: helper._checked_roots(args)
            except ValueError: pass
            else: raise AssertionError('unexpected root accepted')
        print(json.dumps({'ok':True}))
    """)
    assert result["ok"] is True


def test_loaded_roi_uses_source_hash_masks_and_keeps_cache_readonly() -> None:
    result = _run("""
        import tempfile
        from pathlib import Path
        import h5py
        import numpy as np
        import Phase4_No12_FrontalROILowAlpha as wrapper
        import phase4_no12_cached_analysis as helper
        source,target=helper.source_engine,wrapper.engine
        with tempfile.TemporaryDirectory(prefix='no12-synthetic-cache-') as temporary:
            root=Path(temporary)
            signal=root/'synthetic_source.bin'
            signal.write_bytes(b'synthetic source')
            stat=signal.stat()
            fingerprints=[{'path':str(signal),'size':stat.st_size,'mtime_ns':stat.st_mtime_ns}]
            spec=source.ParticipantSpec('901','902','902','CCube')
            target.validate_participant_specs([spec])
            t=np.arange(121,dtype=float)
            data=np.full((121,32),2,dtype=np.float32)
            fz=source.EXPECTED_CHANNEL_NAMES.index('Fz')
            data[5,fz]=1e10
            fraction=np.zeros(121)
            fraction[2]=.01
            piece=source.SetPSD(1,data,t,1000+t,t/120*100,t/120*100,
                                (t*256).astype(int),fraction)
            path=source.cache_path(root,spec,'902')
            config_hash=source.configuration_hash(fingerprints)
            source._write_cache(path,spec,'902',{1:piece},{1:signal},np.zeros(32,bool),
                                '[]',config_hash,fingerprints,
                                source.calculate_log3sd_exclusion({1:piece}))
            original_hash=helper._sha256(path)
            roi=target.load_session_cache(path)
            assert helper._sha256(path)==original_hash
            assert roi.channel_names==['FrontalROI']
            assert np.isnan(roi.sets[1].psd_band_mean[2,0])
            assert roi.sets[1].psd_band_mean[5,0]==2
            assert np.isnan(roi.source_session.sets[1].psd_band_mean[5,fz])
            assert roi.sets[1].psd_before_log3sd_exclusion[5,0]>1e9
            with h5py.File(path,'r+') as handle:
                handle.attrs['configuration_hash']=target.configuration_hash(fingerprints)
            try: target.load_session_cache(path)
            except ValueError as error: assert 'configuration hash' in str(error)
            else: raise AssertionError('target identity accepted as source identity')
        print(json.dumps({'ok':True}))
    """)
    assert result["ok"] is True


def test_all_sets_is_window_weighted_and_set1_remains_included() -> None:
    result = _run(
        FIXTURE
        + """
        originals=[source(),source('201','Control')]
        for original in originals:
            original.sets={n:original.sets[n] for n in (1,2)}
            for n,scalar in ((1,2),(2,10)):
                original.sets[n].psd_band_mean[:]=scalar
                original.sets[n].psd_before_log3sd_exclusion[:]=scalar
            piece=original.sets[1]
            for field in vars(piece):
                values=getattr(piece,field)
                if isinstance(values,np.ndarray): setattr(piece,field,values[:60].copy())
        roi=[helper.aggregate_roi_session(s) for s in originals]
        item=dict(spec=a.ParticipantSpec('101','201','101','VRohtoPremium'),
                  product_dir='VRohtoPremium',eye_drop=roi[0],control=roi[1])
        table=a.build_quantification([item],'VRohtoPremium')
        expected=(2*60+10*121)/181
        actual=table[table.Set=='All Sets'].iloc[0].EyeDrop_PSD_uV2_per_Hz
        assert np.isclose(actual,expected) and not np.isclose(actual,6)
        change_item=item|dict(eye_drop=b.make_change_session(roi[0]),
                             control=b.make_change_session(roi[1]))
        table=b.build_quantification([change_item],'VRohtoPremium')
        actual=table[table.Set=='All Sets'].iloc[0].EyeDrop_PSDChange_pct
        assert np.isclose(actual,400*121/181) and not np.isclose(actual,400)
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True


def test_one_missing_roi_channel_not_participant_exclusion_and_all_missing_baseline_fails() -> None:
    result = _run(
        FIXTURE
        + """
        original=source()
        indices=helper.roi_indices(original)
        original.sets[1].psd_band_mean[:,indices[0]]=np.nan
        original.sets[1].psd_before_log3sd_exclusion[:,indices[0]]=np.nan
        roi=helper.aggregate_roi_session(original)
        change=b.make_change_session(roi)
        assert np.isfinite(change.baseline_by_channel).all()
        original.sets[1].psd_band_mean[:,indices]=np.nan
        original.sets[1].psd_before_log3sd_exclusion[:,indices]=np.nan
        invalid=helper.aggregate_roi_session(original)
        try: b.make_change_session(invalid)
        except ValueError as error: assert 'invalid Set 1 baseline' in str(error)
        else: raise AssertionError('all-missing ROI baseline accepted')
        print(json.dumps({'ok':True}))
    """
    )
    assert result["ok"] is True
