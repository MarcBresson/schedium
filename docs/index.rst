Schedium
===========

Schedium is a small in-process scheduler.

- You register **jobs** (a callable + a trigger).
- You call ``Scheduler.run_pending(...)`` periodically.
- Jobs run inline and are **deduplicated** per trigger token, i.e., they won't run more than once for the same trigger event.

Installation
------------

.. code-block:: bash

   pip install schedium

Quick start
-----------

.. code-block:: python

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
   Utils <api/utils>
   Triggers <api/triggers/index>

.. toctree::
   :maxdepth: 1
   :caption: Links

   GitHub <https://github.com/MarcBresson/schedium>
   Issues <https://github.com/MarcBresson/schedium/issues>
   PyPI <https://pypi.org/project/schedium/>
