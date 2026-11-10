"""Read-only spectral review support; never re-estimate IAF or apply exclusions.

Creates separate audit sheets from saved, once-smoothed spectra. Human/Codex
qualitative judgments are entered separately; the program does not infer them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from phase4_iaf import (  # noqa: E402
    ANALYSES,
    DEFAULT_CACHE_ROOT,
    DEFAULT_OUTPUT_ROOT,
    FREQUENCIES,
    rows_from_cache,
    sha256_file,
)
from phase4_iaf_figures import require_arial  # noqa: E402

VERSION = "iaf-clarity-review-20261110-v2-setwise"
BASE = DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
CONDITIONS = ("Eye Drop", "Control")
PRODUCTS = ("CCube", "VRohtoPremium")
PRODUCT_LABELS = {"CCube": "Cキューブ", "VRohtoPremium": "Vロートプレミアム"}
GRADE_LABELS = {"C": "明瞭", "A": "判断保留", "U": "不明瞭", "M": "評価不能（PSD欠測）"}
OBSERVATIONS = ("両条件Cあり", "片条件Cあり", "両条件Cなし")
MISSING_PSD_REASONS = {
    "missing_set",
    "too_short",
    "all_windows_invalid",
    "missing_channel",
    "invalid_spectrum",
}


def label(row):
    return str(row["set_number"]) + (row["interval"] if row["interval"] != "whole" else "")


def make_sheet(rows, path, number, pair, product):
    if number not in ANALYSES:
        raise ValueError("Only current No8 (Pz) and No9 (Fz) are supported")
    count = 6
    nrow = count // 6 * 2
    fig, axes = plt.subplots(nrow, 6, figsize=(24, 3.5 * nrow), squeeze=False)
    for ci, condition in enumerate(CONDITIONS):
        rr = sorted([r for r in rows if r["condition"] == condition], key=lambda r: r["position"])
        if len(rr) != count:
            raise ValueError((pair, condition, len(rr)))
        for i, row in enumerate(rr):
            ax = axes[ci * (count // 6) + i // 6, i % 6]
            power = row["smoothed_mean_psd"]
            zoom = (FREQUENCIES >= 6) & (FREQUENCIES <= 17)
            ax.set_title(f"{condition} {label(row)}  IAF={row['frequency_hz']:.1f}", fontsize=12)
            if np.isfinite(power).all():
                ax.plot(FREQUENCIES[zoom], power[zoom], color="#333333", lw=1.5)
                ax.set_ylim(0, max(power[zoom].max() * 1.1, 1e-10))
                if np.isfinite(row["frequency_hz"]):
                    ax.plot(
                        row["frequency_hz"], row["selected_peak_psd"], "o", ms=4, color="#B12738"
                    )
                inset = ax.inset_axes([0.62, 0.64, 0.36, 0.30])
                broad = FREQUENCIES <= 30
                inset.plot(FREQUENCIES[broad], power[broad], color="#777777", lw=0.7)
                inset.set_xlim(1, 30)
                inset.set_ylim(0, max(power[broad].max() * 1.05, 1e-10))
                inset.set_xticks([1, 15, 30])
                inset.set_yticks([])
                inset.tick_params(labelsize=7, pad=1)
            else:
                ax.text(0.5, 0.5, row["quality"], ha="center", transform=ax.transAxes, fontsize=11)
            ax.axvline(8, color="#999999", ls=":", lw=1)
            ax.axvline(15, color="#999999", ls=":", lw=1)
            ax.set_xlim(6, 17)
            ax.set_xticks([6, 8, 10, 12, 15, 17])
            ax.tick_params(labelsize=10)
            ax.set_xlabel("Hz", fontsize=10)
            ax.set_ylabel("PSD (µV²/Hz)", fontsize=10)
    fig.suptitle(
        f"No{number} {ANALYSES[number][0]} | {pair} | {product}\n"
        "Saved MA5 PSD; independent y axes; dot = saved IAF, not clarity grade; inset 1–30 Hz",
        fontsize=16,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.9 if nrow == 2 else 0.94))
    fig.savefig(path, dpi=110)
    plt.close(fig)


def assert_no_final_selection(root):
    """Protect finalized manual decisions from provisional review overwrites."""
    if (Path(root) / "GrandAverageSelection_Final.json").exists():
        raise ValueError("Finalized selection exists; provisional review cannot overwrite it")


def prepare():
    # Refreshing evidence plots never reopens or overwrites finalized adoption.
    selection_root = BASE / ANALYSES[8][2] / "Sub/PeakClarityReview"
    protected_selection = {
        str(path): sha256_file(path)
        for path in (
            selection_root / "GrandAverageSelection_Final.json",
            selection_root / "GrandAverageSelection_Final.csv",
        )
        if path.exists()
    }
    require_arial()
    plt.rcParams["font.family"] = "Arial"
    manifest_path = BASE / ANALYSES[8][2] / "Sub/tables/ParticipantManifest.csv"
    manifest = pd.read_csv(manifest_path, dtype=str)
    if len(manifest) != 40:
        raise ValueError("Expected 40 pairs")
    paths = sorted(DEFAULT_CACHE_ROOT.glob("*.h5"))
    if len(paths) != 80:
        raise ValueError("Expected 80 current caches")
    all_rows = {number: [] for number in ANALYSES}
    sources = {str(path): sha256_file(path) for path in paths}
    for path in paths:
        for number, rows in rows_from_cache(path).items():
            all_rows[number].extend(rows)
    outputs = []
    for number, rows in all_rows.items():
        root = BASE / ANALYSES[number][2] / "Sub/PeakClarityReview"
        root.mkdir(parents=True, exist_ok=True)
        frame = pd.DataFrame(
            [{k: v for k, v in r.items() if not isinstance(v, np.ndarray)} for r in rows]
        )
        original = pd.read_csv(
            BASE / ANALYSES[number][2] / f"Sub/tables/No{number}_IAF_Estimates.csv"
        )
        keys = ["pair_id", "session_id", "condition", "product", "position"]
        for key in keys:
            frame[key] = frame[key].astype(str)
            original[key] = original[key].astype(str)
        merged = frame.merge(original, on=keys, suffixes=("_cache", "_csv"), validate="one_to_one")
        if len(merged) != len(frame) or not np.allclose(
            merged.frequency_hz_cache, merged.frequency_hz_csv, equal_nan=True
        ):
            raise ValueError("Saved IAF mismatch")
        frame.to_csv(root / "SavedEstimateInventory.csv", index=False, encoding="utf-8-sig")
        for pair in sorted(frame.pair_id.unique()):
            rr = [r for r in rows if r["pair_id"] == pair]
            product = rr[0]["product"]
            target = root / product
            target.mkdir(exist_ok=True)
            out = target / f"Pair{pair}_No{number}_AlphaReview.png"
            make_sheet(rr, out, number, pair, product)
            outputs.append(str(out))
    if any(sha256_file(Path(path)) != value for path, value in sources.items()):
        raise ValueError("Input cache changed")
    assert_hashes(protected_selection)
    record = {
        "version": VERSION,
        "time_utc": datetime.now(UTC).isoformat(),
        "input_sha256": sources,
        "manifest_sha256": sha256_file(manifest_path),
        "review_sheet_count": len(outputs),
        "outputs": outputs,
        "psd_reestimated": False,
        "iaf_reestimated": False,
        "exclusions_applied": False,
        "grand_average_executed": False,
        "cache_unchanged": True,
        "final_selection_unchanged_sha256": protected_selection,
    }
    log = BASE / ANALYSES[8][2] / "Sub/logs/PeakClarityReview_Preparation.json"
    log.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"review_sheet_count": len(outputs), "log": str(log)}))


def interval_labels(number):
    if number not in ANALYSES:
        raise ValueError("Only current No8 (Pz) and No9 (Fz) are supported")
    return [str(i) for i in range(1, 7)]


def read_manifest(path):
    """Validate correspondence, without interpreting the IDs as group labels."""
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = ["first_session_id", "second_session_id", "drops_session_id", "product"]
    if set(frame.columns) != set(required) or len(frame) != 40:
        raise ValueError(f"Manifest must contain 40 pairs and the four required columns: {path}")
    pairs = {}
    sessions = []
    for row in frame.to_dict("records"):
        first, second, drops = (row[k] for k in required[:3])
        if not all(re.fullmatch(r"[0-9]+", value) for value in (first, second, drops)):
            raise ValueError("Session IDs must be numeric strings")
        if first == second or drops not in (first, second) or row["product"] not in PRODUCTS:
            raise ValueError("Invalid manifest session/condition/product correspondence")
        pair = f"{first}-{second}"
        if pair in pairs:
            raise ValueError("Duplicate manifest pair")
        pairs[pair] = {**row, "Eye Drop": drops, "Control": second if drops == first else first}
        sessions.extend((first, second))
    if len(set(sessions)) != 80 or Counter(r["product"] for r in pairs.values()) != dict.fromkeys(
        PRODUCTS, 20
    ):
        raise ValueError("Manifest requires 80 unique sessions and 20 pairs per product")
    return pairs


def load_assessments(paths):
    if len(paths) != 2 or len(set(map(str, paths))) != 2:
        raise ValueError("Provide two distinct assessment JSON files for current No8/9")
    assessments = {}
    for path in paths:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(entries, list) or len(entries) != 40:
            raise ValueError(f"Assessment JSON must contain 40 pairs: {path}")
        numbers = {entry.get("analysis_number") for entry in entries}
        if len(numbers) != 1 or next(iter(numbers)) not in ANALYSES:
            raise ValueError("Each JSON must describe exactly one of No8–9")
        number = next(iter(numbers))
        if number in assessments:
            raise ValueError("Duplicate analysis number in assessment files")
        by_pair = {}
        for entry in entries:
            pair = entry.get("pair_id")
            if (
                not isinstance(pair, str)
                or not re.fullmatch(r"[0-9]+-[0-9]+", pair)
                or pair in by_pair
            ):
                raise ValueError("Invalid or duplicate assessment pair")
            conditions = entry.get("conditions", {})
            if set(conditions) != set(CONDITIONS):
                raise ValueError("Assessment must contain exactly Eye Drop and Control")
            for condition, judgment in conditions.items():
                grades = judgment.get("grades", "")
                if (
                    not isinstance(grades, str)
                    or len(grades) != len(interval_labels(number))
                    or set(grades) - set(GRADE_LABELS)
                ):
                    raise ValueError(f"Invalid grade sequence: No{number} {pair} {condition}")
                if not isinstance(judgment.get("note"), str) or not judgment["note"].strip():
                    raise ValueError("Every condition requires a review note")
            by_pair[pair] = entry
        assessments[number] = by_pair
    if set(assessments) != set(ANALYSES):
        raise ValueError("All of No8–9 are required")
    return assessments


def validated_inventory(path, number, manifest):
    """Check saved PSD-availability metadata separately from finite IAF."""
    frame = pd.read_csv(path, dtype={"pair_id": str, "session_id": str})
    required = {
        "pair_id",
        "session_id",
        "condition",
        "product",
        "analysis_number",
        "channel",
        "set_number",
        "interval",
        "position",
        "frequency_hz",
        "quality",
        "n_valid_segments",
        "n_possible_segments",
        "ica_channel_excluded",
        "smoothing_points",
        "smoothing_passes",
        "peak_input_dataset",
    }
    if not required <= set(frame.columns):
        raise ValueError(f"Inventory columns missing: {required - set(frame.columns)}")
    labels = interval_labels(number)
    if len(frame) != 40 * 2 * len(labels) or set(frame.pair_id) != set(manifest):
        raise ValueError("Inventory pair/row coverage mismatch")
    if frame.duplicated(["pair_id", "condition", "position"]).any():
        raise ValueError("Duplicate inventory interval")
    if (
        not frame.analysis_number.eq(number).all()
        or not frame.channel.eq(ANALYSES[number][0]).all()
    ):
        raise ValueError("Inventory analysis/channel mismatch")
    if not (
        frame.smoothing_points.eq(5)
        & frame.smoothing_passes.eq(1)
        & frame.peak_input_dataset.eq("smoothed_mean_psd_uv2_hz")
    ).all():
        raise ValueError("Inventory is not the current once-smoothed PSD version")
    if set(frame.condition) != set(CONDITIONS):
        raise ValueError("Inventory condition labels mismatch")
    for row in frame.to_dict("records"):
        mapping = manifest[row["pair_id"]]
        if row["session_id"] != mapping[row["condition"]] or row["product"] != mapping["product"]:
            raise ValueError("Inventory condition/ID/product mismatch")
        position = row["position"]
        if (
            not np.isfinite(position)
            or int(position) != position
            or not 1 <= position <= len(labels)
        ):
            raise ValueError("Invalid inventory position")
        if label(row) != labels[int(position) - 1]:
            raise ValueError("Inventory Set/half/position mismatch")
        valid, possible = row["n_valid_segments"], row["n_possible_segments"]
        if not (
            np.isfinite(valid)
            and np.isfinite(possible)
            and int(valid) == valid
            and int(possible) == possible
            and 0 <= valid <= possible
        ):
            raise ValueError("Invalid PSD window counts")
        missing = row["quality"] in MISSING_PSD_REASONS
        if missing != (valid == 0):
            raise ValueError("PSD missing reason contradicts valid-window count")
        finite = bool(np.isfinite(row["frequency_hz"]))
        if row["quality"] not in MISSING_PSD_REASONS | {"ok", "no_local_peak"}:
            raise ValueError("Unrecognized saved missing/quality reason")
        if finite != (row["quality"] == "ok") or (finite and not 8 <= row["frequency_hz"] <= 15):
            raise ValueError("Saved IAF availability contradicts quality/range")
    for _, group in frame.groupby(["pair_id", "condition"]):
        if sorted(group.position) != list(range(1, len(labels) + 1)):
            raise ValueError("Inventory is missing expected interval positions")
    return frame


def build_review_tables(assessments, inventories, manifest, base):
    participants, intervals = [], []
    for number in sorted(ANALYSES):
        if set(assessments[number]) != set(manifest):
            raise ValueError(f"Assessment pair coverage mismatch in No{number}")
        frame = inventories[number]
        labels = interval_labels(number)
        for pair in sorted(manifest):
            mapping = manifest[pair]
            entry = assessments[number][pair]
            # Optional provenance fields are checked if provided, never silently trusted.
            if "product" in entry and entry["product"] != mapping["product"]:
                raise ValueError("Assessment product mismatch")
            result = {
                "analysis_number": number,
                "channel": ANALYSES[number][0],
                "product": mapping["product"],
                "pair_id": pair,
                "eye_drop_session_id": mapping["Eye Drop"],
                "control_session_id": mapping["Control"],
                "baseline_interval": labels[0],
                "review_status": "暫定定性評価・採否未確定",
            }
            finite_by_condition = {}
            for condition, prefix in (("Eye Drop", "eye_drop"), ("Control", "control")):
                judgment = entry["conditions"][condition]
                if "session_id" in judgment and str(judgment["session_id"]) != mapping[condition]:
                    raise ValueError("Assessment condition/session ID mismatch")
                selected = frame.loc[
                    (frame.pair_id == pair) & (frame.condition == condition)
                ].sort_values("position")
                grades = judgment["grades"]
                finite = np.isfinite(selected.frequency_hz.to_numpy())
                finite_by_condition[condition] = finite
                result[f"{prefix}_grades"] = grades
                result[f"{prefix}_note"] = judgment["note"].strip()
                result[f"{prefix}_has_clear_interval"] = "C" in grades
                result[f"{prefix}_baseline_iaf_hz"] = float(selected.iloc[0].frequency_hz)
                result[f"{prefix}_baseline_finite"] = bool(finite[0])
                for grade in GRADE_LABELS:
                    result[f"{prefix}_{grade}_intervals"] = ";".join(
                        lab for lab, g in zip(labels, grades, strict=True) if g == grade
                    )
                    result[f"{prefix}_{grade}_count"] = grades.count(grade)
                for row, lab, grade, available in zip(
                    selected.to_dict("records"), labels, grades, finite, strict=True
                ):
                    missing = row["quality"] in MISSING_PSD_REASONS
                    if (grade == "M") != missing:
                        raise ValueError(
                            "Grade M/PSD missing-reason mismatch: "
                            f"No{number} {pair} {condition} {lab}"
                        )
                    intervals.append(
                        {
                            **row,
                            "interval_label": lab,
                            "clarity_grade": grade,
                            "clarity_label": GRADE_LABELS[grade],
                            "psd_available": not missing,
                            "iaf_finite": bool(available),
                            "condition_note": judgment["note"].strip(),
                            "review_status": "暫定定性評価・採否未確定",
                        }
                    )
            c_count = int(result["eye_drop_has_clear_interval"]) + int(
                result["control_has_clear_interval"]
            )
            result["observation_class"] = OBSERVATIONS[2 - c_count]
            result["contains_ambiguous_interval"] = (
                result["eye_drop_A_count"] + result["control_A_count"] > 0
            )
            result["contains_missing_psd_interval"] = (
                result["eye_drop_M_count"] + result["control_M_count"] > 0
            )
            result["both_baselines_finite"] = (
                result["eye_drop_baseline_finite"] and result["control_baseline_finite"]
            )
            paired = finite_by_condition["Eye Drop"] & finite_by_condition["Control"]
            result["paired_finite_interval_count"] = int(paired.sum())
            result["paired_finite_intervals"] = ";".join(
                lab for lab, ok in zip(labels, paired, strict=True) if ok
            )
            result["baseline_valid_paired_interval_count"] = (
                int(paired.sum()) if result["both_baselines_finite"] else 0
            )
            root = base / ANALYSES[number][2]
            result["review_figure_path"] = str(
                root
                / "Sub/PeakClarityReview"
                / mapping["product"]
                / f"Pair{pair}_No{number}_AlphaReview.png"
            )
            tag = "SetwiseIAF"
            result["original_figure_path"] = str(
                root
                / mapping["product"]
                / "Individual"
                / f"Pair{pair}_No{number}_{ANALYSES[number][0]}_{tag}_ThreePanel.png"
            )
            participants.append(result)
    participant_frame = pd.DataFrame(participants)
    interval_frame = pd.DataFrame(intervals)
    summaries = []
    for number in sorted(ANALYSES):
        for product in PRODUCTS:
            group = participant_frame.loc[
                (participant_frame.analysis_number == number)
                & (participant_frame["product"] == product)
            ]
            segment = interval_frame.loc[
                (interval_frame.analysis_number == number) & (interval_frame["product"] == product)
            ]
            summary = {
                "analysis_number": number,
                "channel": ANALYSES[number][0],
                "product": product,
                "participant_pair_count": len(group),
                "scheduled_interval_condition_count": len(segment),
                "both_conditions_C": int(group.observation_class.eq(OBSERVATIONS[0]).sum()),
                "one_condition_C": int(group.observation_class.eq(OBSERVATIONS[1]).sum()),
                "neither_condition_C": int(group.observation_class.eq(OBSERVATIONS[2]).sum()),
                "pairs_with_A": int(group.contains_ambiguous_interval.sum()),
                "pairs_with_M": int(group.contains_missing_psd_interval.sum()),
                "both_baselines_finite_pairs": int(group.both_baselines_finite.sum()),
                "baseline_unavailable_pairs": int((~group.both_baselines_finite).sum()),
                "selection_finalized": False,
                "grand_average_executed": False,
            }
            for condition, prefix in (("Eye Drop", "eye_drop"), ("Control", "control")):
                selected = segment.loc[segment.condition == condition]
                for grade in GRADE_LABELS:
                    summary[f"{prefix}_{grade}_interval_count"] = int(
                        selected.clarity_grade.eq(grade).sum()
                    )
            summaries.append(summary)
    if (len(participant_frame), len(interval_frame), len(summaries)) != (80, 960, 4):
        raise ValueError("Final report row counts must be 80/960/4")
    return participant_frame, interval_frame, pd.DataFrame(summaries)


def _md(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(participants, summaries, report_root):
    lines = [
        "# No8–9 IAFピーク明瞭性レビュー",
        "",
        "## 位置づけ",
        "",
        "保存済みの周波数方向5点・1回平滑化PSDをNo別・製品群別・条件別に確認した、Codexの暫定的な定性評価です。"
        "IAFの再推定、既存値の置換、被験者除外、Grand-averageの計算・描画は行っていません。採否は未確定です。",
        "",
        "全80の区間別拡大評価図を確認しました（各図の6区間すべて）。"
        "元の3パネルPNGは必要例を併読し、全80元PNGを別途全数目視した意味ではありません。"
        "評価者間信頼性は未測定です。",
        "",
        "- C：周囲背景と分かれた一つの明瞭なalphaの山を識別できる。小振幅だけでは不明瞭にしない。",
        "- A：候補はあるが同程度多峰、肩、帯域端、広帯域の櫛状などで代表峰が曖昧（判断保留）。",
        "- U：確認可能なPSDに明瞭な山が見当たらない。M：PSDがなく評価不能。"
        "Mは不明瞭の証拠ではない。",
        "- 少なくとも1区間Cなら、その条件は『明瞭区間あり』。全区間Cは要求しない。",
        "- 『両条件Cあり／片条件Cあり／両条件Cなし』は観察分類であり採用集合ではない。"
        "CなしでもAやMがあれば全区間Uとは断定できない。",
        "- 基準IAFの有限性と明瞭性は別。No8（Pz）・No9（Fz）ともSet 1全体を基準とする。"
        "基準の明瞭さは必須基準にしていない。",
        "- 片条件のみ明瞭なペアの最終採否は未確定。後続欠測は将来の群集計でその区間だけpaired OR、"
        "片条件の基準欠測は当該Noの差分群集計全体で利用不能。",
        "- 既存IAFの印と条件ラベルが見える非盲検の探索的評価であり、"
        "生理的alpha・ノイズ原因・薬効を証明しない。",
        "",
        "## 集計",
        "",
        "| No | 製品 | ペア | 両条件C | 片条件C | 両条件Cなし |"
        " Aを含むペア | Mを含むペア | 両基準有限 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in summaries.to_dict("records"):
        lines.append(
            f"| No{r['analysis_number']} | {PRODUCT_LABELS[r['product']]} | "
            f"{r['participant_pair_count']} | {r['both_conditions_C']} | "
            f"{r['one_condition_C']} | {r['neither_condition_C']} | "
            f"{r['pairs_with_A']} | {r['pairs_with_M']} | {r['both_baselines_finite_pairs']} |"
        )
    lines += [
        "",
        "詳細な各区間の保存IAF、欠測理由、window数、ICAフラグは "
        "[IntervalReview.csv](IntervalReview.csv)、ペア別属性は "
        "[ParticipantReview.csv](ParticipantReview.csv)、集計は "
        "[GroupSummary.csv](GroupSummary.csv) を参照。",
        "",
    ]
    for number in sorted(ANALYSES):
        lines += [
            f"## No{number}：{ANALYSES[number][0]}・"
            "Set全体",
            "",
            "gradeの並び："
            + ", ".join(interval_labels(number))
            + "。基準IAFはHz。『有限区間』は両条件の保存IAFが有限な区間数で、"
            "採用人数ではありません。",
            "",
        ]
        for product in PRODUCTS:
            lines += [
                f"### {PRODUCT_LABELS[product]}",
                "",
                "| ペア・確認図 | Eye Drop：C区間／grades／理由 | Control：C区間／grades／理由 |"
                " 観察分類 | 基準IAF Eye Drop / Control | 両基準有限 | 両条件有限区間 |",
                "|---|---|---|---|---|---|---|",
            ]
            selected = participants.loc[
                (participants.analysis_number == number) & (participants["product"] == product)
            ]
            for r in selected.to_dict("records"):
                relative = os.path.relpath(r["review_figure_path"], report_root)
                original = os.path.relpath(r["original_figure_path"], report_root)
                descriptions = []
                for prefix in ("eye_drop", "control"):
                    c_intervals = r[f"{prefix}_C_intervals"] or "なし"
                    descriptions.append(
                        f"C={c_intervals}<br>{r[f'{prefix}_grades']}<br>{_md(r[f'{prefix}_note'])}"
                    )
                baseline = " / ".join(
                    f"{r[f'{p}_baseline_iaf_hz']:.1f}" if r[f"{p}_baseline_finite"] else "欠測"
                    for p in ("eye_drop", "control")
                )
                lines.append(
                    f"| [{r['pair_id']}](<{relative}>)・[元図](<{original}>) | "
                    f"{descriptions[0]} | {descriptions[1]} | {r['observation_class']} | "
                    f"{baseline} | {'はい' if r['both_baselines_finite'] else 'いいえ'} | "
                    f"{r['paired_finite_interval_count']}/{len(interval_labels(number))} |"
                )
            lines.append("")
    lines += [
        "## 次の判断",
        "",
        "利用者の確認後に追加対象版の採否を確定します。全利用可能データ版は維持する計画です。今回の分類で既存値をNaN化したり、明瞭な別峰へ差し替えたりしていません。",
        "",
    ]
    return "\n".join(lines)


def assert_hashes(expected):
    for filename, digest in expected.items():
        path = Path(filename)
        if not path.is_file() or sha256_file(path) != digest:
            raise ValueError(f"Source SHA mismatch: {path}")


def finalize(paths, *, base=BASE, cache_root=DEFAULT_CACHE_ROOT):
    """Finalize review records only. Optional roots exist for isolated synthetic tests."""
    base, cache_root = Path(base), Path(cache_root)
    root = base / ANALYSES[8][2] / "Sub/PeakClarityReview"
    assert_no_final_selection(root)
    log_root = base / ANALYSES[8][2] / "Sub/logs"
    preparation_path = log_root / "PeakClarityReview_Preparation.json"
    preparation = json.loads(preparation_path.read_text(encoding="utf-8"))
    cache_hashes = preparation["input_sha256"]
    cache_paths = {str(path) for path in cache_root.glob("*.h5")}
    if (
        len(cache_hashes) != 80
        or set(cache_hashes) != cache_paths
        or not preparation.get("cache_unchanged")
    ):
        raise ValueError("Preparation must provide the exact 80 unchanged cache hashes")
    assert_hashes(cache_hashes)
    protected = {preparation_path, *map(Path, paths)}
    inventories, manifests = {}, {}
    for number in sorted(ANALYSES):
        analysis_root = base / ANALYSES[number][2]
        manifest_path = analysis_root / "Sub/tables/ParticipantManifest.csv"
        inventory_path = analysis_root / "Sub/PeakClarityReview/SavedEstimateInventory.csv"
        manifests[number] = read_manifest(manifest_path)
        inventories[number] = validated_inventory(inventory_path, number, manifests[number])
        original_path = analysis_root / f"Sub/tables/No{number}_IAF_Estimates.csv"
        original = validated_inventory(original_path, number, manifests[number])
        keys = ["pair_id", "condition", "position"]
        columns = sorted(set(original.columns) & set(inventories[number].columns))
        try:
            pd.testing.assert_frame_equal(
                original.sort_values(keys)[columns].reset_index(drop=True),
                inventories[number].sort_values(keys)[columns].reset_index(drop=True),
                check_exact=True,
            )
        except AssertionError as error:
            raise ValueError("Saved estimate table changed since review preparation") from error
        protected.update(
            (
                manifest_path,
                inventory_path,
                analysis_root / f"Sub/tables/No{number}_IAF_Estimates.csv",
            )
        )
        originals = list(analysis_root.glob("*/Individual/*.png"))
        if len(originals) != 40:
            raise ValueError("Expected 40 existing participant PNGs per analysis")
        protected.update(originals)
    manifest = manifests[8]
    if any(value != manifest for value in manifests.values()):
        raise ValueError("Manifest correspondence differs between No8–9")
    if (
        sha256_file(base / ANALYSES[8][2] / "Sub/tables/ParticipantManifest.csv")
        != preparation["manifest_sha256"]
    ):
        raise ValueError("Manifest changed since review preparation")
    assessments = load_assessments(paths)
    participants, intervals, summaries = build_review_tables(
        assessments, inventories, manifest, base
    )
    review_paths = set(participants.review_figure_path)
    if preparation.get("review_sheet_count") != 80 or review_paths != set(preparation["outputs"]):
        raise ValueError("Prepared review sheet coverage mismatch")
    protected.update(map(Path, review_paths))
    if not all(Path(path).is_file() for path in participants.original_figure_path):
        raise ValueError("Expected participant figure path is missing")
    # Strict lookup prevents writing metadata that points to nonexistent evidence.
    source_hashes = {str(path): sha256_file(path) for path in sorted(protected)}
    markdown = render_report(participants, summaries, root)
    merged_assessments = [
        assessments[n][pair] for n in sorted(ANALYSES) for pair in sorted(manifest)
    ]
    root.mkdir(parents=True, exist_ok=True)
    outputs = []
    for filename, frame in (
        ("ParticipantReview.csv", participants),
        ("IntervalReview.csv", intervals),
        ("GroupSummary.csv", summaries),
    ):
        output = root / filename
        frame.to_csv(output, index=False, encoding="utf-8-sig")
        if len(pd.read_csv(output)) != len(frame):
            raise ValueError("Report CSV readback row count mismatch")
        outputs.append(output)
    report_path = root / "PeakClarityReview.md"
    report_path.write_text(markdown, encoding="utf-8")
    assessment_path = root / "AssessmentInput.json"
    assessment_path.write_text(
        json.dumps(merged_assessments, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    outputs.extend((report_path, assessment_path))
    assert_hashes(cache_hashes)
    assert_hashes(source_hashes)
    record = {
        "version": VERSION,
        "time_utc": datetime.now(UTC).isoformat(),
        "participant_review_rows": len(participants),
        "interval_review_rows": len(intervals),
        "group_summary_rows": len(summaries),
        "assessment_input_count": len(merged_assessments),
        "input_cache_sha256": cache_hashes,
        "source_file_sha256": source_hashes,
        "output_sha256": {str(path): sha256_file(path) for path in outputs},
        "cache_unchanged_from_preparation_and_during_finalization": True,
        "existing_png_tables_and_assessment_sources_unchanged_during_finalization": True,
        "psd_reestimated": False,
        "iaf_reestimated": False,
        "exclusions_applied": False,
        "grand_average_executed": False,
        "selection_finalized": False,
        "review_status": "暫定定性評価・観察分類のみ・採否未確定",
        "source_protection_scope": (
            "cacheはprepare時からSHA一致。既存個人PNG・数値表・確認図・入力判定はfinalize前後SHA一致。"
            "cloud同期は独立未検証。"
        ),
    }
    log_root.mkdir(parents=True, exist_ok=True)
    log_path = log_root / "PeakClarityReview_Finalization.json"
    log_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--finalize", nargs=2, type=Path, metavar="ASSESSMENT_JSON")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        record = finalize(args.finalize)
        print(
            json.dumps(
                {
                    key: record[key]
                    for key in (
                        "participant_review_rows",
                        "interval_review_rows",
                        "group_summary_rows",
                        "grand_average_executed",
                    )
                }
            )
        )


if __name__ == "__main__":
    main()
