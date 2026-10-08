"""Opt-in discovery of plugins installed as separate packages."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from importlib.metadata import entry_points

from schedium.plugins.base import Plugin

logger = logging.getLogger("schedium.plugins")

ENTRY_POINT_GROUP = "schedium.plugins"
"""Name of the entry-point group third-party packages publish plugins under."""


def load_entry_point_plugins(
    group: str = ENTRY_POINT_GROUP,
    *,
    names: Iterable[str] | None = None,
) -> list[Plugin]:
    """
    Instantiate the plugins that installed packages published as entry points.

    Nothing is loaded automatically: call this function and pass the result to a
    scheduler (``Scheduler(plugins=load_entry_point_plugins())``) when you want
    this behaviour.

    A package publishes a plugin in its ``pyproject.toml``::

        [project.entry-points."schedium.plugins"]
        my-plugin = "my_package:MyPlugin"

    The entry point may point to a :class:`~schedium.plugins.Plugin` subclass
    (instantiated without arguments), to a zero-argument callable returning a
    plugin, or to a plugin instance. Entry points that fail to load or that do
    not produce a plugin are logged and skipped.

    Parameters
    ----------
    group : str, default "schedium.plugins"
        The entry-point group to read.
    names : Iterable[str], optional
        Only load the entry points with these names.

    Returns
    -------
    list[Plugin]
        The plugin instances, sorted by entry-point name for a stable order.
    """
    wanted = None if names is None else set(names)
    plugins: list[Plugin] = []

    for ep in sorted(entry_points(group=group), key=lambda e: e.name):
        if wanted is not None and ep.name not in wanted:
            continue
        try:
            obj = ep.load()
            if isinstance(obj, type) and issubclass(obj, Plugin):
                obj = obj()
            elif not isinstance(obj, Plugin) and callable(obj):
                obj = obj()
            if not isinstance(obj, Plugin):
                raise TypeError(
                    f"entry point produced {type(obj).__name__}, not a Plugin"
                )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "Could not load schedium plugin %r from %r", ep.name, ep.value
            )
            continue
        plugins.append(obj)
        logger.info("Loaded schedium plugin %r from %r", ep.name, ep.value)

    return plugins
