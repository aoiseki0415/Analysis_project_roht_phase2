#!/usr/bin/env python3
"""Phase 4 No2: compute and analyse all-channel 8-15 Hz PSD time series."""

from __future__ import annotations

import Phase4_No1_FmTheta as engine
from phase4_band_variant_config import configure_band_engine

configure_band_engine(
    engine,
    analysis_stem="No2_OccipitalAlpha",
    cache_file_tag="OccipitalAlpha",
    focus_channel="Oz",
    frequencies_hz=tuple(range(8, 16)),
    script_version="phase4-no2-occipital-alpha-2026-10-04.1",
    cache_version="phase4-no2-occipital-alpha-2026-10-04.1",
    ccube_color="#C23B8A",
    ccube_quantification_color="#CE62A1",
    vrohto_color="#E36A8D",
    vrohto_quantification_color="#E988A4",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
