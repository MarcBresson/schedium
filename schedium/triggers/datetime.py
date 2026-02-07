from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from schedium.triggers.base import BaseTrigger, Granularity


@dataclass(frozen=True)
class BetweenDateTime(BaseTrigger):
    start_date: datetime
    end_date: datetime

    def matches(self, now: datetime) -> bool:
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self.start_date <= now <= self.end_date

    def fallback_granularity(self) -> Granularity:
        return Granularity.SECOND

    def datetime_of_next_run(
        self,
        after: datetime,
        *args,
        **kwargs,
    ) -> datetime | None:
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")

        if after <= self.start_date:
            return self.start_date
        if self.start_date <= after <= self.end_date:
            return after
        return None


@dataclass(frozen=True)
class AtDateTimeTrigger(BaseTrigger):
    run_date: datetime

    def required_granularity(self) -> Granularity:
        return Granularity.EXACT

    def fallback_granularity(self) -> Granularity:
        return Granularity.EXACT

    def matches(self, now: datetime) -> bool:
        return now >= self.run_date

    def datetime_of_next_run(
        self,
        after: datetime,
        *args,
        **kwargs,
    ) -> datetime | None:
        return self.run_date if self.run_date >= after else None
