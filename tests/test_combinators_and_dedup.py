from __future__ import annotations

from datetime import datetime

from schedium import Every, Job, On, Scheduler


def test_or_on_minutes():
    trigger = Every(unit="minute", interval=1) & (
        On(unit="minute_of_hour", value=55) | On(unit="minute_of_hour", value=12)
    )

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    sched.run_pending(now=datetime(2026, 2, 4, 9, 12, 0))
    assert ran == [1]
    sched.run_pending(now=datetime(2026, 2, 4, 9, 13, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 9, 55, 0))
    assert ran == [1, 1]
    sched.run_pending(now=datetime(2026, 2, 4, 10, 12, 30))
    assert ran == [1, 1, 1]


def test_scheduler_dedupplication_bucket():
    trigger = Every(unit="minute", interval=1)

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    assert ran == [1]

    sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    assert ran == [1, 1]
