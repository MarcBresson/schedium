API reference: Plugins
======================

The plugin framework in :mod:`schedium.plugins`. See :doc:`/plugins/developers` for a guide.

Plugin
------

.. autoclass:: schedium.plugins.Plugin
   :members:
   :undoc-members:
   :show-inheritance:

RunContext
----------

.. autoclass:: schedium.plugins.RunContext
   :members:
   :undoc-members:

RunStatus
---------

.. autoclass:: schedium.plugins.RunStatus
   :members:
   :undoc-members:
   :show-inheritance:

Helpers
-------

.. autofunction:: schedium.plugins.get_current_run

.. autofunction:: schedium.plugins.load_entry_point_plugins

.. autodata:: schedium.plugins.ENTRY_POINT_GROUP
   :no-value:
