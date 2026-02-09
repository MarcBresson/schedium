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

   # Every 2 weeks, but only at 08:00
   trigger = (
       Every(unit="week", interval=2)
       & On(unit="hour_of_day", value=8)
       & On(unit="minute_of_hour", value=0)
   )

OR (alternatives)
^^^^^^^^^^^^^^^^^

Use ``|`` to allow either branch to match.

.. code-block:: python

   from schedium import Every, On

   # at 08:00 and anytime in the 17th hour every 2 days
   trigger = (
       Every(unit="day", interval=2)
       & (
           (On(unit="hour_of_day", value=8) & On(unit="minute_of_hour", value=0))
           | (On(unit="hour_of_day", value=17))
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

.. code-block:: python

   from schedium import Every, On

   # Weekdays at 08:00
   trigger = (
      Every(unit="day", interval=1)
      & On(unit="weekdays", value=1)
      & On(unit="hour_of_day", value=8)
      & On(unit="minute_of_hour", value=0)
   )

Between (range constraint)
^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.between.Between` matches when a datetime field is
within an inclusive range (e.g. hours 9..17).

.. code-block:: python

   from schedium import Between, Every

   # Every 10 minutes, but only during working hours
   trigger = Every(unit="minute", interval=10) & Between(
      unit="hour_of_day", start=9, end=17
   )

BetweenDateTime (datetime window)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.datetime.BetweenDateTime` matches inside a concrete
inclusive datetime window.

.. code-block:: python

   from datetime import datetime, timezone
   from schedium import BetweenDateTime, Every

   window = BetweenDateTime(
      start_date=datetime(2026, 2, 8, 1, 0, tzinfo=timezone.utc),
      end_date=datetime(2026, 2, 8, 2, 0, tzinfo=timezone.utc),
   )
   trigger = Every(unit="minute", interval=1) & window

AtDateTime (one-shot)
^^^^^^^^^^^^^^^^^^^^^

:class:`~schedium.triggers.datetime.AtDateTime` fires once at/after a target
datetime, even if the scheduler starts late.

.. code-block:: python

   from datetime import datetime
   from schedium import AtDateTime

   trigger = AtDateTime(datetime(2026, 2, 8, 12, 0, 0))

Weekly (helper)
^^^^^^^^^^^^^^^

:func:`~schedium.triggers.sugar.weekly.Weekly` is a convenience helper that
builds a composed trigger for “weekly on weekday X, optionally at HH:MM”.

.. code-block:: python

   from schedium import Weekly

   trigger = Weekly("mon", at="09:30")

Combinators (AndTrigger / OrTrigger)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Although you will typically compose triggers using ``&`` and ``|``, schedium
also exposes :class:`~schedium.triggers.AndTrigger` and
:class:`~schedium.triggers.OrTrigger`.

.. code-block:: python

   from schedium import Every, On

   # Equivalent to: AndTrigger([Every(...), On(...)])
   trigger = Every(unit="day", interval=1) & On(unit="hour_of_day", value=8)

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
