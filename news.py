"""Market intelligence module — news, insider data, earnings, fundamentals,
ETF holdings, technicals, sentiment, congressional trading from Finnhub."""
import os
import socket
import logging
import requests
import yfinance as yf
from contextlib import contextmanager
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("news")

API_KEY = os.environ["FINNHUB_API_KEY"]
BASE = "https://finnhub.io/api/v1"


@contextmanager
def _force_ipv4():
    """Pin DNS resolution to IPv4 for the duration of the block.

    This host resolves Yahoo/Finnhub to IPv6 but has no working IPv6 route, so
    yfinance's default lookups dead-end and return an empty (looks-delisted)
    result. Scoped rather than global so we don't alter socket behavior for the
    whole process. Not thread-safe — only used from the (single-threaded) report
    / backfill paths.
    """
    orig = socket.getaddrinfo

    def ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return orig(host, port, socket.AF_INET, type, proto, flags)

    socket.getaddrinfo = ipv4_only
    try:
        yield
    finally:
        socket.getaddrinfo = orig

def _get(endpoint, params):
    params["token"] = API_KEY
    try:
        resp = requests.get(f"{BASE}/{endpoint}", params=params, timeout=10)
        return resp.json() if resp.ok else {}
    except Exception as e:
        # requests exceptions embed the full URL (incl. token=...) — scrub it
        log.error(f"Finnhub {endpoint} failed: {str(e).replace(API_KEY, '***')}")
        return {}

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
    today = datetime.now().strftime("%Y-%m-%d")
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime("%Y-%m-%d")
    data = _get("stock/insider-sentiment", {"symbol": ticker, "from": six_months_ago, "to": today})
    months = data.get("data", [])
    if not months:
        return None
    recent = months[-3:] if len(months) >= 3 else months
    return [
        {
            "year": m.get("year"),
            "month": m.get("month"),
            "mspr": round(m.get("mspr", 0), 2),
            "change": m.get("change", 0),
        }
        for m in recent
    ]

# --- Insider Transactions ---

def get_insider_transactions(ticker, limit=5):
    data = _get("stock/insider-transactions", {"symbol": ticker})
    txns = data.get("data", [])
    if not txns:
        return []
    return [
        {
            "name": t.get("name", ""),
            "share": t.get("share", 0),
            "change": t.get("change", 0),
            "transaction_type": "Buy" if t.get("change", 0) > 0 else "Sell",
            "date": t.get("transactionDate", ""),
            "price": t.get("transactionPrice"),
        }
        for t in txns[:limit]
    ]

# --- Recommendation Trends ---

def get_recommendations(ticker):
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
    data = _get("stock/metric", {"symbol": ticker, "metric": "all"})
    m = data.get("metric", {})
    if not m:
        return None

    result = {}
    if m.get("52WeekHigh"):
        result["52_week_high"] = m["52WeekHigh"]
        result["52_week_high_date"] = m.get("52WeekHighDate", "")
    if m.get("52WeekLow"):
        result["52_week_low"] = m["52WeekLow"]
        result["52_week_low_date"] = m.get("52WeekLowDate", "")
    if m.get("beta"):
        result["finnhub_beta"] = round(m["beta"], 3)

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

    for key, label in [
        ("priceRelativeToS&P5004Week", "vs_sp500_4w"),
        ("priceRelativeToS&P50013Week", "vs_sp500_13w"),
        ("priceRelativeToS&P50052Week", "vs_sp500_52w"),
    ]:
        if m.get(key) is not None:
            result[label] = round(m[key], 2)

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

# --- ETF Holdings ---

def get_etf_holdings(ticker, limit=10):
    """Get top holdings of an ETF."""
    data = _get("etf/holdings", {"symbol": ticker})
    holdings = data.get("holdings", [])
    if not holdings:
        return []
    return [
        {
            "symbol": h.get("symbol", "N/A"),
            "name": h.get("name", ""),
            "percent": round(h.get("percent", 0) * 100, 2) if h.get("percent", 0) < 1 else round(h.get("percent", 0), 2),
            "value": h.get("value"),
        }
        for h in holdings[:limit]
    ]

