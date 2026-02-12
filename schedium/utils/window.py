from __future__ import annotations

from datetime import timedelta

from schedium.types.time_window import TimeWindow

ONE_MICROSECOND = timedelta(microseconds=1)


def window_overlaps(a: TimeWindow, b: TimeWindow) -> bool:
    """
    Return True when two inclusive windows overlap.

    Treats ``end=None`` as +infinity.

    Parameters
    ----------
    a : schedium.types.time_window.TimeWindow
        First window.
    b : schedium.types.time_window.TimeWindow
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
    if a_end is None and b_end is not None:
        return a.start <= b_end
    if b_end is None and a_end is not None:
        return b.start <= a_end
    # at this point, it is not possible for either end to be None,
    # so we can compare them directly. The assert is for type checkers.
    assert a_end is not None and b_end is not None
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
