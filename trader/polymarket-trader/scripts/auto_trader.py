#!/usr/bin/env python3
"""
Automated paper trading scanner for Polymarket.

Runs on schedule to:
1. Scan cross-market arbitrage opportunities
2. Execute paper trades on Simmer (if enabled)
3. Log weather opportunities as hypothetical trades
4. Track everything for review

Usage:
  python3 auto_trader.py                    # Single scan + trade
  python3 auto_trader.py --dry-run          # Scan only, no trades
  python3 auto_trader.py --status           # Show current state
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
JOURNAL_DIR = SCRIPT_DIR.parent / "journal"

# Ensure journal directory exists
JOURNAL_DIR.mkdir(exist_ok=True)

# Files
STATE_FILE = CONFIG_DIR / "trading_state.json"
SIMMER_CONFIG = CONFIG_DIR / "simmer_config.json"
HYPOTHETICAL_LOG = JOURNAL_DIR / "hypothetical_trades.jsonl"
PAPER_TRADE_LOG = JOURNAL_DIR / "paper_trades.jsonl"
SCAN_LOG = JOURNAL_DIR / "scan_log.jsonl"

# Trading parameters
MIN_EDGE_PCT = 3.0  # Minimum edge to consider
MAX_TRADES_PER_SCAN = 2
POSITION_SIZE_PCT = 5.0  # 5% of simulated balance

def load_state():
    """Load trading state."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "simulated_balance": 100.0,
        "total_trades": 0,
        "total_pnl": 0.0,
        "open_positions": [],
        "last_scan": None,
        "trades_today": 0,
        "daily_pnl": 0.0,
        "trial_start": datetime.now().isoformat(),
        "trial_end": (datetime.now() + timedelta(hours=48)).isoformat()
    }

def save_state(state):
    """Save trading state."""
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

def load_simmer_config():
    """Load Simmer configuration."""
    if SIMMER_CONFIG.exists():
        with open(SIMMER_CONFIG) as f:
            return json.load(f)
    return None

def log_entry(filepath, entry):
    """Append JSON entry to log file."""
    with open(filepath, 'a') as f:
        f.write(json.dumps(entry, default=str) + '\n')

