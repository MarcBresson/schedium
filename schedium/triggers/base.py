from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from schedium.exceptions import NextRunMaxIterationsReached
from schedium.schemas.granularity import Granularity
from schedium.utils.truncate_to_granularity import truncate


def _add_months(dt: datetime, months: int) -> datetime:
    if months == 0:
        return dt
    month0 = (dt.year * 12 + (dt.month - 1)) + months
    year = month0 // 12
    month = (month0 % 12) + 1
    return dt.replace(year=year, month=month)


def _increment(dt: datetime, granularity: Granularity) -> datetime:
    if granularity == Granularity.EXACT:
        raise ValueError("Cannot increment EXACT granularity")
    if granularity == Granularity.MILLISECOND:
        return dt + timedelta(milliseconds=1)
    if granularity == Granularity.SECOND:
        return dt + timedelta(seconds=1)
    if granularity == Granularity.MINUTE:
        return dt + timedelta(minutes=1)
    if granularity == Granularity.HOUR:
        return dt + timedelta(hours=1)
    if granularity == Granularity.DAY:
        return dt + timedelta(days=1)
    if granularity == Granularity.WEEK:
        return dt + timedelta(days=7)
    if granularity == Granularity.MONTH:
        return _add_months(dt, 1)
    if granularity == Granularity.YEAR:
        return dt.replace(year=dt.year + 1)
    raise ValueError(f"Unsupported granularity: {granularity}")


def _effective_granularity(trigger: BaseTrigger) -> Granularity:
    g = trigger.required_granularity()
    if g is not None:
        return g
    g = trigger.fallback_granularity()
    if g is not None:
        return g
    return Granularity.SECOND


@dataclass
class TriggerEvent:
    token: object


class BaseTrigger:
    """Base trigger node.

    Triggers are pure (no mutation). Deduplication is handled at job level via
    the returned `TriggerEvent.token`.
    """

    def __and__(self, other: BaseTrigger) -> BaseCombinatorTrigger:
        return AndTrigger(triggers=[self, other])

    def __or__(self, other: BaseTrigger) -> BaseCombinatorTrigger:
        return OrTrigger(triggers=[self, other])

    def matches(self, now: datetime) -> bool:
        raise NotImplementedError

    def required_granularity(self) -> Granularity | None:
        return None

    def fallback_granularity(self) -> Granularity | None:
        return None

    def datetime_of_next_run(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> datetime | None:
        """Return the earliest run time that is >= `after`.

        Returns None when there are no future runs (e.g., one-shot in the past).
        """

        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")

        if self.matches(after):
            return after

        granularity = _effective_granularity(self)
        if granularity == Granularity.EXACT:
            return None

        candidate = truncate(after, granularity)
        if candidate < after:
            candidate = _increment(candidate, granularity)

        from schedium.exceptions import NextRunMaxIterationsReached

        iterations = 0
        while True:
            if self.matches(candidate):
                return candidate
            if iterations >= max_iterations:
                break
            candidate = _increment(candidate, granularity)
            iterations += 1

        raise NextRunMaxIterationsReached(
            max_iterations=max_iterations,
            trigger_repr=repr(self),
        )


@dataclass(frozen=True)
class BaseCombinatorTrigger(BaseTrigger):
    triggers: Sequence[BaseTrigger]

    def required_granularity(self) -> Granularity | None:
        gran: list[Granularity] = []
        for t in self.triggers:
            g = t.required_granularity()
            if g is not None:
                gran.append(g)
        return min(gran) if gran else None

    def fallback_granularity(self) -> Granularity | None:
        gran: list[Granularity] = []
        for t in self.triggers:
            g = t.fallback_granularity()
            if g is not None:
                gran.append(g)
        return min(gran) if gran else None


@dataclass(frozen=True)
class AndTrigger(BaseCombinatorTrigger):
    def matches(self, now: datetime) -> bool:
        return all(t.matches(now) for t in self.triggers)

    def datetime_of_next_run(
        self, after: datetime, *, max_iterations: int = 100000
    ) -> datetime | None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")

        candidate = after
        iterations = 0
        while iterations < max_iterations:
            remaining = max_iterations - iterations
            next_times: list[datetime] = []
            for t in self.triggers:
                nxt = t.datetime_of_next_run(candidate, max_iterations=remaining)
                if nxt is None:
                    return None
                next_times.append(nxt)

            new_candidate = max(next_times)
            if all(t.matches(new_candidate) for t in self.triggers):
                return new_candidate

            # Progress is guaranteed because at least one child is not
            # satisfied at `new_candidate`, so its datetime_of_next_run(...) must
            # return a value strictly > new_candidate on the next iteration.
            candidate = new_candidate
            iterations += 1

        raise NextRunMaxIterationsReached(
            max_iterations=max_iterations,
            trigger_repr=repr(self),
        )


@dataclass(frozen=True)
class OrTrigger(BaseCombinatorTrigger):
    def matches(self, now: datetime) -> bool:
        return any(t.matches(now) for t in self.triggers)

    def datetime_of_next_run(
        self, after: datetime, *, max_iterations: int = 100000
    ) -> datetime | None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")

        best: datetime | None = None
        for t in self.triggers:
            nxt = t.datetime_of_next_run(after, max_iterations=max_iterations)
            if nxt is None:
                continue
            if best is None or nxt < best:
                best = nxt
        return best
