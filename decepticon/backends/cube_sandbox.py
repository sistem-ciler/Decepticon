"""
Cube Sandbox Backend — KVM MicroVM isolation for Decepticon agents.

Provides hardware-level isolation for red team agent execution using
tencentcloud/cube-sandbox KVM MicroVMs instead of Docker containers.

Architecture:
    Agent → CubeSandboxBackend → cube-sandbox API → KVM MicroVM
                                            ↓
                              Each agent gets its own kernel
                              <60ms cold start, E2B-compatible

The cube-sandbox SDK provides:
    - create()  → spawn a new MicroVM from a snapshot
    - execute() → run commands inside the VM
    - upload()  → write files into the VM
    - download() → read files from the VM
    - destroy() → tear down the VM
    - pause() / resume() → hibernate for reuse

This backend wraps the cube-sandbox HTTP API to provide the same
interface as HTTPSandbox and DaemonSandbox, so the agent code
(Decepticon agents, bash tool, middleware stack) works unchanged.

Trust model: each MicroVM is a fresh KVM instance with its own kernel.
Even if an agent achieves code execution inside the VM, it cannot
escape to the host or other VMs. This is fundamentally stronger than
Docker container isolation (shared kernel).

Requirements:
    - Bare-metal server or cloud VM with KVM support (/dev/kvm)
    - XFS filesystem on /data/cubelet for VM snapshots
    - cube-sandbox daemon running on the host
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
import uuid
from typing import ClassVar, Optional

import httpx
from deepagents.backends.protocol import (
    ExecuteResponse,
    FileDownloadResponse,
    FileUploadResponse,
)
from deepagents.backends.sandbox import BaseSandbox

from decepticon.sandbox_kernel import BackgroundJob, BackgroundJobTracker

logger = logging.getLogger(__name__)


# ── Cube-sandbox SDK types ─────────────────────────────────────────────────

CUBE_API_VERSION = "v1"
DEFAULT_CUBE_URL = "http://localhost:7779"
DEFAULT_CUBE_TOKEN = ""
DEFAULT_TEMPLATE = "kali-rolling"
DEFAULT_CPU = 1
DEFAULT_MEMORY_MB = 512


class CubeVMState:
    """Tracks the state of a single cube-sandbox MicroVM."""

    def __init__(self, vm_id: str, template: str, cpu: int, memory_mb: int):
        self.vm_id = vm_id
        self.template = template
        self.cpu = cpu
        self.memory_mb = memory_mb
        self.created_at = time.monotonic()
        self.last_used = time.monotonic()
        self.status = "running"  # running | paused | destroyed
        self._reuse_count = 0

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_used

    def touch(self):
        self.last_used = time.monotonic()
        self._reuse_count += 1


class CubeSandboxBackend(BaseSandbox):
    """
    Sandbox backend that uses tencentcloud/cube-sandbox KVM MicroVMs.

    Each engagement gets its own isolated MicroVM with a fresh kernel.
    The VM is created from a template snapshot (e.g. kali-rolling with
    pre-installed security tools) and can be paused/resumed for reuse
    or destroyed when the engagement is complete.

    This provides hardware-level isolation — even if an agent achieves
    RCE inside the VM, it cannot escape to the host or other VMs.

    Args:
        base_url: cube-sandbox daemon URL
        token: API authentication token
        template: VM template name (default: kali-rolling)
        cpu: Number of vCPUs per VM
        memory_mb: Memory per VM in MB
        vm_ttl_seconds: Maximum VM lifetime before forced recycle
        max_pool_size: Maximum number of warm VMs to keep for reuse
        sandbox_token: Legacy token for compat with HTTPSandbox interface
    """

    _jobs: ClassVar[BackgroundJobTracker] = BackgroundJobTracker()
    _log_offsets: ClassVar[dict[str, int]] = {}

    def __init__(
        self,
        base_url: str = DEFAULT_CUBE_URL,
        token: str = DEFAULT_CUBE_TOKEN,
        template: str = DEFAULT_TEMPLATE,
        cpu: int = DEFAULT_CPU,
        memory_mb: int = DEFAULT_MEMORY_MB,
        vm_ttl_seconds: int = 3600,
        max_pool_size: int = 10,
        sandbox_token: str | None = None,
        **kwargs,
    ):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._template = template
        self._cpu = cpu
        self._memory_mb = memory_mb
        self._vm_ttl_seconds = vm_ttl_seconds
        self._max_pool_size = max_pool_size
        self._sandbox_token = sandbox_token
        self._client: httpx.Client | None = None

        # VM pool management
        self._vm_pool: list[CubeVMState] = []  # warm, reusable VMs
        self._active_vms: dict[str, CubeVMState] = {}  # tenant_id → VM

        # Background job tracking (mirrors HTTPSandbox interface)
        self._local_jobs: dict[str, BackgroundJob] = {}

    @property
    def id(self) -> str:
        return f"cube-sandbox:{self._base_url}"

    # ── HTTP client ────────────────────────────────────────────────────────

    def _http(self) -> httpx.Client:
        if self._client is None:
            headers = {"User-Agent": "decepticon-cube-sandbox/1"}
            if self._token:
                headers["Authorization"] = f"Bearer {self._token}"
            self._client = httpx.Client(
                base_url=self._base_url,
                headers=headers,
                timeout=300.0,
            )
        return self._client

    def close(self) -> None:
        """Destroy all active VMs and close the HTTP client."""
        for vm_id, vm in list(self._active_vms.items()):
            try:
                self._destroy_vm(vm.vm_id)
            except Exception:
                logger.warning(f"Failed to destroy VM {vm_id} during close")
        for vm in self._vm_pool:
            try:
                self._destroy_vm(vm.vm_id)
            except Exception:
                pass
        self._vm_pool.clear()
        self._active_vms.clear()
        if self._client is not None:
            self._client.close()
            self._client = None

    # ── VM lifecycle ───────────────────────────────────────────────────────

    def _create_vm(self) -> CubeVMState:
        """Create a new MicroVM from the template snapshot."""
        resp = self._http().post(
            f"/api/{CUBE_API_VERSION}/vms",
            json={
                "template": self._template,
                "cpu": self._cpu,
                "memory_mb": self._memory_mb,
                "labels": {"managed_by": "decepticon"},
            },
        )
        resp.raise_for_status()
        data = resp.json()
        vm_id = data["vm_id"]
        vm = CubeVMState(vm_id=vm_id, template=self._template, cpu=self._cpu, memory_mb=self._memory_mb)
        logger.info(f"Created cube-sandbox VM {vm_id} (template={self._template})")
        return vm

    def _destroy_vm(self, vm_id: str) -> None:
        """Destroy a MicroVM."""
        resp = self._http().delete(f"/api/{CUBE_API_VERSION}/vms/{vm_id}")
        if resp.status_code not in (200, 204, 404):
            resp.raise_for_status()
        logger.info(f"Destroyed cube-sandbox VM {vm_id}")

    def _pause_vm(self, vm_id: str) -> None:
        """Pause (hibernate) a VM for later reuse."""
        resp = self._http().post(f"/api/{CUBE_API_VERSION}/vms/{vm_id}/pause")
        if resp.status_code in (200, 204):
            logger.info(f"Paused cube-sandbox VM {vm_id}")

    def _resume_vm(self, vm_id: str) -> CubeVMState:
        """Resume a paused VM."""
        resp = self._http().post(f"/api/{CUBE_API_VERSION}/vms/{vm_id}/resume")
        resp.raise_for_status()
        data = resp.json()
        vm = CubeVMState(
            vm_id=vm_id,
            template=data.get("template", self._template),
            cpu=data.get("cpu", self._cpu),
            memory_mb=data.get("memory_mb", self._memory_mb),
        )
        vm.status = "running"
        logger.info(f"Resumed cube-sandbox VM {vm_id}")
        return vm

    def _get_or_create_vm(self, tenant_id: str) -> CubeVMState:
        """
        Get an existing VM for the tenant, or create/warm-start a new one.

        Reuse strategy:
        1. If the tenant already has an active VM, return it.
        2. If there's a warm VM in the pool, assign it to the tenant.
        3. Otherwise create a new VM.
        """
        # Check existing
        if tenant_id in self._active_vms:
            vm = self._active_vms[tenant_id]
            if vm.status == "running" and vm.age_seconds < self._vm_ttl_seconds:
                vm.touch()
                return vm
            else:
                # Expired or dead — recycle
                self._destroy_vm(vm.vm_id)
                del self._active_vms[tenant_id]

        # Try pool
        if self._vm_pool:
            vm = self._vm_pool.pop(0)
            if vm.status == "paused":
                vm = self._resume_vm(vm.vm_id)
            vm.touch()
            self._active_vms[tenant_id] = vm
            logger.info(f"Reusing pooled VM {vm.vm_id} for tenant {tenant_id}")
            return vm

        # Create new
        vm = self._create_vm()
        self._active_vms[tenant_id] = vm
        return vm

    def _recycle_vm(self, tenant_id: str) -> None:
        """
        Release a tenant's VM back to the pool or destroy it.
        Keeps warm VMs for reuse up to max_pool_size.
        """
        if tenant_id not in self._active_vms:
            return
        vm = self._active_vms.pop(tenant_id)
        if len(self._vm_pool) < self._max_pool_size:
            try:
                self._pause_vm(vm.vm_id)
                vm.status = "paused"
                self._vm_pool.append(vm)
                return
            except Exception:
                pass
        self._destroy_vm(vm.vm_id)

    # ── BaseSandbox abstract methods ────────────────────────────────────────

    def _execute_in_vm(self, vm_id: str, command: str, timeout: int | None = None) -> ExecuteResponse:
        """Execute a command inside a specific MicroVM."""
        effective_timeout = timeout or 120
        resp = self._http().post(
            f"/api/{CUBE_API_VERSION}/vms/{vm_id}/execute",
            json={"command": command, "timeout": effective_timeout},
            timeout=float(effective_timeout + 15),
        )
        resp.raise_for_status()
        data = resp.json()
        return ExecuteResponse(
            output=data.get("output", ""),
            exit_code=data.get("exit_code", 0),
            truncated=data.get("truncated", False),
        )

    def _upload_to_vm(self, vm_id: str, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """Upload files into a specific MicroVM."""
        payload = {
            "files": [
                {"path": path, "data_b64": base64.b64encode(data).decode("ascii")}
                for path, data in files
            ]
        }
        resp = self._http().post(
            f"/api/{CUBE_API_VERSION}/vms/{vm_id}/upload",
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
        return [FileUploadResponse(path=f["path"], error=f.get("error")) for f in data.get("files", [])]

    def _download_from_vm(self, vm_id: str, paths: list[str]) -> list[FileDownloadResponse]:
        """Download files from a specific MicroVM."""
        resp = self._http().post(
            f"/api/{CUBE_API_VERSION}/vms/{vm_id}/download",
            json={"paths": paths},
        )
        resp.raise_for_status()
        data = resp.json()
        out: list[FileDownloadResponse] = []
        for item in data.get("files", []):
            content_b64 = item.get("data_b64")
            content = base64.b64decode(content_b64) if content_b64 else None
            out.append(FileDownloadResponse(path=item["path"], content=content, error=item.get("error")))
        return out

    # ── Tenant-scoped operations (used by agent middleware) ─────────────────

    def _tenant_vm_id(self, tenant_id: str = "default") -> str:
        """Get the active VM ID for a tenant (for direct VM-level ops)."""
        vm = self._get_or_create_vm(tenant_id)
        return vm.vm_id

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        """Execute in the tenant's active VM."""
        vm_id = self._tenant_vm_id("default")
        return self._execute_in_vm(vm_id, command, timeout)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        vm_id = self._tenant_vm_id("default")
        return self._upload_to_vm(vm_id, files)

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        vm_id = self._tenant_vm_id("default")
        return self._download_from_vm(vm_id, paths)

    # ── tmux / background surface — mirrors HTTPSandbox ─────────────────────

    def execute_tmux(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
        workspace_path: str | None = None,
    ) -> str:
        """Execute via tmux in the active VM. Mirrors HTTPSandbox.execute_tmux."""
        vm_id = self._tenant_vm_id("default")
        if not command and not is_input:
            # Read tmux screen
            resp = self._execute_in_vm(vm_id, f"tmux capture-pane -p -t {session} 2>/dev/null || echo 'Session not found'", timeout=10)
            return resp.output
        elif is_input:
            resp = self._execute_in_vm(vm_id, f"tmux send-keys -t {session} '{command}' Enter", timeout=10)
            return resp.output
        else:
            safe_cmd = command.replace("'", "'\\''").replace("\n", "\\n")
            resp = self._execute_in_vm(vm_id, f"tmux send-keys -t {session} '{safe_cmd}' Enter", timeout=timeout)
            return resp.output

    async def execute_tmux_async(
        self,
        command: str = "",
        session: str = "main",
        timeout: int | None = None,
        is_input: bool = False,
        workspace_path: str | None = None,
        on_auto_background=None,
    ) -> str:
        return await asyncio.to_thread(
            self.execute_tmux, command=command, session=session,
            timeout=timeout, is_input=is_input, workspace_path=workspace_path,
        )

    def start_background(self, command: str, session: str = "main", workspace_path: str = "/workspace") -> None:
        vm_id = self._tenant_vm_id("default")
        self._execute_in_vm(vm_id, f"tmux send-keys -t {session} '{command.replace(chr(39), chr(39)+chr(92)+chr(39)+chr(39))}' Enter", timeout=30)
        self._jobs.register(session=session, command=command, initial_markers=0, workspace_path=workspace_path)

    def poll_completion(self, session: str = "main", workspace_path: str | None = None) -> BackgroundJob | None:
        return self._jobs.get(session=session)

    def kill_session(self, session: str = "main", workspace_path: str | None = None) -> None:
        vm_id = self._tenant_vm_id("default")
        self._execute_in_vm(vm_id, f"tmux kill-session -t {session} 2>/dev/null; true", timeout=10)
        self._jobs.remove(session=session)

    def read_session_log_diff(self, session: str = "main", workspace_path: str | None = None) -> str:
        key = f"{session}:{workspace_path or '/workspace'}"
        log_path = f"{workspace_path or '/workspace'}/.sessions/{session}.log"
        results = self.download_files([log_path])
        if not results or results[0].error or results[0].content is None:
            return ""
        full = results[0].content.decode("utf-8", errors="replace")
        prev_offset = self._log_offsets.get(key, 0)
        if prev_offset > len(full):
            prev_offset = 0
        new_bytes = full[prev_offset:]
        self._log_offsets[key] = len(full)
        return new_bytes

    def reset_session_log_offset(self, session: str = "main", workspace_path: str | None = None) -> None:
        key = f"{session}:{workspace_path or '/workspace'}"
        self._log_offsets.pop(key, None)

    def session_log_path(self, session: str = "main", workspace_path: str | None = None) -> str:
        return f"{workspace_path or '/workspace'}/.sessions/{session}.log"

    # ── Cube-specific operations ────────────────────────────────────────────

    def get_vm_status(self, tenant_id: str = "default") -> Optional[dict]:
        """Get the status of a tenant's active VM."""
        if tenant_id not in self._active_vms:
            return None
        vm = self._active_vms[tenant_id]
        try:
            resp = self._http().get(f"/api/{CUBE_API_VERSION}/vms/{vm.vm_id}")
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {"vm_id": vm.vm_id, "status": vm.status, "template": vm.template}

    def get_pool_stats(self) -> dict:
        """Get VM pool statistics."""
        return {
            "active_vms": len(self._active_vms),
            "pooled_vms": len(self._vm_pool),
            "max_pool_size": self._max_pool_size,
            "active": [
                {"vm_id": v.vm_id, "tenant": t, "age_seconds": v.age_seconds, "reuse_count": v._reuse_count}
                for t, v in self._active_vms.items()
            ],
            "pool": [
                {"vm_id": v.vm_id, "status": v.status, "age_seconds": v.age_seconds}
                for v in self._vm_pool
            ],
        }

    def health_check(self) -> dict:
        """Check cube-sandbox daemon health."""
        try:
            resp = self._http().get(f"/api/{CUBE_API_VERSION}/health", timeout=5.0)
            if resp.status_code == 200:
                return {"status": "healthy", "daemon": resp.json()}
            return {"status": "degraded", "http_code": resp.status_code}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    def destroy_all(self) -> dict:
        """Destroy all VMs (emergency cleanup)."""
        destroyed = 0
        for vm_id in list(self._active_vms.keys()):
            vm = self._active_vms[vm_id]
            try:
                self._destroy_vm(vm.vm_id)
                destroyed += 1
            except Exception:
                pass
        self._active_vms.clear()
        for vm in self._vm_pool:
            try:
                self._destroy_vm(vm.vm_id)
                destroyed += 1
            except Exception:
                pass
        self._vm_pool.clear()
        return {"destroyed": destroyed}
