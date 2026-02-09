Scheduler
=========

The :class:`~schedium.scheduler.Scheduler` holds jobs and runs them when they are
**due**.

Core loop
---------

schedium is intentionally "in-process": you call
:meth:`schedium.scheduler.Scheduler.run_pending` periodically.

.. code-block:: python

   import time
   from schedium import Every, Job, Scheduler

   sched = Scheduler()

   def task() -> None:
       print("task")

   sched.append(Job(task, Every(unit="minute", interval=5)))

   while True:
       sched.run_pending()
       time.sleep(1)

Testing and deterministic time
------------------------------

Both :meth:`~schedium.scheduler.Scheduler.run_pending` and
:meth:`~schedium.scheduler.Scheduler.time_of_next_run` accept an explicit time
argument. This makes tests deterministic.

.. code-block:: python

   from datetime import datetime
   from schedium import DidNotRun, Every, Job, Scheduler

   sched = Scheduler()
   sched.append(Job(lambda: "ran", Every(unit="minute", interval=1)))

   # Not on a minute boundary
   assert sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 30))[0] is DidNotRun

   # On the boundary
   assert sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))[0] == "ran"

Timezones (UTC preferred)
-------------------------

schedium compares datetimes and derives **trigger tokens** from time buckets. To
avoid surprises, keep your time handling consistent.

Preferred: UTC-aware datetimes
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Using timezone-aware UTC datetimes avoids Daylight Saving Time (DST) transitions.
DST can:

- make some local times **repeat** ("fall back"), and
- make some local times **not exist** ("spring forward").

When your schedule granularity is smaller than an hour (minute/second/etc.), a
"fall back" transition can cause apparent duplication in local time. For
example, if the wall clock repeats 01:30 twice, a minute-bucket schedule may run
again during the repeated interval because the local-time bucket label repeats.

With UTC, the timeline is monotonic and there are no repeated or missing local
clock times.

.. code-block:: python

   import time
   from datetime import datetime, timezone
   from schedium import Every, Job, Scheduler

   sched = Scheduler()
   sched.append(Job(lambda: print("tick"), Every(unit="minute", interval=1)))

   while True:
       sched.run_pending(now=datetime.now(timezone.utc))
       time.sleep(1)

Using local time
^^^^^^^^^^^^^^^^

If you want schedules in a local timezone, use timezone-aware datetimes with a
real zone (PEP 615), for example via :mod:`zoneinfo`.

.. code-block:: python

   import time
   from datetime import datetime
   from zoneinfo import ZoneInfo
   from schedium import Every, Job, Scheduler

   tz = ZoneInfo("Europe/Paris")

   sched = Scheduler()
   sched.append(Job(lambda: print("local tick"), Every(unit="minute", interval=1)))

   while True:
       sched.run_pending(now=datetime.now(tz))
       time.sleep(1)

If you do this, be aware of DST transitions:

- In "spring forward", some local times do not exist; schedules that target
  those times will effectively skip.
- In "fall back", local times repeat; schedules can run twice in the repeated
  window if your deduplication bucket is smaller than the repeated interval.

Naive datetimes
^^^^^^^^^^^^^^^

If you omit the ``now=...`` argument, schedium uses ``datetime.now()`` (naive
local time). Naive datetimes have no timezone information, so DST folds and
offset changes are not representable.

If you care about DST correctness, prefer timezone-aware datetimes and pass
``now=...`` explicitly.

Related concepts
----------------

- Trigger tokens and deduplication: :doc:`../concepts/trigger_tokens`
- Granularity and buckets: :doc:`../concepts/granularity`
- Window time (`next_window`): :doc:`../concepts/window_time`

API reference
-------------

- :doc:`/api/scheduler <../api/scheduler>`
