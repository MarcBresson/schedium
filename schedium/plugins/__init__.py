"""
Plugin framework.

Plugins observe and modify how jobs run. Subclass :class:`Plugin`, override the
hooks you care about, and attach instances to a scheduler or a job::

    from schedium import Plugin, Scheduler

    class Announce(Plugin):
        def on_job_start(self, run):
            print("starting", run.job.identifier)

    scheduler = Scheduler(plugins=[Announce()])

Plugins distributed as their own packages (for instance ``schedium-history``)
use this same public API.
"""

from schedium.plugins.base import Plugin
from schedium.plugins.context import RunContext, RunStatus, get_current_run
from schedium.plugins.discovery import ENTRY_POINT_GROUP, load_entry_point_plugins

__all__ = [
    "ENTRY_POINT_GROUP",
    "Plugin",
    "RunContext",
    "RunStatus",
    "get_current_run",
    "load_entry_point_plugins",
]
