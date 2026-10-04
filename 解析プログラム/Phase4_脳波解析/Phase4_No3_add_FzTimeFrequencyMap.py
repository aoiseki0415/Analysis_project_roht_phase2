#!/usr/bin/env python3
"""Phase 4 No3_add: Fz 1-30 Hz Grand-average time-frequency maps."""

from __future__ import annotations

import Phase4_No1_add_FzTimeFrequencyMap as engine
from phase4_band_variant_config import configure_tfm_engine

configure_tfm_engine(
    engine,
    analysis_stem="No3_add_FzTimeFrequencyMap",
    cache_file_tag="FzTFM",
    focus_channel="Fz",
    script_version="phase4-no3-add-fz-tfm-2026-10-04.1",
    cache_version="phase4-no3-add-fz-tfm-2026-10-04.1",
)


if __name__ == "__main__":
    raise SystemExit(engine.main())
