#!/usr/bin/env bash
# Trader Instance Monitor
# Checks that exactly 1 autonomous_trader_v2.py process is running.
# Sends a Telegram alert if count != 1.
# Run via cron every 10 minutes.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$HOME/.tinyclaw/logs/trader-monitor.log"
STATE_FILE="/tmp/trader-monitor-last-state"

# Telegram config
BOT_TOKEN="$(jq -r '.channels.telegram.bot_token // empty' "$HOME/.tinyclaw/settings.json" 2>/dev/null)"
CHAT_ID="8463145663"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

send_alert() {
    local message="$1"
    if [ -n "$BOT_TOKEN" ] && [ -n "$CHAT_ID" ]; then
        curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
            -d chat_id="$CHAT_ID" \
            -d text="$message" \
            -d parse_mode="Markdown" > /dev/null 2>&1
        log "ALERT sent: $message"
    else
        log "ALERT (no telegram): $message"
    fi
}

# Count trader processes (only python3, exclude shell/grep matches)
COUNT=$(pgrep -xc -f "python3 .*autonomous_trader_v2.py" 2>/dev/null || echo "0")

# Read previous state to avoid repeated alerts
PREV_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo "unknown")
CURR_STATE="ok"

if [ "$COUNT" -eq 1 ]; then
    CURR_STATE="ok"
    if [ "$PREV_STATE" != "ok" ]; then
        log "OK: Trader back to normal (1 instance)"
        send_alert "✅ *Trader Monitor*: Back to normal — 1 instance running."
    fi
elif [ "$COUNT" -eq 0 ]; then
    CURR_STATE="zero"
    if [ "$PREV_STATE" != "zero" ]; then
        log "ALERT: No trader instances running!"
        send_alert "⚠️ *Trader Monitor*: No trader process detected! The autonomous trader is not running."
    fi
elif [ "$COUNT" -gt 1 ]; then
    CURR_STATE="duplicate"
    if [ "$PREV_STATE" != "duplicate" ]; then
        PIDS=$(pgrep -x -f "python3 .*autonomous_trader_v2.py" | tr '\n' ' ')
        log "ALERT: $COUNT trader instances running! PIDs: $PIDS"
        send_alert "🔴 *Trader Monitor*: $COUNT trader instances detected (PIDs: $PIDS). Kill duplicates with: \`kill <PID>\`"
    fi
fi

echo "$CURR_STATE" > "$STATE_FILE"
