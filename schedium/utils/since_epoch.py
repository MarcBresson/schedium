from datetime import date, datetime, timedelta

from schedium.schemas.granularity import Granularity


def _months_since_epoch(dt: datetime, epoch_year: int = 1970) -> int:
    return (dt.year - epoch_year) * 12 + (dt.month - 1)


def _weeks_since_epoch(dt: datetime, epoch_monday: date = date(1970, 1, 5)) -> int:
    monday = dt.date() - timedelta(days=dt.weekday())
    return (monday - epoch_monday).days // 7


def _days_since_epoch(dt: datetime, epoch: date = date(1970, 1, 1)) -> int:
    return (dt.date() - epoch).days


def _hours_since_epoch(dt: datetime) -> int:
    dt0 = dt.replace(minute=0, second=0, microsecond=0)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    return int((dt0 - epoch).total_seconds() // 3600)


def _minutes_since_epoch(dt: datetime) -> int:
    dt0 = dt.replace(second=0, microsecond=0)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    return int((dt0 - epoch).total_seconds() // 60)


def _seconds_since_epoch(dt: datetime) -> int:
    dt0 = dt.replace(microsecond=0)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    return int((dt0 - epoch).total_seconds())


def _milliseconds_since_epoch(dt: datetime) -> int:
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    return int((dt - epoch).total_seconds() * 1000)


def since_epoch(dt: datetime, granularity: Granularity) -> int:
    if granularity == Granularity.YEAR:
        return dt.year - 1970
    if granularity == Granularity.MONTH:
        return _months_since_epoch(dt)
    if granularity == Granularity.WEEK:
        return _weeks_since_epoch(dt)
    if granularity == Granularity.DAY:
        return _days_since_epoch(dt)
    if granularity == Granularity.HOUR:
        return _hours_since_epoch(dt)
    if granularity == Granularity.MINUTE:
        return _minutes_since_epoch(dt)
    if granularity == Granularity.SECOND:
        return _seconds_since_epoch(dt)
    if granularity == Granularity.MILLISECOND:
        return _milliseconds_since_epoch(dt)
    raise ValueError(f"Unsupported granularity: {granularity}")
