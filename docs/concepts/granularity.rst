Granularity
===========

schedium uses a concept called **granularity** to describe how finely time is
partitioned for scheduling.

Granularity shows up in two places:

- **Deduplication**: deciding whether a job already ran for the current “time
  bucket”.
- **Scanning and bucket windows**: default logic that searches forward for the
  next match and/or returns a single-bucket :class:`~schedium.utils.window.TimeWindow`.

The Granularity enum
--------------------

The enum lives in :class:`~schedium.schemas.granularity.Granularity` and is
ordered from *finest* (most frequent) to *coarsest* (least frequent):

- ``EXACT``
- ``MILLISECOND``
- ``SECOND``
- ``MINUTE``
- ``HOUR``
- ``DAY``
- ``WEEK``
- ``MONTH``
- ``YEAR``

Lower values are finer.

String units
^^^^^^^^^^^^

Many APIs accept unit strings via
:data:`~schedium.schemas.granularity.UNIT_TO_GRANULARITY_MAP`, for example
``"minute"`` or ``"day"``.

What “bucket” means
-------------------

For a given granularity, schedium defines a **bucket** as an interval that starts
at a boundary and continues until the next boundary.

Boundaries are computed by truncating a datetime to its bucket start using
:func:`~schedium.utils.truncate_to_granularity.truncate`.

Example
^^^^^^^

If ``granularity == MINUTE`` then:

- bucket start is ``dt.replace(second=0, microsecond=0)``
- all timestamps with the same truncated value are considered “in the same
  minute bucket”

For ``WEEK``, truncation returns the Monday 00:00 of the week.

Granularity and deduplication
-----------------------------

When a trigger matches, schedium turns the match into a trigger event token.
For most trigger trees, the token has the form::

   ("bucket", granularity, truncate(now, granularity))

A job runs at most once per token. If you call
:meth:`schedium.scheduler.Scheduler.run_pending` repeatedly, it will keep
returning :obj:`schedium.scheduler.DidNotRun` for that job until the token
changes (i.e., the bucket changes).

Effective granularity
^^^^^^^^^^^^^^^^^^^^^

The effective granularity is derived from the trigger tree (see
:func:`schedium.utils.evaluate.evaluate`):

- If any node reports ``required_granularity()``, schedium uses the **finest**
  required granularity.
- Otherwise it uses the **finest** ``fallback_granularity()``.

Tick sources (like :class:`~schedium.triggers.every.Every` and
:class:`~schedium.triggers.sugar.tick.Tick`) typically define the effective
granularity for the entire schedule.

Special case: EXACT and AtDateTime
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.datetime.AtDateTime` is treated as a one-shot.
Even though it matches forever after ``run_date``, it produces a stable token::

   ("at", run_date)

This prevents repeated runs while still allowing late starts.

Granularity and next_window
---------------------------

Many constraint-style triggers don’t have an obvious duration. The default
implementation of :meth:`schedium.triggers.base.BaseTrigger.next_window` uses an
inferred granularity to:

1. scan forward to the next matching bucket boundary, and
2. return a window covering exactly that bucket.

This is why choosing a tick source granularity matters: it affects both
**deduplication** and how quickly some AND-combinations converge when scanning.

Practical guidance
------------------

- Use :class:`~schedium.triggers.sugar.tick.Tick` when you want constraints to
  “drive” *which* time within a larger bucket is chosen, but still cap execution
  rate.
- Use :class:`~schedium.triggers.every.Every` when you want an epoch-aligned
  cadence.
- If a schedule seems to “miss” events, call ``run_pending`` more frequently
  than the bucket size implied by its effective granularity.
