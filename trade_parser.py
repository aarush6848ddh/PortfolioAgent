"""Parse trade intent from plain English text or brokerage screenshot images.

Uses gpt-oss-120b for text parsing, qwen3.6-27b for image parsing.
Returns a trade dict or None if the message isn't a trade.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

TRADE_SYSTEM_PROMPT = """You are a trade parser for a personal stock portfolio tracker.

If the user's message describes a stock trade (buy or sell), extract the details and return JSON:
{
  "action": "buy" or "sell",
  "ticker": "UPPERCASE TICKER",
  "shares": number,
  "price": number or null,
  "time": "HH:MM" or null
}

Rules:
- ticker must be a valid US stock/ETF ticker, always uppercase
- shares must be a positive number
- price is per share in USD, null if not mentioned
- time is in ET (Eastern), null if not mentioned. "market open" = "09:30", "market close" = "16:00"
- If the message is NOT about logging a trade, return exactly: null

Return ONLY valid JSON. No explanation, no markdown, no code fences."""


import re
import logging

from retry_utils import retry_call

log = logging.getLogger("trade_parser")


def _groq_once(messages, model):
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
        timeout=30,
    )
    resp.raise_for_status()  # raises on 429 too, so retry_call backs off
    return resp.json()["choices"][0]["message"]["content"].strip()


def _call_groq(messages, model="openai/gpt-oss-120b"):
    """Groq call with retry on rate limits AND connection errors (4 tries, 2/8/30s)."""
    return retry_call(_groq_once, messages, model, what=f"Groq {model}")


def _validate_trade(result):
    """Sanity-check LLM output before it ever reaches the DB."""
    if not (result and isinstance(result, dict)):
        return None
    if result.get("action") not in ("buy", "sell"):
        return None
    ticker = str(result.get("ticker", "")).upper()
    if not re.fullmatch(r"[A-Z.]{1,6}", ticker):
        return None
    try:
        shares = float(result.get("shares"))
        price = result.get("price")
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        return None
    if not (0 < shares < 100_000):
        return None
    if price is not None and not (0 < price < 1_000_000):
        return None
    result["ticker"] = ticker
    return result


def parse_trade(text):
    """Parse a plain English message into a trade dict, or return None."""
    messages = [
        {"role": "system", "content": TRADE_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    raw = _call_groq(messages)
    try:
        return _validate_trade(json.loads(raw))
    except json.JSONDecodeError:
        return None


def parse_trade_image(image_bytes, mime_type="image/jpeg"):
    """Parse a brokerage screenshot (raw bytes) into a trade dict, or return None.

    Takes raw bytes and sends a base64 data: URL to Groq. Never pass a
    Telegram file URL here — those embed the bot token and would leak it
    to a third party.
    """
    import base64

    data_url = f"data:{mime_type};base64,{base64.b64encode(bytes(image_bytes)).decode()}"
    messages = [
        {"role": "system", "content": TRADE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract the trade details from this brokerage confirmation screenshot."},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]
    raw = _call_groq(messages, model="qwen/qwen3.6-27b")
    try:
        return _validate_trade(json.loads(raw))
    except json.JSONDecodeError:
        return None
