#!/usr/bin/env bash
# verify_polymarket_creds.sh
# Health check: verifies Polymarket credentials are correctly configured.
# Run after any tinyclaw update or if trading fails with auth errors.
#
# Checks:
#   (a) ~/.tinyclaw/polymarket.env exists
#   (b) POLYMARKET_PRIVATE_KEY is present (without displaying value)
#   (c) POLYMARKET_ADDRESS is present (without displaying value)
#   (d) ~/.tinyclaw/.env does NOT contain Polymarket credentials (daemon.sh wipes it)
#
# Does NOT display any secret values.

POLYMARKET_ENV="$HOME/.tinyclaw/polymarket.env"
TINYCLAW_ENV="$HOME/.tinyclaw/.env"

PASS=0
FAIL=0

ok()   { echo "  ✅ $1"; ((PASS++)); }
fail() { echo "  ❌ $1"; ((FAIL++)); }
warn() { echo "  ⚠️  $1"; }

echo "========================================"
echo "  Polymarket Credentials Health Check"
echo "========================================"
echo

echo "1. Checking ~/.tinyclaw/polymarket.env exists..."
if [ -f "$POLYMARKET_ENV" ]; then
    ok "polymarket.env exists"
else
    fail "polymarket.env NOT FOUND at $POLYMARKET_ENV"
    echo
    echo "Fix: Create $POLYMARKET_ENV and add:"
    echo "  POLYMARKET_PRIVATE_KEY=your_key"
    echo "  POLYMARKET_ADDRESS=0xYourProxyWalletAddress"
    echo
fi

echo
echo "2. Checking POLYMARKET_PRIVATE_KEY is set..."
if [ -f "$POLYMARKET_ENV" ] && grep -q "^POLYMARKET_PRIVATE_KEY=." "$POLYMARKET_ENV"; then
    ok "POLYMARKET_PRIVATE_KEY is present (value hidden)"
else
    fail "POLYMARKET_PRIVATE_KEY is missing or empty in polymarket.env"
fi

echo
echo "3. Checking POLYMARKET_ADDRESS is set..."
if [ -f "$POLYMARKET_ENV" ] && grep -q "^POLYMARKET_ADDRESS=." "$POLYMARKET_ENV"; then
    ok "POLYMARKET_ADDRESS is present (value hidden)"
else
    fail "POLYMARKET_ADDRESS is missing or empty in polymarket.env"
fi

echo
echo "4. Checking ~/.tinyclaw/.env does NOT contain Polymarket credentials..."
if [ -f "$TINYCLAW_ENV" ]; then
    if grep -q "^POLYMARKET" "$TINYCLAW_ENV"; then
        fail ".env contains Polymarket credentials — these will be WIPED by daemon.sh on restart"
        warn "Remove POLYMARKET_* from $TINYCLAW_ENV immediately"
    else
        ok ".env is clean (no Polymarket credentials)"
    fi
else
    ok ".env does not exist (clean)"
fi

echo
echo "5. Variables in polymarket.env (names only, no values)..."
if [ -f "$POLYMARKET_ENV" ]; then
    while IFS= read -r line; do
        [[ "$line" =~ ^#.*$ ]] && continue  # skip comments
        [[ -z "$line" ]] && continue         # skip blank lines
        varname="${line%%=*}"
        echo "     $varname"
    done < "$POLYMARKET_ENV"
fi

echo
echo "========================================"
echo "  Result: $PASS passed, $FAIL failed"
echo "========================================"

if [ "$FAIL" -eq 0 ]; then
    echo "  🟢 All checks passed — credentials OK"
    exit 0
else
    echo "  🔴 $FAIL check(s) failed — fix before trading"
    exit 1
fi
