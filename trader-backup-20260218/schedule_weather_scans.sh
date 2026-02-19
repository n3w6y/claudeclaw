#!/bin/bash
# Schedule weather arbitrage scans every 2 hours
# Usage: ./schedule_weather_scans.sh

cd /home/andrew/claudeclaw/trader

while true; do
    echo "========================================"
    echo "Running weather scan at $(date)"
    echo "========================================"

    python3 weather_scanner_supervised.py

    echo ""
    echo "Next scan in 2 hours ($(date -d '+2 hours'))"
    echo ""

    # Sleep for 2 hours (7200 seconds)
    sleep 7200
done
