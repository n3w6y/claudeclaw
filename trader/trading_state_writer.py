#!/usr/bin/env python3
"""
Trading State Writer - Single Source of Truth for Mission Control

Writes trading_state.json after every trading action.
DO NOT include secrets (full wallet addresses, private keys, API keys).
"""

import json
from pathlib import Path
from datetime import datetime

# Trading state file location (single source of truth)
TRADING_STATE_FILE = Path(__file__).parent / "polymarket-trader" / "trading_state.json"

def mask_wallet(wallet_address):
    """Mask wallet address for security (show first 6 and last 4 chars)."""
    if not wallet_address or len(wallet_address) < 10:
        return "0x****"
    return f"{wallet_address[:6]}...{wallet_address[-4:]}"

def load_recent_activity():
    """Load recent activity from existing state file."""
    if not TRADING_STATE_FILE.exists():
        return []

    try:
        with open(TRADING_STATE_FILE, 'r') as f:
            state = json.load(f)
            return state.get('recent_activity', [])
    except:
        return []

def add_activity(activity_type, market, details):
    """Add an activity event to recent activity list."""
    activity = load_recent_activity()
    activity.append({
        "timestamp": datetime.now().isoformat(),
        "type": activity_type,
        "market": market,
        "details": details
    })
    return activity[-20:]  # Keep last 20 events

def write_trading_state(balance_data, open_orders, active_positions, recent_activity=None):
    """
    Write trading state to single source of truth file.

    Args:
        balance_data: dict with 'balance_usdc' and 'wallet' keys
        open_orders: list of open order dicts
        active_positions: list of position dicts
        recent_activity: optional list of recent activity events (or None to keep existing)
    """

    # Use existing activity if not provided
    if recent_activity is None:
        recent_activity = load_recent_activity()

    # Calculate stats
    total_locked = sum(o.get('amount', 0) for o in open_orders if o.get('status') == 'OPEN')
    total_deployed = sum(p.get('cost_basis', 0) for p in active_positions)

    state = {
        "last_updated": datetime.now().isoformat(),
        "balance": {
            "usdc": round(balance_data.get('balance_usdc', 0), 2),
            "wallet": mask_wallet(balance_data.get('wallet', ''))
        },
        "open_orders": [
            {
                "order_id": o.get('order_id', 'N/A')[:16] + "...",  # Truncate for display
                "market": o.get('market', 'Unknown'),
                "side": o.get('side', 'UNKNOWN'),
                "price": o.get('price', 0),
                "amount": o.get('amount', 0),
                "edge": o.get('edge', 0),
                "time_placed": o.get('time_placed', ''),
                "ttl_expiry": o.get('ttl_expiry', ''),
                "status": o.get('status', 'UNKNOWN')
            }
            for o in open_orders
        ],
        "active_positions": [
            {
                "market_name": p.get('market_name', 'Unknown'),
                "side": p.get('side', 'UNKNOWN'),
                "entry_price": p.get('entry_price', 0),
                "current_price": p.get('current_price', p.get('entry_price', 0)),
                "shares": p.get('shares', 0),
                "cost_basis": p.get('cost_basis', 0),
                "current_value": p.get('current_value', 0),
                "pnl": p.get('pnl', 0),
                "pnl_percent": p.get('pnl_percent', 0),
                "entry_edge": p.get('original_edge', 0),
                "entry_date": p.get('entry_date', ''),
                "status": p.get('status', 'ACTIVE')
            }
            for p in active_positions
        ],
        "recent_activity": recent_activity,
        "stats": {
            "total_open_orders": len([o for o in open_orders if o.get('status') == 'OPEN']),
            "total_active_positions": len(active_positions),
            "total_capital_deployed": round(total_deployed, 2),
            "total_locked_in_orders": round(total_locked, 2),
            "available_balance": round(balance_data.get('balance_usdc', 0) - total_locked, 2)
        }
    }

    # Write atomically (write to temp, then rename)
    temp_file = TRADING_STATE_FILE.with_suffix('.tmp')
    with open(temp_file, 'w') as f:
        json.dump(state, f, indent=2)

    temp_file.replace(TRADING_STATE_FILE)

def log_balance_check(balance_data):
    """Log a balance check event."""
    activity = add_activity(
        "BALANCE_CHECK",
        "System",
        f"Balance: ${balance_data.get('balance_usdc', 0):.2f}"
    )
    return activity

def log_order_placed(order_data):
    """Log an order placement event."""
    activity = add_activity(
        "ORDER_PLACED",
        order_data.get('market', 'Unknown'),
        f"GTC order: BUY {order_data.get('side', '?')} @ {order_data.get('price', 0)*100:.0f}¢, ${order_data.get('amount', 0):.2f}"
    )
    return activity

def log_order_filled(order_data, fill_details):
    """Log an order fill event."""
    activity = add_activity(
        "ORDER_FILLED",
        order_data.get('market', 'Unknown'),
        f"Filled at {fill_details.get('price', 0)*100:.0f}¢, {fill_details.get('shares', 0):.2f} shares"
    )
    return activity

def log_order_cancelled(order_data, reason):
    """Log an order cancellation event."""
    activity = add_activity(
        "ORDER_CANCELLED",
        order_data.get('market', 'Unknown'),
        f"Reason: {reason}"
    )
    return activity

def log_position_exit(position_data, reason, pnl):
    """Log a position exit event."""
    activity = add_activity(
        "POSITION_EXIT",
        position_data.get('market_name', 'Unknown'),
        f"Exit: {reason}, P&L: ${pnl:.2f}"
    )
    return activity

# Example usage
if __name__ == "__main__":
    # Test writing trading state
    test_balance = {
        'balance_usdc': 56.34,
        'wallet': '0x8DE0a4326BD1A7F96C50A9935D1f2234B8aA9bD1'
    }

    test_orders = [
        {
            'order_id': '0x1234567890abcdef',
            'market': 'Test City - 2026-02-17',
            'side': 'NO',
            'price': 0.48,
            'amount': 5.0,
            'edge': 18.5,
            'time_placed': '2026-02-16T18:00:00',
            'ttl_expiry': '2026-02-16T18:30:00',
            'status': 'OPEN'
        }
    ]

    test_positions = []

    test_activity = [
        {
            'timestamp': '2026-02-16T18:00:00',
            'type': 'BALANCE_CHECK',
            'market': 'System',
            'details': 'Balance: $56.34'
        }
    ]

    write_trading_state(test_balance, test_orders, test_positions, test_activity)

    print(f"✅ Test trading_state.json written to {TRADING_STATE_FILE}")
    print(f"\nContents:")
    with open(TRADING_STATE_FILE, 'r') as f:
        print(json.dumps(json.load(f), indent=2))
