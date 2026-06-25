"""Shared utilities: database, market data, compliance, logging."""
import os
import re
import logging
import psycopg2
import requests
from datetime import datetime, date, time, timedelta
from dotenv import load_dotenv
import pytz

load_dotenv()

log = logging.getLogger("portfolio")

ET = pytz.timezone("America/New_York")

SYSTEM_PROMPT = """You are a portfolio data analyst that presents observations and quantitative facts.
You are NOT a financial advisor. You have no fiduciary duty and no license.

Hard rules:
- NEVER recommend buying, selling, holding, or rebalancing any position.
- NEVER use phrases like "you should", "I recommend", "consider selling", "it might be wise to".
- NEVER predict future prices or guarantee outcomes.
- Present data, surface patterns, and explain what the numbers mean — let the user decide.
- Every number you cite must come from the data provided. Never fabricate statistics."""

BANNED_PHRASES = [
    "you should", "i recommend", "i suggest", "consider buying", "consider selling",
    "consider holding", "it might be wise", "i advise", "my recommendation",
    "i would suggest", "you might want to buy", "you might want to sell",
    "you ought to", "i encourage you to",
]

def sanitize_response(text):
    lower = text.lower()
    found = [p for p in BANNED_PHRASES if p in lower]
    if found:
        text += f"\n\n[Auto-flagged advisory language: {', '.join(found)}. This is data analysis, not financial advice.]"
    return text

# --- Database ---

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def get_holdings():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    rows = cur.fetchall()
    conn.close()
    return [{"ticker": row[0], "shares": float(row[1]), "cost_basis": float(row[2])} for row in rows]

def log_run(run_type, prompt, response, sent, reason):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO agent_logs (run_type, prompt, response, sent, reason) VALUES (%s, %s, %s, %s, %s)",
            (run_type, prompt, response, sent, reason)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to log run: {e}")

def store_daily_close(ticker, close_price):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO daily_closes (ticker, date, close_price)
               VALUES (%s, %s, %s) ON CONFLICT (ticker, date) DO UPDATE SET close_price = %s""",
            (ticker, date.today(), close_price, close_price)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to store daily close for {ticker}: {e}")

# --- Alert State ---

def get_alert_threshold(alert_type):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT last_threshold FROM alert_state WHERE alert_type = %s", (alert_type,))
        row = cur.fetchone()
        conn.close()
        return float(row[0]) if row else None
    except Exception as e:
        log.error(f"Failed to get alert threshold: {e}")
        return None

def set_alert_threshold(alert_type, threshold):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO alert_state (alert_type, last_threshold, last_alerted_at)
               VALUES (%s, %s, NOW())
               ON CONFLICT (alert_type) DO UPDATE SET last_threshold = %s, last_alerted_at = NOW()""",
            (alert_type, threshold, threshold)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to set alert threshold: {e}")

# --- Daily Snapshots ---

def store_daily_snapshot(total_value, total_cost, day_pl, fg_score=None):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO daily_snapshots (date, total_value, total_cost, day_pl, fear_greed_score)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (date) DO UPDATE SET total_value = %s, total_cost = %s, day_pl = %s, fear_greed_score = %s""",
            (date.today(), total_value, total_cost, day_pl, fg_score,
             total_value, total_cost, day_pl, fg_score)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to store daily snapshot: {e}")

def get_weekly_snapshots():
    try:
        conn = get_conn()
        cur = conn.cursor()
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        cur.execute(
            "SELECT date, total_value, total_cost, day_pl, fear_greed_score FROM daily_snapshots WHERE date >= %s ORDER BY date",
            (monday,)
        )
        rows = cur.fetchall()
        conn.close()
        return [{"date": r[0], "total_value": float(r[1]), "total_cost": float(r[2]),
                 "day_pl": float(r[3]) if r[3] else 0, "fg_score": float(r[4]) if r[4] else None} for r in rows]
    except Exception as e:
        log.error(f"Failed to get weekly snapshots: {e}")
        return []

def get_last_week_snapshots():
    try:
        conn = get_conn()
        cur = conn.cursor()
        today = date.today()
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        cur.execute(
            "SELECT date, total_value, total_cost, day_pl, fear_greed_score FROM daily_snapshots WHERE date >= %s AND date < %s ORDER BY date",
            (last_monday, this_monday)
        )
        rows = cur.fetchall()
        conn.close()
        return [{"date": r[0], "total_value": float(r[1]), "total_cost": float(r[2]),
                 "day_pl": float(r[3]) if r[3] else 0, "fg_score": float(r[4]) if r[4] else None} for r in rows]
    except Exception as e:
        log.error(f"Failed to get last week snapshots: {e}")
        return []

def get_monthly_snapshots():
    """Get daily snapshots for the last 30 days — for PDF report charts."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT date, total_value, total_cost, day_pl, fear_greed_score FROM daily_snapshots WHERE date >= %s ORDER BY date",
            (date.today() - timedelta(days=30),)
        )
        rows = cur.fetchall()
        conn.close()
        return [{"date": r[0], "total_value": float(r[1]), "total_cost": float(r[2]),
                 "day_pl": float(r[3]) if r[3] else 0, "fg_score": float(r[4]) if r[4] else None} for r in rows]
    except Exception as e:
        log.error(f"Failed to get monthly snapshots: {e}")
        return []

# --- Contributions ---

def store_contribution(amount, note=""):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO contributions (amount, note) VALUES (%s, %s)", (amount, note))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to store contribution: {e}")

def get_total_contributions():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM contributions")
        total = float(cur.fetchone()[0])
        conn.close()
        return total
    except Exception as e:
        log.error(f"Failed to get contributions: {e}")
        return 0.0

# --- Decision Memory ---

def store_decision_memory(run_type, takeaways, portfolio_value):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO decision_memory (date, run_type, takeaways, portfolio_value) VALUES (%s, %s, %s, %s)",
            (date.today(), run_type, takeaways, portfolio_value)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to store decision memory: {e}")

def get_recent_decisions(limit=5):
    """Get recent decision memories for context injection."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT date, run_type, takeaways, portfolio_value FROM decision_memory ORDER BY created_at DESC LIMIT %s",
            (limit,)
        )
        rows = cur.fetchall()
        conn.close()
        return [{"date": r[0], "run_type": r[1], "takeaways": r[2],
                 "portfolio_value": float(r[3]) if r[3] else None} for r in rows]
    except Exception as e:
        log.error(f"Failed to get decisions: {e}")
        return []

# --- Target Allocation + Drift ---

def set_target_allocation(ticker, target_pct):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO target_allocation (ticker, target_pct)
               VALUES (%s, %s)
               ON CONFLICT (ticker) DO UPDATE SET target_pct = %s""",
            (ticker, target_pct, target_pct)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to set target allocation: {e}")

def get_target_allocations():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT ticker, target_pct FROM target_allocation")
        rows = cur.fetchall()
        conn.close()
        return {r[0]: float(r[1]) for r in rows}
    except Exception as e:
        log.error(f"Failed to get target allocations: {e}")
        return {}

# --- Dividends ---

def store_dividend(ticker, amount, ex_date, pay_date):
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO dividends (ticker, amount, ex_date, pay_date)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (ticker, ex_date) DO NOTHING""",
            (ticker, amount, ex_date, pay_date)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to store dividend: {e}")

def get_total_dividends():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COALESCE(SUM(amount), 0) FROM dividends")
        total = float(cur.fetchone()[0])
        conn.close()
        return total
    except Exception as e:
        log.error(f"Failed to get dividends: {e}")
        return 0.0

# --- Yesterday's Closes ---

def get_yesterday_closes(tickers):
    try:
        conn = get_conn()
        cur = conn.cursor()
        results = {}
        for t in tickers:
            cur.execute(
                "SELECT close_price, date FROM daily_closes WHERE ticker = %s AND date < %s ORDER BY date DESC LIMIT 1",
                (t, date.today())
            )
            row = cur.fetchone()
            if row:
                results[t] = {"price": float(row[0]), "date": row[1]}
        conn.close()
        return results
    except Exception as e:
        log.error(f"Failed to get yesterday closes: {e}")
        return {}

# --- Market Data ---

def get_finnhub_quote(ticker):
    try:
        api_key = os.environ["FINNHUB_API_KEY"]
        resp = requests.get("https://finnhub.io/api/v1/quote", params={"symbol": ticker, "token": api_key}, timeout=10)
        data = resp.json()
        if not data.get("c"):
            return None
        return {
            "current": float(data["c"]),
            "open": float(data["o"]),
            "high": float(data["h"]),
            "low": float(data["l"]),
            "prev_close": float(data["pc"]),
            "change_pct": float(data["dp"]) if data.get("dp") else 0.0,
        }
    except Exception as e:
        log.error(f"Failed to get quote for {ticker}: {e}")
        return None

def get_prev_close(ticker):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT close_price FROM daily_closes WHERE ticker = %s ORDER BY date DESC LIMIT 1",
        (ticker,)
    )
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else None

def get_streak(ticker, lookback=10):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT close_price FROM daily_closes WHERE ticker = %s ORDER BY date DESC LIMIT %s",
        (ticker, lookback + 1)
    )
    rows = [float(r[0]) for r in cur.fetchall()]
    conn.close()
    if len(rows) < 2:
        return 0
    streak = 0
    direction = None
    for i in range(len(rows) - 1):
        diff = rows[i] - rows[i + 1]
        if direction is None:
            direction = 1 if diff > 0 else -1
        if (diff > 0 and direction > 0) or (diff < 0 and direction < 0):
            streak += 1
        else:
            break
    return streak * direction

def get_latest_price(ticker):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT price FROM prices WHERE ticker = %s ORDER BY recorded_at DESC LIMIT 1", (ticker,))
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else None

# --- Market Hours ---

def is_market_open():
    """Check if US market is open using Finnhub API (handles half-days/holidays).
    Falls back to hardcoded schedule if API fails."""
    try:
        from news import get_market_status
        status = get_market_status()
        if status:
            return status["is_open"]
    except Exception:
        pass
    # Fallback: hardcoded schedule
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    return time(9, 30) <= now.time() <= time(16, 0)
