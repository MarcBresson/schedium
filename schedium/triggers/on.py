from __future__ import annotations

from datetime import datetime, timedelta

from schedium.schemas.granularity import Granularity
from schedium.schemas.on_unit import OnUnit
from schedium.triggers.base import (
    BaseTrigger,
    _bucket_end_inclusive,
    _scan_next_match_start,
)
from schedium.utils.window import TimeWindow


class On(BaseTrigger):
    """
    Constraint trigger that matches when a datetime falls *on* a specific value.

    `On` is a **constraint**: it filters time, but does not define a cadence by
    itself.

    Parameters
    ----------
    unit : {year, month_of_year, week_of_year, day_of_week, weekdays, weekend_days,
        day_of_month, hour_of_day, minute_of_hour, second_of_minute,
        millisecond_of_second}

        Which part of the datetime to check.

        Supported values are:

        - ``"year"``
        - ``"month_of_year"`` (1..12)
        - ``"week_of_year"`` (ISO week number, 1..53)
        - ``"weekdays"`` (Mon..Fri; ``value`` is ignored)
        - ``"weekend_days"`` (Sat..Sun; ``value`` is ignored)
        - ``"day_of_week"`` (iso-style, 1..7 where 1=Mon)
        - ``"day_of_month"`` (1..31)
        - ``"hour_of_day"`` (0..23)
        - ``"minute_of_hour"`` (0..59)
        - ``"second_of_minute"`` (0..59)
        - ``"millisecond_of_second"`` (0..999)
    value : int, default None
        The target value to match for the selected unit.

        For ``unit in {"weekdays", "weekend_days"}`` the value is ignored
        since the unit already fully defines the constraint.

    Notes
    -----
    Scheduling notes
        `On` may match for an extended interval (for example, an entire hour or
        day), so jobs should rely on deduplication to avoid repeated runs.

    Day-of-week semantics
        `On` uses **iso-style** day-of-week numbering (1..7) via
        :meth:`datetime.datetime.isoweekday`.

    Timezones
        All comparisons are performed against the provided ``datetime`` object.
        If you're using timezone-aware datetimes, ensure you pass consistent
        tz-aware values to the scheduler.

    Examples
    --------
    Run every weekday at 08:00

    >>> from schedium import Every, On
    >>> trigger = (
    ...     Every(unit="day", interval=1)
    ...     & On(unit="weekdays")
    ...     & On(unit="hour_of_day", value=8)
    ...     & On(unit="minute_of_hour", value=0)
    ... )

    Run on the 1st of each month at midnight

    >>> from schedium import Every, On
    >>> trigger = (
    ...     Every(unit="day", interval=1)
    ...     & On(unit="day_of_month", value=1)
    ...     & On(unit="hour_of_day", value=0)
    ...     & On(unit="minute_of_hour", value=0)
    ... )
    """

    def __init__(
        self,
        unit: OnUnit,
        value: int | None = None,
    ):
        self.unit: OnUnit = unit
        self.value = value
        self.granularity = _parse_unit(unit)

    def fallback_granularity(self) -> Granularity:
        return self.granularity

    def matches(self, now: datetime) -> bool:  # pyright: ignore[reportReturnType]
        if self.unit == "weekdays":
            return now.weekday() < 5
        if self.unit == "weekend_days":
            return now.weekday() >= 5

        assert self.value is not None, f"value must be provided for unit {self.unit!r}"
        if self.unit == "year":
            return now.year == self.value
        if self.unit == "month_of_year":
            return now.month == self.value
        if self.unit == "week_of_year":
            return now.isocalendar().week == self.value
        if self.unit == "day_of_week":
            if 1 <= self.value <= 7:
                return now.isoweekday() == self.value
            raise ValueError("day_of_week must be in 1..7 (iso)")
        if self.unit == "day_of_month":
            return now.day == self.value
        if self.unit == "hour_of_day":
            return now.hour == self.value
        if self.unit == "minute_of_hour":
            return now.minute == self.value
        if self.unit == "second_of_minute":
            return now.second == self.value
        if self.unit == "millisecond_of_second":
            return (now.microsecond // 1000) == self.value

    def next_window(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> TimeWindow | None:
        # Year can be computed without scanning.
        if self.unit == "year":
            assert self.value is not None, (
                f"value must be provided for unit {self.unit!r}"
            )
            if after.year > self.value:
                return None

            start_dt_year = (
                after
                if self.matches(after)
                else datetime(self.value, 1, 1, tzinfo=after.tzinfo)
            )
            end_exclusive = datetime(self.value + 1, 1, 1, tzinfo=after.tzinfo)
            return TimeWindow(
                start=start_dt_year, end=end_exclusive - timedelta(microseconds=1)
            )

        granularity = self.granularity

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

        return TimeWindow(
            start=start_dt, end=_bucket_end_inclusive(start_dt, granularity)
        )

    def __repr__(self) -> str:
        return f"On(unit={self.unit!r}, value={self.value})"


def _parse_unit(unit: OnUnit) -> Granularity:
    if unit in {"year"}:
        return Granularity.YEAR
    if unit in {"month_of_year"}:
        return Granularity.MONTH
    if unit in {"week_of_year"}:
        return Granularity.WEEK
    if unit in {"day_of_week", "day_of_month", "weekdays", "weekend_days"}:
        return Granularity.DAY
    if unit == "hour_of_day":
        return Granularity.HOUR
    if unit == "minute_of_hour":
        return Granularity.MINUTE
    if unit == "second_of_minute":
        return Granularity.SECOND
    if unit == "millisecond_of_second":
        return Granularity.MILLISECOND
    return Granularity.DAY
