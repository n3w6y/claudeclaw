#!/usr/bin/env python3
"""
Autonomous Weather Arbitrage Trader

Executes weather arbitrage trades with strict criteria:
- Edge > 10%
- Confidence > 80%
- Price 30-70¢
- 3-source triangulation

Uses client.get_market(condition_id) to retrieve token IDs (fix for empty clobTokenIds).
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

# Add scripts to path
TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from polymarket_api import get_client, get_balance
from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

# Journal directory
JOURNAL_DIR = TRADER_DIR / "polymarket-trader" / "journal"
JOURNAL_DIR.mkdir(exist_ok=True)

def get_todays_journal():
    """Get today's journal file."""
    today = datetime.now().strftime("%Y-%m-%d")
    return JOURNAL_DIR / f"{today}.md"

def log_trade(trade_data):
    """Log trade to daily journal."""
    journal = get_todays_journal()

    with open(journal, 'a') as f:
        f.write(f"\n## Trade - {datetime.now().strftime('%H:%M:%S')}\n\n")
        f.write(f"**Market**: {trade_data['city']} on {trade_data['date']}\n")
        f.write(f"**Question**: {trade_data['question'][:80]}\n")
        f.write(f"**Action**: {trade_data['action']}\n")
        f.write(f"**Edge**: {trade_data['edge']:.1f}%\n")
        f.write(f"**Confidence**: {trade_data['confidence']*100:.0f}%\n")
        f.write(f"**Sources**: {', '.join(trade_data['sources'])}\n")
        f.write(f"**Price**: {trade_data['price']*100:.1f}¢\n")
        f.write(f"**Size**: ${trade_data['size']:.2f}\n")
        f.write(f"**Cost**: ${trade_data['cost']:.2f}\n")

        if trade_data.get('success'):
            f.write(f"**Status**: ✅ EXECUTED\n")
            f.write(f"**Order ID**: {trade_data['order_id']}\n")
        else:
            f.write(f"**Status**: ❌ FAILED\n")
            f.write(f"**Error**: {trade_data['error']}\n")

        f.write("\n")

def get_token_id_from_condition(client, condition_id, side):
    """
    Get token ID using client.get_market(condition_id).

    This is the FIX for empty clobTokenIds from Gamma API.
    """
    try:
        market_data = client.get_market(condition_id)
        tokens = market_data.get('tokens', [])

        for token in tokens:
            if token.get('outcome', '').upper() == side.upper():
                return token.get('token_id')

        return None
    except Exception as e:
        print(f"    ❌ Error getting token ID: {e}")
        return None

