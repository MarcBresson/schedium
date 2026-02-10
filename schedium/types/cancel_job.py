from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CancelJob:
    """
    Return value that cancels (removes) the current job.

    If a job's callable returns an instance of :class:`~schedium.types.cancel_job.CancelJob`,
    :meth:`schedium.scheduler.Scheduler.run_pending` will remove that job from
    the scheduler.

    Attributes
    ----------
    reason : str | None, default None
        Optional human-readable reason for cancellation.
    """

    reason: str | None = None
