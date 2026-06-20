import os
import requests
from dotenv import load_dotenv

load_dotenv()

DISCLAIMER = "\n\n---\nData analysis only — not financial advice."

def send_message(text, disclaimer=True):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    if disclaimer:
        text += DISCLAIMER
    resp = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    if not resp.ok:
        requests.post(url, json={"chat_id": chat_id, "text": text})

def get_updates(offset=None):
    """Poll Telegram for new messages."""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {"timeout": 30}
    if offset is not None:
        params["offset"] = offset
    resp = requests.get(url, params=params, timeout=35)
    if resp.ok:
        return resp.json().get("result", [])
    return []
