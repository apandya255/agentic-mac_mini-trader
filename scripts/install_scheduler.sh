#!/bin/bash
# install_scheduler.sh — Install/update all launchd plists for the Agentic Trading platform
# Requirements: 4.1, 4.2
#
# Installs 10 plists from the project's plists/ directory:
#   1. com.agentic-trader.setenv         — Set PATH/HOME for launchd environment on login
#   2. com.agentic-trader.pipeline-0940  — Pipeline at 09:40 ET Mon-Fri
#   3. com.agentic-trader.pipeline-1130  — Pipeline at 11:30 ET Mon-Fri
#   4. com.agentic-trader.pipeline-1330  — Pipeline at 13:30 ET Mon-Fri
#   5. com.agentic-trader.pipeline-1530  — Pipeline at 15:30 ET Mon-Fri
#   6. com.agentic-trader.monitor        — Monitor with KeepAlive + ThrottleInterval=300
#   7. com.agentic-trader.session-reset  — Session reset at 09:30 ET weekdays
#   8. com.agentic-trader.price-poller   — Continuous price poller during market hours (KeepAlive)
#   9. com.agentic-trader.cloudflared    — Cloudflare tunnel (KeepAlive)
#  10. com.agentic-trader.serve          — Flask web server (KeepAlive)

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_DIR="${PROJECT_DIR}/plists"
LAUNCH_AGENTS_DIR="${HOME}/Library/LaunchAgents"

# The 10 plists to install (setenv first to ensure PATH is set before others)
PLISTS=(
    "com.agentic-trader.setenv"
    "com.agentic-trader.pipeline-0940"
    "com.agentic-trader.pipeline-1130"
    "com.agentic-trader.pipeline-1330"
    "com.agentic-trader.pipeline-1530"
    "com.agentic-trader.monitor"
    "com.agentic-trader.session-reset"
    "com.agentic-trader.price-poller"
    "com.agentic-trader.cloudflared"
    "com.agentic-trader.serve"
)

echo "=== Agentic Trading Scheduler Installer ==="
echo "  Project dir:       $PROJECT_DIR"
echo "  Source plists:     $PLIST_DIR"
echo "  LaunchAgents dir:  $LAUNCH_AGENTS_DIR"
echo ""

# --- Pre-flight checks ---
if [ ! -d "$PLIST_DIR" ]; then
    echo "ERROR: Source plist directory not found: $PLIST_DIR" >&2
    exit 1
fi

# Ensure target directories exist
mkdir -p "$LAUNCH_AGENTS_DIR"
mkdir -p "$PROJECT_DIR/memos/logs"

# --- Track results ---
LOADED=0
FAILED=0
FAILED_LABELS=()

echo "Installing ${#PLISTS[@]} launchd plists..."
echo ""

for label in "${PLISTS[@]}"; do
    plist_file="${label}.plist"
    source_path="${PLIST_DIR}/${plist_file}"
    target_path="${LAUNCH_AGENTS_DIR}/${plist_file}"

    echo -n "  ${label}: "

    # Check source exists
    if [ ! -f "$source_path" ]; then
        echo "FAILED (source not found: ${source_path})"
        FAILED=$((FAILED + 1))
        FAILED_LABELS+=("$label")
        continue
    fi

    # Unload existing version (if loaded) — suppress errors
    launchctl unload "$target_path" 2>/dev/null || true

    # Copy plist to LaunchAgents directory
    cp "$source_path" "$target_path"

    # Load the plist
    if launchctl load "$target_path" 2>&1; then
        echo "loaded successfully"
        LOADED=$((LOADED + 1))
    else
        load_error=$?
        echo "FAILED (launchctl load exit code: ${load_error})" >&2
        FAILED=$((FAILED + 1))
        FAILED_LABELS+=("$label")
    fi
done

echo ""
echo "--- Results ---"
echo "  Loaded:  ${LOADED}/${#PLISTS[@]}"
echo "  Failed:  ${FAILED}/${#PLISTS[@]}"

if [ ${FAILED} -gt 0 ]; then
    echo ""
    echo "Failed plists:" >&2
    for failed_label in "${FAILED_LABELS[@]}"; do
        echo "  - ${failed_label}" >&2
    done
    echo ""
    echo "To verify: launchctl list | grep agentic-trader"
    echo "To uninstall: bash ${PROJECT_DIR}/scripts/uninstall_scheduler.sh"
    exit 1
fi

echo ""
echo "All ${#PLISTS[@]} plists installed and loaded successfully."
echo ""
echo "Schedule summary:"
echo "  Env setup:       PATH and HOME set for launchd (RunAtLoad)"
echo "  Pipeline cycles: 09:40, 11:30, 13:30, 15:30 ET (Mon-Fri)"
echo "  Monitor:         every 300s (KeepAlive + ThrottleInterval)"
echo "  Session reset:   09:30 ET (Mon-Fri)"
echo "  Price poller:    continuous during market hours (KeepAlive + caffeinate)"
echo "  Cloudflared:     Cloudflare tunnel (KeepAlive)"
echo "  Serve:           Flask web server (KeepAlive)"
echo ""
echo "To verify: launchctl list | grep agentic-trader"
echo "To uninstall: bash ${PROJECT_DIR}/scripts/uninstall_scheduler.sh"
