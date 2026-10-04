With FastAPI
============

FastAPI runs on an ``asyncio`` event loop, so :class:`~schedium.asyncio.AsyncScheduler`
fits naturally: the scheduler loop runs as a background task on the same loop that
serves requests, without blocking it, and ``async def`` jobs can share the
application's async resources (HTTP clients, database sessions, ...).

The scheduler is started and stopped with FastAPI's
`lifespan <https://fastapi.tiangolo.com/advanced/events/>`_: everything before the
``yield`` runs at startup, everything after it at shutdown. The loop itself is
:meth:`AsyncScheduler.start() <schedium.asyncio.AsyncScheduler.start>`, described in
:ref:`running-the-loop-in-the-background`.

Example: run the scheduler in the application's lifespan
--------------------------------------------------------

.. code-block:: python

  from collections.abc import AsyncIterator
  from contextlib import asynccontextmanager

  from fastapi import FastAPI
  from schedium import Every, Job
  from schedium.asyncio import AsyncScheduler

  scheduler = AsyncScheduler(require_async_jobs=True)


  async def refresh_cache() -> None:
      # Runs on the event loop, next to your request handlers.
      ...


  scheduler.append(Job(refresh_cache, Every(unit="minute", interval=5), name="refresh-cache"))


  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncIterator[None]:
      async with scheduler:
          yield


  app = FastAPI(lifespan=lifespan)


  @app.get("/")
  async def root() -> dict[str, str]:
      return {"status": "ok"}

Run it as usual, for example with ``uvicorn main:app``. ``async with scheduler``
calls :meth:`~schedium.asyncio.AsyncScheduler.start` when the application starts,
and :meth:`~schedium.asyncio.AsyncScheduler.stop` when the server shuts down.

To control the tick rate or how long shutdown waits for running jobs, call the
methods explicitly:

.. code-block:: python

  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncIterator[None]:
      scheduler.start(interval=0.5)
      try:
          yield
      finally:
          # give running jobs 10 seconds to finish, then cancel them
          await scheduler.stop(timeout=10)

Why the ``try/finally``?
~~~~~~~~~~~~~~~~~~~~~~~~

On a normal shutdown, the server resumes the lifespan after the ``yield`` and the
``finally`` makes no difference. It matters when an *exception is raised at the*
``yield``: in an :func:`~contextlib.asynccontextmanager`, nothing after the ``yield``
runs in that case unless it is in a ``finally``, so ``stop()`` would be skipped and
the loop task and any running job would be left to be destroyed with the event loop.

While your application serves requests, the lifespan is suspended at the ``yield``
waiting for the shutdown message. That is the only place it can be interrupted, and
only the following can raise there:

- **The lifespan task is cancelled** (:class:`asyncio.CancelledError`). For
  example, the event loop is being torn down while the lifespan is still
  suspended, or the server cancels the application task.
- **The server fails while waiting for the shutdown message.** The exception is
  raised from the ``receive()`` call that the lifespan is blocked on.

Things that look like candidates but do *not* reach the ``yield``:

- An exception in a route handler: it becomes a 500 response for that request.
- An exception in a scheduled job: it is logged by schedium and the loop keeps going.
- An exception *before* the ``yield`` (startup): the code after it is never entered,
  and neither is the ``finally``. If you start something else between ``start()`` and
  the ``yield``, it needs its own cleanup (for example with
  :class:`contextlib.AsyncExitStack`), or put it inside the ``try``.

.. note::

  The ``finally`` is a safety net, not a guarantee. When you press Ctrl+C twice,
  uvicorn switches to a forced exit and skips the lifespan shutdown entirely: it
  never sends the shutdown message. Whether your ``finally`` still runs then depends
  on the event loop teardown, so do not rely on it. Write jobs so they tolerate being
  interrupted, because that is what a force quit (or a ``SIGKILL``) does.

``async with scheduler`` does not need any of this: ``__aexit__`` runs on every exit
path, exactly like a ``finally``.

Accessing the scheduler from request handlers
---------------------------------------------

Instead of a module-level global, you can keep the scheduler on ``app.state`` and
reach it from handlers through the request. This also lets you add jobs at runtime:

.. code-block:: python

  from fastapi import FastAPI, Request

  @asynccontextmanager
  async def lifespan(app: FastAPI) -> AsyncIterator[None]:
      app.state.scheduler = AsyncScheduler()
      async with app.state.scheduler:
          yield

  app = FastAPI(lifespan=lifespan)

  @app.post("/jobs/ping")
  async def add_ping_job(request: Request) -> dict[str, int]:
      request.app.state.scheduler.append(Job(ping, Every(unit="minute", interval=1)))
      return {"jobs": len(request.app.state.scheduler.jobs)}

Notes
-----

- Job failures are logged by schedium rather than raised, so one failing job never
  stops the scheduler loop.
- Prefer ``async def`` jobs. Plain functions are offloaded to a thread pool; use
  ``AsyncScheduler(require_async_jobs=True)`` if you would rather have them rejected
  than run in a thread by accident (see :doc:`asyncio`).
- Use ``AsyncScheduler(max_concurrency=...)`` to cap how many jobs run at once, so
  scheduled work cannot starve request handling.
- **Testing:** you do not need the loop to test your jobs. Call
  ``await scheduler.run_pending(now=...)`` with a fixed ``now`` instead.
- **Multiple workers:** every worker process (``uvicorn --workers N``, gunicorn)
  runs its own lifespan and therefore its own scheduler, so each job would run once
  *per worker*. Run the scheduler in a single dedicated process, or guard jobs with
  a distributed lock, if that is not what you want.
