from typing import Literal, TypeAlias

OnUnit: TypeAlias = Literal[
    "year",
    "month_of_year",
    "week_of_year",
    "weekend_days",
    "weekdays",
    "day_of_week",
    "day_of_month",
    "hour_of_day",
    "minute_of_hour",
    "second_of_minute",
    "millisecond_of_second",
]
