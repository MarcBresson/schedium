from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pyscheduler.triggers.base import BaseTrigger, Granularity


@dataclass(frozen=True)
class On(BaseTrigger):
    unit: Literal[
        "year",
        "month_of_year",
        "week_of_year",
        "weekend_days",
        "weekdays",
        "day_of_week",
        "day_of_month",
        "hour_of_day",
        "minute_of_hour",
        "second_of_minute",
        "millisecond_of_second",
    ]
    value: int

    def fallback_granularity(self) -> Granularity:
        if self.unit in {"year"}:
            return Granularity.YEAR
        if self.unit in {"month_of_year", "week_of_year"}:
            return Granularity.MONTH
        if self.unit in {"day_of_week", "day_of_month", "weekdays", "weekend_days"}:
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
            if self.value == 0:
                return now.weekday() == 0
            if 1 <= self.value <= 7:
                return now.isoweekday() == self.value
            raise ValueError("day_of_week must be in 0..6 (python) or 1..7 (cron)")
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

        raise ValueError(f"Unsupported unit: {self.unit}")

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
