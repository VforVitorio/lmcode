"""Plugin manager — discovers and registers plugins via entry_points."""

from __future__ import annotations

from importlib.metadata import entry_points

import pluggy

from lmcode.plugins.hookspecs import LMCodeSpec

_manager: pluggy.PluginManager | None = None


def get_plugin_manager() -> pluggy.PluginManager:
    """Return the global plugin manager (lazy singleton)."""
    global _manager
    if _manager is not None:
        return _manager

    pm = pluggy.PluginManager("lmcode")
    pm.add_hookspecs(LMCodeSpec)

    # Auto-discover third-party plugins via entry_points
    eps = entry_points(group="lmcode.plugins")
    for ep in eps:
        plugin = ep.load()
        pm.register(plugin(), name=ep.name)

    _manager = pm
    return _manager
