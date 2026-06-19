import os
import sys
import psycopg2
import requests
from groq import Groq
from dotenv import load_dotenv
from telegram import send_message
from datetime import datetime, time
import pytz

load_dotenv()

client = Groq(api_key=os.environ["GROQ_API_KEY"])

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

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

def get_closing_price(ticker):
    api_key = os.environ["FINNHUB_API_KEY"]
    resp = requests.get("https://finnhub.io/api/v1/quote", params={"symbol": ticker, "token": api_key})
    data = resp.json()
    return float(data["c"]) if data.get("c") else None

def build_prompt(holdings):
    lines = []
    for h in holdings:
        price = get_latest_price(h["ticker"])
        if price is None:
            continue
        gain = (price - h["cost_basis"]) * h["shares"]
        lines.append(f"{h['ticker']}: {h['shares']} shares, cost ${h['cost_basis']}, now ${price}, P&L: ${gain:.2f}")

    portfolio = "\n".join(lines)
    return f"""You are a portfolio analyst. Here are my current holdings: {portfolio}
           Only respond if something genuinely matters (big move, approaching cost
           basis, unusual activity). Otherwise respond with exactly: SILENT"""

def analyze(prompt):
    response = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role": "user", "content": prompt}])
    return response.choices[0].message.content

def is_market_open():
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    return time(9, 30) <= now.time() <= time(16, 0)

def daily_summary():
    holdings = get_holdings()
    lines = []
    total_value = 0.0
    total_pl = 0.0

    for h in holdings:
        price = get_closing_price(h["ticker"])
        if price is None:
            lines.append(f"{h['ticker']}: no price data")
            continue
        value = price * h["shares"]
        pl = (price - h["cost_basis"]) * h["shares"]
        pl_pct = ((price - h["cost_basis"]) / h["cost_basis"]) * 100
        total_value += value
        total_pl += pl
        arrow = "+" if pl >= 0 else ""
        lines.append(f"{h['ticker']}: ${price:.2f} | {arrow}{pl:.2f} ({arrow}{pl_pct:.2f}%)")

    summary = "📊 End of Day Summary\n\n"
    summary += "\n".join(lines)
    summary += f"\n\nTotal Value: ${total_value:.2f}"
    arrow = "+" if total_pl >= 0 else ""
    summary += f"\nTotal P&L: {arrow}${total_pl:.2f}"
    send_message(summary)

if __name__ == "__main__":
    if "--summary" in sys.argv:
        daily_summary()
    else:
        if not is_market_open():
            print("Market closed, exiting.")
            exit(0)
        holdings = get_holdings()
        prompt = build_prompt(holdings)
        response = analyze(prompt)
        if response.strip() != "SILENT":
            send_message(response)
