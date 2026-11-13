"""Pz low-alpha adapters preserve No10 cache identity and the existing algorithms."""

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
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys\n"
            f"sys.path.insert(0, {str(SCRIPT_DIR)!r})\n" + textwrap.dedent(body),
        ],
        cwd=ROOT,
        env={**os.environ, "MPLBACKEND": "Agg", "MPLCONFIGDIR": "/tmp/mplconfig-roht"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_source_identity_stays_no10_while_target_is_pz_with_own_colors() -> None:
    result = _run(
        """
        import Phase4_No10_FzLowAlpha as source
        from pathlib import Path
        before = source.engine.analysis_configuration()
        before_hash = source.engine.configuration_hash([])
        import Phase4_No11_PzLowAlpha as absolute
        import Phase4_No11_sub_PzLowAlphaChange as sub
        a, b = absolute.engine, sub.engine
        assert source.engine.analysis_configuration() == before
        assert source.engine.configuration_hash([]) == before_hash
        assert a is not source.engine
        assert a.FOCUS_CHANNEL == b.FOCUS_CHANNEL == 'Pz'
        assert a.load_pair_item is source.engine.load_pair_item
        assert a.validate_cache is source.engine.validate_cache
        assert a.DEFAULT_CACHE_ROOT == b.DEFAULT_CACHE_ROOT == source.engine.DEFAULT_CACHE_ROOT
        assert b.INCLUDE_TOPOGRAPHY is False
        assert b.ALTERNATE_GROUP_EXCLUSIONS == {} and b.ALTERNATE_GROUP_SUFFIX is None
        assert 'No10_sub' not in b.write_group.__code__.co_filename
        assert b.SIGNIFICANCE_STAR_FACTOR_OVERRIDE == 1.08
        assert b.SIGNIFICANCE_STAR_FONTSIZE_OVERRIDE == 42
        assert a.normalize_product('CCube')[2:] == ('#476975', '#7B949D')
        assert a.normalize_product('VRohtoPremium')[2:] == ('#789BA3', '#A0B8BD')
        assert a.CONTROL_COLOR == '#402B5D'
        assert a.CONTROL_QUANTIFICATION_COLOR == '#66547D'
        assert all('Topography' not in str(p) for p in
                   a._output_directories(Path('/tmp/synthetic'), 'CCube').values())
        assert all('Topography' not in str(p) for p in
                   b.output_directories(Path('/tmp/synthetic'), 'CCube').values())
        for function in (a.compute_session_cache, a.calculate_set_psd, a._write_cache,
                         a.plot_topography_grid, b.plot_topography):
            try:
                function()
            except RuntimeError:
                pass
            else:
                raise AssertionError('No11 allowed generation of an out-of-scope result')
        print(json.dumps({'ok': True}))
        """
    )
    assert result["ok"] is True


def test_pz_values_baseline_missingness_and_smoothing_use_existing_functions() -> None:
    result = _run(
        """
        import numpy as np
        import Phase4_No11_PzLowAlpha as absolute
        import Phase4_No11_sub_PzLowAlphaChange as sub
        a, b = absolute.engine, sub.engine
        def session(sid, condition, scale, missing=()):
            sets = {}
            for s in range(1,7):
                if s in missing:
                    continue
                t = np.arange(121, dtype=float)
                p = t / t[-1] * 100
                data = np.ones((121,32)) * 900  # Fz differs markedly from Pz
                data[:,16] = scale * s + t / 120
                before = data.copy()
                data[20:25,16] = np.nan
                sets[s] = a.SetPSD(s, data, t, 10000+t, p, (s-1)*100+p,
                                  (t*256).astype(int), np.zeros(121), before)
            return a.SessionPSD(sid,condition,'101-201','VRohtoPremium',
                                a.EXPECTED_CHANNEL_NAMES,sets,np.zeros(32,bool))
        spec = a.ParticipantSpec('101','201','101','VRohtoPremium')
        eye, control = session('101','Eye Drop',2), session('201','Control',3,(3,))
        item = dict(spec=spec, product_dir='VRohtoPremium', eye_drop=eye, control=control)
        values = a.build_quantification([item], 'VRohtoPremium')
        for s in (1,2,4,5,6):
            row = values[values.Set == s].iloc[0]
            assert np.isclose(row.EyeDrop_PSD_uV2_per_Hz,
                              np.nanmean(eye.sets[s].psd_band_mean[:,16]))
        assert np.isnan(values[values.Set == 3].iloc[0].EyeDrop_PSD_uV2_per_Hz)
        grand,_ = a.build_grand_average([item], 'VRohtoPremium')
        assert grand.loc[grand.Set == 3, 'EyeDrop_Mean_PSD_uV2_per_Hz'].isna().all()
        change_item = item | {'eye_drop': b.make_change_session(eye),
                             'control': b.make_change_session(control)}
        change = b.build_quantification([change_item], 'VRohtoPremium')
        expected_baseline = np.nanmean(eye.sets[1].psd_band_mean[:,16])
        assert np.isclose(change_item['eye_drop'].baseline_by_channel[16], expected_baseline)
        # Check all finite values rather than depending on the CSV column spelling.
        numeric = change.select_dtypes(include='number').to_numpy()
        assert np.nanmax(np.abs(numeric)) > 100
        expected = (eye.sets[6].psd_band_mean[:,16] / expected_baseline - 1) * 100
        np.testing.assert_allclose(b.set_change_values(change_item['eye_drop'],6,16),
                                   expected, equal_nan=True)
        np.testing.assert_allclose(
            b.set_change_values(change_item['eye_drop'],6,16,smoothing_seconds=60),
            a.centered_nanmean(expected,60), equal_nan=True)
        assert a._channel_index(eye) == 16
        assert b._channel_index(change_item['eye_drop']) == 16
        assert a.plot_individual_timecourse.__code__.co_filename.endswith('Phase4_No1_FmTheta.py')
        assert b.plot_individual.__code__.co_filename.endswith('Phase4_No1_sub_FmThetaChange.py')
        print(json.dumps({'ok': True}))
        """
    )
    assert result["ok"] is True


def test_main_cli_has_no_cache_generation_or_force_mode() -> None:
    for name in ("Phase4_No11_PzLowAlpha.py", "Phase4_No11_sub_PzLowAlphaChange.py"):
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / name), "--help"],
            cwd=ROOT,
            env={**os.environ, "MPLCONFIGDIR": "/tmp/mplconfig-roht"},
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert "--all" in result.stdout
        assert "--preflight-only" in result.stdout
        assert "--compute-psd" not in result.stdout
        assert "--force-recompute" not in result.stdout


