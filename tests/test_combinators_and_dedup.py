from __future__ import annotations

from datetime import datetime

from schedium import Every, Job, On, Scheduler
from schedium.triggers.base import BaseTrigger
from schedium.types.granularity import Granularity


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


def test_run_pending_evaluates_trigger_once_per_job():
    class CountingTrigger(BaseTrigger):
        def __init__(self) -> None:
            self.match_count = 0

        def matches(self, now: datetime) -> bool:
            self.match_count += 1
            return True

        def fallback_granularity(self) -> Granularity:
            return Granularity.SECOND

    trigger = CountingTrigger()
    sched = Scheduler()
    sched.append(Job(lambda: None, trigger))

    sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))

    # Before the fix run_pending called is_due() then run(), each calling
    # evaluate() → trigger.matches(). That doubled the call count to 2.
    assert trigger.match_count == 1