# --- ETF Sector Exposure ---

def get_etf_sector_exposure(ticker):
    """Get sector breakdown of an ETF."""
    data = _get("etf/sector", {"symbol": ticker})
    sectors = data.get("sectorExposure", [])
    if not sectors:
        return []
    return [
        {"sector": s.get("sector", ""), "percent": round(s.get("percent", 0) * 100, 2) if s.get("percent", 0) < 1 else round(s.get("percent", 0), 2)}
        for s in sectors if s.get("percent", 0) > 0
    ]

# --- Economic Calendar ---

def get_economic_calendar(days_ahead=3):
    """Get upcoming economic events (CPI, jobs, Fed, etc.)."""
    today = datetime.now().strftime("%Y-%m-%d")
    future = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    data = _get("calendar/economic", {"from": today, "to": future})
    events = data.get("economicCalendar", {}).get("result", [])
    if not isinstance(events, list):
        return []
    # Filter to high-impact events
    high_impact = [e for e in events if e.get("impact", "") == "high"]
    if high_impact:
        return [
            {
                "event": e.get("event", ""),
                "country": e.get("country", ""),
                "time": e.get("time", ""),
                "impact": e.get("impact", ""),
                "previous": e.get("prev"),
                "estimate": e.get("estimate"),
                "actual": e.get("actual"),
            }
            for e in high_impact[:10]
        ]
    # Fall back to all events if no high-impact
    return [
        {
            "event": e.get("event", ""),
            "country": e.get("country", ""),
            "time": e.get("time", ""),
            "impact": e.get("impact", ""),
        }
        for e in events[:10]
    ]

# --- Upgrade/Downgrade ---

def get_upgrades_downgrades(ticker, days=14):
    """Get recent analyst rating changes."""
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    data = _get("stock/upgrade-downgrade", {"symbol": ticker, "from": from_date, "to": today})
    if not isinstance(data, list):
        return []
    return [
        {
            "company": d.get("company", ""),
            "action": d.get("action", ""),
            "from_grade": d.get("fromGrade", ""),
            "to_grade": d.get("toGrade", ""),
            "date": d.get("gradeTime", ""),
        }
        for d in data[:5]
    ]

# --- Price Target ---

def get_price_target(ticker):
    """Get analyst consensus price target."""
    data = _get("stock/price-target", {"symbol": ticker})
    if not data.get("targetHigh"):
        return None
    return {
        "high": data.get("targetHigh"),
        "low": data.get("targetLow"),
        "mean": data.get("targetMean"),
        "median": data.get("targetMedian"),
        "last_updated": data.get("lastUpdated", ""),
    }

# --- Congressional Trading ---

def get_congressional_trading(ticker, limit=5):
    """Get recent congressional stock trading activity."""
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    data = _get("stock/congressional-trading", {"symbol": ticker, "from": from_date, "to": today})
    trades = data.get("data", [])
    if not isinstance(trades, list) or not trades:
        return []
    return [
        {
            "name": t.get("name", ""),
            "amount": t.get("amount", ""),
            "transaction_type": t.get("transactionType", ""),
            "date": t.get("transactionDate", ""),
        }
        for t in trades[:limit]
    ]

# --- Social Sentiment ---

def get_social_sentiment(ticker):
    """Get Reddit/Twitter social sentiment data."""
    today = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    data = _get("stock/social-sentiment", {"symbol": ticker, "from": from_date, "to": today})
    reddit = data.get("reddit", [])
    twitter = data.get("twitter", [])

    result = {}
    if reddit:
        total_mentions = sum(r.get("mention", 0) for r in reddit)
        avg_score = sum(r.get("score", 0) for r in reddit) / len(reddit) if reddit else 0
        result["reddit_mentions"] = total_mentions
        result["reddit_sentiment"] = round(avg_score, 3)
    if twitter:
        total_mentions = sum(t.get("mention", 0) for t in twitter)
        avg_score = sum(t.get("score", 0) for t in twitter) / len(twitter) if twitter else 0
        result["twitter_mentions"] = total_mentions
        result["twitter_sentiment"] = round(avg_score, 3)
    return result if result else None

