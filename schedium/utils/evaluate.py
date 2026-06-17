from datetime import datetime

from schedium.triggers import (
    AtDateTime,
    BaseCombinatorTrigger,
    BaseTrigger,
    TriggerEvent,
)
from schedium.types.granularity import Granularity
from schedium.utils.truncate_to_granularity import truncate


def _effective_granularity(trigger: BaseTrigger) -> Granularity:
    required: list[Granularity] = []
    fallback: list[Granularity] = []

    def walk(t: BaseTrigger) -> None:
        req = t.required_granularity()
        if req is not None:
            required.append(req)
        gran_fallback = t.fallback_granularity()
        if gran_fallback is not None:
            fallback.append(gran_fallback)

        if isinstance(t, BaseCombinatorTrigger):
            for child in t.triggers:
                walk(child)

    walk(trigger)
    if required:
        return min(required)
    if fallback:
        return min(fallback)
    return Granularity.SECOND


def _find_at_datetime(t: BaseTrigger) -> AtDateTime | None:
    if isinstance(t, AtDateTime):
        return t
    if isinstance(t, BaseCombinatorTrigger):
        for child in t.triggers:
            found = _find_at_datetime(child)
            if found is not None:
                return found
    return None


def evaluate(trigger: BaseTrigger, now: datetime) -> TriggerEvent | None:
    if not trigger.matches(now):
        return None

    at_dt = _find_at_datetime(trigger)
    if at_dt is not None:
        return TriggerEvent(token=("at", at_dt.run_date))

    gran = _effective_granularity(trigger)
    return TriggerEvent(token=("bucket", gran, truncate(now, gran)))
