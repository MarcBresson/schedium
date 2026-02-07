from enum import IntEnum


class Granularity(IntEnum):
    """How finely a schedule can fire.

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
