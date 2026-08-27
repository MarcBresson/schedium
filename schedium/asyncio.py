"""
Async-capable scheduler helpers.

:class:`AsyncScheduler` keeps its own job list -- used directly the same way
you would use :class:`~schedium.scheduler.Scheduler` -- and runs due jobs on the
current event loop. ``async def`` job functions are awaited directly; plain
synchronous job functions are offloaded to the default executor so they never
block the loop.

To run the scheduler loop itself in the background, use a plain
:func:`asyncio.create_task` -- see :doc:`/usage/asyncio` for the pattern.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime
from functools import partial
from typing import Literal, overload

from schedium.job import Job
from schedium.scheduler import JobDidNotRun, JobDidNotRunType
from schedium.triggers.base import TriggerEvent
from schedium.types.cancel_job import CancelJob
from schedium.utils.evaluate import evaluate
from schedium.utils.time_of_next_run import time_of_next_run as _time_of_next_run

logger = logging.getLogger(__name__)


async def _run_job_func(job: Job) -> object:
    if inspect.iscoroutinefunction(job.func):
        return await job.func()

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, job.func)


def _claim_due_event(
    job: Job,
    now: datetime,
) -> tuple[bool, TriggerEvent | None, TriggerEvent | None]:
    event = evaluate(job.trigger, now)
    if event is None:
        return False, None, None

    previous_event = job.last_event
    if event == previous_event:
        return False, event, previous_event

    job.last_event = event
    return True, event, previous_event


def _on_task_done(
    task: asyncio.Task[object],
    *,
    _scheduler: AsyncScheduler,
    _job: Job,
    _event: TriggerEvent,
    _prev: TriggerEvent | None,
) -> None:
    try:
        result = task.result()
    except BaseException:  # pylint: disable=broad-except
        logger.exception("Async job %r raised", _job)
        _scheduler.maybe_revert_last_event(
            _job,
            claimed_event=_event,
            previous_event=_prev,
        )
        return

    if isinstance(result, CancelJob):
        _scheduler.remove_job_if_present(_job)


class AsyncScheduler:
    """
    Async-native scheduler: evaluate triggers and run due jobs on the event loop.

    Unlike :class:`~schedium.threading.ThreadedJobsScheduler`, this class does not
    wrap a :class:`~schedium.scheduler.Scheduler`. It keeps its own job list and is
    meant to be used directly, the same way you would use
    :class:`~schedium.scheduler.Scheduler`.

    Key differences vs. :meth:`schedium.scheduler.Scheduler.run_pending`:

    - When a job is due, this scheduler *claims* the trigger token immediately (by
      updating ``job.last_event``) before dispatching the job. This prevents duplicate
      submissions when the scheduler loop runs again while a job is still executing.
    - ``async def`` job functions are awaited directly on the event loop. Plain
      synchronous job functions run in the default executor (a thread pool) via
      :meth:`asyncio.loop.run_in_executor`, so they never block the event loop.

    Parameters
    ----------
    max_concurrency : int | None, default None
        If provided, limits the number of jobs running at the same time using an
        :class:`asyncio.Semaphore`. If omitted, all due jobs run concurrently.
    revert_last_event_on_failure : bool, default False
        If True, and a job raises an exception, ``job.last_event`` is reverted to its
        previous value so the job may be retried within the same token on a subsequent
        call.

    Notes
    -----
    Concurrency safety
        Unlike :class:`~schedium.threading.ThreadedJobsScheduler`, no lock is needed
        to guard ``jobs``/``job.last_event``. asyncio runs cooperatively on a single
        thread, and this scheduler never awaits between reading and claiming a
        trigger token, so there is no window for another task to interleave.

    CancelJob handling
        If a job returns :class:`~schedium.types.cancel_job.CancelJob`, the job is
        removed from the scheduler.

    Examples
    --------
    Run due jobs concurrently while keeping control of the event loop

    >>> import asyncio
    >>> from datetime import datetime
    >>> from schedium import Every, Job
    >>> from schedium.asyncio import AsyncScheduler
    >>> async def main():
    ...     async def tick():
    ...         return "ok"
    ...     sched = AsyncScheduler()
    ...     sched.append(Job(tick, Every(unit="second", interval=1)))
    ...     return await sched.run_pending(now=datetime(2026, 2, 12, 12, 0, 0))
    >>> asyncio.run(main())
    ['ok']
    """

    def __init__(
        self,
        *,
        max_concurrency: int | None = None,
        revert_last_event_on_failure: bool = False,
    ) -> None:
        self.jobs: list[Job] = []

        self.max_concurrency = max_concurrency
        self.revert_last_event_on_failure = revert_last_event_on_failure

        self._semaphore = (
            asyncio.Semaphore(max_concurrency) if max_concurrency is not None else None
        )

    def append(self, job: Job) -> None:
        """
        Append an already-constructed job.

        Parameters
        ----------
        job : Job
            The job to append. The job's trigger is used to determine when it runs.
        """

        self.jobs.append(job)

    def __getitem__(self, item: int) -> Job:
        return self.jobs[item]

    def remove_job_if_present(self, job: Job) -> None:
        """
        Remove a job from the scheduler if it is still present.

        Parameters
        ----------
        job : Job
            The job to remove. If the job is not present, this method does nothing.
        """
        try:
            self.jobs.remove(job)
        except ValueError:
            return

    def maybe_revert_last_event(
        self,
        job: Job,
        *,
        claimed_event: TriggerEvent,
        previous_event: TriggerEvent | None,
    ) -> None:
        """
        Try to revert a job's last event to its previous value.

        If ``self.revert_last_event_on_failure`` is True, and the job's last
        event is still the claimed event, revert it to its previous value.
        This allows the job to be retried within the same token on a subsequent
        call.

        Parameters
        ----------
        job : Job
            The job whose last event may be reverted.
        claimed_event : TriggerEvent
            The trigger event that was claimed for this job.
        previous_event : TriggerEvent | None
            The trigger event that was previously stored in ``job.last_event``. If
            the job's last event is still the claimed event, it will be reverted to this
            value.
        """
        if not self.revert_last_event_on_failure:
            return
        if job.last_event == claimed_event:
            job.last_event = previous_event

    async def _execute(self, job: Job) -> object:
        if self._semaphore is None:
            return await _run_job_func(job)

        async with self._semaphore:
            return await _run_job_func(job)

    @overload
    async def run_pending(
        self,
        now: datetime | None = None,
        *,
        wait: Literal[False],
    ) -> list[JobDidNotRunType | asyncio.Task[object]]: ...

    @overload
    async def run_pending(
        self,
        now: datetime | None = None,
        *,
        wait: Literal[True] = True,
    ) -> list[object]: ...

    async def run_pending(
        self,
        now: datetime | None = None,
        *,
        wait: bool = True,
    ) -> list[JobDidNotRunType | asyncio.Task[object]] | list[object]:
        """
        Run due jobs on the event loop.

        Parameters
        ----------
        now : datetime | None, optional
            Timestamp used to evaluate triggers. Defaults to ``datetime.now()``.
        wait : bool, default True
            If True, await every due job and return concrete results (like
            ``Scheduler.run_pending``). If False, return immediately with an
            :class:`asyncio.Task` for each due job.

        Returns
        -------
        list[JobDidNotRunType | asyncio.Task[object]] | list[object]
            A list aligned with the scheduler's job snapshot.

            - Not due -> :obj:`schedium.scheduler.JobDidNotRun`
            - Due + wait=False -> :class:`asyncio.Task`
            - Due + wait=True -> the job's return value
        """

        now_dt = now if now is not None else datetime.now()
        jobs_snapshot = list(self.jobs)

        pending: list[JobDidNotRunType | asyncio.Task[object]] = []
        tasks_to_job: dict[
            asyncio.Task[object],
            tuple[Job, TriggerEvent, TriggerEvent | None],
        ] = {}

        for job in jobs_snapshot:
            claimed, event, prev_event = _claim_due_event(job, now_dt)
            if not claimed or event is None:
                pending.append(JobDidNotRun)
                continue

            task: asyncio.Task[object] = asyncio.ensure_future(self._execute(job))
            tasks_to_job[task] = (job, event, prev_event)

            if not wait:
                task.add_done_callback(
                    partial(
                        _on_task_done,
                        _scheduler=self,
                        _job=job,
                        _event=event,
                        _prev=prev_event,
                    )
                )

            pending.append(task)

        if not wait:
            return pending

        results: list[object] = []
        for item in pending:
            if item is JobDidNotRun:
                results.append(JobDidNotRun)
                continue

            # make type checkers happy. This is not completely equivalent to
            # item is JobDidNotRun because of the possibility of multiple
            # JobDidNotRun instances.
            assert not isinstance(item, JobDidNotRunType)

            task = item
            job, event, prev_event = tasks_to_job[task]
            try:
                result = await task
            except BaseException:
                logger.exception("Async job %r raised", job)
                self.maybe_revert_last_event(
                    job,
                    claimed_event=event,
                    previous_event=prev_event,
                )
                raise

            results.append(result)
            if isinstance(result, CancelJob):
                self.remove_job_if_present(job)

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
        return f"AsyncScheduler(jobs={self.jobs!r})"
