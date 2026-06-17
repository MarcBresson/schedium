from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from schedium.exceptions import NextRunMaxIterationsReached
from schedium.types.granularity import Granularity
from schedium.types.time_window import TimeWindow
from schedium.utils.truncate_to_granularity import truncate
from schedium.utils.window import (
    ONE_MICROSECOND,
    window_intersection,
    window_union_if_overlapping,
)


def _add_months(dt: datetime, months: int) -> datetime:
    if months == 0:
        return dt
    month0 = (dt.year * 12 + (dt.month - 1)) + months
    year = month0 // 12
    month = (month0 % 12) + 1
    max_day = calendar.monthrange(year, month)[1]
    return dt.replace(year=year, month=month, day=min(dt.day, max_day))


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


def _bucket_end_inclusive(bucket_start: datetime, granularity: Granularity) -> datetime:
    next_boundary = _increment(truncate(bucket_start, granularity), granularity)
    return next_boundary - ONE_MICROSECOND


def _scan_next_match_start(
    trigger: BaseTrigger,
    after: datetime,
    *,
    granularity: Granularity,
    max_iterations: int,
) -> datetime | None:
    if max_iterations <= 0:
        raise ValueError("max_iterations must be > 0")

    if granularity == Granularity.EXACT:
        return None

    candidate = truncate(after, granularity)
    if candidate < after:
        candidate = _increment(candidate, granularity)

    iterations = 0
    while True:
        if trigger.matches(candidate):
            return candidate
        if iterations >= max_iterations:
            break
        candidate = _increment(candidate, granularity)
        iterations += 1

    raise NextRunMaxIterationsReached(
        max_iterations=max_iterations,
        trigger_repr=repr(trigger),
    )


class BaseTrigger:
    """
    Base trigger node.

    Triggers are pure (no mutation). Deduplication is handled at job level via
    the returned `TriggerEvent.token`.
    """

    def __and__(self, other: BaseTrigger) -> BaseCombinatorTrigger:
        left = self.triggers if isinstance(self, AndTrigger) else (self,)
        right = other.triggers if isinstance(other, AndTrigger) else (other,)
        return AndTrigger(triggers=[*left, *right])

    def __or__(self, other: BaseTrigger) -> BaseCombinatorTrigger:
        left = self.triggers if isinstance(self, OrTrigger) else (self,)
        right = other.triggers if isinstance(other, OrTrigger) else (other,)
        return OrTrigger(triggers=[*left, *right])

    def matches(self, now: datetime) -> bool:
        raise NotImplementedError

    def required_granularity(self) -> Granularity | None:
        return None

    def fallback_granularity(self) -> Granularity | None:
        return None

    def next_window(
        self,
        after: datetime,
        *,
        max_iterations: int = 100_000,
    ) -> TimeWindow | None:
        """
        Return the next validity window whose start is >= ``after``.

        For most constraint-style triggers, the default implementation:

        1) finds the next matching time using a forward scan at an inferred
           granularity, then
        2) returns a single-bucket window at that granularity.

        Parameters
        ----------
        after : datetime
            Lower bound (inclusive) for the returned window start.
        max_iterations : int, default 100_000
            Safety cap used by some triggers/combinators that scan forward.

        Returns
        -------
        schedium.types.time_window.TimeWindow | None
            Next validity window, or :obj:`None` if no future window exists.

        Raises
        ------
        ValueError
            If ``max_iterations <= 0``.
        schedium.exceptions.NextRunMaxIterationsReached
            If a forward scan exceeds ``max_iterations``.
        """

        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")

        granularity = _effective_granularity(self)

        if self.matches(after):
            if granularity == Granularity.EXACT:
                return TimeWindow(start=after, end=after)
            return TimeWindow(
                start=after, end=_bucket_end_inclusive(after, granularity)
            )

        start = _scan_next_match_start(
            self,
            after,
            granularity=granularity,
            max_iterations=max_iterations,
        )
        if start is None:
            return None

        return TimeWindow(start=start, end=_bucket_end_inclusive(start, granularity))


class BaseCombinatorTrigger(BaseTrigger):
    def __init__(self, triggers: Sequence[BaseTrigger]) -> None:
        self.triggers = triggers

    def __repr__(self) -> str:
        inner = ", ".join(repr(t) for t in self.triggers)
        return f"{type(self).__name__}({inner})"

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


