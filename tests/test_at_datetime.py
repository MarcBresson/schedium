from __future__ import annotations

from datetime import datetime

from schedium import AtDateTime, Job, Scheduler


def test_at_datetime_runs_once_even_if_late():
    run_at = datetime(2026, 2, 4, 10, 0, 0)
    trigger = AtDateTime(run_date=run_at)

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    # Before : not due
    sched.run_pending(now=datetime(2026, 2, 4, 9, 59, 59))
    assert ran == []

    # Exactly : due
    sched.run_pending(now=run_at)
    assert ran == [1]

    # Later : should not run again
    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 1))
    assert ran == [1]


def test_at_datetime_with_constraints():
    # Even if evaluated later, AND with constraints should still run once.
    run_at = datetime(2026, 2, 4, 10, 0, 0)
    trigger = AtDateTime(run_date=run_at)

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))
    assert ran == [1]

    sched.run_pending(now=datetime(2026, 2, 4, 10, 6, 0))
    assert ran == [1]
