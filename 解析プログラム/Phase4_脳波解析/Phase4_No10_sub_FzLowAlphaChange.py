#!/usr/bin/env python3
"""Phase 4 No10_sub: session/channel-specific Set-1 low-alpha PSD change.

Read the No10 cache, reapply both exclusion masks, and use unsmoothed values
for baselines, quantification and topography. No additional PSD cache is made.
"""

from __future__ import annotations

import sys

import Phase4_No1_sub_FmThetaChange as engine
from phase4_band_variant_config import configure_change_engine
from Phase4_No10_FzLowAlpha import engine as parent_engine
from phase4_no10_sub_sensitivity import sensitivity_main

configure_change_engine(
    engine,
    parent_engine,
    analysis_stem="No10_sub_FzLowAlphaChange",
    focus_channel="Fz",
    script_version="20261116_lowalpha_change_quality_review_no_pair_exclusion_v3",
)


def main() -> int:
    if "--sensitivity-only" in sys.argv[1:]:
        return sensitivity_main(engine)
    return engine.main()


if __name__ == "__main__":
    raise SystemExit(main())
