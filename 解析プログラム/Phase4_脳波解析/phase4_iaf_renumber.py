"""One-time, audited migration to No8=Pz and No9=Fz setwise IAF.

No raw input or numerical spectrum is modified. Exact target inventories and
verified non-image backups precede removal of superseded outputs. The CLI is
restricted to the authorized production result/cache roots. Participant-specific
additional exclusions are supplied at execution, not embedded in this module.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import shutil
from collections import Counter
from pathlib import Path

BASE = Path(
    "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/"
    "SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_本解析/Phase4_脳波解析"
)
CACHE_BASE = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/Phase4_脳波解析"
)
OLD = {
    8: "No8_PzSetwiseIAF",
    9: "No9_PzHalfSetIAF",
    10: "No10_FzSetwiseIAF",
    11: "No11_FzHalfSetIAF",
}
NEW = {8: OLD[8], 9: "No9_FzSetwiseIAF"}
RENUMBER = {8: 8, 10: 9}
ADOPTION = "Grand-average採用（追加選別版）"
HISTORY = "Sub/history/BeforeRenumbering_20261110"
SCHEMA = "phase4-iaf-selection-setwise-2026-11-10-v2"


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def csv_load(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def csv_save(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.getvalue().encode("utf-8-sig"))
    if csv_load(path) != (fields, rows):
        raise ValueError(f"CSV readback mismatch: {path}")


def remap_row(row: dict[str, str]) -> dict[str, str]:
    """Change only identity/path metadata; numerical strings are untouched."""
    new = dict(row)
    if "analysis_number" in new:
        old = int(new["analysis_number"])
        if old not in RENUMBER:
            raise ValueError("Retired half-set row cannot enter current tables")
        new["analysis_number"] = str(RENUMBER[old])
    for key in ("review_figure_path", "original_figure_path"):
        if key in new:
            new[key] = new[key].replace(OLD[10], NEW[9]).replace("_No10_", "_No9_")
    return new


def selection_update(record: dict, additional: dict) -> dict:
    manual = {str(new): record["manual_exclusions"][str(old)] for old, new in RENUMBER.items()}
    manual = json.loads(json.dumps(manual))
    decisions = []
    matched = set()
    for row in record["decisions"]:
        old = int(row["analysis_number"])
        if old not in RENUMBER:
            continue
        current = remap_row({k: str(v) for k, v in row.items()})
        number, product, pair = current["analysis_number"], current["product"], current["pair_id"]
        if pair in additional.get(number, {}).get(product, []):
            if current[ADOPTION] != "する":
                raise ValueError("New exclusion must refer to a previously adopted pair")
            manual[number][product].append(pair)
            matched.add((number, product, pair))
            current[ADOPTION] = "しない"
            current["利用者指定追加除外"] = "あり"
            current["採否理由"] = "利用者の単峰明瞭性確認による追加不採用（2026-11-10改番時）"
        elif current[ADOPTION] == "する":
            current["採否理由"] = (
                "両条件に明瞭な単一の山を認める区間あり・両Set1有限・利用者確認後の採用"
            )
        decisions.append(current)
    expected = {
        (n, p, pair)
        for n, groups in additional.items()
        for p, pairs in groups.items()
        for pair in pairs
    }
    if matched != expected:
        raise ValueError("Additional exclusion not found or product/analysis mismatch")
    for groups in manual.values():
        for product, pairs in groups.items():
            if len(pairs) != len(set(pairs)):
                raise ValueError("Duplicate manual exclusion")
            groups[product] = sorted(pairs)
    return {
        "schema": SCHEMA,
        "active_analyses": {"8": "Pz", "9": "Fz"},
        "decision_date": "2026-11-10",
        "status": "final",
        "scope": "No8・No9 IAF差分Grand-average追加選別版のみ",
        "rule": (
            "両条件それぞれに単一の明瞭なalphaの山を認める区間あり・両Set1有限・"
            "利用者の最終指定を適用。全Set明瞭は要求しない。"
        ),
        "interpretation": (
            "探索的な形状選別。元のC/A/U/M観察と利用者採否を分離し、個人IAFは修正しない。"
        ),
        "manual_exclusions": manual,
        "decisions": decisions,
        "grand_average_execution_record": "../logs/IAFGrandAverage_*.json",
        "individual_iaf_changed": False,
    }


def protected_inventory(base: Path) -> dict:
    excluded = set(OLD.values()) | set(NEW.values())
    return {
        str(p): [p.stat().st_size, p.stat().st_mtime_ns]
        for folder in base.iterdir()
        if folder.name not in excluded and folder.is_dir()
        for p in folder.rglob("*")
        if p.is_file() and p.name != ".DS_Store"
    }


def migrate(base: Path, cache_base: Path, additional: dict, apply: bool) -> dict:
    roots = [base / name for name in OLD.values()]
    archive = base / OLD[8] / HISTORY
    logs = base / OLD[8] / "Sub/logs"
    plan_path = logs / "IAFRenumbering_Plan_20261110.json"
    result_path = logs / "IAFRenumbering_20261110.json"
    old_cache = cache_base / "No8-11_PzFzIAF"
    new_cache = cache_base / "No8-9_PzFzIAF"
    if result_path.exists():
        result = json.loads(result_path.read_text())
        if result["additional_exclusions"] != additional:
            raise ValueError("Completed migration uses different additional exclusions")
        for path, digest in result["retained_individual_png_sha256"].items():
            if sha(Path(path)) != digest:
                raise ValueError("Retained individual figure changed")
        for relative, digest in result["cache_sha256"].items():
            if sha(new_cache / relative) != digest:
                raise ValueError("Preserved cache changed")
        for path, digest in result["selection_sha256"].items():
            if sha(Path(path)) != digest:
                raise ValueError("Current selection differs from completed migration")
        return {"status": "already_migrated_verified", "audit": str(result_path)}
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
    else:
        if any(not p.is_dir() or p.is_symlink() for p in roots) or (base / NEW[9]).exists():
            raise ValueError("Unexpected source/target roots")
        if not old_cache.is_dir() or new_cache.exists() or archive.exists():
            raise ValueError("Unexpected cache/history roots")
        files = [
            p for root in roots for p in root.rglob("*") if p.is_file() and p.name != ".DS_Store"
        ]
        if any(p.is_symlink() for root in roots for p in root.rglob("*")):
            raise ValueError("Symlinks are not allowed in migration targets")
        if any(p.suffix not in (".png", ".csv", ".md", ".json", ".py") for p in files):
            raise ValueError("Unrecognized target file type")
        cache_files = [p for p in old_cache.rglob("*") if p.is_file()]
        if len(cache_files) != 80 or any(p.suffix != ".h5" or p.is_symlink() for p in cache_files):
            raise ValueError("Expected exactly 80 HDF5 cache files")
        plan = {
            "files": {str(p.relative_to(base)): sha(p) for p in files},
            "cache_sha256": {str(p.relative_to(old_cache)): sha(p) for p in cache_files},
            "protected_other_outputs": protected_inventory(base),
            "additional_exclusions": additional,
        }
    if plan["additional_exclusions"] != additional:
        raise ValueError("Resume arguments differ from frozen migration plan")
    for relative in plan["files"]:
        target = Path(relative)
        if target.is_absolute() or ".." in target.parts or target.parts[0] not in OLD.values():
            raise ValueError("Unsafe migration inventory path")
    source_selection = archive / OLD[8] / "Sub/PeakClarityReview/GrandAverageSelection_Final.json"
    if not source_selection.exists():
        source_selection = base / OLD[8] / "Sub/PeakClarityReview/GrandAverageSelection_Final.json"
    validated_selection = selection_update(json.loads(source_selection.read_text()), additional)
    expected_counts = {
        ("8", "CCube"): 12,
        ("8", "VRohtoPremium"): 11,
        ("9", "CCube"): 11,
        ("9", "VRohtoPremium"): 10,
    }
    validated_rows = validated_selection["decisions"]
    validated_counts = Counter(
        (r["analysis_number"], r["product"], r[ADOPTION]) for r in validated_rows
    )
    if (
        len(validated_rows) != 80
        or len({(r["analysis_number"], r["pair_id"]) for r in validated_rows}) != 80
        or any(validated_counts[(n, p, "する")] != v for (n, p), v in expected_counts.items())
    ):
        raise ValueError("Final adopted roster count mismatch before migration")
    summary = {
        "target_files": len(plan["files"]),
        "cache_files": len(plan["cache_sha256"]),
        "write": apply,
    }
    if not apply:
        return summary
    if not plan_path.exists():
        dump(plan_path, plan)
    # Snapshot every non-PNG old output before modifying any old content.
    for relative, digest in plan["files"].items():
        if Path(relative).suffix == ".png":
            continue
        source, backup = base / relative, archive / relative
        if not backup.exists():
            if sha(source) != digest:
                raise ValueError("Source changed before backup")
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup)
        if sha(backup) != digest:
            raise ValueError("Historical snapshot checksum mismatch")
    (archive / "README.md").write_text(
        "# 改番前の記録（現行解析には使わない）\n\n"
        "旧No8–11の表・観察・実行記録を原文保存。旧番号・採否・実績は過去情報。"
        "現行はNo8=Pz、No9=FzのSet全体のみ。旧PNGは保存しない。"
        "数値PSD/IAFはNo8-9_PzFzIAF/SpectralSegmentsへ内容不変で移動。\n",
        encoding="utf-8",
    )
    if old_cache.exists():
        old_cache.rename(new_cache)
    for relative, digest in plan["cache_sha256"].items():
        if sha(new_cache / relative) != digest:
            raise ValueError("Cache changed during directory rename")
    retained = {}
    desired = set()
    for old, new in RENUMBER.items():
        target = base / NEW[new]
        for relative, digest in plan["files"].items():
            rel = Path(relative)
            if rel.parts[0] != OLD[old] or "Individual" not in rel.parts or rel.suffix != ".png":
                continue
            source = base / rel
            destination = target.joinpath(*rel.parts[1:]).with_name(
                rel.name.replace(f"_No{old}_", f"_No{new}_")
            )
            if source != destination and not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.rename(destination)
            if sha(destination) != digest:
                raise ValueError("Individual PNG changed during rename")
            retained[str(destination)] = digest
            desired.add(str(destination.relative_to(base)))
        for suffix in ("IAF_Estimates", "PeakAvailability"):
            source = archive / OLD[old] / f"Sub/tables/No{old}_{suffix}.csv"
            destination = target / f"Sub/tables/No{new}_{suffix}.csv"
            destination.parent.mkdir(parents=True, exist_ok=True)
            if old == new or suffix == "PeakAvailability":
                shutil.copy2(source, destination)
            else:
                fields, rows = csv_load(source)
                csv_save(destination, fields, [remap_row(r) for r in rows])
            desired.add(str(destination.relative_to(base)))
        destination = target / "Sub/tables/ParticipantManifest.csv"
        shutil.copy2(archive / OLD[old] / "Sub/tables/ParticipantManifest.csv", destination)
        desired.add(str(destination.relative_to(base)))
        for product in ("CCube", "VRohtoPremium"):
            (target / product / "GrandAverage").mkdir(parents=True, exist_ok=True)
        (target / "Sub/logs").mkdir(parents=True, exist_ok=True)
    if len(retained) != 80:
        raise ValueError("Expected 80 retained individual PNGs")
    source_review = archive / OLD[8] / "Sub/PeakClarityReview"
    review = base / OLD[8] / "Sub/PeakClarityReview"
    record = selection_update(
        json.loads((source_review / "GrandAverageSelection_Final.json").read_text()), additional
    )
    decisions = {(r["analysis_number"], r["pair_id"]): r for r in record["decisions"]}
    counts = Counter((r["analysis_number"], r["product"], r[ADOPTION]) for r in record["decisions"])
    expected = {
        ("8", "CCube"): 12,
        ("8", "VRohtoPremium"): 11,
        ("9", "CCube"): 11,
        ("9", "VRohtoPremium"): 10,
    }
    if len(decisions) != 80 or any(counts[(n, p, "する")] != v for (n, p), v in expected.items()):
        raise ValueError("Final adopted roster count mismatch")
    selection_json = review / "GrandAverageSelection_Final.json"
    selection_csv = review / "GrandAverageSelection_Final.csv"
    dump(selection_json, record)
    csv_save(selection_csv, list(record["decisions"][0]), record["decisions"])
    for name in ("ParticipantReview.csv", "IntervalReview.csv", "GroupSummary.csv"):
        fields, rows = csv_load(source_review / name)
        current = [remap_row(r) for r in rows if int(r["analysis_number"]) in RENUMBER]
        for row in current:
            if name == "ParticipantReview.csv":
                row.update(decisions[(row["analysis_number"], row["pair_id"])])
            if "review_status" in row:
                row["review_status"] = "観察記録を継承・現行採否は確定一覧参照"
            if name == "GroupSummary.csv":
                row["selection_finalized"] = "True"
                row.pop("grand_average_executed", None)
                row["adopted_pairs"] = str(expected[(row["analysis_number"], row["product"])])
        if name == "GroupSummary.csv":
            fields.remove("grand_average_executed")
            fields.append("adopted_pairs")
        csv_save(review / name, fields, current)
    assessment = json.loads((source_review / "AssessmentInput.json").read_text())
    current_assessment = []
    for row in assessment:
        if int(row["analysis_number"]) in RENUMBER:
            row["analysis_number"] = RENUMBER[int(row["analysis_number"])]
            current_assessment.append(row)
    dump(review / "AssessmentInput.json", current_assessment)
    md = [
        "# No8・No9：明瞭な単一ピークの追加選別版・確定採否",
        "",
        record["rule"],
        "",
        record["interpretation"],
        "",
        "実行結果はSub/logsとSub/tables/GrandAverageを参照。採用集合のNとSet別の有効Nは異なる場合がある。",
        "",
    ]
    for number, product in expected:
        md += [
            f"## No{number} / {product}（採用{expected[(number, product)]}人）",
            "",
            "| ID | 採用 | 理由 |",
            "|---|---|---|",
        ]
        md += [
            f"| {r['pair_id']} | {r[ADOPTION]} | {r['採否理由']} |"
            for r in record["decisions"]
            if (r["analysis_number"], r["product"]) == (number, product)
        ]
        md.append("")
    (review / "GrandAverageSelection_Final.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (review / "PeakClarityReview.md").write_text(
        "# No8・No9：形状観察と採否\n\n"
        "現在の採否は[確定一覧](GrandAverageSelection_Final.md)。ParticipantReview.csvのID直後の採用列も同じ。"
        "C=明瞭、A=競合峰/曖昧、U=不明瞭、M=PSD欠測の元観察は変更しない。"
        "現行の選別は利用者の単峰明瞭性確認を反映したもので、Cがあることだけでは採用を保証しない。"
        "両条件に明瞭な区間が必要だが全Setで明瞭である必要はない。"
        "旧番号・旧採否・旧実行記録はSub/historyに隔離し、現行計算に読まない。"
        "IntervalReview.csvの元形状観察と、現在の採否判断は別層。\n",
        encoding="utf-8",
    )
    desired.update(
        str(p.relative_to(base))
        for p in review.iterdir()
        if p.is_file() and p.name != "SavedEstimateInventory.csv"
    )
    # Only files in the frozen, exact target inventory can be removed.
    removed = []
    for relative, digest in plan["files"].items():
        path = base / relative
        if relative in desired or not path.exists():
            continue
        if sha(path) != digest:
            raise ValueError(f"Unexpectedly modified deletion target: {path}")
        if path.suffix != ".png" and sha(archive / relative) != digest:
            raise ValueError("Deletion target has no verified historical copy")
        path.unlink()
        removed.append(relative)
    for number in (9, 10, 11):
        root = base / OLD[number]
        for directory in sorted(
            [p for p in root.rglob("*") if p.is_dir()], key=lambda p: len(p.parts), reverse=True
        ):
            if not any(directory.iterdir()):
                directory.rmdir()
        if root.exists():
            root.rmdir()
    selection_outputs = [
        selection_json,
        selection_csv,
        review / "ParticipantReview.csv",
        review / "GrandAverageSelection_Final.md",
    ]
    dump(
        logs / "PeakClarityReview_SelectionFinalized.json",
        {
            "schema": SCHEMA,
            "status": "final",
            "rows": 80,
            "observation_grades_unchanged": True,
            "outputs_sha256": {str(p): sha(p) for p in selection_outputs},
        },
    )
    if protected_inventory(base) != plan["protected_other_outputs"]:
        raise ValueError("An out-of-scope result changed during migration")
    result = {
        "status": "migration_verified_grand_average_pending",
        "mapping": {"8": "Pz", "9": "Fz (formerly No10)"},
        "retired": [OLD[9], OLD[11]],
        "archive": str(archive),
        "retained_individual_png_sha256": retained,
        "cache_sha256": plan["cache_sha256"],
        "removed_files": removed,
        "removed_png_count": sum(Path(p).suffix == ".png" for p in removed),
        "numerical_iaf_and_psd_unchanged": True,
        "additional_exclusions": additional,
        "selection_sha256": {str(p): sha(p) for p in (selection_json, selection_csv)},
        "out_of_scope_result_inventory_unchanged": True,
        "selection_counts": [
            {"number": n, "product": p, "adopted": count} for (n, p), count in expected.items()
        ],
    }
    dump(result_path, result)
    return {
        **summary,
        "status": result["status"],
        "removed_png": result["removed_png_count"],
        "audit": str(result_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--additional", action="append", default=[], metavar="NEW_NO:PRODUCT:PAIR,PAIR"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    additional = {}
    for text in args.additional:
        number, product, pairs = text.split(":", 2)
        if number not in ("8", "9") or product not in ("CCube", "VRohtoPremium"):
            raise ValueError("Invalid current analysis/product")
        if product in additional.get(number, {}):
            raise ValueError("Duplicate additional-exclusion argument")
        additional.setdefault(number, {})[product] = pairs.split(",")
    print(json.dumps(migrate(BASE, CACHE_BASE, additional, args.apply), ensure_ascii=False))


if __name__ == "__main__":
    main()
