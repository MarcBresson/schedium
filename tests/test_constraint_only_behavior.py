from __future__ import annotations

import pytest

from schedium import Job, On, Scheduler


def test_constraint_only_trigger_fires_once_per_day_when_first_seen():
    trigger = On(unit="day_of_week", value=1)

    ran: list[int] = []
    sched = Scheduler()
    with pytest.raises(ValueError):
        sched.append(Job(lambda: ran.append(1), trigger))
