#!/usr/bin/env python3
"""Phase 4 No2_sub: Set-1-normalised occipital-alpha PSD change."""

from __future__ import annotations

import Phase4_No1_sub_FmThetaChange as engine
from phase4_band_variant_config import configure_change_engine
from Phase4_No2_OccipitalAlpha import engine as parent_engine

configure_change_engine(
    engine,
    parent_engine,
    analysis_stem="No2_sub_OccipitalAlphaChange",
    focus_channel="Oz",
    script_version="phase4-no2-sub-occipital-alpha-change-2026-10-04.1",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
