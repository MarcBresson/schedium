from __future__ import annotations

from datetime import datetime

from schedium import Between, Every, Job, On, Scheduler


def test_every_5_minutes():
    trigger = Every(unit="minute", interval=5)
    sched = Scheduler()
    ran: list[int] = []
    sched.append(Job(lambda: ran.append(1), trigger))

    # Not on boundary => no run
    sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
    assert ran == []

    # On boundary => runs once
    sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))
    assert ran == [1]

    # Same timestamp => dedup
    sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))
    assert ran == [1]

    # Next boundary => runs
    sched.run_pending(now=datetime(2026, 2, 4, 10, 10, 0))
    assert ran == [1, 1]


def test_every_hour_between_9_17_on_minute_55():
    # Every hour between 9 and 17 inclusive, at minute 55.
    trigger = (
        Every(unit="minute", interval=1)
        & Between(unit="hour_of_day", start=9, end=17)
        & On(unit="minute_of_hour", value=55)
    )

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    # Wrong minute
    sched.run_pending(now=datetime(2026, 2, 4, 9, 54, 0))
    assert ran == []

    # Correct
    sched.run_pending(now=datetime(2026, 2, 4, 9, 55, 0))
    assert ran == [1]

    # Dedup within same minute
    sched.run_pending(now=datetime(2026, 2, 4, 9, 55, 0))
    assert ran == [1]

    # Next hour
    sched.run_pending(now=datetime(2026, 2, 4, 10, 55, 0))
    assert ran == [1, 1]

    # Outside window
    sched.run_pending(now=datetime(2026, 2, 4, 18, 55, 0))
    assert ran == [1, 1]


def test_every_weekday_at_8am():
    trigger = (
        Every(unit="day", interval=1)
        & On(unit="weekdays", value=1)
        & On(unit="hour_of_day", value=8)
    )

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    # 2026-02-02 is Monday
    sched.run_pending(now=datetime(2026, 2, 2, 8, 0, 0))
    assert ran == [1]

    # Same day, same hour boundary => dedup
    sched.run_pending(now=datetime(2026, 2, 2, 8, 0, 0))
    assert ran == [1]

    # Tuesday
    sched.run_pending(now=datetime(2026, 2, 3, 8, 0, 0))
    assert ran == [1, 1]

    # Saturday should not run
    sched.run_pending(now=datetime(2026, 2, 7, 8, 0, 0))
    assert ran == [1, 1]


def test_on_day_of_week_is_constraint():
    # Value 1 means Monday in cron-style; 0 means Monday in python-style.
    monday_cron = On(unit="day_of_week", value=1)
    monday_py = On(unit="day_of_week", value=0)

    assert monday_cron.matches(datetime(2026, 2, 2, 12, 34, 56))
    assert monday_py.matches(datetime(2026, 2, 2, 12, 34, 56))
    assert not monday_cron.matches(datetime(2026, 2, 3, 12, 34, 56))
