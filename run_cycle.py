#!/usr/bin/env python3
"""
Agentic Trading POC — Orchestrator Script

Runs one full pipeline cycle:
  1. Data refresh (prices for POC universe)
  2. Blind first pass (fund_energy + macro_commodities generate proposals)
  3. Memo exchange debate (2-3 rounds)
  4. Conviction check (scripted, not LLM)
  5. Technical scoring (tech_equity scores survivors)
  6. Risk gate (risk_management evaluates — DIFFERENT MODEL)
  7. PM decision (portfolio_manager sizes approved trades)
  8. Update book state + print blotter

Usage:
    python run_cycle.py              # full cycle
    python run_cycle.py --phase 1    # just data refresh
    python run_cycle.py --phase 2    # just proposals
    python run_cycle.py --skip-data  # skip data refresh (use cached)
    python run_cycle.py --dry-run    # print what would run without invoking OpenClaw

Requires:
    - OpenClaw installed and configured
    - ANTHROPIC_API_KEY and OPENAI_API_KEY in environment
    - Price data backfilled (run with --phase 1 first)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"
MANDATES_DIR = PROJECT_ROOT / "openclaw" / "mandates"
MEMOS_DIR = PROJECT_ROOT / "memos"
STATE_FILE = MEMOS_DIR / "state" / "book.json"
LOG_DIR = MEMOS_DIR / "logs"

# Load .env if present
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    for line in _env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

# POC Universe tickers
POC_TICKERS = [
    # Energy
    "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "DVN",
    "XLE", "RSPG", "RSP", "USO", "XOP", "GLD", "ACWI",
    # Japan
    "EWJ", "DXJ", "EFA",
    # Factor proxies
    "UUP", "SPY", "IEF", "VIXY", "IWF", "IWD", "IWB", "IWM", "HYG",
]

# Models per agent (risk on different family)
# Using OpenRouter format: provider/model-name
# Default model for research agents; risk_management uses a different family per spec
DEFAULT_RESEARCH_MODEL = "openrouter/anthropic/claude-sonnet-4"
AGENT_MODELS = {
    "risk_management": "openrouter/openai/gpt-4o",  # DIFFERENT MODEL FAMILY per spec
    "portfolio_manager": "openrouter/anthropic/claude-sonnet-4",
    "tech_equity": "openrouter/anthropic/claude-sonnet-4",
}

# OpenRouter configuration
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def get_model_for_agent(agent_id: str) -> str:
    """Return the model to use for a given agent, falling back to default."""
    return AGENT_MODELS.get(agent_id, DEFAULT_RESEARCH_MODEL)


def discover_research_agents() -> dict:
    """
    Discover all fund_* and macro_* mandates in the mandates directory.
    Returns dict: {agent_id: mandate_path}
    """
    agents = {}
    if MANDATES_DIR.exists():
        for f in sorted(MANDATES_DIR.glob("fund_*.md")):
            agent_id = f.stem  # e.g., "fund_energy"
            agents[agent_id] = f
        for f in sorted(MANDATES_DIR.glob("macro_*.md")):
            agent_id = f.stem  # e.g., "macro_commodities"
            agents[agent_id] = f
    return agents


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H-%M-%S")


def log(msg: str, level: str = "INFO") -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{level}] {msg}")


def ensure_dirs() -> None:
    """Create memo directories if they don't exist."""
    for subdir in ["proposals", "debate", "scores", "risk", "orders", "state", "logs"]:
        (MEMOS_DIR / subdir).mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        STATE_FILE.write_text(json.dumps({
            "nav": 10_000_000,
            "initial_nav": 10_000_000,
            "cash_pct": 1.0,
            "positions": [],
            "trade_journal": [],
        }, indent=2))


def run_cli(command: str) -> dict | None:
    """Run a data_platform CLI command and return parsed JSON."""
    full_cmd = f"python3 -m data_platform.cli {command}"
    try:
        result = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True,
            cwd=str(SRC_DIR), timeout=60,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None

