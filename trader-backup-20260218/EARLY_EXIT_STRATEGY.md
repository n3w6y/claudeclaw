# Early Exit Strategy - Cost Basis Recovery

## Overview

The early exit strategy implements automatic partial position exits when trades reach 2× the entry price, allowing you to recover your initial investment while letting the remaining position ride risk-free.

## Strategy Rules

### Exit Trigger
- **Condition**: Current market price ≥ 2× entry price
- **Action**: Sell HALF the position at current market price
- **Result**: Cost basis recovered, remaining shares = pure profit

### Example
```
Entry: 10 shares @ 30¢ = $3.00 cost
Trigger: Price hits 60¢ (2× entry)
Action: Sell 5 shares @ 60¢ = $3.00 recovered
Result: 5 shares remaining (risk-free position)
```

### Important Notes
- ✅ **This IS**: A profit-taking strategy that guarantees cost recovery
- ❌ **This IS NOT**: A stop-loss (we hold through dips, only exit on gains)
- Only exits when we can guarantee full cost recovery
- Uses FOK (Fill-Or-Kill) market orders for immediate execution

## Implementation

### Files Created/Modified

1. **`early_exit_manager.py`** - Core exit logic
   - `PositionTracker`: Manages active positions and exits
   - `check_exit_trigger()`: Determines if position qualifies for exit
   - `execute_early_exit()`: Executes the partial sell
   - `monitor_and_exit()`: Main monitoring loop

2. **`autonomous_trader_v2.py`** - Updated trader
   - Initializes position tracker
   - Checks for exits BEFORE scanning for new trades
   - Tracks positions when trades execute
   - Logs exits to journal

3. **`weather_scanner_supervised.py`** - Updated scanner
   - Checks for exit opportunities during each scan
   - Executes exits before showing new opportunities

4. **`update_exit_resolution.py`** - Resolution tracking tool
   - Updates exit records when markets resolve
   - Calculates profit metrics
   - Appends resolution data to journal

5. **`positions_state.json`** - State file (auto-created)
   - Tracks all active positions
   - Stores exit records
   - Persists across sessions

## Execution Flow

### 1. Every Scan Cycle

```
START
  ↓
Check Active Positions
  ↓
For each position:
  - Fetch current price
  - Check if price ≥ 2× entry
  ↓
If triggered:
  - Sell HALF at current price
  - Update position tracker
  - Log to journal
  ↓
Continue with normal scanning
```

### 2. When Trade Executes

```
Trade Executed
  ↓
Create Position Record:
  - Market name
  - Token ID
  - Entry price
  - Number of shares
  - Cost basis
  ↓
Save to positions_state.json
  ↓
Position now monitored for exits
```

### 3. When Market Resolves

```
Market Resolves
  ↓
Run: python update_exit_resolution.py
  --token-id <TOKEN_ID>
  --resolution-price <0 or 1.00>
  ↓
Calculate Metrics:
  - Profit from remaining shares
  - Profit if held all shares
  - Early exit cost/benefit
  ↓
Update journal with resolution
```

## Journal Format

### Early Exit Log (Immediate)
```markdown
## EARLY EXIT LOG - 14:30:15

### Chicago - 2026-02-18

- **Market**: Chicago - 2026-02-18
- **Side**: YES
- **Entry price**: 30¢
- **Exit price**: 60¢ (half position)
- **Total shares originally**: 10.0
- **Shares sold**: 5.0
- **Cost recovered**: $3.00
- **Remaining shares**: 5.0 (risk-free)
- **Exit order ID**: abc123...

**FINAL RESOLUTION**: _Pending market resolution_
- Resolution price: _TBD_ (0¢ or 100¢)
- Profit from remaining shares: _TBD_
- Profit if we had held everything: _TBD_
- Early exit cost/benefit: _TBD_

_Will be updated when market resolves_
```

### Resolution Update (After Market Settles)
```markdown
## EARLY EXIT RESOLUTION - 18:45:20

### Chicago - 2026-02-18

**Original Exit**: 2026-02-18T14:30:15

**FINAL RESOLUTION**:
- Resolution price: 100¢
- Profit from remaining shares: $5.00
- Profit if we had held everything: $7.00
- Early exit cost/benefit: -$2.00 ❌ (LOST MONEY by exiting early)
```

## Usage Examples

### Running the Autonomous Trader
```bash
python autonomous_trader_v2.py
```

Output:
```
======================================================================
🎯 AUTONOMOUS WEATHER ARBITRAGE TRADING V2
======================================================================

FIXES APPLIED:
  ✓ FIX 1: Using MarketOrderArgs with amount (dollars)
  ✓ FIX 2: Non-US markets allowed (2 sources, 15% edge)
  ✓ FIX 3: Tiered position sizing by balance
  ✓ NEW: Early exit strategy (2x entry = sell half, recover cost)

Initial Balance: $99.94
Position Tracker: 3 active positions

======================================================================
STEP 1: CHECK EARLY EXIT OPPORTUNITIES
======================================================================

🔍 CHECKING POSITIONS FOR EARLY EXIT TRIGGERS

Position: Chicago - 2026-02-18
  Entry: 10.0 shares @ 30¢ ($3.00)
  Current: 62¢
  Exit threshold: 60¢ (2x entry)
  ✅ TRIGGER MET - Executing early exit...

    🎯 EARLY EXIT TRIGGERED
    Market: Chicago - 2026-02-18
    Entry: 10.0 shares @ 30¢
    Current: 62¢ (≥ 2x entry)
    Selling: 5.0 shares
    Expected recovery: $3.10 (cost was $3.00)
    Remaining: 5.0 shares (risk-free)

    ✅ EXIT EXECUTED
    Order ID: xyz789...
    Status: HALF position sold, half riding risk-free

✅ Executed 1 early exits

======================================================================
STEP 2: SCAN FOR NEW OPPORTUNITIES
======================================================================
[continues with normal scanning...]
```

