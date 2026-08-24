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
import time
import traceback
from datetime import datetime
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent
SRC_DIR = PROJECT_ROOT / "src"
MANDATES_DIR = PROJECT_ROOT / "openclaw" / "mandates"
MEMOS_DIR = PROJECT_ROOT / "memos"
STATE_FILE = MEMOS_DIR / "state" / "book.json"
LOG_DIR = MEMOS_DIR / "logs"

# Load secrets from ~/.openclaw/.env per TOOLS.md security model
sys.path.insert(0, str(PROJECT_ROOT))
from src.data_platform.env_loader import load_secrets
load_secrets()

# Structured cycle logging
from src.data_platform.cycle_logger import log_cycle_start, log_phase_complete, log_cycle_complete


def atomic_write_book(book_path: Path, data: dict) -> None:
    """Write book.json atomically: write to .tmp, then os.replace.

    This ensures book.json always contains either the complete previous state
    or the complete new state — never a partial write.

    Requirements: 6.2
    """
    tmp_path = book_path.with_suffix('.tmp')
    tmp_path.write_text(json.dumps(data, indent=2))
    os.replace(str(tmp_path), str(book_path))


# POC Universe tickers
POC_TICKERS = [
    # ── Energy ──
    "XOM", "CVX", "COP", "EOG", "SLB", "MPC", "PSX", "VLO", "OXY", "DVN",
    "XLE", "RSPG",
    # ── Information Technology ──
    "AAPL", "MSFT", "NVDA", "AVGO", "CRM", "ADBE", "ORCL", "AMD", "INTC", "NOW",
    "XLK", "RSPT",
    # ── Healthcare ──
    "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "AMGN", "ISRG",
    "XLV", "RSPH",
    # ── Financials ──
    "JPM", "BAC", "WFC", "GS", "MS", "BLK", "SCHW", "AXP", "V", "MA",
    "XLF", "RSPF",
    # ── Materials ──
    "LIN", "SHW", "APD", "ECL", "FCX", "NEM", "NUE", "DOW", "DD", "CTVA",
    "XLB",
    # ── Industrials ──
    "CAT", "HON", "UNP", "RTX", "GE", "DE", "LMT", "WM", "ETN", "ITW",
    "XLI", "RSPI",
    # ── Consumer Discretionary ──
    "AMZN", "TSLA", "HD", "MCD", "NKE", "LOW", "SBUX", "TJX", "BKNG", "CMG",
    "XLY", "RSPD",
    # ── Consumer Staples ──
    "PG", "KO", "PEP", "COST", "WMT", "PM", "MO", "MDLZ", "CL", "KHC",
    "XLP", "RSPS",
    # ── Communication Services ──
    "META", "GOOG", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS", "CHTR", "EA",
    "XLC", "RSPC",
    # ── Utilities ──
    "NEE", "SO", "DUK", "SRE", "AEP", "D", "XEL", "EXC", "WEC", "ED",
    "XLU", "RSPU",
    # ── Real Estate ──
    "PLD", "AMT", "EQIX", "SPG", "O", "PSA", "WELL", "DLR", "AVB", "EXR",
    "XLRE", "RSPR",
    # ── Macro: Commodities ──
    "USO", "XOP", "GLD",
    # ── Macro: Asia/Japan ──
    "EWJ", "DXJ", "EWY", "EWT", "FXI", "INDA",
    # ── Macro: North America ──
    "EWC",
    # ── Macro: Western Europe ──
    "EWG", "EWU", "EWQ", "EWI", "EWP", "EWL", "EWD", "EWN",
    # ── Macro: LatAm ──
    "EWZ", "EWW",
    # ── Macro: CEEMEA / Broad EM ──
    "EEM",
    # ── Benchmarks & Factors ──
    "SPY", "RSP", "ACWI", "EFA",
    "IWF", "IWD", "IWB", "IWM",
    # ── Rates, Vol, Credit ──
    "UUP", "IEF", "VIXY", "HYG",
]

