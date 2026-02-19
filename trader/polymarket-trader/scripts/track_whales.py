#!/usr/bin/env python3
"""
Track top Polymarket traders (whales) and their positions.
Note: User-specific endpoints require authentication - use this for now only for
leaderboard instructions and wallet management. For actual whale data, use Dune Analytics.

To track top traders:
1. Visit https://polymarket.com/leaderboard
2. Use browser to scrape top wallet addresses
3. Add them with: python3 track_whales.py --add-wallet <address> --name "TopTrader"
4. Then verify their positions manually on-chain or via Dune
"""

import argparse
import json
import sys
from datetime import datetime

# Known successful traders (public addresses from leaderboards)
# These should be updated periodically from Dune dashboards or leaderboard scraping
KNOWN_WHALES = [
    # Add wallet addresses here as they're discovered
    # {"address": "0x...", "name": "Trader1", "notes": "Known for political markets"}
]

def load_config():
    """Load tracked wallets from config."""
    try:
        with open("polymarket_config.json", "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"tracked_wallets": []}

def save_wallet_to_config(address, name=None):
    """Add a wallet to tracked list."""
    config = load_config()
    for w in config.get("tracked_wallets", []):
        if w.get("address", "").lower() == address.lower():
            print(f"Wallet {address} already tracked")
            return
    
    config.setdefault("tracked_wallets", []).append({
        "address": address,
        "name": name or f"Wallet_{address[:8]}",
        "added": datetime.now().isoformat()
    })
    
    with open("polymarket_config.json", "w") as f:
        json.dump(config, f, indent=2)
    print(f"Added {address} to tracked wallets")

def main():
    parser = argparse.ArgumentParser(description="Track Polymarket whales (public data only)")
    parser.add_argument("--wallet", help="Wallet address to track (requires auth - use for reference only)")
    parser.add_argument("--positions", action="store_true", help="Show wallet positions (requires auth)")
    parser.add_argument("--activity", action="store_true", help="Show recent activity (requires auth)")
    parser.add_argument("--add-wallet", help="Add wallet to tracking list")
    parser.add_argument("--name", help="Name for tracked wallet")
    parser.add_argument("--list", action="store_true", help="List tracked wallets")
    parser.add_argument("--scan-all", action="store_true", help="Scan all tracked wallets (requires auth)")
    parser.add_argument("--min-size", type=float, default=1000, help="Minimum trade size to show (requires auth)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--leaderboard", action="store_true", help="Show instructions for leaderboard")
    args = parser.parse_args()
    
    if args.leaderboard:
        print("""
🏆 Polymarket Leaderboard / Whale Discovery

The leaderboard is available at: https://polymarket.com/leaderboard

To track top traders (manual process):

1. Visit https://polymarket.com/leaderboard
2. Extract wallet addresses from top performers
3. Add them with: python3 track_whales.py --add-wallet <address> --name "TopTrader"

Dune Analytics dashboards with whale data:
- https://dune.com/datadashboards/polymarket-overview
- https://dune.com/hildobby/polymarket

For wallet-specific positions/activity:
- Use Polymarket web interface (logged in)
- Or export private key and set up L1/L2 auth

Note: The Data API requires authentication for user-specific endpoints.
Use this script for wallet management, not real-time tracking.
""")
        return
    
    if args.add_wallet:
        save_wallet_to_config(args.add_wallet, args.name)
        return
    
    if args.list:
        config = load_config()
        wallets = config.get("tracked_wallets", [])
        if not wallets:
            print("No tracked wallets. Add with --add-wallet <address>")
        else:
            print(f"Tracked Wallets ({len(wallets)}):")
            for w in wallets:
                print(f"  {w.get('name', 'Unknown')}: {w.get('address')}")
        return
    
    parser.print_help()

if __name__ == "__main__":
    main()
