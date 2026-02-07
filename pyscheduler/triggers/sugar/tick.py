from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pyscheduler.schemas.granularity import Granularity
from pyscheduler.triggers.base import BaseTrigger


@dataclass(frozen=True)
class Tick(BaseTrigger):
    """A tick source that always matches, but defines the dedup bucket.

    In this project, a *tick source* is required for a trigger to be schedulable
    (see `Scheduler.append(...)`). Many triggers (like `On(...)` / `Between(...)`) are
    *constraints* and do not generate ticks on their own.

    `Tick` differs from `Every`:

    - `Every(unit=..., interval=...)` is a *real cadence*: it only matches at
        specific aligned instants derived from epoch math.
    - `Tick(granularity=...)` is a *bucket limiter*: it matches at any `now`, but
        causes deduplication to happen at the given granularity via `evaluate(...)`.

    Why this is useful:

    - When composing constraints with AND, using `Every(unit="week", interval=1)`
        can force alignment to week boundaries (e.g. Monday 00:00), which makes
        intersection search for schedules like "Monday at 09:30" less direct.
    - `Tick(Granularity.WEEK)` keeps the schedule driven by the constraints
        (weekday/time), while still guaranteeing the job won't run more than once
        per WEEK bucket.

    `Tick` is intended mainly for "sugar" helpers (like `Weekly(...)`) and
    advanced compositions.
    """

    granularity: Granularity

    def required_granularity(self) -> Granularity:
        return self.granularity

    def fallback_granularity(self) -> Granularity:
        return self.granularity

    def matches(self, now: datetime) -> bool:
        return True

    def datetime_of_next_run(self, after: datetime, *args, **kwargs) -> datetime:
        return after