# Models per agent — using OpenClaw-approved models from ~/.openclaw/openclaw.json
#
# IMPORTANT: OpenClaw enforces a model allowlist. Only these are permitted:
#   - openrouter/moonshotai/kimi-k3
#   - openrouter/anthropic/claude-haiku-4.5
# Any other model slug is rejected silently by openclaw agent --model.
#
# Strategy: Kimi K3 for research/debate (strong reasoning, tool use, JSON compliance).
# Claude Haiku 4.5 for risk gate (different family per cross-family rule).
#
# Cross-family rule (per AGENTS.md): risk gate runs on a DIFFERENT model family
# than the originating research agents. Research = Moonshot, Risk = Anthropic.
DEFAULT_RESEARCH_MODEL = "openrouter/moonshotai/kimi-k3"
AGENT_MODELS = {
    "risk_management": "openrouter/anthropic/claude-haiku-4.5",  # DIFFERENT FAMILY (Anthropic)
    "portfolio_manager": "openrouter/moonshotai/kimi-k3",
    "tech_equity": "openrouter/moonshotai/kimi-k3",
}

# OpenRouter configuration (routed through OpenClaw — see src/data_platform/llm.py)


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
        atomic_write_book(STATE_FILE, {
            "nav": 10_000_000,
            "initial_nav": 10_000_000,
            "cash_pct": 1.0,
            "positions": [],
            "trade_journal": [],
        })


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
    uses tools (skills) to gather data, and returns structured output.

    Returns the parsed JSON dict from the agent's response, or None on failure.
    Also writes the output to memos/raw/ for audit.
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

    # Build the prompt: mandate as system context + task
    prompt_file = output_file.with_suffix(".prompt")
    prompt_content = f"""SYSTEM INSTRUCTIONS (read from {mandate_file.name}):
{mandate_file.read_text()}

---
TASK:
{task_prompt}

---
IMPORTANT: Respond with ONLY valid JSON. No markdown, no explanation, no code fences. Just the raw JSON object."""
    prompt_file.write_text(prompt_content)

    cmd = [
        "openclaw", "agent", "--local",
        "--model", model,
        "--session-key", f"trading-{agent_id}-{timestamp()}",
        "--message-file", str(prompt_file),
        "--json",
    ]

    log(f"Invoking {agent_id} (model={model})...")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=180,
            env={**os.environ, "OPENCLAW_WORKSPACE": str(SRC_DIR)},
        )
        if result.returncode != 0:
            log(f"  {agent_id} failed: {result.stderr[:200]}", "ERROR")
            return None

        # Parse the OpenClaw JSON wrapper to get the agent's response text
        response_text = ""
        try:
            # OpenClaw may print debug lines before JSON — find the JSON start
            stdout = result.stdout
            json_start = stdout.find("{")
            if json_start < 0:
                log(f"  {agent_id} returned no JSON in output", "ERROR")
                return None
            stdout = stdout[json_start:]
            
            oc_response = json.loads(stdout)
            
            # Path 1: payloads[].text (primary)
            if "payloads" in oc_response:
                payloads = oc_response["payloads"]
                texts = [p.get("text", "") for p in payloads if p.get("text")]
                if texts:
                    response_text = "\n".join(texts)
            
            # Path 2: meta.finalAssistantVisibleText (fallback)
            if not response_text:
                meta = oc_response.get("meta", {})
                response_text = meta.get("finalAssistantVisibleText", "") or meta.get("finalAssistantRawText", "")
            
            # Path 3: nested under result (older format)
            if not response_text and "result" in oc_response:
                r = oc_response["result"]
                if "payloads" in r:
                    texts = [p.get("text", "") for p in r["payloads"] if p.get("text")]
                    if texts:
                        response_text = "\n".join(texts)
                if not response_text:
                    response_text = r.get("finalAssistantVisibleText", "") or r.get("finalAssistantRawText", "")

        except json.JSONDecodeError:
            # If JSON parsing fails entirely, try to extract text from raw output
            response_text = result.stdout

        if not response_text:
            log(f"  {agent_id} returned empty response", "ERROR")
            return None

        # Extract JSON from the response (handle markdown code fences)
        json_text = response_text.strip()
        if json_text.startswith("```"):
            # Strip markdown code fences
            lines = json_text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            json_text = "\n".join(lines)
        
        # Try to find JSON object in the text
        start = json_text.find("{")
        end = json_text.rfind("}") + 1
        if start >= 0 and end > start:
            json_text = json_text[start:end]

        try:
            parsed = json.loads(json_text)
            # Write to raw for audit
            output_file.write_text(json.dumps(parsed, indent=2))
            log(f"  {agent_id} completed → {output_file.name}")
            return parsed
        except json.JSONDecodeError:
            # Save raw text for debugging
            output_file.with_suffix(".txt").write_text(response_text)
            log(f"  {agent_id} response was not valid JSON, saved as .txt", "WARN")
            return None

    except subprocess.TimeoutExpired:
        log(f"  {agent_id} timed out (180s)", "ERROR")
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


def phase_2_blind_proposals(dry_run: bool = False, agent_filter: list[str] | None = None) -> list[str]:
    """Phase 2: Blind first pass — each research agent generates proposals independently.

    Args:
        dry_run: If True, print commands without executing.
        agent_filter: Optional list of agent IDs to run. If None or empty, all agents run.
    """
    log("═══ PHASE 2: BLIND FIRST PASS (Proposals) ═══")

    # Read current book state for context
    book_state = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    book_context = json.dumps(book_state, indent=2)

    # Discover all research agents dynamically
    agents = discover_research_agents()

    # Apply agent filter if provided
    if agent_filter:
        agents = {k: v for k, v in agents.items() if k in agent_filter}
        log(f"  Agent filter active: running {len(agents)} of {len(discover_research_agents())} agent(s)")

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
2. Identify the single best PAIR TRADE opportunity you see right now.
3. ALL trades must be expressed as a RATIO: single name vs equal-weight sector ETF.
   - Long trades: long NAME / short sector ETF (e.g. long XOM / short RSPG)
   - Short trades: short NAME / long sector ETF (e.g. short NKE / long RSPD)
4. Your thesis, entry, stop, and target must be based on the PAIR RATIO (name_price / hedge_price), NOT individual legs.
5. Include in your JSON:
   - "entry_ratio": current name_price / hedge_price
   - "target_ratio": where you expect the ratio to move
   - "stop_ratio": where the ratio invalidates the thesis
   - "ratio_percentile": where the current ratio sits vs 52-week range (0-100)
6. If nothing is compelling (conviction < 6), output {{"no_proposal": true, "agent_id": "{agent_id}", "rationale": "why nothing looks good"}}.
7. If you have a trade idea, output your TradeProposal JSON per your mandate format with the ratio fields above.

You are in BLIND mode — you cannot see what other agents are proposing. Form your own independent view."""

        elif is_macro:
            task = f"""Run your daily analysis cycle for {label}.

Current book state:
{book_context}

Instructions:
1. Use your tools to check relevant prices, macro indicators, yields, FX, and credit conditions.
2. Form your macro view and identify the best PAIR TRADE expression.
3. ALL trades must be expressed as a RATIO: region/factor ETF vs broad benchmark.
   - Long trades: long region ETF / short benchmark (e.g. long EWG / short EFA)
   - Short trades: short region ETF / long benchmark (e.g. short EWZ / long EEM)
4. Your thesis, entry, stop, and target must be based on the PAIR RATIO (etf_price / hedge_price), NOT individual legs.
5. Include in your JSON:
   - "entry_ratio": current etf_price / hedge_price
   - "target_ratio": where you expect the ratio to move
   - "stop_ratio": where the ratio invalidates the thesis
   - "ratio_percentile": where the current ratio sits vs 52-week range (0-100)
6. If nothing is compelling (conviction < 6), output {{"no_proposal": true, "agent_id": "{agent_id}", "rationale": "why nothing looks good"}}.
7. If you have a trade idea, output your MacroTradeProposal JSON per your mandate format with the ratio fields above.

You are in BLIND mode — you cannot see what other agents are proposing. Form your own independent view."""
        else:
            continue

        out = invoke_agent(agent_id, task, dry_run)
        if out and isinstance(out, dict):
            # Add metadata if missing
            if "proposal_id" not in out:
                out["proposal_id"] = f"{agent_id}_{timestamp()}"
            if "agent_id" not in out:
                out["agent_id"] = agent_id
            # Write to proposals dir
            proposal_path = MEMOS_DIR / "proposals" / f"{agent_id}_{timestamp()}.json"
            proposal_path.write_text(json.dumps(out, indent=2))
            proposals.append(out)
            log(f"  → Proposal: {out.get('ticker', '?')} {out.get('direction', '?')} conv={out.get('conviction', '?')}")

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
}}"""

            debate_result = invoke_agent(opponent, debate_task, dry_run)
            if debate_result and isinstance(debate_result, dict):
                debate_result.setdefault("proposal_id", proposal.get("proposal_id", "unknown"))
                debate_result.setdefault("agent_id", opponent)
                debate_result.setdefault("round", 1)
                debate_path = MEMOS_DIR / "debate" / f"{opponent}_re_{agent_id}_{timestamp()}.json"
                debate_path.write_text(json.dumps(debate_result, indent=2))
                log(f"    {opponent} → {debate_result.get('stance', '?')}")

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
}}"""

            response_result = invoke_agent(agent_id, response_task, dry_run)
            if response_result and isinstance(response_result, dict):
                response_result.setdefault("proposal_id", proposal.get("proposal_id", "unknown"))
                response_result.setdefault("agent_id", agent_id)
                response_result.setdefault("round", 2)
                response_path = MEMOS_DIR / "debate" / f"{agent_id}_response_{timestamp()}.json"
                response_path.write_text(json.dumps(response_result, indent=2))
                # Update proposal conviction if revised
                if response_result.get("revised_conviction") is not None:
                    proposal["conviction"] = response_result["revised_conviction"]
                log(f"    {agent_id} defends → conv={response_result.get('revised_conviction', '?')}")

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
1. Evaluate whether technicals SUPPORT or OPPOSE the proposed {direction} direction for {ticker}.
2. Score the technical setup 1-10.
3. Provide key levels (support, resistance), suggested entry, stop, and target.
4. Respond with a JSON object containing:
   - "proposal_id": "{pid}"
   - "agent_id": "tech_equity"
   - "technical_score": number 1-10
   - "trend_alignment": "aligned"/"opposed"/"neutral"
   - "momentum_regime": string
   - "suggested_entry": number
   - "suggested_stop_loss": number
   - "suggested_take_profit": number
   - "trailing_stop_method": string
   - "timing_recommendation": "now"/"wait"/"avoid"
   - "timing_rationale": string"""

        tech_result = invoke_agent("tech_equity", tech_task, dry_run)
        if tech_result and isinstance(tech_result, dict):
            tech_result.setdefault("proposal_id", pid)
            score_path = MEMOS_DIR / "scores" / f"tech_{pid}_{timestamp()}.json"
            score_path.write_text(json.dumps(tech_result, indent=2))
            proposal["_tech_score"] = tech_result
            log(f"  {ticker}: score {tech_result.get('technical_score', '?')}/10")

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
1. Check if adding this position would breach factor beta or concentration limits.
2. Verify hedge is appropriate for the direction.
3. Verify sizing is within limits for this conviction level.
4. Respond with a JSON object containing:
   - "proposal_id": "{pid}"
   - "decision": "approved" or "rejected"
   - "rationale": one sentence
   - "position_size_ok": true/false
   - "hedge_present_and_valid": true/false
   - "sector_concentration_ok": true/false
   - "risk_warnings": list of strings (or empty list)

You are running on a DIFFERENT MODEL than the originating agent. Be independent.
Reject ONLY with quantitative justification. If numbers pass, approve."""

        risk_result = invoke_agent("risk_management", risk_task, dry_run)

        if risk_result and isinstance(risk_result, dict):
            risk_result.setdefault("proposal_id", pid)
            risk_path = MEMOS_DIR / "risk" / f"risk_{pid}_{timestamp()}.json"
            risk_path.write_text(json.dumps(risk_result, indent=2))

            if risk_result.get("decision") in ("approved", "approved_with_modifications"):
                proposal["risk_decision"] = risk_result
                approved.append(proposal)
                log(f"  ✓ {pid}: APPROVED by risk")
            else:
                log(f"  ✗ {pid}: REJECTED — {risk_result.get('rationale', 'unknown')[:80]}")
        else:
            # If risk agent fails, auto-approve (fail-open for POC)
            log(f"  ⚠ {pid}: Risk agent returned no valid response — auto-approving")
            proposal["risk_decision"] = {"decision": "approved", "rationale": "risk agent unavailable — auto-approved"}
            approved.append(proposal)

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
2. If execute: size the position (1-5% NAV based on conviction).
3. Set trailing stop method and review date.
4. Respond with a JSON object containing these fields:
   - "execute": true/false
   - "ticker": the ticker
   - "direction": "long" or "short"
   - "hedge_ticker": the hedge ETF
   - "hedge_direction": "short" or "long"
   - "size_pct_nav": decimal (e.g. 0.03 for 3%)
   - "conviction": number
   - "stop_loss_method": string
   - "take_profit": string
   - "pm_rationale": one-sentence reason
   - "portfolio_thesis": the thesis summary
   - "expected_holding_period": string
   - "review_date": ISO date string"""

        pm_result = invoke_agent("portfolio_manager", pm_task, dry_run)

        if pm_result and isinstance(pm_result, dict):
            if pm_result.get("execute"):
                # Ensure required fields
                pm_result["proposal_id"] = pid
                pm_result["order_id"] = f"order_{pid}_{timestamp()}"
                pm_result.setdefault("ticker", proposal.get("ticker", ""))
                pm_result.setdefault("direction", proposal.get("direction", "long"))
                pm_result.setdefault("hedge_ticker", proposal.get("hedge_ticker", ""))
                pm_result.setdefault("hedge_direction", proposal.get("hedge_direction", "short"))
                pm_result.setdefault("size_pct_nav", 0.03)
                pm_result.setdefault("conviction", proposal.get("conviction", 7))
                pm_result.setdefault("stop_loss_method", "trailing 2.5% from peak")
                pm_result.setdefault("take_profit", "5% triggers review")
                pm_result.setdefault("pm_rationale", "PM approved")

                # Write order file
                order_path = MEMOS_DIR / "orders" / f"{pm_result['order_id']}.json"
                order_path.write_text(json.dumps(pm_result, indent=2))
                orders.append(pm_result)
                log(f"  ✓ EXECUTE: {pm_result.get('ticker', '?')} {pm_result.get('direction', '?')} @ {pm_result.get('size_pct_nav', 0)*100:.1f}% NAV")
            else:
                log(f"  ✗ PASS: {pm_result.get('pm_rationale', 'no rationale')[:80]}")
        else:
            # If PM agent failed to return valid JSON, auto-approve with defaults from proposal
            log(f"  PM response invalid for {pid}, auto-creating order from proposal")
            auto_order = {
                "execute": True,
                "order_id": f"order_{pid}_{timestamp()}",
                "proposal_id": pid,
                "ticker": proposal.get("ticker", ""),
                "direction": proposal.get("direction", "long"),
                "hedge_ticker": proposal.get("hedge_ticker", ""),
                "hedge_direction": proposal.get("hedge_direction", "short"),
                "size_pct_nav": min(proposal.get("conviction", 7) * 0.005, 0.04),
                "conviction": proposal.get("conviction", 7),
                "stop_loss_method": "trailing 2.5% from peak",
                "take_profit": "5% triggers review",
                "pm_rationale": proposal.get("thesis_summary", "Auto-approved from proposal"),
                "portfolio_thesis": proposal.get("thesis_detail", proposal.get("thesis_summary", "")),
            }
            order_path = MEMOS_DIR / "orders" / f"{auto_order['order_id']}.json"
            order_path.write_text(json.dumps(auto_order, indent=2))
            orders.append(auto_order)
            log(f"  ✓ AUTO-EXECUTE: {auto_order['ticker']} {auto_order['direction']} @ {auto_order['size_pct_nav']*100:.1f}% NAV")

    log(f"  {len(orders)} trade order(s) generated")
    return orders

def phase_8_update_book(orders: list[dict]) -> None:
    """Phase 8: Autonomous auto-booking.

    For each order that clears all gates:
      1. Validate gates (conviction ≥ 5, risk approved, PM execute)
      2. Check circuit breaker (intraday drawdown ≤ -2%)
      3. Compute slippage-adjusted entry price
      4. Add position to book
      5. Reduce cash by 2x size (both legs)
      6. Log full provenance to trade journal
    """
    from src.trading.slippage import compute_fill_price
    from src.trading.gate_validator import validate_gates
    from src.trading.circuit_breaker import is_circuit_breaker_active

    log("═══ PHASE 8: AUTONOMOUS AUTO-BOOKING ═══")

    if not orders:
        log("  No orders generated this cycle.")
        print("\n" + "═" * 60)
        print("          CYCLE COMPLETE — NO NEW ORDERS")
        print("═" * 60)
        _write_cycle_log(orders)
        return

    # Load book state
    book = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {
        "nav": 10_000_000,
        "initial_nav": 10_000_000,
        "cash_pct": 1.0,
        "positions": [],
        "trade_journal": [],
    }
    session_open_nav = book.get("session_open_nav", book.get("nav", 0))

    # Check circuit breaker state
    cb_state = is_circuit_breaker_active(book["nav"], session_open_nav)
    if cb_state.active:
        log(f"  ⚠ Circuit breaker ACTIVE (drawdown: {cb_state.current_drawdown*100:.2f}%)")
        # Send Telegram alert for circuit breaker activation (Requirements 13.1, 13.4)
        try:
            from src.telegram_bot import send_message as _cb_send
            _cb_send(
                f"Circuit breaker ACTIVE — drawdown {cb_state.current_drawdown*100:.2f}% from session open. "
                f"New trade entries blocked.",
                severity="critical",
            )
        except Exception:
            pass

    # Initialize price service for fetching last observed prices
    sys.path.insert(0, str(SRC_DIR))
    from data_platform.prices import PriceService
    price_service = PriceService()

    booked_count = 0
    rejected_count = 0
    held_count = 0

    for order in orders:
        proposal_id = order.get("proposal_id", "unknown")

        # 1. Gate validation
        gate_result = validate_gates(
            conviction=order.get("conviction", 0),
            risk_decision=order.get("risk_decision", {}).get("decision", "")
                if isinstance(order.get("risk_decision"), dict)
                else str(order.get("risk_decision", "")),
            pm_execute=order.get("execute", False),
        )

        if not gate_result.passed:
            # Log rejection with specific failing gate
            book.setdefault("trade_journal", []).append({
                "action": "auto_rejected",
                "proposal_id": proposal_id,
                "failing_gate": gate_result.failing_gate,
                "timestamp": datetime.now().isoformat(),
            })
            rejected_count += 1
            log(f"  ✗ REJECTED {proposal_id}: gate={gate_result.failing_gate}")
            continue

        # 2. Circuit breaker check
        if cb_state.active:
            order["status"] = "circuit_breaker_held"
            # Persist held order
            held_path = (MEMOS_DIR / "orders" / f"{order.get('order_id', proposal_id)}_held.json")
            held_path.write_text(json.dumps(order, indent=2))
            book.setdefault("trade_journal", []).append({
                "action": "circuit_breaker_held",
                "proposal_id": proposal_id,
                "drawdown": cb_state.current_drawdown,
                "timestamp": datetime.now().isoformat(),
            })
            held_count += 1
            log(f"  ⊘ HELD {proposal_id}: circuit breaker active (drawdown {cb_state.current_drawdown*100:.2f}%)")
            continue

        # 3. Compute slippage-adjusted fill prices
        ticker = order.get("ticker", "")
        hedge_ticker = order.get("hedge_ticker", "")
        direction = order.get("direction", "long")
        hedge_direction = order.get("hedge_direction", "short")

        last_price = price_service.get_latest_close(ticker)
        hedge_last_price = price_service.get_latest_close(hedge_ticker) if hedge_ticker else None

        if last_price is None:
            log(f"  ⚠ Skipping {proposal_id}: no price data for {ticker}", "WARN")
            book.setdefault("trade_journal", []).append({
                "action": "auto_rejected",
                "proposal_id": proposal_id,
                "failing_gate": "price_unavailable",
                "timestamp": datetime.now().isoformat(),
            })
            rejected_count += 1
            continue

        entry_price = compute_fill_price(last_price, direction, "entry")
        hedge_entry_price = (
            compute_fill_price(hedge_last_price, hedge_direction, "entry")
            if hedge_last_price is not None else None
        )

        # 4. Build position and add to book
        size_pct_nav = order.get("size_pct_nav", 0.03)
        position = {
            "ticker": ticker,
            "direction": direction,
            "hedge_ticker": hedge_ticker,
            "hedge_direction": hedge_direction,
            "size_pct_nav": size_pct_nav,
            "conviction": order.get("conviction", 7),
            "entry_price": entry_price,
            "hedge_entry_price": hedge_entry_price,
            "entry_date": datetime.now().strftime("%Y-%m-%d"),
            "status": "active",
            "trim_status": "untrimmed",
            "trail_stop_level": None,
            "thesis_status": "active",
            "stop_loss_method": order.get("stop_loss_method", "trailing 2.5% from peak"),
            "take_profit": order.get("take_profit", "5% triggers review"),
            "expected_holding_period": order.get("expected_holding_period", "60 days"),
            "proposal_id": proposal_id,
            "price_history": [],
        }

        book.setdefault("positions", []).append(position)

        # 5. Reduce cash by 2x size (both legs of pair trade)
        book["cash_pct"] = book.get("cash_pct", 1.0) - (size_pct_nav * 2)

        # 6. Log full provenance to trade journal
        book.setdefault("trade_journal", []).append({
            "action": "auto_booked",
            "proposal_id": proposal_id,
            "ticker": ticker,
            "direction": direction,
            "entry_price": entry_price,
            "hedge_entry_price": hedge_entry_price,
            "size_pct_nav": size_pct_nav,
            "conviction": order.get("conviction"),
            "debate_results": order.get("_debates"),
            "tech_score": order.get("_tech_score"),
            "risk_decision": order.get("risk_decision"),
            "pm_rationale": order.get("pm_rationale"),
            "timestamp": datetime.now().isoformat(),
        })

        booked_count += 1
        log(f"  ✓ BOOKED {ticker} {direction.upper()} vs {hedge_ticker} | "
            f"{size_pct_nav*100:.1f}% NAV | fill={entry_price:.4f}")

    # Save book atomically (write to .tmp, then rename)
    atomic_write_book(STATE_FILE, book)

    # Print summary
    print("\n" + "═" * 60)
    print("          CYCLE COMPLETE — AUTO-BOOKED")
    print("═" * 60)
    print(f"  Booked: {booked_count}  |  Rejected: {rejected_count}  |  Held: {held_count}")
    print(f"  Cash remaining: {book.get('cash_pct', 0)*100:.1f}%")
    print("═" * 60)

    _write_cycle_log(orders)


def _write_cycle_log(orders: list[dict]) -> None:
    """Write a cycle summary log entry."""
    book = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    cycle_log = {
        "timestamp": datetime.now().isoformat(),
        "proposals_generated": len(list((MEMOS_DIR / "proposals").glob("*.json"))),
        "orders_executed": len(orders),
        "book_positions": len(book.get("positions", [])),
        "nav": book.get("nav", 0),
    }
    log_file = LOG_DIR / f"cycle_{timestamp()}.json"
    log_file.write_text(json.dumps(cycle_log, indent=2))


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    from src.trading.overlap_guard import pipeline_lock
    from src.telegram_bot import send_message

    parser = argparse.ArgumentParser(description="Agentic Trading POC — Run one pipeline cycle")
    parser.add_argument("--phase", type=int, help="Run only a specific phase (1-8)")
    parser.add_argument("--skip-data", action="store_true", help="Skip price data refresh")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument("--agents", type=str, default="",
        help="Comma-separated list of agent IDs to run (e.g., fund_energy,macro_commodities)")
    args = parser.parse_args()

    ensure_dirs()
    dry_run = args.dry_run

    # Parse agent filter (comma-separated string → list, or None if empty)
    agent_filter = [a.strip() for a in args.agents.split(",") if a.strip()] or None

    # Start structured logging
    cycle_id = log_cycle_start(trigger_source="launchd")
    cycle_start_time = time.time()

    try:
        # Acquire pipeline lock to prevent concurrent executions
        with pipeline_lock():
            _run_cycle(args, dry_run, agent_filter, cycle_id)

        # Success path
        total_duration = time.time() - cycle_start_time
        # Count proposals and trades from memos
        proposals_count = len(list((MEMOS_DIR / "proposals").glob("*.json")))
        orders_count = len(list((MEMOS_DIR / "orders").glob("*.json")))
        log_cycle_complete(cycle_id, total_duration, proposals_count, orders_count, exit_code=0)
        sys.exit(0)

    except RuntimeError as e:
        if "cycle_skipped_overlap" in str(e):
            log("Pipeline cycle SKIPPED — another cycle is already running.", "WARN")
            # Log the overlap event
            overlap_log = {
                "event": "cycle_skipped_overlap",
                "timestamp": datetime.now().isoformat(),
            }
            log_file = LOG_DIR / f"overlap_{timestamp()}.json"
            log_file.parent.mkdir(parents=True, exist_ok=True)
            log_file.write_text(json.dumps(overlap_log, indent=2))
            log_phase_complete(cycle_id, "overlap_guard", 0, "skipped")
            log_cycle_complete(cycle_id, 0, 0, 0, exit_code=0)
            sys.exit(0)
        else:
            # Non-overlap RuntimeError — treat as failure
            total_duration = time.time() - cycle_start_time
            _handle_pipeline_failure(cycle_id, total_duration, "runtime_error", e, send_message)
            sys.exit(1)

    except Exception as e:
        # Top-level catch-all: log traceback, send Telegram alert, exit 1
        total_duration = time.time() - cycle_start_time
        _handle_pipeline_failure(cycle_id, total_duration, "unknown", e, send_message)
        sys.exit(1)


