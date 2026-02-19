#!/usr/bin/env python3
"""
Order Monitor - Check GTC orders every 5 minutes

Checks all open orders and:
1. If FILLED → Log position, remove from open orders
2. If TTL expired (30 min) → Cancel order, log cancellation
3. If still OPEN → Continue waiting

Run frequency: Every 5 minutes
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add scripts to path
TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from polymarket_api import get_client, get_balance
from early_exit_manager import PositionTracker, Position
from trading_state_writer import (
    write_trading_state, log_order_filled, log_order_cancelled
)

# Files
STATE_DIR = TRADER_DIR / "polymarket-trader"
OPEN_ORDERS_FILE = STATE_DIR / "open_orders.json"
POSITION_STATE_FILE = STATE_DIR / "positions_state.json"
JOURNAL_DIR = TRADER_DIR / "polymarket-trader" / "journal"
JOURNAL_DIR.mkdir(exist_ok=True)

def get_todays_journal():
    """Get today's journal file."""
    today = datetime.now().strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"{today}.md"

def load_open_orders():
    """Load open orders from JSON file."""
    if not OPEN_ORDERS_FILE.exists():
        return []

    try:
        with open(OPEN_ORDERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_open_orders(orders):
    """Save open orders to JSON file."""
    with open(OPEN_ORDERS_FILE, 'w') as f:
        json.dump(orders, f, indent=2)

def log_order_fill(order_data, fill_data):
    """Log order fill to daily journal."""
    journal = get_todays_journal()

    with open(journal, 'a') as f:
        f.write(f"\n## Order Filled - {datetime.now().strftime('%H:%M:%S')}\n\n")
        f.write(f"**Market**: {order_data['market']}\n")
        f.write(f"**Action**: BUY {order_data['side']}\n")
        f.write(f"**Price**: {order_data['price']*100:.1f}¢\n")
        f.write(f"**Amount**: ${order_data['amount']:.2f}\n")
        f.write(f"**Edge**: {order_data.get('edge', 0):.1f}%\n")
        f.write(f"**Order ID**: {order_data['order_id']}\n")
        f.write(f"**Time Placed**: {order_data['time_placed']}\n")
        f.write(f"**Fill Time**: {datetime.now().isoformat()}\n")
        f.write(f"**Shares**: {fill_data['shares']:.2f}\n")
        f.write(f"**Status**: ✅ FILLED\n")
        f.write("\n")

def log_order_cancellation(order_data, reason):
    """Log order cancellation to daily journal."""
    journal = get_todays_journal()

    with open(journal, 'a') as f:
        f.write(f"\n## Order Cancelled - {datetime.now().strftime('%H:%M:%S')}\n\n")
        f.write(f"**Market**: {order_data['market']}\n")
        f.write(f"**Action**: BUY {order_data['side']}\n")
        f.write(f"**Price**: {order_data['price']*100:.1f}¢\n")
        f.write(f"**Amount**: ${order_data['amount']:.2f}\n")
        f.write(f"**Order ID**: {order_data['order_id']}\n")
        f.write(f"**Reason**: {reason}\n")
        f.write(f"**Status**: ❌ CANCELLED\n")
        f.write("\n")

def check_order_status(client, order_id):
    """
    Check if order is filled or still open.
    Returns: ('FILLED', fill_details) or ('OPEN', None) or ('NOT_FOUND', None)
    """
    try:
        # Get order status from API
        order = client.get_order(order_id)

        if not order:
            return 'NOT_FOUND', None

        # Check status
        status = order.get('status', '').upper()

        if status == 'MATCHED' or status == 'FILLED':
            # Extract fill details
            fill_details = {
                'price': float(order.get('price', 0)),
                'size': float(order.get('size', 0)),
                'shares': float(order.get('size', 0))  # Size is in shares
            }
            return 'FILLED', fill_details
        elif status == 'LIVE' or status == 'OPEN':
            return 'OPEN', None
        else:
            # CANCELLED, EXPIRED, etc.
            return status, None

    except Exception as e:
        print(f"    Error checking order {order_id[:8]}: {e}")
        return 'ERROR', None

def cancel_order(client, order_id):
    """Cancel an order via API."""
    try:
        response = client.cancel(order_id)
        return True
    except Exception as e:
        print(f"    Error cancelling order: {e}")
        return False

def main():
    print("="*70)
    print("📋 ORDER MONITOR - Checking Open GTC Orders")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Load open orders
    open_orders = load_open_orders()

    if not open_orders:
        print("✅ No open orders to monitor")
        return

    # Filter for OPEN status only
    open_orders = [o for o in open_orders if o.get('status') == 'OPEN']

    if not open_orders:
        print("✅ No open orders to monitor (all filled/cancelled)")
        return

    print(f"Found {len(open_orders)} open orders")
    print()

    # Connect to API
    client = get_client(signature_type=1)
    tracker = PositionTracker(POSITION_STATE_FILE)

    # Track changes
    filled_count = 0
    cancelled_count = 0
    still_open_count = 0

    all_orders = load_open_orders()  # Load full list for updates

    for order in open_orders:
        order_id = order['order_id']
        market = order['market']
        side = order['side']
        price = order['price']
        amount = order['amount']

        print(f"Checking: {market} - BUY {side} @ {price*100:.0f}¢")
        print(f"  Order ID: {order_id[:16]}...")

        # Check TTL expiry
        ttl_expiry = datetime.fromisoformat(order['ttl_expiry'])
        now = datetime.now()

        if now > ttl_expiry:
            print(f"  ⏰ TTL EXPIRED (placed {order['time_placed']}, expired {order['ttl_expiry']})")
            print(f"  Cancelling order...")

            # Cancel the order
            if cancel_order(client, order_id):
                print(f"  ✅ Order cancelled")

                # Update status
                for o in all_orders:
                    if o['order_id'] == order_id:
                        o['status'] = 'CANCELLED'
                        o['cancellation_reason'] = 'TTL_EXPIRED'
                        o['cancellation_time'] = now.isoformat()

                # Log cancellation
                log_order_cancellation(order, "TTL_EXPIRED (30 min)")
                cancelled_count += 1

                # Update trading state
                current_balance = get_balance(client)
                all_positions = [vars(p) for p in tracker.get_active_positions()]
                recent_activity = log_order_cancelled(order, "TTL_EXPIRED")
                write_trading_state(current_balance, all_orders, all_positions, recent_activity)
                print(f"  📊 Trading state updated")
            else:
                print(f"  ❌ Failed to cancel (may already be filled)")

            print()
            continue

        # Check order status
        status, fill_details = check_order_status(client, order_id)

        if status == 'FILLED':
            print(f"  ✅ ORDER FILLED!")
            print(f"  Fill price: {fill_details['price']*100:.1f}¢")
            print(f"  Shares: {fill_details['shares']:.2f}")

            # Update status
            for o in all_orders:
                if o['order_id'] == order_id:
                    o['status'] = 'FILLED'
                    o['fill_time'] = now.isoformat()
                    o['fill_details'] = fill_details

            # Log fill
            log_order_fill(order, fill_details)

            # Track position
            shares = fill_details['shares']
            actual_price = fill_details['price']

            # Extract threshold temp from question
            threshold_temp = 80.0  # Default
            question = order.get('question', '')
            if "°F" in question or "degrees" in question:
                import re
                match = re.search(r'(\d+)°?F', question)
                if match:
                    threshold_temp = float(match.group(1))

            # Parse market name for city and date
            market_parts = market.split(' - ')
            city = market_parts[0] if len(market_parts) > 0 else 'Unknown'
            market_date = market_parts[1] if len(market_parts) > 1 else 'Unknown'

            position = Position(
                market_name=market,
                condition_id=order['condition_id'],
                token_id=order['token_id'],
                side=side,
                entry_price=actual_price,
                shares=shares,
                cost_basis=amount,  # Original amount
                entry_date=now.isoformat(),
                order_id=order_id,
                original_edge=order.get('edge', 0),
                threshold_temp_f=threshold_temp,
                city=city,
                market_date=market_date,
                is_us_market=('noaa' in order.get('sources', [])),
                forecast_sources=','.join(order.get('sources', []))
            )
            tracker.add_position(position)

            print(f"  📊 Position tracked: {shares:.1f} shares @ {actual_price*100:.1f}¢")
            filled_count += 1

            # Update trading state
            current_balance = get_balance(client)
            all_orders = load_open_orders()
            all_positions = [vars(p) for p in tracker.get_active_positions()]
            recent_activity = log_order_filled(order, fill_details)
            write_trading_state(current_balance, all_orders, all_positions, recent_activity)
            print(f"  📊 Trading state updated")
            print()

        elif status == 'OPEN':
            time_remaining = (ttl_expiry - now).total_seconds() / 60
            print(f"  ⏳ Still open (expires in {time_remaining:.0f} min)")
            still_open_count += 1

        elif status == 'NOT_FOUND':
            print(f"  ⚠️  Order not found (may have been cancelled)")
            # Mark as unknown
            for o in all_orders:
                if o['order_id'] == order_id:
                    o['status'] = 'NOT_FOUND'

        else:
            print(f"  ℹ️  Status: {status}")

        print()

    # Save updated orders
    save_open_orders(all_orders)

    # Summary
    print("="*70)
    print("MONITORING SUMMARY")
    print("="*70)
    print(f"Orders filled: {filled_count}")
    print(f"Orders cancelled (TTL): {cancelled_count}")
    print(f"Orders still open: {still_open_count}")
    print()

    if filled_count > 0:
        print(f"✅ Logged {filled_count} fills to {get_todays_journal()}")
        print(f"📊 Positions tracked in {POSITION_STATE_FILE}")

    if cancelled_count > 0:
        print(f"❌ Logged {cancelled_count} cancellations to {get_todays_journal()}")

    print()

if __name__ == "__main__":
    main()
