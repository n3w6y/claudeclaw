#!/usr/bin/env python3
"""
POSITION THESIS MONITORING

Monitors active positions every 4 hours by re-checking forecast data.
Exits positions if forecast thesis breaks (edge drops below 5%).
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from polymarket_api import get_client, get_open_orders
from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event, get_ensemble_forecast

JOURNAL_DIR = Path(__file__).parent / "polymarket-trader" / "journal"
POSITIONS_FILE = Path(__file__).parent / "polymarket-trader" / "cache" / "active_positions.json"

def load_active_positions():
    """Load active positions from cache."""
    if not POSITIONS_FILE.exists():
        return []

    with open(POSITIONS_FILE) as f:
        return json.load(f)

def save_active_positions(positions):
    """Save active positions to cache."""
    POSITIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(POSITIONS_FILE, 'w') as f:
        json.dump(positions, indent=2, fp=f)

def get_todays_log():
    """Get today's log file path."""
    today = datetime.now().strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"{today}.md"

def log_monitor_cycle(results, timestamp):
    """Log monitoring results to daily journal."""
    log_file = get_todays_log()

    with open(log_file, 'a') as f:
        f.write(f"\n## POSITION MONITOR - {timestamp.strftime('%H:%M:%S')}\n\n")

        if not results:
            f.write("No active positions to monitor.\n\n")
            return

        # Table header
        f.write("| Market | Entry Price | Current Price | Original Edge | Current Edge | Forecast Change | Action |\n")
        f.write("|--------|-------------|---------------|---------------|--------------|-----------------|--------|\n")

        for r in results:
            f.write(f"| {r['market']} | {r['entry_price']}¢ | {r['current_price']}¢ | "
                   f"{r['original_edge']:.1f}% | {r['current_edge']:.1f}% | "
                   f"{r['forecast_change']} | {r['action']} |\n")

        f.write("\n### Forecast Details\n\n")

        for r in results:
            if r.get('forecast_details'):
                f.write(f"**{r['market']}**: {r['forecast_details']}\n\n")

def monitor_position(position, events):
    """
    Monitor a single position against fresh forecast data.

    Returns dict with:
    - action: HOLD, EXIT, STRENGTHEN
    - current_edge: recalculated edge
    - forecast_change: description of change
    """
    city = position['city']
    date_str = position['date']
    question = position['question']
    original_edge = position['edge']
    entry_price = position['price']
    side = position['side']

    # Find the market
    market_data = None
    for event in events:
        parsed = parse_weather_event(event)
        if not parsed or parsed['city'].lower() != city.lower():
            continue
        if parsed['date'].strftime('%Y-%m-%d') != date_str:
            continue

        # Find matching question
        for market in parsed.get('markets', []):
            if market.get('question') == question:
                market_data = market
                break

        if market_data:
            break

    if not market_data:
        return {
            'action': 'HOLD',
            'current_edge': original_edge,
            'current_price': entry_price,
            'forecast_change': 'Market not found',
            'forecast_details': None
        }

    # Get fresh forecast
    parsed = parse_weather_event(event)
    opps = analyze_weather_event(parsed)

    # Find the specific opportunity
    current_opp = None
    for opp in opps:
        if opp['market_question'] == question:
            current_opp = opp
            break

    if not current_opp:
        return {
            'action': 'HOLD',
            'current_edge': original_edge,
            'current_price': entry_price,
            'forecast_change': 'Unable to recalculate',
            'forecast_details': None
        }

    # Compare forecasts
    original_temp = position.get('forecast_temp')
    current_temp = current_opp.get('forecast_temp')
    current_edge = current_opp.get('confidence_adjusted_edge')
    current_price = current_opp['market_yes_price'] if side == 'YES' else current_opp['market_no_price']

    # Determine action
    if abs(current_edge) < 5:
        action = 'EXIT'
        forecast_change = f"Edge collapsed: {original_edge:.1f}% → {current_edge:.1f}%"
        forecast_details = (f"Forecast changed from {original_temp} to {current_temp}. "
                          f"Edge now {current_edge:.1f}%, below 5% threshold.")

    elif abs(current_edge) > abs(original_edge) + 10:
        action = 'STRENGTHEN'
        forecast_change = f"Edge increased: {original_edge:.1f}% → {current_edge:.1f}%"
        forecast_details = (f"Forecast shifted from {original_temp} to {current_temp}. "
                          f"Position now stronger.")

    else:
        action = 'HOLD'
        temp_change = "unchanged" if original_temp == current_temp else f"{original_temp} → {current_temp}"
        forecast_change = temp_change
        forecast_details = None

    return {
        'action': action,
        'current_edge': current_edge,
        'current_price': current_price * 100,  # to cents
        'forecast_change': forecast_change,
        'forecast_details': forecast_details,
        'opportunity': current_opp if action in ['EXIT', 'STRENGTHEN'] else None
    }

