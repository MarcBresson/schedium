from __future__ import annotations

from datetime import datetime

from schedium.triggers.base import BaseTrigger
from schedium.types.granularity import (
    UNIT_TO_GRANULARITY_MAP,
    Granularity,
    GranularityUnit,
)
from schedium.types.time_window import TimeWindow


class Tick(BaseTrigger):
    """
    A trigger that always matches, but defines the dedup bucket.

    Tick(...) doesn’t control when; it controls how often at most it can run (once per bucket)
    when other parts of the trigger tree make it match.

    Even though both ``Every(unit=..., interval=1)`` and ``Tick(...)`` match for
    all ``now``, they differ in their notion of “next time”. For example, for
    ``after=10:00:30``:

    - ``Tick("minute").next_window(after)`` starts at ``10:00:30``.
    - ``Every("minute", interval=1).next_window(after)`` starts at the next
        epoch-aligned boundary (typically ``10:01:00``).

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
