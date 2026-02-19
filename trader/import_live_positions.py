#!/usr/bin/env python3
"""
Import Live Positions — Bootstrap position tracker from live wallet

Fetches filled orders from Polymarket, identifies open positions (bought but
not yet sold), and writes them to positions_state.json so the monitor can
track exit conditions.

Usage:
    python3 import_live_positions.py            # import and write positions
    python3 import_live_positions.py --dry-run  # print only, no writes

Output:
    polymarket-trader/positions_state.json — populated with live positions

Notes:
    - Entry price derived from actual fill price
    - market_date and city must be inferred from the market question (best effort)
    - Threshold temp defaults to 0 if not parseable — review output manually
    - Run once after any manual trades or after a fresh credential rotation
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime, timedelta

TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from polymarket_api import get_client, get_balance, get_wallet_address
from early_exit_manager import PositionTracker, Position

POSITION_STATE_FILE = TRADER_DIR / "polymarket-trader" / "positions_state.json"


def parse_market_question(question: str):
    """
    Best-effort extraction of city, date, threshold, and side from a market question.

    Examples:
      "Will the highest temperature in Chicago be 54°F or higher on February 19?"
      "Will the highest temperature in Buenos Aires be 27°C on February 20?"
      "Will the highest temperature in Dallas be 65°F or below on February 20?"

    Returns dict with: city, market_date_str, threshold_f, is_or_higher
    """
    result = {
        'city': '',
        'market_date_str': '',
        'threshold_f': 0.0,
        'is_or_higher': True,
    }

    # Extract city: "highest temperature in CITY be ..."
    city_match = re.search(r'temperature in (.+?) be', question, re.IGNORECASE)
    if city_match:
        result['city'] = city_match.group(1).strip()

    # Extract date: "on Month Day?" or "on Month Day, Year?"
    date_match = re.search(
        r'on (January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d+)[\?,]?(?:\s+(\d{4}))?',
        question, re.IGNORECASE
    )
    if date_match:
        month = date_match.group(1)
        day = int(date_match.group(2))
        year = int(date_match.group(3)) if date_match.group(3) else datetime.now().year
        try:
            market_date = datetime.strptime(f"{month} {day} {year}", "%B %d %Y")
            result['market_date_str'] = market_date.strftime('%Y-%m-%dT23:59:59')
        except ValueError:
            pass

    # Extract threshold and direction
    # Patterns: "54°F or higher", "65°F or below", "27°C"
    temp_match = re.search(r'(\d+(?:\.\d+)?)[°\u00b0]([FC])\s*(or higher|or below)?', question, re.IGNORECASE)
    if temp_match:
        value = float(temp_match.group(1))
        unit = temp_match.group(2).upper()
        direction = (temp_match.group(3) or 'or higher').lower()

        if unit == 'C':
            value = (value * 9 / 5) + 32  # Convert to F

        result['threshold_f'] = value
        result['is_or_higher'] = 'higher' in direction

    return result


def fetch_filled_positions(client):
    """
    Query recent trades to find tokens currently held.

    Uses get_trades() to find filled BUY orders, then nets against SELL orders
    to find positions still open.

    Returns list of position candidates with token_id, condition_id, etc.
    """
    wallet = get_wallet_address()
    print(f"Fetching trades for wallet {wallet[:6]}...{wallet[-4:]}")

    try:
        trades = client.get_trades() or []
    except Exception as e:
        print(f"❌ Error fetching trades: {e}")
        return []

    print(f"Found {len(trades)} trades")

    # Group by token_id: accumulate shares
    # BUY adds shares, SELL subtracts
    holdings = {}

    for trade in trades:
        token_id = trade.get('asset_id') or trade.get('token_id', '')
        side = trade.get('side', '').upper()
        size = float(trade.get('size', 0))
        price = float(trade.get('price', 0))
        condition_id = trade.get('market_id', '')
        outcome = trade.get('outcome', '')
        matched_time = trade.get('match_time', '') or trade.get('created_at', '')

        if not token_id:
            continue

        if token_id not in holdings:
            holdings[token_id] = {
                'token_id': token_id,
                'condition_id': condition_id,
                'outcome': outcome,
                'shares': 0.0,
                'cost_basis': 0.0,
                'last_buy_price': 0.0,
                'last_buy_time': '',
                'order_id': trade.get('id', ''),
            }

        if side == 'BUY':
            holdings[token_id]['shares'] += size
            holdings[token_id]['cost_basis'] += size * price
            holdings[token_id]['last_buy_price'] = price
            holdings[token_id]['last_buy_time'] = matched_time
        elif side == 'SELL':
            holdings[token_id]['shares'] -= size
            holdings[token_id]['cost_basis'] -= size * price

    # Filter: only positions with positive shares remaining
    open_positions = [
        h for h in holdings.values()
        if h['shares'] > 0.01  # ignore dust
    ]

    print(f"Open positions (positive token balance): {len(open_positions)}")
    return open_positions


def enrich_with_market_data(client, holding):
    """
    Fetch market info to get the question text for a token's condition_id.

    Returns (question, token_outcome) or ('', '')
    """
    cid = holding.get('condition_id', '')
    if not cid:
        return '', ''

    try:
        market = client.get_market(cid)
        question = market.get('question', '')
        tokens = market.get('tokens', [])

        # Find which outcome (YES/NO) matches our token_id
        token_id = holding['token_id']
        for token in tokens:
            if token.get('token_id') == token_id:
                return question, token.get('outcome', '').upper()

        return question, holding.get('outcome', '').upper()

    except Exception as e:
        print(f"    ⚠️  Could not fetch market for {cid[:20]}...: {e}")
        return '', ''


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Import live Polymarket positions into positions_state.json")
    parser.add_argument('--dry-run', action='store_true', help='Print what would be imported without writing')
    args = parser.parse_args()

    print("=" * 70)
    print("IMPORT LIVE POSITIONS")
    if args.dry_run:
        print("DRY RUN — no writes")
    print("=" * 70)
    print()

    client = get_client(signature_type=1)
    bal = get_balance(client)
    print(f"Balance: ${bal['balance_usdc']:.2f}")
    print()

    # Fetch open positions from trade history
    holdings = fetch_filled_positions(client)

    if not holdings:
        print("No open positions found.")
        print()
        print("If you have positions, they may not show in get_trades().")
        print("Fallback: manually add positions to positions_state.json")
        return

    # Build Position objects
    tracker = PositionTracker(POSITION_STATE_FILE)
    added = 0
    skipped = 0

    for h in holdings:
        token_id = h['token_id']
        condition_id = h['condition_id']
        shares = h['shares']
        cost_basis = max(h['cost_basis'], 0.0)

        # Avoid duplicate imports
        if token_id in tracker.positions:
            print(f"  SKIP (already tracked): {token_id[:20]}...")
            skipped += 1
            continue

        # Get market question for metadata
        question, outcome = enrich_with_market_data(client, h)
        if not question:
            question = f"Unknown market ({condition_id[:20]}...)"
        if not outcome:
            outcome = h.get('outcome', 'YES')

        # Parse city, date, threshold from question
        meta = parse_market_question(question)
        city = meta['city']
        market_date_str = meta['market_date_str']
        threshold_f = meta['threshold_f']

        # Compute entry price from cost basis
        entry_price = cost_basis / shares if shares > 0 else h['last_buy_price']

        print(f"\n  Position: {question[:70]}")
        print(f"    Token:   {token_id[:30]}...")
        print(f"    Side:    {outcome}")
        print(f"    Shares:  {shares:.4f}")
        print(f"    Cost:    ${cost_basis:.2f}")
        print(f"    Entry:   {entry_price * 100:.1f}¢")
        print(f"    City:    {city}")
        print(f"    Date:    {market_date_str}")
        print(f"    Threshold: {threshold_f:.0f}°F")

        position = Position(
            market_name=question[:80],
            condition_id=condition_id,
            token_id=token_id,
            side=outcome,
            entry_price=entry_price,
            shares=shares,
            cost_basis=cost_basis,
            entry_date=h.get('last_buy_time', datetime.now().isoformat()),
            order_id=h.get('order_id', ''),
            original_edge=0.0,  # Unknown — was not recorded at entry
            threshold_temp_f=threshold_f,
            city=city,
            market_date=market_date_str,
            is_us_market=(city in {'Chicago', 'Dallas', 'Miami', 'Houston', 'Phoenix',
                                   'Atlanta', 'Los Angeles', 'New York', 'Seattle', 'Denver'}),
            forecast_sources='',
        )

        if not args.dry_run:
            tracker.add_position(position)
        added += 1
        print(f"    ✅ {'Would add' if args.dry_run else 'Added to tracker'}")

    print()
    print("=" * 70)
    print(f"Import {'summary (dry run)' if args.dry_run else 'complete'}: {added} {'found' if args.dry_run else 'added'}, {skipped} already tracked")
    if not args.dry_run:
        print(f"State file: {POSITION_STATE_FILE}")
    print()

    if added > 0:
        print("⚠️  Review positions_state.json and fill in any missing fields:")
        print("   - original_edge (edge at entry, used for edge evaporation check)")
        print("   - forecast_sources (comma-separated: noaa,open-meteo,visual-crossing)")
        print("   - market_date (ISO format YYYY-MM-DDTHH:MM:SS)")
        print()
        print("Then run: python3 position_monitor.py")


if __name__ == "__main__":
    main()
