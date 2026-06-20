"""Market sentiment — Fear & Greed Index."""
import fear_and_greed


def get_fear_greed():
    """Get current CNN Fear & Greed Index.
    Returns dict with score (0-100) and rating, or None on failure."""
    try:
        data = fear_and_greed.get()
        score = round(data.value, 1)
        rating = data.description  # 'extreme fear', 'fear', 'neutral', 'greed', 'extreme greed'

        # Educational context for a beginner
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

        return {
            "score": score,
            "rating": rating,
            "context": context,
        }
    except Exception:
        return None


def format_fear_greed(fg):
    """Format for prompt inclusion."""
    if not fg:
        return "Fear & Greed Index: unavailable"
    return f"Fear & Greed Index: {fg['score']}/100 ({fg['rating']}) — {fg['context']}"
