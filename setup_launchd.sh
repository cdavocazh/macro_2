#!/bin/bash
# ==============================================================================
# setup_launchd.sh — Install or uninstall macOS launchd schedulers
#
# Five jobs:
#   1. scheduled-extract:   Full extraction 5x/day Mon-Sat (FRED, SEC, web scrapers)
#   2. fast-extract:        Real-time yfinance data every 5 minutes
#   3. hl-extract:          Hyperliquid perps every 1 minute
#   4. polymarket-extract:  Polymarket prediction markets every 5 minutes
#   5. onchain-extract:     CheckOnChain BTC on-chain data daily at 14:00 GMT+8
#
# Generates .plist files from .plist.example templates, replacing placeholders
# with your local Python path and project directory. The generated .plist files
# are gitignored — only the .example templates are committed.
#
# launchd catches up missed runs after sleep/restart, unlike cron.
#
# Usage:
#   bash setup_launchd.sh              # Install all jobs
#   bash setup_launchd.sh --uninstall  # Deactivate and remove all
#   bash setup_launchd.sh --status     # Check if jobs are loaded
# ==============================================================================

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="${REPO_DIR}/logs"

# Auto-detect Python path (prefer conda/mamba, then system)
if command -v python3 &>/dev/null; then
    PYTHON_PATH="$(which python3)"
else
    echo "ERROR: python3 not found in PATH. Please install Python 3."
    exit 1
fi
PYTHON_BIN_DIR="$(dirname "$PYTHON_PATH")"

JOBS=("com.macro2.scheduled-extract" "com.macro2.fast-extract" "com.macro2.hl-extract" "com.macro2.polymarket-extract" "com.macro2.onchain-extract")

# ---------- Generate .plist from .plist.example ----------
generate_plist() {
    local NAME="$1"
    local TEMPLATE="${REPO_DIR}/${NAME}.plist.example"
    local OUTPUT="${REPO_DIR}/${NAME}.plist"

    if [[ ! -f "$TEMPLATE" ]]; then
        echo "  WARNING: ${TEMPLATE} not found, skipping."
        return 1
    fi

    sed \
        -e "s|__PYTHON_PATH__|${PYTHON_PATH}|g" \
        -e "s|__PYTHON_BIN_DIR__|${PYTHON_BIN_DIR}|g" \
        -e "s|__PROJECT_DIR__|${REPO_DIR}|g" \
        "$TEMPLATE" > "$OUTPUT"

    echo "  Generated ${NAME}.plist (python: ${PYTHON_PATH})"
    return 0
}

# ---------- Uninstall ----------
if [[ "$1" == "--uninstall" ]]; then
    echo "Uninstalling macro_2 launchd jobs..."
    for NAME in "${JOBS[@]}"; do
        DST="$HOME/Library/LaunchAgents/${NAME}.plist"
        if launchctl list | grep -q "$NAME"; then
            launchctl unload "$DST" 2>/dev/null || true
            echo "  Unloaded $NAME"
        fi
        if [[ -f "$DST" ]]; then
            rm "$DST"
            echo "  Removed $DST"
        fi
        # Clean up generated plist in repo dir
        if [[ -f "${REPO_DIR}/${NAME}.plist" ]]; then
            rm "${REPO_DIR}/${NAME}.plist"
        fi
    done
    echo "Done. All scheduled jobs removed."
    exit 0
fi

# ---------- Status ----------
if [[ "$1" == "--status" ]]; then
    echo "=== macro_2 launchd status ==="
    echo ""
    for NAME in "${JOBS[@]}"; do
        if launchctl list | grep -q "$NAME"; then
            echo "$NAME: LOADED"
            launchctl list | grep "$NAME"
        else
            echo "$NAME: NOT loaded"
        fi
    done
    echo ""
    echo "Log files:"
    for LOG in launchd_stdout.log launchd_stderr.log fast_extract_stdout.log fast_extract_stderr.log hl_extract_stdout.log hl_extract_stderr.log polymarket_extract_stdout.log polymarket_extract_stderr.log onchain_extract_stdout.log onchain_extract_stderr.log; do
        if [[ -f "$LOGS_DIR/$LOG" ]]; then
            echo "  $LOG: $(wc -l < "$LOGS_DIR/$LOG") lines"
        else
            echo "  $LOG: (no log yet)"
        fi
    done
    exit 0
fi

# ---------- Install ----------
echo "Installing macOS launchd schedulers for macro_2..."
echo "  Python: ${PYTHON_PATH}"
echo "  Project: ${REPO_DIR}"
echo ""

# Create logs directory
mkdir -p "$LOGS_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

# Generate and install each job
for NAME in "${JOBS[@]}"; do
    DST="$HOME/Library/LaunchAgents/${NAME}.plist"

    # Generate .plist from template
    if ! generate_plist "$NAME"; then
        continue
    fi

    SRC="${REPO_DIR}/${NAME}.plist"

    # Unload existing
    if launchctl list | grep -q "$NAME"; then
        launchctl unload "$DST" 2>/dev/null || true
    fi

    # Copy and load
    cp "$SRC" "$DST"
    launchctl load "$DST"

    if launchctl list | grep -q "$NAME"; then
        echo "  ✅ $NAME — loaded"
    else
        echo "  ❌ $NAME — failed to load"
    fi
done

echo ""
echo "=== Schedule ==="
echo "  scheduled-extract: 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8 (Mon-Sat)"
echo "                     Full extraction: FRED, SEC, web scrapers, yfinance, all CSVs"
echo ""
echo "  fast-extract:      Every 5 minutes (24/7)"
echo "                     Real-time only: yfinance futures, FX, commodities, indices"
echo ""
echo "  hl-extract:        Every 1 minute (24/7)"
echo "                     Hyperliquid perps + HIP-3 spot stocks"
echo ""
echo "  polymarket-extract: Every 5 minutes (24/7)"
echo "                     Polymarket prediction market events (Finance, Geopolitics, Trending)"
echo ""
echo "  onchain-extract:   Daily at 14:00 GMT+8 (06:00 UTC)"
echo "                     CheckOnChain BTC on-chain metrics (MVRV, SOPR, NUPL, etc.)"
echo ""
echo "Logs: $LOGS_DIR/"
echo ""
echo "Commands:"
echo "  bash setup_launchd.sh --status      # Check status"
echo "  bash setup_launchd.sh --uninstall   # Remove all jobs"
echo "  launchctl start com.macro2.scheduled-extract  # Run full extraction now"
echo "  launchctl start com.macro2.fast-extract       # Run fast extraction now"
echo "  launchctl start com.macro2.hl-extract         # Run HL extraction now"
echo "  launchctl start com.macro2.polymarket-extract  # Run Polymarket extraction now"
echo "  launchctl start com.macro2.onchain-extract     # Run on-chain extraction now"
