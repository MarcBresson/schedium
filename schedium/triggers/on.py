from __future__ import annotations

from datetime import datetime

from schedium.schemas.granularity import Granularity
from schedium.schemas.on_unit import OnUnit
from schedium.triggers.base import BaseTrigger


class On(BaseTrigger):
    def __init__(
        self,
        unit: OnUnit,
        value: int,
    ):
        self.unit: OnUnit = unit
        self.value = value
        self.granularity = _parse_unit(unit)

    def fallback_granularity(self) -> Granularity:
        return self.granularity

    def matches(self, now: datetime) -> bool:
        if self.unit == "weekdays":
            return now.weekday() < 5
        if self.unit == "weekend_days":
            return now.weekday() >= 5

        if self.unit == "year":
            return now.year == self.value
        if self.unit == "month_of_year":
            return now.month == self.value
        if self.unit == "week_of_year":
            return now.isocalendar().week == self.value
        if self.unit == "day_of_week":
            if 1 <= self.value <= 7:
                return now.isoweekday() == self.value
            raise ValueError("day_of_week must be in 1..7 (cron)")
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
