"""
Deception & Cube Sandbox API Routes.

Provides REST endpoints for:
- Deception engagement lifecycle (create, start, stop, status)
- Agent management and monitoring
- Cube-sandbox VM pool management
- Integrated red team + deception reporting

Mounted at /api/v1/cybersecurity/deception/ and /api/v1/cybersecurity/cube/
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..services.deception_engine import (
    DeceptionEngine,
    DeceptionAgentType,
    EngagementPhase,
    get_deception_engine,
    reset_deception_engine,
)
from ..services.cube_sandbox_manager import (
    get_cube_manager,
    CubeSandboxManager,
)

logger = logging.getLogger(__name__)

deception_router = APIRouter(tags=["Deception — Multi-Agent Red Team"])
cube_router = APIRouter(tags=["Cube Sandbox — KVM MicroVM Management"])


def _tid() -> str:
    return "default-tenant"


# ═══════════════════════════════════════════════════════════════════════════
#  DECEPTION ENGAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@deception_router.post("/engagements", status_code=201, summary="Create deception engagement")
async def create_engagement(
    name: str,
    description: str = "",
    target_scope: list[str] = Query(default=[]),
    excluded_scope: list[str] = Query(default=[]),
    config: dict = Query(default={}),
    tenant_id: str = Depends(_tid),
):
    """Create a new multi-agent deception engagement."""
    engine = get_deception_engine()
    eng = engine.create_engagement(
        tenant_id=tenant_id,
        name=name,
        description=description,
        target_scope=target_scope,
        excluded_scope=excluded_scope,
        config=config,
    )
    return {
        "id": eng.id,
        "name": eng.name,
        "phase": eng.phase.value,
        "target_scope": eng.target_scope,
        "created_at": eng.created_at.isoformat(),
    }


@deception_router.get("/engagements", summary="List deception engagements")
async def list_engagements(tenant_id: str = Depends(_tid)):
    """List all deception engagements for the tenant."""
    engine = get_deception_engine()
    engagements = engine.list_engagements(tenant_id)
    return [
        {
            "id": e.id,
            "name": e.name,
            "phase": e.phase.value,
            "agents_count": len(e.agents),
            "findings_count": len(e.findings),
            "created_at": e.created_at.isoformat(),
        }
        for e in engagements
    ]


@deception_router.get("/engagements/{engagement_id}", summary="Get engagement details")
async def get_engagement(engagement_id: str, tenant_id: str = Depends(_tid)):
    """Get detailed status of a deception engagement."""
    engine = get_deception_engine()
    status_data = engine.get_engagement_status(engagement_id)
    if "error" in status_data:
        raise HTTPException(404, status_data["error"])
    return status_data


@deception_router.post("/engagements/{engagement_id}/start", summary="Start engagement")
async def start_engagement(engagement_id: str, tenant_id: str = Depends(_tid)):
    """Start an engagement — deploy all agents in parallel across cube-sandbox VMs."""
    engine = get_deception_engine()
    try:
        eng = await engine.start_engagement(engagement_id)
        return {
            "id": eng.id,
            "phase": eng.phase.value,
            "agents_deployed": len(eng.agents),
            "started_at": eng.started_at.isoformat() if eng.started_at else None,
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@deception_router.post("/engagements/{engagement_id}/stop", summary="Stop engagement")
async def stop_engagement(engagement_id: str, tenant_id: str = Depends(_tid)):
    """Stop an engagement — destroy all agent VMs."""
    engine = get_deception_engine()
    try:
        result = await engine.stop_engagement(engagement_id)
        return {"status": "stopped", **result}
    except ValueError as e:
        raise HTTPException(404, str(e))


@deception_router.post("/engagements/{engagement_id}/report", summary="Generate report")
async def generate_report(engagement_id: str, tenant_id: str = Depends(_tid)):
    """Generate a comprehensive engagement report."""
    engine = get_deception_engine()
    try:
        report = await engine.generate_report(engagement_id)
        if "error" in report:
            raise HTTPException(404, report["error"])
        return report
    except ValueError as e:
        raise HTTPException(404, str(e))


@deception_router.get("/agents", summary="List available deception agents")
async def list_agents():
    """List all available deception agent types and their playbooks."""
    from ..services.deception_engine import AGENT_PLAYBOOKS
    return {
        agent_type.value: {
            "name": playbook.get("name", ""),
            "description": playbook.get("description", ""),
            "phase": playbook.get("phase", "").value if playbook.get("phase") else None,
            "tools": playbook.get("tools", []),
            "cpu": playbook.get("cpu", 1),
            "memory_mb": playbook.get("memory_mb", 512),
        }
        for agent_type, playbook in AGENT_PLAYBOOKS.items()
    }


@deception_router.get("/health", summary="Deception engine health")
async def deception_health():
    """Check deception engine and cube-sandbox health."""
    engine = get_deception_engine()
    health = {
        "service": "deception-engine",
        "status": "healthy",
        "active_engagements": len([e for e in engine._engagements.values() if e.phase != EngagementPhase.COMPLETED]),
        "total_engagements": len(engine._engagements),
    }
    if engine.sandbox:
        health["sandbox_backend"] = engine.sandbox.id
        if hasattr(engine.sandbox, 'health_check'):
            health["sandbox_health"] = engine.sandbox.health_check()
    return health


# ═══════════════════════════════════════════════════════════════════════════
#  CUBE SANDBOX MANAGEMENT ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

@cube_router.get("/status", summary="Cube-sandbox daemon status")
async def cube_status():
    """Check cube-sandbox daemon health and get pool statistics."""
    manager = get_cube_manager()
    return {
        "daemon_health": manager.health_check(),
        "pool_stats": manager.get_pool_stats(),
        "config": {
            "base_url": manager.base_url,
            "template": manager.template,
            "default_cpu": manager.default_cpu,
            "default_memory_mb": manager.default_memory_mb,
            "max_pool_size": manager.max_pool_size,
        },
    }


@cube_router.get("/vms", summary="List all VMs")
async def cube_list_vms():
    """List all VMs managed by cube-sandbox."""
    manager = get_cube_manager()
    return manager.list_vms()


@cube_router.post("/vms", status_code=201, summary="Create a new VM")
async def cube_create_vm(
    template: str = "kali-rolling",
    cpu: int = 1,
    memory_mb: int = 512,
    labels: dict = Query(default={}),
):
    """Create a new MicroVM from a template snapshot."""
    manager = get_cube_manager()
    try:
        vm = manager.create_vm(template=template, cpu=cpu, memory_mb=memory_mb, labels=labels)
        return {"vm_id": vm.vm_id, "status": vm.status, "template": template}
    except Exception as e:
        raise HTTPException(500, f"Failed to create VM: {e}")


@cube_router.delete("/vms/{vm_id}", summary="Destroy a VM")
async def cube_destroy_vm(vm_id: str):
    """Destroy a MicroVM and free its resources."""
    manager = get_cube_manager()
    try:
        manager.destroy_vm(vm_id)
        return {"vm_id": vm_id, "status": "destroyed"}
    except Exception as e:
        raise HTTPException(500, f"Failed to destroy VM: {e}")


@cube_router.post("/vms/{vm_id}/pause", summary="Pause a VM")
async def cube_pause_vm(vm_id: str):
    """Pause (hibernate) a VM for later reuse."""
    manager = get_cube_manager()
    try:
        manager.pause_vm(vm_id)
        return {"vm_id": vm_id, "status": "paused"}
    except Exception as e:
        raise HTTPException(500, f"Failed to pause VM: {e}")


@cube_router.post("/vms/{vm_id}/resume", summary="Resume a VM")
async def cube_resume_vm(vm_id: str):
    """Resume a paused VM."""
    manager = get_cube_manager()
    try:
        vm = manager.resume_vm(vm_id)
        return {"vm_id": vm.vm_id, "status": vm.status}
    except Exception as e:
        raise HTTPException(500, f"Failed to resume VM: {e}")


@cube_router.post("/vms/{vm_id}/execute", summary="Execute command in VM")
async def cube_execute(
    vm_id: str,
    command: str,
    timeout: int = Query(default=120, ge=1, le=3600),
):
    """Execute a command inside a specific VM."""
    manager = get_cube_manager()
    try:
        result = manager.execute(vm_id, command, timeout=timeout)
        return result
    except Exception as e:
        raise HTTPException(500, f"Execution failed: {e}")


@cube_router.get("/pool", summary="VM pool statistics")
async def cube_pool_stats():
    """Get detailed VM pool statistics."""
    manager = get_cube_manager()
    return manager.get_pool_stats()


@cube_router.post("/cleanup", summary="Clean up all VMs")
async def cube_cleanup():
    """Emergency cleanup — destroy all VMs."""
    manager = get_cube_manager()
    result = manager.cleanup_all()
    return {"status": "cleaned", **result}


@cube_router.get("/templates", summary="List available VM templates")
async def cube_templates():
    """List available VM templates for cube-sandbox."""
    manager = get_cube_manager()
    return {"templates": manager.list_templates()}
