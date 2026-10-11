from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from datetime import datetime

from schedium.job import Job
from schedium.plugins._runner import PluginHost, notify, run_sync
from schedium.plugins.base import Plugin
from schedium.triggers.base import BaseTrigger
from schedium.types.cancel_job import CancelJob
from schedium.utils.evaluate import evaluate
from schedium.utils.time_of_next_run import time_of_next_run as _time_of_next_run

logger = logging.getLogger(__name__)


class JobDidNotRunType: ...


JobDidNotRun = JobDidNotRunType()
"""Sentinel value used by Scheduler.run_pending to indicate a job was not due"""


class Scheduler(PluginHost):
    """
    Simple in-process scheduler.

    This scheduler is intentionally minimal:

    - Jobs run inline (no threads/processes by default).
    - User is responsible for calling :meth:`run_pending` periodically.
    - Deduplication is handled per-job: if you call :meth:`run_pending` multiple
      times within the same trigger "token" (e.g., the same minute bucket), the
      job runs only once.

    Parameters
    ----------
    plugins : Iterable[Plugin], default ()
        Plugins that apply to every job of this scheduler. See
        :class:`~schedium.plugins.Plugin`.

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

    def __init__(self, *, plugins: Iterable[Plugin] = ()) -> None:
        self.jobs: list[Job] = []
        self._init_plugins(list(plugins))

    def append(self, job: Job) -> None:
        """
        Append an already-constructed job.

        Parameters
        ----------
        job : Job
            The job to append. The job's trigger is used to determine when it runs.
        """

        self.jobs.append(job)
        notify(self._effective_plugins(), "on_job_added", self, job)

    def add_job(
        self,
        trigger: BaseTrigger,
        name: str | None = None,
        *,
        id: str | None = None,
        plugins: Iterable[Plugin] = (),
    ) -> Callable[[Callable[[], object]], Callable[[], object]]:
        """
        Return a decorator that adds the decorated function as a job.

        Use this when you prefer declaring the job next to the function it runs
        instead of building a :class:`~schedium.job.Job` and passing it to
        :meth:`append`.

        Parameters
        ----------
        trigger : BaseTrigger
            The trigger that decides when the decorated function runs.
        name : str, default None
            Human-readable label for the job. Falls back to the
            ``__name__`` of the decorated function.
        id : str, default None
            Stable identifier for the job. Falls back to the ``__name__`` of
            the decorated function. See :attr:`schedium.job.Job.identifier`.
        plugins : Iterable[Plugin], default ()
            Plugins that apply to this job only, in addition to the plugins of
            this scheduler. See :class:`~schedium.plugins.Plugin`.

        Returns
        -------
        Callable
            A decorator that registers the decorated function and returns it
            unchanged, so the function can still be called normally and stacked
            with other decorators.

        Examples
        --------
        >>> from schedium import Every, Scheduler
        >>> sched = Scheduler()
        >>> @sched.add_job(Every(unit="minute", interval=5))
        ... def tick():
        ...     print("tick")
        >>> sched.jobs[0].name
        'tick'
        >>> tick()
        tick
        """

        def decorator(func: Callable[[], object]) -> Callable[[], object]:
            job = Job(
                func,
                trigger,
                name if name is not None else func.__name__,
                id=id if id is not None else func.__name__,
                plugins=plugins,
            )
            self.append(job)
            return func

        return decorator

    def __getitem__(self, item: int) -> Job:
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
            event = evaluate(job.trigger, now_dt)
            if event is None or event == job.last_event:
                results.append(JobDidNotRun)
                continue

            result = run_sync(
                job, scheduler=self, plugins=self._effective_plugins(), event=event
            )
            job.last_event = event
            results.append(result)

            if isinstance(result, CancelJob):
                try:
                    self.jobs.remove(job)
                except ValueError:
                    # Already removed by user code.
                    pass
                else:
                    notify(
                        self._effective_plugins(),
                        "on_job_removed",
                        self,
                        job,
                        result.reason,
                    )
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
        return _time_of_next_run(self.jobs, after, max_iterations=max_iterations)

    def __repr__(self) -> str:
        return f"Scheduler(jobs={self.jobs!r})"
