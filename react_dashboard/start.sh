#!/bin/bash
# Start both FastAPI backend and React frontend for the Macro Dashboard.
# Usage: bash start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Install backend deps if needed
echo -e "${GREEN}[1/4] Checking backend dependencies...${NC}"
cd "$BACKEND_DIR"
$PYTHON -c "import fastapi" 2>/dev/null || {
    echo "Installing FastAPI dependencies..."
    $PYTHON -m pip install -r requirements.txt
}

# Install frontend deps if needed
echo -e "${GREEN}[2/4] Checking frontend dependencies...${NC}"
cd "$FRONTEND_DIR"
if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

# Start backend
echo -e "${GREEN}[3/4] Starting FastAPI backend on :8000...${NC}"
cd "$BACKEND_DIR"
$PYTHON -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 2

# Start frontend
echo -e "${GREEN}[4/4] Starting React frontend on :5173...${NC}"
cd "$FRONTEND_DIR"
npm run dev &
FRONTEND_PID=$!

echo ""
echo -e "${BLUE}Dashboard running:${NC}"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo "  API docs: http://localhost:8000/docs"
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
