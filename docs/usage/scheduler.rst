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

full API reference for :class:`~schedium.job.Job` available in :doc:`/api/scheduler <../api/scheduler>`.
