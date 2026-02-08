from __future__ import annotations

from datetime import datetime, time

from schedium import Job, Weekly


def test_weekly_day_string_datetime_of_next_run():
    t = Weekly("monday")
    # 2026-02-03 is Tuesday; next Monday is 2026-02-09.
    assert Job(lambda: None, t).datetime_of_next_run(
        datetime(2026, 2, 3, 9, 12, 5)
    ) == datetime(2026, 2, 9, 0, 0, 0)


def test_weekly_at_hhmm_datetime_of_next_run():
    t = Weekly("mon", at="09:30")
    assert Job(lambda: None, t).datetime_of_next_run(
        datetime(2026, 2, 3, 9, 12, 5)
    ) == datetime(2026, 2, 9, 9, 30, 0)


def test_weekly_at_time_object_datetime_of_next_run():
    t = Weekly("monday", at=time(9, 30, 15))
    assert Job(lambda: None, t).datetime_of_next_run(
        datetime(2026, 2, 3, 9, 12, 5)
    ) == datetime(2026, 2, 9, 9, 30, 15)


def test_weekly_accepts_iso_int_weekday():
    # ISO: Monday=1
    t = Weekly(1, at="09:00")
    assert Job(lambda: None, t).datetime_of_next_run(
        datetime(2026, 2, 3, 9, 12, 5)
    ) == datetime(2026, 2, 9, 9, 0, 0)
