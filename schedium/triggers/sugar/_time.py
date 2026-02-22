from __future__ import annotations

from datetime import time


def _split_time_into_components(t: time) -> tuple[int, int, int | None, int | None]:
    hour = t.hour
    minute = t.minute
    second: int | None = t.second if (t.second != 0 or t.microsecond != 0) else None
    millisecond: int | None = t.microsecond // 1000 if t.microsecond != 0 else None
    return hour, minute, second, millisecond


def parse_at(at: str | time) -> tuple[int, int, int | None, int | None]:
    if isinstance(at, time):
        return _split_time_into_components(at)

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
