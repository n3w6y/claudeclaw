#!/usr/bin/env python3
"""
Autonomous Weather Arbitrage Trader v3

EXECUTION STRATEGY: GTC with 30-minute TTL (Updated Feb 16, 2026)
- Uses GTC maker orders (provide liquidity on order book)
- 30-minute time-to-live with auto-cancellation
- Tracks open orders in open_orders.json
- Order monitor checks every 5 minutes for fills

FIXES IMPLEMENTED:
1. Uses dollar amounts (share_size = amount/price calculation)
2. Allows non-US markets with 2 sources if they agree within 1°C and edge > 15%
3. Implements tiered position sizing based on balance
4. Fetches FRESH prices at execution time (not stale scan prices)
5. CHANGED: Uses GTC with TTL (replaced FOK that never filled)
6. Re-validates ALL criteria against fresh prices before submitting

Position Sizing:
- Balance < $100: $5 per trade
- $100-200: $10 per trade
- $200-300: $15 per trade
- Pattern: ceil(balance/100) * $5
- Hard floor: stop if balance < $10
- Max 10 active positions

Criteria:
- US markets: 3 sources (NOAA+Open-Meteo+Visual Crossing), edge > 10%
- Non-US markets: 2 sources must agree within 1°C, edge > 15%
- Price 30-70¢ for all markets
- No duplicate markets
"""

import sys
import json
import math
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts to path
TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from polymarket_api import get_client, get_balance
from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY
from early_exit_manager import (
    PositionTracker, Position, monitor_and_exit, log_early_exits_to_journal
)
from forecast_monitor import (
    ForecastMonitor, monitor_all_positions, log_forecast_monitoring_to_journal
)
from trading_state_writer import (
    write_trading_state, log_balance_check, log_order_placed
)

# Journal directory
JOURNAL_DIR = TRADER_DIR / "polymarket-trader" / "journal"
JOURNAL_DIR.mkdir(exist_ok=True)

# Position tracking state file
STATE_DIR = TRADER_DIR / "polymarket-trader"
POSITION_STATE_FILE = STATE_DIR / "positions_state.json"
OPEN_ORDERS_FILE = STATE_DIR / "open_orders.json"

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

def check_market_has_open_order(condition_id):
    """Check if market already has an open order."""
    orders = load_open_orders()
    for order in orders:
        if order['condition_id'] == condition_id and order['status'] == 'OPEN':
            return True
    return False

def count_open_orders():
    """Count how many orders are currently open."""
    orders = load_open_orders()
    return sum(1 for o in orders if o['status'] == 'OPEN')

def calculate_position_size(balance_usdc):
    """
    Calculate position size based on tiered strategy.

    Balance < $100: $5
    $100-200: $10
    $200-300: $15
    Pattern: ceil(balance/100) * $5
    """
    if balance_usdc < 10:
        return 0  # Stop trading

    if balance_usdc < 100:
        return 5.0

    # Upper limit of $100 bracket × 5%
    bracket = math.ceil(balance_usdc / 100)
    return bracket * 5.0

def log_trade(trade_data):
    """Log trade to daily journal."""
    journal = get_todays_journal()

    with open(journal, 'a') as f:
        f.write(f"\n## GTC Order Placed - {datetime.now().strftime('%H:%M:%S')}\n\n")
        f.write(f"**Market**: {trade_data['city']} on {trade_data['date']}\n")
        f.write(f"**Question**: {trade_data['question'][:80]}\n")
        f.write(f"**Action**: {trade_data['action']}\n")
        f.write(f"**Edge**: {trade_data['edge']:.1f}%\n")
        f.write(f"**Confidence**: {trade_data['confidence']*100:.0f}%\n")
        f.write(f"**Sources**: {', '.join(trade_data['sources'])}\n")

        # Log both scan and execution prices to spot drift
        if 'scan_price' in trade_data and 'execution_price' in trade_data:
            scan_p = trade_data['scan_price'] * 100
            exec_p = trade_data['execution_price'] * 100
            drift = abs(exec_p - scan_p)
            f.write(f"**Scan Price**: {scan_p:.1f}¢\n")
            f.write(f"**Order Price**: {exec_p:.1f}¢ (drift: {drift:.1f}¢)\n")
        else:
            f.write(f"**Price**: {trade_data['price']*100:.1f}¢\n")

        f.write(f"**Amount**: ${trade_data['amount']:.2f}\n")
        f.write(f"**Expected Cost**: ~${trade_data['expected_cost']:.2f}\n")

        if trade_data.get('success'):
            f.write(f"**Status**: ✅ GTC ORDER PLACED\n")
            f.write(f"**Order ID**: {trade_data['order_id']}\n")
            f.write(f"**Order Type**: GTC with 30-min TTL\n")
            f.write(f"**Note**: Order sitting on book, waiting for fill\n")
        else:
            f.write(f"**Status**: ❌ FAILED\n")
            f.write(f"**Error**: {trade_data['error']}\n")

        f.write("\n")

