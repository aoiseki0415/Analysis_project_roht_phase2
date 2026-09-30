#!/usr/bin/env python3
"""Phase 2 No1: analyse reaction-time change across trials and sets."""

from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

N_SETS = 6
N_TRIALS = 320
WINDOW_TRIALS = 20
FWHM_TRIALS = 9.0
GAUSSIAN_SIGMA = FWHM_TRIALS / (2.0 * np.sqrt(2.0 * np.log(2.0)))
OUTLIER_SD = 2.0
CONTROL_COLOR = "#563A7C"
EEG_MISSING_SET_BY_SESSION = {
    "109": 1,
    "120": 6,
    "135": 2,
    "225": 4,
}
PRODUCTS = {
    "ccube": ("CCube", "C Cube", "#C84A4A"),
    "c_cube": ("CCube", "C Cube", "#C84A4A"),
    "cキューブ": ("CCube", "C Cube", "#C84A4A"),
    "vrohtopremium": ("VRohtoPremium", "V Rohto Premium", "#E58A2B"),
    "v_rohto_premium": ("VRohtoPremium", "V Rohto Premium", "#E58A2B"),
    "vロート": ("VRohtoPremium", "V Rohto Premium", "#E58A2B"),
    "vロートプレミアム": ("VRohtoPremium", "V Rohto Premium", "#E58A2B"),
}
DEFAULT_RAW_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/行動データ"
)
DEFAULT_OUTPUT_ROOT = Path(
    "/Users/aoiseki/Library/CloudStorage/OneDrive-個人用/デスクトップ/"
    "SandBoxプロジェクト/ロート製薬フェーズ2 2026.5/実験本番_本解析"
)


@dataclass(frozen=True)
class ParticipantSpec:
    """Mapping confirmed in the de-identified participant spreadsheet."""

    first_session_id: str
    second_session_id: str
    drops_session_id: str
    product: str

    def __post_init__(self) -> None:
        if self.first_session_id == self.second_session_id:
            raise ValueError("The first and second session IDs must differ")
        if self.drops_session_id not in {self.first_session_id, self.second_session_id}:
            raise ValueError("The eye-drop session must be either the first or second session")

    @property
    def pair_id(self) -> str:
        return f"{self.first_session_id}-{self.second_session_id}"

    @property
    def control_session_id(self) -> str:
        if self.drops_session_id == self.first_session_id:
            return self.second_session_id
        return self.first_session_id

    @property
    def eye_drops_visit(self) -> str:
        return "1回目" if self.drops_session_id == self.first_session_id else "2回目"


@dataclass
class SessionResult:
    """Processed result and quality-control values for one session."""

    session_id: str
    condition: str
    product: str
    trials: pd.DataFrame
    mean_rt_ms: float
    sd_rt_ms: float
    lower_2sd_ms: float
    upper_2sd_ms: float
    outlier_count: int
    outlier_trials: str
    valid_rt_count: int
    rt_match: str
    source_notes: str
    eeg_missing_set: int | None


def normalize_product(value: str) -> tuple[str, str, str]:
    """Return output-directory name, figure label, and fixed figure colour."""

    key = value.strip().lower().replace(" ", "").replace("-", "")
    if key not in PRODUCTS:
        allowed = "CCube or VRohtoPremium"
        raise ValueError(f"Unknown product {value!r}; expected {allowed}")
    return PRODUCTS[key]


def parse_participant(value: str) -> ParticipantSpec:
    """Parse first_session:second_session:drops_session:product."""

    parts = [item.strip() for item in value.split(":")]
    if len(parts) != 4 or not all(parts):
        raise argparse.ArgumentTypeError(
            "--participant must be first_session:second_session:drops_session:product"
        )
    normalize_product(parts[3])
    return ParticipantSpec(*parts)


