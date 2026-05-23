#!/usr/bin/env bash
# =============================================================================
# Decepticon — VPS Setup Script
# =============================================================================
# Run on a fresh Ubuntu 24.04 / Debian 12+ VPS as root:
#   curl -fsSL https://raw.githubusercontent.com/sistem-ciler/Decepticon/main/scripts/vps-setup.sh | bash
# =============================================================================

set -euo pipefail

GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'
log() { echo -e "${GREEN}[+]${NC} $*"; }
step() { echo -e "${BLUE}[*]${NC} $*"; }

step "Updating system..."
apt-get update -qq && apt-get upgrade -y -qq

step "Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log "Docker installed: $(docker version --format '{{.Server.Version}}')"
else
    log "Docker already installed"
fi

step "Installing dependencies..."
apt-get install -y -qq git curl ufw

step "Configuring firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment "SSH"
ufw allow 80/tcp comment "HTTP"
ufw allow 443/tcp comment "HTTPS"
ufw allow 3000/tcp comment "Decepticon Web"
ufw allow 2024/tcp comment "LangGraph API"
ufw --force enable
log "Firewall configured"

step "Cloning Decepticon..."
INSTALL_DIR="/opt/decepticon"
if [ -d "$INSTALL_DIR" ]; then
    cd "$INSTALL_DIR" && git pull
else
    git clone https://github.com/sistem-ciler/Decepticon.git "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

step "Creating .env..."
if [ ! -f .env ]; then
    cp .env.example .env
    # Generate random passwords
    POSTGRES_PASS=$(openssl rand -hex 16)
    NEO4J_PASS=$(openssl rand -hex 16)
    LITELLM_KEY=$(openssl rand -hex 24)
    sed -i "s/POSTGRES_PASSWORD=decepticon/POSTGRES_PASSWORD=${POSTGRES_PASS}/" .env
    sed -i "s/NEO4J_PASSWORD=decepticon-graph/NEO4J_PASSWORD=${NEO4J_PASS}/" .env
    sed -i "s/LITELLM_MASTER_KEY=sk-decepticon-master/LITELLM_MASTER_KEY=sk-${LITELLM_KEY}/" .env
    log "Generated random passwords in .env"
fi

step "Building and starting Decepticon..."
chmod +x start.sh
./start.sh

echo ""
log "═══════════════════════════════════════════════════════"
log "  Decepticon installed!"
log "═══════════════════════════════════════════════════════"
echo ""
log "  Web Dashboard:    http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):3000"
log "  LangGraph API:    http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):2024"
log "  Neo4j Browser:    http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR_IP'):7474"
echo ""
log "  Manage: cd ${INSTALL_DIR} && ./start.sh --help"