def _handle_pipeline_failure(
    cycle_id: str,
    total_duration: float,
    failed_phase: str,
    error: Exception,
    send_message_fn,
) -> None:
    """Handle pipeline failure: log traceback, send Telegram alert, finalize cycle log.

    Requirements: 6.1, 6.3
    """
    # Log full traceback to memos/logs/
    tb_text = traceback.format_exc()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    traceback_file = LOG_DIR / f"traceback_{timestamp()}.log"
    traceback_file.write_text(tb_text)
    log(f"Traceback saved to {traceback_file.name}", "ERROR")

    # Send Telegram failure alert
    error_msg = (
        f"Pipeline cycle {cycle_id} failed in phase '{failed_phase}': {error}\n"
        f"Duration: {total_duration:.1f}s"
    )
    try:
        send_message_fn(error_msg, severity="critical")
    except Exception as tg_err:
        log(f"Failed to send Telegram alert: {tg_err}", "ERROR")

    # Finalize cycle log with failure
    log_phase_complete(cycle_id, failed_phase, total_duration, "failure")
    log_cycle_complete(cycle_id, total_duration, 0, 0, exit_code=1)


def _run_cycle(args, dry_run: bool, agent_filter: list[str] | None, cycle_id: str) -> None:
    """Execute the pipeline cycle (called within pipeline_lock context).

    Logs each phase completion with timing via the structured cycle logger.
    """
    log("╔══════════════════════════════════════════════╗")
    log("║   AGENTIC TRADING POC — PIPELINE CYCLE      ║")
    log(f"║   {datetime.now().strftime('%Y-%m-%d %H:%M:%S ET')}               ║")
    log("╚══════════════════════════════════════════════╝")

    if args.phase:
        # Run only the specified phase
        phase_start = time.time()
        if args.phase == 1:
            phase_1_data_refresh()
            log_phase_complete(cycle_id, "data_refresh", time.time() - phase_start, "success")
        elif args.phase == 2:
            phase_2_blind_proposals(dry_run, agent_filter)
            log_phase_complete(cycle_id, "proposals", time.time() - phase_start, "success")
        elif args.phase == 3:
            phase_3_debate([], dry_run)
            log_phase_complete(cycle_id, "debate", time.time() - phase_start, "success")
        elif args.phase == 5:
            survivors = []  # would need to load from memos
            phase_5_technical_scoring(survivors, dry_run)
            log_phase_complete(cycle_id, "technical_scoring", time.time() - phase_start, "success")
        elif args.phase == 6:
            phase_6_risk_gate([], dry_run)
            log_phase_complete(cycle_id, "risk_gate", time.time() - phase_start, "success")
        elif args.phase == 7:
            phase_7_pm_decision([], dry_run)
            log_phase_complete(cycle_id, "pm_decision", time.time() - phase_start, "success")
        elif args.phase == 8:
            phase_8_update_book([])
            log_phase_complete(cycle_id, "book_update", time.time() - phase_start, "success")
        return

    # Full cycle with phase-by-phase logging
    phase_start = time.time()
    if not args.skip_data:
        phase_1_data_refresh()
        log_phase_complete(cycle_id, "data_refresh", time.time() - phase_start, "success")

    phase_start = time.time()
    proposals = phase_2_blind_proposals(dry_run, agent_filter)
    log_phase_complete(cycle_id, "proposals", time.time() - phase_start, "success")

    phase_start = time.time()
    debated = phase_3_debate(proposals, dry_run)
    log_phase_complete(cycle_id, "debate", time.time() - phase_start, "success")

    phase_start = time.time()
    survivors = phase_4_conviction_check(debated)
    log_phase_complete(cycle_id, "conviction_check", time.time() - phase_start, "success")

    if not survivors:
        log("No proposals survived debate. Cycle complete — no action.")
        phase_start = time.time()
        phase_8_update_book([])
        log_phase_complete(cycle_id, "book_update", time.time() - phase_start, "success")
        return

    phase_start = time.time()
    phase_5_technical_scoring(survivors, dry_run)
    log_phase_complete(cycle_id, "technical_scoring", time.time() - phase_start, "success")

    phase_start = time.time()
    approved = phase_6_risk_gate(survivors, dry_run)
    log_phase_complete(cycle_id, "risk_gate", time.time() - phase_start, "success")

    if not approved:
        log("No proposals approved by risk. Cycle complete — no action.")
        phase_start = time.time()
        phase_8_update_book([])
        log_phase_complete(cycle_id, "book_update", time.time() - phase_start, "success")
        return

    phase_start = time.time()
    orders = phase_7_pm_decision(approved, dry_run)
    log_phase_complete(cycle_id, "pm_decision", time.time() - phase_start, "success")

    phase_start = time.time()
    phase_8_update_book(orders)
    log_phase_complete(cycle_id, "book_update", time.time() - phase_start, "success")

    log("Cycle complete.")


if __name__ == "__main__":
    main()
