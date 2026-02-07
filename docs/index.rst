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


   sched.append(Job(hello, Every(unit="minute", interval=1), name="hello"))

   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 0, 30))
   assert results[0] is DidNotRun

   results = sched.run_pending(now=datetime(2026, 2, 4, 10, 1, 0))
   # prints: hello
   assert results == [None]

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