def invoke_agent(agent_id: str, task_prompt: str, dry_run: bool = False) -> str | None:
    """
    Invoke an OpenClaw agent session with a specific task prompt.

    The agent reads its mandate (system prompt) and the task prompt,
    uses tools (skills) to gather data, and writes output to a file.

    Returns the path to the output file, or None if dry_run.
    """
    mandate_file = MANDATES_DIR / f"{agent_id}.md"
    model = get_model_for_agent(agent_id)
    output_file = MEMOS_DIR / "raw" / f"{agent_id}_{timestamp()}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        log(f"[DRY RUN] Would invoke {agent_id} with model={model}")
        log(f"  Mandate: {mandate_file}")
        log(f"  Task: {task_prompt[:100]}...")
        return None

    # Build the OpenClaw command
    # Using `openclaw agent --local` — runs embedded agent with shell tool access
    # System prompt comes from the mandate .md, task via --message-file
    prompt_file = output_file.with_suffix(".prompt")
    prompt_content = f"""SYSTEM INSTRUCTIONS (read from {mandate_file.name}):
{mandate_file.read_text()}

---
TASK:
{task_prompt}

---
IMPORTANT: Write your JSON output to the file: {output_file}
Use the exec tool to run: cat > {output_file} << 'JSONEOF'
<your JSON here>
JSONEOF"""
    prompt_file.write_text(prompt_content)

    cmd = [
        "openclaw", "agent", "--local",
        "--model", model,
        "--session-key", f"trading-{agent_id}-{timestamp()}",
        "--message-file", str(prompt_file),
    ]

    log(f"Invoking {agent_id} (model={model})...")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            env={**os.environ, "OPENCLAW_WORKSPACE": str(SRC_DIR)},
        )
        if result.returncode == 0:
            log(f"  {agent_id} completed successfully → {output_file.name}")
            return str(output_file)
        else:
            log(f"  {agent_id} failed: {result.stderr[:200]}", "ERROR")
            return None
    except subprocess.TimeoutExpired:
        log(f"  {agent_id} timed out (120s)", "ERROR")
        return None


# ===========================================================================
# PIPELINE PHASES
# ===========================================================================

def phase_1_data_refresh() -> None:
    """Phase 1: Refresh price data for POC universe."""
    log("═══ PHASE 1: DATA REFRESH ═══")
    tickers_str = " ".join(POC_TICKERS)
    result = run_cli(f"prices update --tickers {tickers_str}")
    if result:
        log(f"  Updated {result.get('rows_inserted', 0)} rows for {result.get('tickers_requested', 0)} tickers")
    else:
        log("  Price update returned no result (may already be current)", "WARN")


def phase_2_blind_proposals(dry_run: bool = False) -> list[str]:
    """Phase 2: Blind first pass — each research agent generates proposals independently."""
    log("═══ PHASE 2: BLIND FIRST PASS (Proposals) ═══")

    # Read current book state for context
    book_state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    book_context = json.dumps(book_state, indent=2)

    # Discover all research agents dynamically
    agents = discover_research_agents()
    log(f"  Discovered {len(agents)} research agent(s): {', '.join(agents.keys())}")

    proposals = []

    for agent_id, mandate_path in agents.items():
        # Determine agent type for task framing
        is_fund = agent_id.startswith("fund_")
        is_macro = agent_id.startswith("macro_")

        # Extract sector/region name for context
        label = agent_id.replace("fund_", "").replace("macro_", "").replace("_", " ").title()

        if is_fund:
            task = f"""Run your daily screening cycle for the {label} sector.

Current book state:
{book_context}

Instructions:
1. Use your tools to check returns, valuations, technicals, and news for your coverage universe.
2. Identify the single best opportunity (long or short) you see right now.
3. If nothing is compelling (conviction < 6), output {{"no_proposal": true, "agent_id": "{agent_id}", "rationale": "why nothing looks good"}}.
4. If you have a trade idea, output your TradeProposal JSON per your mandate format.
5. Write your output to: {MEMOS_DIR}/proposals/{agent_id}_{timestamp()}.json

You are in BLIND mode — you cannot see what other agents are proposing. Form your own independent view."""

        elif is_macro:
            task = f"""Run your daily analysis cycle for {label}.

Current book state:
{book_context}

Instructions:
1. Use your tools to check relevant prices, macro indicators, yields, FX, and credit conditions.
2. Form your macro view and identify the best trade expression (ETF, commodity vehicle, or pass).
3. If nothing is compelling (conviction < 6), output {{"no_proposal": true, "agent_id": "{agent_id}", "rationale": "why nothing looks good"}}.
4. If you have a trade idea, output your MacroTradeProposal JSON per your mandate format.
5. Write your output to: {MEMOS_DIR}/proposals/{agent_id}_{timestamp()}.json

You are in BLIND mode — you cannot see what other agents are proposing. Form your own independent view."""
        else:
            continue

        out = invoke_agent(agent_id, task, dry_run)
        if out:
            proposals.append(out)

    log(f"  {len(proposals)} proposal(s) generated")
    return proposals

