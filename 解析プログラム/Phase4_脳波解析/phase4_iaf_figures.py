"""Individual-only IAF figures for Phase 4 No8--No11.

Numerical estimation belongs to the common IAF engine.  This module only renders
the supplied estimates, preserves missing values, and never bridges Set borders.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from matplotlib.lines import Line2D

CONTROL_COLOR = "#402B5D"
SETWISE_COLORS = {"CCube": "#00616B", "VRohtoPremium": "#008F95"}
TIME_RESOLVED_COLORS = {"CCube": "#405A8C", "VRohtoPremium": "#718FB8"}
PRODUCT_LABELS = {"CCube": "C Cube", "VRohtoPremium": "V Rohto Premium"}
CHANNELS = {8: "Pz", 9: "Pz", 10: "Fz", 11: "Fz"}
Y_LIMITS = (7.5, 15.5)
Y_TICKS = (8, 10, 12, 14)
DPI = 180


def _require_arial() -> str:
    """Fail explicitly instead of silently substituting another font."""
    path = font_manager.findfont(
        font_manager.FontProperties(family=["Arial"]), fallback_to_default=False
    )
    family = font_manager.FontProperties(fname=path).get_name()
    if family != "Arial":
        raise RuntimeError(f"Arial required; font resolver returned {family!r}: {path}")
    return path


def _prepare_axis(axis: Any, *, time_resolved: bool) -> None:
    axis.set_ylim(*Y_LIMITS)
    axis.set_yticks(Y_TICKS)
    axis.set_ylabel("IAF (Hz)", fontsize=28, labelpad=16)
    axis.tick_params(axis="both", labelsize=20, length=6, width=1.5)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    if time_resolved:
        axis.set_xlim(0, 600)
        axis.set_xticks(np.arange(0, 601, 50))
        axis.set_xlabel("Experimental Progress, %", fontsize=28, labelpad=18)
        for boundary in range(100, 600, 100):
            axis.axvline(boundary, color="#B8B8B8", linestyle="--", linewidth=1.4)
        for set_number in range(1, 7):
            axis.text(
                100 * (set_number - 0.5),
                15.18,
                f"Set {set_number}",
                ha="center",
                va="top",
                fontsize=22,
                fontfamily="Arial",
            )
    else:
        axis.set_xlim(0.75, 6.25)
        axis.set_xticks(range(1, 7))
        axis.set_xlabel("Set", fontsize=28, labelpad=18)


def _validate_rows(
    rows: list[dict[str, Any]], specs: list[Any], analysis_number: int
) -> dict[str, list[dict[str, Any]]]:
    if analysis_number not in CHANNELS:
        raise ValueError("analysis_number must be 8, 9, 10, or 11")
    spec_by_pair = {str(spec.pair_id): spec for spec in specs}
    if len(spec_by_pair) != len(specs):
        raise ValueError("Duplicate participant pairs")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        pair_id = str(row["pair_id"])
        if pair_id not in spec_by_pair:
            raise ValueError(f"Unexpected participant pair: {pair_id}")
        spec = spec_by_pair[pair_id]
        if str(row["channel"]) != CHANNELS[analysis_number]:
            raise ValueError(f"No{analysis_number} received an incorrect channel")
        product = str(row["product"])
        if product not in PRODUCT_LABELS or product != str(spec.product):
            raise ValueError(f"Product mismatch for pair {pair_id}")
        session_id = str(row["session_id"])
        if session_id not in {str(spec.first_session_id), str(spec.second_session_id)}:
            raise ValueError(f"Session does not belong to pair {pair_id}")
        expected_condition = "Eye Drop" if session_id == str(spec.drops_session_id) else "Control"
        if str(row["condition"]) != expected_condition:
            raise ValueError(f"Condition mismatch for pair {pair_id}")
        if int(row["set_number"]) not in range(1, 7):
            raise ValueError("Set number must be between 1 and 6")
        frequency = float(row["frequency_hz"])
        if np.isinf(frequency):
            raise ValueError("Infinite IAF is not a valid estimate")
        if np.isfinite(frequency):
            if not 8 - 1e-9 <= frequency <= 15 + 1e-9:
                raise ValueError("IAF lies outside the specified 8--15 Hz band")
            if str(row["quality"]) != "ok":
                raise ValueError("An unavailable estimate must be NaN")
        grouped[pair_id].append(row)
    for pair_id in spec_by_pair:
        for condition in ("Eye Drop", "Control"):
            present = {
                int(row["set_number"]) for row in grouped[pair_id] if row["condition"] == condition
            }
            if present != set(range(1, 7)):
                raise ValueError(f"Missing Set rows/sentinels for pair {pair_id}, {condition}")
    return grouped


def _plot_condition(
    axis: Any,
    rows: list[dict[str, Any]],
    condition: str,
    color: str,
    *,
    time_resolved: bool,
) -> None:
    selected = [row for row in rows if row["condition"] == condition]
    if not time_resolved:
        selected.sort(key=lambda row: int(row["set_number"]))
        if len(selected) != 6:
            raise ValueError("Setwise IAF requires exactly one row per Set and session")
        axis.plot(
            [int(row["set_number"]) for row in selected],
            [float(row["frequency_hz"]) for row in selected],
            color=color,
            linewidth=3,
            marker="o",
            markersize=9,
            markeredgecolor="white",
            markeredgewidth=1.2,
        )
        return

    for set_number in range(1, 7):
        segment = [row for row in selected if int(row["set_number"]) == set_number]
        segment = [row for row in segment if np.isfinite(float(row["progress"]))]
        segment.sort(key=lambda row: float(row["center_seconds"]))
        if not segment:
            continue
        times = np.asarray([float(row["center_seconds"]) for row in segment])
        progress = np.asarray([float(row["progress"]) for row in segment])
        frequencies = np.asarray([float(row["frequency_hz"]) for row in segment])
        if np.any(np.diff(times) <= 0) or np.any(np.diff(progress) <= 0):
            raise ValueError("IAF time/progress coordinates must increase within each Set")
        if np.any(progress < 100 * (set_number - 1) - 1e-7) or np.any(
            progress > 100 * set_number + 1e-7
        ):
            raise ValueError("IAF progress is outside its Set")
        # No9/No11 should contain every 5-second position, including NaN estimates.
        # Also split unexpected time gaps defensively rather than joining them.
        breaks = np.flatnonzero(np.diff(times) > 5.0 + 1e-6) + 1
        for indices in np.split(np.arange(len(segment)), breaks):
            axis.plot(
                progress[indices],
                frequencies[indices],
                color=color,
                linewidth=3,
                marker="o",
                markersize=2.5,
                markeredgewidth=0,
            )


def render_analysis(
    rows: list[dict[str, Any]],
    specs: list[Any],
    output_dir: Path,
    analysis_number: int,
) -> list[Path]:
    """Render one Eye Drop/Control PNG per pair under product/Individual.

    ``rows`` must contain only this analysis's channel and estimation method.
    Missing estimates remain NaN; missing Sets must have explicit sentinel rows.
    ``output_dir`` is the analysis root authorized/validated by the caller.
    """
    _require_arial()
    grouped = _validate_rows(rows, specs, analysis_number)
    time_resolved = analysis_number in (9, 11)
    method = "TimeResolvedIAF" if time_resolved else "SetwiseIAF"
    colors = TIME_RESOLVED_COLORS if time_resolved else SETWISE_COLORS
    channel = CHANNELS[analysis_number]
    destinations: list[Path] = []
    style = {
        "font.family": "Arial",
        "axes.linewidth": 1.5,
        "axes.unicode_minus": True,
        "savefig.facecolor": "white",
    }
    with plt.rc_context(style):
        for spec in specs:
            pair_id = str(spec.pair_id)
            product = str(spec.product)
            pair_rows = grouped[pair_id]
            figure, axis = plt.subplots(figsize=(24, 8) if time_resolved else (12, 8))
            try:
                _prepare_axis(axis, time_resolved=time_resolved)
                _plot_condition(
                    axis, pair_rows, "Eye Drop", colors[product], time_resolved=time_resolved
                )
                _plot_condition(
                    axis, pair_rows, "Control", CONTROL_COLOR, time_resolved=time_resolved
                )
                handles = [
                    Line2D([0], [0], color=colors[product], linewidth=3),
                    Line2D([0], [0], color=CONTROL_COLOR, linewidth=3),
                ]
                axis.legend(
                    handles,
                    [f"Eye Drop ({PRODUCT_LABELS[product]})", "Control"],
                    loc="upper center",
                    bbox_to_anchor=(0.5, 1.18),
                    ncol=2,
                    frameon=False,
                    fontsize=20,
                )
                axis.set_title(channel, loc="left", fontsize=22, pad=10)
                if not any(np.isfinite(float(row["frequency_hz"])) for row in pair_rows):
                    axis.text(
                        0.5,
                        0.5,
                        "No valid peak estimates",
                        transform=axis.transAxes,
                        ha="center",
                        va="center",
                        fontsize=20,
                        color="#666666",
                    )
                figure.subplots_adjust(left=0.09, right=0.985, top=0.78, bottom=0.20)
                destination = (
                    Path(output_dir)
                    / product
                    / "Individual"
                    / f"Pair{pair_id}_No{analysis_number}_{channel}_{method}.png"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                figure.savefig(destination, dpi=DPI, bbox_inches="tight")
                destinations.append(destination)
            finally:
                plt.close(figure)
    return destinations
