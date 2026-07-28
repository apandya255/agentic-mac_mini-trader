#!/usr/bin/env python3
"""
Backtest Engine — Historical P&L Simulation

Replays historical price data through the system's sizing and stop logic
to show hypothetical performance for a given ticker/hedge pair.

Simulates:
  - Entry at a specified date (or most recent)
  - Trailing stop-loss monitoring (ATR-based or fixed %)
  - Take-profit targets
  - Daily mark-to-market P&L
  - Combined pair P&L (main leg + hedge leg)

Results saved to: memos/backtest/

Usage:
    python3 backtest.py --ticker XOM --hedge RSPG --direction long --entry-date 2026-06-01
    python3 backtest.py --ticker MSFT --hedge RSPT --direction long --lookback 60
    python3 backtest.py --ticker JPM --hedge RSPF --direction long --stop 2.5 --target 5
"""

import warnings
warnings.filterwarnings('ignore')

import argparse
import json
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict

sys.path.insert(0, str(Path(__file__).parent / "src"))
from data_platform.prices import PriceService

BASE_DIR = Path(__file__).parent
BACKTEST_DIR = BASE_DIR / "memos" / "backtest"
BACKTEST_DIR.mkdir(parents=True, exist_ok=True)

price_service = PriceService()


@dataclass
class BacktestResult:
    """Results of a single backtest simulation."""
    ticker: str
    hedge_ticker: str
    direction: str
    hedge_direction: str
    entry_date: str
    exit_date: str
    exit_reason: str          # "stop_loss", "take_profit", "end_of_period"
    entry_price: float
    exit_price: float
    hedge_entry_price: float
    hedge_exit_price: float
    main_leg_pnl_pct: float
    hedge_leg_pnl_pct: float
    combined_pnl_pct: float
    max_drawdown_pct: float
    max_gain_pct: float
    days_held: int
    stop_level_pct: float
    target_level_pct: float
    daily_pnl: list           # [{date, price, hedge_price, combined_pnl}]


def get_price_history(ticker: str, start_date: str, end_date: str = None):
    """Get price history from the database."""
    import sqlite3
    import pandas as pd

    db_path = BASE_DIR / "data" / "prices.db"
    if not db_path.exists():
        return []

    with sqlite3.connect(db_path) as conn:
        query = "SELECT date, close FROM price_history WHERE ticker = ? AND date >= ?"
        params = [ticker, start_date]
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        query += " ORDER BY date ASC"

        rows = conn.execute(query, params).fetchall()
    return [(r[0], r[1]) for r in rows]


