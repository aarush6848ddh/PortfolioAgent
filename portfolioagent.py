import sys
import psycopg2
import os

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def buy(ticker, shares, cost_basis):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO holdings (ticker, shares, cost_basis) VALUES (%s, %s, %s)", (ticker, shares, cost_basis))
    conn.commit()
    cur.close()
    conn.close()
    print(f"Bought {shares} shares of {ticker}, at ${cost_basis}")

def sell(ticker, shares):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE holdings SET sold_at = NOW() WHERE ticker = %s and sold_at IS NULL", (ticker,))
    conn.commit()
    cur.close()
    conn.close()
    print(f"Sold {shares} shares of {ticker}")

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "buy":
        buy(sys.argv[2], sys.argv[3], sys.argv[4])
    elif command == "sell":
        sell(sys.argv[2], sys.argv[3])
