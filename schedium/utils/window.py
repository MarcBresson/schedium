from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class TimeWindow:
    """
    A validity window for a trigger.

    The window is inclusive on both ends: ``start <= t <= end``.

    If ``end`` is None, the window is unbounded into the future.
    """

    start: datetime
    end: datetime | None


ONE_MICROSECOND = timedelta(microseconds=1)


def window_overlaps(a: TimeWindow, b: TimeWindow) -> bool:
    """
    Return True when two inclusive windows overlap.

    Treats ``end=None`` as +infinity.

    Parameters
    ----------
    a : schedium.utils.window.TimeWindow
        First window.
    b : schedium.utils.window.TimeWindow
        Second window.

    Returns
    -------
    bool
        True if the windows overlap.
    """

    a_end = a.end
    b_end = b.end

    if a_end is None and b_end is None:
        return True
    if a_end is None:
        return a.start <= b_end  # type: ignore[operator]
    if b_end is None:
        return b.start <= a_end
    return a.start <= b_end and b.start <= a_end


def window_intersection(a: TimeWindow, b: TimeWindow) -> TimeWindow | None:
    start = max(a.start, b.start)
    if a.end is None:
        end = b.end
    elif b.end is None:
        end = a.end
    else:
        end = min(a.end, b.end)

    if end is not None and start > end:
        return None
    return TimeWindow(start=start, end=end)


def window_union_if_overlapping(a: TimeWindow, b: TimeWindow) -> TimeWindow | None:
    if not window_overlaps(a, b):
        return None

    start = min(a.start, b.start)
    if a.end is None or b.end is None:
        end = None
    else:
        end = max(a.end, b.end)
    return TimeWindow(start=start, end=end)
