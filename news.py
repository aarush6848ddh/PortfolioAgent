"""Market intelligence module — news, insider data, earnings, fundamentals from Finnhub."""
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ["FINNHUB_API_KEY"]
BASE = "https://finnhub.io/api/v1"

def _get(endpoint, params):
    params["token"] = API_KEY
    resp = requests.get(f"{BASE}/{endpoint}", params=params)
    return resp.json() if resp.ok else {}

# --- Company News ---

def get_company_news(ticker, days=2):
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    data = _get("company-news", {"symbol": ticker, "from": from_date, "to": today})
    if not isinstance(data, list):
        return []
    return [
        {
            "headline": a.get("headline", ""),
            "source": a.get("source", ""),
            "summary": a.get("summary", "")[:200],
            "datetime": datetime.fromtimestamp(a["datetime"]).strftime("%Y-%m-%d %H:%M") if a.get("datetime") else "",
        }
        for a in data[:5]
    ]

# --- Insider Sentiment (MSPR) ---

def get_insider_sentiment(ticker):
    """Get monthly insider sentiment. MSPR ranges -100 (bearish) to +100 (bullish)."""
    today = datetime.now().strftime("%Y-%m-%d")
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    data = _get("stock/insider-sentiment", {"symbol": ticker, "from": six_months_ago, "to": today})
    months = data.get("data", [])
    if not months:
        return None
    # Return most recent months
    recent = months[-3:] if len(months) >= 3 else months
    return [
        {
            "year": m.get("year"),
            "month": m.get("month"),
            "mspr": round(m.get("mspr", 0), 2),
            "change": m.get("change", 0),  # net shares bought/sold
        }
        for m in recent
    ]

# --- Insider Transactions ---

def get_insider_transactions(ticker, limit=5):
    """Get recent insider buy/sell transactions."""
    data = _get("stock/insider-transactions", {"symbol": ticker})
    txns = data.get("data", [])
    if not txns:
        return []
    return [
        {
            "name": t.get("name", ""),
            "share": t.get("share", 0),
            "change": t.get("change", 0),  # positive = buy, negative = sell
            "transaction_type": "Buy" if t.get("change", 0) > 0 else "Sell",
            "date": t.get("transactionDate", ""),
            "price": t.get("transactionPrice"),
        }
        for t in txns[:limit]
    ]

# --- Recommendation Trends ---

def get_recommendations(ticker):
    """Get analyst recommendation trends (strong buy/buy/hold/sell/strong sell)."""
    data = _get("stock/recommendation", {"symbol": ticker})
    if not isinstance(data, list) or not data:
        return None
    latest = data[0]
    return {
        "period": latest.get("period", ""),
        "strong_buy": latest.get("strongBuy", 0),
        "buy": latest.get("buy", 0),
        "hold": latest.get("hold", 0),
        "sell": latest.get("sell", 0),
        "strong_sell": latest.get("strongSell", 0),
    }

# --- Earnings Calendar ---

def get_upcoming_earnings(days_ahead=7):
    """Get earnings reports in the next N days."""
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    data = _get("calendar/earnings", {"from": today, "to": future})
    earnings = data.get("earningsCalendar", [])
    return [
        {
            "symbol": e.get("symbol", ""),
            "date": e.get("date", ""),
            "eps_estimate": e.get("epsEstimate"),
            "revenue_estimate": e.get("revenueEstimate"),
        }
        for e in earnings
    ]

# --- Earnings Surprises ---

def get_earnings_surprises(ticker, limit=4):
    """Get recent EPS actual vs estimate."""
    data = _get("stock/earnings", {"symbol": ticker, "limit": limit})
    if not isinstance(data, list) or not data:
        return None
    return [
        {
            "period": e.get("period", ""),
            "actual": e.get("actual"),
            "estimate": e.get("estimate"),
            "surprise_pct": e.get("surprisePercent"),
        }
        for e in data
    ]

# --- Basic Financials / Metrics ---

def get_basic_financials(ticker):
    """Get key financial metrics — works for both stocks and ETFs."""
    data = _get("stock/metric", {"symbol": ticker, "metric": "all"})
    m = data.get("metric", {})
    if not m:
        return None

    result = {}
    # 52-week range
    if m.get("52WeekHigh"):
        result["52_week_high"] = m["52WeekHigh"]
        result["52_week_high_date"] = m.get("52WeekHighDate", "")
    if m.get("52WeekLow"):
        result["52_week_low"] = m["52WeekLow"]
        result["52_week_low_date"] = m.get("52WeekLowDate", "")

    # Beta
    if m.get("beta"):
        result["finnhub_beta"] = round(m["beta"], 3)

    # Price returns
    for key, label in [
        ("5DayPriceReturnDaily", "5d_return"),
        ("13WeekPriceReturnDaily", "13w_return"),
        ("26WeekPriceReturnDaily", "26w_return"),
        ("52WeekPriceReturnDaily", "52w_return"),
        ("yearToDatePriceReturnDaily", "ytd_return"),
        ("monthToDatePriceReturnDaily", "mtd_return"),
    ]:
        if m.get(key) is not None:
            result[label] = round(m[key], 2)

    # S&P 500 relative performance
    for key, label in [
        ("priceRelativeToS&P5004Week", "vs_sp500_4w"),
        ("priceRelativeToS&P50013Week", "vs_sp500_13w"),
        ("priceRelativeToS&P50052Week", "vs_sp500_52w"),
    ]:
        if m.get(key) is not None:
            result[label] = round(m[key], 2)

    # Stock-specific metrics (won't exist for ETFs)
    for key, label in [
        ("peNormalizedAnnual", "pe_ratio"),
        ("psTTM", "ps_ratio"),
        ("currentDividendYieldTTM", "dividend_yield"),
        ("epsGrowthTTMYoy", "eps_growth_yoy"),
        ("revenueGrowthTTMYoy", "revenue_growth_yoy"),
        ("roeTTM", "roe"),
        ("netProfitMarginTTM", "net_margin"),
        ("currentRatioQuarterly", "current_ratio"),
    ]:
        if m.get(key) is not None:
            result[label] = round(m[key], 2)

    return result