def get_token_id_and_fresh_price(client, condition_id, side):
    """
    Get token ID AND fresh market price using client.get_market(condition_id).
    Returns (token_id, current_price) or (None, None) on error.

    FIX for:
    - Empty clobTokenIds from Gamma API
    - Stale prices from scan time
    """
    try:
        market_data = client.get_market(condition_id)
        tokens = market_data.get('tokens', [])

        token_id = None
        current_price = None

        for token in tokens:
            if token.get('outcome', '').upper() == side.upper():
                token_id = token.get('token_id')
                # Get fresh price from token
                current_price = float(token.get('price', 0))
                break

        return token_id, current_price
    except Exception as e:
        print(f"    ❌ Error getting token data: {e}")
        return None, None

def check_source_agreement(forecasts, max_diff_celsius=1.0):
    """
    Check if forecast sources agree within max_diff.

    For non-US markets with 2 sources.
    """
    if len(forecasts) < 2:
        return False

    temps = [f['high_c'] for f in forecasts]
    max_temp = max(temps)
    min_temp = min(temps)

    return (max_temp - min_temp) <= max_diff_celsius

def main():
    print("="*70)
    print("🎯 AUTONOMOUS WEATHER ARBITRAGE TRADING V3")
    print("="*70)
    print()
    print("EXECUTION STRATEGY: GTC with 30-minute TTL")
    print("  ✓ GTC maker orders (provide liquidity on order book)")
    print("  ✓ 30-minute auto-cancellation (no locked funds)")
    print("  ✓ Order monitor checks every 5 minutes")
    print("  ✓ Max 3 open orders, 1 per market")
    print()
    print("FIXES APPLIED:")
    print("  ✓ FIX 1: Using MarketOrderArgs with amount (dollars)")
    print("  ✓ FIX 2: Non-US markets allowed (2 sources, 15% edge)")
    print("  ✓ FIX 3: Tiered position sizing by balance")
    print("  ✓ NEW: Early exit strategy (2x entry = sell half, recover cost)")
    print("  ✓ NEW: Forecast monitoring (4-hour data re-checks, exit if edge < 5%)")
    print()
    print("Configuration:")
    print("  - US markets: 3 sources, edge > 10%, price 30-70¢")
    print("  - Non-US markets: 2 sources (agreement <1°C), edge > 15%, price 30-70¢")
    print("  - Position sizing: Tiered by balance")
    print("  - Early exit: Sell half at 2x entry to recover cost")
    print("  - Forecast monitoring: Every 4 hours, exit if edge < 5%")
    print("  - Max trades: 9 (already have 1 active)")
    print("  - Stop if balance < $10")
    print()

    # Connect
    client = get_client(signature_type=1)
    initial_balance = get_balance(client)

    print(f"Initial Balance: ${initial_balance['balance_usdc']:.2f}")
    print(f"Wallet: {initial_balance['wallet'][:6]}...{initial_balance['wallet'][-4:]}")
    print()

    # Write initial trading state (balance check)
    tracker = PositionTracker(POSITION_STATE_FILE)
    open_orders = load_open_orders()
    active_positions = [vars(p) for p in tracker.get_active_positions()]
    recent_activity = log_balance_check(initial_balance)
    write_trading_state(initial_balance, open_orders, active_positions, recent_activity)
    print("📊 Trading state updated (balance check)")
    print()

    if initial_balance['balance_usdc'] < 10:
        print("❌ Balance below $10 - cannot trade")
        return

    # Initialize forecast monitor
    forecast_monitor = ForecastMonitor(POSITION_STATE_FILE)
    print(f"Position Tracker: {len(tracker.get_active_positions())} active positions")
    print()

    # STEP 0: Check forecast data every 4 hours (runs BEFORE price-based exits)
    if forecast_monitor.should_run_check():
        print("="*70)
        print("STEP 0: FORECAST MONITORING (4-Hour Data Re-Check)")
        print("="*70)
        print()

        forecast_checks = monitor_all_positions(client, tracker, get_token_id_and_fresh_price, forecast_monitor)

        if forecast_checks:
            # Save updated state with forecast monitoring data
            state_data = {
                'positions': [vars(pos) for pos in tracker.get_active_positions()],
                'exits': [vars(exit) for exit in tracker.exits]
            }
            forecast_monitor.save_state(state_data)

            # Log to journal
            log_forecast_monitoring_to_journal(get_todays_journal(), forecast_checks)
            print(f"✅ Logged forecast monitoring to journal")
            print()

        # Update balance after any forecast exits
        exits_count = sum(1 for c in forecast_checks if c.exit_executed)
        if exits_count > 0:
            current_balance = get_balance(client)
            print(f"Balance after forecast exits: ${current_balance['balance_usdc']:.2f}")
            print()
    else:
        time_since_last = datetime.now() - forecast_monitor.last_check_time if forecast_monitor.last_check_time else None
        if time_since_last:
            hours = time_since_last.total_seconds() / 3600
            print(f"⏭️  Skipping forecast check (last check {hours:.1f}h ago, runs every 4h)")
            print()

    # STEP 1: Check for early exit opportunities BEFORE scanning for new trades
    print("="*70)
    print("STEP 1: CHECK EARLY EXIT OPPORTUNITIES (2× Price)")
    print("="*70)
    print()

    early_exits = monitor_and_exit(client, tracker, get_token_id_and_fresh_price)

    if early_exits:
        # Log exits to journal
        log_early_exits_to_journal(get_todays_journal(), early_exits)
        print(f"✅ Logged {len(early_exits)} early exits to journal")
        print()

    # Update balance after exits
    if early_exits:
        current_balance = get_balance(client)
        print(f"Balance after exits: ${current_balance['balance_usdc']:.2f}")
        print()

    # STEP 2: Check open order limits
    open_order_count = count_open_orders()
    print(f"📋 Open orders: {open_order_count}/3")

    if open_order_count >= 3:
        print("⚠️  Max open orders (3) reached - skipping new scans")
        print("   Wait for orders to fill or expire before placing new ones")
        return
    print()

    # STEP 3: Scan for new trading opportunities
    print("="*70)
    print("STEP 3: SCAN FOR NEW OPPORTUNITIES")
    print("="*70)
    print()

    # Scan for opportunities
    print("🔍 Scanning weather markets...")
    print()

    cutoff_date = datetime.now() + timedelta(hours=72)
    events = get_weather_events(days_ahead=3)

    qualifying_opps = []

    # Track active markets (Chicago already active)
    active_markets = {'Chicago'}  # Already have 1 position

    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue

        event_date = parsed.get('date')
        if isinstance(event_date, str):
            try:
                event_date = datetime.fromisoformat(event_date)
            except:
                continue

        if event_date > cutoff_date or event_date < datetime.now():
            continue

        opps = analyze_weather_event(parsed)

        for opp in opps:
            edge = opp['confidence_adjusted_edge']
            conf = opp['forecast_confidence']
            yes_p = opp['market_yes_price']
            no_p = opp['market_no_price']
            sources = opp['forecast_sources']
            num_sources = len(sources)

            # Skip if already have position in this city
            city = opp.get('city', '')
            if city in active_markets:
                continue

            # Get condition_id early to check for open orders
            event = opp.get('event_data')
            if not event:
                continue

            markets = event.get('markets', [])
            market_question = opp.get('market_question', '')

            condition_id = None
            for market in markets:
                mq = market.get('question', '')
                if market_question in mq or mq in market_question:
                    condition_id = market.get('conditionId')
                    break

            # Skip if no condition_id or already has open order
            if not condition_id:
                continue

            if check_market_has_open_order(condition_id):
                continue

            # Check price range
            if not (0.30 <= yes_p <= 0.70 or 0.30 <= no_p <= 0.70):
                continue

            # Check confidence
            if conf < 0.80:
                continue

            # Determine if US market (has NOAA)
            is_us = 'noaa' in sources

            # Apply different criteria for US vs non-US
            qualifies = False

            if is_us:
                # US market: 3 sources, edge > 10%
                if num_sources >= 3 and edge >= 10.0:
                    qualifies = True
            else:
                # Non-US market: 2 sources, agreement <1°C, edge > 15%
                if num_sources >= 2 and edge >= 15.0:
                    # Check source agreement
                    forecasts = opp.get('individual_forecasts', [])
                    if forecasts and check_source_agreement(forecasts, max_diff_celsius=1.0):
                        qualifies = True

            if qualifies:
                opp['date'] = event_date
                opp['event_data'] = event
                opp['is_us_market'] = is_us
                opp['condition_id'] = condition_id  # Store for later
                qualifying_opps.append(opp)

    # Sort by edge
    qualifying_opps.sort(key=lambda x: x['confidence_adjusted_edge'], reverse=True)

    print(f"✅ Found {len(qualifying_opps)} qualifying opportunities")
    print()

    if len(qualifying_opps) == 0:
        print("❌ No opportunities found meeting criteria")
        return

    # Execute up to available slots (max 3 open orders total)
    available_slots = 3 - open_order_count
    max_trades = min(available_slots, len(qualifying_opps))

    if max_trades == 0:
        print("❌ No available order slots (3 open orders already)")
        return

    print(f"Will attempt to place {max_trades} GTC orders (slots: {available_slots}/3)")
    print()

    trades_executed = []
    trades_failed = []

    for i, opp in enumerate(qualifying_opps[:max_trades], 1):
        # Check balance before each trade
        current_bal = get_balance(client)
        balance_usdc = current_bal['balance_usdc']

        if balance_usdc < 10:
            print(f"⚠️  Balance dropped below $10 - stopping")
            remaining = qualifying_opps[i-1:]
            for r in remaining:
                trades_failed.append({
                    'city': r.get('city'),
                    'reason': 'Insufficient balance',
                    'edge': r['confidence_adjusted_edge']
                })
            break

        # Calculate position size
        position_size = calculate_position_size(balance_usdc)

        print(f"{'='*70}")
        print(f"TRADE {i}/{max_trades}")
        print(f"{'='*70}")

        city = opp.get('city', 'Unknown')
        date_str = opp['date'].strftime('%Y-%m-%d') if hasattr(opp['date'], 'strftime') else str(opp['date'])
        question = opp.get('market_question', 'N/A')
        edge = opp['confidence_adjusted_edge']
        conf = opp['forecast_confidence']
        sources = opp['forecast_sources']
        is_us = opp.get('is_us_market', False)

        print(f"Market: {city} on {date_str}")
        print(f"Type: {'US' if is_us else 'Non-US'} market")
        print(f"Question: {question[:70]}")
        print(f"Edge: {edge:.1f}%")
        print(f"Confidence: {conf*100:.0f}%")
        print(f"Sources: {', '.join(sources)} ({len(sources)} sources)")

        # Show source agreement for non-US
        if not is_us:
            forecasts = opp.get('individual_forecasts', [])
            if forecasts:
                temps = [f['high_c'] for f in forecasts]
                spread = max(temps) - min(temps)
                print(f"Source agreement: {spread:.1f}°C spread")

        # Determine side from scan
        side = "YES" if "YES" in opp['action'] else "NO"
        scan_yes_price = opp['market_yes_price']
        scan_no_price = opp['market_no_price']
        scan_price = scan_yes_price if side == "YES" else scan_no_price

        print(f"Scan price: {side} @ {scan_price*100:.1f}¢")
        print(f"Position size: ${position_size:.2f} (Balance: ${balance_usdc:.2f})")
        print()

        # Get condition_id (pre-validated during scan)
        condition_id = opp.get('condition_id')

        if not condition_id:
            print(f"    ❌ No condition_id")
            trades_failed.append({
                'city': city,
                'reason': 'No condition_id',
                'edge': edge
            })
            print()
            continue

        print(f"    Condition ID: {condition_id[:20]}...")

        # Get token ID AND fresh price
        print(f"    Fetching fresh market data...")
        token_id, fresh_price = get_token_id_and_fresh_price(client, condition_id, side)

        if not token_id or fresh_price is None:
            print(f"    ❌ Could not retrieve token data")
            trades_failed.append({
                'city': city,
                'reason': f'No token data for {side}',
                'edge': edge
            })
            print()
            continue

        print(f"    Token ID: {str(token_id)[:20]}...")
        print(f"    Fresh price: {fresh_price*100:.1f}¢ (scan: {scan_price*100:.1f}¢, drift: {abs(fresh_price - scan_price)*100:.1f}¢)")
        print()

        # RE-VALIDATE ALL CRITERIA against fresh price
        print(f"    Re-validating entry criteria with fresh price...")

        # Check 1: Price still 30-70¢?
        if not (0.30 <= fresh_price <= 0.70):
            print(f"    ❌ SKIP - Fresh price {fresh_price*100:.1f}¢ outside 30-70¢ range")
            trades_failed.append({
                'city': city,
                'reason': f'Price moved to {fresh_price*100:.1f}¢ (outside range)',
                'edge': edge
            })
            print()
            continue

        # Check 2: Recalculate edge with fresh price
        # forecast_prob from scan is still valid (weather doesn't change in seconds)
        forecast_prob = opp.get('forecast_probability', 0.5)
        fresh_edge = abs(forecast_prob - fresh_price) * 100

        required_edge = 10.0 if is_us else 15.0
        if fresh_edge < required_edge:
            print(f"    ❌ SKIP - Fresh edge {fresh_edge:.1f}% below threshold ({required_edge:.0f}%)")
            trades_failed.append({
                'city': city,
                'reason': f'Edge dropped to {fresh_edge:.1f}% (below {required_edge:.0f}%)',
                'edge': fresh_edge
            })
            print()
            continue

        print(f"    ✅ All criteria still valid")
        print(f"    Fresh edge: {fresh_edge:.1f}%")
        print()

        # Use fresh price for execution (we're MAKING the market)
        execution_price = fresh_price
        expected_cost = position_size * execution_price

        # Execute trade with GTC (Good-Til-Cancel with 30min TTL)
        print(f"    🚀 Submitting GTC maker order for ${position_size:.2f} @ {execution_price*100:.1f}¢...")
        print(f"       Order will auto-cancel in 30 minutes if not filled")

        trade_log = {
            'city': city,
            'date': date_str,
            'question': question,
            'action': f'BUY {side}',
            'edge': fresh_edge,  # Use fresh edge
            'confidence': conf,
            'sources': sources,
            'scan_price': scan_price,
            'execution_price': execution_price,
            'price': execution_price,  # For compatibility
            'amount': position_size,
            'expected_cost': expected_cost
        }

        try:
            # Use MarketOrderArgs with dollar amount and GTC
            # This places a maker order on the book
            order_args = MarketOrderArgs(
                token_id=str(token_id),
                amount=position_size,  # Dollar amount to spend
                side=BUY,
                price=execution_price,  # Limit price (provide liquidity at this price)
                order_type=OrderType.GTC  # Good-Til-Cancel (sits on book)
            )

            # Create the signed order
            signed_order = client.create_market_order(order_args)

            # Post it with GTC order type
            response = client.post_order(signed_order, OrderType.GTC)

            order_id = response.get('orderID', 'N/A')

            # Calculate TTL expiry (30 minutes from now)
            time_placed = datetime.now()
            ttl_expiry = time_placed + timedelta(minutes=30)

            # Track the open order
            open_orders = load_open_orders()
            open_orders.append({
                'order_id': order_id,
                'market': f"{city} - {date_str}",
                'condition_id': condition_id,
                'token_id': str(token_id),
                'side': side,
                'price': execution_price,
                'amount': position_size,
                'time_placed': time_placed.isoformat(),
                'ttl_expiry': ttl_expiry.isoformat(),
                'status': 'OPEN',
                'edge': fresh_edge,
                'sources': sources,
                'question': question[:80]
            })
            save_open_orders(open_orders)

            print(f"    ✅ GTC ORDER PLACED!")
            print(f"    Order ID: {order_id}")
            print(f"    TTL expires: {ttl_expiry.strftime('%H:%M:%S')} (30 min)")
            print(f"    📋 Order tracked in open_orders.json")
            print()

            # Update trading state
            current_balance = get_balance(client)
            all_positions = [vars(p) for p in tracker.get_active_positions()]
            recent_activity = log_order_placed(open_orders[-1])
            write_trading_state(current_balance, open_orders, all_positions, recent_activity)
            print(f"    📊 Trading state updated")
            print()

            trade_log['success'] = True
            trade_log['order_id'] = order_id

            trades_executed.append({
                'city': city,
                'date': date_str,
                'side': side,
                'scan_price': scan_price,
                'execution_price': execution_price,
                'amount': position_size,
                'expected_cost': expected_cost,
                'edge': fresh_edge,
                'order_id': order_id,
                'status': 'OPEN'
            })

            # Don't add to active markets yet (order not filled)
            # Don't track position yet (will be tracked by order_monitor when filled)

            # Log to journal
            log_trade(trade_log)

        except Exception as e:
            error_msg = str(e)
            print(f"    ❌ Trade failed: {error_msg[:80]}")

            trade_log['success'] = False
            trade_log['error'] = error_msg[:100]

            trades_failed.append({
                'city': city,
                'reason': error_msg[:50],
                'edge': edge
            })

            # Log failure
            log_trade(trade_log)

            if "403" in error_msg or "regional" in error_msg.lower():
                print(f"    🚫 GEO-BLOCKING DETECTED - Stopping")
                break

            print()

    # Final summary
    print()
    print("="*70)
    print("EXECUTION SUMMARY")
    print("="*70)
    print()

    final_balance = get_balance(client)
    final_open_orders = count_open_orders()

    print(f"GTC orders placed: {len(trades_executed)}")
    print(f"Total open orders: {final_open_orders}/3")
    print(f"Orders failed: {len(trades_failed)}")
    print()
    print(f"Balance: ${final_balance['balance_usdc']:.2f} (funds locked in open orders)")
    print()

    if trades_executed:
        print("✅ GTC orders placed (waiting to fill):")
        for t in trades_executed:
            exec_p = t['execution_price'] * 100
            scan_p = t['scan_price'] * 100
            drift = abs(exec_p - scan_p)
            print(f"  {t['city']} ({t['date']}): BUY {t['side']} @ {exec_p:.0f}¢")
            print(f"    Amount: ${t['amount']:.2f}, Edge: {t['edge']:.1f}%, Drift: {drift:.1f}¢")
            print(f"    Order: {t['order_id']}")
            print(f"    Status: OPEN (expires in 30 min)")
        print()
        print("📋 Orders tracked in open_orders.json")
        print("🔍 Run order_monitor.py to check fill status")
        print()

    if trades_failed:
        print("❌ Failed trades:")
        for t in trades_failed[:5]:
            print(f"  {t['city']}: {t['reason'][:50]}")
        print()

    print(f"📝 Full log: {get_todays_journal()}")
    print()
    print("="*70)

if __name__ == "__main__":
    main()
