"""Portfolio intelligence agent with four reasoning modes:
- morning:  Pre-market briefing (8:55 AM ET)
- intraday: Market-hours check (every 30 min, 9:30-4:00 ET)
- daily:    End-of-day summary (4:05 PM ET)
- weekly:   Weekend digest (Saturday 9 AM ET)

Every run is logged to agent_logs, even when the agent stays silent.
"""
import os
import sys
import json
import psycopg2
import requests
from groq import Groq
from dotenv import load_dotenv
from datetime import datetime, date, time, timedelta
from telegram import send_message
from quant import get_quant_summary, format_quant_for_prompt
import pytz

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])
ET = pytz.timezone("America/New_York")

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

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

def get_holdings():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ticker, shares, cost_basis FROM holdings WHERE sold_at IS NULL")
    rows = cur.fetchall()
    conn.close()
    return [{"ticker": row[0], "shares": float(row[1]), "cost_basis": float(row[2])} for row in rows]

def get_latest_price(ticker):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT price FROM prices WHERE ticker = %s ORDER BY recorded_at DESC LIMIT 1", (ticker,))
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else None

def get_finnhub_quote(ticker):
    """Get current quote from Finnhub REST API (open, high, low, current, prev close)."""
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
    """Get yesterday's close from daily_closes table."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT close_price FROM daily_closes WHERE ticker = %s ORDER BY date DESC LIMIT 1",
        (ticker,)
    )
    row = cur.fetchone()
    conn.close()
    return float(row[0]) if row else None

def store_daily_close(ticker, close_price):
    """Store today's closing price in daily_closes."""
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

def get_streak(ticker, lookback=10):
    """Count consecutive up or down days from daily_closes."""
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
        diff = rows[i] - rows[i + 1]  # newest - next oldest
        if direction is None:
            direction = 1 if diff > 0 else -1
        if (diff > 0 and direction > 0) or (diff < 0 and direction < 0):
            streak += 1
        else:
            break
    return streak * direction  # positive = up streak, negative = down streak

def call_llm(prompt):
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content

# === MORNING BRIEFING (8:55 AM ET) ===

def morning_briefing():
    holdings = get_holdings()
    quant = get_quant_summary(holdings)
    quant_text = format_quant_for_prompt(quant)

    lines = ["=== PORTFOLIO SNAPSHOT ==="]
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        prev = get_prev_close(h["ticker"])
        quote = get_finnhub_quote(h["ticker"])
        streak = get_streak(h["ticker"])

        price = quote["current"] if quote else prev
        if price is None:
            continue

        value = price * h["shares"]
        cost = h["cost_basis"] * h["shares"]
        total_value += value
        total_cost += cost
        pl = value - cost
        pl_pct = (price - h["cost_basis"]) / h["cost_basis"] * 100

        streak_str = f"{abs(streak)}-day {'up' if streak > 0 else 'down'} streak" if streak != 0 else "no streak"

        pre_chg = ""
        if quote and quote["prev_close"] > 0:
            pre_chg = f", pre-market: {quote['change_pct']:+.2f}%"

        lines.append(
            f"{h['ticker']}: {h['shares']} shares | prev close ${prev or 'N/A'} | "
            f"P&L: ${pl:.2f} ({pl_pct:+.1f}%) | {streak_str}{pre_chg}"
        )

    alloc_lines = []
    for h in holdings:
        prev = get_prev_close(h["ticker"])
        if prev:
            weight = (prev * h["shares"]) / total_value * 100 if total_value > 0 else 0
            alloc_lines.append(f"{h['ticker']}: {weight:.1f}%")
    lines.append(f"Allocation: {', '.join(alloc_lines)}")
    lines.append(f"Total value: ${total_value:.2f} | Total cost: ${total_cost:.2f} | Total P&L: ${total_value - total_cost:+.2f}")

    lines.append("")
    lines.append(quant_text)

    portfolio_data = "\n".join(lines)

    prompt = f"""You are a portfolio intelligence agent. It's morning, before market open.
Give me a concise morning briefing based on this data. Focus on:
1. What happened yesterday (use the prev close vs cost basis)
2. Any notable streaks or trends
3. Quantitative insights — especially correlation and diversification observations
4. What to watch today

Use the quant data to make SPECIFIC observations (e.g. "your SOXX has 0.89 correlation
with SCHG, so they're moving together — that's not real diversification").

Be direct, no fluff. Use numbers from the data, never fabricate.

{portfolio_data}"""

    response = call_llm(prompt)
    log_run("morning", prompt, response, True, "morning briefing always sent")
    send_message(f"Good morning.\n\n{response}")

# === INTRADAY CHECK (every 30 min) ===

def intraday_check():
    holdings = get_holdings()
    quant = get_quant_summary(holdings)
    quant_text = format_quant_for_prompt(quant)

    lines = ["=== INTRADAY SNAPSHOT ==="]
    any_big_move = False

    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        if quote is None:
            continue

        intraday_chg = quote["change_pct"]
        day_range = quote["high"] - quote["low"]
        pl = (quote["current"] - h["cost_basis"]) * h["shares"]

        if abs(intraday_chg) >= 2.0:
            any_big_move = True

        lines.append(
            f"{h['ticker']}: ${quote['current']:.2f} ({intraday_chg:+.2f}% today) | "
            f"range ${quote['low']:.2f}-${quote['high']:.2f} | "
            f"P&L: ${pl:.2f}"
        )

    lines.append("")
    lines.append(quant_text)

    portfolio_data = "\n".join(lines)

    prompt = f"""You are a portfolio intelligence agent monitoring intraday activity.

Rules:
- Only respond if something genuinely matters: a holding moved 2%+ intraday,
  a correlated pair is diverging unusually, or there's a notable pattern.
- Use the quantitative data to add insight, not just report price changes.
  For example, if two highly correlated holdings are moving in opposite directions today,
  that's worth noting.
- If nothing notable is happening, respond with exactly: SILENT

{portfolio_data}"""

    response = call_llm(prompt)
    is_silent = response.strip() == "SILENT"

    if is_silent:
        log_run("intraday", prompt, response, False, "nothing notable — agent chose SILENT")
    elif any_big_move:
        log_run("intraday", prompt, response, True, "big move detected (2%+)")
        send_message(response)
    else:
        log_run("intraday", prompt, response, True, "agent flagged something notable")
        send_message(response)

# === DAILY SUMMARY (4:05 PM ET) ===

def daily_summary():
    holdings = get_holdings()
    quant = get_quant_summary(holdings)
    quant_text = format_quant_for_prompt(quant)

    lines = []
    total_value = 0.0
    total_cost = 0.0
    total_day_pl = 0.0

    for h in holdings:
        quote = get_finnhub_quote(h["ticker"])
        if quote is None:
            lines.append(f"{h['ticker']}: no price data")
            continue

        price = quote["current"]
        store_daily_close(h["ticker"], price)

        value = price * h["shares"]
        cost = h["cost_basis"] * h["shares"]
        day_change = quote["change_pct"]
        day_pl = (price - quote["prev_close"]) * h["shares"]

        total_value += value
        total_cost += cost
        total_day_pl += day_pl

        lines.append({
            "ticker": h["ticker"],
            "price": price,
            "day_change": day_change,
            "day_pl": day_pl,
            "total_pl": value - cost,
            "total_pl_pct": (price - h["cost_basis"]) / h["cost_basis"] * 100,
            "value": value,
        })

    # Store SPY close once for beta calculations
    spy_quote = get_finnhub_quote("SPY")
    if spy_quote:
        store_daily_close("SPY", spy_quote["current"])

    # Build summary message
    msg_lines = ["End of Day Summary\n"]

    for item in lines:
        if isinstance(item, str):
            msg_lines.append(item)
            continue
        weight = item["value"] / total_value * 100 if total_value > 0 else 0
        arrow = "+" if item["day_change"] >= 0 else ""
        msg_lines.append(
            f"{item['ticker']}: ${item['price']:.2f} | "
            f"today: {arrow}{item['day_change']:.2f}% (${item['day_pl']:+.2f}) | "
            f"total: {item['total_pl_pct']:+.1f}% | "
            f"weight: {weight:.0f}%"
        )

    msg_lines.append(f"\nPortfolio: ${total_value:.2f}")
    msg_lines.append(f"Today's P&L: ${total_day_pl:+.2f}")
    msg_lines.append(f"Total P&L: ${total_value - total_cost:+.2f}")

    summary_data = "\n".join(msg_lines)

    # Now ask LLM for a brief analytical note
    prompt = f"""You are a portfolio analyst. Here is today's end-of-day data and quantitative analysis.
Write a brief (2-4 sentence) analytical note to append to the daily summary. Focus on:
- What drove today's moves
- Any quant insight worth highlighting (diversification, correlation, risk)
- Do NOT repeat the numbers — they're already in the summary above
- Be specific, use the quant data

{summary_data}

{quant_text}"""

    response = call_llm(prompt)
    log_run("daily", prompt, response, True, "daily summary always sent")

    full_msg = f"{summary_data}\n\n{response}"
    send_message(full_msg)

# === WEEKLY DIGEST (Saturday 9 AM ET) ===

def weekly_digest():
    holdings = get_holdings()
    quant = get_quant_summary(holdings)
    quant_text = format_quant_for_prompt(quant)

    # Get this week's closes for each holding
    conn = get_conn()
    cur = conn.cursor()
    week_ago = date.today() - timedelta(days=7)

    week_data = []
    for h in holdings:
        cur.execute(
            """SELECT date, close_price FROM daily_closes
               WHERE ticker = %s AND date >= %s ORDER BY date""",
            (h["ticker"], week_ago)
        )
        rows = cur.fetchall()
        if len(rows) >= 2:
            start = float(rows[0][1])
            end = float(rows[-1][1])
            week_return = (end - start) / start * 100
            week_data.append(f"{h['ticker']}: {week_return:+.2f}% this week (${start:.2f} -> ${end:.2f})")
        else:
            week_data.append(f"{h['ticker']}: insufficient data this week")

    # Count agent activity this week
    cur.execute(
        "SELECT run_type, COUNT(*), SUM(CASE WHEN sent THEN 1 ELSE 0 END) FROM agent_logs WHERE created_at >= %s GROUP BY run_type",
        (week_ago,)
    )
    activity = cur.fetchall()
    conn.close()

    activity_lines = [f"{r[0]}: {r[1]} runs, {r[2]} messages sent" for r in activity]

    prompt = f"""You are a portfolio intelligence agent delivering a weekly digest.

Weekly performance:
{chr(10).join(week_data)}

Agent activity this week:
{chr(10).join(activity_lines) if activity_lines else "No activity logged."}

{quant_text}

Write a concise weekly digest. Cover:
1. Best and worst performer this week
2. Portfolio-level return for the week
3. Key quant observation — especially anything about diversification, drawdown, or risk
4. One thing to watch next week
5. How the portfolio compared to the VTI baseline (use the backtest data)

Be direct and specific. Use numbers from the data."""

    response = call_llm(prompt)
    log_run("weekly", prompt, response, True, "weekly digest always sent")
    send_message(f"Weekly Digest\n\n{response}")

# === MARKET HOURS CHECK ===

def is_market_open():
    now = datetime.now(ET)
    if now.weekday() >= 5:
        return False
    return time(9, 30) <= now.time() <= time(16, 0)

# === MAIN ===

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "intraday"

    if mode == "--morning":
        morning_briefing()
    elif mode == "--summary":
        daily_summary()
    elif mode == "--weekly":
        weekly_digest()
    else:
        # Default: intraday check (only during market hours)
        if not is_market_open():
            print("Market closed, exiting.")
            exit(0)
        intraday_check()
