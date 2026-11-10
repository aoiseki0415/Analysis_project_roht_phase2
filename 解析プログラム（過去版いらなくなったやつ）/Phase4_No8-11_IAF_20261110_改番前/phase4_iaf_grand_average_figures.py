"""Square No8–11 baseline-referenced IAF Grand-average figures.

The numerical engine supplies participant-averaged IAF differences and SEM.
This module neither estimates IAF nor smooths, interpolates, or imputes values.
The caller computes one shared limit from both cohorts within each No/product.
"""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import ticker  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from numpy.typing import ArrayLike  # noqa: E402
from phase4_iaf_figures import FIGURE_CONFIG as INDIVIDUAL_CONFIG  # noqa: E402
from phase4_iaf_figures import (  # noqa: E402
    PRODUCT_LABELS,
    require_arial,
)
from PIL import Image  # noqa: E402

FIGURE_CONFIG = {
    "version": "phase4-iaf-change-grand-average-2026-11-10-v1",
    "font": "Arial",
    "figure_inches": [10, 10],
    "dpi": 180,
    "pixels": [1800, 1800],
    "margins": {"left": 0.17, "right": 0.96, "bottom": 0.18, "top": 0.87},
    "axes_box_aspect": 1,
    "axis_label_pt": 28,
    "axis_label_pad": 14,
    "tick_label_pt": 20,
    "tick_length_pt": 6,
    "tick_width_pt": 1.5,
    "spine_width_pt": 1.5,
    "title_pt": 26,
    "title_pad": 20,
    "title_line_spacing": 1.3,
    "line_width_pt": 3,
    "marker_pt": 10,
    "marker_edge_pt": 1,
    "legend_pt": 17,
    "legend_handlelength": 2,
    "half_set_note_pt": 17,
    "half_set_note_xy": [0.5, 0.035],
    "shade": "mean ± SEM",
    "shade_alpha": 0.18,
    "symmetric_axis_fraction": 0.80,
    "zero_or_empty_y_limit_hz": 1.0,
    "tick_steps": [1, 2, 2.5, 5, 10],
    "control_color": INDIVIDUAL_CONFIG["control_color"],
    "eye_drop_colors": deepcopy(INDIVIDUAL_CONFIG["eye_drop_colors"]),
    "plotting_applies_smoothing": False,
    "plotting_applies_interpolation": False,
}

COHORT_LABELS = {
    "AllAvailable": "All available participants",
    "SelectedParticipants": "Selected participants",
}


def _mean_sem_arrays(mean: ArrayLike, sem: ArrayLike) -> tuple[np.ndarray, np.ndarray]:
    means, sems = np.asarray(mean, dtype=float), np.asarray(sem, dtype=float)
    if means.ndim != 1 or sems.shape != means.shape:
        raise ValueError("Mean and SEM must be matching one-dimensional arrays")
    if np.isinf(means).any() or np.isinf(sems).any():
        raise ValueError("Infinite group means or SEM are not valid")
    if np.any(sems[np.isfinite(sems)] < 0):
        raise ValueError("SEM must be nonnegative or NaN")
    if np.any(np.isfinite(sems) & ~np.isfinite(means)):
        raise ValueError("A missing mean cannot have a finite SEM")
    return means, sems


def shared_y_limit(series: Iterable[tuple[ArrayLike, ArrayLike]]) -> float:
    """Return the common symmetric half-range for all/selected, both conditions.

    The largest absolute mean ± SEM is placed at 80% of the distance from zero
    to either limit. A mean with undefined SEM (e.g. N=1) still enters the
    limit, without treating its undefined uncertainty as zero for drawing.
    The ±1 Hz fallback is used only for entirely zero or absent information.
    """
    maximum = 0.0
    for mean, sem in series:
        means, sems = _mean_sem_arrays(mean, sem)
        finite_mean = np.isfinite(means)
        if finite_mean.any():
            maximum = max(maximum, float(np.max(np.abs(means[finite_mean]))))
        finite_sem = finite_mean & np.isfinite(sems)
        if finite_sem.any():
            endpoints = np.concatenate([
                means[finite_sem] - sems[finite_sem], means[finite_sem] + sems[finite_sem],
            ])
            maximum = max(maximum, float(np.max(np.abs(endpoints))))
    if maximum == 0:
        return FIGURE_CONFIG["zero_or_empty_y_limit_hz"]
    return maximum / FIGURE_CONFIG["symmetric_axis_fraction"]