# --- Technical Indicators ---

def get_aggregate_indicators(ticker, resolution="D"):
    """Get aggregate technical indicator signals (buy/sell/neutral counts)."""
    data = _get("scan/technical-indicator", {"symbol": ticker, "resolution": resolution})
    tech = data.get("technicalAnalysis", {})
    trend = data.get("trend", {})
    if not tech:
        return None
    return {
        "buy": tech.get("count", {}).get("buy", 0),
        "sell": tech.get("count", {}).get("sell", 0),
        "neutral": tech.get("count", {}).get("neutral", 0),
        "signal": tech.get("signal", ""),
        "adx": trend.get("adx", None),
        "trending": trend.get("trending", None),
    }

# --- Support/Resistance ---

def get_support_resistance(ticker, resolution="D"):
    """Get key support and resistance price levels."""
    data = _get("scan/support-resistance", {"symbol": ticker, "resolution": resolution})
    levels = data.get("levels", [])
    if not levels:
        return None
    return [round(l, 2) for l in levels[:6]]

# --- Pattern Recognition ---

def get_pattern_recognition(ticker, resolution="D"):
    """Get detected chart patterns."""
    data = _get("scan/pattern", {"symbol": ticker, "resolution": resolution})
    points = data.get("points", [])
    if not isinstance(points, list) or not points:
        return []
    return [
        {
            "pattern": p.get("patternname", ""),
            "type": p.get("patterntype", ""),
            "status": p.get("status", ""),
        }
        for p in points[:5]
    ]

# --- ESG Scores ---

def get_esg_score(ticker):
    """Get ESG (Environmental, Social, Governance) scores."""
    data = _get("stock/esg", {"symbol": ticker})
    if not data.get("totalESGScore"):
        return None
    return {
        "total": data.get("totalESGScore"),
        "environment": data.get("environmentScore"),
        "social": data.get("socialScore"),
        "governance": data.get("governanceScore"),
    }

# --- Dividends ---

def get_dividends(ticker, days=365):
    """Per-share dividend history for a ticker, newest first.

    Source: yfinance (Yahoo). Finnhub's stock/dividend is a premium endpoint
    that 403s on the free plan, so the old implementation silently returned []
    for everything — indistinguishable from "this ticker pays no dividend" and
    the reason the dividends table stayed empty. Yahoo does not expose a pay
    date, so pay_date is None here.

    Raises RuntimeError on a fetch failure (network/API problem) so it can't
    quietly zero out a backfill; a genuinely dividend-free ticker returns [].
    """
    cutoff = (datetime.now() - timedelta(days=days)).date()
    try:
        with _force_ipv4():
            tk = yf.Ticker(ticker)
            divs = tk.dividends
            if divs is None or divs.empty:
                # yfinance returns an empty series both for a real no-dividend
                # ticker AND for a failed fetch. Disambiguate: if we can't even
                # pull recent prices, the fetch failed — surface it loudly.
                hist = tk.history(period="5d")
                if hist is None or hist.empty:
                    raise RuntimeError(f"no data returned for {ticker} (fetch likely failed)")
                return []
    except RuntimeError:
        raise
    except Exception as e:
        log.error(f"yfinance dividends fetch failed for {ticker}: {e}")
        raise RuntimeError(f"dividend fetch failed for {ticker}") from e

    result = []
    for ex_ts, amount in divs.items():
        ex_date = ex_ts.date()
        if ex_date < cutoff:
            continue
        result.append({
            "ex_date": ex_date.isoformat(),
            "pay_date": None,  # Yahoo does not provide a pay date
            "amount": round(float(amount), 4),
            "currency": "USD",
        })
    result.sort(key=lambda d: d["ex_date"], reverse=True)
    return result

