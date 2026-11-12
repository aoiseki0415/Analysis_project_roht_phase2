#!/usr/bin/env python3
"""Phase 4 No10: all-channel 8–10 Hz PSD, with Fz as the focus channel.

Run this entry point in its own Python process: the shared No1 engine is
configured in memory, without changing the established No1–9 source files.
"""

from __future__ import annotations

import Phase4_No1_FmTheta as engine
from phase4_band_variant_config import configure_band_engine
from phase4_no10_cache_guard import install_cache_guard

configure_band_engine(
    engine,
    analysis_stem="No10_FzLowAlpha",
    cache_file_tag="FzLowAlpha",
    focus_channel="Fz",
    frequencies_hz=(8, 9, 10),
    script_version="20261112_lowalpha_8to10_v2",
    cache_version="20261112_lowalpha_8to10_cache_v2",
    ccube_color="#637B22",
    ccube_quantification_color="#8B9D58",
    vrohto_color="#91A63D",
    vrohto_quantification_color="#ACBC6E",
)
install_cache_guard(engine)


if __name__ == "__main__":
    raise SystemExit(engine.main())
