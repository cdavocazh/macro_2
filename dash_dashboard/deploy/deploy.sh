#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Automated deployment of Macro Dashboard to Ubuntu VPS (Lightsail)
#
# Prerequisites:
#   - Ubuntu 22.04 or 24.04 Lightsail instance (1 GB RAM minimum, 2 GB recommended)
#   - SSH access as 'ubuntu' user
#   - This repo cloned to /opt/macro_2
#
# Usage:
#   sudo bash dash_dashboard/deploy/deploy.sh
#
# What this script does:
#   1. Installs system packages (Python 3.10+, Nginx, certbot)
#   2. Creates Python virtual environment and installs dependencies
#   3. Creates required directories and sets permissions
#   4. Copies environment file template
#   5. Seeds initial data cache (first extraction)
#   6. Installs systemd services (Gunicorn + extraction timers)
#   7. Configures Nginx reverse proxy
#   8. Starts everything
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────
APP_DIR="/opt/macro_2"
VENV_DIR="${APP_DIR}/venv"
DEPLOY_DIR="${APP_DIR}/dash_dashboard/deploy"
LOG_DIR="/var/log/macro-dash"
SERVICE_USER="ubuntu"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; }

# ─── Pre-checks ─────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
    err "This script must be run as root (sudo)"
    exit 1
fi

if [[ ! -d "${APP_DIR}" ]]; then
    err "App directory ${APP_DIR} not found."
    echo "Clone the repo first:"
    echo "  sudo git clone https://github.com/cdavocazh/macro_2.git ${APP_DIR}"
    echo "  sudo chown -R ${SERVICE_USER}:${SERVICE_USER} ${APP_DIR}"
    exit 1
fi

log "Starting deployment of Macro Dashboard..."
echo "────────────────────────────────────────────"

# ─── Step 1: System packages ────────────────────────────────────────────────
log "Step 1/7: Installing system packages..."
apt-get update -qq
apt-get install -y -qq \
    python3 python3-venv python3-pip python3-dev \
    nginx certbot python3-certbot-nginx \
    build-essential curl git

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
log "  Python version: ${PYTHON_VERSION}"

# ─── Step 2: Python virtual environment ─────────────────────────────────────
log "Step 2/7: Setting up Python virtual environment..."
if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
    log "  Created venv at ${VENV_DIR}"
else
    log "  Venv already exists at ${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip -q
"${VENV_DIR}/bin/pip" install -r "${DEPLOY_DIR}/requirements-server.txt" -q
log "  Dependencies installed"

# ─── Step 3: Directories and permissions ────────────────────────────────────
log "Step 3/7: Creating directories and setting permissions..."
mkdir -p "${APP_DIR}/data_cache"
mkdir -p "${APP_DIR}/historical_data"
mkdir -p "${APP_DIR}/data_export"
mkdir -p "${APP_DIR}/logs"
mkdir -p "${LOG_DIR}"

chown -R ${SERVICE_USER}:${SERVICE_USER} "${APP_DIR}"
chown -R ${SERVICE_USER}:${SERVICE_USER} "${LOG_DIR}"
log "  Directories ready"

# ─── Step 4: Environment file ───────────────────────────────────────────────
log "Step 4/7: Setting up environment file..."
if [[ ! -f "${APP_DIR}/.env" ]]; then
    cp "${DEPLOY_DIR}/.env.example" "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    chown ${SERVICE_USER}:${SERVICE_USER} "${APP_DIR}/.env"
    warn "  Created ${APP_DIR}/.env from template — EDIT IT with your FRED_API_KEY!"
else
    log "  .env already exists, skipping"
fi

# ─── Step 5: Seed initial data ──────────────────────────────────────────────
log "Step 5/7: Seeding initial data cache (this takes ~40s)..."
if [[ ! -f "${APP_DIR}/data_cache/all_indicators.json" ]]; then
    sudo -u ${SERVICE_USER} bash -c "
        source ${VENV_DIR}/bin/activate
        cd ${APP_DIR}
        python scheduled_extract.py --force 2>&1 | tail -5
    " || warn "  Initial extraction failed — dashboard will start with empty data. Run manually later."
    log "  Initial data extraction complete"
else
    log "  Cache already exists, skipping initial extraction"
fi

# ─── Step 6: Install systemd services ───────────────────────────────────────
log "Step 6/7: Installing systemd services..."

# Dash web app (Gunicorn)
cp "${DEPLOY_DIR}/macro-dash.service" /etc/systemd/system/
log "  Installed macro-dash.service"

# Full extraction timer (5x/day)
cp "${DEPLOY_DIR}/macro-extract.service" /etc/systemd/system/
cp "${DEPLOY_DIR}/macro-extract.timer"   /etc/systemd/system/
log "  Installed macro-extract.service + timer"

# Fast extraction timer (every 5 min)
cp "${DEPLOY_DIR}/macro-fast-extract.service" /etc/systemd/system/
cp "${DEPLOY_DIR}/macro-fast-extract.timer"   /etc/systemd/system/
log "  Installed macro-fast-extract.service + timer"

systemctl daemon-reload

# Enable and start
systemctl enable --now macro-dash.service
systemctl enable --now macro-extract.timer
systemctl enable --now macro-fast-extract.timer

log "  All services started"

# ─── Step 7: Nginx reverse proxy ────────────────────────────────────────────
log "Step 7/7: Configuring Nginx..."
cp "${DEPLOY_DIR}/nginx-macro-dash.conf" /etc/nginx/sites-available/macro-dash
ln -sf /etc/nginx/sites-available/macro-dash /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

if nginx -t 2>/dev/null; then
    systemctl reload nginx
    log "  Nginx configured and reloaded"
else
    err "  Nginx config test failed! Run: sudo nginx -t"
fi

# ─── Done ────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════════════════════"
echo -e "${GREEN}  ✅ Deployment complete!${NC}"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "  Dashboard URL:   http://$(curl -s ifconfig.me 2>/dev/null || echo '<YOUR_IP>')"
echo ""
echo "  Quick commands:"
echo "    sudo systemctl status macro-dash           # check web server"
echo "    sudo journalctl -u macro-dash -f           # stream web logs"
echo "    sudo journalctl -u macro-extract -f        # stream extraction logs"
echo "    systemctl list-timers macro-*               # check schedules"
echo ""
echo "  Next steps:"
echo "    1. Edit /opt/macro_2/.env with your FRED_API_KEY"
echo "    2. (Optional) Point a domain and run: sudo certbot --nginx -d yourdomain.com"
echo "    3. Open Lightsail firewall: Networking > IPv4 Firewall > Add rule > HTTP (80)"
echo ""
