"""Plugin registry — central read-only view of discovered plugins.

Closes gaps §8 #4 (collision detection) and §8 #7 (introspection API).
Phase 2 wires this into the framework boot path; this module ships the
public API surface plugin-author guides reference directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from decepticon_core.registry.conflict import PluginConflictWarning
from decepticon_core.registry.resolution import RoleResolution


@dataclass(frozen=True)
class PluginInfo:
    """Static description of one discovered plugin.

    Returned by ``PluginRegistry.list_plugins()``.
    """

    name: str
    package: str
    bundle: str | None
    groups: tuple[str, ...] = field(default_factory=tuple)


class PluginRegistry:
    """Read-only view of all plugins loaded into the current process.

    Built by ``load()`` at framework boot — walks entry-point groups
    (``decepticon.tools``, ``.middleware``, ``.subagents``, ``.bundles``,
    ``.skills``, ``.callbacks``, ``.roles``, ``.prompts``) and snapshots
    the result. Subsequent imports of this module re-use the singleton.

    Phase 1 ships the API shape; Phase 2 wires the actual entry-point
    walk and collision tracking. Until then ``load()`` returns an
    empty registry — calls succeed but yield no plugins.
    """

    _instance: PluginRegistry | None = None
    _plugins: tuple[PluginInfo, ...] = ()
    _collisions: tuple[PluginConflictWarning, ...] = ()

    @classmethod
    def load(cls) -> PluginRegistry:
        """Return the singleton, building it on first call.

        Phase 1 stub: returns an empty registry. Phase 2 implements
        the entry-point walk; subsequent calls return the cached
        instance.
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_plugins(self) -> tuple[PluginInfo, ...]:
        """Return every discovered plugin in name-sorted order."""
        return self._plugins

    def get_plugin(self, name: str) -> PluginInfo | None:
        """Return the ``PluginInfo`` for ``name``, or ``None`` if absent."""
        for info in self._plugins:
            if info.name == name:
                return info
        return None

    def detect_collisions(self) -> tuple[PluginConflictWarning, ...]:
        """Return all collisions surfaced during ``load()``.

        Phase 1 stub: returns an empty tuple. Phase 2 populates the
        collisions tuple as side effect of the entry-point walk.
        """
        return self._collisions

    def introspect_role(self, role: str) -> RoleResolution | None:
        """Return the resolved ``RoleResolution`` for ``role``.

        Phase 1 stub: returns ``None`` for every role. Phase 2 builds
        ``RoleResolution`` by composing the role's middleware stack,
        tool list, skill sources, and applied overrides.

        Read-only by contract — never mutates registry state
        (spec §16.4 #2).
        """
        del role  # unused in Phase 1 stub
        return None
