#!/bin/bash
# Start the Grafana Macro Dashboard
# Usage:
#   ./start.sh          — auto-detect: Docker if available, otherwise local
#   ./start.sh docker   — force Docker Compose
#   ./start.sh local    — start API bridge + Grafana locally (Homebrew)
#   ./start.sh stop     — stop all services

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
PYTHON="${PYTHON:-python3}"

# ─── Helper functions ────────────────────────────────────────────────────────

has_docker() {
    if ! command -v docker >/dev/null 2>&1; then
        return 1
    fi
    # Docker CLI exists — check if daemon is running
    if ! docker info >/dev/null 2>&1; then
        echo "Docker CLI found but daemon not running. Starting Docker Desktop..."
        open -a "Docker" 2>/dev/null || return 1
        # Wait up to 60s for daemon
        for i in $(seq 1 30); do
            if docker info >/dev/null 2>&1; then
                echo "Docker daemon is ready."
                return 0
            fi
            sleep 2
        done
        echo "WARNING: Docker daemon did not start within 60s."
        return 1
    fi
    return 0
}

has_brew_grafana() {
    command -v grafana &>/dev/null || command -v grafana-server &>/dev/null || \
        brew list grafana &>/dev/null 2>&1
}

install_grafana_brew() {
    echo "Installing Grafana via Homebrew..."
    if ! command -v brew &>/dev/null; then
        echo "ERROR: Homebrew not found. Install from https://brew.sh"
        exit 1
    fi
    brew install grafana
    echo "Installing Infinity plugin..."
    grafana cli plugins install yesoreyeram-infinity-datasource 2>/dev/null || \
        grafana-cli plugins install yesoreyeram-infinity-datasource 2>/dev/null || true
}

setup_grafana_local() {
    # Determine Grafana config/data directories
    local GRAFANA_HOME
    if [ -d "/opt/homebrew/share/grafana" ]; then
        GRAFANA_HOME="/opt/homebrew/share/grafana"
    elif [ -d "/usr/local/share/grafana" ]; then
        GRAFANA_HOME="/usr/local/share/grafana"
    else
        GRAFANA_HOME="$(brew --prefix grafana 2>/dev/null)/share/grafana" || true
    fi

    local GRAFANA_PROV
    if [ -d "/opt/homebrew/etc/grafana/provisioning" ]; then
        GRAFANA_PROV="/opt/homebrew/etc/grafana/provisioning"
    elif [ -d "/usr/local/etc/grafana/provisioning" ]; then
        GRAFANA_PROV="/usr/local/etc/grafana/provisioning"
    else
        GRAFANA_PROV="$(brew --prefix grafana 2>/dev/null)/etc/grafana/provisioning" || true
    fi

    echo "Grafana home: $GRAFANA_HOME"
    echo "Provisioning: $GRAFANA_PROV"

    # Symlink provisioning files
    if [ -d "$GRAFANA_PROV" ]; then
        echo "Setting up provisioning symlinks..."

        # Datasource — create local-mode config with localhost (not Docker hostname)
        mkdir -p "$GRAFANA_PROV/datasources"
        local DS_FILE="$GRAFANA_PROV/datasources/macro_api.yaml"
        cat > "$DS_FILE" <<DSYAML
apiVersion: 1
datasources:
  - name: MacroAPI
    type: yesoreyeram-infinity-datasource
    access: proxy
    url: http://localhost:8001
    isDefault: true
    editable: true
    jsonData:
      url: http://localhost:8001
    version: 1
DSYAML
        echo "  ✓ Created datasource config (localhost mode)"

        # Dashboard provider
        mkdir -p "$GRAFANA_PROV/dashboards"
        local DP_FILE="$GRAFANA_PROV/dashboards/macro_dashboard_provider.yaml"
        # Create a modified provider yaml with absolute path
        cat > "$DP_FILE" <<YAML
apiVersion: 1
providers:
  - name: "Macro Dashboard"
    orgId: 1
    folder: ""
    type: file
    disableDeletion: false
    editable: true
    options:
      path: ${SCRIPT_DIR}/dashboards
      foldersFromFilesStructure: false
YAML
        echo "  ✓ Created dashboard provider config"
    else
        echo "WARNING: Could not find Grafana provisioning directory at $GRAFANA_PROV"
        echo "You may need to manually import the dashboard JSON from $SCRIPT_DIR/dashboards/"
    fi

    # Install Infinity plugin if not present
    local PLUGINS_DIR
    if [ -d "/opt/homebrew/var/lib/grafana/plugins" ]; then
        PLUGINS_DIR="/opt/homebrew/var/lib/grafana/plugins"
    elif [ -d "/usr/local/var/lib/grafana/plugins" ]; then
        PLUGINS_DIR="/usr/local/var/lib/grafana/plugins"
    fi
    if [ -n "$PLUGINS_DIR" ] && [ ! -d "$PLUGINS_DIR/yesoreyeram-infinity-datasource" ]; then
        echo "Installing Infinity plugin..."
        grafana cli plugins install yesoreyeram-infinity-datasource 2>/dev/null || \
            grafana-cli plugins install yesoreyeram-infinity-datasource 2>/dev/null || \
            echo "WARNING: Could not install Infinity plugin automatically. Install manually."
    fi
}

