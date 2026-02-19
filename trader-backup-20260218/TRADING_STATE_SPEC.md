# Trading State File Specification

**File Location**: `/home/andrew/claudeclaw/trader/polymarket-trader/trading_state.json`

**Purpose**: Single source of truth for Mission Control dashboard

**Update Frequency**: After every trading action:
- Balance check
- Order placed
- Order filled
- Order cancelled
- Position exited
- Forecast monitoring
- Early exit check

---

## Schema

```json
{
  "last_updated": "2026-02-16T18:30:00.000000",
  "balance": {
    "usdc": 56.34,
    "wallet": "0x8DE0...9bD1"
  },
  "open_orders": [
    {
      "order_id": "0x...",
      "market": "City - Date",
      "side": "YES" | "NO",
      "price": 0.48,
      "amount": 5.0,
      "edge": 18.5,
      "time_placed": "2026-02-16T18:00:00",
      "ttl_expiry": "2026-02-16T18:30:00",
      "status": "OPEN"
    }
  ],
  "active_positions": [
    {
      "market_name": "Chicago Feb 17 - ≥54°F",
      "side": "NO",
      "entry_price": 0.52,
      "current_price": 0.50,
      "shares": 9.62,
      "cost_basis": 5.0,
      "current_value": 4.81,
      "pnl": -0.19,
      "pnl_percent": -3.8,
      "entry_edge": 44.5,
      "current_edge": 42.0,
      "entry_date": "2026-02-14T10:30:00",
      "status": "HOLD"
    }
  ],
  "recent_activity": [
    {
      "timestamp": "2026-02-16T18:00:00",
      "type": "ORDER_PLACED",
      "market": "Test City - 2026-02-17",
      "details": "GTC order: BUY NO @ 48¢, $5"
    },
    {
      "timestamp": "2026-02-16T18:05:00",
      "type": "ORDER_FILLED",
      "market": "Test City - 2026-02-17",
      "details": "Filled at 48¢, 10.42 shares"
    }
  ],
  "stats": {
    "total_open_orders": 1,
    "total_active_positions": 1,
    "total_capital_deployed": 10.0,
    "total_locked_in_orders": 5.0,
    "available_balance": 51.34
  }
}
```

---

## Implementation

### Files to Update

1. **`autonomous_trader_v2.py`**
   - Write after: balance check, order placement

2. **`order_monitor.py`**
   - Write after: order filled, order cancelled, TTL expired

3. **`position_monitor.py`**
   - Write after: position exits, forecast monitoring

4. **`early_exit_manager.py`**
   - Write after: early exit triggers

---

## Security

**DO NOT include in trading_state.json**:
- Private keys
- API keys
- Full wallet addresses (mask middle: `0x8DE0...9bD1`)
- Seed phrases
- Passwords

**Safe to include**:
- Balance amounts
- Masked wallet addresses
- Order IDs
- Market names
- Prices and amounts
- Timestamps
- Status updates

---

## Writing the File

```python
import json
from pathlib import Path
from datetime import datetime

TRADING_STATE_FILE = Path(__file__).parent / "polymarket-trader" / "trading_state.json"

def write_trading_state(balance, open_orders, active_positions, recent_activity):
    """Write trading state to single source of truth file."""

    state = {
        "last_updated": datetime.now().isoformat(),
        "balance": {
            "usdc": balance['balance_usdc'],
            "wallet": f"{balance['wallet'][:6]}...{balance['wallet'][-4:]}"  # Masked
        },
        "open_orders": open_orders,
        "active_positions": active_positions,
        "recent_activity": recent_activity[-20:],  # Last 20 events
        "stats": {
            "total_open_orders": len([o for o in open_orders if o['status'] == 'OPEN']),
            "total_active_positions": len(active_positions),
            "total_capital_deployed": sum(p['cost_basis'] for p in active_positions),
            "total_locked_in_orders": sum(o['amount'] for o in open_orders if o['status'] == 'OPEN'),
            "available_balance": balance['balance_usdc']
        }
    }

    with open(TRADING_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)
```

---

## Dashboard Integration

Mission Control dashboard reads this file to display:
- Current balance and available funds
- Open orders with TTL countdown
- Active positions with P&L
- Recent activity feed
- System status

**Refresh rate**: Dashboard polls every 30 seconds or on file change notification.

---

**Created**: Feb 16, 2026
**Location**: Must always be `~/claudeclaw/trader/polymarket-trader/trading_state.json`
