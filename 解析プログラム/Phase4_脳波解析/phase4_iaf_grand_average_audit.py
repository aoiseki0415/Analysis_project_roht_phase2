"""Read-only independent audit of saved No8–9 IAF Change grand-averages."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path

import pandas as pd
from PIL import Image

BASE = Path(
    "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/"
    "SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_本解析/Phase4_脳波解析"
)
FOLDERS = {
    8: "No8_PzSetwiseIAF",
    9: "No9_FzSetwiseIAF",
}
CHANNEL = {8: "Pz", 9: "Fz"}
PRODUCTS = ("CCube", "VRohtoPremium")
CONDITIONS = ("Eye Drop", "Control")
COHORTS = ("AllAvailable", "SelectedParticipants")
ADOPTION = "Grand-average採用（追加選別版）"
EXPECTED_SELECTED = {8: (12, 10), 9: (11, 10)}


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_value(expected, observed, name):
    if math.isnan(expected):
        assert math.isnan(observed), (name, expected, observed)
    else:
        assert math.isclose(expected, observed, rel_tol=1e-12, abs_tol=1e-12), (
            name,
            expected,
            observed,
        )


def latest_output_records(log_paths):
    """Resolve each file's latest successful writer, including scoped reruns.

    Older run hashes remain historical evidence, not current selection claims.
    The latest run must succeed; a failed run is never silently bypassed.
    """
    assert log_paths, "No grand-average run log"
    logs = [(p, json.loads(p.read_text())) for p in sorted(log_paths)]
    path, latest = logs[-1]
    assert latest["status"] == "complete", "Latest run is not complete"
    outputs = {}
    for source_path, run in logs:
        if run["status"] != "complete":
            continue
        for item in run["outputs"]:
            outputs[item["path"]] = {**item, "source_run_log": str(source_path)}
    return path, latest, outputs


def audit_current_layout():
    """Verify retirement, retained content and observations without changing them."""
    logs = BASE / FOLDERS[8] / "Sub/logs"
    migration = json.loads((logs / "IAFRenumbering_20261110.json").read_text())
    plan = json.loads((logs / "IAFRenumbering_Plan_20261110.json").read_text())
    archive = Path(migration["archive"])
    for relative, expected in plan["files"].items():
        if Path(relative).suffix != ".png":
            assert sha256(archive / relative) == expected
    assert not list(archive.rglob("*.png"))
    for name in ("No9_PzHalfSetIAF", "No10_FzSetwiseIAF", "No11_FzHalfSetIAF"):
        assert not (BASE / name).exists()
    cache_base = Path(
        "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/Phase4_脳波解析"
    )
    assert not (cache_base / "No8-11_PzFzIAF").exists()
    for relative, expected in migration["cache_sha256"].items():
        assert sha256(cache_base / "No8-9_PzFzIAF" / relative) == expected
    for path, expected in migration["retained_individual_png_sha256"].items():
        assert sha256(path) == expected
    for path, metadata in plan["protected_other_outputs"].items():
        stat = Path(path).stat()
        assert [stat.st_size, stat.st_mtime_ns] == metadata
    inventories = {}
    for number, name in FOLDERS.items():
        root = BASE / name
        counts = {
            "individual_png": len(list(root.glob("*/Individual/*.png"))),
            "grand_average_png": len(list(root.glob("*/GrandAverage/*.png"))),
            "review_png": len(list(root.glob("Sub/PeakClarityReview/*/*.png"))),
            "grand_average_csv": len(list(root.glob("Sub/tables/GrandAverage/*.csv"))),
        }
        assert counts == {
            "individual_png": 40,
            "grand_average_png": 4,
            "review_png": 40,
            "grand_average_csv": 3,
        }
        assert len(list(root.rglob("*.png"))) == 84
        inventories[str(number)] = counts
    current_review = BASE / FOLDERS[8] / "Sub/PeakClarityReview"
    old_review = archive / FOLDERS[8] / "Sub/PeakClarityReview"
    ignored = {
        "analysis_number",
        "review_status",
        ADOPTION,
        "採否確定状態",
        "利用者指定追加除外",
        "採否理由",
        "review_figure_path",
        "original_figure_path",
    }
    for name, expected_rows in (("ParticipantReview.csv", 80), ("IntervalReview.csv", 960)):
        before = pd.read_csv(old_review / name, dtype=str, keep_default_na=False)
        before = before.loc[before.analysis_number.isin(["8", "10"])].reset_index(drop=True)
        after = pd.read_csv(current_review / name, dtype=str, keep_default_na=False)
        assert len(after) == expected_rows
        fields = [name for name in before.columns if name not in ignored]
        pd.testing.assert_frame_equal(before[fields], after[fields], check_exact=True)
    return {
        "inventories": inventories,
        "retired_roots_absent": True,
        "historical_png_count": 0,
        "original_observation_rows_preserved": {"participant": 80, "interval": 960},
        "cache_files_byte_identical": len(migration["cache_sha256"]),
        "individual_png_byte_identical": len(migration["retained_individual_png_sha256"]),
        "other_output_files_metadata_unchanged": len(plan["protected_other_outputs"]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write aggregate audit JSON only to the fixed authorized No8 log path",
    )
    args = parser.parse_args()
    log_paths = sorted((BASE / FOLDERS[8] / "Sub/logs").glob("IAFGrandAverage_[0-9]*Z.json"))
    path, log, output_records = latest_output_records(log_paths)
    assert set(log["analyses"]).issubset(FOLDERS) and log["analyses"]
    assert log["psd_recomputed"] is False and log["iaf_reestimated"] is False
    for no in log["analyses"]:
        twin = BASE / FOLDERS[no] / "Sub/logs" / path.name
        assert json.loads(twin.read_text()) == log, "Two run records differ"
    for source, expected in log["protected_files_sha256"].items():
        assert sha256(source) == expected, "Protected file hash changed"
    for item in output_records.values():
        assert sha256(item["path"]) == item["sha256"], "Saved output hash changed"
    source_directory = Path(
        "/Users/aoiseki/GitHub/Analysis_project_roht_phase2/解析プログラム/Phase4_脳波解析"
    )
    for name, expected in log["script_sha256"].items():
        assert sha256(source_directory / name) == expected, "Run source-code hash changed"
    selection_path = BASE / FOLDERS[8] / "Sub/PeakClarityReview/GrandAverageSelection_Final.csv"
    selection = pd.read_csv(selection_path, dtype={"pair_id": str})
    counts = {"individual_change_rows": 0, "paired_inclusion_rows": 0, "group_rows": 0, "png": 0}
    results = []
    maximum_absolute_residual = 0.0
    for number, folder in FOLDERS.items():
        root = BASE / folder
        source = pd.read_csv(
            root / f"Sub/tables/No{number}_IAF_Estimates.csv",
            dtype={"session_id": str, "pair_id": str},
        )
        old_number = 8 if number == 8 else 10
        historical_root = (
            BASE
            / FOLDERS[8]
            / "Sub/history/BeforeRenumbering_20261110"
            / ("No8_PzSetwiseIAF" if number == 8 else "No10_FzSetwiseIAF")
        )
        previous_source = pd.read_csv(
            historical_root / f"Sub/tables/No{old_number}_IAF_Estimates.csv",
            dtype={"session_id": str, "pair_id": str},
        )
        previous_source["analysis_number"] = number
        pd.testing.assert_frame_equal(source, previous_source, check_exact=True)
        originals = source.set_index(["pair_id", "condition", "position"])
        assert originals.index.is_unique
        by_condition = source.pivot(
            index=["pair_id", "position"], columns="condition", values="frequency_hz"
        )
        k = 6
        pairs = sorted(source.pair_id.unique())
        selected_no = selection.loc[selection.analysis_number == number].set_index("pair_id")
        assert set(pairs) == set(selected_no.index)
        baseline = {
            (pair, cond): float(originals.loc[(pair, cond, 1), "frequency_hz"])
            for pair in pairs
            for cond in CONDITIONS
        }
        both_baselines = {
            pair: all(math.isfinite(baseline[(pair, cond)]) for cond in CONDITIONS)
            for pair in pairs
        }
        both_intervals = by_condition.notna().all(axis=1).to_dict()
        selected = selected_no[ADOPTION].eq("する").to_dict()
        for i, product in enumerate(PRODUCTS):
            selected_n = int(
                ((selected_no["product"] == product) & selected_no[ADOPTION].eq("する")).sum()
            )
            assert selected_n == EXPECTED_SELECTED[number][i]
        saved = root / "Sub/tables/GrandAverage"
        participant = pd.read_csv(
            saved / "ParticipantIAFChange.csv", dtype={"session_id": str, "pair_id": str}
        )
        assert len(participant) == len(source) == 80 * k
        assert not participant.duplicated(["pair_id", "condition", "position"]).any()
        for row in participant.itertuples(index=False):
            key = (row.pair_id, row.condition, row.position)
            src = originals.loc[key]
            expected = float(src.frequency_hz) - baseline[(row.pair_id, row.condition)]
            assert_value(expected, row.iaf_change_hz, "participant difference")
            assert_value(float(src.frequency_hz), row.saved_iaf_hz, "saved original IAF")
            assert_value(
                baseline[(row.pair_id, row.condition)], row.baseline_iaf_hz, "own baseline"
            )
            assert row.session_id == src.session_id and row.product == src["product"]
            assert row.source_quality == src.quality
            assert bool(row.both_baselines_finite) == both_baselines[row.pair_id]
            assert bool(row.both_interval_iaf_finite) == both_intervals[(row.pair_id, row.position)]
            paired = both_baselines[row.pair_id] and both_intervals[(row.pair_id, row.position)]
            assert bool(row.included_all_available) == paired
            assert bool(row.included_selected_participants) == (paired and selected[row.pair_id])
            assert bool(row.selected_participant) == selected[row.pair_id]
            if math.isfinite(expected):
                maximum_absolute_residual = max(
                    maximum_absolute_residual, abs(row.iaf_change_hz - expected)
                )
        counts["individual_change_rows"] += len(participant)
        inclusion = pd.read_csv(saved / "InclusionByInterval.csv", dtype={"pair_id": str}).fillna(
            ""
        )
        assert len(inclusion) == 40 * k * 2
        assert not inclusion.duplicated(["pair_id", "cohort", "position"]).any()
        for row in inclusion.itertuples(index=False):
            member = row.cohort == "AllAvailable" or selected[row.pair_id]
            baseline_ok = both_baselines[row.pair_id]
            interval_ok = both_intervals[(row.pair_id, row.position)]
            expected_reasons = []
            if not member:
                expected_reasons.append("not_in_final_selected_cohort")
            if not baseline_ok:
                expected_reasons.append("paired_baseline_missing")
            if not interval_ok:
                expected_reasons.append("paired_interval_missing")
            assert bool(row.included) == (member and baseline_ok and interval_ok)
            assert bool(row.cohort_member) == member
            assert row.exclusion_reason == ";".join(expected_reasons)
        counts["paired_inclusion_rows"] += len(inclusion)
        groups = pd.read_csv(saved / "GroupSummary.csv")
        previous_groups = pd.read_csv(historical_root / "Sub/tables/GrandAverage/GroupSummary.csv")
        previous_groups["analysis_number"] = number
        # AllAvailable numerical results must not change with selected-cohort edits.
        identity = ["product", "cohort", "condition", "position"]
        values_columns = identity + [
            "n",
            "mean_iaf_change_hz",
            "sd_iaf_change_hz",
            "sem_iaf_change_hz",
        ]
        pd.testing.assert_frame_equal(
            groups.loc[groups.cohort == "AllAvailable", values_columns]
            .sort_values(identity)
            .reset_index(drop=True),
            previous_groups.loc[previous_groups.cohort == "AllAvailable", values_columns]
            .sort_values(identity)
            .reset_index(drop=True),
            check_exact=True,
        )
        assert len(groups) == 2 * 2 * 2 * k
        assert not groups.duplicated(["product", "cohort", "condition", "position"]).any()
        for row in groups.itertuples(index=False):
            cohort_pairs = [
                pair
                for pair in pairs
                if selected_no.loc[pair, "product"] == row.product
                and both_baselines[pair]
                and both_intervals[(pair, row.position)]
                and (row.cohort == "AllAvailable" or selected[pair])
            ]
            values = [
                float(originals.loc[(pair, row.condition, row.position), "frequency_hz"])
                - baseline[(pair, row.condition)]
                for pair in cohort_pairs
            ]
            n = len(values)
            expected_mean = sum(values) / n if n else math.nan
            expected_sd = (
                math.sqrt(sum((x - expected_mean) ** 2 for x in values) / (n - 1))
                if n >= 2
                else math.nan
            )
            expected_sem = expected_sd / math.sqrt(n) if n >= 2 else math.nan
            assert row.n == n
            assert_value(expected_mean, row.mean_iaf_change_hz, "mean")
            assert_value(expected_sd, row.sd_iaf_change_hz, "sample SD")
            assert_value(expected_sem, row.sem_iaf_change_hz, "SEM")
            if row.position == 1 and n:
                assert row.mean_iaf_change_hz == 0.0
                assert n < 2 or row.sem_iaf_change_hz == 0.0
            membership = inclusion.loc[
                (inclusion["product"] == row.product)
                & (inclusion.cohort == row.cohort)
                & (inclusion.position == row.position)
                & inclusion.included,
                "pair_id",
            ]
            assert set(membership) == set(cohort_pairs)
        counts["group_rows"] += len(groups)
        ns = groups.pivot(index=["product", "cohort", "position"], columns="condition", values="n")
        assert ns["Eye Drop"].equals(ns["Control"])
        for product in PRODUCTS:
            output_audits = []
            for cohort in COHORTS:
                png = (
                    root
                    / product
                    / "GrandAverage"
                    / f"No{number}_{CHANNEL[number]}_IAFChange_{product}_{cohort}.png"
                )
                with Image.open(png) as img:
                    assert img.size == (1800, 1800)
                    img.verify()
                counts["png"] += 1
                output_audits.append(
                    output_records[str(png)]["render"]
                )
                assert output_audits[-1]["y_limits_hz"] == [-1.1, 1.1]
                assert output_audits[-1]["y_ticks_hz"] == [-1.0, -0.5, 0.0, 0.5, 1.0]
                gg = groups.loc[(groups["product"] == product) & (groups.cohort == cohort)]
                results.append(
                    {
                        "analysis_number": number,
                        "product": product,
                        "cohort": cohort,
                        "n_min": int(gg.n.min()),
                        "n_max": int(gg.n.max()),
                    }
                )
            assert output_audits[0]["y_limits_hz"] == output_audits[1]["y_limits_hz"]
            lower, upper = output_audits[0]["y_limits_hz"]
            assert lower == -1.1 and upper == 1.1
            assert output_audits[0]["y_ticks_hz"] == [-1.0, -0.5, 0.0, 0.5, 1.0]
    assert counts == {
        "individual_change_rows": 960,
        "paired_inclusion_rows": 960,
        "group_rows": 96,
        "png": 8,
    }
    report = {
        "status": "passed",
        "audit_method": (
            "independent pandas input join and Python sum/sample variance; "
            "no engine aggregation calls"
        ),
        "run_log": str(path),
        "run_log_sha256": sha256(path),
        "audit_script_sha256": sha256(__file__),
        "audit_git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True,
            cwd=Path(__file__).resolve().parents[2],
        ).strip(),
        "checked_counts": counts,
        "protected_source_files_checked": len(log["protected_files_sha256"]),
        "output_hashes_checked": len(output_records),
        "current_outputs_latest_writer": {
            name: record["source_run_log"] for name, record in output_records.items()
        },
        "run_source_code_hashes_checked": len(log["script_sha256"]),
        "maximum_absolute_participant_difference_residual_hz": maximum_absolute_residual,
        "source_differences_mean_sample_sd_sem_n_membership_baseline_zero": "all match",
        "source_data_changed_by_audit": False,
        "external_writes": 1 if args.write_report else 0,
        "pre_migration_individual_estimates_identical_except_number": True,
        "all_available_results_n_mean_sd_sem_identical_to_pre_migration": True,
        "current_layout_and_preservation": audit_current_layout(),
        "cohort_valid_n": results,
    }
    if args.write_report:
        run_tag = path.stem.removeprefix("IAFGrandAverage_")
        destination = (
            BASE / FOLDERS[8] / "Sub/logs"
            / f"IAFGrandAverage_IndependentAudit_{run_tag}.json"
        )
        assert destination.parent.is_dir(), "Authorized log directory missing"
        assert destination.parent.resolve().is_relative_to(BASE.resolve()), (
            "Output symlink escapes Phase4"
        )
        assert destination.resolve().parent == destination.parent.resolve(), (
            "Report destination symlink escapes log directory"
        )
        assert destination.name == f"IAFGrandAverage_IndependentAudit_{run_tag}.json"
        temporary = destination.with_name(destination.name + ".partial")
        assert not temporary.is_symlink(), "Temporary output must not be a symlink"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, destination)
        assert json.loads(destination.read_text(encoding="utf-8")) == report
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