def phase_3_debate(proposals: list[str], dry_run: bool = False) -> list[dict]:
    """Phase 3: Memo exchange debate between fund_energy and macro_commodities."""
    log("═══ PHASE 3: DEBATE (Memo Exchange) ═══")

    # Load proposals from files
    loaded_proposals = []
    for pfile in (MEMOS_DIR / "proposals").glob("*.json"):
        try:
            data = json.loads(pfile.read_text())
            if not data.get("no_proposal"):
                loaded_proposals.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    if not loaded_proposals:
        log("  No proposals to debate. Cycle ends.")
        return []

    log(f"  {len(loaded_proposals)} proposal(s) entering debate")

    # Round 1: Each agent reads the other's proposal and responds
    for proposal in loaded_proposals:
        agent_id = proposal.get("agent_id", "unknown")

        # Determine debate opponents:
        # Fund agents get challenged by relevant macro agents and vice versa
        # Same-type agents (fund vs fund) also cross-challenge
        opponents = []
        all_agents = discover_research_agents()
        for other_id in all_agents:
            if other_id != agent_id:
                # Fund agents debate with macro agents primarily
                # But also cross-sector fund agents can challenge
                is_cross_type = (agent_id.startswith("fund_") and other_id.startswith("macro_")) or \
                                (agent_id.startswith("macro_") and other_id.startswith("fund_"))
                if is_cross_type:
                    opponents.append(other_id)

        # Limit to max 2 opponents to control costs
        opponents = opponents[:2]

        for opponent in opponents:
            debate_task = f"""You are in DEBATE mode. Read this proposal from {agent_id} and provide your challenge or support.

PROPOSAL:
{json.dumps(proposal, indent=2)}

Instructions:
1. Evaluate this proposal from your perspective (macro/fundamental).
2. Challenge with specific counter-evidence OR support with additional data.
3. Use your tools to gather data that either confirms or contradicts the thesis.
4. Output your response as JSON:
{{
  "proposal_id": "{proposal.get('proposal_id', 'unknown')}",
  "agent_id": "{opponent}",
  "round": 1,
  "stance": "support" | "challenge" | "neutral",
  "argument": "Your detailed response with specific data points",
  "revised_conviction": null  // only if you were the originator
}}
5. Write to: {MEMOS_DIR}/debate/{opponent}_re_{agent_id}_{timestamp()}.json"""

            invoke_agent(opponent, debate_task, dry_run)

    # Round 2: Originators respond to challenges
    debate_files = list((MEMOS_DIR / "debate").glob("*.json"))
    for proposal in loaded_proposals:
        agent_id = proposal.get("agent_id", "unknown")
        # Find challenges directed at this agent
        challenges = []
        for df in debate_files:
            try:
                d = json.loads(df.read_text())
                if d.get("proposal_id") == proposal.get("proposal_id") and d.get("stance") == "challenge":
                    challenges.append(d)
            except (json.JSONDecodeError, KeyError):
                continue

        if challenges:
            response_task = f"""You are responding to challenges against your proposal.

YOUR ORIGINAL PROPOSAL:
{json.dumps(proposal, indent=2)}

CHALLENGES RECEIVED:
{json.dumps(challenges, indent=2)}

Instructions:
1. Address each challenge with data/logic. Use your tools if needed.
2. Revise your conviction if the challenges have merit.
3. If conviction drops below 5, withdraw the proposal.
4. Output your response:
{{
  "proposal_id": "{proposal.get('proposal_id', 'unknown')}",
  "agent_id": "{agent_id}",
  "round": 2,
  "stance": "defend",
  "argument": "Your response to the challenges with evidence",
  "revised_conviction": 8  // your updated conviction (1-10)
}}
5. Write to: {MEMOS_DIR}/debate/{agent_id}_response_{timestamp()}.json"""

            invoke_agent(agent_id, response_task, dry_run)

    return loaded_proposals


