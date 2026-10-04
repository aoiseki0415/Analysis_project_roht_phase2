#!/usr/bin/env python3
"""Phase 4 No1_sub: analyse Set-1-normalised Fm-theta PSD change."""

from __future__ import annotations

import argparse
import json
import logging
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mne
import numpy as np
import pandas as pd
import Phase4_No1_FmTheta as no1

COMMON_DIR = Path(__file__).resolve().parents[1]
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from paired_statistics import (  # noqa: E402
    adjusted_p_values,
    paired_t_statistics,
    significance_label,
)

SCRIPT_VERSION = "phase4-no1-sub-fmtheta-change-2026-10-04.2"
N_SETS = no1.N_SETS
PROGRESS_POINTS = no1.GROUP_PROGRESS_POINTS_PER_SET
SMOOTHING_SECONDS = no1.TIMECOURSE_SMOOTHING_SECONDS
SET1_MISSING_PAIR_ID = "109-209"
Y_LABEL = "PSD Change, %"
TOPOGRAPHY_LABEL = "Difference in PSD Change, %"

DEFAULT_CACHE_ROOT = no1.DEFAULT_CACHE_ROOT
DEFAULT_OUTPUT_ROOT = no1.DEFAULT_OUTPUT_ROOT


@dataclass
class ChangeSession:
    source: no1.SessionPSD
    baseline_by_channel: np.ndarray

    @property
    def session_id(self) -> str:
        return self.source.session_id

    @property
    def channel_names(self) -> list[str]:
        return self.source.channel_names


def calculate_set1_baseline(session: no1.SessionPSD) -> np.ndarray:
    """Return one finite positive Set-1 mean for every channel."""
    if 1 not in session.sets:
        raise ValueError(f"ID{session.session_id}: Set 1 is absent")
    values = np.asarray(session.sets[1].psd_band_mean, dtype=float)
    with np.errstate(invalid="ignore"):
        baseline = np.nanmean(values, axis=0)
    invalid = ~np.isfinite(baseline) | (baseline <= np.finfo(float).tiny)
    if invalid.any():
        channels = [session.channel_names[index] for index in np.flatnonzero(invalid)]
        raise ValueError(
            f"ID{session.session_id}: invalid Set 1 baseline for {', '.join(channels)}"
        )
    return baseline


def to_percent_change(values: np.ndarray, baseline: np.ndarray | float) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    denominator = np.asarray(baseline, dtype=float)
    if np.any(~np.isfinite(denominator)) or np.any(denominator <= np.finfo(float).tiny):
        raise ValueError("baseline must be finite and positive")
    return (values / denominator - 1.0) * 100.0


def make_change_session(session: no1.SessionPSD) -> ChangeSession:
    baseline = calculate_set1_baseline(session)
    change = ChangeSession(session, baseline)
    set1_change = to_percent_change(session.sets[1].psd_band_mean, baseline)
    means = np.nanmean(set1_change, axis=0)
    if not np.allclose(means, 0.0, atol=1e-8, rtol=0.0, equal_nan=False):
        raise ValueError(f"ID{session.session_id}: Set 1 change does not average to zero")
    return change


def set_change_values(
    session: ChangeSession,
    set_number: int,
    channel_index: int,
    *,
    smoothing_seconds: int | None = None,
) -> np.ndarray:
    raw = to_percent_change(
        session.source.sets[set_number].psd_band_mean[:, channel_index],
        session.baseline_by_channel[channel_index],
    )
    if smoothing_seconds is None:
        return raw
    points = int(round(smoothing_seconds * no1.SFREQ / no1.STEP_SAMPLES))
    return no1.centered_nanmean(raw, points)


def _channel_index(session: ChangeSession, channel: str = "Fz") -> int:
    try:
        return session.channel_names.index(channel)
    except ValueError as error:
        raise ValueError(f"ID{session.session_id}: {channel} is absent") from error


def _all_displayed_values(session: ChangeSession, channel: str, smoothing: int) -> np.ndarray:
    index = _channel_index(session, channel)
    return np.concatenate(
        [
            set_change_values(session, number, index, smoothing_seconds=smoothing)
            for number in sorted(session.source.sets)
        ]
    )