class AndTrigger(BaseCombinatorTrigger):  # numpydoc ignore=PR02
    """
    Logical AND (intersection) of multiple triggers.

    An :class:`~schedium.triggers.AndTrigger` matches a datetime only when **all**
    its child triggers match.

    In window-time terms, ``A & B`` behaves like the intersection of the next
    validity windows returned by ``A`` and ``B``.

    Parameters
    ----------
    triggers : Sequence[BaseTrigger]
        Child triggers to combine with AND logic.

    Notes
    -----
    - Prefer composing with ``&`` over instantiating :class:`~schedium.triggers.AndTrigger`
      directly.
    - ``&`` is associative in meaning. schedium also flattens nested AND nodes,
      so ``(A & B) & C`` becomes a single :class:`~schedium.triggers.AndTrigger`.

    Examples
    --------
    Use ``&`` to combine existing triggers:

    >>> from schedium import Every, On
    >>> trigger1 = Every(unit="day", interval=1)
    >>> trigger2 = On(unit="hour_of_day", value=8)
    >>> trigger3 = On(unit="minute_of_hour", value=0)

    ``trigger1 & trigger2`` produces an explicit ``AndTrigger(trigger1, trigger2)``:

    >>> trigger1 & trigger2
    AndTrigger(Every(unit='day', interval=1, offset=0), On(unit='hour_of_day', value=8))

    Chaining ``&`` is flattened into a single AndTrigger node:

    >>> trigger1 & trigger2 & trigger3
    AndTrigger(Every(unit='day', interval=1, offset=0), On(unit='hour_of_day', value=8), On(unit='minute_of_hour', value=0))
    """

    def matches(self, now: datetime) -> bool:
        return all(t.matches(now) for t in self.triggers)

    def next_window(
        self, after: datetime, *, max_iterations: int = 100_000
    ) -> TimeWindow | None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")

        candidate = after
        iterations = 0
        while iterations < max_iterations:
            remaining = max_iterations - iterations
            windows: list[TimeWindow] = []
            for t in self.triggers:
                w = t.next_window(candidate, max_iterations=remaining)
                if w is None:
                    return None
                windows.append(w)

            # Intersect all child windows.
            intersection = windows[0]
            for w in windows[1:]:
                nxt = window_intersection(intersection, w)
                if nxt is None:
                    intersection = None  # type: ignore[assignment]
                    break
                intersection = nxt

            if intersection is not None:
                return intersection

            # No overlap: advance just past the earliest window end.
            earliest_end: datetime | None = None
            for w in windows:
                if w.end is None:
                    continue
                if earliest_end is None or w.end < earliest_end:
                    earliest_end = w.end

            if earliest_end is None:
                # All windows are unbounded but still didn't overlap (shouldn't happen)
                return None

            candidate = earliest_end + ONE_MICROSECOND
            iterations += 1

        raise NextRunMaxIterationsReached(
            max_iterations=max_iterations, trigger_repr=repr(self)
        )


class OrTrigger(BaseCombinatorTrigger):  # numpydoc ignore=PR02
    """
    Logical OR (alternatives) of multiple triggers.

    An :class:`~schedium.triggers.OrTrigger` matches a datetime when **any** child
    trigger matches.

    For ``A | B``, :meth:`~schedium.triggers.base.BaseTrigger.next_window` returns
    the earliest next window among children. If multiple children yield overlapping
    windows at the earliest start, those windows are merged.

    Parameters
    ----------
    triggers : Sequence[BaseTrigger]
        Child triggers to combine with OR logic.

    Notes
    -----
    - Prefer composing with ``|`` over instantiating :class:`~schedium.triggers.OrTrigger`
        directly.
    - schedium flattens nested OR nodes, so ``(A | B) | C`` becomes a single
        :class:`~schedium.triggers.OrTrigger`.
    """

    def matches(self, now: datetime) -> bool:
        return any(t.matches(now) for t in self.triggers)

    def next_window(
        self, after: datetime, *, max_iterations: int = 100_000
    ) -> TimeWindow | None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")

        best: TimeWindow | None = None
        windows: list[TimeWindow] = []
        for t in self.triggers:
            w = t.next_window(after, max_iterations=max_iterations)
            if w is None:
                continue
            windows.append(w)
            if best is None or w.start < best.start:
                best = w

        if best is None:
            return None

        # If any other child window overlaps the earliest, merge them.
        merged = best
        for w in windows:
            if w is merged:
                continue
            u = window_union_if_overlapping(merged, w)
            if u is not None:
                merged = u
                if merged.end is None:
                    break

        return merged
