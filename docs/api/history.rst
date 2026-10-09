API reference: History plugin
=============================

The ``schedium-history`` package. See :doc:`/plugins/history` for a guide.

HistoryPlugin
-------------

.. autoclass:: schedium_history.HistoryPlugin
   :members:
   :show-inheritance:

Backends
--------

.. autoclass:: schedium_history.MemoryStore
   :members:

.. autoclass:: schedium_history.JSONLStore
   :members:

.. autoclass:: schedium_history.SQLAlchemyStore
   :members:

Records
-------

.. autoclass:: schedium_history.RunRecord
   :members:

.. autoclass:: schedium_history.ErrorInfo
   :members:

.. autoclass:: schedium_history.LogEntry
   :members:

.. autoclass:: schedium_history.Retention
   :members:

Backend protocols
-----------------

.. autoclass:: schedium_history.TraceStore
   :members:

.. autoclass:: schedium_history.QueryableStore
   :members:

.. autoclass:: schedium_history.PrunableStore
   :members:
