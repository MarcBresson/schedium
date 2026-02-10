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

Related concepts
----------------

- Trigger tokens and deduplication: :doc:`../concepts/trigger_tokens`
- Granularity and buckets: :doc:`../concepts/granularity`
- Window time (`next_window`): :doc:`../concepts/window_time`

API reference
-------------

- :doc:`/api/scheduler <../api/scheduler>`
