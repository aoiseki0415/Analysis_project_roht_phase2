"""No10 regression checks run each mutable band variant in an isolated process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "解析プログラム" / "Phase4_脳波解析"
MAIN_MODULE = "Phase4_No10_FzLowAlpha"
CHANGE_MODULE = "Phase4_No10_sub_FzLowAlphaChange"


def _run(module: str, body: str) -> dict[str, object]:
    source = (
        "import json, sys\n"
        f"sys.path.insert(0, {str(SCRIPT_DIR)!r})\n"
        f"import {module} as wrapper\n"
        "engine = wrapper.engine\n" + textwrap.dedent(body)
    )
    completed = subprocess.run(
        [sys.executable, "-c", source],
        cwd=ROOT,
        env={**os.environ, "MPLBACKEND": "Agg"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return json.loads(completed.stdout)


def test_main_configuration_is_lowalpha_all_channel_and_inherits_no1_method() -> None:
    actual = _run(
        MAIN_MODULE,
        """
        from pathlib import Path
        print(json.dumps({
            "stem": engine.ANALYSIS_STEM,
            "tag": engine.CACHE_FILE_TAG,
            "focus": engine.FOCUS_CHANNEL,
            "version": engine.SCRIPT_VERSION,
            "cache_version": engine.CACHE_CONFIGURATION_VERSION,
            "cache_root": str(engine.DEFAULT_CACHE_ROOT),
            "configuration": engine.analysis_configuration(),
            "downstream": engine.downstream_configuration(),
            "ccube": engine.normalize_product("CCube"),
            "vrohto": engine.normalize_product("VRohtoPremium"),
            "control": [engine.CONTROL_COLOR, engine.CONTROL_QUANTIFICATION_COLOR],
            "compute_source": Path(engine.calculate_set_psd.__code__.co_filename).name,
        }))
        """,
    )
    assert actual["stem"] == "No10_FzLowAlpha"
    assert actual["tag"] == "FzLowAlpha"
    assert actual["focus"] == "Fz"
    assert actual["version"] == "20261112_lowalpha_8to10_v2"
    assert actual["cache_version"] == "20261112_lowalpha_8to10_cache_v2"
    assert str(actual["cache_root"]).endswith("No10_FzLowAlpha/PSDTimeSeries")
    configuration = actual["configuration"]
    assert configuration["frequencies_hz"] == [8.0, 9.0, 10.0]
    assert len(configuration["channel_names"]) == 32
    assert configuration["channel_names"][1] == "Fz"
    for key in ("sfreq", "window_samples", "step_samples", "n_fft", "n_per_seg"):
        assert configuration[key] == 256
    assert configuration["pad_samples"] == 128
    assert configuration["n_overlap"] == 0
    assert configuration["window_function"] == "hann"
    assert configuration["remove_dc"] is True
    assert configuration["time_smoothing"] == "none"
    assert actual["compute_source"] == "Phase4_No1_FmTheta.py"
    downstream = actual["downstream"]
    assert downstream["interval_mask_overlap_threshold"] == 0.01
    assert downstream["log3sd_multiplier"] == 3.0
    assert downstream["timecourse_smoothing"]["seconds"] == 60
    assert downstream["timecourse_smoothing"]["minimum_valid_points"] == 1
    assert downstream["quantification_smoothing"] == "none"
    assert downstream["topography_smoothing"] == "none"
    assert downstream["grand_average_y_axis"]["target_fraction"] == 0.75
    assert downstream["grand_average_y_axis"]["basis"] == "maximum_mean_plus_sem"
    assert actual["ccube"][2:] == ["#637B22", "#8B9D58"]
    assert actual["vrohto"][2:] == ["#91A63D", "#ACBC6E"]
    assert actual["control"] == ["#402B5D", "#66547D"]


def test_sub_configuration_preserves_full_cohort_and_uses_no10_cache() -> None:
    actual = _run(
        CHANGE_MODULE,
        """
        from pathlib import Path
        print(json.dumps({
            "stem": engine.ANALYSIS_STEM,
            "focus": engine.FOCUS_CHANNEL,
            "version": engine.SCRIPT_VERSION,
            "parent_stem": engine.no1.ANALYSIS_STEM,
            "cache_root": str(engine.DEFAULT_CACHE_ROOT),
            "smoothing": engine.SMOOTHING_SECONDS,
            "include_topography": engine.INCLUDE_TOPOGRAPHY,
            "alternate": engine.ALTERNATE_GROUP_EXCLUSIONS,
            "suffix": engine.ALTERNATE_GROUP_SUFFIX,
            "star_factor": engine.SIGNIFICANCE_STAR_FACTOR_OVERRIDE,
            "star_size": engine.SIGNIFICANCE_STAR_FONTSIZE_OVERRIDE,
            "baseline_source": Path(engine.calculate_set1_baseline.__code__.co_filename).name,
            "paths": {
                k: str(v)
                for k, v in engine.output_directories(Path("/tmp/output"), "CCube").items()
            },
        }))
        """,
    )
    assert actual["stem"] == "No10_sub_FzLowAlphaChange"
    assert actual["focus"] == "Fz"
    assert actual["version"] == "20261112_lowalpha_8to10_change_v2"
    assert actual["parent_stem"] == "No10_FzLowAlpha"
    assert str(actual["cache_root"]).endswith("No10_FzLowAlpha/PSDTimeSeries")
    assert actual["smoothing"] == 60
    assert actual["include_topography"] is True
    assert actual["alternate"] == {}
    assert actual["suffix"] is None
    assert actual["star_factor"] == 1.08
    assert actual["star_size"] == 42.0
    assert actual["baseline_source"] == "Phase4_No1_sub_FmThetaChange.py"
    assert all("No10_sub_FzLowAlphaChange" in path for path in actual["paths"].values())


def test_lowalpha_psd_matches_independent_scipy_welch_with_edges_and_progress() -> None:
    actual = _run(
        MAIN_MODULE,
        """
        import numpy as np
        from scipy.signal import get_window, welch
        sfreq = 256.0
        n_samples = 1027
        t = np.arange(n_samples) / sfreq
        scale = np.linspace(0.5, 3.0, 32)
        signal_uv = (
            2 * np.sin(2 * np.pi * 8 * t)
            + 3 * np.sin(2 * np.pi * 10 * t)
            + 5 * np.sin(2 * np.pi * 11 * t)
            + 7 * np.sin(2 * np.pi * 14 * t)
            + 12 + 0.2 * t
        )[:, None] * scale[None, :]
        mask = np.zeros(n_samples, bool)
        mask[:3] = True
        mask[500:520] = True
        result = engine.calculate_set_psd(signal_uv * 1e-6, t, 10000 + t, mask, 4)
        centers = np.array([0, 256, 512, 768, 1024, 1026])
        padded = np.pad(signal_uv, ((128, 128), (0, 0)), mode="reflect")
        padded_mask = np.pad(mask.astype(float), (128, 128), mode="reflect")
        reference = []
        fraction = []
        for center in centers:
            freq, psd = welch(
                padded[center:center + 256].T,
                fs=sfreq,
                window=get_window("hann", 256, fftbins=True),
                nperseg=256, noverlap=0, nfft=256,
                detrend="constant", return_onesided=True,
                scaling="density", axis=-1, average="mean",
            )
            bins = (freq >= 8) & (freq <= 10)
            np.testing.assert_array_equal(freq[bins], [8, 9, 10])
            reference.append(psd[:, bins].mean(axis=1))
            fraction.append(padded_mask[center:center + 256].mean())
        np.testing.assert_allclose(result.psd_band_mean, reference, rtol=1e-6, atol=1e-7)
        np.testing.assert_array_equal(result.source_center_sample, centers)
        np.testing.assert_allclose(result.set_progress_pct, centers / 1026 * 100)
        np.testing.assert_allclose(result.global_progress_pct, 300 + centers / 1026 * 100)
        np.testing.assert_allclose(result.relative_seconds_center, t[centers])
        np.testing.assert_allclose(result.original_timestamp_center, (10000 + t)[centers])
        np.testing.assert_allclose(result.ica_training_mask_fraction, fraction)
        assert result.psd_band_mean.shape == (6, 32)
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_no10_log3sd_is_session_wide_channel_specific_and_does_not_clip_lows() -> None:
    actual = _run(
        MAIN_MODULE,
        """
        import numpy as np
        def make_set(number, data, fraction):
            t = np.arange(len(data), dtype=float)
            p = t / t[-1] * 100
            return engine.SetPSD(number, data, t, 1000 + t, p,
                                 (number - 1) * 100 + p,
                                 np.arange(len(data)) * 256, fraction)
        a = np.ones((40, 32), float)
        b = np.ones((40, 32), float)
        a[0, 0] = 1e15
        a[1, 1] = 1e-10
        b[-1, 2] = 1e10
        fraction = np.zeros(40)
        fraction[0] = .01
        sets = {1: make_set(1, a, fraction), 6: make_set(6, b, np.zeros(40))}
        result = engine.calculate_log3sd_exclusion(sets)
        assert result["masks"][6][-1, 2]
        assert not result["masks"][1][1, 1]
        assert not result["masks"][1][0].any()
        assert result["masks"][6].sum() == 1
        assert result["valid_count_by_set_ch"][0, 0] == 39
        for ch in range(32):
            pooled = np.concatenate([a[1:, ch], b[:, ch]])
            logged = np.log10(pooled)
            np.testing.assert_allclose(result["mean"][ch], logged.mean())
            np.testing.assert_allclose(result["sample_sd"][ch], logged.std(ddof=1))
            np.testing.assert_allclose(
                result["threshold_log"][ch], logged.mean() + 3 * logged.std(ddof=1)
            )
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_sub_uses_own_id_channel_baselines_and_paired_missing_set() -> None:
    actual = _run(
        CHANGE_MODULE,
        """
        import numpy as np
        parent = engine.no1
        chscale = np.arange(1, 33, dtype=float)
        def make_session(sid, condition, scale, missing):
            sets = {}
            for number in range(1, 7):
                if number in missing:
                    continue
                t = np.arange(4 + number, dtype=float)
                p = t / t[-1] * 100
                time_scale = number + np.linspace(-.1, .1, len(t))
                values = (scale * chscale)[None, :] * time_scale[:, None]
                values[0, 3] = np.nan
                sets[number] = parent.SetPSD(number, values, t, t + 1000, p,
                                            (number - 1) * 100 + p,
                                            (t * 256).astype(int), np.zeros(len(t)))
            return parent.SessionPSD(sid, condition, "901-902", "CCube",
                                     parent.EXPECTED_CHANNEL_NAMES, sets, np.zeros(32, bool))
        eye = engine.make_change_session(make_session("902", "Eye Drop", 3, {3}))
        control = engine.make_change_session(make_session("901", "Control", 7, set()))
        np.testing.assert_allclose(eye.baseline_by_channel[[0, 1]], [3, 6])
        np.testing.assert_allclose(control.baseline_by_channel[[0, 1]], [7, 14])
        for session in (eye, control):
            np.testing.assert_allclose(engine.set_channel_means(session)[1], 0, atol=1e-10)
            values = engine.set_change_values(session, 2, 1)
            smoothed = engine.set_change_values(session, 2, 1, smoothing_seconds=60)
            np.testing.assert_allclose(smoothed, parent.centered_nanmean(values, 60))
        spec = parent.ParticipantSpec("901", "902", "902", "CCube")
        item = {"spec": spec, "product_dir": "CCube", "eye_drop": eye, "control": control}
        quant = engine.build_quantification([item], "CCube")
        value_columns = ["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]
        assert quant.loc[quant.Set == 3, value_columns].isna().all().all()
        assert 3 in control.source.sets
        grand, stacks = engine.build_grand_average([item], "CCube")
        assert grand.loc[grand.Set == 3, "EyeDrop_Mean_PSDChange_pct"].isna().all()
        assert grand.loc[grand.Set == 3, "Control_Mean_PSDChange_pct"].isna().all()
        topo = engine.pair_topography_values(item)
        assert np.isnan(topo[2]).all()
        common = [1, 2, 4, 5, 6]
        pieces = [engine.set_change_values(eye, number, 1) for number in common]
        expected = np.concatenate(pieces).mean()
        observed = quant.loc[quant.Set == "All Sets", "EyeDrop_PSDChange_pct"].iloc[0]
        np.testing.assert_allclose(observed, expected)
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_existing_band_defaults_are_unmodified_in_separate_processes() -> None:
    for module, stem, frequencies, focus in (
        ("Phase4_No1_FmTheta", "No1_FmTheta", [4, 5, 6, 7], "Fz"),
        ("Phase4_No2_OccipitalAlpha", "No2_OccipitalAlpha", list(range(8, 16)), "Oz"),
        ("Phase4_No3_FrontalDelta", "No3_FrontalDelta", [1, 2, 3], "Fz"),
    ):
        body = """
        print(json.dumps({
            "stem": engine.ANALYSIS_STEM,
            "frequencies": engine.INCLUDED_FREQUENCIES_HZ.tolist(),
            "focus": engine.FOCUS_CHANNEL,
        }))
        """
        if module == "Phase4_No1_FmTheta":
            # The primary engine is itself the public module rather than a wrapper.
            source = (
                "import json, sys\n"
                f"sys.path.insert(0, {str(SCRIPT_DIR)!r})\n"
                f"import {module} as engine\n" + textwrap.dedent(body)
            )
            completed = subprocess.run(
                [sys.executable, "-c", source],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )
            actual = json.loads(completed.stdout)
        else:
            actual = _run(module, body)
        assert actual == {"stem": stem, "frequencies": frequencies, "focus": focus}


def test_cache_guard_rejects_wrong_band_hash_manifest_and_stale_source() -> None:
    actual = _run(
        MAIN_MODULE,
        """
        import tempfile
        from pathlib import Path
        import h5py
        import numpy as np
        with tempfile.TemporaryDirectory(prefix="no10-cache-test-") as temporary:
            root = Path(temporary)
            source = root / "synthetic_source.bin"
            source.write_bytes(b"synthetic source fingerprint")
            stat = source.stat()
            fingerprint = [{"path": str(source), "size": stat.st_size,
                            "mtime_ns": stat.st_mtime_ns}]
            spec = engine.ParticipantSpec("901", "902", "902", "CCube")
            engine.validate_participant_specs([spec])
            values = np.full((3, 32), 2.0, dtype=np.float32)
            t = np.arange(3, dtype=float)
            segment = engine.SetPSD(1, values, t, 1000 + t, t * 50,
                                    t * 50, (t * 256).astype(int), np.zeros(3))
            sets = {1: segment}
            path = engine.cache_path(root, spec, "902")
            engine._write_cache(
                path, spec, "902", sets, {1: source}, np.zeros(32, bool), "[]",
                engine.configuration_hash(fingerprint), fingerprint,
                engine.calculate_log3sd_exclusion(sets),
            )
            assert engine.validate_cache(path)["ok"]
            def must_fail(fragment):
                try:
                    engine.validate_cache(path)
                except ValueError as error:
                    assert fragment in str(error), str(error)
                else:
                    raise AssertionError("invalid cache was accepted")
            with h5py.File(path, "r+") as handle:
                handle.attrs["included_frequencies_hz"] = json.dumps([8, 9, 10, 11])
            must_fail("frequency band")
            with h5py.File(path, "r+") as handle:
                handle.attrs["included_frequencies_hz"] = json.dumps([8, 9, 10])
                handle.attrs["configuration_hash"] = "invalid-configuration-hash"
            must_fail("configuration hash")
            with h5py.File(path, "r+") as handle:
                handle.attrs["configuration_hash"] = engine.configuration_hash(fingerprint)
                handle.attrs["condition"] = "Control"
            must_fail("condition mismatch")
            with h5py.File(path, "r+") as handle:
                handle.attrs["condition"] = "Eye Drop"
            assert engine.validate_cache(path)["ok"]
            engine.SCRIPT_VERSION = "new-figure-only-script-version"
            assert engine.validate_cache(path)["ok"]
            source.write_bytes(b"changed synthetic source fingerprint")
            must_fail("source changed")
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_previous_band_cache_hash_is_incompatible_even_if_frequency_attr_is_changed() -> None:
    actual = _run(
        MAIN_MODULE,
        """
        import numpy as np
        original_hash = engine.configuration_hash([])
        engine.INCLUDED_FREQUENCIES_HZ = np.array([8, 9, 10, 11], float)
        engine.FMAX_HZ = 11.0
        engine.CACHE_CONFIGURATION_VERSION = "20261112_lowalpha_cache_v1"
        assert engine.configuration_hash([]) != original_hash
        # Version alone prevents accepting a stale numerical schema.
        engine.INCLUDED_FREQUENCIES_HZ = np.array([8, 9, 10], float)
        engine.FMAX_HZ = 10.0
        assert engine.configuration_hash([]) != original_hash
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_sensitivity_removes_whole_pairs_and_preserves_input_objects() -> None:
    actual = _run(
        CHANGE_MODULE,
        """
        from types import SimpleNamespace
        import phase4_no10_sub_sensitivity as sensitivity
        items = []
        for index, (product, excluded) in enumerate(sensitivity.EXCLUDED_PAIRS_BY_PRODUCT.items()):
            for pair in [*sorted(excluded), f"retained-{index}"]:
                items.append({"spec": SimpleNamespace(pair_id=pair), "product_dir": product,
                              "eye_drop": object(), "control": object()})
        before = [(id(item), id(item["eye_drop"]), id(item["control"])) for item in items]
        selected, table = sensitivity.select_sensitivity_cohorts(items)
        assert table.Included.sum() == 2
        assert (~table.Included).sum() == 3
        for product, cohort in selected.items():
            assert len(cohort) == 1
            assert cohort[0] in items
            assert cohort[0]["spec"].pair_id not in sensitivity.EXCLUDED_PAIRS_BY_PRODUCT[product]
        assert before == [(id(item), id(item["eye_drop"]), id(item["control"])) for item in items]
        try:
            sensitivity.select_sensitivity_cohorts(items[1:])
        except ValueError as error:
            assert "requires specified pair" in str(error)
        else:
            raise AssertionError("missing exclusion target accepted")
        bad = [dict(item) for item in items]
        bad[0]["product_dir"] = "OtherProduct"
        try:
            sensitivity.select_sensitivity_cohorts(bad)
        except ValueError as error:
            assert "product mismatch" in str(error)
        else:
            raise AssertionError("wrong product accepted")
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_sensitivity_outputs_use_retained_curves_axes_and_paired_statistics_only() -> None:
    actual = _run(
        CHANGE_MODULE,
        """
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        import numpy as np
        import pandas as pd
        from scipy.stats import ttest_rel
        import phase4_no10_sub_sensitivity as sensitivity
        parent = engine.no1
        def item_for(pair, product, multiplier, extreme=False):
            sessions = []
            for condition in ["Eye Drop", "Control"]:
                sets = {}
                for number in range(1, 7):
                    t = np.arange(70, dtype=float)
                    values = np.ones((70, 32)) * (10 + number * multiplier)
                    if condition == "Control":
                        values *= 1 + .01 * number * multiplier
                    if extreme and number > 1:
                        values *= 1000
                    if pair == "retained-0-0" and number == 4 and condition == "Control":
                        continue
                    sets[number] = parent.SetPSD(number, values, t, 1000 + t,
                        t / 69 * 100, (number - 1) * 100 + t / 69 * 100,
                        (t * 256).astype(int), np.zeros(len(t)))
                source = parent.SessionPSD(condition, condition, pair, product,
                                           parent.EXPECTED_CHANNEL_NAMES, sets, np.zeros(32, bool))
                sessions.append(engine.make_change_session(source))
            return {"spec": SimpleNamespace(pair_id=pair), "product_dir": product,
                    "eye_drop": sessions[0], "control": sessions[1]}
        items = []
        for idx, (product, exclusions) in enumerate(sensitivity.EXCLUDED_PAIRS_BY_PRODUCT.items()):
            items.extend(item_for(pair, product, 2, True) for pair in sorted(exclusions))
            items.extend(item_for(f"retained-{idx}-{j}", product, j + 1) for j in range(3))
        calls = []
        def grand_plot(frame, product, path, **kwargs):
            calls.append(("grand", product, kwargs["common_limit"]))
            path.write_bytes(b"synthetic plot")
        def quant_plot(frame, stats, product, path):
            assert len(frame.PairID.unique()) == 3
            calls.append(("quant", product, path.name))
            path.write_bytes(b"synthetic plot")
        engine.plot_grand_average = grand_plot
        engine.plot_quantification = quant_plot
        engine.plot_overall_quantification = quant_plot
        engine.plot_topography = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("sensitivity must not draw topography"))
        with tempfile.TemporaryDirectory(prefix="no10-sensitivity-test-") as tmp:
            root = Path(tmp)
            original = root / "original.png"
            original.write_bytes(b"keep original")
            result = sensitivity.write_sensitivity_group_outputs(engine, items, root)
            assert original.read_bytes() == b"keep original"
            selected, _ = sensitivity.select_sensitivity_cohorts(items)
            expected_axis, _ = engine.grand_average_axis([
                engine.build_grand_average(cohort, product)[0]
                for product, cohort in selected.items()
            ])
            full_axis, _ = engine.grand_average_axis([
                engine.build_grand_average(items, product)[0] for product in selected
            ])
            assert expected_axis < full_axis
            assert [entry[2] for entry in calls if entry[0] == "grand"] == [expected_axis] * 2
            assert len(list(root.rglob("*.png"))) == 7
            assert len(list(root.rglob("*.csv"))) == 9
            assert not list(root.rglob("Topography"))
            for product, info in result["outputs"].items():
                values = pd.read_csv(info["quantification_values"])
                assert values.PairID.nunique() == 3
                assert len(values) == 21
                assert len(pd.read_csv(info["grand_average_values"])) == 600
                stats = pd.read_csv(info["set_statistics"])
                assert np.isnan(stats.loc[stats.Set == 1, "P_value_raw"]).all()
                section = values.loc[values.Set == "2"]
                check = ttest_rel(section.EyeDrop_PSDChange_pct, section.Control_PSDChange_pct)
                np.testing.assert_allclose(stats.loc[stats.Set == 2, "P_value_raw"], check.pvalue)
                assert {"P_value_Bonferroni", "P_value_Holm", "P_value_FDR_BH"} <= set(stats)
                if product == "CCube":
                    assert info["paired_n"]["4"] == 2
                    assert info["paired_n"]["All Sets"] == 3
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True


def test_full_group_mode_adds_sensitivity_but_pilot_preserves_original_scope() -> None:
    actual = _run(
        CHANGE_MODULE,
        """
        from pathlib import Path
        from types import SimpleNamespace
        import phase4_no10_sub_sensitivity as sensitivity
        items = [
            {"spec": SimpleNamespace(pair_id=pair), "product_dir": product}
            for product, exclusions in sensitivity.EXCLUDED_PAIRS_BY_PRODUCT.items()
            for pair in sorted(exclusions)
        ]
        for index in range(36):
            items.append({"spec": SimpleNamespace(pair_id=f"retained-{index}"),
                          "product_dir": "CCube" if index % 2 else "VRohtoPremium"})
        calls = []
        def original(data, root):
            calls.append("original")
            return {product: {"topography": "original"} for product in ["CCube", "VRohtoPremium"]}
        def addition(configured, data, root):
            calls.append("sensitivity")
            return {"outputs": {product: {"new": True} for product in ["CCube", "VRohtoPremium"]}}
        fake = SimpleNamespace(no1=SimpleNamespace(PRODUCTION_PARTICIPANT_COUNT=40),
                               write_group=original)
        sensitivity.write_sensitivity_group_outputs = addition
        sensitivity.install_sensitivity_group_outputs(fake)
        full = fake.write_group(items, Path("/tmp/no10-not-written"))
        assert calls == ["original", "sensitivity"]
        assert full["CCube"]["topography"] == "original"
        assert full["CCube"]["specified_pair_sensitivity"] == {"new": True}
        calls.clear()
        pilot = fake.write_group(items[:1], Path("/tmp/no10-not-written"))
        assert calls == ["original"]
        assert "specified_pair_sensitivity" not in pilot["CCube"]
        print(json.dumps({"ok": True}))
        """,
    )
    assert actual["ok"] is True
