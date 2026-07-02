"""Real-time price streaming.

One asyncio task holds the single allowed Finnhub WebSocket connection,
subscribes to all active holdings + SPY, and on every trade tick:
  1. updates the shared REST quote cache (api/quotes.py)
  2. broadcasts {ticker, price, ts} to all connected dashboard browsers

Browsers connect to the FastAPI /ws endpoint — the Finnhub key never
leaves the server. Auto-reconnects with backoff; refreshes the ticker
list every 5 minutes so new holdings get subscribed automatically.
"""
import os
import json
import asyncio
import logging
import time

import websockets

from api import quotes
from api.db import get_db

log = logging.getLogger("stream")

FINNHUB_WS = "wss://ws.finnhub.io"
TICKER_REFRESH_SECONDS = 300
MAX_CLIENTS = 20  # public endpoint — cap fan-out connections

_clients: set = set()


# --- Browser fan-out ---

def client_count():
    return len(_clients)


def add_client(ws):
    _clients.add(ws)


def remove_client(ws):
    _clients.discard(ws)


async def _broadcast(payload: str):
    dead = []
    for ws in _clients:
        try:
            await ws.send_text(payload)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


# --- Finnhub upstream ---

def _get_tickers():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT ticker FROM holdings WHERE sold_at IS NULL")
        tickers = [r[0] for r in cur.fetchall()]
        cur.close()
    if "SPY" not in tickers:
        tickers.append("SPY")
    return tickers


async def _handle_message(raw: str):
    data = json.loads(raw)
    if data.get("type") != "trade":
        return
    # Collapse multiple ticks per message to the latest per ticker.
    latest = {}
    for t in data.get("data", []):
        latest[t["s"]] = t
    for ticker, t in latest.items():
        price = t["p"]
        quotes.update_price(ticker, price)
        await _broadcast(json.dumps({"ticker": ticker, "price": price, "ts": t.get("t")}))


async def finnhub_stream():
    """Long-running task started from the FastAPI lifespan."""
    token = os.environ.get("FINNHUB_API_KEY", "")
    backoff = 5
    while True:
        try:
            subscribed = set(await asyncio.to_thread(_get_tickers))
            async with websockets.connect(f"{FINNHUB_WS}?token={token}") as ws:
                log.info(f"Finnhub WS connected, subscribing: {sorted(subscribed)}")
                for t in subscribed:
                    await ws.send(json.dumps({"type": "subscribe", "symbol": t}))
                backoff = 5
                last_refresh = time.monotonic()

                while True:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=60)
                        await _handle_message(raw)
                    except asyncio.TimeoutError:
                        pass  # quiet market — fall through to refresh check

                    if time.monotonic() - last_refresh >= TICKER_REFRESH_SECONDS:
                        last_refresh = time.monotonic()
                        current = set(await asyncio.to_thread(_get_tickers))
                        for t in current - subscribed:
                            await ws.send(json.dumps({"type": "subscribe", "symbol": t}))
                        for t in subscribed - current:
                            await ws.send(json.dumps({"type": "unsubscribe", "symbol": t}))
                        subscribed = current
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning(f"Finnhub WS dropped ({e}), reconnecting in {backoff}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)