# --- Market Status ---

def get_market_status():
    """Get real-time market open/closed status for US exchanges."""
    data = _get("stock/market-status", {"exchange": "US"})
    if not data:
        return None
    return {
        "exchange": data.get("exchange", "US"),
        "is_open": data.get("isOpen", False),
        "session": data.get("session", ""),
        "holiday": data.get("holiday", ""),
        "timezone": data.get("t", ""),
    }

# --- Bond Yield Curve ---

def get_bond_yield_curve():
    """Get US Treasury yield curve."""
    data = _get("bond/yield-curve", {"code": "10y"})
    if not data.get("data"):
        return None
    points = data["data"]
    if not isinstance(points, list):
        return None
    return [{"maturity": p.get("d", ""), "yield": p.get("v")} for p in points[:10] if p.get("v")]


# --- Full Intelligence Report ---

def get_full_intel(holdings):
    """Gather all available Finnhub intelligence for the portfolio."""
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

    # 2. Basic Financials
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

    # 3. ETF Holdings
    etf_data = []
    for t in tickers:
        holdings_data = get_etf_holdings(t)
        if holdings_data:
            etf_data.append(f"{t} top holdings:")
            for h in holdings_data[:5]:
                etf_data.append(f"  {h['symbol']}: {h['percent']}% — {h['name']}")
    if etf_data:
        sections.append("\n=== ETF HOLDINGS (what you actually own) ===")
        sections.extend(etf_data)

    # 4. ETF Sector Exposure
    sector_data = []
    for t in tickers:
        sectors = get_etf_sector_exposure(t)
        if sectors:
            sector_parts = [f"{s['sector']}: {s['percent']}%" for s in sectors[:5]]
            sector_data.append(f"{t}: {', '.join(sector_parts)}")
    if sector_data:
        sections.append("\n=== ETF SECTOR EXPOSURE ===")
        sections.extend(sector_data)

    # 5. Insider Activity
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

    # 6. Analyst Recommendations
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

    # 7. Upgrade/Downgrade
    upgrade_data = []
    for t in tickers:
        changes = get_upgrades_downgrades(t)
        if changes:
            for c in changes:
                upgrade_data.append(f"{t}: {c['company']} — {c['action']} ({c['from_grade']} -> {c['to_grade']}) {c['date']}")
    if upgrade_data:
        sections.append("\n=== RECENT UPGRADES/DOWNGRADES ===")
        sections.extend(upgrade_data)

    # 8. Price Targets
    target_data = []
    for t in tickers:
        pt = get_price_target(t)
        if pt:
            target_data.append(f"{t}: median ${pt['median']}, mean ${pt['mean']}, range ${pt['low']}-${pt['high']}")
    if target_data:
        sections.append("\n=== ANALYST PRICE TARGETS ===")
        sections.extend(target_data)

    # 9. Earnings Calendar
    upcoming = get_upcoming_earnings(days_ahead=7)
    if upcoming:
        sections.append(f"\n=== EARNINGS THIS WEEK ({len(upcoming)} companies reporting) ===")
        for e in upcoming[:15]:
            eps = f"est EPS: {e['eps_estimate']}" if e["eps_estimate"] else "no estimate"
            sections.append(f"  {e['symbol']}: {e['date']} ({eps})")
        if len(upcoming) > 15:
            sections.append(f"  ... and {len(upcoming) - 15} more")

    # 10. Earnings Surprises
    surprise_data = []
    for t in tickers:
        surprises = get_earnings_surprises(t)
        if surprises:
            beats = sum(1 for s in surprises if s["surprise_pct"] and s["surprise_pct"] > 0)
            surprise_data.append(f"{t}: beat estimates {beats}/{len(surprises)} recent quarters")
    if surprise_data:
        sections.append("\n=== EARNINGS TRACK RECORD ===")
        sections.extend(surprise_data)

    # 11. Economic Calendar
    econ_events = get_economic_calendar(days_ahead=3)
    if econ_events:
        sections.append(f"\n=== ECONOMIC CALENDAR (next 3 days) ===")
        for e in econ_events:
            impact_tag = f"[{e.get('impact', '').upper()}]" if e.get("impact") else ""
            prev_str = f" (prev: {e['previous']})" if e.get("previous") else ""
            est_str = f" (est: {e['estimate']})" if e.get("estimate") else ""
            sections.append(f"  {impact_tag} {e['event']} ({e.get('country', '')}) {e.get('time', '')}{prev_str}{est_str}")

    # 12. Congressional Trading
    congress_data = []
    for t in tickers:
        trades = get_congressional_trading(t)
        if trades:
            for ct in trades:
                congress_data.append(f"{t}: {ct['name']} — {ct['transaction_type']} {ct['amount']} ({ct['date']})")
    if congress_data:
        sections.append("\n=== CONGRESSIONAL TRADING ===")
        sections.extend(congress_data)

    # 13. Social Sentiment
    social_data = []
    for t in tickers:
        sentiment = get_social_sentiment(t)
        if sentiment:
            parts = []
            if "reddit_mentions" in sentiment:
                parts.append(f"Reddit: {sentiment['reddit_mentions']} mentions (score: {sentiment['reddit_sentiment']})")
            if "twitter_mentions" in sentiment:
                parts.append(f"Twitter: {sentiment['twitter_mentions']} mentions (score: {sentiment['twitter_sentiment']})")
            if parts:
                social_data.append(f"{t}: {' | '.join(parts)}")
    if social_data:
        sections.append("\n=== SOCIAL SENTIMENT ===")
        sections.extend(social_data)

    # 14. Technical Indicators
    tech_data = []
    for t in tickers:
        indicators = get_aggregate_indicators(t)
        if indicators:
            tech_data.append(
                f"{t}: Signal={indicators['signal']} "
                f"(Buy: {indicators['buy']}, Sell: {indicators['sell']}, Neutral: {indicators['neutral']})"
                + (f" ADX: {indicators['adx']:.1f} (trending: {indicators['trending']})" if indicators.get("adx") else "")
            )
        levels = get_support_resistance(t)
        if levels:
            tech_data.append(f"  Support/Resistance levels: {', '.join(f'${l}' for l in levels)}")
    if tech_data:
        sections.append("\n=== TECHNICAL INDICATORS ===")
        sections.extend(tech_data)

    # 15. Chart Patterns
    pattern_data = []
    for t in tickers:
        patterns = get_pattern_recognition(t)
        if patterns:
            for p in patterns:
                pattern_data.append(f"{t}: {p['pattern']} ({p['type']}) — {p['status']}")
    if pattern_data:
        sections.append("\n=== CHART PATTERNS ===")
        sections.extend(pattern_data)

    # 16. ESG Scores
    esg_data = []
    for t in tickers:
        esg = get_esg_score(t)
        if esg:
            esg_data.append(f"{t}: Total ESG={esg['total']}, Env={esg['environment']}, Social={esg['social']}, Gov={esg['governance']}")
    if esg_data:
        sections.append("\n=== ESG SCORES ===")
        sections.extend(esg_data)

    # 17. Dividends
    div_data = []
    for t in tickers:
        try:
            divs = get_dividends(t, days=180)
        except RuntimeError as e:
            log.warning(f"skipping dividends for {t}: {e}")
            continue
        if divs:
            recent = divs[0]
            pay = recent["pay_date"] or "n/a"
            div_data.append(f"{t}: last dividend ${recent['amount']} (ex-date: {recent['ex_date']}, pay: {pay})")
    if div_data:
        sections.append("\n=== RECENT DIVIDENDS ===")
        sections.extend(div_data)

    return "\n".join(sections)
