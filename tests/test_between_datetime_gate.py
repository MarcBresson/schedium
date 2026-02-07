from __future__ import annotations

from datetime import datetime

from pyscheduler import BetweenDateTime, Every, Job, Scheduler


def test_between_datetime_as_gate():
    gate = BetweenDateTime(
        start_date=datetime(2026, 2, 4, 10, 0, 0),
        end_date=datetime(2026, 2, 4, 10, 2, 0),
    )
    trigger = Every(unit="minute", interval=1) & gate

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    sched.run_pending(now=datetime(2026, 2, 4, 9, 59, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 10, 2, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 10, 3, 0))

    assert ran == [1, 1, 1]
