#!/usr/bin/env python3
# ruff: noqa: E501
"""Phase 3 No1: detect blinks and calculate blink-rate change by participant pair."""

from __future__ import annotations

import argparse
import base64
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import h5py
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.signal import butter, find_peaks, peak_prominences, sosfiltfilt

N_SETS = 6
SFREQ = 256.0
FILTER_LOW_HZ = 1.0
FILTER_HIGH_HZ = 10.0
FILTER_ORDER = 4
MAD_NORMAL_CONSISTENCY = 1.4826
PROMINENCE_MAD_MULTIPLIER = 10.0
PROMINENCE_MULTIPLIER_BASIS = (
    "exploratory pilot comparison of k=8, 10, and 12 in four participant pairs "
    "(eight sessions); not a literature-recommended value"
)
PERCENTILE_THRESHOLD_REJECTION_REASON = (
    "A within-session percentile selects a similar upper fraction for every ID and can "
    "make extracted totals artificially similar across IDs, weakening genuine ID and "
    "condition differences."
)
MINIMUM_PEAK_DISTANCE_SECONDS = 0.100
MINIMUM_PEAK_WIDTH_SECONDS = 0.020
MAXIMUM_PEAK_WIDTH_SECONDS = 0.320
RATE_WINDOW_SECONDS = 60.0
RATE_STEP_SECONDS = 1.0
RATE_SMOOTHING_SECONDS = 15
CONTROL_COLOR = "#402B5D"
CONTROL_QUANTIFICATION_COLOR = "#66547D"
QUANTIFICATION_COLORS = {
    "CCube": "#4CA79E",
    "VRohtoPremium": "#62AFC6",
}
PRODUCTS = {
    "ccube": ("CCube", "C Cube", "#168C80", "Cキューブ"),
    "c_cube": ("CCube", "C Cube", "#168C80", "Cキューブ"),
    "cキューブ": ("CCube", "C Cube", "#168C80", "Cキューブ"),
    "vrohtopremium": ("VRohtoPremium", "V Rohto Premium", "#2A91B3", "Vロートプレミアム"),
    "v_rohto_premium": ("VRohtoPremium", "V Rohto Premium", "#2A91B3", "Vロートプレミアム"),
    "vロートプレミアム": ("VRohtoPremium", "V Rohto Premium", "#2A91B3", "Vロートプレミアム"),
}
DEFAULT_INPUT_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/"
    "Phase1_脳波前処理/No2_AutomatedPreProcessing"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/"
    "SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_本解析"
)


@dataclass(frozen=True)
class ParticipantSpec:
    first_session_id: str
    second_session_id: str
    drops_session_id: str
    product: str

    def __post_init__(self) -> None:
        if self.first_session_id == self.second_session_id:
            raise ValueError("The two session IDs must differ")
        if self.drops_session_id not in {self.first_session_id, self.second_session_id}:
            raise ValueError("drops_session_id must be one of the paired session IDs")
        normalize_product(self.product)

    @property
    def pair_id(self) -> str:
        return f"{self.first_session_id}-{self.second_session_id}"

    @property
    def control_session_id(self) -> str:
        return (
            self.second_session_id
            if self.drops_session_id == self.first_session_id
            else self.first_session_id
        )


@dataclass
class SetSignal:
    session_id: str
    set_number: int
    path: Path
    relative_seconds: np.ndarray
    original_timestamp: np.ndarray
    raw_uv: dict[str, np.ndarray]
    filtered_uv: dict[str, np.ndarray]
    peaks: dict[str, np.ndarray]

    @property
    def duration_seconds(self) -> float:
        if self.relative_seconds.size < 2:
            return 0.0
        return float(self.relative_seconds[-1] - self.relative_seconds[0] + 1.0 / SFREQ)


@dataclass
class SessionResult:
    session_id: str
    condition: str
    thresholds: dict[str, dict[str, float | None]]
    prominence_distributions: dict[str, np.ndarray]
    sets: dict[int, SetSignal]


def normalize_product(value: str) -> tuple[str, str, str, str]:
    key = value.strip().lower().replace(" ", "").replace("-", "")
    if key not in PRODUCTS:
        raise ValueError(f"Unknown product: {value}")
    return PRODUCTS[key]


def parse_participant(value: str) -> ParticipantSpec:
    parts = [item.strip() for item in value.split(":")]
    if len(parts) != 4 or not all(parts):
        raise argparse.ArgumentTypeError(
            "--participant must be first_session:second_session:drops_session:product"
        )
    return ParticipantSpec(*parts)


def load_manifest(path: Path) -> list[ParticipantSpec]:
    frame = pd.read_csv(path, dtype=str)
    required = ["first_session_id", "second_session_id", "drops_session_id", "product"]
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"Manifest is missing columns: {missing}")
    return [
        ParticipantSpec(*(str(row[column]).strip() for column in required))
        for _, row in frame.iterrows()
    ]


def _decode_names(values: np.ndarray) -> list[str]:
    return [item.decode("utf-8") if isinstance(item, bytes) else str(item) for item in values]


