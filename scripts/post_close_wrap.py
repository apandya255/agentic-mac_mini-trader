#!/usr/bin/env python3
"""
Post-Close Wrap — runs weekday 16:30 ET via launchd.

Generates a 12-line-max end-of-day summary covering:
  - Book P&L (paper, carry-adjusted)
  - Today's entries and exits with fills
  - Movers (biggest gainers/losers in the book today)
  - Factor beta (if any exceeds |0.4|)
  - Current leverage stance

Delivery: Telegram + log for email mirror.

Graceful degradation: Without OPENROUTER_API_KEY, generates a structured
data summary (template-based) instead of LLM-generated prose.

Requirements: 8.1, 8.2, 8.3, 8.4
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path so we can import src.*
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.data_platform.book_ops import load_book
from src.data_platform.cycle_logger import log_cycle
from src.data_platform.market_calendar import ET, is_trading_day
from src.telegram_bot import send_message

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("post_close_wrap")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4")

# Email mirror log path (for downstream email integration)
EMAIL_MIRROR_DIR = PROJECT_ROOT / "memos" / "logs" / "email_mirror"


# ---------------------------------------------------------------------------
# Data Gathering
# ---------------------------------------------------------------------------


def _get_today_str() -> str:
    """Return today's date in ISO format (ET timezone)."""
    return datetime.now(ET).strftime("%Y-%m-%d")


def _compute_book_pnl(book: dict) -> dict[str, Any]:
    """Compute overall book P&L metrics.

    Returns:
        Dict with nav, initial_nav, total_pnl_pct, total_pnl_dollars.
    """
    nav = book.get("nav", 0)
    initial_nav = book.get("initial_nav", 0)

    if initial_nav > 0:
        total_pnl_pct = (nav - initial_nav) / initial_nav
        total_pnl_dollars = nav - initial_nav
    else:
        total_pnl_pct = 0.0
        total_pnl_dollars = 0.0

    return {
        "nav": nav,
        "initial_nav": initial_nav,
        "total_pnl_pct": total_pnl_pct,
        "total_pnl_dollars": total_pnl_dollars,
    }


def _get_todays_entries_exits(book: dict) -> dict[str, list[dict]]:
    """Find today's entries and exits from the trade journal.

    Returns:
        Dict with "entries" and "exits" lists.
    """
    today = _get_today_str()
    journal = book.get("trade_journal", [])

    entries: list[dict] = []
    exits: list[dict] = []

    for entry in journal:
        ts = entry.get("timestamp", "")
        if not ts.startswith(today):
            continue

        action = entry.get("action", "")
        order = entry.get("order", {})

        record = {
            "ticker": order.get("ticker", entry.get("ticker", "?")),
            "direction": order.get("direction", "?"),
            "hedge_ticker": order.get("hedge_ticker", ""),
            "size_pct_nav": order.get("size_pct_nav", 0),
            "entry_price": entry.get("entry_price", order.get("entry_price", 0)),
            "hedge_entry_price": entry.get(
                "hedge_entry_price", order.get("hedge_entry_price", 0)
            ),
        }

        if action == "open":
            entries.append(record)
        elif action in ("close", "trail_breach", "target_exit"):
            exits.append(record)

    return {"entries": entries, "exits": exits}


def _compute_movers(book: dict) -> list[dict]:
    """Find biggest movers (gainers and losers) in the book today.

    Ranks active positions by today's daily change or combined P&L change.

    Returns:
        List of position summaries sorted by absolute P&L (descending).
    """
    positions = book.get("positions", [])
    movers: list[dict] = []

    for pos in positions:
        if pos.get("status") != "active":
            continue

        ticker = pos.get("ticker", "?")
        combined_pnl = pos.get("combined_pnl_pct", 0.0)

        # Try to compute today's change from price_history
        daily_change = pos.get("daily_change_pct", 0.0)

        # If daily_change is zero, try computing from price_history
        history = pos.get("price_history", [])
        if len(history) >= 2 and daily_change == 0.0:
            today_pnl = history[-1].get("combined_pnl_pct", 0.0)
            yesterday_pnl = history[-2].get("combined_pnl_pct", 0.0)
            daily_change = today_pnl - yesterday_pnl

        movers.append(
            {
                "ticker": ticker,
                "hedge_ticker": pos.get("hedge_ticker", ""),
                "combined_pnl_pct": combined_pnl,
                "daily_change_pct": daily_change,
                "size_pct_nav": pos.get("size_pct_nav", 0),
            }
        )

    # Sort by absolute daily change (biggest movers first)
    movers.sort(key=lambda m: abs(m["daily_change_pct"]), reverse=True)
    return movers


