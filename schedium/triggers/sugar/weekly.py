from __future__ import annotations

from datetime import time

from schedium.schemas.granularity import Granularity
from schedium.triggers.base import BaseTrigger
from schedium.triggers.on import On
from schedium.triggers.sugar.tick import Tick

_WEEKDAY_ALIASES_TO_ISO = {
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
    "sun": 7,
}


def _parse_weekday_to_on_value(day: str | int) -> int:
    if isinstance(day, int):
        if 1 <= day <= 7:
            return day
        raise ValueError("weekday integer must be 1..7 (Mon..Sun)")

    key = day.strip()[:3].lower()

    if key in _WEEKDAY_ALIASES_TO_ISO:
        return _WEEKDAY_ALIASES_TO_ISO[key]

    raise ValueError(
        "weekday must be one of: mon/tue/wed/thu/fri/sat/sun (or full names), or 1..7"
    )


def _split_time_into_components(t: time) -> tuple[int, int, int | None, int | None]:
    hour = t.hour
    minute = t.minute
    second: int | None = t.second if (t.second != 0 or t.microsecond != 0) else None
    millisecond: int | None = t.microsecond // 1000 if t.microsecond != 0 else None
    return hour, minute, second, millisecond


def _parse_at(at: str | time) -> tuple[int, int, int | None, int | None]:
    if isinstance(at, time):
        return _split_time_into_components(at)

    s = at.strip()
    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(
            "at must be in format 'HH:MM' or 'HH:MM:SS' (optionally with .mmm)"
        )

    s = at.strip()
    parts = s.split(":")
    if len(parts) not in (2, 3):
        raise ValueError(
            "at must be in format 'HH:MM' or 'HH:MM:SS' (optionally with .mmm)"
        )

    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError as e:
        raise ValueError("at has invalid hour/minute") from e

    second: int | None = None
    millisecond: int | None = None

    if len(parts) == 3:
        sec_part = parts[2]
        if "." in sec_part:
            sec_str, frac = sec_part.split(".", 1)

            # pad to at least 3 digits for millisecond parsing
            frac = frac.ljust(3, "0")[:3]
            try:
                millisecond = int(frac)
            except ValueError as e:
                raise ValueError("at has invalid milliseconds") from e
        else:
            sec_str = sec_part

        try:
            second = int(sec_str)
        except ValueError as e:
            raise ValueError("at has invalid seconds") from e

    if not (0 <= hour <= 23):
        raise ValueError("at hour must be in 0..23")
    if not (0 <= minute <= 59):
        raise ValueError("at minute must be in 0..59")
    if second is not None and not (0 <= second <= 59):
        raise ValueError("at second must be in 0..59")
    if millisecond is not None and not (0 <= millisecond <= 999):
        raise ValueError("at millisecond must be in 0..999")

    return hour, minute, second, millisecond


def Weekly(
    day: str | int, *, at: str | time | None = None, force_0_minute: bool = False
) -> BaseTrigger:
    """Convenience trigger: run weekly on a specific weekday, optionally at a time.

    Parameters
    ----------
    day: str | int
        Weekday to run on. Can be a string like "mon"/"monday" (case-insensitive,
        only first 3 letters are considered) or an integer in ISO format where
        Monday=1 and Sunday=7.
    at: str | time, optional
        Time of day to run at. If not provided, it will not constrain the time.
        Can be a `datetime.time` object, or a string in "HH:MM" or
        "HH:MM:SS[.mmm]" format.
    force_0_minute: bool, default False
        By default, if `at` is provided without a minute component (e.g. "09:00" or
        `time(9, 0)`), the trigger does not constrain the minute (i.e., it can run
        every minute during the 9 o'clock hour). Setting `force_0_minute=True` makes
        it so that the minute is constrained to 0, meaning it will only run at the top
        of the hour (e.g. 09:00:37).

    Examples
    --------
    ```
    Weekly("monday")

    # specify a time to run at
    Weekly("mon", at="09:30")
    from datetime import time
    Weekly("thursday", at=time(9, 30))
    Weekly("thursday", at=time(9))

    # don't run if job is overdue by more than a minute (e.g. if scheduler was down)
    # i.e. only run at 09:00 sharp
    Weekly("thursday", at=time(9, 0), force_0_minute=True)
    ```

    Notes
    -----
    This helper composes a *tick source* with *constraints*:

    - Tick source: `Tick(Granularity.WEEK)`
        - Always matches, but provides a WEEK "bucket" for deduplication.
        - This makes the trigger schedulable without imposing a cadence.
    - Constraints: `On(day_of_week=...)` and, if `at` is provided, hour/minute
        (and optionally second/millisecond).

    Using `Tick(WEEK)` (instead of `Every(unit="week", interval=1)`) avoids forcing
    alignment to week boundaries (e.g. Monday 00:00). That alignment can make
    `next_window()` for AND-combinations like "Monday at 09:30" converge
    poorly by repeatedly jumping to week boundaries.
    """

    weekday_value = _parse_weekday_to_on_value(day)

    trigger: BaseTrigger = Tick(Granularity.WEEK) & On(
        unit="day_of_week", value=weekday_value
    )

    if at is None:
        return trigger

    hour, minute, second, millisecond = _parse_at(at)

    trigger = trigger & On(unit="hour_of_day", value=hour)
    if minute != 0 or force_0_minute:
        trigger = trigger & On(unit="minute_of_hour", value=minute)

    if second is not None:
        trigger = trigger & On(unit="second_of_minute", value=second)
    if millisecond is not None:
        trigger = trigger & On(unit="millisecond_of_second", value=millisecond)

    return trigger
