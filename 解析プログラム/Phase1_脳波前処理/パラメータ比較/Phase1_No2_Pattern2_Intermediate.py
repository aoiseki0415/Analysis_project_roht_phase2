#!/usr/bin/env python3
"""Run Phase 1 No2 with the intermediate ID101 comparison profile."""

from __future__ import annotations

import sys
from pathlib import Path

MODULE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_DIR))

from Phase1_No2_AutomatedPreProcessing import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(
        main(
            forced_profile="Pattern2_Intermediate",
            forced_output_label="Pattern2_Intermediate",
            force_skip_local_data_output=True,
        )
    )
