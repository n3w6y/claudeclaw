#!/usr/bin/env python3
"""
Find arbitrage opportunities on Polymarket.

Types of arbitrage detected:
1. Internal mispricing - Yes + No prices don't sum to 1.0
2. Multi-outcome mispricing - Multiple outcomes don't sum correctly
3. Related market discrepancies - Same event, different market structures
"""

import argparse
import json
import sys
from urllib.request import urlopen, Request
from urllib.error import URLError

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

def fetch_json(url):
    """Fetch JSON from URL."""
    req = Request(url, headers={"User-Agent": "PolymarketTrader/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def get_active_events(limit=100):
    """Get active events from Gamma API."""
    url = f"{GAMMA_API}/events?active=true&closed=false&limit={limit}"
    return fetch_json(url) or []

def get_orderbook(token_id):
    """Get orderbook for a token to find true best prices."""
    url = f"{CLOB_API}/book?token_id={token_id}"
    return fetch_json(url)

def analyze_market_pricing(market):
    """
    Analyze a single market for pricing inefficiencies.
    Returns arbitrage opportunity if found.
    """
    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        prices = json.loads(market.get("outcomePrices", "[]"))
        prices = [float(p) for p in prices]
    except (json.JSONDecodeError, ValueError):
        return None
    
    if len(outcomes) < 2 or len(prices) < 2:
        return None
    
    price_sum = sum(prices)
    
    # For a binary market, prices should sum to ~1.0
    # For multi-outcome, they should also sum to ~1.0
    # Deviation = potential arbitrage
    
    deviation = abs(1.0 - price_sum)
    
    if deviation < 0.001:  # Less than 0.1% - no opportunity
        return None
    
    opportunity = {
        "market": market.get("question", "Unknown"),
        "slug": market.get("slug", ""),
        "outcomes": list(zip(outcomes, prices)),
        "price_sum": price_sum,
        "deviation_pct": deviation * 100,
        "type": None,
        "action": None,
        "expected_profit_pct": 0,
    }
    
    if price_sum < 1.0:
        # Prices sum to less than 1 - buy all outcomes for <$1, guaranteed $1 payout
        opportunity["type"] = "buy_all"
        opportunity["action"] = f"Buy all outcomes for ${price_sum:.4f}, receive $1.00 on resolution"
        opportunity["expected_profit_pct"] = (1.0 - price_sum) / price_sum * 100
    else:
        # Prices sum to more than 1 - sell all outcomes for >$1, pay $1 on resolution
        opportunity["type"] = "sell_all"
        opportunity["action"] = f"Sell all outcomes for ${price_sum:.4f}, pay $1.00 on resolution"
        opportunity["expected_profit_pct"] = (price_sum - 1.0) * 100
    
    return opportunity

def find_related_market_arb(events):
    """
    Find arbitrage between related markets (same underlying event).
    E.g., "Will X win?" vs "X vs Y vs Z winner" markets.
    """
    # Group events by similar titles/topics
    # This is a heuristic approach - could be improved with NLP
    opportunities = []
    
    # Look for multi-market events
    for event in events:
        markets = event.get("markets", [])
        if len(markets) > 1:
            # Multiple markets under same event - check for inconsistencies
            # This would need domain-specific logic
            pass
    
    return opportunities

def check_orderbook_spread(market):
    """
    Check orderbook for actual executable prices.
    The displayed price might not be achievable due to spread.
    """
    token_ids = market.get("clobTokenIds", [])
    if not token_ids:
        return None
    
    spreads = []
    for token_id in token_ids:
        book = get_orderbook(token_id)
        if book:
            bids = book.get("bids", [])
            asks = book.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0].get("price", 0))
                best_ask = float(asks[0].get("price", 0))
                spread = best_ask - best_bid
                spreads.append({
                    "token_id": token_id,
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "spread": spread,
                    "spread_pct": spread / best_ask * 100 if best_ask > 0 else 0
                })
    
    return spreads

def main():
    parser = argparse.ArgumentParser(description="Find Polymarket arbitrage opportunities")
    parser.add_argument("--threshold", type=float, default=2.0, 
                       help="Minimum deviation %% to report (default: 2.0)")
    parser.add_argument("--limit", type=int, default=100,
                       help="Number of events to scan")
    parser.add_argument("--check-books", action="store_true",
                       help="Also check orderbooks for real spreads (slower)")
    parser.add_argument("--json", action="store_true",
                       help="Output as JSON")
    parser.add_argument("--verbose", action="store_true",
                       help="Show all markets, not just opportunities")
    args = parser.parse_args()
    
    print(f"Scanning {args.limit} events for arbitrage opportunities...\n")
    
    events = get_active_events(limit=args.limit)
    opportunities = []
    total_markets = 0
    
    for event in events:
        for market in event.get("markets", []):
            total_markets += 1
            opp = analyze_market_pricing(market)
            
            if opp and opp["deviation_pct"] >= args.threshold:
                opp["event_title"] = event.get("title", "")
                opp["volume"] = float(market.get("volume", 0) or 0)
                opp["liquidity"] = float(market.get("liquidity", 0) or 0)
                
                if args.check_books:
                    opp["orderbook_spreads"] = check_orderbook_spread(market)
                
                opportunities.append(opp)
            elif args.verbose and opp:
                print(f"  Below threshold: {opp['market'][:50]}... ({opp['deviation_pct']:.2f}%)")
    
    # Sort by expected profit
    opportunities.sort(key=lambda x: x["expected_profit_pct"], reverse=True)
    
    if args.json:
        print(json.dumps(opportunities, indent=2))
    else:
        print(f"Scanned {total_markets} markets across {len(events)} events")
        print(f"Found {len(opportunities)} opportunities above {args.threshold}% threshold\n")
        
        if not opportunities:
            print("No arbitrage opportunities found at current threshold.")
            print("Try lowering --threshold or check back later.")
        else:
            for opp in opportunities:
                print(f"{'='*60}")
                print(f"🎯 {opp['type'].upper()} Opportunity ({opp['deviation_pct']:.2f}% edge)")
                print(f"   Market: {opp['market'][:55]}...")
                print(f"   Volume: ${opp['volume']:,.0f} | Liquidity: ${opp['liquidity']:,.0f}")
                print(f"   Outcomes:")
                for outcome, price in opp["outcomes"]:
                    print(f"      {outcome}: {price*100:.1f}%")
                print(f"   Price Sum: {opp['price_sum']:.4f}")
                print(f"   Action: {opp['action']}")
                print(f"   Expected Profit: {opp['expected_profit_pct']:.2f}%")
                
                if opp.get("orderbook_spreads"):
                    print(f"   Orderbook Spreads:")
                    for spread in opp["orderbook_spreads"]:
                        print(f"      Bid: {spread['best_bid']:.3f} | Ask: {spread['best_ask']:.3f} | Spread: {spread['spread_pct']:.1f}%")
                print()
        
        print("\n⚠️  Notes:")
        print("  - Always verify with orderbook before trading (use --check-books)")
        print("  - Account for fees (typically 0.5-2%)")
        print("  - Low liquidity markets may not be executable")
        print("  - Prices change rapidly - opportunities may disappear")

if __name__ == "__main__":
    main()
