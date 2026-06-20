#!/bin/bash
# Auto-restarting wrapper for the interactive Telegram bot.
# Started via @reboot crontab — no systemd/sudo required.
cd /home/aarushs684/portfolioagent
source venv/bin/activate
while true; do
    python bot.py >> /home/aarushs684/portfolioagent/bot.log 2>&1
    echo "[$(date)] Bot exited, restarting in 5s..." >> /home/aarushs684/portfolioagent/bot.log
    sleep 5
done
