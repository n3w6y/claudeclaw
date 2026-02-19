# Polymarket Credentials Status

**Date**: Feb 17, 2026 10:44 UTC
**Status**: ❌ INCOMPLETE

---

## Current Situation

**File**: `~/.tinyclaw/.env`
- ✅ File exists
- ✅ Contains `TELEGRAM_BOT_TOKEN`
- ❌ Missing `POLYMARKET_PRIVATE_KEY`
- ❌ Missing `POLYMARKET_ADDRESS`

---

## Required Variables

The Polymarket API client requires TWO environment variables:

### 1. POLYMARKET_PRIVATE_KEY
- **Purpose**: Magic.link signer key for authentication
- **Source**: From Polymarket account setup
- **Status**: ❌ NOT SET

### 2. POLYMARKET_ADDRESS
- **Purpose**: Proxy wallet address from Polymarket profile page
- **Format**: Ethereum address (0x...)
- **Source**: Polymarket.com → Profile → Wallet Address
- **Status**: ❌ NOT SET

---

## How to Fix

Add these two lines to `~/.tinyclaw/.env`:

```bash
POLYMARKET_PRIVATE_KEY=your_key_here
POLYMARKET_ADDRESS=0xYourProxyWalletAddress
```

**Important**:
- The `POLYMARKET_ADDRESS` is your Polymarket proxy wallet address (from profile page)
- It is NOT the address derived from your private key
- Both are required for signature_type=1 (Polymarket.com accounts)

---

## Impact

**Without these credentials**:
- ❌ Cannot check live balance
- ❌ Cannot place orders
- ❌ Cannot exit positions
- ❌ Cannot monitor market prices via API

**Current workaround**:
- Using last known balance: $56.34
- Manual exits via Polymarket UI (as done with Chicago)
- Cannot run autonomous trading

---

## Next Steps

1. **User action required**: Add both keys to `~/.tinyclaw/.env`
2. **Test connection**: Run `python3 polymarket-trader/scripts/test_auth.py`
3. **Get live balance**: Once credentials work, update trading_state.json
4. **Resume trading**: Autonomous scans can then execute GTC orders

---

**Until credentials are restored, all trading must be done manually via Polymarket UI.**