def _nice_symmetric_limit(values: np.ndarray, target_fraction: float) -> tuple[float, np.ndarray]:
    finite = np.abs(np.asarray(values, dtype=float))
    finite = finite[np.isfinite(finite)]
    maximum = float(finite.max()) if finite.size else 1.0
    raw = max(maximum / target_fraction, 1.0)
    exponent = math.floor(math.log10(raw))
    candidates: list[tuple[float, float, np.ndarray]] = []
    for power in range(exponent - 2, exponent + 2):
        scale = 10.0**power
        for multiplier in (1.0, 2.0, 2.5, 5.0):
            step = multiplier * scale
            limit = math.ceil(raw / step) * step
            ticks = np.arange(-limit, limit + step * 0.01, step)
            if 3 <= ticks.size <= 7:
                candidates.append((abs(ticks.size - 5), limit, ticks))
    if not candidates:
        return raw, np.linspace(-raw, raw, 5)
    _, limit, ticks = min(candidates, key=lambda item: (item[0], item[1]))
    return float(limit), ticks


def _nice_close_symmetric_limit(
    values: np.ndarray, target_fraction: float
) -> tuple[float, np.ndarray]:
    """Choose a readable symmetric limit while prioritising target occupancy."""
    finite = np.abs(np.asarray(values, dtype=float))
    finite = finite[np.isfinite(finite)]
    maximum = float(finite.max()) if finite.size else 1.0
    raw = max(maximum / target_fraction, 1.0)
    exponent = math.floor(math.log10(raw))
    limits = [
        multiplier * 10.0**power
        for power in range(exponent - 2, exponent + 2)
        for multiplier in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)
        if multiplier * 10.0**power >= raw
    ]
    limit = min(limits)
    tick_choices: list[tuple[float, float, np.ndarray]] = []
    for power in range(exponent - 2, exponent + 2):
        scale = 10.0**power
        for multiplier in (1.0, 2.0, 2.5, 4.0, 5.0, 10.0):
            step = multiplier * scale
            ticks = np.arange(-limit, limit + step * 0.01, step)
            if 3 <= ticks.size <= 7 and np.any(np.isclose(ticks, 0.0)):
                tick_choices.append((abs(ticks.size - 5), step, ticks))
    ticks = (
        min(tick_choices, key=lambda item: (item[0], item[1]))[2]
        if tick_choices
        else np.linspace(-limit, limit, 5)
    )
    return float(limit), ticks


def _configure_time_axis(axis: plt.Axes, limit: float, ticks: np.ndarray) -> None:
    axis.axhline(0.0, color="#9E9E9E", linewidth=1.3, zorder=0)
    for boundary in range(100, 600, 100):
        axis.axvline(boundary, color="#9E9E9E", linestyle="--", linewidth=1.5, zorder=0)
    for set_number in range(1, N_SETS + 1):
        axis.text(
            (set_number - 0.5) * 100,
            0.96,
            f"Set {set_number}",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=22,
            fontfamily="Arial",
            color="#333333",
        )
    axis.set_xlim(0, 600)
    axis.set_ylim(-limit, limit)
    axis.set_xticks(np.arange(0, 601, 50))
    axis.set_yticks(ticks)
    axis.set_xlabel("Experimental Progress, %", fontsize=28, labelpad=18)
    axis.set_ylabel(Y_LABEL, fontsize=28)
    axis.tick_params(axis="both", labelsize=20, width=1.5, length=6)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_individual(item: dict[str, Any], path: Path) -> None:
    spec = item["spec"]
    _, product_label, product_color, _ = no1.normalize_product(spec.product)
    eye: ChangeSession = item["eye_drop"]
    control: ChangeSession = item["control"]
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    for session, color, label in (
        (control, no1.CONTROL_COLOR, "Control"),
        (eye, product_color, f"Eye Drop ({product_label})"),
    ):
        channel = _channel_index(session)
        first = True
        for set_number, values in sorted(session.source.sets.items()):
            axis.plot(
                values.global_progress_pct,
                set_change_values(
                    session, set_number, channel, smoothing_seconds=SMOOTHING_SECONDS
                ),
                color=color,
                linewidth=3.0,
                label=label if first else None,
            )
            first = False
    displayed = np.concatenate(
        [
            _all_displayed_values(eye, "Fz", SMOOTHING_SECONDS),
            _all_displayed_values(control, "Fz", SMOOTHING_SECONDS),
        ]
    )
    limit, ticks = _nice_symmetric_limit(displayed, 0.70)
    _configure_time_axis(axis, limit, ticks)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False, fontsize=20)
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def interpolate_change_progress(
    session: ChangeSession, *, symmetrically_missing_sets: set[int] | None = None
) -> np.ndarray:
    output = np.full((N_SETS, PROGRESS_POINTS), np.nan)
    target = np.linspace(0.0, 100.0, PROGRESS_POINTS, endpoint=False)
    channel = _channel_index(session)
    missing = symmetrically_missing_sets or set()
    for set_number, values in session.source.sets.items():
        if set_number in missing:
            continue
        smooth = set_change_values(
            session, set_number, channel, smoothing_seconds=SMOOTHING_SECONDS
        )
        output[set_number - 1] = no1._interpolate_finite_runs(  # noqa: SLF001
            values.set_progress_pct, smooth, target
        )
    return output