def main():
    print("="*70)
    print("🎯 AUTONOMOUS WEATHER ARBITRAGE TRADING")
    print("="*70)
    print()
    print("Configuration:")
    print("  - Position size: $5 per trade")
    print("  - Max trades: 10")
    print("  - Min edge: 10%")
    print("  - Min confidence: 80%")
    print("  - Market price: 30-70¢")
    print("  - Sources: NOAA, Open-Meteo, Visual Crossing")
    print()

    # Connect
    client = get_client(signature_type=1)
    initial_balance = get_balance(client)

    print(f"Initial Balance: ${initial_balance['balance_usdc']:.2f}")
    print(f"Wallet: {initial_balance['wallet'][:6]}...{initial_balance['wallet'][-4:]}")
    print()

    # Scan for opportunities
    print("🔍 Scanning weather markets...")
    print()

    cutoff_date = datetime.now() + timedelta(hours=72)
    events = get_weather_events(days_ahead=3)

    qualifying_opps = []

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

            # Apply ALL criteria
            if (edge >= 10.0 and
                conf >= 0.80 and
                (0.30 <= yes_p <= 0.70 or 0.30 <= no_p <= 0.70) and
                len(opp['forecast_sources']) >= 3):

                opp['date'] = event_date
                opp['event_data'] = event  # Save for token lookup
                qualifying_opps.append(opp)

    # Sort by edge
    qualifying_opps.sort(key=lambda x: x['confidence_adjusted_edge'], reverse=True)

    print(f"✅ Found {len(qualifying_opps)} qualifying opportunities")
    print()

    if len(qualifying_opps) == 0:
        print("❌ No opportunities found meeting all criteria")
        return

    # Execute up to 10 trades
    max_trades = min(10, len(qualifying_opps))
    print(f"Will attempt to execute {max_trades} trades")
    print()

    trades_executed = []
    trades_failed = []

    for i, opp in enumerate(qualifying_opps[:max_trades], 1):
        print(f"{'='*70}")
        print(f"TRADE {i}/{max_trades}")
        print(f"{'='*70}")

        city = opp.get('city', 'Unknown')
        date_str = opp['date'].strftime('%Y-%m-%d') if hasattr(opp['date'], 'strftime') else str(opp['date'])
        question = opp.get('market_question', 'N/A')
        edge = opp['confidence_adjusted_edge']
        conf = opp['forecast_confidence']
        sources = opp['forecast_sources']

        print(f"Market: {city} on {date_str}")
        print(f"Question: {question[:70]}")
        print(f"Edge: {edge:.1f}%")
        print(f"Confidence: {conf*100:.0f}%")
        print(f"Sources: {', '.join(sources)}")

        # Determine side and price
        side = "YES" if "YES" in opp['action'] else "NO"
        yes_price = opp['market_yes_price']
        no_price = opp['market_no_price']
        price = yes_price if side == "YES" else no_price
        size = 5.0
        cost = size * price

        print(f"Action: BUY {side} @ {price*100:.1f}¢")
        print(f"Cost: ${cost:.2f}")
        print()

        # Get condition_id from event
        event = opp['event_data']
        markets = event.get('markets', [])

        # Find matching market
        target_market = None
        for market in markets:
            market_question = market.get('question', '')
            if question in market_question or market_question in question:
                target_market = market
                break

        if not target_market:
            print(f"    ❌ Could not find market in event data")
            trades_failed.append({
                'city': city,
                'reason': 'Market not found in event',
                'edge': edge
            })
            print()
            continue

        condition_id = target_market.get('conditionId')

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

        # Get token ID using the FIX
        print(f"    Getting token ID via client.get_market()...")
        token_id = get_token_id_from_condition(client, condition_id, side)

        if not token_id:
            print(f"    ❌ Could not retrieve token ID")
            trades_failed.append({
                'city': city,
                'reason': f'No token ID for {side}',
                'edge': edge
            })
            print()
            continue

        print(f"    Token ID: {str(token_id)[:20]}...")
        print()

        # Execute trade
        print(f"    🚀 Submitting order...")

        trade_log = {
            'city': city,
            'date': date_str,
            'question': question,
            'action': f'BUY {side}',
            'edge': edge,
            'confidence': conf,
            'sources': sources,
            'price': price,
            'size': size,
            'cost': cost
        }

        try:
            order_args = OrderArgs(
                token_id=str(token_id),
                price=price,
                size=size,
                side=BUY
            )

            response = client.create_and_post_order(order_args)

            order_id = response.get('orderID', 'N/A')

            print(f"    ✅ TRADE EXECUTED!")
            print(f"    Order ID: {order_id}")
            print()

            trade_log['success'] = True
            trade_log['order_id'] = order_id

            trades_executed.append({
                'city': city,
                'date': date_str,
                'side': side,
                'price': price,
                'cost': cost,
                'edge': edge,
                'order_id': order_id
            })

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

            # Log failure to journal
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
    spent = initial_balance['balance_usdc'] - final_balance['balance_usdc']

    print(f"Trades executed: {len(trades_executed)}")
    print(f"Trades failed: {len(trades_failed)}")
    print()
    print(f"Initial balance: ${initial_balance['balance_usdc']:.2f}")
    print(f"Final balance: ${final_balance['balance_usdc']:.2f}")
    print(f"Total spent: ${spent:.2f}")
    print()

    if trades_executed:
        print("✅ Executed trades:")
        for t in trades_executed:
            print(f"  {t['city']} ({t['date']}): BUY {t['side']} @ {t['price']*100:.0f}¢")
            print(f"    Cost: ${t['cost']:.2f}, Edge: {t['edge']:.1f}%, Order: {t['order_id']}")
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
