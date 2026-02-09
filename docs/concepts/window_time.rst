Window Time (TimeWindow)
========================

schedium computes “what happens next?” using **windows**.

A trigger exposes::

   next_window(after: datetime, *, max_iterations: int = 100_000) -> TimeWindow | None

Instead of returning a single datetime, it returns the next **validity interval**
for which the trigger is satisfied.

TimeWindow
----------

A :class:`~schedium.utils.window.TimeWindow` is a pair ``(start, end)``.

- **Inclusive semantics**: the window represents ``start <= t <= end``.
- **Unbounded windows**: ``end=None`` means the window is valid forever into the future.

This representation is powerful because it can express constraints that are
conceptually “partial datetimes” (like “year is 2026”) as *real timeline ranges*
without inventing a separate PartialDateTime type.

Contract for next_window
------------------------

The ``next_window(after)`` contract is:

- Returns ``None`` if the trigger can never match at or after ``after``.
- Otherwise returns a window where:

  - ``window.start >= after`` OR the trigger is already satisfied at ``after``
    (in which case ``window.start == after``), and
  - for all ``t`` in the interval ``[window.start, window.end]`` (or unbounded),
    the trigger is considered satisfied.

``max_iterations`` is a safety valve for triggers that scan forward. If the
limit is exceeded, schedium raises
:class:`~schedium.exceptions.NextRunMaxIterationsReached`.

Buckets and default behavior
----------------------------

Many constraint triggers (for example :class:`~schedium.triggers.on.On`) do not
have an obvious “duration” on their own. For those, the default implementation
in :class:`~schedium.triggers.base.BaseTrigger`:

1) scans forward (at an inferred granularity) until it finds the next match, then
2) returns a **single bucket window** at that granularity.

Example: ``On(unit="hour_of_day", value=9)`` returns a window covering the rest of
that hour once it finds the next matching hour.

Combinators (AND / OR)
----------------------

Combinator triggers operate on windows.

AND: intersection
^^^^^^^^^^^^^^^^^

For ``A & B``, schedium computes the intersection of the child windows.

- If the current windows overlap, the result is their **intersection**.
- If they are disjoint, schedium advances past the earliest ending window and
  tries again.

This matches the intuition: a time is valid for ``A & B`` only when it is valid
for both.

OR: earliest window + optional merge
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For ``A | B``, schedium asks each child for its next window and picks the one
with the earliest start.

- If the other child’s next window overlaps that earliest window, schedium
  returns the **merged union** of those overlapping windows.
- If the windows are disjoint, schedium returns the earliest one unchanged.

Important: OR does **not** attempt to return a full “set of disjoint windows”. It
returns a single window suitable for “what’s next?”.

From windows to next run datetime
---------------------------------

Jobs expose::

   Job.datetime_of_next_run(after) -> datetime | None

This is derived directly from windows:

- ``window = trigger.next_window(after)``
- next run time is ``window.start``

This keeps the scheduler logic simple while still benefiting from the richer
window representation for combinators and constraints.

Practical notes
---------------

- Inclusive ends are convenient for expressing “inside a maintenance window”
  constraints like :class:`~schedium.triggers.datetime.BetweenDateTime`.
- Some implementations compute “end of bucket” as the next boundary minus one
  microsecond; this is a pragmatic way to keep endpoints representable with
  Python’s ``datetime``.