start_local() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  Macro Dashboard — Local Mode (no Docker)           ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""

    # Check/install Grafana
    if ! has_brew_grafana; then
        echo "Grafana not found. Attempting to install via Homebrew..."
        install_grafana_brew
    fi

    # Setup provisioning
    setup_grafana_local

    # Install Python deps for API bridge
    echo ""
    echo "Checking Python dependencies..."
    pip install fastapi uvicorn --quiet 2>/dev/null || \
        $PYTHON -m pip install fastapi uvicorn --quiet 2>/dev/null || true

    # Start API bridge in background
    echo ""
    echo "Starting API Bridge on http://localhost:8001 ..."
    cd "$PROJECT_ROOT"
    $PYTHON -m uvicorn grafana_dashboard.api_bridge.main:app \
        --host 0.0.0.0 --port 8001 --reload \
        > "$SCRIPT_DIR/logs/api_bridge.log" 2>&1 &
    API_PID=$!
    mkdir -p "$SCRIPT_DIR/logs"
    echo $API_PID > "$SCRIPT_DIR/logs/api_bridge.pid"
    echo "  API Bridge PID: $API_PID"

    # Wait for API to be ready
    echo "  Waiting for API bridge..."
    for i in $(seq 1 15); do
        if curl -sf http://localhost:8001/ >/dev/null 2>&1; then
            echo "  ✓ API Bridge is ready"
            break
        fi
        sleep 1
    done

    # Start Grafana
    echo ""
    echo "Starting Grafana on http://localhost:3000 ..."
    brew services start grafana 2>/dev/null || \
        brew services restart grafana 2>/dev/null || \
        (echo "Starting grafana-server directly..." && \
         grafana-server --homepath="$(brew --prefix grafana)/share/grafana" \
             --config="$(brew --prefix grafana)/etc/grafana/grafana.ini" \
             > "$SCRIPT_DIR/logs/grafana.log" 2>&1 &)

    echo ""
    echo "════════════════════════════════════════════════════════"
    echo "  API Bridge: http://localhost:8001"
    echo "  Grafana:    http://localhost:3000"
    echo "  Credentials: admin / admin (Homebrew default)"
    echo ""
    echo "  Logs: $SCRIPT_DIR/logs/"
    echo "  Stop: $0 stop"
    echo "════════════════════════════════════════════════════════"
    echo ""

    # If running in foreground, wait for API bridge
    if [ -t 0 ]; then
        echo "Press Ctrl+C to stop the API bridge..."
        trap "kill $API_PID 2>/dev/null; brew services stop grafana 2>/dev/null; echo 'Stopped.'" INT TERM
        wait $API_PID
    fi
}

start_docker() {
    echo ""
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║  Macro Dashboard — Docker Compose                   ║"
    echo "╚══════════════════════════════════════════════════════╝"
    echo ""
    echo "  API Bridge: http://localhost:8001"
    echo "  Grafana:    http://localhost:3000 (admin / macro2024)"
    echo ""
    cd "$SCRIPT_DIR"
    docker compose up -d --build
    echo ""
    echo "Dashboard is starting. Open http://localhost:3000"
}

stop_all() {
    echo "Stopping Macro Dashboard..."

    # Stop API bridge
    if [ -f "$SCRIPT_DIR/logs/api_bridge.pid" ]; then
        PID=$(cat "$SCRIPT_DIR/logs/api_bridge.pid")
        kill "$PID" 2>/dev/null && echo "  Stopped API bridge (PID $PID)" || true
        rm -f "$SCRIPT_DIR/logs/api_bridge.pid"
    fi

    # Also kill any lingering uvicorn on port 8001
    lsof -ti:8001 2>/dev/null | xargs kill 2>/dev/null || true

    # Stop Grafana (brew)
    brew services stop grafana 2>/dev/null && echo "  Stopped Grafana (brew)" || true

    # Stop Docker if available
    if has_docker; then
        cd "$SCRIPT_DIR"
        docker compose down 2>/dev/null && echo "  Stopped Docker Compose" || true
    fi

    echo "Stopped."
}

# ─── Main ─────────────────────────────────────────────────────────────────────

case "${1:-auto}" in
    auto)
        if has_docker; then
            start_docker
        else
            echo "Docker not found. Falling back to local mode..."
            start_local
        fi
        ;;
    docker)
        if ! has_docker; then
            echo "ERROR: Docker is not installed or not running."
            echo "Install Docker Desktop from https://www.docker.com/products/docker-desktop/"
            echo ""
            echo "Or use local mode: $0 local"
            exit 1
        fi
        start_docker
        ;;
    local)
        start_local
        ;;
    stop)
        stop_all
        ;;
    status)
        echo "API Bridge:"
        if curl -sf http://localhost:8001/api/status 2>/dev/null; then
            echo "  ✓ Running"
        else
            echo "  ✗ Not running"
        fi
        echo ""
        echo "Grafana:"
        if curl -sf http://localhost:3000/api/health 2>/dev/null; then
            echo "  ✓ Running"
        else
            echo "  ✗ Not running"
        fi
        ;;
    *)
        echo "Usage: $0 [auto|docker|local|stop|status]"
        echo ""
        echo "  auto    — auto-detect: Docker if available, otherwise local (default)"
        echo "  docker  — force Docker Compose"
        echo "  local   — start API bridge + Grafana via Homebrew (no Docker)"
        echo "  stop    — stop all services"
        echo "  status  — check if services are running"
        exit 1
        ;;
esac
