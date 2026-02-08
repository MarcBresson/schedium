from datetime import datetime

from schedium.schemas.granularity import Granularity
from schedium.triggers import (
    AtDateTime,
    BaseCombinatorTrigger,
    BaseTrigger,
    TriggerEvent,
)
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
    return min(fallback)


def evaluate(trigger: BaseTrigger, now: datetime) -> TriggerEvent | None:
    if not trigger.matches(now):
        return None

    if isinstance(trigger, AtDateTime):
        return TriggerEvent(token=("at", trigger.run_date))

    if isinstance(trigger, BaseCombinatorTrigger):
        for t in trigger.triggers:
            if isinstance(t, AtDateTime):
                return TriggerEvent(token=("at", t.run_date))

    gran = _effective_granularity(trigger)
    return TriggerEvent(token=("bucket", gran, truncate(now, gran)))
