# schedium-history

A [schedium](https://github.com/MarcBresson/schedium) plugin that remembers what happened to every job run:
when it started and stopped, its status, its error (with traceback) and, optionally, the logs it emitted.

```bash
pip install schedium-history                 # memory and JSON Lines file backends
pip install "schedium-history[sqlalchemy]"   # + SQL databases
```

```python
from schedium import Every, Job, Scheduler
from schedium_history import JSONLStore, HistoryPlugin

store = JSONLStore("runs.jsonl")  # or MemoryStore(), SQLAlchemyStore("sqlite:///runs.db"), your own
scheduler = Scheduler(plugins=[HistoryPlugin(store, capture_logging=True)])
scheduler.append(Job(lambda: print("hi"), Every(unit="minute", interval=5), name="hello"))

scheduler.run_pending()

for run in store.get_runs(job_id="hello", limit=10):
    print(run.started_at, run.status.value, run.duration, run.error)
```

It works with every schedium scheduler (sync, threaded, queued and asyncio). Features:

- **Backends**: in memory, a JSON Lines file, any SQL database through SQLAlchemy 2.1, or your own
  (a single `save(record)` method is enough).
- **Logs**: opt-in capture of the standard `logging` records emitted while a job runs, attributed to the
  right run even when jobs overlap.
- **Crash detection**: a `running` record is written when a job starts, so runs that never finished stand out.
- **Retention**: keep at most N runs per job and/or delete runs older than a `timedelta`.
- **Querying**: `get_run` / `get_runs` with job, status and time filters.

Documentation: <https://schedium.readthedocs.io/en/latest/plugins/history.html>

This package requires schedium 1.2.0 or newer, the first release with the plugin API.
