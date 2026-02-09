Trigger Tokens, Deduplication
=============================

schedium is designed to be called frequently (for example, once per second) via
:meth:`schedium.scheduler.Scheduler.run_pending`. Most triggers match for an
*interval* of time (sometimes a full bucket, sometimes an unbounded window), so
without deduplication the same job would run repeatedly while the trigger
remains satisfied.

schedium avoids that by turning a trigger match into a **trigger event token**.
Each :class:`~schedium.job.Job` remembers the last token it ran for and will not
run again for the same token.

Where tokens come from
----------------------

A trigger tree is evaluated by :func:`schedium.utils.evaluate.evaluate`.
Conceptually:

- If ``trigger.matches(now)`` is false, the result is ``None`` (no event).
- If it matches, schedium returns a :class:`~schedium.triggers.base.TriggerEvent`.
- The job compares ``event.token`` to its stored ``last_event``.

Token shapes
^^^^^^^^^^^^

schedium currently emits tokens in two main forms:

1. One-shot tokens for :class:`~schedium.triggers.datetime.AtDateTime`:

   - If an ``AtDateTime`` exists anywhere in the trigger tree,
     ``evaluate(...)`` returns ``("at", run_date)``.
   - This makes one-shot schedules behave like true one-shot events even
     though ``AtDateTime.matches(now)`` is true for all ``now >= run_date``.

2. Bucket tokens for everything else:

   - ``("bucket", granularity, truncate(now, granularity))``

   Here, ``truncate(...)`` floors the timestamp to the bucket start.

Effective granularity
---------------------

Bucket tokens require a granularity. schedium picks an **effective granularity**
from the trigger tree. See :ref:`Granularity: effective granularity <effective-granularity>` for details.

Why this matters in practice
----------------------------

Calling ``run_pending`` frequently
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you call ``run_pending`` every second, you generally want:

- jobs to *not* run again and again within the same minute/hour/day bucket, and
- jobs to run immediately when the bucket changes.

Bucket tokens provide exactly that behavior.

Long-lived matches (constraints)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Constraint triggers like :class:`~schedium.triggers.between.Between` and
:class:`~schedium.triggers.datetime.BetweenDateTime` can match for long windows.
Deduplication prevents jobs from running continuously throughout that window.

Example: with ``Tick("minute") & BetweenDateTime(...)`` the job runs at most
once per minute while the datetime window is active.

One-shot schedules
^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.datetime.AtDateTime` matches for all future times.
The special ``("at", run_date)`` token ensures the job runs only once even if
``run_pending`` is called repeatedly after the target time.

Relationship to window time
---------------------------

- ``next_window(after)`` answers: “what validity window comes next?”
- trigger tokens answer: “did I already run for this trigger event?”

These are intentionally separate concepts:

- windows are used to compute *future schedule structure* (especially for AND/OR
  combinators), while
- tokens are used to provide stable, easy-to-reason-about **deduplication** for
  repeated evaluations.

Resetting deduplication
-----------------------

Jobs are stateful. If you want to run the same callable under multiple
independent schedules, create multiple :class:`~schedium.job.Job` instances.

If you need to force a job to run again within the same token, you can clear its
stored event token by setting ``job.last_event = None`` (or by constructing a
fresh job).