def load_set_signal(path: Path, session_id: str, set_number: int) -> SetSignal:
    with h5py.File(path, "r") as handle:
        sfreq = float(handle.attrs["sampling_frequency_hz"])
        if not np.isclose(sfreq, SFREQ):
            raise ValueError(f"{path}: sampling rate {sfreq} Hz, expected {SFREQ} Hz")
        if str(handle.attrs["signal_unit"]) != "V":
            raise ValueError(f"{path}: signal unit must be V")
        if str(handle.attrs["participant_id"]) != session_id:
            raise ValueError(f"{path}: participant_id mismatch")
        if int(handle.attrs["set_number"]) != set_number:
            raise ValueError(f"{path}: set_number mismatch")
        names = _decode_names(handle["signal/channel_names"][:])
        required = ["Fp1", "Fp2", "Fp1_Fp2_mean"]
        if names != required:
            raise ValueError(f"{path}: unexpected signal columns {names}")
        matrix_uv = handle["signal/data"][:].astype(np.float64) * 1e6
        relative = handle["time/relative_seconds"][:].astype(np.float64)
        original = handle["time/OriginalTimestamp"][:].astype(np.float64)
    if matrix_uv.shape != (relative.size, 3) or original.size != relative.size:
        raise ValueError(f"{path}: signal/time lengths do not match")
    if not np.isfinite(matrix_uv).all():
        raise ValueError(f"{path}: non-finite blink signal")
    sos = butter(
        FILTER_ORDER,
        [FILTER_LOW_HZ, FILTER_HIGH_HZ],
        btype="bandpass",
        fs=SFREQ,
        output="sos",
    )
    raw = {name: matrix_uv[:, index] for index, name in enumerate(names)}
    filtered = {name: sosfiltfilt(sos, values) for name, values in raw.items()}
    return SetSignal(session_id, set_number, path, relative, original, raw, filtered, {})


def input_path(root: Path, session_id: str, set_number: int) -> Path:
    return (
        root
        / f"ID{session_id}"
        / f"Set{set_number}"
        / f"ID{session_id}_Set{set_number}_blink_signal.h5"
    )


def calculate_session_thresholds(
    sets: dict[int, SetSignal],
    prominence_mad_multiplier: float = PROMINENCE_MAD_MULTIPLIER,
) -> tuple[dict[str, dict[str, float | None]], dict[str, np.ndarray]]:
    thresholds: dict[str, dict[str, float | None]] = {}
    distributions: dict[str, np.ndarray] = {}
    for channel in ("Fp1", "Fp2", "Fp1_Fp2_mean"):
        candidate_prominences: list[np.ndarray] = []
        for set_signal in sets.values():
            values = set_signal.filtered_uv[channel]
            candidates, _ = find_peaks(values)
            if candidates.size:
                candidate_prominences.append(peak_prominences(values, candidates)[0])
        if not candidate_prominences:
            raise ValueError(f"No local maxima available for {channel}")
        prominences = np.concatenate(candidate_prominences)
        median = float(np.median(prominences))
        mad = float(np.median(np.abs(prominences - median)))
        robust_sd = MAD_NORMAL_CONSISTENCY * mad
        prominence_threshold = median + prominence_mad_multiplier * robust_sd
        thresholds[channel] = {
            "height_uv": None,
            "prominence_uv": float(prominence_threshold),
            "prominence_candidate_count": int(prominences.size),
            "prominence_median_uv": median,
            "prominence_mad_uv": mad,
            "prominence_robust_sd_uv": robust_sd,
            "prominence_mad_multiplier": prominence_mad_multiplier,
        }
        distributions[channel] = prominences
    return thresholds, distributions


def detect_blink_peaks(values: np.ndarray, prominence_uv: float) -> np.ndarray:
    """Detect blink peaks using the fixed prominence and morphology criteria."""
    peaks, _ = find_peaks(
        values,
        prominence=prominence_uv,
        distance=max(1, round(MINIMUM_PEAK_DISTANCE_SECONDS * SFREQ)),
        width=(
            max(1, round(MINIMUM_PEAK_WIDTH_SECONDS * SFREQ)),
            max(1, round(MAXIMUM_PEAK_WIDTH_SECONDS * SFREQ)),
        ),
    )
    return peaks.astype(np.int64)


def detect_session(
    session_id: str,
    input_root: Path,
    condition: str,
    prominence_mad_multiplier: float = PROMINENCE_MAD_MULTIPLIER,
) -> SessionResult:
    sets: dict[int, SetSignal] = {}
    for set_number in range(1, N_SETS + 1):
        path = input_path(input_root, session_id, set_number)
        if not path.exists():
            logging.warning("ID%s Set%d is missing: %s", session_id, set_number, path)
            continue
        sets[set_number] = load_set_signal(path, session_id, set_number)
    if not sets:
        raise FileNotFoundError(f"No Phase 1 blink HDF5 found for ID{session_id}")
    thresholds, distributions = calculate_session_thresholds(
        sets, prominence_mad_multiplier
    )
    for set_signal in sets.values():
        for channel, values in set_signal.filtered_uv.items():
            threshold = thresholds[channel]
            set_signal.peaks[channel] = detect_blink_peaks(
                values,
                float(threshold["prominence_uv"]),
            )
    return SessionResult(session_id, condition, thresholds, distributions, sets)


