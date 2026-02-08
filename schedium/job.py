"""Job definition.

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

from collections.abc import Callable
from datetime import datetime

from schedium.triggers import BaseTrigger
from schedium.triggers.base import TriggerEvent
from schedium.utils.evaluate import evaluate


class Job:
    """A scheduled unit of work.

    Parameters
    ----------
    func : Callable[[], object]
        A zero-argument callable. The return value is returned by
        :meth:`run` and by :meth:`schedium.scheduler.Scheduler.run_pending`.
        If you need to pass arguments, wrap them in a closure or `functools.partial`.
    trigger : BaseTrigger
        The trigger that decides when this job is due.
    name : str, default: None
        Optional human-readable label used in `repr(job)`.

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
    ):
        self.func = func
        self.trigger = trigger
        self.name = name

        self.last_event: TriggerEvent | None = None

    def is_due(self, now: datetime) -> bool:
        """Return True if the job should run at ``now``.

        A job is due when:

        1) its trigger matches at ``now`` and yields an event token, and
        2) that token is different from the last token the job already ran for.

        This method does not mutate state.
        """
        event = evaluate(self.trigger, now)
        if event is None:
            return False
        return event != self.last_event

    def run(self, now: datetime) -> object:
        """Run the job if due, update :attr:`last_event`, and return the result.

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

        result = self.func()
        self.last_event = event
        return result

    def datetime_of_next_run(
        self,
        after: datetime | None = None,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        """Return the next run datetime for this job.

        This is derived from the trigger's next validity window.

        Parameters
        ----------
        after : datetime, optional
            Lower bound (inclusive) for the computed next run time. If omitted,
            uses the current system time.
        max_iterations:
            Safety cap used by some triggers/combinators that scan forward.
        """
        if after is None:
            after = datetime.now()

        window = self.trigger.next_window(after, max_iterations=max_iterations)
        return None if window is None else window.start

    def __repr__(self) -> str:
        return f"Job(name={self.name!r}, func={self.func!r}, trigger={self.trigger!r})"
