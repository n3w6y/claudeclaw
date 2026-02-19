#!/usr/bin/env python3
"""
SUPERVISED WEATHER ARBITRAGE SCANNER

Runs every 2 hours, logs opportunities, requires approval for first 10 trades.
"""

import sys
import json
from datetime import datetime
from pathlib import Path

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event
from polymarket_api import get_client
from early_exit_manager import PositionTracker, monitor_and_exit, log_early_exits_to_journal
from forecast_monitor import ForecastMonitor, monitor_all_positions, log_forecast_monitoring_to_journal

# Paths
JOURNAL_DIR = Path(__file__).parent / "polymarket-trader" / "journal"
JOURNAL_DIR.mkdir(exist_ok=True)

STATE_DIR = Path(__file__).parent / "polymarket-trader"
POSITION_STATE_FILE = STATE_DIR / "positions_state.json"

def get_todays_log():
    """Get today's log file path."""
    today = datetime.now().strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"{today}.md"

def log_scan(opportunities, scan_time):
    """Log scan results to daily journal."""
    log_file = get_todays_log()

    with open(log_file, 'a') as f:
        f.write(f"\n## Weather Scan - {scan_time.strftime('%H:%M:%S')}\n\n")

        if not opportunities:
            f.write("No opportunities found above threshold.\n")
        else:
            f.write(f"Found {len(opportunities)} opportunities:\n\n")

            for opp in opportunities[:10]:  # Top 10
                f.write(f"### {opp['action']} - {opp['edge_pct']:.1f}% edge\n")
                f.write(f"- **Market**: {opp['city']} on {opp['date']}\n")
                f.write(f"- **Forecast**: {opp['forecast_temp']} ({len(opp['forecast_sources'])} sources: {', '.join(opp['forecast_sources'])})\n")
                f.write(f"- **Confidence**: {opp['forecast_confidence']*100:.0f}%\n")
                f.write(f"- **Market Price**: YES {opp['market_yes_price']*100:.0f}¢ / NO {opp['market_no_price']*100:.0f}¢\n")
                f.write(f"- **Our Probability**: {opp['forecast_prob']*100:.0f}%\n")
                f.write(f"- **Edge**: {opp['edge_pct']:.1f}% (adj: {opp['confidence_adjusted_edge']:.1f}%)\n")
                f.write(f"- **EV**: {opp['expected_value']:.2f}x\n")
                f.write(f"- **URL**: {opp['url']}\n\n")

def calculate_position_size(edge_pct, confidence, balance_usdc=99.94):
    """Calculate position size based on tier rules."""
    # Balance < $100: max $5
    if balance_usdc < 100:
        max_size = 5.0
    elif balance_usdc < 500:
        max_size = 10.0
    else:
        max_size = 25.0

    # Adjust by confidence and edge
    if confidence >= 0.8 and edge_pct >= 10:
        return max_size
    elif confidence >= 0.7 and edge_pct >= 7:
        return max_size * 0.8
    elif confidence >= 0.6 and edge_pct >= 5:
        return max_size * 0.6
    else:
        return max_size * 0.4

def format_opportunity(opp, balance=99.94):
    """Format opportunity for user notification."""
    size = calculate_position_size(
        opp['confidence_adjusted_edge'],
        opp['forecast_confidence'],
        balance
    )

    conf_emoji = "🟢" if opp['forecast_confidence'] > 0.8 else "🟡" if opp['forecast_confidence'] > 0.6 else "🔴"

    msg = f"\n{'='*70}\n"
    msg += f"🎯 **{opp['action']}** - {opp['edge_pct']:.1f}% edge ({opp['confidence_adjusted_edge']:.1f}% adj)\n\n"
    msg += f"**Market**: {opp['city']} on {opp['date']}\n"
    msg += f"**Question**: {opp['market_question']}\n\n"
    msg += f"**Forecast Sources**: {', '.join(opp['forecast_sources'])} ({len(opp['forecast_sources'])} sources)\n"
    msg += f"**Forecast Temp**: {opp['forecast_temp']}\n"

    if opp['individual_forecasts']:
        msg += f"**Individual Forecasts**:\n"
        for fc in opp['individual_forecasts']:
            msg += f"  - {fc['source']}: {fc['high_c']:.1f}°C\n"

    msg += f"\n{conf_emoji} **Consensus Confidence**: {opp['forecast_confidence']*100:.0f}%\n"

    if opp.get('forecast_spread'):
        msg += f"**Spread**: ±{opp['forecast_spread']:.1f}°C\n"

    msg += f"\n**Market Price**: YES {opp['market_yes_price']*100:.0f}¢ / NO {opp['market_no_price']*100:.0f}¢\n"
    msg += f"**Our Probability**: {opp['forecast_prob']*100:.0f}% YES\n"
    msg += f"**Expected Value**: {opp['expected_value']:.2f}x\n"
    msg += f"**Liquidity**: ${opp['liquidity']:,.0f}\n\n"
    msg += f"💵 **Recommended Size**: ${size:.2f}\n"
    msg += f"🔗 **URL**: {opp['url']}\n"
    msg += f"{'='*70}\n"

    return msg

def scan_weather_markets(min_edge=5.0, days_ahead=3):
    """Scan weather markets for opportunities."""
    print("🌡️  WEATHER ARBITRAGE SCAN")
    print(f"   Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   Min edge: {min_edge}%\n")

    # Fetch weather events
    print("   Fetching weather markets from Polymarket...")
    events = get_weather_events(days_ahead=days_ahead)
    print(f"   Found {len(events)} weather events\n")

    if not events:
        print("   ⚠️  No weather markets found")
        return []

    # Analyze each event
    all_opportunities = []
    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue

        print(f"   Analyzing {parsed['city']} on {parsed['date'].strftime('%Y-%m-%d')}...")
        opps = analyze_weather_event(parsed)
        all_opportunities.extend(opps)

    # Filter by adjusted edge
    filtered = [o for o in all_opportunities if o['confidence_adjusted_edge'] >= min_edge]
    filtered.sort(key=lambda x: x['confidence_adjusted_edge'], reverse=True)

    print(f"\n   ✅ Found {len(filtered)} opportunities above {min_edge}% adjusted edge\n")

    # Log to journal
    scan_time = datetime.now()
    log_scan(filtered, scan_time)
    print(f"   📝 Logged to {get_todays_log()}\n")

    return filtered

def get_token_id_and_fresh_price(client, condition_id, side):
    """
    Get token ID AND fresh market price (same as in autonomous_trader_v2.py).
    """
    try:
        market_data = client.get_market(condition_id)
        tokens = market_data.get('tokens', [])

        token_id = None
        current_price = None

        for token in tokens:
            if token.get('outcome', '').upper() == side.upper():
                token_id = token.get('token_id')
                current_price = float(token.get('price', 0))
                break

        return token_id, current_price
    except Exception as e:
        print(f"    ❌ Error getting token data: {e}")
        return None, None

def main():
    """Run scan and display opportunities."""
    # Check for forecast monitoring and early exits first
    try:
        client = get_client(signature_type=1)
        tracker = PositionTracker(POSITION_STATE_FILE)
        forecast_monitor = ForecastMonitor(POSITION_STATE_FILE)

        active_positions = tracker.get_active_positions()
        print(f"Active positions: {len(active_positions)}")
        print()

        # STEP 0: Forecast monitoring (every 4 hours)
        if active_positions and forecast_monitor.should_run_check():
            print("="*70)
            print("🔬 FORECAST MONITORING (4-Hour Data Re-Check)")
            print("="*70)
            print()

            forecast_checks = monitor_all_positions(client, tracker, get_token_id_and_fresh_price, forecast_monitor)

            if forecast_checks:
                # Save state
                state_data = {
                    'positions': [vars(pos) for pos in tracker.get_active_positions()],
                    'exits': [vars(exit) for exit in tracker.exits]
                }
                forecast_monitor.save_state(state_data)

                # Log to journal
                log_forecast_monitoring_to_journal(get_todays_log(), forecast_checks)
                print(f"✅ Logged forecast monitoring to journal")
                print()

        # STEP 1: Early exits (2× price)
        print("="*70)
        print("🔍 CHECKING FOR EARLY EXIT OPPORTUNITIES (2× Price)")
        print("="*70)
        print()

        active_positions = tracker.get_active_positions()  # Refresh after potential forecast exits
        if active_positions:
            early_exits = monitor_and_exit(client, tracker, get_token_id_and_fresh_price)

            if early_exits:
                log_early_exits_to_journal(get_todays_log(), early_exits)
                print(f"✅ Executed and logged {len(early_exits)} early exits")
                print()

        print("="*70)
        print("📊 SCANNING FOR NEW OPPORTUNITIES")
        print("="*70)
        print()

    except Exception as e:
        print(f"⚠️  Error during position monitoring: {e}")
        print("   Continuing with scan...\n")

    opportunities = scan_weather_markets(min_edge=5.0, days_ahead=3)

    if not opportunities:
        print("   No opportunities found at current threshold.")
        print("   Markets may be efficient or forecasts aligned with odds.\n")
        return

    print(f"{'='*70}")
    print(f"📊 OPPORTUNITIES SUMMARY")
    print(f"{'='*70}\n")

    for i, opp in enumerate(opportunities[:5], 1):  # Show top 5
        print(f"\n{i}. {format_opportunity(opp)}")

    print("\n💬 RECOMMENDATIONS:")
    for i, opp in enumerate(opportunities[:5], 1):
        action_emoji = "✅" if opp['action'] == "BUY YES" else "❌"
        print(f"   {i}. {action_emoji} {opp['action']} {opp['city']} ({opp['confidence_adjusted_edge']:.1f}% edge)")

    print(f"\n⚠️  AWAITING APPROVAL - No trades placed (supervised mode)")
    print(f"   Total opportunities: {len(opportunities)}")
    print(f"   Log: {get_todays_log()}")

if __name__ == "__main__":
    main()
