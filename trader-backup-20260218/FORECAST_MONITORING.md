# Forecast Monitoring System

## Overview

The forecast monitoring system implements **Position Thesis Monitoring** - it re-validates all active positions against fresh forecast data every 4 hours. This is NOT a stop-loss based on price movement; it ensures the data that justified each trade still supports it.

## Key Principle

**We never exit because the market price moved against us. We only exit because our forecast data no longer supports the trade.**

> **Price is noise. Data is signal.**

## How It Works

### Monitoring Schedule

- **Frequency**: Every 4 hours
- **First check**: 4 hours after trade entry
- **Runs before**: New opportunity scanning and price-based early exits
- **Skip condition**: Positions within 2 hours of resolution (exit price would be poor)

### Data Sources

**US Markets:**
- NOAA
- Open-Meteo
- Visual Crossing

**Non-US Markets:**
- Open-Meteo
- Visual Crossing

### Three Outcomes

#### 1. HOLD ✓
- **Condition**: Forecasts unchanged, edge still > 5%
- **Action**: Do nothing
- **Log**: "Position check: [market] — forecasts unchanged, edge [X]%, holding"

#### 2. EXIT 🚨
- **Condition**: Forecasts shifted, edge dropped below 5%
- **Action**: Exit FULL position immediately at market price (FOK order)
  - Includes the "risk-free" half from any earlier 2× exit
  - If the thesis is broken, we exit everything
- **Reason**: The data that justified the trade no longer supports it
- **Log**: Full details including original vs new forecast, original vs new edge, exit price, P&L

#### 3. STRENGTHEN 📈
- **Condition**: Forecasts shifted in our favor, edge increased
- **Action**:
  - Log the new edge
  - If position now meets fresh entry criteria (edge > 10% US / 15% non-US, price 30-70¢, confidence > 80%)
  - AND we have room under the 10 active positions cap
  - Flag as "potential add opportunity" (do NOT auto-add)

## Implementation

### Files

1. **`forecast_monitor.py`** - Core monitoring logic
   - `ForecastMonitor` class - Manages 4-hour check cycles
   - `monitor_position_forecast()` - Re-validates single position
   - `execute_forecast_exit()` - Exits full position if thesis broken
   - `monitor_all_positions()` - Main monitoring loop
   - Journal logging with monitoring table

2. **Updated `early_exit_manager.py`**
   - Enhanced `Position` dataclass with forecast metadata:
     - `original_edge`: Edge at entry
     - `threshold_temp_f`: Market threshold temperature
     - `city`, `market_date`: For forecast re-fetching
     - `is_us_market`: Determines which sources to use
     - `forecast_sources`: Original sources used

3. **Updated `autonomous_trader_v2.py`**
   - STEP 0: Forecast monitoring (runs first)
   - Stores metadata when creating positions
   - Extracts threshold from market question

4. **Updated `weather_scanner_supervised.py`**
   - Checks forecasts before price-based exits
   - Runs during scheduled scans

## Execution Flow

```
START SCAN CYCLE
  ↓
STEP 0: Forecast Monitoring (every 4 hours)
  ↓
  For each active position:
    - Fetch fresh forecasts from all sources
    - Recalculate edge vs current price
    - Determine: HOLD / EXIT / STRENGTHEN
  ↓
  If EXIT:
    - Sell FULL position (FOK order)
    - Log P&L and reason
    - Remove from tracker
  ↓
  If STRENGTHEN:
    - Log opportunity
    - Flag for potential add
  ↓
STEP 1: Early Exit Check (2× price)
  ↓
STEP 2: Scan for New Opportunities
```

## Journal Format

### Position Monitor Table

```markdown
## POSITION MONITOR — 14:30:15

| Market | Entry Price | Current Price | Original Edge | Current Edge | Forecast Change | Action |
|--------|-------------|---------------|---------------|--------------|-----------------|--------|
| Chicago - 2026-02-18 | 30¢ | 42¢ | 12.5% | 8.2% | Forecasts shifted 2°C lower | ✓ HOLD |
| Miami - 2026-02-19 | 45¢ | 48¢ | 15.0% | 3.5% | Forecasts shifted 5°C lower | 🚨 EXIT |
| NYC - 2026-02-20 | 35¢ | 38¢ | 10.0% | 18.5% | Forecasts shifted 3°C higher | 📈 STRENGTHEN |
```

### Forecast Details

```markdown
### Forecast Details

**Miami - 2026-02-19** (EXITED):
- Forecasts shifted against us (edge dropped 11.5%) — edge now 3.5% (below 5% threshold)
- Exit order: xyz789...
- P&L: -$1.20

**NYC - 2026-02-20** (STRENGTHENED):
- Forecasts shifted in our favor (edge increased 8.5%)
- Potential add opportunity (if criteria met and capacity available)
```

## Examples

### Example 1: HOLD

```
Position: Chicago - 2026-02-18
  Entry: 10.0 shares @ 30¢ ($3.00)
  Current price: 42¢
  Fetching fresh forecasts...
  Sources: noaa, open-meteo, visualcrossing (3 sources)
  Consensus: 26.5°C (confidence: 85%)
  Original edge: 12.5%
  Current edge: 8.2%
  Forecasts unchanged
  Action: HOLD

✓ Edge still above 5% threshold, position remains valid
```

