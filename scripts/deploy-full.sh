#!/usr/bin/env bash
# =============================================================================
# Decepticon + BitNet — Full Stack Deployment Script
# =============================================================================
# Deploys the complete integrated stack on a fresh VPS:
#   - Decepticon (red team agent framework)
#   - BitNet (local 1-bit LLM inference)
#   - All supporting services (postgres, neo4j, litellm, web UI)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/sistem-ciler/Decepticon/main/scripts/deploy-full.sh | bash
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[+]${NC} $*"; }
step() { echo -e "${BLUE}[*]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[X]${NC} $*"; }

INSTALL_DIR="/opt/decepticon"
BITNET_DIR="/opt/bitnet"

# ── System check ─────────────────────────────────────────────────────────
step "System check..."
if [[ "$(uname)" != "Linux" ]]; then
    err "This script only supports Linux."
    exit 1
fi
if [[ $EUID -ne 0 ]]; then
    err "Run as root: sudo bash $0"
    exit 1
fi

ARCH=$(uname -m)
if [[ "$ARCH" != "x86_64" ]]; then
    err "Only x86_64 is supported. Detected: $ARCH"
    exit 1
fi

TOTAL_MEM_GB=$(free -g | awk '/MemTotal/{print $2}')
if [[ $TOTAL_MEM_GB -lt 8 ]]; then
    warn "Recommended: 8GB+ RAM. Detected: ${TOTAL_MEM_GB}GB"
fi

log "System OK: $ARCH, ${TOTAL_MEM_GB}RAM, $(nproc) CPUs"

# ── Install Docker ───────────────────────────────────────────────────────
step "Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log "Docker installed: $(docker version --format '{{.Server.Version}}')"
else
    log "Docker already installed: $(docker version --format '{{.Server.Version}}')"
fi

# ── Configure firewall ───────────────────────────────────────────────────
step "Configuring firewall..."
if command -v ufw &>/dev/null; then
    ufw allow 22/tcp comment "SSH"
    ufw allow 80/tcp comment "HTTP"
    ufw allow 443/tcp comment "HTTPS"
    ufw allow 3000/tcp comment "Decepticon Web"
    ufw allow 2024/tcp comment "LangGraph API"
    ufw allow 8080/tcp comment "BitNet API"
    ufw --force enable
    log "Firewall configured"
else
    warn "ufw not found, skipping firewall setup"
fi

# ── Clone repos ──────────────────────────────────────────────────────────
step "Cloning repositories..."

# Decepticon
if [[ -d "$INSTALL_DIR" ]]; then
    cd "$INSTALL_DIR" && git pull
    log "Decepticon updated"
else
    git clone https://github.com/sistem-ciler/Decepticon.git "$INSTALL_DIR"
    log "Decepticon cloned"
fi

# BitNet (for model download and setup)
if [[ -d "$BITNET_DIR" ]]; then
    cd "$BITNET_DIR" && git pull
    log "BitNet updated"
else
    git clone --recursive https://github.com/microsoft/BitNet.git "$BITNET_DIR"
    log "BitNet cloned"
fi

cd "$INSTALL_DIR"

# ── Create .env ──────────────────────────────────────────────────────────
step "Creating .env..."
if [[ ! -f .env ]]; then
    POSTGRES_PASS=$(openssl rand -hex 16 2>/dev/null || head -c 32 /dev/urandom | xxd -p)
    NEO4J_PASS=$(openssl rand -hex 16 2>/dev/null || head -c 32 /dev/urandom | xxd -p)
    LITELLM_KEY="sk-$(openssl rand -hex 24 2>/dev/null || head -c 48 /dev/urandom | xxd -p)"

    cat > .env << EOF
# Decepticon + BitNet — Environment
POSTGRES_PASSWORD=${POSTGRES_PASS}
NEO4J_PASSWORD=${NEO4J_PASS}
LITELLM_MASTER_KEY=${LITELLM_KEY}
LITELLM_SALT_KEY=sk-decepticon-salt

# BitNet
BITNET_MODEL=bitnet-2b
BITNET_THREADS=$(nproc)
BITNET_CTX_SIZE=4096

# Model Profile: eco | max | test
DECEPTICON_MODEL_PROFILE=eco

# Ports
WEB_PORT=3000
LANGGRAPH_PORT=2024
LITELLM_PORT=4000
BITNET_PORT=8080
NEO4J_HTTP_PORT=7474
NEO4J_BOLT_PORT=7687

# Cloud API keys (optional — BitNet handles local inference)
ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
OPENAI_API_KEY=${OPENAI_API_KEY:-}
GEMINI_API_KEY=${GEMINI_API_KEY:-}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}

DECEPTICON_VERSION=dev
VERSION=0.0.0
EOF
    log ".env created with random passwords"
else
    log ".env already exists"
fi

# ── Build and start ─────────────────────────────────────────────────────
step "Building Docker images (first run takes 5-10 minutes)..."
docker compose -f docker-compose.integrated.yml build 2>&1 | tail -20

step "Starting services..."
docker compose -f docker-compose.integrated.yml up -d --wait --wait-timeout 600 2>&1 | tail -10

# ── Download BitNet model ────────────────────────────────────────────────
step "Checking BitNet models..."
MODEL_DIR="$BITNET_DIR/models/BitNet-b1.58-2B-4T"
if [[ ! -d "$MODEL_DIR" ]]; then
    log "Downloading BitNet 2B model (about 1.5GB)..."
    cd "$BITNET_DIR"
    pip install -q huggingface-hub 2>/dev/null || true
    python3 -c "
from huggingface_hub import snapshot_download
snapshot_download('microsoft/BitNet-b1.58-2B-4T', local_dir='models/BitNet-b1.58-2B-4T', local_dir_use_symlinks=False)
" 2>&1 | tail -5
    log "Model downloaded"
else
    log "BitNet model already exists"
fi

# ── Status ───────────────────────────────────────────────────────────────
echo ""
log "═══════════════════════════════════════════════════════"
log "  Decepticon + BitNet — Deployment Complete!"
log "═══════════════════════════════════════════════════════"
echo ""

PUBLIC_IP=$(curl -s --max-time 5 ifconfig.me 2>/dev/null || echo "YOUR_IP")

log "  Web Dashboard:    http://${PUBLIC_IP}:3000"
log "  LangGraph API:    http://${PUBLIC_IP}:2024"
log "  BitNet API:       http://${PUBLIC_IP}:8080"
log "  LiteLLM Proxy:    http://${PUBLIC_IP}:4000"
log "  Neo4j Browser:    http://${PUBLIC_IP}:7474"
echo ""
log "  BitNet Models:"
log "    - bitnet-2b:    2.4B params, ~1.5GB RAM (recommended)"
log "    - bitnet-3b:    3.3B params, ~2.5GB RAM"
log "    - falcon-e-1b:  1.0B params, ~0.8GB RAM (fastest)"
log "    - falcon-e-3b:  3.0B params, ~1.5GB RAM (edge)"
echo ""
log "  Management:"
log "    cd ${INSTALL_DIR}"
log "    docker compose -f docker-compose.integrated.yml ps"
log "    docker compose -f docker-compose.integrated.yml logs -f"
log "    docker compose -f docker-compose.integrated.yml down"
echo ""
