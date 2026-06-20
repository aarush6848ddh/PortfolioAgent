"""Shared utilities: database, market data, compliance, logging."""
import os
import re
import psycopg2
import requests
from datetime import datetime, date, time, timedelta
from dotenv import load_dotenv
import pytz

load_dotenv()

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
    """Scan for banned advisory phrases and flag them."""
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
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agent_logs (run_type, prompt, response, sent, reason) VALUES (%s, %s, %s, %s, %s)",
        (run_type, prompt, response, sent, reason)
    )
    conn.commit()
    cur.close()
    conn.close()

def store_daily_close(ticker, close_price):
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

# --- Market Data ---

def get_finnhub_quote(ticker):
    api_key = os.environ["FINNHUB_API_KEY"]
    resp = requests.get("https://finnhub.io/api/v1/quote", params={"symbol": ticker, "token": api_key})
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
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    return time(9, 30) <= now.time() <= time(16, 0)
