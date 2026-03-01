#!/bin/bash
# ==============================================================================
# setup_launchd.sh — Install or uninstall the macOS launchd scheduler
#
# This schedules scheduled_extract.py to run automatically at:
#   9:30 AM, 1:00 PM, 4:30 PM on weekdays (Mon-Fri)
#
# launchd catches up missed runs after sleep/restart, unlike cron.
#
# Usage:
#   bash setup_launchd.sh              # Install and activate
#   bash setup_launchd.sh --uninstall  # Deactivate and remove
#   bash setup_launchd.sh --status     # Check if job is loaded
# ==============================================================================

set -e

PLIST_NAME="com.macro2.scheduled-extract"
PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/${PLIST_NAME}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOGS_DIR="$(cd "$(dirname "$0")" && pwd)/logs"

# ---------- Uninstall ----------
if [[ "$1" == "--uninstall" ]]; then
    echo "Uninstalling ${PLIST_NAME}..."
    if launchctl list | grep -q "$PLIST_NAME"; then
        launchctl unload "$PLIST_DST" 2>/dev/null || true
        echo "  Job unloaded."
    fi
    if [[ -f "$PLIST_DST" ]]; then
        rm "$PLIST_DST"
        echo "  Plist removed from ~/Library/LaunchAgents/"
    fi
    echo "Done. The scheduled job has been removed."
    exit 0
fi

# ---------- Status ----------
if [[ "$1" == "--status" ]]; then
    if launchctl list | grep -q "$PLIST_NAME"; then
        echo "Job is LOADED and active."
        launchctl list | grep "$PLIST_NAME"
    else
        echo "Job is NOT loaded."
    fi
    echo ""
    echo "Log files:"
    [[ -f "$LOGS_DIR/launchd_stdout.log" ]] && echo "  stdout: $(wc -l < "$LOGS_DIR/launchd_stdout.log") lines" || echo "  stdout: (no log yet)"
    [[ -f "$LOGS_DIR/launchd_stderr.log" ]] && echo "  stderr: $(wc -l < "$LOGS_DIR/launchd_stderr.log") lines" || echo "  stderr: (no log yet)"
    exit 0
fi

# ---------- Install ----------
echo "Installing macOS launchd scheduler for macro_2..."
echo ""

# 1. Check plist source exists
if [[ ! -f "$PLIST_SRC" ]]; then
    echo "Error: ${PLIST_SRC} not found."
    echo "Make sure you run this from the macro_2 repo directory."
    exit 1
fi

# 2. Create logs directory
mkdir -p "$LOGS_DIR"
echo "  Created logs directory: $LOGS_DIR"

# 3. Unload existing job if present
if launchctl list | grep -q "$PLIST_NAME"; then
    launchctl unload "$PLIST_DST" 2>/dev/null || true
    echo "  Unloaded existing job."
fi

# 4. Copy plist to LaunchAgents
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
echo "  Copied plist to: $PLIST_DST"

# 5. Load the job
launchctl load "$PLIST_DST"
echo "  Job loaded and active."

# 6. Verify
echo ""
if launchctl list | grep -q "$PLIST_NAME"; then
    echo "SUCCESS — Scheduler is now active."
else
    echo "WARNING — Job may not have loaded correctly. Check:"
    echo "  launchctl list | grep macro2"
    exit 1
fi

echo ""
echo "Schedule: 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8 (Mon-Sat)"
echo "Logs:     $LOGS_DIR/launchd_stdout.log"
echo "          $LOGS_DIR/launchd_stderr.log"
echo ""
echo "Commands:"
echo "  bash setup_launchd.sh --status      # Check status"
echo "  bash setup_launchd.sh --uninstall   # Remove scheduler"
echo "  launchctl start $PLIST_NAME         # Run now (for testing)"
