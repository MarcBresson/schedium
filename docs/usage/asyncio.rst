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

Which job functions are awaited
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The scheduler decides how to call a job function as follows:

- ``async def`` functions, and callable objects whose ``__call__`` is ``async def``
  (also when wrapped in :func:`functools.partial`), are awaited directly on the
  event loop.
- Any other callable runs in the default executor. If it returns an awaitable (a
  coroutine, :class:`asyncio.Future`, ...), that awaitable is awaited on the event
  loop, so ``lambda: fetch(url)`` or a synchronous decorator that returns the
  wrapped coroutine behave as expected.

.. code-block:: python

   class Poller:
       def __init__(self, url: str) -> None:
           self.url = url

       async def __call__(self) -> str:
           return await fetch(self.url)

   async_sched.append(Job(Poller("https://example.com"), Every(unit="minute", interval=1)))
   async_sched.append(Job(lambda: fetch("https://example.com"), Every(unit="minute", interval=1)))

.. warning::

   For the second kind, the synchronous part of the function runs in a worker
   thread. Return the coroutine and let the scheduler await it, or make the
   function ``async def``. Prefer ``async def`` or an ``async def __call__``
   when you can as they skip the
   thread hop.

   An awaitable returned by an ``async def`` function is the job's return value and
   is *not* awaited a second time. Likewise, a synchronous function cannot return a
   task or future "as a value": it is awaited, and the job's result is the awaited value.

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
