"""Current No8–11 three-panel IAF figures; no spectral calculations.

All inputs are the already validated linear, interval-mean PSD and its selected
local alpha peak. Plotting neither smooths the spectra nor imputes missing data.
"""

from __future__ import annotations

import colorsys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib import colors, font_manager, ticker  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from numpy.typing import ArrayLike  # noqa: E402
from PIL import Image  # noqa: E402

FIGURE_CONFIG = {
    "version": "phase4-iaf-threepanel-2026-11-10-v2",
    "font": "Arial",
    "figure_inches": [27, 10],
    "dpi": 180,
    "pixels": [4860, 1800],
    "margins": {"left": 0.052, "right": 0.985, "bottom": 0.19, "top": 0.88, "wspace": 0.30},
    "axis_label_pt": 28,
    "axis_label_pad": 14,
    "tick_label_pt": 20,
    "tick_length_pt": 6,
    "tick_width_pt": 1.5,
    "spine_width_pt": 1.5,
    "title_pt": 26,
    "title_pad": 20,
    "psd_line_width_pt": 2.5,
    "psd_peak_axis_fraction": 0.80,
    "psd_legend_pt": 18,
    "psd_legend_labelspacing": 0.30,
    "psd_legend_handlelength": 1.7,
    "psd_legend_columnspacing": 0.8,
    "psd_display_hz": [1, 30],
    "psd_ticks_hz": [1, 5, 10, 15, 20, 25, 30],
    "psd_axis_scale": "linear",
    "psd_scientific_powerlimits": [-3, 4],
    "alpha_edges_hz": [8, 15],
    "alpha_boundary_color": "#888888",
    "alpha_boundary_width_pt": 1.5,
    "iaf_ylim_hz": [7.5, 15.5],
    "iaf_ticks_hz": list(range(8, 16)),
    "iaf_line_width_pt": 3,
    "iaf_marker_pt": 10,
    "iaf_marker_edge_pt": 1,
    "iaf_legend_pt": 17,
    "half_set_note_pt": 17,
    "lightness_first": 0.80,
    "lightness_span": 0.58,
    "control_color": "#402B5D",
    "eye_drop_colors": {
        8: {"CCube": "#2456A6", "VRohtoPremium": "#5689CF"},
        9: {"CCube": "#23734B", "VRohtoPremium": "#53A078"},
        10: {"CCube": "#A63D46", "VRohtoPremium": "#CF7278"},
        11: {"CCube": "#79543A", "VRohtoPremium": "#AC8058"},
    },
}

PRODUCT_LABELS = {"CCube": "C Cube", "VRohtoPremium": "V Rohto Premium"}


def require_arial() -> str:
    """Resolve the actual Arial font, rejecting silent platform fallback."""
    path = font_manager.findfont(
        font_manager.FontProperties(family="Arial"), fallback_to_default=False
    )
    if font_manager.FontProperties(fname=path).get_name() != "Arial":
        raise RuntimeError(f"Arial is required; font resolver returned {path}")
    return path


def segment_colors(base_color: str, count: int) -> list[tuple[float, float, float]]:
    """Keep hue/saturation and use the specified bright-to-dark HLS gradient."""
    if count not in (6, 12):
        raise ValueError("IAF figures require exactly 6 or 12 intervals")
    hue, _, saturation = colorsys.rgb_to_hls(*colors.to_rgb(base_color))
    return [
        colorsys.hls_to_rgb(hue, 0.80 - 0.58 * index / (count - 1), saturation)
        for index in range(count)
    ]


def _interval_labels(count: int) -> list[str]:
    if count == 6:
        return [f"Set {index}" for index in range(1, 7)]
    return [f"Set {index}{half}" for index in range(1, 7) for half in ("a", "b")]