def build_grand_average(
    items: list[dict[str, Any]], product_dir: str
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    selected = [item for item in items if item["product_dir"] == product_dir]
    eye_values: list[np.ndarray] = []
    control_values: list[np.ndarray] = []
    for item in selected:
        missing = set(range(1, N_SETS + 1)).difference(item["eye_drop"].source.sets)
        missing.update(set(range(1, N_SETS + 1)).difference(item["control"].source.sets))
        eye_values.append(
            interpolate_change_progress(item["eye_drop"], symmetrically_missing_sets=missing)
        )
        control_values.append(
            interpolate_change_progress(item["control"], symmetrically_missing_sets=missing)
        )
    eye = np.vstack([value.reshape(-1) for value in eye_values])
    control = np.vstack([value.reshape(-1) for value in control_values])
    eye_stats = no1._columnwise_statistics(eye)  # noqa: SLF001
    control_stats = no1._columnwise_statistics(control)  # noqa: SLF001
    within = np.tile(np.linspace(0.0, 100.0, PROGRESS_POINTS, endpoint=False), N_SETS)
    sets = np.repeat(np.arange(1, N_SETS + 1), PROGRESS_POINTS)
    frame = pd.DataFrame(
        {
            "Set": sets,
            "SetProgressPercent": within,
            "GlobalProgressPercent": (sets - 1) * 100.0 + within,
        }
    )
    for prefix, stats in (("EyeDrop", eye_stats), ("Control", control_stats)):
        frame[f"{prefix}_Mean_PSDChange_pct"] = stats["mean"]
        frame[f"{prefix}_SD_PSDChange_pct"] = stats["sample_sd"]
        frame[f"{prefix}_SEM_PSDChange_pct"] = stats["sem"]
        frame[f"{prefix}_N"] = stats["valid_n"]
    return frame, {"eye_drop": eye, "control": control}


def plot_grand_average(
    frame: pd.DataFrame,
    product_dir: str,
    path: Path,
    *,
    common_limit: float,
    common_ticks: np.ndarray,
) -> None:
    _, product_label, product_color, _ = no1.normalize_product(product_dir)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    x = frame["GlobalProgressPercent"].to_numpy(float)
    for prefix, color, label in (
        ("Control", no1.CONTROL_COLOR, "Control"),
        ("EyeDrop", product_color, f"Eye Drop ({product_label})"),
    ):
        mean = frame[f"{prefix}_Mean_PSDChange_pct"].to_numpy(float)
        sem = frame[f"{prefix}_SEM_PSDChange_pct"].to_numpy(float)
        for set_number in range(1, N_SETS + 1):
            mask = frame["Set"].to_numpy(int) == set_number
            axis.fill_between(
                x[mask],
                mean[mask] - sem[mask],
                mean[mask] + sem[mask],
                color=color,
                alpha=0.18,
                linewidth=0,
            )
            axis.plot(
                x[mask],
                mean[mask],
                color=color,
                linewidth=3.0,
                label=label if set_number == 1 else None,
            )
    _configure_time_axis(axis, common_limit, common_ticks)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False, fontsize=20)
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def grand_average_axis(frames: list[pd.DataFrame]) -> tuple[float, np.ndarray]:
    """Return a shared symmetric axis from mean lines only."""
    values = [
        frame[f"{prefix}_Mean_PSDChange_pct"].to_numpy(float)
        for frame in frames
        for prefix in ("EyeDrop", "Control")
    ]
    return _nice_close_symmetric_limit(np.concatenate(values), 0.75)


def set_channel_means(session: ChangeSession) -> dict[int, np.ndarray]:
    return {
        number: np.nanmean(
            to_percent_change(values.psd_band_mean, session.baseline_by_channel), axis=0
        )
        for number, values in session.source.sets.items()
    }


