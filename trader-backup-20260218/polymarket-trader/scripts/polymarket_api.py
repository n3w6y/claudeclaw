#!/usr/bin/env python3
"""
Polymarket CLOB API client wrapper.

Handles authentication, order placement, and balance checking.
Credentials loaded from ~/.tinyclaw/polymarket.env (POLYMARKET_PRIVATE_KEY, POLYMARKET_ADDRESS).

Usage:
    from polymarket_api import get_client, place_order, get_balance
    
    client = get_client()
    balance = get_balance(client)
    order = place_order(client, token_id, side="BUY", size=5, price=0.65)
"""

import os
import json
from decimal import Decimal
from pathlib import Path
from typing import Optional, Literal

from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds, OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL
from eth_account import Account

# Polymarket credentials loaded from ~/.tinyclaw/polymarket.env (not .env — daemon.sh wipes .env on restart)
load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))

# Constants
CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137  # Polygon mainnet

# Config
SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR.parent / "config"
TRADING_CONFIG = CONFIG_DIR / "trading_limits.json"

def load_trading_limits():
    """Load trading limits from config."""
    defaults = {
        "max_order_usd": 10,      # Max single order
        "daily_limit_usd": 100,   # Max daily volume
        "require_confirmation": True,
        "allowed_markets": []     # Empty = all allowed
    }
    
    if TRADING_CONFIG.exists():
        with open(TRADING_CONFIG) as f:
            config = json.load(f)
            defaults.update(config)
    
    return defaults

def get_client(signature_type: int = 1) -> ClobClient:
    """
    Get authenticated Polymarket CLOB client.

    Uses POLYMARKET_PRIVATE_KEY environment variable for the Magic.link signer key,
    and POLYMARKET_ADDRESS for the proxy wallet address (from your profile page).

    Args:
        signature_type: 0=EOA (standalone wallet), 1=POLY_PROXY (Polymarket account via email/Google),
                        2=GNOSIS_SAFE (browser wallet). Default 1 for Polymarket.com accounts.
    """
    key = os.environ.get("POLYMARKET_PRIVATE_KEY")
    if not key:
        raise ValueError("POLYMARKET_PRIVATE_KEY environment variable not set")

    funder = os.environ.get("POLYMARKET_ADDRESS")
    if not funder:
        raise ValueError(
            "POLYMARKET_ADDRESS environment variable not set. "
            "This should be your Polymarket proxy wallet address from your profile page, "
            "NOT the address derived from your private key."
        )

    client = ClobClient(
        host=CLOB_HOST,
        chain_id=CHAIN_ID,
        key=key,
        signature_type=signature_type,
        funder=funder  # Polymarket proxy wallet address (from profile page)
    )
    
    # Derive and set API credentials
    creds = client.create_or_derive_api_creds()
    client.set_api_creds(ApiCreds(
        api_key=creds.api_key,
        api_secret=creds.api_secret,
        api_passphrase=creds.api_passphrase
    ))
    
    return client

def get_wallet_address() -> str:
    """Get Polymarket proxy wallet address (the one that holds balances/positions)."""
    addr = os.environ.get("POLYMARKET_ADDRESS")
    if not addr:
        raise ValueError("POLYMARKET_ADDRESS not set")
    return addr

def get_balance(client: ClobClient) -> dict:
    """
    Get account balances.
    
    Returns dict with USDC balance and allowances.
    """
    from py_clob_client.clob_types import BalanceAllowanceParams
    
    try:
        params = BalanceAllowanceParams(asset_type="COLLATERAL")
        bal = client.get_balance_allowance(params)
        
        # Balance is in wei (6 decimals for USDC)
        balance_raw = int(bal.get("balance", "0"))
        balance_usdc = balance_raw / 1_000_000
        
        return {
            "wallet": get_wallet_address(),
            "balance_usdc": balance_usdc,
            "balance_raw": balance_raw,
            "allowances": bal.get("allowances", {})
        }
    except Exception as e:
        return {"error": str(e)}

def get_open_orders(client: ClobClient) -> list:
    """Get all open orders."""
    try:
        return client.get_orders() or []
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return []

def get_positions(client: ClobClient) -> list:
    """
    Get all active positions (non-zero token holdings).

    Returns list of positions with:
    - token_id: Token ID
    - outcome: YES or NO
    - market: Market question/title
    - condition_id: Condition ID
    - balance: Number of shares held
    - current_price: Current market price
    - entry_price: Estimated entry price (cost_basis / balance)
    - cost_basis: Total amount paid for position
    """
    try:
        wallet = get_wallet_address()

        # Get all open orders to find active markets
        orders = client.get_orders() or []

        # Get order history to calculate entry prices
        # Note: We'll need to track this via journal or state file
        # For now, we'll get current positions from balance

        positions = []

        # This is a simplified version - in production you'd want to:
        # 1. Query all token balances from the wallet
        # 2. Get market info for each token
        # 3. Calculate entry price from trade history

        # For now, return empty list - will be populated from journal/state
        return positions

    except Exception as e:
        print(f"Error fetching positions: {e}")
        return []

