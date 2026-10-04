#!/usr/bin/env python3
"""Phase 4 No3: compute and analyse all-channel 1-3 Hz PSD time series."""

from __future__ import annotations

import Phase4_No1_FmTheta as engine
from phase4_band_variant_config import configure_band_engine

configure_band_engine(
    engine,
    analysis_stem="No3_FrontalDelta",
    cache_file_tag="FrontalDelta",
    focus_channel="Fz",
    frequencies_hz=(1, 2, 3),
    script_version="phase4-no3-frontal-delta-2026-10-04.1",
    cache_version="phase4-no3-frontal-delta-2026-10-04.1",
    ccube_color="#8F7300",
    ccube_quantification_color="#A58F33",
    vrohto_color="#C29A00",
    vrohto_quantification_color="#CEAE33",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
