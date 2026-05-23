# Decepticon — Quick Start (Docker)

Get Decepticon running in minutes with Docker Compose.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.22+)
- 8GB+ RAM available for Docker
- At least one LLM API key (Anthropic, OpenAI, etc.) or Ollama for local LLM

## Quick Start

```bash
# Clone the repository
git clone https://github.com/PurpleAILAB/Decepticon.git
cd Decepticon

# Start everything (builds images on first run)
./start.sh
```

That's it. The script will:
1. Check Docker is installed and running
2. Create a `.env` file with defaults
3. Build all Docker images
4. Start all services with health checks
5. Print the URLs

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

If you prefer running Docker Compose directly:

```bash
# Copy and edit environment
cp .env.example .env
# Edit .env to add your LLM API keys

# Build and start
docker compose -f docker-compose.quickstart.yml up --build -d

# Check status
docker compose -f docker-compose.quickstart.yml ps

# View logs
docker compose -f docker-compose.quickstart.yml logs -f

# Stop
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

**Services not starting?**
```bash
# Check logs for a specific service
docker compose -f docker-compose.quickstart.yml logs langgraph
docker compose -f docker-compose.quickstart.yml logs web
docker compose -f docker-compose.quickstart.yml logs litellm
```

**Port already in use?**
Edit `.env` and change the port (e.g., `WEB_PORT=3001`), then restart.

**Out of memory?**
Neo4j and the sandbox need ~4GB RAM combined. Increase Docker's memory limit in Docker Desktop settings.

**Need to reset everything?**
```bash
./start.sh --down
docker volume rm decepticon_postgres_data decepticon_neo4j_data
./start.sh
```

## Development

For development with hot-reload:
```bash
# Backend hot-reload
make dev

# Web frontend locally + backend in Docker
make web-dev

# CLI locally + backend in Docker
make cli-dev
```

## License

Apache 2.0 — see [LICENSE](LICENSE)
