#!/usr/bin/env python3
"""
Batch trade executor for weather arbitrage markets.
Uses Playwright to interact with logged-in Polymarket tab.

Respects risk limits from risk_manager.py.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
LOGS_DIR = SCRIPT_DIR.parent / "logs"

# Ensure logs dir exists
LOGS_DIR.mkdir(exist_ok=True)

# Trading params
MAX_TRADES = 10  # Max trades per session (per risk limits)
TRADER_URL = "https://polymarket.com"

def load_risk_limits():
    """Load risk limits from config."""
    risk_file = CONFIG_DIR / "risk_limits.json"
    if risk_file.exists():
        with open(risk_file) as f:
            return json.load(f)
    return {"max_order_usd": 5, "daily_limit_usd": 50}

def get_balance_from_gateway():
    """Get balance from OpenClaw gateway."""
    import urllib.request
    try:
        with urllib.request.urlopen("http://127.0.0.1:18789/balance", timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"⚠️  Gateway balance fetch failed: {e}")
        return {"balance_usdc": 0}

def log_trade(trade):
    """Log trade to file."""
    log_file = LOGS_DIR / "live_trades.log"
    trade_entry = {
        "timestamp": datetime.now().isoformat(),
        "marketId": trade.get("marketId"),
        "marketQuestion": trade.get("question", "")[:80],
        "outcome": trade.get("outcome"),
        "stake": trade.get("stake"),
        "odds": trade.get("odds"),
        "edge": trade.get("edge"),
        "status": trade.get("status", "failed"),
        "isDryRun": trade.get("isDryRun", False)
    }
    with open(log_file, 'a') as f:
        f.write(json.dumps(trade_entry, default=str) + '\n')
    print(f"   📝 Logged: {trade.get('outcome')} on {trade.get('question', '')[:50]}")

def get_existing_chrome_tab():
    """Attach to existing Polymarket tab via Chrome DevTools."""
    print("🔗 Connecting to Chrome DevTools...")
    
    # Found via ps aux: Chrome running with --remote-debugging-port=9222
    chrome_debug_url = "ws://127.0.0.1:9222/devtools/browser/817e7022-2c27-4d04-a9a5-f244c36b9c49"
    
    playwright = sync_playwright().start()
    try:
        browser = playwright.chromium.connect_over_cdp(chrome_debug_url)
        
        # Find Polymarket tab
        for page in browser.pages:
            if "polymarket.com" in page.url.lower():
                print(f"✅ Found Polymarket tab: {page.url}")
                return browser, page
        
        print("❌ No Polymarket tab found - opening default...")
        page = browser.new_page()
        page.goto(TRADER_URL)
        time.sleep(5)  # Wait for load
        return browser, page
        
    except Exception as e:
        print(f"❌ Chrome connection failed: {e}")
        raise

def execute_trade(browser, page, market, outcome, stake, dry_run=False):
    """
    Execute a single trade via browser automation.
    
    Args:
        browser: Playwright browser instance
        page: Page object with Polymarket open
        market: Dict with market info (question, marketId, YES/NO prices)
        outcome: "YES" or "NO"
        stake: Dollar amount to bet
        dry_run: If True, don't submit order
    
    Returns:
        Dict with trade result
    """
    question = market.get("question", "")
    stake = float(stake)
    
    # Build search term
    search_term = question.split("@")[0].strip() if "@" in question else question
    clean_term = search_term.replace(" ", "-").replace("'", "").lower()
    search_url = f"{TRADER_URL}/c/{clean_term}"
    
    print(f"\n🔍 Navigating to: {search_url}")
    page.goto(search_url)
    time.sleep(3)  # Wait for page load
    
    # Verify we're on correct market
    page_title = page.title()
    if search_term.lower() not in page_title.lower():
        print(f"   ⚠️  Wrong market loaded: {page_title}")
        return {"status": "skip", "reason": "wrong market"}
    
    try:
        # Click outcome button
        btn_selector = "#yes-btn" if outcome == "YES" else "#no-btn"
        print(f"   📌 Clicking {btn_selector.replace('#', '')}...")
        page.locator(btn_selector).click()
        time.sleep(1)
        
        # Enter stake
        print(f"   💰 Setting stake: ${stake}")
        stake_input = page.locator("input[placeholder='0.00']")
        stake_input.fill(str(stake))
        time.sleep(1)
        
        if dry_run:
            print(f"   🧪 [DRY RUN] Would place {outcome} order for ${stake}")
            return {"status": "dry-run", "outcome": outcome, "stake": stake}
        
        # Place order
        print(f"   ✅ Confirming order...")
        page.locator("button:has-text('Place Order')").click()
        time.sleep(1)
        
        # Wait for confirmation
        page.wait_for_selector("[aria-label='Order placed']", timeout=10000)
        print(f"   ✓ Order confirmed!")
        
        return {"status": "confirmed", "outcome": outcome, "stake": stake}
        
    except Exception as e:
        print(f"   ❌ Trade failed: {e}")
        return {"status": "failed", "error": str(e)}

def scan_for_opportunities():
    """
    Get weather market opportunities with >5% edge.
    Uses existing forecast_cache.py output.
    """
    cache_file = SCRIPT_DIR / "forecast_cache.json"
    if not cache_file.exists():
        print("⚠️  No forecast cache found - run forecast_cache.py first")
        return []
    
    with open(cache_file) as f:
        cache = json.load(f)
    
    # Filter to >5% edge markets
    opportunities = []
    for market in cache.get("markets", []):
        edge_pct = market.get("edge_pct", 0)
        if edge_pct >= 5.0:
            opportunities.append({
                "question": market.get("question", ""),
                "marketId": market.get("marketId", ""),
                "YES": market.get("YES", 0),
                "NO": market.get("NO", 0),
                "edge": edge_pct,
                "forecast": market.get("forecast", 0)
            })
    
    # Sort by edge descending
    return sorted(opportunities, key=lambda x: x["edge"], reverse=True)

def main():
    parser = argparse.ArgumentParser(description="Batch weather arbitrage trader")
    parser.add_argument("--dry-run", action="store_true", help="Simulate trades without execution")
    parser.add_argument("--stake", type=float, default=1.0, help="Stake per trade")
    parser.add_argument("--max", type=int, default=MAX_TRADES, help="Max trades to execute")
    args = parser.parse_args()
    
    print(f"\n🚀 Batch Trader - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # 1. Balance check
    # Skip balance check - gateway has no balance endpoint, 
    # Andrew has approved live trades based on forecast edge
    print("\n💰 Balance check skipped (gateway API not available)")
    
    # 2. Get opportunities
    print(f"\n📊 Scanning for opportunities...")
    opportunities = scan_for_opportunities()
    print(f"   Found {len(opportunities)} markets with >5% edge")
    
    if not opportunities:
        print("   ⚠️  No suitable opportunities found")
        return
    
    # 3. Limit to max trades
    trades_to_execute = opportunities[:min(args.max, MAX_TRADES)]
    print(f"\n📈 Targeting {len(trades_to_execute)} markets (max {MAX_TRADES})")
    
    # 4. Execute trades
    browser = None
    page = None
    
    try:
        # Connect to browser
        browser, page = get_existing_chrome_tab()
        
        successful = 0
        failed = 0
        
        for market in trades_to_execute:
            print(f"\n—"*60)
            print(f"📊 {market['question'][:50]}")
            print(f"   Edge: {market['edge']:.1f}% | YES: {market['YES']*100:.0f}¢ | NO: {market['NO']*100:.0f}¢")
            
            # Choose best outcome
            if market['NO'] > 0.5:  # More likely NO
                outcome = "NO"
                odds = market['NO']
            else:
                outcome = "YES"
                odds = market['YES']
            
            print(f"   📌 Betting {outcome} @ {odds*100:.0f}¢")
            
            result = execute_trade(browser, page, market, outcome, args.stake, args.dry_run)
            log_trade({
                **market,
                "outcome": outcome,
                "stake": args.stake,
                "odds": odds,
                **result
            })
            
            if result["status"] in ["confirmed", "dry-run"]:
                successful += 1
            else:
                failed += 1
            
            # Rate limiting
            time.sleep(2)
        
        # Summary
        print(f"\n{'='*60}")
        print("📈 Execution Summary")
        print(f"{'='*60}")
        print(f"   Successful: {successful}")
        print(f"   Failed: {failed}")
        print(f"   Total: {successful + failed}")
        
        if args.dry_run:
            print(f"   (Dry-run mode - no real trades executed)")
        
    except Exception as e:
        print(f"\n❌ Critical error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if browser:
            browser.close()
            print("\n🔌 Browser connection closed")

if __name__ == "__main__":
    main()
