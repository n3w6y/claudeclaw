# TinyClaw Weather Trader — Rules & Operating Manual

**Version**: 2.0
**Effective**: 2026-02-19
**Replaces**: All previous versions. This is the ONLY rules document.

---

## Core Strategy

**Trade forecast convergence with consensus hold option.**

Enter positions when weather forecasts disagree with market pricing by ≥20%.
Exit on profit target, stop loss, or edge evaporation.
Hold to resolution ONLY when all sources unanimously agree with sufficient margin.

---

## 1. Entry Rules

### Position Criteria
- **Minimum edge**: 20% between forecast probability and market price
- **Position size**: Tiered by account balance:
  - < $100: $5 per position
  - $100–199: $10 per position
  - $200–499: $15 per position
  - $500+: $20 per position
- **Max simultaneous positions**: 10 (includes open GTC orders)
- **Price range**: 30–70¢ only (avoid extremes)
- **Time to resolution**: Must be > 4 hours at time of entry
- **No opposing sides**: Never hold YES and NO in the same market
- **No duplicate markets**: One position per conditionId
- **Max new orders per cycle**: 3

### Forecast Confidence Requirements

**US markets** (3 sources required):
- NOAA (local, weighted 40%)
- Open-Meteo (global, weighted 25%)
- Visual Crossing (global, weighted 35%)
- Minimum 80% confidence from ensemble

**Non-US markets WITH local national source** (3 sources required):
- Local national service (weighted 50%) — e.g. MetService (NZ), BOM (Australia)
- Open-Meteo (global, weighted 25%)
- Visual Crossing (global, weighted 25%)
- Minimum 80% confidence from ensemble

**Non-US markets WITHOUT local source** (2 sources required):
- Open-Meteo + Visual Crossing
- Minimum edge raised to 25% (higher bar due to lower confidence)
- Must agree within 1°C

### Disagreement Flag
If local national source and global model average disagree by > 2°C:
- Confidence capped at 50%
- This effectively blocks the trade (below 80% threshold)
- Rationale: local source is almost certainly right, global is wrong — but we
  don't know which direction the error falls, so don't trade

### Liquidity Check
- Check order book depth before entry
- Skip market if bid-side liquidity < $500
- Rationale: thin markets mean you can't exit at anything near quoted price

### Live Re-validation
- After initial scan identifies a candidate, pull live CLOB price
- Recalculate edge at live price — must still be ≥ 20% (or 25% for no-local markets)
- If edge has collapsed since Gamma API snapshot, skip

---

## 2. Exit Rules

Exit checks run in priority order. First match wins.

### Priority 0: Consensus Hold → HOLD TO RESOLUTION
**Runs FIRST — can override all other exits including the time exit.**

ALL of the following must be true:
- At least one local national source available (MetService, BOM, or NOAA)
- ALL forecast sources are on the same side of the threshold
  - NO position: every source forecasts BELOW threshold
  - YES position: every source forecasts AT OR ABOVE threshold
- Margin meets tiered threshold for time remaining:

| Time to resolution | Required margin (°C) | Required margin (°F) |
|---|---|---|
| 12–24 hours | 3°C | 5°F |
| 6–12 hours | 2°C | 4°F |
| < 6 hours | 1°C | 2°F |

- Position is at break-even or better (P&L ≥ -5%)
- Time to resolution is < 24 hours

If ALL conditions met: **HOLD TO RESOLUTION**, skip all other exits.
If ANY condition fails: fall through to normal exit logic below.

**Rationale**: When every source agrees with margin, the expected value of holding
to resolution ($0.90–0.97/share) exceeds selling early into thin liquidity (~$0.58/share
after slippage).

### Priority 1: Time Exit → SELL
- Trigger: < 4 hours to market resolution
- Action: Sell at market (GTC order)
- Rationale: Avoid binary resolution risk when consensus hold criteria aren't met

