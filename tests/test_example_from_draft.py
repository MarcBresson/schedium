from __future__ import annotations

from datetime import datetime

from pyscheduler import Between, Every, On


def test_example_from_interface_first_draft():
    # every monday for every hour between 9am and 5pm on minute 12 and on minute 55
    example = (
        Every(unit="minute", interval=1)
        & On(unit="day_of_week", value=1)
        & Between(unit="hour_of_day", start=9, end=17)
        & (On(unit="minute_of_hour", value=55) | On(unit="minute_of_hour", value=12))
    )

    assert example.matches(datetime(2026, 2, 2, 9, 12, 0))
    assert example.matches(datetime(2026, 2, 2, 9, 55, 0))
    assert not example.matches(datetime(2026, 2, 2, 9, 13, 0))
    assert not example.matches(datetime(2026, 2, 3, 9, 12, 0))  # Tuesday