def build_quantification(items: list[dict[str, Any]], product_dir: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        if item["product_dir"] != product_dir:
            continue
        eye_means = set_channel_means(item["eye_drop"])
        control_means = set_channel_means(item["control"])
        common = set(eye_means).intersection(control_means)
        fz = _channel_index(item["eye_drop"])
        for number in range(1, N_SETS + 1):
            rows.append(
                {
                    "PairID": item["spec"].pair_id,
                    "Set": number,
                    "EyeDrop_PSDChange_pct": float(eye_means[number][fz])
                    if number in common
                    else np.nan,
                    "Control_PSDChange_pct": float(control_means[number][fz])
                    if number in common
                    else np.nan,
                }
            )
        analysis_sets = sorted(common)
        eye_values = np.concatenate(
            [
                to_percent_change(
                    item["eye_drop"].source.sets[number].psd_band_mean[:, fz],
                    item["eye_drop"].baseline_by_channel[fz],
                )
                for number in analysis_sets
            ]
        )
        control_values = np.concatenate(
            [
                to_percent_change(
                    item["control"].source.sets[number].psd_band_mean[:, fz],
                    item["control"].baseline_by_channel[fz],
                )
                for number in analysis_sets
            ]
        )
        rows.append(
            {
                "PairID": item["spec"].pair_id,
                "Set": "All Sets",
                "EyeDrop_PSDChange_pct": float(np.nanmean(eye_values)),
                "Control_PSDChange_pct": float(np.nanmean(control_values)),
            }
        )
    return pd.DataFrame(rows)


def quantification_statistics(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = [
        {
            "Set": 1,
            "N": int(frame.loc[frame["Set"] == 1, "PairID"].nunique()),
            "T_statistic": np.nan,
            "P_value_raw": np.nan,
            "Note": "Baseline; no test",
        }
    ]
    for number in range(2, N_SETS + 1):
        selected = frame.loc[frame["Set"] == number]
        rows.append(
            {
                "Set": number,
                **paired_t_statistics(
                    selected["EyeDrop_PSDChange_pct"].to_numpy(float),
                    selected["Control_PSDChange_pct"].to_numpy(float),
                ),
                "Note": "Paired t-test",
            }
        )
    statistics = pd.DataFrame(rows)
    p_values = statistics.loc[statistics["Set"] != 1, "P_value_raw"].to_numpy(float)
    for method, column in (
        ("bonferroni", "P_value_Bonferroni"),
        ("holm", "P_value_Holm"),
        ("fdr_bh", "P_value_FDR_BH"),
    ):
        statistics[column] = np.nan
        statistics.loc[statistics["Set"] != 1, column] = adjusted_p_values(p_values, method)
    selected = frame.loc[frame["Set"] == "All Sets"]
    overall = pd.DataFrame(
        [
            {
                "Set": "All Sets",
                **paired_t_statistics(
                    selected["EyeDrop_PSDChange_pct"].to_numpy(float),
                    selected["Control_PSDChange_pct"].to_numpy(float),
                ),
            }
        ]
    )
    return statistics, overall


def _quantification_layout(
    values: np.ndarray,
) -> tuple[float, float, np.ndarray, float, float, float]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    observed_max = float(np.max(finite)) if finite.size else 0.0
    observed_min = float(np.min(finite)) if finite.size else 0.0
    reference_max = max(observed_max, 2.0 * abs(min(observed_min, 0.0)) / 1.37, 1.0)
    upper = 1.37 * reference_max
    lower = -upper / 2.0

    exponent = int(np.floor(np.log10(upper))) if upper > 0 else 0
    choices: list[tuple[float, float, np.ndarray]] = []
    for power in range(exponent - 2, exponent + 2):
        scale = 10.0**power
        for multiplier in (1.0, 2.0, 2.5, 5.0, 10.0):
            step = multiplier * scale
            start = math.ceil(lower / step) * step
            stop = math.floor(upper / step) * step
            ticks = np.arange(start, stop + step * 0.01, step)
            if 3 <= ticks.size <= 6 and np.any(np.isclose(ticks, 0.0)):
                choices.append((abs(ticks.size - 5), step, ticks))
    ticks = (
        min(choices, key=lambda item: (item[0], item[1]))[2]
        if choices
        else np.linspace(lower, upper, 5)
    )
    return (
        lower,
        upper,
        ticks,
        1.13 * reference_max,
        1.18 * reference_max,
        1.29 * reference_max,
    )


def _draw_quant_panel(
    axis: plt.Axes,
    eye: np.ndarray,
    control: np.ndarray,
    eye_color: str,
    product_label: str,
    panel_label: str,
    p_value: float | None,
    layout: tuple[float, float, np.ndarray, float, float, float],
    seed: int,
    *,
    show_ylabel: bool,
) -> None:
    lower, upper, ticks, line_y, text_y, set_y = layout
    paired = np.isfinite(eye) & np.isfinite(control)
    eye, control = eye[paired], control[paired]
    x = np.array([-0.32, 0.32])
    axis.bar(
        x,
        [eye.mean(), control.mean()],
        width=0.42,
        color=[eye_color, no1.CONTROL_QUANTIFICATION_COLOR],
        alpha=0.82,
        edgecolor="#222222",
        linewidth=1.0,
        zorder=1,
    )
    jitter = np.random.default_rng(seed).uniform(-0.055, 0.055, eye.size)
    for offset, eye_value, control_value in zip(jitter, eye, control, strict=True):
        axis.plot(
            x + offset,
            [eye_value, control_value],
            color="#777777",
            linewidth=1.2,
            alpha=0.34,
            zorder=2,
        )
    axis.scatter(
        x[0] + jitter,
        eye,
        s=150,
        color=eye_color,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    axis.scatter(
        x[1] + jitter,
        control,
        s=150,
        color=no1.CONTROL_QUANTIFICATION_COLOR,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    axis.axhline(0, color="#9E9E9E", linewidth=1.2, zorder=0)
    if p_value is None:
        axis.text(0, text_y, "Baseline", ha="center", va="bottom", fontsize=22, fontfamily="Arial")
    else:
        axis.plot(
            [x[0], x[0], x[1], x[1]],
            [line_y - 0.02 * (upper - lower), line_y, line_y, line_y - 0.02 * (upper - lower)],
            color="black",
            linewidth=2.2,
        )
        axis.text(
            0,
            text_y,
            significance_label(p_value),
            ha="center",
            va="bottom",
            fontsize=34 if p_value < 0.05 else 26,
            fontfamily="Arial",
        )
    axis.text(
        0,
        set_y,
        panel_label,
        ha="center",
        va="center",
        fontsize=26,
        fontfamily="Arial",
    )
    axis.set_xlim(-0.9, 0.9)
    axis.set_ylim(lower, upper)
    axis.set_yticks(ticks)
    axis.set_xticks(x, ["Eye Drop", "Control"], fontsize=22)
    axis.text(
        x[0],
        -0.105,
        f"({product_label})",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=18,
        fontfamily="Arial",
        clip_on=False,
    )
    axis.tick_params(axis="x", labelsize=22, width=1.5, length=6, pad=12)
    axis.tick_params(axis="y", labelsize=23, width=1.5, length=6, labelleft=True)
    if show_ylabel:
        axis.set_ylabel(Y_LABEL, fontsize=30)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_quantification(
    frame: pd.DataFrame, statistics: pd.DataFrame, product: str, path: Path
) -> None:
    _, product_label, _, eye_color = no1.normalize_product(product)
    values = frame.loc[
        frame["Set"] != "All Sets", ["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]
    ].to_numpy(float)
    layout = _quantification_layout(values)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axes = plt.subplots(1, N_SETS, figsize=(34, 9), sharey=True)
    for number, axis in enumerate(axes, 1):
        selected = frame.loc[frame["Set"] == number]
        p = (
            None
            if number == 1
            else float(statistics.loc[statistics["Set"] == number, "P_value_raw"].iloc[0])
        )
        _draw_quant_panel(
            axis,
            selected["EyeDrop_PSDChange_pct"].to_numpy(float),
            selected["Control_PSDChange_pct"].to_numpy(float),
            eye_color,
            product_label,
            f"Set {number}",
            p,
            layout,
            8100 + number,
            show_ylabel=number == 1,
        )
    figure.subplots_adjust(left=0.06, right=0.995, top=0.94, bottom=0.25, wspace=0.24)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_overall_quantification(
    frame: pd.DataFrame, statistics: pd.DataFrame, product: str, path: Path
) -> None:
    _, product_label, _, eye_color = no1.normalize_product(product)
    selected = frame.loc[frame["Set"] == "All Sets"]
    values = selected[["EyeDrop_PSDChange_pct", "Control_PSDChange_pct"]].to_numpy(float)
    layout = _quantification_layout(values)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(7.5, 9))
    _draw_quant_panel(
        axis,
        selected["EyeDrop_PSDChange_pct"].to_numpy(float),
        selected["Control_PSDChange_pct"].to_numpy(float),
        eye_color,
        product_label,
        "All Sets",
        float(statistics["P_value_raw"].iloc[0]),
        layout,
        9101,
        show_ylabel=True,
    )
    figure.subplots_adjust(left=0.20, right=0.98, top=0.94, bottom=0.25)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def pair_topography_values(item: dict[str, Any]) -> np.ndarray:
    eye = set_channel_means(item["eye_drop"])
    control = set_channel_means(item["control"])
    output = np.full((N_SETS, len(no1.EXPECTED_CHANNEL_NAMES)), np.nan)
    for number in set(eye).intersection(control):
        output[number - 1] = eye[number] - control[number]
    return output


def _topography_limit(values: np.ndarray) -> float:
    finite = np.abs(values[np.isfinite(values)])
    maximum = float(finite.max()) if finite.size else 1.0
    if maximum <= np.finfo(float).eps:
        return 1.0
    target = maximum / 0.85
    exponent = math.floor(math.log10(target))
    scale = 10**exponent
    for multiplier in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if target <= multiplier * scale:
            return float(multiplier * scale)
    raise RuntimeError("Unable to determine topography limit")


def plot_topography(values: np.ndarray, path: Path) -> float:
    limit = _topography_limit(values)
    plt.rcParams.update({"font.family": "Arial"})
    figure, axes = plt.subplots(1, N_SETS, figsize=(36, 6.5))
    info = no1._topomap_info()  # noqa: SLF001
    for index, axis in enumerate(axes):
        vector = values[index]
        axis.set_title(f"Set {index + 1}", fontsize=24, fontfamily="Arial", pad=16)
        if not np.isfinite(vector).all():
            axis.set_axis_off()
            axis.text(0.5, 0.5, "Missing", ha="center", va="center", fontsize=22)
            continue
        image, _ = mne.viz.plot_topomap(
            vector,
            info,
            axes=axis,
            show=False,
            cmap="RdBu_r",
            vlim=(-limit, limit),
            sensors="k.",
            names=None,
            contours=0,
            extrapolate="head",
            sphere=(0, 0, 0, 0.095),
            image_interp="cubic",
            border="mean",
            res=256,
        )
        for line_number, line in enumerate(axis.lines):
            if line_number == 0:
                line.set_markersize(8.0)
                line.set_markeredgewidth(0)
                line.set_color("#2F2F2F")
                line.set_alpha(0.82)
            elif line_number in (1, 2):
                line.set_linewidth(4.0)
                line.set_color("#303030")
            else:
                line.set_visible(False)
        colorbar = figure.colorbar(image, ax=axis, fraction=0.080, pad=0.10, aspect=12, shrink=0.94)
        colorbar.set_ticks([-limit, 0, limit])
        colorbar.set_label(TOPOGRAPHY_LABEL, fontsize=18, rotation=270, labelpad=28)
        colorbar.ax.tick_params(labelsize=24, width=1.5, length=7)
    figure.subplots_adjust(left=0.018, right=0.99, top=0.86, bottom=0.08, wspace=0.62)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return limit


def output_directories(output_root: Path, product_dir: str) -> dict[str, Path]:
    root = output_root / "Phase4_脳波解析" / "No1_sub_FmThetaChange"
    product = root / product_dir
    return {
        "root": root,
        "individual": product / "Individual",
        "grand": product / "GrandAverage",
        "quantification": product / "SetQuantification",
        "topography_individual": product / "Topography" / "Individual",
        "topography_grand": product / "Topography" / "GrandAverage",
        "baseline_tables": root / "Sub" / "tables" / "Set1Baseline",
        "grand_tables": root / "Sub" / "tables" / "GrandAverage",
        "quantification_tables": root / "Sub" / "tables" / "SetQuantification",
        "topography_tables": root / "Sub" / "tables" / "Topography",
        "logs": root / "Sub" / "logs",
    }


def load_pair_item(spec: no1.ParticipantSpec, cache_root: Path) -> dict[str, Any]:
    first = no1.load_session_cache(no1.cache_path(cache_root, spec, spec.first_session_id))
    second = no1.load_session_cache(no1.cache_path(cache_root, spec, spec.second_session_id))
    by_id = {
        first.session_id: make_change_session(first),
        second.session_id: make_change_session(second),
    }
    return {
        "spec": spec,
        "product_dir": no1.normalize_product(spec.product)[0],
        "eye_drop": by_id[spec.drops_session_id],
        "control": by_id[spec.control_session_id],
    }


def preflight(
    specs: list[no1.ParticipantSpec], cache_root: Path, production: bool
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    no1.validate_participant_specs(specs, production_batch=production)
    excluded: list[dict[str, str]] = []
    items: list[dict[str, Any]] = []
    for spec in specs:
        paths = [
            no1.cache_path(cache_root, spec, session_id)
            for session_id in (spec.first_session_id, spec.second_session_id)
        ]
        for path in paths:
            if not path.is_file():
                raise FileNotFoundError(f"No1 cache is absent: {path}")
            no1.validate_cache(path)
        if spec.pair_id == SET1_MISSING_PAIR_ID:
            first = no1.load_session_cache(paths[0])
            second = no1.load_session_cache(paths[1])
            missing = [session.session_id for session in (first, second) if 1 not in session.sets]
            if missing != ["109"]:
                raise ValueError(f"Pair {spec.pair_id}: unexpected Set 1 availability")
            excluded.append(
                {"pair_id": spec.pair_id, "reason": "ID109 Set 1 absent; baseline unavailable"}
            )
            continue
        items.append(load_pair_item(spec, cache_root))
    if production and len(items) != no1.PRODUCTION_PARTICIPANT_COUNT - 1:
        raise ValueError(f"Expected 39 analysable pairs after Set 1 exclusion, found {len(items)}")
    summary = {
        "requested_pairs": len(specs),
        "analysable_pairs": len(items),
        "excluded_pairs": excluded,
        "cache_root": str(cache_root),
        "baseline_definition": "finite post-mask unsmoothed Set 1 mean per session ID and channel",
    }
    return items, summary


def baseline_table(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        for condition, session in (("Eye Drop", item["eye_drop"]), ("Control", item["control"])):
            for channel, value in zip(
                session.channel_names, session.baseline_by_channel, strict=True
            ):
                rows.append(
                    {
                        "PairID": item["spec"].pair_id,
                        "SessionID": session.session_id,
                        "Condition": condition,
                        "Product": item["product_dir"],
                        "Channel": channel,
                        "Set1Baseline_PSD_uV2_per_Hz": value,
                    }
                )
    return pd.DataFrame(rows)


def write_individual(item: dict[str, Any], output_root: Path) -> dict[str, str]:
    spec = item["spec"]
    paths = output_directories(output_root, item["product_dir"])
    individual = paths["individual"] / f"ID{spec.pair_id}_No1_sub_FmThetaChange_Individual.png"
    topography = (
        paths["topography_individual"] / f"ID{spec.pair_id}_No1_sub_FmThetaChange_Topography.png"
    )
    plot_individual(item, individual)
    plot_topography(pair_topography_values(item), topography)
    return {"individual": str(individual), "topography": str(topography)}


def write_group(items: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
    products = sorted({item["product_dir"] for item in items})
    grand_by_product: dict[str, pd.DataFrame] = {}
    for product in products:
        grand, _ = build_grand_average(items, product)
        grand_by_product[product] = grand
    common_limit, common_ticks = grand_average_axis(list(grand_by_product.values()))
    outputs: dict[str, Any] = {}
    for product in products:
        paths = output_directories(output_root, product)
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        for legacy_path in (
            paths["quantification"]
            / f"No1_sub_FmThetaChange_Sets2to6Quantification_{product}.png",
            paths["quantification_tables"]
            / f"No1_sub_FmThetaChange_Sets2to6Quantification_Statistics_{product}.csv",
        ):
            legacy_path.unlink(missing_ok=True)
        grand = grand_by_product[product]
        grand_png = paths["grand"] / f"No1_sub_FmThetaChange_GrandAverage_{product}.png"
        grand_csv = (
            paths["grand_tables"] / f"No1_sub_FmThetaChange_GrandAverage_Values_{product}.csv"
        )
        plot_grand_average(
            grand, product, grand_png, common_limit=common_limit, common_ticks=common_ticks
        )
        grand.to_csv(grand_csv, index=False)

        quant = build_quantification(items, product)
        set_stats, overall_stats = quantification_statistics(quant)
        quant_png = (
            paths["quantification"] / f"No1_sub_FmThetaChange_SetQuantification_{product}.png"
        )
        overall_png = (
            paths["quantification"] / f"No1_sub_FmThetaChange_AllSetsQuantification_{product}.png"
        )
        plot_quantification(quant, set_stats, product, quant_png)
        plot_overall_quantification(quant, overall_stats, product, overall_png)
        quant.to_csv(
            paths["quantification_tables"]
            / f"No1_sub_FmThetaChange_Quantification_Values_{product}.csv",
            index=False,
        )
        set_stats.to_csv(
            paths["quantification"]
            / f"No1_sub_FmThetaChange_SetQuantification_Statistics_{product}.csv",
            index=False,
        )
        overall_stats.to_csv(
            paths["quantification_tables"]
            / f"No1_sub_FmThetaChange_AllSetsQuantification_Statistics_{product}.csv",
            index=False,
        )

        selected = [item for item in items if item["product_dir"] == product]
        pair_values = np.stack([pair_topography_values(item) for item in selected])
        group = np.full(pair_values.shape[1:], np.nan)
        valid_n = np.zeros(N_SETS, dtype=int)
        for index in range(N_SETS):
            valid = np.isfinite(pair_values[:, index, :]).all(axis=1)
            valid_n[index] = int(valid.sum())
            if valid.any():
                group[index] = pair_values[valid, index].mean(axis=0)
        topo_png = (
            paths["topography_grand"]
            / f"No1_sub_FmThetaChange_Topography_GrandAverage_{product}.png"
        )
        plot_topography(group, topo_png)
        topo_frame = pd.DataFrame(group, columns=no1.EXPECTED_CHANNEL_NAMES)
        topo_frame.insert(0, "Set", np.arange(1, N_SETS + 1))
        topo_frame.insert(1, "Valid_N", valid_n)
        topo_frame.to_csv(
            paths["topography_tables"]
            / f"No1_sub_FmThetaChange_Topography_GrandAverage_Values_{product}.csv",
            index=False,
        )
        outputs[product] = {
            "grand_average": str(grand_png),
            "set_quantification": str(quant_png),
            "all_sets_quantification": str(overall_png),
            "topography": str(topo_png),
        }
    return outputs


def git_revision() -> str:
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repository, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def write_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", action="append", type=no1.parse_participant, default=[])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--production-batch", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--individual-only", action="store_true")
    modes.add_argument("--group-outputs-only", action="store_true")
    modes.add_argument("--all", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = list(args.participant)
    if args.manifest:
        specs.extend(no1.load_manifest(args.manifest))
    if not specs:
        raise SystemExit("Provide --participant or --manifest")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    items, preflight_summary = preflight(specs, args.cache_root, args.production_batch)
    logging.info("No1_sub preflight passed: %s", json.dumps(preflight_summary, ensure_ascii=False))
    if args.preflight_only:
        return 0

    baseline_path = (
        output_directories(args.output_root, "CCube")["baseline_tables"]
        / "No1_sub_FmThetaChange_Set1Baseline_AllAnalysablePairs.csv"
    )
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_table(items).to_csv(baseline_path, index=False)

    individual_outputs: dict[str, Any] = {}
    if args.individual_only or args.all:
        for item in items:
            individual_outputs[item["spec"].pair_id] = write_individual(item, args.output_root)
        if args.individual_only:
            log = (
                output_directories(args.output_root, "CCube")["logs"]
                / "No1_sub_FmThetaChange_IndividualSummary.json"
            )
            write_log(
                log,
                {
                    "script_version": SCRIPT_VERSION,
                    "git_commit": git_revision(),
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "mode": "individual-only",
                    "preflight": preflight_summary,
                    "outputs": individual_outputs,
                },
            )
            return 0

    group_outputs: dict[str, Any] = {}
    if args.group_outputs_only or args.all:
        group_outputs = write_group(items, args.output_root)

    log = (
        output_directories(args.output_root, "CCube")["logs"]
        / "No1_sub_FmThetaChange_RunSummary.json"
    )
    write_log(
        log,
        {
            "script_version": SCRIPT_VERSION,
            "git_commit": git_revision(),
            "completed_at": datetime.now().astimezone().isoformat(),
            "mode": "all" if args.all else "group-outputs-only",
            "preflight": preflight_summary,
            "individual_outputs": individual_outputs,
            "group_outputs": group_outputs,
        },
    )
    logging.info("No1_sub outputs completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
