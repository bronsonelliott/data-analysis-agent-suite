"""Helpers for finding pipeline output files.

Every stage stamps its outputs with _YYYYmmdd_HHMMSS. "Latest" means the
newest timestamp in the filename, everywhere, so the pipeline, report
writer and summarizer all agree on which run is current.
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Union

# Every stage stamps its outputs with _YYYYmmdd_HHMMSS
TIMESTAMP_PATTERN = re.compile(r'(\d{8}_\d{6})')


def sort_newest_first(paths: Iterable[Union[str, Path]]) -> List[str]:
    """
    Sort output paths by the timestamp in their filename, newest first.

    Sorting by name instead would rank "zeta_report_2024..." above
    "alpha_report_2026...", and sorting by modification time changes
    whenever a file is copied or touched. Files without a timestamp fall
    back to modification time.

    Args:
        paths: Paths to sort

    Returns:
        Path strings, newest first
    """
    def sort_key(p: Union[str, Path]) -> str:
        stamps = TIMESTAMP_PATTERN.findall(os.path.basename(str(p)))
        if stamps:
            return stamps[-1]
        return datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y%m%d_%H%M%S")

    return [str(p) for p in sorted(paths, key=sort_key, reverse=True)]
