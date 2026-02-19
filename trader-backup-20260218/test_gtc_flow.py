#!/usr/bin/env python3
"""
Test GTC Order Flow

This script simulates the complete GTC order flow:
1. Places a test GTC order
2. Shows how order_monitor.py would process it
3. Demonstrates the 30-minute TTL
"""

import json
from pathlib import Path
from datetime import datetime, timedelta

TRADER_DIR = Path(__file__).parent
STATE_DIR = TRADER_DIR / "polymarket-trader"
OPEN_ORDERS_FILE = STATE_DIR / "open_orders.json"

def create_test_order():
    """Create a simulated GTC order for testing."""

    time_placed = datetime.now()
    ttl_expiry = time_placed + timedelta(minutes=30)

    test_order = {
        "order_id": "0xTEST123456789",
        "market": "Test City - 2026-02-17",
        "condition_id": "0x0000000000000000000000000000000000000000000000000000000000000000",
        "token_id": "12345678901234567890",
        "side": "NO",
        "price": 0.48,
        "amount": 5.0,
        "time_placed": time_placed.isoformat(),
        "ttl_expiry": ttl_expiry.isoformat(),
        "status": "OPEN",
        "edge": 18.5,
        "sources": ["noaa", "open-meteo", "visual-crossing"],
        "question": "Will Test City reach ≥80°F on Feb 17?"
    }

    return test_order

def main():
    print("="*70)
    print("🧪 GTC ORDER FLOW TEST")
    print("="*70)
    print()

    print("This test demonstrates the complete GTC order flow:")
    print("1. Order placement with 30-minute TTL")
    print("2. Order tracking in open_orders.json")
    print("3. Order monitor checks (every 5 minutes)")
    print("4. Three possible outcomes: FILLED, TTL_EXPIRED, or STILL_OPEN")
    print()

    # Create test order
    test_order = create_test_order()

    print("="*70)
    print("STEP 1: GTC ORDER PLACED")
    print("="*70)
    print()
    print(f"Market: {test_order['market']}")
    print(f"Action: BUY {test_order['side']} @ {test_order['price']*100:.0f}¢")
    print(f"Amount: ${test_order['amount']:.2f}")
    print(f"Edge: {test_order['edge']:.1f}%")
    print(f"Sources: {', '.join(test_order['sources'])}")
    print()
    print(f"Order ID: {test_order['order_id']}")
    print(f"Time placed: {test_order['time_placed']}")
    print(f"TTL expires: {test_order['ttl_expiry']}")
    print()

    # Save to open_orders.json
    orders = []
    if OPEN_ORDERS_FILE.exists():
        with open(OPEN_ORDERS_FILE, 'r') as f:
            try:
                orders = json.load(f)
            except:
                orders = []

    orders.append(test_order)

    with open(OPEN_ORDERS_FILE, 'w') as f:
        json.dump(orders, f, indent=2)

    print(f"✅ Order tracked in {OPEN_ORDERS_FILE}")
    print()

    # Explain monitoring
    print("="*70)
    print("STEP 2: ORDER MONITORING (Every 5 Minutes)")
    print("="*70)
    print()
    print("The order_monitor.py script will check this order every 5 minutes:")
    print()
    print("Scenario A - ORDER FILLED:")
    print("  → Query Polymarket API: order status = 'MATCHED'")
    print("  → Extract fill details (actual price, shares)")
    print("  → Create Position in positions_state.json")
    print("  → Update order status to 'FILLED' in open_orders.json")
    print("  → Log fill to daily journal")
    print()
    print("Scenario B - TTL EXPIRED (30 minutes):")
    print("  → Current time > ttl_expiry")
    print("  → Cancel order via API: client.cancel(order_id)")
    print("  → Update order status to 'CANCELLED' in open_orders.json")
    print("  → Log cancellation with reason 'TTL_EXPIRED'")
    print("  → Funds freed for next opportunity")
    print()
    print("Scenario C - STILL OPEN:")
    print("  → Order status = 'LIVE' or 'OPEN'")
    print("  → TTL not yet expired")
    print("  → Continue waiting")
    print("  → Check again in 5 minutes")
    print()

    # Calculate time remaining
    ttl_time = datetime.fromisoformat(test_order['ttl_expiry'])
    now = datetime.now()
    minutes_remaining = (ttl_time - now).total_seconds() / 60

    print("="*70)
    print("CURRENT STATUS")
    print("="*70)
    print()
    print(f"Order: {test_order['market']}")
    print(f"Status: OPEN")
    print(f"Time remaining: {minutes_remaining:.0f} minutes")
    print()
    print("To check order status, run:")
    print("  python3 order_monitor.py")
    print()
    print("To manually clear test order:")
    print(f"  rm {OPEN_ORDERS_FILE} && echo '[]' > {OPEN_ORDERS_FILE}")
    print()
    print("="*70)

if __name__ == "__main__":
    main()
