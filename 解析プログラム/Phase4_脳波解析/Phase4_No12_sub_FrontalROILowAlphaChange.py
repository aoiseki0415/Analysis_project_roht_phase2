#!/usr/bin/env python3
"""Phase 4 No12_sub: own-ID Set-1-relative frontal ROI low-alpha change."""

from phase4_no12_cached_analysis import build_change_engine
from Phase4_No12_FrontalROILowAlpha import engine as parent_engine

engine = build_change_engine(parent_engine)


if __name__ == "__main__":
    raise SystemExit(engine.main())
