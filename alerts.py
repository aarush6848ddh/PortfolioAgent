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

from portfolio import (
    get_conn,
    get_finnhub_quote,
    get_holdings,
    is_market_open,
    get_alert_threshold,
    set_alert_threshold,
)
from tg_helpers import send_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("alerts")

ET = pytz.timezone("America/New_York")
STEP_PCT = 3.0  # alert every 3% band crossed (3%, 6%, 9%, ...)

# --- Allocation drift ---
# Target split: 50% VOO / 30% QQQM / 20% individual names. Everything that
# isn't VOO or QQQM is summed into the "individuals" bucket.
TARGETS = {"VOO": 50, "QQQM": 30, "individuals": 20}
# Deadband: a bucket must be more than ALLOC_STEP pts off target to alert, and
# it re-alerts only when it crosses into the next ALLOC_STEP band (so a bucket
# on target = drift 0 = band 0 = silent; worse drift re-alerts; no spam).
ALLOC_STEP = 5


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
    fired = []  # (ticker, band) — recorded only after the send succeeds
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
        fired.append((ticker, band))
        log.info(f"Alerting {ticker}: {change_pct:+.1f}% (band {prev_band} -> {band})")

    if lines:
        # Mark bands only after the send succeeds — if Telegram fails, the
        # alert stays eligible and will retry on the next 5-min run.
        send_message("Big move alert\n\n" + "\n".join(lines), disclaimer=False)
        for ticker, band in fired:
            set_alerted_band(ticker, band)


def get_bucket_weights():
    """Return {bucket: current % of portfolio} using live quotes.

    Returns None if any quote is missing — better to skip a run than to alert
    on a distorted allocation computed from incomplete prices.
    """
    values = {}
    total = 0.0
    for holding in get_holdings():
        ticker = holding["ticker"]
        quote = get_finnhub_quote(ticker)
        if not quote:
            return None
        value = holding["shares"] * quote["current"]
        total += value
        bucket = ticker if ticker in ("VOO", "QQQM") else "individuals"
        values[bucket] = values.get(bucket, 0.0) + value

    if total == 0:
        return None
    return {bucket: value / total * 100 for bucket, value in values.items()}


def check_allocation():
    """Alert when a bucket drifts more than ALLOC_STEP pts from its target.

    Same band/dedup mechanic as check_moves(), but keyed on drift-from-target
    instead of daily price change, and without the daily reset — allocation
    drift persists across days. A bucket re-alerts only when it worsens into a
    new band; once it heals back inside the deadband its stored band resets to
    0 so a future drift will alert again.
    """
    weights = get_bucket_weights()
    if not weights:
        log.info("Allocation check skipped: incomplete quote data.")
        return

    lines = []
    fired = []  # (key, band) — recorded only after the send succeeds
    for bucket, target in TARGETS.items():
        current = weights.get(bucket, 0.0)
        drift = current - target
        band = int(drift / ALLOC_STEP)  # 0 while within +/- ALLOC_STEP pts (deadband)

        key = f"alloc_{bucket}"
        prev = get_alert_threshold(key)
        prev_band = int(prev) if prev is not None else 0

        if band == 0:
            # Back within tolerance: reset so a future drift can re-alert.
            if prev_band != 0:
                set_alert_threshold(key, 0)
            continue

        moved_further = (band > 0 and band > prev_band) or (band < 0 and band < prev_band)
        if not moved_further:
            continue

        side = "overweight" if drift > 0 else "underweight"
        lines.append(f"{bucket}: {current:.1f}% vs {target}% target ({side} {drift:+.1f}pt)")
        fired.append((key, band))
        log.info(f"Alloc alert {bucket}: {current:.1f}% (band {prev_band} -> {band})")

    if lines:
        send_message(
            "Allocation drift alert\n\nRebalance toward 50/30/20:\n" + "\n".join(lines),
            disclaimer=False,
        )
        for key, band in fired:
            set_alert_threshold(key, band)


if __name__ == "__main__":
    if not is_market_open():
        log.info("Market closed, exiting.")
    else:
        check_moves()
        check_allocation()
