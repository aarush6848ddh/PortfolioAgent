import os
import requests
from dotenv import load_dotenv

load_dotenv()

def send_message(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # Try Markdown first, fall back to plain text if formatting fails
    resp = requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
    if not resp.ok:
        requests.post(url, json={"chat_id": chat_id, "text": text})
