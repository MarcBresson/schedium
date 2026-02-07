from datetime import datetime, timedelta

from schedium.schemas.granularity import Granularity


def truncate(dt: datetime, granularity: Granularity) -> datetime:
    if granularity == Granularity.EXACT:
        return dt
    if granularity == Granularity.MILLISECOND:
        micro = (dt.microsecond // 1000) * 1000
        return dt.replace(microsecond=micro)
    if granularity == Granularity.SECOND:
        return dt.replace(microsecond=0)
    if granularity == Granularity.MINUTE:
        return dt.replace(second=0, microsecond=0)
    if granularity == Granularity.HOUR:
        return dt.replace(minute=0, second=0, microsecond=0)
    if granularity == Granularity.DAY:
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if granularity == Granularity.WEEK:
        dt0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        return dt0 - timedelta(days=dt0.weekday())
    if granularity == Granularity.MONTH:
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if granularity == Granularity.YEAR:
        return dt.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