def load_manifest(path: Path) -> list[ParticipantSpec]:
    """Read a private batch manifest without copying it into the repository."""

    frame = pd.read_csv(path, dtype=str)
    columns = ["first_session_id", "second_session_id", "drops_session_id", "product"]
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Manifest is missing columns: {missing}")
    specs = [
        ParticipantSpec(*(str(row[column]).strip() for column in columns))
        for _, row in frame.iterrows()
    ]
    for spec in specs:
        normalize_product(spec.product)
    return specs


def gaussian_moving_average(values: np.ndarray) -> np.ndarray:
    """Smooth one 320-trial set without crossing a set boundary.

    The 20-position local support follows the fixed convention i-10 through
    i+9. At an edge, and for NaNs, only available weights are renormalised.
    """

    values = np.asarray(values, dtype=float)
    result = np.full(values.shape, np.nan, dtype=float)
    for index in range(values.size):
        start = max(0, index - 10)
        stop = min(values.size, index + 10)
        positions = np.arange(start, stop)
        valid = np.isfinite(values[start:stop])
        if not valid.any():
            continue
        weights = np.exp(-0.5 * ((positions - index) / GAUSSIAN_SIGMA) ** 2)
        weights = weights[valid]
        result[index] = np.sum(values[start:stop][valid] * weights) / np.sum(weights)
    return result


def _read_stimulus_rows(path: Path, set_number: int) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "Trial",
        "TiltOnset(ms)",
        "KeyPress(ms)",
        "RT(ms)",
        "ResponseType",
        "Block",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")

    response_type = frame["ResponseType"].astype(str).str.strip().str.lower()
    block = pd.to_numeric(frame["Block"], errors="coerce")
    stimulus = frame.loc[(response_type != "mistouch") & (block == set_number)].copy()
    stimulus["Trial"] = pd.to_numeric(stimulus["Trial"], errors="coerce")
    stimulus["TiltOnset(ms)"] = pd.to_numeric(stimulus["TiltOnset(ms)"], errors="coerce")
    stimulus["KeyPress(ms)"] = pd.to_numeric(stimulus["KeyPress(ms)"], errors="coerce")
    stimulus["RT(ms)"] = pd.to_numeric(stimulus["RT(ms)"], errors="coerce")
    stimulus["RT_recomputed_ms"] = stimulus["KeyPress(ms)"] - stimulus["TiltOnset(ms)"]
    stimulus["source_file"] = str(path)
    return stimulus


def _is_complete_set(frame: pd.DataFrame) -> bool:
    trials = pd.to_numeric(frame["Trial"], errors="coerce")
    expected = np.arange(1, N_TRIALS + 1)
    return (
        len(frame) == N_TRIALS
        and trials.notna().all()
        and frame["RT_recomputed_ms"].notna().all()
        and np.array_equal(np.sort(trials.astype(int).to_numpy()), expected)
    )


