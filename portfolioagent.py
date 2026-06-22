import sys
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

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

def sell(ticker, shares, sale_price=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE holdings SET sold_at = NOW(), sale_price = %s WHERE ticker = %s and sold_at IS NULL", (sale_price, ticker))
    conn.commit()
    cur.close()
    conn.close()
    print(f"Sold {shares} shares of {ticker}" + (f" at ${sale_price}" if sale_price else ""))

if __name__ == "__main__":
    command = sys.argv[1]
    if command == "buy":
        buy(sys.argv[2], sys.argv[3], sys.argv[4])
    elif command == "sell":
        price = sys.argv[4] if len(sys.argv) > 4 else None
        sell(sys.argv[2], sys.argv[3], price)
