import importlib.resources
from collections.abc import Mapping
from typing import Any

from deepagents.backends import CompositeBackend, FilesystemBackend

from .factory import build_sandbox_backend
from .http_sandbox import HTTPSandbox

# Skills ship as package data under ``decepticon/skills/`` and are read
# in-process by a local ``FilesystemBackend`` (not the sandbox container).
# Resolving via ``importlib.resources`` yields the correct on-disk location
# for every install shape — wheel (site-packages), editable (repo checkout),
# and the langgraph Docker image (``/app/decepticon/skills``) — so no
# container-specific path is hardcoded.
SKILLS_LOCAL_PATH = str(importlib.resources.files("decepticon") / "skills")


def make_agent_backend(
    sandbox: Any,
    *,
    extra_routes: Mapping[str, Any] | None = None,
) -> CompositeBackend:
    """Compose the runtime backend for a Decepticon agent.

    Routes ``/skills/`` to a local ``FilesystemBackend`` reading the
    package's ``decepticon/skills`` tree in-process, and routes everything
    else (notably ``/workspace/``) through the sandbox transport
    (``HTTPSandbox``). Returning a ``CompositeBackend`` lets
    ``SkillsMiddleware`` and ``FilesystemMiddleware`` share the same
    backend object while reading from different physical storage:

      /skills/...   ->  decepticon/skills/... read in-process (~5ms)
      /workspace/.. ->  sandbox container via HTTP (isolated, persistent)

    Args:
        sandbox: the default transport (``HTTPSandbox`` in OSS). All
            paths that don't match a more specific route fall through
            here.
        extra_routes: optional caller-supplied prefix -> backend mapping
            merged on top of the OSS defaults. Closes gap §8 #1 from
            the SaaS consumption audit: commercial overlays mount their
            own asset trees (``/skills/plugins/apt-emulation/``, etc.)
            without forking ``make_agent_backend``. Per spec §16.4 #5,
            routes are sorted by descending prefix length so the longest
            match wins deterministically — a tenant-specific
            ``/skills/tenant/<id>/`` route overrides the default
            ``/skills/`` prefix.
    """
    base: dict[str, Any] = {
        "/skills/": FilesystemBackend(
            root_dir=SKILLS_LOCAL_PATH,
            virtual_mode=True,
        ),
    }
    merged: dict[str, Any] = {**base, **dict(extra_routes or {})}
    # Longest-prefix-wins: sort by len(prefix) descending so a tenant
    # path like ``/skills/tenant/<id>/`` always matches before the
    # generic ``/skills/`` default.
    sorted_routes = dict(
        sorted(merged.items(), key=lambda kv: len(kv[0]), reverse=True)
    )
    return CompositeBackend(default=sandbox, routes=sorted_routes)


__all__ = [
    "HTTPSandbox",
    "SKILLS_LOCAL_PATH",
    "build_sandbox_backend",
    "make_agent_backend",
]
