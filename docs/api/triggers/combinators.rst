API reference: Combinator triggers
==================================

Combinator triggers let you build schedules by composing other triggers.

- Use ``A & B`` (AND) to require that both branches match.
- Use ``A | B`` (OR) to allow either branch to match.

In most cases you will compose using the operators rather than instantiating
the classes directly.

.. code-block:: python

   from schedium import Every, On

   trigger1 = Every(unit="day", interval=1)
   trigger2 = On(unit="hour_of_day", value=8)
   trigger3 = On(unit="minute_of_hour", value=0)

   trigger = trigger1 & trigger2 & trigger3
   print(trigger)
   # AndTrigger(
   #   Every(unit='day', interval=1, offset=0),
   #   On(unit='hour_of_day', value=8),
   #   On(unit='minute_of_hour', value=0)
   # )


.. autoclass:: schedium.triggers.base.AndTrigger
   :members:
   :undoc-members:
   :show-inheritance:

.. autoclass:: schedium.triggers.base.OrTrigger
   :members:
   :undoc-members:
   :show-inheritance:
