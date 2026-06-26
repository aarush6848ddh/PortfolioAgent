#!/bin/bash
# Auto-restarting wrapper for the Telegram bot.
# Started via @reboot crontab.
cd /home/aarushs684/portfolioagent
source venv/bin/activate
while true; do
    echo "[$(date)] Bot starting..." >> bot.log
    python -u bot.py >> bot.log 2>&1
    EXIT_CODE=$?
    echo "[$(date)] Bot exited (code $EXIT_CODE), restarting in 10s..." >> bot.log
    sleep 10
done