def run_backtest(
    ticker: str,
    hedge_ticker: str,
    direction: str = "long",
    hedge_direction: str = "short",
    entry_date: str = None,
    lookback_days: int = 60,
    stop_pct: float = 2.5,
    target_pct: float = 5.0,
    size_pct_nav: float = 0.04,
) -> BacktestResult:
    """
    Run a single backtest simulation.

    Args:
        ticker: Main position ticker
        hedge_ticker: Hedge instrument ticker
        direction: "long" or "short" for main leg
        hedge_direction: "long" or "short" for hedge leg
        entry_date: ISO date string for entry (defaults to lookback_days ago)
        lookback_days: If no entry_date, go back this many calendar days
        stop_pct: Stop-loss percentage (e.g., 2.5 = -2.5%)
        target_pct: Take-profit percentage (e.g., 5.0 = +5.0%)
        size_pct_nav: Position size as fraction of NAV
    """
    # Determine date range
    if entry_date:
        start = entry_date
    else:
        start = (date.today() - timedelta(days=lookback_days)).isoformat()

    end = date.today().isoformat()

    # Fetch price data
    main_prices = get_price_history(ticker, start, end)
    hedge_prices = get_price_history(hedge_ticker, start, end)

    if not main_prices or len(main_prices) < 2:
        raise ValueError(f"Insufficient price data for {ticker} from {start}")
    if not hedge_prices or len(hedge_prices) < 2:
        raise ValueError(f"Insufficient price data for {hedge_ticker} from {start}")

    # Align dates (only keep dates present in both)
    main_dict = dict(main_prices)
    hedge_dict = dict(hedge_prices)
    common_dates = sorted(set(main_dict.keys()) & set(hedge_dict.keys()))

    if len(common_dates) < 2:
        raise ValueError(f"Not enough overlapping dates for {ticker}/{hedge_ticker}")

    # Entry prices (first common date)
    entry_px = main_dict[common_dates[0]]
    hedge_entry_px = hedge_dict[common_dates[0]]
    actual_entry_date = common_dates[0]

    # Simulate day-by-day
    stop_level = -stop_pct / 100.0
    target_level = target_pct / 100.0
    daily_pnl = []
    max_combined = 0.0
    min_combined = 0.0
    exit_date = common_dates[-1]
    exit_reason = "end_of_period"
    exit_px = main_dict[common_dates[-1]]
    hedge_exit_px = hedge_dict[common_dates[-1]]

    for d in common_dates:
        px = main_dict[d]
        hpx = hedge_dict[d]

        # Main leg P&L
        if direction == "long":
            main_pnl = (px - entry_px) / entry_px
        else:
            main_pnl = (entry_px - px) / entry_px

        # Hedge leg P&L
        if hedge_direction == "short":
            hedge_pnl = (hedge_entry_px - hpx) / hedge_entry_px
        else:
            hedge_pnl = (hpx - hedge_entry_px) / hedge_entry_px

        combined = (main_pnl + hedge_pnl) / 2

        daily_pnl.append({
            "date": d,
            "price": px,
            "hedge_price": hpx,
            "main_pnl_pct": round(main_pnl, 6),
            "hedge_pnl_pct": round(hedge_pnl, 6),
            "combined_pnl_pct": round(combined, 6),
        })

        max_combined = max(max_combined, combined)
        min_combined = min(min_combined, combined)

        # Check stop
        if combined <= stop_level:
            exit_date = d
            exit_reason = "stop_loss"
            exit_px = px
            hedge_exit_px = hpx
            break

        # Check take profit
        if combined >= target_level:
            exit_date = d
            exit_reason = "take_profit"
            exit_px = px
            hedge_exit_px = hpx
            break

    # Final P&L
    if direction == "long":
        final_main_pnl = (exit_px - entry_px) / entry_px
    else:
        final_main_pnl = (entry_px - exit_px) / entry_px

    if hedge_direction == "short":
        final_hedge_pnl = (hedge_entry_px - hedge_exit_px) / hedge_entry_px
    else:
        final_hedge_pnl = (hedge_exit_px - hedge_entry_px) / hedge_entry_px

    final_combined = (final_main_pnl + final_hedge_pnl) / 2
    days_held = len([d for d in daily_pnl])

    return BacktestResult(
        ticker=ticker,
        hedge_ticker=hedge_ticker,
        direction=direction,
        hedge_direction=hedge_direction,
        entry_date=actual_entry_date,
        exit_date=exit_date,
        exit_reason=exit_reason,
        entry_price=entry_px,
        exit_price=exit_px,
        hedge_entry_price=hedge_entry_px,
        hedge_exit_price=hedge_exit_px,
        main_leg_pnl_pct=round(final_main_pnl, 6),
        hedge_leg_pnl_pct=round(final_hedge_pnl, 6),
        combined_pnl_pct=round(final_combined, 6),
        max_drawdown_pct=round(min_combined, 6),
        max_gain_pct=round(max_combined, 6),
        days_held=days_held,
        stop_level_pct=stop_level,
        target_level_pct=target_level,
        daily_pnl=daily_pnl,
    )


