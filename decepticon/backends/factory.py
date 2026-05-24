"""Backend factory — builds sandbox backends from environment configuration.

Supports three backend types:
  - docker:   DockerSandbox (docker exec transport) — legacy, dev-only
  - http:     HTTPSandbox (HTTP daemon in sandbox container) — prod default
  - cube:     CubeSandboxBackend (KVM MicroVM isolation) — strongest isolation

Selection via SANDBOX_BACKEND env var:
  docker | http | cube  (default: http)

For cube backend, additional env vars control VM sizing and pooling:
  CUBE_SANDBOX_URL       — daemon URL (default: http://localhost:7779)
  CUBE_SANDBOX_TOKEN     — API auth token
  CUBE_TEMPLATE          — VM template (default: kali-rolling)
  CUBE_CPU               — vCPUs per VM (default: 1)
  CUBE_MEMORY_MB         — RAM per VM in MB (default: 512)
  CUBE_VM_TTL_SECONDS    — max VM lifetime (default: 3600)
  CUBE_MAX_POOL_SIZE     — warm VM pool size (default: 10)
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Registry of available backends
_BACKENDS = {}


def register_backend(name: str, cls):
    """Register a sandbox backend class."""
    _BACKENDS[name] = cls


def get_backend_names() -> list[str]:
    """Return list of registered backend names."""
    return list(_BACKENDS.keys())


def build_sandbox_backend(
    backend_type: str | None = None,
) -> object:
    """
    Build the sandbox backend based on environment or explicit type.

    Args:
        backend_type: Force a specific backend. If None, reads
            SANDBOX_BACKEND env var (default: http).

    Returns:
        A sandbox backend instance implementing the BaseSandbox interface.

    Raises:
        ValueError: If the requested backend is not registered.
    """
    backend = (backend_type or os.environ.get("SANDBOX_BACKEND", "http")).lower()

    if backend not in _BACKENDS:
        available = ", ".join(_BACKENDS.keys())
        raise ValueError(
            f"Unknown sandbox backend '{backend}'. Available: {available}"
        )

    cls = _BACKENDS[backend]

    if backend == "cube":
        return _build_cube_backend()
    elif backend == "http":
        return _build_http_backend()
    elif backend == "docker":
        return _build_docker_backend()
    else:
        return cls()


def _build_cube_backend():
    """Build CubeSandboxBackend from environment variables."""
    from decepticon.backends.cube_sandbox import (
        CubeSandboxBackend,
        DEFAULT_CUBE_URL,
        DEFAULT_CUBE_TOKEN,
        DEFAULT_TEMPLATE,
        DEFAULT_CPU,
        DEFAULT_MEMORY_MB,
    )

    backend = CubeSandboxBackend(
        base_url=os.environ.get("CUBE_SANDBOX_URL", DEFAULT_CUBE_URL),
        token=os.environ.get("CUBE_SANDBOX_TOKEN", DEFAULT_CUBE_TOKEN),
        template=os.environ.get("CUBE_TEMPLATE", DEFAULT_TEMPLATE),
        cpu=int(os.environ.get("CUBE_CPU", DEFAULT_CPU)),
        memory_mb=int(os.environ.get("CUBE_MEMORY_MB", DEFAULT_MEMORY_MB)),
        vm_ttl_seconds=int(os.environ.get("CUBE_VM_TTL_SECONDS", "3600")),
        max_pool_size=int(os.environ.get("CUBE_MAX_POOL_SIZE", "10")),
    )
    logger.info(
        f"CubeSandboxBackend created: url={backend._base_url}, "
        f"template={backend._template}, cpu={backend._cpu}, "
        f"memory={backend._memory_mb}MB"
    )
    return backend


def _build_http_backend():
    """Build HTTPSandbox from environment variables (existing behavior)."""
    from decepticon.backends.http_sandbox import HTTPSandbox

    base_url = os.environ.get("SAAS_SANDBOX_URL", "http://localhost:9999")
    token = os.environ.get("SAAS_SANDBOX_TOKEN") or None
    backend = HTTPSandbox(base_url=base_url, token=token)
    logger.info(f"HTTPSandbox created: url={base_url}")
    return backend


def _build_docker_backend():
    """Build DockerSandbox from environment variables (legacy)."""
    # DockerSandbox is the original docker-exec transport.
    # Kept for backwards compatibility but not recommended for production
    # because it requires mounting /var/run/docker.sock (host-escape vector).
    try:
        from decepticon.backends.docker_sandbox import DockerSandbox
    except ImportError:
        # DockerSandbox was removed in the HTTP-only refactor.
        # Fall back to HTTPSandbox with a warning.
        logger.warning(
            "DockerSandbox is no longer available (docker-exec transport removed). "
            "Falling back to HTTPSandbox. Set SANDBOX_BACKEND=http explicitly."
        )
        return _build_http_backend()

    container_name = os.environ.get("SANDBOX_CONTAINER", "decepticon-sandbox")
    workspace = os.environ.get("SANDBOX_WORKSPACE", "/workspace")
    backend = DockerSandbox(container_name=container_name, workspace_path=workspace)
    logger.info(f"DockerSandbox created: container={container_name}")
    return backend


# Auto-register built-in backends
register_backend("http", _build_http_backend)
register_backend("cube", _build_cube_backend)
register_backend("docker", _build_docker_backend)