def _select_set(session_dir: Path, set_number: int) -> tuple[pd.DataFrame, str]:
    pattern = re.compile(rf"_block{set_number}_results\.csv$", re.IGNORECASE)
    candidates = sorted(
        path for path in session_dir.rglob("*_results.csv") if pattern.search(path.name)
    )
    if not candidates:
        raise FileNotFoundError(f"ID{session_dir.name}: no results CSV for set {set_number}")

    frames = [(path, _read_stimulus_rows(path, set_number)) for path in candidates]
    complete = [(path, frame) for path, frame in frames if _is_complete_set(frame)]
    if len(complete) == 1:
        path, frame = complete[0]
        return frame.sort_values("Trial").reset_index(drop=True), path.name
    if len(complete) > 1:
        reference = complete[0][1].sort_values("Trial")["RT_recomputed_ms"].to_numpy()
        if all(
            np.allclose(
                reference,
                frame.sort_values("Trial")["RT_recomputed_ms"].to_numpy(),
                rtol=0.0,
                atol=1e-6,
            )
            for _, frame in complete[1:]
        ):
            path, frame = complete[-1]
            note = f"{path.name} (selected from {len(complete)} identical complete files)"
            return frame.sort_values("Trial").reset_index(drop=True), note
        names = [path.name for path, _ in complete]
        raise ValueError(f"Set {set_number}: multiple non-identical complete files: {names}")

    combined = pd.concat([frame for _, frame in frames], ignore_index=True)
    selected: list[pd.Series] = []
    for trial in range(1, N_TRIALS + 1):
        rows = combined.loc[combined["Trial"] == trial]
        if rows.empty:
            raise ValueError(f"Set {set_number}: Trial {trial} is missing")
        values = rows["RT_recomputed_ms"].dropna().to_numpy(dtype=float)
        if values.size == 0:
            raise ValueError(f"Set {set_number}: Trial {trial} has no calculable RT")
        if not np.allclose(values, values[0], rtol=0.0, atol=1e-6):
            raise ValueError(f"Set {set_number}: Trial {trial} has conflicting duplicate RTs")
        selected.append(rows.iloc[-1])
    reconstructed = pd.DataFrame(selected).reset_index(drop=True)
    if not _is_complete_set(reconstructed):
        raise ValueError(f"Set {set_number}: could not reconstruct 320 unique trials")
    note = "reconstructed from " + ", ".join(path.name for path, _ in frames)
    return reconstructed, note


def process_session(
    raw_root: Path,
    session_id: str,
    condition: str,
    product: str,
) -> SessionResult:
    """Load, validate, clean, and smooth all six sets for one session."""

    session_dir = raw_root / session_id
    if not session_dir.is_dir():
        raise FileNotFoundError(f"Behavior directory not found: {session_dir}")

    sets: list[pd.DataFrame] = []
    notes: list[str] = []
    for set_number in range(1, N_SETS + 1):
        frame, note = _select_set(session_dir, set_number)
        frame = frame.copy()
        frame["Set"] = set_number
        sets.append(frame)
        notes.append(f"Set{set_number}: {note}")
    trials = pd.concat(sets, ignore_index=True)
    if len(trials) != N_SETS * N_TRIALS:
        raise ValueError(f"ID{session_id}: expected 1920 stimulus trials, found {len(trials)}")

    recomputed = trials["RT_recomputed_ms"].to_numpy(dtype=float)
    csv_rt = trials["RT(ms)"].to_numpy(dtype=float)
    rt_match = "一致" if np.allclose(recomputed, csv_rt, rtol=0.0, atol=1e-6) else "不一致"

    eeg_missing_set = EEG_MISSING_SET_BY_SESSION.get(session_id)
    eeg_missing = np.zeros(len(trials), dtype=bool)
    if eeg_missing_set is not None:
        eeg_missing = trials["Set"].to_numpy(dtype=int) == eeg_missing_set

    analysis_rt = recomputed.copy()
    analysis_rt[eeg_missing] = np.nan
    finite_analysis_rt = analysis_rt[np.isfinite(analysis_rt)]
    mean_rt = float(np.mean(finite_analysis_rt))
    sd_rt = float(np.std(finite_analysis_rt, ddof=1))
    lower = mean_rt - OUTLIER_SD * sd_rt
    upper = mean_rt + OUTLIER_SD * sd_rt
    outlier = np.isfinite(analysis_rt) & ((analysis_rt < lower) | (analysis_rt > upper))
    trials["EEG_missing_set"] = eeg_missing
    trials["RT_raw_ms"] = analysis_rt
    trials["Outlier_2SD"] = outlier
    trials["RT_clean_ms"] = np.where(outlier, np.nan, analysis_rt)
    trials["RT_smoothed_ms"] = np.nan
    trials["Progress_within_set_pct"] = 1.0 + (
        (trials["Trial"].astype(float) - 1.0) / (N_TRIALS - 1.0) * 99.0
    )
    trials["Global_progress_pct"] = (
        (trials["Set"].astype(float) - 1.0) * 100.0 + trials["Progress_within_set_pct"]
    )
    for set_number in range(1, N_SETS + 1):
        mask = trials["Set"] == set_number
        values = trials.loc[mask, "RT_clean_ms"].to_numpy(dtype=float)
        trials.loc[mask, "RT_smoothed_ms"] = gaussian_moving_average(values)

    outlier_trials = "; ".join(
        f"Set{int(row.Set)}-Trial{int(row.Trial)}"
        for row in trials.loc[outlier, ["Set", "Trial"]].itertuples(index=False)
    )
    keep = [
        "Set",
        "Trial",
        "Progress_within_set_pct",
        "Global_progress_pct",
        "RT_raw_ms",
        "EEG_missing_set",
        "Outlier_2SD",
        "RT_clean_ms",
        "RT_smoothed_ms",
        "RT(ms)",
        "TiltOnset(ms)",
        "KeyPress(ms)",
        "ResponseType",
        "source_file",
    ]
    trials = trials[keep].copy()
    trials.insert(0, "condition", condition)
    trials.insert(0, "product", product)
    trials.insert(0, "session_id", session_id)
    return SessionResult(
        session_id=session_id,
        condition=condition,
        product=product,
        trials=trials,
        mean_rt_ms=mean_rt,
        sd_rt_ms=sd_rt,
        lower_2sd_ms=lower,
        upper_2sd_ms=upper,
        outlier_count=int(outlier.sum()),
        outlier_trials=outlier_trials or "なし",
        valid_rt_count=int(np.isfinite(trials["RT_clean_ms"]).sum()),
        rt_match=rt_match,
        source_notes=" | ".join(notes),
        eeg_missing_set=eeg_missing_set,
    )


