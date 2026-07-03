"""
Provides a default, ready-to-use `Scheduler` instance and convenient helper functions for managing scheduled jobs.

It enables both quick scripting and integration with the broader schedium API. For more control, use the `Scheduler` class directly.

Attributes
----------------

- ``default_scheduler``: The default `Scheduler` instance (internal, use helpers below).
- ``run_pending()``: Run all jobs that are scheduled to run at the current time.
- ``add_job(job, trigger=None, name=None)``: Add a job to the default scheduler. Accepts either a `Job` object or a function+trigger pair.
- ``append(job)``: Alias for `add_job` for compatibility with other schedium APIs.

See Also
--------

schedium.Scheduler: for the full Scheduler API.
schedium.Job: for the Job class and related functionality.
schedium.triggers: for available trigger types and how to create them.

Examples
--------

    from schedium.default import add_job, run_pending, Job
    from schedium import Every

    def my_task():
        print("Task executed!")

    # Add a job using a function and trigger:
    add_job(my_task, trigger=Every(unit="second", interval=5))
    # You can also add a Job object directly:
    job = Job(my_task, trigger=Every(unit="second", interval=10))
    add_job(job)

    run_pending()
"""

from collections.abc import Callable
from typing import overload

from schedium.job import Job
from schedium.scheduler import Scheduler
from schedium.triggers.base import BaseTrigger

default_scheduler = Scheduler()


def run_pending() -> None:
    default_scheduler.run_pending()


@overload
def add_job(job: Job) -> None: ...


@overload
def add_job(
    job: Callable[[], object], trigger: BaseTrigger, name: str | None = None
) -> None: ...


def add_job(
    job: Job | Callable[[], object],
    trigger: BaseTrigger | None = None,
    name: str | None = None,
) -> None:
    if not isinstance(job, Job):
        if trigger is None:
            raise ValueError("trigger must be provided when job is not a Job instance")
        job = Job(job, trigger=trigger, name=name)
    default_scheduler.append(job)


append = add_job
