from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム"
    / "Phase4_脳波解析"
    / "Phase4_PSDChange500OutlierExcludedTopography.py"
)
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("phase4_psdchange500", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _record(set_number: int, channel: str, session_id: str = "101"):
    return MODULE.OutlierRecord(
        analysis="No1",
        pair_id="101-201",
        session_id=session_id,
        condition="Eye Drop",
        product="CCube",
        set_number=set_number,
        channel=channel,
        psd_change_pct=600.0,
    )


def test_persistent_channel_is_removed_from_all_postbaseline_sets(monkeypatch):
    source = np.zeros((6, len(MODULE.phase4.EXPECTED_CHANNEL_NAMES)))
    monkeypatch.setattr(
        MODULE.change, "pair_topography_values", lambda item: source.copy()
    )
    records = [_record(3, "F7"), _record(4, "F7"), _record(5, "CP2")]

    masked, persistent = MODULE.masked_pair_topography({}, records)

    f7 = MODULE.phase4.EXPECTED_CHANNEL_NAMES.index("F7")
    cp2 = MODULE.phase4.EXPECTED_CHANNEL_NAMES.index("CP2")
    assert ("101", "F7") in persistent
    assert np.isfinite(masked[0, f7])
    assert np.isnan(masked[1:, f7]).all()
    assert np.isnan(masked[4, cp2])
    assert np.isfinite(masked[[0, 1, 2, 3, 5], cp2]).all()


def test_group_average_excludes_one_pair_channel_without_dropping_other_channels(
    monkeypatch,
):
    n_channels = len(MODULE.phase4.EXPECTED_CHANNEL_NAMES)
    first = np.ones((6, n_channels))
    second = np.full((6, n_channels), 3.0)
    first[2, 0] = np.nan
    values = iter([(first, set()), (second, set())])
    monkeypatch.setattr(MODULE, "masked_pair_topography", lambda item, records: next(values))
    monkeypatch.setattr(
        MODULE,
        "apply_spatial_outlier_mask",
        lambda values, item, config: (values, []),
    )
    items = [
        {"product_dir": "CCube", "spec": SimpleNamespace(pair_id="101-201")},
        {"product_dir": "CCube", "spec": SimpleNamespace(pair_id="102-202")},
    ]

    group, valid_n, _, spatial = MODULE.group_topography(
        items, [], "CCube", MODULE.ANALYSES["No1"]
    )

    assert group[2, 0] == 3.0
    assert valid_n[2, 0] == 1
    assert group[2, 1] == 2.0
    assert valid_n[2, 1] == 2
    assert spatial == []


def test_spatial_outlier_mask_removes_isolated_channel_only(monkeypatch):
    n_channels = len(MODULE.phase4.EXPECTED_CHANNEL_NAMES)
    rng = np.random.default_rng(20261017)
    values = rng.normal(0.0, 1.0, size=(6, n_channels))
    target = MODULE.phase4.EXPECTED_CHANNEL_NAMES.index("Oz")
    values[2, target] = 100.0
    item = {
        "spec": SimpleNamespace(pair_id="101-201"),
        "product_dir": "CCube",
    }

    masked, records = MODULE.apply_spatial_outlier_mask(
        values, item, MODULE.ANALYSES["No1"]
    )

    assert np.isnan(masked[2, target])
    assert np.isfinite(masked[0]).all()
    assert any(record.channel == "Oz" and record.set_number == 3 for record in records)


def test_output_filename_states_the_exclusion_rule(tmp_path):
    path = MODULE.output_path(tmp_path, MODULE.ANALYSES["No1"], "CCube")
    assert path.name.endswith("_PSDChange500pctOutlierExcluded.png")
    assert "Topography/GrandAverage" in path.as_posix()


def test_audit_tables_record_both_exclusion_stages(tmp_path):
    spatial = MODULE.SpatialOutlierRecord(
        analysis="No1",
        pair_id="101-201",
        product="CCube",
        set_number=3,
        channel="Oz",
        pair_difference_pct=-398.0,
        neighbor_median_pct=37.1,
        spatial_residual_pct=-435.1,
        residual_center_pct=0.0,
        residual_mad_pct=18.5,
        robust_z=-15.84,
    )
    paths = MODULE.write_audit_tables(
        tmp_path,
        MODULE.ANALYSES["No1"],
        [_record(3, "F7")],
        [spatial],
        {"CCube": {"minimum": 18, "maximum": 20}},
    )

    assert "psd_change_pct" in Path(paths["absolute_outliers_csv"]).read_text()
    assert "robust_z" in Path(paths["spatial_outliers_csv"]).read_text()
    assert '"spatial_outlier_count": 1' in Path(paths["run_summary_json"]).read_text()