def _qc_row(result: SessionResult) -> dict[str, object]:
    return {
        "session_id": result.session_id,
        "product": result.product,
        "condition": result.condition,
        "six_sets_confirmed": True,
        "320_trials_per_set_confirmed": True,
        "mean_rt_ms": result.mean_rt_ms,
        "sd_rt_ms_ddof1": result.sd_rt_ms,
        "lower_2sd_ms": result.lower_2sd_ms,
        "upper_2sd_ms": result.upper_2sd_ms,
        "outlier_count": result.outlier_count,
        "outlier_trials": result.outlier_trials,
        "valid_rt_count": result.valid_rt_count,
        "rt_match": result.rt_match,
        "eeg_missing_set": (
            f"Set{result.eeg_missing_set}" if result.eeg_missing_set is not None else "なし"
        ),
        "analysis_set_count": N_SETS - int(result.eeg_missing_set is not None),
        "eeg_missing_trial_count": N_TRIALS if result.eeg_missing_set is not None else 0,
        "source_notes": result.source_notes,
    }


def figure_y_upper_limit(values: np.ndarray) -> float:
    """Place the largest smoothed RT near 70% of a zero-based y-axis."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    if finite.size == 0:
        return 100.0
    target = float(np.max(finite)) / 0.70
    return max(100.0, float(np.ceil(target / 100.0) * 100.0))


def grand_figure_y_upper_limit(values: np.ndarray, product: str) -> float:
    """Place the largest upper SD bound near 87.5% of a zero-based y-axis."""

    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    product_dir, _, _ = normalize_product(product)
    minimum = 2_000.0 if product_dir == "CCube" else 100.0
    if finite.size == 0:
        return minimum
    target = float(np.max(finite)) / 0.875
    return max(minimum, float(np.ceil(target / 100.0) * 100.0))


def _format_rt_axis(axis: plt.Axes, upper_limit: float) -> None:
    """Apply the fixed No1 axis and set-boundary presentation."""

    for boundary in range(1, N_SETS):
        boundary_x = boundary * 100.0 + 0.5
        axis.axvline(boundary_x, color="#9E9E9E", linestyle="--", linewidth=1.5)
    for set_number in range(1, N_SETS + 1):
        axis.text(
            (set_number - 0.5) * 100.0,
            0.96,
            f"Set {set_number}",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=22,
            color="#333333",
        )
    axis.set_xlim(0.0, N_SETS * 100.0)
    axis.set_ylim(0.0, upper_limit)
    axis.set_xticks(np.arange(0.0, N_SETS * 100.0 + 1.0, 50.0))
    axis.set_yticks(np.arange(0.0, upper_limit + 1.0, 500.0))
    axis.set_xlabel("Experimental Progress, %", fontsize=28, labelpad=18)
    axis.set_ylabel("Reaction Time (ms)", fontsize=28)
    axis.tick_params(axis="x", labelsize=20, width=1.5, length=6)
    axis.tick_params(axis="y", labelsize=20, width=1.5, length=6)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_individual(
    participant: ParticipantSpec,
    drops: SessionResult,
    control: SessionResult,
    path: Path,
) -> None:
    """Create one continuous six-set figure for a participant pair."""

    _, product_label, product_color = normalize_product(participant.product)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    drops_x = drops.trials["Global_progress_pct"].to_numpy(dtype=float)
    control_x = control.trials["Global_progress_pct"].to_numpy(dtype=float)
    axis.plot(
        control_x,
        control.trials["RT_smoothed_ms"],
        color=CONTROL_COLOR,
        linewidth=3,
        label="Control",
    )
    axis.plot(
        drops_x,
        drops.trials["RT_smoothed_ms"],
        color=product_color,
        linewidth=3,
        label=f"Eye Drop ({product_label})",
    )
    displayed = np.concatenate(
        [
            drops.trials["RT_smoothed_ms"].to_numpy(dtype=float),
            control.trials["RT_smoothed_ms"].to_numpy(dtype=float),
        ]
    )
    upper_limit = figure_y_upper_limit(displayed)
    _format_rt_axis(axis, upper_limit)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False, fontsize=20)
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def write_participant_outputs(
    output_root: Path,
    participant: ParticipantSpec,
    drops: SessionResult,
    control: SessionResult,
) -> dict[str, str]:
    """Write only authorized OneDrive outputs; never write a local processed copy."""

    product_dir, _, _ = normalize_product(participant.product)
    participant_dir = (
        output_root
        / "Phase2_行動データ解析"
        / "No1_ReactionTime"
        / product_dir
        / "Individual"
        / f"ID{participant.pair_id}"
    )
    participant_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"ID{participant.pair_id}_No1_RT"
    figure_path = participant_dir / f"{prefix}_Individual.png"
    qc_path = participant_dir / f"{prefix}_QC.csv"
    log_path = participant_dir / f"{prefix}_RunSummary.json"

    plot_individual(participant, drops, control, figure_path)
    pd.DataFrame([_qc_row(drops), _qc_row(control)]).to_csv(qc_path, index=False)
    summary = {
        "participant": {
            **asdict(participant),
            "pair_id": participant.pair_id,
            "control_session_id": participant.control_session_id,
            "eye_drops_visit": participant.eye_drops_visit,
        },
        "parameters": {
            "rt": "KeyPress(ms) - TiltOnset(ms)",
            "outlier": "session mean +/- 2 sample SD (ddof=1), after EEG-missing set masking",
            "outlier_replacement": "NaN; trial positions retained",
            "eeg_missing_set_rule": (
                "Only the affected session is NaN-masked in individual analysis; "
                "both paired conditions are masked for the same set in grand-average"
            ),
            "moving_average": "Gaussian, local support 20 trials, FWHM 9 trials",
            "gaussian_sigma_trials": float(GAUSSIAN_SIGMA),
            "grand_average_created": False,
            "local_processed_data_created": False,
        },
        "sessions": [_qc_row(drops), _qc_row(control)],
        "outputs": {
            "figure": str(figure_path),
            "qc": str(qc_path),
        },
        "completed_at": datetime.now().astimezone().isoformat(),
    }
    log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "directory": str(participant_dir),
        "figure": str(figure_path),
        "qc": str(qc_path),
        "summary": str(log_path),
    }


def _columnwise_mean_sd_n(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return NaN-aware mean, sample SD, and valid participant count."""

    values = np.asarray(matrix, dtype=float)
    valid = np.isfinite(values)
    count = valid.sum(axis=0)
    total = np.where(valid, values, 0.0).sum(axis=0)
    mean = np.divide(total, count, out=np.full(values.shape[1], np.nan), where=count > 0)
    squared = np.where(valid, (values - mean) ** 2, 0.0).sum(axis=0)
    variance = np.divide(
        squared,
        count - 1,
        out=np.full(values.shape[1], np.nan),
        where=count > 1,
    )
    return mean, np.sqrt(variance), count


