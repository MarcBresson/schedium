from __future__ import annotations

from datetime import datetime

from schedium.schemas.granularity import Granularity
from schedium.schemas.on_unit import OnUnit
from schedium.triggers.base import BaseTrigger


class On(BaseTrigger):
    """Constraint trigger that matches when a datetime falls *on* a specific value.

    `On` is a **constraint**: it filters time, but does not define a cadence by
    itself. To schedule a job, combine it with a tick source such as
    :class:`~schedium.triggers.every.Every`, :class:`~schedium.triggers.sugar.tick.Tick`,
    or :class:`~schedium.triggers.datetime.AtDateTime`.

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
    Tick source requirement
        `On` does not generate time buckets on its own. If you attempt to append
        a constraint-only trigger tree to :class:`~schedium.scheduler.Scheduler`,
        :meth:`~schedium.scheduler.Scheduler.append` raises ``ValueError``.

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
    ...     & On(unit="weekdays", value=1)
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

    def datetime_of_next_run(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        if self.unit != "year":
            return super().datetime_of_next_run(after, max_iterations=max_iterations)

        assert self.value is not None, f"value must be provided for unit {self.unit!r}"
        if after.year > self.value:
            return None
        if after.year == self.value and self.matches(after):
            return after
        return datetime(self.value, 1, 1, tzinfo=after.tzinfo)

    def __repr__(self) -> str:
        return f"On(unit={self.unit!r}, value={self.value})"


def _parse_unit(unit: OnUnit) -> Granularity:
    if unit in {"year"}:
        return Granularity.YEAR
    if unit in {"month_of_year", "week_of_year"}:
        return Granularity.MONTH
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
