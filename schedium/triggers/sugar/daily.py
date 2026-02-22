from __future__ import annotations

from datetime import time

from schedium.triggers.base import BaseTrigger
from schedium.triggers.on import On
from schedium.triggers.sugar._time import parse_at
from schedium.triggers.sugar.tick import Tick
from schedium.types.granularity import Granularity


def Daily(*, at: str | time | None = None) -> BaseTrigger:
    """
    Convenience trigger: run daily, optionally at a time.

    Parameters
    ----------
    at : str | datetime.time, optional
        Time of day to run at. If not provided, it will not constrain the time.
        Can be a :class:`datetime.time` object, or a string in "HH:MM" or
        "HH:MM:SS[.mmm]" format.

    Notes
    -----
    This helper composes triggers to express a daily schedule.

    - `Tick(Granularity.DAY)` provides a DAY "bucket" for deduplication.
    - If `at` is provided, it constrains hour/minute
      (and optionally second/millisecond).

    Examples
    --------
    >>> Daily()
    >>> Daily(at="09:30")
    >>> from datetime import time
    >>> Daily(at=time(9, 30, 15))
    """

    trigger: BaseTrigger = Tick(Granularity.DAY)

    if at is None:
        return trigger

    hour, minute, second, millisecond = parse_at(at)

    trigger = trigger & On(unit="hour_of_day", value=hour)
    trigger = trigger & On(unit="minute_of_hour", value=minute)

    if second is not None:
        trigger = trigger & On(unit="second_of_minute", value=second)
    if millisecond is not None:
        trigger = trigger & On(unit="millisecond_of_second", value=millisecond)

    return trigger