def calculate_blink_rate(set_signal: SetSignal) -> pd.DataFrame:
    duration = set_signal.duration_seconds
    centers = np.arange(0.0, np.floor(duration) + 1e-9, RATE_STEP_SECONDS)
    peak_times = set_signal.relative_seconds[set_signal.peaks["Fp1_Fp2_mean"]]
    half_window = RATE_WINDOW_SECONDS / 2.0
    rates: list[float] = []
    window_durations: list[float] = []
    counts: list[int] = []
    for center in centers:
        start = max(0.0, center - half_window)
        stop = min(duration, center + half_window)
        count = int(np.count_nonzero((peak_times >= start) & (peak_times < stop)))
        actual_duration = stop - start
        counts.append(count)
        window_durations.append(actual_duration)
        rates.append(count / (actual_duration / 60.0) if actual_duration > 0 else np.nan)
    smoothed_rates = (
        pd.Series(rates, dtype=float)
        .rolling(window=RATE_SMOOTHING_SECONDS, center=True, min_periods=1)
        .mean()
        .to_numpy()
    )
    progress = (set_signal.set_number - 1) * 100.0 + centers / duration * 100.0
    return pd.DataFrame(
        {
            "SessionID": set_signal.session_id,
            "Set": set_signal.set_number,
            "SetTimeSeconds": centers,
            "ExperimentalProgressPercent": progress,
            "WindowDurationSeconds": window_durations,
            "BlinkCountInWindow": counts,
            "BlinkRateBlinksPerMin": rates,
            "BlinkRateSmoothed15sBlinksPerMin": smoothed_rates,
        }
    )


def set_summary(result: SessionResult, pair_id: str, product_jp: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for set_number in range(1, N_SETS + 1):
        set_signal = result.sets.get(set_number)
        if set_signal is None:
            rows.append(
                {
                    "PairID": pair_id,
                    "SessionID": result.session_id,
                    "Product": product_jp,
                    "Condition": result.condition,
                    "Set": set_number,
                    "Status": "欠測",
                }
            )
            continue
        duration_minutes = set_signal.duration_seconds / 60.0
        primary_count = int(set_signal.peaks["Fp1_Fp2_mean"].size)
        rows.append(
            {
                "PairID": pair_id,
                "SessionID": result.session_id,
                "Product": product_jp,
                "Condition": result.condition,
                "Set": set_number,
                "Status": "使用",
                "MeanSignalBlinkCount": primary_count,
                "Fp1BlinkCount": int(set_signal.peaks["Fp1"].size),
                "Fp2BlinkCount": int(set_signal.peaks["Fp2"].size),
                "SetDurationMinutes": duration_minutes,
                "BlinkRateBlinksPerMin": primary_count / duration_minutes,
                "PeakHeightThresholdUv": result.thresholds["Fp1_Fp2_mean"]["height_uv"],
                "ProminenceThresholdUv": result.thresholds["Fp1_Fp2_mean"]["prominence_uv"],
                "SourceHDF5": str(set_signal.path),
            }
        )
    return pd.DataFrame(rows)


def event_table(result: SessionResult) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for set_number, set_signal in sorted(result.sets.items()):
        peaks = set_signal.peaks["Fp1_Fp2_mean"]
        for event_number, sample in enumerate(peaks, 1):
            rows.append(
                {
                    "SessionID": result.session_id,
                    "Set": set_number,
                    "BlinkEvent": event_number,
                    "Sample": int(sample),
                    "SetTimeSeconds": float(set_signal.relative_seconds[sample]),
                    "OriginalTimestamp": float(set_signal.original_timestamp[sample]),
                    "ExperimentalProgressPercent": (
                        (set_number - 1) * 100.0
                        + set_signal.relative_seconds[sample] / set_signal.duration_seconds * 100.0
                    ),
                    "FilteredAmplitudeUv": float(set_signal.filtered_uv["Fp1_Fp2_mean"][sample]),
                }
            )
    return pd.DataFrame(rows)


def plot_prominence_distribution(result: SessionResult, path: Path) -> None:
    """Plot the useful prominence range and report candidates above that range."""
    _configure_plot()
    values = result.prominence_distributions["Fp1_Fp2_mean"]
    threshold = float(result.thresholds["Fp1_Fp2_mean"]["prominence_uv"])
    figure, axis = plt.subplots(figsize=(12, 8))
    display_max_uv = 500.0
    axis.hist(
        values[values <= display_max_uv],
        bins=np.linspace(0.0, display_max_uv, 101),
        color="#8CA6C0",
        edgecolor="white",
        linewidth=0.35,
    )
    axis.axvline(
        threshold,
        color="#C23B3B",
        linestyle="--",
        linewidth=2.8,
        label=f"MAD threshold = {threshold:.2f} µV",
    )
    axis.set_xlabel("Peak Prominence (µV)", labelpad=14)
    axis.set_ylabel("Candidate Peak Count (log scale)", labelpad=14)
    axis.set_xlim(0, display_max_uv)
    axis.set_yscale("log")
    above_count = int(np.count_nonzero(values > display_max_uv))
    axis.text(
        0.98,
        0.88,
        f"> 500 µV: {above_count:,}",
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=17,
    )
    axis.legend(loc="upper right", frameon=False)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def detection_reset_scale_uv(result: SessionResult) -> float:
    """Return the shared y half-range used by the HTML Reset view and PNG."""
    finite_absolute = np.concatenate(
        [
            np.abs(signal.filtered_uv["Fp1_Fp2_mean"])
            for signal in result.sets.values()
            if signal.filtered_uv["Fp1_Fp2_mean"].size
        ]
    )
    finite_absolute = finite_absolute[np.isfinite(finite_absolute)]
    if not finite_absolute.size:
        return 10.0
    finite_absolute.sort()
    percentile_index = min(
        finite_absolute.size - 1, int(np.floor(finite_absolute.size * 0.995))
    )
    return max(10.0, float(finite_absolute[percentile_index]) * 1.60)


def plot_detection_overview(result: SessionResult, path: Path) -> None:
    """Save a wide, static counterpart of the HTML Reset view."""
    _configure_plot()
    figure, axis = plt.subplots(figsize=(32, 8))
    line_label_used = False
    peak_label_used = False
    for set_number in range(1, N_SETS + 1):
        signal = result.sets.get(set_number)
        if signal is None:
            continue
        values = signal.filtered_uv["Fp1_Fp2_mean"]
        progress = (set_number - 1) * 100.0 + np.arange(values.size) / max(
            1, values.size - 1
        ) * 100.0
        axis.plot(
            progress,
            values,
            color="#3268A8",
            linewidth=0.35,
            rasterized=True,
            label="Eye Blink Component Signal" if not line_label_used else None,
        )
        line_label_used = True
        peaks = signal.peaks["Fp1_Fp2_mean"]
        if peaks.size:
            axis.scatter(
                progress[peaks],
                values[peaks],
                s=22,
                facecolors="none",
                edgecolors="#D14B45",
                linewidths=0.9,
                zorder=3,
                label="Detected blink" if not peak_label_used else None,
            )
            peak_label_used = True
    y_half_range = detection_reset_scale_uv(result)
    axis.set_xlim(0, 600)
    axis.set_ylim(-y_half_range, y_half_range)
    axis.set_xticks(np.arange(0, 601, 50))
    for boundary in range(100, 600, 100):
        axis.axvline(boundary, color="#999999", linestyle="--", linewidth=1.1, zorder=0)
    for set_number in range(1, N_SETS + 1):
        axis.text(
            (set_number - 0.5) * 100,
            0.94,
            f"Set {set_number}",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=17,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 1.5},
        )
    axis.set_xlabel("Experimental Progress, %", labelpad=14)
    axis.set_ylabel("Amplitude (µV)", labelpad=14)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.12), ncol=2, frameon=False)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _configure_plot() -> None:
    plt.rcParams.update(
        {
            "font.family": "Arial",
            "axes.linewidth": 1.5,
            "axes.labelsize": 26,
            "xtick.labelsize": 18,
            "ytick.labelsize": 18,
            "legend.fontsize": 17,
        }
    )


