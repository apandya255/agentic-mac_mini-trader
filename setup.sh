#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Agentic Trading System — Setup Script
# ─────────────────────────────────────────────────────────────────────────────
# Run once on a fresh machine (Mac Mini or any macOS) to bootstrap the system.
#
# Usage:
#   chmod +x setup.sh
#   ./setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║  Agentic Trading System — Setup             ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# ── 1. Check Python version ──────────────────────────────────────────────────
echo "  [1/7] Checking Python..."
if ! command -v python3 &>/dev/null; then
    echo "  ✗ python3 not found. Install Python 3.11+ first."
    echo "    brew install python@3.11"
    exit 1
fi

PY_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  ✓ Python $PY_VERSION found"

# Check minimum version
PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 9 ]); then
    echo "  ✗ Python 3.9+ required (found $PY_VERSION)"
    exit 1
fi

# ── 2. Install Python dependencies ──────────────────────────────────────────
echo "  [2/7] Installing Python dependencies..."
pip3 install -r requirements.txt --quiet 2>/dev/null
echo "  ✓ Dependencies installed"

# ── 3. Create directory structure ────────────────────────────────────────────
echo "  [3/7] Creating directories..."
mkdir -p memos/{proposals,debate,scores,risk,orders,state,logs,backtest}
mkdir -p data
echo "  ✓ Memo and data directories created"

# ── 4. Initialize book state ────────────────────────────────────────────────
echo "  [4/7] Initializing book state..."
if [ ! -f memos/state/book.json ]; then
    cat > memos/state/book.json << 'EOF'
{
  "nav": 10000000,
  "initial_nav": 10000000,
  "cash_pct": 1.0,
  "positions": [],
  "trade_journal": []
}
EOF
    echo "  ✓ book.json initialized ($10M NAV)"
else
    echo "  ✓ book.json already exists (preserving)"
fi

# ── 5. Check .env ───────────────────────────────────────────────────────────
echo "  [5/7] Checking environment..."
if [ ! -f .env ]; then
    cp .env.template .env
    echo "  ⚠ Created .env from template — EDIT IT with your API keys:"
    echo "    nano .env"
    echo ""
    ENV_NEEDS_EDIT=true
else
    echo "  ✓ .env exists"
    ENV_NEEDS_EDIT=false
fi

# ── 6. Seed price data ──────────────────────────────────────────────────────
echo "  [6/7] Seeding price database..."
if [ ! -f data/prices.db ] || [ "$(stat -f%z data/prices.db 2>/dev/null || echo 0)" -lt 1000 ]; then
    cd src
    python3 -m data_platform.cli prices update --tickers \
        XOM CVX COP EOG SLB MPC PSX VLO OXY DVN \
        XLE RSPG RSP USO XOP GLD ACWI \
        AAPL MSFT NVDA AVGO CRM ADBE ORCL AMD INTC NOW \
        XLK RSPT \
        UNH JNJ LLY ABBV MRK PFE TMO ABT AMGN ISRG \
        XLV RSPH \
        JPM BAC WFC GS MS BLK SCHW AXP V MA \
        XLF RSPF \
        EWJ DXJ EFA \
        UUP SPY IEF VIXY IWF IWD IWB IWM HYG \
        2>/dev/null || echo "  ⚠ Some tickers may have failed (this is OK for setup)"
    cd "$SCRIPT_DIR"
    echo "  ✓ Price data seeded"
else
    echo "  ✓ Price database already populated"
fi

# ── 7. Install launchd agent (auto mark-to-market) ──────────────────────────
echo "  [7/7] Installing daily mark-to-market scheduler..."
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST_FILE="$PLIST_DIR/com.agentictrading.marktomarket.plist"
mkdir -p "$PLIST_DIR"

PYTHON_PATH=$(which python3)

cat > "$PLIST_FILE" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.agentictrading.marktomarket</string>
    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_PATH}</string>
        <string>${SCRIPT_DIR}/mark_to_market.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>16</integer><key>Minute</key><integer>5</integer></dict>
    </array>
    <key>StandardOutPath</key>
    <string>${SCRIPT_DIR}/memos/logs/mtm_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>${SCRIPT_DIR}/memos/logs/mtm_stderr.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST_FILE" 2>/dev/null || true
launchctl load "$PLIST_FILE"
echo "  ✓ Mark-to-market scheduled (weekdays 4:05pm)"

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo "  ══════════════════════════════════════════════"
echo "  Setup complete!"
echo "  ══════════════════════════════════════════════"
echo ""
echo "  Quick start:"
echo "    python3 serve.py            # dashboard at http://127.0.0.1:5100/"
echo "    python3 run_cycle.py --dry-run  # test pipeline"
echo "    python3 mark_to_market.py   # mark positions"
echo "    python3 monitor.py          # check risk alerts"
echo "    python3 backtest.py --ticker XOM --hedge RSPG --direction long"
echo ""
if [ "$ENV_NEEDS_EDIT" = true ]; then
    echo "  ⚠ IMPORTANT: Edit .env with your API keys before running the pipeline."
    echo ""
fi
