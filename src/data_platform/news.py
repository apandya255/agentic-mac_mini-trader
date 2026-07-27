"""
News & Event Scanner for the Agentic AI Trading System.

Surfaces headlines, detects earnings releases, and flags unusual
news activity for a given ticker or sector. Used by all agents
to stay current on market-moving events.

Per spec, agents can use "news sources, chat rooms, whatever they
need to get a pulse on the market and find opportunities."

Data sources:
- yfinance: earnings calendar, major holders, news headlines
- RSS feeds: free, no API key required (optional)
- NewsAPI: requires API key (free tier: 100 requests/day)

Usage:
    from data_platform.news import NewsScanner
    scanner = NewsScanner()
    headlines = scanner.get_headlines("XOM", days=2)
    calendar = scanner.earnings_calendar(["XOM", "CVX", "COP"])
    events = scanner.upcoming_events()
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Headline:
    """A news headline with metadata."""
    title: str
    source: str
    url: str
    published: str  # ISO date string
    ticker: str
    relevance: str  # "high" | "medium" | "low"


@dataclass(frozen=True)
class EarningsEvent:
    """An upcoming or recent earnings release."""
    ticker: str
    company_name: str
    earnings_date: str
    eps_estimate: Optional[float]
    revenue_estimate: Optional[float]
    days_until: int  # negative = already reported


@dataclass(frozen=True)
class MarketEvent:
    """A scheduled market-moving event."""
    date: str
    event: str
    region: str  # "US", "EU", "Asia", "Global"
    importance: str  # "high" | "medium" | "low"


@dataclass(frozen=True)
class NewsSpikeAlert:
    """Alert when unusual headline volume is detected for a ticker."""
    ticker: str
    headline_count: int
    normal_avg: float
    spike_ratio: float  # headline_count / normal_avg
    sample_headlines: list[str]


# ---------------------------------------------------------------------------
# News Scanner
# ---------------------------------------------------------------------------

class NewsScanner:
    """
    Surfaces news headlines and market events.

    Primary source: yfinance (free, no API key).
    Optional: NewsAPI key for broader coverage.
    """

    def __init__(self, newsapi_key: Optional[str] = None):
        self.newsapi_key = newsapi_key

    # ------------------------------------------------------------------
    # Headlines (via yfinance)
    # ------------------------------------------------------------------

    def get_headlines(self, ticker: str, max_items: int = 10) -> list[Headline]:
        """
        Get recent news headlines for a ticker from yfinance.

        Args:
            ticker: Ticker symbol.
            max_items: Maximum headlines to return.

        Returns:
            List of Headline dataclasses, most recent first.
        """
        try:
            import yfinance as yf
            t = yf.Ticker(ticker)
            news = t.news

            if not news:
                return []

            headlines = []
            for item in news[:max_items]:
                title = item.get("title", "")
                source = item.get("publisher", "unknown")
                url = item.get("link", "")
                pub_time = item.get("providerPublishTime", 0)

                if pub_time:
                    pub_date = datetime.fromtimestamp(pub_time).isoformat()
                else:
                    pub_date = date.today().isoformat()

                # Simple relevance heuristic: if ticker is in title, high relevance
                if ticker.upper() in title.upper():
                    relevance = "high"
                else:
                    relevance = "medium"

                headlines.append(Headline(
                    title=title,
                    source=source,
                    url=url,
                    published=pub_date,
                    ticker=ticker,
                    relevance=relevance,
                ))

            return headlines

        except Exception:
            return []

    def get_sector_headlines(self, tickers: list[str], max_per_ticker: int = 3) -> list[Headline]:
        """Get headlines across multiple tickers (e.g., all energy names)."""
        all_headlines = []
        for ticker in tickers:
            headlines = self.get_headlines(ticker, max_per_ticker)
            all_headlines.extend(headlines)

        # Sort by published date (most recent first)
        all_headlines.sort(key=lambda h: h.published, reverse=True)
        return all_headlines

    # ------------------------------------------------------------------
    # Earnings Calendar
    # ------------------------------------------------------------------

    def earnings_calendar(self, tickers: list[str]) -> list[EarningsEvent]:
        """
        Get upcoming earnings dates for a list of tickers.

        Args:
            tickers: List of ticker symbols to check.

        Returns:
            List of EarningsEvent, sorted by date (soonest first).
        """
        events = []

        for ticker in tickers:
            try:
                import yfinance as yf
                t = yf.Ticker(ticker)
                info = t.info or {}

                # Try to get earnings date from calendar
                cal = t.calendar
                if cal is not None and not cal.empty:
                    if hasattr(cal, 'iloc') and len(cal) > 0:
                        earn_date = str(cal.iloc[0, 0]) if cal.shape[1] > 0 else None
                    else:
                        earn_date = None
                else:
                    earn_date = None

                if earn_date is None:
                    continue

                # Compute days until
                try:
                    earn_dt = datetime.strptime(earn_date[:10], "%Y-%m-%d").date()
                    days_until = (earn_dt - date.today()).days
                except (ValueError, TypeError):
                    days_until = 0
                    earn_date = "unknown"

                events.append(EarningsEvent(
                    ticker=ticker,
                    company_name=info.get("shortName", ticker),
                    earnings_date=earn_date[:10] if earn_date else "unknown",
                    eps_estimate=info.get("forwardEps"),
                    revenue_estimate=None,
                    days_until=days_until,
                ))

            except Exception:
                continue

        # Sort by days_until (soonest first)
        events.sort(key=lambda e: e.days_until)
        return events

    def upcoming_earnings(self, tickers: list[str], within_days: int = 14) -> list[EarningsEvent]:
        """Filter earnings calendar to only those within N days."""
        all_events = self.earnings_calendar(tickers)
        return [e for e in all_events if 0 <= e.days_until <= within_days]

    # ------------------------------------------------------------------
    # Event Detection
    # ------------------------------------------------------------------

    def detect_news_spike(
        self,
        ticker: str,
        threshold_ratio: float = 2.0,
    ) -> Optional[NewsSpikeAlert]:
        """
        Detect if a ticker has unusually high news volume.

        Simple heuristic: if current headline count exceeds threshold_ratio
        times the typical amount, flag it.

        Note: With yfinance's limited news API, this is approximate.
        A production system would use a real news feed with historical volume.
        """
        headlines = self.get_headlines(ticker, max_items=20)
        if not headlines:
            return None

        # Count headlines from last 24 hours
        cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        recent = [h for h in headlines if h.published >= cutoff]

        # Assume "normal" is 2-3 headlines per day for an S&P 500 name
        normal_avg = 3.0
        count = len(recent)
        ratio = count / normal_avg

        if ratio >= threshold_ratio:
            return NewsSpikeAlert(
                ticker=ticker,
                headline_count=count,
                normal_avg=normal_avg,
                spike_ratio=round(ratio, 1),
                sample_headlines=[h.title for h in recent[:5]],
            )

        return None

    # ------------------------------------------------------------------
    # Scheduled Economic Events (Static Calendar)
    # ------------------------------------------------------------------

    def upcoming_macro_events(self, days_ahead: int = 7) -> list[MarketEvent]:
        """
        Return known upcoming macro events.

        In production, this would pull from a live economic calendar API.
        For now, returns common recurring events based on day of week/month.
        """
        events = []
        today = date.today()

        # Generate events for the next N days based on typical schedule
        for i in range(days_ahead):
            d = today + timedelta(days=i)
            dow = d.weekday()  # 0=Mon, 4=Fri
            dom = d.day

            # First Friday = NFP
            if dow == 4 and dom <= 7:
                events.append(MarketEvent(
                    date=d.isoformat(),
                    event="US Nonfarm Payrolls",
                    region="US",
                    importance="high",
                ))

            # Tuesday/Wednesday mid-month = CPI
            if dom in (12, 13, 14) and dow in (1, 2):
                events.append(MarketEvent(
                    date=d.isoformat(),
                    event="US CPI Release",
                    region="US",
                    importance="high",
                ))

            # Last Wednesday of month = FOMC (roughly every 6 weeks)
            if dow == 2 and 22 <= dom <= 28 and d.month in (1, 3, 5, 6, 7, 9, 11, 12):
                events.append(MarketEvent(
                    date=d.isoformat(),
                    event="FOMC Decision",
                    region="US",
                    importance="high",
                ))

            # First business day = ISM Manufacturing PMI
            if dow == 0 and dom <= 3:
                events.append(MarketEvent(
                    date=d.isoformat(),
                    event="ISM Manufacturing PMI",
                    region="US",
                    importance="medium",
                ))

        return events

    # ------------------------------------------------------------------
    # NewsAPI Integration (optional)
    # ------------------------------------------------------------------

    def search_newsapi(
        self,
        query: str,
        days_back: int = 2,
        max_results: int = 10,
    ) -> list[Headline]:
        """
        Search for news via NewsAPI (requires API key).

        Args:
            query: Search query (e.g., "XOM earnings", "OPEC oil production").
            days_back: How many days back to search.
            max_results: Max articles to return.

        Returns:
            List of Headline dataclasses.
        """
        if not self.newsapi_key:
            return []

        try:
            import urllib.request
            import json

            from_date = (date.today() - timedelta(days=days_back)).isoformat()
            url = (
                f"https://newsapi.org/v2/everything?"
                f"q={query}&from={from_date}&sortBy=publishedAt"
                f"&pageSize={max_results}&apiKey={self.newsapi_key}"
            )

            req = urllib.request.Request(url, headers={"User-Agent": "AgenticTrading/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            articles = data.get("articles", [])
            headlines = []
            for art in articles:
                headlines.append(Headline(
                    title=art.get("title", ""),
                    source=art.get("source", {}).get("name", "unknown"),
                    url=art.get("url", ""),
                    published=art.get("publishedAt", "")[:10],
                    ticker=query,
                    relevance="medium",
                ))
            return headlines

        except Exception:
            return []
