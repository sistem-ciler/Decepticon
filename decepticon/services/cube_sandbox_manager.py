"""
Cube Sandbox Manager — High-level management of cube-sandbox MicroVMs.

Manages VM lifecycle including creation, pooling, reuse, and cleanup.
Provides a simplified API on top of CubeSandboxBackend for use by
the deception engine and API routes.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Optional

from decepticon.backends.cube_sandbox import CubeSandboxBackend, CubeVMState

logger = logging.getLogger(__name__)

# Default VM templates with pre-installed tools
DEFAULT_TEMPLATES = {
    "kali-rolling": {
        "name": "Kali Linux Rolling",
        "description": "Full Kali Linux with security tools pre-installed",
        "tools": ["nmap", "sqlmap", "metasploit", "burpsuite", "wireshark"],
        "pre_installed": True,
    },
    "ubuntu-minimal": {
        "name": "Ubuntu Minimal",
        "description": "Minimal Ubuntu for lightweight agent tasks",
        "tools": ["python3", "curl", "wget"],
        "pre_installed": False,
    },
    "debian-security": {
        "name": "Debian Security",
        "description": "Debian with security tools",
        "tools": ["nmap", "nikto", "dirb", "gobuster"],
        "pre_installed": True,
    },
}


class CubeSandboxManager:
    """
    High-level manager for cube-sandbox VMs.

    Wraps CubeSandboxBackend with additional features:
    - Named templates
    - VM tagging and labeling
    - Batch operations
    - Monitoring and metrics
    """

    def __init__(
        self,
        base_url: str = "http://localhost:7779",
        token: str = "",
        template: str = "kali-rolling",
        default_cpu: int = 1,
        default_memory_mb: int = 512,
        vm_ttl_seconds: int = 3600,
        max_pool_size: int = 10,
    ):
        self._backend = CubeSandboxBackend(
            base_url=base_url,
            token=token,
            template=template,
            cpu=default_cpu,
            memory_mb=default_memory_mb,
            vm_ttl_seconds=vm_ttl_seconds,
            max_pool_size=max_pool_size,
        )
        self._metrics = {"vms_created": 0, "vms_destroyed": 0, "vms_reused": 0, "errors": 0}

    @property
    def backend(self) -> CubeSandboxBackend:
        return self._backend

    @property
    def base_url(self) -> str:
        return self._backend._base_url

    @property
    def template(self) -> str:
        return self._backend._template

    @property
    def default_cpu(self) -> int:
        return self._backend._cpu

    @property
    def default_memory_mb(self) -> int:
        return self._backend._memory_mb

    @property
    def max_pool_size(self) -> int:
        return self._backend._max_pool_size

    # ── Health and status ─────────────────────────────────────────────────

    def health_check(self) -> dict:
        return self._backend.health_check()

    def get_pool_stats(self) -> dict:
        stats = self._backend.get_pool_stats()
        stats["metrics"] = self._metrics.copy()
        return stats

    def list_templates(self) -> list[dict]:
        return [{"id": k, **v} for k, v in DEFAULT_TEMPLATES.items()]

    # ── VM operations ─────────────────────────────────────────────────────

    def create_vm(
        self,
        template: str = "kali-rolling",
        cpu: int = 1,
        memory_mb: int = 512,
        labels: dict | None = None,
    ) -> CubeVMState:
        """Create a new VM."""
        try:
            vm = self._backend._create_vm()
            self._metrics["vms_created"] += 1
            return vm
        except Exception as e:
            self._metrics["errors"] += 1
            raise

    def destroy_vm(self, vm_id: str) -> None:
        """Destroy a VM."""
        try:
            self._backend._destroy_vm(vm_id)
            self._metrics["vms_destroyed"] += 1
        except Exception as e:
            self._metrics["errors"] += 1
            raise

    def pause_vm(self, vm_id: str) -> None:
        """Pause a VM."""
        self._backend._pause_vm(vm_id)

    def resume_vm(self, vm_id: str) -> CubeVMState:
        """Resume a paused VM."""
        return self._backend._resume_vm(vm_id)

    def execute(self, vm_id: str, command: str, timeout: int = 120) -> dict:
        """Execute a command in a VM."""
        result = self._backend._execute_in_vm(vm_id, command, timeout)
        return {
            "output": result.output,
            "exit_code": result.exit_code,
            "truncated": result.truncated,
        }

    def upload_files(self, vm_id: str, files: dict[str, bytes]) -> list[dict]:
        """Upload files to a VM. files = {path: content}."""
        file_list = list(files.items())
        results = self._backend._upload_to_vm(vm_id, file_list)
        return [{"path": r.path, "error": r.error} for r in results]

    def download_files(self, vm_id: str, paths: list[str]) -> dict[str, bytes]:
        """Download files from a VM. Returns {path: content}."""
        results = self._backend._download_from_vm(vm_id, paths)
        return {r.path: r.content for r in results if r.content is not None and not r.error}

    def list_vms(self) -> list[dict]:
        """List all VMs."""
        stats = self._backend.get_pool_stats()
        vms = []
        for t, v in stats.get("active", []):
            if isinstance(v, dict):
                vms.append(v)
        for v in stats.get("pool", []):
            if isinstance(v, dict):
                vms.append(v)
        return vms

    def cleanup_all(self) -> dict:
        """Destroy all VMs."""
        result = self._backend.destroy_all()
        return result


# ── Singleton ──────────────────────────────────────────────────────────────

_manager_instance: Optional[CubeSandboxManager] = None


def get_cube_manager(
    base_url: str = "http://localhost:7779",
    token: str = "",
    template: str = "kali-rolling",
    default_cpu: int = 1,
    default_memory_mb: int = 512,
    max_pool_size: int = 10,
) -> CubeSandboxManager:
    """Get or create the global CubeSandboxManager singleton."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = CubeSandboxManager(
            base_url=base_url,
            token=token,
            template=template,
            default_cpu=default_cpu,
            default_memory_mb=default_memory_mb,
            max_pool_size=max_pool_size,
        )
    return _manager_instance


def reset_cube_manager():
    """Reset the manager (for testing)."""
    global _manager_instance
    if _manager_instance:
        try:
            _manager_instance._backend.close()
        except Exception:
            pass
    _manager_instance = None
