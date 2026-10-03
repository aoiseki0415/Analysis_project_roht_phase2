"""Shared paired-test and multiple-comparison utilities for analysis figures."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from matplotlib.axes import Axes
from matplotlib.transforms import blended_transform_factory
from scipy.stats import t as student_t
from scipy.stats import ttest_rel


def quantification_axis_layout(
    values: np.ndarray,
    *,
    minimum_upper: float,
    integer_ticks: bool = False,
) -> tuple[float, np.ndarray, float, float, float]:
    """Place data, statistics, set label, and top margin from one data maximum."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    observed_max = float(np.max(finite)) if finite.size else 0.0
    reference_max = max(observed_max, float(minimum_upper) / 1.38)
    upper = reference_max * 1.38
    if integer_ticks:
        upper = float(np.ceil(upper))

    exponent = int(np.floor(np.log10(upper))) if upper > 0 else 0
    choices: list[tuple[float, float, np.ndarray]] = []
    for power in range(exponent - 2, exponent + 2):
        scale = 10.0**power
        for multiplier in (1.0, 2.0, 2.5, 5.0, 10.0):
            step = multiplier * scale
            if integer_ticks and step < 1.0:
                continue
            ticks = np.arange(0.0, upper + step * 0.01, step)
            if 3 <= ticks.size <= 6:
                choices.append((abs(ticks.size - 5), step, ticks))
    if choices:
        _, _, ticks = min(choices, key=lambda item: (item[0], item[1]))
    else:
        ticks = np.linspace(0.0, upper, 5)

    bracket_line_y = 1.10 * reference_max / upper
    statistic_text_y = 1.14 * reference_max / upper
    set_label_y = 1.31 * reference_max / upper
    return upper, ticks, bracket_line_y, statistic_text_y, set_label_y


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
    fontsize: float | None = None,
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
    label_fontsize = fontsize if fontsize is not None else (30.0 if label == "n.s." else 42.0)
    optical_text_y = text_y if label == "n.s." else text_y - 0.018
    axis.text(
        (x_left + x_right) / 2.0,
        optical_text_y,
        label,
        transform=transform,
        ha="center",
        va="center",
        color="black",
        fontfamily="Arial",
        fontsize=label_fontsize,
        fontweight="bold" if label != "n.s." else "normal",
        clip_on=False,
        zorder=6,
    )
