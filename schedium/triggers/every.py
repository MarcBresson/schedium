from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone, tzinfo

from schedium.schemas.granularity import (
    GRANULARITY_TO_UNIT_MAP,
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
        return f"Every(unit={GRANULARITY_TO_UNIT_MAP[self.granularity]!r}, interval={self.interval}, offset={self.offset})"


def auto_offset_from_now(granularity: Granularity, interval: int) -> int:
    """Calculate the offset for an auto-offset Every trigger, based on current time.

    This allows for the first run to fire right away, and subsequent runs to be
    spaced by the given interval.
    """
    now = datetime.now(timezone.utc)
    return since_epoch(now, granularity) % interval