def _symmetric_ticks(limit: float) -> np.ndarray:
    """Keep exact data-derived limits with 3–6 nice, symmetric visible ticks."""
    for nbins in (5, 4, 6, 3):
        candidates = ticker.MaxNLocator(
            nbins=nbins, steps=FIGURE_CONFIG["tick_steps"], symmetric=True
        ).tick_values(-limit, limit)
        visible = candidates[(candidates >= -limit) & (candidates <= limit)]
        if 3 <= visible.size <= 6 and np.allclose(visible, -visible[::-1]):
            return visible
    raise ValueError(f"Cannot construct 3–6 symmetric ticks for ±{limit} Hz")


def build_grand_average_figure(
    *,
    analysis_number: int,
    product: str,
    cohort: str,
    drops_mean_hz: ArrayLike,
    drops_sem_hz: ArrayLike,
    control_mean_hz: ArrayLike,
    control_sem_hz: ArrayLike,
    y_limit_hz: float,
) -> Figure:
    """Build a square figure without writing; the caller owns and closes it."""
    require_arial()
    if analysis_number not in (8, 9, 10, 11):
        raise ValueError("Only No8, No9, No10 and No11 are supported")
    if product not in PRODUCT_LABELS or cohort not in COHORT_LABELS:
        raise ValueError("Unknown product or Grand-average cohort")
    count = 12 if analysis_number in (9, 11) else 6
    data = [
        _mean_sem_arrays(drops_mean_hz, drops_sem_hz),
        _mean_sem_arrays(control_mean_hz, control_sem_hz),
    ]
    if any(mean.shape != (count,) for mean, _ in data):
        raise ValueError(f"No{analysis_number} requires exactly {count} interval values")
    if not np.array_equal(np.isfinite(data[0][0]), np.isfinite(data[1][0])):
        raise ValueError("Both conditions must have the same paired interval availability")
    if not np.isfinite(y_limit_hz) or y_limit_hz <= 0:
        raise ValueError("The symmetric y limit must be finite and positive")
    required = shared_y_limit(data) * FIGURE_CONFIG["symmetric_axis_fraction"]
    if any(np.isfinite(mean).any() for mean, _ in data) and required > y_limit_hz + 1e-12:
        raise ValueError("The supplied y limit would clip a mean or SEM endpoint")
    channel = "Pz" if analysis_number in (8, 9) else "Fz"
    palette = [
        FIGURE_CONFIG["eye_drop_colors"][analysis_number][product],
        FIGURE_CONFIG["control_color"],
    ]
    labels = [f"Eye Drop ({PRODUCT_LABELS[product]})", "Control"]
    rc = {
        "font.family": "Arial", "font.size": 20, "axes.linewidth": 1.5,
        "mathtext.fontset": "custom", "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic", "mathtext.bf": "Arial:bold",
        "axes.unicode_minus": True,
    }
    with matplotlib.rc_context(rc):
        fig, ax = plt.subplots(figsize=FIGURE_CONFIG["figure_inches"], dpi=180, facecolor="white")
        fig.subplots_adjust(**FIGURE_CONFIG["margins"])
        ax.set_box_aspect(1)
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_linewidth(1.5)
        ax.tick_params(labelsize=20, width=1.5, length=6)
        x = np.arange(1, count + 1)
        for (mean, sem), color, label in zip(data, palette, labels, strict=True):
            # Matplotlib keeps NaNs as disconnected segments. In particular,
            # undefined SEM is not rendered as if it were zero uncertainty.
            ax.fill_between(
                x, mean - sem, mean + sem, color=color,
                alpha=FIGURE_CONFIG["shade_alpha"], linewidth=0, zorder=1,
            )
            ax.plot(
                x, mean, "-o", color=color, lw=3, markersize=10,
                markeredgecolor="white", markeredgewidth=1, label=label, zorder=2,
            )
        ax.set(
            xlim=(0.75, count + 0.25), ylim=(-y_limit_hz, y_limit_hz), xticks=x,
            yticks=_symmetric_ticks(y_limit_hz),
        )
        if count == 12:
            ax.set_xticklabels([f"{number}{half}" for number in range(1, 7) for half in ("a", "b")])
        ax.set_xlabel("Set / Half" if count == 12 else "Set", fontsize=28, labelpad=14)
        ax.set_ylabel("IAF Change (Hz)", fontsize=28, labelpad=14)
        ax.set_title(
            f"{channel} — {PRODUCT_LABELS[product]}\n{COHORT_LABELS[cohort]}",
            fontsize=26, pad=20, linespacing=FIGURE_CONFIG["title_line_spacing"],
        )
        ax.legend(loc="upper right", frameon=False, fontsize=17, handlelength=2)
        formatter = ticker.ScalarFormatter(useOffset=False)
        formatter.set_scientific(False)
        ax.yaxis.set_major_formatter(formatter)
        if count == 12:
            fig.text(
                *FIGURE_CONFIG["half_set_note_xy"],
                "a: first half (0–50%)  |  b: second half (50–100%)",
                ha="center", fontsize=17,
            )
        if not any(np.isfinite(mean).any() for mean, _ in data):
            ax.text(
                0.5, 0.35, "No available paired IAF change", ha="center", va="center",
                transform=ax.transAxes, fontsize=17,
            )
        fig.canvas.draw()
    return fig


