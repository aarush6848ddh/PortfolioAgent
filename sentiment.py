"""Market sentiment — Fear & Greed Index with history tracking."""
import logging
from datetime import date, timedelta
import fear_and_greed
from portfolio import get_conn, get_alert_threshold, set_alert_threshold
from config import FEAR_THRESHOLD, FEAR_SUSTAINED_DAYS

log = logging.getLogger("sentiment")


def get_fear_greed():
    try:
        data = fear_and_greed.get()
        score = round(data.value, 1)
        rating = data.description

        if score <= 25:
            context = "Markets are very scared — historically, buying during extreme fear has been rewarding long-term, but it feels terrible in the moment."
        elif score <= 45:
            context = "Markets are cautious. Investors are worried but not panicking."
        elif score <= 55:
            context = "Markets are balanced — no strong emotion driving prices either way."
        elif score <= 75:
            context = "Markets are optimistic. Prices tend to be higher, so new money buys less."
        else:
            context = "Markets are euphoric — historically, extreme greed often precedes pullbacks. Not a prediction, just a pattern."

        return {"score": score, "rating": rating, "context": context}
    except Exception:
        return None


def format_fear_greed(fg):
    if not fg:
        return "Fear & Greed Index: unavailable"
    return f"Fear & Greed Index: {fg['score']}/100 ({fg['rating']}) — {fg['context']}"


def store_fear_greed(score, rating):
    """Store daily Fear & Greed reading."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO fear_greed_history (date, score, rating)
               VALUES (%s, %s, %s)
               ON CONFLICT (date) DO UPDATE SET score = %s, rating = %s""",
            (date.today(), score, rating, score, rating)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"Failed to store F&G: {e}")


def get_consecutive_fear_days():
    """Count consecutive days with F&G below FEAR_THRESHOLD, going back from today."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT date, score FROM fear_greed_history ORDER BY date DESC LIMIT 30"
        )
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return 0
        count = 0
        for row in rows:
            if float(row[1]) < FEAR_THRESHOLD:
                count += 1
            else:
                break
        return count
    except Exception as e:
        log.error(f"Failed to get fear streak: {e}")
        return 0


def check_sustained_fear():
    """Check if sustained fear alert should fire. Returns alert text or None.
    Only fires once per fear period — resets when F&G goes above threshold."""
    days = get_consecutive_fear_days()
    if days < FEAR_SUSTAINED_DAYS:
        if days == 0:
            set_alert_threshold("sustained_fear", 0)
        return None

    last = get_alert_threshold("sustained_fear")
    if last and float(last) >= 1:
        return None

    set_alert_threshold("sustained_fear", 1)
    return f"SUSTAINED FEAR: Market has been in fear (F&G below {FEAR_THRESHOLD}) for {days} consecutive days"


def get_avg_fear_greed(days=5):
    """Get average Fear & Greed score over the last N days."""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT AVG(score) FROM fear_greed_history WHERE date >= %s",
            (date.today() - timedelta(days=days),)
        )
        row = cur.fetchone()
        conn.close()
        return round(float(row[0]), 1) if row and row[0] else None
    except Exception as e:
        log.error(f"Failed to get avg F&G: {e}")
        return None
