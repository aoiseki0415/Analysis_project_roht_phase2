"""Shared implementation for Phase 1 EEG input auditing and preprocessing.

The raw Desktop data are always read-only.  This module writes processed data
only below ``解析に必要なデータたち`` and human-facing QC only below the
authorised OneDrive result folder.
"""

# ruff: noqa: E501

from __future__ import annotations

import base64
import json
import logging
import math
import platform
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from io import StringIO
from pathlib import Path
from typing import Any

import h5py
import matplotlib

matplotlib.use("Agg")

import mne
import numpy as np
import pandas as pd
import scipy
from autoreject import Ransac
from matplotlib import pyplot as plt
from mne.preprocessing import ICA
from mne_icalabel.iclabel import iclabel_label_components
from scipy import signal

SFREQ = 256.0
PIPELINE_SPEC_VERSION = "phase1-fixed-2026-09-22.2"
RANDOM_SEED = 97
QC_FIGURE_STYLE_VERSION = "phase1-qc-v2"
FILTERED_COLOR = "#4472c4"
ICA_BEFORE_COLOR = "#1261a0"
ICA_AFTER_COLOR = "#d1495b"
BLINK_MEAN_COLOR = "#2e8b57"
EYE_BLINK_PROBABILITY_THRESHOLD = 0.80
ICA_ABSOLUTE_AMPLITUDE_THRESHOLD_UV = 500.0
ICA_ABSOLUTE_AMPLITUDE_PADDING_SECONDS = 1.0
HTML_ENVELOPE_BIN_SAMPLES = 64
EEG_PREFIX = "EEG."
CHANNELS = [
    "Cz",
    "Fz",
    "Fp1",
    "F7",
    "F3",
    "FC1",
    "C3",
    "FC5",
    "FT9",
    "T7",
    "CP5",
    "CP1",
    "P3",
    "P7",
    "PO9",
    "O1",
    "Pz",
    "Oz",
    "O2",
    "PO10",
    "P8",
    "P4",
    "CP2",
    "CP6",
    "T8",
    "FT10",
    "FC6",
    "C4",
    "FC2",
    "F4",
    "F8",
    "Fp2",
]
ICA_QC_GROUPS = (
    ("QC01_BlinkCheck", ("Fp1", "Fp2")),
    ("QC02_Frontal", ("Fz", "F3", "F4")),
    ("QC03_CentralTemporal", ("Cz", "T7", "T8")),
    ("QC04_ParietalOccipital", ("Pz", "O1", "O2")),
)
ICA_EXCLUSION_REVIEW_CODE = "QC05_ICAExclusionReview"
DISPLAY_CHANNELS = ICA_QC_GROUPS[0][1]
ALL_QC_CHANNELS = tuple(
    dict.fromkeys(channel for _, channels in ICA_QC_GROUPS for channel in channels)
)
SKIP_IDS = {"130", "230"}
SPLIT_EXCLUSIONS = {"109": {1}, "120": {6}, "135": {2}, "225": {4}}
SPLIT_PART_SETS = {
    "109": {2: 2, 3: 2, 4: 2, 5: 2, 6: 2},
    "120": {1: 1, 2: 1, 3: 1, 4: 1, 5: 1},
    "135": {1: 1, 3: 2, 4: 2, 5: 2, 6: 2},
    "225": {1: 1, 2: 1, 3: 1, 5: 2, 6: 2},
}
ICLABEL_CLASSES = [
    "brain",
    "muscle artifact",
    "eye blink",
    "heart beat",
    "line noise",
    "channel noise",
    "other",
]


@dataclass(frozen=True)
class ProjectPaths:
    raw_root: Path
    eeg_root: Path
    behavior_root: Path
    processed_root: Path
    onedrive_root: Path


@dataclass
class EegPart:
    part: int
    path: Path
    metadata: str
    original_timestamp: np.ndarray
    interpolated: np.ndarray
    data_uv: np.ndarray  # channels x samples


@dataclass(frozen=True)
class SetBoundary:
    set_number: int
    start_ms: float
    end_ms: float
    part: int
    start_sample: int
    end_sample: int
    usable: bool
    reason: str


def _normal(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _find_normalized_child(parent: Path, name: str) -> Path:
    wanted = _normal(name)
    for child in parent.iterdir():
        if _normal(child.name) == wanted:
            return child
    raise FileNotFoundError(f"指定フォルダが見つかりません: {parent / name}")


def resolve_project_paths() -> ProjectPaths:
    desktop = Path.home() / "Desktop"
    raw_root = _find_normalized_child(desktop, "SandBox_ロート案件（データ）")
    eeg_root = _find_normalized_child(raw_root, "EEGデータ")
    behavior_root = _find_normalized_child(raw_root, "行動データ")
    processed_root = _find_normalized_child(raw_root, "解析に必要なデータたち")

    cloud = Path.home() / "Library" / "CloudStorage"
    onedrive = _find_normalized_child(cloud, "OneDrive-個人用")
    od_desktop = _find_normalized_child(onedrive, "デスクトップ")
    sandbox = _find_normalized_child(od_desktop, "SandBoxプロジェクト")
    project = _find_normalized_child(sandbox, "ロート製薬フェーズ2 2026.5")
    onedrive_root = _find_normalized_child(project, "実験本番_本解析")
    return ProjectPaths(raw_root, eeg_root, behavior_root, processed_root, onedrive_root)


def configure_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"phase1:{log_path}")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def participant_output_directory_name(
    participant_id: str, output_label: str | None = None
) -> str:
    """Return the normal ID directory name or an explicitly labelled comparison run."""
    if output_label is None:
        return f"ID{participant_id}"
    if not re.fullmatch(r"[A-Za-z0-9_-]+", output_label):
        raise ValueError("output_labelは英数字・ハイフン・アンダースコアだけを使用してください")
    return f"ID{participant_id}_{output_label}"


def eligible_ids(paths: ProjectPaths) -> list[str]:
    ids = []
    for child in paths.behavior_root.iterdir():
        if child.is_dir() and re.fullmatch(r"\d{3}", child.name) and child.name not in SKIP_IDS:
            if discover_eeg_files(paths, child.name):
                ids.append(child.name)
    return sorted(ids, key=int)


def discover_eeg_files(paths: ProjectPaths, participant_id: str) -> list[Path]:
    pattern = re.compile(
        rf"^rht-mvp01-{re.escape(participant_id)}(?:-\d+)?_.*(?<!intervalMarker)\.csv$"
    )
    files = [p for p in paths.eeg_root.iterdir() if p.is_file() and pattern.match(p.name)]
    return sorted(files, key=lambda p: ("-2_" in p.name, p.name))


def _behavior_candidates(paths: ProjectPaths, participant_id: str) -> list[Path]:
    root = paths.behavior_root / participant_id
    return sorted(root.glob("**/behave/*_events.csv"))


