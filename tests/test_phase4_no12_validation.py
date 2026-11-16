"""Synthetic tests for the independent ROI saved-output audit."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import validate_phase4_no12_outputs as audit  # noqa: E402


def test_authorized_report_location_and_non_target_refusal():
    root = audit.source_engine.DEFAULT_OUTPUT_ROOT
    args = SimpleNamespace(
        output_root=root,
        cache_root=audit.source_engine.DEFAULT_CACHE_ROOT,
        report=root / "Phase4_脳波解析" / audit.MAIN_STEM / "Sub/logs/Validation.json",
    )
    audit.validate_locations(args)
    args.report = root / "Phase4_脳波解析/No10_FzLowAlpha/Sub/logs/Validation.json"
    with pytest.raises(ValueError, match="No12"):
        audit.validate_locations(args)
    args.output_root = Path("/tmp/arbitrary_output")
    with pytest.raises(ValueError, match="authorized OneDrive"):
        audit.validate_locations(args)


def test_png_inventory_has_no_topography_or_sensitivity():
    cohort = [
        (SimpleNamespace(pair_id=f"Synthetic{i}", product=product), [])
        for product in audit.PRODUCTS
        for i in range(20)
    ]
    main_paths = audit.expected_png_paths(Path(audit.MAIN_STEM), cohort, change=False)
    assert len(main_paths) == 126
    sub_paths = audit.expected_png_paths(Path(audit.SUB_STEM), cohort[:-1], change=True)
    assert len(sub_paths) == 45
    assert not any("Topography" in str(path) for path in main_paths | sub_paths)
    assert not any("Excluded" in str(path) for path in main_paths | sub_paths)


def _items():
    result = []
    for person in range(3):
        spec = SimpleNamespace(pair_id=f"Synthetic{person}", product="CCube")
        sessions = []
        for condition in range(2):
            sets = {}
            for s in range(1, 7):
                if person == 2 and condition == 0 and s == 6:
                    continue
                values = np.full((101, 1), 5000.0)
                values[:, audit.ROI] = (person + 1) * s + condition * (person + 0.5)
                sets[s] = values, np.linspace(0, 100, 101)
            sessions.append(sets)
        result.append((spec, sessions))
    return result


def test_group_audit_uses_pz_and_paired_set_mask(monkeypatch):
    frames = {}

    def capture(path, expected, keys, report):
        frames[path.name] = expected.copy()

    monkeypatch.setattr(audit, "compare_csv", capture)
    report = {"groups": []}
    audit.audit_group(_items(), Path(audit.MAIN_STEM), "CCube", False, report)
    values = frames[f"{audit.MAIN_STEM}_SetQuantification_Values_CCube.csv"]
    row = values[(values.PairID == "Synthetic0") & (values.Set == "1")].iloc[0]
    assert row.EyeDrop_PSD_uV2_per_Hz == 1
    assert row.Control_PSD_uV2_per_Hz == 1.5
    missing = values[(values.PairID == "Synthetic2") & (values.Set == "6")].iloc[0]
    assert np.isnan(missing.EyeDrop_PSD_uV2_per_Hz)
    assert np.isnan(missing.Control_PSD_uV2_per_Hz)
    assert report["groups"][0]["set_paired_n"] == [3, 3, 3, 3, 3, 2]
    assert report["groups"][0]["correction_family_tests"] == 6


def test_change_uses_five_comparisons_and_preserves_baseline(monkeypatch):
    frames = {}

    def capture(path, expected, keys, report):
        frames[path.name] = expected.copy()

    monkeypatch.setattr(audit, "compare_csv", capture)
    items = _items()
    transformed = []
    for spec, sessions in items:
        transformed.append(
            (
                spec,
                [
                    {
                        s: ((values / np.mean(session[1][0], axis=0) - 1) * 100, progress)
                        for s, (values, progress) in session.items()
                    }
                    for session in sessions
                ],
            )
        )
    report = {"groups": []}
    audit.audit_group(transformed, Path(audit.SUB_STEM), "CCube", True, report)
    statistics = frames[f"{audit.SUB_STEM}_SetQuantification_Statistics_CCube.csv"]
    baseline = statistics[statistics.Set == "1"].iloc[0]
    assert np.isnan(baseline.P_value_raw)
    assert np.isnan(baseline.P_value_FDR_BH)
    assert report["groups"][0]["correction_family_tests"] == 5
    values = frames[f"{audit.SUB_STEM}_Quantification_Values_CCube.csv"]
    assert (values[values.Set == "1"].EyeDrop_PSDChange_pct == 0).all()


def test_finite_channel_mean_no_quorum_zero_fill_or_global_average():
    values = np.array(
        [
            [2.0, 4.0, 6.0, 8.0, 10.0],
            [np.nan, 4.0, np.nan, np.nan, np.nan],
            [np.nan, np.nan, np.nan, np.nan, np.nan],
            [2.0, np.nan, np.inf, 8.0, 10.0],
        ]
    )
    means, counts, bits = audit.roi_values(values)
    np.testing.assert_allclose(means, [6, 4, np.nan, 20 / 3], equal_nan=True)
    np.testing.assert_array_equal(counts, [5, 1, 0, 3])
    np.testing.assert_array_equal(bits, [31, 2, 0, 25])


def test_roi_then_baseline_is_not_mean_of_channel_percentages():
    baseline = np.array([[1.0, 10.0, 1.0, 10.0, 1.0]])
    later = np.array([[2.0, 10.0, 2.0, 10.0, 2.0]])
    b, _, _ = audit.roi_values(baseline)
    y, _, _ = audit.roi_values(later)
    expected = (y / b - 1) * 100
    wrong = ((later / baseline - 1) * 100).mean(axis=1)
    assert expected[0] == pytest.approx(300 / 23)
    assert not np.isclose(expected, wrong)[0]


def test_roi_mean_before_smoothing_noncommutes_with_missing_channels():
    import pandas as pd

    values = np.array([[10.0, np.nan], [0.0, 100.0], [np.nan, 0.0]])
    roi, _, _ = audit.roi_values(values)
    first_roi = pd.Series(roi).rolling(3, center=True, min_periods=1).mean()
    first_smooth = pd.DataFrame(values).rolling(3, center=True, min_periods=1).mean().mean(axis=1)
    assert not np.allclose(first_roi, first_smooth)


def test_allsets_weights_windows_not_sets_and_keeps_set1(monkeypatch):
    frames = {}
    monkeypatch.setattr(
        audit,
        "compare_csv",
        lambda path, expected, keys, report: frames.update({path.name: expected}),
    )
    spec = SimpleNamespace(pair_id="Synthetic", product="CCube")
    sessions = [
        {
            1: (np.full((100, 1), 1.0 + condition), np.linspace(0, 100, 100)),
            2: (np.full((200, 1), 10.0 + condition), np.linspace(0, 100, 200)),
        }
        for condition in range(2)
    ]
    audit.audit_group([(spec, sessions)], Path(audit.MAIN_STEM), "CCube", False, {"groups": []})
    values = frames[f"{audit.MAIN_STEM}_SetQuantification_Values_CCube.csv"]
    overall = values[values.Set == "All Sets"].iloc[0]
    assert overall.EyeDrop_PSD_uV2_per_Hz == pytest.approx(7.0)
    assert overall.Control_PSD_uV2_per_Hz == pytest.approx(8.0)


def test_no12_cannot_accept_sensitivity_png(tmp_path):
    root = tmp_path / audit.MAIN_STEM
    extra = root / "CCube/GrandAverage/SpecifiedPairsExcluded.png"
    extra.parent.mkdir(parents=True)
    extra.touch()
    with pytest.raises(ValueError, match="PNG inventory mismatch"):
        audit.audit_pngs(root, [], False, {"images": [], "png_counts": {}})


def test_raw_cache_reconstruction_applies_phase1_then_ch_log3sd_then_roi(tmp_path, monkeypatch):
    import json

    import h5py

    path = tmp_path / "synthetic.h5"
    raw = np.ones((101, 32), dtype=np.float32)
    fz = audit.SOURCE_CHANNELS.index("Fz")
    raw[50, fz] = 1e6
    raw[20, :] = 500.0
    overlap = np.zeros(101)
    overlap[20] = 0.01
    valid = np.isfinite(raw) & (raw > 0) & (overlap[:, None] < 0.01)
    moments = np.array(
        [
            [np.log10(raw[valid[:, ch], ch]).mean() for ch in range(32)],
            [np.log10(raw[valid[:, ch], ch]).std(ddof=1) for ch in range(32)],
        ],
        dtype=float,
    )
    threshold = moments[0] + 3 * moments[1]
    excluded = valid & (np.log10(raw) > threshold)
    counts, denominators = np.zeros((6, 32), int), np.zeros((6, 32), int)
    counts[0], denominators[0] = excluded.sum(axis=0), valid.sum(axis=0)
    rates = np.divide(counts, denominators, out=np.full((6, 32), np.nan), where=denominators > 0)
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            participant_id="synthetic",
            pair_id="pair",
            condition="Eye Drop",
            product="CCube",
            sampling_frequency_hz=256,
            fmin_hz=8,
            fmax_hz=10,
            step_samples=256,
            n_fft=256,
            n_per_seg=256,
            n_overlap=0,
            time_smoothing="none",
            included_frequencies_hz=json.dumps([8, 9, 10]),
            configuration_hash="synthetic",
        )
        group = handle.create_group("sets/Set1")
        group.attrs["source_n_samples"] = 25601
        for name, values in (
            ("psd_band_mean", raw),
            ("ica_training_mask_fraction", overlap),
            ("source_center_sample", np.arange(101) * 256),
            ("set_progress_pct", np.arange(101)),
            ("global_progress_pct", np.arange(101)),
            ("relative_seconds_center", np.arange(101)),
            ("OriginalTimestamp_center", np.arange(101) + 10000),
            ("log3sd_outlier_mask", excluded),
        ):
            group.create_dataset(name, data=values)
        qc = handle.create_group("qc")
        for name, values in (
            ("log3sd_mean_by_channel", moments[0]),
            ("log3sd_sd_by_channel", moments[1]),
            ("log3sd_threshold_log_by_channel", threshold),
            ("log3sd_threshold_linear_by_channel", 10.0**threshold),
            ("log3sd_excluded_count_by_set_ch", counts),
            ("log3sd_valid_count_by_set_ch", denominators),
            ("log3sd_excluded_rate_by_set_ch", rates),
            ("ica_channel_excluded_mask", np.ones(32, bool)),
        ):
            qc.create_dataset(name, data=values)
    monkeypatch.setattr(audit.source_engine, "validate_cache", lambda path: None)
    monkeypatch.setattr(
        audit.source_engine, "EXPECTED_MISSING_SETS", {"synthetic": set(range(2, 7))}
    )
    report = {"caches": []}
    values = audit.reconstruct_masked_cache(path, "synthetic", report)[1][0][:, 0]
    assert np.isnan(values[20])
    assert values[50] == 1.0
    quality = report["_audit_sessions"]["synthetic"]["sets"][1]
    assert quality["before_bits"][50] == 31
    assert quality["after_bits"][50] == 29
    assert quality["after_n"][50] == 4
    assert quality["after_n"][20] == 0
    assert report["caches"][0]["sha256"]
