#!/usr/bin/env python3
"""Phase 4 No2_sub: Set-1-normalised occipital-alpha PSD change."""

from __future__ import annotations

import sys

import Phase4_No1_sub_FmThetaChange as engine
from phase4_band_variant_config import configure_change_engine
from Phase4_No2_OccipitalAlpha import engine as parent_engine


def configure_oz() -> None:
    configure_change_engine(
        engine,
        parent_engine,
        analysis_stem="No2_sub_OccipitalAlphaChange",
        focus_channel="Oz",
        script_version="phase4-no2-sub-occipital-alpha-change-2026-10-25.1",
        alternate_group_exclusions={"VRohtoPremium": {"125-225"}},
        alternate_group_suffix="ExcludePair125-225",
    )


def configure_pz() -> None:
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


configure_oz()


def main() -> int:
    configure_oz()
    status = engine.main()
    if status == 0 and "--production-batch" in sys.argv and "--all" in sys.argv:
        configure_pz()
        status = engine.main()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
