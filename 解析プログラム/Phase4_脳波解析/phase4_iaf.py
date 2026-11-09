"""Common, reproducible Phase 4 No8--11 individual alpha peak pipeline.

Only Phase 1 ICA-processed continuous EEG is used. A shared spectral cache
separates the expensive FFT from peak estimation and individual-only rendering.
See docs/Phase4_No8-11_共有用解析仕様.md for decisions and limitations.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
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
    preflight_inputs,
    session_file_prefix,
    validate_participant_specs,
)
from scipy.signal import find_peaks, get_window, periodogram, savgol_filter

VERSION = "phase4-iaf-2026-11-09.1"
CHANNELS = ("Pz", "Fz")
SFREQ = 256.0
SEGMENT_SAMPLES = 2560
STEP_SAMPLES = 1280
FREQUENCIES = np.arange(10, 401, dtype=float) / 10
ANALYSES = {
    8: ("Pz", "setwise", "No8_PzSetwiseIAF"),
    9: ("Pz", "time_resolved", "No9_PzTimeResolvedIAF"),
    10: ("Fz", "setwise", "No10_FzSetwiseIAF"),
    11: ("Fz", "time_resolved", "No11_FzTimeResolvedIAF"),
}
DEFAULT_CACHE_ROOT = (
    DEFAULT_INPUT_ROOT.parents[1] / "Phase4_脳波解析/No8-11_PzFzIAF/SpectralSegments"
)
CONFIG = {
    "version": VERSION,
    "channels": CHANNELS,
    "sfreq_hz": SFREQ,
    "segment_seconds": 10,
    "step_seconds": 5,
    "window": "periodic Hann",
    "nfft": 2560,
    "detrend": "constant",
    "scaling": "density",
    "sidedness": "one-sided",
    "spectrum_unit": "µV²/Hz",
    "spectral_cache_hz": [1, 40],
    "artifact_rule": "reject any 10s segment containing any Phase1 excluded sample",
    "alpha_band_inclusive_hz": [8, 15],
    "background": "linear least squares log10(power) ~ log10(f), 1-40Hz",
    "spectral_smoothing": {"method": "Savitzky-Golay", "bins": 27, "degree": 5},
    "peak_z_minimum": 1.75,
    "peak_z_ddof": 1,
    "peak_z_reference": "1 <= abs(f-fpeak) <= 5 Hz, plus peak itself",
    "multiple_peak_flag_height_fraction": 0.8,
    "multiple_peak_flag_separation_hz": 0.5,
    "setwise_minimum_unique_seconds": 60,
    "moving_nominal_seconds": 60,
    "moving_minimum_valid_segments": 6,
    "moving_possible_segments": 11,
    "moving_minimum_unique_seconds": 35,
    "time_smoothing": "none",
    "resampling": "none; time coordinate converted to progress only",
    "minimum_data_rule_source": "project QC choice, not a universal literature rule",
}


def config_json() -> str:
    return json.dumps(CONFIG, sort_keys=True, ensure_ascii=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_periodograms(
    data: np.ndarray, mask: np.ndarray, sfreq: float = SFREQ
) -> dict[str, np.ndarray]:
    """10s Hann periodograms of volts, retaining positions across rejected gaps."""
    data = np.asarray(data, dtype=np.float64)
    mask = np.asarray(mask, dtype=bool)
    if sfreq != SFREQ:
        raise ValueError("IAF requires the verified 256 Hz Phase1 sampling rate")
    if data.ndim != 2 or data.shape[1] != 2 or mask.shape != (len(data),):
        raise ValueError("Expected two EEG channels and one time-aligned artifact mask")
    starts = np.arange(0, len(data) - SEGMENT_SAMPLES + 1, STEP_SAMPLES, dtype=int)
    spectra = np.full((len(starts), 2, len(FREQUENCIES)), np.nan)
    valid = np.zeros((len(starts), 2), dtype=bool)
    rejection_code = np.zeros((len(starts), 2), dtype=np.uint8)
    window = get_window("hann", SEGMENT_SAMPLES, fftbins=True)
    for index, start in enumerate(starts):
        stop = start + SEGMENT_SAMPLES
        if mask[start:stop].any():
            rejection_code[index, :] = 1
            continue
        for channel in range(2):
            segment = data[start:stop, channel]
            if not np.isfinite(segment).all():
                rejection_code[index, channel] = 2
                continue
            frequencies, power = periodogram(
                segment * 1e6,
                fs=sfreq,
                window=window,
                nfft=SEGMENT_SAMPLES,
                detrend="constant",
                return_onesided=True,
                scaling="density",
            )
            selected = power[10:401]
            if not np.allclose(frequencies[10:401], FREQUENCIES, atol=1e-12):
                raise RuntimeError("Unexpected spectral frequency grid")
            spectra[index, channel] = selected
            valid[index, channel] = True
    return {
        "freqs": FREQUENCIES.copy(),
        "psd": spectra,
        "starts": starts,
        "ends": starts + SEGMENT_SAMPLES,
        "valid": valid,
        "rejection_code": rejection_code,
    }


def corrected_spectrum(freqs: np.ndarray, power: np.ndarray) -> np.ndarray:
    log_frequency = np.log10(freqs)
    log_power = np.log10(power)
    background = np.polyval(np.polyfit(log_frequency, log_power, 1), log_frequency)
    return savgol_filter(log_power - background, 27, 5, mode="interp")


def select_peak(freqs: np.ndarray, mean_linear_psd: np.ndarray) -> dict[str, Any]:
    """Janssens-style spectral maximum plus peak-quality screening (adaptation)."""
    freqs = np.asarray(freqs, dtype=float)
    power = np.asarray(mean_linear_psd, dtype=float)
    result: dict[str, Any] = {
        "frequency_hz": np.nan,
        "candidate_hz": np.nan,
        "raw_band_max_hz": np.nan,
        "z_score": np.nan,
        "quality": "invalid_spectrum",
        "multiple_peaks": False,
        "n_candidates": 0,
    }
    if freqs.shape != FREQUENCIES.shape or not np.allclose(freqs, FREQUENCIES):
        raise ValueError("Expected 1-40 Hz at 0.1 Hz spacing")
    if power.shape != freqs.shape or not np.isfinite(power).all() or np.any(power <= 0):
        return result
    band = (freqs >= 8) & (freqs <= 15)
    result["raw_band_max_hz"] = float(freqs[np.flatnonzero(band)[np.argmax(power[band])]])
    residual = corrected_spectrum(freqs, power)
    result["quality"] = "no_local_peak"
    if np.ptp(residual) < 1e-10:
        return result
    candidates, _ = find_peaks(residual)
    candidates = candidates[band[candidates]]
    result["n_candidates"] = len(candidates)
    if len(candidates) == 0:
        return result
    peak = int(candidates[np.argmax(residual[candidates])])
    candidate = float(freqs[peak])
    result["candidate_hz"] = candidate
    distance = np.abs(freqs - candidate)
    reference = ((distance >= 1 - 1e-8) & (distance <= 5 + 1e-8)) | (distance < 1e-8)
    sample = residual[reference]
    deviation = float(np.std(sample, ddof=1))
    result["quality"] = "no_clear_peak"
    if deviation < 1e-10:
        return result
    z_score = float((residual[peak] - np.mean(sample)) / deviation)
    result["z_score"] = z_score
    result["multiple_peaks"] = bool(
        residual[peak] > 0
        and np.any(
            (np.abs(freqs[candidates] - candidate) >= 0.5 - 1e-8)
            & (residual[candidates] >= 0.8 * residual[peak])
        )
    )
    if z_score >= 1.75:
        result.update(frequency_hz=candidate, quality="ok")
    return result


def unique_coverage_seconds(starts: np.ndarray) -> float:
    """Union length of retained half-open 10s segments; overlaps counted once."""
    starts = np.sort(np.asarray(starts, dtype=int))
    if not len(starts):
        return 0.0
    covered = SEGMENT_SAMPLES
    previous_end = int(starts[0]) + SEGMENT_SAMPLES
    for start in starts[1:]:
        end = int(start) + SEGMENT_SAMPLES
        covered += max(0, end - max(int(start), previous_end))
        previous_end = max(end, previous_end)
    return covered / SFREQ


def estimate(
    spectra: np.ndarray, starts: np.ndarray, valid: np.ndarray, *, moving: bool
) -> dict[str, Any]:
    n_valid = int(np.sum(valid))
    usable_seconds = unique_coverage_seconds(starts[valid])
    enough = (n_valid >= 6 and usable_seconds >= 35) if moving else usable_seconds >= 60
    if enough:
        peak = select_peak(FREQUENCIES, np.mean(spectra[valid], axis=0))
    else:
        peak = select_peak(FREQUENCIES, np.full(len(FREQUENCIES), np.nan))
        peak["quality"] = "insufficient_data"
    return {
        **peak,
        "n_valid_segments": n_valid,
        "n_possible_segments": len(starts),
        "usable_seconds": usable_seconds,
    }


def source_fingerprints(spec: ParticipantSpec, sid: str, root: Path) -> list[dict[str, Any]]:
    records = []
    for number in range(1, 7):
        path = input_path(root, sid, number)
        if not path.exists():
            if number not in EXPECTED_MISSING_SETS.get(sid, set()):
                raise FileNotFoundError(path)
            continue
        stat = path.stat()
        records.append(
            {
                "set": number,
                "path": str(path),
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": sha256_file(path),
            }
        )
    return records


def cache_file(root: Path, spec: ParticipantSpec, sid: str) -> Path:
    return root / f"{session_file_prefix(spec, sid)}_PzFz_IAFSpectra.h5"


def session_metadata(spec: ParticipantSpec, sid: str) -> dict[str, Any]:
    return {
        "pair_id": spec.pair_id,
        "session_id": sid,
        "product": normalize_product(spec.product)[0],
        "condition": "Eye Drop" if sid == spec.drops_session_id else "Control",
    }


def prepare_cache(
    spec: ParticipantSpec, sid: str, input_root: Path, cache_root: Path, *, read_only: bool
) -> tuple[Path, bool]:
    path = cache_file(cache_root, spec, sid)
    fingerprints = source_fingerprints(spec, sid, input_root)
    fingerprint_json = json.dumps(fingerprints, sort_keys=True)
    metadata = session_metadata(spec, sid)
    if path.exists():
        with h5py.File(path, "r") as handle:
            expected = {**metadata, "config_json": config_json(), "sources_json": fingerprint_json}
            for name, value in expected.items():
                if handle.attrs.get(name) != value:
                    raise ValueError(f"Stale/mismatched cache {path}: {name}; no silent overwrite")
            if handle.attrs.get("complete") != 1:
                raise ValueError(f"Incomplete cache: {path}")
        return path, False
    if read_only:
        raise FileNotFoundError(f"--figures-only requires validated cache: {path}")
    cache_root.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial.h5")
    with h5py.File(temporary, "w") as target:
        target.attrs.update(metadata)
        target.attrs["config_json"] = config_json()
        target.attrs["config_sha256"] = hashlib.sha256(config_json().encode()).hexdigest()
        target.attrs["sources_json"] = fingerprint_json
        target.attrs["rejection_code_legend"] = "0=valid,1=Phase1_time_mask,2=nonfinite_channel"
        target.attrs["channel_names_json"] = json.dumps(CHANNELS)
        target.create_dataset("frequencies_hz", data=FREQUENCIES)
        for record in fingerprints:
            with h5py.File(record["path"], "r") as source:
                names = _decode_names(source["signal/channel_names"][:])
                # h5py fancy indices must ascend; explicitly stack in the declared Pz,Fz order.
                values = np.column_stack(
                    [source["signal/data"][:, names.index(ch)] for ch in CHANNELS]
                )
                mask = source["qc/ica_training_excluded_mask"][:].astype(bool)
                spectral = compute_periodograms(values, mask)
                group = target.create_group(f"Set{record['set']}")
                group.attrs["duration_seconds"] = len(values) / SFREQ
                group.attrs["n_samples"] = len(values)
                group.attrs["artifact_sample_fraction"] = float(np.mean(mask))
                excluded = source["qc/ica_channel_excluded_mask"][:].astype(bool)
                group.create_dataset(
                    "ica_channel_excluded", data=[excluded[names.index(ch)] for ch in CHANNELS]
                )
                for name in ("psd", "starts", "ends", "valid", "rejection_code"):
                    group.create_dataset(
                        name, data=spectral[name], compression="gzip", shuffle=True
                    )
        target.attrs["complete"] = 1
    os.replace(temporary, path)
    with h5py.File(path, "r") as check:
        for record in fingerprints:
            group = check[f"Set{record['set']}"]
            psd, valid = group["psd"][:], group["valid"][:]
            if psd.shape != (len(group["starts"]), 2, len(FREQUENCIES)):
                raise AssertionError("Spectral cache shape mismatch on readback")
            if not np.isfinite(psd[valid]).all() or not np.isnan(psd[~valid]).all():
                raise AssertionError("Spectral cache valid/invalid mask mismatch on readback")
    return path, True


def rows_from_cache(path: Path) -> dict[int, list[dict[str, Any]]]:
    rows: dict[int, list[dict[str, Any]]] = {number: [] for number in ANALYSES}
    with h5py.File(path, "r") as handle:
        metadata = {
            key: str(handle.attrs[key]) for key in ("pair_id", "session_id", "condition", "product")
        }
        for number in range(1, 7):
            set_key = f"Set{number}"
            if set_key not in handle:
                for analysis, (channel, _, _) in ANALYSES.items():
                    empty = estimate(
                        np.empty((0, len(FREQUENCIES))),
                        np.array([], int),
                        np.array([], bool),
                        moving=False,
                    )
                    rows[analysis].append(
                        {
                            **metadata,
                            "set_number": number,
                            "channel": channel,
                            **empty,
                            "quality": "missing_set",
                            "duration_seconds": np.nan,
                            "center_seconds": np.nan,
                            "progress": np.nan,
                            "ica_channel_excluded": False,
                        }
                    )
                continue
            group = handle[set_key]
            spectra = group["psd"][:]
            starts = group["starts"][:]
            valid = group["valid"][:]
            duration = float(group.attrs["duration_seconds"])
            n_samples = int(group.attrs["n_samples"])
            excluded = group["ica_channel_excluded"][:]
            for ch_index, channel in enumerate(CHANNELS):
                base = {
                    **metadata,
                    "set_number": number,
                    "channel": channel,
                    "duration_seconds": duration,
                    "ica_channel_excluded": bool(excluded[ch_index]),
                }
                set_analysis = 8 if channel == "Pz" else 10
                moving_analysis = set_analysis + 1
                rows[set_analysis].append(
                    {
                        **base,
                        **estimate(spectra[:, ch_index], starts, valid[:, ch_index], moving=False),
                        "center_seconds": np.nan,
                        "progress": np.nan,
                    }
                )
                if n_samples < 60 * SFREQ:
                    rows[moving_analysis].append(
                        {
                            **base,
                            **estimate(
                                np.empty((0, len(FREQUENCIES))),
                                np.array([], int),
                                np.array([], bool),
                                moving=True,
                            ),
                            "center_seconds": np.nan,
                            "progress": np.nan,
                        }
                    )
                for start in range(0, n_samples - int(60 * SFREQ) + 1, STEP_SAMPLES):
                    selected = (starts >= start) & (starts + SEGMENT_SAMPLES <= start + 60 * SFREQ)
                    if np.sum(selected) != 11:
                        raise RuntimeError("A full 60s window must contain 11 candidate segments")
                    result = estimate(
                        spectra[selected, ch_index],
                        starts[selected],
                        valid[selected, ch_index],
                        moving=True,
                    )
                    center = start / SFREQ + 30
                    rows[moving_analysis].append(
                        {
                            **base,
                            **result,
                            "center_seconds": center,
                            "progress": 100 * (number - 1) + 100 * center / duration,
                        }
                    )
    return rows


def validate_rows(rows: list[dict[str, Any]], number: int, n_sessions: int) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    if number in (8, 10) and len(frame) != n_sessions * 6:
        raise AssertionError("Setwise table must preserve six positions per session")
    finite = np.isfinite(frame.frequency_hz)
    if not (frame.loc[finite, "quality"] == "ok").all():
        raise AssertionError("Rejected peaks must be NaN")
    values = frame.loc[finite, "frequency_hz"].to_numpy()
    if np.any((values < 8) | (values > 15)) or not np.allclose(values * 10, np.round(values * 10)):
        raise AssertionError("Peak frequency is outside 8-15Hz / 0.1Hz grid")
    if frame.duplicated(["session_id", "set_number", "center_seconds"]).any():
        raise AssertionError("Repeated estimates")
    return {
        "rows": len(frame),
        "valid_estimates": int(finite.sum()),
        "quality_counts": dict(Counter(frame.quality)),
        "multiple_peak_flags": int(frame.multiple_peaks.sum()),
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


def render_spectral_qc(cache_paths: list[Path], output: Path, channel: str) -> list[Path]:
    """Six Set spectra per session; raw PSD and chosen/rejected candidate for audit."""
    import matplotlib.pyplot as plt
    from phase4_iaf_figures import _require_arial

    _require_arial()
    files = []
    ch_index = CHANNELS.index(channel)
    with plt.rc_context(
        {"font.family": "Arial", "axes.spines.top": False, "axes.spines.right": False}
    ):
        for path in cache_paths:
            figure, axes = plt.subplots(2, 3, figsize=(18, 9))
            with h5py.File(path, "r") as handle:
                for number, axis in enumerate(axes.ravel(), 1):
                    key = f"Set{number}"
                    axis.set_title(f"Set {number}", fontsize=20)
                    axis.set_xlim(5, 20)
                    axis.tick_params(labelsize=14)
                    axis.set_xlabel("Frequency (Hz)", fontsize=17)
                    axis.set_ylabel("PSD (µV²/Hz)", fontsize=17)
                    if key not in handle:
                        axis.text(0.5, 0.5, "Missing Set", transform=axis.transAxes, ha="center")
                        continue
                    group = handle[key]
                    valid = group["valid"][:, ch_index]
                    if not valid.any():
                        axis.text(
                            0.5,
                            0.5,
                            "No valid 10 s segments",
                            transform=axis.transAxes,
                            ha="center",
                        )
                        continue
                    spectrum = np.mean(group["psd"][:, ch_index][valid], axis=0)
                    result = estimate(
                        group["psd"][:, ch_index], group["starts"][:], valid, moving=False
                    )
                    axis.semilogy(FREQUENCIES, spectrum, linewidth=1.8, color="#404040")
                    if np.isfinite(spectrum).all() and np.all(spectrum > 0):
                        secondary = axis.twinx()
                        secondary.plot(
                            FREQUENCIES,
                            corrected_spectrum(FREQUENCIES, spectrum),
                            color="#008F95",
                            alpha=0.7,
                            linewidth=1.2,
                        )
                        secondary.set_ylabel("Corrected log PSD", fontsize=11, color="#008F95")
                        secondary.tick_params(labelsize=10, colors="#008F95")
                    axis.axvspan(8, 15, alpha=0.08, color="#008F95")
                    if np.isfinite(result["candidate_hz"]):
                        axis.axvline(
                            result["candidate_hz"],
                            color="#008F95" if result["quality"] == "ok" else "#A04040",
                            linestyle="--",
                        )
                    axis.set_title(f"Set {number}: {result['quality']}", fontsize=17)
                figure.suptitle(
                    f"{channel}: {handle.attrs['condition']} — {handle.attrs['session_id']}",
                    fontsize=22,
                )
            figure.tight_layout()
            destination = output / f"{path.stem}_{channel}_SetSpectra.png"
            destination.parent.mkdir(parents=True, exist_ok=True)
            figure.savefig(destination, dpi=130)
            plt.close(figure)
            files.append(destination)
    return files


def render_moving_qc(
    rows: list[dict[str, Any]], cache_paths: list[Path], output: Path, channel: str
) -> list[Path]:
    """Deterministic real-window examples: accepted/weak/multiple/data-limited."""
    import matplotlib.pyplot as plt

    frame = pd.DataFrame(rows)
    selections = []
    for label, selected in (
        ("accepted lowest z", frame[frame.quality.eq("ok")].sort_values("z_score")),
        (
            "accepted highest z",
            frame[frame.quality.eq("ok")].sort_values("z_score", ascending=False),
        ),
        ("multiple peaks", frame[frame.quality.eq("ok") & frame.multiple_peaks]),
        ("weak peak", frame[frame.quality.eq("no_clear_peak")]),
        ("insufficient data", frame[frame.quality.eq("insufficient_data")]),
        ("no local peak", frame[frame.quality.eq("no_local_peak")]),
    ):
        if len(selected):
            selections.append((label, selected.iloc[0]))
    if not selections:
        return []
    by_session = {}
    for path in cache_paths:
        with h5py.File(path, "r") as handle:
            by_session[str(handle.attrs["session_id"])] = path
    ch_index = CHANNELS.index(channel)
    with plt.rc_context({"font.family": "Arial"}):
        fig, axes = plt.subplots(
            len(selections), 2, figsize=(15, 3.3 * len(selections)), squeeze=False
        )
        for i, (label, row) in enumerate(selections):
            with h5py.File(by_session[str(row.session_id)], "r") as handle:
                group = handle[f"Set{int(row.set_number)}"]
                starts = group["starts"][:]
                start = (row.center_seconds - 30) * SFREQ
                chosen = (starts >= start) & (starts + SEGMENT_SAMPLES <= start + 60 * SFREQ)
                chosen &= group["valid"][:, ch_index]
                power = np.mean(group["psd"][:, ch_index][chosen], axis=0) if chosen.any() else None
            for ax in axes[i]:
                ax.set_xlim(5, 20)
                ax.tick_params(labelsize=13)
                ax.set_xlabel("Frequency (Hz)", fontsize=16)
                ax.axvspan(8, 15, color="#008F95", alpha=0.08)
            if power is not None and np.all(power > 0):
                axes[i, 0].semilogy(FREQUENCIES, power, color="#404040", linewidth=2)
                axes[i, 1].plot(
                    FREQUENCIES,
                    corrected_spectrum(FREQUENCIES, power),
                    color="#008F95",
                    linewidth=2,
                )
            if np.isfinite(row.candidate_hz):
                for ax in axes[i]:
                    ax.axvline(row.candidate_hz, linestyle="--", color="#A04040")
            axes[i, 0].set_ylabel("PSD (µV²/Hz)", fontsize=16)
            axes[i, 1].set_ylabel("Corrected log PSD", fontsize=16)
            axes[i, 0].set_title(
                f"{label}: ID{row.session_id} Set{row.set_number}, center {row.center_seconds:g}s",
                fontsize=15,
            )
            axes[i, 1].set_title(
                f"{row.quality}, z={row.z_score:.2f}, valid={row.n_valid_segments}/11", fontsize=15
            )
        fig.tight_layout()
        path = output / f"{channel}_MovingWindowExamples.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return [path]


def main(argv: list[str] | None = None, *, fixed_analysis: int | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--production-batch", action="store_true")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--all", action="store_true")
    mode.add_argument("--compute-only", action="store_true")
    mode.add_argument("--figures-only", action="store_true")
    if fixed_analysis is None:
        parser.add_argument(
            "--analysis", type=int, choices=list(ANALYSES), nargs="+", default=list(ANALYSES)
        )
    args = parser.parse_args(argv)
    numbers = [fixed_analysis] if fixed_analysis else args.analysis
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    specs = load_manifest(args.manifest)
    specs = [
        ParticipantSpec(
            s.first_session_id,
            s.second_session_id,
            s.drops_session_id,
            normalize_product(s.product)[0],
        )
        for s in specs
    ]
    validate_participant_specs(specs, production_batch=args.production_batch)
    # Roots are deliberately not CLI-overridable: never silently write elsewhere.
    output_base = DEFAULT_OUTPUT_ROOT / "Phase4_脳波解析"
    run_time = datetime.now(UTC).isoformat()
    code_paths = [Path(__file__), Path(__file__).with_name("phase4_iaf_figures.py")]
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    run = {
        "started_utc": run_time,
        "config": CONFIG,
        "git_head": git_head,
        "script_sha256": {p.name: sha256_file(p) for p in code_paths},
        "manifest_sha256": sha256_file(args.manifest),
        "n_pairs": len(specs),
        "mode": "compute-only"
        if args.compute_only
        else "figures-only"
        if args.figures_only
        else "all",
        "analyses": numbers,
        "status": "running",
    }
    run_tag = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    log_paths = [output_base / ANALYSES[n][2] / "Sub/logs" / f"run_{run_tag}.json" for n in numbers]
    try:
        logging.info("Preflight: verifying Phase1 input files and known missing Sets")
        audit = preflight_inputs(specs, DEFAULT_INPUT_ROOT)
        run["input_audit"] = audit
        # Check authorized destinations before expensive computation.
        for log_path in log_paths:
            write_json(log_path, run)
        paths = []
        created = 0
        rows = {n: [] for n in ANALYSES}
        for index, spec in enumerate(specs, 1):
            for sid in (spec.first_session_id, spec.second_session_id):
                path, new = prepare_cache(
                    spec, sid, DEFAULT_INPUT_ROOT, DEFAULT_CACHE_ROOT, read_only=args.figures_only
                )
                paths.append(path)
                created += int(new)
                if not args.compute_only:
                    session_rows = rows_from_cache(path)
                    for n in numbers:
                        rows[n].extend(session_rows[n])
            logging.info("Cache/estimates pair %d/%d complete", index, len(specs))
        run.update(
            cache_created=created,
            cache_reused=len(paths) - created,
            cache_files=[str(p) for p in paths],
        )
        if not args.compute_only:
            from phase4_iaf_figures import render_analysis
            from PIL import Image

            run["validation"] = {}
            for n in numbers:
                root = output_base / ANALYSES[n][2]
                table_dir = root / "Sub/tables"
                table_dir.mkdir(parents=True, exist_ok=True)
                stats = validate_rows(rows[n], n, len(specs) * 2)
                table = table_dir / f"No{n}_IAF_Estimates.csv"
                frame = pd.DataFrame(rows[n])
                frame.to_csv(table, index=False)
                restored = pd.read_csv(table)
                if len(restored) != len(frame) or not np.allclose(
                    restored.frequency_hz, frame.frequency_hz, equal_nan=True
                ):
                    raise AssertionError("IAF CSV readback mismatch")
                summary = (
                    frame.groupby(["product", "condition", "quality"])
                    .size()
                    .rename("count")
                    .reset_index()
                )
                summary.to_csv(table_dir / f"No{n}_PeakAvailability.csv", index=False)
                pd.DataFrame([asdict(s) for s in specs]).to_csv(
                    table_dir / "ParticipantManifest.csv", index=False
                )
                figures = render_analysis(rows[n], specs, root, n)
                if len(figures) != len(specs):
                    raise AssertionError("One figure per participant pair required")
                qc_figures = []
                if n in (8, 10):
                    qc_figures = render_spectral_qc(
                        paths, root / "Sub/QualityCheck/SetSpectra", ANALYSES[n][0]
                    )
                else:
                    qc_figures = render_moving_qc(
                        rows[n], paths, root / "Sub/QualityCheck", ANALYSES[n][0]
                    )
                for image_path in figures + qc_figures:
                    with Image.open(image_path) as image:
                        image.verify()
                stats.update(
                    figures=[str(p) for p in figures],
                    qc_figures=[str(p) for p in qc_figures],
                    table=str(table),
                    table_sha256=sha256_file(table),
                    png_readback="all files decoded",
                )
                run["validation"][str(n)] = stats
                logging.info(
                    "No%d rendered and readback-verified: %s",
                    n,
                    {k: v for k, v in stats.items() if k not in ("figures", "qc_figures")},
                )
        run.update(status="complete", finished_utc=datetime.now(UTC).isoformat())
        for path in log_paths:
            write_json(path, run)
        logging.info("IAF run complete; %s", [str(p) for p in log_paths])
        return 0
    except Exception as error:
        run.update(status="failed", error=f"{type(error).__name__}: {error}")
        for path in log_paths:
            if path.parent.is_dir():
                try:
                    write_json(path, run)
                except OSError:
                    logging.exception("Could not persist failure to authorized log path")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
