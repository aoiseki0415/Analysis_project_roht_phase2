#!/usr/bin/env python3
"""Phase 4 No2_add: Oz 1-30 Hz Grand-average time-frequency maps."""

from __future__ import annotations

import Phase4_No1_add_FzTimeFrequencyMap as engine
from phase4_band_variant_config import configure_tfm_engine

configure_tfm_engine(
    engine,
    analysis_stem="No2_add_OzTimeFrequencyMap",
    cache_file_tag="OzTFM",
    focus_channel="Oz",
    script_version="phase4-no2-add-oz-tfm-2026-10-04.1",
    cache_version="phase4-no2-add-oz-tfm-2026-10-04.1",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
