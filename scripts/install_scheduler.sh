#!/bin/bash
# Install all launchd agents for the Agentic Trading system.
# Generates plist files with auto-detected paths and loads them via launchctl.
set -e

# --- Auto-detect paths ---
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_PATH="$(which python3)"
PLIST_DIR="$HOME/Library/LaunchAgents"

echo "=== Agentic Trading Scheduler Installer ==="
echo "  Project dir:  $PROJECT_DIR"
echo "  Python path:  $PYTHON_PATH"
echo "  Plist dir:    $PLIST_DIR"
echo ""

# --- Create required directories ---
mkdir -p "$PLIST_DIR"
mkdir -p "$PROJECT_DIR/memos/logs"

# --- Generate Price Poller plist (weekday 09:25 ET, Mon-Fri) ---
cat > "$PLIST_DIR/com.agentictrading.pricepoller.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.pricepoller</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/price_poller.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>25</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/poller_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/poller_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>POLL_INTERVAL_MINUTES</key>
        <string>5</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.pricepoller.plist"

# --- Generate Daily Sweep plist (weekday 06:00 ET, Mon-Fri) ---
cat > "$PLIST_DIR/com.agentictrading.dailysweep.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.dailysweep</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/daily_sweep.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>6</integer><key>Minute</key><integer>0</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/sweep_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/sweep_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.dailysweep.plist"

# --- Generate Full Desk Run plist (Saturday 10:00 ET) ---
cat > "$PLIST_DIR/com.agentictrading.fulldesk.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.fulldesk</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/full_desk_run.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>6</integer>
        <key>Hour</key><integer>10</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/fulldesk_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/fulldesk_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.fulldesk.plist"

# --- Generate Headline Scan plist (hourly; script gates on is_market_open internally) ---
cat > "$PLIST_DIR/com.agentictrading.headlinescan.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.headlinescan</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/headline_scan.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartInterval</key>
    <integer>3600</integer>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/headlinescan_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/headlinescan_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.headlinescan.plist"

# --- Generate Asia Note plist (21:45 ET, Sun-Thu) ---
cat > "$PLIST_DIR/com.agentictrading.asianote.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.asianote</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/asia_note.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>0</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>21</integer><key>Minute</key><integer>45</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/asianote_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/asianote_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.asianote.plist"

# --- Generate Morning Brief plist (05:30 ET, Mon-Fri) ---
cat > "$PLIST_DIR/com.agentictrading.morningbrief.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.morningbrief</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/morning_brief.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>5</integer><key>Minute</key><integer>30</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/morningbrief_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/morningbrief_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.morningbrief.plist"

# --- Generate Post-Close Wrap plist (16:30 ET, Mon-Fri) ---
cat > "$PLIST_DIR/com.agentictrading.postclosewrap.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.postclosewrap</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/post_close_wrap.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>30</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/postclosewrap_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/postclosewrap_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.postclosewrap.plist"

# --- Generate Coverage Digest plist (17:30 ET, Mon-Fri) ---
cat > "$PLIST_DIR/com.agentictrading.coveragedigest.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.coveragedigest</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/coverage_digest.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>17</integer><key>Minute</key><integer>30</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/coveragedigest_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/coveragedigest_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.coveragedigest.plist"

# --- Generate Week-Ahead plist (Sunday 18:00 ET) ---
cat > "$PLIST_DIR/com.agentictrading.weekahead.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.weekahead</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${PROJECT_DIR}/scripts/week_ahead.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${PROJECT_DIR}</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key><integer>0</integer>
        <key>Hour</key><integer>18</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${PROJECT_DIR}/memos/logs/weekahead_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${PROJECT_DIR}/memos/logs/weekahead_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

echo "  Generated com.agentictrading.weekahead.plist"

# --- Load all plists ---
echo ""
echo "Loading launchd agents..."

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
    launchctl unload "$PLIST_DIR/$plist.plist" 2>/dev/null || true
    launchctl load "$PLIST_DIR/$plist.plist"
    echo "  Loaded $plist"
done

echo ""
echo "All schedulers installed successfully."
echo ""
echo "Quiet_Hours note: Non-exempt scripts (headline scan, post-close wrap, coverage digest)"
echo "  check Quiet_Hours (22:00-07:00 ET) internally and skip execution during that window."
echo "  Exempt scripts (Asia note, morning brief) fire regardless of Quiet_Hours."
echo ""
echo "To verify: launchctl list | grep agentictrading"
echo "To uninstall: bash $PROJECT_DIR/scripts/uninstall_scheduler.sh"
