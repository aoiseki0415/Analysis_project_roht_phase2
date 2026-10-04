#!/usr/bin/env python3
"""Configure the validated Phase 4 No1 engines for fixed band variants."""

from __future__ import annotations

from pathlib import Path
from types import ModuleType

import numpy as np


def _product_map(
    ccube_color: str,
    ccube_quantification_color: str,
    vrohto_color: str,
    vrohto_quantification_color: str,
) -> dict[str, tuple[str, str, str, str]]:
    ccube = ("CCube", "C Cube", ccube_color, ccube_quantification_color)
    vrohto = (
        "VRohtoPremium",
        "V Rohto Premium",
        vrohto_color,
        vrohto_quantification_color,
    )
    return {
        "ccube": ccube,
        "c_cube": ccube,
        "cキューブ": ccube,
        "vrohtopremium": vrohto,
        "v_rohto_premium": vrohto,
        "vロート": vrohto,
        "vロートプレミアム": vrohto,
    }


def configure_band_engine(
    engine: ModuleType,
    *,
    analysis_stem: str,
    cache_file_tag: str,
    focus_channel: str,
    frequencies_hz: tuple[int, ...],
    script_version: str,
    cache_version: str,
    ccube_color: str,
    ccube_quantification_color: str,
    vrohto_color: str,
    vrohto_quantification_color: str,
) -> ModuleType:
    """Apply one complete, isolated band-analysis configuration."""
    phase4_cache_root = Path(engine.DEFAULT_CACHE_ROOT).parents[1]
    engine.ANALYSIS_STEM = analysis_stem
    engine.CACHE_FILE_TAG = cache_file_tag
    engine.FOCUS_CHANNEL = focus_channel
    engine.SCRIPT_VERSION = script_version
    engine.CACHE_CONFIGURATION_VERSION = cache_version
    engine.FMIN_HZ = float(min(frequencies_hz))
    engine.FMAX_HZ = float(max(frequencies_hz))
    engine.INCLUDED_FREQUENCIES_HZ = np.asarray(frequencies_hz, dtype=float)
    engine.DEFAULT_CACHE_ROOT = phase4_cache_root / analysis_stem / "PSDTimeSeries"
    engine.PRODUCTS = _product_map(
        ccube_color,
        ccube_quantification_color,
        vrohto_color,
        vrohto_quantification_color,
    )
    return engine


def configure_change_engine(
    engine: ModuleType,
    parent_engine: ModuleType,
    *,
    analysis_stem: str,
    focus_channel: str,
    script_version: str,
) -> ModuleType:
    """Bind the Set-1 change engine to one configured parent PSD engine."""
    engine.no1 = parent_engine
    engine.ANALYSIS_STEM = analysis_stem
    engine.FOCUS_CHANNEL = focus_channel
    engine.SCRIPT_VERSION = script_version
    engine.N_SETS = parent_engine.N_SETS
    engine.PROGRESS_POINTS = parent_engine.GROUP_PROGRESS_POINTS_PER_SET
    engine.SMOOTHING_SECONDS = parent_engine.TIMECOURSE_SMOOTHING_SECONDS
    engine.DEFAULT_CACHE_ROOT = parent_engine.DEFAULT_CACHE_ROOT
    engine.DEFAULT_OUTPUT_ROOT = parent_engine.DEFAULT_OUTPUT_ROOT
    return engine


def configure_tfm_engine(
    engine: ModuleType,
    *,
    analysis_stem: str,
    cache_file_tag: str,
    focus_channel: str,
    script_version: str,
    cache_version: str,
) -> ModuleType:
    """Apply one complete, isolated representative-channel TFM configuration."""
    phase4_cache_root = Path(engine.DEFAULT_CACHE_ROOT).parents[1]
    engine.ANALYSIS_STEM = analysis_stem
    engine.CACHE_FILE_TAG = cache_file_tag
    engine.FOCUS_CHANNEL = focus_channel
    engine.FOCUS_CHANNEL_INDEX = engine.EXPECTED_CHANNEL_NAMES.index(focus_channel)
    engine.SCRIPT_VERSION = script_version
    engine.CACHE_CONFIGURATION_VERSION = cache_version
    engine.DEFAULT_CACHE_ROOT = phase4_cache_root / analysis_stem / "TimeFrequencySeries"
    return engine
