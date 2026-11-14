"""Synthetic tests for the independent Pz saved-output audit."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム" / "Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import validate_phase4_no11_outputs as audit  # noqa: E402


def test_authorized_report_location_and_non_target_refusal():
    root = audit.source_engine.DEFAULT_OUTPUT_ROOT
    args = SimpleNamespace(
        output_root=root,
        cache_root=audit.source_engine.DEFAULT_CACHE_ROOT,
        report=root / "Phase4_脳波解析" / audit.MAIN_STEM / "Sub/logs/Validation.json",
    )
    audit.validate_locations(args)
    args.report = root / "Phase4_脳波解析/No10_FzLowAlpha/Sub/logs/Validation.json"
    with pytest.raises(ValueError, match="No11"):
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


def test_primary_audit_recognizes_only_complete_named_supplement(tmp_path):
    root = tmp_path / audit.MAIN_STEM
    main = root / "CCube/GrandAverage/main.png"
    main.parent.mkdir(parents=True)
    main.touch()
    assert audit.primary_png_inventory(root) == ({main}, set())
    additional = audit.additional_png_paths(root)
    assert len(additional) == 6
    first, *remaining = sorted(additional)
    first.parent.mkdir(parents=True, exist_ok=True)
    first.touch()
    with pytest.raises(ValueError, match="incomplete"):
        audit.primary_png_inventory(root)
    for path in remaining:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert audit.primary_png_inventory(root) == ({main}, additional)
    unexpected = root / "UnknownExcluded.png"
    unexpected.touch()
    primary, _ = audit.primary_png_inventory(root)
    assert unexpected in primary  # Full audit must still reject this unknown output.


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
                values = np.full((101, 32), 5000.0)
                values[:, audit.PZ] = (person + 1) * s + condition * (person + 0.5)
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
