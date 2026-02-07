from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pyscheduler.triggers.base import BaseTrigger, Granularity


@dataclass(frozen=True)
class Between(BaseTrigger):
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
    start: int
    end: int

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
        if self.start > self.end:
            raise ValueError("start must be <= end")

        if self.unit == "weekdays":
            return now.weekday() < 5
        if self.unit == "weekend_days":
            return now.weekday() >= 5

        if self.unit == "year":
            v = now.year
        elif self.unit == "month_of_year":
            v = now.month
        elif self.unit == "week_of_year":
            v = now.isocalendar().week
        elif self.unit == "day_of_week":
            if self.start == 0 or self.end == 0:
                if not (0 <= self.start <= 6 and 0 <= self.end <= 6):
                    raise ValueError(
                        "day_of_week range must use 0..6 (python) or 1..7 (cron), consistently"
                    )
                return self.start <= now.weekday() <= self.end
            if 1 <= self.start <= 7 and 1 <= self.end <= 7:
                return self.start <= now.isoweekday() <= self.end
            raise ValueError(
                "day_of_week range must use 0..6 (python) or 1..7 (cron), consistently"
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

    def datetime_of_next_run(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        if self.unit != "year":
            return super().datetime_of_next_run(after, max_iterations=max_iterations)
        if self.start > self.end:
            raise ValueError("start must be <= end")
        if after.year > self.end:
            return None
        if self.start <= after.year <= self.end and self.matches(after):
            return after
        return datetime(self.start, 1, 1, tzinfo=after.tzinfo)