def build_grand_average(results: list[dict[str, object]], product: str) -> pd.DataFrame:
    """Aggregate individual smoothed RT at identical set/trial positions."""

    product_dir, _, _ = normalize_product(product)
    selected = [
        result
        for result in results
        if normalize_product(result["participant"].product)[0] == product_dir
    ]
    if len(selected) < 2:
        raise ValueError(f"Grand-average for {product_dir} requires at least two participants")

    reference = selected[0]["drops"].trials[["Set", "Trial", "Global_progress_pct"]].reset_index(
        drop=True
    )
    drops_values: list[np.ndarray] = []
    control_values: list[np.ndarray] = []
    for result in selected:
        for condition in ("drops", "control"):
            trials = result[condition].trials.reset_index(drop=True)
            coordinates = trials[["Set", "Trial", "Global_progress_pct"]]
            if not coordinates.equals(reference):
                pair_id = result["participant"].pair_id
                raise ValueError(f"Participant {pair_id} has incompatible set/trial coordinates")
        pairwise_missing_sets = {
            value
            for value in (
                result["drops"].eeg_missing_set,
                result["control"].eeg_missing_set,
            )
            if value is not None
        }
        if len(pairwise_missing_sets) > 1:
            pair_id = result["participant"].pair_id
            raise ValueError(f"Participant {pair_id} has multiple EEG-missing sets")
        drops = result["drops"].trials["RT_smoothed_ms"].to_numpy(dtype=float).copy()
        control = result["control"].trials["RT_smoothed_ms"].to_numpy(dtype=float).copy()
        if pairwise_missing_sets:
            missing_set = next(iter(pairwise_missing_sets))
            missing_mask = reference["Set"].to_numpy(dtype=int) == missing_set
            drops[missing_mask] = np.nan
            control[missing_mask] = np.nan
        drops_values.append(drops)
        control_values.append(control)

    drops_mean, drops_sd, drops_n = _columnwise_mean_sd_n(np.vstack(drops_values))
    control_mean, control_sd, control_n = _columnwise_mean_sd_n(np.vstack(control_values))
    grand = reference.copy()
    grand["EyeDrop_mean_RT_ms"] = drops_mean
    grand["EyeDrop_SD_RT_ms"] = drops_sd
    grand["EyeDrop_N"] = drops_n
    grand["Control_mean_RT_ms"] = control_mean
    grand["Control_SD_RT_ms"] = control_sd
    grand["Control_N"] = control_n
    return grand


