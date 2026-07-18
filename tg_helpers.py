"""Telegram helpers — used by both the async bot and sync cron jobs (agent.py).

The bot uses the python-telegram-bot Application directly.
Cron jobs call send_message() / send_photo() which use simple sync HTTP requests.
"""
import os
import logging
import requests
from dotenv import load_dotenv

from retry_utils import retry_call

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
        resp = retry_call(
            requests.post, url,
            json={"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"},
            timeout=10,
            what="Telegram sendMessage",
        )
        if not resp.ok:
            log.warning(f"Markdown send failed ({resp.status_code}), retrying as plain text")
            resp = retry_call(
                requests.post, url,
                json={"chat_id": chat_id, "text": chunk},
                timeout=10,
                what="Telegram sendMessage (plain)",
            )
            if not resp.ok:
                log.error(
                    f"Telegram send failed: HTTP {resp.status_code} {resp.text} "
                    f"(chunk len={len(chunk)})"
                )


def send_photo(photo_path, caption=""):
    """Sync send photo — used by agent.py for weekly report charts."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendPhoto"

    try:
        with open(photo_path, "rb") as f:
            data = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            resp = requests.post(url, data=data, files={"photo": f}, timeout=30)
            if not resp.ok:
                log.error(f"Photo send failed: {resp.status_code} {resp.text}")
    except Exception as e:
        log.error(f"Failed to send photo {photo_path}: {e}")
