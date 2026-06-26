"""One-time script to seed daily_closes with ~1 year of historical data via yfinance."""
import os
import psycopg2
import yfinance as yf
from dotenv import load_dotenv

load_dotenv()

TICKERS = ["VTI", "SCHG", "SOXX", "SPY"]

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def seed_ticker(ticker, conn):
    etf = yf.Ticker(ticker)
    hist = etf.history(period="1y")

    if hist.empty:
        print(f"  {ticker}: no data returned")
        return 0

    cur = conn.cursor()
    inserted = 0
    for idx, row in hist.iterrows():
        trade_date = idx.date()
        cur.execute(
            """INSERT INTO daily_closes (ticker, date, open_price, high_price, low_price, close_price, volume)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (ticker, date) DO NOTHING""",
            (ticker, trade_date, float(row["Open"]), float(row["High"]),
             float(row["Low"]), float(row["Close"]), int(row["Volume"]))
        )
        inserted += cur.rowcount
    conn.commit()
    cur.close()
    print(f"  {ticker}: {inserted} rows inserted ({len(hist)} total candles)")
    return inserted

if __name__ == "__main__":
    conn = get_conn()
    total = 0
    for ticker in TICKERS:
        print(f"Fetching {ticker}...")
        total += seed_ticker(ticker, conn)
    conn.close()
    print(f"\nDone. {total} total rows inserted.")
