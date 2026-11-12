#!/usr/bin/env python3
"""Phase 4 No10_sub: session/channel-specific Set-1 low-alpha PSD change.

Read the No10 cache, reapply both exclusion masks, and use unsmoothed values
for baselines, quantification and topography. No additional PSD cache is made.
"""

from __future__ import annotations

import Phase4_No1_sub_FmThetaChange as engine
from phase4_band_variant_config import configure_change_engine
from Phase4_No10_FzLowAlpha import engine as parent_engine

configure_change_engine(
    engine,
    parent_engine,
    analysis_stem="No10_sub_FzLowAlphaChange",
    focus_channel="Fz",
    script_version="20261112_lowalpha_change_v1",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
