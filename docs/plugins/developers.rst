Plugins
=======

Plugins let you observe jobs, run extra actions around them and change how they
run, without touching the jobs themselves. They work the same way with every
scheduler: :class:`~schedium.scheduler.Scheduler`,
:class:`~schedium.asyncio.AsyncScheduler`,
:class:`~schedium.threading.ThreadedJobsScheduler` and
:class:`~schedium.threading.QueuedJobsScheduler`.

A plugin is an instance of a :class:`~schedium.plugins.Plugin` subclass. Pick the
hooks you care about and override only those.

.. code-block:: python

   from schedium import Every, Job, Plugin, Scheduler

   class Announce(Plugin):
       def on_job_start(self, run):
           print("starting", run.job.identifier)

       def on_job_failure(self, run):
           print("failed:", run.exception)

   scheduler = Scheduler(plugins=[Announce()])
   scheduler.append(Job(lambda: None, Every(unit="minute", interval=5), name="hello"))

Ready-made plugins are installed as separate packages. The first one,
:doc:`schedium-history </plugins/history>`, remembers every run (when it started
and stopped, its status, errors and logs).

Attaching plugins
-----------------

- **To a scheduler**, with ``Scheduler(plugins=[...])`` or
  ``scheduler.add_plugin(plugin)`` (``remove_plugin`` detaches it). The plugin applies to every job of that
  scheduler, including the jobs added before it. This is the usual choice.
- **To one job**, with ``Job(..., plugins=[...])``, for behaviour that only that
  job needs (for example a retry policy).

Scheduler plugins are the outer layer and job plugins the inner layer.
:class:`~schedium.threading.ThreadedJobsScheduler` and
:class:`~schedium.threading.QueuedJobsScheduler` also apply the plugins of the
:class:`~schedium.scheduler.Scheduler` they wrap.

Hooks
-----

Observer hooks
~~~~~~~~~~~~~~

Observer hooks are notified at fixed moments. They cannot change what a job
does, and an exception raised inside one is logged on the ``schedium.plugins``
logger and otherwise ignored: a broken plugin never fails a job, and the other
plugins still run.

.. list-table::
   :header-rows: 1
   :widths: 28 72

   * - Hook
     - When it is called
   * - ``on_job_start(run)``
     - Right before a job runs.
   * - ``on_job_success(run)``
     - The job returned normally. ``run.result`` is its return value.
   * - ``on_job_failure(run)``
     - The job raised. ``run.exception`` is the exception, which is still raised
       to the scheduler afterwards.
   * - ``on_job_cancelled(run)``
     - The job returned :class:`~schedium.types.cancel_job.CancelJob`.
       ``run.cancel_reason`` is the reason.
   * - ``on_job_end(run)``
     - After every run, whatever its outcome (like ``finally``). It is the only
       hook that also fires for skipped and interrupted runs.
   * - ``on_job_added(scheduler, job)``, ``on_job_removed(scheduler, job, reason)``
     - A job is appended to a scheduler, or removed because it cancelled itself.
   * - ``on_scheduler_start(scheduler)``, ``on_scheduler_stop(scheduler)``
     - A scheduler starts or stops: ``AsyncScheduler.start()``/``stop()``,
       ``QueuedJobsScheduler.start_workers()``/``stop_workers()``,
       ``ThreadedJobsScheduler.shutdown()`` (stop only), and
       :class:`~schedium.threading.SchedulerThread` for a plain
       :class:`~schedium.scheduler.Scheduler`. ``on_scheduler_stop`` may be called
       more than once: write it so that it is safe to repeat.

When several plugins are attached, ``on_job_start`` runs in registration order
(scheduler plugins first). ``on_job_success``, ``on_job_failure``,
``on_job_cancelled`` and ``on_job_end`` run in the reverse order, like nested
context managers.

Wrap hooks
~~~~~~~~~~

A wrap hook surrounds the call of the job and decides how, and whether, it runs.
Override :meth:`~schedium.plugins.Plugin.wrap_run` to take part in it. Call
``call_next()`` to run the next layer (ultimately the job): zero times to skip
the job, once to run it, several times to retry it.

