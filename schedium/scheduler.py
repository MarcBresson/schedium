from __future__ import annotations

import logging
from datetime import datetime

from schedium.job import Job
from schedium.types.cancel_job import CancelJob

logger = logging.getLogger(__name__)

JobDidNotRun = object()
"""Sentinel value used by Scheduler.run_pending to indicate a job was not due"""


class Scheduler:
    """
    Simple in-process scheduler.

    This scheduler is intentionally minimal:

    - Jobs run inline (no threads/processes by default).
    - User is responsible for calling :meth:`run_pending` periodically.
    - Deduplication is handled per-job: if you call :meth:`run_pending` multiple
      times within the same trigger "token" (e.g., the same minute bucket), the
      job runs only once.

    Notes
    -----
    - :meth:`run_pending` returns a list aligned with :attr:`jobs`. For jobs that
        are not due, the entry is the sentinel :obj:`JobDidNotRun`.
    - Many triggers match only at specific boundaries (minute/hour/day). In
        production, call :meth:`run_pending` on a short interval (e.g., once per
        second) so you don't skip over a matching boundary.

    Examples
    --------
    Run something every 5 minutes

    >>> from datetime import datetime
    >>> from schedium import JobDidNotRun, Every, Job, Scheduler
    >>> sched = Scheduler()
    >>> def tick():
    ...     print("tick")
    >>> sched.append(Job(tick, Every(unit="minute", interval=5)))
    >>> results = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    >>> results[0] is JobDidNotRun
    True
    >>> results = sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))
    tick
    >>> results
    [None]

    Deduplication when called repeatedly at the same timestamp

    >>> results = sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))  # same minute bucket
    >>> results[0] is JobDidNotRun
    True

    Combine triggers (weekday at 08:00)

    >>> from schedium import On
    >>> weekday_8am = (
    ...     Every(unit="day", interval=1)
    ...     & On(unit="weekdays")
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
    """

    def __init__(self):
        self.jobs: list[Job] = []

    def append(self, job: Job) -> None:
        """
        Append an already-constructed job.

        Parameters
        ----------
        job : Job
            The job to append. The job's trigger is used to determine when it runs.
        """

        self.jobs.append(job)

    def __getitem__(self, item):
        return self.jobs[item]

    def run_pending(self, now: datetime | None = None) -> list[object]:
        """
        Run all jobs that are due at ``now``.

        Parameters
        ----------
        now : datetime, optional
            If provided, uses this timestamp to evaluate triggers. If omitted,
            uses the current system time.

        Returns
        -------
        list[object]
            The list of return values from each job. If a job is not due, its
            return value is :obj:`JobDidNotRun`.

            If a job runs and returns :class:`~schedium.types.cancel_job.CancelJob`, the job
            is removed from the scheduler.
        """

        now_dt = now if now is not None else datetime.now()
        results: list[object] = []

        # Iterate over a snapshot so results align with the jobs that were
        # present at the start of this call.
        for job in list(self.jobs):
            if not job.is_due(now_dt):
                results.append(JobDidNotRun)
                continue

            result = job.run(now_dt)
            results.append(result)

            if isinstance(result, CancelJob):
                try:
                    self.jobs.remove(job)
                except ValueError:
                    # Already removed by user code.
                    pass
                logger.info(
                    "Job %r cancelled itself (reason=%r)",
                    job,
                    result.reason,
                )

        return results

    def time_of_next_run(
        self,
        after: datetime | None = None,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        """
        Return the earliest next run time across all jobs.

        This asks each job's trigger for its next run time and returns the
        minimum. Triggers that cannot compute a next time are ignored.

        Parameters
        ----------
        after : datetime, optional
            Lower bound (inclusive) for the computed next run time. If omitted,
            uses the current system time.
        max_iterations : int, default 100_000
            Safety cap used by some triggers/combinators that scan forward.
        """
        if after is None:
            after = datetime.now()

        next_runs: list[datetime] = []
        for job in self.jobs:
            next_run = job.datetime_of_next_run(after, max_iterations=max_iterations)
            if next_run is not None:
                next_runs.append(next_run)
        return min(next_runs) if next_runs else None

    def __repr__(self) -> str:
        return f"Scheduler(jobs={self.jobs!r})"