def _read_events(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"SysUnixTime(ms)", "Event", "Detail"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: events列不足 {sorted(missing)}")
    return df


def select_behavior_session(paths: ProjectPaths, participant_id: str) -> tuple[Path, pd.DataFrame]:
    candidates: list[tuple[int, int, Path, pd.DataFrame]] = []
    for path in _behavior_candidates(paths, participant_id):
        events = _read_events(path)
        starts = events.loc[events["Event"].eq("block_start"), "Detail"]
        ends = events.loc[events["Event"].eq("block_end"), "Detail"]
        complete = len(
            set(pd.to_numeric(starts, errors="coerce").dropna().astype(int))
            & set(pd.to_numeric(ends, errors="coerce").dropna().astype(int))
        )
        candidates.append((complete, len(events), path, events))
    if not candidates:
        raise FileNotFoundError(f"ID{participant_id}: events.csvが見つかりません")
    complete, _, path, events = max(candidates, key=lambda item: (item[0], item[1], item[2].name))
    if complete < 6:
        raise ValueError(f"ID{participant_id}: 6セット完了したevents.csvを特定できません")
    return path, events


def _results_for_session(event_path: Path, participant_id: str) -> dict[int, Path]:
    prefix = event_path.name.removesuffix("_events.csv")
    output: dict[int, Path] = {}
    for set_number in range(1, 7):
        exact = event_path.parent / f"{prefix}_block{set_number}_results.csv"
        candidates = (
            [exact]
            if exact.exists()
            else sorted(event_path.parent.glob(f"*block{set_number}_results.csv"))
        )
        if len(candidates) != 1:
            raise ValueError(
                f"ID{participant_id} Set{set_number}: results.csvを一意に特定できません"
            )
        output[set_number] = candidates[0]
    return output


def read_eeg_part(path: Path, part_number: int, logger: logging.Logger) -> EegPart:
    logger.info("EEG読込開始 Part%d: %s", part_number, path.name)
    with path.open("r", encoding="utf-8-sig", errors="replace") as handle:
        metadata = handle.readline().rstrip("\n")
    usecols = ["OriginalTimestamp", "EEG.Interpolated", *[EEG_PREFIX + ch for ch in CHANNELS]]
    dtype = {"OriginalTimestamp": "float64", "EEG.Interpolated": "float32"}
    dtype.update({EEG_PREFIX + ch: "float32" for ch in CHANNELS})
    frame = pd.read_csv(path, skiprows=1, usecols=usecols, dtype=dtype, memory_map=True)
    if frame[usecols].isna().any().any():
        bad = frame[usecols].isna().sum()
        raise ValueError(f"{path.name}: EEG必須列にNaN {bad[bad.gt(0)].to_dict()}")
    timestamp = frame.pop("OriginalTimestamp").to_numpy(dtype=np.float64, copy=False)
    interpolated = frame.pop("EEG.Interpolated").to_numpy(dtype=np.float32, copy=False)
    data_uv = frame.to_numpy(dtype=np.float32, copy=False).T
    del frame
    logger.info(
        "EEG読込完了 Part%d: %d samples x %d ch", part_number, data_uv.shape[1], data_uv.shape[0]
    )
    return EegPart(part_number, path, metadata, timestamp, interpolated, data_uv)


def _parse_set_number(value: Any) -> int | None:
    try:
        return int(float(value))
    except TypeError, ValueError:
        match = re.search(r"(?:block=)?(\d+)", str(value))
        return int(match.group(1)) if match else None


def derive_boundaries(
    participant_id: str, parts: list[EegPart], events: pd.DataFrame
) -> list[SetBoundary]:
    timestamp_ranges = [
        (float(part.original_timestamp[0] * 1000), float(part.original_timestamp[-1] * 1000))
        for part in parts
    ]
    output = []
    exclusions = SPLIT_EXCLUSIONS.get(participant_id, set())
    forced_parts = SPLIT_PART_SETS.get(participant_id, {})
    for set_number in range(1, 7):
        start_rows = events.loc[events["Event"].eq("block_start")]
        end_rows = events.loc[events["Event"].eq("block_end")]
        starts = start_rows.loc[start_rows["Detail"].map(_parse_set_number).eq(set_number)]
        ends = end_rows.loc[end_rows["Detail"].map(_parse_set_number).eq(set_number)]
        if len(starts) != 1 or len(ends) != 1:
            raise ValueError(f"ID{participant_id} Set{set_number}: 境界イベントが一意でありません")
        start_ms = float(starts.iloc[0]["SysUnixTime(ms)"])
        end_ms = float(ends.iloc[0]["SysUnixTime(ms)"])
        matching = [
            i
            for i, (lo, hi) in enumerate(timestamp_ranges, start=1)
            if lo <= start_ms <= hi and lo <= end_ms <= hi
        ]
        part_number = forced_parts.get(set_number, matching[0] if len(matching) == 1 else 0)
        usable = set_number not in exclusions and part_number > 0
        reason = (
            "使用"
            if usable
            else (
                "既知の分割記録欠測セット"
                if set_number in exclusions
                else "単一取得区間に完全収容されない"
            )
        )
        if part_number:
            part = parts[part_number - 1]
            eeg_ms = part.original_timestamp * 1000.0
            start_sample = int(np.searchsorted(eeg_ms, start_ms, side="left"))
            end_sample = int(np.searchsorted(eeg_ms, end_ms, side="right"))
            if start_sample >= end_sample or end_sample > len(eeg_ms):
                usable = False
                reason = "セット境界とEEGサンプルが対応しない"
        else:
            start_sample = end_sample = -1
        output.append(
            SetBoundary(
                set_number, start_ms, end_ms, part_number, start_sample, end_sample, usable, reason
            )
        )
    return output


def sampling_audit(part: EegPart) -> dict[str, Any]:
    delta = np.diff(part.original_timestamp)
    positive = delta[delta > 0]
    median = float(np.median(positive))
    inferred = float(1.0 / median)
    return {
        "part": part.part,
        "input_file": part.path.name,
        "n_samples": int(part.data_uv.shape[1]),
        "n_channels": int(part.data_uv.shape[0]),
        "original_timestamp_start_s": float(part.original_timestamp[0]),
        "original_timestamp_end_s": float(part.original_timestamp[-1]),
        "median_sample_interval_ms": median * 1000.0,
        "inferred_sfreq_hz": inferred,
        "sfreq_256_ok": bool(abs(inferred - SFREQ) < 1.0),
        "nonpositive_timestamp_diffs": int(np.count_nonzero(delta <= 0)),
        "interpolated_fraction": float(np.mean(part.interpolated != 0)),
        "min_uv": float(np.min(part.data_uv)),
        "max_uv": float(np.max(part.data_uv)),
    }


def audit_participant(
    paths: ProjectPaths, participant_id: str, logger: logging.Logger
) -> dict[str, Any]:
    eeg_files = discover_eeg_files(paths, participant_id)
    if not eeg_files:
        raise FileNotFoundError(f"ID{participant_id}: EEG CSVが見つかりません")
    parts = [read_eeg_part(path, index, logger) for index, path in enumerate(eeg_files, start=1)]
    event_path, events = select_behavior_session(paths, participant_id)
    result_paths = _results_for_session(event_path, participant_id)
    boundaries = derive_boundaries(participant_id, parts, events)
    result_rows = {str(n): int(len(pd.read_csv(path))) for n, path in result_paths.items()}
    manifest = {
        "participant_id": participant_id,
        "created_on": date.today().isoformat(),
        "sampling_frequency_hz": SFREQ,
        "eeg_unit_in_csv": "uV",
        "mne_internal_unit": "V",
        "eeg_timebase": "OriginalTimestamp seconds; multiply by 1000 for behavior sync",
        "behavior_timebase": "SysUnixTime(ms), TiltOnsetSys(ms), KeyPressSys(ms)",
        "event_file": str(event_path),
        "result_files": {str(k): str(v) for k, v in result_paths.items()},
        "result_rows": result_rows,
        "parts": [sampling_audit(part) for part in parts],
        "sets": [asdict(boundary) for boundary in boundaries],
    }
    return {
        "manifest": manifest,
        "parts": parts,
        "events": events,
        "results": result_paths,
        "boundaries": boundaries,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def write_audit_outputs(
    paths: ProjectPaths,
    participant_id: str,
    audit: dict[str, Any],
    *,
    save_local_manifest: bool = True,
) -> tuple[Path | None, Path]:
    local_dir = paths.processed_root / "Phase1_脳波前処理" / "No1_InputAuditAndSynchronization"
    qc_dir = paths.onedrive_root / "Phase1_脳波前処理" / "No1_InputAuditAndSynchronization"
    local_path = local_dir / f"ID{participant_id}_input_manifest.json"
    if save_local_manifest:
        write_json(local_path, audit["manifest"])
    rows = []
    for part in audit["manifest"]["parts"]:
        rows.append({"record_type": "part", **part})
    for boundary in audit["manifest"]["sets"]:
        rows.append({"record_type": "set", **boundary})
    qc_dir.mkdir(parents=True, exist_ok=True)
    qc_path = qc_dir / f"ID{participant_id}_input_audit.csv"
    pd.DataFrame(rows).to_csv(qc_path, index=False)
    return local_path if save_local_manifest else None, qc_path


def make_mne_raw(data_uv: np.ndarray, channel_names: list[str] | None = None) -> mne.io.RawArray:
    channel_names = channel_names or CHANNELS
    info = mne.create_info(channel_names, SFREQ, ch_types="eeg")
    # RawArray receives already-filtered data, so record the known passband
    # without applying a second filter to the signal.
    with info._unlock():
        info["highpass"] = 1.0
        info["lowpass"] = 100.0
    info.set_montage(mne.channels.make_standard_montage("colin27_1020"), on_missing="warn")
    return mne.io.RawArray(data_uv.astype(np.float64) * 1e-6, info, verbose=False)


def filter_and_detrend(part: EegPart) -> tuple[np.ndarray, np.ndarray]:
    raw_v = part.data_uv.astype(np.float64) * 1e-6
    sos_stop = signal.butter(4, [49.0, 51.0], btype="bandstop", fs=SFREQ, output="sos")
    sos_band = signal.butter(4, [1.0, 100.0], btype="bandpass", fs=SFREQ, output="sos")
    filtered = signal.sosfiltfilt(sos_stop, raw_v, axis=1)
    filtered = signal.sosfiltfilt(sos_band, filtered, axis=1)
    detrended = signal.detrend(filtered, axis=1, type="linear", overwrite_data=True)
    return filtered, detrended


def channel_quality_signal(part: EegPart) -> np.ndarray:
    """Create the pre-notch signal used only for bad-channel decisions."""
    raw_v = part.data_uv.astype(np.float64) * 1e-6
    sos_band = signal.butter(4, [1.0, 100.0], btype="bandpass", fs=SFREQ, output="sos")
    bandpassed = signal.sosfiltfilt(sos_band, raw_v, axis=1)
    return signal.detrend(bandpassed, axis=1, type="linear", overwrite_data=True)


def _minmax_envelope(values: np.ndarray, max_points: int = 7000) -> tuple[np.ndarray, np.ndarray]:
    block = max(1, math.ceil(values.shape[-1] / max_points))
    usable = values.shape[-1] // block * block
    core = values[..., :usable].reshape(*values.shape[:-1], -1, block)
    low = np.min(core, axis=-1)
    high = np.max(core, axis=-1)
    return low, high


def _contiguous_true_regions(mask: np.ndarray) -> list[tuple[int, int]]:
    padded = np.pad(mask.astype(np.int8), (1, 1))
    changes = np.diff(padded)
    return list(zip(np.flatnonzero(changes == 1), np.flatnonzero(changes == -1), strict=True))


def detect_flatlines(data_v: np.ndarray, minimum_seconds: float = 30.0) -> list[dict[str, Any]]:
    minimum = int(round(minimum_seconds * SFREQ))
    candidates = []
    for channel_index, channel in enumerate(CHANNELS):
        exact_flat = np.diff(data_v[channel_index], prepend=np.nan) == 0
        for start, end in _contiguous_true_regions(exact_flat):
            if end - start >= minimum:
                candidates.append(
                    {
                        "channel": channel,
                        "reason": "continuous_zero_or_exact_flatline",
                        "start_s": start / SFREQ,
                        "end_s": end / SFREQ,
                        "duration_s": (end - start) / SFREQ,
                        "fraction": (end - start) / data_v.shape[1],
                    }
                )
    return candidates


def detect_line_noise(data_v: np.ndarray, z_threshold: float = 4.0) -> list[dict[str, Any]]:
    # clean_rawdata/clean_channels.m criterion: robust amplitude above 50 Hz
    # divided by robust amplitude below 50 Hz, robust-z-scored across channels.
    fir = signal.firwin(101, 45.0, fs=SFREQ)
    below_50 = signal.filtfilt(fir, [1.0], data_v, axis=1)
    above_50 = data_v - below_50
    channel_mad = np.median(np.abs(above_50 - np.median(above_50, axis=1)[:, None]), axis=1)
    signal_mad = np.median(np.abs(below_50 - np.median(below_50, axis=1)[:, None]), axis=1)
    noisiness = channel_mad / np.maximum(signal_mad, np.finfo(float).eps)
    median = np.median(noisiness)
    mad = 1.4826 * np.median(np.abs(noisiness - median))
    z = (noisiness - median) / max(mad, np.finfo(float).eps)
    return [
        {
            "channel": CHANNELS[i],
            "reason": "line_noise_above_4sd",
            "z_score": float(z[i]),
            "noise_to_signal_ratio": float(noisiness[i]),
            "recording_fraction": 1.0,
        }
        for i in np.flatnonzero(z > z_threshold)
    ]


def detect_ransac_channels(data_v: np.ndarray) -> list[dict[str, Any]]:
    lowpass = signal.butter(4, 45.0, btype="lowpass", fs=SFREQ, output="sos")
    data_v = signal.sosfiltfilt(lowpass, data_v, axis=1)
    window_samples = int(5 * SFREQ)
    n_epochs = data_v.shape[1] // window_samples
    if n_epochs < 2:
        return []
    epochs_data = (
        data_v[:, : n_epochs * window_samples]
        .reshape(data_v.shape[0], n_epochs, window_samples)
        .transpose(1, 0, 2)
    )
    info = mne.create_info(CHANNELS, SFREQ, ch_types="eeg")
    info.set_montage(mne.channels.make_standard_montage("colin27_1020"), on_missing="warn")
    epochs = mne.EpochsArray(epochs_data, info, verbose=False)
    ransac = Ransac(
        n_resample=50,
        min_channels=0.25,
        min_corr=0.80,
        unbroken_time=0.50,
        n_jobs=1,
        random_state=RANDOM_SEED,
        verbose=False,
    )
    ransac.fit(epochs)
    output = []
    for channel in ransac.bad_chs_:
        channel_index = CHANNELS.index(str(channel))
        poor = ransac.corr_[:, channel_index] < 0.80
        poor_indices = np.flatnonzero(poor)
        output.append(
            {
                "channel": str(channel),
                "reason": "ransac_correlation_below_0.80_for_over_50pct",
                "start_s": float(poor_indices[0] * 5.0),
                "end_s": float((poor_indices[-1] + 1) * 5.0),
                "duration_s": float(np.count_nonzero(poor) * 5.0),
                "recording_fraction": float(np.mean(poor)),
                "median_reconstruction_correlation": float(
                    np.median(ransac.corr_[:, channel_index])
                ),
            }
        )
    return output


def detect_bad_channels(
    raw_parts_v: list[np.ndarray],
    filtered_parts_v: list[np.ndarray],
    line_quality_parts_v: list[np.ndarray],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for part_number, (raw_v, line_v) in enumerate(
        zip(raw_parts_v, line_quality_parts_v, strict=True), start=1
    ):
        for item in detect_flatlines(raw_v):
            candidates.append({"part": part_number, **item})
        for item in detect_line_noise(line_v):
            candidates.append({"part": part_number, **item})
    concatenated = np.concatenate(filtered_parts_v, axis=1)
    for item in detect_ransac_channels(concatenated):
        candidates.append({"part": "all", **item})
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in candidates:
        unique[(str(item["channel"]), str(item["reason"]))] = item
    return list(unique.values())


def select_ica_channel_exclusion_candidates(
    candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Restrict automatic ICA-only exclusion to clear record-wide problems.

    The official-derived 4-SD line-noise and 0.80/50% RANSAC criteria remain
    exploratory detectors. Automatic ICA-only exclusion is more conservative:
    a >=30 s exact flatline, very strong line noise (>=6 robust SD), RANSAC
    failure over >=80% of the record, or agreement of at least two detectors.
    """
    reasons_by_channel: dict[str, set[str]] = {}
    for item in candidates:
        reasons_by_channel.setdefault(str(item["channel"]), set()).add(str(item["reason"]))
    output = []
    for item in candidates:
        reason = str(item["reason"])
        clear_problem = (
            reason == "continuous_zero_or_exact_flatline"
            or (reason == "line_noise_above_4sd" and float(item.get("z_score", 0.0)) >= 6.0)
            or (
                reason == "ransac_correlation_below_0.80_for_over_50pct"
                and float(item.get("recording_fraction", 0.0)) >= 0.80
            )
            or len(reasons_by_channel[str(item["channel"])]) >= 2
        )
        if clear_problem:
            output.append(item)
    return output


def build_ica_channel_exclusion_records(
    candidates: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Turn conservative bad-channel candidates into automatic ICA-only exclusions."""
    excluded_channels = sorted({str(item["channel"]) for item in candidates}, key=CHANNELS.index)
    records = [
        {
            "channel": channel,
            "decision": "automatically_excluded_from_ica_training_only",
            "final_eeg_handling": "retained_filtered_and_detrended_without_ica_projection",
            "reasons": [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"channel", "start_sample", "end_sample"}
                }
                for item in candidates
                if str(item["channel"]) == channel
            ],
        }
        for channel in excluded_channels
    ]
    return excluded_channels, records


def save_bad_channel_figures(
    qc_dir: Path,
    participant_id: str,
    parts: list[EegPart],
    filtered_parts_v: list[np.ndarray],
    candidates: list[dict[str, Any]],
) -> None:
    for candidate in candidates:
        channel = str(candidate["channel"])
        channel_index = CHANNELS.index(channel)
        part_numbers = (
            range(1, len(parts) + 1) if candidate["part"] == "all" else [candidate["part"]]
        )
        for part_number in part_numbers:
            filtered_uv = filtered_parts_v[part_number - 1][channel_index] * 1e6
            filtered_lo, filtered_hi = _minmax_envelope(filtered_uv)
            time = np.linspace(0, len(filtered_uv) / SFREQ, len(filtered_lo), endpoint=False)
            robust_limit = float(np.quantile(np.abs(filtered_uv), 0.999)) * 1.15
            limit = max(1.0, robust_limit)
            fig, axis = plt.subplots(1, 1, figsize=(15, 4.5))
            axis.fill_between(
                time,
                filtered_lo,
                filtered_hi,
                color=FILTERED_COLOR,
                linewidth=0,
                alpha=0.85,
                label="Filtered + detrended signal: min–max envelope",
            )
            axis.axhline(0.0, color="#222222", linewidth=0.8, label="0 µV reference")
            axis.set_ylim(-limit, limit)
            axis.set_ylabel(f"{channel} amplitude (µV)")
            axis.set_xlabel("Time from Part start (s)")
            axis.legend(loc="upper right")
            fig.suptitle(f"ID{participant_id} Part{part_number} {channel}: {candidate['reason']}")
            fig.tight_layout()
            fig.savefig(
                qc_dir
                / f"ID{participant_id}_Part{part_number}_{channel}_bad_channel_candidate.png",
                dpi=160,
            )
            plt.close(fig)


def _robust_z(values: np.ndarray, axis: int = 0) -> np.ndarray:
    median = np.median(values, axis=axis, keepdims=True)
    mad = 1.4826 * np.median(np.abs(values - median), axis=axis, keepdims=True)
    return (values - median) / np.maximum(mad, np.finfo(float).eps)


def absolute_amplitude_intervals(data_v: np.ndarray) -> list[tuple[int, int, str, int]]:
    """Find obviously excessive amplitudes for exclusion from ICA training only."""
    threshold_v = ICA_ABSOLUTE_AMPLITUDE_THRESHOLD_UV * 1e-6
    exceeded = np.abs(data_v) >= threshold_v
    flagged = np.any(exceeded, axis=0)
    if not np.any(flagged):
        return []
    edges = np.diff(np.pad(flagged.astype(np.int8), (1, 1)))
    starts = np.flatnonzero(edges == 1)
    ends = np.flatnonzero(edges == -1)
    padding = int(round(ICA_ABSOLUTE_AMPLITUDE_PADDING_SECONDS * SFREQ))
    intervals = []
    for raw_start, raw_end in zip(starts, ends, strict=True):
        affected = int(np.count_nonzero(np.any(exceeded[:, raw_start:raw_end], axis=1)))
        intervals.append(
            (
                max(0, int(raw_start) - padding),
                min(data_v.shape[1], int(raw_end) + padding),
                f"AbsoluteAmplitude_{ICA_ABSOLUTE_AMPLITUDE_THRESHOLD_UV:g}uV",
                affected,
            )
        )
    return intervals


def detect_ica_bad_intervals(
    data_v: np.ndarray, part_number: int, original_timestamp: np.ndarray
) -> list[dict[str, Any]]:
    """Detect burst/window artifacts without reconstructing the final EEG.

    The 0.5 s detector applies an ASR-compatible generalized-eigenvalue burst
    criterion of 20 against robust calibration covariance.  The 1 s detector
    implements the configured clean-windows tolerances and 25% bad-channel rule.
    Only detected time spans are returned; reconstructed ASR samples are never
    used downstream.
    """
    half = int(round(0.5 * SFREQ))
    step_half = half // 2
    starts = np.arange(0, data_v.shape[1] - half + 1, step_half)
    rms = np.stack(
        [np.sqrt(np.mean(np.square(data_v[:, start : start + half]), axis=1)) for start in starts]
    )
    rms_z = _robust_z(np.log(np.maximum(rms, np.finfo(float).tiny)), axis=0)
    calibration = np.all((rms_z >= -3.5) & (rms_z <= 3.5), axis=1)
    if np.count_nonzero(calibration) < max(20, int(0.05 * len(starts))):
        order = np.argsort(np.max(np.abs(rms_z), axis=1))
        calibration = np.zeros(len(starts), dtype=bool)
        calibration[order[: max(20, int(0.1 * len(starts)))]] = True
    calibration_samples = np.concatenate(
        [data_v[:, start : start + half] for start in starts[calibration]], axis=1
    )
    reference_cov = np.cov(calibration_samples)
    eigenvalues, eigenvectors = scipy.linalg.eigh(reference_cov)
    whitening = (eigenvectors / np.sqrt(np.maximum(eigenvalues, 1e-20))) @ eigenvectors.T
    burst_flags = []
    burst_affected = []
    for start in starts:
        window = data_v[:, start : start + half]
        whitened = whitening @ (window - np.mean(window, axis=1, keepdims=True))
        window_cov = np.cov(whitened)
        component_power = np.maximum(scipy.linalg.eigvalsh(window_cov), 0.0)
        burst_flags.append(float(np.sqrt(np.max(component_power))) > 20.0)
        channel_rms_z = np.abs(_robust_z(np.sqrt(np.mean(window * window, axis=1)), axis=0))
        burst_affected.append(int(np.count_nonzero(channel_rms_z > 7.0)))

    one = int(round(1.0 * SFREQ))
    step_one = max(1, int(round(one * (1.0 - 0.66))))
    starts_one = np.arange(0, data_v.shape[1] - one + 1, step_one)
    channel_rms = np.stack(
        [
            np.sqrt(np.mean(np.square(data_v[:, start : start + one]), axis=1))
            for start in starts_one
        ]
    )
    window_z = _robust_z(np.log(np.maximum(channel_rms, np.finfo(float).tiny)), axis=0)
    window_bad_channels = (window_z < -3.5) | (window_z > 7.0)
    window_flags = np.mean(window_bad_channels, axis=1) > 0.25

    intervals: list[tuple[int, int, str, int]] = absolute_amplitude_intervals(data_v)
    for flag, start, affected in zip(burst_flags, starts, burst_affected, strict=True):
        if flag:
            intervals.append((int(start), int(start + half), "ASR_BurstCriterion_20", affected))
    for flag, start, bads in zip(window_flags, starts_one, window_bad_channels, strict=True):
        if flag:
            intervals.append(
                (int(start), int(start + one), "WindowCriterion_0.25", int(bads.sum()))
            )
    if not intervals:
        return []
    intervals.sort()
    merged: list[list[Any]] = []
    for start, end, reason, affected in intervals:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
            merged[-1][2].add(reason)
            merged[-1][3] = max(merged[-1][3], affected)
        else:
            merged.append([start, end, {reason}, affected])
    return [
        {
            "part": part_number,
            "start_original_timestamp_s": float(original_timestamp[start]),
            "end_original_timestamp_s": float(
                original_timestamp[min(end - 1, len(original_timestamp) - 1)]
            ),
            "reason": "+".join(sorted(reasons)),
            "affected_channel_count": int(affected),
            "start_sample": int(start),
            "end_sample": int(end),
        }
        for start, end, reasons, affected in merged
    ]


def mask_intervals(n_samples: int, intervals: list[dict[str, Any]], part_number: int) -> np.ndarray:
    keep = np.ones(n_samples, dtype=bool)
    for item in intervals:
        if item["part"] == part_number:
            keep[item["start_sample"] : item["end_sample"]] = False
    return keep


def infomax_convergence_diagnostics(
    log_text: str,
    *,
    reported_n_iter: int,
    max_iter: int,
    weight_change_threshold: float,
) -> dict[str, Any]:
    """Recover the actual Infomax stopping condition from MNE's log."""
    step_matches = re.findall(
        r"step\s+(\d+)\s+-\s+lrate\s+([0-9.eE+-]+),\s+wchange\s+([0-9.eE+-]+)",
        log_text,
    )
    if not step_matches:
        raise RuntimeError("Infomax ICAの反復ログを取得できませんでした")
    final_step, final_learning_rate, final_weight_change = step_matches[-1]
    final_step = int(final_step)
    final_learning_rate = float(final_learning_rate)
    final_weight_change = float(final_weight_change)
    if reported_n_iter < max_iter:
        converged = True
        stop_reason = "small_angle"
    elif final_weight_change < weight_change_threshold:
        converged = True
        stop_reason = "weight_change"
    else:
        converged = False
        stop_reason = "max_iterations"
    return {
        "converged": converged,
        "stop_reason": stop_reason,
        "actual_iterations": final_step,
        "mne_reported_n_iter": reported_n_iter,
        "final_weight_change": final_weight_change,
        "final_learning_rate": final_learning_rate,
    }


def fit_ica_and_label(
    training_v: np.ndarray, channel_names: list[str]
) -> tuple[ICA, mne.io.RawArray, np.ndarray, list[int], dict[str, Any]]:
    raw = make_mne_raw(training_v * 1e6, channel_names)
    rank = int(mne.compute_rank(raw, rank=None, verbose=False)["eeg"])
    block = int(np.ceil(min(5 * np.log(training_v.shape[1]), 0.3 * training_v.shape[1])))
    learning_rate = float(0.00065 / np.log(rank))
    ica = ICA(
        n_components=rank,
        method="infomax",
        random_state=RANDOM_SEED,
        max_iter=1000,
        # Match EEGLAB runica defaults for a decomposition below 33 components.
        fit_params={
            "extended": True,
            "w_change": 1e-6,
            "block": block,
            "l_rate": learning_rate,
            "anneal_step": 0.98,
            "verbose": "INFO",
        },
        verbose=False,
    )
    # MNE's Infomax implementation reports ``max_iter`` when the weight-change
    # stopping rule fires because it assigns ``step = max_iter`` internally.
    # Capture the final logged weight change so a valid early stop is not
    # mistaken for failure to converge.
    with mne.utils.catch_logging(verbose="INFO") as ica_log:
        ica.fit(raw, verbose="INFO")
    diagnostics = infomax_convergence_diagnostics(
        ica_log.getvalue(),
        reported_n_iter=int(ica.n_iter_),
        max_iter=1000,
        weight_change_threshold=1e-6,
    )
    probabilities = iclabel_label_components(raw, ica, inplace=True, backend="onnx")
    eye_column = ICLABEL_CLASSES.index("eye blink")
    eye_components = np.flatnonzero(
        probabilities[:, eye_column] >= EYE_BLINK_PROBABILITY_THRESHOLD
    ).astype(int).tolist()
    return ica, raw, probabilities, eye_components, diagnostics


def apply_ica(
    ica: ICA,
    data_v: np.ndarray,
    eye_components: list[int],
    channel_names: list[str],
) -> tuple[np.ndarray, np.ndarray]:
    raw = make_mne_raw(data_v * 1e6, channel_names)
    cleaned = raw.copy()
    ica.apply(cleaned, exclude=eye_components, verbose=False)
    cleaned_v = cleaned.get_data()
    return cleaned_v, data_v - cleaned_v


def _csv_text_for_results(path: Path) -> tuple[str, int]:
    frame = pd.read_csv(path)
    frame = frame.drop(columns=["TiltOnset(ms)", "KeyPress(ms)"], errors="ignore")
    buffer = StringIO()
    frame.to_csv(buffer, index=False, lineterminator="\n")
    return buffer.getvalue(), len(frame)


def _interval_annotations_for_set(
    intervals: list[dict[str, Any]], part_number: int, start: int, end: int
) -> list[dict[str, Any]]:
    output = []
    for item in intervals:
        if item["part"] != part_number:
            continue
        overlap_start = max(start, item["start_sample"])
        overlap_end = min(end, item["end_sample"])
        if overlap_start < overlap_end:
            output.append(
                {
                    "relative_start_s": (overlap_start - start) / SFREQ,
                    "relative_end_s": (overlap_end - start) / SFREQ,
                    "reason": item["reason"],
                    "affected_channel_count": item["affected_channel_count"],
                }
            )
    return output


def _interval_mask_for_set(
    intervals: list[dict[str, Any]], part_number: int, start: int, end: int
) -> np.ndarray:
    """Return a sample-aligned mask for intervals excluded from ICA training."""
    mask = np.zeros(end - start, dtype=bool)
    for item in intervals:
        if item["part"] != part_number:
            continue
        overlap_start = max(start, item["start_sample"])
        overlap_end = min(end, item["end_sample"])
        if overlap_start < overlap_end:
            mask[overlap_start - start : overlap_end - start] = True
    return mask


def merge_ica_cleaned_channels(
    full_detrended_v: np.ndarray,
    reduced_cleaned_v: np.ndarray,
    ica_included_channel_names: list[str],
    original_channel_names: list[str],
) -> np.ndarray:
    """Keep all original channels and replace only ICA-modelled rows with cleaned data."""
    if full_detrended_v.shape[0] != len(original_channel_names):
        raise ValueError("全チャンネル信号と元チャンネル名の数が一致しません")
    if reduced_cleaned_v.shape[0] != len(ica_included_channel_names):
        raise ValueError("信号行列と保持チャンネル名の列数が一致しません")
    if full_detrended_v.shape[1] != reduced_cleaned_v.shape[1]:
        raise ValueError("全チャンネル信号とICA適用信号のサンプル数が一致しません")
    if len(set(ica_included_channel_names)) != len(ica_included_channel_names):
        raise ValueError("保持チャンネル名に重複があります")
    unknown = sorted(set(ica_included_channel_names) - set(original_channel_names))
    if unknown:
        raise ValueError(f"元チャンネル一覧にないチャンネルがあります: {unknown}")
    merged = np.array(full_detrended_v, copy=True)
    source_index = {channel: index for index, channel in enumerate(ica_included_channel_names)}
    target_index = {channel: index for index, channel in enumerate(original_channel_names)}
    for channel, source in source_index.items():
        merged[target_index[channel]] = reduced_cleaned_v[source]
    return merged


def save_set_hdf5(
    path: Path,
    *,
    participant_id: str,
    boundary: SetBoundary,
    source_file: Path,
    data_v: np.ndarray,
    channel_names: list[str],
    original_timestamp: np.ndarray,
    results_csv: str,
    results_rows: int,
    bad_intervals: list[dict[str, Any]],
    original_channel_names: list[str],
    ica_excluded_channels: list[str],
    ica_excluded_channel_records: list[dict[str, Any]],
    data_kind: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = data_v.shape[1]
    relative_seconds = np.arange(n_samples, dtype=np.float64) / SFREQ
    if len(original_timestamp) != n_samples:
        raise ValueError("signalとOriginalTimestampの行数が一致しません")
    annotations = _interval_annotations_for_set(
        bad_intervals, boundary.part, boundary.start_sample, boundary.end_sample
    )
    exclusion_mask = _interval_mask_for_set(
        bad_intervals, boundary.part, boundary.start_sample, boundary.end_sample
    )
    utf8 = h5py.string_dtype("utf-8")
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            {
                "participant_id": participant_id,
                "set_number": boundary.set_number,
                "data_kind": data_kind,
                "sampling_frequency_hz": SFREQ,
                "signal_unit": "V",
                "source_part": boundary.part,
                "source_file": source_file.name,
                "timebase": "OriginalTimestamp",
                "pipeline_spec_version": PIPELINE_SPEC_VERSION,
                "original_channel_names_json": json.dumps(original_channel_names),
                "ica_excluded_channels_json": json.dumps(ica_excluded_channels),
            }
        )
        signal_group = handle.create_group("signal")
        signal_group.create_dataset(
            "data",
            data=data_v.T.astype(np.float32),
            compression="gzip",
            compression_opts=4,
            shuffle=True,
        )
        signal_group.create_dataset("channel_names", data=np.asarray(channel_names, dtype=utf8))
        time_group = handle.create_group("time")
        time_group.create_dataset("relative_seconds", data=relative_seconds)
        time_group.create_dataset("OriginalTimestamp", data=original_timestamp.astype(np.float64))
        behavior = handle.create_group("behavior")
        behavior.create_dataset("results_csv", data=results_csv, dtype=utf8)
        behavior.attrs["n_rows"] = results_rows
        qc = handle.create_group("qc")
        qc.create_dataset(
            "ica_channel_excluded_mask",
            data=np.asarray(
                [channel in ica_excluded_channels for channel in original_channel_names],
                dtype=bool,
            ),
        )
        qc.create_dataset(
            "ica_excluded_channel_records_json",
            data=json.dumps(ica_excluded_channel_records, ensure_ascii=False),
            dtype=utf8,
        )
        qc.create_dataset(
            "ica_training_excluded_mask",
            data=exclusion_mask,
            compression="gzip",
            compression_opts=4,
            shuffle=True,
        )
        qc.create_dataset(
            "ica_training_exclusions_json",
            data=json.dumps(annotations, ensure_ascii=False),
            dtype=utf8,
        )


def validate_hdf5(
    path: Path, expected_channel_names: list[str], expected_behavior_rows: int
) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        signal_shape = tuple(handle["signal/data"].shape)
        relative_count = len(handle["time/relative_seconds"])
        timestamp_count = len(handle["time/OriginalTimestamp"])
        exclusion_mask_count = len(handle["qc/ica_training_excluded_mask"])
        ica_channel_excluded_mask = handle["qc/ica_channel_excluded_mask"][:].astype(bool)
        saved_channel_names = [
            value.decode("utf-8") if isinstance(value, bytes) else str(value)
            for value in handle["signal/channel_names"][:]
        ]
        channel_count = len(saved_channel_names)
        original_channel_names = json.loads(handle.attrs["original_channel_names_json"])
        ica_excluded_channels = json.loads(handle.attrs["ica_excluded_channels_json"])
        raw_exclusion_records = handle["qc/ica_excluded_channel_records_json"][()]
        if isinstance(raw_exclusion_records, bytes):
            raw_exclusion_records = raw_exclusion_records.decode("utf-8")
        ica_excluded_channel_records = json.loads(str(raw_exclusion_records))
        expected_excluded_mask = np.asarray(
            [channel in ica_excluded_channels for channel in original_channel_names],
            dtype=bool,
        )
        mask_matches = np.array_equal(ica_channel_excluded_mask, expected_excluded_mask)
        record_channels = [record["channel"] for record in ica_excluded_channel_records]
        exclusion_records_match = sorted(record_channels) == sorted(ica_excluded_channels) and all(
            record.get("decision") == "automatically_excluded_from_ica_training_only"
            and bool(record.get("reasons"))
            for record in ica_excluded_channel_records
        )
        signal_data = handle["signal/data"][:]
        fixed_channel_layout_ok = True
        if str(handle.attrs["data_kind"]) == "brain_activity_eeg":
            fixed_channel_layout_ok = (
                saved_channel_names == original_channel_names
                and signal_shape[1] == len(original_channel_names)
                and bool(np.isfinite(signal_data).all())
            )
        else:
            fp1_excluded = "Fp1" in ica_excluded_channels
            fp2_excluded = "Fp2" in ica_excluded_channels
            expected_nan_columns = (fp1_excluded, fp2_excluded, fp1_excluded and fp2_excluded)
            fixed_channel_layout_ok = saved_channel_names == [
                "Fp1",
                "Fp2",
                "Fp1_Fp2_mean",
            ] and all(
                bool(np.isnan(signal_data[:, index]).all())
                if should_be_nan
                else bool(np.isfinite(signal_data[:, index]).all())
                for index, should_be_nan in enumerate(expected_nan_columns)
            )
        behavior_rows = int(handle["behavior"].attrs["n_rows"])
        ok = (
            signal_shape[0] == relative_count == timestamp_count == exclusion_mask_count
            and signal_shape[1] == channel_count == len(expected_channel_names)
            and saved_channel_names == expected_channel_names
            and mask_matches
            and exclusion_records_match
            and fixed_channel_layout_ok
            and behavior_rows == expected_behavior_rows
        )
        return {
            "path": str(path),
            "signal_shape": signal_shape,
            "relative_seconds_rows": relative_count,
            "original_timestamp_rows": timestamp_count,
            "ica_training_excluded_mask_rows": exclusion_mask_count,
            "channel_count": channel_count,
            "channel_names_match": saved_channel_names == expected_channel_names,
            "ica_channel_excluded_mask_matches": bool(mask_matches),
            "ica_excluded_channel_records_match": bool(exclusion_records_match),
            "fixed_channel_layout_ok": bool(fixed_channel_layout_ok),
            "behavior_rows": behavior_rows,
            "ok": bool(ok),
        }


def save_iclabel_outputs(
    qc_dir: Path,
    participant_id: str,
    ica: ICA,
    training_raw: mne.io.RawArray,
    probabilities: np.ndarray,
    eye_components: list[int],
) -> None:
    qc_dir.mkdir(parents=True, exist_ok=True)
    probability_frame = pd.DataFrame(probabilities, columns=ICLABEL_CLASSES)
    probability_frame.index.name = "component"
    probability_frame.to_csv(qc_dir / f"ID{participant_id}_ICLabel_probabilities.csv")
    if eye_components:
        for component in eye_components:
            figure = ica.plot_components(picks=[component], colorbar=True, show=False)
            if isinstance(figure, list):
                figure = figure[0]
            figure.suptitle(
                f"ID{participant_id}: removed eye component IC{component}\n"
                "Scalp color = ICA spatial weight [a.u.]",
                fontsize=11,
            )
            figure.savefig(
                qc_dir / f"ID{participant_id}_eye_IC_topomap_IC{component}.png", dpi=160
            )
            plt.close(figure)
        sources = ica.get_sources(training_raw).get_data(picks=eye_components)
        fig, axes = plt.subplots(len(eye_components), 2, figsize=(14, 3.2 * len(eye_components)))
        axes = np.atleast_2d(axes)
        for row, component in enumerate(eye_components):
            trace = sources[row]
            stride = max(1, len(trace) // 10000)
            axes[row, 0].plot(
                np.arange(0, len(trace), stride) / SFREQ,
                trace[::stride],
                color=FILTERED_COLOR,
                lw=0.5,
                label=f"IC{component} activation",
            )
            axes[row, 0].set_title(f"IC{component}: time series")
            axes[row, 0].set_xlabel("Time in ICA training data (s)")
            axes[row, 0].set_ylabel("ICA activation [a.u.]")
            axes[row, 0].legend(loc="upper right", fontsize=8)
            frequencies, psd = signal.welch(trace, fs=SFREQ, nperseg=2048)
            keep = (frequencies >= 1) & (frequencies <= 100)
            axes[row, 1].semilogy(
                frequencies[keep],
                psd[keep],
                color=ICA_AFTER_COLOR,
                label=f"IC{component} power spectrum",
            )
            axes[row, 1].set_title(f"IC{component}: PSD")
            axes[row, 1].set_xlabel("Frequency (Hz)")
            axes[row, 1].set_ylabel("Power spectral density [a.u.^2/Hz]")
            axes[row, 1].legend(loc="upper right", fontsize=8)
        fig.suptitle(
            f"ID{participant_id}: removed eye-component diagnostics",
            fontsize=12,
        )
        fig.tight_layout()
        fig.savefig(qc_dir / f"ID{participant_id}_eye_IC_timeseries_PSD.png", dpi=160)
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(8, 3))
        ax.axis("off")
        ax.text(
            0.5,
            0.5,
            f"No IC reached eye blink probability ≥ {EYE_BLINK_PROBABILITY_THRESHOLD:.2f}",
            ha="center",
            va="center",
        )
        fig.savefig(qc_dir / f"ID{participant_id}_eye_IC_none.png", dpi=160)
        plt.close(fig)


def _encoded_float32(values: np.ndarray) -> str:
    return base64.b64encode(np.asarray(values, dtype="<f4").tobytes()).decode("ascii")


def _fixed_bin_minmax_envelope(
    values: np.ndarray, bin_samples: int
) -> tuple[np.ndarray, np.ndarray]:
    """Return a peak-preserving envelope for a long one-dimensional signal."""
    values = np.asarray(values, dtype=np.float32)
    if values.ndim != 1:
        raise ValueError("min/max envelope requires one-dimensional input")
    if bin_samples < 1:
        raise ValueError("bin_samples must be at least 1")
    padding = (-values.size) % bin_samples
    if padding:
        values = np.pad(values, (0, padding), constant_values=np.nan)
    bins = values.reshape(-1, bin_samples)
    finite = np.isfinite(bins)
    low = np.min(np.where(finite, bins, np.inf), axis=1)
    high = np.max(np.where(finite, bins, -np.inf), axis=1)
    empty = ~finite.any(axis=1)
    low[empty] = np.nan
    high[empty] = np.nan
    return low, high


def _static_svg_overview(
    participant_id: str,
    part_number: int,
    display_channels: tuple[str, ...],
    before_envelopes: list[tuple[np.ndarray, np.ndarray]],
    after_envelopes: list[tuple[np.ndarray, np.ndarray]],
    duration_s: float,
    shared_scale_uv: float,
    set_markers: list[dict[str, Any]],
    excluded_intervals: list[dict[str, Any]] | None = None,
    excluded_channels: list[str] | None = None,
    before_only: bool = False,
) -> str:
    """Build a visible overview for viewers that do not execute JavaScript."""
    excluded_intervals = excluded_intervals or []
    excluded_channels = excluded_channels or []
    width = 1600
    height = max(660, 76 + 30 * len(display_channels))
    left, right, top, bottom = 78, 18, 28, 48
    plot_width = width - left - right
    plot_height = height - top - bottom
    row_height = plot_height / len(display_channels)

    def reduce_envelope(low: np.ndarray, high: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        group = max(1, math.ceil(low.size / int(plot_width)))
        padding = (-low.size) % group
        if padding:
            low = np.pad(low, (0, padding), constant_values=np.nan)
            high = np.pad(high, (0, padding), constant_values=np.nan)
        return (
            np.nanmin(low.reshape(-1, group), axis=1),
            np.nanmax(high.reshape(-1, group), axis=1),
        )

    pieces = [
        f'<svg role="img" aria-label="ID{participant_id} Part{part_number} ICA overview" '
        f'viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">',
        '<rect width="100%" height="100%" fill="white"/>',
        '<style>text{font-family:system-ui,sans-serif;fill:#111}.axis{stroke:#222;stroke-width:1}'
        f'.grid{{stroke:#ddd;stroke-width:1}}.before{{stroke:{ICA_BEFORE_COLOR};stroke-width:.8;opacity:.70}}'
        f'.after{{stroke:{ICA_AFTER_COLOR};stroke-width:.8;opacity:.85}}'
        '.excluded-interval{fill:#d1495b;opacity:.16}'
        '.excluded-channel{fill:#f4b942;opacity:.18}'
        '.set-start{stroke:#2e8b57;stroke-width:1.5;stroke-dasharray:7 4}'
        '.set-end{stroke:#7b3f98;stroke-width:1.5;stroke-dasharray:3 4}</style>',
    ]
    reduced = []
    for channel_index in range(len(display_channels)):
        reduced.append(
            (
                reduce_envelope(*before_envelopes[channel_index]),
                reduce_envelope(*after_envelopes[channel_index]),
            )
        )
    shared_scale = max(1.0, shared_scale_uv)
    for tick in range(6):
        x = left + plot_width * tick / 5
        seconds = duration_s * tick / 5
        pieces.append(
            f'<line class="grid" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
            f'y2="{top + plot_height:.1f}"/><text x="{x:.1f}" '
            f'y="{top + plot_height + 22:.1f}" text-anchor="middle" '
            f'font-size="14">{seconds:.1f}</text>'
        )
    for interval in excluded_intervals:
        x1 = left + plot_width * float(interval["start_s"]) / max(duration_s, 1e-9)
        x2 = left + plot_width * float(interval["end_s"]) / max(duration_s, 1e-9)
        pieces.append(
            f'<rect class="excluded-interval" x="{x1:.1f}" y="{top}" '
            f'width="{max(1.0, x2 - x1):.1f}" height="{plot_height:.1f}"/>'
        )
    for marker in set_markers:
        x = left + plot_width * float(marker["time_s"]) / max(duration_s, 1e-9)
        css_class = "set-start" if marker["kind"] == "start" else "set-end"
        pieces.append(
            f'<line class="{css_class}" x1="{x:.1f}" y1="{top}" x2="{x:.1f}" '
            f'y2="{top + plot_height:.1f}"/><text x="{x + 3:.1f}" y="{top + 13:.1f}" '
            f'font-size="11">{marker["label"]}</text>'
        )
    for channel_index, channel in enumerate(display_channels):
        y_center = top + (channel_index + 0.5) * row_height
        (before_low, before_high), (after_low, after_high) = reduced[channel_index]
        if channel in excluded_channels:
            pieces.append(
                f'<rect class="excluded-channel" x="{left}" '
                f'y="{top + channel_index * row_height:.1f}" width="{plot_width}" '
                f'height="{row_height:.1f}"/>'
            )
        channel_label = f"{channel} [ICA除外]" if channel in excluded_channels else channel
        pieces.append(
            f'<line class="axis" x1="{left}" y1="{y_center:.1f}" '
            f'x2="{left + plot_width}" y2="{y_center:.1f}"/>'
            f'<text x="{left + 5}" y="{top + channel_index * row_height + 18:.1f}" '
            f'font-size="14">{channel_label}</text><text x="{left + 155}" '
            f'y="{top + channel_index * row_height + 18:.1f}" font-size="14">±{shared_scale:.1f} µV</text>'
        )
        plot_series = [("before", before_low, before_high)]
        if not before_only:
            plot_series.append(("after", after_low, after_high))
        for css_class, low, high in plot_series:
            denominator = max(1, low.size - 1)
            segments = []
            for index, (low_value, high_value) in enumerate(zip(low, high, strict=True)):
                x = left + plot_width * index / denominator
                y_low = y_center - low_value / shared_scale * row_height * 0.40
                y_high = y_center - high_value / shared_scale * row_height * 0.40
                segments.append(f'M{x:.1f},{y_low:.1f}V{y_high:.1f}')
            pieces.append(f'<path class="{css_class}" d="{"".join(segments)}"/>')
    pieces.extend(
        [
            f'<rect class="axis" fill="none" x="{left}" y="{top}" '
            f'width="{plot_width}" height="{plot_height}"/>',
            f'<text x="{left + plot_width / 2:.1f}" y="{height - 8}" '
            'text-anchor="middle" font-size="14">Time from Part start (s)</text>',
            '<text x="18" y="330" text-anchor="middle" font-size="14" '
            'transform="rotate(-90 18 330)">EEG amplitude (µV)</text>',
            '<line class="before" x1="1110" y1="18" x2="1135" y2="18"/>'
            '<text x="1142" y="23" font-size="14">Before ICA</text>',
            (
                '<rect class="excluded-interval" x="1240" y="10" width="22" height="12"/>'
                '<text x="1268" y="23" font-size="14">ICA学習除外区間</text>'
                if before_only
                else '<line class="after" x1="1325" y1="18" x2="1350" y2="18"/>'
                '<text x="1357" y="23" font-size="14">After ICA</text>'
            ),
            '</svg>',
        ]
    )
    return "".join(pieces)


def save_interactive_html(
    path: Path,
    participant_id: str,
    part_number: int,
    before_v: np.ndarray,
    after_v: np.ndarray,
    channel_names: list[str],
    display_channels: tuple[str, ...] = DISPLAY_CHANNELS,
    shared_scale_uv: float | None = None,
    set_markers: list[dict[str, Any]] | None = None,
    *,
    excluded_intervals: list[dict[str, Any]] | None = None,
    excluded_channels: list[str] | None = None,
    before_only: bool = False,
    title: str | None = None,
) -> None:
    picks = [channel_names.index(ch) for ch in display_channels]
    set_markers = set_markers or []
    excluded_intervals = excluded_intervals or []
    excluded_channels = excluded_channels or []
    if shared_scale_uv is None:
        shared_scale_uv = max(
            1.0,
            max(
                float(np.nanmax(np.abs(values[picks] * 1e6)))
                for values in (before_v, after_v)
            )
            * 1.08,
        )
    bin_samples = HTML_ENVELOPE_BIN_SAMPLES
    before_envelopes = [
        _fixed_bin_minmax_envelope(before_v[pick] * 1e6, bin_samples) for pick in picks
    ]
    after_envelopes = [
        _fixed_bin_minmax_envelope(after_v[pick] * 1e6, bin_samples) for pick in picks
    ]
    static_svg = _static_svg_overview(
        participant_id,
        part_number,
        display_channels,
        before_envelopes,
        after_envelopes,
        before_v.shape[1] / SFREQ,
        shared_scale_uv,
        set_markers,
        excluded_intervals,
        excluded_channels,
        before_only,
    )
    payload = {
        "sfreq": SFREQ,
        "channels": list(display_channels),
        "n_samples": int(before_v.shape[1]),
        "shared_scale_uv": float(shared_scale_uv),
        "set_markers": set_markers,
        "excluded_intervals": excluded_intervals,
        "excluded_channels": excluded_channels,
        "before_only": before_only,
        "before": [_encoded_float32(before_v[pick] * 1e6) for pick in picks],
    }
    if not before_only:
        payload["after"] = [_encoded_float32(after_v[pick] * 1e6) for pick in picks]
    canvas_height = max(660, 76 + 30 * len(display_channels))
    html = """<!doctype html><html lang=\"ja\"><head><meta charset=\"utf-8\">
<title>ICA before/after</title><style>
body{font-family:system-ui,sans-serif;margin:16px;color:#202124}.toolbar,.channels{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:8px 0}button{padding:5px 12px}canvas{border:1px solid #777;width:100%;height:__CANVAS_HEIGHT__px;touch-action:none;cursor:grab;display:none}#staticFallback{border:1px solid #777;width:100%;overflow:auto}#staticFallback svg{display:block;width:100%;height:auto;min-width:900px}.hint{color:#555}.legend{display:flex;gap:18px;flex-wrap:wrap}.swatch{display:inline-block;width:22px;height:3px;vertical-align:middle;margin-right:5px}.band{display:inline-block;width:22px;height:12px;vertical-align:middle;margin-right:5px}#readout{white-space:pre-wrap}</style></head><body>
<h1>__TITLE__</h1><div class=\"channels\" id=\"checks\"></div>
<div class=\"toolbar\"><button id=\"zoomIn\">x軸 拡大</button><button id=\"zoomOut\">x軸 縮小</button><button id=\"yZoomIn\">y軸 拡大</button><button id=\"yZoomOut\">y軸 縮小</button><button id=\"yReset\">y軸 初期化</button><button id=\"reset\">全体表示</button><span id=\"window\"></span><span id=\"yScale\"></span></div>
	<div class=\"legend\">__LEGEND__<span style=\"color:#2e8b57\">-- Set start</span><span style=\"color:#7b3f98\">-- Set end</span></div>
	<p class=\"hint\">__HINT__ ホイールまたはボタン: x軸拡大・縮小／波形を左右へドラッグまたは左右矢印キー: 時間移動（長押し中は連続移動）／y軸ボタン: 表示チャンネル共通縦軸の拡大・縮小・初期化／ダブルクリック: 全体表示／チェック: チャンネル切替。横軸はPart開始からの時間 (s)、縦軸はEEG amplitude (µV)。緑の破線はセット開始、紫の破線はセット終了です。x軸の表示範囲を変えても縦軸は自動変更しません。十分に拡大すると256 Hzの元波形を表示します。</p>
<p id=\"status\" class=\"hint\">JavaScriptが無効な表示環境でも、下の全体波形は表示されます。</p>
<div id=\"staticFallback\">__STATIC_SVG__</div>
<canvas id=\"plot\" width=\"1600\" height=\"__CANVAS_HEIGHT__\"></canvas><pre id=\"readout\"></pre>
<script id=\"waveformPayload\" type=\"application/json\">__PAYLOAD__</script>
<script>window.addEventListener('error',function(event){var status=document.getElementById('status');if(status){status.textContent='JavaScript error: '+(event.message||'unknown error')+' (line '+event.lineno+')';status.style.color='#b00020'}});</script>
<script>"use strict";try{const P=JSON.parse(document.getElementById('waveformPayload').textContent);
function decode(s){const b=atob(s),u=new Uint8Array(b.length);for(let i=0;i<b.length;i++)u[i]=b.charCodeAt(i);return new Float32Array(u.buffer)}
P.before=P.before.map(decode);if(P.after)P.after=P.after.map(decode);
let active=P.channels.map(()=>true),start=0,end=P.n_samples,drag=null,panTimer=null,panDirection=0;
const cv=document.getElementById('plot'),ctx=cv.getContext('2d'),left=78,right=18,top=28,bottom=48;
let baseSharedMax=Math.max(1,P.shared_scale_uv);let sharedYScale=baseSharedMax;
P.channels.forEach((c,i)=>{const l=document.createElement('label');l.innerHTML=`<input type=\"checkbox\" checked data-i=\"${i}\"> ${c}`;document.getElementById('checks').append(l)});
document.getElementById('checks').addEventListener('change',e=>{active[Number(e.target.dataset.i)]=e.target.checked;draw()});
function sampleTime(i){return i/P.sfreq}
function clampWindow(s,e){const minSpan=Math.min(P.n_samples,Math.ceil(P.sfreq*2));let span=Math.max(minSpan,Math.min(P.n_samples,Math.round(e-s)));s=Math.max(0,Math.min(P.n_samples-span,Math.round(s)));return[s,s+span]}
function zoom(factor,ratio=.5){const anchor=start+ratio*(end-start),span=(end-start)*factor;[start,end]=clampWindow(anchor-ratio*span,anchor+(1-ratio)*span);draw()}
function zoomY(factor){sharedYScale=Math.max(.1,Math.min(baseSharedMax*1000,sharedYScale*factor));draw()}
function pan(direction){const span=end-start;if(span>=P.n_samples)return;const shift=Math.max(1,Math.round(span*.05))*direction;[start,end]=clampWindow(start+shift,end+shift);draw()}
function stopPan(){if(panTimer!==null){clearInterval(panTimer);panTimer=null}panDirection=0}
function startPan(direction){if(panDirection===direction)return;stopPan();panDirection=direction;pan(direction);panTimer=setInterval(()=>pan(direction),80)}
function draw(){ctx.clearRect(0,0,cv.width,cv.height);const span=end-start,plotW=cv.width-left-right,plotH=cv.height-top-bottom,rows=P.channels.length,rh=plotH/rows;ctx.font='14px sans-serif';
 ctx.strokeStyle='#222';ctx.lineWidth=1;ctx.strokeRect(left,top,plotW,plotH);ctx.fillStyle='#111';ctx.textAlign='center';ctx.fillText('Time from Part start (s)',left+plotW/2,cv.height-8);ctx.save();ctx.translate(18,top+plotH/2);ctx.rotate(-Math.PI/2);ctx.fillText('EEG amplitude (µV)',0,0);ctx.restore();
 for(let tick=0;tick<=5;tick++){const px=left+plotW*tick/5,t=sampleTime(start+(end-start)*tick/5);ctx.strokeStyle='#ddd';ctx.beginPath();ctx.moveTo(px,top);ctx.lineTo(px,top+plotH);ctx.stroke();ctx.fillStyle='#111';ctx.fillText(t.toFixed(1),px,top+plotH+20)}
 P.excluded_intervals.forEach(interval=>{const a=interval.start_s*P.sfreq,b=interval.end_s*P.sfreq;if(b<start||a>end)return;const x1=left+(Math.max(a,start)-start)/Math.max(1,span)*plotW,x2=left+(Math.min(b,end)-start)/Math.max(1,span)*plotW;ctx.fillStyle='rgba(209,73,91,.16)';ctx.fillRect(x1,top,Math.max(1,x2-x1),plotH)});
 P.set_markers.forEach(marker=>{const sample=marker.time_s*P.sfreq;if(sample<start||sample>end)return;const x=left+(sample-start)/Math.max(1,span)*plotW;ctx.save();ctx.strokeStyle=marker.kind==='start'?'#2e8b57':'#7b3f98';ctx.setLineDash(marker.kind==='start'?[7,4]:[3,4]);ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(x,top);ctx.lineTo(x,top+plotH);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=ctx.strokeStyle;ctx.textAlign='left';ctx.fillText(marker.label,x+3,top+13);ctx.restore()});
 for(let ch=0;ch<rows;ch++){const y0=top+(ch+.5)*rh,isExcluded=P.excluded_channels.includes(P.channels[ch]);if(isExcluded){ctx.fillStyle='rgba(244,185,66,.18)';ctx.fillRect(left,top+ch*rh,plotW,rh)}ctx.strokeStyle='#bbb';ctx.beginPath();ctx.moveTo(left,y0);ctx.lineTo(left+plotW,y0);ctx.stroke();ctx.textAlign='left';ctx.fillStyle=isExcluded?'#9a4d00':'#111';ctx.fillText(P.channels[ch]+(isExcluded?' [ICA除外]':''),left+5,top+ch*rh+Math.min(17,rh*.75));if(!active[ch])continue;const series=P.before_only?[P.before[ch]]:[P.before[ch],P.after[ch]];ctx.fillText(`±${sharedYScale.toFixed(1)} µV`,left+155,top+ch*rh+Math.min(17,rh*.75));
  series.forEach((values,k)=>{ctx.strokeStyle=k?'__AFTER_COLOR__':'__BEFORE_COLOR__';ctx.globalAlpha=k?.85:.70;ctx.beginPath();if(span<=plotW*2){for(let i=start;i<end;i++){const x=left+(i-start)/Math.max(1,span-1)*plotW,y=y0-values[i]/sharedYScale*(rh*.40);if(i===start)ctx.moveTo(x,y);else ctx.lineTo(x,y)}}else{for(let px=0;px<plotW;px++){const a=Math.floor(start+px*span/plotW),b=Math.max(a+1,Math.floor(start+(px+1)*span/plotW));let lo=Infinity,hi=-Infinity;for(let j=a;j<Math.min(b,P.n_samples);j++){lo=Math.min(lo,values[j]);hi=Math.max(hi,values[j])}const yl=y0-lo/sharedYScale*(rh*.40),yh=y0-hi/sharedYScale*(rh*.40);ctx.moveTo(left+px,yl);ctx.lineTo(left+px,yh)}}ctx.stroke()});ctx.globalAlpha=1}
 document.getElementById('window').textContent=`表示範囲 ${sampleTime(start).toFixed(1)}–${sampleTime(end).toFixed(1)} s`;document.getElementById('yScale').textContent=`共通縦軸 ±${sharedYScale.toFixed(1)} µV`;}
document.getElementById('zoomIn').addEventListener('click',()=>zoom(.5));document.getElementById('zoomOut').addEventListener('click',()=>zoom(2));document.getElementById('yZoomIn').addEventListener('click',()=>zoomY(1/1.5));document.getElementById('yZoomOut').addEventListener('click',()=>zoomY(1.5));document.getElementById('yReset').addEventListener('click',()=>{sharedYScale=baseSharedMax;draw()});document.getElementById('reset').addEventListener('click',()=>{start=0;end=P.n_samples;sharedYScale=baseSharedMax;draw()});
document.addEventListener('keydown',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();startPan(e.key==='ArrowLeft'?-1:1)}});document.addEventListener('keyup',e=>{if(e.key==='ArrowLeft'||e.key==='ArrowRight'){e.preventDefault();stopPan()}});window.addEventListener('blur',stopPan);
cv.addEventListener('wheel',e=>{e.preventDefault();const rect=cv.getBoundingClientRect(),ratio=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width));zoom(e.deltaY>0?1.5:.67,ratio)},{passive:false});
cv.addEventListener('pointerdown',e=>{cv.setPointerCapture(e.pointerId);drag={x:e.clientX,s:start,span:end-start};cv.style.cursor='grabbing'});cv.addEventListener('pointerup',e=>{if(cv.hasPointerCapture(e.pointerId))cv.releasePointerCapture(e.pointerId);drag=null;cv.style.cursor='grab'});cv.addEventListener('pointercancel',()=>{drag=null;cv.style.cursor='grab'});
cv.addEventListener('pointermove',e=>{const rect=cv.getBoundingClientRect();if(drag){const delta=(e.clientX-drag.x)/rect.width*drag.span;[start,end]=clampWindow(drag.s-delta,drag.s-delta+drag.span);draw();return}const ratio=Math.max(0,Math.min(1,(e.clientX-rect.left)/rect.width)),i=Math.min(P.n_samples-1,Math.max(0,Math.floor(start+ratio*(end-start)))),t=sampleTime(i),intervals=P.excluded_intervals.filter(x=>x.start_s<=t&&t<=x.end_s).map(x=>x.reason).join(', ');document.getElementById('readout').textContent=`Cursor: t=${t.toFixed(3)} s`+(intervals?` | ICA学習除外区間: ${intervals}`:'')+' | '+P.channels.map((c,j)=>P.before_only?`${c}: ${P.before[j][i].toFixed(2)} µV`:`${c}: before ${P.before[j][i].toFixed(2)} µV, after ${P.after[j][i].toFixed(2)} µV`).join(' | ')});
cv.addEventListener('dblclick',()=>{start=0;end=P.n_samples;sharedYScale=baseSharedMax;draw()});draw();document.getElementById('staticFallback').style.display='none';cv.style.display='block';document.getElementById('status').textContent='インタラクティブ表示準備完了（256 Hzの元波形を保持・固定共通縦軸）';}catch(error){const status=document.getElementById('status');status.textContent='JavaScript initialization error: '+error.name+': '+error.message;status.style.color='#b00020';}
</script></body></html>"""
    page_title = title or (
        f"ID{participant_id} Part{part_number}: ICA before/after "
        f"({' / '.join(display_channels)})"
    )
    if before_only:
        legend = (
            f'<span><i class="swatch" style="background:{ICA_BEFORE_COLOR}"></i>Before ICA</span>'
            '<span><i class="band" style="background:rgba(209,73,91,.28)"></i>ICA学習除外区間</span>'
            '<span><i class="band" style="background:rgba(244,185,66,.32)"></i>ICA学習除外ch</span>'
        )
        hint = "赤い帯はICA学習から除外した時間帯、黄色の行と[ICA除外]表示はICA学習・適用から除外したチャンネルです。"
    else:
        legend = (
            f'<span><i class="swatch" style="background:{ICA_BEFORE_COLOR}"></i>Before ICA</span>'
            f'<span><i class="swatch" style="background:{ICA_AFTER_COLOR}"></i>After ICA</span>'
        )
        hint = ""
    html = html.replace("__TITLE__", page_title)
    html = html.replace("__LEGEND__", legend)
    html = html.replace("__HINT__", hint)
    html = html.replace("__CANVAS_HEIGHT__", str(canvas_height))
    html = html.replace("__STATIC_SVG__", static_svg)
    html = html.replace("__PAYLOAD__", json.dumps(payload, separators=(",", ":")))
    html = html.replace("__BEFORE_COLOR__", ICA_BEFORE_COLOR)
    html = html.replace("__AFTER_COLOR__", ICA_AFTER_COLOR)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def save_blink_signal_figure(
    path: Path,
    participant_id: str,
    boundary: SetBoundary,
    blink_signal_v: np.ndarray,
    excluded_intervals: list[dict[str, Any]],
) -> None:
    """Save the exact Phase 3 input signal as a set-level overview."""
    time = np.arange(blink_signal_v.shape[1]) / SFREQ
    values_uv = blink_signal_v * 1e6
    finite_values = np.abs(values_uv[np.isfinite(values_uv)])
    limit = max(1.0, float(np.max(finite_values)) * 1.05) if finite_values.size else 1.0
    max_points = 5000
    stride = max(1, math.ceil(blink_signal_v.shape[1] / max_points))
    envelope_time = []
    envelope_low = []
    envelope_high = []
    for values in values_uv:
        low, high = _fixed_bin_minmax_envelope(values, stride)
        n_bins = low.size
        envelope_time.append((np.arange(n_bins) * stride + stride / 2) / SFREQ)
        envelope_low.append(low)
        envelope_high.append(high)
    fig, axes = plt.subplots(3, 1, figsize=(14, 8), sharex=True)
    labels = ("Fp1", "Fp2", "Fp1/Fp2 mean")
    colors = (ICA_BEFORE_COLOR, ICA_AFTER_COLOR, BLINK_MEAN_COLOR)
    annotations = _interval_annotations_for_set(
        excluded_intervals, boundary.part, boundary.start_sample, boundary.end_sample
    )
    for axis, label, color, plot_time, low, high in zip(
        axes,
        labels,
        colors,
        envelope_time,
        envelope_low,
        envelope_high,
        strict=True,
    ):
        axis.fill_between(
            plot_time,
            low,
            high,
            color=color,
            alpha=0.70,
            linewidth=0,
            label=f"{label} removed Eye-IC contribution",
        )
        for index, annotation in enumerate(annotations):
            axis.axvspan(
                annotation["relative_start_s"],
                annotation["relative_end_s"],
                color="#808080",
                alpha=0.18,
                label="Excluded from ICA training" if index == 0 else None,
            )
        axis.axhline(0, color="#444444", lw=0.6)
        axis.set_ylabel(f"{label} amplitude (µV)")
        axis.set_ylim(-limit, limit)
        axis.legend(loc="upper right")
    axes[-1].set_xlim(0, time[-1] if time.size else 0)
    axes[-1].set_xlabel("Time from set start (s)")
    fig.suptitle(
        f"ID{participant_id} Set{boundary.set_number}: Phase 3 blink-analysis signal\n"
        f"Shared y-axis across channels; source data {SFREQ:g} Hz"
    )
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def qc_html_filename(participant_id: str, part_number: int, qc_code: str) -> str:
    return f"ID{participant_id}_Part{part_number}_{qc_code}_ICA_before_after.html"


def exclusion_review_html_filename(participant_id: str, part_number: int) -> str:
    return f"ID{participant_id}_Part{part_number}_{ICA_EXCLUSION_REVIEW_CODE}_BeforeICA.html"


def _excluded_intervals_for_part(
    intervals: list[dict[str, Any]], part_number: int
) -> list[dict[str, Any]]:
    """Convert saved ICA-training exclusions to Part-relative HTML annotations."""
    annotations = []
    for interval in intervals:
        if int(interval["part"]) != part_number:
            continue
        annotations.append(
            {
                "start_s": float(interval["start_sample"]) / SFREQ,
                "end_s": float(interval["end_sample"]) / SFREQ,
                "reason": str(interval["reason"]),
                "affected_channel_count": int(interval["affected_channel_count"]),
            }
        )
    return annotations


def save_ica_exclusion_review_html(
    path: Path,
    participant_id: str,
    part: EegPart,
    before_v: np.ndarray,
    intervals: list[dict[str, Any]],
    excluded_channels: list[str],
    set_markers: list[dict[str, Any]],
) -> None:
    """Save all 32 Before-ICA channels with interval/channel exclusions overlaid."""
    scale_uv = max(1.0, float(np.nanmax(np.abs(before_v * 1e6))) * 1.08)
    save_interactive_html(
        path,
        participant_id,
        part.part,
        before_v,
        before_v,
        CHANNELS,
        tuple(CHANNELS),
        scale_uv,
        set_markers,
        excluded_intervals=_excluded_intervals_for_part(intervals, part.part),
        excluded_channels=excluded_channels,
        before_only=True,
        title=(
            f"ID{participant_id} Part{part.part}: ICA学習除外確認 "
            "（Before ICA・全32ch）"
        ),
    )


def _shared_qc_scale_uv(
    before_parts_v: list[np.ndarray], after_parts_v: list[np.ndarray]
) -> float:
    picks = [CHANNELS.index(channel) for channel in ALL_QC_CHANNELS]
    maximum = max(
        float(np.nanmax(np.abs(data_v[picks] * 1e6)))
        for data_v in [*before_parts_v, *after_parts_v]
    )
    return max(1.0, maximum * 1.08)


def _set_markers_for_part(events: pd.DataFrame, part: EegPart) -> list[dict[str, Any]]:
    """Assign every start/end event independently to the Part containing its timestamp."""
    markers: list[dict[str, Any]] = []
    start_ms = float(part.original_timestamp[0] * 1000.0)
    end_ms = float(part.original_timestamp[-1] * 1000.0)
    marker_rows = events.loc[events["Event"].isin(["block_start", "block_end"])]
    for _, row in marker_rows.iterrows():
        event_ms = float(row["SysUnixTime(ms)"])
        if not start_ms <= event_ms <= end_ms:
            continue
        event_name = str(row["Event"])
        set_number = _parse_set_number(row["Detail"])
        kind = "start" if event_name == "block_start" else "end"
        markers.append(
            {
                "time_s": event_ms / 1000.0 - float(part.original_timestamp[0]),
                "label": f"Set{set_number} {kind}",
                "kind": kind,
            }
        )
    return sorted(markers, key=lambda marker: (float(marker["time_s"]), marker["kind"]))


def extract_blink_analysis_signal(
    blink_contribution_v: np.ndarray,
    ica_included_channel_names: list[str],
) -> np.ndarray:
    """Return Fp1, Fp2 and their available-channel mean from the Eye-IC projection."""
    signals = []
    for channel in ("Fp1", "Fp2"):
        if channel in ica_included_channel_names:
            signals.append(blink_contribution_v[ica_included_channel_names.index(channel)])
        else:
            signals.append(np.full(blink_contribution_v.shape[1], np.nan, dtype=float))
    stacked = np.vstack(signals)
    valid_count = np.sum(np.isfinite(stacked), axis=0)
    mean = np.full(stacked.shape[1], np.nan, dtype=float)
    np.divide(np.nansum(stacked, axis=0), valid_count, out=mean, where=valid_count > 0)
    return np.vstack([stacked, mean])


def regenerate_interactive_html_outputs(
    paths: ProjectPaths,
    participant_id: str,
    *,
    logger: logging.Logger,
    output_label: str | None = None,
) -> dict[str, Any]:
    """Rebuild only the interactive QC HTML from the saved ICA solution."""
    output_directory = participant_output_directory_name(participant_id, output_label)
    local_dir = (
        paths.processed_root
        / "Phase1_脳波前処理"
        / "No2_AutomatedPreProcessing"
        / output_directory
    )
    qc_dir = (
        paths.onedrive_root
        / "Phase1_脳波前処理"
        / "No2_AutomatedPreProcessing"
        / output_directory
    )
    metadata_path = local_dir / f"ID{participant_id}_preprocessing_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    ica_excluded_channels = list(metadata["ica_excluded_channels"])
    keep_channels = [channel for channel in CHANNELS if channel not in ica_excluded_channels]
    keep_indices = [CHANNELS.index(channel) for channel in keep_channels]
    eye_components = [int(component) for component in metadata["removed_eye_components"]]
    expected_parts = {int(part) for part in metadata["source_parts"]}

    audit = audit_participant(paths, participant_id, logger)
    saved_intervals = []
    parts_by_number = {part.part: part for part in audit["parts"]}
    for interval in metadata["ica_training_excluded_intervals"]:
        part_number = int(interval["part"])
        part = parts_by_number[part_number]
        saved_intervals.append(
            {
                **interval,
                "start_sample": int(
                    np.searchsorted(
                        part.original_timestamp,
                        float(interval["start_original_timestamp_s"]),
                        side="left",
                    )
                ),
                "end_sample": int(
                    np.searchsorted(
                        part.original_timestamp,
                        float(interval["end_original_timestamp_s"]),
                        side="right",
                    )
                ),
            }
        )
    ica = mne.preprocessing.read_ica(local_dir / f"ID{participant_id}_ica.fif", verbose="ERROR")
    outputs = []
    prepared_parts: list[tuple[EegPart, np.ndarray, np.ndarray]] = []
    for part in audit["parts"]:
        if part.part not in expected_parts:
            continue
        _, detrended_v = filter_and_detrend(part)
        reduced_v = detrended_v[keep_indices]
        cleaned_reduced_v, _ = apply_ica(ica, reduced_v, eye_components, keep_channels)
        cleaned_full_v = merge_ica_cleaned_channels(
            detrended_v, cleaned_reduced_v, keep_channels, CHANNELS
        )
        prepared_parts.append((part, detrended_v, cleaned_full_v))
    shared_scale_uv = _shared_qc_scale_uv(
        [item[1] for item in prepared_parts], [item[2] for item in prepared_parts]
    )
    for part, detrended_v, cleaned_full_v in prepared_parts:
        for qc_code, display_channels in ICA_QC_GROUPS:
            output_path = qc_dir / qc_html_filename(participant_id, part.part, qc_code)
            save_interactive_html(
                output_path,
                participant_id,
                part.part,
                detrended_v,
                cleaned_full_v,
                CHANNELS,
                display_channels,
                shared_scale_uv,
                _set_markers_for_part(audit["events"], part),
            )
            outputs.append(
                {
                    "part": part.part,
                    "qc_code": qc_code,
                    "path": str(output_path),
                    "size_bytes": output_path.stat().st_size,
                }
            )
        exclusion_output = qc_dir / exclusion_review_html_filename(
            participant_id, part.part
        )
        save_ica_exclusion_review_html(
            exclusion_output,
            participant_id,
            part,
            detrended_v,
            saved_intervals,
            ica_excluded_channels,
            _set_markers_for_part(audit["events"], part),
        )
        outputs.append(
            {
                "part": part.part,
                "qc_code": ICA_EXCLUSION_REVIEW_CODE,
                "path": str(exclusion_output),
                "size_bytes": exclusion_output.stat().st_size,
            }
        )
    logger.info("ID%s: interactive HTML regenerated without refitting ICA", participant_id)
    return {
        "participant_id": participant_id,
        "output_label": output_label,
        "ica_refitted": False,
        "outputs": outputs,
    }


def software_versions() -> dict[str, str]:
    import autoreject
    import mne_icalabel

    return {
        "python": platform.python_version(),
        "mne": mne.__version__,
        "mne_icalabel": mne_icalabel.__version__,
        "autoreject": autoreject.__version__,
        "numpy": np.__version__,
        "pandas": pd.__version__,
        "scipy": scipy.__version__,
        "h5py": h5py.__version__,
        "platform": platform.platform(),
    }


def preprocess_participant(
    paths: ProjectPaths,
    participant_id: str,
    *,
    logger: logging.Logger,
    output_label: str | None = None,
    save_local_data: bool = True,
) -> dict[str, Any]:
    audit = audit_participant(paths, participant_id, logger)
    write_audit_outputs(
        paths,
        participant_id,
        audit,
        save_local_manifest=save_local_data,
    )
    parts: list[EegPart] = audit["parts"]
    boundaries: list[SetBoundary] = audit["boundaries"]
    output_directory = participant_output_directory_name(participant_id, output_label)
    qc_dir = (
        paths.onedrive_root
        / "Phase1_脳波前処理"
        / "No2_AutomatedPreProcessing"
        / output_directory
    )
    local_dir = (
        paths.processed_root
        / "Phase1_脳波前処理"
        / "No2_AutomatedPreProcessing"
        / output_directory
    )
    qc_dir.mkdir(parents=True, exist_ok=True)
    if save_local_data:
        local_dir.mkdir(parents=True, exist_ok=True)

    detrended_parts: list[np.ndarray] = []
    line_quality_parts: list[np.ndarray] = []
    for part in parts:
        _, detrended = filter_and_detrend(part)
        detrended_parts.append(detrended)
        line_quality_parts.append(channel_quality_signal(part))

    exploratory_bad_candidates = detect_bad_channels(
        [part.data_uv for part in parts], detrended_parts, line_quality_parts
    )
    bad_candidates = select_ica_channel_exclusion_candidates(exploratory_bad_candidates)
    del line_quality_parts
    ica_excluded_channels, ica_excluded_channel_records = (
        build_ica_channel_exclusion_records(bad_candidates)
    )
    write_json(
        qc_dir / f"ID{participant_id}_bad_channel_exploratory_detections.json",
        exploratory_bad_candidates,
    )
    write_json(qc_dir / f"ID{participant_id}_bad_channel_candidates.json", bad_candidates)
    if bad_candidates:
        save_bad_channel_figures(qc_dir, participant_id, parts, detrended_parts, bad_candidates)
    write_json(
        qc_dir / f"ID{participant_id}_ICA_channel_exclusions.json",
        {
            "participant_id": participant_id,
            "ica_excluded_channels": ica_excluded_channels,
            "policy": (
                "保守的通知基準に該当したチャンネルを利用者承認なしでICA学習・"
                "ICA適用対象から自動除外し、最終32ch EEGではフィルタ・"
                "トレンド除去済み信号を保持する"
            ),
            "ica_excluded_channel_records": ica_excluded_channel_records,
            "decision_date": date.today().isoformat(),
        },
    )

    keep_channels = [ch for ch in CHANNELS if ch not in ica_excluded_channels]
    keep_indices = [CHANNELS.index(ch) for ch in keep_channels]
    ica_input_parts = [data_v[keep_indices] for data_v in detrended_parts]

    intervals: list[dict[str, Any]] = []
    for part, data_v in zip(parts, ica_input_parts, strict=True):
        intervals.extend(detect_ica_bad_intervals(data_v, part.part, part.original_timestamp))
    pd.DataFrame(
        [
            {k: value for k, value in item.items() if k not in {"start_sample", "end_sample"}}
            for item in intervals
        ],
        columns=[
            "part",
            "start_original_timestamp_s",
            "end_original_timestamp_s",
            "reason",
            "affected_channel_count",
        ],
    ).to_csv(qc_dir / f"ID{participant_id}_ICA_training_excluded_intervals.csv", index=False)

    training_segments = []
    for part, data_v in zip(parts, ica_input_parts, strict=True):
        usable_mask = np.zeros(data_v.shape[1], dtype=bool)
        for boundary in boundaries:
            if boundary.usable and boundary.part == part.part:
                usable_mask[boundary.start_sample : boundary.end_sample] = True
        usable_mask &= mask_intervals(data_v.shape[1], intervals, part.part)
        if np.any(usable_mask):
            training_segments.append(data_v[:, usable_mask])
    if not training_segments:
        raise RuntimeError(f"ID{participant_id}: ICA学習可能サンプルがありません")
    training_v = np.concatenate(training_segments, axis=1)
    ica, training_raw, probabilities, eye_components, ica_diagnostics = fit_ica_and_label(
        training_v, keep_channels
    )
    save_iclabel_outputs(qc_dir, participant_id, ica, training_raw, probabilities, eye_components)
    if save_local_data:
        ica.save(local_dir / f"ID{participant_id}_ica.fif", overwrite=True)

    expected_qc_parts = sorted({b.part for b in boundaries if b.usable})
    cleaned_parts: list[np.ndarray] = []
    blink_parts: list[np.ndarray] = []
    for _part, full_detrended_v, ica_input_v in zip(
        parts, detrended_parts, ica_input_parts, strict=True
    ):
        cleaned_reduced_v, blink_v = apply_ica(
            ica, ica_input_v, eye_components, keep_channels
        )
        cleaned_parts.append(
            merge_ica_cleaned_channels(
                full_detrended_v, cleaned_reduced_v, keep_channels, CHANNELS
            )
        )
        blink_parts.append(blink_v)
    qc_part_indices = [part_number - 1 for part_number in expected_qc_parts]
    shared_qc_scale_uv = _shared_qc_scale_uv(
        [detrended_parts[index] for index in qc_part_indices],
        [cleaned_parts[index] for index in qc_part_indices],
    )
    html_files = []
    exclusion_review_html_files = []
    for part_number in expected_qc_parts:
        part_index = part_number - 1
        for qc_code, display_channels in ICA_QC_GROUPS:
            html_path = qc_dir / qc_html_filename(participant_id, part_number, qc_code)
            save_interactive_html(
                html_path,
                participant_id,
                part_number,
                detrended_parts[part_index],
                cleaned_parts[part_index],
                CHANNELS,
                display_channels,
                shared_qc_scale_uv,
                _set_markers_for_part(audit["events"], parts[part_index]),
            )
            html_files.append(html_path)
        exclusion_html_path = qc_dir / exclusion_review_html_filename(
            participant_id, part_number
        )
        save_ica_exclusion_review_html(
            exclusion_html_path,
            participant_id,
            parts[part_index],
            detrended_parts[part_index],
            intervals,
            ica_excluded_channels,
            _set_markers_for_part(audit["events"], parts[part_index]),
        )
        exclusion_review_html_files.append(exclusion_html_path)

    validations = []
    generated_sets = []
    blink_figure_files = []
    for boundary in boundaries:
        if not boundary.usable:
            continue
        part = parts[boundary.part - 1]
        start, end = boundary.start_sample, boundary.end_sample
        brain_signal = cleaned_parts[boundary.part - 1][:, start:end]
        blink_signal = extract_blink_analysis_signal(
            blink_parts[boundary.part - 1][:, start:end], keep_channels
        )
        if save_local_data:
            results_csv, results_rows = _csv_text_for_results(
                audit["results"][boundary.set_number]
            )
            set_dir = local_dir / f"Set{boundary.set_number}"
            brain_path = (
                set_dir / f"ID{participant_id}_Set{boundary.set_number}_brain_activity.h5"
            )
            blink_path = (
                set_dir / f"ID{participant_id}_Set{boundary.set_number}_blink_signal.h5"
            )
            save_set_hdf5(
                brain_path,
                participant_id=participant_id,
                boundary=boundary,
                source_file=part.path,
                data_v=brain_signal,
                channel_names=CHANNELS,
                original_timestamp=part.original_timestamp[start:end],
                results_csv=results_csv,
                results_rows=results_rows,
                bad_intervals=intervals,
                original_channel_names=CHANNELS,
                ica_excluded_channels=ica_excluded_channels,
                ica_excluded_channel_records=ica_excluded_channel_records,
                data_kind="brain_activity_eeg",
            )
            save_set_hdf5(
                blink_path,
                participant_id=participant_id,
                boundary=boundary,
                source_file=part.path,
                data_v=blink_signal,
                channel_names=["Fp1", "Fp2", "Fp1_Fp2_mean"],
                original_timestamp=part.original_timestamp[start:end],
                results_csv=results_csv,
                results_rows=results_rows,
                bad_intervals=intervals,
                original_channel_names=CHANNELS,
                ica_excluded_channels=ica_excluded_channels,
                ica_excluded_channel_records=ica_excluded_channel_records,
                data_kind="removed_eye_component_signal",
            )
            validations.extend(
                [
                    validate_hdf5(brain_path, CHANNELS, results_rows),
                    validate_hdf5(
                        blink_path, ["Fp1", "Fp2", "Fp1_Fp2_mean"], results_rows
                    ),
                ]
            )
        blink_figure_path = (
            qc_dir
            / f"ID{participant_id}_Set{boundary.set_number}_blink_signal_timeseries.png"
        )
        save_blink_signal_figure(
            blink_figure_path,
            participant_id,
            boundary,
            blink_signal,
            intervals,
        )
        blink_figure_files.append(blink_figure_path)
        generated_sets.append(boundary.set_number)

    expected_sets = [b.set_number for b in boundaries if b.usable]
    qc_files = [str(path) for path in sorted(qc_dir.iterdir())]
    converged = bool(ica_diagnostics["converged"])
    before_all = np.concatenate(detrended_parts, axis=1)
    after_all = np.concatenate(cleaned_parts, axis=1)
    before_p99 = float(np.quantile(np.abs(before_all), 0.99) * 1e6)
    after_p99 = float(np.quantile(np.abs(after_all), 0.99) * 1e6)
    before_rms = float(np.sqrt(np.mean(np.square(before_all))) * 1e6)
    after_rms = float(np.sqrt(np.mean(np.square(after_all))) * 1e6)
    complete = (
        generated_sets == expected_sets
        and (not save_local_data or all(v["ok"] for v in validations))
        and converged
        and len(html_files) == len(expected_qc_parts) * len(ICA_QC_GROUPS)
        and all(path.exists() for path in html_files)
        and len(exclusion_review_html_files) == len(expected_qc_parts)
        and all(path.exists() for path in exclusion_review_html_files)
        and len(blink_figure_files) == len(expected_sets)
        and all(path.exists() for path in blink_figure_files)
    )
    summary = {
        "status": "complete" if complete else "needs_review",
        "participant_id": participant_id,
        "output_label": output_label,
        "execution_scope": (
            "full_with_local_analysis_data"
            if save_local_data
            else "onedrive_qc_only_without_local_analysis_data"
        ),
        "local_analysis_data_saved": save_local_data,
        "pipeline_spec_version": PIPELINE_SPEC_VERSION,
        "random_seed": RANDOM_SEED,
        "qc_figure_style_version": QC_FIGURE_STYLE_VERSION,
        "fixed_parameters": {
            "sampling_frequency_hz": SFREQ,
            "bandpass_hz": [1.0, 100.0],
            "bandstop_hz": [49.0, 51.0],
            "flatline_minimum_seconds": 30.0,
            "ica_absolute_amplitude_threshold_uv": ICA_ABSOLUTE_AMPLITUDE_THRESHOLD_UV,
            "ica_absolute_amplitude_padding_seconds": ICA_ABSOLUTE_AMPLITUDE_PADDING_SECONDS,
            "iclabel_eye_blink_threshold": EYE_BLINK_PROBABILITY_THRESHOLD,
        },
        "expected_sets": expected_sets,
        "generated_sets": generated_sets,
        "source_parts": expected_qc_parts,
        "ica_excluded_channels": ica_excluded_channels,
        "ica_excluded_channel_records": ica_excluded_channel_records,
        "brain_activity_channel_layout": {
            "channel_names": CHANNELS,
            "all_channels_retained": True,
            "ica_excluded_channels_keep_filtered_detrended_signal": True,
        },
        "ica_channel_excluded_mask": [
            channel in ica_excluded_channels for channel in CHANNELS
        ],
        "ica_training_excluded_intervals": [
            {k: v for k, v in item.items() if k not in {"start_sample", "end_sample"}}
            for item in intervals
        ],
        "ica_n_components": int(ica.n_components_),
        "ica_n_iter": int(ica.n_iter_),
        "ica_actual_iterations": int(ica_diagnostics["actual_iterations"]),
        "ica_converged": bool(converged),
        "ica_stop_reason": str(ica_diagnostics["stop_reason"]),
        "ica_final_weight_change": float(ica_diagnostics["final_weight_change"]),
        "ica_final_learning_rate": float(ica_diagnostics["final_learning_rate"]),
        "ica_stop_weight_change": 1e-6,
        "ica_block_size": int(
            np.ceil(min(5 * np.log(training_v.shape[1]), 0.3 * training_v.shape[1]))
        ),
        "ica_learning_rate": float(0.00065 / np.log(ica.n_components_)),
        "ica_anneal_step": 0.98,
        "removed_eye_components": eye_components,
        "removed_eye_probabilities": {
            str(index): float(probabilities[index, ICLABEL_CLASSES.index("eye blink")])
            for index in eye_components
        },
        "ica_before_after_overall_uv": {
            "absolute_amplitude_p99_before": before_p99,
            "absolute_amplitude_p99_after": after_p99,
            "rms_before": before_rms,
            "rms_after": after_rms,
        },
        "blink_signal_figure_sets": expected_sets,
        "qc_html_groups": [
            {"code": code, "channels": list(channels)}
            for code, channels in ICA_QC_GROUPS
        ],
        "qc_html_shared_scale_uv": shared_qc_scale_uv,
        "ica_exclusion_review_html": {
            "code": ICA_EXCLUSION_REVIEW_CODE,
            "channels": CHANNELS,
            "before_ica_only": True,
            "interval_exclusions_overlaid": True,
            "channel_exclusions_highlighted": True,
        },
        "blink_accuracy_review_html": "QC01_BlinkCheck (Fp1, Fp2) only",
        "iclabel_average_reference_deviation": (
            "ICLabel推奨の共通平均参照は、旧MATLAB実装との一貫性を優先して未実施"
        ),
        "validations": validations,
        "local_output": str(local_dir) if save_local_data else None,
        "onedrive_output": str(qc_dir),
        "qc_files": qc_files,
        "software_versions": software_versions(),
    }
    if save_local_data:
        write_json(local_dir / f"ID{participant_id}_preprocessing_metadata.json", summary)
    write_json(qc_dir / f"ID{participant_id}_QC_summary.json", summary)
    pd.DataFrame(
        [
            {
                "participant_id": participant_id,
                "status": summary["status"],
                "generated_sets": ",".join(map(str, generated_sets)),
                "ica_excluded_channels": ",".join(ica_excluded_channels) or "none",
                "ica_training_excluded_interval_count": len(intervals),
                "ica_converged": converged,
                "ica_n_iter": int(ica.n_iter_),
                "ica_actual_iterations": int(ica_diagnostics["actual_iterations"]),
                "ica_stop_reason": str(ica_diagnostics["stop_reason"]),
                "ica_final_weight_change": float(ica_diagnostics["final_weight_change"]),
                "removed_eye_components": ",".join(map(str, eye_components)) or "none",
            }
        ]
    ).to_csv(qc_dir / f"ID{participant_id}_QC_table.csv", index=False)
    logger.info("ID%s 前処理完了: status=%s", participant_id, summary["status"])
    return summary


def choose_ids(
    paths: ProjectPaths, participant_ids: list[str] | None, first_only: bool
) -> list[str]:
    ids = participant_ids or eligible_ids(paths)
    forbidden = sorted(set(ids) & SKIP_IDS)
    if forbidden:
        raise ValueError(f"解析対象外IDが指定されました: {forbidden}")
    missing = [
        participant_id for participant_id in ids if participant_id not in eligible_ids(paths)
    ]
    if missing:
        raise ValueError(f"入力が揃わないIDです: {missing}")
    return ids[:1] if first_only else ids
