from __future__ import annotations

from contextlib import suppress
from datetime import datetime

from pyscheduler.exceptions import NotATickingTrigger
from pyscheduler.job import Job
from pyscheduler.triggers import (
    AtDateTimeTrigger,
    BaseCombinatorTrigger,
    BaseTrigger,
    Every,
)


def _has_tick_source(trigger: BaseTrigger) -> bool:
    from pyscheduler.triggers.sugar.tick import Tick

    if isinstance(trigger, (Every, Tick, AtDateTimeTrigger)):
        return True
    if isinstance(trigger, BaseCombinatorTrigger):
        return any(_has_tick_source(t) for t in trigger.triggers)
    return False


DidNotRun = object()


class Scheduler:
    """Simple in-process scheduler.

    This scheduler is intentionally minimal:

    - Jobs run inline (no threads/processes by default).
    - User is responsible for calling :meth:`run_pending` periodically.
    - Deduplication is handled per-job: if you call :meth:`run_pending` multiple
      times within the same trigger "token" (e.g., the same minute bucket), the
      job runs only once.

    Examples
    --------
    Run something every 5 minutes

    >>> from datetime import datetime
    >>> from pyscheduler import DidNotRun, Every, Job, Scheduler
    >>> sched = Scheduler()
    >>> def tick():
    ...     print("tick")
    >>> sched.append(Job(tick, Every(unit="minute", interval=5)))
    >>> results = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    >>> results[0] is DidNotRun
    True
    >>> results = sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))
    tick
    >>> results
    [None]

    Deduplication when called repeatedly at the same timestamp

    >>> results = sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))  # same minute bucket
    >>> results[0] is DidNotRun
    True

    Combine triggers (weekday at 08:00)

    >>> from pyscheduler import On
    >>> weekday_8am = (
    ...     Every(unit="day", interval=1)
    ...     & On(unit="weekdays", value=1)
    ...     & On(unit="hour_of_day", value=8)
    ... )
    >>> sched = Scheduler()
    >>> def weekday_job():
    ...     print("weekday job")
    >>> sched.append(Job(weekday_job, weekday_8am))
    >>> results = sched.run_pending(now=datetime(2026, 2, 2, 8, 0, 0))  # Monday
    weekday job
    >>> results
    [None]

    Inspect the next run time across all jobs

    >>> sched.time_of_next_run(after=datetime(2026, 2, 2, 8, 0, 1))
    datetime.datetime(2026, 2, 3, 8, 0)

    Notes
    -----
    - :meth:`run_pending` returns a list aligned with :attr:`jobs`. For jobs that
      are not due, the entry is the sentinel :obj:`DidNotRun`.
    - Many triggers match only at specific boundaries (minute/hour/day). In
      production, call :meth:`run_pending` on a short interval (e.g., once per
      second) so you don't skip over a matching boundary.
    """

    def __init__(self):
        self.jobs: list[Job] = []

    def append(self, job: Job):
        """Append an already-constructed :class:`~pyscheduler.job.Job`."""
        if not _has_tick_source(job.trigger):
            raise ValueError(
                "Trigger is not schedulable without a tick source. "
                "Combine constraints (On/Between/BetweenDateTime) with a tick source "
                "like Every(...), Tick(...), or AtDateTimeTrigger(...)."
            )
        self.jobs.append(job)

    def __getitem__(self, item):
        return self.jobs[item]

    def run_pending(self, now: datetime | None = None) -> list[object]:
        """Run all jobs that are due at ``now``.

        Parameters
        ----------
        now:
            If provided, uses this timestamp to evaluate triggers. If omitted,
            uses the current system time.

        Returns
        -------
        list[object]
            The list of return values from each job. If a job is not due, its
            return value is :obj:`DidNotRun`.
        """
        now_dt = now if now is not None else datetime.now()
        results: list[object] = []
        for job in list(self.jobs):
            if job.is_due(now_dt):
                results.append(job.run(now_dt))
            else:
                results.append(DidNotRun)
        return results

    def time_of_next_run(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        """Return the earliest next run time across all jobs.

        This asks each job's trigger for its next run time and returns the
        minimum. Triggers that cannot compute a next time (for example,
        constraint-only triggers that require an external tick source) are
        ignored.

        Parameters
        ----------
        after:
            Lower bound (inclusive) for the computed next run time.
        max_iterations:
            Safety cap used by some triggers/combinators that scan forward.
        """
        next_runs: list[datetime] = []
        for job in self.jobs:
            # Ignore triggers that can't compute a next run time
            with suppress(NotATickingTrigger):
                next_run = job.trigger.datetime_of_next_run(
                    after, max_iterations=max_iterations
                )
                if next_run is not None:
                    next_runs.append(next_run)
        return min(next_runs) if next_runs else None

    def __repr__(self) -> str:
        return f"Scheduler(jobs={self.jobs!r})"
