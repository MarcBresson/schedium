from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from schedium.triggers.base import BaseTrigger, Granularity


@dataclass(frozen=True)
class BetweenDateTime(BaseTrigger):
    """Constraint trigger that matches within an inclusive datetime window.

    `BetweenDateTime` is a **constraint**: it filters time but does not define a
    cadence by itself. To schedule a job, combine it with a tick source such as
    :class:`~schedium.triggers.every.Every`, :class:`~schedium.triggers.sugar.tick.Tick`,
    or :class:`~schedium.triggers.datetime.AtDateTime`.

    Parameters
    ----------
    start_date:
        Inclusive lower bound of the window.
    end_date:
        Inclusive upper bound of the window.

    Notes
    -----
    Inclusivity
        The window is **inclusive** on both ends: ``start_date <= now <= end_date``.

    Validation
        If ``start_date > end_date`` a ``ValueError`` is raised.

    Granularity
        This trigger reports a fallback granularity of
        :attr:`~schedium.schemas.granularity.Granularity.SECOND`. That fallback is
        only used for generic scanning logic in
        :meth:`~schedium.triggers.base.BaseTrigger.datetime_of_next_run`.
        `BetweenDateTime` also implements an efficient
        :meth:`datetime_of_next_run` that returns:

        - ``start_date`` when queried before the window,
        - ``after`` when queried inside the window,
        - ``None`` when queried after the window.

    Timezones
        Keep ``start_date``, ``end_date``, and the scheduler's ``now`` either all
        timezone-aware (same tz) or all naive; comparing mixed values raises in
        Python.

    Examples
    --------
    Allow a job to run only during a maintenance window

    >>> from datetime import datetime, timezone
    >>> from schedium import BetweenDateTime, Every
    >>> window = BetweenDateTime(
    ...     start_date=datetime(2026, 2, 8, 1, 0, tzinfo=timezone.utc),
    ...     end_date=datetime(2026, 2, 8, 2, 0, tzinfo=timezone.utc),
    ... )
    >>> trigger = Every(unit="minute", interval=1) & window
    """

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
class AtDateTime(BaseTrigger):
    """One-shot tick-source trigger that fires at/after a specific datetime.

    `AtDateTime` matches when ``now >= run_date``.

    Unlike cadence-based tick sources (like :class:`~schedium.triggers.every.Every`),
    `AtDateTime` is intended for **one-shot** schedules. It is also safe if the
    scheduler starts late: the first evaluation after ``run_date`` will match,
    and deduplication ensures it runs only once.

    Parameters
    ----------
    run_date:
        The target datetime.

    Notes
    -----
    Granularity.EXACT
        `AtDateTime` declares :attr:`~schedium.schemas.granularity.Granularity.EXACT`
        as both its required and fallback granularity.

    Deduplication token
        When an `AtDateTime` is present anywhere in a trigger tree, schedium uses
        a token tied to ``run_date`` (rather than a time bucket). This ensures the
        job is treated as a true one-shot even if evaluated multiple times.

    Composing with constraints
        You can AND `AtDateTime` with constraints like
        :class:`~schedium.triggers.on.On` or
        :class:`~schedium.triggers.datetime.BetweenDateTime` to prevent late
        execution outside an intended window.

    Examples
    --------
    Run once at a specific time

    >>> from datetime import datetime
    >>> from schedium import AtDateTime
    >>> trigger = AtDateTime(datetime(2026, 2, 8, 12, 0, 0))

    Run once, but only if we're still inside a window

    >>> from datetime import datetime
    >>> from schedium import AtDateTime, BetweenDateTime
    >>> trigger = (
    ...     AtDateTime(datetime(2026, 2, 8, 12, 0, 0))
    ...     & BetweenDateTime(
    ...         start_date=datetime(2026, 2, 8, 0, 0, 0),
    ...         end_date=datetime(2026, 2, 8, 23, 59, 59),
    ...     )
    ... )
    """

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