### Priority 2: Stop Loss → SELL
- Trigger: Position value ≤ 80% of cost basis (-20%)
- Example: Bought $5.00 → sell if value drops to $4.00
- Action: Sell immediately (GTC order)
- No exceptions. Loss aversion kills accounts.

### Priority 3: Edge Evaporation → SELL
- Trigger: Recalculated edge < 10%
- Action: Sell regardless of P&L
- Check: Pull fresh forecasts, recalculate edge vs current market price
- Rationale: If edge is gone, position has no informational value

### Priority 4: Profit Target → SELL
- Trigger: Position value ≥ 130% of cost basis (+30%)
- Example: Bought $5.00 → sell if value reaches $6.50
- Action: Sell (GTC order)
- Rationale: Lock gains when consensus hold conditions aren't met

---

## 3. Unit Handling

**Critical rule**: All margin and threshold comparisons must use the market's native unit.

- US markets resolve in °F
- Non-US markets resolve in °C
- All forecast sources store data internally in °C
- Convert to market's native unit ONLY at comparison points:
  1. Edge calculation (forecast probability vs market price)
  2. Consensus hold margin check
  3. Journal logging (display in market's unit)

**Never** apply a °C margin threshold to a °F market or vice versa.
A 3°C margin = 5.4°F. A 3°F margin = 1.7°C. Getting this wrong means
either being too conservative (°F threshold on °C market) or dangerously
loose (°C threshold on °F market).

---

## 4. Monitoring Schedule

| Task | Frequency | What it does |
|------|-----------|--------------|
| Order monitoring | 5 minutes | Check GTC order fills and expiries |
| Position monitoring | 10 minutes | Check all exit triggers for each position |
| Opportunity scanning | 2 hours | Scan for new entry opportunities |
| Forecast refresh | 2 hours | Pull fresh data from all sources |

---

## 5. Order Execution

- **Order type**: GTC (Good-Til-Cancelled) with 30-minute TTL
- **Maker orders only**: Place limit orders, never market orders
- **Sell orders**: Also GTC (NOT FOK — thin markets won't fill FOK)
- **Balance check**: Must account for capital locked in open GTC orders
  - `available_capital = balance - (open_order_count × position_size) - $5_buffer`

---

## 6. Position Sizing by Account Balance

| Balance | Position Size | Max Positions | Max Deployed |
|---------|--------------|---------------|-------------|
| < $100 | $5 | 10 | $50 |
| $100–199 | $10 | 10 | $100 |
| $200–499 | $15 | 10 | $150 |
| $500+ | $20 | 10 | $200 |

Always keep a $5 minimum cash buffer — never go below $5 available.

---

## 7. Weather Data Sources

### Local National Services (Anchor Sources)

| Country | Service | API | Weight |
|---------|---------|-----|--------|
| USA | NOAA | weather.gov API | 40% (US ensemble) |
| New Zealand | MetService | publicData JSON feeds | 50% (non-US ensemble) |
| Australia | BOM | api.weather.bom.gov.au | 50% (non-US ensemble) |

### Global Services (Sanity Check Sources)

| Service | Coverage | Weight |
|---------|----------|--------|
| Open-Meteo | Global | 25% |
| Visual Crossing | Global | 35% (US) / 25% (non-US with local) |

### Cities with Local Sources

| City | Local Source | Available |
|------|-------------|-----------|
| US cities (all) | NOAA | ✅ Yes |
| Wellington | MetService | ✅ Yes |
| Auckland | MetService | ✅ Yes |
| Sydney | BOM | ✅ Yes |
| Brisbane | BOM | ✅ Yes |
| Melbourne | BOM | ✅ Yes |
| Seoul | KMA | ❌ Not yet |
| London | Met Office | ❌ Not yet |
| Tokyo | JMA | ❌ Not yet |
| Paris | Météo-France | ❌ Not yet |
| Toronto | ECCC | ❌ Not yet |
| Ankara | MGM | ❌ Not yet |
| Buenos Aires | SMN | ❌ Not yet |

Cities without local sources use the 25% minimum edge rule.

---

## 8. Journal Logging

Every action gets logged to `polymarket-trader/journal/YYYY-MM-DD.md`.

### Scan Entry
```
## Scan — HH:MM:SS
Balance: $XX.XX
Markets scanned: N
Qualifying (≥20% edge): N
Passed live re-validation: N
Orders placed: N
Skipped: N
  - City SIDE: reason
```

### Position Monitor
```
## Monitor — HH:MM:SS
Market: City Date — SIDE ≥threshold
Entry: SIDE @ XX¢, N shares, $X.XX cost
Current: XX¢ → value $X.XX (±XX.X%)
Sources: Source1 XX°, Source2 XX°, Source3 XX°
Edge: XX% (was XX% at entry)
Action: HOLD | EXIT (reason) | 🏁 CONSENSUS HOLD (reason)
```

### Consensus Hold Entry
```
## Monitor — HH:MM:SS
Market: City Date — SIDE ≥threshold
Entry: SIDE @ XX¢, N shares, $X.XX cost
Current: XX¢ → value $X.XX (+XX.X%)
Sources: Local XX°, Global1 XX°, Global2 XX°
Threshold: ≥XX° (market unit)
Margin: X.X° (required: X.X° at X.Xh)
Resolution: X.Xh remaining
Action: 🏁 CONSENSUS HOLD — N sources agree, holding to resolution
Expected payout: $X.XX
Expected profit: $X.XX (+XX%)
```

### Exit Entry
```
## EXIT — HH:MM:SS
Market: City Date — SIDE ≥threshold
Reason: PROFIT TARGET | STOP LOSS | EDGE EVAPORATION | TIME EXIT
Entry: SIDE @ XX¢, $X.XX cost
Exit: XX¢, $X.XX recovered
P&L: $±X.XX (±XX.X%)
Hold duration: Xh Xm
```

---

## 9. State Files

| File | Purpose | Updated by |
|------|---------|-----------|
| `positions_state.json` | All tracked positions + exits | autonomous_trader_v2.py |
| `open_orders.json` | Currently open GTC orders | autonomous_trader_v2.py |
| `trading_state.json` | Summary for Mission Control | autonomous_trader_v2.py |
| `journal/YYYY-MM-DD.md` | Human-readable audit trail | All components |
| `config/weather_api.json` | API keys and BOM geohashes | Manual config |
| `config/trading_limits.json` | Position size tiers | Manual config |

---

## 10. What NOT To Do

1. **Never place orders without checking actual position count first** — query the API,
   don't trust local state alone
2. **Never hold YES and NO in the same market** — check conditionId before entry
3. **Never trade without live price re-validation** — Gamma API prices can be stale
4. **Never hold to resolution WITHOUT consensus hold criteria being met** — every source
   must agree, with sufficient margin, and a local source must be present
5. **Never use cron jobs or TinyClaw scheduler for trading** — run in a visible tmux
   window only
6. **Never embed rules in code comments that differ from this document** — this file is
   the single source of truth
7. **Never average into a losing position** — if stopped out, the edge was wrong
8. **Never exceed 10 simultaneous positions** — includes open GTC orders
9. **Never mix temperature units** — always compare in the market's native unit
10. **Never trade a non-US market without a local source at the 20% edge threshold** —
    use 25% minimum or wait until local source is implemented

---

## 11. Activation Checklist

Before starting `run_weather_strategy.sh`:
- [ ] `positions_state.json` reflects reality (run import if needed)
- [ ] `open_orders.json` is empty or matches actual open orders
- [ ] No cron jobs referencing weather/trader: `crontab -l`
- [ ] No background trading processes: `ps aux | grep trader`
- [ ] Balance is sufficient for at least 1 position + $5 buffer
- [ ] VPN is connected (ProtonVPN → Cyprus)
- [ ] Running in a visible tmux window, NOT via scheduler

---

**This document is the single source of truth. All code implements these rules.
No other .md files contain trading instructions.**
