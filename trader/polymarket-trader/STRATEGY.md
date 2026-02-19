# Polymarket Trading Strategy

**Goal:** Double account balance weekly
**Risk limit:** Tier-based max bet (see `risk_manager.py` BET_TIERS)
**Alert channel:** TBD (Telegram not yet implemented)

---

## Fee Structure

| Market Type | Trading Fee | Notes |
|-------------|-------------|-------|
| Most markets | **0%** | No fees to trade |
| 15-min crypto | Small taker fee | Funds maker rebates |
| Deposits/Withdrawals | 0% | But Coinbase/MoonPay may charge |

**Key insight:** No trading fees on most markets = we keep the full edge.

---

## Position Sizing

Tiered: 5% of the ceiling of the current $100 range:
- $0-99 balance → $5 max per trade
- $100-199 → $10 max per trade
- $200-299 → $15 max per trade
- $300-399 → $20, $400-499 → $25, $500-599 → $30, etc.
- $1000+ → $55 max per trade

See `scripts/risk_manager.py` BET_TIERS for authoritative values.

**Kelly Criterion suggestion:** For edges < 5%, size even smaller (1-2% of balance).

---

## Hedging / "Stop Loss" via Opposing Positions

Polymarket has no traditional stop-loss. Instead, hedge by buying the opposite:

### Lock In Profit
```
Buy YES @ 40¢ → Price rises to 60¢
Hedge: Buy NO @ 40¢ (same $ amount)
Result: Guaranteed 60¢ + 40¢ = $1 payout, locked profit
```

### Limit Loss
```
Buy YES @ 60¢ → Price drops to 40¢
Option A: Sell YES @ 40¢ (realize 20¢ loss)
Option B: Buy NO @ 60¢ to lock outcome (lose 20¢ either way, but capped)
```

### Spread Trade (Built-in hedge)
```
Entry: Buy YES @ 45¢ AND NO @ 50¢ simultaneously
Cost: 95¢ total
Guaranteed payout: $1
Profit: 5¢ per $0.95 = 5.3% risk-free
```

---

## Strategy Tiers

### Tier 1: True Arbitrage (Risk-Free)
- YES + NO < $1.00 on same market
- Edge: 1-5%
- Frequency: Rare
- Action: IMMEDIATE, max position

### Tier 2: Cross-Market Arbitrage
- Related markets with pricing inconsistency
- Edge: 2-10%
- Risk: Medium (depends on market structure)
- Action: Verify logic, then trade

### Tier 3: Whale Copy
- Follow top traders' high-conviction bets
- Edge: Unknown (riding their analysis)
- Risk: Higher
- Action: Smaller position, quick exit plan

### Tier 4: Directional Bets
- Betting on outcomes you believe in
- Edge: Depends on your analysis
- Risk: Highest
- Action: Smallest positions, clear thesis

---

## Timing

### Best Times for Opportunities
1. **News breaks** — One market updates faster than related ones
2. **New market launch** — Initial mispricing common
3. **Low liquidity hours** — Fewer bots watching (late night US)
4. **Market close approaching** — Forced position unwinding

### Scan Schedule
- Every 30 min: Micro-arb scanner
- Every 2 hours: Cross-market scanner
- On news events: Manual check of related markets

---

## Prioritization Matrix

| Factor | Weight | Notes |
|--------|--------|-------|
| Edge % | High | Higher edge = better |
| Liquidity | High | Can you actually execute? |
| Time to resolution | Medium | Faster = faster compounding |
| Risk profile | High | True arb > directional |
| Capital required | Medium | Stay within 5% rule |

**Priority Score = Edge × Liquidity × (1/Risk)**

---

## Profit Taking

### Rule 1: Lock gains at 50% of max potential
If bought YES @ 30¢ and it hits 65¢:
- Max potential: 70¢ profit (at 100¢)
- 50% = 35¢ profit
- 30¢ + 35¢ = 65¢ → LOCK or EXIT

### Rule 2: Exit arbitrage immediately
True arb = take the guaranteed spread, don't wait.

### Rule 3: Trailing hedge
As position gains, buy small opposing position to protect gains.

---

## Doubling Weekly — Reality Check

To double $500 → $1000 in a week:

**If pure arbitrage (2% edge):**
- Need 35 successful round-trips
- 5 trades/day, all winners
- Very tight but possible IF opportunities exist

**If directional (50% win rate, 2:1 reward):**
- Need ~20 wins, ~20 losses
- Much more variance

**Realistic target:** 20-50% weekly with disciplined arbitrage hunting.
100% weekly requires either leverage, large edges, or luck.

---

## Risk Rules (Non-Negotiable)

1. **Never exceed tier max bet** (see `risk_manager.py` BET_TIERS)
2. **Always verify liquidity before sizing**
3. **No revenge trading after losses**
4. **Daily loss limit: $100 hard cap** — stop trading if hit
5. **Max 2 trades/hour, 10 trades/session, 3 weather trades/day**

---

## Execution Checklist

Before any trade:
- [ ] Edge > 2%?
- [ ] Liquidity sufficient for position size?
- [ ] Position within tier max bet?
- [ ] Exit plan clear?
- [ ] Hedge option identified?
- [ ] Within daily/hourly trade limits?

---

## Order Execution — GTC with Guardrails

**Updated Feb 16, 2026** — Replaced FOK taker orders with GTC maker orders after order book diagnosis showed weather markets have 99¢ spreads with no taker liquidity.

### Why Not FOK?
- FOK (Fill-Or-Kill) requires immediate execution at specified price
- Weather markets have order books with 99¢ spreads (quote: 0.7¢, best ask: 99.9¢)
- Zero taker liquidity = FOK orders always fail
- Market maker quotes ≠ order book prices

### Why Not Unmanaged GTC?
- GTC orders without TTL can lock funds indefinitely
- Previous bug: Orders sat unfilled for days, preventing capital reuse
- No auto-cancellation = manual cleanup required

### Solution: GTC with 30-Minute TTL

All orders now use **GTC maker orders with automatic expiration**:

1. **Order Type**: GTC (Good-Til-Cancel) maker order
2. **Time-to-Live**: 30 minutes from placement
3. **Price**: AT the current market price (we provide liquidity)
4. **Tracking**: All open orders logged to `open_orders.json`
5. **Auto-Cancel**: Orders unfilled after 30 minutes are automatically cancelled

### Open Order Tracking

Every GTC order is tracked with:
- `order_id`: Polymarket order ID
- `market`: Market name/description
- `condition_id`: Market condition ID
- `token_id`: Token being purchased
- `side`: YES or NO
- `price`: Order price (in dollar terms, 0.00-1.00)
- `amount`: Dollar amount (e.g., $5)
- `time_placed`: ISO timestamp of order submission
- `ttl_expiry`: ISO timestamp when order should be cancelled (time_placed + 30 min)
- `status`: "OPEN" | "FILLED" | "CANCELLED"

### Execution Cycle (Every 5 Minutes)

1. **Check open orders**: Query Polymarket API for order status
2. **If FILLED**:
   - Log position to `positions_state.json`
   - Remove from `open_orders.json`
   - Record fill details in daily journal
3. **If TTL expired**:
   - Cancel the order via API
   - Free up locked funds
   - Log cancellation with reason "TTL_EXPIRED"
4. **If still OPEN**:
   - Continue waiting
   - Check again in 5 minutes
5. **New opportunities**: Only place order if no existing open order for that market

### Guardrails

1. **One order per market**: Cannot place second order if one already open
2. **Max 3 open orders**: Prevent capital lockup across too many markets
3. **30-minute hard limit**: All orders auto-cancel after 30 minutes
4. **5-minute check cycle**: Fast enough to react, slow enough to avoid API spam
5. **Position cap still enforced**: Max 10 active positions total

### Order Flow Example

```
T+0:00  - Place GTC order: Buy YES @ 35¢, $5
T+0:05  - Check: Still open, wait
T+0:10  - Check: Still open, wait
T+0:15  - Check: FILLED at 35¢
         → Log position, remove from open orders
T+0:20  - [Order already processed]

Alternative:
T+0:00  - Place GTC order: Buy NO @ 48¢, $5
T+0:05  - Check: Still open
...
T+0:30  - Check: Still open, TTL expired
         → Cancel order, log "TTL_EXPIRED"
         → Funds freed for next opportunity
```

### Files Modified

- `autonomous_trader_v2.py`: Order placement now uses GTC with TTL
- `open_orders.json`: New file tracking all open orders
- `order_monitor.py`: New script checking orders every 5 minutes
- `weather_scanner_supervised.py`: Integrated order status checks

---

## Alert Format (Telegram)

```
🎯 ARBITRAGE ALERT

Market: [name]
Type: [tier]
Edge: X.X%
Action: Buy YES @ XX¢ / NO @ XX¢
Size: $XX (X% of balance)
Risk: [low/med/high]

Reply "GO" to execute or "PASS"
```
