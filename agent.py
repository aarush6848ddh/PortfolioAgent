"""Portfolio intelligence agent — entry point for cron jobs.

Modes:
  --morning    Pre-market briefing (8:55 AM ET) — includes disclaimer
  (default)    Intraday check (every 30 min during market hours)
  --summary    End-of-day summary (4:05 PM ET)
  --friday     Friday EOD weekly P&L digest (4:35 PM ET Friday)
  --weekly     Weekend digest (Saturday 9 AM ET) — full report with charts
"""
import sys
import logging
from portfolio import is_market_open, log_run
from orchestrator import run_agents
from tg_helpers import send_message, send_photo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("agent")


def morning_briefing():
    response = run_agents("morning")
    log_run("morning", "multi-agent pipeline", response, True, "morning briefing always sent")
    send_message(f"Good morning.\n\n{response}", disclaimer=True)


def intraday_check():
    if not is_market_open():
        print("Market closed, exiting.")
        return

    response = run_agents("intraday")
    is_silent = response.strip() == "SILENT"

    if is_silent:
        log_run("intraday", "multi-agent pipeline", response, False, "nothing notable — agent chose SILENT")
    else:
        log_run("intraday", "multi-agent pipeline", response, True, "agent flagged something notable")
        send_message(response, disclaimer=False)


def daily_summary():
    response = run_agents("daily")
    log_run("daily", "multi-agent pipeline", response, True, "daily summary always sent")
    send_message(response, disclaimer=False)


def friday_eod():
    response = run_agents("friday_eod")
    log_run("friday_eod", "multi-agent pipeline", response, True, "friday eod digest always sent")
    send_message(f"Weekly P&L Digest\n\n{response}", disclaimer=False)


def weekly_digest():
    response = run_agents("weekly")
    log_run("weekly", "multi-agent pipeline", response, True, "weekly digest always sent")
    send_message(f"Weekly Digest\n\n{response}", disclaimer=False)

    # Generate and send charts
    try:
        from reports import generate_weekly_report
        chart_paths = generate_weekly_report()
        for path in chart_paths:
            send_photo(path)
            log.info(f"Sent chart: {path}")
    except Exception as e:
        log.error(f"Failed to generate/send charts: {e}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "intraday"

    try:
        if mode == "--morning":
            morning_briefing()
        elif mode == "--summary":
            daily_summary()
        elif mode == "--friday":
            friday_eod()
        elif mode == "--weekly":
            weekly_digest()
        else:
            intraday_check()
    except Exception as e:
        # Graceful degradation: the failure alert must NOT depend on the LLM
        # (a Groq rate limit is the most likely cause of failure here).
        log.exception(f"Agent run failed (mode={mode})")
        err = f"{type(e).__name__}: {e}"
        try:
            send_message(f"Agent run failed ({mode}).\n{err[:500]}", disclaimer=False)
        except Exception:
            log.exception("Failed to send failure alert to Telegram")
        sys.exit(1)
