"""Shared paired-test and multiple-comparison utilities for analysis figures."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.transforms import blended_transform_factory
from scipy.stats import t as student_t
from scipy.stats import ttest_rel


def paired_t_statistics(eye_drop: np.ndarray, control: np.ndarray) -> dict[str, float | int]:
    """Return a two-sided paired t-test and paired effect-size statistics."""

    eye_drop = np.asarray(eye_drop, dtype=float)
    control = np.asarray(control, dtype=float)
    paired = np.isfinite(eye_drop) & np.isfinite(control)
    eye_drop = eye_drop[paired]
    control = control[paired]
    n = int(eye_drop.size)
    if n < 2:
        return {
            "Paired_N": n,
            "T_statistic": np.nan,
            "Degrees_of_freedom": max(0, n - 1),
            "P_value_raw": np.nan,
            "Mean_difference_EyeDrop_minus_Control": np.nan,
            "Difference_SD": np.nan,
            "Difference_CI95_lower": np.nan,
            "Difference_CI95_upper": np.nan,
            "Cohen_dz": np.nan,
        }

    differences = eye_drop - control
    mean_difference = float(np.mean(differences))
    difference_sd = float(np.std(differences, ddof=1))
    if difference_sd == 0.0:
        if mean_difference == 0.0:
            t_statistic, p_value, cohen_dz = 0.0, 1.0, 0.0
        else:
            t_statistic = float(np.sign(mean_difference) * np.inf)
            p_value = 0.0
            cohen_dz = t_statistic
        ci_lower = ci_upper = mean_difference
    else:
        result = ttest_rel(eye_drop, control, nan_policy="omit")
        t_statistic = float(result.statistic)
        p_value = float(result.pvalue)
        standard_error = difference_sd / np.sqrt(n)
        margin = float(student_t.ppf(0.975, df=n - 1) * standard_error)
        ci_lower = mean_difference - margin
        ci_upper = mean_difference + margin
        cohen_dz = mean_difference / difference_sd
    return {
        "Paired_N": n,
        "T_statistic": t_statistic,
        "Degrees_of_freedom": n - 1,
        "P_value_raw": p_value,
        "Mean_difference_EyeDrop_minus_Control": mean_difference,
        "Difference_SD": difference_sd,
        "Difference_CI95_lower": ci_lower,
        "Difference_CI95_upper": ci_upper,
        "Cohen_dz": cohen_dz,
    }


def adjusted_p_values(p_values: Iterable[float], method: str) -> np.ndarray:
    """Adjust finite p-values with Bonferroni, Holm, or BH-FDR, preserving NaNs."""

    p_values = np.asarray(list(p_values), dtype=float)
    adjusted = np.full(p_values.shape, np.nan, dtype=float)
    finite_indices = np.flatnonzero(np.isfinite(p_values))
    finite = p_values[finite_indices]
    count = int(finite.size)
    if count == 0:
        return adjusted
    if method == "bonferroni":
        adjusted[finite_indices] = np.minimum(1.0, finite * count)
        return adjusted
    if method == "fdr_bh":
        order = np.argsort(finite)
        ordered = finite[order]
        ordered_adjusted = np.minimum.accumulate(
            (ordered * count / np.arange(1, count + 1))[::-1]
        )[::-1]
        ordered_adjusted = np.minimum(1.0, ordered_adjusted)
        restored = np.empty_like(ordered_adjusted)
        restored[order] = ordered_adjusted
        adjusted[finite_indices] = restored
        return adjusted
    if method != "holm":
        raise ValueError(f"Unsupported p-value adjustment method: {method}")

    order = np.argsort(finite)
    ordered = finite[order]
    ordered_adjusted = np.maximum.accumulate(
        [(count - rank) * value for rank, value in enumerate(ordered)]
    )
    ordered_adjusted = np.minimum(1.0, ordered_adjusted)
    restored = np.empty_like(ordered_adjusted)
    restored[order] = ordered_adjusted
    adjusted[finite_indices] = restored
    return adjusted


def significance_label(p_value: float) -> str:
    """Return the fixed figure label for an adjusted or unadjusted p-value."""

    if not np.isfinite(p_value):
        return "n.s."
    if p_value < 0.001:
        return "***"
    if p_value < 0.01:
        return "**"
    if p_value < 0.05:
        return "*"
    return "n.s."


def add_significance_bracket(
    axis: Axes,
    x_left: float,
    x_right: float,
    label: str,
    *,
    line_y: float = 0.75,
    text_y: float = 0.775,
    linewidth: float = 2.2,
    fontsize: float = 24.0,
) -> None:
    """Draw a black paired-comparison bracket at a fixed axes-relative height."""

    transform = blended_transform_factory(axis.transData, axis.transAxes)
    cap = 0.018
    axis.plot(
        [x_left, x_left, x_right, x_right],
        [line_y - cap, line_y, line_y, line_y - cap],
        color="black",
        linewidth=linewidth,
        transform=transform,
        clip_on=False,
        zorder=5,
    )
    axis.text(
        (x_left + x_right) / 2.0,
        text_y,
        label,
        transform=transform,
        ha="center",
        va="bottom",
        color="black",
        fontsize=fontsize,
        fontweight="bold" if label != "n.s." else "normal",
        clip_on=False,
        zorder=6,
    )
