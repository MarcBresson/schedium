from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from schedium.triggers.base import (
    BaseTrigger,
    Granularity,
    TimeWindow,
    _bucket_end_inclusive,
    _increment,
    _scan_next_match_start,
)
from schedium.utils.truncate_to_granularity import truncate


@dataclass(frozen=True)
class Between(BaseTrigger):
    """Constraint trigger that matches when a datetime field is within a range.

    `Between` is a **constraint**: it filters time, but does not define a cadence.
    To schedule a job, combine it with a tick source such as
    :class:`~schedium.triggers.every.Every`, :class:`~schedium.triggers.sugar.tick.Tick`,
    or :class:`~schedium.triggers.datetime.AtDateTime`.

    Parameters
    ----------
    unit:
        Which datetime component to examine.

        Supported values:

        - ``"year"``
        - ``"month_of_year"`` (1..12)
        - ``"week_of_year"`` (ISO week number via ``datetime.isocalendar().week``)
        - ``"day_of_week"`` (1..7 where 1=Mon, 7=Sun)
        - ``"day_of_month"`` (1..31)
        - ``"hour_of_day"`` (0..23)
        - ``"minute_of_hour"`` (0..59)
        - ``"second_of_minute"`` (0..59)
        - ``"millisecond_of_second"`` (0..999)
    start:
        Inclusive lower bound for the selected unit.
    end:
        Inclusive upper bound for the selected unit.

    Notes
    -----
    Inclusivity
        Ranges are **inclusive**: a datetime matches when ``start <= value <= end``.

    Validation
        If ``start > end`` a ``ValueError`` is raised.

        For ``unit in {"weekdays", "weekend_days"}``, `start` and `end` are
        ignored by the matching logic, but the ``start <= end`` validation still
        applies.

    Day-of-week numbering
        ``unit="day_of_week"`` uses **ISO / cron-style** numbering (1..7) via
        :meth:`datetime.datetime.isoweekday`. Values outside 1..7 raise
        ``ValueError``.

    Next-run computation
        Most units fall back to a generic forward scan in
        :meth:`~schedium.triggers.base.BaseTrigger.datetime_of_next_run` using an
        inferred granularity.

        ``unit="year"`` overrides :meth:`datetime_of_next_run` to return:

        - ``None`` when ``after.year > end``
        - ``after`` when already within the range and matching
        - ``datetime(start, 1, 1, tzinfo=after.tzinfo)`` otherwise

    Examples
    --------
    Working hours: any 10 minute between 09:00 and 17:00

    >>> from schedium import Between, Every
    >>> trigger = Every(unit="minute", interval=10) & Between(unit="hour_of_day", start=9, end=17)

    First business week of the month (Mon..Fri)

    >>> from schedium import Between, Tick
    >>> trigger = (
    ...     Tick(granularity="day")
    ...     & Between(unit="day_of_month", start=1, end=7)
    ...     & Between(unit="day_of_week", start=1, end=5)
    ... )
    """

    unit: Literal[
        "year",
        "month_of_year",
        "week_of_year",
        "day_of_week",
        "day_of_month",
        "hour_of_day",
        "minute_of_hour",
        "second_of_minute",
        "millisecond_of_second",
    ]
    start: int
    end: int

    def fallback_granularity(self) -> Granularity:
        if self.unit in {"year"}:
            return Granularity.YEAR
        if self.unit in {"month_of_year"}:
            return Granularity.MONTH
        if self.unit in {"week_of_year"}:
            return Granularity.WEEK
        if self.unit in {"day_of_week", "day_of_month"}:
            return Granularity.DAY
        if self.unit == "hour_of_day":
            return Granularity.HOUR
        if self.unit == "minute_of_hour":
            return Granularity.MINUTE
        if self.unit == "second_of_minute":
            return Granularity.SECOND
        if self.unit == "millisecond_of_second":
            return Granularity.MILLISECOND
        return Granularity.DAY

    def matches(self, now: datetime) -> bool:
        if self.start > self.end:
            raise ValueError("start must be <= end")

        if self.unit == "year":
            v = now.year
        elif self.unit == "month_of_year":
            v = now.month
        elif self.unit == "week_of_year":
            v = now.isocalendar().week
        elif self.unit == "day_of_week":
            if 1 <= self.start <= 7 and 1 <= self.end <= 7:
                return self.start <= now.isoweekday() <= self.end
            raise ValueError(
                "day_of_week range must use 1..7 (Monday..Sunday), consistently"
            )
        elif self.unit == "day_of_month":
            v = now.day
        elif self.unit == "hour_of_day":
            v = now.hour
        elif self.unit == "minute_of_hour":
            v = now.minute
        elif self.unit == "second_of_minute":
            v = now.second
        elif self.unit == "millisecond_of_second":
            v = now.microsecond // 1000
        else:
            raise ValueError(f"Unsupported unit: {self.unit}")

        return self.start <= v <= self.end

    def next_window(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> TimeWindow | None:
        if self.start > self.end:
            raise ValueError("start must be <= end")

        # Year range can be computed without scanning.
        if self.unit == "year":
            if after.year > self.end:
                return None

            start_dt = after
            if after.year < self.start:
                start_dt = datetime(self.start, 1, 1, tzinfo=after.tzinfo)
            elif not self.matches(after):
                # after.year is within [start,end] but doesn't match (shouldn't happen)
                start_dt = datetime(self.start, 1, 1, tzinfo=after.tzinfo)

            end_exclusive = datetime(self.end + 1, 1, 1, tzinfo=after.tzinfo)
            return TimeWindow(
                start=start_dt, end=end_exclusive - timedelta(microseconds=1)
            )

        granularity = self.fallback_granularity()

        start_dt: datetime | None = None
        if self.matches(after):
            start_dt = after
        else:
            start_dt = _scan_next_match_start(
                self,
                after,
                granularity=granularity,
                max_iterations=max_iterations,
            )
            if start_dt is None:
                return None

        # Expand to the end of the contiguous matching region by stepping buckets.
        bucket = truncate(start_dt, granularity)
        if not self.matches(bucket):
            # Safety: if we landed inside a matching bucket, normalize.
            bucket = truncate(start_dt, granularity)

        next_bucket = _increment(bucket, granularity)
        steps = 0
        while self.matches(next_bucket):
            if steps >= max_iterations:
                break
            bucket = next_bucket
            next_bucket = _increment(bucket, granularity)
            steps += 1

        if steps >= max_iterations:
            # Fall back to a single bucket window to avoid unbounded loops.
            return TimeWindow(
                start=start_dt, end=_bucket_end_inclusive(start_dt, granularity)
            )

        window_end = next_bucket - timedelta(microseconds=1)
        if window_end < start_dt:
            window_end = _bucket_end_inclusive(start_dt, granularity)
        return TimeWindow(start=start_dt, end=window_end)
