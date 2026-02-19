# New Trading Rules - Forecast Convergence Strategy

**Effective**: Feb 16, 2026
**Replaces**: Previous hold-to-resolution strategy

---

## Core Principle

**You are NOT holding to resolution. You are trading forecast convergence.**

Profit from the market repricing as forecasts solidify. Enter on edge, exit on profit target, stop loss, or edge evaporation. **Never hold to close.**

---

## Entry Rules (Unchanged)

1. **Minimum edge**: 20% between forecast probability and market price
2. **Position size**: $5 per position (Tier 1 - until account grows)
3. **Max positions**: 10 simultaneous positions allowed
4. **Price range**: 30-70¢ (avoid extreme prices)
5. **Forecast quality**:
   - US markets: 3 sources (NOAA, Open-Meteo, Visual Crossing)
   - Non-US markets: 2 sources agreeing within 1°C

---

## Exit Rules (NEW - All Active Simultaneously)

### 1. Profit Target: +30% Gain → EXIT
- **Trigger**: Position value reaches 130% of cost basis
- **Example**: Bought for $5.00 → Exit at $6.50
- **Action**: SELL IMMEDIATELY at market (FOK or GTC)
- **Rationale**: Lock gains, don't get greedy

### 2. Stop Loss: -20% Drawdown → EXIT
- **Trigger**: Position value drops 20% from entry cost
- **Example**: Bought for $5.00 → Exit if value drops to $4.00
- **Action**: SELL IMMEDIATELY at market (FOK or GTC)
- **Rationale**: Cut losses early, preserve capital
- **No exceptions**: Loss aversion kills traders - take the L and move on

### 3. Edge Evaporation: Edge < 10% → EXIT
- **Trigger**: Recalculated edge vs market price drops below 10%
- **Action**: Re-check forecasts, recalculate edge, EXIT if <10%
- **Timing**: Check on every position monitoring cycle (every 2 hours)
- **Rationale**: If edge is gone, position has no value
- **Regardless of P&L**: If edge <10%, exit even if profitable

---

## Position Monitoring (NEW - Critical)

### Frequency: Every 2 Hours

**Actions per check**:
1. Pull fresh forecasts from all sources
2. Get current market price via API
3. Recalculate edge (forecast_prob - market_price)
4. Check all three exit conditions:
   - Value ≥ 130% cost? → Profit target
   - Value ≤ 80% cost? → Stop loss
   - Edge < 10%? → Edge evaporation
5. Log monitoring check to journal

**Journal format**:
```
## Position Monitor - HH:MM:SS

Market: City - Date
Entry: SIDE @ XX¢, shares, cost
Current price: XX¢
Current value: $X.XX
P&L: $±X.XX (±XX%)
Fresh forecast: X°C (sources: A, B, C)
Recalculated edge: XX%
Action: HOLD | EXIT (reason)
```

---

## Never Hold to Resolution

**Hard rule**: Do NOT hold any position into its resolution window

- **Resolution window**: <4 hours until market closes
- **Action**: If market resolves in <4 hours and you haven't exited, EXIT AT MARKET
- **Rationale**: Profit comes from market repricing, not resolution payoff
- **Example**: Market resolves Feb 17 at 12:00 PM
  - Must exit by Feb 17 at 8:00 AM
  - Don't wait for resolution - exit earlier if profit/loss/edge triggers hit

---

## Implementation

### Files to Update

1. **`position_monitor.py`** (or create new)
   - Run every 2 hours (not 4 hours)
   - Pull fresh forecasts
   - Recalculate edge
   - Check all 3 exit conditions
   - Execute exits immediately
   - Log to journal

2. **`autonomous_trader_v2.py`**
   - Update entry criteria: 20% min edge (was 10-15%)
   - Update max positions: 10 (unchanged)
   - Remove hold-to-resolution logic

3. **`early_exit_manager.py`**
   - Update exit trigger: +30% gain (was 2x price)
   - Add stop loss: -20% drawdown
   - Add edge check: exit if <10%

4. **`run_weather_strategy.sh`**
   - Position monitoring: Every 2 hours (was 4)
   - Order monitoring: Every 5 minutes (unchanged)
   - Opportunity scanning: Every 2 hours (unchanged)

---

## Examples

### Example 1: Profit Target Hit

```
Entry: BUY NO @ 45¢, $5.00 cost
Day 1: Price moves to 35¢ → Value $6.43 (+28.6%) → HOLD
Day 2: Price moves to 32¢ → Value $7.03 (+40.6%) → EXIT
Action: SELL at market, lock $2.03 profit
```

### Example 2: Stop Loss Hit

```
Entry: BUY YES @ 60¢, $5.00 cost
Hour 2: Price drops to 50¢ → Value $4.17 (-16.6%) → HOLD
Hour 4: Price drops to 47¢ → Value $3.92 (-21.6%) → EXIT
Action: SELL at market, take -$1.08 loss
```

### Example 3: Edge Evaporation

```
Entry: BUY NO @ 35¢, edge 25% (forecast 10%, market 35%)
Hour 2: Check forecast → Now 28% (edge 7%) → EXIT
Action: SELL regardless of P&L
Reason: Edge gone, holding has no value
```

### Example 4: Never Hold to Close

```
Entry: Feb 15 at 8 AM, market resolves Feb 17 at 12 PM
Feb 17 at 7 AM: 5 hours to resolution, position +15% → EXIT
Reason: <4 hours to close, take the 15% gain
```

---

## Monitoring Schedule

| Task | Frequency | Purpose |
|------|-----------|---------|
| Order monitoring | 5 minutes | Check GTC fills/expiries |
| Position monitoring | **2 hours** | Check exit conditions |
| Opportunity scanning | 2 hours | Find new entries |

---

## Key Mindset Shifts

### OLD (Wrong):
- ❌ Hold to resolution to capture full payoff
- ❌ "Market is wrong, I'll wait for them to realize"
- ❌ Let losses run, they might recover
- ❌ Check positions once per day

### NEW (Correct):
- ✅ Exit on profit target, stop loss, or edge loss
- ✅ "Edge is gone → position has no value"
- ✅ Cut losses at -20%, no exceptions
- ✅ Monitor every 2 hours, exit immediately on triggers
- ✅ Profit comes from repricing, not resolution

---

## Performance Tracking

After implementing new rules, track:

1. **Exit reason distribution**:
   - Profit target: X%
   - Stop loss: X%
   - Edge evaporation: X%
   - Time to resolution: X%

2. **Average hold time**: Should be 1-3 days, not full market duration

3. **Win rate**: Should improve with -20% stop loss

4. **Average winner vs average loser**: Target +30% winners vs -20% losers

---

**These rules override all previous hold-to-resolution guidance. Implement immediately.**