def _validate_inputs(
    analysis_number: int,
    product: str,
    frequencies_hz: ArrayLike,
    drops_psd: ArrayLike,
    control_psd: ArrayLike,
    drops_iaf_hz: ArrayLike,
    control_iaf_hz: ArrayLike,
) -> tuple[np.ndarray, list[np.ndarray], list[np.ndarray], int]:
    if analysis_number not in (8, 9, 10, 11):
        raise ValueError("Only No8, No9, No10 and No11 are supported")
    if product not in PRODUCT_LABELS:
        raise ValueError(f"Unknown product: {product}")
    count = 12 if analysis_number in (9, 11) else 6
    frequencies = np.asarray(frequencies_hz, dtype=float)
    expected_frequencies = np.arange(10, 401, dtype=float) / 10
    if frequencies.shape != (391,) or not np.allclose(
        frequencies, expected_frequencies, rtol=0, atol=1e-10
    ):
        raise ValueError("Expected 391 frequency bins at 0.1 Hz from 1 to 40 Hz")
    spectra = [np.asarray(item, dtype=float) for item in (drops_psd, control_psd)]
    iafs = [np.asarray(item, dtype=float) for item in (drops_iaf_hz, control_iaf_hz)]
    for psd, iaf in zip(spectra, iafs, strict=True):
        if psd.shape != (count, 391) or iaf.shape != (count,):
            raise ValueError(f"Expected PSD shape ({count},391) and IAF shape ({count},)")
        if np.isinf(psd).any() or np.isinf(iaf).any():
            raise ValueError("Infinite values are not valid PSD/IAF results")
        if np.any(psd[np.isfinite(psd)] < 0):
            raise ValueError("Linear PSD cannot be negative")
        if np.any((iaf[np.isfinite(iaf)] < 8) | (iaf[np.isfinite(iaf)] > 15)):
            raise ValueError("Finite IAF must be within 8–15 Hz")
        missing_psd = ~np.any(np.isfinite(psd), axis=1)
        if np.any(np.isfinite(iaf[missing_psd])):
            raise ValueError("A missing PSD cannot have a finite IAF")
    return frequencies, spectra, iafs, count


def _psd_y_ticks(top: float) -> np.ndarray:
    """Keep the exact data-derived limit and 3–6 well-spaced visible ticks."""
    for nbins in (5, 4, 6, 3):
        proposed = ticker.MaxNLocator(nbins=nbins, steps=[1, 2, 2.5, 5, 10]).tick_values(
            0, top
        )
        visible = proposed[(proposed >= 0) & (proposed <= top)]
        if 3 <= len(visible) <= 6:
            return visible
    raise ValueError(f"Cannot construct 3–6 PSD tick labels for y upper limit {top}")


def build_three_panel_figure(
    *,
    analysis_number: int,
    product: str,
    frequencies_hz: ArrayLike,
    drops_psd: ArrayLike,
    control_psd: ArrayLike,
    drops_iaf_hz: ArrayLike,
    control_iaf_hz: ArrayLike,
) -> Figure:
    """Build the approved figure without writing files; caller owns the figure.

    PSD rows and IAF elements retain all 6/12 interval positions, including NaNs.
    The input arrays are never altered. In particular no paired-OR missingness is
    imposed: an available condition remains visible when its partner is missing.
    """
    require_arial()
    frequencies, spectra, iafs, count = _validate_inputs(
        analysis_number, product, frequencies_hz, drops_psd, control_psd,
        drops_iaf_hz, control_iaf_hz,
    )
    channel = "Pz" if analysis_number in (8, 9) else "Fz"
    drops_label = f"Eye Drop ({PRODUCT_LABELS[product]})"
    labels = _interval_labels(count)
    palette = [
        FIGURE_CONFIG["eye_drop_colors"][analysis_number][product],
        FIGURE_CONFIG["control_color"],
    ]
    rc = {
        "font.family": "Arial",
        "font.size": 20,
        "axes.linewidth": 1.5,
        "mathtext.fontset": "custom",
        "mathtext.rm": "Arial",
        "mathtext.it": "Arial:italic",
        "mathtext.bf": "Arial:bold",
        "axes.unicode_minus": True,
    }
    with matplotlib.rc_context(rc):
        fig, axes = plt.subplots(1, 3, figsize=(27, 10), dpi=180, facecolor="white")
        fig.subplots_adjust(**FIGURE_CONFIG["margins"])
        for ax in axes:
            ax.set_box_aspect(1)
            ax.spines[["top", "right"]].set_visible(False)
            ax.spines[["left", "bottom"]].set_linewidth(1.5)
            ax.tick_params(labelsize=20, width=1.5, length=6)
        displayed = (frequencies >= 1) & (frequencies <= 30)
        for ax, psd, base_color, title in zip(
            axes[:2], spectra, palette, [drops_label, "Control"], strict=True
        ):
            shades = segment_colors(base_color, count)
            for row, label, color in zip(psd, labels, shades, strict=True):
                display_label = label if np.isfinite(row).any() else f"{label} unavailable"
                ax.plot(
                    frequencies[displayed], row[displayed], color=color, lw=2.5,
                    alpha=1, label=display_label,
                )
            for edge in (8, 15):
                ax.axvline(edge, color="#888888", lw=1.5, linestyle=":", zorder=0)
            finite_values = psd[:, displayed][np.isfinite(psd[:, displayed])]
            maximum = float(finite_values.max()) if finite_values.size else np.nan
            top = maximum / 0.80 if maximum > 0 else 1.0
            ax.set(xlim=(1, 30), ylim=(0, top), xticks=[1, 5, 10, 15, 20, 25, 30])
            ax.set_yticks(_psd_y_ticks(top))
            formatter = ticker.ScalarFormatter(useOffset=False)
            # Scientific tick notation avoids clipping long numbers while the
            # axis, actual PSD values and exact M/0.80 upper limit remain linear.
            formatter.set_scientific(True)
            formatter.set_powerlimits(tuple(FIGURE_CONFIG["psd_scientific_powerlimits"]))
            ax.yaxis.set_major_formatter(formatter)
            ax.set_xlabel("Frequency (Hz)", fontsize=28, labelpad=14)
            ax.set_ylabel("PSD (µV²/Hz)", fontsize=28, labelpad=14)
            ax.set_title(title, fontsize=26, pad=20)
            handles, legend_labels = ax.get_legend_handles_labels()
            order = list(range(0, count, 2)) + list(range(1, count, 2)) if count == 12 else (
                list(range(count))
            )
            ax.legend(
                [handles[index] for index in order], [legend_labels[index] for index in order],
                loc="upper right", frameon=False, fontsize=18, handlelength=1.7,
                labelspacing=0.30, ncol=2 if count == 12 else 1, columnspacing=0.8,
            )
            if not finite_values.size or maximum == 0:
                message = "No usable PSD" if not finite_values.size else "Zero PSD"
                ax.text(0.5, 0.35, message, ha="center", va="center", transform=ax.transAxes)

        iaf_ax = axes[2]
        x = np.arange(1, count + 1)
        for iaf, color, condition in zip(iafs, palette, [drops_label, "Control"], strict=True):
            iaf_ax.plot(
                x, iaf, "-o", color=color, lw=3, markersize=10,
                markeredgecolor="white", markeredgewidth=1, label=condition,
            )
        iaf_ax.set(
            xlim=(0.75, count + 0.25), ylim=(7.5, 15.5), xticks=x, yticks=range(8, 16)
        )
        if count == 12:
            iaf_ax.set_xticklabels([label.removeprefix("Set ") for label in labels])
        iaf_ax.set_xlabel("Set / Half" if count == 12 else "Set", fontsize=28, labelpad=14)
        iaf_ax.set_ylabel("IAF (Hz)", fontsize=28, labelpad=14)
        iaf_ax.set_title(f"{channel} — Alpha Peak Frequency", fontsize=26, pad=20)
        iaf_ax.legend(loc="upper right", frameon=False, fontsize=17, handlelength=2)
        if count == 12:
            fig.text(
                0.5, 0.035, "a: first half (0–50%)  |  b: second half (50–100%)",
                ha="center", fontsize=17,
            )
        # Ensure newly instantiated tick texts acquire the same explicit font.
        fig.canvas.draw()
    return fig


