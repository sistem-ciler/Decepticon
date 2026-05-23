"""Framework boot — runs once at ``import decepticon`` time.

Phase 2 of the core/framework/sdk split (per spec §10) hooks into
the framework's import to:

  1. Register the 16 OSS roles with ``decepticon_core.registry.RoleRegistry``
     so plugins can introspect and ``LLMFactory`` can consume the
     pluggable role catalog (closes gap §8 #5).
  2. Build the ``decepticon_core.registry.PluginRegistry`` singleton
     and stash the collisions tuple. Subsequent imports re-use the
     instance.

This module is private (``_boot``); the framework re-imports it from
``decepticon/__init__.py``. Plugin authors interact with the
registries through their public API only.
"""

from __future__ import annotations

import logging

from decepticon_core.contracts.slots import SLOTS_PER_ROLE
from decepticon_core.registry import PluginRegistry, RoleRegistry

logger = logging.getLogger(__name__)


def _register_oss_roles() -> None:
    """Pre-register the 16 OSS roles with ``RoleRegistry``.

    Idempotent — re-imports across multi-process workers all succeed
    silently (spec §16.4 #3). The per-role ``skill_sources`` and
    ``llm_role_fallback`` fields stay empty in Phase 2; framework
    middleware assemblers still derive them from their existing
    sources. Phase 3+ wires them into the role catalog directly.
    """
    for role, slots in SLOTS_PER_ROLE.items():
        RoleRegistry.register(role, slots=slots)


def run() -> None:
    """Execute framework boot — idempotent."""
    _register_oss_roles()
    # Materialize the plugin registry singleton. Phase 2 ships the
    # API surface; Phase 2.x will wire the entry-point walk.
    PluginRegistry.load()
    logger.debug("decepticon framework boot complete (%d roles registered)", len(SLOTS_PER_ROLE))


__all__ = ["run"]
