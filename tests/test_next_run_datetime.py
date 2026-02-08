from __future__ import annotations

from datetime import datetime

import pytest

from schedium import AtDateTime, Between, BetweenDateTime, Every, Job, On
from schedium.exceptions import NextRunMaxIterationsReached


@pytest.mark.parametrize(
    ("trigger", "after", "expected"),
    [
        # Base triggers (use eager scanning + fallback granularity)
        (
            On(unit="hour_of_day", value=9),
            datetime(2026, 2, 2, 8, 59, 59),
            datetime(2026, 2, 2, 9, 0, 0),
        ),
        (
            Between(unit="hour_of_day", start=9, end=17),
            datetime(2026, 2, 2, 8, 0, 0),
            datetime(2026, 2, 2, 9, 0, 0),
        ),
        # If it already matches, we return `after` exactly.
        (
            Between(unit="hour_of_day", start=9, end=17),
            datetime(2026, 2, 2, 9, 30, 5),
            datetime(2026, 2, 2, 9, 30, 5),
        ),
        # day_of_week=1 is Monday (cron/isoweekday)
        (
            On(unit="day_of_week", value=1),
            datetime(2026, 2, 3, 9, 12, 5),
            datetime(2026, 2, 9, 0, 0, 0),
        ),
        # Weekday constraint: next match from Saturday is Monday 00:00.
        (
            On(unit="weekdays"),
            datetime(2026, 2, 7, 12, 0, 0),
            datetime(2026, 2, 9, 0, 0, 0),
        ),
        (
            Between(unit="day_of_week", start=1, end=5),
            datetime(2026, 2, 7, 12, 0, 0),
            datetime(2026, 2, 9, 0, 0, 0),
        ),
    ],
)
def test_datetime_of_next_run_base_triggers(trigger, after, expected):
    j = Job(lambda: None, trigger)
    assert j.datetime_of_next_run(after) == expected


def test_datetime_of_next_run_between_datetime_trigger_fast_path():
    t = BetweenDateTime(
        start_date=datetime(2026, 2, 2, 9, 0, 0),
        end_date=datetime(2026, 2, 2, 10, 0, 0),
    )
    j = Job(lambda: None, t)
    assert j.datetime_of_next_run(datetime(2026, 2, 2, 8, 0, 0)) == datetime(
        2026, 2, 2, 9, 0, 0
    )
    assert j.datetime_of_next_run(datetime(2026, 2, 2, 9, 30, 0)) == datetime(
        2026, 2, 2, 9, 30, 0
    )
    assert j.datetime_of_next_run(datetime(2026, 2, 2, 10, 0, 1)) is None


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2026, 2, 2, 9, 12, 1), datetime(2026, 2, 2, 9, 15, 0)),
        (datetime(2026, 2, 2, 9, 15, 0), datetime(2026, 2, 2, 9, 15, 0)),
        (datetime(2026, 2, 2, 9, 15, 1), datetime(2026, 2, 2, 9, 20, 0)),
    ],
)
def test_datetime_of_next_run_every(after, expected):
    t = Every(unit="minute", interval=5)
    j = Job(lambda: None, t)
    assert j.datetime_of_next_run(after) == expected


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2026, 2, 2, 9, 11, 59), datetime(2026, 2, 2, 9, 12, 0)),
        (datetime(2026, 2, 2, 9, 12, 0), datetime(2026, 2, 2, 9, 12, 0)),
        (datetime(2026, 2, 2, 9, 12, 1), None),
    ],
)
def test_datetime_of_next_run_at_datetime(after, expected):
    t = AtDateTime(run_date=datetime(2026, 2, 2, 9, 12, 0))
    j = Job(lambda: None, t)
    assert j.datetime_of_next_run(after) == expected


def test_datetime_of_next_run_or_combinator_chooses_earliest_child():
    t = On(unit="minute_of_hour", value=12) | On(unit="minute_of_hour", value=55)
    after = datetime(2026, 2, 2, 9, 13, 0)
    j = Job(lambda: None, t)
    assert j.datetime_of_next_run(after) == datetime(2026, 2, 2, 9, 55, 0)


def test_datetime_of_next_run_and_combinator_with_at_datetime():
    at = AtDateTime(run_date=datetime(2026, 2, 2, 9, 12, 0))
    constraints = On(unit="day_of_week", value=1) & Between(
        unit="hour_of_day", start=9, end=17
    )
    t = at & constraints
    j = Job(lambda: None, t)
    assert j.datetime_of_next_run(datetime(2026, 2, 2, 0, 0, 0)) == datetime(
        2026, 2, 2, 9, 12, 0
    )
    assert j.datetime_of_next_run(datetime(2026, 2, 2, 9, 12, 1)) is None


@pytest.mark.parametrize(
    ("after", "expected"),
    [
        (datetime(2026, 2, 2, 9, 13, 0), datetime(2026, 2, 2, 9, 55, 0)),
        (datetime(2026, 2, 2, 9, 56, 0), datetime(2026, 2, 2, 10, 12, 0)),
    ],
)
def test_datetime_of_next_run_complex_combination(after, expected):
    # every monday for every hour between 9am and 5pm on minute 12 and on minute 55
    trigger = (
        Every(unit="minute", interval=1)
        & On(unit="day_of_week", value=1)
        & Between(unit="hour_of_day", start=9, end=17)
        & (On(unit="minute_of_hour", value=55) | On(unit="minute_of_hour", value=12))
    )
    j = Job(lambda: None, trigger)
    assert j.datetime_of_next_run(after) == expected


def test_datetime_of_next_run_raises_when_max_iterations_reached():
    # Impossible constraint: cannot be two different hours at once.
    t = On(unit="hour_of_day", value=1) & On(unit="hour_of_day", value=2)
    with pytest.raises(NextRunMaxIterationsReached):
        Job(lambda: None, t).datetime_of_next_run(
            datetime(2026, 2, 2, 0, 0, 0), max_iterations=10
        )


def test_datetime_of_next_run_raises_when_max_iterations_reached_base_trigger():
    # Tuesday -> next Monday is 6 day-steps; cap at 3 to force exception.
    t = On(unit="day_of_week", value=1)
    with pytest.raises(NextRunMaxIterationsReached):
        Job(lambda: None, t).datetime_of_next_run(
            datetime(2026, 2, 3, 9, 0, 0), max_iterations=3
        )


def test_every_datetime_of_next_run_signature_accepts_max_iterations():
    t = Every(unit="minute", interval=5)
    after = datetime(2026, 2, 2, 9, 12, 1)
    nxt = Job(lambda: None, t).datetime_of_next_run(after, max_iterations=10)
    assert nxt is not None
