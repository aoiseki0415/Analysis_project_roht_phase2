"""Explicit, resumable revision of the frozen No8/9 selected-cohort decision.

Participant IDs enter only through the command line, never through source code.
The CLI is restricted to the authorized OneDrive tree. Synthetic tests pass a
temporary base to revise_selection; no EEG, PSD or IAF value is read or changed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import phase4_iaf_grand_average as ga

OLD_SCHEMA = "phase4-iaf-selection-setwise-2026-11-10-v2"
OLD_COUNTS = {8: {"CCube": 12, "VRohtoPremium": 11}, 9: {"CCube": 11, "VRohtoPremium": 10}}
REVIEW = Path("Sub/PeakClarityReview")
FROZEN = Path("Sub/logs/PeakClarityReview_SelectionFinalized.json")
EDITABLE = tuple(
    REVIEW / name
    for name in (
        "GrandAverageSelection_Final.json",
        "GrandAverageSelection_Final.csv",
        "GrandAverageSelection_Final.md",
        "ParticipantReview.csv",
        "GroupSummary.csv",
    )
) + (FROZEN,)


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def revise_record(record: dict, number: int, product: str, pair: str, reason: str) -> dict:
    """Change exactly one currently selected pair; all observations stay external."""
    revised = copy.deepcopy(record)
    matches = [
        r
        for r in revised["decisions"]
        if int(r["analysis_number"]) == number and r["pair_id"] == pair
    ]
    if len(matches) != 1 or matches[0]["product"] != product:
        raise ValueError("Requested No/pair/product does not match one frozen decision")
    target = matches[0]
    if target[ga.ADOPTION] != "する":
        raise ValueError("Requested pair was not selected in the frozen source")
    target[ga.ADOPTION] = "しない"
    target["利用者指定追加除外"] = "あり"
    target["採否理由"] += " / 利用者確定の追加除外: " + reason
    revised["manual_exclusions"][str(number)][product].append(pair)
    revised["manual_exclusions"][str(number)][product].sort()
    revised["schema"] = ga.SELECTION_SCHEMA
    revised["updated_utc"] = datetime.now(UTC).isoformat()
    revised["revision"] = {
        "source_schema": record["schema"],
        "analysis_number": number,
        "product": product,
        "pair_id": pair,
        "reason": reason,
        "scope": "SelectedParticipants only; both conditions and all six sets",
        "automatic_psd_cutoff_added": False,
        "observations_reclassified": False,
    }
    return revised


def selection_markdown(record: dict) -> str:
    lines = [
        "# No8・No9：追加選別Grand-averageの最新確定採否",
        "",
        record.get("rule", "明瞭な単峰に基づく追加選別。元観察と最新採否を分離する。"),
        "",
        record.get("interpretation", "事後・探索的な選別であり、生理的正解や効果を保証しない。"),
        "",
        "## 今回の確定変更",
        "",
        f"No{record['revision']['analysis_number']} / {record['revision']['product']} / "
        f"{record['revision']['pair_id']}: {record['revision']['reason']}",
        "",
        "追加選別版だけで当該ペアの両条件・全Setを不採用とする。AllAvailable、個人図、"
        "保存IAF/PSD、他Noは変更しない。一般的なPSD閾値は導入しない。"
        "C/A/U/Mは元の形状観察であり、最新の採否とは別に保持する。",
        "",
        "採用集合の人数と欠測適用後のSet別有効Nは区別する。実行結果はSub/logs、"
        "Sub/tables/GrandAverageを参照。以前の判断・非PNG記録はSub/historyに保存。",
        "",
    ]
    for number in ga.ANALYSES:
        for product in ga.PRODUCTS:
            rows = [
                r
                for r in record["decisions"]
                if int(r["analysis_number"]) == number and r["product"] == product
            ]
            count = sum(r[ga.ADOPTION] == "する" for r in rows)
            lines += [
                f"## No{number} / {product}（採用{count}人）",
                "",
                "| ID | 採用 | 理由 |",
                "|---|---|---|",
            ]
            lines += [f"| {r['pair_id']} | {r[ga.ADOPTION]} | {r['採否理由']} |" for r in rows]
            lines.append("")
    return "\n".join(lines) + "\n"


def revised_outputs(source: Path, manifest: dict, request: dict) -> dict[Path, bytes]:
    selection_json = source / REVIEW / "GrandAverageSelection_Final.json"
    selection_csv = source / REVIEW / "GrandAverageSelection_Final.csv"
    ga.load_selection(
        selection_json,
        selection_csv,
        manifest,
        expected_schema=OLD_SCHEMA,
        expected_counts=OLD_COUNTS,
    )
    record = revise_record(json.loads(selection_json.read_text()), **request)
    decisions = pd.DataFrame(record["decisions"]).astype(str)
    review = read_csv(source / REVIEW / "ParticipantReview.csv")
    if len(review) != 80 or review.duplicated(["analysis_number", "pair_id"]).any():
        raise ValueError("ParticipantReview must have exactly 80 unique decisions")
    if not set(decisions.columns).issubset(review.columns):
        raise ValueError("ParticipantReview lacks current adoption columns")
    original_decisions = read_csv(selection_csv)
    keys = ["analysis_number", "pair_id"]
    pd.testing.assert_frame_equal(
        review[list(original_decisions.columns)].sort_values(keys).reset_index(drop=True),
        original_decisions.sort_values(keys).reset_index(drop=True),
    )
    lookup = decisions.set_index(["analysis_number", "pair_id"])
    for index, row in review.iterrows():
        decision = lookup.loc[(row.analysis_number, row.pair_id)]
        for column in decisions.columns:
            if column not in ("analysis_number", "pair_id"):
                review.loc[index, column] = decision[column]
    old_review = read_csv(source / REVIEW / "ParticipantReview.csv")
    observation_columns = old_review.columns.difference(decisions.columns)
    pd.testing.assert_frame_equal(old_review[observation_columns], review[observation_columns])
    groups = read_csv(source / REVIEW / "GroupSummary.csv")
    if len(groups) != 4 or groups.duplicated(["analysis_number", "product"]).any():
        raise ValueError("Observation GroupSummary requires four current No/product groups")
    for index, row in groups.iterrows():
        count = int(
            (
                (decisions.analysis_number == row.analysis_number)
                & (decisions["product"] == row["product"])
                & decisions[ga.ADOPTION].eq("する")
            ).sum()
        )
        if count != ga.SELECTED_COUNTS[int(row.analysis_number)][row["product"]]:
            raise ValueError("Revised adoption does not match the current cohort contract")
        groups.loc[index, "adopted_pairs"] = str(count)
    return {
        REVIEW / "GrandAverageSelection_Final.json": json_bytes(record),
        REVIEW / "GrandAverageSelection_Final.csv": csv_bytes(decisions),
        REVIEW / "GrandAverageSelection_Final.md": selection_markdown(record).encode(),
        REVIEW / "ParticipantReview.csv": csv_bytes(review),
        REVIEW / "GroupSummary.csv": csv_bytes(groups),
    }


def revise_selection(
    base: Path,
    manifest_path: Path,
    number: int,
    product: str,
    pair: str,
    reason: str,
    revision_key: str,
    apply: bool = False,
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", revision_key) or not reason.strip():
        raise ValueError("Provide a safe revision key and explicit reason")
    if number not in ga.ANALYSES or product not in ga.PRODUCTS:
        raise ValueError("Invalid current No/product")
    root = base / ga.ANALYSES[8][2]
    archive = root / "Sub/history" / f"SelectionRevision_{revision_key}"
    plan_path = archive / "plan.json"
    report_path = root / "Sub/logs" / f"IAFSelectionRevision_{revision_key}.json"
    for path in (*[root / p for p in EDITABLE], plan_path, report_path):
        ga.assert_output_path(path, base)
    request = {"number": number, "product": product, "pair": pair, "reason": reason}
    manifest = ga.read_manifest(manifest_path)
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        if plan["request"] != request or plan["manifest_sha256"] != ga.sha256_file(manifest_path):
            raise ValueError("Revision key already belongs to a different request or manifest")
        source = archive / "before"
        for relative, digest in plan["before_sha256"].items():
            if ga.sha256_file(source / relative) != digest:
                raise ValueError("Frozen pre-revision backup changed")
        if report_path.exists():
            report = json.loads(report_path.read_text())
            if report.get("status") == "selection_revised_grand_average_pending":
                ga.assert_hashes(report["outputs_sha256"])
                return report
    else:
        source = root
        frozen = json.loads((root / FROZEN).read_text())
        for relative in EDITABLE[:4]:
            path = root / relative
            if frozen.get("outputs_sha256", {}).get(str(path)) != ga.sha256_file(path):
                raise ValueError("Source selection/review does not match frozen audit hash")
        plan = {
            "request": request,
            "manifest_sha256": ga.sha256_file(manifest_path),
            "before_sha256": {str(p): ga.sha256_file(root / p) for p in EDITABLE},
        }
    outputs = revised_outputs(source, manifest, request)
    if not apply:
        return {
            "status": "selection_revision_preflight_passed",
            "writes": 0,
            "request": request,
            "archive": str(archive),
            "expected_counts": ga.SELECTED_COUNTS,
        }
    if not plan_path.exists():
        for relative, digest in plan["before_sha256"].items():
            destination = archive / "before" / relative
            ga.assert_output_path(destination, base)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
            if ga.sha256_file(destination) != digest:
                raise ValueError("Pre-revision backup verification failed")
        atomic_bytes(plan_path, json_bytes(plan))
    # An interrupted revision resumes from the immutable backup, never mixed live files.
    for relative, data in outputs.items():
        atomic_bytes(root / relative, data)
    ga.load_selection(
        root / REVIEW / "GrandAverageSelection_Final.json",
        root / REVIEW / "GrandAverageSelection_Final.csv",
        manifest,
    )
    fingerprints = {str(root / p): ga.sha256_file(root / p) for p in outputs}
    frozen = {
        "schema": ga.SELECTION_SCHEMA,
        "status": "final",
        "rows": 80,
        "observation_grades_unchanged": True,
        "outputs_sha256": fingerprints,
        "revision_request": request,
        "previous_frozen_audit": str(archive / "before" / FROZEN),
    }
    atomic_bytes(root / FROZEN, json_bytes(frozen))
    fingerprints[str(root / FROZEN)] = ga.sha256_file(root / FROZEN)
    report = {
        "status": "selection_revised_grand_average_pending",
        "schema": ga.SELECTION_SCHEMA,
        "request": request,
        "completed_utc": datetime.now(UTC).isoformat(),
        "archive": str(archive),
        "before_sha256": plan["before_sha256"],
        "outputs_sha256": fingerprints,
        "expected_counts": {str(n): counts for n, counts in ga.SELECTED_COUNTS.items()},
        "iaf_changed": False,
        "observations_reclassified": False,
        "grand_average_executed": False,
    }
    atomic_bytes(report_path, json_bytes(report))
    ga.assert_hashes(fingerprints)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--analysis", required=True, type=int, choices=ga.ANALYSES)
    parser.add_argument("--product", required=True, choices=ga.PRODUCTS)
    parser.add_argument("--pair", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--revision-key", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = revise_selection(
        ga.BASE,
        args.manifest,
        args.analysis,
        args.product,
        args.pair,
        args.reason,
        args.revision_key,
        args.apply,
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("outputs_sha256", "before_sha256")},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
