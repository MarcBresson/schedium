from __future__ import annotations

from datetime import datetime

from schedium.schemas.granularity import (
    UNIT_TO_GRANULARITY_MAP,
    Granularity,
    GranularityUnit,
)
from schedium.triggers.base import BaseTrigger
from schedium.utils.window import TimeWindow


class Tick(BaseTrigger):
    """
    A tick source that always matches, but defines the dedup bucket.

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

    Parameters
    ----------
    granularity : schedium.schemas.granularity.Granularity | schedium.schemas.granularity.GranularityUnit
        Deduplication bucket size. If given as a string, it is converted via
        :data:`~schedium.schemas.granularity.UNIT_TO_GRANULARITY_MAP`.
    """

    def __init__(self, granularity: Granularity | GranularityUnit) -> None:
        if isinstance(granularity, str):
            granularity = UNIT_TO_GRANULARITY_MAP[granularity]
        self.granularity = granularity

    def required_granularity(self) -> Granularity:
        return self.granularity

    def fallback_granularity(self) -> Granularity:
        return self.granularity

    def matches(self, now: datetime) -> bool:
        return True

    def next_window(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> TimeWindow:
        return TimeWindow(start=after, end=None)
