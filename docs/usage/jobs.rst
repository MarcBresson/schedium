Jobs
====

A **Job** is the smallest runnable unit in schedium: it couples a callable (your work)
with a trigger (when it should run).

In this project you register jobs by constructing a ``Job`` and adding it to a ``Scheduler``
with ``Scheduler.append(job)``.

Creating a job
--------------

A job takes:

- ``func``: a zero-argument callable
- ``trigger``: a trigger tree (often an ``Every(...)`` tick source AND-ed with constraints)
- ``name``: an optional label used in ``repr(job)``

.. code-block:: python

   from schedium import Every, Job, Scheduler

   sched = Scheduler()


   def my_task() -> None:
       print("my_task ran")


   job = Job(
       func=my_task,
       trigger=Every(unit="minute", interval=5),
       name="print-every-5-min",
   )

   sched.append(job)

Due vs not due
--------------

A job is considered **due** at time ``now`` when its trigger matches and yields a *new*
trigger token compared to the last time it ran.

This is what powers deduplication when ``run_pending`` is called repeatedly.

.. code-block:: python

   from datetime import datetime
   from schedium import DidNotRun, Every, Job, Scheduler

   sched = Scheduler()


   def task() -> None:
       print("task")


   sched.append(Job(task, Every(unit="minute", interval=1)))

   # Not on a minute boundary => not due
   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 30))
   assert results[0] is DidNotRun

   # On the boundary => due
   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
   # prints: task
   assert results == [None]

   # Same boundary again => dedup
   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
   assert results[0] is DidNotRun

Trigger tokens and deduplication
--------------------------------

Internally, schedium evaluates triggers into a ``TriggerEvent(token=...)``.

- For most triggers, the token is a **time bucket** derived from an effective granularity
  (minute/hour/day/etc.).
- For ``AtDateTime``, the token is tied to the target datetime, so it runs **once**
  even if evaluated late.

This means:

- Calling ``Scheduler.run_pending`` many times per second is safe.
- A job runs at most once per bucket for its trigger.

Tick sources vs constraints (important)

Many triggers are **constraints** (they only filter time), for example:

- ``On(unit="hour_of_day", value=8)``
- ``Between(unit="hour_of_day", start=9, end=17)``
- ``BetweenDateTime(start_date=..., end_date=...)``

A constraint alone doesn't define a cadence. To be schedulable, a job must include a
**tick source**, such as:

- ``Every(unit=..., interval=...)``
- ``Tick(granularity=...)`` (advanced)
- ``AtDateTime(...)`` (one-shot)

Example: every minute, but only during working hours

.. code-block:: python

   from schedium import Between, Every, Job, Scheduler

   sched = Scheduler()


   def work_hours_task() -> None:
       print("work hours")


   trigger = Every(unit="minute", interval=1) & Between(unit="hour_of_day", start=9, end=17)

   sched.append(Job(work_hours_task, trigger, name="work-hours"))

If you try to schedule a constraint-only trigger, ``Scheduler.append(...)`` raises
``ValueError`` to prevent surprising behavior.

Return values
-------------

``Scheduler.run_pending(...)`` returns a list aligned with ``Scheduler.jobs``:

- If a job runs, its entry is the callable's return value.
- If a job does not run, its entry is the sentinel ``DidNotRun``.

Errors
------

``Job.run(now)`` raises ``RuntimeError`` if you call it when the job is not due or if you
call it twice for the same token.

In normal usage you should call ``Scheduler.run_pending(...)`` instead of calling
``Job.run(...)`` directly.

API reference
-------------

full API reference for :class:`~schedium.job.Job` avaible in :ref:`api/job`.

.. autoclass:: schedium.job.Job
   :show-inheritance:
