#!/bin/bash
# Weather Arbitrage Strategy Runner
# - Order monitoring every 5 minutes (GTC orders)
# - Position monitoring every 4 hours (active positions)
# - Opportunity scanning every 2 hours
# - Order monitoring runs FIRST (most frequent)

cd /home/andrew/claudeclaw/trader

LAST_ORDER_CHECK=0
LAST_POSITION_MONITOR=0
LAST_SCAN=0
ORDER_CHECK_INTERVAL=300      # 5 minutes
POSITION_MONITOR_INTERVAL=14400  # 4 hours
SCAN_INTERVAL=7200            # 2 hours

echo "🌡️  WEATHER ARBITRAGE STRATEGY STARTED"
echo "   Order check interval: 5 minutes"
echo "   Position monitor interval: 4 hours"
echo "   Scan interval: 2 hours"
echo ""

while true; do
    NOW=$(date +%s)

    # Check open GTC orders (every 5 minutes)
    if [ $((NOW - LAST_ORDER_CHECK)) -ge $ORDER_CHECK_INTERVAL ]; then
        echo "========================================"
        echo "Checking open orders at $(date)"
        echo "========================================"

        python3 order_monitor.py

        LAST_ORDER_CHECK=$NOW
        echo ""
    fi

    # Check if it's time for position monitoring (every 4 hours)
    if [ $((NOW - LAST_POSITION_MONITOR)) -ge $POSITION_MONITOR_INTERVAL ]; then
        echo "========================================"
        echo "Running position monitor at $(date)"
        echo "========================================"

        python3 position_monitor.py

        LAST_POSITION_MONITOR=$NOW
        echo ""
    fi

    # Check if it's time for opportunity scanning (every 2 hours)
    if [ $((NOW - LAST_SCAN)) -ge $SCAN_INTERVAL ]; then
        echo "========================================"
        echo "Running opportunity scan at $(date)"
        echo "========================================"

        python3 weather_scanner_supervised.py

        LAST_SCAN=$NOW
        echo ""
        echo "Next scan in 2 hours ($(date -d '+2 hours'))"
        echo ""
    fi

    # Sleep for 1 minute before checking again
    sleep 60
done
