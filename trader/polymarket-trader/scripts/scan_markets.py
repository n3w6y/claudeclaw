#!/usr/bin/env python3
"""
Scan Polymarket for active markets and analyze odds.
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

def get_active_events(limit=50, tag_id=None):
    """Get active events from Gamma API."""
    url = f"{GAMMA_API}/events?active=true&closed=false&limit={limit}"
    if tag_id:
        url += f"&tag_id={tag_id}"
    return fetch_json(url) or []

def get_market_details(slug):
    """Get market details by slug."""
    url = f"{GAMMA_API}/markets?slug={slug}"
    return fetch_json(url)

def get_price(token_id, side="buy"):
    """Get current price for a token."""
    url = f"{CLOB_API}/price?token_id={token_id}&side={side}"
    return fetch_json(url)

def get_orderbook(token_id):
    """Get orderbook for a token."""
    url = f"{CLOB_API}/book?token_id={token_id}"
    return fetch_json(url)

def get_tags():
    """Get all available tags/categories."""
    url = f"{GAMMA_API}/tags?limit=100"
    return fetch_json(url) or []

def analyze_market(market):
    """Analyze a single market for trading signals."""
    analysis = {
        "question": market.get("question", "Unknown"),
        "slug": market.get("slug", ""),
        "volume": market.get("volume", 0),
        "liquidity": market.get("liquidity", 0),
    }
    
    # Parse outcomes and prices
    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        prices = json.loads(market.get("outcomePrices", "[]"))
        analysis["outcomes"] = list(zip(outcomes, [float(p) for p in prices]))
    except (json.JSONDecodeError, ValueError):
        analysis["outcomes"] = []
    
    # Check for mispricing (prices should sum close to 1.0)
    if analysis["outcomes"]:
        price_sum = sum(p for _, p in analysis["outcomes"])
        analysis["price_sum"] = price_sum
        analysis["spread"] = abs(1.0 - price_sum)
    
    return analysis

def main():
    parser = argparse.ArgumentParser(description="Scan Polymarket markets")
    parser.add_argument("--active", action="store_true", help="Show active markets")
    parser.add_argument("--limit", type=int, default=20, help="Number of markets to fetch")
    parser.add_argument("--tag", type=int, help="Filter by tag ID")
    parser.add_argument("--tags", action="store_true", help="List available tags")
    parser.add_argument("--slug", help="Get details for specific market slug")
    parser.add_argument("--volume-min", type=float, default=0, help="Minimum volume filter")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()
    
    if args.tags:
        tags = get_tags()
        if args.json:
            print(json.dumps(tags, indent=2))
        else:
            print("Available Tags:")
            for tag in tags[:50]:
                print(f"  {tag.get('id', '?'):>6}: {tag.get('label', 'Unknown')}")
        return
    
    if args.slug:
        market = get_market_details(args.slug)
        if market:
            if args.json:
                print(json.dumps(market, indent=2))
            else:
                print(f"Market: {args.slug}")
                print(json.dumps(market, indent=2))
        return
    
    events = get_active_events(limit=args.limit, tag_id=args.tag)
    
    results = []
    for event in events:
        for market in event.get("markets", []):
            volume = float(market.get("volume", 0) or 0)
            if volume >= args.volume_min:
                analysis = analyze_market(market)
                analysis["event_title"] = event.get("title", "")
                analysis["event_slug"] = event.get("slug", "")
                results.append(analysis)
    
    # Sort by volume
    results.sort(key=lambda x: float(x.get("volume", 0) or 0), reverse=True)
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"Found {len(results)} markets:\n")
        for r in results[:args.limit]:
            print(f"📊 {r['question'][:60]}...")
            print(f"   Volume: ${float(r.get('volume', 0) or 0):,.0f} | Liquidity: ${float(r.get('liquidity', 0) or 0):,.0f}")
            if r.get("outcomes"):
                for outcome, price in r["outcomes"]:
                    pct = price * 100
                    print(f"   {outcome}: {pct:.1f}%")
            if r.get("spread", 0) > 0.02:
                print(f"   ⚠️  Spread: {r['spread']*100:.1f}% (potential arb)")
            print()

if __name__ == "__main__":
    main()
