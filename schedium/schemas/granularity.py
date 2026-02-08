from enum import IntEnum
from typing import Literal, TypeAlias


class Granularity(IntEnum):
    """
    How finely a schedule can fire.

    Lower values are *finer* (more frequent) than higher values.
    """

    EXACT = 0
    MILLISECOND = 1
    SECOND = 2
    MINUTE = 3
    HOUR = 4
    DAY = 5
    WEEK = 6
    MONTH = 7
    YEAR = 8


UNIT_TO_GRANULARITY_MAP = {
    "year": Granularity.YEAR,
    "month": Granularity.MONTH,
    "week": Granularity.WEEK,
    "day": Granularity.DAY,
    "hour": Granularity.HOUR,
    "minute": Granularity.MINUTE,
    "second": Granularity.SECOND,
    "millisecond": Granularity.MILLISECOND,
}


GranularityUnit: TypeAlias = Literal[
    "year",
    "month",
    "week",
    "day",
    "hour",
    "minute",
    "second",
    "millisecond",
]
