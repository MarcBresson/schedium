"""
Job definition.

A :class:`~schedium.job.Job` couples:

- a *callable* (your work), and
- a *trigger* (when to run).

Jobs are intentionally small and stateful: each job tracks the last trigger
event it ran for so it can deduplicate repeated calls to
:meth:`schedium.scheduler.Scheduler.run_pending`.

Most users will construct jobs directly and register them via
:meth:`schedium.scheduler.Scheduler.append`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from schedium.plugins._runner import run_sync
from schedium.plugins.base import Plugin
from schedium.triggers import BaseTrigger
from schedium.triggers.base import TriggerEvent
from schedium.utils.evaluate import evaluate


class Job:
    """
    A scheduled unit of work.

    Parameters
    ----------
    func : Callable[[], object]
        A zero-argument callable. The return value is returned by
        :meth:`run` and by :meth:`schedium.scheduler.Scheduler.run_pending`.
        If you need to pass arguments, wrap them in a closure or `functools.partial`.
    trigger : BaseTrigger
        The trigger that decides when this job is due.
    name : str, default None
        Optional human-readable label used in `repr(job)`.
    id : str, default None
        Optional stable identifier. Plugins that keep history (for example run
        traces) use it to tell jobs apart across restarts. See
        :attr:`identifier`.
    plugins : Iterable[Plugin], default ()
        Plugins that apply to this job only, in addition to the plugins of the
        scheduler running it. See :class:`~schedium.plugins.Plugin`.

    Notes
    -----
    Deduplication
        A job runs at most once per trigger *event token*.

        Internally, :func:`schedium.utils.evaluate.evaluate` turns a trigger
        match into a :class:`schedium.triggers.base.TriggerEvent`. The
        event's token typically represents a *time bucket* (minute/hour/day, etc.).
        If the scheduler is called multiple times within the same bucket, the
        job is considered not due after the first run.

    State
        Jobs are stateful: :attr:`last_event` is updated on successful
        :meth:`run`. If you want the same callable to run under multiple
        independent schedules, create multiple :class:`Job` instances.

    Threading
        Jobs do not run in separate threads/processes by default.
        The scheduler runs them inline.
    """

    def __init__(
        self,
        func: Callable[[], object],
        trigger: BaseTrigger,
        name: str | None = None,
        *,
        id: str | None = None,
        plugins: Iterable[Plugin] = (),
    ):
        self.func = func
        self.trigger = trigger
        self.name = name
        self.id = id
        self.plugins: list[Plugin] = list(plugins)

        self.last_event: TriggerEvent | None = None

    @property
    def identifier(self) -> str:
        """
        Stable label that identifies this job in traces and logs.

        It is :attr:`id` if given, otherwise :attr:`name`, otherwise the
        ``module.qualname`` of the callable (``repr`` for callables without
        one). History stays attached to the same job across restarts as long as
        that value does not change.
        """
        if self.id is not None:
            return self.id
        if self.name is not None:
            return self.name
        func = self.func
        while hasattr(func, "func"):  # functools.partial
            func = func.func
        qualname = getattr(func, "__qualname__", None)
        if qualname is None:
            return repr(self.func)
        return f"{getattr(func, '__module__', '?')}.{qualname}"

    def is_due(self, now: datetime) -> bool:
        """
        Return True if the job should run at ``now``.

        A job is due when:

        1) its trigger matches at ``now`` and yields an event token, and
        2) that token is different from the last token the job already ran for.

        This method does not mutate state.

        Parameters
        ----------
        now : datetime
            Timestamp used to evaluate the trigger.

        Returns
        -------
        bool
            True if the job is due at ``now``.
        """
        event = evaluate(self.trigger, now)
        if event is None:
            return False
        return event != self.last_event

    def run(self, now: datetime) -> object:
        """
        Run the job if due, update :attr:`last_event`, and return the result.

        Parameters
        ----------
        now : datetime
            Timestamp used to evaluate the trigger.

        Returns
        -------
        object
            The callable's return value.

        Raises
        ------
        RuntimeError
            If called when the job is not due, or if called again for the same
            trigger token (double-run protection).
        """
        event = evaluate(self.trigger, now)
        if event is None:
            raise RuntimeError("Job.run() called when job is not due")
        if event == self.last_event:
            raise RuntimeError("Job.run() called but job already ran for this token")

        result = run_sync(self, event=event)
        self.last_event = event
        return result

    def run_func(self) -> object:
        """
        Run the job's callable without checking triggers or updating state.

        Particularly useful to override in subclasses that want to customize
        the run behavior while keeping the same trigger-based scheduling
        logic.

        Returns
        -------
        object
            The callable's return value.
        """
        return self.func()

    def datetime_of_next_run(
        self,
        after: datetime | None = None,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        """
        Return the next run datetime for this job.

        This is derived from the trigger's next validity window.

        Parameters
        ----------
        after : datetime, optional
            Lower bound (inclusive) for the computed next run time. If omitted,
            uses the current system time.
        max_iterations : int, default 100_000
            Safety cap used by some triggers/combinators that scan forward.

        Returns
        -------
        datetime | None
            The earliest datetime at which this job is due, or :obj:`None` if the
            trigger tree cannot produce a next window.
        """
        if after is None:
            after = datetime.now()

        window = self.trigger.next_window(after, max_iterations=max_iterations)
        return None if window is None else window.start

    def __repr__(self) -> str:
        return f"Job(name={self.name!r}, func={self.func!r}, trigger={self.trigger!r})"
