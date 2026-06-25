"""Telegram helpers — used by both the async bot and sync cron jobs (agent.py).

The bot uses the python-telegram-bot Application directly.
Cron jobs call send_message() which uses a simple sync HTTP request.
"""
import os
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("telegram")

DISCLAIMER = "\n\n---\nData analysis only — not financial advice."
MAX_MSG_LEN = 4096


def send_message(text, disclaimer=False):
    """Sync send — used by agent.py cron jobs (not the bot).
    Disclaimer only appended when explicitly requested (morning briefing only)."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    if disclaimer:
        text += DISCLAIMER

    chunks = [text[i:i + MAX_MSG_LEN] for i in range(0, len(text), MAX_MSG_LEN)]

    for chunk in chunks:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            timeout=10,
        )
        if not resp.ok:
            log.warning(f"Markdown send failed ({resp.status_code}), retrying as plain text")
            resp = requests.post(
                url,
                json={"chat_id": chat_id, "text": chunk},
                timeout=10,
            )
            if not resp.ok:
                log.error(f"Send failed: {resp.status_code} {resp.text}")
