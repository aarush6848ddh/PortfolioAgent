#!/bin/bash
cd ~/portfolioagent/dashboard
while true; do
    echo "[$(date)] Starting dashboard..."
    npx next start --port 3000 2>&1
    echo "[$(date)] Dashboard crashed, restarting in 3s..."
    sleep 3
done
