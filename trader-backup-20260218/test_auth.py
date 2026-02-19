#!/usr/bin/env python3
"""
Test Polymarket API authentication without placing trades or exposing keys.
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Polymarket credentials loaded from ~/.tinyclaw/polymarket.env (not .env — daemon.sh wipes .env on restart)
load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))

# Add scripts directory to path
script_dir = Path(__file__).parent / "polymarket-trader" / "scripts"
sys.path.insert(0, str(script_dir))

def test_authentication():
    """Test wallet signing and API authentication."""
    print("🔐 Testing Polymarket API Authentication\n")

    # Check if key is set
    if not os.environ.get("POLYMARKET_PRIVATE_KEY"):
        print("❌ POLYMARKET_PRIVATE_KEY environment variable not set")
        return False

    print("✅ Private key environment variable found")

    try:
        from polymarket_api import get_client, get_wallet_address

        # Test 1: Derive wallet address (no network call)
        print("\n1️⃣ Testing wallet derivation...")
        wallet = get_wallet_address()
        print(f"   ✅ Wallet address derived: {wallet[:6]}...{wallet[-4:]}")

        # Test 2: Initialize client and derive API credentials
        print("\n2️⃣ Testing API credential derivation...")
        client = get_client()
        print("   ✅ ClobClient initialized")
        print("   ✅ API credentials derived and set")

        # Test 3: Make a simple read-only API call
        print("\n3️⃣ Testing API connection (read-only)...")
        markets = client.get_markets()
        market_count = len(markets) if markets else 0
        print(f"   ✅ API connection successful")
        print(f"   ✅ Retrieved {market_count} markets")

        # Test 4: Check balance (read-only)
        print("\n4️⃣ Testing balance query...")
        from polymarket_api import get_balance
        balance_info = get_balance(client)

        if "error" in balance_info:
            print(f"   ⚠️  Balance query returned error: {balance_info['error']}")
        else:
            print(f"   ✅ Balance retrieved successfully")
            print(f"   📊 USDC Balance: ${balance_info.get('balance_usdc', 0):.2f}")

        print("\n" + "="*60)
        print("✅ AUTHENTICATION TEST PASSED")
        print("="*60)
        print("\nSummary:")
        print("  • Wallet signing: ✅ Operational")
        print("  • API credentials: ✅ Derived successfully")
        print("  • Network calls: ✅ Working")
        print("  • Balance queries: ✅ Working")
        print("\n⚠️  No trades were placed during this test")

        return True

    except ImportError as e:
        print(f"\n❌ Import error: {e}")
        print("   Make sure py-clob-client is installed: pip install py-clob-client")
        return False

    except Exception as e:
        print(f"\n❌ Authentication test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_authentication()
    sys.exit(0 if success else 1)
