"""Portfolio intelligence agent — entry point for cron jobs.

Modes:
  --morning   Pre-market briefing (8:55 AM ET) — includes disclaimer
  (default)   Intraday check (every 30 min during market hours)
  --summary   End-of-day summary (4:05 PM ET)
  --weekly    Weekend digest (Saturday 9 AM ET / Friday after close)

All reasoning flows through the multi-agent orchestrator:
  data_agent + news_agent + quant_agent -> synthesis_agent
"""
import sys
from portfolio import is_market_open, log_run
from orchestrator import run_agents
from tg_helpers import send_message


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


def weekly_digest():
    response = run_agents("weekly")
    log_run("weekly", "multi-agent pipeline", response, True, "weekly digest always sent")
    send_message(f"Weekly Digest\n\n{response}", disclaimer=False)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "intraday"

    if mode == "--morning":
        morning_briefing()
    elif mode == "--summary":
        daily_summary()
    elif mode == "--weekly":
        weekly_digest()
    else:
        intraday_check()
