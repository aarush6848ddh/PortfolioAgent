#!/bin/bash
# Kill the wrapper and bot, then restart cleanly.
echo "Stopping bot..."
pkill -f "run_bot.sh" 2>/dev/null
sleep 1
pkill -9 -f "python.*bot.py" 2>/dev/null
sleep 1

# Verify killed
if pgrep -f "python.*bot.py" > /dev/null; then
    echo "ERROR: Bot still running. Try: kill -9 $(pgrep -f 'python.*bot.py')"
    exit 1
fi

echo "Starting bot..."
cd /home/aarushs684/portfolioagent
nohup bash run_bot.sh &
sleep 2

if pgrep -f "python.*bot.py" > /dev/null; then
    echo "Bot is running (PID: $(pgrep -f 'python.*bot.py'))"
else
    echo "ERROR: Bot failed to start. Check bot.log"
    tail -10 bot.log
    exit 1
fi
