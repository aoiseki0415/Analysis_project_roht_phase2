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
OUTLIER_SD = 3.0
CONTROL_COLOR = "#563A7C"
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
    lower_3sd_ms: float
    upper_3sd_ms: float
    outlier_count: int
    outlier_trials: str
    valid_rt_count: int
    rt_match: str
    source_notes: str


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

    mean_rt = float(np.mean(recomputed))
    sd_rt = float(np.std(recomputed, ddof=1))
    lower = mean_rt - OUTLIER_SD * sd_rt
    upper = mean_rt + OUTLIER_SD * sd_rt
    outlier = (recomputed < lower) | (recomputed > upper)
    trials["RT_raw_ms"] = recomputed
    trials["Outlier_3SD"] = outlier
    trials["RT_clean_ms"] = np.where(outlier, np.nan, recomputed)
    trials["RT_smoothed_ms"] = np.nan
    trials["Progress_within_set_pct"] = (trials["Trial"].astype(float) - 1.0) / (
        N_TRIALS - 1.0
    ) * 100.0
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
        "Outlier_3SD",
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
        lower_3sd_ms=lower,
        upper_3sd_ms=upper,
        outlier_count=int(outlier.sum()),
        outlier_trials=outlier_trials or "なし",
        valid_rt_count=int((~outlier).sum()),
        rt_match=rt_match,
        source_notes=" | ".join(notes),
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
        "lower_3sd_ms": result.lower_3sd_ms,
        "upper_3sd_ms": result.upper_3sd_ms,
        "outlier_count": result.outlier_count,
        "outlier_trials": result.outlier_trials,
        "valid_rt_count": result.valid_rt_count,
        "rt_match": result.rt_match,
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
        label=f"Eye Drop Condition ({product_label})",
    )
    for boundary in range(1, N_SETS):
        axis.axvline(boundary * 100.0, color="#9E9E9E", linestyle="--", linewidth=1.5)
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

    tick_positions: list[float] = []
    tick_labels: list[str] = []
    for set_number in range(N_SETS):
        tick_positions.extend(set_number * 100.0 + np.array([0.0, 25.0, 50.0, 75.0]))
        tick_labels.extend(["0", "25", "50", "75"])
    tick_positions.append(N_SETS * 100.0)
    tick_labels.append("100")

    displayed = np.concatenate(
        [
            drops.trials["RT_smoothed_ms"].to_numpy(dtype=float),
            control.trials["RT_smoothed_ms"].to_numpy(dtype=float),
        ]
    )
    upper_limit = figure_y_upper_limit(displayed)
    axis.set_xlim(0.0, N_SETS * 100.0)
    axis.set_ylim(0.0, upper_limit)
    axis.set_xticks(tick_positions, tick_labels)
    axis.set_xlabel("Experimental Progress Within Each Set, %", fontsize=28, labelpad=18)
    axis.set_ylabel("Reaction Time (ms)", fontsize=28)
    axis.tick_params(axis="both", labelsize=18, width=1.5, length=6)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
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
    trial_path = participant_dir / f"{prefix}_TrialData.csv"
    qc_path = participant_dir / f"{prefix}_QC.csv"
    log_path = participant_dir / f"{prefix}_RunSummary.json"

    plot_individual(participant, drops, control, figure_path)
    pd.concat([drops.trials, control.trials], ignore_index=True).to_csv(trial_path, index=False)
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
            "outlier": "session mean +/- 3 sample SD (ddof=1)",
            "outlier_replacement": "NaN; trial positions retained",
            "moving_average": "Gaussian, local support 20 trials, FWHM 9 trials",
            "gaussian_sigma_trials": float(GAUSSIAN_SIGMA),
            "grand_average_created": False,
            "local_processed_data_created": False,
        },
        "sessions": [_qc_row(drops), _qc_row(control)],
        "outputs": {
            "figure": str(figure_path),
            "trial_data": str(trial_path),
            "qc": str(qc_path),
        },
        "completed_at": datetime.now().astimezone().isoformat(),
    }
    log_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "directory": str(participant_dir),
        "figure": str(figure_path),
        "trial_data": str(trial_path),
        "qc": str(qc_path),
        "summary": str(log_path),
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
    results = []
    for spec in specs:
        results.append(run_participant(args.raw_root, args.output_root, spec))
    for result in results:
        outputs = result["outputs"]
        logging.info(
            "Completed participant %s: %s",
            result["participant"].pair_id,
            outputs["directory"],
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
