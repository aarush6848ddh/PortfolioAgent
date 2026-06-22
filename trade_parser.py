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


def _call_groq(messages, model="openai/gpt-oss-120b"):
    """Make a raw Groq API call and return the response text."""
    resp = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json={"model": model, "messages": messages, "temperature": 0},
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def parse_trade(text):
    """Parse a plain English message into a trade dict, or return None."""
    messages = [
        {"role": "system", "content": TRADE_SYSTEM_PROMPT},
        {"role": "user", "content": text},
    ]
    raw = _call_groq(messages)
    try:
        result = json.loads(raw)
        if result and isinstance(result, dict) and result.get("action") and result.get("ticker") and result.get("shares"):
            return result
    except json.JSONDecodeError:
        pass
    return None


def parse_trade_image(image_url):
    """Parse a brokerage screenshot into a trade dict, or return None."""
    messages = [
        {"role": "system", "content": TRADE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Extract the trade details from this brokerage confirmation screenshot."},
                {"type": "image_url", "image_url": {"url": image_url}},
            ],
        },
    ]
    raw = _call_groq(messages, model="qwen/qwen3.6-27b")
    try:
        result = json.loads(raw)
        if result and isinstance(result, dict) and result.get("action") and result.get("ticker") and result.get("shares"):
            return result
    except json.JSONDecodeError:
        pass
    return None
