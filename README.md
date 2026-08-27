<p align="center">
  <img src="docs/logo.svg" alt="schedium logo" width="180" />
</p>

<h1 align="center">schedium</h1>

<p align="center">
  <em>A lightweight, composable, in-process, pure-python job scheduler.</em>
</p>

<p align="center">
  <a href="https://github.com/MarcBresson/schedium/actions/workflows/tests.yml"><img src="https://github.com/MarcBresson/schedium/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/MarcBresson/schedium/actions/workflows/docs.yml"><img src="https://github.com/MarcBresson/schedium/actions/workflows/docs.yml/badge.svg" alt="Docs"></a>
  <a href="https://pypi.org/project/schedium/"><img src="https://img.shields.io/pypi/v/schedium?color=blue" alt="PyPI version"></a>
  <a href="https://pypi.org/project/schedium/"><img src="https://img.shields.io/pypi/pyversions/schedium" alt="Python versions"></a>
  <a href="https://github.com/MarcBresson/schedium/blob/main/LICENSE"><img src="https://img.shields.io/github/license/MarcBresson/schedium" alt="License"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff"></a>
  <a href="https://numpydoc.readthedocs.io/en/latest/format.html"><img src="https://img.shields.io/badge/docstyle-numpydoc-blue" alt="numpydoc"></a>
  <a href="http://mypy-lang.org/"><img src="https://img.shields.io/badge/type--checked-mypy-blue" alt="mypy"></a>
</p>

---

## Why schedium?

Most Python schedulers either require a background thread / daemon or force you into a rigid cron syntax. **schedium** takes a different approach:

- **No threads, no processes** — jobs run inline when you call `run_pending()`. They can be ran in [threads](https://schedium.readthedocs.io/en/latest/usage/threading.html) or [asynchronously](https://schedium.readthedocs.io/en/latest/usage/asyncios.html) using helpers.
- **Composable triggers** — build complex schedules by combining simple primitives with `&` (AND) and `|` (OR). See [`composing triggers` doc](https://schedium.readthedocs.io/en/latest/usage/triggers.html#composing-triggers-and-or)
- **Automatic deduplication** — calling `run_pending()` multiple times within the same time bucket is safe; jobs run at most once per bucket. See [`deduplication` doc](https://schedium.readthedocs.io/en/latest/concepts/trigger_tokens.html#trigger-tokens-deduplication)
- **Zero dependencies** — pure Python, nothing outside the standard library.
- **Fully typed** — first-class type annotations and mypy-checked.
- **Supports all currently maintained Python versions**: 3.10, 3.11, 3.12, 3.13, and 3.14.

[link to the documentation](https://schedium.readthedocs.io)

## Installation

```bash
pip install schedium
```

## Quick start

```python
import time
from schedium import Every, Job, Scheduler, Weekly

sched = Scheduler()

def hello():
    print("hello!")

# Every 5 minutes
sched.append(Job(hello, Every(unit="minute", interval=5), name="5-min"))

# Every Monday at 09:30
sched.append(Job(hello, Weekly("monday", at="09:30"), name="weekly"))

while True:
    sched.run_pending()
    time.sleep(1)
```

## Threading (optional)

schedium runs jobs inline by default. If you want multi-threading, use the helpers in
`schedium.threading`:

- `ThreadedJobsScheduler`: runs each *due* job on a worker thread (thread pool).
- `QueuedJobsScheduler`: keeps the scheduler in your thread and enqueues due jobs for worker threads.
- `SchedulerThread`: runs the scheduler loop itself in a dedicated thread.

```python
from schedium import Every, Job, Scheduler
from schedium.threading import SchedulerThread, ThreadedJobsScheduler

sched = Scheduler()
sched.append(Job(lambda: print("tick"), Every(unit="second", interval=1)))

threaded = ThreadedJobsScheduler(sched, max_workers=8)
runner = SchedulerThread(threaded, interval=1.0)
runner.start()

# ... later
runner.stop()
runner.join()
threaded.shutdown()
```

## Async (optional)

For `asyncio` applications, use `schedium.asyncio.AsyncScheduler`. It is used the
same way as `Scheduler`, but runs due jobs on the event loop — `async def` jobs are
awaited directly, plain sync jobs run in an executor so they never block the loop.

```python
import asyncio
from schedium import Every, Job
from schedium.asyncio import AsyncScheduler

async_sched = AsyncScheduler()
async_sched.append(Job(lambda: print("tick"), Every(unit="second", interval=1)))

async def main():
    while True:
        await async_sched.run_pending()
        await asyncio.sleep(1)

asyncio.run(main())
```

## Composing triggers

Triggers are the building blocks of schedules. Combine them freely:

```python
from schedium import Every, On, Between

# Every minute, but only on weekdays between 9 AM and 5 PM
trigger = (
    Every(unit="minute", interval=1)
    & On(unit="weekdays")
    & Between(unit="hour_of_day", start=9, end=17)
)
```

```python
from schedium import Every, On

# Every hour, at minute 12 OR minute 55
trigger = (
    Every(unit="hour", interval=1)
    & (On(unit="minute_of_hour", value=12) | On(unit="minute_of_hour", value=55))
)
```

### Available triggers

| Trigger | Role | Example |
|---|---|---|
| `Every(unit, interval)` | Epoch-aligned cadence | `Every(unit="minute", interval=5)` |
| `Tick(granularity)` | Always matches; sets the dedup bucket | `Tick("day")` |
| `On(unit, value)` | Equality constraint | `On(unit="hour_of_day", value=8)` |
| `Between(unit, start, end)` | Range constraint (inclusive) | `Between(unit="hour_of_day", start=9, end=17)` |
| `AtDateTime(run_date)` | One-shot at a specific datetime | `AtDateTime(datetime(2026, 3, 1, 12, 0))` |
| `BetweenDateTime(start, end)` | Datetime window constraint | `BetweenDateTime(start_date=..., end_date=...)` |
| `Daily(at=...)` | Convenience: daily (optionally at a time) | `Daily(at="09:30")` |
| `Weekly(day, at=...)` | Convenience: weekly on a weekday | `Weekly("mon", at="09:30")` |
| `trigger_a & trigger_b` | AND combinator | All conditions must match |
| `trigger_a \| trigger_b` | OR combinator | Either condition can match |

## Deduplication

schedium automatically deduplicates job runs. Calling `run_pending()` repeatedly within the same time bucket will only execute the job once:

```python
from datetime import datetime
from schedium import JobDidNotRun, Every, Job, Scheduler

sched = Scheduler()
sched.append(Job(lambda: print("tick"), Every(unit="minute", interval=1)))

# First call at 10:05 → runs the job
sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))

# Second call at 10:05 → already ran for this bucket
result = sched.run_pending(now=datetime(2026, 2, 4, 10, 5, 0))
assert result[0] is JobDidNotRun

# Next minute → runs again
sched.run_pending(now=datetime(2026, 2, 4, 10, 6, 0))
```

## Inspecting next run times

```python
from datetime import datetime
from schedium import Every, Job, Scheduler

sched = Scheduler()
sched.append(Job(lambda: None, Every(unit="minute", interval=5)))

next_run = sched.time_of_next_run(after=datetime(2026, 2, 4, 10, 3, 0))
print(next_run)  # datetime(2026, 2, 4, 10, 5, 0)
```

## Timezone handling

For predictable behavior, use UTC-aware datetimes:

```python
import time
from datetime import datetime, timezone
from schedium import Every, Job, Scheduler

sched = Scheduler()
sched.append(Job(lambda: print("tick"), Every(unit="minute", interval=1)))

while True:
    sched.run_pending(now=datetime.now(timezone.utc))
    time.sleep(1)
```

Local timezones work too (via `zoneinfo`), but be aware of DST transitions — see the [docs](https://schedium.readthedocs.io) for details.

## Documentation

Full documentation is built with Sphinx and hosted alongside the project:

- **Guides**: Scheduler usage, job creation, trigger composition
- **Concepts**: Granularity, trigger tokens & deduplication, window time
- **API reference**: Every class and function documented with numpydoc

Build locally:

```bash
pip install -e . --group docs
sphinx-build -b html docs docs/_build/html
```

## Development

### Setup

```bash
git clone https://github.com/MarcBresson/schedium.git
cd schedium
python -m venv .venv && source .venv/bin/activate
pip install -e . --group dev --group test --group docs
pre-commit install
```

### Run tests

```bash
pytest
```

### Linting & formatting

The project uses [Ruff](https://github.com/astral-sh/ruff) for linting and formatting, [mypy](http://mypy-lang.org/) for type checking, and [numpydoc](https://numpydoc.readthedocs.io/) for docstring validation — all enforced via [pre-commit](https://pre-commit.com/):

```bash
pre-commit run --all-files
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git switch -c feature/my-feature`)
3. Ensure all tests pass (`pytest`) and pre-commit hooks are clean
4. Open a pull request

## License

schedium is licensed under the [Apache License 2.0](LICENSE).