def plot_grand_average(
    *,
    output_path: Path,
    analysis_number: int,
    product: str,
    cohort: str,
    drops_mean_hz: ArrayLike,
    drops_sem_hz: ArrayLike,
    control_mean_hz: ArrayLike,
    control_sem_hz: ArrayLike,
    y_limit_hz: float,
) -> dict:
    """Write/read back one 1800×1800 PNG and close the figure in all cases."""
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".png":
        raise ValueError("Grand-average results must be PNG files")
    fig = build_grand_average_figure(
        analysis_number=analysis_number, product=product, cohort=cohort,
        drops_mean_hz=drops_mean_hz, drops_sem_hz=drops_sem_hz,
        control_mean_hz=control_mean_hz, control_sem_hz=control_sem_hz,
        y_limit_hz=y_limit_hz,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with matplotlib.rc_context({"savefig.bbox": None}):
            fig.savefig(output_path, dpi=180, facecolor="white", bbox_inches=None)
        with Image.open(output_path) as png:
            png.load()
            dimensions = list(png.size)
        if dimensions != FIGURE_CONFIG["pixels"]:
            raise RuntimeError(f"Unexpected Grand-average figure dimensions: {dimensions}")
        return {
            "figure": str(output_path), "figure_style_version": FIGURE_CONFIG["version"],
            "font_file": require_arial(), "dimensions_px": dimensions,
            "analysis_number": analysis_number, "product": product, "cohort": cohort,
            "channel": "Pz" if analysis_number in (8, 9) else "Fz",
            "interval_count": 12 if analysis_number in (9, 11) else 6,
            "y_limits_hz": list(fig.axes[0].get_ylim()),
            "y_ticks_hz": fig.axes[0].get_yticks().tolist(),
            "eye_drop_color": FIGURE_CONFIG["eye_drop_colors"][analysis_number][product],
            "control_color": FIGURE_CONFIG["control_color"],
            "shade": FIGURE_CONFIG["shade"], "shade_alpha": FIGURE_CONFIG["shade_alpha"],
            "plotting_applies_smoothing": False, "plotting_applies_interpolation": False,
        }
    finally:
        plt.close(fig)
