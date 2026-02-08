from __future__ import annotations

from datetime import datetime

from schedium import Between, Every, Job, On, Scheduler


def test_every_2_hours_alignment():
    trigger = Every(unit="hour", interval=2) & On(unit="minute_of_hour", value=0)

    ran: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran.append(1), trigger))

    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 11, 0, 0))
    sched.run_pending(now=datetime(2026, 2, 4, 12, 0, 0))

    assert ran == [1, 1]


def test_between_day_of_week_accepts_1_to_7():
    # 1..5 = Monday..Friday
    is_weekday = Between(unit="day_of_week", start=1, end=5)

    assert is_weekday.matches(datetime(2026, 2, 2, 12, 0, 0))  # Monday
    assert is_weekday.matches(datetime(2026, 2, 6, 12, 0, 0))  # Friday
    assert not is_weekday.matches(datetime(2026, 2, 7, 12, 0, 0))  # Saturday


def test_second_and_millisecond_granularity_dedup():
    second_trigger = Every(unit="second", interval=1)
    milli_trigger = Every(unit="millisecond", interval=1)

    ran_s: list[int] = []
    ran_ms: list[int] = []
    sched = Scheduler()
    sched.append(Job(lambda: ran_s.append(1), second_trigger))
    sched.append(Job(lambda: ran_ms.append(1), milli_trigger))

    t = datetime(2026, 2, 4, 10, 0, 0, 123456)
    sched.run_pending(now=t)
    sched.run_pending(now=t)  # dedup same token

    assert ran_s == [1]
    assert ran_ms == [1]

    # Next second changes the second bucket; should run again.
    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 1, 1))
    assert ran_s == [1, 1]
    assert ran_ms == [1, 1]

    # Next millisecond changes the ms bucket; should run again.
    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 1, 2000))
    assert ran_ms == [1, 1, 1]