# --- Full Intelligence Report ---

def get_full_intel(holdings):
    """Gather all available Finnhub intelligence for the portfolio.
    Returns a dict with all data, formatted as text for LLM consumption."""
    tickers = [h["ticker"] for h in holdings]

    sections = []

    # 1. News
    sections.append("=== RECENT NEWS ===")
    for t in tickers:
        articles = get_company_news(t)
        if articles:
            sections.append(f"{t}:")
            for a in articles:
                sections.append(f"  - [{a['source']}] {a['headline']} ({a['datetime']})")
        else:
            sections.append(f"{t}: No recent news")

    # 2. Basic Financials (works for ETFs)
    sections.append("\n=== KEY METRICS ===")
    for t in tickers:
        metrics = get_basic_financials(t)
        if metrics:
            parts = []
            if "52_week_high" in metrics:
                parts.append(f"52wH: ${metrics['52_week_high']} ({metrics.get('52_week_high_date','')})")
            if "52_week_low" in metrics:
                parts.append(f"52wL: ${metrics['52_week_low']} ({metrics.get('52_week_low_date','')})")
            if "ytd_return" in metrics:
                parts.append(f"YTD: {metrics['ytd_return']:+.1f}%")
            if "5d_return" in metrics:
                parts.append(f"5D: {metrics['5d_return']:+.1f}%")
            if "vs_sp500_13w" in metrics:
                parts.append(f"vs S&P 13w: {metrics['vs_sp500_13w']:+.1f}%")
            if "vs_sp500_52w" in metrics:
                parts.append(f"vs S&P 52w: {metrics['vs_sp500_52w']:+.1f}%")
            if "pe_ratio" in metrics:
                parts.append(f"P/E: {metrics['pe_ratio']}")
            if "dividend_yield" in metrics:
                parts.append(f"Div: {metrics['dividend_yield']:.2f}%")
            sections.append(f"{t}: {' | '.join(parts)}")

    # 3. Insider Sentiment (stocks only, skip for ETFs silently)
    insider_data = []
    for t in tickers:
        sentiment = get_insider_sentiment(t)
        if sentiment:
            latest = sentiment[-1]
            insider_data.append(f"{t}: MSPR {latest['mspr']:+.2f} (net shares: {latest['change']:+,})")

        txns = get_insider_transactions(t)
        if txns:
            for tx in txns[:3]:
                insider_data.append(f"  {tx['name']}: {tx['transaction_type']} {abs(tx['change']):,} shares @ ${tx['price'] or 'N/A'} ({tx['date']})")

    if insider_data:
        sections.append("\n=== INSIDER ACTIVITY ===")
        sections.extend(insider_data)

    # 4. Analyst Recommendations (stocks only)
    rec_data = []
    for t in tickers:
        rec = get_recommendations(t)
        if rec:
            total = rec["strong_buy"] + rec["buy"] + rec["hold"] + rec["sell"] + rec["strong_sell"]
            rec_data.append(
                f"{t}: {rec['strong_buy']} strong buy, {rec['buy']} buy, "
                f"{rec['hold']} hold, {rec['sell']} sell, {rec['strong_sell']} strong sell "
                f"({rec['period']})"
            )
    if rec_data:
        sections.append("\n=== ANALYST RECOMMENDATIONS ===")
        sections.extend(rec_data)

    # 5. Earnings Calendar (upcoming for any stock)
    upcoming = get_upcoming_earnings(days_ahead=7)
    if upcoming:
        sections.append(f"\n=== EARNINGS THIS WEEK ({len(upcoming)} companies reporting) ===")
        # Show first 15
        for e in upcoming[:15]:
            eps = f"est EPS: {e['eps_estimate']}" if e["eps_estimate"] else "no estimate"
            sections.append(f"  {e['symbol']}: {e['date']} ({eps})")
        if len(upcoming) > 15:
            sections.append(f"  ... and {len(upcoming) - 15} more")

    # 6. Earnings Surprises (stocks only)
    surprise_data = []
    for t in tickers:
        surprises = get_earnings_surprises(t)
        if surprises:
            beats = sum(1 for s in surprises if s["surprise_pct"] and s["surprise_pct"] > 0)
            surprise_data.append(f"{t}: beat estimates {beats}/{len(surprises)} recent quarters")
    if surprise_data:
        sections.append("\n=== EARNINGS TRACK RECORD ===")
        sections.extend(surprise_data)

    return "\n".join(sections)
