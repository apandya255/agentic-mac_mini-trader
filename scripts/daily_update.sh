#!/bin/bash
# Daily price update and mark-to-market
# Runs after market close (4:30 PM ET) to capture final EOD prices

set -e

PROJECT_DIR="/Users/akashpandya/AgenticTradingResearch"
cd "$PROJECT_DIR"

LOG_FILE="$PROJECT_DIR/logs/daily_update.log"
mkdir -p "$PROJECT_DIR/logs"

echo "=== Daily Update: $(date) ===" >> "$LOG_FILE"

# Step 1: Update price database from yfinance
echo "Updating prices..." >> "$LOG_FILE"
python3 -c "
import sys
sys.path.insert(0, 'src')
from data_platform.prices import PriceService
from data_platform.universe import Universe
svc = PriceService()
u = Universe()
inserted = svc.update(u.all_tickers(), lookback_days=5, progress=False)
print(f'Prices updated: {inserted} rows')
" >> "$LOG_FILE" 2>&1

# Step 2: Mark positions to market
echo "Marking to market..." >> "$LOG_FILE"
python3 mark_to_market.py >> "$LOG_FILE" 2>&1

# Step 2.5: Sync desk/positions.md from book.json
echo "Syncing desk files..." >> "$LOG_FILE"
python3 scripts/sync_desk.py >> "$LOG_FILE" 2>&1

# Step 3: Regenerate dashboard HTML
echo "Regenerating dashboard..." >> "$LOG_FILE"
python3 dashboard.py --no-open >> "$LOG_FILE" 2>&1

echo "=== Done: $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