def phase_4_conviction_check(proposals: list[dict]) -> list[dict]:
    """Phase 4: Conviction check — filter proposals below threshold."""
    log("═══ PHASE 4: CONVICTION CHECK ═══")

    # Read final convictions from debate responses
    survivors = []
    for proposal in proposals:
        pid = proposal.get("proposal_id", "")
        agent_id = proposal.get("agent_id", "")
        final_conviction = proposal.get("conviction", 0)

        # Check if there's a revised conviction in debate responses
        for df in (MEMOS_DIR / "debate").glob(f"{agent_id}_response_*.json"):
            try:
                d = json.loads(df.read_text())
                if d.get("proposal_id") == pid and d.get("revised_conviction") is not None:
                    final_conviction = d["revised_conviction"]
            except (json.JSONDecodeError, KeyError):
                continue

        if final_conviction >= 5:
            proposal["final_conviction"] = final_conviction
            survivors.append(proposal)
            priority = "HIGH" if final_conviction >= 7 else "LOW"
            log(f"  ✓ {pid}: conviction {final_conviction}/10 [{priority} priority]")
        else:
            log(f"  ✗ {pid}: conviction {final_conviction}/10 — WITHDRAWN")

    log(f"  {len(survivors)} proposal(s) survive debate")
    return survivors

def phase_5_technical_scoring(survivors: list[dict], dry_run: bool = False) -> list[dict]:
    """Phase 5: Technical agent scores surviving proposals."""
    log("═══ PHASE 5: TECHNICAL SCORING ═══")

    if not survivors:
        log("  No proposals to score.")
        return []

    for proposal in survivors:
        ticker = proposal.get("ticker", "XLE")
        pid = proposal.get("proposal_id", "unknown")
        direction = proposal.get("direction", "long")

        tech_task = f"""Score this trade proposal on technicals.

PROPOSAL:
{json.dumps(proposal, indent=2)}

Instructions:
1. Run a full technical scan on {ticker} using your tools.
2. Evaluate whether technicals SUPPORT or OPPOSE the proposed {direction} direction.
3. Score the technical setup 1-10 per your methodology.
4. Provide key levels (support, resistance, Fibonacci), entry, stop, and target.
5. Output your TechnicalScore JSON per your mandate format.
6. Write to: {MEMOS_DIR}/scores/tech_{pid}_{timestamp()}.json"""

        invoke_agent("tech_equity", tech_task, dry_run)

    return survivors


