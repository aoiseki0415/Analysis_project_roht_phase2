#!/usr/bin/env python3
"""Phase 4 No11: Pz 8–10 Hz absolute PSD from verified No10 all-channel caches."""

from phase4_no11_cached_analysis import absolute_main, build_absolute_engine

engine = build_absolute_engine()


def main() -> int:
    return absolute_main(engine)


if __name__ == "__main__":
    raise SystemExit(main())
