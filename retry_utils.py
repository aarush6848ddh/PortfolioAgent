"""Retry helper for network calls — rides out the ~2min WiFi roam gaps."""
import time
import logging

log = logging.getLogger("retry")

# Backoff between attempts: 4 total tries (1 initial + 3 retries).
DELAYS = (2, 8, 30)


def retry_call(fn, *args, what="call", **kwargs):
    for attempt, delay in enumerate(DELAYS, start=1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            log.warning(
                f"{what} failed (attempt {attempt}/{len(DELAYS) + 1}): "
                f"{type(e).__name__}: {e} — retrying in {delay}s"
            )
            time.sleep(delay)
    # Final attempt: let the real exception propagate with full traceback
    return fn(*args, **kwargs)
