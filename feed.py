import websocket
import json
import psycopg2
import os 
from dotenv import load_dotenv

load_dotenv()

def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])

def get_tickers():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM holdings WHERE sold_at IS NULL")
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def store_price(ticker, price):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO prices (ticker, price) VALUES (%s, %s)", (ticker, price))
    conn.commit()
    cur.close()
    conn.close()

def on_message(ws, message):
    data = json.loads(message)
    if data["type"] == "trade":
        for trade in data["data"]:
            ticker = trade["s"]
            price = trade["p"]
            store_price(ticker, price)
            print(f"{ticker}: ${price}")

def on_open(ws):
    tickers = get_tickers()
    for ticker in tickers:
        ws.send(json.dumps({"type": "subscribe", "symbol": ticker}))

if __name__ == "__main__":
    api_key = os.environ["FINNHUB_API_KEY"]
    ws = websocket.WebSocketApp(f"wss://ws.finnhub.io?token={api_key}", on_message=on_message, on_open=on_open)
    ws.run_forever()


