#!/usr/bin/env python3
"""Phase 4 No11_sub: Pz 8–10 Hz Set-1-relative change, without extra exclusions."""

from phase4_no11_cached_analysis import build_change_engine
from Phase4_No11_PzLowAlpha import engine as parent_engine

engine = build_change_engine(parent_engine)


if __name__ == "__main__":
    raise SystemExit(engine.main())
