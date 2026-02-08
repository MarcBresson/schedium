from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, tzinfo

from schedium.schemas.granularity import (
    UNIT_TO_GRANULARITY_MAP,
    Granularity,
    GranularityUnit,
)
from schedium.triggers.base import BaseTrigger
from schedium.utils.since_epoch import since_epoch
from schedium.utils.truncate_to_granularity import truncate

logger = logging.getLogger(__name__)


def datetime_from_since_epoch(
    value: int, granularity: Granularity, tzinfo: tzinfo | None
) -> datetime:
    epoch = datetime(1970, 1, 1, tzinfo=tzinfo)
    if granularity == Granularity.MILLISECOND:
        epoch = epoch
        return epoch + timedelta(milliseconds=value)
    if granularity == Granularity.SECOND:
        epoch = epoch
        return epoch + timedelta(seconds=value)
    if granularity == Granularity.MINUTE:
        epoch = epoch
        return epoch + timedelta(minutes=value)
    if granularity == Granularity.HOUR:
        epoch = epoch
        return epoch + timedelta(hours=value)
    if granularity == Granularity.DAY:
        d = epoch + timedelta(days=value)
        return datetime(d.year, d.month, d.day, tzinfo=tzinfo)
    if granularity == Granularity.WEEK:
        d = epoch + timedelta(days=value * 7)
        return datetime(d.year, d.month, d.day, tzinfo=tzinfo)
    if granularity == Granularity.MONTH:
        year = 1970 + (value // 12)
        month = (value % 12) + 1
        return datetime(year, month, 1, tzinfo=tzinfo)
    if granularity == Granularity.YEAR:
        return datetime(1970 + value, 1, 1, tzinfo=tzinfo)
    raise ValueError(f"Unsupported granularity for datetime conversion: {granularity}")


class Every(BaseTrigger):
    """Tick-source trigger that matches on a fixed cadence.

    `Every` is a **tick source**: it defines *when time advances* for a schedule.
    When it matches, the scheduler may run the job (subject to deduplication and
    any additional constraints).

    Conceptually, `Every` divides time into buckets of a given granularity
    (minute/hour/day/etc.) starting at the Unix epoch, and matches when the
    bucket number satisfies::

        unit_since_epoch % interval == offset

    unit_since_epoch is the number of complete `unit` buckets since the Unix
    epoch. For example, for `unit="minute"`, it counts the number of complete
    minutes since 1970-01-01T00:00:00Z.

    Parameters
    ----------
    unit:
        The cadence unit. One of ``"year"``, ``"month"``, ``"week"``, ``"day"``,
        ``"hour"``, ``"minute"``, ``"second"``, ``"millisecond"``.
    interval:
        The period in number of `unit` buckets. Must be ``> 0``.

        Example: ``interval=5`` with ``unit="minute"`` means every 5 minutes on
        epoch-aligned boundaries.
    offset:
        Phase offset within the cycle. Must satisfy ``0 <= offset < interval``.

        Example: with ``Every(unit="minute", interval=5, offset=2)``, the trigger
        matches for minute buckets numbered 2, 7, 12, ... since epoch.
    auto_offset:
        If True, ignores the provided `offset` and chooses an offset based on
        the current time (UTC) such that the trigger matches immediately and
        then repeats every `interval` buckets.

        This is useful when you want to start a job “now” but still maintain a
        stable cadence afterward.

    Notes
    -----
    Alignment (important)
        `Every` is **epoch-aligned**, not “relative to job creation time” when
        auto_offset is False. For example, ``Every(unit="hour", interval=1)``
        matches exactly on the hour. If you need a “run **once** sometime after X”
        semantics, consider :class:`~schedium.triggers.datetime.AtDateTime`.

    Deduplication
        schedium deduplicates at the job level using a trigger event token.
        For `Every`, the effective token bucket is the trigger's granularity
        (minute/hour/day...). Calling ``Scheduler.run_pending`` repeatedly
        within the same bucket will run the job only once.

    `interval == 1`
        When ``interval=1``, `Every` matches every bucket. The project logs a
        warning suggesting :class:`~schedium.triggers.sugar.tick.Tick` instead,
        which is often clearer for “always match, but dedup by granularity”.

    Timezones
        `since_epoch(...)` uses the provided ``datetime``. If you use timezone-
        aware datetimes, keep them consistent across calls.

    Examples
    --------
    Every 5 minutes

    >>> from schedium import Every
    >>> Every(unit="minute", interval=5)
    Every(unit='minute', interval=5, offset=0)

    Every 5 minutes, but shifted by 2 minutes

    >>> from schedium import Every
    >>> Every(unit="minute", interval=5, offset=2)
    Every(unit='minute', interval=5, offset=2)

    Every 2 hours minute 30 (cadence + constraints)

    >>> from schedium import Every, On
    >>> trigger = Every(unit="hour", interval=2) & On(unit="minute_of_hour", value=30)

    Auto-offset: run immediately, then every 10 minutes

    >>> from schedium import Every
    >>> trigger = Every(unit="minute", interval=10, auto_offset=True)
    """

    def __init__(
        self,
        unit: GranularityUnit,
        interval: int,
        offset: int = 0,
        auto_offset: bool = False,
    ):
        if interval <= 0:
            raise ValueError("interval must be > 0")
        if not (0 <= offset < interval):
            raise ValueError("offset must satisfy 0 <= offset < interval")
        if interval == 1:
            logger.warning(
                "Prefer using Tick(unit=%r) instead of Every(unit=%r, interval=1)",
                unit,
                unit,
            )

        self.unit = unit
        self.granularity = UNIT_TO_GRANULARITY_MAP[unit]
        self.interval = interval
        self.offset = offset

        if auto_offset:
            self.offset = auto_offset_from_now(
                self.required_granularity(), self.interval
            )

    def required_granularity(self) -> Granularity:
        return self.granularity

    def fallback_granularity(self) -> Granularity:
        return self.required_granularity()

    def matches(self, now: datetime) -> bool:
        granularity = self.required_granularity()
        return since_epoch(now, granularity) % self.interval == self.offset

    def datetime_of_next_run(
        self,
        after: datetime,
        *args,
        **kwargs,
    ) -> datetime:
        """
        Calculate the next run time after the given datetime.

        It will return the earliest time of the next interval that is >= `after`.
        """
        granularity = self.required_granularity()

        start = since_epoch(after, granularity)
        if truncate(after, granularity) < after:
            start += 1

        remainder = start % self.interval
        delta = (self.offset - remainder) % self.interval
        value = start + delta
        return datetime_from_since_epoch(value, granularity, after.tzinfo)

    def __repr__(self) -> str:
        return (
            f"Every(unit={self.unit!r}, interval={self.interval}, offset={self.offset})"
        )


def auto_offset_from_now(granularity: Granularity, interval: int) -> int:
    """Calculate the offset for an auto-offset Every trigger, based on current time.

    This allows for the first run to fire right away, and subsequent runs to be
    spaced by the given interval.
    """
    now = datetime.now(timezone.utc)
    return since_epoch(now, granularity) % interval
