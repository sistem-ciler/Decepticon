# Decepticon + BitNet — Integrated Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Hetzner VPS (Bare Metal)                         │
│                    188.245.210.10 (8+ vCPU, 32GB RAM)                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Docker Compose Stack                         │   │
│  │                                                                  │   │
│  │  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐      │   │
│  │  │   Web UI     │    │  LangGraph   │    │   LiteLLM    │      │   │
│  │  │   (Next.js)  │───▶│  (Agents)    │───▶│   Gateway    │      │   │
│  │  │   :3000      │    │   :2024      │    │   :4000      │      │   │
│  │  └──────────────┘    └──────┬───────┘    └──────┬───────┘      │   │
│  │         │                   │                    │               │   │
│  │         │            ┌──────┴───────┐     ┌──────┴───────┐      │   │
│  │         │            │   Sandbox    │     │    BitNet    │      │   │
│  │         │            │   (Kali)     │     │  (1-bit LLM) │      │   │
│  │         │            │   :9999      │     │   :8080      │      │   │
│  │         │            └──────────────┘     └──────────────┘      │   │
│  │         │                                                        │   │
│  │  ┌──────┴───────┐    ┌──────────────┐    ┌──────────────┐      │   │
│  │  │  PostgreSQL  │    │    Neo4j     │    │  Cloud APIs  │      │   │
│  │  │   :5432      │    │   :7474      │    │  (fallback)  │      │   │
│  │  └──────────────┘    └──────────────┘    └──────────────┘      │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     Data Persistence                             │   │
│  │  • postgres_data:    LiteLLM config + web dashboard DB          │   │
│  │  • neo4j_data:       Attack chain graph database                │   │
│  │  • bitnet_models:    Quantized 1-bit LLM models (~1.5GB each)  │   │
│  │  • sandbox_workspace: Engagement files + findings               │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## Service Details

### BitNet (:8024) — Local 1-bit LLM Inference
- **What:** Microsoft's BitNet b1.58 inference server
- **Model:** BitNet-b1.58-2B-4T (2.4B params, ~1.5GB RAM)
- **API:** OpenAI-compatible (`/v1/completions`, `/v1/chat/completions`)
- **Use:** Zero-cost local inference for high-volume agent tasks
- **Fallback:** Cloud APIs (Anthropic, OpenAI) for complex reasoning

### LiteLLM (:4000) — LLM Gateway
- **What:** Unified LLM API gateway
- **Routes to:** BitNet (local) → Cloud APIs (fallback)
- **Features:** Load balancing, rate limiting, cost tracking
- **Model priority:**
  1. `bitnet/bitnet-2b` — Free, fast, good for most tasks
  2. `bitnet/bitnet-3b` — Free, better quality
  3. `anthropic/claude-sonnet-4` — Paid, best reasoning
  4. `openai/gpt-4o` — Paid, fallback

### LangGraph (:2024) — Agent Orchestration
- **What:** Decepticon's red team agent framework
- **Agents:** recon, exploit, postexploit, analyst, reverser, etc.
- **Tools:** nmap, sqlmap, metasploit (via sandbox)
- **Memory:** Neo4j attack chain graph

### Sandbox (:9999) — Red Team Tools
- **What:** Kali Linux container with security tools
- **Tools:** nmap, sqlmap, nikto, hydra, metasploit, etc.
- **Isolation:** Docker container (shared kernel)
- **Future:** Replace with Cube Sandbox (KVM MicroVM) for hardware isolation

### Web Dashboard (:3000) — Management UI
- **What:** Next.js web interface
- **Features:** Engagement management, agent monitoring, findings review
- **Terminal:** WebSocket-based terminal (:3003)

## Data Flow

```
Operator → Web UI → LangGraph → LiteLLM → BitNet (local)
                                    ↓
                              Cloud APIs (fallback)
                                    ↓
                              LangGraph → Sandbox → Security Tools
                                    ↓
                              Neo4j (attack chain graph)
```

## Resource Allocation (32GB RAM VPS)

| Service | RAM | CPU | Disk |
|---------|-----|-----|------|
| BitNet 2B | 2GB | 2 cores | 2GB |
| LiteLLM | 512MB | 0.5 cores | 100MB |
| LangGraph | 1GB | 1 core | 500MB |
| Sandbox | 2GB | 2 cores | 5GB |
| Web | 512MB | 0.5 cores | 500MB |
| PostgreSQL | 512MB | 0.5 cores | 1GB |
| Neo4j | 1GB | 1 core | 2GB |
| **Total** | **~8GB** | **8 cores** | **~12GB** |
| **Remaining** | **24GB** | — | — |

## BitNet Model Selection

| Model | Size | RAM | Speed | Quality | Best For |
|-------|------|-----|-------|---------|----------|
| falcon-e-1b | 1B | 0.8GB | 50+ tok/s | Basic | Edge, CCTV alerts |
| bitnet-2b | 2.4B | 1.5GB | 30-50 tok/s | Good | General agent tasks |
| falcon-e-3b | 3B | 1.5GB | 25-40 tok/s | Good | Multilingual |
| bitnet-3b | 3.3B | 2.5GB | 20-35 tok/s | Better | Complex analysis |
| llama3-8b-bitnet | 8B | 5GB | 10-20 tok/s | Best | Reasoning, reports |

## Cost Comparison

| Approach | Cost/1M tokens | Privacy | Latency |
|----------|---------------|---------|---------|
| Cloud APIs (current) | $2-4 | Data leaves | 200-500ms |
| BitNet local | $0 | Full privacy | 50-100ms |
| BitNet + Cloud fallback | $0.50-1 | Selective | 50-500ms |

## Deployment

```bash
# One-command deployment
curl -fsSL https://raw.githubusercontent.com/sistem-ciler/Decepticon/main/scripts/deploy-full.sh | bash

# Or manual:
git clone https://github.com/sistem-ciler/Decepticon.git
cd Decepticon
docker compose -f docker-compose.integrated.yml up --build -d
```

## Future: Cube Sandbox Integration

For production red team operations, replace the Docker sandbox with Cube Sandbox:

```
Current:  Agent → Docker container (shared kernel) → tools
Future:   Agent → Cube Sandbox MicroVM (dedicated KVM kernel) → tools
          + BitNet 2B model inside each MicroVM
          = 1000+ concurrent isolated agents per server
```

Requirements for Cube Sandbox:
- Bare-metal server or PVM kernel on cloud VM
- KVM support (/dev/kvm)
- XFS filesystem for /data/cubelet
