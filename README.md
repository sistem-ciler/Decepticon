# Decepticon — Quick Start (Docker)

Get Decepticon running in minutes with Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (20.10+) with Compose v2
- 8GB+ RAM available for Docker
- At least one LLM API key (Anthropic, OpenAI, etc.) or Ollama for local LLM

## Quick Start — Fresh VPS (Ubuntu/Debian)

One-command install on a fresh VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/sistem-ciler/Decepticon/main/scripts/vps-setup.sh | bash
```

This installs Docker, configures the firewall, clones the repo, builds images, and starts all services.

## Quick Start — Manual

```bash
git clone https://github.com/sistem-ciler/Decepticon.git
cd Decepticon
./start.sh
```

## Access

| Service | URL | Description |
|---------|-----|-------------|
| **Web Dashboard** | http://localhost:3000 | Main UI for managing engagements |
| **LangGraph API** | http://localhost:2024 | Agent API server |
| **LiteLLM Proxy** | http://localhost:4000 | LLM gateway |
| **Neo4j Browser** | http://localhost:7474 | Attack chain graph DB |

Default Neo4j credentials: `neo4j` / `decepticon-graph`

## Commands

```bash
./start.sh            # Build and start
./start.sh --no-build # Start without rebuilding
./start.sh --status   # Show service status
./start.sh --logs     # Follow logs
./start.sh --down     # Stop everything
./start.sh --help     # Show all options
```

## Manual Docker Compose

```bash
cp .env.example .env
# Edit .env to add your LLM API keys

docker compose -f docker-compose.quickstart.yml up --build -d
docker compose -f docker-compose.quickstart.yml ps
docker compose -f docker-compose.quickstart.yml logs -f
docker compose -f docker-compose.quickstart.yml down
```

## Configuration

Edit `.env` to configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `OPENAI_API_KEY` | — | OpenAI API key |
| `WEB_PORT` | 3000 | Web dashboard port |
| `LANGGRAPH_PORT` | 2024 | LangGraph API port |
| `LITELLM_PORT` | 4000 | LiteLLM proxy port |
| `DECEPTICON_MODEL_PROFILE` | eco | Model tier: eco/max/test |
| `OLLAMA_API_BASE` | — | Ollama URL for local LLM |

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Web UI     │────▶│  LangGraph   │────▶│  LiteLLM    │
│  (Next.js)  │     │  (Agents)    │     │  (LLM GW)   │
│  :3000      │     │  :2024       │     │  :4000      │
└─────────────┘     └──────┬───────┘     └─────────────┘
                           │
                    ┌──────┴───────┐
                    │   Sandbox    │
                    │   (Kali)     │
                    │   :9999      │
                    └──────┬───────┘
                           │
       ┌───────────────────┼───────────────────┐
       │                   │                   │
┌──────┴──────┐    ┌──────┴──────┐    ┌───────┴──────┐
│  PostgreSQL │    │   Neo4j     │    │  C2 Sliver   │
│  :5432      │    │   :7474     │    │              │
└─────────────┘    └─────────────┘    └──────────────┘
```

## Troubleshooting

**Docker daemon not running?**
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

**Services not starting?**
```bash
docker compose -f docker-compose.quickstart.yml logs langgraph
docker compose -f docker-compose.quickstart.yml logs web
docker compose -f docker-compose.quickstart.yml logs litellm
```

**Port already in use?**
Edit `.env` and change the port (e.g., `WEB_PORT=3001`), then restart.

**Out of memory?**
Neo4j and the sandbox need ~4GB RAM combined. Increase Docker's memory limit.

**Reset everything?**
```bash
./start.sh --down
docker volume rm decepticon_postgres_data decepticon_neo4j_data decepticon_workspace
./start.sh
```

## Development

For development with hot-reload:
```bash
make dev          # Backend hot-reload
make web-dev      # Web locally + backend in Docker
make cli-dev      # CLI locally + backend in Docker
```

## License

Apache 2.0 — see [LICENSE](LICENSE)
