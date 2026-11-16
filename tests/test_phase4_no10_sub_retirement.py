"""Exact-scope retirement safeguards, exercised on synthetic files only."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

PHASE4 = Path(__file__).resolve().parents[1] / "解析プログラム/Phase4_脳波解析"
sys.path.insert(0, str(PHASE4))

import run_phase4_no10_sub_exclusion_retirement as runner  # noqa: E402


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.fixture
def synthetic(tmp_path):
    root = tmp_path / "phase4" / runner.STEM
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "preserved.h5").write_bytes(b"synthetic cache")
    attention = tmp_path / "attention.md"
    attention.write_text(
        "## Phase 4 sub被験者除外の現行指定（2026-11-16）\n"
        "| No10_sub（Fz low-alpha） | なし | なし | 検討した上で不要と判断 |\n",
        encoding="utf-8",
    )
    for path in runner.legacy_paths(root):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic legacy output")
    selection = []
    for product, count in (("CCube", 20), ("VRohtoPremium", 19)):
        rows = []
        for index in range(count):
            pair = f"synthetic-{product}-{index}"
            rows.extend(
                {"PairID": pair, "Set": str(number)} for number in [1, 2, 3, 4, 5, 6, "All Sets"]
            )
            selection.append({"PairID": pair, "Product": product, "Included": index > 1})
        write_csv(
            root
            / "Sub/tables/SetQuantification"
            / f"{runner.STEM}_Quantification_Values_{product}.csv",
            ["PairID", "Set"],
            rows,
        )
        for folder, kind in (
            ("GrandAverage", "GrandAverage"),
            ("SetQuantification", "SetQuantification"),
            ("SetQuantification", "AllSetsQuantification"),
        ):
            path = root / product / folder / f"{runner.STEM}_{kind}_{product}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (5, 5), "white").save(path)
    write_csv(
        root
        / "Sub/tables/SetQuantification"
        / f"{runner.STEM}_CohortSelection_{runner.SUFFIX}.csv",
        ["PairID", "Product", "Included"],
        selection,
    )
    for relative in (
        "No11_sub_PzLowAlphaChange/CCube/GrandAverage/preserved.png",
        "No11_PzLowAlpha/CCube/GrandAverage/preserved.png",
        "No10_FzLowAlpha/CCube/GrandAverage/preserved.png",
        "補足分析（被験者除外あり）/before.png",
        f"{runner.STEM}/CCube/Topography/GrandAverage/preserved.png",
    ):
        path = root.parent / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"protected synthetic artifact")
    return root, cache, attention


def test_plan_is_read_only_and_allowlist_has_exact_scope(synthetic):
    root, cache, attention = synthetic
    before = runner.inventory([root.parent, cache], set())
    plan = runner.build_plan(root, cache, attention)
    assert runner.inventory([root.parent, cache], set()) == before
    assert len(plan["planned_files"]) == 16
    assert sum(item["action"] == "delete_obsolete_png" for item in plan["planned_files"]) == 6
    assert sum(item["action"] == "archive_non_png" for item in plan["planned_files"]) == 10
    assert all("Topography" not in item["source"] for item in plan["planned_files"])
    assert plan["primary_validation"]["CCube"]["eligible_pairs"] == 20
    assert plan["primary_validation"]["VRohtoPremium"]["eligible_pairs"] == 19


def test_execute_archives_non_png_removes_only_six_images_and_protects_all_else(synthetic):
    root, cache, attention = synthetic
    plan = runner.build_plan(root, cache, attention)
    result = runner.execute_plan(plan)
    assert result["status"] == "completed"
    assert result["deleted_png_count"] == 6
    assert result["archived_non_png_count"] == 10
    assert result["protected_unchanged"]
    assert not result["psd_recomputed"]
    assert not result["primary_figures_rerendered"]
    assert not result["no11_results_recomputed"]
    assert not runner.current_legacy_files(root)
    assert not list(Path(plan["archive_root"]).rglob("*.png"))
    assert len([p for p in Path(plan["archive_root"]).rglob("*") if p.is_file()]) == 10
    for entry in plan["planned_files"]:
        assert not Path(entry["source"]).exists()
        if entry["destination"]:
            assert runner.digest(Path(entry["destination"])) == entry["sha256"]
    assert json.loads(Path(plan["record"]).read_text()) == result
    assert all(
        not (root / product / "SetQuantification" / runner.SUFFIX).exists()
        for product in runner.PRODUCTS
    )
    with pytest.raises(ValueError, match="stale, tampered, or already"):
        runner.execute_plan(plan)


def test_unexpected_legacy_file_blocks_before_any_write(synthetic):
    root, cache, attention = synthetic
    extra = root / "Sub" / f"Unexpected_{runner.SUFFIX}.csv"
    extra.write_text("unexpected")
    with pytest.raises(ValueError, match="exact 16-file"):
        runner.build_plan(root, cache, attention)
    assert all(path.exists() for path in runner.legacy_paths(root))


def test_generic_named_file_in_retired_directory_blocks_before_any_write(synthetic):
    root, cache, attention = synthetic
    extra = root / "CCube/SetQuantification" / runner.SUFFIX / "README.txt"
    extra.write_text("unexpected file must not be silently retained or deleted")
    with pytest.raises(ValueError, match="exact 16-file"):
        runner.build_plan(root, cache, attention)
    assert extra.exists()


def test_finder_metadata_is_retained_and_not_counted_as_analysis(synthetic):
    root, cache, attention = synthetic
    metadata = root / "CCube/SetQuantification" / runner.SUFFIX / ".DS_Store"
    metadata.write_bytes(b"preserve Finder metadata")
    plan = runner.build_plan(root, cache, attention)
    runner.execute_plan(plan)
    assert metadata.read_bytes() == b"preserve Finder metadata"
    assert not runner.current_legacy_files(root)


def test_old_nonempty_policy_blocks_before_any_write(synthetic):
    root, cache, attention = synthetic
    attention.write_text(attention.read_text().replace("| なし | なし |", "| prior-pair | なし |"))
    with pytest.raises(ValueError, match="must be none"):
        runner.build_plan(root, cache, attention)


def test_primary_missing_restored_pair_blocks_retirement(synthetic):
    root, cache, attention = synthetic
    path = root / "Sub/tables/SetQuantification" / f"{runner.STEM}_Quantification_Values_CCube.csv"
    text = path.read_text()
    path.write_text(
        "\n".join(line for line in text.splitlines() if "synthetic-CCube-0," not in line)
    )
    with pytest.raises(ValueError, match="Primary cohort differs"):
        runner.build_plan(root, cache, attention)


def test_changed_hash_blocks_before_any_write(synthetic):
    root, cache, attention = synthetic
    plan = runner.build_plan(root, cache, attention)
    Path(plan["planned_files"][0]["source"]).write_bytes(b"changed after planning")
    with pytest.raises(ValueError, match="file changed"):
        runner.execute_plan(plan)
    assert not Path(plan["record"]).exists()
    assert not Path(plan["archive_root"]).exists()


def test_tampered_destination_blocks_before_any_write(synthetic):
    root, cache, attention = synthetic
    plan = runner.build_plan(root, cache, attention)
    next(item for item in plan["planned_files"] if item["destination"])["destination"] = (
        "/tmp/not-allowed"
    )
    with pytest.raises(ValueError, match="plan tampered"):
        runner.execute_plan(plan)
    assert not Path(plan["record"]).exists()


def test_failed_archive_copy_deletes_nothing(synthetic, monkeypatch):
    root, cache, attention = synthetic
    plan = runner.build_plan(root, cache, attention)

    def fail_copy(*args, **kwargs):
        raise OSError("synthetic failure")

    monkeypatch.setattr(runner.shutil, "copy2", fail_copy)
    with pytest.raises(OSError, match="synthetic failure"):
        runner.execute_plan(plan)
    assert all(path.exists() for path in runner.legacy_paths(root))
    assert json.loads(Path(plan["record"]).read_text())["status"] == "failed"


def test_symlinked_target_is_not_followed(synthetic, tmp_path):
    root, cache, attention = synthetic
    path = runner.legacy_paths(root)[0]
    external = tmp_path / "external.png"
    external.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(ValueError, match="regular file"):
        runner.build_plan(root, cache, attention)


def test_verify_completed_retirement_is_read_only_and_checks_no11(synthetic):
    root, cache, attention = synthetic
    runner.execute_plan(runner.build_plan(root, cache, attention))
    before = runner.inventory([root.parent, cache], set())
    result = runner.verify_retirement(root, cache, attention)
    assert result["status"] == "verified_completed"
    assert result["read_only"]
    assert result["archived_non_png_count"] == 10
    assert result["current_retired_file_count"] == 0
    assert result["protected_no11_file_count"] == 2
    assert runner.inventory([root.parent, cache], set()) == before


@pytest.mark.parametrize("changed", ["archive", "no11", "policy", "legacy"])
def test_verify_rejects_changed_evidence_or_current_state(synthetic, changed):
    root, cache, attention = synthetic
    plan = runner.build_plan(root, cache, attention)
    runner.execute_plan(plan)
    if changed == "archive":
        path = next(
            Path(item["destination"]) for item in plan["planned_files"] if item["destination"]
        )
        path.write_text("changed archive")
    elif changed == "no11":
        path = root.parent / "No11_sub_PzLowAlphaChange/CCube/GrandAverage/preserved.png"
        path.write_bytes(b"unexpected No11 change")
    elif changed == "policy":
        attention.write_text(
            attention.read_text().replace("| なし | なし |", "| prior-pair | なし |")
        )
    else:
        folder = root / "CCube/SetQuantification" / runner.SUFFIX
        folder.mkdir()
        (folder / "README.txt").write_text("unexpected current output")
    with pytest.raises(ValueError):
        runner.verify_retirement(root, cache, attention)
