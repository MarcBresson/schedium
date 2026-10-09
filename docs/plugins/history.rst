History: remember job runs
==========================

``schedium-history`` is a :doc:`plugin </plugins/developers>` that keeps a trace of
every job run, so you can answer "did the nightly job run?", "how long does it
take?" and "why did it fail?".

For each run it records:

- when it **started** and **ended**, and the **duration**;
- its **status** (:class:`~schedium.plugins.RunStatus`): ``running``, ``success``,
  ``failed``, ``cancelled``, ``interrupted`` or ``skipped``;
- the **error**, with its type, message and full traceback, when the job failed;
- the reason, when the job cancelled itself with
  :class:`~schedium.types.cancel_job.CancelJob`;
- the **trigger** and the trigger *event* (time bucket) that made the job due;
- optionally, the **logs** emitted while the job ran.

It is a separate package, so schedium itself keeps zero dependencies:

.. code-block:: bash

   pip install schedium-history                 # memory and JSON Lines file backends
   pip install "schedium-history[sqlalchemy]"   # + SQL databases

Quick start
-----------

.. code-block:: python

   from schedium import Every, Job, Scheduler
   from schedium_history import JSONLStore, HistoryPlugin

   store = JSONLStore("runs.jsonl")
   scheduler = Scheduler(plugins=[HistoryPlugin(store)])
   scheduler.append(Job(hello, Every(unit="minute", interval=5), name="hello"))

   scheduler.run_pending()

   for run in store.get_runs(job_id="hello", limit=10):
       print(run.started_at, run.status.value, run.duration)

The plugin works with every scheduler. With the
:class:`~schedium.asyncio.AsyncScheduler` the writes happen in a worker thread, so
a slow database never blocks the event loop.

Backends
--------

All backends are used the same way: build one and give it to
:class:`~schedium_history.HistoryPlugin`.

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - Backend
     - Use it for
   * - :class:`~schedium_history.MemoryStore`
     - Tests, short-lived processes, or a "last N runs" view. Lost when the
       process ends. ``MemoryStore(max_runs=1000)`` bounds its size.
   * - :class:`~schedium_history.JSONLStore`
     - A simple, human-readable file with one JSON object per line, easy to grep or
       load with ``jq`` or pandas. One process at a time.
   * - :class:`~schedium_history.SQLAlchemyStore`
     - Any SQL database supported by SQLAlchemy 2.1 (SQLite, PostgreSQL, MySQL...).
       Shared by several processes, queryable with SQL.
   * - Your own
     - Any object with a ``save(record)`` method, see :ref:`custom-backend`.

SQL databases
~~~~~~~~~~~~~

.. code-block:: python

   from schedium_history import SQLAlchemyStore, HistoryPlugin

   store = SQLAlchemyStore("postgresql+psycopg://user:password@host/db")
   # or reuse an engine you already have:
   store = SQLAlchemyStore(engine, table_name="job_runs")

The table (``schedium_runs`` by default) is created if it does not exist; pass
``create_tables=False`` to manage it with your own migrations (the expected columns
are described by ``store.table``). The store uses SQLAlchemy's synchronous API;
asynchronous engines are not supported.

Capturing logs
--------------

Enable ``capture_logging`` and every log record emitted by the standard
:mod:`logging` module *while a job runs* is attached to that run. The jobs do not
change.

.. code-block:: python

   import logging

   logging.basicConfig(level=logging.INFO)   # let INFO records through
   log = logging.getLogger("etl")

   def import_orders():
       log.info("imported %d orders", 42)

   scheduler = Scheduler(plugins=[HistoryPlugin(store, capture_logging=True)])

   run = store.get_runs(job_id="import_orders")[0]
   [entry.message for entry in run.logs]       # ['imported 42 orders']

- Logs are attributed to the right run even when several jobs run at the same time,
  on the async scheduler or on threads. Records emitted outside of a job are ignored.
- A record is captured only if it reaches the handler, so it must pass the level of
  its logger. The root logger lets only ``WARNING`` and above through unless you
  configure it as above.
- ``capture_level`` (default ``INFO``) sets the minimum level kept, and
  ``capture_loggers=["etl"]`` restricts capture to some loggers instead of the
  root logger.
- Tasks created with :func:`asyncio.create_task` by a job are captured. Threads a
  job starts itself are not.
- Captured logs are stored with the run, so mind their size on chatty jobs.

Crash detection
---------------

By default a ``running`` record is written as soon as a job starts, and replaced when
it ends. If the process dies mid-run, the record stays ``running`` forever, which is
how you can tell a crashed run from a slow one:

.. code-block:: python

   from datetime import datetime, timedelta, timezone
   from schedium.plugins import RunStatus

   stale = store.get_runs(
       status=RunStatus.RUNNING,
       until=datetime.now(timezone.utc) - timedelta(hours=1),
   )

Pass ``write_at_start=False`` to write each run only once, when it ends.

Retention
---------

History grows forever unless you limit it:

.. code-block:: python

   from datetime import timedelta
   from schedium_history import Retention, HistoryPlugin

   plugin = HistoryPlugin(
       store,
       retention=Retention(max_runs_per_job=500, max_age=timedelta(days=30)),
   )

A run is deleted as soon as it exceeds *either* limit. The policy is applied every
``prune_every`` finished runs (default 100) and when the scheduler stops. It needs a
backend that can delete, which all the built-in ones can.

Querying
--------

:class:`~schedium_history.MemoryStore`, :class:`~schedium_history.JSONLStore` and
:class:`~schedium_history.SQLAlchemyStore` can be read back:

.. code-block:: python

   store.get_run(run_id)
   store.get_runs(
       job_id="hello",
       status=[RunStatus.FAILED, RunStatus.INTERRUPTED],
       since=datetime(2026, 1, 1, tzinfo=timezone.utc),
       limit=20,
   )

Results are :class:`~schedium_history.RunRecord` objects, newest first. Timestamps
are timezone-aware UTC.

.. _custom-backend:

Writing your own backend
------------------------

Backends are described by small protocols that you implement without inheriting
from anything:

- :class:`~schedium_history.TraceStore`: **required**. A single method,
  ``save(record)``, that inserts or updates the record identified by
  ``record.run_id``. It is called when a run starts and again when it ends, from
  whichever thread runs the job, so it must be thread-safe. The record object is
  reused between calls, so store a copy of its content.
- :class:`~schedium_history.QueryableStore`: optional. Adds ``get_run`` and
  ``get_runs``.
- :class:`~schedium_history.PrunableStore`: optional. Adds ``prune``, which lets
  the plugin apply a retention policy.

.. code-block:: python

   import redis

   class RedisStore:
       def __init__(self, client: redis.Redis):
           self.client = client

       def save(self, record):
           self.client.set(f"run:{record.run_id}", json.dumps(record.to_dict()))

   scheduler = Scheduler(plugins=[HistoryPlugin(RedisStore(client))])

``record.to_dict()`` and ``RunRecord.from_dict()`` convert to and from plain
JSON-compatible values.

When storing fails
------------------

If the store raises (database down, disk full), the error is logged on the
``schedium.plugins`` logger and the job is not affected.
