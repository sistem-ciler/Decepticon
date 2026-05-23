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
PROJECT_NAME="decepticon"

# Detect Docker Compose command
if docker compose version &>/dev/null 2>&1; then
    COMPOSE="docker compose -f ${COMPOSE_FILE}"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose -f ${COMPOSE_FILE}"
else
    echo "ERROR: Docker Compose not found. Install Docker first."
    exit 1
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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
      echo "After startup:"
      echo "  Web Dashboard:    http://localhost:3000"
      echo "  LangGraph API:    http://localhost:2024"
      echo "  LiteLLM Proxy:    http://localhost:4000"
      echo "  Neo4j Browser:    http://localhost:7474"
      exit 0
      ;;
    *) EXTRA_ARGS+=("$arg") ;;
  esac
done

# ── Check prerequisites ─────────────────────────────────────────────────
check_prerequisites() {
  log_step "Checking prerequisites..."

  # Wait for Docker daemon (up to 30s)
  local docker_ready=false
  for i in $(seq 1 15); do
    if docker info &>/dev/null 2>&1; then
      docker_ready=true
      break
    fi
    sleep 2
  done

  if [ "$docker_ready" = false ]; then
    log_error "Docker daemon is not responding."
    log_error "Start Docker manually: sudo systemctl start docker"
    log_error "Or if Docker is not installed:"
    log_error "  curl -fsSL https://get.docker.com | sh"
    log_error "  sudo usermod -aG docker \$USER"
    exit 1
  fi

  log_info "Docker OK: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'unknown')"
}

# ── Ensure .env exists ──────────────────────────────────────────────────
ensure_env() {
  if [ ! -f .env ]; then
    log_step "Creating .env from template..."
    sed 's/your-anthropic-key-here/sk-placeholder/' .env.example > .env 2>/dev/null || cp .env.example .env
    log_info ".env created. Edit it to add your LLM API keys."
  fi
}

# ── Build and start ─────────────────────────────────────────────────────
do_up() {
  check_prerequisites
  ensure_env

  log_step "Starting Decepticon..."

  local up_args=()
  if [ "$NO_BUILD" = true ]; then
    log_info "Skipping build (--no-build)"
    up_args=("--no-build")
  fi

  log_step "Building images (first run takes 5-10 minutes)..."
    $COMPOSE build "${up_args[@]}" 2>&1 | tail -20

  log_step "Starting services..."
  $COMPOSE up -d --wait --wait-timeout 600 2>&1 | tail -10

  echo ""
  log_info "═══════════════════════════════════════════════════════"
  log_info "  Decepticon is running!"
  log_info "═══════════════════════════════════════════════════════"
  echo ""
  log_info "  Web Dashboard:    http://localhost:${WEB_PORT:-3000}"
  log_info "  LangGraph API:    http://localhost:${LANGGRAPH_PORT:-2024}"
  log_info "  LiteLLM Proxy:    http://localhost:${LITELLM_PORT:-4000}"
  log_info "  Neo4j Browser:    http://localhost:7474"
  log_info "    (user: neo4j, pass: ${NEO4J_PASSWORD:-decepticon-graph})"
  echo ""
  log_info "  View logs:  ./start.sh --logs"
  log_info "  Stop:       ./start.sh --down"
  log_info "  Status:     ./start.sh --status"
  echo ""

  sleep 3
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
  $COMPOSE ps 2>/dev/null || true
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
