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
- Any other callable runs in the default executor. Its return value is passed
  through unchanged, *unless* the scheduler was created with
  ``await_awaitable_results=True``: then, if it returns an awaitable (a coroutine,
  :class:`asyncio.Future`, ...), that awaitable is awaited on the event loop, so
  ``lambda: fetch(url)`` or a synchronous decorator that returns the wrapped
  coroutine behave as expected. Without the option, the job's result is the
  un-awaited coroutine object and the coroutine never runs.
- With ``require_async_jobs=True``, the executor fallback is disabled and any job
  that is not an async callable is rejected (see `Refusing synchronous jobs`_).

.. code-block:: python

   class Poller:
       def __init__(self, url: str) -> None:
           self.url = url

       async def __call__(self) -> str:
           return await fetch(self.url)

   async_sched.append(Job(Poller("https://example.com"), Every(unit="minute", interval=1)))

   # Needs AsyncScheduler(await_awaitable_results=True) to actually be awaited
   async_sched.append(Job(lambda: fetch("https://example.com"), Every(unit="minute", interval=1)))

.. warning::

   For the second kind, the synchronous part of the function runs in a worker
   thread, and the returned coroutine is only awaited if
   ``await_awaitable_results=True``. Prefer ``async def`` or an ``async def __call__``
   when you can: they skip the thread hop and need no option.

   An awaitable returned by an ``async def`` function is the job's return value and
   is *not* awaited a second time. With ``await_awaitable_results=True``, a
   synchronous function cannot return a task or future "as a value": it is awaited,
   and the job's result is the awaited value.

Refusing synchronous jobs
~~~~~~~~~~~~~~~~~~~~~~~~~

Falling back to a worker thread is convenient, but it is easy to trigger by
accident: forget the ``async`` keyword on a job function, or wrap a coroutine
function in a decorator that is not itself ``async``, and the job silently moves
off the event loop. Anything it shares with the loop (HTTP clients, database
sessions, caches, thread-affine resources) is then used from another thread, which
tends to fail intermittently and far from the cause.

If you want a guarantee that every job runs on the event loop, create the
scheduler with ``require_async_jobs=True``. The thread pool is then never used, and
any job whose callable is not known to be async is rejected with
:class:`~schedium.exceptions.SyncJobNotAllowed` (a :class:`TypeError`):

.. code-block:: python

   from schedium.exceptions import SyncJobNotAllowed

   async_sched = AsyncScheduler(require_async_jobs=True)

   async_sched.append(Job(io_bound_work, Every(unit="second", interval=1)))  # ok

   try:
       async_sched.append(Job(cpu_or_blocking_work, Every(unit="second", interval=1)))
   except SyncJobNotAllowed:
       ...  # not an async callable: refused, and never run in a thread

Details worth knowing:

- The check happens in :meth:`~schedium.asyncio.AsyncScheduler.append`, so the
  mistake shows up where the job is registered rather than the first time it is due.
  It is repeated when the job is about to run, to catch jobs put directly into
  ``async_sched.jobs`` or whose ``func`` was swapped afterwards. In that case the
  error is handled like any other job failure: raised from ``run_pending`` with
  ``wait=True``, or logged with ``wait=False``.
- A callable only counts as async if it can be recognised without calling it:
  ``async def`` functions and callable objects with an ``async def __call__``, also
  inside :func:`functools.partial`. A synchronous function that *returns* a
  coroutine, such as ``lambda: fetch(url)``, is rejected too: telling it apart
  from a blocking function would require calling it, which is exactly the thread
  hop this flag exists to prevent. Write ``async def`` wrappers instead
  (``async def poll(): return await fetch(url)``).
- ``await_awaitable_results`` has no effect with this option, as no synchronous
  job is ever called.
- It is off by default so that blocking jobs keep working out of the box. Leave it
  off if you rely on the thread offloading; turn it on if you consider a
  synchronous job in an asyncio scheduler to be a bug.

Limiting concurrency
~~~~~~~~~~~~~~~~~~~~~

Use ``max_concurrency`` to cap how many jobs run at the same time. If max_concurrency is reached, due jobs are queued until a running job finishes.

.. code-block:: python

   async_sched = AsyncScheduler(max_concurrency=4)

.. _running-the-loop-in-the-background:

Running the loop in the background
-----------------------------------

If your current coroutine should stay free for other work, call
:meth:`~schedium.asyncio.AsyncScheduler.start`. It runs the scheduler loop as a task
on the running event loop and returns immediately. Every ``interval`` seconds (1 by
default) due jobs are dispatched without waiting for them, so a slow job never
delays the next tick.

.. code-block:: python

   async def main():
       async_sched.start(interval=1.0)

       ...  # the rest of your application

       await async_sched.stop(timeout=10)

   asyncio.run(main())

:meth:`~schedium.asyncio.AsyncScheduler.stop` cancels the loop, so nothing new is
dispatched, then waits for the jobs that are still running. Those that have not
finished after ``timeout`` seconds are cancelled (with the default
``timeout=None``, it waits for them for as long as it takes). Cancelling a job this
way is not logged as a failure, but ``revert_last_event_on_failure`` still applies.

The scheduler can also be used as an ``async with`` block, which calls ``start()``
on entry and ``stop()`` on exit:

.. code-block:: python

   async def main():
       async with async_sched:
           ...  # the rest of your application

Details worth knowing:

- ``start()`` must be called from a running event loop (a coroutine, or a callback
  of the loop), otherwise it raises :class:`RuntimeError`. It does nothing if the
  loop is already running, and the scheduler can be started again after ``stop()``.
- Job failures are logged, and so is any error raised by the loop itself. Neither
  stops the loop. Use :attr:`~schedium.asyncio.AsyncScheduler.is_running` to check
  that it is alive.
- ``stop()`` only waits for jobs dispatched by the background loop (or by your own
  ``run_pending(wait=False)`` calls). Jobs you ran with ``wait=True`` are yours to
  await.

For a web application, see :doc:`fastapi` for how to tie the loop to the
application's lifespan.

If you need something different, such as a custom sleep strategy, nothing stops you
from writing the loop yourself with :func:`asyncio.create_task`: it is only a
``while True`` around ``await async_sched.run_pending(wait=False)`` and
``await asyncio.sleep(...)``.


Notes and caveats
-----------------

- ``CancelJob`` is supported: returning :class:`~schedium.types.cancel_job.CancelJob`
  from a job removes it from the scheduler.
- If you want "retry within the same token" semantics on failures, enable the
  ``revert_last_event_on_failure`` option. Be careful: this may cause rapid retry
  loops if your scheduler loop runs very frequently.
