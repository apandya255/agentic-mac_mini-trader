"""
Technical Indicators Module for the Agentic AI Trading System.

Computes standard technical signals from OHLCV price data. These are
consumed by the Technical Agent(s) to score trade setups and surface
purely technical opportunities.

Per spec, technical agents evaluate:
- Price momentum, moving averages, volume, option pricing
- Signals like KST
- CTA levels, supports, resistances, Fibonacci levels
- Mean reversion indicators to identify sustainable trends

This module is pure math on pandas Series/DataFrames. No opinions,
no LLM calls — just computed signals.

Usage:
    from data_platform.technicals import TechnicalAnalysis
    ta = TechnicalAnalysis(price_service)
    signals = ta.full_scan("XOM")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MovingAverages:
    """Moving average levels and crossover status."""
    sma_20: float
    sma_50: float
    sma_100: float
    sma_200: float
    ema_20: float
    ema_50: float
    price_vs_sma20: str   # "above" | "below"
    price_vs_sma50: str
    price_vs_sma200: str
    golden_cross: bool     # 50 > 200 (bullish)
    death_cross: bool      # 50 < 200 (bearish)


@dataclass(frozen=True)
class MomentumSignals:
    """RSI, MACD, KST outputs."""
    rsi_14: float
    rsi_status: str        # "overbought" | "oversold" | "neutral"
    macd_line: float
    macd_signal: float
    macd_histogram: float
    macd_crossover: str    # "bullish" | "bearish" | "none"
    kst_value: float
    kst_signal: float
    kst_crossover: str     # "bullish" | "bearish" | "none"
    adx: float
    adx_trend: str         # "strong_trend" | "weak_trend" | "no_trend"


@dataclass(frozen=True)
class VolatilitySignals:
    """Bollinger Bands, ATR."""
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width: float
    bb_position: float     # 0-1 where price sits within bands
    bb_squeeze: bool       # bandwidth at 6-month low
    atr_14: float
    atr_pct: float         # ATR as % of price


@dataclass(frozen=True)
class VolumeSignals:
    """Volume analysis."""
    obv_trend: str         # "rising" | "falling" | "flat"
    volume_vs_avg_20: float  # ratio (>1.5 = unusual)
    unusual_volume: bool
    accumulation_distribution: float


@dataclass(frozen=True)
class FibonacciLevels:
    """Fibonacci retracement/extension from recent swing."""
    swing_high: float
    swing_low: float
    retrace_236: float
    retrace_382: float
    retrace_500: float
    retrace_618: float
    extension_1272: float
    extension_1618: float


@dataclass(frozen=True)
class TechnicalSnapshot:
    """Complete technical picture for a ticker."""
    ticker: str
    moving_averages: MovingAverages
    momentum: MomentumSignals
    volatility: VolatilitySignals
    volume: VolumeSignals
    fibonacci: FibonacciLevels
    overall_score: int     # 1-10 composite
    bias: str              # "bullish" | "bearish" | "neutral"


# ---------------------------------------------------------------------------
# Computation Functions (operate on pandas Series)
# ---------------------------------------------------------------------------

def sma(series: pd.Series, period: int) -> pd.Series:
    """Simple moving average."""
    return series.rolling(window=period, min_periods=period).mean()


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD line, signal line, histogram."""
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def kst(series: pd.Series):
    """Know Sure Thing (KST) indicator."""
    roc1 = series.pct_change(10)
    roc2 = series.pct_change(15)
    roc3 = series.pct_change(20)
    roc4 = series.pct_change(30)

    smooth1 = sma(roc1, 10)
    smooth2 = sma(roc2, 10)
    smooth3 = sma(roc3, 10)
    smooth4 = sma(roc4, 15)

    kst_line = smooth1 * 1 + smooth2 * 2 + smooth3 * 3 + smooth4 * 4
    kst_signal = sma(kst_line, 9)
    return kst_line, kst_signal


def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average Directional Index (ADX)."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    plus_dm = high.diff()
    minus_dm = -low.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

    atr_val = tr.ewm(alpha=1/period, min_periods=period).mean()
    plus_di = 100 * (plus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr_val)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, min_periods=period).mean() / atr_val)

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    return dx.ewm(alpha=1/period, min_periods=period).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, min_periods=period).mean()


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    """Bollinger Bands: upper, middle, lower, bandwidth."""
    middle = sma(series, period)
    std = series.rolling(window=period, min_periods=period).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    width = (upper - lower) / middle
    return upper, middle, lower, width


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.sign(close.diff())
    return (direction * volume).cumsum()


def find_swing_high_low(high: pd.Series, low: pd.Series, lookback: int = 60):
    """Find the most recent swing high and swing low within lookback period."""
    recent_high = high.iloc[-lookback:]
    recent_low = low.iloc[-lookback:]
    return float(recent_high.max()), float(recent_low.min())


def fibonacci_retracements(swing_high: float, swing_low: float) -> FibonacciLevels:
    """Compute Fibonacci retracement and extension levels."""
    diff = swing_high - swing_low
    return FibonacciLevels(
        swing_high=swing_high,
        swing_low=swing_low,
        retrace_236=swing_high - 0.236 * diff,
        retrace_382=swing_high - 0.382 * diff,
        retrace_500=swing_high - 0.500 * diff,
        retrace_618=swing_high - 0.618 * diff,
        extension_1272=swing_high + 0.272 * diff,
        extension_1618=swing_high + 0.618 * diff,
    )


# ---------------------------------------------------------------------------
# Technical Analysis Class
# ---------------------------------------------------------------------------

class TechnicalAnalysis:
    """
    Computes full technical snapshot for a ticker.

    Requires a PriceService instance to fetch OHLCV data.
    """

    def __init__(self, price_service):
        self.price_service = price_service

    def full_scan(self, ticker: str, lookback: int = 300) -> Optional[TechnicalSnapshot]:
        """
        Run all technical computations for a ticker and return a snapshot.

        Args:
            ticker: Ticker symbol.
            lookback: Days of history to use (default 300 for 200-day MA + buffer).

        Returns:
            TechnicalSnapshot with all signals, or None if insufficient data.
        """
        df = self.price_service.get_history(ticker, lookback)
        if df.empty or len(df) < 200:
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        vol = df["volume"]
        current_price = float(close.iloc[-1])

        # Moving Averages
        ma_result = self._compute_moving_averages(close, current_price)

        # Momentum
        mom_result = self._compute_momentum(close, high, low)

        # Volatility
        vol_result = self._compute_volatility(close, high, low, current_price)

        # Volume
        vol_signals = self._compute_volume(close, vol)

        # Fibonacci
        sw_high, sw_low = find_swing_high_low(high, low, 60)
        fib = fibonacci_retracements(sw_high, sw_low)

        # Composite score
        score, bias = self._compute_score(ma_result, mom_result, vol_result, vol_signals)

        return TechnicalSnapshot(
            ticker=ticker,
            moving_averages=ma_result,
            momentum=mom_result,
            volatility=vol_result,
            volume=vol_signals,
            fibonacci=fib,
            overall_score=score,
            bias=bias,
        )

    def _compute_moving_averages(self, close: pd.Series, price: float) -> MovingAverages:
        sma20 = float(sma(close, 20).iloc[-1])
        sma50 = float(sma(close, 50).iloc[-1])
        sma100 = float(sma(close, 100).iloc[-1])
        sma200 = float(sma(close, 200).iloc[-1])
        ema20 = float(ema(close, 20).iloc[-1])
        ema50 = float(ema(close, 50).iloc[-1])

        return MovingAverages(
            sma_20=round(sma20, 2),
            sma_50=round(sma50, 2),
            sma_100=round(sma100, 2),
            sma_200=round(sma200, 2),
            ema_20=round(ema20, 2),
            ema_50=round(ema50, 2),
            price_vs_sma20="above" if price > sma20 else "below",
            price_vs_sma50="above" if price > sma50 else "below",
            price_vs_sma200="above" if price > sma200 else "below",
            golden_cross=sma50 > sma200,
            death_cross=sma50 < sma200,
        )

    def _compute_momentum(self, close: pd.Series, high: pd.Series, low: pd.Series) -> MomentumSignals:
        rsi_val = float(rsi(close, 14).iloc[-1])
        if rsi_val > 70:
            rsi_status = "overbought"
        elif rsi_val < 30:
            rsi_status = "oversold"
        else:
            rsi_status = "neutral"

        macd_l, macd_s, macd_h = macd(close)
        macd_line_val = float(macd_l.iloc[-1])
        macd_signal_val = float(macd_s.iloc[-1])
        macd_hist_val = float(macd_h.iloc[-1])

        # MACD crossover detection
        if len(macd_h) >= 2:
            if macd_h.iloc[-1] > 0 and macd_h.iloc[-2] <= 0:
                macd_cross = "bullish"
            elif macd_h.iloc[-1] < 0 and macd_h.iloc[-2] >= 0:
                macd_cross = "bearish"
            else:
                macd_cross = "none"
        else:
            macd_cross = "none"

        kst_l, kst_s = kst(close)
        kst_val = float(kst_l.iloc[-1]) if not np.isnan(kst_l.iloc[-1]) else 0.0
        kst_sig = float(kst_s.iloc[-1]) if not np.isnan(kst_s.iloc[-1]) else 0.0

        if len(kst_l) >= 2 and not np.isnan(kst_l.iloc[-2]):
            prev_diff = kst_l.iloc[-2] - kst_s.iloc[-2]
            curr_diff = kst_l.iloc[-1] - kst_s.iloc[-1]
            if curr_diff > 0 and prev_diff <= 0:
                kst_cross = "bullish"
            elif curr_diff < 0 and prev_diff >= 0:
                kst_cross = "bearish"
            else:
                kst_cross = "none"
        else:
            kst_cross = "none"

        adx_val = float(adx(high, low, close, 14).iloc[-1])
        if adx_val > 25:
            adx_trend = "strong_trend"
        elif adx_val > 15:
            adx_trend = "weak_trend"
        else:
            adx_trend = "no_trend"

        return MomentumSignals(
            rsi_14=round(rsi_val, 1),
            rsi_status=rsi_status,
            macd_line=round(macd_line_val, 4),
            macd_signal=round(macd_signal_val, 4),
            macd_histogram=round(macd_hist_val, 4),
            macd_crossover=macd_cross,
            kst_value=round(kst_val, 4),
            kst_signal=round(kst_sig, 4),
            kst_crossover=kst_cross,
            adx=round(adx_val, 1),
            adx_trend=adx_trend,
        )

    def _compute_volatility(self, close: pd.Series, high: pd.Series, low: pd.Series, price: float) -> VolatilitySignals:
        bb_u, bb_m, bb_l, bb_w = bollinger_bands(close, 20, 2.0)
        bb_upper = float(bb_u.iloc[-1])
        bb_middle = float(bb_m.iloc[-1])
        bb_lower = float(bb_l.iloc[-1])
        bb_width_val = float(bb_w.iloc[-1])

        # Position within bands (0 = at lower, 1 = at upper)
        band_range = bb_upper - bb_lower
        bb_pos = (price - bb_lower) / band_range if band_range > 0 else 0.5

        # Squeeze: current bandwidth at 6-month (126-day) low
        bb_squeeze = False
        if len(bb_w) >= 126:
            bb_squeeze = bb_width_val <= float(bb_w.iloc[-126:].min()) * 1.05

        atr_val = float(atr(high, low, close, 14).iloc[-1])
        atr_pct_val = atr_val / price if price > 0 else 0.0

        return VolatilitySignals(
            bb_upper=round(bb_upper, 2),
            bb_middle=round(bb_middle, 2),
            bb_lower=round(bb_lower, 2),
            bb_width=round(bb_width_val, 4),
            bb_position=round(bb_pos, 3),
            bb_squeeze=bb_squeeze,
            atr_14=round(atr_val, 2),
            atr_pct=round(atr_pct_val, 4),
        )

    def _compute_volume(self, close: pd.Series, volume: pd.Series) -> VolumeSignals:
        obv_series = obv(close, volume)
        obv_sma20 = sma(obv_series, 20)

        # OBV trend: compare current OBV to its 20-day MA
        if len(obv_sma20) >= 1 and not np.isnan(obv_sma20.iloc[-1]):
            if obv_series.iloc[-1] > obv_sma20.iloc[-1] * 1.02:
                obv_t = "rising"
            elif obv_series.iloc[-1] < obv_sma20.iloc[-1] * 0.98:
                obv_t = "falling"
            else:
                obv_t = "flat"
        else:
            obv_t = "flat"

        # Volume vs. 20-day average
        vol_avg_20 = float(volume.iloc[-20:].mean()) if len(volume) >= 20 else float(volume.mean())
        current_vol = float(volume.iloc[-1])
        vol_ratio = current_vol / vol_avg_20 if vol_avg_20 > 0 else 1.0

        # Accumulation/Distribution
        mfm = ((close - close.shift(1).combine_first(close)) * volume).iloc[-20:].sum()
        ad_val = float(mfm) if not np.isnan(mfm) else 0.0

        return VolumeSignals(
            obv_trend=obv_t,
            volume_vs_avg_20=round(vol_ratio, 2),
            unusual_volume=vol_ratio > 1.5,
            accumulation_distribution=round(ad_val, 0),
        )

    def _compute_score(
        self,
        ma: MovingAverages,
        mom: MomentumSignals,
        vol: VolatilitySignals,
        volume: VolumeSignals,
    ) -> tuple[int, str]:
        """
        Compute a composite technical score (1-10) and bias.
        This is a simple weighted heuristic — not a trained model.
        """
        score = 5  # start neutral

        # Trend alignment (+/- 2)
        if ma.price_vs_sma50 == "above" and ma.price_vs_sma200 == "above":
            score += 2
        elif ma.price_vs_sma50 == "below" and ma.price_vs_sma200 == "below":
            score -= 2

        # Golden/death cross (+/- 1)
        if ma.golden_cross:
            score += 1
        elif ma.death_cross:
            score -= 1

        # RSI (mean-reversion signal at extremes)
        if mom.rsi_status == "oversold":
            score += 1  # potential bounce
        elif mom.rsi_status == "overbought":
            score -= 1  # potential pullback

        # MACD crossover (+/- 1)
        if mom.macd_crossover == "bullish":
            score += 1
        elif mom.macd_crossover == "bearish":
            score -= 1

        # ADX trend strength
        if mom.adx_trend == "strong_trend" and ma.price_vs_sma50 == "above":
            score += 1
        elif mom.adx_trend == "strong_trend" and ma.price_vs_sma50 == "below":
            score -= 1

        # Volume confirmation
        if volume.unusual_volume and volume.obv_trend == "rising":
            score += 1
        elif volume.unusual_volume and volume.obv_trend == "falling":
            score -= 1

        # Clamp to 1-10
        score = max(1, min(10, score))

        # Determine bias
        if score >= 7:
            bias = "bullish"
        elif score <= 3:
            bias = "bearish"
        else:
            bias = "neutral"

        return score, bias
