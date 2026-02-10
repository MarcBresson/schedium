from __future__ import annotations

import logging
from datetime import datetime

import pytest

from schedium import Every, Job, Scheduler
from schedium.types.cancel_job import CancelJob
from schedium.utils import cancel_job_on_failure


def test_cancel_job_on_failure_decorator_catches_logs_and_cancels(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.ERROR)

    sched = Scheduler()

    @cancel_job_on_failure(
        cancel=True,
        catch=(ValueError,),
        logger=logging.getLogger("schedium.test"),
        log_message="task blew up",
    )
    def task():
        raise ValueError("boom")

    sched.append(Job(task, Every(unit="minute", interval=1)))

    results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    assert len(results) == 1
    assert isinstance(results[0], CancelJob)
    assert "ValueError: boom" in (results[0].reason or "")

    # The exception must be logged.
    assert any("task blew up" in rec.getMessage() for rec in caplog.records)
    assert any(rec.exc_info is not None for rec in caplog.records)

    # Job removed from scheduler.
    assert sched.jobs == []


def test_cancel_job_on_failure_decorator_can_swallow_without_cancelling(
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.ERROR)

    sched = Scheduler()

    @cancel_job_on_failure(
        cancel=False,
        catch=(ValueError,),
        logger=logging.getLogger("schedium.test"),
        log_message="task failed but kept",
    )
    def task():
        raise ValueError("boom")

    sched.append(Job(task, Every(unit="minute", interval=1)))

    results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    assert results == [None]
    assert len(sched.jobs) == 1

    # Logged, but job not cancelled.
    assert any("task failed but kept" in rec.getMessage() for rec in caplog.records)

    # Next minute: job runs again (since it's still scheduled).
    results2 = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    assert results2 == [None]


def test_cancel_job_on_failure_decorator_does_not_catch_unlisted_exceptions():
    sched = Scheduler()

    @cancel_job_on_failure(cancel=True, catch=(ValueError,))
    def task():
        raise TypeError("not caught")

    sched.append(Job(task, Every(unit="minute", interval=1)))

    with pytest.raises(TypeError):
        sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))

    # Job is still present; failure propagated.
    assert len(sched.jobs) == 1
