"""Synthetic migration tests: no production participants or filesystem writes."""

from __future__ import annotations

import copy
import json
import sys
from collections import Counter
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parents[1] / "解析プログラム/Phase4_脳波解析"
sys.path.insert(0, str(SCRIPT_DIR))
import phase4_iaf_renumber as migration  # noqa: E402


def write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def file_hashes(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): migration.sha(p) for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def layout(tmp_path):
    """Match production cardinalities using invented IDs and non-image bytes."""
    base, cache_base = tmp_path / "results", tmp_path / "cache"
    products = ("CCube", "VRohtoPremium")
    people = [(f"{10001 + i}-{20001 + i}", products[i // 20], i % 20) for i in range(40)]
    initial_adopted = {
        (8, "CCube"): 14,
        (8, "VRohtoPremium"): 15,
        (10, "CCube"): 13,
        (10, "VRohtoPremium"): 13,
    }
    additional_counts = {
        ("8", "CCube"): 2,
        ("8", "VRohtoPremium"): 4,
        ("9", "CCube"): 2,
        ("9", "VRohtoPremium"): 3,
    }
    additional = {"8": {}, "9": {}}
    for old, new in migration.RENUMBER.items():
        for product in products:
            end = initial_adopted[old, product]
            start = end - additional_counts[str(new), product]
            additional[str(new)][product] = [
                pair for pair, p, index in people if p == product and start <= index < end
            ]
    decisions = []
    for number, folder in migration.OLD.items():
        root = base / folder
        rows = []
        for pair, product, index in people:
            write_bytes(
                root / product / "Individual" / f"ID{pair}_No{number}_IAF.png",
                f"synthetic individual {number} {pair}".encode(),
            )
            adopted = index < initial_adopted.get((number, product), 20)
            decisions.append(
                {
                    "analysis_number": str(number),
                    "channel": "Pz" if number in (8, 9) else "Fz",
                    "product": product,
                    "pair_id": pair,
                    migration.ADOPTION: "する" if adopted else "しない",
                    "採否確定状態": "確定",
                    "利用者指定追加除外": "なし",
                    "採否理由": "synthetic original observation",
                }
            )
            for condition in ("Eye Drop", "Control"):
                for position in range(1, 7):
                    rows.append(
                        {
                            "analysis_number": str(number),
                            "pair_id": pair,
                            "condition": condition,
                            "position": str(position),
                            "frequency_hz": f"{8.1 + index / 10 + position / 10:.17g}",
                        }
                    )
        migration.csv_save(root / f"Sub/tables/No{number}_IAF_Estimates.csv", list(rows[0]), rows)
        migration.csv_save(
            root / f"Sub/tables/No{number}_PeakAvailability.csv",
            ["product", "available"],
            [{"product": p, "available": "120"} for p in products],
        )
        migration.csv_save(
            root / "Sub/tables/ParticipantManifest.csv",
            ["pair_id", "product"],
            [{"pair_id": pair, "product": p} for pair, p, _ in people],
        )
        migration.dump(root / f"Sub/logs/old_run_{number}.json", {"analysis_number": number})
        for product in products:
            write_bytes(root / product / "GrandAverage" / f"old_No{number}.png", b"obsolete")
    review = base / migration.OLD[8] / "Sub/PeakClarityReview"
    record = {
        "manual_exclusions": {str(n): {p: [] for p in products} for n in migration.OLD},
        "decisions": decisions,
    }
    migration.dump(review / "GrandAverageSelection_Final.json", record)
    migration.csv_save(review / "GrandAverageSelection_Final.csv", list(decisions[0]), decisions)
    review_rows = [{**r, "review_status": "old", "original_grade": "C"} for r in decisions]
    migration.csv_save(review / "ParticipantReview.csv", list(review_rows[0]), review_rows)
    intervals = [
        {
            "analysis_number": r["analysis_number"],
            "pair_id": r["pair_id"],
            "position": str(pos),
            "condition": condition,
            "grade": "C",
        }
        for r in decisions
        for pos in range(1, 7)
        for condition in ("Eye Drop", "Control")
    ]
    migration.csv_save(review / "IntervalReview.csv", list(intervals[0]), intervals)
    groups = [
        {
            "analysis_number": str(n),
            "product": p,
            "selection_finalized": "True",
            "grand_average_executed": "True",
        }
        for n in migration.OLD
        for p in products
    ]
    migration.csv_save(review / "GroupSummary.csv", list(groups[0]), groups)
    migration.csv_save(review / "SavedEstimateInventory.csv", ["obsolete"], [{"obsolete": "yes"}])
    migration.dump(review / "AssessmentInput.json", decisions)
    write_bytes(review / "GrandAverageSelection_Final.md", b"old decisions")
    write_bytes(review / "PeakClarityReview.md", b"old methods")
    for n in migration.OLD:
        write_bytes(review / "CCube" / f"old_No{n}_review.png", f"old review {n}".encode())
    for index in range(80):
        write_bytes(
            cache_base / "No8-11_PzFzIAF/SpectralSegments" / f"synthetic_{index:03d}.h5",
            f"synthetic preserved spectral payload {index}".encode(),
        )
    write_bytes(base / "No7_Protected" / "original.txt", b"do not touch")
    return base, cache_base, additional


def test_preflight_does_not_write(layout):
    base, cache_base, additional = layout
    before = file_hashes(base), file_hashes(cache_base)
    result = migration.migrate(base, cache_base, additional, False)
    assert result["cache_files"] == 80
    assert result["write"] is False
    assert (file_hashes(base), file_hashes(cache_base)) == before


def test_full_migration_preserves_sources_and_is_repeatable(layout):
    base, cache_base, additional = layout
    before = file_hashes(base)
    old_cache = file_hashes(cache_base / "No8-11_PzFzIAF")
    result = migration.migrate(base, cache_base, additional, True)
    assert result["status"] == "migration_verified_grand_average_pending"
    assert result["removed_png"] == 92  # 80 half-set individuals, 8 GA, 4 QC.
    archive = base / migration.OLD[8] / migration.HISTORY
    assert not list(archive.rglob("*.png"))
    for relative, digest in before.items():
        path = Path(relative)
        if path.parts[0] not in migration.OLD.values():
            assert migration.sha(base / relative) == digest
        elif path.suffix != ".png":
            assert migration.sha(archive / relative) == digest
    for old, new in migration.RENUMBER.items():
        pngs = list((base / migration.NEW[new]).glob("*/Individual/*.png"))
        assert len(pngs) == 40
        for png in pngs:
            relative = str(png.relative_to(base)).replace(migration.NEW[new], migration.OLD[old])
            relative = relative.replace(f"_No{new}_", f"_No{old}_")
            assert migration.sha(png) == before[relative]
        source = archive / migration.OLD[old] / f"Sub/tables/No{old}_IAF_Estimates.csv"
        current = base / migration.NEW[new] / f"Sub/tables/No{new}_IAF_Estimates.csv"
        fields, source_rows = migration.csv_load(source)
        assert migration.csv_load(current) == (
            fields,
            [migration.remap_row(r) for r in source_rows],
        )
    for old in (9, 10, 11):
        assert not (base / migration.OLD[old]).exists()
    assert not (cache_base / "No8-11_PzFzIAF").exists()
    assert file_hashes(cache_base / "No8-9_PzFzIAF") == old_cache
    review = base / migration.OLD[8] / "Sub/PeakClarityReview"
    record = json.loads((review / "GrandAverageSelection_Final.json").read_text())
    assert len(record["decisions"]) == 80
    counts = Counter(
        (r["analysis_number"], r["product"])
        for r in record["decisions"]
        if r[migration.ADOPTION] == "する"
    )
    assert counts == {
        ("8", "CCube"): 12,
        ("8", "VRohtoPremium"): 11,
        ("9", "CCube"): 11,
        ("9", "VRohtoPremium"): 10,
    }
    _, rows = migration.csv_load(review / "IntervalReview.csv")
    assert len(rows) == 960
    assert {r["analysis_number"] for r in rows} == {"8", "9"}
    assert {r["grade"] for r in rows} == {"C"}
    before_repeat = file_hashes(base), file_hashes(cache_base)
    assert (
        migration.migrate(base, cache_base, additional, True)["status"]
        == "already_migrated_verified"
    )
    assert (file_hashes(base), file_hashes(cache_base)) == before_repeat


@pytest.mark.parametrize("apply", [False, True])
def test_bad_cohort_is_rejected_before_writes(layout, apply):
    base, cache_base, additional = layout
    bad = copy.deepcopy(additional)
    bad["8"]["CCube"].pop()
    before = file_hashes(base), file_hashes(cache_base)
    with pytest.raises(ValueError, match="count mismatch before migration"):
        migration.migrate(base, cache_base, bad, apply)
    assert (file_hashes(base), file_hashes(cache_base)) == before


def test_completed_migration_rejects_argument_and_selection_changes(layout):
    base, cache_base, additional = layout
    migration.migrate(base, cache_base, additional, True)
    bad = copy.deepcopy(additional)
    bad["8"]["CCube"].pop()
    with pytest.raises(ValueError, match="different additional exclusions"):
        migration.migrate(base, cache_base, bad, True)
    selection = base / migration.OLD[8] / "Sub/PeakClarityReview/GrandAverageSelection_Final.json"
    selection.write_text(selection.read_text() + "\n")
    with pytest.raises(ValueError, match="selection differs"):
        migration.migrate(base, cache_base, additional, True)


def test_interrupted_migration_can_resume_without_numerical_recomputation(layout, monkeypatch):
    base, cache_base, additional = layout
    original_save = migration.csv_save
    original_cache = file_hashes(cache_base / "No8-11_PzFzIAF")

    def fail_new_table(path, fields, rows):
        if path.name == "No9_IAF_Estimates.csv":
            raise RuntimeError("synthetic interruption")
        return original_save(path, fields, rows)

    monkeypatch.setattr(migration, "csv_save", fail_new_table)
    with pytest.raises(RuntimeError, match="synthetic interruption"):
        migration.migrate(base, cache_base, additional, True)
    monkeypatch.setattr(migration, "csv_save", original_save)
    result = migration.migrate(base, cache_base, additional, True)
    assert result["status"] == "migration_verified_grand_average_pending"
    assert file_hashes(cache_base / "No8-9_PzFzIAF") == original_cache
    assert (
        sum(len(list((base / name).glob("*/Individual/*.png"))) for name in migration.NEW.values())
        == 80
    )
