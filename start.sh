#!/usr/bin/env bash
# =============================================================================
# Decepticon — Quick Start Script
# =============================================================================
# Usage:
#   ./start.sh            # Build and start all services
#   ./start.sh --no-build # Start without rebuilding images
#   ./start.sh --down     # Stop all services
#   ./start.sh --status   # Show service status
#   ./start.sh --logs     # Follow logs
#   ./start.sh --help     # Show help
# =============================================================================

set -euo pipefail

COMPOSE_FILE="docker-compose.quickstart.yml"
COMPOSE="docker compose -f ${COMPOSE_FILE}"
PROJECT_NAME="decepticon"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $*"; }

# ── Parse args ──────────────────────────────────────────────────────────
ACTION="up"
NO_BUILD=false
EXTRA_ARGS=()

for arg in "$@"; do
  case "$arg" in
    --no-build) NO_BUILD=true ;;
    --down)     ACTION="down" ;;
    --status)   ACTION="status" ;;
    --logs)     ACTION="logs" ;;
    --help|-h)
      echo "Decepticon Quick Start"
      echo ""
      echo "Usage: ./start.sh [OPTIONS]"
      echo ""
      echo "Options:"
      echo "  --no-build   Start without rebuilding Docker images"
      echo "  --down       Stop all services and remove containers"
      echo "  --status     Show running service status"
      echo "  --logs       Follow container logs"
      echo "  --help       Show this help"
      echo ""
      echo "Environment variables:"
      echo "  WEB_PORT       Web dashboard port (default: 3000)"
      echo "  LANGGRAPH_PORT LangGraph API port (default: 2024)"
      echo "  LITELLM_PORT   LiteLLM proxy port (default: 4000)"
      echo ""
      echo "After startup:"
      echo "  Web Dashboard:    http://localhost:\${WEB_PORT:-3000}"
      echo "  LangGraph API:    http://localhost:\${LANGGRAPH_PORT:-2024}"
      echo "  LiteLLM Proxy:    http://localhost:\${LITELLM_PORT:-4000}"
      echo "  Neo4j Browser:    http://localhost:7474"
      exit 0
      ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

# ── Check prerequisites ─────────────────────────────────────────────────
check_prerequisites() {
  log_step "Checking prerequisites..."

  if ! command -v docker &>/dev/null; then
    log_error "Docker is not installed. Install Docker first:"
    log_error "  https://docs.docker.com/get-docker/"
    exit 1
  fi

  if ! docker compose version &>/dev/null; then
    log_error "Docker Compose v2 is required. Upgrade Docker:"
    log_error "  https://docs.docker.com/compose/install/"
    exit 1
  fi

  if ! docker info &>/dev/null; then
    log_error "Docker daemon is not running. Start Docker first."
    exit 1
  fi

  log_info "Docker OK: $(docker version --format '{{.Server.Version}}')"
}

# ── Ensure .env exists ──────────────────────────────────────────────────
ensure_env() {
  if [ ! -f .env ]; then
    log_step "Creating .env from template..."
    cat > .env << 'ENVEOF'
# Decepticon Environment
# Configure at least one LLM API key below, or use Ollama for local LLM.

ANTHROPIC_API_KEY=your-anthropic-key-here
OPENAI_API_KEY=your-openai-key-here
GEMINI_API_KEY=
DEEPSEEK_API_KEY=
OPENROUTER_API_KEY=

# LiteLLM
LITELLM_MASTER_KEY=sk-decepticon-master
LITELLM_SALT_KEY=sk-decepticon-salt

# PostgreSQL
POSTGRES_PASSWORD=decepticon

# Neo4j
NEO4J_PASSWORD=decepticon-graph

# Model Profile: eco | max | test
DECEPTICON_MODEL_PROFILE=eco

# Ports
WEB_PORT=3000
LANGGRAPH_PORT=2024
LITELLM_PORT=4000
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687

# Version
DECEPTICON_VERSION=dev
VERSION=0.0.0

# Ollama (optional)
# OLLAMA_API_BASE=http://host.docker.internal:11434
# OLLAMA_MODEL=qwen2.5-coder-7b-instruct
ENVEOF
    log_info ".env created. Edit it to add your LLM API keys."
  fi
}

# ── Build and start ─────────────────────────────────────────────────────
do_up() {
  check_prerequisites
  ensure_env

  log_step "Starting Decepticon..."

  local build_args=()
  if [ "$NO_BUILD" = true ]; then
    log_info "Skipping build (--no-build)"
    build_args=("--no-build")
  fi

  log_step "Building and starting services..."
  $COMPOSE build "${build_args[@]}" 2>&1 | tail -20

  log_step "Starting containers..."
  $COMPOSE up -d --wait --wait-timeout 600 2>&1 | tail -10

  echo ""
  log_info "═══════════════════════════════════════════════════════"
  log_info "  Decepticon is starting up!"
  log_info "═══════════════════════════════════════════════════════"
  echo ""
  log_info "  Web Dashboard:    http://localhost:${WEB_PORT:-3000}"
  log_info "  LangGraph API:    http://localhost:${LANGGRAPH_PORT:-2024}"
  log_info "  LiteLLM Proxy:    http://localhost:${LITELLM_PORT:-4000}"
  log_info "  Neo4j Browser:    http://localhost:7474"
  log_info "    (user: neo4j, pass: ${NEO4J_PASSWORD:-decepticon-graph})"
  echo ""
  log_warn "  First build takes 5-10 minutes. Services may need"
  log_warn "  1-2 minutes to become healthy after containers start."
  echo ""
  log_info "  View logs:  ./start.sh --logs"
  log_info "  Stop:       ./start.sh --down"
  log_info "  Status:     ./start.sh --status"
  echo ""

  # Wait a moment then show status
  sleep 5
  do_status
}

# ── Stop ────────────────────────────────────────────────────────────────
do_down() {
  log_step "Stopping Decepticon..."
  $COMPOSE down --remove-orphans
  log_info "All services stopped."
}

# ── Status ──────────────────────────────────────────────────────────────
do_status() {
  echo ""
  log_info "Service Status:"
  echo ""
  $COMPOSE ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || $COMPOSE ps
  echo ""
}

# ── Logs ────────────────────────────────────────────────────────────────
do_logs() {
  log_info "Following logs (Ctrl-C to exit)..."
  $COMPOSE logs -f "${EXTRA_ARGS[@]:-}"
}

# ── Main ────────────────────────────────────────────────────────────────
case "$ACTION" in
  up)     do_up ;;
  down)   do_down ;;
  status) do_status ;;
  logs)   do_logs ;;
  *)
    log_error "Unknown action: $ACTION"
    echo "Usage: ./start.sh [--no-build|--down|--status|--logs|--help]"
    exit 1
    ;;
esac
