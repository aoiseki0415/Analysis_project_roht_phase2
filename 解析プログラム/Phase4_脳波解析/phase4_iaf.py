"""No8–11: once-smoothed whole/half-Set PSD alpha peaks and audited raw cache.

The fixed production roots are deliberately not CLI-overridable. Numerical helper
functions accept arrays/paths so synthetic tests never require production writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import tempfile
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import h5py
import numpy as np
import pandas as pd
from Phase4_No1_FmTheta import (
    DEFAULT_INPUT_ROOT,
    DEFAULT_OUTPUT_ROOT,
    EXPECTED_MISSING_SETS,
    ParticipantSpec,
    _decode_names,
    input_path,
    load_manifest,
    normalize_product,
    session_file_prefix,
    validate_participant_specs,
)
from scipy.signal import find_peaks, get_window, periodogram

VERSION = "phase4-iaf-smoothed-localpeak-2026-11-10.3"
SCHEMA = "phase4-iaf-smoothed-localpeak-2026-11-10-v3"
LEGACY_SCHEMA = "phase4-iaf-localpeak-2026-11-10-v2"
CHANNELS = ("Pz", "Fz")
SFREQ = 256.0
SEGMENT_SAMPLES = 2560
STEP_SAMPLES = 1280
FREQUENCIES = np.arange(10, 401, dtype=float) / 10
ANALYSES = {
    8: ("Pz", "setwise", "No8_PzSetwiseIAF"),
    9: ("Pz", "halfset", "No9_PzHalfSetIAF"),
    10: ("Fz", "setwise", "No10_FzSetwiseIAF"),
    11: ("Fz", "halfset", "No11_FzHalfSetIAF"),
}
DEFAULT_CACHE_ROOT = (
    DEFAULT_INPUT_ROOT.parents[1] / "Phase4_脳波解析/No8-11_PzFzIAF/SpectralSegments"
)
LEGACY_CONFIG = {
    "schema": LEGACY_SCHEMA,
    "channels": CHANNELS,
    "sfreq_hz": SFREQ,
    "segment_samples": SEGMENT_SAMPLES,
    "step_samples": STEP_SAMPLES,
    "window": "get_window(hann,2560,fftbins=True)",
    "nfft": SEGMENT_SAMPLES,
    "detrend": "constant",
    "scaling": "density",
    "return_onesided": True,
    "unit": "uV^2/Hz",
    "input_conversion_precision": "float64 before amplitude scaling to microvolts",
    "frequency_hz": [1.0, 40.0, 0.1],
    "intervals": "whole Set; halves split at ceil(N/2), each independently anchored",
    "invalid_window": "any Phase1 bad sample or target-channel nonfinite sample",
    "minimum_valid_windows": 1,
    "mean": "linear arithmetic mean of valid periodograms",
    "peak": "find_peaks(mean linear PSD),8-15Hz inclusive,highest PSD,tie lowest Hz",
    "extra_peak_constraints": None,
    "padding": False,
    "additional_filter_or_reference": False,
    "background_correction_or_smoothing": False,
    "log3sd_exclusion": False,
}
BASE_PSD_CONFIG = {
    key: value
    for key, value in LEGACY_CONFIG.items()
    if key not in ("schema", "peak", "extra_peak_constraints", "background_correction_or_smoothing")
}
SMOOTHING_CONFIG = {
    "axis": "frequency",
    "input": "mean linear PSD after valid periodogram averaging,1-40Hz",
    "method": "centered equal-weight arithmetic moving average",
    "points": 5,
    "passes": 1,
    "bin_spacing_hz": 0.1,
    "center_offsets_hz": [-0.2, -0.1, 0.0, 0.1, 0.2],
    "endpoint": "truncated available bins,3/4 points at stored 1/40Hz edges",
    "nonfinite": "invalid spectrum remains unavailable; no interpolation",
}
CONFIG = {
    **BASE_PSD_CONFIG,
    "schema": SCHEMA,
    "smoothing": SMOOTHING_CONFIG,
    "peak": "find_peaks(smoothed mean linear PSD),8-15Hz inclusive,highest PSD,tie lowest Hz",
    "extra_peak_constraints": None,
    "background_correction": False,
}
RAW_INTERVAL_DATASETS = (
    "psd",
    "starts",
    "ends",
    "valid",
    "rejection_code",
    "mean_psd",
    "n_valid_segments",
    "usable_seconds",
    "coverage_fraction",
)
SPECTRAL_ROW_KEYS = {"mean_psd", "smoothed_mean_psd"}


def _json_config(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


def _config_digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_json_config(value).encode()).hexdigest()


def config_json() -> str:
    return _json_config(CONFIG)


def config_hash() -> str:
    return _config_digest(CONFIG)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def estimation_intervals(n_samples: int) -> dict[str, tuple[int, int]]:
    """Half-open intervals on original sample support, before artifact removal."""
    if n_samples < 0:
        raise ValueError("Negative sample count")
    midpoint = (int(n_samples) + 1) // 2
    return {"whole": (0, int(n_samples)), "a": (0, midpoint), "b": (midpoint, int(n_samples))}


def compute_periodograms(
    data_uv: np.ndarray, mask: np.ndarray, sfreq: float = SFREQ, *, start_sample: int = 0
) -> dict[str, np.ndarray]:
    """Input is explicitly microvolts; missing time is never concatenated."""
    data = np.asarray(data_uv, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    if sfreq != SFREQ:
        raise ValueError("IAF requires the verified 256 Hz sampling rate")
    if data.ndim != 2 or data.shape[1] != 2 or mask.shape != (len(data),):
        raise ValueError("Expected N×2 EEG channels and one time-aligned mask")
    if start_sample < 0:
        raise ValueError("Negative sample offset")
    local_starts = np.arange(0, len(data) - SEGMENT_SAMPLES + 1, STEP_SAMPLES, dtype=int)
    spectra = np.full((len(local_starts), 2, len(FREQUENCIES)), np.nan)
    valid = np.zeros((len(local_starts), 2), dtype=bool)
    codes = np.zeros((len(local_starts), 2), dtype=np.uint8)
    window = get_window("hann", SEGMENT_SAMPLES, fftbins=True)
    for i, start in enumerate(local_starts):
        stop = start + SEGMENT_SAMPLES
        bad_time = bool(mask[start:stop].any())
        for ch in range(2):
            segment = data[start:stop, ch]
            # Bit flags retain both reasons when they overlap.
            codes[i, ch] = int(bad_time) + 2 * int(not np.isfinite(segment).all())
            if codes[i, ch]:
                continue
            freqs, power = periodogram(
                segment,
                fs=sfreq,
                window=window,
                nfft=SEGMENT_SAMPLES,
                detrend="constant",
                return_onesided=True,
                scaling="density",
            )
            if not np.allclose(freqs[10:401], FREQUENCIES, atol=1e-12, rtol=0):
                raise AssertionError("Unexpected frequency grid")
            spectra[i, ch] = power[10:401]
            valid[i, ch] = True
    return {
        "freqs": FREQUENCIES.copy(),
        "psd": spectra,
        "starts": local_starts + start_sample,
        "ends": local_starts + start_sample + SEGMENT_SAMPLES,
        "valid": valid,
        "rejection_code": codes,
    }


def select_peak(freqs: np.ndarray, mean_linear_psd: np.ndarray) -> dict[str, Any]:
    """Pure selector: caller supplies the once-smoothed PSD; no hidden smoothing."""
    freqs = np.asarray(freqs, dtype=float)
    power = np.asarray(mean_linear_psd, dtype=float)
    if freqs.shape != FREQUENCIES.shape or not np.allclose(freqs, FREQUENCIES):
        raise ValueError("Expected 1–40 Hz in 0.1 Hz bins")
    result = {
        "frequency_hz": np.nan,
        "selected_peak_psd": np.nan,
        "n_candidates": 0,
        "candidate_frequencies_hz": np.array([], float),
        "candidate_psd": np.array([], float),
        "quality": "invalid_spectrum",
    }
    if power.shape != freqs.shape or not np.isfinite(power).all() or np.any(power < 0):
        return result
    indices, _ = find_peaks(power)
    indices = indices[(freqs[indices] >= 8) & (freqs[indices] <= 15)]
    result.update(
        n_candidates=len(indices),
        candidate_frequencies_hz=freqs[indices].copy(),
        candidate_psd=power[indices].copy(),
        quality="no_local_peak",
    )
    if len(indices):
        chosen = indices[np.argmax(power[indices])]
        result.update(
            frequency_hz=float(freqs[chosen]), selected_peak_psd=float(power[chosen]), quality="ok"
        )
    return result


def smooth_mean_psd(mean_linear_psd: np.ndarray) -> np.ndarray:
    """Apply one frequency-domain 5-bin mean without changing raw input.

    Averaging is across the last axis of the complete stored 1–40 Hz spectrum.
    A partially nonfinite/negative spectrum is invalid, not repaired by smoothing.
    Stored endpoints use 3/4 available bins; alpha endpoints still use all 5 bins.
    """
    source = np.asarray(mean_linear_psd, dtype=np.float64)
    if source.ndim < 1 or source.shape[-1] != len(FREQUENCIES):
        raise ValueError("Smoothing requires the complete 391-bin 1–40 Hz spectrum")
    result = np.full(source.shape, np.nan, dtype=np.float64)
    flattened = source.reshape((-1, len(FREQUENCIES)))
    output = result.reshape(flattened.shape)
    for index, spectrum in enumerate(flattened):
        if not np.isfinite(spectrum).all() or np.any(spectrum < 0):
            continue
        # Direct local means avoid cumulative-sum cancellation for small bins.
        output[index] = [
            spectrum[max(0, i - 2) : min(len(spectrum), i + 3)].mean() for i in range(len(spectrum))
        ]
    return result


def unique_coverage_seconds(starts: np.ndarray) -> float:
    starts = np.sort(np.asarray(starts, dtype=int))
    if not len(starts):
        return 0.0
    total = SEGMENT_SAMPLES
    previous_end = int(starts[0]) + SEGMENT_SAMPLES
    for start in starts[1:]:
        end = int(start) + SEGMENT_SAMPLES
        total += max(0, end - max(int(start), previous_end))
        previous_end = max(end, previous_end)
    return total / SFREQ


def estimate_interval(
    data_uv: np.ndarray, mask: np.ndarray, *, start_sample: int = 0
) -> dict[str, Any]:
    result: dict[str, Any] = compute_periodograms(data_uv, mask, start_sample=start_sample)
    means = np.full((2, len(FREQUENCIES)), np.nan)
    smoothed = np.full_like(means, np.nan)
    counts = result["valid"].sum(axis=0).astype(int)
    coverage = np.zeros(2)
    peaks = []
    for ch in range(2):
        valid = result["valid"][:, ch]
        if counts[ch]:
            means[ch] = result["psd"][valid, ch].mean(axis=0)
        smoothed[ch] = smooth_mean_psd(means[ch])
        peak = select_peak(FREQUENCIES, smoothed[ch])
        if not counts[ch]:
            peak["quality"] = "too_short" if not len(result["starts"]) else "all_windows_invalid"
        peaks.append(peak)
        coverage[ch] = unique_coverage_seconds(result["starts"][valid])
    duration = len(data_uv) / SFREQ
    last_end = int(result["ends"][-1]) - start_sample if len(result["ends"]) else 0
    result.update(
        mean_psd=means,
        smoothed_mean_psd=smoothed,
        n_possible_segments=len(result["starts"]),
        n_valid_segments=counts,
        usable_seconds=coverage,
        coverage_fraction=coverage / duration if duration else np.zeros(2),
        tail_unused_seconds=(len(data_uv) - last_end) / SFREQ,
        duration_seconds=duration,
        start_sample=start_sample,
        stop_sample=start_sample + len(data_uv),
        peaks=peaks,
    )
    return result


def _text(value: Any) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def inspect_source(path: Path, sid: str, set_number: int) -> dict[str, Any]:
    """Read metadata/time/mask only; spectra loader reads the two channels later."""
    with h5py.File(path, "r") as handle:
        required = [
            "signal/data",
            "signal/channel_names",
            "time/relative_seconds",
            "time/OriginalTimestamp",
            "qc/ica_training_excluded_mask",
            "qc/ica_channel_excluded_mask",
        ]
        if any(key not in handle for key in required):
            raise ValueError(f"{path}: incomplete Phase1 schema")
        if _text(handle.attrs.get("participant_id")) != sid:
            raise ValueError(f"{path}: participant mismatch")
        if int(handle.attrs.get("set_number", -1)) != set_number:
            raise ValueError(f"{path}: Set mismatch")
        if _text(handle.attrs.get("data_kind")) != "brain_activity_eeg":
            raise ValueError(f"{path}: not brain-activity EEG")
        fs = float(handle.attrs.get("sampling_frequency_hz", np.nan))
        if fs != SFREQ:
            raise ValueError(f"{path}: sampling frequency must be 256 Hz")
        unit = _text(handle.attrs.get("signal_unit"))
        if unit not in ("V", "uV", "µV", "μV"):
            raise ValueError(f"{path}: unknown amplitude unit {unit}")
        names = _decode_names(handle["signal/channel_names"][:])
        shape = handle["signal/data"].shape
        if len(set(names)) != len(names) or len(shape) != 2 or shape[1] != len(names):
            raise ValueError(f"{path}: channel/shape mismatch")
        n = shape[0]
        if n < 1:
            raise ValueError(f"{path}: empty Set")
        for key in required[2:5]:
            if handle[key].shape != (n,):
                raise ValueError(f"{path}: bad shape for {key}")
        excluded = handle["qc/ica_channel_excluded_mask"][:]
        mask = handle["qc/ica_training_excluded_mask"][:]
        if excluded.shape != (len(names),) or not np.isin(excluded, [0, 1]).all():
            raise ValueError(f"{path}: invalid channel mask")
        if not np.isin(mask, [0, 1]).all():
            raise ValueError(f"{path}: invalid time mask")
        relative = handle["time/relative_seconds"][:]
        original = handle["time/OriginalTimestamp"][:]
        if not np.isfinite(relative).all() or not np.allclose(
            np.diff(relative), 1 / SFREQ, rtol=0, atol=1e-8
        ):
            raise ValueError(f"{path}: relative sample clock is not uniform 256 Hz")
        # Wireless OriginalTimestamp has acquisition jitter. The Phase1 uniform
        # relative sample clock, not transport timestamps, defines Welch windows.
        if not np.isfinite(original).all() or np.any(np.diff(original) <= 0):
            raise ValueError(f"{path}: original timestamps must be finite and increasing")
        info = {
            "set": set_number,
            "path": str(path.resolve()),
            "n_samples": n,
            "sfreq_hz": fs,
            "signal_unit": unit,
            "amplitude_to_uv": 1e6 if unit == "V" else 1.0,
            "channel_names": names,
            "missing_channels": [ch for ch in CHANNELS if ch not in names],
            "relative_start_seconds": float(relative[0]),
            "original_start_seconds": float(original[0]),
            "original_timestamp_max_step_error_seconds": float(
                np.max(np.abs(np.diff(original) - 1 / SFREQ))
            )
            if n > 1
            else 0.0,
            "ica_channel_excluded": [
                bool(excluded[names.index(ch)]) if ch in names else False for ch in CHANNELS
            ],
        }
    stat = path.stat()
    info.update(bytes=stat.st_size, mtime_ns=stat.st_mtime_ns, sha256=sha256_file(path))
    return info


def source_fingerprints(spec: ParticipantSpec, sid: str, root: Path) -> list[dict[str, Any]]:
    session_file_prefix(spec, sid)  # Validate membership.
    records = []
    missing = set()
    for number in range(1, 7):
        path = input_path(root, sid, number)
        if not path.exists():
            missing.add(number)
        else:
            records.append(inspect_source(path, sid, number))
    if missing != EXPECTED_MISSING_SETS.get(sid, set()):
        raise ValueError(f"ID{sid}: unexpected missing Sets {sorted(missing)}")
    return records


def cache_file(root: Path, spec: ParticipantSpec, sid: str) -> Path:
    return root / f"{session_file_prefix(spec, sid)}_PzFz_IAFSpectra.h5"


def session_metadata(spec: ParticipantSpec, sid: str) -> dict[str, Any]:
    return {
        "pair_id": spec.pair_id,
        "session_id": sid,
        "product": normalize_product(spec.product)[0],
        "condition": "Eye Drop" if sid == spec.drops_session_id else "Control",
        "first_session_id": spec.first_session_id,
        "second_session_id": spec.second_session_id,
        "drops_session_id": spec.drops_session_id,
    }


def _write_interval(group: h5py.Group, result: dict[str, Any]) -> None:
    for key in (
        "start_sample",
        "stop_sample",
        "duration_seconds",
        "tail_unused_seconds",
        "n_possible_segments",
    ):
        group.attrs[key] = result[key]
    group.attrs["start_seconds"] = result["start_sample"] / SFREQ
    group.attrs["stop_seconds"] = result["stop_sample"] / SFREQ
    for key in RAW_INTERVAL_DATASETS:
        group.create_dataset(key, data=result[key], compression="gzip", shuffle=True)
    _write_smoothing(group, result["smoothed_mean_psd"])
    for channel, peak in zip(CHANNELS, result["peaks"], strict=True):
        _write_peak(group, channel, peak)


def _write_smoothing(group: h5py.Group, smoothed: np.ndarray) -> None:
    # Explicit-unit names are hard links, not a second rounded copy of the raw PSD.
    group["window_psd_uv2_hz"] = group["psd"]
    group["mean_psd_uv2_hz"] = group["mean_psd"]
    group.create_dataset(
        "smoothed_mean_psd_uv2_hz", data=smoothed, compression="gzip", shuffle=True
    )


def _write_peak(group: h5py.Group, channel: str, peak: dict[str, Any]) -> None:
    target = group.create_group(f"peaks/{channel}")
    for key, value in peak.items():
        if isinstance(value, np.ndarray):
            target.create_dataset(key, data=value)
        else:
            target.attrs[key] = value


def validate_cache(
    path: Path,
    *,
    expected_metadata: dict[str, Any] | None = None,
    expected_sources: list[dict[str, Any]] | None = None,
    legacy_unsmoothed: bool = False,
) -> dict[str, Any]:
    """Validate current cache, or explicitly validate exact v2 for migration only."""
    expected_config = LEGACY_CONFIG if legacy_unsmoothed else CONFIG
    expected_schema = LEGACY_SCHEMA if legacy_unsmoothed else SCHEMA
    raw_payload_sha256 = None
    with h5py.File(path, "r") as handle:
        expected = {
            "schema": expected_schema,
            "calc_config_json": _json_config(expected_config),
            "calc_config_sha256": _config_digest(expected_config),
            "complete": 1,
        }
        if not legacy_unsmoothed:
            expected.update(
                base_psd_config_json=_json_config(BASE_PSD_CONFIG),
                base_psd_config_sha256=_config_digest(BASE_PSD_CONFIG),
                smoothing_config_json=_json_config(SMOOTHING_CONFIG),
                smoothing_config_sha256=_config_digest(SMOOTHING_CONFIG),
                peak_input_dataset="smoothed_mean_psd_uv2_hz",
            )
        expected.update(expected_metadata or {})
        for key, value in expected.items():
            if handle.attrs.get(key) != value:
                raise ValueError(f"{path}: stale/mismatched cache attribute {key}")
        if not legacy_unsmoothed:
            raw_payload_sha256 = handle.attrs.get("raw_payload_sha256")
            if not isinstance(raw_payload_sha256, str) or len(raw_payload_sha256) != 64:
                raise ValueError(f"{path}: missing raw spectral payload fingerprint")
        sources = json.loads(handle.attrs["sources_json"])
        if expected_sources is not None and sources != expected_sources:
            raise ValueError(f"{path}: changed source fingerprints; no silent reuse")
        if not np.array_equal(handle["frequencies_hz"][:], FREQUENCIES):
            raise ValueError(f"{path}: frequency mismatch")
        if _decode_names(handle["channel_names"][:]) != list(CHANNELS):
            raise ValueError(f"{path}: channel mismatch")
        if handle.attrs.get("psd_unit") != "uV^2/Hz" or handle.attrs.get("sfreq_hz") != SFREQ:
            raise ValueError(f"{path}: units/fs mismatch")
        actual_sets = {int(key[3:]) for key in handle if key.startswith("Set")}
        if actual_sets != {r["set"] for r in sources}:
            raise ValueError(f"{path}: Set inventory mismatch")
        for record in sources:
            parent = handle[f"Set{record['set']}"]
            n = int(parent.attrs["n_samples"])
            if n != record["n_samples"]:
                raise ValueError(f"{path}: sample count mismatch")
            if not np.array_equal(
                parent["ica_channel_excluded"][:], record["ica_channel_excluded"]
            ):
                raise ValueError(f"{path}: ICA exclusion provenance mismatch")
            for interval, (start, stop) in estimation_intervals(n).items():
                group = parent[interval]
                expected_starts = np.arange(start, stop - SEGMENT_SAMPLES + 1, STEP_SAMPLES)
                starts, ends = group["starts"][:], group["ends"][:]
                valid, psd = group["valid"][:], group["psd"][:]
                if group.attrs["start_sample"] != start or group.attrs["stop_sample"] != stop:
                    raise ValueError(f"{path}: interval boundary mismatch")
                if not np.array_equal(starts, expected_starts) or not np.array_equal(
                    ends, starts + SEGMENT_SAMPLES
                ):
                    raise ValueError(f"{path}: independent window-grid mismatch")
                if psd.shape != (len(starts), 2, len(FREQUENCIES)) or valid.shape != (
                    len(starts),
                    2,
                ):
                    raise ValueError(f"{path}: spectral shape mismatch")
                if not legacy_unsmoothed:
                    if (
                        group["mean_psd_uv2_hz"].id != group["mean_psd"].id
                        or group["window_psd_uv2_hz"].id != group["psd"].id
                        or group["smoothed_mean_psd_uv2_hz"].shape != (2, len(FREQUENCIES))
                    ):
                        raise ValueError(f"{path}: raw aliases/smoothed spectrum mismatch")
                if (
                    not np.isfinite(psd[valid]).all()
                    or np.any(psd[valid] < 0)
                    or not np.isnan(psd[~valid]).all()
                ):
                    raise ValueError(f"{path}: invalid spectral values")
                if not np.array_equal(group["rejection_code"][:] == 0, valid):
                    raise ValueError(f"{path}: exclusion flags disagree")
                if not np.array_equal(group["n_valid_segments"][:], valid.sum(axis=0)):
                    raise ValueError(f"{path}: count mismatch")
                duration = (stop - start) / SFREQ
                tail = (stop - int(ends[-1])) / SFREQ if len(ends) else duration
                if (
                    group.attrs["n_possible_segments"] != len(starts)
                    or not np.isclose(group.attrs["duration_seconds"], duration)
                    or not np.isclose(group.attrs["tail_unused_seconds"], tail)
                ):
                    raise ValueError(f"{path}: interval/count/tail metadata mismatch")
                for ci, ch in enumerate(CHANNELS):
                    mean = (
                        psd[valid[:, ci], ci].mean(axis=0)
                        if valid[:, ci].any()
                        else np.full(len(FREQUENCIES), np.nan)
                    )
                    if not np.allclose(
                        group["mean_psd"][ci], mean, equal_nan=True, rtol=1e-12, atol=0
                    ):
                        raise ValueError(f"{path}: mean spectrum mismatch")
                    peak_input = mean
                    if not legacy_unsmoothed:
                        peak_input = smooth_mean_psd(mean)
                        if not np.array_equal(
                            group["smoothed_mean_psd_uv2_hz"][ci], peak_input, equal_nan=True
                        ):
                            raise ValueError(f"{path}: once-smoothed spectrum mismatch")
                    peak = select_peak(FREQUENCIES, peak_input)
                    cached_peak = group[f"peaks/{ch}"]
                    if not np.isclose(
                        cached_peak.attrs["frequency_hz"], peak["frequency_hz"], equal_nan=True
                    ):
                        raise ValueError(f"{path}: peak mismatch")
                    quality = peak["quality"]
                    if not valid[:, ci].any():
                        quality = "too_short" if not len(starts) else "all_windows_invalid"
                    if ch in record["missing_channels"]:
                        quality = "missing_channel"
                    if (
                        cached_peak.attrs["quality"] != quality
                        or cached_peak.attrs["n_candidates"] != peak["n_candidates"]
                        or not np.isclose(
                            cached_peak.attrs["selected_peak_psd"],
                            peak["selected_peak_psd"],
                            equal_nan=True,
                        )
                    ):
                        raise ValueError(f"{path}: peak quality metadata mismatch")
                    for key in ("candidate_frequencies_hz", "candidate_psd"):
                        if not np.array_equal(cached_peak[key][:], peak[key]):
                            raise ValueError(f"{path}: candidate mismatch")
                    coverage = unique_coverage_seconds(starts[valid[:, ci]])
                    if not np.isclose(group["usable_seconds"][ci], coverage):
                        raise ValueError(f"{path}: coverage mismatch")
                    fraction = coverage / duration if duration else 0
                    if not np.isclose(group["coverage_fraction"][ci], fraction):
                        raise ValueError(f"{path}: coverage fraction mismatch")
    if raw_payload_sha256 is not None and raw_cache_fingerprint(path) != raw_payload_sha256:
        raise ValueError(f"{path}: raw spectral payload fingerprint mismatch")
    return {"path": str(path), "schema": expected_schema, "validated": True}


def _processing_attributes() -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "calc_config_json": config_json(),
        "calc_config_sha256": config_hash(),
        "base_psd_config_json": _json_config(BASE_PSD_CONFIG),
        "base_psd_config_sha256": _config_digest(BASE_PSD_CONFIG),
        "smoothing_config_json": _json_config(SMOOTHING_CONFIG),
        "smoothing_config_sha256": _config_digest(SMOOTHING_CONFIG),
        "peak_input_dataset": "smoothed_mean_psd_uv2_hz",
        "code_version": VERSION,
        "engine_sha256": sha256_file(Path(__file__)),
    }


def raw_cache_fingerprint(path: Path) -> str:
    """Hash untouched raw values and acquisition/window metadata, excluding peaks."""
    digest = hashlib.sha256()

    def update_value(key: str, value: Any) -> None:
        digest.update(key.encode())
        array = np.asarray(value)
        digest.update(str((array.shape, array.dtype.str)).encode())
        if array.dtype.kind in "OSU":
            digest.update(json.dumps(array.tolist(), default=_text, sort_keys=True).encode())
        else:
            digest.update(np.ascontiguousarray(array).tobytes())

    with h5py.File(path, "r") as handle:
        for key in ("sources_json", "sfreq_hz", "psd_unit"):
            update_value(f"attrs/{key}", handle.attrs[key])
        for key in ("frequencies_hz", "channel_names"):
            update_value(key, handle[key][:])
        for name in sorted(key for key in handle if key.startswith("Set")):
            parent = handle[name]
            for key in sorted(parent.attrs):
                update_value(f"{name}/attrs/{key}", parent.attrs[key])
            update_value(f"{name}/ica_channel_excluded", parent["ica_channel_excluded"][:])
            for interval in ("whole", "a", "b"):
                group = parent[interval]
                for key in sorted(group.attrs):
                    update_value(f"{name}/{interval}/attrs/{key}", group.attrs[key])
                for key in RAW_INTERVAL_DATASETS:
                    update_value(f"{name}/{interval}/{key}", group[key][:])
    return digest.hexdigest()


def upgrade_smoothing_cache(
    path: Path,
    *,
    expected_metadata: dict[str, Any],
    expected_sources: list[dict[str, Any]],
) -> dict[str, Any]:
    """Explicit atomic v2→v3 upgrade; never recompute EEG PSD or accept other schemas."""
    with h5py.File(path, "r") as source:
        schema = source.attrs.get("schema")
    if schema == SCHEMA:
        validate_cache(path, expected_metadata=expected_metadata, expected_sources=expected_sources)
        return {"upgraded": False, "schema": SCHEMA}
    validate_cache(
        path,
        expected_metadata=expected_metadata,
        expected_sources=expected_sources,
        legacy_unsmoothed=True,
    )
    original_hash = sha256_file(path)
    raw_hash = raw_cache_fingerprint(path)
    descriptor, filename = tempfile.mkstemp(
        prefix=f".{path.stem}.", suffix=".partial.h5", dir=path.parent
    )
    os.close(descriptor)
    temporary = Path(filename)
    try:
        shutil.copyfile(path, temporary)
        with h5py.File(temporary, "r+") as target:
            target.attrs["complete"] = 0
            prior_code = _text(target.attrs.get("code_version", "unknown"))
            prior_engine = _text(target.attrs.get("engine_sha256", "unknown"))
            target.attrs.update(_processing_attributes())
            target.attrs.update(
                upgraded_from_schema=LEGACY_SCHEMA,
                upgraded_from_code_version=prior_code,
                base_psd_created_by_version=prior_code,
                base_psd_engine_sha256=prior_engine,
                upgraded_from_file_sha256=original_hash,
                raw_payload_sha256=raw_hash,
                smoothing_applied_utc=datetime.now(UTC).isoformat(),
                upgrade_method="validated raw cache copy; no EEG PSD recomputation",
            )
            for record in expected_sources:
                parent = target[f"Set{record['set']}"]
                for interval in ("whole", "a", "b"):
                    group = parent[interval]
                    smoothed = smooth_mean_psd(group["mean_psd"][:])
                    _write_smoothing(group, smoothed)
                    del group["peaks"]
                    for ci, ch in enumerate(CHANNELS):
                        peak = select_peak(FREQUENCIES, smoothed[ci])
                        if not group["n_valid_segments"][ci]:
                            peak["quality"] = (
                                "too_short" if not len(group["starts"]) else "all_windows_invalid"
                            )
                        if ch in record["missing_channels"]:
                            peak["quality"] = "missing_channel"
                        _write_peak(group, ch, peak)
            target.attrs["complete"] = 1
        validate_cache(
            temporary, expected_metadata=expected_metadata, expected_sources=expected_sources
        )
        if raw_cache_fingerprint(temporary) != raw_hash:
            raise AssertionError("Smoothing upgrade changed raw spectral payload")
        if sha256_file(path) != original_hash:
            raise ValueError("Cache changed during upgrade; refusing replacement")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "upgraded": True,
        "schema": SCHEMA,
        "raw_payload_sha256": raw_hash,
        "previous_file_sha256": original_hash,
        "sha256": sha256_file(path),
    }


def prepare_cache(
    spec: ParticipantSpec,
    sid: str,
    input_root: Path,
    cache_root: Path,
    *,
    read_only: bool,
    fingerprints: list[dict[str, Any]] | None = None,
    upgrade_smoothing: bool = False,
) -> tuple[Path, bool]:
    if read_only and upgrade_smoothing:
        raise ValueError("--figures-only is read-only and cannot upgrade smoothing")
    path = cache_file(cache_root, spec, sid)
    records = (
        fingerprints if fingerprints is not None else source_fingerprints(spec, sid, input_root)
    )
    metadata = session_metadata(spec, sid)
    if path.exists():
        if upgrade_smoothing:
            upgrade_smoothing_cache(path, expected_metadata=metadata, expected_sources=records)
        validate_cache(path, expected_metadata=metadata, expected_sources=records)
        return path, False
    if read_only or upgrade_smoothing:
        raise FileNotFoundError(f"This mode requires a valid existing cache: {path}")
    cache_root.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial.h5")
    try:
        with h5py.File(temporary, "w") as target:
            target.attrs.update(metadata)
            target.attrs.update(_processing_attributes())
            target.attrs.update(
                sources_json=json.dumps(records, sort_keys=True),
                sfreq_hz=SFREQ,
                psd_unit="uV^2/Hz",
                created_utc=datetime.now(UTC).isoformat(),
                base_psd_created_by_version=VERSION,
                base_psd_engine_sha256=sha256_file(Path(__file__)),
                rejection_code_legend="bit0=Phase1_bad_time;bit1=target_nonfinite;0=valid",
            )
            target.create_dataset("frequencies_hz", data=FREQUENCIES)
            target.create_dataset(
                "channel_names", data=np.asarray(CHANNELS, dtype=h5py.string_dtype())
            )
            for record in records:
                source_path = Path(record["path"])
                stat = source_path.stat()
                if stat.st_size != record["bytes"] or stat.st_mtime_ns != record["mtime_ns"]:
                    raise ValueError(f"Source changed after preflight: {source_path}")
                with h5py.File(source_path, "r") as source:
                    names = record["channel_names"]
                    values = np.full((record["n_samples"], 2), np.nan)
                    for ci, channel in enumerate(CHANNELS):
                        if channel in names:
                            values[:, ci] = (
                                np.asarray(
                                    source["signal/data"][:, names.index(channel)], dtype=np.float64
                                )
                                * record["amplitude_to_uv"]
                            )
                    mask = source["qc/ica_training_excluded_mask"][:].astype(bool)
                parent = target.create_group(f"Set{record['set']}")
                parent.attrs.update(
                    n_samples=len(values),
                    duration_seconds=len(values) / SFREQ,
                    original_start_seconds=record["original_start_seconds"],
                    relative_start_seconds=record["relative_start_seconds"],
                    artifact_sample_fraction=float(mask.mean()),
                    missing_channels_json=json.dumps(record["missing_channels"]),
                )
                parent.create_dataset("ica_channel_excluded", data=record["ica_channel_excluded"])
                for label, (start, stop) in estimation_intervals(len(values)).items():
                    result = estimate_interval(
                        values[start:stop], mask[start:stop], start_sample=start
                    )
                    for ci, ch in enumerate(CHANNELS):
                        if ch in record["missing_channels"]:
                            result["peaks"][ci]["quality"] = "missing_channel"
                    _write_interval(parent.create_group(label), result)
            target.attrs["complete"] = 1
        raw_hash = raw_cache_fingerprint(temporary)
        with h5py.File(temporary, "r+") as target:
            target.attrs["raw_payload_sha256"] = raw_hash
        validate_cache(temporary, expected_metadata=metadata, expected_sources=records)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    validate_cache(path, expected_metadata=metadata, expected_sources=records)
    return path, True


def rows_from_cache(path: Path) -> dict[int, list[dict[str, Any]]]:
    rows: dict[int, list[dict[str, Any]]] = {number: [] for number in ANALYSES}
    with h5py.File(path, "r") as handle:
        if (
            handle.attrs.get("schema") != SCHEMA
            or handle.attrs.get("calc_config_sha256") != config_hash()
        ):
            raise ValueError("Rows require current smoothed-PSD cache; no raw fallback")
        metadata = {
            key: _text(handle.attrs[key])
            for key in ("pair_id", "session_id", "condition", "product")
        }
        for analysis, (channel, kind, _) in ANALYSES.items():
            ci = CHANNELS.index(channel)
            labels = ("whole",) if kind == "setwise" else ("a", "b")
            for set_number in range(1, 7):
                for interval in labels:
                    row = {
                        **metadata,
                        "analysis_number": analysis,
                        "channel": channel,
                        "set_number": set_number,
                        "interval": interval,
                        "position": set_number
                        if kind == "setwise"
                        else 2 * set_number - int(interval == "a"),
                        "frequency_hz": np.nan,
                        "selected_peak_psd": np.nan,
                        "n_candidates": 0,
                        "candidate_frequencies_hz": "[]",
                        "candidate_psd": "[]",
                        "quality": "missing_set",
                        "n_possible_segments": 0,
                        "n_valid_segments": 0,
                        "usable_seconds": 0.0,
                        "coverage_fraction": 0.0,
                        "duration_seconds": np.nan,
                        "set_duration_seconds": np.nan,
                        "start_sample": np.nan,
                        "stop_sample": np.nan,
                        "start_seconds": np.nan,
                        "stop_seconds": np.nan,
                        "tail_unused_seconds": np.nan,
                        "ica_channel_excluded": False,
                        "mean_psd": np.full(len(FREQUENCIES), np.nan),
                        "smoothed_mean_psd": np.full(len(FREQUENCIES), np.nan),
                        "peak_input_dataset": "smoothed_mean_psd_uv2_hz",
                        "smoothing_points": 5,
                        "smoothing_passes": 1,
                    }
                    if f"Set{set_number}" in handle:
                        parent = handle[f"Set{set_number}"]
                        group = parent[interval]
                        peak = group[f"peaks/{channel}"]
                        row.update(
                            {
                                key: value.item() if isinstance(value, np.generic) else value
                                for key, value in peak.attrs.items()
                            }
                        )
                        for key in ("candidate_frequencies_hz", "candidate_psd"):
                            row[key] = json.dumps(peak[key][:].tolist())
                        for key in (
                            "duration_seconds",
                            "start_sample",
                            "stop_sample",
                            "start_seconds",
                            "stop_seconds",
                            "tail_unused_seconds",
                            "n_possible_segments",
                        ):
                            row[key] = group.attrs[key]
                        for key in ("n_valid_segments", "usable_seconds", "coverage_fraction"):
                            row[key] = group[key][ci].item()
                        row.update(
                            mean_psd=group["mean_psd"][ci],
                            smoothed_mean_psd=group["smoothed_mean_psd_uv2_hz"][ci],
                            set_duration_seconds=float(parent.attrs["duration_seconds"]),
                            ica_channel_excluded=bool(parent["ica_channel_excluded"][ci]),
                        )
                    rows[analysis].append(row)
    return rows


def validate_rows(rows: list[dict[str, Any]], number: int, n_sessions: int) -> dict[str, Any]:
    frame = pd.DataFrame(
        [{k: v for k, v in row.items() if k not in SPECTRAL_ROW_KEYS} for row in rows]
    )
    expected = n_sessions * (6 if number in (8, 10) else 12)
    if len(frame) != expected or frame.duplicated(["session_id", "position"]).any():
        raise AssertionError("Estimate row count/positions mismatch")
    finite = np.isfinite(frame.frequency_hz)
    values = frame.loc[finite, "frequency_hz"].to_numpy()
    if (
        not frame.loc[finite, "quality"].eq("ok").all()
        or not frame.loc[~finite, "quality"].ne("ok").all()
    ):
        raise AssertionError("Peak quality contradicts frequency availability")
    if np.any((values < 8) | (values > 15)) or not np.allclose(values * 10, np.round(values * 10)):
        raise AssertionError("Peak outside inclusive 8–15 Hz / 0.1 Hz grid")
    if np.any(frame.n_valid_segments > frame.n_possible_segments):
        raise AssertionError("Invalid window counts")
    return {
        "rows": len(frame),
        "valid_estimates": int(finite.sum()),
        "quality_counts": dict(Counter(frame.quality)),
        "retained_ica_excluded_channel_rows": int(frame.ica_channel_excluded.sum()),
    }


def write_json(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial.json")
    temporary.write_text(
        json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    os.replace(temporary, path)
    json.loads(path.read_text(encoding="utf-8"))


def render_analysis(
    rows: list[dict[str, Any]], specs: list[ParticipantSpec], root: Path, number: int
) -> list[dict[str, Any]]:
    from phase4_iaf_figures import plot_pair_three_panel

    channel, kind, _ = ANALYSES[number]
    tag = "SetwiseIAF" if kind == "setwise" else "HalfSetIAF"
    results = []
    for spec in specs:
        pair_rows = [row for row in rows if row["pair_id"] == spec.pair_id]
        kwargs: dict[str, Any] = {}
        for condition, prefix in (("Eye Drop", "drops"), ("Control", "control")):
            selected = sorted(
                [r for r in pair_rows if r["condition"] == condition], key=lambda r: r["position"]
            )
            if len(selected) != (6 if kind == "setwise" else 12):
                raise ValueError("Figure requires all fixed positions for both conditions")
            kwargs[f"{prefix}_psd"] = np.stack([r["smoothed_mean_psd"] for r in selected])
            kwargs[f"{prefix}_iaf_hz"] = np.array([r["frequency_hz"] for r in selected])
        destination = (
            root
            / spec.product
            / "Individual"
            / f"Pair{spec.pair_id}_No{number}_{channel}_{tag}_ThreePanel.png"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = plot_pair_three_panel(
            analysis_number=number,
            product=spec.product,
            frequencies_hz=FREQUENCIES,
            output_path=destination,
            **kwargs,
        )
        results.append(
            {"path": str(destination), "sha256": sha256_file(destination), "render": result}
        )
    return results


def main(argv: list[str] | None = None, *, fixed_analysis: int | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--production-batch", action="store_true")
    parser.add_argument(
        "--upgrade-smoothing",
        action="store_true",
        help="Validate and atomically upgrade v2 raw caches without EEG PSD recomputation",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("all", "compute-only", "figures-only", "preflight-only"):
        mode.add_argument(f"--{name}", action="store_true")
    if fixed_analysis is None:
        parser.add_argument(
            "--analysis", type=int, choices=list(ANALYSES), nargs="+", default=list(ANALYSES)
        )
    args = parser.parse_args(argv)
    if args.upgrade_smoothing and (args.figures_only or args.preflight_only):
        parser.error("--upgrade-smoothing requires --all or --compute-only")
    numbers = [fixed_analysis] if fixed_analysis else args.analysis
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    specs = [
        ParticipantSpec(
            s.first_session_id,
            s.second_session_id,
            s.drops_session_id,
            normalize_product(s.product)[0],
        )
        for s in load_manifest(args.manifest)
    ]
    if not specs:
        raise ValueError("Empty participant manifest")
    validate_participant_specs(specs, production_batch=args.production_batch)
    if args.production_batch:
        expected_first = {str(i) for i in range(101, 142)} - {"130"}
        if {s.first_session_id for s in specs} != expected_first or any(
            int(s.second_session_id) != int(s.first_session_id) + 100 for s in specs
        ):
            raise ValueError("Production manifest does not match the authorized 40 paired sessions")
    output_base = DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
    run_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    selected_mode = (
        "preflight-only"
        if args.preflight_only
        else "compute-only"
        if args.compute_only
        else "figures-only"
        if args.figures_only
        else "all"
    )
    code_paths = [Path(__file__), Path(__file__).with_name("phase4_iaf_figures.py")]
    run: dict[str, Any] = {
        "started_utc": datetime.now(UTC).isoformat(),
        "status": "running",
        "mode": selected_mode,
        "version": VERSION,
        "schema": SCHEMA,
        "config": CONFIG,
        "calc_config_sha256": config_hash(),
        "base_psd_config_sha256": _config_digest(BASE_PSD_CONFIG),
        "smoothing_config_sha256": _config_digest(SMOOTHING_CONFIG),
        "upgrade_smoothing_requested": args.upgrade_smoothing,
        "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "script_sha256": {p.name: sha256_file(p) for p in code_paths if p.exists()},
        "manifest_sha256": sha256_file(args.manifest),
        "n_pairs": len(specs),
        "analyses": numbers,
        "limitations": (
            "Exploratory once-smoothed-PSD local maxima; no peak-strength cutoff; "
            "no biological/efficacy inference"
        ),
    }
    logs = (
        []
        if args.preflight_only
        else [output_base / ANALYSES[n][2] / "Sub/logs" / f"run_{run_tag}.json" for n in numbers]
    )
    try:
        for path in logs:
            write_json(path, run)
        sources = {}
        for spec in specs:
            for sid in (spec.first_session_id, spec.second_session_id):
                sources[sid] = source_fingerprints(spec, sid, DEFAULT_INPUT_ROOT)
        run["input_audit"] = {
            "source_files": sum(len(x) for x in sources.values()),
            "sessions": len(sources),
            "missing_by_session": {
                sid: sorted(EXPECTED_MISSING_SETS[sid])
                for sid in sources
                if sid in EXPECTED_MISSING_SETS
            },
            "sources": sources,
        }
        if args.preflight_only:
            print(
                json.dumps(
                    {
                        "status": "preflight_passed",
                        "pairs": len(specs),
                        "sessions": len(sources),
                        "source_files": run["input_audit"]["source_files"],
                        "config_sha256": config_hash(),
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        rows: dict[int, list[dict[str, Any]]] = {n: [] for n in numbers}
        cache_records = []
        for index, spec in enumerate(specs, 1):
            for sid in (spec.first_session_id, spec.second_session_id):
                expected_path = cache_file(DEFAULT_CACHE_ROOT, spec, sid)
                previous_hash = sha256_file(expected_path) if expected_path.exists() else None
                path, created = prepare_cache(
                    spec,
                    sid,
                    DEFAULT_INPUT_ROOT,
                    DEFAULT_CACHE_ROOT,
                    read_only=args.figures_only,
                    fingerprints=sources[sid],
                    upgrade_smoothing=args.upgrade_smoothing,
                )
                before_hash = sha256_file(path)
                session_rows = rows_from_cache(path)
                for n in numbers:
                    rows[n].extend(session_rows[n])
                cache_records.append(
                    {
                        "path": str(path),
                        "created": created,
                        "sha256": before_hash,
                        "upgraded_smoothing": not created and previous_hash != before_hash,
                        "previous_sha256": previous_hash,
                        "raw_payload_sha256": raw_cache_fingerprint(path),
                    }
                )
            logging.info("Cache pair %d/%d ready", index, len(specs))
        run["cache"] = cache_records
        run["validation"] = {}
        for n in numbers:
            root = output_base / ANALYSES[n][2]
            table_root = root / "Sub/tables"
            table_root.mkdir(parents=True, exist_ok=True)
            stats = validate_rows(rows[n], n, len(specs) * 2)
            frame = pd.DataFrame(
                [{k: v for k, v in row.items() if k not in SPECTRAL_ROW_KEYS} for row in rows[n]]
            )
            table_path = table_root / f"No{n}_IAF_Estimates.csv"
            frame.to_csv(table_path, index=False)
            restored = pd.read_csv(table_path)
            if len(restored) != len(frame) or not np.allclose(
                restored.frequency_hz, frame.frequency_hz, equal_nan=True
            ):
                raise AssertionError("Estimate CSV readback mismatch")
            frame.groupby(["product", "condition", "quality"]).size().rename(
                "count"
            ).reset_index().to_csv(table_root / f"No{n}_PeakAvailability.csv", index=False)
            pd.DataFrame([asdict(s) for s in specs]).to_csv(
                table_root / "ParticipantManifest.csv", index=False
            )
            stats.update(table=str(table_path), table_sha256=sha256_file(table_path))
            if not args.compute_only:
                from phase4_iaf_figures import FIGURE_CONFIG
                from PIL import Image

                run["figure_config"] = FIGURE_CONFIG
                figures = render_analysis(rows[n], specs, root, n)
                if len(figures) != len(specs):
                    raise AssertionError("One figure per pair required")
                for figure in figures:
                    with Image.open(figure["path"]) as image:
                        if image.size != (4860, 1800):
                            raise AssertionError("PNG dimensions differ from approved design")
                        image.verify()
                stats.update(figures=figures, png_readback="all decoded,4860x1800")
            run["validation"][str(n)] = stats
            logging.info(
                "No%d validated: %s", n, {k: v for k, v in stats.items() if k != "figures"}
            )
        for item in cache_records:
            if sha256_file(Path(item["path"])) != item["sha256"]:
                raise AssertionError("Rendering/estimation modified the spectral cache")
        run.update(
            status="complete",
            finished_utc=datetime.now(UTC).isoformat(),
            cache_unchanged_after_render=True,
        )
        for path in logs:
            write_json(path, run)
        return 0
    except Exception as error:
        run.update(
            status="failed",
            error=f"{type(error).__name__}: {error}",
            finished_utc=datetime.now(UTC).isoformat(),
        )
        for path in logs:
            if path.parent.is_dir():
                try:
                    write_json(path, run)
                except OSError:
                    logging.exception("Could not persist failure at authorized destination")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
