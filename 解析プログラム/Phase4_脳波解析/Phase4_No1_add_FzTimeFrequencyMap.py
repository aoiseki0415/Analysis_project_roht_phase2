#!/usr/bin/env python3
"""Phase 4 No1_add: Fz 1-30 Hz Grand-average time-frequency maps."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import h5py
import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import mne
import numpy as np
import pandas as pd

SCRIPT_VERSION = "phase4-no1-add-fz-tfm-2026-10-04.3"
CACHE_CONFIGURATION_VERSION = "phase4-no1-add-fz-tfm-2026-10-04.1"
ANALYSIS_STEM = "No1_add_FzTimeFrequencyMap"
CACHE_FILE_TAG = "FzTFM"
FOCUS_CHANNEL = "Fz"
DIFFERENCE_COLORBAR_LABEL = "Difference in PSD (µV²/Hz)"
N_SETS = 6
SFREQ = 256.0
WINDOW_SAMPLES = 256
STEP_SAMPLES = 256
PAD_SAMPLES = 128
FREQUENCIES_HZ = np.arange(1.0, 31.0, 1.0)
FOCUS_CHANNEL_INDEX = 1
PSD_WINDOW_BATCH_SIZE = 512
PSD_MASK_OVERLAP_THRESHOLD = 0.01
LOG3SD_MULTIPLIER = 3.0
SMOOTHING_SECONDS = 60
GROUP_PROGRESS_POINTS_PER_SET = 100
ABSOLUTE_PSD_COLOR_LIMIT = 30.0
ABSOLUTE_PSD_COLOR_TICKS = np.array([0.0, 10.0, 20.0, 30.0])
DIFFERENCE_COLOR_LIMIT = 20.0
DIFFERENCE_COLOR_TICKS = np.array([-20.0, -10.0, 0.0, 10.0, 20.0])
PRODUCTION_PARTICIPANT_COUNT = 40
PRODUCTION_PARTICIPANTS_PER_PRODUCT = 20
EXCLUDED_SESSION_IDS = {"130", "230"}
EXPECTED_MISSING_SETS = {"109": {1}, "120": {6}, "135": {2}, "225": {4}}
EXPECTED_CHANNEL_NAMES = [
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
PRODUCTS = {
    "ccube": ("CCube", "C Cube"),
    "c_cube": ("CCube", "C Cube"),
    "cキューブ": ("CCube", "C Cube"),
    "vrohtopremium": ("VRohtoPremium", "V Rohto Premium"),
    "v_rohto_premium": ("VRohtoPremium", "V Rohto Premium"),
    "vロート": ("VRohtoPremium", "V Rohto Premium"),
    "vロートプレミアム": ("VRohtoPremium", "V Rohto Premium"),
}

DEFAULT_INPUT_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/"
    "Phase1_脳波前処理/No2_AutomatedPreProcessing"
)
DEFAULT_CACHE_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/"
    "Phase4_脳波解析/No1_add_FzTimeFrequencyMap/TimeFrequencySeries"
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
            raise ValueError("The paired session IDs must differ")
        if self.drops_session_id not in {self.first_session_id, self.second_session_id}:
            raise ValueError("drops_session_id must belong to the pair")
        normalize_product(self.product)

    @property
    def pair_id(self) -> str:
        return f"{self.first_session_id}-{self.second_session_id}"

    @property
    def control_session_id(self) -> str:
        if self.drops_session_id == self.first_session_id:
            return self.second_session_id
        return self.first_session_id


@dataclass
class SetTFM:
    set_number: int
    raw_psd: np.ndarray
    relative_seconds_center: np.ndarray
    original_timestamp_center: np.ndarray
    set_progress_pct: np.ndarray
    global_progress_pct: np.ndarray
    source_center_sample: np.ndarray
    phase1_mask_fraction: np.ndarray
    broadband_psd: np.ndarray
    broadband_outlier_mask: np.ndarray


@dataclass
class SessionTFM:
    session_id: str
    condition: str
    pair_id: str
    product: str
    sets: dict[int, SetTFM]
    threshold_log: float
    threshold_linear: float
    log_mean: float
    log_sample_sd: float


def normalize_product(value: str) -> tuple[str, str]:
    key = value.strip().lower().replace(" ", "").replace("-", "")
    if key not in PRODUCTS:
        raise ValueError(f"Unknown product: {value}")
    return PRODUCTS[key]


def parse_participant(value: str) -> ParticipantSpec:
    parts = [part.strip() for part in value.split(":")]
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


def validate_specs(specs: list[ParticipantSpec], production_batch: bool) -> None:
    pairs = [spec.pair_id for spec in specs]
    sessions = [sid for spec in specs for sid in (spec.first_session_id, spec.second_session_id)]
    if len(pairs) != len(set(pairs)):
        raise ValueError("Manifest contains a duplicated participant pair")
    if len(sessions) != len(set(sessions)):
        raise ValueError("Manifest reuses a session ID")
    excluded = sorted(EXCLUDED_SESSION_IDS.intersection(sessions))
    if excluded:
        raise ValueError(f"Excluded session IDs are present: {excluded}")
    if production_batch:
        if len(specs) != PRODUCTION_PARTICIPANT_COUNT:
            raise ValueError(
                f"Production batch requires {PRODUCTION_PARTICIPANT_COUNT} pairs; got {len(specs)}"
            )
        counts: dict[str, int] = {}
        for spec in specs:
            product = normalize_product(spec.product)[0]
            counts[product] = counts.get(product, 0) + 1
        expected = {"CCube": 20, "VRohtoPremium": 20}
        if counts != expected:
            raise ValueError(f"Production product counts must be {expected}; got {counts}")


def input_path(root: Path, session_id: str, set_number: int) -> Path:
    return (
        root
        / f"ID{session_id}"
        / f"Set{set_number}"
        / (f"ID{session_id}_Set{set_number}_brain_activity.h5")
    )


def session_prefix(spec: ParticipantSpec, session_id: str) -> str:
    order = 1 if session_id == spec.first_session_id else 2
    return f"Pair{spec.pair_id}_{order:02d}_ID{session_id}"


def cache_path(root: Path, spec: ParticipantSpec, session_id: str) -> Path:
    return root / f"{session_prefix(spec, session_id)}_{CACHE_FILE_TAG}.h5"


def _decode_names(values: np.ndarray) -> list[str]:
    return [value.decode() if isinstance(value, bytes) else str(value) for value in values]


def validate_source(path: Path, session_id: str, set_number: int) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        required = [
            "signal/data",
            "signal/channel_names",
            "time/relative_seconds",
            "time/OriginalTimestamp",
            "qc/ica_training_excluded_mask",
        ]
        absent = [name for name in required if name not in handle]
        if absent:
            raise ValueError(f"{path}: missing {absent}")
        if str(handle.attrs.get("participant_id")) != session_id:
            raise ValueError(f"{path}: participant_id mismatch")
        if int(handle.attrs.get("set_number", -1)) != set_number:
            raise ValueError(f"{path}: set_number mismatch")
        if not np.isclose(float(handle.attrs.get("sampling_frequency_hz", np.nan)), SFREQ):
            raise ValueError(f"{path}: sampling rate must be 256 Hz")
        if str(handle.attrs.get("signal_unit")) != "V":
            raise ValueError(f"{path}: signal unit must be V")
        names = _decode_names(handle["signal/channel_names"][:])
        if names != EXPECTED_CHANNEL_NAMES or names[FOCUS_CHANNEL_INDEX] != FOCUS_CHANNEL:
            raise ValueError(f"{path}: fixed channel order mismatch")
        shape = handle["signal/data"].shape
        if len(shape) != 2 or shape[1] != len(EXPECTED_CHANNEL_NAMES) or shape[0] < 2:
            raise ValueError(f"{path}: invalid EEG shape {shape}")
        n_samples = shape[0]
        for name in required[2:]:
            if handle[name].shape != (n_samples,):
                raise ValueError(f"{path}: {name} length mismatch")
        relative = handle["time/relative_seconds"][:]
        original = handle["time/OriginalTimestamp"][:]
        if not np.isfinite(relative).all() or not np.isfinite(original).all():
            raise ValueError(f"{path}: non-finite timestamps")
        if np.any(np.diff(relative) <= 0) or np.any(np.diff(original) <= 0):
            raise ValueError(f"{path}: timestamps are not monotonic")
        if not np.allclose(np.diff(relative), 1.0 / SFREQ, rtol=0.0, atol=1e-8):
            raise ValueError(f"{path}: relative_seconds does not match 256 Hz")
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def preflight(specs: list[ParticipantSpec], root: Path) -> dict[str, Any]:
    fingerprints: list[dict[str, Any]] = []
    missing_by_session: dict[str, list[int]] = {}
    for spec in specs:
        for session_id in (spec.first_session_id, spec.second_session_id):
            missing: set[int] = set()
            for set_number in range(1, N_SETS + 1):
                path = input_path(root, session_id, set_number)
                if not path.exists():
                    missing.add(set_number)
                else:
                    fingerprints.append(validate_source(path, session_id, set_number))
            expected = EXPECTED_MISSING_SETS.get(session_id, set())
            if missing != expected:
                raise ValueError(
                    f"ID{session_id}: missing Sets {sorted(missing)}, expected {sorted(expected)}"
                )
            if missing:
                missing_by_session[session_id] = sorted(missing)
    return {
        "participant_pairs": len(specs),
        "session_ids": len(specs) * 2,
        "checked_files": len(fingerprints),
        "missing_by_session": missing_by_session,
        "inputs": fingerprints,
    }


def analysis_configuration() -> dict[str, Any]:
    return {
        "configuration_version": CACHE_CONFIGURATION_VERSION,
        "channel": FOCUS_CHANNEL,
        "sfreq_hz": SFREQ,
        "window_samples": WINDOW_SAMPLES,
        "step_samples": STEP_SAMPLES,
        "padding_samples": PAD_SAMPLES,
        "n_fft": WINDOW_SAMPLES,
        "n_per_seg": WINDOW_SAMPLES,
        "n_overlap": 0,
        "window": "hann",
        "remove_dc": True,
        "frequencies_hz": FREQUENCIES_HZ.tolist(),
        "phase1_mask_overlap_threshold": PSD_MASK_OVERLAP_THRESHOLD,
        "broadband_mask": "session_all_sets_log10_mean_plus_3_sample_sd_upper_only",
        "smoothing_seconds": SMOOTHING_SECONDS,
        "progress_points_per_set": GROUP_PROGRESS_POINTS_PER_SET,
    }


def configuration_hash(fingerprints: list[dict[str, Any]]) -> str:
    payload = {"configuration": analysis_configuration(), "inputs": fingerprints}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def window_centers(n_samples: int) -> np.ndarray:
    centers = np.arange(0, n_samples, STEP_SAMPLES, dtype=np.int64)
    if centers[-1] != n_samples - 1:
        centers = np.append(centers, n_samples - 1)
    return centers


def windowed_mask_fraction(mask: np.ndarray, centers: np.ndarray) -> np.ndarray:
    padded = np.pad(np.asarray(mask, dtype=float), (PAD_SAMPLES, PAD_SAMPLES), mode="reflect")
    return np.asarray(
        [padded[center : center + WINDOW_SAMPLES].mean() for center in centers],
        dtype=np.float32,
    )


def calculate_set_tfm(
    fz_v: np.ndarray,
    relative_seconds: np.ndarray,
    original_timestamp: np.ndarray,
    phase1_mask: np.ndarray,
    set_number: int,
) -> SetTFM:
    fz_v = np.asarray(fz_v, dtype=float)
    n_samples = fz_v.size
    centers = window_centers(n_samples)
    padded = np.pad(fz_v * 1e6, (PAD_SAMPLES, PAD_SAMPLES), mode="reflect")
    output = np.empty((centers.size, FREQUENCIES_HZ.size), dtype=np.float32)
    for start in range(0, centers.size, PSD_WINDOW_BATCH_SIZE):
        stop = min(start + PSD_WINDOW_BATCH_SIZE, centers.size)
        batch_centers = centers[start:stop]
        windows = np.stack([padded[center : center + WINDOW_SAMPLES] for center in batch_centers])
        psd, frequencies = mne.time_frequency.psd_array_welch(
            windows,
            sfreq=SFREQ,
            fmin=1.0,
            fmax=30.0,
            n_fft=WINDOW_SAMPLES,
            n_per_seg=WINDOW_SAMPLES,
            n_overlap=0,
            window="hann",
            average="mean",
            output="power",
            remove_dc=True,
            verbose=False,
        )
        if not np.array_equal(frequencies, FREQUENCIES_HZ):
            raise ValueError(f"Unexpected Welch bins: {frequencies.tolist()}")
        output[start:stop] = psd.astype(np.float32)
    progress = centers.astype(float) / float(n_samples - 1) * 100.0
    broadband = output.mean(axis=1).astype(np.float32)
    return SetTFM(
        set_number=set_number,
        raw_psd=output,
        relative_seconds_center=np.asarray(relative_seconds)[centers],
        original_timestamp_center=np.asarray(original_timestamp)[centers],
        set_progress_pct=progress,
        global_progress_pct=(set_number - 1) * 100.0 + progress,
        source_center_sample=centers,
        phase1_mask_fraction=windowed_mask_fraction(phase1_mask, centers),
        broadband_psd=broadband,
        broadband_outlier_mask=np.zeros(centers.size, dtype=bool),
    )


def calculate_broadband_mask(sets: dict[int, SetTFM]) -> dict[str, Any]:
    pieces: list[np.ndarray] = []
    for values in sets.values():
        valid = (
            np.isfinite(values.broadband_psd)
            & (values.broadband_psd > 0)
            & (values.phase1_mask_fraction < PSD_MASK_OVERLAP_THRESHOLD)
        )
        pieces.append(values.broadband_psd[valid])
    pooled = np.concatenate(pieces) if pieces else np.array([], dtype=float)
    if pooled.size < 2:
        raise ValueError("At least two valid broadband windows are required")
    logged = np.log10(pooled)
    log_mean = float(np.mean(logged))
    log_sd = float(np.std(logged, ddof=1))
    threshold_log = log_mean + LOG3SD_MULTIPLIER * log_sd
    threshold_linear = float(10.0**threshold_log)
    counts: dict[int, dict[str, float | int]] = {}
    for set_number, values in sets.items():
        valid = (
            np.isfinite(values.broadband_psd)
            & (values.broadband_psd > 0)
            & (values.phase1_mask_fraction < PSD_MASK_OVERLAP_THRESHOLD)
        )
        mask = valid & (np.log10(np.where(valid, values.broadband_psd, 1.0)) > threshold_log)
        values.broadband_outlier_mask = mask
        count = int(mask.sum())
        denominator = int(valid.sum())
        counts[set_number] = {
            "valid_count": denominator,
            "excluded_count": count,
            "excluded_rate": count / denominator if denominator else math.nan,
        }
    return {
        "log_mean": log_mean,
        "log_sample_sd": log_sd,
        "threshold_log": threshold_log,
        "threshold_linear": threshold_linear,
        "counts": counts,
    }


def _load_source(path: Path, set_number: int) -> SetTFM:
    with h5py.File(path, "r") as handle:
        return calculate_set_tfm(
            handle["signal/data"][:, FOCUS_CHANNEL_INDEX],
            handle["time/relative_seconds"][:],
            handle["time/OriginalTimestamp"][:],
            handle["qc/ica_training_excluded_mask"][:],
            set_number,
        )


def _write_cache(
    path: Path,
    spec: ParticipantSpec,
    session_id: str,
    sets: dict[int, SetTFM],
    fingerprints: list[dict[str, Any]],
    config_hash: str,
    mask_info: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".h5", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with h5py.File(temporary, "w") as handle:
            product = normalize_product(spec.product)[0]
            condition = "Eye Drop" if session_id == spec.drops_session_id else "Control"
            handle.attrs.update(
                {
                    "participant_id": session_id,
                    "pair_id": spec.pair_id,
                    "condition": condition,
                    "product": product,
                    "channel": FOCUS_CHANNEL,
                    "sampling_frequency_hz": SFREQ,
                    "input_signal_unit": "V",
                    "psd_unit": "uV^2/Hz",
                    "frequency_min_hz": 1.0,
                    "frequency_max_hz": 30.0,
                    "configuration_hash": config_hash,
                    "input_fingerprints_json": json.dumps(fingerprints, ensure_ascii=False),
                    "script_version": SCRIPT_VERSION,
                    "created_at": datetime.now().astimezone().isoformat(),
                }
            )
            handle.create_dataset("frequencies_hz", data=FREQUENCIES_HZ)
            set_group = handle.create_group("sets")
            for set_number, values in sorted(sets.items()):
                group = set_group.create_group(f"Set{set_number}")
                for name, data in (
                    ("raw_psd", values.raw_psd),
                    ("relative_seconds_center", values.relative_seconds_center),
                    ("OriginalTimestamp_center", values.original_timestamp_center),
                    ("set_progress_pct", values.set_progress_pct),
                    ("global_progress_pct", values.global_progress_pct),
                    ("source_center_sample", values.source_center_sample),
                    ("phase1_mask_fraction", values.phase1_mask_fraction),
                    ("broadband_psd", values.broadband_psd),
                    ("broadband_outlier_mask", values.broadband_outlier_mask),
                ):
                    group.create_dataset(
                        name, data=data, compression="gzip", compression_opts=4, shuffle=True
                    )
            qc = handle.create_group("qc")
            qc.attrs.update(
                {
                    "log_mean": mask_info["log_mean"],
                    "log_sample_sd": mask_info["log_sample_sd"],
                    "threshold_log": mask_info["threshold_log"],
                    "threshold_linear": mask_info["threshold_linear"],
                }
            )
            availability = np.array([number in sets for number in range(1, N_SETS + 1)], dtype=bool)
            qc.create_dataset("source_set_availability", data=availability)
            valid_counts = np.zeros(N_SETS, dtype=np.int64)
            excluded_counts = np.zeros(N_SETS, dtype=np.int64)
            excluded_rates = np.full(N_SETS, np.nan)
            for number, counts in mask_info["counts"].items():
                valid_counts[number - 1] = counts["valid_count"]
                excluded_counts[number - 1] = counts["excluded_count"]
                excluded_rates[number - 1] = counts["excluded_rate"]
            qc.create_dataset("valid_count_by_set", data=valid_counts)
            qc.create_dataset("excluded_count_by_set", data=excluded_counts)
            qc.create_dataset("excluded_rate_by_set", data=excluded_rates)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_cache(path: Path, expected_hash: str | None = None) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        if expected_hash and str(handle.attrs.get("configuration_hash")) != expected_hash:
            raise ValueError(f"{path}: configuration/input hash mismatch")
        if str(handle.attrs.get("psd_unit")) != "uV^2/Hz":
            raise ValueError(f"{path}: PSD unit mismatch")
        if not np.array_equal(handle["frequencies_hz"][:], FREQUENCIES_HZ):
            raise ValueError(f"{path}: frequency bins mismatch")
        availability = handle["qc/source_set_availability"][:].astype(bool)
        for set_number in range(1, N_SETS + 1):
            key = f"sets/Set{set_number}"
            if availability[set_number - 1] != (key in handle):
                raise ValueError(f"{path}: Set availability mismatch")
            if key not in handle:
                continue
            group = handle[key]
            n_windows = group["raw_psd"].shape[0]
            if group["raw_psd"].shape != (n_windows, FREQUENCIES_HZ.size):
                raise ValueError(f"{path}: invalid raw PSD shape")
            if not np.isfinite(group["raw_psd"][:]).all() or np.any(group["raw_psd"][:] < 0):
                raise ValueError(f"{path}: invalid raw PSD values")
            for name in (
                "relative_seconds_center",
                "OriginalTimestamp_center",
                "set_progress_pct",
                "global_progress_pct",
                "source_center_sample",
                "phase1_mask_fraction",
                "broadband_psd",
                "broadband_outlier_mask",
            ):
                if group[name].shape != (n_windows,):
                    raise ValueError(f"{path}: invalid {key}/{name}")
            progress = group["set_progress_pct"][:]
            if not np.isclose(progress[0], 0.0) or not np.isclose(progress[-1], 100.0):
                raise ValueError(f"{path}: progress endpoints mismatch")
    return {"path": str(path), "ok": True}


def compute_session_cache(
    spec: ParticipantSpec,
    session_id: str,
    input_root: Path,
    cache_root: Path,
    force_recompute: bool,
) -> dict[str, Any]:
    sources = {
        number: input_path(input_root, session_id, number)
        for number in range(1, N_SETS + 1)
        if input_path(input_root, session_id, number).exists()
    }
    fingerprints = [
        validate_source(path, session_id, number) for number, path in sorted(sources.items())
    ]
    config_hash = configuration_hash(fingerprints)
    destination = cache_path(cache_root, spec, session_id)
    if destination.exists() and not force_recompute:
        validate_cache(destination, config_hash)
        return {"path": str(destination), "status": "reused", "hash": config_hash}
    sets = {number: _load_source(path, number) for number, path in sorted(sources.items())}
    mask_info = calculate_broadband_mask(sets)
    _write_cache(destination, spec, session_id, sets, fingerprints, config_hash, mask_info)
    validate_cache(destination, config_hash)
    return {"path": str(destination), "status": "computed", "hash": config_hash}


def load_session_cache(path: Path) -> SessionTFM:
    validate_cache(path)
    with h5py.File(path, "r") as handle:
        sets: dict[int, SetTFM] = {}
        for set_number in range(1, N_SETS + 1):
            key = f"sets/Set{set_number}"
            if key not in handle:
                continue
            group = handle[key]
            sets[set_number] = SetTFM(
                set_number=set_number,
                raw_psd=group["raw_psd"][:],
                relative_seconds_center=group["relative_seconds_center"][:],
                original_timestamp_center=group["OriginalTimestamp_center"][:],
                set_progress_pct=group["set_progress_pct"][:],
                global_progress_pct=group["global_progress_pct"][:],
                source_center_sample=group["source_center_sample"][:],
                phase1_mask_fraction=group["phase1_mask_fraction"][:],
                broadband_psd=group["broadband_psd"][:],
                broadband_outlier_mask=group["broadband_outlier_mask"][:].astype(bool),
            )
        qc = handle["qc"]
        return SessionTFM(
            session_id=str(handle.attrs["participant_id"]),
            condition=str(handle.attrs["condition"]),
            pair_id=str(handle.attrs["pair_id"]),
            product=str(handle.attrs["product"]),
            sets=sets,
            threshold_log=float(qc.attrs["threshold_log"]),
            threshold_linear=float(qc.attrs["threshold_linear"]),
            log_mean=float(qc.attrs["log_mean"]),
            log_sample_sd=float(qc.attrs["log_sample_sd"]),
        )


def masked_tfm(values: SetTFM) -> np.ndarray:
    output = values.raw_psd.astype(float).copy()
    invalid = (
        values.phase1_mask_fraction >= PSD_MASK_OVERLAP_THRESHOLD
    ) | values.broadband_outlier_mask
    output[invalid, :] = np.nan
    return output


def centered_nanmean_2d(values: np.ndarray, window_points: int) -> np.ndarray:
    frame = pd.DataFrame(np.asarray(values, dtype=float))
    return frame.rolling(window=window_points, center=True, min_periods=1).mean().to_numpy()


def interpolate_finite_runs(x: np.ndarray, y: np.ndarray, target: np.ndarray) -> np.ndarray:
    result = np.full(target.shape, np.nan, dtype=float)
    indices = np.flatnonzero(np.isfinite(x) & np.isfinite(y))
    if not indices.size:
        return result
    breaks = np.where(np.diff(indices) > 1)[0] + 1
    for run in np.split(indices, breaks):
        if run.size == 1:
            nearest = int(np.argmin(np.abs(target - x[run[0]])))
            if np.isclose(target[nearest], x[run[0]]):
                result[nearest] = y[run[0]]
            continue
        inside = (target >= x[run[0]]) & (target <= x[run[-1]])
        result[inside] = np.interp(target[inside], x[run], y[run])
    return result


def session_progress_tfm(session: SessionTFM, symmetric_missing: set[int]) -> np.ndarray:
    output = np.full(
        (N_SETS, GROUP_PROGRESS_POINTS_PER_SET, FREQUENCIES_HZ.size), np.nan, dtype=float
    )
    target = np.linspace(0.0, 100.0, GROUP_PROGRESS_POINTS_PER_SET, endpoint=False)
    for set_number, values in session.sets.items():
        if set_number in symmetric_missing:
            continue
        smoothed = centered_nanmean_2d(masked_tfm(values), SMOOTHING_SECONDS)
        for frequency_index in range(FREQUENCIES_HZ.size):
            output[set_number - 1, :, frequency_index] = interpolate_finite_runs(
                values.set_progress_pct, smoothed[:, frequency_index], target
            )
    return output


def load_pair(spec: ParticipantSpec, cache_root: Path) -> dict[str, Any]:
    first = load_session_cache(cache_path(cache_root, spec, spec.first_session_id))
    second = load_session_cache(cache_path(cache_root, spec, spec.second_session_id))
    by_id = {first.session_id: first, second.session_id: second}
    return {
        "spec": spec,
        "product": normalize_product(spec.product)[0],
        "eye_drop": by_id[spec.drops_session_id],
        "control": by_id[spec.control_session_id],
    }


def finite_statistics(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    valid = np.isfinite(values)
    count = valid.sum(axis=0)
    total = np.where(valid, values, 0.0).sum(axis=0)
    mean = np.divide(total, count, out=np.full(count.shape, np.nan), where=count > 0)
    return mean, count


def build_grand_average(items: list[dict[str, Any]], product: str) -> dict[str, np.ndarray]:
    eye_list: list[np.ndarray] = []
    control_list: list[np.ndarray] = []
    difference_list: list[np.ndarray] = []
    for item in items:
        if item["product"] != product:
            continue
        missing = set(range(1, N_SETS + 1)).difference(item["eye_drop"].sets)
        missing.update(set(range(1, N_SETS + 1)).difference(item["control"].sets))
        eye = session_progress_tfm(item["eye_drop"], missing)
        control = session_progress_tfm(item["control"], missing)
        eye_list.append(eye)
        control_list.append(control)
        difference_list.append(eye - control)
    if not eye_list:
        raise ValueError(f"No participant pairs for {product}")
    eye = np.stack(eye_list)
    control = np.stack(control_list)
    difference = np.stack(difference_list)
    eye_mean, eye_n = finite_statistics(eye)
    control_mean, control_n = finite_statistics(control)
    difference_mean, difference_n = finite_statistics(difference)
    return {
        "eye_mean": eye_mean,
        "eye_n": eye_n,
        "control_mean": control_mean,
        "control_n": control_n,
        "difference_mean": difference_mean,
        "difference_n": difference_n,
    }


def grand_average_table(product: str, values: dict[str, np.ndarray]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    within = np.linspace(0.0, 100.0, GROUP_PROGRESS_POINTS_PER_SET, endpoint=False)
    for set_index in range(N_SETS):
        for progress_index, set_progress in enumerate(within):
            for frequency_index, frequency in enumerate(FREQUENCIES_HZ):
                rows.append(
                    {
                        "Product": product,
                        "Set": set_index + 1,
                        "SetProgressPercent": set_progress,
                        "GlobalProgressPercent": set_index * 100.0 + set_progress,
                        "Frequency_Hz": frequency,
                        "EyeDrop_Mean_PSD_uV2_per_Hz": values["eye_mean"][
                            set_index, progress_index, frequency_index
                        ],
                        "EyeDrop_N": values["eye_n"][set_index, progress_index, frequency_index],
                        "Control_Mean_PSD_uV2_per_Hz": values["control_mean"][
                            set_index, progress_index, frequency_index
                        ],
                        "Control_N": values["control_n"][
                            set_index, progress_index, frequency_index
                        ],
                        "Difference_Mean_PSD_uV2_per_Hz": values["difference_mean"][
                            set_index, progress_index, frequency_index
                        ],
                        "Difference_N": values["difference_n"][
                            set_index, progress_index, frequency_index
                        ],
                    }
                )
    return pd.DataFrame(rows)


def plot_tfm(
    product: str,
    values: dict[str, np.ndarray],
    path: Path,
    absolute_limit: float,
    absolute_ticks: np.ndarray,
    difference_limit: float,
    difference_ticks: np.ndarray,
) -> None:
    _, product_label = normalize_product(product)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.8})
    figure, axes = plt.subplots(3, 1, figsize=(24, 18), sharex=True, sharey=True)
    panels = [
        ("eye_mean", f"Eye Drop ({product_label})", "viridis", 0.0, absolute_limit),
        ("control_mean", "Control", "viridis", 0.0, absolute_limit),
        ("difference_mean", "Eye Drop − Control", "RdBu_r", -difference_limit, difference_limit),
    ]
    extent = (0.0, 600.0, 0.5, 30.5)
    for panel_index, (key, title, cmap, vmin, vmax) in enumerate(panels):
        axis = axes[panel_index]
        image = axis.imshow(
            values[key].reshape(600, FREQUENCIES_HZ.size).T,
            origin="lower",
            aspect="auto",
            extent=extent,
            interpolation="nearest",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
        for boundary in range(100, 600, 100):
            axis.axvline(boundary, color="#BDBDBD", linestyle="--", linewidth=1.3)
        for set_number in range(1, N_SETS + 1):
            axis.text(
                (set_number - 0.5) * 100.0,
                0.97,
                f"Set {set_number}",
                transform=axis.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=20,
                color="white",
                fontweight="bold",
                bbox={"facecolor": "#303030", "edgecolor": "none", "alpha": 0.55, "pad": 2.5},
            )
        axis.set_title(title, fontsize=28, pad=12)
        axis.set_ylabel("Frequency (Hz)", fontsize=30, labelpad=16)
        axis.set_yticks([1, 5, 10, 15, 20, 25, 30])
        axis.tick_params(axis="both", labelsize=22, width=1.6, length=7)
        colorbar = figure.colorbar(image, ax=axis, fraction=0.022, pad=0.035, aspect=22)
        if panel_index < 2:
            colorbar.set_ticks(absolute_ticks)
            colorbar.set_label("PSD (µV²/Hz)", fontsize=26, rotation=270, labelpad=32)
        else:
            colorbar.set_ticks(difference_ticks)
            colorbar.set_label(DIFFERENCE_COLORBAR_LABEL, fontsize=26, rotation=270, labelpad=32)
        colorbar.ax.tick_params(labelsize=20, width=1.4, length=6)
    axes[-1].set_xlim(0.0, 600.0)
    axes[-1].set_xticks(np.arange(0.0, 601.0, 50.0))
    axes[-1].set_xlabel("Experimental Progress, %", fontsize=30, labelpad=18)
    figure.subplots_adjust(left=0.08, right=0.91, top=0.95, bottom=0.08, hspace=0.27)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(figure)


def output_directories(root: Path, product: str | None = None) -> dict[str, Path]:
    no1_add = root / "Phase4_脳波解析" / ANALYSIS_STEM
    result = {
        "root": no1_add,
        "tables": no1_add / "Sub" / "tables",
        "logs": no1_add / "Sub" / "logs",
    }
    if product:
        result["grand"] = no1_add / product / "GrandAverage"
    return result


def build_mask_diagnostics(items: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        for session in (item["eye_drop"], item["control"]):
            for set_number in range(1, N_SETS + 1):
                values = session.sets.get(set_number)
                if values is None:
                    rows.append(
                        {
                            "PairID": item["spec"].pair_id,
                            "SessionID": session.session_id,
                            "Condition": session.condition,
                            "Product": item["product"],
                            "Set": set_number,
                            "Available": False,
                        }
                    )
                    continue
                phase1_valid = values.phase1_mask_fraction < PSD_MASK_OVERLAP_THRESHOLD
                valid_count = int(phase1_valid.sum())
                excluded_count = int(values.broadband_outlier_mask.sum())
                rows.append(
                    {
                        "PairID": item["spec"].pair_id,
                        "SessionID": session.session_id,
                        "Condition": session.condition,
                        "Product": item["product"],
                        "Set": set_number,
                        "Available": True,
                        "Log10Mean": session.log_mean,
                        "Log10SampleSD": session.log_sample_sd,
                        "Log10UpperThreshold": session.threshold_log,
                        "LinearUpperThreshold_uV2_per_Hz": session.threshold_linear,
                        "Phase1ValidWindowCount": valid_count,
                        "BroadbandExcludedWindowCount": excluded_count,
                        "BroadbandExcludedRate": excluded_count / valid_count
                        if valid_count
                        else math.nan,
                    }
                )
    return pd.DataFrame(rows)


def write_group_outputs(items: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
    products = sorted({item["product"] for item in items})
    grand = {product: build_grand_average(items, product) for product in products}
    absolute_limit = ABSOLUTE_PSD_COLOR_LIMIT
    absolute_ticks = ABSOLUTE_PSD_COLOR_TICKS
    difference_limit = DIFFERENCE_COLOR_LIMIT
    difference_ticks = DIFFERENCE_COLOR_TICKS
    outputs: dict[str, Any] = {}
    for product in products:
        dirs = output_directories(output_root, product)
        for directory in dirs.values():
            directory.mkdir(parents=True, exist_ok=True)
        png = dirs["grand"] / f"{ANALYSIS_STEM}_GrandAverage_{product}.png"
        table = dirs["tables"] / f"{ANALYSIS_STEM}_GrandAverage_Values_{product}.csv"
        plot_tfm(
            product,
            grand[product],
            png,
            absolute_limit,
            absolute_ticks,
            difference_limit,
            difference_ticks,
        )
        grand_average_table(product, grand[product]).to_csv(table, index=False)
        outputs[product] = {"figure": str(png), "values": str(table)}
    scale_table = pd.DataFrame(
        [
            {
                "AbsolutePSD_Min": 0.0,
                "AbsolutePSD_Max": absolute_limit,
                "AbsolutePSD_Ticks": json.dumps(absolute_ticks.tolist()),
                "Difference_Min": -difference_limit,
                "Difference_Max": difference_limit,
                "Difference_Ticks": json.dumps(difference_ticks.tolist()),
            }
        ]
    )
    scale_path = output_directories(output_root)["tables"] / (
        f"{ANALYSIS_STEM}_ColorScale.csv"
    )
    scale_table.to_csv(scale_path, index=False)
    outputs["color_scale"] = str(scale_path)
    return outputs


def git_revision() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=Path(__file__).resolve().parents[2],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def write_log(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--participant", action="append", type=parse_participant, default=[])
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--input-root", type=Path, default=DEFAULT_INPUT_ROOT)
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--production-batch", action="store_true")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--compute-tfm", action="store_true")
    modes.add_argument("--group-outputs-only", action="store_true")
    modes.add_argument("--all", action="store_true")
    parser.add_argument("--force-recompute", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = list(args.participant)
    if args.manifest:
        specs.extend(load_manifest(args.manifest))
    if not specs:
        raise SystemExit("Provide --participant or --manifest")
    if args.force_recompute and not (args.compute_tfm or args.all):
        raise SystemExit("--force-recompute requires --compute-tfm or --all")
    validate_specs(specs, args.production_batch)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    preflight_result = preflight(specs, args.input_root)
    logging.info("Input preflight passed for %d participant pairs", len(specs))
    if args.preflight_only:
        return 0

    cache_records: list[dict[str, Any]] = []
    if args.compute_tfm or args.all:
        for spec in specs:
            for session_id in (spec.first_session_id, spec.second_session_id):
                record = compute_session_cache(
                    spec,
                    session_id,
                    args.input_root,
                    args.cache_root,
                    args.force_recompute,
                )
                cache_records.append({"pair_id": spec.pair_id, "session_id": session_id, **record})
                logging.info("TFM cache %s: ID%s", record["status"], session_id)
        if args.compute_tfm:
            summary = output_directories(args.output_root)["logs"] / (
                f"{ANALYSIS_STEM}_CacheSummary.json"
            )
            write_log(
                summary,
                {
                    "script_version": SCRIPT_VERSION,
                    "git_commit": git_revision(),
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "mode": "compute-tfm",
                    "configuration": analysis_configuration(),
                    "preflight": preflight_result,
                    "cache_records": cache_records,
                },
            )
            return 0

    items = [load_pair(spec, args.cache_root) for spec in specs]
    directories = output_directories(args.output_root)
    directories["tables"].mkdir(parents=True, exist_ok=True)
    diagnostics_path = directories["tables"] / (
        f"{ANALYSIS_STEM}_BroadbandMaskDiagnostics.csv"
    )
    build_mask_diagnostics(items).to_csv(diagnostics_path, index=False)
    outputs = write_group_outputs(items, args.output_root)
    summary = directories["logs"] / f"{ANALYSIS_STEM}_RunSummary.json"
    write_log(
        summary,
        {
            "script_version": SCRIPT_VERSION,
            "git_commit": git_revision(),
            "completed_at": datetime.now().astimezone().isoformat(),
            "mode": "all" if args.all else "group-outputs-only",
            "configuration": analysis_configuration(),
            "participants": [asdict(spec) | {"pair_id": spec.pair_id} for spec in specs],
            "preflight": preflight_result,
            "cache_records": cache_records,
            "mask_diagnostics": str(diagnostics_path),
            "outputs": outputs,
        },
    )
    logging.info("Phase 4 %s completed: %s", ANALYSIS_STEM, summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
