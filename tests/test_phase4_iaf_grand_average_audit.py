"""Synthetic provenance tests; no real participant records or external writes."""

import importlib.util
import json
from pathlib import Path

import pytest

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "解析プログラム/Phase4_脳波解析/phase4_iaf_grand_average_audit.py"
)
SPEC = importlib.util.spec_from_file_location("iaf_independent_audit", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _log(tmp_path, name, status, outputs):
    path = tmp_path / name
    path.write_text(json.dumps({"status": status, "outputs": outputs}))
    return path


def test_scoped_rerun_keeps_provenance_for_untouched_outputs(tmp_path):
    old = _log(tmp_path, "001.json", "complete", [
        {"path": "target.png", "sha256": "old", "render": {"axis": 1}},
        {"path": "untouched.png", "sha256": "keep", "render": {"axis": 1}},
    ])
    new = _log(tmp_path, "002.json", "complete", [
        {"path": "target.png", "sha256": "new", "render": {"axis": 1}},
    ])
    path, latest, outputs = MODULE.latest_output_records([new, old])
    assert path == new and latest["status"] == "complete"
    assert outputs["target.png"]["sha256"] == "new"
    assert outputs["target.png"]["source_run_log"] == str(new)
    assert outputs["untouched.png"]["sha256"] == "keep"
    assert outputs["untouched.png"]["source_run_log"] == str(old)


def test_failed_latest_run_is_not_silently_replaced_with_old_success(tmp_path):
    old = _log(tmp_path, "001.json", "complete", [])
    failed = _log(tmp_path, "002.json", "failed", [])
    with pytest.raises(AssertionError, match="Latest run is not complete"):
        MODULE.latest_output_records([old, failed])


def test_no_run_log_cannot_be_reported_as_verified():
    with pytest.raises(AssertionError, match="No grand-average run log"):
        MODULE.latest_output_records([])
