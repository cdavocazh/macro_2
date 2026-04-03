#!/bin/bash
# Start both FastAPI backend and React frontend for the Macro Dashboard.
# Usage: bash start.sh
# Ports auto-increment if the default is already in use.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[0;33m'
NC='\033[0m'

# Find a free port starting from the given port, trying up to 20 consecutive ports.
find_free_port() {
    local port=$1
    local max_attempts=20
    for ((i=0; i<max_attempts; i++)); do
        if ! lsof -i :"$port" -sTCP:LISTEN &>/dev/null; then
            echo "$port"
            return 0
        fi
        port=$((port + 1))
    done
    echo "Error: Could not find a free port starting from $1" >&2
    return 1
}

echo -e "${BLUE}Starting Macro Indicators Dashboard${NC}"
echo "========================================"

# Check Python
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" &>/dev/null; then
    echo "Error: Python not found. Set PYTHON env var to your Python path."
    exit 1
fi

# Check Node.js
if ! command -v node &>/dev/null; then
    echo "Error: Node.js not found. Install Node.js 18+ first."
    exit 1
fi

# Resolve ports (auto-find free ones)
BACKEND_PORT="${BACKEND_PORT:-$(find_free_port 8000)}"
FRONTEND_PORT="${FRONTEND_PORT:-$(find_free_port 5173)}"

if [ "$BACKEND_PORT" != "8000" ]; then
    echo -e "${YELLOW}Port 8000 in use, backend will use :${BACKEND_PORT}${NC}"
fi
if [ "$FRONTEND_PORT" != "5173" ]; then
    echo -e "${YELLOW}Port 5173 in use, frontend will use :${FRONTEND_PORT}${NC}"
fi

# Install backend deps if needed
echo -e "${GREEN}[1/5] Checking backend dependencies...${NC}"
cd "$BACKEND_DIR"
$PYTHON -c "import fastapi" 2>/dev/null || {
    echo "Installing FastAPI dependencies..."
    $PYTHON -m pip install -r requirements.txt
}

# Install frontend deps if needed
echo -e "${GREEN}[2/5] Checking frontend dependencies...${NC}"
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Ensure indicator data exists (run scheduled_extract.py if cache is missing)
echo -e "${GREEN}[3/5] Checking for cached indicator data...${NC}"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CACHE_FILE="$PROJECT_ROOT/data_cache/all_indicators.json"
if [ ! -f "$CACHE_FILE" ]; then
    echo -e "${YELLOW}No cached data found. Running scheduled_extract.py to populate...${NC}"
    cd "$PROJECT_ROOT"
    $PYTHON scheduled_extract.py --force || {
        echo -e "${YELLOW}Warning: Data extraction failed. Dashboard will start but show no data.${NC}"
    }
else
    echo "Cache found: $(ls -lh "$CACHE_FILE" | awk '{print $5}')"
fi

# Start backend (must run from project root so data_cache/ paths resolve correctly)
echo -e "${GREEN}[4/5] Starting FastAPI backend on :${BACKEND_PORT}...${NC}"
cd "$PROJECT_ROOT"
$PYTHON -m uvicorn react_dashboard.backend.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start frontend (pass backend port so Vite proxy targets the right port)
echo -e "${GREEN}[5/5] Starting React frontend on :${FRONTEND_PORT}...${NC}"
cd "$FRONTEND_DIR"
VITE_BACKEND_PORT="$BACKEND_PORT" npx vite --port "$FRONTEND_PORT" --strictPort &
FRONTEND_PID=$!

echo ""
echo -e "${BLUE}Dashboard running:${NC}"
echo "  Backend:  http://localhost:${BACKEND_PORT}"
echo "  Frontend: http://localhost:${FRONTEND_PORT}"
echo "  API docs: http://localhost:${BACKEND_PORT}/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

# Trap Ctrl+C to kill both
cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID 2>/dev/null
    wait $FRONTEND_PID 2>/dev/null
    echo "Done."
}
trap cleanup INT TERM

# Wait for either to exit
wait
