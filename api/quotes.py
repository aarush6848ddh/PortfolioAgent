"""Shared Finnhub quote cache.

All API endpoints read quotes through here. A 30s TTL + per-ticker
single-flight lock means public traffic can never hit Finnhub more than
once per ticker per 30s (quota-DoS protection). The WebSocket stream
(api/stream.py) pushes live prices into the same cache so REST responses
stay fresh during market hours without extra REST calls.
"""
import os
import time
import logging
import threading

import requests

log = logging.getLogger("quotes")

TTL_SECONDS = 30

_cache: dict = {}  # ticker -> {"expires": float, "quote": dict}
_locks: dict = {}  # ticker -> threading.Lock (single-flight)
_locks_guard = threading.Lock()


def _fetch(ticker):
    """One real Finnhub REST call. Returns quote dict or None."""
    key = os.environ.get("FINNHUB_API_KEY", "")
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": key},
            timeout=5,
        )
        data = r.json()
        if not data.get("c"):
            return None
        return {
            "current": float(data["c"]),
            "prev_close": float(data["pc"]),
            "day_change": float(data["d"]) if data.get("d") else 0.0,
            "day_change_pct": float(data["dp"]) if data.get("dp") else 0.0,
        }
    except Exception as e:
        log.error(f"Quote fetch failed for {ticker}: {e}")
        return None


def get_quote(ticker):
    """Cached quote. Concurrent requests for the same ticker share one fetch."""
    entry = _cache.get(ticker)
    if entry and entry["expires"] > time.time():
        return entry["quote"]

    with _locks_guard:
        lock = _locks.setdefault(ticker, threading.Lock())

    with lock:
        # Another request may have refreshed it while we waited on the lock.
        entry = _cache.get(ticker)
        if entry and entry["expires"] > time.time():
            return entry["quote"]

        quote = _fetch(ticker)
        if quote:
            _cache[ticker] = {"expires": time.time() + TTL_SECONDS, "quote": quote}
            return quote
        # Fetch failed: serve stale data rather than nothing.
        return entry["quote"] if entry else None


def update_price(ticker, price):
    """Push a live WebSocket tick into the cache (extends TTL)."""
    entry = _cache.get(ticker)
    if not entry:
        return
    q = dict(entry["quote"])
    q["current"] = float(price)
    pc = q.get("prev_close") or 0
    if pc:
        q["day_change"] = round(q["current"] - pc, 4)
        q["day_change_pct"] = round((q["current"] - pc) / pc * 100, 4)
    _cache[ticker] = {"expires": time.time() + TTL_SECONDS, "quote": q}
