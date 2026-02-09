Triggers
========

A **trigger** determines *when* a :class:`~schedium.job.Job` is due.

In schedium, triggers are designed to be composed:

- Use a **tick source** to define a cadence (or at least a deduplication bucket).
- AND it with one or more **constraints** to narrow down the times you want.

Tick sources vs constraints
---------------------------

Tick sources
^^^^^^^^^^^^

A **tick source** makes a trigger tree schedulable by defining how time advances.
Common tick sources are:

- :class:`~schedium.triggers.every.Every` (epoch-aligned cadence)
- :class:`~schedium.triggers.sugar.tick.Tick` (always matches, but caps runs by bucket)
- :class:`~schedium.triggers.datetime.AtDateTime` (one-shot)

Constraints
^^^^^^^^^^^

A **constraint** filters time but does not define a cadence by itself.
Examples:

- :class:`~schedium.triggers.on.On` ("hour is 8")
- :class:`~schedium.triggers.between.Between` ("hour between 9 and 17")
- :class:`~schedium.triggers.datetime.BetweenDateTime` ("inside this datetime window")

If you try to schedule a constraint-only trigger tree, :meth:`~schedium.scheduler.Scheduler.append`
raises ``ValueError``.

Composing triggers (AND / OR)
-----------------------------

AND (intersection)
^^^^^^^^^^^^^^^^^^

Use ``&`` to require that *all* conditions are satisfied.

.. code-block:: python

   from schedium import Every, On

   # Every day, but only at 08:00
   trigger = (
       Every(unit="day", interval=1)
       & On(unit="hour_of_day", value=8)
       & On(unit="minute_of_hour", value=0)
   )

OR (alternatives)
^^^^^^^^^^^^^^^^^

Use ``|`` to allow either branch to match.

.. code-block:: python

   from schedium import Every, On

   # Either 08:00 or 17:00
   trigger = (
       Every(unit="day", interval=1)
       & (
           (On(unit="hour_of_day", value=8) & On(unit="minute_of_hour", value=0))
           | (On(unit="hour_of_day", value=17) & On(unit="minute_of_hour", value=0))
       )
   )

How “next time” is computed
---------------------------

schedium computes future schedules using window time:

- Each trigger implements ``next_window(after) -> TimeWindow | None``.
- A job’s next run time is ``window.start``.

See the Concepts pages for details:

- :doc:`Window time <../concepts/window_time>`
- :doc:`Trigger tokens & deduplication <../concepts/trigger_tokens>`
- :doc:`Granularity <../concepts/granularity>`

Trigger overview
----------------

Every (cadence)
^^^^^^^^^^^^^^^

:class:`~schedium.triggers.every.Every` matches on epoch-aligned boundaries.

.. code-block:: python

   from schedium import Every

   Every(unit="minute", interval=5)          # every 5 minutes
   Every(unit="hour", interval=2, offset=1)  # every 2 hours, phase-shifted

Tick (bucket limiter)
^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.sugar.tick.Tick` always matches, but it defines the
bucket size used for deduplication.

This is useful when you want constraints to drive the schedule but still prevent
repeated execution.

.. code-block:: python

   from schedium import Tick, On

   # Runs once per day when the scheduler first sees a matching time.
   trigger = Tick("day") & On(unit="hour_of_day", value=8)

On (equality constraint)
^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.on.On` matches when a datetime field equals a value
(e.g. hour=8, weekday=Mon).

Between (range constraint)
^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.between.Between` matches when a datetime field is
within an inclusive range (e.g. hours 9..17).

BetweenDateTime (datetime window)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.datetime.BetweenDateTime` matches inside a concrete
inclusive datetime window.

AtDateTime (one-shot)
^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.datetime.AtDateTime` fires once at/after a target
datetime, even if the scheduler starts late.

Weekly (helper)
^^^^^^^^^^^^^^^

:func:`~schedium.triggers.sugar.weekly.Weekly` is a convenience helper that
builds a composed trigger for “weekly on weekday X, optionally at HH:MM”.

API reference
-------------

The full trigger API reference is here: :doc:`Triggers (API) <../api/triggers/index>`.

Direct links:

- :doc:`Every <../api/triggers/every>`
- :doc:`Tick <../api/triggers/tick>`
- :doc:`On <../api/triggers/on>`
- :doc:`Between <../api/triggers/between>`
- :doc:`BetweenDateTime / AtDateTime <../api/triggers/datetime>`
- :doc:`Combinators (AND/OR) <../api/triggers/combinators>`
- :doc:`Weekly <../api/triggers/weekly>`
