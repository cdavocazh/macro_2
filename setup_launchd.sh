#!/bin/bash
# ==============================================================================
# setup_launchd.sh — Install or uninstall macOS launchd schedulers
#
# Two jobs:
#   1. scheduled-extract: Full extraction 5x/day Mon-Sat (FRED, SEC, web scrapers)
#   2. fast-extract:      Real-time yfinance data every 5 minutes (market hours)
#
# launchd catches up missed runs after sleep/restart, unlike cron.
#
# Usage:
#   bash setup_launchd.sh              # Install both jobs
#   bash setup_launchd.sh --uninstall  # Deactivate and remove both
#   bash setup_launchd.sh --status     # Check if jobs are loaded
# ==============================================================================

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS_DIR="${REPO_DIR}/logs"

SCHEDULED_NAME="com.macro2.scheduled-extract"
FAST_NAME="com.macro2.fast-extract"

SCHEDULED_SRC="${REPO_DIR}/${SCHEDULED_NAME}.plist"
FAST_SRC="${REPO_DIR}/${FAST_NAME}.plist"

SCHEDULED_DST="$HOME/Library/LaunchAgents/${SCHEDULED_NAME}.plist"
FAST_DST="$HOME/Library/LaunchAgents/${FAST_NAME}.plist"

# ---------- Uninstall ----------
if [[ "$1" == "--uninstall" ]]; then
    echo "Uninstalling macro_2 launchd jobs..."
    for NAME in "$SCHEDULED_NAME" "$FAST_NAME"; do
        DST="$HOME/Library/LaunchAgents/${NAME}.plist"
        if launchctl list | grep -q "$NAME"; then
            launchctl unload "$DST" 2>/dev/null || true
            echo "  Unloaded $NAME"
        fi
        if [[ -f "$DST" ]]; then
            rm "$DST"
            echo "  Removed $DST"
        fi
    done
    echo "Done. All scheduled jobs removed."
    exit 0
fi

# ---------- Status ----------
if [[ "$1" == "--status" ]]; then
    echo "=== macro_2 launchd status ==="
    echo ""
    for NAME in "$SCHEDULED_NAME" "$FAST_NAME"; do
        if launchctl list | grep -q "$NAME"; then
            echo "$NAME: LOADED"
            launchctl list | grep "$NAME"
        else
            echo "$NAME: NOT loaded"
        fi
    done
    echo ""
    echo "Log files:"
    for LOG in launchd_stdout.log launchd_stderr.log fast_extract_stdout.log fast_extract_stderr.log; do
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
echo ""

# Create logs directory
mkdir -p "$LOGS_DIR"
mkdir -p "$HOME/Library/LaunchAgents"

# Install each job
for NAME in "$SCHEDULED_NAME" "$FAST_NAME"; do
    SRC="${REPO_DIR}/${NAME}.plist"
    DST="$HOME/Library/LaunchAgents/${NAME}.plist"

    if [[ ! -f "$SRC" ]]; then
        echo "  WARNING: ${SRC} not found, skipping."
        continue
    fi

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
echo "Logs: $LOGS_DIR/"
echo ""
echo "Commands:"
echo "  bash setup_launchd.sh --status      # Check status"
echo "  bash setup_launchd.sh --uninstall   # Remove all jobs"
echo "  launchctl start $SCHEDULED_NAME     # Run full extraction now"
echo "  launchctl start $FAST_NAME          # Run fast extraction now"
