schedium
===========

schedium is a small in-process scheduler.

- You register **jobs** (a callable + a trigger).
- You call ``Scheduler.run_pending(...)`` periodically.
- Jobs run inline and are **deduplicated** per trigger token.

Quick start
-----------

.. code-block:: python

   from datetime import datetime
   from schedium import DidNotRun, Every, Job, Scheduler

   sched = Scheduler()

   def hello() -> None:
       print("hello")

   print_hello_job = Job(hello, Every(unit="minute", interval=1), name="hello")
   sched.append(print_hello_job)

   while True:
      sched.run_pending()

Contents
--------

.. toctree::
   :maxdepth: 2
   :caption: Guides

   jobs

.. toctree::
   :maxdepth: 2
   :caption: API Reference

   api/job