def _compute_leverage(book: dict) -> dict[str, float]:
    """Compute current leverage stance.

    Returns:
        Dict with gross_exposure, net_exposure, cash_pct, position_count.
    """
    positions = book.get("positions", [])
    cash_pct = book.get("cash_pct", 1.0)

    gross_long = 0.0
    gross_short = 0.0
    position_count = 0

    for pos in positions:
        if pos.get("status") != "active":
            continue
        position_count += 1
        size = pos.get("size_pct_nav", 0)
        gross_long += size
        gross_short += size  # hedge leg is assumed equal weight

    gross_exposure = gross_long + gross_short
    net_exposure = gross_long - gross_short  # pairs book, net ~0

    return {
        "gross_exposure_pct": gross_exposure,
        "net_exposure_pct": net_exposure,
        "cash_pct": cash_pct,
        "position_count": position_count,
    }


def _check_factor_beta(book: dict) -> list[dict]:
    """Check if any factor beta exceeds |0.4|.

    Looks for factor_betas field in book or positions.
    Returns list of exceeded factors (if data available).
    """
    exceeded: list[dict] = []

    # Check book-level factor betas
    factor_betas = book.get("factor_betas", {})
    for factor, beta in factor_betas.items():
        if abs(beta) > 0.4:
            exceeded.append({"factor": factor, "beta": beta})

    # Check position-level factor data
    for pos in book.get("positions", []):
        if pos.get("status") != "active":
            continue
        pos_factors = pos.get("factor_betas", {})
        for factor, beta in pos_factors.items():
            if abs(beta) > 0.4:
                exceeded.append(
                    {"factor": factor, "beta": beta, "ticker": pos.get("ticker")}
                )

    return exceeded


# ---------------------------------------------------------------------------
# Wrap Generation
# ---------------------------------------------------------------------------


def _generate_template_wrap(
    book_pnl: dict,
    entries_exits: dict,
    movers: list[dict],
    leverage: dict,
    factor_alerts: list[dict],
) -> str:
    """Generate a structured template-based wrap (no LLM).

    Produces a 12-line-max summary suitable for Telegram delivery.
    """
    today = _get_today_str()
    lines: list[str] = []

    # Line 1: Header
    lines.append(f"POST-CLOSE WRAP | {today}")

    # Line 2: Book P&L
    pnl_pct = book_pnl["total_pnl_pct"] * 100
    pnl_dollars = book_pnl["total_pnl_dollars"]
    nav = book_pnl["nav"]
    sign = "+" if pnl_pct >= 0 else ""
    lines.append(f"Book: {sign}{pnl_pct:.2f}% ({sign}${pnl_dollars:,.0f}) | NAV ${nav:,.0f}")

    # Lines 3-4: Today's entries/exits
    entries = entries_exits["entries"]
    exits = entries_exits["exits"]

    if entries:
        entry_strs = [f"{e['ticker']} ({e['direction'][0].upper()})" for e in entries]
        lines.append(f"Entries: {', '.join(entry_strs)}")
    if exits:
        exit_strs = [f"{e['ticker']}" for e in exits]
        lines.append(f"Exits: {', '.join(exit_strs)}")
    if not entries and not exits:
        lines.append("No entries/exits today")

    # Lines 5-7: Movers (top 3)
    if movers:
        mover_lines: list[str] = []
        for m in movers[:3]:
            chg = m["daily_change_pct"] * 100
            total = m["combined_pnl_pct"] * 100
            sign_d = "+" if chg >= 0 else ""
            sign_t = "+" if total >= 0 else ""
            mover_lines.append(
                f"  {m['ticker']}/{m['hedge_ticker']}: "
                f"day {sign_d}{chg:.2f}% | total {sign_t}{total:.2f}%"
            )
        lines.append("Movers:")
        lines.extend(mover_lines)
    else:
        lines.append("Movers: No active positions")

    # Line 8: Factor beta alerts
    if factor_alerts:
        alerts = [f"{fa['factor']}={fa['beta']:.2f}" for fa in factor_alerts[:3]]
        lines.append(f"Factor beta >|0.4|: {', '.join(alerts)}")
    else:
        lines.append("Factor beta: within bounds")

    # Line 9: Leverage
    gross = leverage["gross_exposure_pct"] * 100
    cash = leverage["cash_pct"] * 100
    n_pos = leverage["position_count"]
    lines.append(f"Leverage: {gross:.0f}% gross | {cash:.0f}% cash | {n_pos} positions")

    # Trim to 12 lines max
    return "\n".join(lines[:12])


def _generate_llm_wrap(
    book_pnl: dict,
    entries_exits: dict,
    movers: list[dict],
    leverage: dict,
    factor_alerts: list[dict],
) -> str:
    """Generate wrap using OpenRouter/OpenClaw LLM.

    Constructs a prompt with the data and requests a 12-line-max summary.
    Falls back to template if LLM call fails.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    today = _get_today_str()

    # Build context for the LLM
    data_context = {
        "date": today,
        "book_pnl": book_pnl,
        "entries_today": entries_exits["entries"],
        "exits_today": entries_exits["exits"],
        "movers": movers[:5],
        "leverage": leverage,
        "factor_beta_alerts": factor_alerts,
    }

    prompt = f"""Generate a post-close trading wrap for {today}. 
