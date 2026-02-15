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
- ``trigger``: a trigger tree
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

Return values
-------------

``Scheduler.run_pending(...)`` returns a list aligned with ``Scheduler.jobs``:

- If a job runs, its entry is the callable's return value.
- If a job does not run, its entry is the sentinel :py:obj:`schedium.scheduler.JobDidNotRun`.
- If a job returns :class:`~schedium.types.cancel_job.CancelJob` in a scheduler, the job is removed
  from the scheduler. See below for more information.

.. _jobs-cancelling-a-job-self-removal:

Cancelling a job (self-removal)
-------------------------------

Sometimes a job should stop scheduling itself (for example, after completing a
one-off migration, or after detecting a permanent configuration error).

If a job's callable returns :class:`~schedium.types.cancel_job.CancelJob`, schedium removes
that job from the scheduler.

.. code-block:: python

   from datetime import datetime
   from schedium import CancelJob, Every, Job, Scheduler

   sched = Scheduler()

   def run_once_then_cancel():
      # do work...
      if condition_to_stop():
         return CancelJob("completed")

   sched.append(Job(run_once_then_cancel, Every(unit="minute", interval=1)))

   # First due evaluation: job runs and cancels itself.
   result = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 0))
   assert isinstance(result[0], CancelJob)
   assert len(sched.jobs) == 0

   # Subsequent calls: nothing left to run.
   assert sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0)) == []

Due vs not due
--------------

A job is considered **due** at time ``now`` when its trigger matches and yields a *new*
trigger token compared to the last time it ran.

This is what powers deduplication when ``run_pending`` is called repeatedly.

.. code-block:: python

   from datetime import datetime
   from schedium import JobDidNotRun, Every, Job, Scheduler

   sched = Scheduler()


   def task() -> None:
       print("task")


   sched.append(Job(task, Every(unit="minute", interval=1)))

   # First call in this minute bucket => due
   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 30))
   # prints: task
   assert results == [None]

   # Same minute bucket again => dedup
   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 45))
   assert results[0] is JobDidNotRun

   # Next minute => due again
   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
   assert results == [None]

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

Example: every minute, but only during working hours

.. code-block:: python

   from schedium import Between, Every, Job, Scheduler

   sched = Scheduler()


   def work_hours_task() -> None:
       print("work hours")


   trigger = Every(unit="minute", interval=1) & Between(unit="hour_of_day", start=9, end=17)

   sched.append(Job(work_hours_task, trigger, name="work-hours"))

API reference
-------------

full API reference for :class:`~schedium.job.Job` available in :doc:`/api/job <../api/job>`.