def fetch_json(url, timeout=15):
    """Fetch JSON from URL."""
    req = Request(url, headers={"User-Agent": "PolyTrader/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

# ============================================================================
# Market Scanners
# ============================================================================

def scan_cross_market_arb(min_edge=3.0):
    """Scan for cross-market arbitrage opportunities."""
    # Import the scanner - ensure we're importing from the right place
    script_path = str(SCRIPT_DIR.resolve())
    if script_path not in sys.path:
        sys.path.insert(0, script_path)
    try:
        from cross_market_arb import scan_for_arbitrage
        opportunities = scan_for_arbitrage(min_edge=min_edge)
        # Filter to safer opportunities (date mispricing, not all-NO bets)
        # Note: type is lowercase in the actual output
        safe_opps = [o for o in opportunities if o.get('type') == 'date_mispricing']
        return safe_opps
    except Exception as e:
        print(f"Cross-market scan error: {e}")
        import traceback
        traceback.print_exc()
        return []

def scan_weather_markets():
    """Scan for weather arbitrage opportunities."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event
        
        events = get_weather_events()
        opportunities = []
        
        for event in events:
            parsed = parse_weather_event(event)
            if not parsed:
                continue
            opps = analyze_weather_event(parsed)
            opportunities.extend(opps)
        
        return opportunities
    except Exception as e:
        print(f"Weather scan error: {e}")
        return []

def scan_internal_arb():
    """Scan for YES+NO < $1 arbitrage."""
    GAMMA_API = "https://gamma-api.polymarket.com"
    url = f"{GAMMA_API}/markets?closed=false&limit=500"
    
    markets = fetch_json(url) or []
    opportunities = []
    
    for market in markets:
        try:
            prices = json.loads(market.get("outcomePrices", "[]"))
            if len(prices) >= 2:
                yes_price = float(prices[0])
                no_price = float(prices[1])
                total = yes_price + no_price
                
                if total < 0.98:  # >2% edge
                    edge = (1.0 - total) * 100
                    opportunities.append({
                        "type": "INTERNAL_ARB",
                        "market": market.get("question", "")[:60],
                        "slug": market.get("slug"),
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "total": total,
                        "edge_pct": edge,
                        "liquidity": float(market.get("liquidity", 0) or 0)
                    })
        except:
            continue
    
    return sorted(opportunities, key=lambda x: x["edge_pct"], reverse=True)

# ============================================================================
# Paper Trading (Simmer)
# ============================================================================

def execute_simmer_trade(opportunity, state, config):
    """Execute a paper trade on Simmer."""
    # Calculate position size
    balance = state["simulated_balance"]
    position_size = balance * (POSITION_SIZE_PCT / 100)
    
    # Check daily limits
    settings = config.get("settings", {})
    max_daily_loss = settings.get("max_daily_loss", 100)
    
    if state["daily_pnl"] <= -max_daily_loss:
        return {"error": "Daily loss limit reached"}
    
    # For now, simulate the trade locally (Simmer API integration can be added)
    trade = {
        "timestamp": datetime.now().isoformat(),
        "type": opportunity.get("type"),
        "market": opportunity.get("market") or opportunity.get("event_title", "")[:60],
        "action": opportunity.get("action", "BUY"),
        "edge_pct": opportunity.get("edge_pct"),
        "position_size": position_size,
        "entry_price": opportunity.get("yes_price") or opportunity.get("market_yes_price"),
        "status": "OPEN",
        "venue": "simmer_simulated"
    }
    
    # Log the trade
    log_entry(PAPER_TRADE_LOG, trade)
    
    # Update state
    state["total_trades"] += 1
    state["trades_today"] += 1
    state["open_positions"].append(trade)
    
    return {"success": True, "trade": trade}

# ============================================================================
# Main Scanner
# ============================================================================

def run_scan(dry_run=False):
    """Run full market scan and execute trades."""
    state = load_state()
    config = load_simmer_config()
    
    scan_time = datetime.now()
    print(f"\n{'='*60}")
    print(f"🔍 Auto-Trader Scan — {scan_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}")
    
    # Reset daily counters if new day
    if state.get("last_scan"):
        last_scan = datetime.fromisoformat(state["last_scan"])
        if last_scan.date() < scan_time.date():
            state["trades_today"] = 0
            state["daily_pnl"] = 0.0
    
    state["last_scan"] = scan_time.isoformat()
    
    results = {
        "timestamp": scan_time.isoformat(),
        "cross_market": [],
        "weather": [],
        "internal_arb": [],
        "trades_executed": [],
        "hypothetical_logged": []
    }
    
    # 1. Scan cross-market arbitrage
    print("\n📊 Scanning cross-market arbitrage...")
    cross_opps = scan_cross_market_arb(min_edge=MIN_EDGE_PCT)
    results["cross_market"] = cross_opps[:10]
    print(f"   Found {len(cross_opps)} opportunities above {MIN_EDGE_PCT}% edge")
    
    # 2. Scan internal arbitrage (YES+NO < $1)
    print("\n💰 Scanning internal arbitrage...")
    internal_opps = scan_internal_arb()
    internal_opps = [o for o in internal_opps if o["edge_pct"] >= MIN_EDGE_PCT]
    results["internal_arb"] = internal_opps[:10]
    print(f"   Found {len(internal_opps)} opportunities above {MIN_EDGE_PCT}% edge")
    
    # 3. Scan weather markets (log as hypothetical)
    print("\n🌡️  Scanning weather markets...")
    weather_opps = scan_weather_markets()
    weather_opps = [o for o in weather_opps if o.get("confidence_adjusted_edge", 0) >= MIN_EDGE_PCT]
    results["weather"] = weather_opps[:10]
    print(f"   Found {len(weather_opps)} opportunities above {MIN_EDGE_PCT}% adjusted edge")
    
    # Log weather opportunities as hypothetical trades
    for opp in weather_opps[:3]:
        hypothetical = {
            "timestamp": scan_time.isoformat(),
            "type": "WEATHER_ARB",
            "market": opp.get("market_question", "")[:60],
            "city": opp.get("city"),
            "date": opp.get("date"),
            "action": opp.get("action"),
            "forecast_temp": opp.get("forecast_temp"),
            "forecast_confidence": opp.get("forecast_confidence"),
            "market_yes_price": opp.get("market_yes_price"),
            "market_no_price": opp.get("market_no_price"),
            "our_probability": opp.get("forecast_prob"),
            "edge_pct": opp.get("edge_pct"),
            "adjusted_edge_pct": opp.get("confidence_adjusted_edge"),
            "would_trade": True,
            "hypothetical_size": state["simulated_balance"] * (POSITION_SIZE_PCT / 100),
            "url": opp.get("url"),
            "sources": opp.get("forecast_sources", [])
        }
        log_entry(HYPOTHETICAL_LOG, hypothetical)
        results["hypothetical_logged"].append(hypothetical)
        print(f"   📝 Logged hypothetical: {opp.get('city')} weather @ {opp.get('edge_pct', 0):.1f}% edge")
    
    # Execute paper trades on best opportunities (cross-market + internal)
    if not dry_run and config:
        all_tradeable = cross_opps + internal_opps
        all_tradeable.sort(key=lambda x: x.get("edge_pct", 0), reverse=True)
        
        trades_this_scan = 0
        for opp in all_tradeable[:MAX_TRADES_PER_SCAN]:
            if trades_this_scan >= MAX_TRADES_PER_SCAN:
                break
            
            result = execute_simmer_trade(opp, state, config)
            if result.get("success"):
                results["trades_executed"].append(result["trade"])
                trades_this_scan += 1
                print(f"\n   ✅ Paper trade: {opp.get('type')} @ {opp.get('edge_pct', 0):.1f}% edge")
                print(f"      Market: {opp.get('market', '')[:50]}...")
    
    # Log scan results
    log_entry(SCAN_LOG, results)
    
    # Save state
    save_state(state)
    
    # Summary
    print(f"\n{'='*60}")
    print(f"📈 Scan Summary")
    print(f"{'='*60}")
    print(f"   Simulated balance: ${state['simulated_balance']:.2f}")
    print(f"   Total trades: {state['total_trades']}")
    print(f"   Trades today: {state['trades_today']}")
    print(f"   Open positions: {len(state['open_positions'])}")
    print(f"   Paper trades this scan: {len(results['trades_executed'])}")
    print(f"   Hypotheticals logged: {len(results['hypothetical_logged'])}")
    
    trial_end = datetime.fromisoformat(state["trial_end"])
    remaining = trial_end - scan_time
    if remaining.total_seconds() > 0:
        hours = remaining.total_seconds() / 3600
        print(f"   Trial time remaining: {hours:.1f} hours")
    else:
        print(f"   ⏰ Trial period complete!")
    
    return results

def show_status():
    """Show current trading status."""
    state = load_state()
    
    print(f"\n{'='*60}")
    print(f"📊 Auto-Trader Status")
    print(f"{'='*60}")
    print(f"   Simulated balance: ${state['simulated_balance']:.2f}")
    print(f"   Total trades: {state['total_trades']}")
    print(f"   Total P&L: ${state['total_pnl']:.2f}")
    print(f"   Trades today: {state['trades_today']}")
    print(f"   Daily P&L: ${state['daily_pnl']:.2f}")
    print(f"   Open positions: {len(state['open_positions'])}")
    
    if state.get("trial_start"):
        start = datetime.fromisoformat(state["trial_start"])
        end = datetime.fromisoformat(state["trial_end"])
        now = datetime.now()
        
        print(f"\n   Trial started: {start.strftime('%Y-%m-%d %H:%M')}")
        print(f"   Trial ends: {end.strftime('%Y-%m-%d %H:%M')}")
        
        if now < end:
            remaining = (end - now).total_seconds() / 3600
            print(f"   Time remaining: {remaining:.1f} hours")
        else:
            print(f"   ✅ Trial complete!")
    
    # Show recent logs
    if PAPER_TRADE_LOG.exists():
        with open(PAPER_TRADE_LOG) as f:
            trades = [json.loads(line) for line in f.readlines()[-5:]]
        if trades:
            print(f"\n   Recent paper trades:")
            for t in trades:
                print(f"      - {t.get('type')}: {t.get('market', '')[:40]}... @ {t.get('edge_pct', 0):.1f}%")
    
    if HYPOTHETICAL_LOG.exists():
        with open(HYPOTHETICAL_LOG) as f:
            hypos = [json.loads(line) for line in f.readlines()[-5:]]
        if hypos:
            print(f"\n   Recent hypothetical (weather):")
            for h in hypos:
                print(f"      - {h.get('city')}: {h.get('action')} @ {h.get('edge_pct', 0):.1f}%")

def main():
    parser = argparse.ArgumentParser(description="Automated paper trading scanner")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no trades")
    parser.add_argument("--status", action="store_true", help="Show current status")
    args = parser.parse_args()
    
    if args.status:
        show_status()
    else:
        run_scan(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