### Running the Scanner
```bash
python weather_scanner_supervised.py
```

The scanner will check for exits first, then show new opportunities.

### Listing Unresolved Exits
```bash
python update_exit_resolution.py --list
```

Output:
```
Found 2 unresolved exits:

1. Chicago - 2026-02-18
   Token ID: 123456789
   Exit date: 2026-02-16
   Shares remaining: 5.0

2. Miami - 2026-02-19
   Token ID: 987654321
   Exit date: 2026-02-16
   Shares remaining: 7.5
```

### Updating Resolution (Market Resolved YES)
```bash
python update_exit_resolution.py --token-id 123456789 --resolution-price 1.00
```

Output:
```
Found exit: Chicago - 2026-02-18
  Entry: 30¢
  Exit: 62¢
  Shares sold: 5.0
  Shares remaining: 5.0
  Cost recovered: $3.10

✅ Resolution updated
  Resolution price: 100¢
  Profit from remaining shares: $5.00
  Profit if held all shares: $7.00
  Early exit cost/benefit: -$2.00

📝 Appended resolution to journal/2026-02-16.md
```

### Updating Resolution (Market Resolved NO)
```bash
python update_exit_resolution.py --token-id 987654321 --resolution-price 0
```

Output:
```
Found exit: Miami - 2026-02-19
  Entry: 40¢
  Exit: 85¢
  Shares sold: 7.5
  Shares remaining: 7.5
  Cost recovered: $6.38

✅ Resolution updated
  Resolution price: 0¢
  Profit from remaining shares: $0.00
  Profit if held all shares: -$6.38
  Early exit cost/benefit: $6.38

📝 Appended resolution to journal/2026-02-16.md
```

In this case, the early exit **saved** $6.38 because the market resolved against us!

## State File Structure

`positions_state.json`:
```json
{
  "positions": [
    {
      "market_name": "Chicago - 2026-02-18",
      "condition_id": "0xabc...",
      "token_id": "123456789",
      "side": "YES",
      "entry_price": 0.30,
      "shares": 10.0,
      "cost_basis": 3.00,
      "entry_date": "2026-02-16T10:30:00",
      "order_id": "order_123"
    }
  ],
  "exits": [
    {
      "market_name": "Chicago - 2026-02-18",
      "condition_id": "0xabc...",
      "token_id": "123456789",
      "side": "YES",
      "entry_price": 0.30,
      "exit_price": 0.62,
      "total_shares": 10.0,
      "shares_sold": 5.0,
      "shares_remaining": 5.0,
      "cost_recovered": 3.10,
      "exit_date": "2026-02-16T14:30:15",
      "exit_order_id": "exit_456",
      "resolution_date": null,
      "resolution_price": null,
      "profit_from_remaining": null,
      "profit_if_held_all": null,
      "early_exit_cost_benefit": null
    }
  ],
  "last_updated": "2026-02-16T14:30:15"
}
```

## Benefits

1. **Risk Management**: Guarantees cost recovery on winning trades
2. **Psychological**: Removes emotional decision-making about when to exit
3. **Data-Driven**: Tracks long-term performance of the strategy
4. **Upside Preservation**: Still captures 50% of further gains
5. **Downside Protection**: If market reverses, you've already recovered cost

## Analysis Over Time

The resolution tracking gives you hard data to evaluate:

- **How often do we exit early vs. markets resolving?**
- **Do early exits cost us money or save us money on average?**
- **Should we adjust the 2× threshold (make it 1.5× or 3×)?**
- **Are there market types where early exits perform better/worse?**

Track these metrics in your journal to continuously improve the strategy.

## Safety Features

- ✅ Only exits when price ≥ 2× entry (no early exits on small gains)
- ✅ Uses FOK orders (immediate fill or cancel, no partial fills)
- ✅ Re-validates current price before executing
- ✅ Updates position tracker after exit
- ✅ Logs everything for audit trail
- ✅ Persists state across restarts

## Troubleshooting

### Position not being tracked?
Check `positions_state.json` - positions are added when trades execute.

### Exit not triggering?
- Verify current price ≥ 2× entry price
- Check that position exists in tracker
- Look for errors in console output

### Resolution update failing?
- Ensure token_id matches exactly
- Resolution price must be 0 or 1.00
- Check that exit hasn't already been resolved

### State file corrupted?
Delete `positions_state.json` and manually re-add active positions, or restore from backup.

## Next Steps

After markets resolve:
1. Run `update_exit_resolution.py --list` to see unresolved exits
2. For each exit, run `update_exit_resolution.py --token-id <ID> --resolution-price <0 or 1.00>`
3. Review journal entries to analyze strategy performance
4. Adjust 2× threshold if data suggests optimization
