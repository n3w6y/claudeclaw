# Maintenance Notes — claudeclaw/trader

This file tracks persistent configuration decisions and things to re-apply after updates.

---

## ⚠️ After Any tinyclaw Update — Check Polymarket Credentials

**Date applied**: Feb 17, 2026

### Background

`daemon.sh` (`~/.tinyclaw/lib/daemon.sh`) **completely wipes `~/.tinyclaw/.env`** on every `tinyclaw start`. It truncates the file and only writes channel tokens (e.g. `TELEGRAM_BOT_TOKEN`). Any Polymarket credentials stored there will be silently erased.

### Solution Applied

Polymarket credentials are stored in a **separate file** that daemon.sh never touches:

**`~/.tinyclaw/polymarket.env`**

Contains:
- `POLYMARKET_PRIVATE_KEY`
- `POLYMARKET_ADDRESS`

### Files Modified

The following files were changed to load from `polymarket.env` instead of `.env`:

1. **`trader/polymarket-trader/scripts/polymarket_api.py`** (line ~29)
   ```python
   # Polymarket credentials loaded from ~/.tinyclaw/polymarket.env (not .env — daemon.sh wipes .env on restart)
   load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))
   ```

2. **`trader/test_auth.py`** (line ~12)
   ```python
   # Polymarket credentials loaded from ~/.tinyclaw/polymarket.env (not .env — daemon.sh wipes .env on restart)
   load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))
   ```

### If a tinyclaw Update Overwrites polymarket_api.py

If a tinyclaw update replaces `polymarket_api.py` and reverts it to load from `~/.tinyclaw/.env`:

1. Re-apply the one-line change:
   ```bash
   # In polymarket_api.py, change:
   load_dotenv(os.path.expanduser("~/.tinyclaw/.env"))
   # To:
   load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))
   ```

2. Same fix in `test_auth.py`.

3. Run the health check to verify:
   ```bash
   bash ~/claudeclaw/scripts/verify_polymarket_creds.sh
   ```

4. Test the connection:
   ```bash
   cd ~/claudeclaw/trader && python3 test_auth.py
   ```

### Health Check Script

```bash
bash ~/claudeclaw/scripts/verify_polymarket_creds.sh
```

Checks:
- `polymarket.env` exists
- Both variables present (without showing values)
- `~/.tinyclaw/.env` does NOT contain Polymarket credentials

---

## Trading Strategy Rules (Updated Feb 17, 2026)

See `trader/NEW_TRADING_RULES.md` for full specification.

**Key changes from original strategy**:
- Core: Trade forecast convergence, NOT hold to resolution
- Entry: Minimum **20% edge** (raised from 10-15%)
- Exit 1: **+30% profit target** → sell immediately
- Exit 2: **-20% stop loss** → sell immediately, no exceptions
- Exit 3: **Edge <10%** → sell regardless of P&L
- Monitoring: Every **2 hours** (was 4 hours)
- Never hold into resolution window (<4 hours to close)

---

## Credential Storage Map

| Credential | File | Notes |
|-----------|------|-------|
| TELEGRAM_BOT_TOKEN | `~/.tinyclaw/.env` | Written by daemon.sh on start |
| POLYMARKET_PRIVATE_KEY | `~/.tinyclaw/polymarket.env` | Permanent, never wiped |
| POLYMARKET_ADDRESS | `~/.tinyclaw/polymarket.env` | Permanent, never wiped |

---

## Order Execution Strategy (Updated Feb 16, 2026)

Weather markets use **GTC maker orders with 30-minute TTL** — not FOK.

FOK orders showed 0% fill rate (weather markets have 99¢ spreads, no taker liquidity).

See `trader/GTC_IMPLEMENTATION_COMPLETE.md` for full implementation details.

---

## Mission Control Dashboard

**Single source of truth**: `trader/polymarket-trader/trading_state.json`

Updated after every trading action. Never store secrets in this file — wallet is masked as `0x8DE0...9bD1`.

---