def test_future_source_band_change_is_not_silently_inherited() -> None:
    result = _run(
        """
        import numpy as np
        from phase4_no11_cached_analysis import build_absolute_engine, source_engine
        source_engine.INCLUDED_FREQUENCIES_HZ = np.array([8.,9.,10.,11.])
        try:
            build_absolute_engine()
        except ValueError as error:
            assert 'cache contract' in str(error)
        else:
            raise AssertionError('A different No10 band was silently accepted')
        print(json.dumps({'ok': True}))
        """
    )
    assert result["ok"] is True


def test_checked_roots_reject_non_authorized_output_or_cache() -> None:
    result = _run(
        """
        from pathlib import Path
        from argparse import Namespace
        from phase4_no11_cached_analysis import _checked_roots, source_engine
        good = Namespace(cache_root=source_engine.DEFAULT_CACHE_ROOT,
                         output_root=source_engine.DEFAULT_OUTPUT_ROOT)
        _checked_roots(good)
        for key in ('cache_root','output_root'):
            bad = Namespace(**vars(good))
            setattr(bad,key,Path('/tmp/not-the-authorized-root'))
            try:
                _checked_roots(bad)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid root accepted')
        print(json.dumps({'ok': True}))
        """
    )
    assert result["ok"] is True


def test_readonly_adapter_validates_original_source_hash_and_reapplies_masks() -> None:
    result = _run(
        """
        import tempfile
        from pathlib import Path
        import h5py
        import numpy as np
        import Phase4_No11_PzLowAlpha as wrapper
        from phase4_no11_cached_analysis import source_engine as source
        target = wrapper.engine
        with tempfile.TemporaryDirectory(prefix='no11-synthetic-cache-') as temporary:
            root = Path(temporary)
            signal = root / 'synthetic_source.bin'
            signal.write_bytes(b'synthetic source')
            st = signal.stat()
            fingerprints = [{'path': str(signal), 'size': st.st_size,
                             'mtime_ns': st.st_mtime_ns}]
            spec = source.ParticipantSpec('901','902','902','CCube')
            target.validate_participant_specs([spec])
            t = np.arange(121,dtype=float)
            values = np.ones((121,32), dtype=np.float32) * 2
            values[:,16] = np.linspace(1,4,121)
            values[5,16] = 1e10
            fraction = np.zeros(121)
            fraction[2] = .01
            piece = source.SetPSD(1,values,t,1000+t,t/120*100,t/120*100,
                                  (t*256).astype(int),fraction)
            path = source.cache_path(root,spec,'902')
            expected_hash = source.configuration_hash(fingerprints)
            assert expected_hash != target.configuration_hash(fingerprints)
            source._write_cache(path,spec,'902',{1:piece},{1:signal},np.zeros(32,bool),
                                '[]',expected_hash,fingerprints,
                                source.calculate_log3sd_exclusion({1:piece}))
            assert target.validate_cache(path)['ok']
            data = target.load_session_cache(path)
            assert target._channel_index(data) == 16
            assert np.isnan(data.sets[1].psd_band_mean[2]).all()
            assert np.isnan(data.sets[1].psd_band_mean[5,16])
            assert data.sets[1].psd_before_log3sd_exclusion[5,16] == 1e10
            assert np.isfinite(data.sets[1].psd_band_mean[5,1])
            with h5py.File(path,'r+') as handle:
                handle.attrs['configuration_hash'] = target.configuration_hash(fingerprints)
            try:
                target.validate_cache(path)
            except ValueError as error:
                assert 'configuration hash' in str(error)
            else:
                raise AssertionError('No11 target hash incorrectly accepted as source hash')
        print(json.dumps({'ok': True}))
        """
    )
    assert result["ok"] is True
