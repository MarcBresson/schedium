"""The :class:`Plugin` base class."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from schedium.job import Job
    from schedium.plugins.context import RunContext


class Plugin:
    """
    Base class for schedium plugins.

    A plugin is an object with optional hook methods. Subclass it and override
    only the hooks you need; every hook is a no-op by default. Plugins are
    attached to a scheduler (``Scheduler(plugins=[...])``) or to a single job
    (``Job(..., plugins=[...])``).

    There are two kinds of hooks:

    - *Observer hooks* (``on_*``) are notified at fixed moments. They cannot
      change what the job does. An exception raised in an observer hook is
      logged on the ``schedium.plugins`` logger and otherwise ignored, so a
      broken plugin never fails a job or prevents other plugins from running.
    - *Wrap hooks* (:meth:`wrap_run` and :meth:`wrap_run_async`) surround the
      job call. They can skip the job, call it several times (retry), time it
      out or replace its result. Exceptions raised by a wrap hook are **not**
      swallowed: they become the outcome of the run.

    Attributes
    ----------
    blocking : bool
        Set to True when the plugin's hooks do blocking I/O (files, databases,
        network). :class:`~schedium.asyncio.AsyncScheduler` then runs them in a
        worker thread instead of on the event loop. Hooks must therefore be
        thread-safe. Ignored by the threaded schedulers, which never run on an
        event loop.

    Notes
    -----
    Order
        Per-run hooks of scheduler plugins run before those of job plugins.
        ``on_job_start`` runs in registration order; ``on_job_success``,
        ``on_job_failure``, ``on_job_cancelled`` and ``on_job_end`` run in
        reverse order, like nested context managers. Wrap hooks nest the same
        way: the first scheduler plugin is the outermost layer.

    Threads
        With the threaded schedulers, per-run hooks run in the worker thread
        that executes the job. Scheduler lifecycle hooks may run in whichever
        thread starts or stops the scheduler.

    Examples
    --------
    >>> from schedium import Plugin
    >>> class Announce(Plugin):
    ...     def on_job_start(self, run):
    ...         print("starting", run.job.identifier)
    """

    blocking: bool = False

    # -- scheduler lifecycle ------------------------------------------------

    def on_scheduler_start(self, scheduler: Any) -> None:
        """
        Called when a scheduler starts.

        Fired by :meth:`AsyncScheduler.start <schedium.asyncio.AsyncScheduler.start>`,
        :meth:`QueuedJobsScheduler.start_workers
        <schedium.threading.QueuedJobsScheduler.start_workers>` and
        :meth:`SchedulerThread.start <schedium.threading.SchedulerThread.start>`
        (when it drives a plain :class:`~schedium.scheduler.Scheduler`).

        Parameters
        ----------
        scheduler : object
            The scheduler that is starting.
        """

    def on_scheduler_stop(self, scheduler: Any) -> None:
        """
        Called when a scheduler stops.

        Fired by :meth:`AsyncScheduler.stop <schedium.asyncio.AsyncScheduler.stop>`,
        :meth:`QueuedJobsScheduler.stop_workers
        <schedium.threading.QueuedJobsScheduler.stop_workers>`,
        :meth:`ThreadedJobsScheduler.shutdown
        <schedium.threading.ThreadedJobsScheduler.shutdown>` and
        :meth:`SchedulerThread.stop <schedium.threading.SchedulerThread.stop>`
        (when it drives a plain :class:`~schedium.scheduler.Scheduler`). Use it
        to flush and release resources. It may be called more than once, so
        implement it idempotently.

        Parameters
        ----------
        scheduler : object
            The scheduler that is stopping.
        """

    def on_job_added(self, scheduler: Any, job: Job) -> None:
        """
        Called when a job is appended to a scheduler.

        Parameters
        ----------
        scheduler : object
            The scheduler the job was added to.
        job : Job
            The job that was added.
        """

    def on_job_removed(self, scheduler: Any, job: Job, reason: str | None) -> None:
        """
        Called when a scheduler removes a job (it cancelled itself).

        Parameters
        ----------
        scheduler : object
            The scheduler the job was removed from.
        job : Job
            The job that was removed.
        reason : str, optional
            The reason given to :class:`~schedium.types.cancel_job.CancelJob`.
        """

    # -- per-run hooks ------------------------------------------------------

    def on_job_start(self, run: RunContext) -> None:
        """
        Called right before a job runs.

        Parameters
        ----------
        run : RunContext
            The run that is starting (``run.status`` is
            :attr:`~schedium.plugins.RunStatus.RUNNING`).
        """

    def on_job_success(self, run: RunContext) -> None:
        """
        Called when a job returned normally.

        Parameters
        ----------
        run : RunContext
            The finished run (``run.result`` holds the return value).
        """

    def on_job_failure(self, run: RunContext) -> None:
        """
        Called when a job raised an exception.

        The exception is still re-raised to the scheduler afterwards.

        Parameters
        ----------
        run : RunContext
            The finished run (``run.exception`` holds the exception).
        """

    def on_job_cancelled(self, run: RunContext) -> None:
        """
        Called when a job returned :class:`~schedium.types.cancel_job.CancelJob`.

        Parameters
        ----------
        run : RunContext
            The finished run (``run.cancel_reason`` holds the reason).
        """

    def on_job_end(self, run: RunContext) -> None:
        """
        Called after every run, whatever its outcome (like ``finally``).

        It also fires for runs that were skipped or interrupted, for which none
        of ``on_job_success``, ``on_job_failure`` or ``on_job_cancelled`` fire.
        Check ``run.status`` to know what happened.

        Parameters
        ----------
        run : RunContext
            The finished run, with ``ended_at`` and ``status`` set.
        """

    # -- wrap hooks ---------------------------------------------------------

    def wrap_run(self, run: RunContext, call_next: Callable[[], object]) -> object:
        """
        Surround the job call (used by every scheduler except the async one).

        Override this to change behaviour. The default implementation just
        calls the next layer. A plugin that does not override this method does
        not take part in the wrap chain at all.

        Parameters
        ----------
        run : RunContext
            The current run.
        call_next : Callable[[], object]
            Calls the next plugin, or the job itself for the innermost plugin.
            You may call it zero times (skip), once, or several times (retry).

        Returns
        -------
        object
            The value that becomes the result of the run.

        Examples
        --------
        >>> from schedium import Plugin
        >>> class Retry(Plugin):
        ...     def wrap_run(self, run, call_next):
        ...         for attempt in range(3):
        ...             try:
        ...                 return call_next()
        ...             except Exception:
        ...                 if attempt == 2:
        ...                     raise
        """
        return call_next()

    async def wrap_run_async(
        self, run: RunContext, call_next: Callable[[], Awaitable[object]]
    ) -> object:
        """
        Surround the job call on :class:`~schedium.asyncio.AsyncScheduler`.

        The asynchronous counterpart of :meth:`wrap_run`. A plugin that wants to
        change behaviour on every scheduler implements both.

        Parameters
        ----------
        run : RunContext
            The current run.
        call_next : Callable[[], Awaitable[object]]
            Calls the next layer; ``await`` the result.

        Returns
        -------
        object
            The value that becomes the result of the run.
        """
        return await call_next()