def plot_pair_three_panel(
    *,
    output_path: Path,
    analysis_number: int,
    product: str,
    frequencies_hz: ArrayLike,
    drops_psd: ArrayLike,
    control_psd: ArrayLike,
    drops_iaf_hz: ArrayLike,
    control_iaf_hz: ArrayLike,
) -> dict:
    """Save a 4860×1800 PNG, read it back, close the figure, return audit metadata."""
    output_path = Path(output_path)
    if output_path.suffix.lower() != ".png":
        raise ValueError("Three-panel results must be PNG files")
    fig = build_three_panel_figure(
        analysis_number=analysis_number, product=product, frequencies_hz=frequencies_hz,
        drops_psd=drops_psd, control_psd=control_psd, drops_iaf_hz=drops_iaf_hz,
        control_iaf_hz=control_iaf_hz,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # An unrelated renderer may have set savefig.bbox='tight' globally.
        # Explicit rc isolation keeps our fixed canvas contract in that case.
        with matplotlib.rc_context({"savefig.bbox": None}):
            fig.savefig(output_path, dpi=180, facecolor="white", bbox_inches=None)
        with Image.open(output_path) as png:
            png.load()
            dimensions = list(png.size)
        if dimensions != FIGURE_CONFIG["pixels"]:
            raise RuntimeError(f"Unexpected IAF figure dimensions: {dimensions}")
        return {
            "figure": str(output_path),
            "figure_style_version": FIGURE_CONFIG["version"],
            "font_file": require_arial(),
            "dimensions_px": dimensions,
            "analysis_number": analysis_number,
            "channel": "Pz" if analysis_number in (8, 9) else "Fz",
            "product": product,
            "interval_count": 12 if analysis_number in (9, 11) else 6,
            "psd_y_limits": [list(ax.get_ylim()) for ax in fig.axes[:2]],
            "iaf_y_limits": list(fig.axes[2].get_ylim()),
            "missing_iaf_eye_drop": int(np.isnan(drops_iaf_hz).sum()),
            "missing_iaf_control": int(np.isnan(control_iaf_hz).sum()),
        }
    finally:
        plt.close(fig)
