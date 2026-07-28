#!/usr/bin/env python3
"""
CLI Interface for the Data Platform.

Designed for OpenClaw agent invocation — all output is JSON to stdout.
Agents call this via shell commands:

    python -m data_platform.cli prices returns --ticker XOM
    python -m data_platform.cli technicals scan --ticker XOM
    python -m data_platform.cli risk factor-betas --returns-file book_returns.csv
    python -m data_platform.cli universe hedge --ticker XOM --direction long
    python -m data_platform.cli book blotter
    python -m data_platform.cli sizing compute --conviction 8
    ...

Every command outputs valid JSON to stdout. Errors output JSON with an "error" key.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

# Ensure src/ is on path
_SRC_DIR = Path(__file__).parent.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))


def json_out(data) -> None:
    """Print JSON to stdout and exit cleanly."""
    print(json.dumps(data, indent=2, default=str))
    sys.exit(0)


def json_err(msg: str) -> None:
    """Print error JSON to stdout and exit with code 1."""
    print(json.dumps({"error": msg}, indent=2))
    sys.exit(1)


# ===========================================================================
# UNIVERSE commands
# ===========================================================================

def cmd_universe(args):
    from data_platform.universe import Universe, get_hedge, SECTOR_ETFS, COUNTRY_ETFS, COMMODITY_VEHICLES, GICSSector

    if args.subcmd == "hedge":
        if not args.ticker:
            json_err("--ticker required")
        result = get_hedge(args.ticker, args.direction or "long")
        if result is None:
            json_err(f"Ticker '{args.ticker}' not found in universe")
        json_out({
            "primary_ticker": result.primary_ticker,
            "primary_direction": result.primary_direction,
            "hedge_ticker": result.hedge_ticker,
            "hedge_direction": result.hedge_direction,
        })

    elif args.subcmd == "sector":
        if not args.ticker:
            json_err("--ticker required")
        u = Universe()
        u.load()
        sector = u.get_sector(args.ticker)
        if sector is None:
            json_err(f"Ticker '{args.ticker}' not found in S&P 500")
        constituents = u.sector_constituents(sector)
        json_out({
            "ticker": args.ticker,
            "sector": sector.value,
            "sector_etf": SECTOR_ETFS[sector]["cap_weight"],
            "ew_hedge_etf": SECTOR_ETFS[sector]["equal_weight"],
            "constituent_count": len(constituents),
            "constituents": constituents,
        })

    elif args.subcmd == "list":
        u = Universe()
        u.load()
        json_out({
            "sp500_count": len(u.sp500_tickers),
            "sector_etfs": u.sector_etf_tickers,
            "ew_etfs": u.equal_weight_etf_tickers,
            "country_etfs": u.country_etf_tickers,
            "commodities": u.commodity_tickers,
            "hedges": u.hedge_tickers,
            "total_tickers": len(u.all_tickers()),
        })

    else:
        json_err(f"Unknown universe subcommand: {args.subcmd}. Use: hedge, sector, list")


# ===========================================================================
# PRICES commands
# ===========================================================================

def cmd_prices(args):
    from data_platform.prices import PriceService

    svc = PriceService()

    if args.subcmd == "update":
        tickers = args.tickers or []
        if args.full:
            from data_platform.universe import Universe
            u = Universe()
            u.load()
            tickers = u.all_tickers()
        elif not tickers:
            json_err("Provide --tickers or --full")
        count = svc.update(tickers, lookback_days=args.lookback or 400, progress=False)
        json_out({"tickers_requested": len(tickers), "rows_inserted": count, "db_size_mb": round(svc.db_size_mb, 2)})

    elif args.subcmd == "returns":
        if not args.ticker:
            json_err("--ticker required")
        result = svc.compute_returns(args.ticker)
        if not result:
            json_err(f"No data for {args.ticker}. Run 'prices update' first.")
        json_out({"ticker": args.ticker, "returns": result})

    elif args.subcmd == "pair-ratio":
        if not args.ticker or not args.hedge:
            json_err("--ticker and --hedge required")
        ratio = svc.get_pair_ratio(args.ticker, args.hedge)
        if ratio is None:
            json_err(f"Insufficient data for {args.ticker}/{args.hedge}")
        json_out({
            "long": ratio.long_ticker,
            "short": ratio.short_ticker,
            "ratio": ratio.current_ratio,
            "z_score": ratio.ratio_z_score,
            "percentile": ratio.ratio_percentile,
            "52w_high": ratio.ratio_52w_high,
            "52w_low": ratio.ratio_52w_low,
            "as_of": str(ratio.as_of_date),
        })

    elif args.subcmd == "history":
        if not args.ticker:
            json_err("--ticker required")
        df = svc.get_history(args.ticker, args.lookback or 20)
        if df.empty:
            json_err(f"No data for {args.ticker}")
        records = df.reset_index().to_dict(orient="records")
        for r in records:
            r["date"] = str(r["date"].date()) if hasattr(r["date"], "date") else str(r["date"])
        json_out({"ticker": args.ticker, "rows": len(records), "data": records})

    elif args.subcmd == "relative-strength":
        if not args.ticker:
            json_err("--ticker required")
        benchmark = args.benchmark or "SPY"
        rs = svc.relative_strength(args.ticker, benchmark, args.lookback or 63)
        if rs is None:
            json_err(f"Insufficient data for relative strength")
        json_out({"ticker": args.ticker, "benchmark": benchmark, "relative_strength": rs, "lookback_days": args.lookback or 63})

    else:
        json_err(f"Unknown prices subcommand: {args.subcmd}. Use: update, returns, pair-ratio, history, relative-strength")


# ===========================================================================
# TECHNICALS commands
# ===========================================================================

def cmd_technicals(args):
    from data_platform.prices import PriceService
    from data_platform.technicals import TechnicalAnalysis

    svc = PriceService()
    ta = TechnicalAnalysis(price_service=svc)

    if args.subcmd == "scan":
        if not args.ticker:
            json_err("--ticker required")
        snapshot = ta.full_scan(args.ticker)
        if snapshot is None:
            json_err(f"Insufficient data for {args.ticker}. Need 200+ days. Run 'prices update' first.")
        json_out({
            "ticker": snapshot.ticker,
            "overall_score": snapshot.overall_score,
            "bias": snapshot.bias,
            "moving_averages": asdict(snapshot.moving_averages),
            "momentum": asdict(snapshot.momentum),
            "volatility": asdict(snapshot.volatility),
            "volume": asdict(snapshot.volume),
            "fibonacci": asdict(snapshot.fibonacci),
        })

    else:
        json_err(f"Unknown technicals subcommand: {args.subcmd}. Use: scan")


# ===========================================================================
# VALUATIONS commands
# ===========================================================================

def cmd_valuations(args):
    from data_platform.valuations import ValuationService

    vs = ValuationService()

    if args.subcmd == "snapshot":
        if not args.ticker:
            json_err("--ticker required")
        snap = vs.get_snapshot(args.ticker)
        if snap is None:
            json_err(f"Could not fetch data for {args.ticker}")
        json_out(asdict(snap))

    elif args.subcmd == "peers":
        if not args.ticker or not args.peers:
            json_err("--ticker and --peers required")
        comp = vs.peer_comparison(args.ticker, args.peers)
        if comp is None:
            json_err(f"Insufficient peer data")
        json_out(asdict(comp))

    else:
        json_err(f"Unknown valuations subcommand: {args.subcmd}. Use: snapshot, peers")


# ===========================================================================
# MACRO commands
# ===========================================================================

def cmd_macro(args):
    from data_platform.macro_data import MacroDataService, FRED_SERIES
    import os

    fred_key = args.fred_key or os.environ.get("FRED_API_KEY")
    mds = MacroDataService(fred_api_key=fred_key)

    if args.subcmd == "refresh":
        if not fred_key:
            json_err("FRED API key required. Pass --fred-key or set FRED_API_KEY env var.")
        count = mds.refresh()
        json_out({"indicators_refreshed": count})

    elif args.subcmd == "indicator":
        if not args.name:
            json_err("--name required (e.g., US_CPI, US_10Y, VIX)")
        reading = mds.get_indicator(args.name)
        if reading is None:
            json_err(f"No data for '{args.name}'. Run 'macro refresh' first or check name.")
        json_out(asdict(reading))

    elif args.subcmd == "yield-curve":
        curve = mds.yield_curve()
        json_out(asdict(curve))

    elif args.subcmd == "inflation":
        json_out(mds.inflation_snapshot())

    elif args.subcmd == "labor":
        json_out(mds.labor_snapshot())

    elif args.subcmd == "credit":
        json_out(mds.credit_snapshot())

    elif args.subcmd == "list":
        json_out({"indicators": sorted(FRED_SERIES.keys()), "count": len(FRED_SERIES)})

    elif args.subcmd == "freshness":
        json_out(mds.data_freshness())

    else:
        json_err(f"Unknown macro subcommand: {args.subcmd}. Use: refresh, indicator, yield-curve, inflation, labor, credit, list, freshness")


# ===========================================================================
# RISK commands
# ===========================================================================

def cmd_risk(args):
    if args.subcmd == "factor-betas":
        from data_platform.factor_betas import FactorBetaCalculator, FACTOR_PROXY_TICKERS
        from data_platform.prices import PriceService
        import pandas as pd

        svc = PriceService()
        calc = FactorBetaCalculator(price_service=svc)

        if args.returns_file:
            # Read book returns from CSV
            df = pd.read_csv(args.returns_file, index_col=0, parse_dates=True)
            book_returns = df.iloc[:, 0]
        else:
            json_err("--returns-file required (CSV with date index and one return column)")

        betas = calc.compute_betas(book_returns)
        violations = calc.check_limits(betas)
        json_out({
            "betas": [asdict(b) for b in betas],
            "violations": [asdict(v) for v in violations],
            "factor_proxies": FACTOR_PROXY_TICKERS,
        })

    elif args.subcmd == "correlation":
        from data_platform.factor_betas import FactorBetaCalculator
        from data_platform.prices import PriceService

        svc = PriceService()
        calc = FactorBetaCalculator(price_service=svc)

        if not args.tickers:
            json_err("--tickers required")

        corr = calc.correlation_matrix(args.tickers, window=args.window or 60)
        if corr is None:
            json_err("Insufficient data for correlation")
        json_out({
            "tickers": args.tickers,
            "window": args.window or 60,
            "matrix": corr.to_dict(),
        })

    elif args.subcmd == "crowding":
        from data_platform.factor_betas import FactorBetaCalculator
        from data_platform.prices import PriceService

        svc = PriceService()
        calc = FactorBetaCalculator(price_service=svc)

        if not args.tickers:
            json_err("--tickers required")

        result = calc.crowding_check(args.tickers, window=args.window or 60)
        json_out(result)

    elif args.subcmd == "circuit-breaker":
        from data_platform.circuit_breaker import BookMonitor

        if not args.nav:
            json_err("--nav required (current book NAV in dollars)")

        monitor = BookMonitor(initial_nav=args.initial_nav or 650000000)
        monitor.update_nav(args.nav)
        json_out(monitor.snapshot())

    elif args.subcmd == "trailing-stop":
        from data_platform.trailing_stop import TrailingStop

        if not all([args.ticker, args.direction, args.entry_price, args.current_price]):
            json_err("--ticker, --direction, --entry-price, --current-price all required")

        stop = TrailingStop(
            ticker=args.ticker,
            direction=args.direction,
            entry_price=args.entry_price,
            trail_pct=args.trail_pct or 0.025,
        )
        # If peak is provided, simulate the ratchet
        if args.peak_price:
            stop.update(args.peak_price)
        stop.update(args.current_price)
        json_out(stop.status())

    else:
        json_err(f"Unknown risk subcommand: {args.subcmd}. Use: factor-betas, correlation, crowding, circuit-breaker, trailing-stop")


# ===========================================================================
# SIZING commands
# ===========================================================================

def cmd_sizing(args):
    from data_platform.sizing import PositionSizer

    sizer = PositionSizer(nav=args.nav or 650000000)

    if args.subcmd == "compute":
        if not args.conviction:
            json_err("--conviction required (1-10)")
        result = sizer.compute_size(
            conviction=args.conviction,
            high_conviction=args.high_conviction or False,
            circuit_breaker_mult=args.cb_mult if args.cb_mult is not None else 1.0,
            ticker=args.ticker or "",
        )
        json_out(asdict(result))

    elif args.subcmd == "table":
        cb_mult = args.cb_mult if args.cb_mult is not None else 1.0
        table = sizer.sizing_table(circuit_breaker_mult=cb_mult)
        json_out({"nav": sizer.nav, "circuit_breaker_mult": cb_mult, "table": table})

    else:
        json_err(f"Unknown sizing subcommand: {args.subcmd}. Use: compute, table")


# ===========================================================================
# NEWS commands
# ===========================================================================

def cmd_news(args):
    from data_platform.news import NewsScanner
    import os

    newsapi_key = args.newsapi_key or os.environ.get("NEWSAPI_KEY")
    scanner = NewsScanner(newsapi_key=newsapi_key)

    if args.subcmd == "headlines":
        if not args.ticker:
            json_err("--ticker required")
        headlines = scanner.get_headlines(args.ticker, max_items=args.max or 10)
        json_out({"ticker": args.ticker, "count": len(headlines), "headlines": [asdict(h) for h in headlines]})

    elif args.subcmd == "earnings":
        if not args.tickers:
            json_err("--tickers required")
        events = scanner.earnings_calendar(args.tickers)
        json_out({"count": len(events), "events": [asdict(e) for e in events]})

    elif args.subcmd == "upcoming-earnings":
        if not args.tickers:
            json_err("--tickers required")
        events = scanner.upcoming_earnings(args.tickers, within_days=args.days or 14)
        json_out({"within_days": args.days or 14, "count": len(events), "events": [asdict(e) for e in events]})

    elif args.subcmd == "spike":
        if not args.ticker:
            json_err("--ticker required")
        alert = scanner.detect_news_spike(args.ticker)
        if alert is None:
            json_out({"ticker": args.ticker, "spike": False, "message": "Normal news volume"})
        else:
            json_out({"ticker": args.ticker, "spike": True, **asdict(alert)})

    elif args.subcmd == "macro-events":
        events = scanner.upcoming_macro_events(days_ahead=args.days or 7)
        json_out({"days_ahead": args.days or 7, "count": len(events), "events": [asdict(e) for e in events]})

    else:
        json_err(f"Unknown news subcommand: {args.subcmd}. Use: headlines, earnings, upcoming-earnings, spike, macro-events")


# ===========================================================================
# CARRY commands
# ===========================================================================

def cmd_carry(args):
    from data_platform.carry import CarryCalculator
    import os

    fred_key = args.fred_key or os.environ.get("FRED_API_KEY")
    calc = CarryCalculator(fred_api_key=fred_key, nav=args.nav or 650000000)

    if args.subcmd == "refresh":
        count = calc.refresh_sofr()
        json_out({"rates_stored": count, "current_sofr": calc.get_current_sofr()})

    elif args.subcmd == "cash":
        if args.cash_pct is None:
            json_err("--cash-pct required (e.g., 0.40 for 40%)")
        snap = calc.daily_cash_carry(args.cash_pct)
        json_out(asdict(snap))

    elif args.subcmd == "position-cost":
        if not args.direction or not args.notional:
            json_err("--direction and --notional required")
        cost = calc.position_carry_cost(args.direction, args.notional, ticker=args.ticker or "")
        json_out(asdict(cost))

    elif args.subcmd == "rate":
        json_out({"sofr_rate": calc.get_current_sofr(), "sofr_pct": f"{calc.get_current_sofr()*100:.2f}%"})

    else:
        json_err(f"Unknown carry subcommand: {args.subcmd}. Use: refresh, cash, position-cost, rate")


# ===========================================================================
# Argument Parser
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="data_platform.cli",
        description="Agentic Trading Data Platform — CLI for OpenClaw agent invocation. All output is JSON.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # --- Universe ---
    p_uni = subparsers.add_parser("universe", help="Universe lookups")
    p_uni.add_argument("subcmd", choices=["hedge", "sector", "list"])
    p_uni.add_argument("--ticker", type=str)
    p_uni.add_argument("--direction", type=str, default="long")

    # --- Prices ---
    p_prices = subparsers.add_parser("prices", help="Price data operations")
    p_prices.add_argument("subcmd", choices=["update", "returns", "pair-ratio", "history", "relative-strength"])
    p_prices.add_argument("--ticker", type=str)
    p_prices.add_argument("--hedge", type=str)
    p_prices.add_argument("--tickers", nargs="+")
    p_prices.add_argument("--benchmark", type=str, default="SPY")
    p_prices.add_argument("--lookback", type=int)
    p_prices.add_argument("--full", action="store_true")

    # --- Technicals ---
    p_tech = subparsers.add_parser("technicals", help="Technical analysis")
    p_tech.add_argument("subcmd", choices=["scan"])
    p_tech.add_argument("--ticker", type=str)

    # --- Valuations ---
    p_val = subparsers.add_parser("valuations", help="Fundamental valuations")
    p_val.add_argument("subcmd", choices=["snapshot", "peers"])
    p_val.add_argument("--ticker", type=str)
    p_val.add_argument("--peers", nargs="+")

    # --- Macro ---
    p_macro = subparsers.add_parser("macro", help="Macro data from FRED")
    p_macro.add_argument("subcmd", choices=["refresh", "indicator", "yield-curve", "inflation", "labor", "credit", "list", "freshness"])
    p_macro.add_argument("--name", type=str)
    p_macro.add_argument("--fred-key", type=str)

    # --- Risk ---
    p_risk = subparsers.add_parser("risk", help="Risk computations")
    p_risk.add_argument("subcmd", choices=["factor-betas", "correlation", "crowding", "circuit-breaker", "trailing-stop"])
    p_risk.add_argument("--returns-file", type=str)
    p_risk.add_argument("--tickers", nargs="+")
    p_risk.add_argument("--window", type=int)
    p_risk.add_argument("--nav", type=float)
    p_risk.add_argument("--initial-nav", type=float)
    p_risk.add_argument("--ticker", type=str)
    p_risk.add_argument("--direction", type=str)
    p_risk.add_argument("--entry-price", type=float)
    p_risk.add_argument("--current-price", type=float)
    p_risk.add_argument("--peak-price", type=float)
    p_risk.add_argument("--trail-pct", type=float)

    # --- Sizing ---
    p_size = subparsers.add_parser("sizing", help="Position sizing")
    p_size.add_argument("subcmd", choices=["compute", "table"])
    p_size.add_argument("--conviction", type=int)
    p_size.add_argument("--high-conviction", action="store_true")
    p_size.add_argument("--cb-mult", type=float)
    p_size.add_argument("--nav", type=float)
    p_size.add_argument("--ticker", type=str)

    # --- News ---
    p_news = subparsers.add_parser("news", help="News and events")
    p_news.add_argument("subcmd", choices=["headlines", "earnings", "upcoming-earnings", "spike", "macro-events"])
    p_news.add_argument("--ticker", type=str)
    p_news.add_argument("--tickers", nargs="+")
    p_news.add_argument("--days", type=int)
    p_news.add_argument("--max", type=int)
    p_news.add_argument("--newsapi-key", type=str)

    # --- Carry ---
    p_carry = subparsers.add_parser("carry", help="SOFR / carry computations")
    p_carry.add_argument("subcmd", choices=["refresh", "cash", "position-cost", "rate"])
    p_carry.add_argument("--cash-pct", type=float)
    p_carry.add_argument("--direction", type=str)
    p_carry.add_argument("--notional", type=float)
    p_carry.add_argument("--ticker", type=str)
    p_carry.add_argument("--fred-key", type=str)
    p_carry.add_argument("--nav", type=float)

    return parser


# ===========================================================================
# Main
# ===========================================================================

def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # Print available commands as JSON
        json_out({
            "usage": "python -m data_platform.cli <command> <subcommand> [options]",
            "commands": {
                "universe": ["hedge", "sector", "list"],
                "prices": ["update", "returns", "pair-ratio", "history", "relative-strength"],
                "technicals": ["scan"],
                "valuations": ["snapshot", "peers"],
                "macro": ["refresh", "indicator", "yield-curve", "inflation", "labor", "credit", "list", "freshness"],
                "risk": ["factor-betas", "correlation", "crowding", "circuit-breaker", "trailing-stop"],
                "sizing": ["compute", "table"],
                "news": ["headlines", "earnings", "upcoming-earnings", "spike", "macro-events"],
                "carry": ["refresh", "cash", "position-cost", "rate"],
            },
            "note": "All output is JSON. Pipe to jq for pretty-printing.",
        })
        return

    dispatch = {
        "universe": cmd_universe,
        "prices": cmd_prices,
        "technicals": cmd_technicals,
        "valuations": cmd_valuations,
        "macro": cmd_macro,
        "risk": cmd_risk,
        "sizing": cmd_sizing,
        "news": cmd_news,
        "carry": cmd_carry,
    }

    handler = dispatch.get(args.command)
    if handler:
        try:
            handler(args)
        except SystemExit:
            raise
        except Exception as e:
            json_err(f"Execution error: {str(e)}")
    else:
        json_err(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
