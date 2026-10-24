#!/usr/bin/env python3
"""Phase 4 No2-2_sub: Pz-based occipital-alpha PSD change."""

from __future__ import annotations

import Phase4_No1_sub_FmThetaChange as engine
from phase4_band_variant_config import configure_change_engine
from Phase4_No2_OccipitalAlpha import engine as parent_engine

configure_change_engine(
    engine,
    parent_engine,
    analysis_stem="No2-2_sub_OccipitalAlphaChange_Pz",
    focus_channel="Pz",
    script_version="phase4-no2-2-sub-occipital-alpha-change-pz-2026-10-25.1",
    include_topography=False,
    alternate_group_exclusions={"VRohtoPremium": {"125-225"}},
    alternate_group_suffix="ExcludePair125-225",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
