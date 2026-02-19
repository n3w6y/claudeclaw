# Quick Start: GTC Trading System

## TL;DR

Weather markets use **GTC maker orders with 30-minute TTL** instead of FOK.

Orders sit on the book waiting to be filled. They auto-cancel after 30 minutes if not filled.

---

## Commands

### Place orders (finds opportunities, places up to 3 GTC orders)
```bash
python3 autonomous_trader_v2.py
```

### Check order status (runs every 5 min in production)
```bash
python3 order_monitor.py
```

### Run full strategy (automated loop)
```bash
./run_weather_strategy.sh
```

### Test the flow (demo only)
```bash
python3 test_gtc_flow.py
```

---

## What Changed?

**Before**: FOK orders failed (0% fill rate on weather markets)
**After**: GTC orders sit on book with 30-min expiry

---

## Files to Check

**Trading state (Mission Control)**: `polymarket-trader/trading_state.json` 🔥
```bash
cat polymarket-trader/trading_state.json | jq '.'
```
This is the **single source of truth** for the dashboard. Updated after every trading action.

**Open orders**: `polymarket-trader/open_orders.json`
```bash
cat polymarket-trader/open_orders.json | jq '.'
```

**Active positions**: `polymarket-trader/positions_state.json`
```bash
cat polymarket-trader/positions_state.json | jq '.positions'
```

**Today's log**: `polymarket-trader/journal/YYYY-MM-DD.md`
```bash
tail -50 polymarket-trader/journal/$(date +%Y-%m-%d).md
```

---

## Order Lifecycle

```
1. PLACED (autonomous_trader_v2.py)
   ↓
2. TRACKED (open_orders.json with 30-min TTL)
   ↓
3. MONITORED (order_monitor.py every 5 min)
   ↓
4. THREE OUTCOMES:

   A. FILLED
      → Position created in positions_state.json
      → Removed from open_orders.json
      → Logged to journal

   B. TTL EXPIRED (30 min)
      → Order cancelled via API
      → Marked CANCELLED in open_orders.json
      → Funds freed for next trade

   C. STILL OPEN
      → Continue waiting
      → Check again in 5 minutes
```

---

## Guardrails

- **Max 3 open orders** at once
- **One order per market** (no duplicates)
- **30-minute auto-cancel** (no locked funds)
- **5-minute checks** (fast reaction)

---

## Expected Behavior

**Good**: Order placed → sits on book → fills in 5-25 min → position tracked
**Normal**: Order placed → sits on book → expires at 30 min → funds freed
**Bad**: Order placed → immediate error → not tracked

Weather markets have wide spreads, so expiries are normal. The system handles them automatically.

---

## Monitoring in Production

The `run_weather_strategy.sh` script runs:

| Task | Frequency | Purpose |
|------|-----------|---------|
| Order monitor | 5 minutes | Check fills/expirations |
| Position monitor | 4 hours | Forecast validation |
| Opportunity scan | 2 hours | Find new trades |

Leave it running in screen/tmux for 24/7 operation.

---

## Troubleshooting

**No opportunities found**:
- Normal - weather markets need 10-15% edge with 3 sources (US) or 15%+ edge with 2 sources (non-US)
- Prices must be 30-70¢
- Most opportunities are 0-5¢ (too extreme) or 85-100¢ (mispriced the other way)

**Order placed but never fills**:
- Expected - weather markets have 99¢ spreads with low taker activity
- Order will auto-cancel at 30 minutes
- Funds freed for next opportunity
- This is WHY we use GTC with TTL instead of FOK

**Balance unchanged after order**:
- Correct - GTC orders lock funds until filled or cancelled
- Check `open_orders.json` to see locked capital
- When order fills/cancels, balance updates

---

## Next Steps

1. ✅ Documentation updated (STRATEGY.md, POSITION_MONITORING.md)
2. ✅ Code implemented (autonomous_trader_v2.py, order_monitor.py)
3. ⏳ **Live test**: Place one $5 GTC order when opportunity appears
4. Monitor for 30 minutes
5. Observe: FILLED, TTL_EXPIRED, or STILL_OPEN outcome
6. Review logs in `journal/` directory

---

**Ready to trade** - just waiting for qualifying opportunities!