def phase_6_risk_gate(survivors: list[dict], dry_run: bool = False) -> list[dict]:
    """Phase 6: Risk agent evaluates proposals — DIFFERENT MODEL."""
    log("═══ PHASE 6: RISK GATE (Different Model) ═══")

    if not survivors:
        log("  No proposals for risk review.")
        return []

    book_state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    approved = []

    for proposal in survivors:
        pid = proposal.get("proposal_id", "unknown")
        ticker = proposal.get("ticker", "")

        # Gather tech score if available
        tech_scores = []
        for sf in (MEMOS_DIR / "scores").glob(f"tech_{pid}_*.json"):
            try:
                tech_scores.append(json.loads(sf.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue

        risk_task = f"""Evaluate this trade proposal against risk limits.

PROPOSAL:
{json.dumps(proposal, indent=2)}

TECHNICAL SCORE:
{json.dumps(tech_scores[0] if tech_scores else {}, indent=2)}

CURRENT BOOK STATE:
{json.dumps(book_state, indent=2)}

Instructions:
1. Check circuit breaker status (current NAV = {book_state.get('nav', 10000000)}).
2. Check if adding this position would breach any factor beta limits.
3. Check correlation with existing positions.
4. Verify hedge is correct (use universe hedge tool).
5. Verify sizing is within limits for this conviction level.
6. Output your RiskDecision JSON per your mandate format.
7. Write to: {MEMOS_DIR}/risk/risk_{pid}_{timestamp()}.json

You are running on a DIFFERENT MODEL than the originating agent. Be independent.
Reject ONLY with quantitative justification. If numbers pass, approve."""

        invoke_agent("risk_management", risk_task, dry_run)

    # Read risk decisions
    for proposal in survivors:
        pid = proposal.get("proposal_id", "unknown")
        for rf in (MEMOS_DIR / "risk").glob(f"risk_{pid}_*.json"):
            try:
                decision = json.loads(rf.read_text())
                if decision.get("decision") in ("approved", "approved_with_modifications"):
                    proposal["risk_decision"] = decision
                    approved.append(proposal)
                    log(f"  ✓ {pid}: APPROVED by risk")
                else:
                    log(f"  ✗ {pid}: REJECTED — {decision.get('rationale', 'unknown')}")
            except (json.JSONDecodeError, KeyError):
                # If we can't read the decision, assume approved for now (POC)
                approved.append(proposal)
                log(f"  ? {pid}: Risk decision file unreadable, passing through (POC mode)")

    log(f"  {len(approved)} proposal(s) approved by risk")
    return approved


def phase_7_pm_decision(approved: list[dict], dry_run: bool = False) -> list[dict]:
    """Phase 7: PM agent sizes and decides on approved proposals."""
    log("═══ PHASE 7: PM DECISION ═══")

    if not approved:
        log("  No approved proposals for PM review.")
        return []

    book_state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    orders = []

    for proposal in approved:
        pid = proposal.get("proposal_id", "unknown")

        # Gather all pipeline context
        tech_scores = []
        for sf in (MEMOS_DIR / "scores").glob(f"tech_{pid}_*.json"):
            try:
                tech_scores.append(json.loads(sf.read_text()))
            except (json.JSONDecodeError, KeyError):
                continue

        risk_decision = proposal.get("risk_decision", {})

        pm_task = f"""Decide whether to execute this risk-approved trade.

PROPOSAL (post-debate, conviction = {proposal.get('final_conviction', proposal.get('conviction', 0))}):
{json.dumps(proposal, indent=2)}

TECHNICAL SCORE:
{json.dumps(tech_scores[0] if tech_scores else {"technical_score": 6, "note": "no score file found"}, indent=2)}

RISK DECISION:
{json.dumps(risk_decision, indent=2)}

CURRENT BOOK STATE:
{json.dumps(book_state, indent=2)}

Instructions:
1. Decide: execute or pass?
2. If execute: size the position using your conviction-based model.
3. Set entry approach, trailing stop method, and review date.
4. Consider how this fits the overall book (portfolio construction).
5. Output your TradeOrder JSON per your mandate format.
6. Write to: {MEMOS_DIR}/orders/order_{pid}_{timestamp()}.json"""

        invoke_agent("portfolio_manager", pm_task, dry_run)

    # Read orders
    for of in (MEMOS_DIR / "orders").glob("order_*.json"):
        try:
            order = json.loads(of.read_text())
            if order.get("execute"):
                orders.append(order)
                log(f"  ✓ EXECUTE: {order.get('ticker', '?')} {order.get('direction', '?')} @ {order.get('size_pct_nav', 0)*100:.1f}% NAV")
            else:
                log(f"  ✗ PASS: {order.get('pm_rationale', 'no rationale')[:80]}")
        except (json.JSONDecodeError, KeyError):
            continue

    log(f"  {len(orders)} trade order(s) generated")
    return orders

def phase_8_update_book(orders: list[dict]) -> None:
    """Phase 8: Update book state with new orders and print blotter."""
    log("═══ PHASE 8: BOOK UPDATE & BLOTTER ═══")

    book = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {
        "nav": 10_000_000, "initial_nav": 10_000_000,
        "cash_pct": 1.0, "positions": [], "trade_journal": [],
    }

    for order in orders:
        if not order.get("execute"):
            continue

        position = {
            "ticker": order.get("ticker"),
            "direction": order.get("direction"),
            "hedge_ticker": order.get("hedge_ticker"),
            "hedge_direction": order.get("hedge_direction", "short"),
            "size_pct_nav": order.get("size_pct_nav", 0.02),
            "conviction": order.get("conviction", 7),
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "proposal_id": order.get("proposal_id"),
        }
        book["positions"].append(position)
        book["cash_pct"] -= position["size_pct_nav"] * 2  # both legs
        book["trade_journal"].append({
            "action": "open",
            "order": order,
            "timestamp": datetime.now().isoformat(),
        })

    # Write updated book
    STATE_FILE.write_text(json.dumps(book, indent=2))

    # Print blotter
    print("\n" + "═" * 60)
    print("          DAILY CYCLE COMPLETE")
    print("═" * 60)
    print(f"NAV: ${book['nav']:,.0f}")
    print(f"Cash: {book['cash_pct']*100:.1f}%")
    print(f"Positions: {len(book['positions'])}")
    print()

    if book["positions"]:
        print("BLOTTER:")
        for pos in book["positions"]:
            t = pos.get("ticker", "?")
            h = pos.get("hedge_ticker", "?")
            d = pos.get("direction", "?")
            s = pos.get("size_pct_nav", 0)
            c = pos.get("conviction", 0)
            print(f"  {t}/{h}  {d} {s*100:.1f}%  [{c}/10]  {pos.get('status', '?')}")
    else:
        print("  (no active positions)")

    if orders:
        print("\nNEW ORDERS THIS CYCLE:")
        for order in orders:
            if order.get("execute"):
                # Format as PM one-pager
                sys.path.insert(0, str(SRC_DIR))
                from data_platform.formatter import format_recommendation, format_recommendation_html
                # Load matching proposal + score + risk
                pid = order.get("proposal_id", "")
                proposal = None
                for pf in (MEMOS_DIR / "proposals").glob("*.json"):
                    try:
                        p = json.loads(pf.read_text())
                        if p.get("proposal_id") == pid:
                            proposal = p
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
                tech_score = None
                for sf in (MEMOS_DIR / "scores").glob(f"*{pid}*"):
                    try:
                        tech_score = json.loads(sf.read_text())
                        break
                    except (json.JSONDecodeError, KeyError):
                        continue
                risk_dec = None
                for rf in (MEMOS_DIR / "risk").glob(f"*{pid}*"):
                    try:
                        risk_dec = json.loads(rf.read_text())
                        break
                    except (json.JSONDecodeError, KeyError):
                        continue

                # Print plain text recommendation
                print()
                print(format_recommendation(order, proposal, tech_score, risk_dec))

                # Save HTML version
                html = format_recommendation_html(order, proposal, tech_score, risk_dec)
                html_file = MEMOS_DIR / "orders" / f"recommendation_{pid}.html"
                html_file.write_text(html)
    else:
        print("\n  (no new orders this cycle)")

    print("═" * 60 + "\n")

    # Send email report
    sys.path.insert(0, str(SRC_DIR))
    from data_platform.emailer import send_cycle_report
    from data_platform.formatter import format_recommendation_html, format_recommendation

    if orders:
        for order in orders:
            if order.get("execute"):
                pid = order.get("proposal_id", "")
                # Load matching data
                proposal = None
                for pf in (MEMOS_DIR / "proposals").glob("*.json"):
                    try:
                        p = json.loads(pf.read_text())
                        if p.get("proposal_id") == pid:
                            proposal = p
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
                tech_score = None
                for sf in (MEMOS_DIR / "scores").glob(f"*{pid}*"):
                    try:
                        tech_score = json.loads(sf.read_text())
                        break
                    except (json.JSONDecodeError, KeyError):
                        continue
                risk_dec = None
                for rf in (MEMOS_DIR / "risk").glob(f"*{pid}*"):
                    try:
                        risk_dec = json.loads(rf.read_text())
                        break
                    except (json.JSONDecodeError, KeyError):
                        continue

                html = format_recommendation_html(order, proposal, tech_score, risk_dec)
                plain = format_recommendation(order, proposal, tech_score, risk_dec)
                send_cycle_report(
                    html_body=html,
                    plain_text=plain,
                    ticker=order.get("ticker", ""),
                    direction=order.get("direction", ""),
                )
    else:
        send_cycle_report(
            html_body="<p>No trade recommendations this cycle. All positions in cash.</p>",
            plain_text="No trade recommendations this cycle. All positions in cash.",
        )

    # Write cycle log
    cycle_log = {
        "timestamp": datetime.now().isoformat(),
        "proposals_generated": len(list((MEMOS_DIR / "proposals").glob("*.json"))),
        "orders_executed": len(orders),
        "book_positions": len(book["positions"]),
        "nav": book["nav"],
    }
    log_file = LOG_DIR / f"cycle_{timestamp()}.json"
    log_file.write_text(json.dumps(cycle_log, indent=2))


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Agentic Trading POC — Run one pipeline cycle")
    parser.add_argument("--phase", type=int, help="Run only a specific phase (1-8)")
    parser.add_argument("--skip-data", action="store_true", help="Skip price data refresh")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    args = parser.parse_args()

    ensure_dirs()
    dry_run = args.dry_run

    log("╔══════════════════════════════════════════════╗")
    log("║   AGENTIC TRADING POC — PIPELINE CYCLE      ║")
    log(f"║   {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}               ║")
    log("╚══════════════════════════════════════════════╝")

    if args.phase:
        # Run only the specified phase
        if args.phase == 1:
            phase_1_data_refresh()
        elif args.phase == 2:
            phase_2_blind_proposals(dry_run)
        elif args.phase == 3:
            phase_3_debate([], dry_run)
        elif args.phase == 5:
            survivors = []  # would need to load from memos
            phase_5_technical_scoring(survivors, dry_run)
        elif args.phase == 6:
            phase_6_risk_gate([], dry_run)
        elif args.phase == 7:
            phase_7_pm_decision([], dry_run)
        elif args.phase == 8:
            phase_8_update_book([])
        return

    # Full cycle
    if not args.skip_data:
        phase_1_data_refresh()

    proposals = phase_2_blind_proposals(dry_run)
    debated = phase_3_debate(proposals, dry_run)
    survivors = phase_4_conviction_check(debated)

    if not survivors:
        log("No proposals survived debate. Cycle complete — no action.")
        phase_8_update_book([])
        return

    phase_5_technical_scoring(survivors, dry_run)
    approved = phase_6_risk_gate(survivors, dry_run)

    if not approved:
        log("No proposals approved by risk. Cycle complete — no action.")
        phase_8_update_book([])
        return

    orders = phase_7_pm_decision(approved, dry_run)
    phase_8_update_book(orders)

    log("Cycle complete.")


if __name__ == "__main__":
    main()
