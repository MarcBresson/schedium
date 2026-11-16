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

Adding jobs with a decorator
----------------------------

The quickest way to register a job is the
:meth:`~schedium.scheduler.Scheduler.add_job` decorator:

.. code-block:: python

   import schedium
   from schedium import Scheduler

   sched = Scheduler()

   @sched.add_job(schedium.Every(unit="minute", interval=5))
   def backup():
       print("backup")

   # options: name (label), job_id (stable id for history plugins), plugins
   @sched.add_job(schedium.Weekly("monday", at="09:30"), name="weekly", job_id="weekly-backup")
   def weekly_backup():
       print("weekly backup")

The decorator returns the function unchanged, so the decorated function stays
importable and callable. It works the same way on every scheduler type
(:class:`~schedium.scheduler.Scheduler`,
:class:`~schedium.threading.ThreadedJobsScheduler`,
:class:`~schedium.threading.QueuedJobsScheduler` and
:class:`~schedium.asyncio.AsyncScheduler`).

Cancelling jobs
---------------

If a job returns :class:`~schedium.types.cancel_job.CancelJob`, the scheduler removes that
job (it cancels itself). See :ref:`jobs-cancelling-a-job-self-removal`.

Related concepts
----------------

- Trigger tokens and deduplication: :doc:`../concepts/trigger_tokens`
- Granularity and buckets: :doc:`../concepts/granularity`
- Window time (`next_window`): :doc:`../concepts/window_time`

API reference
-------------

full API reference for :class:`~schedium.scheduler.Scheduler` available in :doc:`/api/scheduler <../api/scheduler>`.
