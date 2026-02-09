from __future__ import annotations

from datetime import datetime

from schedium import Job, On, Scheduler


def test_constraint_only_trigger_runs_when_observed_within_bucket():
    # Monday constraint; bucket is DAY.
    trigger = On(unit="day_of_week", value=1)

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    # First observation on Monday runs immediately.
    sched.run_pending(now=datetime(2026, 2, 2, 15, 37, 0))
    # Still Monday: dedup prevents repeat runs within the same DAY bucket.
    sched.run_pending(now=datetime(2026, 2, 2, 18, 0, 0))
    assert ran == [1]

    # Tuesday doesn't match.
    sched.run_pending(now=datetime(2026, 2, 3, 8, 0, 0))
    assert ran == [1]


def test_constraint_only_trigger_can_be_appended():
    trigger = On(unit="day_of_week", value=1)

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))
    sched.run_pending(now=datetime(2026, 2, 2, 0, 0, 0))
