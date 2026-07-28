# OpenClaw Configuration for Agentic Trading POC

## Setup

### 1. Install OpenClaw
Follow the official install instructions for your platform.

### 2. Link Skills
Copy or symlink the skills into OpenClaw's skill directory:
```bash
# Option A: symlink (recommended for development)
ln -s $(pwd)/openclaw/skills/* ~/.openclaw/skills/

# Option B: set extra skill load directory in openclaw.json
openclaw config set skills.load.extraDirs '["./openclaw/skills"]'
```

### 3. Set Environment Variables
```bash
export ANTHROPIC_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"      # for risk agent (different model family)
export FRED_API_KEY="your-key-here"        # free at fred.stlouisfed.org
export NEWSAPI_KEY="your-key-here"         # optional, free tier
```

### 4. Initialize Data
```bash
cd src && python -m data_platform.cli prices update --tickers XOM CVX COP EOG SLB MPC PSX VLO OXY DVN XLE RSPG RSP USO XOP GLD UUP SPY IEF VIXY IWF IWD IWB IWM HYG
```

### 5. Create Memo Directories
```bash
mkdir -p memos/{proposals,debate,scores,risk,orders,state,logs}
echo '{"nav": 10000000, "initial_nav": 10000000, "cash_pct": 1.0, "positions": [], "trade_journal": []}' > memos/state/book.json
```

## Agent Invocation

Each agent is invoked via OpenClaw with its mandate as the system prompt:

```bash
# Fundamental agent — blind first pass
openclaw run --mandate openclaw/mandates/fund_energy.md \
  --workspace ./src \
  --model claude-sonnet-4-20250514

# Macro agent — blind first pass
openclaw run --mandate openclaw/mandates/macro_commodities.md \
  --workspace ./src \
  --model claude-sonnet-4-20250514

# Technical agent — scores proposals
openclaw run --mandate openclaw/mandates/tech_equity.md \
  --workspace ./src \
  --model claude-sonnet-4-20250514

# Risk agent — DIFFERENT MODEL (per spec)
openclaw run --mandate openclaw/mandates/risk_management.md \
  --workspace ./src \
  --model gpt-4o

# PM agent — final decision
openclaw run --mandate openclaw/mandates/portfolio_manager.md \
  --workspace ./src \
  --model claude-sonnet-4-20250514
```

## Skills Available to All Agents

| Skill | What It Does |
|-------|-------------|
| trading-prices | Returns, pair ratios, relative strength |
| trading-technicals | Full technical scan (MA, RSI, MACD, KST, ADX, Bollinger, Fibonacci) |
| trading-valuations | P/E, EV/EBITDA, peer comparisons |
| trading-macro | FRED indicators (oil, DXY, yields, CPI, VIX) |
| trading-risk | Circuit breaker, trailing stops, correlations |
| trading-sizing | Position sizing by conviction |
| trading-news | Headlines, earnings calendar, event detection |
| trading-universe | Hedge resolution, sector lookup |
| trading-carry | SOFR rate, cash carry, position costs |

## Orchestration

Run a full cycle:
```bash
python run_cycle.py
```

Or invoke individual pipeline stages manually for testing.
