#!/usr/bin/env python3
"""Phase 2 No2: count paired mistouch events and plot set-wise summaries."""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COMMON_DIR = Path(__file__).resolve().parents[1]
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from paired_statistics import (  # noqa: E402
    add_significance_bracket,
    adjusted_p_values,
    paired_t_statistics,
    quantification_axis_layout,
    significance_label,
)

HERE = Path(__file__).resolve().parent
NO1_PATH = HERE / "Phase2_No1_ReactionTime.py"
SPEC = importlib.util.spec_from_file_location("phase2_no1_shared", NO1_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load shared Phase2 module: {NO1_PATH}")
no1 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = no1
SPEC.loader.exec_module(no1)

N_SETS = 6
CONTROL_COLOR = "#402B5D"
PRODUCTS = {
    "CCube": ("C Cube", "#5F7890"),
    "VRohtoPremium": ("V Rohto Premium", "#708B6A"),
}
BAR_CENTERS = np.array([-0.32, 0.32])
BAR_WIDTH = 0.42
DOT_SIZE = 150.0
JITTER_HALF_WIDTH = 0.055
X_LIMITS = (-0.90, 0.90)
SENSITIVITY_PAIR_ID = "132-232"
SENSITIVITY_SET = 1


@dataclass
class SetCount:
    set_number: int
    raw_mistouch_rows: int
    mistouch_count: float
    consecutive_links_50ms: int
    correct_bridge_links_100ms: int
    missing_keypress_rows: int
    time_reversal_links: int
    source_note: str
    eeg_missing: bool


def _read_raw(path: Path, set_number: int) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {"ResponseType", "KeyPress(ms)", "TiltOnset(ms)", "Block"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    block = pd.to_numeric(frame["Block"], errors="coerce")
    frame = frame.loc[block == set_number].copy().reset_index(drop=True)
    frame["ResponseType_norm"] = frame["ResponseType"].astype(str).str.strip().str.lower()
    frame["KeyPress_num"] = pd.to_numeric(frame["KeyPress(ms)"], errors="coerce")
    frame["TiltOnset_num"] = pd.to_numeric(frame["TiltOnset(ms)"], errors="coerce")
    frame["Correct_RT_ms"] = frame["KeyPress_num"] - frame["TiltOnset_num"]
    return frame


def select_raw_set(session_dir: Path, set_number: int) -> tuple[pd.DataFrame, str]:
    """Use the same completed-file choice as No1, while retaining mistouch rows."""

    selected_stimulus, note = no1._select_set(session_dir, set_number)
    selected_sources = [Path(value) for value in selected_stimulus["source_file"].unique()]
    if len(selected_sources) == 1:
        return _read_raw(selected_sources[0], set_number), note
    raise ValueError(
        f"ID{session_dir.name} Set{set_number}: reconstructed stimulus trials span "
        "multiple files, so mistouch chronology cannot be reconstructed safely"
    )


def count_mistouch_events(frame: pd.DataFrame) -> dict[str, int]:
    """Count mistouches using the fixed 50-ms and correct-bridge 100-ms rules."""

    types = frame["ResponseType_norm"].to_numpy(dtype=object)
    times = frame["KeyPress_num"].to_numpy(dtype=float)
    correct_rt = frame["Correct_RT_ms"].to_numpy(dtype=float)
    mistouch_positions = np.flatnonzero(types == "mistouch")
    raw_count = int(mistouch_positions.size)
    missing = int(np.isnan(times[mistouch_positions]).sum())
    finite_adjacent = np.isfinite(times[:-1]) & np.isfinite(times[1:])
    time_reversals = int(np.sum((np.diff(times) < 0.0) & finite_adjacent))
    assigned: set[int] = set()
    event_count = 0
    consecutive_links = 0
    bridge_links = 0

    for start in mistouch_positions:
        start = int(start)
        if start in assigned:
            continue
        event_count += 1
        assigned.add(start)
        current = start
        while True:
            if current + 1 < len(frame) and types[current + 1] == "mistouch":
                gap = times[current + 1] - times[current]
                if np.isfinite(gap) and 0.0 <= gap <= 50.0:
                    current += 1
                    assigned.add(current)
                    consecutive_links += 1
                    continue
            if (
                current + 2 < len(frame)
                and types[current + 1] == "correct"
                and types[current + 2] == "mistouch"
            ):
                gap = times[current + 2] - times[current]
                rt = correct_rt[current + 1]
                if np.isfinite(gap) and 0.0 <= gap <= 100.0 and np.isfinite(rt) and rt <= 50.0:
                    current += 2
                    assigned.add(current)
                    bridge_links += 1
                    continue
            break
    return {
        "raw_mistouch_rows": raw_count,
        "mistouch_count": event_count,
        "consecutive_links_50ms": consecutive_links,
        "correct_bridge_links_100ms": bridge_links,
        "missing_keypress_rows": missing,
        "time_reversal_links": time_reversals,
    }


def process_session(raw_root: Path, session_id: str) -> list[SetCount]:
    session_dir = raw_root / session_id
    if not session_dir.is_dir():
        raise FileNotFoundError(f"Behavior directory not found: {session_dir}")
    missing_set = no1.EEG_MISSING_SET_BY_SESSION.get(session_id)
    results: list[SetCount] = []
    for set_number in range(1, N_SETS + 1):
        frame, note = select_raw_set(session_dir, set_number)
        counted = count_mistouch_events(frame)
        results.append(
            SetCount(
                set_number=set_number,
                raw_mistouch_rows=counted["raw_mistouch_rows"],
                mistouch_count=float(counted["mistouch_count"]),
                consecutive_links_50ms=counted["consecutive_links_50ms"],
                correct_bridge_links_100ms=counted["correct_bridge_links_100ms"],
                missing_keypress_rows=counted["missing_keypress_rows"],
                time_reversal_links=counted["time_reversal_links"],
                source_note=note,
                eeg_missing=missing_set == set_number,
            )
        )
    return results


def analyse_participant(raw_root: Path, participant: object) -> list[dict[str, object]]:
    drops = process_session(raw_root, participant.drops_session_id)
    control = process_session(raw_root, participant.control_session_id)
    pairwise_missing = {item.set_number for item in drops + control if item.eeg_missing}
    if len(pairwise_missing) > 1:
        raise ValueError(f"ID{participant.pair_id}: multiple EEG-missing sets")
    missing_set = next(iter(pairwise_missing), None)
    product_dir = no1.normalize_product(participant.product)[0]
    rows: list[dict[str, object]] = []
    for drops_set, control_set in zip(drops, control, strict=True):
        masked = drops_set.set_number == missing_set
        rows.append(
            {
                "Product": product_dir,
                "Pair_ID": participant.pair_id,
                "First_session_ID": participant.first_session_id,
                "Second_session_ID": participant.second_session_id,
                "EyeDrop_session_ID": participant.drops_session_id,
                "Control_session_ID": participant.control_session_id,
                "EyeDrop_visit": participant.eye_drops_visit,
                "Set": drops_set.set_number,
                "EyeDrop_mistouch_count": np.nan if masked else drops_set.mistouch_count,
                "Control_mistouch_count": np.nan if masked else control_set.mistouch_count,
                "EyeDrop_raw_rows": drops_set.raw_mistouch_rows,
                "Control_raw_rows": control_set.raw_mistouch_rows,
                "EyeDrop_50ms_links": drops_set.consecutive_links_50ms,
                "Control_50ms_links": control_set.consecutive_links_50ms,
                "EyeDrop_100ms_correct_bridge_links": drops_set.correct_bridge_links_100ms,
                "Control_100ms_correct_bridge_links": control_set.correct_bridge_links_100ms,
                "EyeDrop_missing_keypress_rows": drops_set.missing_keypress_rows,
                "Control_missing_keypress_rows": control_set.missing_keypress_rows,
                "EyeDrop_time_reversal_links": drops_set.time_reversal_links,
                "Control_time_reversal_links": control_set.time_reversal_links,
                "Pairwise_EEG_missing_set": f"Set{missing_set}" if missing_set else "なし",
                "EyeDrop_source": drops_set.source_note,
                "Control_source": control_set.source_note,
            }
        )
    return rows


def build_summary(values: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for product in sorted(values["Product"].unique()):
        for set_number in range(1, N_SETS + 1):
            selected = values.loc[(values["Product"] == product) & (values["Set"] == set_number)]
            drops = selected["EyeDrop_mistouch_count"].to_numpy(float)
            control = selected["Control_mistouch_count"].to_numpy(float)
            paired = np.isfinite(drops) & np.isfinite(control)
            n = int(paired.sum())
            rows.append(
                {
                    "Product": product,
                    "Set": set_number,
                    "EyeDrop_mean_count": float(np.mean(drops[paired])),
                    "EyeDrop_SD_count": float(np.std(drops[paired], ddof=1)) if n > 1 else np.nan,
                    "Control_mean_count": float(np.mean(control[paired])),
                    "Control_SD_count": float(np.std(control[paired], ddof=1)) if n > 1 else np.nan,
                    "Paired_N": n,
                    "Mean_paired_difference_EyeDrop_minus_Control": float(
                        np.mean(drops[paired] - control[paired])
                    ),
                    "Statistics": "Not performed",
                }
            )
    return pd.DataFrame(rows)


def build_ccube_sensitivity_values(values: pd.DataFrame) -> pd.DataFrame:
    """Mask both conditions for ID132-232 Set 1 without changing main results."""

    sensitivity = values.copy()
    target = (
        sensitivity["Product"].eq("CCube")
        & sensitivity["Pair_ID"].eq(SENSITIVITY_PAIR_ID)
        & sensitivity["Set"].eq(SENSITIVITY_SET)
    )
    if int(target.sum()) != 1:
        raise ValueError(
            f"Sensitivity target ID132-232 Set 1 must occur exactly once; found {int(target.sum())}"
        )
    sensitivity.loc[target, ["EyeDrop_mistouch_count", "Control_mistouch_count"]] = np.nan
    return sensitivity


def _axis_layout(values: np.ndarray) -> tuple[float, np.ndarray, float, float, float, float]:
    return quantification_axis_layout(values, minimum_upper=5.0, integer_ticks=True)


def build_setwise_paired_statistics(values: pd.DataFrame, product: str) -> pd.DataFrame:
    """Run six paired t-tests and retain raw plus three adjusted p-values."""

    rows: list[dict[str, object]] = []
    for set_number in range(1, N_SETS + 1):
        selected = values.loc[(values["Product"] == product) & (values["Set"] == set_number)]
        row = {"Product": product, "Set": set_number}
        row.update(
            paired_t_statistics(
                selected["EyeDrop_mistouch_count"].to_numpy(float),
                selected["Control_mistouch_count"].to_numpy(float),
            )
        )
        rows.append(row)
    statistics = pd.DataFrame(rows)
    statistics["P_value_Bonferroni"] = adjusted_p_values(
        statistics["P_value_raw"], "bonferroni"
    )
    statistics["P_value_Holm"] = adjusted_p_values(statistics["P_value_raw"], "holm")
    statistics["P_value_FDR_BH"] = adjusted_p_values(
        statistics["P_value_raw"], "fdr_bh"
    )
    return statistics


def build_all_sets_mistouch_values(values: pd.DataFrame, product: str) -> pd.DataFrame:
    """Sum confirmed mistouches across all paired available sets per participant."""

    rows: list[dict[str, object]] = []
    selected_product = values.loc[values["Product"] == product]
    for pair_id, selected in selected_product.groupby("Pair_ID", sort=True):
        drops = selected["EyeDrop_mistouch_count"].to_numpy(float)
        control = selected["Control_mistouch_count"].to_numpy(float)
        paired = np.isfinite(drops) & np.isfinite(control)
        rows.append(
            {
                "Product": product,
                "Pair_ID": pair_id,
                "Included_set_count": int(paired.sum()),
                "EyeDrop_all_sets_mistouch_count": (
                    float(np.sum(drops[paired])) if paired.any() else np.nan
                ),
                "Control_all_sets_mistouch_count": (
                    float(np.sum(control[paired])) if paired.any() else np.nan
                ),
            }
        )
    return pd.DataFrame(rows)


def plot_product(
    values: pd.DataFrame,
    summary: pd.DataFrame,
    statistics: pd.DataFrame,
    product: str,
    path: Path,
) -> float:
    label, color = PRODUCTS[product]
    product_values = values.loc[values["Product"] == product]
    upper, y_ticks, line_y, text_y, ns_text_y, set_y = _axis_layout(
        product_values[["EyeDrop_mistouch_count", "Control_mistouch_count"]].to_numpy(float)
    )
    plt.rcParams.update(
        {"font.family": "sans-serif", "font.sans-serif": ["Arial"], "axes.linewidth": 1.5}
    )
    figure, axes = plt.subplots(1, N_SETS, figsize=(34, 9), sharey=True)
    for set_number, axis in enumerate(axes, start=1):
        current = product_values.loc[product_values["Set"] == set_number].sort_values("Pair_ID")
        drops = current["EyeDrop_mistouch_count"].to_numpy(float)
        control = current["Control_mistouch_count"].to_numpy(float)
        paired = np.isfinite(drops) & np.isfinite(control)
        drops, control = drops[paired], control[paired]
        row = summary.loc[(summary["Product"] == product) & (summary["Set"] == set_number)].iloc[0]
        axis.bar(
            BAR_CENTERS,
            [row["EyeDrop_mean_count"], row["Control_mean_count"]],
            width=BAR_WIDTH,
            color=[color, CONTROL_COLOR],
            alpha=0.86,
            edgecolor="#222222",
            linewidth=1.0,
            zorder=1,
        )
        offsets = (
            np.linspace(-JITTER_HALF_WIDTH, JITTER_HALF_WIDTH, drops.size)
            if drops.size > 1
            else np.zeros(drops.size)
        )
        for offset, dval, cval in zip(offsets, drops, control, strict=True):
            axis.plot(
                BAR_CENTERS + offset,
                [dval, cval],
                color="#777777",
                alpha=0.34,
                linewidth=1.2,
                zorder=2,
            )
        axis.scatter(
            BAR_CENTERS[0] + offsets,
            drops,
            s=DOT_SIZE,
            color=color,
            alpha=0.68,
            edgecolor="white",
            linewidth=1.0,
            zorder=3,
        )
        axis.scatter(
            BAR_CENTERS[1] + offsets,
            control,
            s=DOT_SIZE,
            color=CONTROL_COLOR,
            alpha=0.68,
            edgecolor="white",
            linewidth=1.0,
            zorder=3,
        )
        axis.text(
            0.5,
            set_y,
            f"Set {set_number}",
            transform=axis.transAxes,
            ha="center",
            va="center",
            fontfamily="Arial",
            fontsize=26,
        )
        p_value = float(
            statistics.loc[statistics["Set"] == set_number, "P_value_raw"].iloc[0]
        )
        add_significance_bracket(
            axis,
            BAR_CENTERS[0],
            BAR_CENTERS[1],
            significance_label(p_value),
            line_y=line_y,
            text_y=text_y,
            nonsignificant_text_y=ns_text_y,
        )
        axis.set_xticks(BAR_CENTERS, ["Eye Drop", "Control"], fontsize=22)
        axis.text(
            BAR_CENTERS[0],
            -0.105,
            f"({label})",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=18,
            clip_on=False,
        )
        axis.set_xlim(*X_LIMITS)
        axis.set_ylim(0, upper)
        axis.set_yticks(y_ticks)
        axis.tick_params(axis="x", labelsize=22, width=1.5, length=6, pad=12)
        axis.tick_params(axis="y", labelsize=23, labelleft=True, width=1.5, length=6)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)
        axis.grid(False)
    axes[0].set_ylabel("Mistouch (count)", fontsize=30, labelpad=12)
    figure.subplots_adjust(left=0.06, right=0.995, top=0.94, bottom=0.25, wspace=0.24)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return upper


def plot_all_sets_mistouch(
    values: pd.DataFrame, product: str, path: Path
) -> tuple[int, dict[str, float | int]]:
    """Plot one all-set count panel with an unadjusted paired t-test."""

    label, color = PRODUCTS[product]
    drops = values["EyeDrop_all_sets_mistouch_count"].to_numpy(float)
    control = values["Control_all_sets_mistouch_count"].to_numpy(float)
    paired = np.isfinite(drops) & np.isfinite(control)
    drops, control = drops[paired], control[paired]
    statistics = paired_t_statistics(drops, control)
    upper, y_ticks, line_y, text_y, ns_text_y, set_y = _axis_layout(
        np.column_stack([drops, control])
    )
    plt.rcParams.update(
        {"font.family": "sans-serif", "font.sans-serif": ["Arial"], "axes.linewidth": 1.5}
    )
    figure, axis = plt.subplots(figsize=(7.5, 9))
    axis.bar(
        BAR_CENTERS,
        [np.mean(drops), np.mean(control)],
        width=BAR_WIDTH,
        color=[color, CONTROL_COLOR],
        alpha=0.86,
        edgecolor="#222222",
        linewidth=1.0,
        zorder=1,
    )
    offsets = np.random.default_rng(7101).uniform(
        -JITTER_HALF_WIDTH, JITTER_HALF_WIDTH, size=drops.size
    )
    for offset, dval, cval in zip(offsets, drops, control, strict=True):
        axis.plot(
            BAR_CENTERS + offset,
            [dval, cval],
            color="#777777",
            alpha=0.34,
            linewidth=1.2,
            zorder=2,
        )
    axis.scatter(
        BAR_CENTERS[0] + offsets,
        drops,
        s=DOT_SIZE,
        color=color,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.0,
        zorder=3,
    )
    axis.scatter(
        BAR_CENTERS[1] + offsets,
        control,
        s=DOT_SIZE,
        color=CONTROL_COLOR,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.0,
        zorder=3,
    )
    axis.text(
        0.5,
        set_y,
        "All Sets",
        transform=axis.transAxes,
        ha="center",
        va="center",
        fontfamily="Arial",
        fontsize=26,
    )
    add_significance_bracket(
        axis,
        BAR_CENTERS[0],
        BAR_CENTERS[1],
        significance_label(float(statistics["P_value_raw"])),
        line_y=line_y,
        text_y=text_y,
        nonsignificant_text_y=ns_text_y,
    )
    axis.set_xticks(BAR_CENTERS, ["Eye Drop", "Control"], fontsize=22)
    axis.text(
        BAR_CENTERS[0],
        -0.105,
        f"({label})",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=18,
        clip_on=False,
    )
    axis.set_xlim(*X_LIMITS)
    axis.set_ylim(0, upper)
    axis.set_yticks(y_ticks)
    axis.tick_params(axis="x", labelsize=22, width=1.5, length=6, pad=12)
    axis.tick_params(axis="y", labelsize=23, width=1.5, length=6)
    axis.set_ylabel("Mistouch (count)", fontsize=30, labelpad=12)
    axis.spines[["top", "right"]].set_visible(False)
    axis.grid(False)
    figure.subplots_adjust(left=0.20, right=0.98, top=0.94, bottom=0.25)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return upper, statistics


def write_statistical_quantification_figures(
    product_dir: Path,
    support_dir: Path,
    values: pd.DataFrame,
    summary: pd.DataFrame,
    product: str,
    prefix: str,
) -> dict[str, object]:
    """Write unadjusted figures and raw plus three adjusted statistical tables."""

    (product_dir / f"{prefix}.png").unlink(missing_ok=True)
    statistics = build_setwise_paired_statistics(values, product)
    setwise_figure = product_dir / f"{prefix}_PairedTTest_Unadjusted.png"
    upper = plot_product(values, summary, statistics, product, setwise_figure)
    all_sets_values = build_all_sets_mistouch_values(values, product)
    all_sets_figure = product_dir / f"{prefix}_AllSets_PairedTTest_Unadjusted.png"
    all_sets_upper, all_sets_statistics = plot_all_sets_mistouch(
        all_sets_values, product, all_sets_figure
    )
    statistics_path = product_dir / f"{prefix}_PairedTTests.csv"
    all_sets_values_path = support_dir / f"{prefix}_AllSets_ParticipantValues.csv"
    all_sets_statistics_path = product_dir / f"{prefix}_AllSets_PairedTTest.csv"
    (support_dir / f"{prefix}_PairedTTests.csv").unlink(missing_ok=True)
    (support_dir / f"{prefix}_AllSets_PairedTTest.csv").unlink(missing_ok=True)
    statistics.to_csv(statistics_path, index=False)
    all_sets_values.to_csv(all_sets_values_path, index=False)
    all_sets_statistics_frame = pd.DataFrame([all_sets_statistics])
    for method, column in (
        ("bonferroni", "P_value_Bonferroni"),
        ("holm", "P_value_Holm"),
        ("fdr_bh", "P_value_FDR_BH"),
    ):
        all_sets_statistics_frame[column] = adjusted_p_values(
            all_sets_statistics_frame["P_value_raw"], method
        )
    all_sets_statistics_frame.to_csv(all_sets_statistics_path, index=False)
    return {
        "setwise_figure": str(setwise_figure),
        "all_sets_figure": str(all_sets_figure),
        "setwise_statistics": str(statistics_path),
        "all_sets_participant_values": str(all_sets_values_path),
        "all_sets_statistics": str(all_sets_statistics_path),
        "figure_y_axis_upper_count": upper,
        "all_sets_figure_y_axis_upper_count": all_sets_upper,
    }


def write_outputs(
    output_root: Path, values: pd.DataFrame, summary: pd.DataFrame
) -> list[dict[str, object]]:
    root = output_root / "Phase2_行動データ解析" / "No2_Mistouch"
    root.mkdir(parents=True, exist_ok=True)
    support_dir = root / "Sub"
    support_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict[str, object]] = []
    for product in PRODUCTS:
        product_dir = root / product
        product_dir.mkdir(parents=True, exist_ok=True)
        for stale in product_dir.glob("No2_Mistouch_*PairedTTest*.png"):
            stale.unlink()
        quantification_dir = product_dir / "SetQuantification"
        quantification_dir.mkdir(parents=True, exist_ok=True)
        for stale in quantification_dir.glob("*.png"):
            stale.unlink()
        for stale in quantification_dir.glob("*.csv"):
            stale.unlink()
        prefix = f"No2_Mistouch_{product}"
        values_path = support_dir / f"{prefix}_ParticipantValues.csv"
        summary_path = support_dir / f"{prefix}_SetSummary.csv"
        run_path = support_dir / f"{prefix}_RunSummary.json"
        selected_values = values.loc[values["Product"] == product].copy()
        selected_summary = summary.loc[summary["Product"] == product].copy()
        statistical_outputs = write_statistical_quantification_figures(
            quantification_dir,
            support_dir,
            selected_values,
            selected_summary,
            product,
            prefix,
        )
        selected_values.to_csv(values_path, index=False)
        selected_summary.to_csv(summary_path, index=False)
        run = {
            "product": product,
            "participant_count": int(selected_values["Pair_ID"].nunique()),
            "definition": {
                "basic": "one mistouch row equals one mistouch event",
                "consecutive": "adjacent mistouch rows with KeyPress gap <= 50 ms are merged",
                "correct_bridge": (
                    "mistouch-correct-mistouch with outer gap <= 100 ms and "
                    "correct RT <= 50 ms is merged"
                ),
                "boundaries": "never merge across sets or files",
            },
            "eeg_missing_set_rule": "both paired conditions are NaN for the same affected set",
            "statistics": (
                "two-sided paired t-test; figures use raw p-values. CSV retains raw, "
                "Bonferroni, Holm, and Benjamini-Hochberg FDR p-values"
            ),
            "local_processed_data_created": False,
            "outputs": {
                **statistical_outputs,
                "participant_values": str(values_path),
                "set_summary": str(summary_path),
            },
            "completed_at": datetime.now().astimezone().isoformat(),
        }
        run_path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        outputs.append({**run["outputs"], "run_summary": str(run_path)})

        if product == "CCube":
            sensitivity_values = build_ccube_sensitivity_values(selected_values)
            sensitivity_summary = build_summary(sensitivity_values)
            sensitivity_summary = sensitivity_summary.loc[
                sensitivity_summary["Product"] == "CCube"
            ].copy()
            sensitivity_prefix = "No2_Mistouch_CCube_SensitivityAnalysis_ExcludeID132-232_Set1"
            sensitivity_dir = (
                quantification_dir / "SensitivityAnalysis_ExcludeID132-232_Set1"
            )
            sensitivity_dir.mkdir(parents=True, exist_ok=True)
            for stale in sensitivity_dir.glob("*.png"):
                stale.unlink()
            for stale in sensitivity_dir.glob("*.csv"):
                stale.unlink()
            sensitivity_csv = support_dir / f"{sensitivity_prefix}_SetSummary.csv"
            sensitivity_run = support_dir / f"{sensitivity_prefix}_RunSummary.json"
            sensitivity_statistical_outputs = write_statistical_quantification_figures(
                sensitivity_dir,
                support_dir,
                sensitivity_values,
                sensitivity_summary,
                "CCube",
                sensitivity_prefix,
            )
            sensitivity_summary.to_csv(sensitivity_csv, index=False)
            sensitivity_record = {
                "analysis_role": "sensitivity analysis; main analysis is unchanged",
                "product": "CCube",
                "excluded_pair": SENSITIVITY_PAIR_ID,
                "excluded_set": SENSITIVITY_SET,
                "exclusion_scope": "both Eye Drop and Control conditions",
                "other_sets_and_participants_changed": False,
                "set1_paired_n": int(
                    sensitivity_summary.loc[sensitivity_summary["Set"] == 1, "Paired_N"].iloc[0]
                ),
                "statistics": (
                    "two-sided paired t-test; figures use raw p-values. CSV retains raw, "
                    "Bonferroni, Holm, and Benjamini-Hochberg FDR p-values"
                ),
                "outputs": {
                    **sensitivity_statistical_outputs,
                    "set_summary": str(sensitivity_csv),
                },
                "completed_at": datetime.now().astimezone().isoformat(),
            }
            sensitivity_run.write_text(
                json.dumps(sensitivity_record, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            outputs.append(
                {
                    **sensitivity_record["outputs"],
                    "run_summary": str(sensitivity_run),
                }
            )
    batch_path = root / "No2_Mistouch_BatchSummary.json"
    batch_path.write_text(
        json.dumps(
            {
                "completed_participant_count": int(values["Pair_ID"].nunique()),
                "completed_pairs": sorted(values["Pair_ID"].unique().tolist()),
                "same_shared_pipeline_for_all_participants": True,
                "outputs": outputs,
                "completed_at": datetime.now().astimezone().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", type=Path, default=no1.DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=no1.DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = no1.load_manifest(args.manifest)
    rows: list[dict[str, object]] = []
    for participant in specs:
        logging.info("Processing ID%s", participant.pair_id)
        rows.extend(analyse_participant(args.raw_root, participant))
    values = pd.DataFrame(rows)
    summary = build_summary(values)
    outputs = write_outputs(args.output_root, values, summary)
    logging.info("Completed %d participants: %s", len(specs), outputs)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    raise SystemExit(main())
