"""Decorator support for registering jobs on a scheduler."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TypeVar

from schedium.job import Job
from schedium.plugins.base import Plugin
from schedium.triggers.base import BaseTrigger

F = TypeVar("F", bound=Callable[[], object])


def job_decorator(
    scheduler: object,
    trigger: BaseTrigger,
    name: str | None = None,
    *,
    job_id: str | None = None,
    plugins: Iterable[Plugin] = (),
) -> Callable[[F], F]:
    """
    Build a decorator that registers the decorated function as a `Job`.

    Parameters
    ----------
    scheduler : object
        Any scheduler exposing ``append(job: Job)``.
    trigger : BaseTrigger
        When the job runs.
    name : str, default None
        Human-readable label; defaults to the function's name via
        :attr:`schedium.job.Job.identifier`.
    job_id : str, default None
        Stable identifier used by history plugins.
    plugins : Iterable[Plugin], default ()
        Plugins applied to this job only.

    Returns
    -------
    Callable[[F], F]
        A decorator that appends the function as a job and returns it unchanged.
    """

    def decorator(func: F) -> F:
        scheduler.append(  # type: ignore[attr-defined]
            Job(func, trigger=trigger, name=name, id=job_id, plugins=plugins)
        )
        return func

    return decorator
