from __future__ import annotations

from datetime import datetime

from schedium import CancelJob, Every, Job, Scheduler


def test_job_can_cancel_itself_by_returning_canceljob():
    sched = Scheduler()

    calls: list[int] = []

    def run_once_then_cancel():
        calls.append(1)
        return CancelJob("done")

    sched.append(Job(run_once_then_cancel, Every(unit="minute", interval=1)))

    results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    assert len(results) == 1
    assert isinstance(results[0], CancelJob)
    assert calls == [1]

    # Job removed from scheduler.
    assert sched.jobs == []

    # Next minute: nothing to run.
    assert sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0)) == []


def test_cancelling_one_job_does_not_prevent_others():
    sched = Scheduler()

    cancelled_calls: list[int] = []
    normal_calls: list[int] = []

    def cancel_job():
        cancelled_calls.append(1)
        return CancelJob("stop")

    def normal_job():
        normal_calls.append(1)
        return "ok"

    sched.append(Job(cancel_job, Every(unit="minute", interval=1), name="cancel"))
    sched.append(Job(normal_job, Every(unit="minute", interval=1), name="normal"))

    results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    assert len(results) == 2
    assert isinstance(results[0], CancelJob)
    assert results[1] == "ok"

    # Only the cancelling job is removed.
    assert len(sched.jobs) == 1
    assert sched.jobs[0].name == "normal"

    # Next minute: normal job runs again.
    results2 = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    assert results2 == ["ok"]
    assert cancelled_calls == [1]
    assert normal_calls == [1, 1]