STRICT RULES:
- Maximum 12 lines
- Include: book P&L, today's entries/exits, movers, factor beta status, leverage
- Use concise financial shorthand
- No headers or bullet points — flowing telegraphic style
- Include actual numbers (never round away precision on fills or P&L)

DATA:
{json.dumps(data_context, indent=2, default=str)}

Generate the 12-line-max wrap now:"""

    payload = json.dumps(
        {
            "model": OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a portfolio manager's desk assistant. "
                    "Generate concise, number-dense trading wraps. "
                    "Never exceed the line limit. Use financial shorthand.",
                },
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 500,
            "temperature": 0.3,
        }
    ).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    }

    req = Request(OPENROUTER_API_URL, data=payload, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()

            # Enforce 12-line limit
            content_lines = content.split("\n")
            if len(content_lines) > 12:
                content = "\n".join(content_lines[:12])

            return content

    except (HTTPError, URLError, OSError, KeyError, IndexError) as e:
        logger.warning(f"LLM call failed ({e}), falling back to template wrap.")
        return _generate_template_wrap(
            book_pnl, entries_exits, movers, leverage, factor_alerts
        )


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def _deliver_wrap(wrap_text: str) -> bool:
    """Deliver wrap via Telegram and save for email mirror.

    Returns:
        True if Telegram delivery succeeded, False otherwise.
    """
    # Telegram delivery
    telegram_success = False
    try:
        telegram_success = send_message(wrap_text)
        if telegram_success:
            logger.info("Wrap delivered via Telegram.")
        else:
            logger.warning("Telegram delivery returned False.")
    except Exception as e:
        logger.error(f"Telegram delivery error: {e}")

    # Email mirror: save wrap text to a log file for downstream email integration
    try:
        EMAIL_MIRROR_DIR.mkdir(parents=True, exist_ok=True)
        today = _get_today_str()
        mirror_path = EMAIL_MIRROR_DIR / f"post_close_wrap_{today}.txt"
        mirror_path.write_text(wrap_text, encoding="utf-8")
        logger.info(f"Email mirror saved to {mirror_path}")
    except Exception as e:
        logger.warning(f"Email mirror save failed: {e}")

    return telegram_success


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Post-close wrap entry point.

    1. Check is_trading_day() — skip if not
    2. Load book.json for current P&L, positions, journal entries from today
    3. Compute movers (biggest gainers/losers in the book today)
    4. Check factor exposure data if available
    5. Construct LLM prompt to generate 12-line wrap (or template-based if no LLM)
    6. Deliver via Telegram + log for email mirror
    7. Log cycle
    """
    cycle_start = time.time()

    # Step 1: Check if today is a trading day
    today = datetime.now(ET).date()
    if not is_trading_day(today):
        logger.info("Not a trading day — skipping post-close wrap.")
        log_cycle(
            cycle_type="post_close_wrap",
            status="skipped",
            duration_seconds=time.time() - cycle_start,
            metrics={"reason": "not_trading_day"},
            trigger_source="launchd",
        )
        return

    logger.info("Generating post-close wrap...")

    # Step 2: Load book
    try:
        book = load_book()
    except Exception as e:
        logger.error(f"Failed to load book.json: {e}")
        log_cycle(
            cycle_type="post_close_wrap",
            status="failure",
            duration_seconds=time.time() - cycle_start,
            metrics={},
            error=f"book load failed: {e}",
            trigger_source="launchd",
        )
        return

    # Step 2b: Compute book P&L
    book_pnl = _compute_book_pnl(book)

    # Step 2c: Get today's entries/exits
    entries_exits = _get_todays_entries_exits(book)

    # Step 3: Compute movers
    movers = _compute_movers(book)

    # Step 4: Check factor beta
    factor_alerts = _check_factor_beta(book)

    # Step 4b: Compute leverage
    leverage = _compute_leverage(book)

    # Step 5: Generate wrap
    if OPENROUTER_API_KEY:
        logger.info("Using LLM (OpenRouter) for wrap generation.")
        wrap_text = _generate_llm_wrap(
            book_pnl, entries_exits, movers, leverage, factor_alerts
        )
    else:
        logger.info("No OPENROUTER_API_KEY — using template-based wrap.")
        wrap_text = _generate_template_wrap(
            book_pnl, entries_exits, movers, leverage, factor_alerts
        )

    logger.info(f"Wrap generated ({len(wrap_text.splitlines())} lines).")

    # Step 6: Deliver
    telegram_ok = _deliver_wrap(wrap_text)

    # Step 7: Log cycle
    duration = time.time() - cycle_start
    log_cycle(
        cycle_type="post_close_wrap",
        status="success",
        duration_seconds=duration,
        metrics={
            "lines": len(wrap_text.splitlines()),
            "telegram_delivered": telegram_ok,
            "llm_used": bool(OPENROUTER_API_KEY),
            "entries_today": len(entries_exits["entries"]),
            "exits_today": len(entries_exits["exits"]),
            "active_positions": leverage["position_count"],
        },
        trigger_source="launchd",
    )
    logger.info(f"Post-close wrap completed in {duration:.1f}s.")


if __name__ == "__main__":
    main()