def plot_grand_average(grand: pd.DataFrame, product: str, path: Path) -> float:
    """Plot product-specific mean RT and between-participant mean +/- 1 SD."""

    _, product_label, product_color = normalize_product(product)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    x = grand["Global_progress_pct"].to_numpy(dtype=float)
    control_mean = grand["Control_mean_RT_ms"].to_numpy(dtype=float)
    control_sd = grand["Control_SD_RT_ms"].to_numpy(dtype=float)
    drops_mean = grand["EyeDrop_mean_RT_ms"].to_numpy(dtype=float)
    drops_sd = grand["EyeDrop_SD_RT_ms"].to_numpy(dtype=float)
    axis.fill_between(
        x,
        control_mean - control_sd,
        control_mean + control_sd,
        color=CONTROL_COLOR,
        alpha=0.18,
        linewidth=0,
    )
    axis.fill_between(
        x,
        drops_mean - drops_sd,
        drops_mean + drops_sd,
        color=product_color,
        alpha=0.18,
        linewidth=0,
    )
    axis.plot(x, control_mean, color=CONTROL_COLOR, linewidth=3, label="Control")
    axis.plot(
        x,
        drops_mean,
        color=product_color,
        linewidth=3,
        label=f"Eye Drop ({product_label})",
    )
    displayed = np.concatenate([control_mean + control_sd, drops_mean + drops_sd])
    upper_limit = grand_figure_y_upper_limit(displayed, product)
    _format_rt_axis(axis, upper_limit)
    axis.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.18),
        ncol=2,
        frameon=False,
        fontsize=20,
    )
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return upper_limit


