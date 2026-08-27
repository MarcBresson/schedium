Asyncio scheduler
==================

schedium runs jobs inline by default (no background threads or event loop
involvement). For ``asyncio`` applications, it is useful to keep schedium's trigger
evaluation but run job functions on the event loop instead.

This page documents :class:`~schedium.asyncio.AsyncScheduler`.

If your application is built on threads rather than ``asyncio``, use the helpers in
:mod:`schedium.threading` instead --
:class:`~schedium.threading.ThreadedJobsScheduler`,
:class:`~schedium.threading.SchedulerThread`, and
:class:`~schedium.threading.QueuedJobsScheduler` -- see :doc:`threading`.

AsyncScheduler (run jobs on the event loop)
------------------------------------------------

:class:`~schedium.asyncio.AsyncScheduler` is used directly, the same way you would
use :class:`~schedium.scheduler.Scheduler`. You call ``run_pending`` yourself
(awaiting it), and due jobs run on the event loop -- concurrently with each other,
and without blocking on synchronous jobs. ``async def`` job functions are awaited
directly; plain synchronous job functions are offloaded to the default executor so
they never block the loop.

.. code-block:: python

   import asyncio
   from schedium import Every, Job, JobDidNotRun
   from schedium.asyncio import AsyncScheduler

   async_sched = AsyncScheduler()

   async def io_bound_work() -> str:
      # Your async job code
      return "ok"

   def cpu_or_blocking_work() -> str:
      # Runs in the default executor, so it will not block the event loop.
      return "ok too"

   async_sched.append(Job(io_bound_work, Every(unit="second", interval=1)))
   async_sched.append(Job(cpu_or_blocking_work, Every(unit="second", interval=1)))

   async def main():
       while True:
           results = await async_sched.run_pending()

           for result in results:
               if result is JobDidNotRun:
                   continue
               print(f"job returned: {result!r}")

           await asyncio.sleep(1)

   asyncio.run(main())

Pass ``wait=False`` to get back :class:`asyncio.Task` objects immediately instead of
awaiting every due job before returning.

Limiting concurrency
~~~~~~~~~~~~~~~~~~~~~

Use ``max_concurrency`` to cap how many jobs run at the same time. If max_concurrency is reached, due jobs are queued until a running job finishes.

.. code-block:: python

   async_sched = AsyncScheduler(max_concurrency=4)

Running the loop in the background
-----------------------------------

If your current coroutine should stay free for other work, run the loop above as a
regular :func:`asyncio.create_task` -- there is no dedicated helper for this,
since asyncio's own task API already covers it in a couple of lines:

.. code-block:: python

   import logging

   async def loop():
       while True:
           await async_sched.run_pending(wait=False)
           await asyncio.sleep(1)

   task = asyncio.create_task(loop())

   # ... later
   task.cancel()
   try:
       await task
   except asyncio.CancelledError:
       pass  # expected: this is the cancellation we just requested
   except Exception:
       logging.exception("scheduler loop crashed")

``task.cancel()`` interrupts the loop at its next await point (immediately, if it is
currently sleeping), and any exception raised inside ``loop()`` surfaces when you
``await task`` -- catch :class:`asyncio.CancelledError` separately if you want to
tell that expected shutdown apart from a genuine crash.


Notes and caveats
-----------------

- ``CancelJob`` is supported: returning :class:`~schedium.types.cancel_job.CancelJob`
  from a job removes it from the scheduler.
- If you want "retry within the same token" semantics on failures, enable the
  ``revert_last_event_on_failure`` option. Be careful: this may cause rapid retry
  loops if your scheduler loop runs very frequently.
