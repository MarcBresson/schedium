from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TimeWindow:
    """
    A validity window for a trigger.

    The window is inclusive on both ends: ``start <= t <= end``.

    If ``end`` is None, the window is unbounded into the future.
    """

    start: datetime
    end: datetime | None