def exit_position(client, position, reason):
    """Exit a position immediately at market price."""
    from py_clob_client.clob_types import OrderArgs
    from py_clob_client.order_builder.constants import SELL, BUY
    from py_clob_client.clob_types import OrderType

    # Parse token ID
    token_ids = json.loads(position['token_id'])

    # Determine which token to sell
    if position['side'] == 'YES':
        token_to_sell = token_ids[0]  # Selling YES token
        exit_side = SELL
    else:
        token_to_sell = token_ids[1]  # Selling NO token
        exit_side = SELL

    try:
        # FOK (Fill-Or-Kill) order at current market price
        order_args = OrderArgs(
            token_id=token_to_sell,
            price=0.50,  # Market order - willing to take any reasonable price
            size=position['shares'],
            side=exit_side
        )

        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, orderType=OrderType.FOK)

        return {
            'success': True,
            'order_id': response.get('orderID'),
            'reason': reason
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'reason': reason
        }

def monitor_all_positions():
    """Run monitoring cycle for all active positions."""
    print(f"🔍 POSITION MONITOR")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    positions = load_active_positions()

    if not positions:
        print("   No active positions to monitor.\n")
        log_monitor_cycle([], datetime.now())
        return

    print(f"   Monitoring {len(positions)} active position(s)...\n")

    # Filter positions that are within 2 hours of resolution
    now = datetime.now()
    positions_to_check = []

    for pos in positions:
        resolution_time = datetime.strptime(pos['date'], '%Y-%m-%d')
        hours_until = (resolution_time - now).total_seconds() / 3600

        if hours_until > 2:
            positions_to_check.append(pos)
        else:
            print(f"   ⏭️  Skipping {pos['market']} - resolves in {hours_until:.1f}h\n")

    if not positions_to_check:
        print("   All positions resolving soon - skipping checks.\n")
        return

    # Fetch current market data
    events = get_weather_events(days_ahead=3)

    results = []
    actions_taken = []
    client = None

    for pos in positions_to_check:
        print(f"   Checking {pos['market']}...")

        monitor_result = monitor_position(pos, events)

        result_row = {
            'market': pos['market'],
            'entry_price': pos['price'] * 100,
            'current_price': monitor_result['current_price'],
            'original_edge': pos['edge'],
            'current_edge': monitor_result['current_edge'],
            'forecast_change': monitor_result['forecast_change'],
            'action': monitor_result['action'],
            'forecast_details': monitor_result['forecast_details']
        }

        results.append(result_row)

        # Take action if needed
        if monitor_result['action'] == 'EXIT':
            if not client:
                client = get_client()

            print(f"   ⚠️  EXITING: {monitor_result['forecast_change']}")
            exit_result = exit_position(client, pos, monitor_result['forecast_details'])

            if exit_result['success']:
                print(f"   ✅ Position exited: {exit_result['order_id']}")
                actions_taken.append({
                    'position': pos['market'],
                    'action': 'EXITED',
                    'reason': exit_result['reason']
                })
                # Remove from active positions
                positions.remove(pos)
            else:
                print(f"   ❌ Exit failed: {exit_result['error']}")

        elif monitor_result['action'] == 'STRENGTHEN':
            print(f"   📈 STRENGTHEN: {monitor_result['forecast_change']}")
            actions_taken.append({
                'position': pos['market'],
                'action': 'STRENGTHEN',
                'details': monitor_result['forecast_details']
            })

        else:
            print(f"   ✅ HOLD: {monitor_result['forecast_change']}")

        print()

    # Save updated positions
    save_active_positions(positions)

    # Log results
    log_monitor_cycle(results, datetime.now())

    print(f"   📝 Monitor cycle logged to {get_todays_log()}")

    if actions_taken:
        print(f"\n   Actions taken:")
        for action in actions_taken:
            print(f"   - {action['action']}: {action['position']}")

    print()

def main():
    """Run position monitoring."""
    monitor_all_positions()

if __name__ == "__main__":
    main()
