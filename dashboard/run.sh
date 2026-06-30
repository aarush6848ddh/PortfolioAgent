#!/bin/bash
cd ~/portfolioagent/dashboard

kill_port() {
    lsof -ti:3000 | xargs kill -9 2>/dev/null
    sleep 1
}

health_check() {
    while true; do
        sleep 60
        # Check if a JS chunk returns 200 (not 500)
        STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://localhost:3000)
        if [ "$STATUS" != "200" ]; then
            echo "[$(date)] Health check failed (HTTP $STATUS), restarting..."
            kill_port
            return 1
        fi
    done
}

while true; do
    echo "[$(date)] Killing any stale process on port 3000..."
    kill_port
    echo "[$(date)] Starting dashboard..."
    npx next start --port 3000 2>&1 &
    NEXT_PID=$!
    sleep 5
    health_check &
    HC_PID=$!
    wait $NEXT_PID
    kill $HC_PID 2>/dev/null
    echo "[$(date)] Dashboard exited, restarting in 3s..."
    sleep 3
done
