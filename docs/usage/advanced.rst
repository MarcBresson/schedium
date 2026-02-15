Advanced usage
==============

This section documents advanced usage patterns.

Guide map
---------

- :doc:`celery` — keep schedium for planning and dispatch due work to Celery workers.
- :doc:`timezone` — recommendations for UTC-aware scheduling and DST caveats.
- :doc:`exceptions` — failure behavior, retry semantics, and cancellation helpers.
- :doc:`threading` — run jobs concurrently with thread pools/queues.

When to use this section
------------------------

Use these guides if you need one or more of the following:

- integration with external execution systems,
- predictable behavior across timezones and DST,
- explicit error-handling strategies,
- concurrent execution while preserving trigger semantics.

.. toctree::
   :maxdepth: 2

   With Celery <celery>
   Timezone <timezone>
   Exceptions <exceptions>
   Threading <threading>
