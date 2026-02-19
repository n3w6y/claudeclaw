# Environment Variable Configuration

## Overview

All Python scripts now load environment variables from `~/.tinyclaw/.env` using `python-dotenv`. This centralizes credential management and ensures consistency across all trading scripts.

## What Was Updated

### 1. Installed Dependencies ✅
```bash
pip install python-dotenv
```

### 2. Updated Scripts ✅

**`polymarket_api.py`** - Core API client
```python
from dotenv import load_dotenv

# Load environment variables from ~/.tinyclaw/.env
load_dotenv(os.path.expanduser("~/.tinyclaw/.env"))
```

**`test_auth.py`** - Authentication test script
```python
from dotenv import load_dotenv

# Load environment variables from ~/.tinyclaw/.env
load_dotenv(os.path.expanduser("~/.tinyclaw/.env"))
```

### 3. Automatic Propagation ✅

All scripts that import `polymarket_api` automatically get credentials loaded:
- `autonomous_trader_v2.py` ✅
- `autonomous_trader.py` ✅
- `weather_scanner_supervised.py` ✅
- `execute_trade.py` ✅
- `position_monitor.py` ✅
- Any other script importing `polymarket_api`

## Environment File Location

**File**: `~/.tinyclaw/.env`

**Current Status**:
- ✅ File exists
- ⚠️ Missing Polymarket credentials

## Required Variables

Add these to `~/.tinyclaw/.env`:

```bash
POLYMARKET_PRIVATE_KEY=your_private_key_here
POLYMARKET_ADDRESS=your_wallet_address_here
```

### Variable Descriptions

**`POLYMARKET_PRIVATE_KEY`**
- Your Magic.link signer key (NOT your wallet's private key)
- Used for API authentication
- Keep this secret and never commit to git

**`POLYMARKET_ADDRESS`**
- Your Polymarket proxy wallet address
- Found on your Polymarket profile page
- This is the address that holds your balances and positions

## Security Notes

✅ **DO NOT**:
- Commit `.env` files to git
- Display or print environment variable values
- Share credentials in logs or console output

✅ **DO**:
- Keep `.env` file permissions restricted (`chmod 600`)
- Use the centralized `~/.tinyclaw/.env` file
- Verify credentials are loaded before running trades

## Testing

### 1. Verify Environment Loading

```bash
cd /home/andrew/claudeclaw/trader
python3 -c "
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser('~/.tinyclaw/.env'))

has_key = bool(os.environ.get('POLYMARKET_PRIVATE_KEY'))
has_address = bool(os.environ.get('POLYMARKET_ADDRESS'))

print(f'POLYMARKET_PRIVATE_KEY: {\"✅ Set\" if has_key else \"⚠️  Not set\"}')
print(f'POLYMARKET_ADDRESS: {\"✅ Set\" if has_address else \"⚠️  Not set\"}')
"
```

### 2. Test Authentication

```bash
cd /home/andrew/claudeclaw/trader
python3 test_auth.py
```

Expected output (after adding credentials):
```
🔐 Testing Polymarket API Authentication

✅ Private key environment variable found

1️⃣ Testing wallet derivation...
   ✅ Wallet address derived: 0xABC...DEF

2️⃣ Testing API credential derivation...
   ✅ ClobClient initialized
   ✅ API credentials derived and set

3️⃣ Testing API connection (read-only)...
   ✅ API connection successful
   ✅ Retrieved N markets

4️⃣ Testing balance query...
   ✅ Balance retrieved successfully
   📊 USDC Balance: $XX.XX

============================================================
✅ AUTHENTICATION TEST PASSED
============================================================
```

## Troubleshooting

### "POLYMARKET_PRIVATE_KEY environment variable not set"

**Cause**: Variables not in `~/.tinyclaw/.env`

**Solution**: Add credentials to the file:
```bash
echo "POLYMARKET_PRIVATE_KEY=your_key" >> ~/.tinyclaw/.env
echo "POLYMARKET_ADDRESS=your_address" >> ~/.tinyclaw/.env
chmod 600 ~/.tinyclaw/.env
```

### "Import error: No module named 'dotenv'"

**Cause**: `python-dotenv` not installed

**Solution**:
```bash
pip install python-dotenv
```

### Variables still not loading

**Check file permissions**:
```bash
ls -la ~/.tinyclaw/.env
```

**Check file contents** (safely):
```bash
grep "POLYMARKET" ~/.tinyclaw/.env | sed 's/=.*/=***/'
```

**Verify path expansion**:
```python
import os
print(os.path.expanduser("~/.tinyclaw/.env"))
```

## Migration Notes

### Previous Setup
Before this update, scripts expected environment variables to be set manually or in various locations.

### Current Setup
All scripts now load from the centralized `~/.tinyclaw/.env` file automatically.

### No Changes Needed
Scripts that already import `polymarket_api` require no code changes - they automatically benefit from the centralized configuration.

## File Structure

```
~/.tinyclaw/
└── .env                    # Centralized environment variables
                           # Contains: POLYMARKET_PRIVATE_KEY, POLYMARKET_ADDRESS

trader/
├── polymarket-trader/
│   └── scripts/
│       └── polymarket_api.py    # Loads ~/.tinyclaw/.env on import
├── autonomous_trader_v2.py      # Auto-loads via polymarket_api import
├── weather_scanner_supervised.py # Auto-loads via polymarket_api import
└── test_auth.py                 # Explicitly loads ~/.tinyclaw/.env
```

## Status

✅ **Configuration Complete**
- All scripts updated to use `~/.tinyclaw/.env`
- `python-dotenv` installed
- Automatic credential loading on module import

⚠️ **Action Required**
- Add `POLYMARKET_PRIVATE_KEY` to `~/.tinyclaw/.env`
- Add `POLYMARKET_ADDRESS` to `~/.tinyclaw/.env`
- Run `test_auth.py` to verify

---

**Last Updated**: 2026-02-16
**Configuration Status**: ✅ Complete (awaiting credentials)
