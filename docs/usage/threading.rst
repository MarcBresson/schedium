Threading schedulers
====================

schedium runs jobs inline by default (no background threads). For some
applications, it is useful to keep schedium's trigger evaluation but run job
functions concurrently.

This page documents the threading helpers in :mod:`schedium.threading`.

When to use which
-----------------

- Use :class:`~schedium.threading.ThreadedJobsScheduler` when you want to keep the
  scheduler loop in your current thread, but execute each *due* job in a worker
  thread pool.
- Use :class:`~schedium.threading.SchedulerThread` when you want the scheduler loop
  itself to run in a dedicated background thread.
- Use :class:`~schedium.threading.QueuedJobsScheduler` when you want scheduling
  decisions to stay synchronous (in your thread), while job execution is handled by
  one or more worker threads consuming a queue.
- If your application is built on ``asyncio`` rather than threads, use
  :class:`~schedium.asyncio.AsyncScheduler` instead -- see :doc:`asyncio`.


ThreadedJobsScheduler (thread pool)
-----------------------------------

In this model, you call ``run_pending`` yourself, but due jobs are dispatched to a
thread pool.

.. code-block:: python

   import time
   from concurrent.futures import TimeoutError

   from schedium import Every, Job, JobDidNotRun, Scheduler
   from schedium.threading import ThreadedJobsScheduler

   sched = Scheduler()

   def cpu_or_io_work() -> str:
      # Your job code
      return "ok"

   sched.append(Job(cpu_or_io_work, Every(unit="second", interval=1)))

   threaded = ThreadedJobsScheduler(sched, max_workers=8)
   try:
      while True:
         futures = threaded.run_pending(wait=False)

         for fut in futures:
            if fut is JobDidNotRun:
               continue

            # Non-blocking check: fut.result(timeout=0) either returns immediately
            # or raises TimeoutError.
            try:
                value = fut.result(timeout=0)
            except TimeoutError:
                continue
            except Exception as exc:
                print(f"job failed: {exc!r}")
            else:
                print(f"job returned: {value!r}")

        time.sleep(1)
   finally:
      threaded.shutdown()


SchedulerThread (scheduler loop in background thread)
-----------------------------------------------------

This model is useful when your main thread should stay free for other work.

.. code-block:: python

   import time
   from schedium import Every, Job, Scheduler
   from schedium.threading import SchedulerThread, ThreadedJobsScheduler

   sched = Scheduler()
   sched.append(Job(lambda: print("tick"), Every(unit="second", interval=1)))

   threaded = ThreadedJobsScheduler(sched, max_workers=8)
   runner = SchedulerThread(threaded, interval=1.0)
   runner.start()

   try:
       time.sleep(10)
   finally:
       runner.stop()
       runner.join()
       threaded.shutdown()

   # If the scheduler thread crashed, check runner.exception.


QueuedJobsScheduler (producer queue + worker threads)
-----------------------------------------------------

This model keeps trigger evaluation and due/skip decisions in your thread, then
enqueues due jobs for worker threads.

.. code-block:: python

   import queue
   import time
   from schedium import Every, Job, Scheduler
   from schedium.threading import QueuedJobsScheduler

   sched = Scheduler()
   sched.append(Job(lambda: "ok", Every(unit="second", interval=1)))

   # Provide your own queue if you want backpressure.
   job_queue = queue.Queue(maxsize=1000)
   queued = QueuedJobsScheduler(sched, worker_count=4, queue_=job_queue)

   try:
       while True:
           futures = queued.run_pending()
           # futures is aligned with sched.jobs; entries are JobDidNotRun or Future
           time.sleep(1)
   finally:
       queued.stop_workers(join=True)


Notes and caveats
-----------------

- Jobs should be thread-safe. If jobs mutate shared state, protect it with your own
  locks or use thread-safe primitives.
- ``CancelJob`` is supported: returning :class:`~schedium.types.cancel_job.CancelJob`
  from a job removes it from the scheduler.
- If you want "retry within the same token" semantics on failures, enable the
  ``revert_last_event_on_failure`` option (where available). Be careful: this may
  cause rapid retry loops if your scheduler loop runs very frequently.
