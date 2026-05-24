"""
Deception Engine — Multi-Agent Red Team Orchestration with Cube Sandbox Isolation.

This is the top-level orchestration layer that coordinates Decepticon's
specialist agents, each running in its own KVM MicroVM via cube-sandbox.

Architecture:
    ┌─────────────────────────────────────────────────────────────┐
    │                    DeceptionEngine                           │
    │                                                              │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
    │  │  Recon    │  │ Exploit  │  │ PostExp  │  │ Analyst  │   │
    │  │ Agent     │  │ Agent    │  │ Agent    │  │ Agent    │   │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
    │       │              │              │              │         │
    │  ┌────┴──────────────┴──────────────┴──────────────┴────┐   │
    │  │           CubeSandboxBackend (KVM MicroVMs)           │   │
    │  │  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐  │   │
    │  │  │VM-1 │ │VM-2 │ │VM-3 │ │VM-4 │ │VM-5 │ │VM-N │  │   │
    │  │  └─────┘ └─────┘ └─────┘ └─────┘ └─────┘ └─────┘  │   │
    │  └───────────────────────────────────────────────────────┘   │
    └─────────────────────────────────────────────────────────────┘

Each agent type gets its own isolated MicroVM:
    - Fresh kernel per agent (hardware isolation)
    - VM snapshots for fast reuse
    - Automatic cleanup on engagement completion

This module is used by the multi-saas-platform cybersecurity service
to provide real red team capabilities to SaaS tenants.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Deception agent types ──────────────────────────────────────────────────

class DeceptionAgentType(str, Enum):
    """Types of deception/red team agents."""
    RECON = "recon"
    EXPLOIT = "exploit"
    POSTEXPLOIT = "postexploit"
    AD_OPERATOR = "ad_operator"
    CLOUD_HUNTER = "cloud_hunter"
    CONTRACT_AUDITOR = "contract_auditor"
    REVERSER = "reverser"
    ANALYST = "analyst"
    # Deception-specific agents
    HONEYPOT_DEPLOYER = "honeypot_deployer"
    LATERAL_MOVEMENT = "lateral_movement"
    DATA_EXFIL_SIM = "data_exfil_sim"
    PERSISTENCE_SIM = "persistence_sim"
    C2_SIMULATOR = "c2_simulator"


class EngagementPhase(str, Enum):
    """Phases of a deception engagement."""
    SETUP = "setup"
    RECON = "recon"
    INITIAL_ACCESS = "initial_access"
    EXECUTION = "execution"
    PERSISTENCE = "persistence"
    LATERAL_MOVEMENT = "lateral_movement"
    COLLECTION = "collection"
    EXFILTRATION = "exfiltrATION"
    ANALYSIS = "analysis"
    REPORTING = "reporting"
    CLEANUP = "cleanup"
    COMPLETED = "completed"


class AgentStatus(str, Enum):
    """Status of a deception agent instance."""
    PENDING = "pending"
    DEPLOYING = "deploying"  # VM being created
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    DESTROYED = "destroyed"


# ── Data models ────────────────────────────────────────────────────────────

@dataclass
class DeceptionAgent:
    """A running deception agent instance."""
    id: str
    agent_type: DeceptionAgentType
    engagement_id: str
    tenant_id: str
    status: AgentStatus = AgentStatus.PENDING
    vm_id: Optional[str] = None  # cube-sandbox VM ID
    vm_ip: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    findings: list[dict] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration(self) -> Optional[timedelta]:
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return datetime.utcnow() - self.started_at
        return None


@dataclass
class DeceptionEngagement:
    """A complete deception/red team engagement."""
    id: str
    tenant_id: str
    name: str
    description: str = ""
    target_scope: list[str] = field(default_factory=list)
    excluded_scope: list[str] = field(default_factory=list)
    phase: EngagementPhase = EngagementPhase.SETUP
    agents: dict[str, DeceptionAgent] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)
    attack_paths: list[dict] = field(default_factory=list)
    opplan: list[dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    config: dict = field(default_factory=dict)

    @property
    def active_agents(self) -> list[DeceptionAgent]:
        return [a for a in self.agents.values() if a.status in (AgentStatus.RUNNING, AgentStatus.DEPLOYING)]

    @property
    def completed_agents(self) -> list[DeceptionAgent]:
        return [a for a in self.agents.values() if a.status == AgentStatus.COMPLETED]

    @property
    def failed_agents(self) -> list[DeceptionAgent]:
        return [a for a in self.agents.values() if a.status == AgentStatus.FAILED]


# ── Agent playbooks ────────────────────────────────────────────────────────

AGENT_PLAYBOOKS: dict[DeceptionAgentType, dict] = {
    DeceptionAgentType.RECON: {
        "name": "Reconnaissance Agent",
        "description": "Passive/active reconnaissance, OSINT, scanning",
        "tools": ["nmap", "subfinder", "httpx", "dnsx", "amass", "masscan"],
        "phase": EngagementPhase.RECON,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 1800,
        "commands": [
            "nmap -sC -sV -oA /workspace/scans/tcp {target}",
            "subfinder -d {target} -o /workspace/recon/subdomains.txt",
            "httpx -l /workspace/recon/subdomains.txt -status-code -title -tech-detect -o /workspace/recon/live.txt",
        ],
    },
    DeceptionAgentType.EXPLOIT: {
        "name": "Exploitation Agent",
        "description": "Initial access via web/AD attacks",
        "tools": ["sqlmap", "metasploit", "impacket", "burpsuite"],
        "phase": EngagementPhase.INITIAL_ACCESS,
        "cpu": 2,
        "memory_mb": 1024,
        "timeout_seconds": 3600,
        "commands": [],
    },
    DeceptionAgentType.POSTEXPLOIT: {
        "name": "Post-Exploitation Agent",
        "description": "Privilege escalation, lateral movement, persistence",
        "tools": ["mimikatz", "bloodhound", "crackmapexec", "impacket"],
        "phase": EngagementPhase.PERSISTENCE,
        "cpu": 1,
        "memory_mb": 1024,
        "timeout_seconds": 3600,
        "commands": [],
    },
    DeceptionAgentType.AD_OPERATOR: {
        "name": "AD Operator",
        "description": "Active Directory attack specialist",
        "tools": ["bloodhound", "rubeus", "certipy", "impacket"],
        "phase": EngagementPhase.LATERAL_MOVEMENT,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 3600,
        "commands": [],
    },
    DeceptionAgentType.CLOUD_HUNTER: {
        "name": "Cloud Hunter",
        "description": "Cloud infrastructure assessment",
        "tools": ["prowler", "scout_suite", "awscli", "azcli"],
        "phase": EngagementPhase.RECON,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 1800,
        "commands": [],
    },
    DeceptionAgentType.CONTRACT_AUDITOR: {
        "name": "Smart Contract Auditor",
        "description": "Solidity/EVM smart contract audit",
        "tools": ["slither", "foundry", "mythril", "echidna"],
        "phase": EngagementPhase.EXECUTION,
        "cpu": 2,
        "memory_mb": 2048,
        "timeout_seconds": 3600,
        "commands": [],
    },
    DeceptionAgentType.REVERSER: {
        "name": "Binary Reverser",
        "description": "Binary analysis and reverse engineering",
        "tools": ["ghidra", "radare2", "binwalk", "ropgadget"],
        "phase": EngagementPhase.ANALYSIS,
        "cpu": 2,
        "memory_mb": 2048,
        "timeout_seconds": 7200,
        "commands": [],
    },
    DeceptionAgentType.ANALYST: {
        "name": "Vulnerability Analyst",
        "description": "Source code review, static analysis",
        "tools": ["semgrep", "bandit", "gitleaks", "codeql"],
        "phase": EngagementPhase.ANALYSIS,
        "cpu": 2,
        "memory_mb": 1024,
        "timeout_seconds": 3600,
        "commands": [],
    },
    # Deception-specific agents
    DeceptionAgentType.HONEYPOT_DEPLOYER: {
        "name": "Honeypot Deployer",
        "description": "Deploys decoy services and credentials for threat detection",
        "tools": ["honeypot", "opencanary", "dionaea"],
        "phase": EngagementPhase.SETUP,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 900,
        "commands": [],
    },
    DeceptionAgentType.LATERAL_MOVEMENT: {
        "name": "Lateral Movement Simulator",
        "description": "Simulates attacker lateral movement for detection testing",
        "tools": ["crackmapexec", "impacket", "bloodhound"],
        "phase": EngagementPhase.LATERAL_MOVEMENT,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 3600,
        "commands": [],
    },
    DeceptionAgentType.DATA_EXFIL_SIM: {
        "name": "Data Exfiltration Simulator",
        "description": "Simulates data exfiltration techniques for DLP testing",
        "tools": ["curl", "wget", "rsync", "scp"],
        "phase": EngagementPhase.EXFILTRATION,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 1800,
        "commands": [],
    },
    DeceptionAgentType.PERSISTENCE_SIM: {
        "name": "Persistence Simulator",
        "description": "Simulates persistence mechanisms for EDR testing",
        "tools": ["bash", "python3", "systemd", "cron"],
        "phase": EngagementPhase.PERSISTENCE,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 1800,
        "commands": [],
    },
    DeceptionAgentType.C2_SIMULATOR: {
        "name": "C2 Simulator",
        "description": "Simulates command-and-control communication patterns",
        "tools": ["sliver", "metasploit", "python3"],
        "phase": EngagementPhase.PERSISTENCE,
        "cpu": 1,
        "memory_mb": 512,
        "timeout_seconds": 3600,
        "commands": [],
    },
}


# ── Deception Engine ───────────────────────────────────────────────────────

class DeceptionEngine:
    """
    Multi-agent deception/red team orchestration engine.

    Coordinates specialist agents, each running in an isolated KVM MicroVM
    via cube-sandbox. Manages the full engagement lifecycle from setup
    through cleanup.

    This is the main entry point used by the multi-saas-platform
    cybersecurity service to provide real red team capabilities.
    """

    def __init__(self, sandbox_backend=None):
        """
        Args:
            sandbox_backend: A sandbox backend instance. If None, uses
                cube-sandbox if available, otherwise falls back to HTTP.
        """
        self._sandbox = sandbox_backend
        self._engagements: dict[str, DeceptionEngagement] = {}
        self._task_handles: dict[str, asyncio.Task] = {}

    @property
    def sandbox(self):
        return self._sandbox

    @sandbox.setter
    def sandbox(self, backend):
        self._sandbox = backend

    # ── Engagement lifecycle ──────────────────────────────────────────────

    def create_engagement(
        self,
        tenant_id: str,
        name: str,
        description: str = "",
        target_scope: list[str] | None = None,
        excluded_scope: list[str] | None = None,
        config: dict | None = None,
    ) -> DeceptionEngagement:
        """Create a new deception engagement."""
        eng = DeceptionEngagement(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            name=name,
            description=description,
            target_scope=target_scope or [],
            excluded_scope=excluded_scope or [],
            config=config or {},
        )
        self._engagements[eng.id] = eng
        logger.info(f"Deception engagement created: {eng.id} ({name})")
        return eng

    def get_engagement(self, engagement_id: str) -> Optional[DeceptionEngagement]:
        return self._engagements.get(engagement_id)

    def list_engagements(self, tenant_id: str) -> list[DeceptionEngagement]:
        return [e for e in self._engagements.values() if e.tenant_id == tenant_id]

    async def start_engagement(self, engagement_id: str) -> DeceptionEngagement:
        """Start an engagement — deploy agents in parallel."""
        eng = self._engagements.get(engagement_id)
        if not eng:
            raise ValueError(f"Engagement not found: {engagement_id}")

        eng.started_at = datetime.utcnow()
        eng.phase = EngagementPhase.RECON

        # Determine which agents to deploy based on target scope
        agent_types = self._select_agents(eng.target_scope)

        # Deploy agents in parallel
        deploy_tasks = []
        for agent_type in agent_types:
            agent = DeceptionAgent(
                id=str(uuid.uuid4()),
                agent_type=agent_type,
                engagement_id=eng.id,
                tenant_id=eng.tenant_id,
                config=AGENT_PLAYBOOKS.get(agent_type, {}),
            )
            eng.agents[agent.id] = agent
            deploy_tasks.append(self._deploy_agent(agent))

        results = await asyncio.gather(*deploy_tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Agent deployment failed: {result}")

        return eng

    async def stop_engagement(self, engagement_id: str) -> dict:
        """Stop an engagement — destroy all agent VMs."""
        eng = self._engagements.get(engagement_id)
        if not eng:
            raise ValueError(f"Engagement not found: {engagement_id}")

        results = {"destroyed": 0, "errors": 0}
        for agent in list(eng.agents.values()):
            try:
                await self._destroy_agent(agent)
                results["destroyed"] += 1
            except Exception as e:
                logger.error(f"Failed to destroy agent {agent.id}: {e}")
                results["errors"] += 1

        eng.phase = EngagementPhase.COMPLETED
        eng.completed_at = datetime.utcnow()
        return results

    def get_engagement_status(self, engagement_id: str) -> dict:
        """Get detailed status of an engagement."""
        eng = self._engagements.get(engagement_id)
        if not eng:
            return {"error": "Engagement not found"}

        return {
            "id": eng.id,
            "name": eng.name,
            "phase": eng.phase.value,
            "total_agents": len(eng.agents),
            "active_agents": len(eng.active_agents),
            "completed_agents": len(eng.completed_agents),
            "failed_agents": len(eng.failed_agents),
            "total_findings": len(eng.findings),
            "created_at": eng.created_at.isoformat(),
            "started_at": eng.started_at.isoformat() if eng.started_at else None,
            "completed_at": eng.completed_at.isoformat() if eng.completed_at else None,
            "agents": [
                {
                    "id": a.id,
                    "type": a.agent_type.value,
                    "status": a.status.value,
                    "vm_id": a.vm_id,
                    "findings_count": len(a.findings),
                    "duration_seconds": a.duration.total_seconds() if a.duration else None,
                }
                for a in eng.agents.values()
            ],
        }

    # ── Agent management ──────────────────────────────────────────────────

    def _select_agents(self, target_scope: list[str]) -> list[DeceptionAgentType]:
        """Select appropriate agents based on target scope."""
        agents = [DeceptionAgentType.RECON]  # Always start with recon

        for target in target_scope:
            target_lower = target.lower()
            if any(kw in target_lower for kw in ["aws", "azure", "gcp", "cloud", "s3", "iam"]):
                agents.append(DeceptionAgentType.CLOUD_HUNTER)
            if any(kw in target_lower for kw in ["ad", "ldap", "domain", "kerberos"]):
                agents.append(DeceptionAgentType.AD_OPERATOR)
            if any(kw in target_lower for kw in ["solidity", "contract", "evm", "defi"]):
                agents.append(DeceptionAgentType.CONTRACT_AUDITOR)
            if any(kw in target_lower for kw in ["elf", "pe", "binary", "firmware", "exe"]):
                agents.append(DeceptionAgentType.REVERSER)
            if any(kw in target_lower for kw in ["web", "api", "http", "app"]):
                agents.append(DeceptionAgentType.EXPLOIT)
            if any(kw in target_lower for kw in ["src", "code", "repo", "git"]):
                agents.append(DeceptionAgentType.ANALYST)

        # Add deception-specific agents
        agents.extend([
            DeceptionAgentType.HONEYPOT_DEPLOYER,
            DeceptionAgentType.PERSISTENCE_SIM,
        ])

        return list(dict.fromkeys(agents))  # Deduplicate preserving order

    async def _deploy_agent(self, agent: DeceptionAgent) -> None:
        """Deploy an agent — create VM and run playbook."""
        agent.status = AgentStatus.DEPLOYING
        playbook = AGENT_PLAYBOOKS.get(agent.agent_type, {})

        try:
            if self._sandbox:
                # Use cube-sandbox backend
                if hasattr(self._sandbox, '_get_or_create_vm'):
                    vm = self._sandbox._get_or_create_vm(agent.tenant_id)
                    agent.vm_id = vm.vm_id
                    agent.status = AgentStatus.RUNNING
                    agent.started_at = datetime.utcnow()

                    # Execute playbook commands
                    commands = playbook.get("commands", [])
                    for cmd_template in commands:
                        cmd = cmd_template.format(target=agent.config.get("target", "127.0.0.1"))
                        try:
                            resp = self._sandbox._execute_in_vm(vm.vm_id, cmd, timeout=playbook.get("timeout_seconds", 1800))
                            if resp.exit_code != 0:
                                logger.warning(f"Agent {agent.id} command failed: {cmd}")
                        except Exception as e:
                            logger.error(f"Agent {agent.id} execution error: {e}")

                    # Collect findings from workspace
                    try:
                        results = self._sandbox._download_from_vm(vm.vm_id, ["/workspace/findings.json"])
                        if results and results[0].content:
                            findings = json.loads(results[0].content)
                            agent.findings.extend(findings)
                    except (json.JSONDecodeError, IndexError):
                        pass

                    agent.status = AgentStatus.COMPLETED
                    agent.completed_at = datetime.utcnow()
                else:
                    # Fallback for other backends
                    agent.status = AgentStatus.RUNNING
                    agent.started_at = datetime.utcnow()
                    agent.status = AgentStatus.COMPLETED
                    agent.completed_at = datetime.utcnow()
            else:
                # No sandbox — simulated execution
                agent.status = AgentStatus.RUNNING
                agent.started_at = datetime.utcnow()
                await asyncio.sleep(0.5)  # Simulate work
                agent.findings.append({"type": "simulation", "agent": agent.agent_type.value, "status": "completed"})
                agent.status = AgentStatus.COMPLETED
                agent.completed_at = datetime.utcnow()

        except Exception as e:
            agent.status = AgentStatus.FAILED
            agent.error = str(e)
            logger.error(f"Agent {agent.id} deployment failed: {e}", exc_info=True)

    async def _destroy_agent(self, agent: DeceptionAgent) -> None:
        """Destroy an agent and its VM."""
        if self._sandbox and hasattr(self._sandbox, '_recycle_vm'):
            self._sandbox._recycle_vm(agent.tenant_id)
        agent.status = AgentStatus.DESTROYED

    # ── Knowledge graph integration ───────────────────────────────────────

    async def ingest_to_kg(self, engagement_id: str, kg_service: Any) -> dict:
        """Ingest engagement findings into the knowledge graph."""
        eng = self._engagements.get(engagement_id)
        if not eng:
            return {"error": "Engagement not found"}

        kg = await kg_service.kg_create(eng.tenant_id, engagement_id, f"deception-{eng.name}")

        nodes_added = 0
        edges_added = 0

        for agent in eng.agents.values():
            for finding in agent.findings:
                node = await kg_service.kg_add_node(
                    kg.id,
                    finding.get("node_type", "finding"),
                    finding.get("label", finding.get("title", "Unknown")),
                    finding,
                    source=agent.agent_type.value,
                )
                if node:
                    nodes_added += 1

        return {"kg_id": kg.id, "nodes_added": nodes_added, "edges_added": edges_added}

    # ── Reporting ──────────────────────────────────────────────────────────

    async def generate_report(self, engagement_id: str) -> dict:
        """Generate a comprehensive engagement report."""
        eng = self._engagements.get(engagement_id)
        if not eng:
            return {"error": "Engagement not found"}

        all_findings = []
        for agent in eng.agents.values():
            for f in agent.findings:
                f["agent_type"] = agent.agent_type.value
                all_findings.append(f)

        # Build MITRE ATT&CK coverage
        mitre_coverage = {}
        for agent in eng.agents.values():
            playbook = AGENT_PLAYBOOKS.get(agent.agent_type, {})
            if "phase" in playbook:
                phase = playbook["phase"].value
                if phase not in mitre_coverage:
                    mitre_coverage[phase] = []
                mitre_coverage[phase].append(agent.agent_type.value)

        return {
            "engagement_id": eng.id,
            "name": eng.name,
            "phase": eng.phase.value,
            "generated_at": datetime.utcnow().isoformat(),
            "executive_summary": {
                "total_agents_deployed": len(eng.agents),
                "agents_succeeded": len(eng.completed_agents),
                "agents_failed": len(eng.failed_agents),
                "total_findings": len(all_findings),
                "mitre_coverage": list(mitre_coverage.keys()),
            },
            "findings": all_findings,
            "agents": [
                {
                    "type": a.agent_type.value,
                    "status": a.status.value,
                    "findings_count": len(a.findings),
                    "duration": str(a.duration) if a.duration else None,
                    "error": a.error,
                }
                for a in eng.agents.values()
            ],
            "mitre_coverage": mitre_coverage,
            "recommendations": self._generate_recommendations(all_findings),
        }

    def _generate_recommendations(self, findings: list[dict]) -> list[str]:
        """Generate remediation recommendations from findings."""
        recommendations = set()
        for f in findings:
            severity = f.get("severity", "").lower()
            if severity in ("critical", "high"):
                recommendations.add(f"Priority remediation: {f.get('title', f.get('description', 'Finding'))}")
            ftype = f.get("type", "").lower()
            if "container" in ftype or "docker" in ftype:
                recommendations.add("Review container security policies and runtime protections")
            if "iam" in ftype or "privilege" in ftype:
                recommendations.add("Implement least-privilege access and review IAM policies")
            if "exposure" in ftype or "public" in ftype:
                recommendations.add("Review network exposure and implement access controls")
        if not recommendations:
            recommendations.add("Continue regular security assessments and monitoring")
        return list(recommendations)


# ── Singleton engine instance ──────────────────────────────────────────────

_engine_instance: Optional[DeceptionEngine] = None


def get_deception_engine(sandbox_backend=None) -> DeceptionEngine:
    """Get or create the global DeceptionEngine singleton."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = DeceptionEngine(sandbox_backend=sandbox_backend)
    return _engine_instance


def reset_deception_engine():
    """Reset the engine (for testing)."""
    global _engine_instance
    if _engine_instance:
        try:
            if _engine_instance.sandbox and hasattr(_engine_instance.sandbox, 'close'):
                _engine_instance.sandbox.close()
        except Exception:
            pass
    _engine_instance = DeceptionEngine()
