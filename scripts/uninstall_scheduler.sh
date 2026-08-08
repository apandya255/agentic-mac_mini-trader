#!/bin/bash
# Uninstall all launchd agents for the Agentic Trading system
set -e
PLIST_DIR="$HOME/Library/LaunchAgents"

ALL_PLISTS=(
    com.agentictrading.pricepoller
    com.agentictrading.dailysweep
    com.agentictrading.fulldesk
    com.agentictrading.headlinescan
    com.agentictrading.asianote
    com.agentictrading.morningbrief
    com.agentictrading.postclosewrap
    com.agentictrading.coveragedigest
    com.agentictrading.weekahead
)

for plist in "${ALL_PLISTS[@]}"; do
    if [ -f "$PLIST_DIR/$plist.plist" ]; then
        launchctl unload "$PLIST_DIR/$plist.plist" 2>/dev/null || true
        rm "$PLIST_DIR/$plist.plist"
        echo "  Removed $plist"
    fi
done

echo "All schedulers uninstalled."