def print_result(result: BacktestResult) -> None:
    """Print a formatted summary of the backtest result."""
    pnl_color = "\033[92m" if result.combined_pnl_pct >= 0 else "\033[91m"
    reset = "\033[0m"

    print(f"\n  ╔══════════════════════════════════════════════╗")
    print(f"  ║  BACKTEST RESULT                             ║")
    print(f"  ╚══════════════════════════════════════════════╝")
    print(f"  Trade: {result.ticker} {result.direction.upper()} / {result.hedge_ticker} {result.hedge_direction.upper()}")
    print(f"  Period: {result.entry_date} → {result.exit_date} ({result.days_held} trading days)")
    print(f"  Exit reason: {result.exit_reason.replace('_', ' ').upper()}")
    print()
    print(f"  Entry: ${result.entry_price:.2f} / ${result.hedge_entry_price:.2f}")
    print(f"  Exit:  ${result.exit_price:.2f} / ${result.hedge_exit_price:.2f}")
    print()
    print(f"  Main leg P&L:    {result.main_leg_pnl_pct*100:+.2f}%")
    print(f"  Hedge leg P&L:   {result.hedge_leg_pnl_pct*100:+.2f}%")
    print(f"  {pnl_color}Combined P&L:    {result.combined_pnl_pct*100:+.2f}%{reset}")
    print()
    print(f"  Max gain:        {result.max_gain_pct*100:+.2f}%")
    print(f"  Max drawdown:    {result.max_drawdown_pct*100:+.2f}%")
    print(f"  Stop level:      {result.stop_level_pct*100:.1f}%")
    print(f"  Target level:    {result.target_level_pct*100:+.1f}%")
    print()

    # Win/loss verdict
    if result.exit_reason == "take_profit":
        print(f"  Verdict: ✓ WIN — hit take-profit target")
    elif result.exit_reason == "stop_loss":
        print(f"  Verdict: ✗ LOSS — stopped out")
    else:
        verdict = "WIN" if result.combined_pnl_pct > 0 else "LOSS" if result.combined_pnl_pct < 0 else "FLAT"
        print(f"  Verdict: {'✓' if result.combined_pnl_pct >= 0 else '✗'} {verdict} — period ended")

    print()


def main():
    parser = argparse.ArgumentParser(description="Backtest Engine — Historical P&L Simulation")
    parser.add_argument("--ticker", required=True, help="Main position ticker (e.g., XOM)")
    parser.add_argument("--hedge", required=True, help="Hedge ticker (e.g., RSPG)")
    parser.add_argument("--direction", default="long", choices=["long", "short"], help="Main leg direction")
    parser.add_argument("--hedge-direction", default="short", choices=["long", "short"], help="Hedge leg direction")
    parser.add_argument("--entry-date", default=None, help="Entry date (YYYY-MM-DD). Defaults to lookback.")
    parser.add_argument("--lookback", type=int, default=60, help="Lookback days from today (default: 60)")
    parser.add_argument("--stop", type=float, default=2.5, help="Stop-loss %% (default: 2.5)")
    parser.add_argument("--target", type=float, default=5.0, help="Take-profit %% (default: 5.0)")
    parser.add_argument("--size", type=float, default=0.04, help="Position size as fraction of NAV (default: 0.04)")
    args = parser.parse_args()

    print(f"\n  Running backtest: {args.ticker} {args.direction.upper()} / {args.hedge} {args.hedge_direction.upper()}")
    print(f"  Stop: -{args.stop}% | Target: +{args.target}% | Lookback: {args.lookback}d")

    try:
        result = run_backtest(
            ticker=args.ticker,
            hedge_ticker=args.hedge,
            direction=args.direction,
            hedge_direction=args.hedge_direction,
            entry_date=args.entry_date,
            lookback_days=args.lookback,
            stop_pct=args.stop,
            target_pct=args.target,
            size_pct_nav=args.size,
        )
    except ValueError as e:
        print(f"\n  Error: {e}")
        print(f"  Try running 'python3 run_cycle.py --phase 1' to refresh price data.\n")
        sys.exit(1)

    # Print results
    print_result(result)

    # Save to file
    output_file = BACKTEST_DIR / f"bt_{args.ticker}_{args.hedge}_{date.today().isoformat()}.json"
    output = asdict(result)
    output_file.write_text(json.dumps(output, indent=2))
    print(f"  Results saved to: {output_file}\n")


if __name__ == "__main__":
    main()
