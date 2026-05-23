"""Framework boot — runs once at ``import decepticon`` time.

Hooks into the framework's import to:

  1. Register the 16 OSS roles with ``RoleRegistry`` so plugins can
     introspect and ``LLMFactory`` can consume the pluggable role
     catalog (gap §8 #5).
  2. Build the ``PluginRegistry`` singleton (entry-point walk +
     collision detection).
  3. Compose a ``RoleResolution`` per OSS role from the framework's
     local slot/skill knowledge and push it into ``PluginRegistry``
     so ``introspect_role()`` returns audit-grade snapshots
     (gap §8 #7).

This module is private (``_boot``); the framework re-imports it from
``decepticon/__init__.py``. Plugin authors interact with the
registries through their public API only.
"""

from __future__ import annotations

import logging

from decepticon_core.contracts.slots import SLOTS_PER_ROLE, MiddlewareSlot
from decepticon_core.registry import (
    MiddlewareInfo,
    PluginRegistry,
    RoleRegistry,
    RoleResolution,
)

logger = logging.getLogger(__name__)


def _register_oss_roles() -> None:
    """Pre-register the 16 OSS roles with ``RoleRegistry``.

    Idempotent — re-imports across multi-process workers all succeed
    silently (spec §16.4 #3). The per-role ``skill_sources`` and
    ``llm_role_fallback`` fields stay empty here; the framework's
    ``skills_sources_for`` derives skill sources at agent-build time
    so multi-tenant overlays (Phase 2 ``extra_routes`` + plugin
    skill paths) still get layered on top.
    """
    for role, slots in SLOTS_PER_ROLE.items():
        RoleRegistry.register(role, slots=slots)


def _push_role_resolutions() -> None:
    """Compose a ``RoleResolution`` per OSS role + register with
    ``PluginRegistry``.

    Closes spec §8 gap #7 — audit consumers call
    ``PluginRegistry.load().introspect_role(role)`` and receive a
    deterministic, hashable snapshot of the role's middleware stack.
    The actual middleware *instances* live in the framework runtime;
    this snapshot carries the slot names + owner attribution audit
    systems care about.

    Skill sources and tool list are intentionally left empty here —
    they vary per agent invocation (plugin contributions layer in via
    ``load_plugin_skill_sources`` and ``load_plugin_tools`` at build
    time). A future commit can record them lazily via a per-build
    hook if introspection consumers ask for it.
    """
    for role, slots in SLOTS_PER_ROLE.items():
        middleware_stack = tuple(
            MiddlewareInfo(slot=slot.value, name=slot.value, owner="decepticon")
            for slot in MiddlewareSlot
            if slot in slots
        )
        resolution = RoleResolution(
            role=role,
            middleware_stack=middleware_stack,
            tool_list=(),
            skill_sources=(),
            llm_model="",
            overrides_applied=(),
        )
        PluginRegistry.set_role_resolution(role, resolution)


def run() -> None:
    """Execute framework boot — idempotent."""
    _register_oss_roles()
    PluginRegistry.load()
    _push_role_resolutions()
    logger.debug(
        "decepticon framework boot complete (%d roles registered, %d resolutions)",
        len(SLOTS_PER_ROLE),
        len(SLOTS_PER_ROLE),
    )


__all__ = ["run"]
