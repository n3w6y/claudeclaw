# Position Thesis Monitoring

## Overview

Every 4 hours, the system re-checks all active positions against fresh forecast data. This is **not a stop-loss** based on price movement - it's verification that the data justifying each trade still supports it.

## Monitoring Rules

### Check Frequency
- **Every 4 hours** for weather positions
- First check: 4 hours after trade entry
- Skip if position resolves within 2 hours

### Data Sources
- **US markets**: NOAA + Open-Meteo + Visual Crossing (3 sources)
- **International markets**: Open-Meteo + Visual Crossing (2 sources)

### Actions

#### 1. HOLD (Edge still > 5%)
- Forecasts unchanged or minor shift
- Edge remains above 5% threshold
- **Action**: Do nothing
- **Log**: "Position check: [market] — forecasts unchanged, edge [X]%, holding"

#### 2. EXIT (Edge dropped below 5%)
- Forecasts shifted significantly
- Edge now below 5% threshold
- **Action**: Exit FULL position immediately (FOK order)
- **Reason**: The data that justified the trade no longer supports it
- **Log**: Full details including forecast changes, edge change, exit price, P&L

#### 3. STRENGTHEN (Edge increased significantly)
- Forecasts shifted in our favor
- Edge increased by 10%+
- **Action**: Log the improvement
- **Consider**: Adding second position if meets fresh entry criteria and under 10 position cap
- **Log**: New edge and potential add opportunity

## Key Principles

### Price is Noise, Data is Signal
- **We NEVER exit because market price moved against us**
- **We ONLY exit because forecast data no longer supports the trade**
- Market price movements are ignored - only forecast changes matter

### Exit Everything on Broken Thesis
- If forecasts shift and edge collapses, exit the FULL position
- This includes any "risk-free" portions from partial exits
- If the thesis is broken, we don't want ANY exposure

## Implementation

### File Structure
```
position_monitor.py          # Main monitoring script
active_positions.json        # Current positions cache
journal/YYYY-MM-DD.md       # Daily logs with monitor results
```

### Log Format
```markdown
## POSITION MONITOR - HH:MM:SS

| Market | Entry Price | Current Price | Original Edge | Current Edge | Forecast Change | Action |
|--------|-------------|---------------|---------------|--------------|-----------------|--------|
| [name] | [X]¢ | [Y]¢ | [X]% | [Y]% | [summary] | HOLD/EXIT/FLAG |

### Forecast Details (if changed)
- [Market]: [source] shifted from [old temp] to [new temp]. Threshold: [X]°F.
```

### Example Monitor Cycle

**Entry**:
- Market: Miami Feb 16 ≤81°F
- Entry: 30¢ YES
- Forecast: 79.7°F (Open-Meteo: 80.6°F, VC: 78.1°F, NOAA: 81.0°F)
- Edge: +54.5%

**4 Hours Later - HOLD**:
- Fresh forecast: 79.5°F (Open-Meteo: 80.2°F, VC: 78.3°F, NOAA: 80.0°F)
- Current edge: +52.1%
- Action: HOLD (edge still > 5%, minor forecast change)

**8 Hours Later - EXIT**:
- Fresh forecast: 83.2°F (Open-Meteo: 83.0°F, VC: 83.5°F, NOAA: 83.1°F)
- Current edge: -12.3% (now AGAINST us)
- Action: EXIT (forecast shifted above threshold, edge collapsed)
- Exit at market price immediately

## Order Monitoring (GTC + TTL)

**Added Feb 16, 2026** — All new trades use GTC maker orders with 30-minute TTL.

### Check Frequency
- **Every 5 minutes** for open GTC orders
- Runs independently from position monitoring

### Tracked Data
Each open order tracked in `open_orders.json`:
- Order ID, market, side, price, amount
- Time placed, TTL expiry (30 minutes)
- Status: OPEN | FILLED | CANCELLED

### Actions

#### 1. FILLED
- Order executed by market taker
- **Action**: Log position to positions_state.json, remove from open orders
- **Log**: Full fill details including actual fill price and timestamp

#### 2. TTL EXPIRED (30 minutes)
- Order still open after 30 minutes
- **Action**: Cancel order immediately, free locked funds
- **Log**: "TTL_EXPIRED" cancellation with order details

#### 3. STILL OPEN
- Order waiting on book, TTL not expired
- **Action**: Continue waiting, check again in 5 minutes
- **Log**: No action needed

### Guardrails
- **Max 3 open orders** at once (prevent capital lockup)
- **One order per market** (no duplicate exposure)
- **30-minute hard limit** (all orders auto-cancel)

## Running the Strategy

### Manual Check
```bash
python3 position_monitor.py
python3 order_monitor.py  # NEW: Check open GTC orders
```

### Automated (with scanning)
```bash
./run_weather_strategy.sh
```

This runs:
- **Order monitoring every 5 minutes** (open GTC orders)
- Position monitoring every 4 hours (active positions)
- Opportunity scanning every 2 hours
- Order monitoring runs FIRST (most frequent)

## Future Extensions

This monitoring framework will extend to other market types:
- **Weather**: 4 hour intervals (current)
- **Sports**: 1 hour intervals (odds change fast)
- **Politics**: 12 hour intervals (polls update daily)
- **Crypto**: 30 minute intervals (price-driven data)

Check intervals vary by how fast the underlying data changes.
