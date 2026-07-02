"""Big-move price alerts — runs every 5 min during market hours via cron.

Deliberately LLM-free: pure quote math + a plain Telegram message, so alerts
still fire even when the Groq token budget is exhausted.

Dedup: alerts fire in 3% steps per ticker. Once a ticker alerts at -3%, it
won't alert again until it crosses -6% (or swings back positive). State lives
in the alert_state table and resets each trading day.
"""
import logging
from datetime import datetime

import pytz

from portfolio import get_conn, get_finnhub_quote, get_holdings, is_market_open
from tg_helpers import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("alerts")

ET = pytz.timezone("America/New_York")
STEP_PCT = 3.0  # alert every 3% band crossed (3%, 6%, 9%, ...)


def get_alerted_band(ticker):
    """Return the band already alerted today for this ticker (0 if none).
    State from a previous trading day is ignored — each day starts fresh."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT last_threshold, last_alerted_at FROM alert_state WHERE alert_type = %s",
        (f"move_{ticker}",),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return 0
    band, alerted_at = int(row[0]), row[1]
    if alerted_at is None or alerted_at.astimezone(ET).date() != datetime.now(ET).date():
        return 0
    return band


def set_alerted_band(ticker, band):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO alert_state (alert_type, last_threshold, last_alerted_at)
           VALUES (%s, %s, NOW())
           ON CONFLICT (alert_type) DO UPDATE SET last_threshold = %s, last_alerted_at = NOW()""",
        (f"move_{ticker}", band, band),
    )
    conn.commit()
    cur.close()
    conn.close()


def check_moves():
    lines = []
    for holding in get_holdings():
        ticker = holding["ticker"]
        quote = get_finnhub_quote(ticker)
        if not quote:
            continue

        change_pct = quote["change_pct"]
        band = int(change_pct / STEP_PCT)  # truncates toward zero: +/-1 at 3%, +/-2 at 6%...
        if band == 0:
            continue

        prev_band = get_alerted_band(ticker)
        # Alert only when the move extends past the last alerted band in the
        # same direction, or flips sign — never on a partial retreat.
        moved_further = (band > 0 and band > prev_band) or (band < 0 and band < prev_band)
        if not moved_further:
            continue

        direction = "up" if change_pct > 0 else "down"
        lines.append(f"{ticker} {direction} {change_pct:+.1f}% today (${quote['current']:.2f})")
        set_alerted_band(ticker, band)
        log.info(f"Alerting {ticker}: {change_pct:+.1f}% (band {prev_band} -> {band})")

    if lines:
        send_message("Big move alert\n\n" + "\n".join(lines), disclaimer=False)


if __name__ == "__main__":
    if not is_market_open():
        log.info("Market closed, exiting.")
    else:
        check_moves()
