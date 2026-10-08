"""
Data passed to plugins while a job runs.

:class:`RunContext` describes one *execution* of a job and :class:`RunStatus`
is the outcome it ends up with.
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from schedium.job import Job
    from schedium.triggers.base import TriggerEvent


class RunStatus(str, Enum):
    """Outcome of one job execution."""

    RUNNING = "running"
    """The job has started and has not finished yet."""

    SUCCESS = "success"
    """The job returned normally."""

    FAILED = "failed"
    """The job raised an exception (see :attr:`RunContext.exception`)."""

    CANCELLED = "cancelled"
    """
    The job returned :class:`~schedium.types.cancel_job.CancelJob`, which
    unregisters it from its scheduler (see :attr:`RunContext.cancel_reason`).
    """

    INTERRUPTED = "interrupted"
    """
    The run was cut short by something that is not a job error, for example
    the asyncio task was cancelled because :meth:`AsyncScheduler.stop
    <schedium.asyncio.AsyncScheduler.stop>` gave up waiting, or the process got
    a :class:`KeyboardInterrupt`.
    """

    SKIPPED = "skipped"
    """
    A plugin's ``wrap_run`` hook decided not to call the job at all (it never
    called ``call_next``).
    """


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class RunContext:
    """
    Everything a plugin may want to know about one execution of a job.

    A fresh context is created for every run and passed to each per-run hook of
    :class:`~schedium.plugins.Plugin`. It is mutable on purpose: the runner fills
    in :attr:`status`, :attr:`result` and the other outcome fields as the run
    progresses.

    Attributes
    ----------
    job : Job
        The job being executed.
    scheduler : object, optional
        The scheduler that triggered the run, or None when the job was run
        manually with :meth:`schedium.job.Job.run`.
    scheduler_kind : str, default "manual"
        Class name of the scheduler (for example ``"AsyncScheduler"``), or
        ``"manual"``.
    event : TriggerEvent, optional
        The trigger event (time bucket) that made the job due.
    run_id : str
        Unique identifier of this execution (random UUID4 hex).
    started_at : datetime
        When the run started, timezone-aware UTC.
    ended_at : datetime, optional
        When the run ended, timezone-aware UTC. None while running.
    status : RunStatus
        Current status. :attr:`RunStatus.RUNNING` until the run ends.
    result : object
        The value returned by the job (after ``wrap_run`` hooks).
    exception : BaseException, optional
        The exception that ended the run, if any.
    cancel_reason : str, optional
        The reason carried by :class:`~schedium.types.cancel_job.CancelJob`.
    extras : dict[str, Any]
        Free-form scratch space for plugins. Use a key that is unique to your
        plugin (its name, for instance) to avoid clashes.
    """

    job: Job
    scheduler: object | None = None
    scheduler_kind: str = "manual"
    event: TriggerEvent | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: datetime = field(default_factory=_utcnow)
    ended_at: datetime | None = None
    status: RunStatus = RunStatus.RUNNING
    result: object = None
    exception: BaseException | None = None
    cancel_reason: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def duration(self) -> float | None:
        """Run duration in seconds, or None while the run is still going."""
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at).total_seconds()


_current_run: ContextVar[RunContext | None] = ContextVar(
    "schedium_current_run", default=None
)


def get_current_run() -> RunContext | None:
    """
    Return the :class:`RunContext` of the job running in the current context.

    The run is tracked with a :class:`contextvars.ContextVar`, so the answer is
    correct per thread *and* per asyncio task: several jobs running at the same
    time each see their own run. This is what lets code that cannot receive the
    context as an argument (a :class:`logging.Handler`, or the job body itself)
    know which run it belongs to.

    Returns
    -------
    RunContext or None
        The current run, or None when called outside of a job run.
    """
    return _current_run.get()
