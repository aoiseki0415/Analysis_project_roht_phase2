#!/usr/bin/env python3
"""Phase 4 No2_add: Oz 1-30 Hz Grand-average time-frequency maps."""

from __future__ import annotations

import numpy as np
import Phase4_No1_add_FzTimeFrequencyMap as engine
from phase4_band_variant_config import configure_tfm_engine

configure_tfm_engine(
    engine,
    analysis_stem="No2_add_OzTimeFrequencyMap",
    cache_file_tag="OzTFM",
    focus_channel="Oz",
    script_version="phase4-no2-add-oz-tfm-2026-10-04.2",
    cache_version="phase4-no2-add-oz-tfm-2026-10-04.1",
)

# Display-only scales. The verified Oz TFM cache remains unchanged.
engine.ABSOLUTE_PSD_COLOR_LIMIT = 20.0
engine.ABSOLUTE_PSD_COLOR_TICKS = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
engine.DIFFERENCE_COLOR_LIMIT = 15.0
engine.DIFFERENCE_COLOR_TICKS = np.array([-15.0, -10.0, -5.0, 0.0, 5.0, 10.0, 15.0])


if __name__ == "__main__":
    raise SystemExit(engine.main())
