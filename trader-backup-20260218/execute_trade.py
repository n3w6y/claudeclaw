#!/usr/bin/env python3
"""
Execute a single Polymarket trade with detailed reporting.
"""

import sys
import json
from pathlib import Path
from datetime import datetime

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from polymarket_api import get_client, place_order, get_balance

def find_market_by_url(url):
    """Extract slug from URL and fetch market details."""
    import re
    from urllib.request import urlopen, Request

    # Extract slug from URL
    # Example: https://polymarket.com/event/highest-temperature-in-chicago-on-february-14-2026
    slug_match = re.search(r'/event/([^/?]+)', url)
    if not slug_match:
        return None

    slug = slug_match.group(1)

    # Fetch market details from Gamma API
    gamma_url = f"https://gamma-api.polymarket.com/events?slug={slug}"
    req = Request(gamma_url, headers={"User-Agent": "PolymarketTrader/1.0"})

    with urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())

    if not data:
        return None

    event = data[0] if isinstance(data, list) else data

    # Get first market from event
    markets = event.get('markets', [])
    if not markets:
        return None

    market = markets[0]

    # Parse tokens - they're in a nested structure
    tokens_raw = market.get('tokens', [])
    outcomes = json.loads(market.get('outcomes', '[]'))
    prices_raw = json.loads(market.get('outcomePrices', '[]'))

    # Map outcomes to tokens
    token_map = {}
    for i, token in enumerate(tokens_raw):
        if i < len(outcomes):
            outcome = outcomes[i].upper()
            token_map[outcome] = token.get('token_id')

    # If tokens empty, try alternative structure
    if not token_map and outcomes:
        # Build from outcomes and tokens arrays
        for i, outcome in enumerate(outcomes):
            if i < len(tokens_raw):
                token_map[outcome.upper()] = tokens_raw[i].get('token_id')

    prices = {outcomes[i].upper(): float(prices_raw[i]) for i in range(len(outcomes))}

    return {
        'question': market.get('question'),
        'condition_id': market.get('conditionId'),
        'tokens': token_map,
        'prices': prices,
        'volume': float(market.get('volume', 0)),
        'liquidity': float(market.get('liquidity', 0)),
    }

def execute_trade(market_url, side, size_usd):
    """Execute a trade on Polymarket."""

    print(f"{'='*70}")
    print(f"🎯 EXECUTING POLYMARKET TRADE")
    print(f"{'='*70}\n")

    # Step 1: Get market details
    print("📊 Fetching market details...")
    market = find_market_by_url(market_url)

    if not market:
        print("❌ Failed to find market")
        return

    print(f"   Question: {market['question']}")
    print(f"   Volume: ${market['volume']:,.0f}")
    print(f"   Liquidity: ${market['liquidity']:,.0f}")
    print(f"   Current prices:")
    for outcome, price in market['prices'].items():
        print(f"      {outcome}: {price*100:.1f}¢")
    print()

    # Step 2: Get client and balance
    print("🔑 Connecting to Polymarket...")
    client = get_client()
    balance = get_balance(client)

    if 'error' in balance:
        print(f"❌ Balance check failed: {balance['error']}")
        return

    print(f"   Wallet: {balance['wallet'][:10]}...{balance['wallet'][-8:]}")
    print(f"   Balance: ${balance['balance_usdc']:.2f} USDC\n")

    # Step 3: Validate trade
    side_upper = side.upper()

    # Debug: show available tokens
    print(f"🔍 Available tokens: {list(market['tokens'].keys())}")

    if side_upper not in market['tokens']:
        print(f"❌ Invalid side '{side}' (uppercase: '{side_upper}'). Must be YES or NO")
        print(f"   Available: {list(market['tokens'].keys())}")
        return

    token_id = market['tokens'][side_upper]
    price = market['prices'][side_upper]

    # Calculate cost
    cost_estimate = size_usd * price

    print(f"💵 Trade Details:")
    print(f"   Side: {side_upper}")
    print(f"   Token ID: {token_id[:16]}...")
    print(f"   Size: {size_usd} shares")
    print(f"   Price: {price*100:.1f}¢")
    print(f"   Estimated cost: ${cost_estimate:.2f}")
    print()

    if cost_estimate > balance['balance_usdc']:
        print(f"❌ Insufficient balance (need ${cost_estimate:.2f}, have ${balance['balance_usdc']:.2f})")
        return

    # Step 4: Place order
    print(f"🚀 Placing order...")
    result = place_order(
        client=client,
        token_id=token_id,
        side="BUY",
        size=size_usd,
        price=price
    )

    print()
    print(f"{'='*70}")
    print(f"📋 TRADE RESULT")
    print(f"{'='*70}\n")

    if result.get('success'):
        print(f"✅ TRADE EXECUTED SUCCESSFULLY")
        print(f"   Order ID: {result.get('order_id', 'N/A')}")
        print(f"   Side: {side_upper}")
        print(f"   Shares: {size_usd}")
        print(f"   Price: {price*100:.1f}¢")
        print(f"   Cost: ${cost_estimate:.2f}")

        # Log trade
        log_file = Path(__file__).parent / "polymarket-trader" / "journal" / "supervised_trades.log"
        log_file.parent.mkdir(exist_ok=True)

        with open(log_file, 'a') as f:
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "market_url": market_url,
                "question": market['question'],
                "side": side_upper,
                "size": size_usd,
                "price": price,
                "cost": cost_estimate,
                "order_id": result.get('order_id'),
                "success": True
            }
            f.write(json.dumps(log_entry) + '\n')

        print(f"\n📝 Logged to: {log_file}")

    elif 'error' in result:
        print(f"❌ TRADE FAILED: {result['error']}")
    elif result.get('requires_confirmation'):
        print(f"⚠️  REQUIRES CONFIRMATION")
        print(f"   {result.get('message')}")
    else:
        print(f"❓ UNKNOWN RESULT")
        print(json.dumps(result, indent=2))

    print(f"\n{'='*70}\n")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Execute Polymarket trade")
    parser.add_argument("url", help="Market URL")
    parser.add_argument("side", choices=["YES", "NO", "yes", "no"], help="YES or NO")
    parser.add_argument("size", type=float, help="Trade size in USD")
    args = parser.parse_args()

    execute_trade(args.url, args.side, args.size)
