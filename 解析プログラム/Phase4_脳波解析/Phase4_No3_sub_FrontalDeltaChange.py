#!/usr/bin/env python3
"""Phase 4 No3_sub: Set-1-normalised frontal-delta PSD change."""

from __future__ import annotations

import Phase4_No1_sub_FmThetaChange as engine
from phase4_band_variant_config import configure_change_engine
from Phase4_No3_FrontalDelta import engine as parent_engine

configure_change_engine(
    engine,
    parent_engine,
    analysis_stem="No3_sub_FrontalDeltaChange",
    focus_channel="Fz",
    script_version="phase4-no3-sub-frontal-delta-change-2026-10-05.5",
)

# Keep the No1_sub/No2_sub bracket and n.s. settings, but enlarge and lower
# significant asterisks for the No3_sub Set-quantification figure only.
engine.SIGNIFICANCE_STAR_FACTOR_OVERRIDE = 1.11
engine.SIGNIFICANCE_STAR_FONTSIZE_OVERRIDE = 40.0


if __name__ == "__main__":
    raise SystemExit(engine.main())
