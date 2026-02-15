With Celery
===========

You can use schedium as a lightweight **schedule planner** and delegate actual
execution to Celery workers.

The clean pattern is to subclass :class:`~schedium.job.Job` and override
:meth:`~schedium.job.Job.run_func`.


- :meth:`~schedium.job.Job.run` already handles due checks and deduplication.
- Overriding only ``run_func`` keeps schedium semantics intact.
- Your custom job only changes *how work is executed* (enqueue to Celery).

Example: dispatch Celery tasks when due
---------------------------------------

.. code-block:: python

   import time
   from datetime import datetime
   from typing import Any

   from celery import Celery
   from schedium import Every, Job, Scheduler
   from schedium.triggers import BaseTrigger

   # redis is great since it can be used both as Celery broker and result backend,
   # but you can use any supported broker/backend.
   celery_app = Celery(
       "my-app",
       broker="redis://localhost:6379/0",
       backend="redis://localhost:6379/0",
   )


   class CeleryDispatchJob(Job):
       """A schedium Job that enqueues a Celery task when due."""

       def __init__(
           self,
           *,
           app: Celery,
           task_name: str,
           trigger: BaseTrigger,
           args: tuple[Any, ...] = (),
           kwargs: dict[str, Any] | None = None,
           queue: str | None = None,
           name: str | None = None,
       ):
           self.app = app
           self.task_name = task_name
           self.args = args
           self.kwargs = kwargs or {}
           self.queue = queue
           super().__init__(func=lambda: None, trigger=trigger, name=name)

       def run_func(self) -> object:
           # Called only when the job is due.
           return self.app.send_task(
               self.task_name,
               args=self.args,
               kwargs=self.kwargs,
               queue=self.queue,
           )


   sched = Scheduler()
   sched.append(
       CeleryDispatchJob(
           app=celery_app,
           task_name="myapp.tasks.generate_report",
           trigger=Every(unit="minute", interval=5),
           kwargs={"report_id": 42},
           queue="reports",
           name="report-dispatch",
       )
   )

   while True:
       # result entries are AsyncResult when dispatched, or JobDidNotRun
       results = sched.run_pending(now=datetime.now())
       print(results)
       time.sleep(1)

Notes
-----

- Install Celery separately (for example, ``pip install celery``).
- This pattern keeps schedium in-process and uses Celery only for async execution.
- ``CancelJob`` still works: return :class:`~schedium.types.cancel_job.CancelJob`
  from ``run_func`` if you want self-removal.
