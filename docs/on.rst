On (constraint trigger)
=======================

:class:`~schedium.triggers.on.On` matches when a datetime falls *on* a specific value
(e.g. “hour is 8”, “day-of-week is Monday”, “it’s a weekend day”).

`On` is a **constraint** trigger: it filters time, but it does not define a cadence.
To make a schedulable trigger, combine it with a tick source like
:class:`~schedium.triggers.every.Every`, :class:`~schedium.triggers.sugar.tick.Tick`,
or :class:`~schedium.triggers.datetime.AtDateTimeTrigger`.

Quick examples
--------------

Weekdays at 08:00

.. code-block:: python

   from schedium import Every, On

   trigger = (
       Every(unit="day", interval=1)
       & On(unit="weekdays", value=1)
       & On(unit="hour_of_day", value=8)
       & On(unit="minute_of_hour", value=0)
   )

First day of the month at midnight

.. code-block:: python

   from schedium import Every, On

   trigger = (
       Every(unit="day", interval=1)
       & On(unit="day_of_month", value=1)
       & On(unit="hour_of_day", value=0)
       & On(unit="minute_of_hour", value=0)
   )

Units and semantics
-------------------

Supported ``unit`` values (see :data:`schedium.schemas.on_unit.OnUnit`):

- ``"year"``
- ``"month_of_year"`` (1..12)
- ``"week_of_year"`` (ISO week number via ``datetime.isocalendar().week``)
- ``"weekdays"`` (Mon..Fri; ``value`` is ignored)
- ``"weekend_days"`` (Sat..Sun; ``value`` is ignored)
- ``"day_of_week"`` (cron-style 1..7 where 1=Mon)
- ``"day_of_month"`` (1..31)
- ``"hour_of_day"`` (0..23)
- ``"minute_of_hour"`` (0..59)
- ``"second_of_minute"`` (0..59)
- ``"millisecond_of_second"`` (0..999)

Notes and gotchas
-----------------

Tick source required
   If your trigger tree contains only constraints (like `On` / `Between` /
   `BetweenDateTime`), :meth:`~schedium.scheduler.Scheduler.append` raises
   ``ValueError``. Add a tick source.

Day-of-week numbering
   ``On(unit="day_of_week", ...)`` uses **cron-style** numbering 1..7 via
   ``datetime.isoweekday()``.

Late start + one-shot triggers
   :class:`~schedium.triggers.datetime.AtDateTimeTrigger` can fire “late” (first time
   the scheduler is called after the run date). Composing it with `On` can be a
   useful guardrail to prevent running outside an intended calendar window.

API reference
-------------

full API reference for :class:`~schedium.triggers.on.On` avaible in :ref:`api/triggers/on`.

.. autoclass:: schedium.triggers.on.On
   :show-inheritance:
