import os
import psycopg2
from groq import Groq
from dotenv import load_dotenv

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

if __name__ == "__main__":
    holdings = get_holdings()
    prompt = build_prompt(holdings)
    response = analyze(prompt)
    if response.strip() != "SILENT":
        print(response)


