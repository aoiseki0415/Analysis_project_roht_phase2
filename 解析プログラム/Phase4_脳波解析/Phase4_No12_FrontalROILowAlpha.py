#!/usr/bin/env python3
"""Phase 4 No12: finite-channel frontal ROI 8–10 Hz absolute PSD."""

from phase4_no12_cached_analysis import absolute_main, build_absolute_engine

engine = build_absolute_engine()


def main() -> int:
    return absolute_main(engine)


if __name__ == "__main__":
    raise SystemExit(main())
