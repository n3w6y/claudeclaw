#!/usr/bin/env python3
"""
Micro-arbitrage scanner for short-duration Polymarket markets.

Focuses on:
- Crypto markets (BTC, ETH, SOL, etc.)
- Short resolution times (hourly, 15-min, daily)
- Brief pricing inefficiencies where YES + NO < 1.0

Usage:
  python3 micro_arb_scanner.py                    # One-shot scan
  python3 micro_arb_scanner.py --watch            # Continuous monitoring
  python3 micro_arb_scanner.py --crypto-only      # Only crypto markets
  python3 micro_arb_scanner.py --min-edge 0.5     # Lower threshold (0.5%)
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from urllib.request import urlopen, Request
from urllib.error import URLError

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"

# Keywords indicating short-duration crypto markets
CRYPTO_KEYWORDS = ["btc", "bitcoin", "eth", "ethereum", "sol", "solana", "crypto", "doge", "xrp"]
SHORT_DURATION_KEYWORDS = ["hour", "15 min", "minute", "daily", "today", "tonight", "midnight"]

def fetch_json(url, timeout=15):
    """Fetch JSON from URL."""
    req = Request(url, headers={"User-Agent": "MicroArbScanner/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except URLError as e:
        return None
    except Exception:
        return None

def get_active_events(limit=200):
    """Get active events from Gamma API."""
    url = f"{GAMMA_API}/events?active=true&closed=false&limit={limit}"
    return fetch_json(url) or []

def get_live_prices(token_id):
    """Get live bid/ask from CLOB."""
    url = f"{CLOB_API}/book?token_id={token_id}"
    book = fetch_json(url, timeout=5)
    if not book:
        return None, None
    
    bids = book.get("bids", [])
    asks = book.get("asks", [])
    
    best_bid = float(bids[0]["price"]) if bids else None
    best_ask = float(asks[0]["price"]) if asks else None
    
    return best_bid, best_ask

def is_crypto_market(market, event):
    """Check if market is crypto-related."""
    text = (
        market.get("question", "").lower() + " " +
        event.get("title", "").lower() + " " +
        market.get("description", "").lower()
    )
    return any(kw in text for kw in CRYPTO_KEYWORDS)

def is_short_duration(market, event):
    """Check if market has short resolution time."""
    text = (
        market.get("question", "").lower() + " " +
        event.get("title", "").lower()
    )
    
    # Check keywords
    if any(kw in text for kw in SHORT_DURATION_KEYWORDS):
        return True
    
    # Check if end date is within 24 hours
    end_date = market.get("endDate") or event.get("endDate")
    if end_date:
        try:
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            hours_until_end = (end_dt - now).total_seconds() / 3600
            if 0 < hours_until_end < 24:
                return True
        except:
            pass
    
    return False

def analyze_binary_market(market, check_orderbook=False):
    """
    Analyze binary market for YES + NO < 1.0 opportunities.
    
    Returns opportunity dict if edge found, None otherwise.
    """
    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        prices = json.loads(market.get("outcomePrices", "[]"))
        token_ids = market.get("clobTokenIds", "[]")
        if isinstance(token_ids, str):
            token_ids = json.loads(token_ids)
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    
    if len(outcomes) != 2 or len(prices) != 2:
        return None  # Only binary markets for this scanner
    
    try:
        yes_price = float(prices[0])
        no_price = float(prices[1])
    except (ValueError, TypeError):
        return None
    
    # Calculate raw edge from displayed prices
    price_sum = yes_price + no_price
    
    # If we want to check real orderbook prices
    actual_yes_ask = yes_price
    actual_no_ask = no_price
    actual_sum = price_sum
    
    if check_orderbook and len(token_ids) >= 2:
        yes_bid, yes_ask = get_live_prices(token_ids[0])
        no_bid, no_ask = get_live_prices(token_ids[1])
        
        if yes_ask and no_ask:
            actual_yes_ask = yes_ask
            actual_no_ask = no_ask
            actual_sum = yes_ask + no_ask
    
    if actual_sum >= 1.0:
        return None  # No opportunity
    
    edge_pct = (1.0 - actual_sum) * 100
    
    # Calculate profit if you buy $100 of each side
    # Cost: actual_sum * 100
    # Guaranteed return: $100 (one side wins)
    cost_per_unit = actual_sum
    profit_per_unit = 1.0 - actual_sum
    roi_pct = (profit_per_unit / cost_per_unit) * 100
    
    return {
        "question": market.get("question", "Unknown"),
        "slug": market.get("slug", ""),
        "market_id": market.get("id", ""),
        "yes_price": actual_yes_ask,
        "no_price": actual_no_ask,
        "price_sum": actual_sum,
        "edge_pct": edge_pct,
        "roi_pct": roi_pct,
        "volume": float(market.get("volume", 0) or 0),
        "liquidity": float(market.get("liquidity", 0) or 0),
        "token_ids": token_ids,
        "url": f"https://polymarket.com/event/{market.get('slug', '')}",
    }

def scan_once(args):
    """Run a single scan."""
    events = get_active_events(limit=args.limit)
    if not events:
        print("Failed to fetch events", file=sys.stderr)
        return []
    
    opportunities = []
    scanned = 0
    
    for event in events:
        for market in event.get("markets", []):
            # Apply filters
            if args.crypto_only and not is_crypto_market(market, event):
                continue
            if args.short_only and not is_short_duration(market, event):
                continue
            
            scanned += 1
            opp = analyze_binary_market(market, check_orderbook=args.check_orderbook)
            
            if opp and opp["edge_pct"] >= args.min_edge:
                opp["event_title"] = event.get("title", "")
                opp["is_crypto"] = is_crypto_market(market, event)
                opp["is_short"] = is_short_duration(market, event)
                opportunities.append(opp)
    
    # Sort by edge
    opportunities.sort(key=lambda x: x["edge_pct"], reverse=True)
    
    return opportunities, scanned

def print_opportunities(opportunities, scanned, timestamp=None):
    """Pretty print opportunities."""
    ts = timestamp or datetime.now().strftime("%H:%M:%S")
    
    print(f"\n[{ts}] Scanned {scanned} markets")
    
    if not opportunities:
        print("  No opportunities above threshold")
        return
    
    print(f"  Found {len(opportunities)} potential arbitrage opportunities:\n")
    
    for opp in opportunities[:10]:  # Top 10
        flags = []
        if opp.get("is_crypto"):
            flags.append("🪙")
        if opp.get("is_short"):
            flags.append("⏱️")
        flag_str = " ".join(flags)
        
        print(f"  {'='*55}")
        print(f"  {flag_str} {opp['edge_pct']:.2f}% EDGE | ROI: {opp['roi_pct']:.2f}%")
        print(f"  {opp['question'][:52]}...")
        print(f"  YES: {opp['yes_price']*100:.1f}¢ | NO: {opp['no_price']*100:.1f}¢ | Sum: {opp['price_sum']:.4f}")
        print(f"  Vol: ${opp['volume']:,.0f} | Liq: ${opp['liquidity']:,.0f}")
        print(f"  {opp['url']}")
        print()

def main():
    parser = argparse.ArgumentParser(description="Micro-arbitrage scanner for Polymarket")
    parser.add_argument("--min-edge", type=float, default=1.0,
                       help="Minimum edge %% to report (default: 1.0)")
    parser.add_argument("--limit", type=int, default=200,
                       help="Number of events to scan")
    parser.add_argument("--crypto-only", action="store_true",
                       help="Only scan crypto-related markets")
    parser.add_argument("--short-only", action="store_true",
                       help="Only scan short-duration markets")
    parser.add_argument("--check-orderbook", action="store_true",
                       help="Check live orderbook prices (slower but accurate)")
    parser.add_argument("--watch", action="store_true",
                       help="Continuous monitoring mode")
    parser.add_argument("--interval", type=int, default=30,
                       help="Seconds between scans in watch mode (default: 30)")
    parser.add_argument("--json", action="store_true",
                       help="Output as JSON")
    parser.add_argument("--alert-only", action="store_true",
                       help="In watch mode, only print when opportunities found")
    args = parser.parse_args()
    
    print("🔍 Polymarket Micro-Arbitrage Scanner")
    print(f"   Min edge: {args.min_edge}% | Crypto only: {args.crypto_only} | Short only: {args.short_only}")
    print(f"   Check orderbook: {args.check_orderbook}")
    
    if args.watch:
        print(f"   Mode: Continuous (every {args.interval}s)")
        print("   Press Ctrl+C to stop\n")
        
        try:
            while True:
                opportunities, scanned = scan_once(args)
                
                if args.json:
                    if opportunities or not args.alert_only:
                        print(json.dumps({"timestamp": datetime.now().isoformat(), 
                                         "scanned": scanned,
                                         "opportunities": opportunities}))
                else:
                    if opportunities or not args.alert_only:
                        print_opportunities(opportunities, scanned)
                
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n\nScan stopped.")
    else:
        opportunities, scanned = scan_once(args)
        
        if args.json:
            print(json.dumps(opportunities, indent=2))
        else:
            print_opportunities(opportunities, scanned)
    
    # Return count for scripting
    return len(opportunities) if 'opportunities' in dir() else 0

if __name__ == "__main__":
    sys.exit(0 if main() else 0)