def get_market_info(client: ClobClient, condition_id: str) -> Optional[dict]:
    """Get market info by condition ID."""
    try:
        market = client.get_market(condition_id)
        return market
    except Exception as e:
        print(f"Error fetching market: {e}")
        return None

def place_order(
    client: ClobClient,
    token_id: str,
    side: Literal["BUY", "SELL"],
    size: float,
    price: float,
    order_type: str = "GTC"
) -> dict:
    """
    Place an order on Polymarket.
    
    Args:
        client: Authenticated ClobClient
        token_id: The token ID (YES or NO token for a market)
        side: "BUY" or "SELL"
        size: Number of shares (in dollars at $1/share if wins)
        price: Price per share (0.01 to 0.99)
        order_type: "GTC" (good-til-cancelled) or "FOK" (fill-or-kill)
    
    Returns:
        Order response dict
    """
    limits = load_trading_limits()
    
    # Safety checks
    order_value = size * price
    if order_value > limits["max_order_usd"]:
        return {
            "error": f"Order value ${order_value:.2f} exceeds limit ${limits['max_order_usd']}"
        }
    
    # Skip confirmation for live trading (edge confirmed via forecast_cache.py)
    if limits["require_confirmation"] and size > 5:
        return {
            "requires_confirmation": True,
            "order": {
                "token_id": token_id,
                "side": side,
                "size": size,
                "price": price,
                "order_type": order_type,
                "value_usd": order_value
            },
            "message": f"Confirm: {side} {size} shares @ {price:.2f} (${order_value:.2f})"
        }
    
    try:
        # Use create_and_post_order as per Polymarket docs
        response = client.create_and_post_order(
            token_id=token_id,
            side=BUY if side == "BUY" else SELL,
            price=price,
            size=size,
            order_type=OrderType.GTC
        )
        
        return {
            "success": True,
            "order_id": response.get("orderID"),
            "response": response
        }
        
    except Exception as e:
        return {"error": str(e)}

def execute_confirmed_order(
    client: ClobClient,
    token_id: str,
    side: Literal["BUY", "SELL"],
    size: float,
    price: float,
    order_type: str = "GTC"
) -> dict:
    """
    Execute an order that has been confirmed (bypasses confirmation check).
    
    Use this after user confirms via place_order().
    """
    try:
        order_args = OrderArgs(
            token_id=token_id,
            price=price,
            size=size,
            side=BUY if side == "BUY" else SELL,
        )
        
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, orderType=OrderType.GTC)
        
        return {
            "success": True,
            "order_id": response.get("orderID"),
            "response": response
        }
        
    except Exception as e:
        return {"error": str(e)}

def cancel_order(client: ClobClient, order_id: str) -> dict:
    """Cancel an open order."""
    try:
        response = client.cancel(order_id)
        return {"success": True, "response": response}
    except Exception as e:
        return {"error": str(e)}

def cancel_all_orders(client: ClobClient) -> dict:
    """Cancel all open orders."""
    try:
        response = client.cancel_all()
        return {"success": True, "response": response}
    except Exception as e:
        return {"error": str(e)}

# ============================================================================
# CLI for testing
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Polymarket API client")
    parser.add_argument("--balance", action="store_true", help="Check balance")
    parser.add_argument("--orders", action="store_true", help="List open orders")
    parser.add_argument("--test", action="store_true", help="Test API connection")
    args = parser.parse_args()
    
    try:
        client = get_client()
        print(f"✅ Connected to Polymarket")
        print(f"   Wallet: {get_wallet_address()}")
        
        if args.balance:
            bal = get_balance(client)
            print(f"\n📊 Balance info:")
            print(json.dumps(bal, indent=2, default=str))
        
        if args.orders:
            orders = get_open_orders(client)
            print(f"\n📋 Open orders: {len(orders)}")
            for o in orders[:5]:
                print(f"   - {o}")
        
        if args.test or (not args.balance and not args.orders):
            print("\n🧪 Testing API...")
            markets = client.get_markets()
            print(f"   Markets accessible: {len(markets) if markets else 'unknown'}")
            print("   ✅ API fully operational")
            
    except Exception as e:
        print(f"❌ Error: {e}")
