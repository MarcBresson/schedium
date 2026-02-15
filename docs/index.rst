Schedium
===========

A lightweight, composable, in-process, pure-python job scheduler.

Why schedium?
-------------

- **No threads, no processes** — jobs run inline when you call `run_pending()`.
- **Composable triggers** — build complex schedules by combining simple primitives with `&` (AND) and `|` (OR).
- **Automatic deduplication** — calling `run_pending()` multiple times within the same time bucket is safe; jobs run at most once per bucket.
- **Zero dependencies** — pure Python, nothing outside the standard library.
- **Fully typed** — first-class type annotations and mypy-checked.
- **Supports all currently maintained Python versions**: 3.10, 3.11, 3.12, 3.13, and 3.14.

Installation
------------

.. code-block:: bash

   pip install schedium

Quick start
-----------

.. code-block:: python

   import time
   from schedium import Every, Job, Weekly, Scheduler

   sched = Scheduler()

   def hello() -> None:
       print("hello")

   print_hello_job = Job(hello, Every(unit="minute", interval=5), name="hello")
   print_hello_job_weekly = Job(hello, Weekly("monday", at="08:00"), name="hello")
   sched.append(print_hello_job)
   sched.append(print_hello_job_weekly)

   while True:
      sched.run_pending()
      time.sleep(1)

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Guides

   Scheduler <usage/scheduler>
   Jobs <usage/jobs>
   Triggers <usage/triggers>
   Advanced <usage/advanced>

.. toctree::
   :maxdepth: 2
   :caption: Concepts

   Concepts <concepts/index>

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   Scheduler <api/scheduler>
   Job <api/job>
   Exceptions <api/exceptions>
   Utils <api/utils>
   Threading <api/threading>
   Triggers <api/triggers/index>

.. toctree::
   :maxdepth: 1
   :caption: Links

   GitHub <https://github.com/MarcBresson/schedium>
   Issues <https://github.com/MarcBresson/schedium/issues>
   PyPI <https://pypi.org/project/schedium/>
