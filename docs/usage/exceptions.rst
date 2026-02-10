Handling exceptions in jobs
===========================

schedium runs jobs **inline** when you call
:meth:`schedium.scheduler.Scheduler.run_pending`.
This makes exception handling simple and explicit: *your code decides* whether a
job failure should crash the loop, be retried, or be recorded and ignored.

What happens by default
-----------------------

- If a job's callable raises, the exception **propagates** out of
  :meth:`~schedium.scheduler.Scheduler.run_pending`.
- Any jobs after the failing job in the current call to ``run_pending`` will
  not run because execution stops at the exception.

A subtle (and useful) detail: a :class:`~schedium.job.Job` updates its
deduplication state (:attr:`schedium.job.Job.last_event`) **only after** the
callable completes successfully.

That means:

- If the callable raises, ``last_event`` is not updated.
- The job will still be considered **due** for the same trigger token the next
  time you call ``run_pending``.

This gives you an implicit "retry on next poll" behavior, which may or may not
be what you want.

Patterns
--------

1) Fail fast (let the process crash)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

This is often the best default for services supervised by systemd/Kubernetes.
You get fast feedback and a clean restart.

.. code-block:: python

   import time
   from schedium import Every, Job, Scheduler

   def task() -> None:
       # Any exception will stop run_pending and propagate.
       do_the_thing()

   sched = Scheduler()
   sched.append(Job(task, Every(unit="minute", interval=1)))

   while True:
       sched.run_pending()
       time.sleep(1)

When to use:

- You want a notification/alert on failure.
- You want a restart to restore a clean state.
- Job failures indicate a real programming or configuration issue.
- You have other jobs that depend on this job and don't make sense to run if it fails.
- It's not important to miss runs during downtime.

2) Catch-and-log inside the job (do not crash)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Wrap the callable and handle exceptions locally.

.. code-block:: python

   import logging
   import time
   from schedium import Every, Job, Scheduler

   logger = logging.getLogger(__name__)

   def task() -> None:
       try:
           do_the_thing()
       except Exception:
           logger.exception("task failed")

   sched = Scheduler()
   sched.append(Job(task, Every(unit="minute", interval=1)))

   while True:
       sched.run_pending()
       time.sleep(1)

Important: retry semantics
""""""""""""""""""""""""""

If you swallow exceptions **inside** the callable (as above), the job is treated
as having "completed" and its ``last_event`` will be updated.

- Pros: prevents hot-loop retries within the same token/bucket.
- Cons: you must surface the failure yourself (logs/metrics/alerts), because the
  scheduler cannot know it failed.

3) Continue running other jobs even if one fails
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you want one job to fail without preventing others from running, you can
isolate exceptions at the scheduler loop.

.. code-block:: python

   import logging
   import time
   from datetime import datetime
   from schedium import DidNotRun, Scheduler

   logger = logging.getLogger(__name__)

   sched = Scheduler()
   # ... append jobs ...

   while True:
       now = datetime.now()
       results = []
       for job in list(sched.jobs):
           try:
               results.append(job.run(now) if job.is_due(now) else DidNotRun)
           except Exception:
               logger.exception("job failed: %r", job)
               results.append(DidNotRun)
       time.sleep(1)

Notes:

- This mirrors :meth:`~schedium.scheduler.Scheduler.run_pending`, but adds a
  per-job try/except.
- Whether a failure should be considered "ran" is up to you. The snippet above
  treats failures as not-run so they can be retried.

4) Prevent rapid retries (one attempt per bucket)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you prefer to attempt work **once per token** even when it fails, catch the
exception and return a value instead of raising.

.. code-block:: python

   import logging
   from dataclasses import dataclass
   from schedium import Every, Job, Scheduler

   logger = logging.getLogger(__name__)

   @dataclass(frozen=True)
   class Failed:
       error: str

   def safe_task():
       try:
           do_the_thing()
           return None
       except Exception as e:
           logger.exception("task failed")
           # Returning keeps the job deduplicated for this bucket.
           return Failed(error=str(e))

   sched = Scheduler()
   sched.append(Job(safe_task, Every(unit="minute", interval=1)))

This pattern is useful when:

- you poll frequently (e.g., every second), and
- a transient error would otherwise cause many retries within the same minute.

Exceptions from next-run computations
-------------------------------------

Exceptions can also arise when *asking* schedium for future times.

- :meth:`schedium.job.Job.datetime_of_next_run`
- :meth:`schedium.scheduler.Scheduler.time_of_next_run`

Some trigger combinations require scanning forward. If scanning exceeds
``max_iterations``, schedium raises
:class:`schedium.exceptions.NextRunMaxIterationsReached`.

Typical handling:

.. code-block:: python

   from datetime import datetime
   from schedium import Job, On
   from schedium.exceptions import NextRunMaxIterationsReached

   trigger = On(unit="hour_of_day", value=1) & On(unit="hour_of_day", value=2)
   job = Job(lambda: None, trigger)

   try:
       nxt = job.datetime_of_next_run(datetime.now(), max_iterations=1_000)
   except NextRunMaxIterationsReached as e:
       # Decide whether to increase max_iterations, simplify the schedule,
       # or treat it as "no next run" for UI purposes.
       nxt = None