def _decorate_progress_axis(axis: plt.Axes) -> None:
    axis.set_xlim(0, 600)
    axis.set_xticks(np.arange(0, 601, 50))
    for boundary in range(100, 600, 100):
        axis.axvline(boundary, color="#B8B8B8", linestyle="--", linewidth=1.2, zorder=0)
    ymax = axis.get_ylim()[1]
    for set_number in range(1, 7):
        axis.text(
            (set_number - 0.5) * 100,
            ymax * 0.94,
            f"Set {set_number}",
            ha="center",
            va="top",
            fontsize=17,
        )


def individual_figure_y_upper_limit(values: np.ndarray) -> float:
    """Place the largest individual Blink Rate near 70% of a zero-based axis."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 5.0
    target = float(np.max(finite)) / 0.70
    return max(5.0, float(np.ceil(target / 5.0) * 5.0))


def grand_figure_y_upper_limit(mean_plus_sem_values: np.ndarray) -> float:
    """Place the largest grand-average mean + SEM near 87.5% of the axis."""

    finite = np.asarray(mean_plus_sem_values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 5.0
    target = float(np.max(finite)) / 0.875
    return max(5.0, float(np.ceil(target / 5.0) * 5.0))


def calculate_grand_average_statistics(values: np.ndarray) -> dict[str, np.ndarray]:
    """Return pointwise mean, sample SD, SEM, and valid N without interpolation."""

    matrix = np.asarray(values, dtype=float)
    if matrix.ndim != 2:
        raise ValueError("values must be a 2D participant-by-position array")
    valid_n = np.sum(np.isfinite(matrix), axis=0).astype(int)
    mean = np.full(matrix.shape[1], np.nan, dtype=float)
    sample_sd = np.full(matrix.shape[1], np.nan, dtype=float)
    sem = np.full(matrix.shape[1], np.nan, dtype=float)
    for position in range(matrix.shape[1]):
        finite = matrix[:, position][np.isfinite(matrix[:, position])]
        if finite.size:
            mean[position] = float(np.mean(finite))
        if finite.size >= 2:
            sample_sd[position] = float(np.std(finite, ddof=1))
            sem[position] = sample_sd[position] / np.sqrt(finite.size)
    return {"mean": mean, "sample_sd": sample_sd, "sem": sem, "valid_n": valid_n}


def plot_pair_timecourse(
    rates: dict[str, pd.DataFrame],
    spec: ParticipantSpec,
    product_label: str,
    color: str,
    path: Path,
) -> None:
    _configure_plot()
    figure, axis = plt.subplots(figsize=(18, 8.5))
    for session_id, label, line_color in (
        (spec.drops_session_id, f"Eye Drop ({product_label})", color),
        (spec.control_session_id, "Control", CONTROL_COLOR),
    ):
        frame = rates[session_id]
        first_set = True
        for _, set_frame in frame.groupby("Set", sort=True):
            axis.plot(
                set_frame["ExperimentalProgressPercent"],
                set_frame["BlinkRateSmoothed15sBlinksPerMin"],
                color=line_color,
                linewidth=2.7,
                label=label if first_set else None,
            )
            first_set = False
    axis.set_xlabel("Experimental Progress, %", labelpad=14)
    axis.set_ylabel("Blink Rate (blinks/min)", labelpad=14)
    displayed = np.concatenate(
        [
            frame["BlinkRateSmoothed15sBlinksPerMin"].to_numpy(dtype=float)
            for frame in rates.values()
        ]
    )
    axis.set_ylim(0, individual_figure_y_upper_limit(displayed))
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.13), ncol=2, frameon=False)
    _decorate_progress_axis(axis)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_pair_quantification(
    summary: pd.DataFrame,
    product_dir: str,
    product_label: str,
    color: str,
    path: Path,
) -> None:
    _configure_plot()
    figure, axes = plt.subplots(1, 6, figsize=(25, 7), sharey=True)
    finite = summary["BlinkRateBlinksPerMin"].dropna().to_numpy(dtype=float)
    ymax = max(1.0, float(np.max(finite)) * 1.30) if finite.size else 1.0
    for set_number, axis in enumerate(axes, 1):
        part = summary[summary["Set"] == set_number]
        values = []
        for condition in ("Eye Drop", "Control"):
            series = part.loc[part["Condition"] == condition, "BlinkRateBlinksPerMin"]
            values.append(
                float(series.iloc[0]) if len(series) and pd.notna(series.iloc[0]) else np.nan
            )
        x = np.array([-0.25, 0.25])
        quantification_color = QUANTIFICATION_COLORS[product_dir]
        axis.bar(
            x,
            values,
            width=0.34,
            color=[quantification_color, CONTROL_QUANTIFICATION_COLOR],
            alpha=0.90,
        )
        if np.isfinite(values).all():
            axis.plot(x, values, color="#8A8A8A", linewidth=1.5, alpha=0.75, zorder=2)
        for xpos, value, dot_color in zip(
            x,
            values,
            [quantification_color, CONTROL_QUANTIFICATION_COLOR],
            strict=True,
        ):
            if np.isfinite(value):
                axis.scatter(
                    xpos,
                    value,
                    s=145,
                    color=dot_color,
                    edgecolor="white",
                    linewidth=1.4,
                    zorder=3,
                    alpha=0.80,
                )
        axis.set_xlim(-0.75, 0.75)
        axis.set_ylim(0, ymax)
        axis.set_xticks(x, [f"Eye Drop\n({product_label})", "Control"], fontsize=14)
        axis.text(0, ymax * 0.94, f"Set {set_number}", ha="center", va="top", fontsize=18)
        axis.spines[["top", "right"]].set_visible(False)
        if set_number == 1:
            axis.set_ylabel("Blink Rate (blinks/min)", labelpad=12)
    figure.tight_layout(w_pad=1.2)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _encoded_float32(values: np.ndarray) -> str:
    array = np.asarray(values, dtype="<f4")
    return base64.b64encode(array.tobytes()).decode("ascii")


def save_detection_html(
    result: SessionResult,
    path: Path,
) -> None:
    segments: list[dict[str, object]] = []
    for set_number in range(1, N_SETS + 1):
        signal = result.sets.get(set_number)
        if signal is None:
            segments.append({"set": set_number, "missing": True})
            continue
        peaks = signal.peaks["Fp1_Fp2_mean"]
        segments.append(
            {
                "set": set_number,
                "missing": False,
                "duration": signal.duration_seconds,
                "values": _encoded_float32(signal.filtered_uv["Fp1_Fp2_mean"]),
                "peaks": peaks.tolist(),
                "peak_times": signal.relative_seconds[peaks].tolist(),
            }
        )
    payload = {
        "session": result.session_id,
        "sfreq": SFREQ,
        "segments": segments,
        "height": result.thresholds["Fp1_Fp2_mean"]["height_uv"],
        "prominence": result.thresholds["Fp1_Fp2_mean"]["prominence_uv"],
        "prominence_mad_multiplier": result.thresholds["Fp1_Fp2_mean"][
            "prominence_mad_multiplier"
        ],
    }
    html = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Blink detection QC</title>
<style>body{font-family:Arial,sans-serif;margin:16px;color:#202124}.tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}button{padding:6px 12px}canvas{border:1px solid #777;width:100%;height:620px;cursor:grab;touch-action:none}.hint{color:#555}.line{display:inline-block;width:24px;height:3px;background:#3268A8;margin-right:5px}.dot{display:inline-block;width:10px;height:10px;border:2px solid #D14B45;border-radius:50%;margin-right:5px}</style></head><body>
<h1>ID__SESSION__: Blink detection quality check (MAD-based prominence threshold, k=__MAD_K__)</h1><p><span class="line"></span>Eye Blink Component Signal &nbsp; <span class="dot"></span>Detected blink</p>
<div class="tools"><button id="xin">x zoom in</button><button id="xout">x zoom out</button><button id="yin">y zoom in</button><button id="yout">y zoom out</button><button id="reset">Reset</button><span id="status"></span></div>
<p class="hint">Drag or use Left/Right Arrow to move. Mouse wheel or x buttons change the x scale. All sets use equal 0–100 progress units; rest periods are omitted. Axes: Experimental Progress, %; Amplitude (µV).</p>
<canvas id="plot" width="1700" height="620"></canvas><pre id="readout"></pre>
<script id="payload" type="application/json">__PAYLOAD__</script><script>"use strict";const P=JSON.parse(document.getElementById('payload').textContent);function decode(s){const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new Float32Array(u.buffer)}P.segments.forEach(s=>{if(!s.missing)s.values=decode(s.values)});const cv=document.getElementById('plot'),ctx=cv.getContext('2d'),L=90,R=25,T=30,B=65;let x0=0,x1=600,drag=null,panTimer=null;let all=[];P.segments.forEach(s=>{if(!s.missing)for(const v of s.values)if(Number.isFinite(v))all.push(Math.abs(v))});all.sort((a,b)=>a-b);let baseY=Math.max(10,all[Math.floor(all.length*.995)]*1.60),ys=baseY;function clamp(a,b){const span=Math.max(2,Math.min(600,b-a));a=Math.max(0,Math.min(600-span,a));return[a,a+span]}function zoom(f,r=.5){const c=x0+r*(x1-x0),span=(x1-x0)*f;[x0,x1]=clamp(c-r*span,c+(1-r)*span);draw()}function pan(d){const shift=(x1-x0)*.05*d;[x0,x1]=clamp(x0+shift,x1+shift);draw()}function stopPan(){if(panTimer){clearInterval(panTimer);panTimer=null}}function startPan(d){stopPan();pan(d);panTimer=setInterval(()=>pan(d),80)}function xy(progress,value,w,h){return[L+(progress-x0)/(x1-x0)*w,T+h/2-value/ys*h*.43]}function draw(){ctx.clearRect(0,0,cv.width,cv.height);const w=cv.width-L-R,h=cv.height-T-B;ctx.strokeStyle='#222';ctx.strokeRect(L,T,w,h);ctx.font='16px Arial';ctx.fillStyle='#111';ctx.textAlign='center';for(let t=Math.ceil(x0/50)*50;t<=x1;t+=50){const x=L+(t-x0)/(x1-x0)*w;ctx.strokeStyle='#ddd';ctx.beginPath();ctx.moveTo(x,T);ctx.lineTo(x,T+h);ctx.stroke();ctx.fillStyle='#111';ctx.fillText(String(t),x,T+h+25)}for(let s=1;s<6;s++){const p=s*100;if(p<x0||p>x1)continue;const x=L+(p-x0)/(x1-x0)*w;ctx.strokeStyle='#999';ctx.setLineDash([6,5]);ctx.beginPath();ctx.moveTo(x,T);ctx.lineTo(x,T+h);ctx.stroke();ctx.setLineDash([])}for(let s=1;s<=6;s++){const p=(s-.5)*100;if(p>=x0&&p<=x1){const tx=L+(p-x0)/(x1-x0)*w;ctx.fillStyle='rgba(255,255,255,.78)';ctx.fillRect(tx-31,T+5,62,21);ctx.fillStyle='#111';ctx.fillText('Set '+s,tx,T+20)}}P.segments.forEach(seg=>{if(seg.missing)return;const start=(seg.set-1)*100,n=seg.values.length;ctx.strokeStyle='#3268A8';ctx.lineWidth=1;ctx.beginPath();const pxCount=Math.max(1,Math.floor(w*2));for(let px=0;px<pxCount;px++){const pa=x0+(x1-x0)*px/pxCount,pb=x0+(x1-x0)*(px+1)/pxCount;if(pb<start||pa>start+100)continue;const a=Math.max(0,Math.floor((pa-start)/100*n)),b=Math.min(n,Math.max(a+1,Math.ceil((pb-start)/100*n)));let lo=Infinity,hi=-Infinity;for(let i=a;i<b;i++){lo=Math.min(lo,seg.values[i]);hi=Math.max(hi,seg.values[i])}if(!Number.isFinite(lo))continue;const x=L+px/pxCount*w;ctx.moveTo(x,xy(pa,lo,w,h)[1]);ctx.lineTo(x,xy(pa,hi,w,h)[1])}ctx.stroke();ctx.strokeStyle='#D14B45';ctx.lineWidth=2;seg.peaks.forEach(i=>{const p=start+i/Math.max(1,n-1)*100;if(p<x0||p>x1)return;const [x,y]=xy(p,seg.values[i],w,h);ctx.beginPath();ctx.arc(x,y,4,0,Math.PI*2);ctx.stroke()})});ctx.fillStyle='#111';ctx.font='20px Arial';ctx.fillText('Experimental Progress, %',L+w/2,cv.height-10);ctx.save();ctx.translate(22,T+h/2);ctx.rotate(-Math.PI/2);ctx.fillText('Amplitude (µV)',0,0);ctx.restore();document.getElementById('status').textContent=`x ${x0.toFixed(1)}–${x1.toFixed(1)} %, y ±${ys.toFixed(1)} µV`}
document.getElementById('xin').onclick=()=>zoom(.5);document.getElementById('xout').onclick=()=>zoom(2);document.getElementById('yin').onclick=()=>{ys=Math.max(.1,ys/1.5);draw()};document.getElementById('yout').onclick=()=>{ys*=1.5;draw()};document.getElementById('reset').onclick=()=>{x0=0;x1=600;ys=baseY;draw()};document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();startPan(e.key==='ArrowLeft'?-1:1)}});document.addEventListener('keyup',e=>{if(e.key.startsWith('Arrow'))stopPan()});window.addEventListener('blur',stopPan);cv.addEventListener('wheel',e=>{e.preventDefault();const r=cv.getBoundingClientRect(),q=(e.clientX-r.left)/r.width;zoom(e.deltaY>0?1.5:.67,Math.max(0,Math.min(1,q)))},{passive:false});cv.addEventListener('pointerdown',e=>{cv.setPointerCapture(e.pointerId);drag={x:e.clientX,a:x0,b:x1};cv.style.cursor='grabbing'});cv.addEventListener('pointerup',e=>{drag=null;cv.style.cursor='grab'});cv.addEventListener('pointermove',e=>{const r=cv.getBoundingClientRect();if(drag){const d=(e.clientX-drag.x)/r.width*(drag.b-drag.a);[x0,x1]=clamp(drag.a-d,drag.b-d);draw();return}const p=x0+(e.clientX-r.left)/r.width*(x1-x0),set=Math.min(6,Math.max(1,Math.floor(p/100)+1)),seg=P.segments[set-1];if(seg.missing){document.getElementById('readout').textContent=`Set ${set}: missing`;return}const q=Math.max(0,Math.min(1,(p-(set-1)*100)/100)),i=Math.min(seg.values.length-1,Math.round(q*(seg.values.length-1))),peak=seg.peaks.includes(i);document.getElementById('readout').textContent=`Set ${set} | progress ${p.toFixed(2)} % | set time ${(i/P.sfreq).toFixed(3)} s | ${seg.values[i].toFixed(2)} µV | peak ${peak?'yes':'no'}`});draw();</script></body></html>"""
    html = (
        html.replace("__SESSION__", result.session_id)
        .replace("__MAD_K__", f"{float(payload['prominence_mad_multiplier']):g}")
        .replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def session_file_prefix(spec: ParticipantSpec, session_id: str) -> str:
    """Return a filename prefix that sorts paired sessions consecutively."""
    if session_id == spec.first_session_id:
        order = 1
    elif session_id == spec.second_session_id:
        order = 2
    else:
        raise ValueError(f"ID{session_id} does not belong to pair {spec.pair_id}")
    return f"Pair{spec.pair_id}_{order:02d}_ID{session_id}"


def process_participant(
    spec: ParticipantSpec,
    input_root: Path,
    output_root: Path,
    prominence_mad_multiplier: float = PROMINENCE_MAD_MULTIPLIER,
    comparison_label: str | None = None,
) -> dict[str, object]:
    product_dir, product_label, product_color, product_jp = normalize_product(spec.product)
    if comparison_label:
        phase_root = (
            output_root
            / "Phase3_瞬き解析"
            / "No1_BlinkRate_ParameterComparison"
            / comparison_label
        )
        filename_suffix = f"_{comparison_label}"
    else:
        phase_root = output_root / "Phase3_瞬き解析" / "No1_BlinkRate"
        filename_suffix = ""
    results = {
        spec.drops_session_id: detect_session(
            spec.drops_session_id,
            input_root,
            "Eye Drop",
            prominence_mad_multiplier,
        ),
        spec.control_session_id: detect_session(
            spec.control_session_id,
            input_root,
            "Control",
            prominence_mad_multiplier,
        ),
    }
    summaries = pd.concat(
        [set_summary(result, spec.pair_id, product_jp) for result in results.values()],
        ignore_index=True,
    )
    for configured_product_dir in ("CCube", "VRohtoPremium"):
        configured_product_root = phase_root / configured_product_dir
        for relative_directory in (
            Path("Individual"),
            Path("GrandAverage"),
            Path("SetQuantification"),
            Path("QualityCheck") / "BlinkDetection",
            Path("QualityCheck") / "ProminenceDistribution",
        ):
            (configured_product_root / relative_directory).mkdir(parents=True, exist_ok=True)
    pair_table_dir = phase_root / "Sub" / "tables"
    pair_table_dir.mkdir(parents=True, exist_ok=True)
    rate_frames: dict[str, pd.DataFrame] = {}
    for session_id, result in results.items():
        rate_frames[session_id] = pd.concat(
            [calculate_blink_rate(signal) for signal in result.sets.values()], ignore_index=True
        )
        prefix = session_file_prefix(spec, session_id)
        detection_dir = phase_root / product_dir / "QualityCheck" / "BlinkDetection"
        prominence_dir = phase_root / product_dir / "QualityCheck" / "ProminenceDistribution"
        html_path = detection_dir / f"{prefix}_No1_BlinkDetection{filename_suffix}.html"
        overview_path = detection_dir / f"{prefix}_No1_BlinkDetection_Overview{filename_suffix}.png"
        distribution_path = prominence_dir / f"{prefix}_No1_ProminenceDistribution{filename_suffix}.png"
        save_detection_html(result, html_path)
        plot_detection_overview(result, overview_path)
        plot_prominence_distribution(result, distribution_path)
        event_table(result).to_csv(
            pair_table_dir / f"ID{session_id}_No1_BlinkEvents.csv",
            index=False,
        )
        rate_frames[session_id].to_csv(
            pair_table_dir / f"ID{session_id}_No1_BlinkRateTimecourse.csv",
            index=False,
        )
    summary_path = pair_table_dir / f"ID{spec.pair_id}_No1_BlinkSetResults.csv"
    summaries.to_csv(summary_path, index=False)
    individual_path = (
        phase_root
        / product_dir
        / "Individual"
        / f"ID{spec.pair_id}_No1_BlinkRate_Timecourse.png"
    )
    plot_pair_timecourse(rate_frames, spec, product_label, product_color, individual_path)
    quant_path = (
        phase_root
        / product_dir
        / "SetQuantification"
        / f"ID{spec.pair_id}_No1_BlinkRate_SetQuantification.png"
    )
    plot_pair_quantification(
        summaries,
        product_dir,
        product_label,
        product_color,
        quant_path,
    )
    run_summary = {
        "created_at": datetime.now().astimezone().isoformat(),
        "script": Path(__file__).name,
        "participant": asdict(spec),
        "pair_id": spec.pair_id,
        "product_directory": product_dir,
        "product_label": product_label,
        "input_root": str(input_root),
        "output_root": str(phase_root),
        "parameters": {
            "sampling_frequency_hz": SFREQ,
            "bandpass_hz": [FILTER_LOW_HZ, FILTER_HIGH_HZ],
            "filter_order": FILTER_ORDER,
            "filter": "Butterworth SOS, zero-phase sosfiltfilt",
            "height_threshold": None,
            "prominence_threshold_method": "median + k * 1.4826 * MAD",
            "prominence_mad_normal_consistency": MAD_NORMAL_CONSISTENCY,
            "prominence_mad_multiplier": prominence_mad_multiplier,
            "prominence_mad_multiplier_basis": PROMINENCE_MULTIPLIER_BASIS,
            "percentile_threshold_used": False,
            "percentile_threshold_rejection_reason": PERCENTILE_THRESHOLD_REJECTION_REASON,
            "comparison_label": comparison_label,
            "minimum_peak_distance_seconds": MINIMUM_PEAK_DISTANCE_SECONDS,
            "peak_width_seconds": [
                MINIMUM_PEAK_WIDTH_SECONDS,
                MAXIMUM_PEAK_WIDTH_SECONDS,
            ],
            "rate_window_seconds": RATE_WINDOW_SECONDS,
            "rate_step_seconds": RATE_STEP_SECONDS,
            "rate_smoothing_seconds": RATE_SMOOTHING_SECONDS,
            "rate_smoothing": "centered simple moving average within each set",
            "grand_average_center": "pointwise between-participant mean",
            "grand_average_shade": "mean +/- SEM",
            "grand_average_sem": "sample SD (ddof=1) / sqrt(valid N), no interpolation",
        },
        "session_thresholds": {
            session_id: result.thresholds for session_id, result in results.items()
        },
        "outputs": {
            "individual_figure": str(individual_path),
            "set_quantification_figure": str(quant_path),
            "set_results_csv": str(summary_path),
            "blink_detection_qc": {
                session_id: {
                    "html": str(
                        phase_root
                        / product_dir
                        / "QualityCheck"
                        / "BlinkDetection"
                        / f"{session_file_prefix(spec, session_id)}_No1_BlinkDetection{filename_suffix}.html"
                    ),
                    "overview_png": str(
                        phase_root
                        / product_dir
                        / "QualityCheck"
                        / "BlinkDetection"
                        / f"{session_file_prefix(spec, session_id)}_No1_BlinkDetection_Overview{filename_suffix}.png"
                    ),
                    "prominence_distribution_png": str(
                        phase_root
                        / product_dir
                        / "QualityCheck"
                        / "ProminenceDistribution"
                        / f"{session_file_prefix(spec, session_id)}_No1_ProminenceDistribution{filename_suffix}.png"
                    ),
                }
                for session_id in results
            },
        },
    }
    log_dir = phase_root / "Sub" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"ID{spec.pair_id}_No1_BlinkRate_RunSummary.json"
    log_path.write_text(json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"summary": summaries, "run_summary": run_summary, "log_path": log_path}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", action="append", type=parse_participant, default=[])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--prominence-mad-multiplier",
        type=float,
        default=PROMINENCE_MAD_MULTIPLIER,
        help="MAD multiplier k in median + k * 1.4826 * MAD (default: 10)",
    )
    parser.add_argument(
        "--comparison-label",
        help="Write to a separated comparison folder; normal production output is unchanged",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = list(args.participant)
    if args.manifest:
        specs.extend(load_manifest(args.manifest))
    if not specs:
        raise SystemExit("Provide --participant or --manifest")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    for spec in specs:
        logging.info("Processing ID%s", spec.pair_id)
        process_participant(
            spec,
            args.input_root,
            args.output_root,
            prominence_mad_multiplier=args.prominence_mad_multiplier,
            comparison_label=args.comparison_label,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
