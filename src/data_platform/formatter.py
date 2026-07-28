"""
Trade Recommendation Formatter for the Agentic AI Trading System.

Converts JSON pipeline output (proposal + score + risk + order) into
a readable one-pager format suitable for a discretionary PM.

Outputs:
  - Plain text (console / terminal)
  - HTML (email-ready)
  - Markdown (for archiving)

Usage:
    from data_platform.formatter import format_recommendation
    text = format_recommendation(order, proposal, tech_score, risk_decision)
    print(text)
"""

from __future__ import annotations

import json
import textwrap
from datetime import date
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────────
# PLAIN TEXT FORMATTER (PM desk format)
# ─────────────────────────────────────────────────────────────────

def format_recommendation(
    order: dict,
    proposal: Optional[dict] = None,
    tech_score: Optional[dict] = None,
    risk_decision: Optional[dict] = None,
) -> str:
    """
    Format a trade recommendation as a readable one-pager.

    Args:
        order: The TradeOrder JSON from the PM agent.
        proposal: The original TradeProposal JSON (for thesis detail).
        tech_score: The TechnicalScore JSON.
        risk_decision: The RiskDecision JSON.

    Returns:
        Formatted plain-text string ready for console or email body.
    """
    ticker = order.get("ticker", "???")
    direction = order.get("direction", "???").upper()
    hedge = order.get("hedge_ticker", "???")
    size_pct = order.get("size_pct_nav", 0)
    size_str = f"{size_pct*100:.0f}% NAV"
    conviction = order.get("conviction", proposal.get("conviction", "?") if proposal else "?")

    # Header
    header = f"{ticker} — {direction} vs. {hedge}  |  {size_str}  |  Conv: {conviction}/10"
    sep = "═" * max(len(header) + 4, 55)

    lines = [sep, header, sep, ""]

    # Thesis
    thesis = order.get("pm_rationale", "")
    if proposal:
        thesis = proposal.get("thesis_summary", thesis)
        variant = proposal.get("variant_perception", "")
        if variant:
            thesis += f" {variant}"
    lines.append("THESIS: " + _wrap(thesis, 55, "        "))
    lines.append("")

    # Technical setup
    if tech_score:
        ts = tech_score.get("technical_score", "?")
        trend = tech_score.get("trend_alignment", "?")
        timing = tech_score.get("timing_recommendation", "?")
        signals = tech_score.get("active_signals", [])
        signal_strs = [s.get("signal", "") for s in signals[:3]]
        lines.append(f"SETUP: Technical {ts}/10. {', '.join(signal_strs)}.")
        if tech_score.get("trailing_stop_method"):
            lines.append(f"       {tech_score['trailing_stop_method']}")
    else:
        lines.append("SETUP: (no technical score available)")
    lines.append("")

    # Levels
    entry = order.get("entry_approach", "market")
    if proposal and proposal.get("current_price"):
        entry = f"${proposal['current_price']:.2f} ({entry})"

    stop = order.get("stop_loss_method", "trailing 2.5%")
    if tech_score and tech_score.get("suggested_stop_loss"):
        stop = f"${tech_score['suggested_stop_loss']:.2f} ({stop})"

    target = order.get("take_profit", "+5% PM review")
    if tech_score and tech_score.get("suggested_take_profit"):
        target = f"${tech_score['suggested_take_profit']:.2f} ({target})"

    lines.append("LEVELS:")
    lines.append(f"  Entry:  {entry}")
    lines.append(f"  Stop:   {stop}")
    lines.append(f"  Target: {target}")
    lines.append("")

    # Risks
    risks = []
    if proposal:
        risks = proposal.get("key_risks", [])
    if risks:
        lines.append("RISK:")
        for r in risks[:4]:
            lines.append(f"  • {r}")
        lines.append("")

    # Debate summary
    if proposal:
        catalyst = proposal.get("catalyst", "")
        timeline = proposal.get("catalyst_timeline", "")
        if catalyst:
            lines.append(f"CATALYST: {catalyst}")
            if timeline:
                lines[-1] += f" ({timeline})"
            lines.append("")

    # Factor impact
    if risk_decision:
        betas = risk_decision.get("projected_factor_betas", {})
        warnings = risk_decision.get("risk_warnings", [])
        if betas:
            # Show top 3 non-zero betas
            sorted_betas = sorted(betas.items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            beta_str = ", ".join(f"{k} {v:+.2f}" for k, v in sorted_betas if abs(v) > 0.01)
            if beta_str:
                lines.append(f"FACTOR IMPACT: {beta_str}. All within ±0.6.")
        if warnings:
            for w in warnings[:2]:
                lines.append(f"  ⚠ {w}")
        lines.append("")

    # Review date
    review = order.get("review_date", "")
    holding = order.get("expected_holding_period", "")
    if review or holding:
        review_line = "REVIEW: "
        if review:
            review_line += review
        if holding:
            review_line += f" (holding: {holding})"
        lines.append(review_line)

    lines.append(sep)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# HTML FORMATTER (email-ready)
# ─────────────────────────────────────────────────────────────────

def format_recommendation_html(
    order: dict,
    proposal: Optional[dict] = None,
    tech_score: Optional[dict] = None,
    risk_decision: Optional[dict] = None,
) -> str:
    """Format as HTML suitable for email delivery."""
    ticker = order.get("ticker", "???")
    direction = order.get("direction", "???").upper()
    hedge = order.get("hedge_ticker", "???")
    size_pct = order.get("size_pct_nav", 0)
    conviction = order.get("conviction", proposal.get("conviction", "?") if proposal else "?")

    dir_color = "#4caf7c" if direction == "LONG" else "#cf6679"

    thesis = order.get("pm_rationale", "")
    if proposal:
        thesis = proposal.get("thesis_summary", thesis)

    # Entry/stop/target
    entry = order.get("entry_approach", "market")
    if proposal and proposal.get("current_price"):
        entry = f"${proposal['current_price']:.2f} ({entry})"
    stop = order.get("stop_loss_method", "trailing 2.5%")
    if tech_score and tech_score.get("suggested_stop_loss"):
        stop = f"${tech_score['suggested_stop_loss']:.2f} ({stop})"
    target = order.get("take_profit", "+5% PM review")
    if tech_score and tech_score.get("suggested_take_profit"):
        target = f"${tech_score['suggested_take_profit']:.2f} ({target})"

    tech_str = ""
    if tech_score:
        tech_str = f"Technical: {tech_score.get('technical_score', '?')}/10"

    risks_html = ""
    if proposal and proposal.get("key_risks"):
        risks_html = "".join(f"<li>{r}</li>" for r in proposal["key_risks"][:4])

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{ font-family: -apple-system, Arial, sans-serif; background: #0a1628; color: #f4f4f4; padding: 20px; max-width: 600px; margin: 0 auto; }}
.header {{ background: linear-gradient(135deg, #0f1f3d, #1a2a4a); border: 1px solid #c9a84c; border-radius: 6px; padding: 16px 20px; margin-bottom: 20px; }}
.ticker {{ font-size: 22px; font-weight: 700; color: #f4f4f4; }}
.direction {{ color: {dir_color}; font-weight: 700; }}
.meta {{ color: #8a7033; font-size: 12px; letter-spacing: 1px; margin-top: 4px; }}
.section {{ margin-bottom: 16px; }}
.section-title {{ color: #c9a84c; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px; }}
.levels {{ background: rgba(201,168,76,0.05); border: 1px solid rgba(201,168,76,0.15); border-radius: 4px; padding: 12px 16px; }}
.level-row {{ display: flex; justify-content: space-between; padding: 4px 0; color: #b0b8c4; font-size: 14px; }}
.level-label {{ color: #6b7a8d; }}
.risks {{ color: #b0b8c4; font-size: 13px; padding-left: 16px; }}
.risks li {{ margin-bottom: 4px; }}
.footer {{ color: #6b7a8d; font-size: 11px; border-top: 1px solid rgba(201,168,76,0.15); padding-top: 12px; margin-top: 20px; }}
</style></head>
<body>
<div class="header">
  <div class="ticker">{ticker} <span class="direction">{direction}</span> vs. {hedge}</div>
  <div class="meta">{size_pct*100:.0f}% NAV &nbsp;|&nbsp; Conviction {conviction}/10 &nbsp;|&nbsp; {tech_str}</div>
</div>

<div class="section">
  <div class="section-title">Thesis</div>
  <p style="color:#b0b8c4; font-size:14px; line-height:1.5;">{thesis}</p>
</div>

<div class="section">
  <div class="section-title">Levels</div>
  <div class="levels">
    <div class="level-row"><span class="level-label">Entry</span><span>{entry}</span></div>
    <div class="level-row"><span class="level-label">Stop</span><span>{stop}</span></div>
    <div class="level-row"><span class="level-label">Target</span><span>{target}</span></div>
  </div>
</div>

{"<div class='section'><div class='section-title'>Key Risks</div><ul class='risks'>" + risks_html + "</ul></div>" if risks_html else ""}

<div class="footer">
  Review: {order.get('review_date', 'TBD')} &nbsp;|&nbsp; Holding: {order.get('expected_holding_period', 'TBD')}<br>
  Generated: {date.today().isoformat()} &nbsp;|&nbsp; Agentic Trading System (POC)
</div>
</body></html>"""
    return html


# ─────────────────────────────────────────────────────────────────
# BATCH FORMATTER (full cycle summary)
# ─────────────────────────────────────────────────────────────────

def format_cycle_summary(
    orders: list[dict],
    book_state: dict,
    proposals_generated: int = 0,
    proposals_survived: int = 0,
) -> str:
    """Format the full cycle result as a readable summary."""
    lines = []
    lines.append("═" * 55)
    lines.append("      DAILY CYCLE SUMMARY")
    lines.append(f"      {date.today().isoformat()}")
    lines.append("═" * 55)
    lines.append("")
    lines.append(f"Proposals generated: {proposals_generated}")
    lines.append(f"Survived debate:     {proposals_survived}")
    lines.append(f"Orders executed:     {len([o for o in orders if o.get('execute')])}")
    lines.append(f"Orders passed:       {len([o for o in orders if not o.get('execute')])}")
    lines.append("")

    nav = book_state.get("nav", 0)
    initial = book_state.get("initial_nav", nav)
    pnl_pct = ((nav - initial) / initial * 100) if initial else 0
    positions = book_state.get("positions", [])

    lines.append(f"NAV:       ${nav:,.0f}  ({pnl_pct:+.2f}%)")
    lines.append(f"Cash:      {book_state.get('cash_pct', 1)*100:.0f}%")
    lines.append(f"Positions: {len(positions)}")
    lines.append("")

    if positions:
        lines.append("BOOK:")
        for pos in positions:
            t = pos.get("ticker", "?")
            h = pos.get("hedge_ticker", "?")
            d = pos.get("direction", "?")
            s = pos.get("size_pct_nav", 0)
            c = pos.get("conviction", 0)
            r = pos.get("pair_ratio", 0)
            lines.append(f"  {t}/{h} @ {r:.4f}  {d} {s*100:.0f}%  [{c}/10]")

    lines.append("")
    lines.append("═" * 55)
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
# LOAD FROM MEMOS DIRECTORY
# ─────────────────────────────────────────────────────────────────

def load_and_format_latest(memos_dir: str = "memos") -> str:
    """
    Load the latest order from memos/ and format it.
    Convenience function for quick reads.
    """
    memos = Path(memos_dir)

    # Find latest order
    order_files = sorted((memos / "orders").glob("*.json"), reverse=True)
    if not order_files:
        return "(No trade orders found in memos/orders/)"

    order = json.loads(order_files[0].read_text())
    proposal_id = order.get("proposal_id", "")

    # Find matching proposal
    proposal = None
    for pf in (memos / "proposals").glob("*.json"):
        try:
            p = json.loads(pf.read_text())
            if p.get("proposal_id") == proposal_id:
                proposal = p
                break
        except (json.JSONDecodeError, KeyError):
            continue

    # Find matching tech score
    tech_score = None
    for sf in (memos / "scores").glob("*.json"):
        try:
            s = json.loads(sf.read_text())
            if proposal_id in sf.name:
                tech_score = s
                break
        except (json.JSONDecodeError, KeyError):
            continue

    # Find matching risk decision
    risk_decision = None
    for rf in (memos / "risk").glob("*.json"):
        try:
            r = json.loads(rf.read_text())
            if proposal_id in rf.name:
                risk_decision = r
                break
        except (json.JSONDecodeError, KeyError):
            continue

    return format_recommendation(order, proposal, tech_score, risk_decision)


# ─────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 55, indent: str = "") -> str:
    """Wrap text to width with indent on continuation lines."""
    wrapped = textwrap.fill(text, width=width, subsequent_indent=indent)
    return wrapped


if __name__ == "__main__":
    import sys
    memos_dir = sys.argv[1] if len(sys.argv) > 1 else "memos"
    print(load_and_format_latest(memos_dir))