.. code-block:: python

   class Retry(Plugin):
       def __init__(self, attempts=3):
           self.attempts = attempts

       def wrap_run(self, run, call_next):
           for attempt in range(1, self.attempts + 1):
               try:
                   return call_next()
               except Exception:
                   if attempt == self.attempts:
                       raise

Unlike observer hooks, an exception that escapes a wrap hook is **not**
swallowed: it becomes the outcome of the run. Returning a different value
replaces the job's result.

:class:`~schedium.asyncio.AsyncScheduler` awaits jobs, so it uses the
asynchronous variant, :meth:`~schedium.plugins.Plugin.wrap_run_async`. A plugin
that must change behaviour on every scheduler implements both; one that
implements only ``wrap_run`` simply does not take part on the async scheduler.

.. code-block:: python

   class Timeout(Plugin):
       def __init__(self, seconds):
           self.seconds = seconds

       async def wrap_run_async(self, run, call_next):
           return await asyncio.wait_for(call_next(), self.seconds)

The run
-------

Every per-run hook receives a :class:`~schedium.plugins.RunContext`, a plain
dataclass describing that execution: a unique ``run_id``, the ``job``, the
``scheduler``, the trigger ``event``, ``started_at`` / ``ended_at`` (timezone-aware
UTC), the ``status`` (a :class:`~schedium.plugins.RunStatus`), the ``result`` or
``exception``, and an ``extras`` dictionary where plugins can keep their own state
for the duration of the run.

Jobs are identified by :attr:`Job.identifier <schedium.job.Job.identifier>`: the
``id`` if you gave one, otherwise the ``name``, otherwise the
``module.qualname`` of the function. Give jobs an ``id`` when you want their
history to survive renaming a function.

Plugins and async schedulers
----------------------------

Hooks are plain methods. On :class:`~schedium.asyncio.AsyncScheduler` they are
called on the event loop, so a hook that blocks (files, databases, network)
would freeze every job. Set ``blocking = True`` on such a plugin: its hooks are
then run in a worker thread. They must be thread-safe, and the flag has no
effect on the threaded schedulers, which have no event loop to protect.

Hooks that are called from synchronous methods (``on_job_added``,
``on_job_removed``, ``on_scheduler_start`` on ``AsyncScheduler``) always run
inline.

Knowing which run you are in
----------------------------

Code that cannot receive the :class:`~schedium.plugins.RunContext` as an
argument, such as the job itself or a :class:`logging.Handler`, can call
:func:`~schedium.plugins.get_current_run`. It uses :mod:`contextvars`, so it is
correct per thread and per asyncio task: jobs that overlap in time each see their
own run. It returns ``None`` outside of a run.

.. code-block:: python

   from schedium.plugins import get_current_run

   def job():
       run = get_current_run()
       print("this is run", run.run_id)

A job that has no plugin attached has no run context, so ``get_current_run()``
returns ``None`` for it as well.

Writing and publishing a plugin
-------------------------------

Subclass :class:`~schedium.plugins.Plugin` in your own code, or ship it as a
package. A package can also advertise its plugin through an entry point, so
applications can find it without importing it by name:

.. code-block:: toml

   [project.entry-points."schedium.plugins"]
   my-plugin = "my_package:MyPlugin"

The entry point may name a :class:`~schedium.plugins.Plugin` subclass (created
without arguments), a function returning a plugin, or a plugin instance.
Applications opt in explicitly:

.. code-block:: python

   from schedium import Scheduler
   from schedium.plugins import load_entry_point_plugins

   scheduler = Scheduler(plugins=load_entry_point_plugins())

Only plugins that can be created without configuration make sense as entry
points. A plugin that needs settings, like the history plugin that needs to know
where to save, is created by the application and passed explicitly.

.. note::

   Plugin packages should depend on ``schedium`` and use only the public API of
   :mod:`schedium.plugins`. :mod:`schedium.plugins._runner` is internal.
