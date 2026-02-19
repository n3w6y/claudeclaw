#!/usr/bin/env python3
"""
Cross-market arbitrage finder for Polymarket.

Finds pricing inefficiencies across RELATED markets:
1. Same event, different dates (cumulative date markets)
2. Mutually exclusive outcomes across markets
3. Must-happen scenarios (all outcomes of a category)

The key insight: When Polymarket has multiple markets about the same 
underlying event, the prices don't always reflect proper probability math.

Usage:
  python3 cross_market_arb.py                    # Scan for opportunities
  python3 cross_market_arb.py --event "iran"     # Filter by keyword
  python3 cross_market_arb.py --min-edge 3       # Minimum edge %
  python3 cross_market_arb.py --json             # JSON output
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from urllib.request import urlopen, Request
from urllib.error import URLError
from datetime import datetime

GAMMA_API = "https://gamma-api.polymarket.com"

def fetch_json(url, timeout=30):
    """Fetch JSON from URL."""
    req = Request(url, headers={"User-Agent": "CrossMarketArb/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def get_all_events(limit=500):
    """Get all active events."""
    url = f"{GAMMA_API}/events?active=true&closed=false&limit={limit}"
    return fetch_json(url) or []

def extract_date_from_title(title):
    """Try to extract a date reference from market title."""
    title_lower = title.lower()
    
    # Patterns like "by March 31", "by April", "before May 2026"
    patterns = [
        r'by\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{1,2})?,?\s*(\d{4})?',
        r'before\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{1,2})?,?\s*(\d{4})?',
        r'in\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{4})?',
        r'(q[1-4])\s*(\d{4})?',
        r'(january|february|march|april|may|june|july|august|september|october|november|december)\s*(\d{4})',
    ]
    
    months = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    
    for pattern in patterns:
        match = re.search(pattern, title_lower)
        if match:
            groups = match.groups()
            if groups[0] in months:
                month = months[groups[0]]
                year = 2026  # default
                day = 15  # middle of month default
                if len(groups) > 1 and groups[1] and groups[1].isdigit():
                    if int(groups[1]) > 12:
                        day = int(groups[1])
                    else:
                        day = int(groups[1])
                if len(groups) > 2 and groups[2] and groups[2].isdigit():
                    year = int(groups[2])
                return (year, month, day)
            elif groups[0].startswith('q'):
                q = int(groups[0][1])
                month = q * 3
                year = int(groups[1]) if len(groups) > 1 and groups[1] else 2026
                return (year, month, 15)
    
    return None

def normalize_event_title(title):
    """
    Normalize title to find related markets.
    Remove date-specific parts to group related events.
    """
    title_lower = title.lower()
    
    # Remove common date patterns
    patterns_to_remove = [
        r'\bby\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*\d*,?\s*\d*',
        r'\bbefore\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*\d*,?\s*\d*',
        r'\bin\s+(january|february|march|april|may|june|july|august|september|october|november|december)\s*\d*',
        r'\b(q[1-4])\s*\d{4}',
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}',
        r'\b\d{4}\b',
        r'\?$',
    ]
    
    normalized = title_lower
    for pattern in patterns_to_remove:
        normalized = re.sub(pattern, '', normalized)
    
    # Clean up whitespace
    normalized = ' '.join(normalized.split())
    
    return normalized

def get_market_prices(market):
    """Extract YES and NO prices from market."""
    try:
        prices = json.loads(market.get("outcomePrices", "[]"))
        if len(prices) >= 2:
            return float(prices[0]), float(prices[1])  # YES, NO
    except:
        pass
    return None, None

def find_date_based_groups(events, keyword_filter=None):
    """
    Group markets by their normalized title (same event, different dates).
    """
    groups = defaultdict(list)
    
    for event in events:
        event_title = event.get("title", "")
        
        # Apply keyword filter
        if keyword_filter:
            if keyword_filter.lower() not in event_title.lower():
                continue
        
        for market in event.get("markets", []):
            question = market.get("question", "")
            normalized = normalize_event_title(question)
            date_info = extract_date_from_title(question)
            
            yes_price, no_price = get_market_prices(market)
            if yes_price is None:
                continue
            
            groups[normalized].append({
                "question": question,
                "event_title": event_title,
                "slug": market.get("slug", ""),
                "yes_price": yes_price,
                "no_price": no_price,
                "date_info": date_info,
                "volume": float(market.get("volume", 0) or 0),
                "liquidity": float(market.get("liquidity", 0) or 0),
            })
    
    # Filter to groups with multiple markets
    return {k: v for k, v in groups.items() if len(v) > 1}

def analyze_cumulative_date_arb(markets):
    """
    Analyze cumulative date markets for arbitrage.
    
    For "by date" markets:
    - If event happens, all markets up to and including that date resolve YES
    - Strategy: Compare cost of YES on early date vs NO on late date
    """
    # Sort by date
    dated_markets = [m for m in markets if m["date_info"]]
    if len(dated_markets) < 2:
        return None
    
    dated_markets.sort(key=lambda x: x["date_info"])
    
    opportunities = []
    
    # Check: Sum of all NO prices
    # If you buy NO on ALL dates, you lose everything if event happens
    # But if event NEVER happens, you win all NOs
    total_no_cost = sum(m["no_price"] for m in dated_markets)
    no_payout_if_never = len(dated_markets)  # Each NO pays $1
    
    if total_no_cost < no_payout_if_never * 0.98:  # Account for some risk
        # This is risky - you lose everything if event happens
        edge = (no_payout_if_never - total_no_cost) / total_no_cost * 100
        opportunities.append({
            "type": "all_no_bet",
            "description": f"Buy NO on all {len(dated_markets)} date variants",
            "cost": total_no_cost,
            "payout_if_never": no_payout_if_never,
            "risk": "Lose all if event happens at any point",
            "edge_if_never_pct": edge,
            "markets": dated_markets,
        })
    
    # Check: Earliest YES vs Latest NO spread
    earliest = dated_markets[0]
    latest = dated_markets[-1]
    
    # Buy YES on earliest (cheapest YES)
    # Buy NO on latest (most likely to be NO)
    combo_cost = earliest["yes_price"] + latest["no_price"]
    
    # If event happens before earliest: both lose? No...
    # If event happens before earliest deadline:
    #   - earliest YES wins ($1)
    #   - latest NO loses ($0) 
    # If event happens between earliest and latest:
    #   - earliest YES loses ($0)
    #   - latest NO loses ($0) -- because event happened
    # If event never happens:
    #   - earliest YES loses ($0)
    #   - latest NO wins ($1)
    
    # So this strategy has a hole - if event happens AFTER earliest but BEFORE latest, you lose both
    # Not a true arbitrage
    
    # Better check: Look for logical inconsistencies
    # If YES(early) > YES(late), that's wrong (later date should be >= earlier)
    for i in range(len(dated_markets) - 1):
        early = dated_markets[i]
        late = dated_markets[i + 1]
        
        if early["yes_price"] > late["yes_price"] + 0.02:  # Early YES more expensive than late YES
            opportunities.append({
                "type": "date_mispricing",
                "description": f"Earlier date YES ({early['yes_price']:.2f}) > Later date YES ({late['yes_price']:.2f})",
                "action": f"Sell YES on early ({early['question'][:40]}), Buy YES on late ({late['question'][:40]})",
                "edge_pct": (early["yes_price"] - late["yes_price"]) * 100,
                "early_market": early,
                "late_market": late,
            })
        
        if early["no_price"] < late["no_price"] - 0.02:  # Early NO cheaper than late NO
            opportunities.append({
                "type": "date_mispricing", 
                "description": f"Earlier date NO ({early['no_price']:.2f}) < Later date NO ({late['no_price']:.2f})",
                "action": f"Buy NO on early, Sell NO on late",
                "edge_pct": (late["no_price"] - early["no_price"]) * 100,
                "early_market": early,
                "late_market": late,
            })
    
    return opportunities if opportunities else None

def analyze_mutually_exclusive(markets):
    """
    Check if markets that should be mutually exclusive are mispriced.
    If only one can be true, sum of YES prices should be <= 1.
    """
    # This requires domain knowledge about which markets are mutually exclusive
    # For now, we look for markets with similar structure that might be exclusive
    
    # Check if total YES across group > 1 (impossible if mutually exclusive)
    total_yes = sum(m["yes_price"] for m in markets)
    
    if total_yes > 1.0:
        # Potential mutual exclusivity arbitrage
        # But we need to verify they're actually mutually exclusive
        return {
            "type": "possible_mutual_exclusive",
            "description": f"Total YES ({total_yes:.2f}) > 1.0 across {len(markets)} related markets",
            "note": "Verify these are mutually exclusive before trading",
            "total_yes": total_yes,
            "markets": markets,
        }
    
    return None

def scan_for_arbitrage(min_edge=2.0, limit=500, keyword_filter=None):
    """
    Scan for cross-market arbitrage opportunities.
    Returns list of opportunities above min_edge threshold.
    
    For use by auto_trader.py and other scripts.
    """
    events = get_all_events(limit)
    if not events:
        return []
    
    groups = find_date_based_groups(events, keyword_filter)
    all_opportunities = []
    
    for normalized_title, markets in groups.items():
        # Analyze for cumulative date arbitrage
        date_opps = analyze_cumulative_date_arb(markets)
        if date_opps:
            for opp in date_opps:
                opp["group"] = normalized_title
                opp["market"] = normalized_title[:60]
                all_opportunities.append(opp)
        
        # Analyze for mutual exclusivity
        mutex_opp = analyze_mutually_exclusive(markets)
        if mutex_opp:
            mutex_opp["group"] = normalized_title
            mutex_opp["market"] = normalized_title[:60]
            all_opportunities.append(mutex_opp)
    
    # Filter by edge
    filtered = [o for o in all_opportunities if o.get("edge_pct", o.get("edge_if_never_pct", 0)) >= min_edge]
    
    return filtered

def main():
    parser = argparse.ArgumentParser(description="Find cross-market arbitrage on Polymarket")
    parser.add_argument("--event", "-e", type=str, help="Filter by event keyword")
    parser.add_argument("--min-edge", type=float, default=2.0, help="Minimum edge %% (default: 2.0)")
    parser.add_argument("--limit", type=int, default=500, help="Events to fetch")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show more details")
    args = parser.parse_args()
    
    print("🔗 Cross-Market Arbitrage Scanner")
    print(f"   Looking for related markets with pricing inefficiencies...\n")
    
    events = get_all_events(args.limit)
    if not events:
        print("Failed to fetch events")
        return 1
    
    print(f"   Fetched {len(events)} events")
    
    # Find groups of related markets
    groups = find_date_based_groups(events, args.event)
    print(f"   Found {len(groups)} groups of related markets\n")
    
    all_opportunities = []
    
    for normalized_title, markets in groups.items():
        if args.verbose:
            print(f"\n--- Group: {normalized_title[:60]}... ({len(markets)} markets)")
        
        # Analyze for cumulative date arbitrage
        date_opps = analyze_cumulative_date_arb(markets)
        if date_opps:
            for opp in date_opps:
                opp["group"] = normalized_title
                all_opportunities.append(opp)
        
        # Analyze for mutual exclusivity
        mutex_opp = analyze_mutually_exclusive(markets)
        if mutex_opp:
            mutex_opp["group"] = normalized_title
            all_opportunities.append(mutex_opp)
    
    # Filter by edge
    filtered = [o for o in all_opportunities if o.get("edge_pct", o.get("edge_if_never_pct", 0)) >= args.min_edge]
    
    if args.json:
        print(json.dumps(filtered, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"Found {len(filtered)} opportunities above {args.min_edge}% edge")
        print(f"{'='*60}\n")
        
        if not filtered:
            print("No cross-market arbitrage opportunities found at current threshold.")
            print("Try --min-edge 1 or filter with --event 'keyword'")
        else:
            for opp in filtered:
                print(f"📊 {opp['type'].upper()}")
                print(f"   Group: {opp['group'][:55]}...")
                print(f"   {opp['description']}")
                if opp.get("action"):
                    print(f"   Action: {opp['action']}")
                if opp.get("edge_pct"):
                    print(f"   Edge: {opp['edge_pct']:.1f}%")
                if opp.get("edge_if_never_pct"):
                    print(f"   Edge (if event never happens): {opp['edge_if_never_pct']:.1f}%")
                    print(f"   ⚠️  Risk: {opp.get('risk', 'Unknown')}")
                if opp.get("note"):
                    print(f"   ⚠️  {opp['note']}")
                print()
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