def write_grand_average_outputs(
    output_root: Path,
    results: list[dict[str, object]],
    product: str,
) -> dict[str, str]:
    """Write the product-specific grand-average figure, values, and run summary."""

    product_dir, _, _ = normalize_product(product)
    selected = [
        result
        for result in results
        if normalize_product(result["participant"].product)[0] == product_dir
    ]
    grand = build_grand_average(results, product_dir)
    output_dir = (
        output_root
        / "Phase2_行動データ解析"
        / "No1_ReactionTime"
        / product_dir
        / "GrandAverage"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"No1_RT_GrandAverage_{product_dir}"
    figure_path = output_dir / f"{prefix}.png"
    values_path = output_dir / f"{prefix}_Values.csv"
    summary_path = output_dir / f"{prefix}_RunSummary.json"
    y_axis_upper_ms = plot_grand_average(grand, product_dir, figure_path)
    grand.to_csv(values_path, index=False)
    max_upper_sd_band_ms = float(
        np.nanmax(
            np.concatenate(
                [
                    grand["Control_mean_RT_ms"].to_numpy(dtype=float)
                    + grand["Control_SD_RT_ms"].to_numpy(dtype=float),
                    grand["EyeDrop_mean_RT_ms"].to_numpy(dtype=float)
                    + grand["EyeDrop_SD_RT_ms"].to_numpy(dtype=float),
                ]
            )
        )
    )
    summary = {
        "product": product_dir,
        "participant_count": len(selected),
        "participant_pairs": [result["participant"].pair_id for result in selected],
        "aggregation": "individual Gaussian-smoothed RT aligned by set and trial",
        "between_participant_variability": "sample SD (ddof=1), shown as mean +/- 1 SD",
        "missing_values": "NaN-aware by position; N stored for each condition and position",
        "pairwise_eeg_missing_sets": {
            result["participant"].pair_id: next(
                (
                    value
                    for value in (
                        result["drops"].eeg_missing_set,
                        result["control"].eeg_missing_set,
                    )
                    if value is not None
                ),
                None,
            )
            for result in selected
            if result["drops"].eeg_missing_set is not None
            or result["control"].eeg_missing_set is not None
        },
        "manifest_controls_inclusion": True,
        "figure_y_axis_upper_ms": y_axis_upper_ms,
        "max_upper_sd_band_ms": max_upper_sd_band_ms,
        "max_upper_sd_band_axis_ratio": max_upper_sd_band_ms / y_axis_upper_ms,
        "local_processed_data_created": False,
        "outputs": {"figure": str(figure_path), "values": str(values_path)},
        "completed_at": datetime.now().astimezone().isoformat(),
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "directory": str(output_dir),
        "figure": str(figure_path),
        "values": str(values_path),
        "summary": str(summary_path),
    }


def run_participant(raw_root: Path, output_root: Path, spec: ParticipantSpec) -> dict[str, object]:
    """Run both conditions for one participant using the shared pipeline."""

    product_dir, _, _ = normalize_product(spec.product)
    logging.info("Participant pair %s (%s)", spec.pair_id, product_dir)
    drops = process_session(raw_root, spec.drops_session_id, "目薬あり", product_dir)
    control = process_session(raw_root, spec.control_session_id, "コントロール", product_dir)
    outputs = write_participant_outputs(output_root, spec, drops, control)
    return {
        "participant": spec,
        "drops": drops,
        "control": control,
        "outputs": outputs,
    }


def run_batch(
    raw_root: Path,
    output_root: Path,
    specs: list[ParticipantSpec],
    *,
    skip_invalid_participants: bool,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Run the shared participant pipeline and optionally record invalid pairs."""

    results: list[dict[str, object]] = []
    exclusions: list[dict[str, str]] = []
    for spec in specs:
        try:
            results.append(run_participant(raw_root, output_root, spec))
        except (FileNotFoundError, ValueError) as error:
            if not skip_invalid_participants:
                raise
            exclusion = {
                "pair_id": spec.pair_id,
                "first_session_id": spec.first_session_id,
                "second_session_id": spec.second_session_id,
                "reason": str(error),
            }
            exclusions.append(exclusion)
            logging.error("Excluded participant %s: %s", spec.pair_id, error)
    return results, exclusions


def write_batch_summary(
    output_root: Path,
    specs: list[ParticipantSpec],
    results: list[dict[str, object]],
    exclusions: list[dict[str, str]],
    grand_outputs: list[dict[str, str]],
) -> Path:
    """Write the batch completion and exclusion record to the authorized output root."""

    output_dir = output_root / "Phase2_行動データ解析" / "No1_ReactionTime"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "No1_RT_BatchSummary.json"
    summary = {
        "requested_participant_count": len(specs),
        "completed_participant_count": len(results),
        "completed_pairs": [result["participant"].pair_id for result in results],
        "excluded_participant_count": len(exclusions),
        "excluded_participants": exclusions,
        "grand_average_outputs": grand_outputs,
        "same_shared_pipeline_for_all_participants": True,
        "completed_at": datetime.now().astimezone().isoformat(),
    }
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--participant",
        action="append",
        type=parse_participant,
        help="first_session:second_session:drops_session:product; repeat for a batch",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Private CSV with first_session_id,second_session_id,drops_session_id,product",
    )
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--grand-average",
        action="store_true",
        help="After all individual results, create a separate grand-average for each product group",
    )
    parser.add_argument(
        "--skip-invalid-participants",
        action="store_true",
        help=(
            "Record and exclude participant pairs with missing or invalid required trials, "
            "then continue the batch"
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = list(args.participant or [])
    if args.manifest:
        specs.extend(load_manifest(args.manifest))
    if not specs:
        raise SystemExit("Provide at least one --participant or --manifest")
    if len({spec.pair_id for spec in specs}) != len(specs):
        raise SystemExit("Duplicate participant pair in batch input")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results, exclusions = run_batch(
        args.raw_root,
        args.output_root,
        specs,
        skip_invalid_participants=args.skip_invalid_participants,
    )
    for result in results:
        outputs = result["outputs"]
        logging.info(
            "Completed participant %s: %s",
            result["participant"].pair_id,
            outputs["directory"],
        )
    grand_outputs: list[dict[str, str]] = []
    if args.grand_average:
        products = sorted(
            {normalize_product(result["participant"].product)[0] for result in results}
        )
        for product in products:
            outputs = write_grand_average_outputs(args.output_root, results, product)
            grand_outputs.append(outputs)
            logging.info("Completed grand-average %s: %s", product, outputs["directory"])
    batch_summary = write_batch_summary(
        args.output_root,
        specs,
        results,
        exclusions,
        grand_outputs,
    )
    logging.info("Completed batch summary: %s", batch_summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
