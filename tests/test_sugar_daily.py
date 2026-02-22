from __future__ import annotations

from datetime import datetime, time

from schedium import Daily, Job


def test_daily_without_at_datetime_of_next_run_is_immediate():
    t = Daily()
    after = datetime(2026, 2, 3, 9, 12, 5)
    assert Job(lambda: None, t).datetime_of_next_run(after) == after


def test_daily_at_hhmm_datetime_of_next_run_same_day():
    t = Daily(at="09:30")
    assert Job(lambda: None, t).datetime_of_next_run(
        datetime(2026, 2, 3, 9, 12, 5)
    ) == datetime(2026, 2, 3, 9, 30, 0)


def test_daily_at_time_object_datetime_of_next_run_next_day_if_missed():
    t = Daily(at=time(9, 30, 15))
    assert Job(lambda: None, t).datetime_of_next_run(
        datetime(2026, 2, 3, 9, 31, 0)
    ) == datetime(2026, 2, 4, 9, 30, 15)
