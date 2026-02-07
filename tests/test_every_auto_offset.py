from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

import pytest

import pyscheduler.triggers.every as every_mod
from pyscheduler.triggers.every import Every


@pytest.fixture
def fixed_now(monkeypatch):
    fixed_now = datetime(2000, 7, 9, 17, 53, 40, tzinfo=timezone.utc)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_now.replace(tzinfo=None)
            return fixed_now

    monkeypatch.setattr(every_mod, "datetime", FixedDateTime)
    return fixed_now


@pytest.mark.parametrize(
    ("unit", "interval", "expected"),
    [
        ("second", 7, 3),
        ("minute", 5, 3),
        ("hour", 3, 2),
        ("day", 2, 1),
    ],
)
def test_every_auto_offset_sets_offset_from_now(
    fixed_now,
    unit: Literal["second", "minute", "hour", "day"],
    interval: int,
    expected: int,
):
    t = Every(unit=unit, interval=interval, offset=1, auto_offset=True)

    assert t.offset == expected
    # With auto_offset, the trigger should match immediately within the current bucket.
    assert t.matches(fixed_now)


def test_every_auto_offset_false_keeps_given_offset():
    t = Every(unit="minute", interval=5, offset=3, auto_offset=False)
    assert t.offset == 3
