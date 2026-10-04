#!/usr/bin/env python3
"""Phase 4 No1: compute and analyse all-channel 4-7 Hz PSD time series."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import sys
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

COMMON_DIR = Path(__file__).resolve().parents[1]
if str(COMMON_DIR) not in sys.path:
    sys.path.insert(0, str(COMMON_DIR))

from paired_statistics import (  # noqa: E402
    add_significance_bracket,
    adjusted_p_values,
    paired_t_statistics,
    quantification_axis_layout,
    significance_label,
)

SCRIPT_VERSION = "phase4-no1-fmtheta-2026-10-04.3"
CACHE_CONFIGURATION_VERSION = "phase4-no1-fmtheta-2026-10-04.2"
N_SETS = 6
SFREQ = 256.0
WINDOW_SAMPLES = 256
STEP_SAMPLES = 256
PAD_SAMPLES = 128
FMIN_HZ = 4.0
FMAX_HZ = 7.0
INCLUDED_FREQUENCIES_HZ = np.array([4.0, 5.0, 6.0, 7.0])
GROUP_PROGRESS_POINTS_PER_SET = 100
PSD_WINDOW_BATCH_SIZE = 512
PSD_MASK_OVERLAP_THRESHOLD = 0.01
FIXED_INDIVIDUAL_Y_UPPER = 100.0
FIXED_INDIVIDUAL_Y_TICKS = np.arange(0.0, 101.0, 20.0)
SMOOTHING_COMPARISON_SECONDS = (15, 30, 60)
EXCLUDED_SESSION_IDS = {"130", "230"}
PRODUCTION_PARTICIPANT_COUNT = 40
PRODUCTION_PARTICIPANTS_PER_PRODUCT = 20
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

CONTROL_COLOR = "#402B5D"
CONTROL_QUANTIFICATION_COLOR = "#66547D"
PRODUCTS = {
    "ccube": ("CCube", "C Cube", "#A94F2D", "#C47A5B"),
    "c_cube": ("CCube", "C Cube", "#A94F2D", "#C47A5B"),
    "cキューブ": ("CCube", "C Cube", "#A94F2D", "#C47A5B"),
    "vrohtopremium": ("VRohtoPremium", "V Rohto Premium", "#D97852", "#E69A7D"),
    "v_rohto_premium": ("VRohtoPremium", "V Rohto Premium", "#D97852", "#E69A7D"),
    "vロート": ("VRohtoPremium", "V Rohto Premium", "#D97852", "#E69A7D"),
    "vロートプレミアム": ("VRohtoPremium", "V Rohto Premium", "#D97852", "#E69A7D"),
}

DEFAULT_INPUT_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/"
    "Phase1_脳波前処理/No2_AutomatedPreProcessing"
)
DEFAULT_CACHE_ROOT = Path(
    "/Users/aoiseki/Desktop/SandBox_ロート案件（データ）/解析に必要なデータたち/"
    "Phase4_脳波解析/No1_FmTheta/PSDTimeSeries"
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
class SetPSD:
    set_number: int
    psd_band_mean: np.ndarray
    relative_seconds_center: np.ndarray
    original_timestamp_center: np.ndarray
    set_progress_pct: np.ndarray
    global_progress_pct: np.ndarray
    source_center_sample: np.ndarray
    ica_training_mask_fraction: np.ndarray


@dataclass
class SessionPSD:
    session_id: str
    condition: str
    pair_id: str
    product: str
    channel_names: list[str]
    sets: dict[int, SetPSD]
    channel_excluded_mask: np.ndarray


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


def validate_participant_specs(
    specs: list[ParticipantSpec], *, production_batch: bool = False
) -> None:
    pair_ids = [spec.pair_id for spec in specs]
    session_ids = [sid for spec in specs for sid in (spec.first_session_id, spec.second_session_id)]
    if len(pair_ids) != len(set(pair_ids)):
        raise ValueError("Participant manifest contains a duplicated participant pair")
    if len(session_ids) != len(set(session_ids)):
        raise ValueError("Participant manifest reuses a session ID in multiple pairs")
    excluded = sorted(EXCLUDED_SESSION_IDS.intersection(session_ids))
    if excluded:
        raise ValueError(f"Excluded session IDs are present in the manifest: {excluded}")
    if not production_batch:
        return
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


def _decode_names(values: np.ndarray) -> list[str]:
    return [value.decode("utf-8") if isinstance(value, bytes) else str(value) for value in values]


def input_path(root: Path, session_id: str, set_number: int) -> Path:
    return (
        root
        / f"ID{session_id}"
        / f"Set{set_number}"
        / (f"ID{session_id}_Set{set_number}_brain_activity.h5")
    )


def session_file_prefix(spec: ParticipantSpec, session_id: str) -> str:
    if session_id == spec.first_session_id:
        order = 1
    elif session_id == spec.second_session_id:
        order = 2
    else:
        raise ValueError(f"ID{session_id} does not belong to pair {spec.pair_id}")
    return f"Pair{spec.pair_id}_{order:02d}_ID{session_id}"


def cache_path(root: Path, spec: ParticipantSpec, session_id: str) -> Path:
    return root / f"{session_file_prefix(spec, session_id)}_FmTheta_AllChannelsPSD.h5"


def _read_text_dataset(dataset: h5py.Dataset) -> str:
    value = dataset[()]
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _validate_source_file(path: Path, session_id: str, set_number: int) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        required_paths = [
            "signal/data",
            "signal/channel_names",
            "time/relative_seconds",
            "time/OriginalTimestamp",
            "qc/ica_training_excluded_mask",
            "qc/ica_channel_excluded_mask",
            "qc/ica_excluded_channel_records_json",
            "qc/ica_training_exclusions_json",
        ]
        missing = [name for name in required_paths if name not in handle]
        if missing:
            raise ValueError(f"{path}: missing HDF5 objects {missing}")
        if str(handle.attrs.get("participant_id")) != session_id:
            raise ValueError(f"{path}: participant_id mismatch")
        if int(handle.attrs.get("set_number", -1)) != set_number:
            raise ValueError(f"{path}: set_number mismatch")
        if str(handle.attrs.get("data_kind")) != "brain_activity_eeg":
            raise ValueError(f"{path}: data_kind must be brain_activity_eeg")
        if not np.isclose(float(handle.attrs.get("sampling_frequency_hz", np.nan)), SFREQ):
            raise ValueError(f"{path}: sampling rate must be {SFREQ:g} Hz")
        if str(handle.attrs.get("signal_unit")) != "V":
            raise ValueError(f"{path}: signal unit must be V")
        names = _decode_names(handle["signal/channel_names"][:])
        if names != EXPECTED_CHANNEL_NAMES:
            raise ValueError(f"{path}: channel order differs from the fixed Phase 1 order")
        shape = handle["signal/data"].shape
        if len(shape) != 2 or shape[1] != len(EXPECTED_CHANNEL_NAMES) or shape[0] < 2:
            raise ValueError(f"{path}: unexpected signal shape {shape}")
        n_samples = shape[0]
        for name in (
            "time/relative_seconds",
            "time/OriginalTimestamp",
            "qc/ica_training_excluded_mask",
        ):
            if handle[name].shape != (n_samples,):
                raise ValueError(f"{path}: {name} length does not match signal")
        if handle["qc/ica_channel_excluded_mask"].shape != (len(EXPECTED_CHANNEL_NAMES),):
            raise ValueError(f"{path}: ICA channel mask must contain 32 values")
        signal = handle["signal/data"][:]
        relative = handle["time/relative_seconds"][:]
        original = handle["time/OriginalTimestamp"][:]
        if not np.isfinite(signal).all():
            raise ValueError(f"{path}: EEG contains non-finite values")
        if not np.isfinite(relative).all() or not np.isfinite(original).all():
            raise ValueError(f"{path}: time arrays contain non-finite values")
        if np.any(np.diff(relative) <= 0) or np.any(np.diff(original) <= 0):
            raise ValueError(f"{path}: time arrays must be strictly increasing")
        if not np.allclose(np.diff(relative), 1.0 / SFREQ, rtol=0.0, atol=1e-8):
            raise ValueError(f"{path}: relative_seconds does not match 256 Hz sampling")
        json.loads(_read_text_dataset(handle["qc/ica_excluded_channel_records_json"]))
        json.loads(_read_text_dataset(handle["qc/ica_training_exclusions_json"]))
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def preflight_inputs(specs: list[ParticipantSpec], root: Path) -> dict[str, Any]:
    checked: list[dict[str, Any]] = []
    missing_by_session: dict[str, list[int]] = {}
    for spec in specs:
        for session_id in (spec.first_session_id, spec.second_session_id):
            observed_missing: set[int] = set()
            for set_number in range(1, N_SETS + 1):
                path = input_path(root, session_id, set_number)
                if not path.exists():
                    observed_missing.add(set_number)
                    continue
                checked.append(_validate_source_file(path, session_id, set_number))
            expected_missing = EXPECTED_MISSING_SETS.get(session_id, set())
            if observed_missing != expected_missing:
                raise ValueError(
                    f"ID{session_id}: missing sets {sorted(observed_missing)}, "
                    f"expected {sorted(expected_missing)}"
                )
            if observed_missing:
                missing_by_session[session_id] = sorted(observed_missing)
    _topomap_info()
    return {
        "participant_pairs": len(specs),
        "session_ids": len(specs) * 2,
        "checked_files": len(checked),
        "missing_by_session": missing_by_session,
        "inputs": checked,
    }


def analysis_configuration() -> dict[str, Any]:
    return {
        "script_version": CACHE_CONFIGURATION_VERSION,
        "sfreq": SFREQ,
        "window_samples": WINDOW_SAMPLES,
        "step_samples": STEP_SAMPLES,
        "pad_samples": PAD_SAMPLES,
        "n_fft": WINDOW_SAMPLES,
        "n_per_seg": WINDOW_SAMPLES,
        "n_overlap": 0,
        "window_function": "hann",
        "remove_dc": True,
        "frequencies_hz": INCLUDED_FREQUENCIES_HZ.tolist(),
        "psd_window_batch_size": PSD_WINDOW_BATCH_SIZE,
        "time_smoothing": "none",
        "interval_mask_policy": "retain_all_samples_store_window_overlap_fraction",
        "channel_mask_policy": "retain_all_32_channels_store_phase1_ica_mask",
        "channel_names": EXPECTED_CHANNEL_NAMES,
    }


def downstream_configuration() -> dict[str, Any]:
    return {
        "interval_mask_policy": "set_psd_nan_when_phase1_mask_overlap_fraction_gte_0.01",
        "interval_mask_overlap_threshold": PSD_MASK_OVERLAP_THRESHOLD,
        "channel_mask_policy": "do_not_apply_phase1_ica_channel_mask_to_psd",
        "time_smoothing": "none",
    }


def configuration_hash(input_fingerprints: list[dict[str, Any]]) -> str:
    payload = {"configuration": analysis_configuration(), "inputs": input_fingerprints}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def window_centers(n_samples: int) -> np.ndarray:
    if n_samples < 2:
        raise ValueError("A set must contain at least two samples")
    centers = np.arange(0, n_samples, STEP_SAMPLES, dtype=np.int64)
    if centers[-1] != n_samples - 1:
        centers = np.append(centers, n_samples - 1)
    return centers


def _windowed_mask_fraction(mask: np.ndarray, centers: np.ndarray) -> np.ndarray:
    padded = np.pad(np.asarray(mask, dtype=float), (PAD_SAMPLES, PAD_SAMPLES), mode="reflect")
    return np.asarray(
        [padded[center : center + WINDOW_SAMPLES].mean() for center in centers],
        dtype=np.float32,
    )


def calculate_set_psd(
    data_v: np.ndarray,
    relative_seconds: np.ndarray,
    original_timestamp: np.ndarray,
    training_excluded_mask: np.ndarray,
    set_number: int,
) -> SetPSD:
    data_v = np.asarray(data_v, dtype=np.float64)
    n_samples = data_v.shape[0]
    if data_v.shape != (n_samples, len(EXPECTED_CHANNEL_NAMES)):
        raise ValueError(f"Unexpected EEG shape: {data_v.shape}")
    centers = window_centers(n_samples)
    data_uv = data_v * 1e6
    padded = np.pad(data_uv, ((PAD_SAMPLES, PAD_SAMPLES), (0, 0)), mode="reflect")
    output = np.empty((centers.size, data_uv.shape[1]), dtype=np.float32)
    for start in range(0, centers.size, PSD_WINDOW_BATCH_SIZE):
        stop = min(start + PSD_WINDOW_BATCH_SIZE, centers.size)
        batch_centers = centers[start:stop]
        windows_uv = np.stack(
            [padded[center : center + WINDOW_SAMPLES].T for center in batch_centers], axis=0
        )
        psd, frequencies = mne.time_frequency.psd_array_welch(
            windows_uv,
            sfreq=SFREQ,
            fmin=FMIN_HZ,
            fmax=FMAX_HZ,
            n_fft=WINDOW_SAMPLES,
            n_per_seg=WINDOW_SAMPLES,
            n_overlap=0,
            window="hann",
            average="mean",
            output="power",
            remove_dc=True,
            verbose=False,
        )
        if not np.array_equal(frequencies, INCLUDED_FREQUENCIES_HZ):
            raise ValueError(f"Unexpected Welch frequency bins: {frequencies.tolist()}")
        output[start:stop] = np.mean(psd, axis=-1).astype(np.float32)
    progress = centers.astype(np.float64) / float(n_samples - 1) * 100.0
    return SetPSD(
        set_number=set_number,
        psd_band_mean=output,
        relative_seconds_center=np.asarray(relative_seconds, dtype=float)[centers],
        original_timestamp_center=np.asarray(original_timestamp, dtype=float)[centers],
        set_progress_pct=progress,
        global_progress_pct=(set_number - 1) * 100.0 + progress,
        source_center_sample=centers,
        ica_training_mask_fraction=_windowed_mask_fraction(training_excluded_mask, centers),
    )


def _load_and_calculate_source(path: Path, set_number: int) -> tuple[SetPSD, np.ndarray, str]:
    with h5py.File(path, "r") as handle:
        result = calculate_set_psd(
            handle["signal/data"][:],
            handle["time/relative_seconds"][:],
            handle["time/OriginalTimestamp"][:],
            handle["qc/ica_training_excluded_mask"][:],
            set_number,
        )
        channel_mask = handle["qc/ica_channel_excluded_mask"][:].astype(bool)
        records = _read_text_dataset(handle["qc/ica_excluded_channel_records_json"])
    return result, channel_mask, records


def _write_cache(
    path: Path,
    spec: ParticipantSpec,
    session_id: str,
    sets: dict[int, SetPSD],
    source_paths: dict[int, Path],
    channel_mask: np.ndarray,
    exclusion_records_json: str,
    config_hash: str,
    fingerprints: list[dict[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    utf8 = h5py.string_dtype("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".h5", delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        with h5py.File(temporary_path, "w") as handle:
            product_dir = normalize_product(spec.product)[0]
            condition = "Eye Drop" if session_id == spec.drops_session_id else "Control"
            session_order = 1 if session_id == spec.first_session_id else 2
            handle.attrs.update(
                {
                    "participant_id": session_id,
                    "pair_id": spec.pair_id,
                    "session_order": session_order,
                    "condition": condition,
                    "product": product_dir,
                    "source_pipeline": "Phase1_No2_AutomatedPreProcessing",
                    "sampling_frequency_hz": SFREQ,
                    "input_signal_unit": "V",
                    "psd_unit": "uV^2/Hz",
                    "psd_method": "mne.time_frequency.psd_array_welch",
                    "window_samples": WINDOW_SAMPLES,
                    "step_samples": STEP_SAMPLES,
                    "n_fft": WINDOW_SAMPLES,
                    "n_per_seg": WINDOW_SAMPLES,
                    "n_overlap": 0,
                    "window_function": "hann",
                    "fmin_hz": FMIN_HZ,
                    "fmax_hz": FMAX_HZ,
                    "included_frequencies_hz": json.dumps(INCLUDED_FREQUENCIES_HZ.tolist()),
                    "time_smoothing": "none",
                    "interval_mask_policy": ("retain_all_samples_store_window_overlap_fraction"),
                    "channel_mask_policy": "retain_all_32_channels_store_phase1_ica_mask",
                    "configuration_hash": config_hash,
                    "input_fingerprints_json": json.dumps(fingerprints, ensure_ascii=False),
                    "script_version": SCRIPT_VERSION,
                    "created_at": datetime.now().astimezone().isoformat(),
                }
            )
            signal = handle.create_group("signal")
            signal.create_dataset(
                "channel_names", data=np.asarray(EXPECTED_CHANNEL_NAMES, dtype=utf8)
            )
            sets_group = handle.create_group("sets")
            for set_number, result in sorted(sets.items()):
                group = sets_group.create_group(f"Set{set_number}")
                group.attrs.update(
                    {
                        "source_file": str(source_paths[set_number].resolve()),
                        "source_n_samples": int(round(result.relative_seconds_center[-1] * SFREQ))
                        + 1,
                        "available": True,
                    }
                )
                for name, values in (
                    ("psd_band_mean", result.psd_band_mean),
                    ("relative_seconds_center", result.relative_seconds_center),
                    ("OriginalTimestamp_center", result.original_timestamp_center),
                    ("set_progress_pct", result.set_progress_pct),
                    ("global_progress_pct", result.global_progress_pct),
                    ("source_center_sample", result.source_center_sample),
                    ("ica_training_mask_fraction", result.ica_training_mask_fraction),
                ):
                    group.create_dataset(
                        name,
                        data=values,
                        compression="gzip",
                        compression_opts=4,
                        shuffle=True,
                    )
            qc = handle.create_group("qc")
            qc.create_dataset("ica_channel_excluded_mask", data=channel_mask.astype(bool))
            qc.create_dataset(
                "ica_excluded_channel_records_json", data=exclusion_records_json, dtype=utf8
            )
            availability = np.array(
                [set_number in sets for set_number in range(1, N_SETS + 1)], dtype=bool
            )
            qc.create_dataset("source_set_availability", data=availability)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def validate_cache(path: Path, expected_hash: str | None = None) -> dict[str, Any]:
    with h5py.File(path, "r") as handle:
        if expected_hash is not None and handle.attrs.get("configuration_hash") != expected_hash:
            raise ValueError(f"{path}: configuration/input hash mismatch")
        if str(handle.attrs.get("psd_unit")) != "uV^2/Hz":
            raise ValueError(f"{path}: unexpected PSD unit")
        names = _decode_names(handle["signal/channel_names"][:])
        if names != EXPECTED_CHANNEL_NAMES:
            raise ValueError(f"{path}: cached channel order mismatch")
        availability = handle["qc/source_set_availability"][:].astype(bool)
        if availability.shape != (N_SETS,):
            raise ValueError(f"{path}: invalid source_set_availability")
        for set_number in range(1, N_SETS + 1):
            key = f"sets/Set{set_number}"
            if availability[set_number - 1] != (key in handle):
                raise ValueError(f"{path}: Set{set_number} availability mismatch")
            if key not in handle:
                continue
            group = handle[key]
            required = [
                "psd_band_mean",
                "relative_seconds_center",
                "OriginalTimestamp_center",
                "set_progress_pct",
                "global_progress_pct",
                "source_center_sample",
                "ica_training_mask_fraction",
            ]
            missing = [name for name in required if name not in group]
            if missing:
                raise ValueError(f"{path}: Set{set_number} missing {missing}")
            values = group["psd_band_mean"][:]
            n_windows = values.shape[0]
            if values.shape != (n_windows, len(EXPECTED_CHANNEL_NAMES)) or n_windows < 2:
                raise ValueError(f"{path}: invalid Set{set_number} PSD shape")
            if not np.isfinite(values).all() or np.any(values < 0):
                raise ValueError(f"{path}: invalid Set{set_number} PSD values")
            for name in required[1:]:
                array = group[name][:]
                if array.shape != (n_windows,) or not np.isfinite(array).all():
                    raise ValueError(f"{path}: invalid Set{set_number}/{name}")
            if np.any(np.diff(group["relative_seconds_center"][:]) <= 0):
                raise ValueError(f"{path}: non-monotonic relative center time")
            if np.any(np.diff(group["OriginalTimestamp_center"][:]) <= 0):
                raise ValueError(f"{path}: non-monotonic OriginalTimestamp")
            progress = group["set_progress_pct"][:]
            if not np.isclose(progress[0], 0.0) or not np.isclose(progress[-1], 100.0):
                raise ValueError(f"{path}: progress endpoints are not 0 and 100")
    return {"path": str(path), "ok": True, "configuration_hash": expected_hash}


def compute_session_cache(
    spec: ParticipantSpec,
    session_id: str,
    input_root: Path,
    cache_root: Path,
    *,
    force_recompute: bool = False,
) -> dict[str, Any]:
    source_paths = {
        set_number: input_path(input_root, session_id, set_number)
        for set_number in range(1, N_SETS + 1)
        if input_path(input_root, session_id, set_number).exists()
    }
    fingerprints = [
        _validate_source_file(path, session_id, set_number)
        for set_number, path in source_paths.items()
    ]
    config_hash = configuration_hash(fingerprints)
    destination = cache_path(cache_root, spec, session_id)
    if destination.exists() and not force_recompute:
        validate_cache(destination, config_hash)
        return {"path": str(destination), "status": "reused", "hash": config_hash}
    sets: dict[int, SetPSD] = {}
    masks: list[np.ndarray] = []
    records: list[str] = []
    for set_number, path in sorted(source_paths.items()):
        result, mask, record = _load_and_calculate_source(path, set_number)
        sets[set_number] = result
        masks.append(mask)
        records.append(record)
    if masks and any(not np.array_equal(masks[0], item) for item in masks[1:]):
        raise ValueError(f"ID{session_id}: ICA channel mask differs across sets")
    if records and any(records[0] != item for item in records[1:]):
        raise ValueError(f"ID{session_id}: ICA channel exclusion records differ across sets")
    _write_cache(
        destination,
        spec,
        session_id,
        sets,
        source_paths,
        masks[0],
        records[0],
        config_hash,
        fingerprints,
    )
    validate_cache(destination, config_hash)
    return {"path": str(destination), "status": "computed", "hash": config_hash}


def load_session_cache(path: Path) -> SessionPSD:
    validate_cache(path)
    with h5py.File(path, "r") as handle:
        sets: dict[int, SetPSD] = {}
        for set_number in range(1, N_SETS + 1):
            key = f"sets/Set{set_number}"
            if key not in handle:
                continue
            group = handle[key]
            psd_band_mean = group["psd_band_mean"][:]
            mask_fraction = group["ica_training_mask_fraction"][:]
            psd_band_mean[mask_fraction >= PSD_MASK_OVERLAP_THRESHOLD] = np.nan
            sets[set_number] = SetPSD(
                set_number,
                psd_band_mean,
                group["relative_seconds_center"][:],
                group["OriginalTimestamp_center"][:],
                group["set_progress_pct"][:],
                group["global_progress_pct"][:],
                group["source_center_sample"][:],
                mask_fraction,
            )
        return SessionPSD(
            session_id=str(handle.attrs["participant_id"]),
            condition=str(handle.attrs["condition"]),
            pair_id=str(handle.attrs["pair_id"]),
            product=str(handle.attrs["product"]),
            channel_names=_decode_names(handle["signal/channel_names"][:]),
            sets=sets,
            channel_excluded_mask=handle["qc/ica_channel_excluded_mask"][:].astype(bool),
        )


def _nice_upper(values: np.ndarray, target_fraction: float) -> tuple[float, np.ndarray]:
    finite = np.asarray(values, dtype=float)
    finite = finite[np.isfinite(finite)]
    maximum = float(np.max(finite)) if finite.size else 1.0
    raw_upper = max(maximum / target_fraction, np.finfo(float).eps)
    exponent = int(math.floor(math.log10(raw_upper)))
    candidates: list[tuple[float, float, np.ndarray]] = []
    for power in range(exponent - 2, exponent + 2):
        scale = 10.0**power
        for multiplier in (1.0, 2.0, 2.5, 5.0):
            step = multiplier * scale
            upper = math.ceil(raw_upper / step) * step
            ticks = np.arange(0.0, upper + step * 0.01, step)
            if 3 <= ticks.size <= 6:
                candidates.append((abs(ticks.size - 5), upper, ticks))
    if not candidates:
        upper = raw_upper
        return upper, np.linspace(0.0, upper, 5)
    _, upper, ticks = min(candidates, key=lambda item: (item[0], item[1]))
    return float(upper), ticks


def _configure_time_axis(axis: plt.Axes, upper: float, ticks: np.ndarray) -> None:
    for boundary in range(100, 600, 100):
        axis.axvline(boundary, color="#9E9E9E", linestyle="--", linewidth=1.5, zorder=0)
    for set_number in range(1, N_SETS + 1):
        axis.text(
            (set_number - 0.5) * 100.0,
            0.96,
            f"Set {set_number}",
            transform=axis.get_xaxis_transform(),
            ha="center",
            va="top",
            fontsize=22,
            fontfamily="Arial",
            color="#333333",
        )
    axis.set_xlim(0.0, 600.0)
    axis.set_ylim(0.0, upper)
    axis.set_xticks(np.arange(0.0, 601.0, 50.0))
    axis.set_yticks(ticks)
    axis.set_xlabel("Experimental Progress, %", fontsize=28, labelpad=18)
    axis.set_ylabel("PSD (µV²/Hz)", fontsize=28)
    axis.tick_params(axis="both", labelsize=20, width=1.5, length=6)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def _channel_index(session: SessionPSD, channel: str = "Fz") -> int:
    try:
        return session.channel_names.index(channel)
    except ValueError as error:
        raise ValueError(f"ID{session.session_id}: {channel} is absent") from error


def centered_nanmean(values: np.ndarray, window_points: int) -> np.ndarray:
    """Centered rolling mean that ignores NaN and returns NaN for all-NaN windows."""
    if window_points < 1:
        raise ValueError("window_points must be positive")
    array = np.asarray(values, dtype=float)
    if array.ndim != 1:
        raise ValueError("values must be one-dimensional")
    return (
        pd.Series(array)
        .rolling(window=int(window_points), center=True, min_periods=1)
        .mean()
        .to_numpy(dtype=float)
    )


def _set_channel_values(
    values: SetPSD,
    channel_index: int,
    *,
    smoothing_seconds: int | None = None,
) -> np.ndarray:
    raw = values.psd_band_mean[:, channel_index]
    if smoothing_seconds is None:
        return np.asarray(raw, dtype=float)
    points = int(round(float(smoothing_seconds) * SFREQ / STEP_SAMPLES))
    return centered_nanmean(raw, points)


def _time_series_values(
    session: SessionPSD,
    channel: str = "Fz",
    *,
    smoothing_seconds: int | None = None,
) -> np.ndarray:
    index = _channel_index(session, channel)
    return np.concatenate(
        [
            _set_channel_values(item, index, smoothing_seconds=smoothing_seconds)
            for _, item in sorted(session.sets.items())
        ]
    )


def plot_individual_timecourse(
    spec: ParticipantSpec,
    eye_drop: SessionPSD,
    control: SessionPSD,
    path: Path,
    *,
    fixed_y_upper: float | None = None,
    smoothing_seconds: int | None = None,
    common_y_axis: tuple[float, np.ndarray] | None = None,
) -> None:
    product_dir, product_label, product_color, _ = normalize_product(spec.product)
    if {eye_drop.product, control.product} != {product_dir}:
        raise ValueError(f"Pair {spec.pair_id}: cached product mismatch")
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    for session, color, label in (
        (control, CONTROL_COLOR, "Control"),
        (eye_drop, product_color, f"Eye Drop ({product_label})"),
    ):
        fz_index = _channel_index(session)
        first = True
        for _, values in sorted(session.sets.items()):
            plotted = _set_channel_values(
                values,
                fz_index,
                smoothing_seconds=smoothing_seconds,
            )
            axis.plot(
                values.global_progress_pct,
                plotted,
                color=color,
                linewidth=3.0,
                label=label if first else None,
            )
            first = False
    displayed = np.concatenate(
        [
            _time_series_values(eye_drop, smoothing_seconds=smoothing_seconds),
            _time_series_values(control, smoothing_seconds=smoothing_seconds),
        ]
    )
    if common_y_axis is not None:
        upper, ticks = common_y_axis
    elif fixed_y_upper is None:
        upper, ticks = _nice_upper(displayed, 0.70)
    else:
        upper = float(fixed_y_upper)
        ticks = FIXED_INDIVIDUAL_Y_TICKS
    _configure_time_axis(axis, upper, ticks)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False, fontsize=20)
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def interpolate_session_progress(
    session: SessionPSD,
    channel: str = "Fz",
    *,
    symmetrically_missing_sets: set[int] | None = None,
) -> np.ndarray:
    output = np.full((N_SETS, GROUP_PROGRESS_POINTS_PER_SET), np.nan, dtype=float)
    index = _channel_index(session, channel)
    target = np.linspace(0.0, 100.0, GROUP_PROGRESS_POINTS_PER_SET, endpoint=False)
    symmetric = symmetrically_missing_sets or set()
    for set_number, values in session.sets.items():
        if set_number in symmetric:
            continue
        output[set_number - 1] = np.interp(
            target, values.set_progress_pct, values.psd_band_mean[:, index]
        )
    return output


def _columnwise_statistics(values: np.ndarray) -> dict[str, np.ndarray]:
    valid = np.isfinite(values)
    count = valid.sum(axis=0)
    total = np.where(valid, values, 0.0).sum(axis=0)
    mean = np.divide(total, count, out=np.full(count.shape, np.nan), where=count > 0)
    squared = np.where(valid, (values - mean) ** 2, 0.0).sum(axis=0)
    variance = np.divide(
        squared, count - 1, out=np.full(count.shape, np.nan, dtype=float), where=count > 1
    )
    sample_sd = np.sqrt(variance)
    sem = np.divide(
        sample_sd,
        np.sqrt(count),
        out=np.full(count.shape, np.nan, dtype=float),
        where=count > 1,
    )
    return {"mean": mean, "sample_sd": sample_sd, "sem": sem, "valid_n": count}


def build_grand_average(
    items: list[dict[str, Any]], product_dir: str
) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    selected = [item for item in items if item["product_dir"] == product_dir]
    if not selected:
        raise ValueError(f"Grand-average for {product_dir} requires at least one pair")
    eye_values: list[np.ndarray] = []
    control_values: list[np.ndarray] = []
    for item in selected:
        missing = set(range(1, N_SETS + 1)).difference(item["eye_drop"].sets)
        missing.update(set(range(1, N_SETS + 1)).difference(item["control"].sets))
        eye_values.append(
            interpolate_session_progress(item["eye_drop"], symmetrically_missing_sets=missing)
        )
        control_values.append(
            interpolate_session_progress(item["control"], symmetrically_missing_sets=missing)
        )
    eye = np.vstack([value.reshape(-1) for value in eye_values])
    control = np.vstack([value.reshape(-1) for value in control_values])
    eye_stats = _columnwise_statistics(eye)
    control_stats = _columnwise_statistics(control)
    within = np.tile(np.linspace(0.0, 100.0, GROUP_PROGRESS_POINTS_PER_SET, endpoint=False), N_SETS)
    sets = np.repeat(np.arange(1, N_SETS + 1), GROUP_PROGRESS_POINTS_PER_SET)
    global_progress = (sets - 1) * 100.0 + within
    frame = pd.DataFrame(
        {"Set": sets, "SetProgressPercent": within, "GlobalProgressPercent": global_progress}
    )
    for prefix, statistics in (("EyeDrop", eye_stats), ("Control", control_stats)):
        frame[f"{prefix}_Mean_PSD_uV2_per_Hz"] = statistics["mean"]
        frame[f"{prefix}_SD_PSD_uV2_per_Hz"] = statistics["sample_sd"]
        frame[f"{prefix}_SEM_PSD_uV2_per_Hz"] = statistics["sem"]
        frame[f"{prefix}_N"] = statistics["valid_n"]
    return frame, {"eye_drop": eye, "control": control}


def plot_grand_average(
    frame: pd.DataFrame,
    product_dir: str,
    path: Path,
    *,
    common_upper: float,
    common_ticks: np.ndarray,
) -> None:
    _, product_label, product_color, _ = normalize_product(product_dir)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(24, 8))
    x = frame["GlobalProgressPercent"].to_numpy(dtype=float)
    for prefix, color, label in (
        ("Control", CONTROL_COLOR, "Control"),
        ("EyeDrop", product_color, f"Eye Drop ({product_label})"),
    ):
        mean = frame[f"{prefix}_Mean_PSD_uV2_per_Hz"].to_numpy(dtype=float)
        sem = frame[f"{prefix}_SEM_PSD_uV2_per_Hz"].to_numpy(dtype=float)
        for set_number in range(1, N_SETS + 1):
            mask = frame["Set"].to_numpy(dtype=int) == set_number
            axis.fill_between(
                x[mask],
                mean[mask] - sem[mask],
                mean[mask] + sem[mask],
                color=color,
                alpha=0.18,
                linewidth=0,
            )
            axis.plot(
                x[mask],
                mean[mask],
                color=color,
                linewidth=3.0,
                label=label if set_number == 1 else None,
            )
    _configure_time_axis(axis, common_upper, common_ticks)
    axis.legend(loc="upper center", bbox_to_anchor=(0.5, 1.18), ncol=2, frameon=False, fontsize=20)
    figure.subplots_adjust(left=0.08, right=0.99, top=0.78, bottom=0.20)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def session_set_channel_means(session: SessionPSD) -> dict[int, np.ndarray]:
    return {
        set_number: np.nanmean(values.psd_band_mean, axis=0)
        for set_number, values in session.sets.items()
    }


def build_quantification(items: list[dict[str, Any]], product_dir: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        if item["product_dir"] != product_dir:
            continue
        eye_means = session_set_channel_means(item["eye_drop"])
        control_means = session_set_channel_means(item["control"])
        common_sets = set(eye_means).intersection(control_means)
        fz = _channel_index(item["eye_drop"])
        for set_number in range(1, N_SETS + 1):
            rows.append(
                {
                    "PairID": item["spec"].pair_id,
                    "Set": set_number,
                    "EyeDrop_PSD_uV2_per_Hz": (
                        float(eye_means[set_number][fz]) if set_number in common_sets else np.nan
                    ),
                    "Control_PSD_uV2_per_Hz": (
                        float(control_means[set_number][fz])
                        if set_number in common_sets
                        else np.nan
                    ),
                }
            )
        eye_windows = np.concatenate(
            [item["eye_drop"].sets[number].psd_band_mean[:, fz] for number in sorted(common_sets)]
        )
        control_windows = np.concatenate(
            [item["control"].sets[number].psd_band_mean[:, fz] for number in sorted(common_sets)]
        )
        rows.append(
            {
                "PairID": item["spec"].pair_id,
                "Set": "All Sets",
                "EyeDrop_PSD_uV2_per_Hz": float(np.nanmean(eye_windows)),
                "Control_PSD_uV2_per_Hz": float(np.nanmean(control_windows)),
            }
        )
    return pd.DataFrame(rows)


def quantification_statistics(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    set_rows: list[dict[str, Any]] = []
    for set_number in range(1, N_SETS + 1):
        selected = frame.loc[frame["Set"] == set_number]
        result = paired_t_statistics(
            selected["EyeDrop_PSD_uV2_per_Hz"].to_numpy(dtype=float),
            selected["Control_PSD_uV2_per_Hz"].to_numpy(dtype=float),
        )
        set_rows.append({"Set": set_number, **result})
    statistics = pd.DataFrame(set_rows)
    raw = statistics["P_value_raw"].to_numpy(dtype=float)
    statistics["P_value_Bonferroni"] = adjusted_p_values(raw, "bonferroni")
    statistics["P_value_Holm"] = adjusted_p_values(raw, "holm")
    statistics["P_value_FDR_BH"] = adjusted_p_values(raw, "fdr_bh")
    all_sets = frame.loc[frame["Set"] == "All Sets"]
    overall = pd.DataFrame(
        [
            {
                "Set": "All Sets",
                **paired_t_statistics(
                    all_sets["EyeDrop_PSD_uV2_per_Hz"].to_numpy(dtype=float),
                    all_sets["Control_PSD_uV2_per_Hz"].to_numpy(dtype=float),
                ),
            }
        ]
    )
    return statistics, overall


def _draw_quantification_panel(
    axis: plt.Axes,
    eye: np.ndarray,
    control: np.ndarray,
    eye_color: str,
    product_label: str,
    label: str,
    seed: int,
    layout: tuple[float, np.ndarray, float, float, float, float],
    p_value: float,
    *,
    show_ylabel: bool,
) -> None:
    upper, ticks, line_y, text_y, ns_y, set_y = layout
    paired = np.isfinite(eye) & np.isfinite(control)
    eye, control = eye[paired], control[paired]
    means = [float(np.mean(eye)), float(np.mean(control))]
    axis.bar(
        [-0.32, 0.32],
        means,
        width=0.42,
        color=[eye_color, CONTROL_QUANTIFICATION_COLOR],
        alpha=0.82,
        edgecolor="#222222",
        linewidth=1.0,
        zorder=1,
    )
    rng = np.random.default_rng(seed)
    jitter = rng.uniform(-0.055, 0.055, size=eye.size)
    for offset, eye_value, control_value in zip(jitter, eye, control, strict=True):
        axis.plot(
            [-0.32 + offset, 0.32 + offset],
            [eye_value, control_value],
            color="#777777",
            linewidth=1.2,
            alpha=0.34,
            zorder=2,
        )
    axis.scatter(
        -0.32 + jitter,
        eye,
        s=150,
        color=eye_color,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    axis.scatter(
        0.32 + jitter,
        control,
        s=150,
        color=CONTROL_QUANTIFICATION_COLOR,
        alpha=0.68,
        edgecolor="white",
        linewidth=1.2,
        zorder=3,
    )
    add_significance_bracket(
        axis,
        -0.32,
        0.32,
        significance_label(p_value),
        line_y=line_y,
        text_y=text_y,
        nonsignificant_text_y=ns_y,
        linewidth=2.2,
    )
    axis.text(
        0.0,
        set_y,
        label,
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="center",
        fontsize=26,
        fontfamily="Arial",
    )
    axis.set_xlim(-0.90, 0.90)
    axis.set_ylim(0.0, upper)
    axis.set_yticks(ticks)
    axis.set_xticks([-0.32, 0.32])
    axis.set_xticklabels(["Eye Drop", "Control"], fontsize=22)
    axis.text(
        -0.32,
        -0.105,
        f"({product_label})",
        transform=axis.get_xaxis_transform(),
        ha="center",
        va="top",
        fontsize=18,
        fontfamily="Arial",
        clip_on=False,
    )
    axis.tick_params(axis="x", labelsize=22, width=1.5, length=6, pad=12)
    axis.tick_params(axis="y", labelsize=23, width=1.5, length=6, labelleft=True)
    if show_ylabel:
        axis.set_ylabel("PSD (µV²/Hz)", fontsize=30)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)


def plot_set_quantification(
    frame: pd.DataFrame,
    statistics: pd.DataFrame,
    product_dir: str,
    path: Path,
) -> None:
    _, product_label, _, eye_color = normalize_product(product_dir)
    values = frame.loc[
        frame["Set"] != "All Sets", ["EyeDrop_PSD_uV2_per_Hz", "Control_PSD_uV2_per_Hz"]
    ].to_numpy(dtype=float)
    layout = quantification_axis_layout(values, minimum_upper=1e-12)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axes = plt.subplots(1, N_SETS, figsize=(34, 9), sharey=True)
    for set_number, axis in enumerate(axes, start=1):
        selected = frame.loc[frame["Set"] == set_number]
        p_value = float(statistics.loc[statistics["Set"] == set_number, "P_value_raw"].iloc[0])
        _draw_quantification_panel(
            axis,
            selected["EyeDrop_PSD_uV2_per_Hz"].to_numpy(dtype=float),
            selected["Control_PSD_uV2_per_Hz"].to_numpy(dtype=float),
            eye_color,
            product_label,
            f"Set {set_number}",
            4000 + set_number,
            layout,
            p_value,
            show_ylabel=set_number == 1,
        )
    figure.subplots_adjust(left=0.06, right=0.995, top=0.94, bottom=0.25, wspace=0.24)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def plot_all_sets_quantification(
    frame: pd.DataFrame,
    statistics: pd.DataFrame,
    product_dir: str,
    path: Path,
) -> None:
    _, product_label, _, eye_color = normalize_product(product_dir)
    selected = frame.loc[frame["Set"] == "All Sets"]
    values = selected[["EyeDrop_PSD_uV2_per_Hz", "Control_PSD_uV2_per_Hz"]].to_numpy()
    layout = quantification_axis_layout(values, minimum_upper=1e-12)
    plt.rcParams.update({"font.family": "Arial", "axes.linewidth": 1.5})
    figure, axis = plt.subplots(figsize=(7.5, 9))
    _draw_quantification_panel(
        axis,
        selected["EyeDrop_PSD_uV2_per_Hz"].to_numpy(dtype=float),
        selected["Control_PSD_uV2_per_Hz"].to_numpy(dtype=float),
        eye_color,
        product_label,
        "All Sets",
        7001,
        layout,
        float(statistics["P_value_raw"].iloc[0]),
        show_ylabel=True,
    )
    figure.subplots_adjust(left=0.20, right=0.98, top=0.94, bottom=0.25)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def pair_topography_values(item: dict[str, Any]) -> np.ndarray:
    eye = session_set_channel_means(item["eye_drop"])
    control = session_set_channel_means(item["control"])
    output = np.full((N_SETS, len(EXPECTED_CHANNEL_NAMES)), np.nan, dtype=float)
    for set_number in set(eye).intersection(control):
        output[set_number - 1] = eye[set_number] - control[set_number]
    return output


def _topomap_info() -> mne.Info:
    info = mne.create_info(EXPECTED_CHANNEL_NAMES, sfreq=SFREQ, ch_types="eeg")
    montage = mne.channels.make_standard_montage("colin27_1020")
    info.set_montage(montage, match_case=False, on_missing="raise")
    return info


def _nice_symmetric_topography_limit(values: np.ndarray) -> float:
    finite = np.abs(np.asarray(values, dtype=float))
    finite = finite[np.isfinite(finite)]
    maximum = float(np.max(finite)) if finite.size else 1.0
    if maximum <= np.finfo(float).eps:
        return 1.0
    exponent = math.floor(math.log10(maximum))
    scale = 10.0**exponent
    normalized = maximum / scale
    for multiplier in (1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0):
        if normalized <= multiplier:
            return float(multiplier * scale)
    raise RuntimeError("Unable to determine topography colour limit")


def plot_topography_grid(values: np.ndarray, path: Path, *, missing_label: bool = True) -> float:
    if values.shape != (N_SETS, len(EXPECTED_CHANNEL_NAMES)):
        raise ValueError(f"Unexpected topography matrix shape {values.shape}")
    limit = _nice_symmetric_topography_limit(values)
    plt.rcParams.update({"font.family": "Arial"})
    figure, axes = plt.subplots(1, N_SETS, figsize=(36, 6.5))
    info = _topomap_info()
    image = None
    for index, axis in enumerate(axes):
        vector = values[index]
        axis.set_title(f"Set {index + 1}", fontsize=24, fontfamily="Arial", pad=16)
        if not np.isfinite(vector).all():
            axis.set_axis_off()
            if missing_label:
                axis.text(0.5, 0.5, "Missing", ha="center", va="center", fontsize=22)
            continue
        image, _ = mne.viz.plot_topomap(
            vector,
            info,
            axes=axis,
            show=False,
            cmap="RdBu_r",
            vlim=(-limit, limit),
            sensors="k.",
            names=None,
            contours=0,
            extrapolate="head",
            # Use one fixed 10-20 head sphere so that sensor positions, the
            # interpolated surface and the scalp outline share the same frame.
            # ``sphere="auto"`` fitted this 32-channel montage too narrowly,
            # leaving several electrode dots and the colour surface outside
            # the drawn head circle.
            sphere=(0.0, 0.0, 0.0, 0.095),
            image_interp="cubic",
            border="mean",
            res=256,
        )
        # Match the agreed reference style: small electrode dots, thick circular
        # outline and nose, and no ear outlines.
        for line_number, line in enumerate(axis.lines):
            if line_number == 0:
                line.set_markersize(8.0)
                line.set_markeredgewidth(0.0)
                line.set_color("#2F2F2F")
                line.set_alpha(0.82)
            elif line_number in (1, 2):
                line.set_linewidth(4.0)
                line.set_color("#303030")
            else:
                line.set_visible(False)
        colorbar = figure.colorbar(
            image,
            ax=axis,
            fraction=0.080,
            pad=0.10,
            aspect=12,
            shrink=0.94,
        )
        colorbar.set_ticks([-limit, 0.0, limit])
        colorbar.set_label("ΔPSD (µV²/Hz)", fontsize=28, rotation=270, labelpad=34)
        colorbar.ax.tick_params(labelsize=24, width=1.5, length=7)
        colorbar.outline.set_linewidth(1.3)
    figure.subplots_adjust(left=0.018, right=0.99, top=0.86, bottom=0.08, wspace=0.62)
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)
    return limit


def _output_directories(output_root: Path, product_dir: str) -> dict[str, Path]:
    no1 = output_root / "Phase4_脳波解析" / "No1_FmTheta"
    product = no1 / product_dir
    return {
        "no1": no1,
        "individual": product / "Individual",
        "individual_fixed_y": product / "Individual" / "FixedYAxis_0to100uV2PerHz",
        "individual_smoothing_comparison": product / "Individual" / "SmoothingComparison",
        "grand": product / "GrandAverage",
        "quantification": product / "SetQuantification",
        "topography_individual": product / "Topography" / "Individual",
        "topography_grand": product / "Topography" / "GrandAverage",
        "grand_tables": no1 / "Sub" / "tables" / "GrandAverage",
        "quantification_tables": no1 / "Sub" / "tables" / "SetQuantification",
        "topography_tables": no1 / "Sub" / "tables" / "Topography",
        "logs": no1 / "Sub" / "logs",
    }


def load_pair_item(spec: ParticipantSpec, cache_root: Path) -> dict[str, Any]:
    first = load_session_cache(cache_path(cache_root, spec, spec.first_session_id))
    second = load_session_cache(cache_path(cache_root, spec, spec.second_session_id))
    by_id = {first.session_id: first, second.session_id: second}
    return {
        "spec": spec,
        "product_dir": normalize_product(spec.product)[0],
        "eye_drop": by_id[spec.drops_session_id],
        "control": by_id[spec.control_session_id],
    }


def write_individual_outputs(item: dict[str, Any], output_root: Path) -> dict[str, str]:
    spec = item["spec"]
    paths = _output_directories(output_root, item["product_dir"])
    individual = paths["individual"] / f"ID{spec.pair_id}_No1_FmTheta_Individual.png"
    individual_fixed_y = paths["individual_fixed_y"] / (
        f"ID{spec.pair_id}_No1_FmTheta_Individual_FixedYAxis_0to100uV2PerHz.png"
    )
    topography = paths["topography_individual"] / (f"ID{spec.pair_id}_No1_FmTheta_Topography.png")
    plot_individual_timecourse(spec, item["eye_drop"], item["control"], individual)
    plot_individual_timecourse(
        spec,
        item["eye_drop"],
        item["control"],
        individual_fixed_y,
        fixed_y_upper=FIXED_INDIVIDUAL_Y_UPPER,
    )
    plot_topography_grid(pair_topography_values(item), topography)
    return {
        "individual": str(individual),
        "individual_fixed_y": str(individual_fixed_y),
        "topography": str(topography),
    }


def write_smoothing_comparison_outputs(
    item: dict[str, Any], output_root: Path
) -> dict[str, str]:
    """Write only the three exploratory individual smoothing comparisons."""
    spec = item["spec"]
    paths = _output_directories(output_root, item["product_dir"])
    destination = paths["individual_smoothing_comparison"]
    all_displayed = []
    for seconds in SMOOTHING_COMPARISON_SECONDS:
        all_displayed.extend(
            [
                _time_series_values(item["eye_drop"], smoothing_seconds=seconds),
                _time_series_values(item["control"], smoothing_seconds=seconds),
            ]
        )
    common_y_axis = _nice_upper(np.concatenate(all_displayed), 0.70)
    outputs: dict[str, str] = {}
    for seconds in SMOOTHING_COMPARISON_SECONDS:
        path = destination / (
            f"ID{spec.pair_id}_No1_FmTheta_Individual_Smoothing{seconds}s.png"
        )
        plot_individual_timecourse(
            spec,
            item["eye_drop"],
            item["control"],
            path,
            smoothing_seconds=seconds,
            common_y_axis=common_y_axis,
        )
        outputs[f"{seconds}s"] = str(path)
    return outputs


def write_group_outputs(items: list[dict[str, Any]], output_root: Path) -> dict[str, Any]:
    products = sorted({item["product_dir"] for item in items})
    grand_by_product: dict[str, pd.DataFrame] = {}
    proposed: dict[str, tuple[float, np.ndarray]] = {}
    for product in products:
        grand, _ = build_grand_average(items, product)
        grand_by_product[product] = grand
        eye_sem = grand["EyeDrop_SEM_PSD_uV2_per_Hz"].fillna(0.0)
        control_sem = grand["Control_SEM_PSD_uV2_per_Hz"].fillna(0.0)
        displayed = np.concatenate(
            [
                grand["EyeDrop_Mean_PSD_uV2_per_Hz"] + eye_sem,
                grand["Control_Mean_PSD_uV2_per_Hz"] + control_sem,
            ]
        )
        proposed[product] = _nice_upper(displayed, 0.75)
    common_upper = max(value[0] for value in proposed.values())
    _, common_ticks = _nice_upper(np.array([common_upper * 0.75]), 0.75)
    if common_ticks[-1] != common_upper:
        step = common_ticks[1] - common_ticks[0]
        common_ticks = np.arange(0.0, common_upper + step * 0.01, step)

    outputs: dict[str, Any] = {}
    for product in products:
        paths = _output_directories(output_root, product)
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        grand = grand_by_product[product]
        grand_png = paths["grand"] / f"No1_FmTheta_GrandAverage_{product}.png"
        grand_csv = paths["grand_tables"] / f"No1_FmTheta_GrandAverage_Values_{product}.csv"
        plot_grand_average(
            grand, product, grand_png, common_upper=common_upper, common_ticks=common_ticks
        )
        grand.to_csv(grand_csv, index=False)

        quantification = build_quantification(items, product)
        set_statistics, overall_statistics = quantification_statistics(quantification)
        quant_png = paths["quantification"] / f"No1_FmTheta_SetQuantification_{product}.png"
        overall_png = paths["quantification"] / (f"No1_FmTheta_AllSetsQuantification_{product}.png")
        statistics_csv = paths["quantification"] / (
            f"No1_FmTheta_SetQuantification_Statistics_{product}.csv"
        )
        values_csv = paths["quantification_tables"] / (
            f"No1_FmTheta_SetQuantification_Values_{product}.csv"
        )
        overall_csv = paths["quantification_tables"] / (
            f"No1_FmTheta_AllSetsQuantification_Statistics_{product}.csv"
        )
        plot_set_quantification(quantification, set_statistics, product, quant_png)
        plot_all_sets_quantification(quantification, overall_statistics, product, overall_png)
        set_statistics.to_csv(statistics_csv, index=False)
        quantification.to_csv(values_csv, index=False)
        overall_statistics.to_csv(overall_csv, index=False)

        selected = [item for item in items if item["product_dir"] == product]
        pair_values = np.stack([pair_topography_values(item) for item in selected])
        group_topography = np.full(pair_values.shape[1:], np.nan)
        n_by_set = np.zeros(N_SETS, dtype=int)
        for set_index in range(N_SETS):
            valid_pairs = np.isfinite(pair_values[:, set_index, :]).all(axis=1)
            n_by_set[set_index] = int(valid_pairs.sum())
            if valid_pairs.any():
                group_topography[set_index] = pair_values[valid_pairs, set_index].mean(axis=0)
        group_topography_png = paths["topography_grand"] / (
            f"No1_FmTheta_Topography_GrandAverage_{product}.png"
        )
        plot_topography_grid(group_topography, group_topography_png)
        topography_values = pd.DataFrame(group_topography, columns=EXPECTED_CHANNEL_NAMES)
        topography_values.insert(0, "Set", np.arange(1, N_SETS + 1))
        topography_values.insert(1, "Valid_N", n_by_set)
        topography_csv = paths["topography_tables"] / (
            f"No1_FmTheta_Topography_GrandAverage_Values_{product}.csv"
        )
        topography_values.to_csv(topography_csv, index=False)
        outputs[product] = {
            "grand_average": str(grand_png),
            "set_quantification": str(quant_png),
            "all_sets_quantification": str(overall_png),
            "topography": str(group_topography_png),
        }
    return outputs


def _write_log(path: Path, payload: dict[str, Any]) -> None:
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
    modes.add_argument("--compute-psd", action="store_true")
    modes.add_argument("--individual-only", action="store_true")
    modes.add_argument("--smoothing-comparison-only", action="store_true")
    modes.add_argument("--group-outputs-only", action="store_true")
    modes.add_argument("--all", action="store_true")
    parser.add_argument(
        "--force-recompute",
        action="store_true",
        help="Recompute matching PSD caches; only use after an explicit analysis decision",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    specs = list(args.participant)
    if args.manifest:
        specs.extend(load_manifest(args.manifest))
    if not specs:
        raise SystemExit("Provide --participant or --manifest")
    if args.force_recompute and not (args.compute_psd or args.all):
        raise SystemExit("--force-recompute requires --compute-psd or --all")
    validate_participant_specs(specs, production_batch=args.production_batch)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    preflight = preflight_inputs(specs, args.input_root)
    logging.info("Input preflight passed: %s", json.dumps(preflight, ensure_ascii=False))
    if args.preflight_only:
        return 0

    cache_records: list[dict[str, Any]] = []
    if args.compute_psd or args.all:
        for spec in specs:
            for session_id in (spec.first_session_id, spec.second_session_id):
                cache_records.append(
                    {
                        "pair_id": spec.pair_id,
                        "session_id": session_id,
                        **compute_session_cache(
                            spec,
                            session_id,
                            args.input_root,
                            args.cache_root,
                            force_recompute=args.force_recompute,
                        ),
                    }
                )
        if args.compute_psd:
            log_root = _output_directories(args.output_root, "CCube")["logs"]
            _write_log(
                log_root / "No1_FmTheta_PSDCacheSummary.json",
                {
                    "script_version": SCRIPT_VERSION,
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "mode": "compute-psd",
                    "preflight": preflight,
                    "cache_records": cache_records,
                },
            )
            logging.info("PSD cache computation and validation completed")
            return 0

    items = [load_pair_item(spec, args.cache_root) for spec in specs]
    if args.smoothing_comparison_only:
        comparison_outputs = {
            item["spec"].pair_id: write_smoothing_comparison_outputs(item, args.output_root)
            for item in items
        }
        log_root = _output_directories(args.output_root, "CCube")["logs"]
        _write_log(
            log_root / "No1_FmTheta_SmoothingComparisonSummary.json",
            {
                "script_version": SCRIPT_VERSION,
                "completed_at": datetime.now().astimezone().isoformat(),
                "mode": "smoothing-comparison-only",
                "psd_window_seconds": WINDOW_SAMPLES / SFREQ,
                "psd_step_seconds": STEP_SAMPLES / SFREQ,
                "smoothing_seconds": list(SMOOTHING_COMPARISON_SECONDS),
                "nan_policy": "ignore_nan_return_nan_only_when_window_all_nan",
                "preflight": preflight,
                "comparison_outputs": comparison_outputs,
            },
        )
        logging.info("Smoothing comparison outputs completed")
        return 0
    individual_outputs: dict[str, dict[str, str]] = {}
    if args.individual_only or args.all:
        for item in items:
            individual_outputs[item["spec"].pair_id] = write_individual_outputs(
                item, args.output_root
            )
        if args.individual_only:
            log_root = _output_directories(args.output_root, "CCube")["logs"]
            _write_log(
                log_root / "No1_FmTheta_IndividualSummary.json",
                {
                    "script_version": SCRIPT_VERSION,
                    "completed_at": datetime.now().astimezone().isoformat(),
                    "mode": "individual-only",
                    "preflight": preflight,
                    "individual_outputs": individual_outputs,
                },
            )
            logging.info("Individual outputs completed")
            return 0

    group_outputs = write_group_outputs(items, args.output_root)
    log_root = _output_directories(args.output_root, "CCube")["logs"]
    summary_path = log_root / "No1_FmTheta_RunSummary.json"
    _write_log(
        summary_path,
        {
            "script_version": SCRIPT_VERSION,
            "completed_at": datetime.now().astimezone().isoformat(),
            "mode": "all" if args.all else "group-outputs-only",
            "cache_configuration": analysis_configuration(),
            "downstream_configuration": downstream_configuration(),
            "participants": [asdict(spec) | {"pair_id": spec.pair_id} for spec in specs],
            "preflight": preflight,
            "cache_records": cache_records,
            "individual_outputs": individual_outputs,
            "group_outputs": group_outputs,
        },
    )
    logging.info("Phase 4 No1 outputs completed: %s", summary_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