### Example 2: EXIT

```
Position: Miami - 2026-02-19
  Entry: 15.0 shares @ 45¢ ($6.75)
  Current price: 48¢
  Fetching fresh forecasts...
  Sources: open-meteo, visualcrossing (2 sources)
  Consensus: 22.0°C (was 27.0°C)
  Original edge: 15.0%
  Current edge: 3.5%
  Forecasts shifted against us (edge dropped 11.5%) — edge now 3.5% (below 5% threshold)
  Action: EXIT

    🚨 FORECAST EXIT TRIGGERED
    Reason: Forecasts shifted against us — edge now 3.5% (below 5% threshold)
    Market: Miami - 2026-02-19
    Exiting FULL position: 15.0 shares @ 48¢
    Cost basis: $6.75
    Expected proceeds: $7.20
    P&L: +$0.45

    ✅ FULL EXIT EXECUTED
    Order ID: abc123...
    Status: Position closed, thesis no longer supported by data
```

### Example 3: STRENGTHEN

```
Position: NYC - 2026-02-20
  Entry: 12.0 shares @ 35¢ ($4.20)
  Current price: 38¢
  Fetching fresh forecasts...
  Sources: noaa, open-meteo, visualcrossing (3 sources)
  Consensus: 31.0°C (was 28.0°C)
  Original edge: 10.0%
  Current edge: 18.5%
  Forecasts shifted in our favor (edge increased 8.5%)
  Action: STRENGTHEN

📈 Position strengthened - potential add opportunity if criteria met and capacity available
```

## State Management

The `ForecastMonitor` tracks:

```json
{
  "last_forecast_check": "2026-02-16T14:30:15",
  "forecast_checks": [
    {
      "position_token_id": "123456",
      "market_name": "Miami - 2026-02-19",
      "check_time": "2026-02-16T14:30:15",
      "entry_price": 0.45,
      "current_price": 0.48,
      "original_edge": 15.0,
      "current_edge": 3.5,
      "forecast_change_summary": "Forecasts shifted 5°C lower",
      "action": "EXIT",
      "exit_executed": true,
      "exit_order_id": "abc123...",
      "exit_pnl": 0.45
    }
  ]
}
```

## Benefits

1. **Data-Driven Exits**: Exit when the fundamental thesis changes, not just price movement
2. **Early Risk Management**: Catch thesis failures before reaching 2× or resolution
3. **Opportunity Detection**: Identify strengthening positions for potential adds
4. **Audit Trail**: Complete log of forecast changes and decisions
5. **Performance Analysis**: Track how often forecasts change vs. initial entry

## Comparing Exit Strategies

### Forecast Exit vs Early Exit

**Forecast Exit (Thesis-Based)**
- Trigger: Edge drops below 5%
- Exit: FULL position (including "risk-free" half)
- Reason: Data no longer supports the trade
- Example: Forecasts shifted from 85°F to 75°F, edge dropped from 12% → 3%

**Early Exit (Price-Based)**
- Trigger: Price reaches 2× entry
- Exit: HALF position to recover cost
- Reason: Lock in guaranteed profit
- Example: Entered at 30¢, price hits 60¢, sell half

**Both can apply**: A position might hit 2× (partial exit), then later fail forecast check (exit remaining half).

## Analysis Over Time

Track these metrics:

- **Forecast change frequency**: How often do forecasts shift significantly?
- **Exit accuracy**: Were forecast exits correct? (Did markets resolve against us?)
- **False exits**: Did we exit positions that would have won?
- **Saved losses**: How much did forecast exits save us?
- **Optimal threshold**: Is 5% edge the right threshold, or should we adjust?

## Configuration

Current settings:

- **Check interval**: 4 hours
- **Exit threshold**: Edge < 5%
- **Strengthen threshold**: Edge > 15% (for flagging adds)
- **Skip window**: 2 hours before resolution
- **Exit type**: FOK market orders (full position)

## Troubleshooting

### Forecast check not running?
- Check `last_forecast_check` in state file
- Must be ≥ 4 hours since last check
- Positions must exist

### Can't fetch fresh forecasts?
- Ensure weather API access
- Check city/date matching
- Verify sources are responding

### Edge calculation seems wrong?
- Verify `threshold_temp_f` stored correctly in position
- Check forecast temperature units (°C vs °F)
- Ensure side (YES/NO) is correct

### Position not exiting at < 5% edge?
- Check that edge calculation is working
- Verify forecast data is fresh
- Look for errors in console output

## Future Enhancements

1. **Adaptive thresholds**: Adjust exit threshold based on market type
2. **Forecast quality scoring**: Weight sources by historical accuracy
3. **Multi-market correlation**: Consider related markets when validating thesis
4. **Auto-add on strengthen**: Automatically add to strengthening positions (with user approval)
5. **Extended to other markets**: Apply thesis monitoring to non-weather markets with different check intervals
