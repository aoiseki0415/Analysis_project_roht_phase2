"""Non-writing guard for the retired No10_sub specified-pair sensitivity.

After signal-quality review on 2026-11-16, the user retained all eligible
participants in both products. This was a reviewed decision, not a missing
exclusion assessment. The independent topography sensitivity is unchanged.
Historical calculation code remains recoverable through Git history.
"""

from __future__ import annotations

import sys
from types import ModuleType

RETIREMENT_REASON = (
    "No10_sub SpecifiedPairsExcluded was retired after signal-quality review "
    "on 2026-11-16. Use the unchanged all-eligible primary results. "
    "No new files were written. Topography sensitivity is independent and unchanged."
)


def sensitivity_main(engine: ModuleType) -> int:
    """Reject the old CLI before preflight, directory creation, or output writes."""
    del engine
    print(RETIREMENT_REASON, file=sys.stderr)
    return 2
