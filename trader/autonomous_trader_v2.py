#!/usr/bin/env python3
"""
Autonomous Weather Arbitrage Trader v2
Rules: ~/claudeclaw/trader/TRADING_RULES.md

Structure:
  1. STARTUP   — connect, check balance, load positions, sync vs live CLOB
  2. MONITOR   — check each position against 4 exit triggers (priority order)
  3. SCAN      — find new opportunities, re-validate live, place GTC orders
  4. STATE     — write trading_state.json, positions_state.json, open_orders.json
"""

import os
import sys
import json
import math
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))

from polymarket_api import get_client, get_balance
from weather_arb import (
    get_weather_events, parse_weather_event, analyze_weather_event,
    calculate_probability, prepare_forecasts_for_market, get_ensemble_forecast,
)
from early_exit_manager import PositionTracker, Position, ExitRecord, execute_full_exit
try:
    from metar_source import assess_resolution_confidence
    HAS_METAR = True
except ImportError:
    HAS_METAR = False
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

JOURNAL_DIR  = TRADER_DIR / "polymarket-trader" / "journal"
STATE_DIR    = TRADER_DIR / "polymarket-trader"
POSITIONS_FILE   = STATE_DIR / "positions_state.json"
OPEN_ORDERS_FILE = STATE_DIR / "open_orders.json"
TRADING_STATE_FILE = STATE_DIR / "trading_state.json"
SCAN_DETAILS_FILE  = STATE_DIR / "scan_details.jsonl"

JOURNAL_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def journal_path() -> Path:
    return JOURNAL_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.md"


def log(text: str):
    with open(journal_path(), 'a') as f:
        f.write(text + "\n")


def log_scan_detail(scan_id: str, scan_ts: str, opp: dict, side: str | None,
                    edge: float, price: float, conf: float,
                    rejection: str | None, qualified: bool = False):
    """Append a single opportunity evaluation to scan_details.jsonl."""
    import json as _json
    row = {
        "scan_id": scan_id,
        "scan_timestamp": scan_ts,
        "city": opp.get("city", ""),
        "market": opp.get("market_question", ""),
        "side": side,
        "edge": round(edge, 2),
        "price": round(price, 4),
        "confidence": round(conf, 4),
        "sources": ",".join(opp.get("forecast_sources", [])),
        "forecast_temp": str(opp.get("forecast_temp", "")),
        "liquidity": opp.get("liquidity", 0) or 0,
        "rejection_reason": rejection,
        "qualified": qualified,
    }
    with open(SCAN_DETAILS_FILE, "a") as f:
        f.write(_json.dumps(row) + "\n")


def load_open_orders() -> list:
    if not OPEN_ORDERS_FILE.exists():
        return []
    try:
        with open(OPEN_ORDERS_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def save_open_orders(orders: list):
    with open(OPEN_ORDERS_FILE, 'w') as f:
        json.dump(orders, f, indent=2, default=str)


def position_size_for(balance_usdc: float) -> float:
    """Tier-based position sizing per TRADING_RULES.md."""
    if balance_usdc < 10:
        return 0.0
    if balance_usdc < 100:
        return 5.0
    return math.ceil(balance_usdc / 100) * 5.0


def hours_to_resolution(market_date_str: str) -> float | None:
    """Hours until a market resolves. Returns None if unparseable."""
    try:
        dt = datetime.fromisoformat(str(market_date_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (dt - datetime.now(timezone.utc)).total_seconds() / 3600
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Price fetching
# ---------------------------------------------------------------------------

def get_token_price(client, condition_id: str, side: str) -> tuple[str | None, float | None]:
    """
    Fetch token_id + fresh mid price from CLOB order book.
    Returns (token_id, price) or (None, None).
    """
    try:
        market = client.get_market(condition_id)
        for token in market.get('tokens', []):
            if token.get('outcome', '').upper() == side.upper():
                token_id = token.get('token_id')
                price = float(token.get('price', 0))
                return token_id, price
    except Exception as e:
        print(f"    error fetching token data for {condition_id}: {e}")
    return None, None


def get_batch_prices(client, positions: list) -> dict:
    """
    Fetch current prices for multiple positions via the batch /prices endpoint.
    Falls back to individual calls if batch fails.
    Returns {token_id: price} — returns None for a token if the spread is
    too wide (>40¢) since the mid price would be unreliable.
    """
    results = {}
    token_ids = [str(p.token_id) for p in positions]
    if not token_ids:
        return results

    try:
        for pos in positions:
            try:
                ob = client.get_order_book(str(pos.token_id))
                bids = ob.bids or []
                asks = ob.asks or []
                best_bid = float(bids[0].price) if bids else None
                best_ask = float(asks[0].price) if asks else None
                if best_bid and best_ask:
                    spread = best_ask - best_bid
                    if spread > 0.40:
                        # Wide spread — mid is unreliable, skip
                        print(f"  ⚠️  {pos.city} {pos.side}: wide spread {best_bid*100:.0f}¢/{best_ask*100:.0f}¢ (spread {spread*100:.0f}¢) — price unreliable, skipping")
                        results[str(pos.token_id)] = None
                        continue
                    mid = (best_bid + best_ask) / 2
                elif best_bid:
                    mid = best_bid
                elif best_ask:
                    mid = best_ask
                else:
                    _, fallback = get_token_price(client, pos.condition_id, pos.side)
                    mid = fallback
                results[str(pos.token_id)] = mid
            except Exception:
                _, fallback = get_token_price(client, pos.condition_id, pos.side)
                results[str(pos.token_id)] = fallback
    except Exception as e:
        print(f"  Batch price fetch error: {e}")

    return results


# ---------------------------------------------------------------------------
# STEP 1: STARTUP
# ---------------------------------------------------------------------------

def _resolve_phantoms(client, tracker: PositionTracker, phantom_orders: list) -> set:
    """
    Phantom orders are in local 'OPEN' state but not found on CLOB.
    Possible causes:
      1. Filled while we were offline
      2. Expired/canceled

    Check client.get_trades() to see if they filled. If so, create Position.
    Returns set of order_ids that were filled.
    """
    if not phantom_orders:
        return set()

    # Fetch all trades for this wallet
    try:
        trades = client.get_trades() or []
    except Exception as e:
        print(f"    ⚠️  Could not fetch trades to resolve phantoms: {e}")
        return set()

    # Build map: order_id -> fills
    # GTC maker orders appear in maker_orders[] array, not at top level
    fills_by_order = {}
    for t in trades:
        # Top-level taker order id
        taker_oid = t.get('taker_order_id') or t.get('order_id') or t.get('orderID')
        if taker_oid:
            fills_by_order.setdefault(taker_oid, []).append({
                'size': float(t.get('size', 0)),
                'price': float(t.get('price', 0)),
                'timestamp': t.get('match_time') or t.get('timestamp'),
            })
        # Maker orders — our GTC limit orders appear here
        for mo in t.get('maker_orders', []):
            mo_oid = mo.get('order_id')
            if mo_oid:
                fills_by_order.setdefault(mo_oid, []).append({
                    'size': float(mo.get('matched_amount', 0)),
                    'price': float(mo.get('price', 0)),
                    'timestamp': t.get('match_time') or t.get('timestamp'),
                })

    filled_ids = set()

    for order in phantom_orders:
        order_id = order.get('order_id')
        if not order_id:
            continue

        fills = fills_by_order.get(order_id, [])
        if not fills:
            continue

        # Aggregate fills for this order
        total_shares = sum(float(f.get('size', 0)) for f in fills)
        total_cost = sum(float(f.get('size', 0)) * float(f.get('price', 0)) for f in fills)
        if total_shares == 0:
            continue

        actual_entry = total_cost / total_shares
        first_fill_time = fills[0].get('timestamp') or fills[0].get('matched_time')

        # Extract metadata from order record
        city = order.get('city', 'Unknown')
        side = order.get('side', 'NO')
        token_id = order.get('token_id', '')
        market_date_str = order.get('date', '') or order.get('market_date', '')
        sources_list_raw = order.get('sources', [])
        if isinstance(sources_list_raw, list):
            sources_str = ','.join(sources_list_raw)
        else:
            sources_str = str(sources_list_raw) if sources_list_raw else ''

        # Determine if US market from sources (NOAA = US market)
        sources_list = order.get('sources', [])
        if isinstance(sources_list, str):
            sources_list = sources_list.split(',')
        is_us = any('noaa' in s.lower() for s in sources_list)

        # Build holding record
        holding = {
            'shares': total_shares,
            'cost': total_cost,
            'time': first_fill_time,
        }

        # Create Position
        position = Position(
            market_name=order.get('question', f"{city} {side}")[:80],
            condition_id=order.get('condition_id', ''),
            token_id=token_id,
            side=side,
            entry_price=actual_entry,
            shares=holding['shares'],
            cost_basis=holding['cost'],
            entry_date=holding['time'] or datetime.now(timezone.utc).isoformat(),
            order_id=order_id,
            original_edge=order.get('edge', 10.0),
            threshold_temp_f=0.0,  # Not stored in order — edge evap still uses original_edge
            city=city,
            market_date=market_date_str,
            is_us_market=is_us,
            forecast_sources=sources_str,
            icao=order.get('icao', ''),
        )

        tracker.add_position(position)
        filled_ids.add(order_id)
        print(f"    ✅ FILLED → position created: {city} {side} @ {actual_entry * 100:.1f}¢  {holding['shares']:.2f} shares  cost ${holding['cost']:.2f}")

    return filled_ids

def startup():
    """
    Connect, check balance, load positions, sync against live CLOB.
    Warns and stops if positions_state.json doesn't match live CLOB orders.
    Returns (client, balance_usdc, tracker, open_orders) or exits.
    """
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    print("=" * 70)
    print("AUTONOMOUS WEATHER ARBITRAGE TRADER v2")
    print(f"Run time : {now}")
    print("Rules    : ~/claudeclaw/trader/TRADING_RULES.md")
    print("=" * 70)

    client = get_client(signature_type=1)
    bal = get_balance(client)
    balance_usdc = bal['balance_usdc']
    wallet = bal['wallet']

    print(f"\nBalance  : ${balance_usdc:.2f}")
    print(f"Wallet   : {wallet[:6]}...{wallet[-4:]}")

    # Load local position tracker
    tracker = PositionTracker(POSITIONS_FILE)
    positions = tracker.get_active_positions()

    # Load local open orders
    open_orders = load_open_orders()
    live_local = [o for o in open_orders if o.get('status') == 'OPEN']

    # Query live CLOB open orders
    try:
        clob_orders = client.get_orders() or []
    except Exception as e:
        print(f"\n⚠️  Could not query CLOB open orders: {e}")
        clob_orders = []

    clob_open_ids = {o.get('id') or o.get('orderID') for o in clob_orders}
    local_open_ids = {o.get('order_id') for o in live_local}

    # Sync check: warn if local state diverges from CLOB reality
    phantom = local_open_ids - clob_open_ids  # in local but not on CLOB
    if phantom:
        print(f"\n⚠️  SYNC: {len(phantom)} local 'OPEN' orders not found on CLOB — checking for fills...")
        phantom_order_records = [o for o in live_local if o.get('order_id') in phantom]
        filled_ids = _resolve_phantoms(client, tracker, phantom_order_records)
        for o in open_orders:
            if o.get('order_id') in phantom:
                if o.get('order_id') in filled_ids:
                    o['status'] = 'FILLED'
                else:
                    o['status'] = 'EXPIRED'
                    print(f"    ↩️  EXPIRED (unfilled): {o.get('city','?')} {o.get('side')} {o.get('order_id','')[:20]}...")
        save_open_orders(open_orders)
        live_local = [o for o in open_orders if o.get('status') == 'OPEN']

    total_deployed = len(positions) + len(live_local)
    print(f"\nPositions  : {len(positions)}")
    print(f"Open orders: {len(live_local)} (live CLOB: {len(clob_orders)})")
    print(f"Slots used : {total_deployed}/10")

    if total_deployed > 10:
        print("\n⚠️  WARNING: total deployed > 10 — check positions_state.json")

    if balance_usdc < 10:
        print("\n❌ Balance below $10 hard floor — cannot trade")

    return client, balance_usdc, tracker, open_orders


# ---------------------------------------------------------------------------
# STEP 2: POSITION MONITORING
# ---------------------------------------------------------------------------

def recalculate_edge(position: Position, current_price: float) -> float:
    """
    Estimate current edge by assuming original forecast probability still holds
    and comparing to fresh market price.
    A proper re-fetch from weather_arb is done in forecast_monitor.py every 2h.
    """
    original_edge = getattr(position, 'original_edge', None)
    if original_edge is None:
        return 0.0

    # Reconstruct implied forecast probability from entry price + original edge
    if position.side == 'YES':
        forecast_prob = position.entry_price + (original_edge / 100)
        fresh_edge = (forecast_prob - current_price) * 100
    else:
        # For NO side: entry_price is the NO price paid (1 - yes_price)
        # forecast_prob for NO = 1 - yes_forecast_prob
        forecast_prob = position.entry_price + (original_edge / 100)
        fresh_edge = (forecast_prob - current_price) * 100

    return max(fresh_edge, 0.0)


def check_exit_triggers(position: Position, current_price: float) -> tuple[str | None, str | None]:
    """
    Check all 4 exit conditions in priority order per TRADING_RULES.md.
    Priority: Time > Stop Loss > Edge Evaporation > Profit Target
    Returns (trigger_name, reason) or (None, None).

    RESOLUTION PROXIMITY GUARD:
    Within 8 hours of resolution, stop loss and edge evaporation are suppressed.
    Near resolution, thin liquidity causes artificially low prices on winning positions.
    Only time exit and profit target fire in the final 8 hours.
    Consensus hold (checked before this function) handles hold-to-resolution decisions.
    """
    cost  = position.cost_basis
    value = position.shares * current_price
    ttl   = hours_to_resolution(getattr(position, 'market_date', ''))

    # 1. Time exit: < 8 hours to resolution (TRADING_RULES.md Priority 1)
    if ttl is not None and ttl < 8:
        return 'time', f"Time exit: {ttl:.1f}h to resolution"

    # Resolution proximity guard — suppress volatile exits in final 8h
    near_resolution = ttl is not None and ttl < 8

    # 2. Stop loss: value <= 80% of cost — suppressed near resolution
    if not near_resolution and value <= cost * 0.80:
        pct = (value / cost - 1) * 100
        return 'stop_loss', f"Stop loss: {pct:.1f}% (value ${value:.2f} <= floor ${cost * 0.80:.2f})"

    # 3. Edge evaporation: recalculated edge < 10% — suppressed near resolution
    if not near_resolution:
        fresh_edge = recalculate_edge(position, current_price)
        if fresh_edge < 10.0:
            return 'edge_evap', f"Edge evaporation: {fresh_edge:.1f}% < 10%"

    # 4. Profit target: value >= 130% of cost — always active
    if value >= cost * 1.30:
        pct = (value / cost - 1) * 100
        return 'profit', f"Profit target: {pct:.1f}% (value ${value:.2f} >= target ${cost * 1.30:.2f})"

    return None, None


def parse_resolution_time(market_date_str: str) -> datetime:
    """Parse market_date into a timezone-aware datetime."""
    try:
        dt = datetime.fromisoformat(str(market_date_str))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc) + timedelta(days=30)


def get_required_margin(hours_remaining: float, is_us_market: bool) -> tuple[float, str]:
    """
    Return required margin in the market's native unit based on time to resolution.

    Tiered thresholds per TRADING_RULES.md — tighter margins allowed as
    resolution approaches because forecast accuracy improves.

    Returns (margin, unit_label).
    """
    if is_us_market:
        if hours_remaining > 12:
            return 5.0, "°F"
        elif hours_remaining > 6:
            return 4.0, "°F"
        else:
            return 2.0, "°F"
    else:
        if hours_remaining > 12:
            return 3.0, "°C"
        elif hours_remaining > 6:
            return 2.0, "°C"
        else:
            return 1.0, "°C"


def check_consensus_hold(
    position: Position,
    forecasts: list,
    threshold: float,
    is_us_market: bool,
    current_price: float,
) -> tuple[bool, str]:
    """
    Check if position qualifies for hold-to-resolution per Priority 0 exit rule.

    All temperatures in `forecasts` must already be in the market's native unit
    (°F for US markets, °C for non-US markets) — use prepare_forecasts_for_market()
    before calling this function.

    `threshold` must also be in the market's native unit.

    Returns (should_hold, reason).
    If True, caller must skip all other exit checks.
    """
    if not forecasts or len(forecasts) < 2:
        return False, "Insufficient sources (need ≥2)"

    # Must have at least one local source (NOAA, MetService, BOM)
    has_local = any(f.get("is_local", False) for f in forecasts)
    if not has_local:
        return False, "No local source — cannot consensus hold"

    # Time-to-resolution check
    resolution_time = parse_resolution_time(getattr(position, 'market_date', ''))
    hours_remaining = (resolution_time - datetime.now(timezone.utc)).total_seconds() / 3600

    if hours_remaining > 24:
        return False, f"Too far from resolution ({hours_remaining:.1f}h > 24h)"
    if hours_remaining < 0.5:
        return False, "Already resolved or <30min"

    required_margin, unit = get_required_margin(hours_remaining, is_us_market)

    # All sources must be on the SAME side of the threshold
    if position.side == "NO":
        # Betting it WON'T reach threshold — every source must forecast BELOW threshold
        all_correct_side = all(f["high"] < threshold for f in forecasts)
        if not all_correct_side:
            above = [f["source"] for f in forecasts if f["high"] >= threshold]
            return False, f"Not all below threshold: {above} above"
        # Most aggressive = closest to threshold
        most_aggressive = max(f["high"] for f in forecasts)
        margin = threshold - most_aggressive
    else:
        # Betting it WILL reach threshold — every source must forecast AT OR ABOVE
        all_correct_side = all(f["high"] >= threshold for f in forecasts)
        if not all_correct_side:
            below = [f["source"] for f in forecasts if f["high"] < threshold]
            return False, f"Not all above threshold: {below} below"
        # Most aggressive = closest to threshold from above
        most_aggressive = min(f["high"] for f in forecasts)
        margin = most_aggressive - threshold

    if margin < required_margin:
        return False, (
            f"Margin {margin:.1f}{unit} < required {required_margin:.1f}{unit} "
            f"at {hours_remaining:.1f}h to resolution"
        )

    # Position must be at break-even or better (P&L ≥ -5%)
    current_value = position.shares * current_price
    pnl_pct = (current_value - position.cost_basis) / position.cost_basis * 100
    if pnl_pct < -5.0:
        return False, f"Position down {pnl_pct:.1f}% (need ≥-5% for consensus hold)"

    n_sources = len(forecasts)
    return True, (
        f"CONSENSUS HOLD: {n_sources} sources agree, "
        f"margin {margin:.1f}{unit} (need {required_margin:.1f}{unit}), "
        f"P&L {pnl_pct:+.1f}%, {hours_remaining:.1f}h to resolution"
    )


def check_confirmation_topup(
    client, pos: Position, current_price: float,
    hrs_to_res: float, tracker: PositionTracker,
    balance_usdc: float, total_deployed: int,
):
    """
    If METAR confirms our thesis, place a top-up GTC buy order.

    Conditions (ALL must be true):
    1. hours_to_resolution between 1 and 8
    2. position has icao
    3. assess_resolution_confidence returns suggest_topup=True
    4. current market price < max_topup_price
    5. position is profitable
    6. topped_up is False (only once per position)
    7. available capital >= $5
    8. total deployed < 10

    Returns True if top-up was placed, False otherwise.
    """
    if not HAS_METAR:
        return False
    if pos.topped_up:
        return False
    if not getattr(pos, 'icao', ''):
        return False
    if hrs_to_res is None or hrs_to_res < 1 or hrs_to_res > 8:
        return False
    if total_deployed >= 10:
        return False
    if balance_usdc < 5:
        return False

    # Position must be profitable
    value = pos.shares * current_price
    if value <= pos.cost_basis:
        return False

    # Parse threshold from temp_bucket or threshold_temp_f
    threshold_c = None
    threshold_f = getattr(pos, 'threshold_temp_f', 0.0)
    if threshold_f and threshold_f > 0:
        threshold_c = (threshold_f - 32) * 5 / 9 if getattr(pos, 'is_us_market', True) else threshold_f
    if threshold_c is None or threshold_c == 0:
        # Try to infer from order records
        orders = load_open_orders()
        for o in orders:
            if o.get('order_id') == pos.order_id:
                bucket = o.get('temp_bucket', '')
                import re
                m = re.match(r'([\d.]+)°([CF])', bucket)
                if m:
                    val = float(m.group(1))
                    if m.group(2) == 'F':
                        threshold_c = (val - 32) * 5 / 9
                    else:
                        threshold_c = val
                break

    if threshold_c is None or threshold_c == 0:
        return False

    # Assess resolution confidence via METAR
    try:
        confidence = assess_resolution_confidence(
            icao=pos.icao,
            threshold_temp_c=threshold_c,
            side=pos.side,
            hours_to_resolution=hrs_to_res,
        )
    except Exception as e:
        print(f"    METAR confidence check failed: {e}")
        return False

    if not confidence.get('suggest_topup'):
        return False

    max_price = confidence.get('max_topup_price', 0.0)
    if current_price >= max_price:
        return False

    # Calculate top-up size
    available_capital = balance_usdc - 5.0  # keep $5 buffer
    topup_amount = min(pos.cost_basis, available_capital * 0.25, 10.0)
    if topup_amount < 1.0:
        return False

    topup_size = round(topup_amount / current_price, 2)
    if topup_size <= 0:
        return False

    # Place GTC buy order
    try:
        order_args = OrderArgs(
            token_id=str(pos.token_id),
            price=current_price,
            size=topup_size,
            side=BUY,
        )
        signed = client.create_order(order_args)
        resp = client.post_order(signed, orderType=OrderType.GTC)
        order_id = resp.get('orderID', 'N/A')

        now = datetime.now(timezone.utc)
        ttl = now + timedelta(minutes=30)

        order_record = {
            'order_id':     order_id,
            'condition_id': pos.condition_id,
            'event_id':     '',
            'token_id':     str(pos.token_id),
            'market':       pos.market_name,
            'city':         pos.city,
            'date':         getattr(pos, 'market_date', ''),
            'question':     f"TOPUP: {pos.market_name}"[:80],
            'side':         pos.side,
            'price':        current_price,
            'size':         topup_size,
            'amount':       topup_amount,
            'edge':         0.0,
            'conf':         1.0,
            'sources':      ['metar_confirmation'],
            'forecast_temp': '',
            'temp_bucket':  '',
            'icao':         pos.icao,
            'time_placed':  now.isoformat(),
            'ttl_expiry':   ttl.isoformat(),
            'status':       'OPEN',
        }

        all_orders = load_open_orders()
        all_orders.append(order_record)
        save_open_orders(all_orders)

        # Mark position as topped up
        pos.topped_up = True
        tracker.save_state()

        note = confidence.get('confidence_note', '')
        print(f"  🔺 CONFIRMATION TOP-UP: {pos.city} {pos.side} "
              f"${topup_amount:.2f} @ {current_price * 100:.1f}¢  "
              f"order {order_id}")
        print(f"     {note}")

        log(f"\n## Confirmation Top-Up — {now.strftime('%H:%M:%S')}")
        log(f"Market: {pos.market_name}")
        log(f"Side: {pos.side}")
        log(f"METAR: {note}")
        log(f"Top-up: ${topup_amount:.2f} @ {current_price * 100:.1f}¢ ({topup_size:.2f} shares)")
        log(f"Order: {order_id}")

        return True

    except Exception as e:
        print(f"    ❌ Top-up order failed: {e}")
        return False


def monitor_positions(client, tracker: PositionTracker, balance_usdc: float = 0.0):
    """
    Fetch fresh prices for all positions using batch order-book calls,
    then check 4 exit triggers in priority order.
    After exit checks, evaluate METAR confirmation top-ups for held positions.
    """
    positions = tracker.get_active_positions()

    if not positions:
        print("\n[STEP 2] No active positions to monitor")
        return

    print(f"\n{'=' * 70}")
    print(f"STEP 2: POSITION MONITORING ({len(positions)} positions)")
    print(f"{'=' * 70}")

    ts = datetime.now().strftime('%H:%M:%S')
    log(f"\n## Monitor — {ts}")
    log("| Market | Entry | Current | P&L % | Edge | Action |")
    log("|--------|-------|---------|-------|------|--------|")

    # Batch price fetch
    price_map = get_batch_prices(client, positions)

    for pos in positions:
        current_price = price_map.get(str(pos.token_id))

        if current_price is None:
            print(f"  ⚠️  {pos.market_name} — could not fetch price, skipping")
            log(f"| {pos.market_name} | {pos.entry_price * 100:.1f}¢ | N/A | N/A | N/A | SKIP (no price) |")
            continue

        cost    = pos.cost_basis
        value   = pos.shares * current_price
        pnl_pct = (value / cost - 1) * 100
        edge    = recalculate_edge(pos, current_price)

        # --- Priority 0: Consensus Hold (runs BEFORE all other exits) ---
        consensus_hold = False
        consensus_reason = ""
        try:
            market_date_str = getattr(pos, 'market_date', '')
            pos_date = parse_resolution_time(market_date_str)
            pos_is_us = getattr(pos, 'is_us_market', False)
            # Fetch fresh forecasts for this position's city and date
            pos_city = getattr(pos, 'city', '')
            pos_lat = None
            pos_lon = None
            pos_local_source = None
            from weather_arb import WEATHER_CITIES
            for c_name, lat, lon, is_us, local_source in WEATHER_CITIES:
                if c_name.lower() == pos_city.lower() or c_name.title() == pos_city:
                    pos_lat, pos_lon = lat, lon
                    pos_local_source = local_source
                    break

            if pos_lat is not None:
                forecast_date = pos_date.replace(tzinfo=None).date()
                from datetime import date as date_type
                forecast_date_dt = datetime.combine(forecast_date, datetime.min.time())
                ensemble = get_ensemble_forecast(
                    pos_lat, pos_lon, forecast_date_dt,
                    is_us=pos_is_us,
                    local_source=pos_local_source,
                    city_name=pos_city,
                )
                if ensemble:
                    indiv = ensemble.get("individual", [])
                    if indiv:
                        converted = prepare_forecasts_for_market(indiv, is_us_market=pos_is_us)
                        # Parse threshold from Position — stored as threshold_temp_f
                        threshold_raw = getattr(pos, 'threshold_temp_f', None)
                        if threshold_raw and pos_is_us:
                            threshold = threshold_raw  # already in °F
                        elif threshold_raw and not pos_is_us:
                            # threshold_temp_f is stored in °F, convert to °C for non-US
                            threshold = (threshold_raw - 32) * 5/9
                        else:
                            threshold = None

                        if threshold is not None:
                            consensus_hold, consensus_reason = check_consensus_hold(
                                pos, converted, threshold, pos_is_us, current_price
                            )
        except Exception as e:
            consensus_reason = f"Consensus hold check error: {e}"

        if consensus_hold:
            # Log consensus hold — do NOT exit
            action = "CONSENSUS HOLD"
            unit_label = "°F" if getattr(pos, 'is_us_market', False) else "°C"
            ts_now = datetime.now().strftime('%H:%M:%S')
            resolution_time = parse_resolution_time(getattr(pos, 'market_date', ''))
            hours_left = (resolution_time - datetime.now(timezone.utc)).total_seconds() / 3600
            expected_payout = pos.shares * 1.0
            expected_profit = expected_payout - pos.cost_basis
            print(f"  🏁 CONSENSUS HOLD  {pos.market_name}  {current_price * 100:.1f}¢  {pnl_pct:+.1f}%  {hours_left:.1f}h left")
            print(f"     {consensus_reason}")
            log(f"\n## Monitor — {ts_now}")
            log(f"Market: {pos.market_name}")
            log(f"Entry: {pos.side} @ {pos.entry_price * 100:.1f}¢, {pos.shares:.4f} shares, ${pos.cost_basis:.2f} cost")
            log(f"Current: {current_price * 100:.1f}¢ → value ${value:.2f} ({pnl_pct:+.1f}%)")
            log(f"Resolution: {hours_left:.1f}h remaining")
            log(f"Action: 🏁 {consensus_reason}")
            log(f"Expected payout: ${expected_payout:.2f}")
            log(f"Expected profit: ${expected_profit:+.2f} ({expected_profit / pos.cost_basis * 100:+.1f}%)")

            # --- METAR confirmation top-up during consensus hold ---
            if HAS_METAR and not pos.topped_up and getattr(pos, 'icao', ''):
                open_orders = load_open_orders()
                live_orders = [o for o in open_orders if o.get('status') == 'OPEN']
                total_dep = len(positions) + len(live_orders)
                if check_confirmation_topup(
                    client, pos, current_price, hours_left,
                    tracker, balance_usdc, total_dep,
                ):
                    action = "CONSENSUS HOLD + TOPUP"
        else:
            # Fall through to normal exit logic
            trigger, reason = check_exit_triggers(pos, current_price)

            if trigger:
                success = execute_full_exit(client, pos, current_price, reason, tracker)
                action = f"EXIT ({trigger})"
                if success:
                    proceeds = pos.shares * current_price
                    pnl = proceeds - pos.cost_basis
                    log(f"\n## Exit — {datetime.now().strftime('%H:%M:%S')}")
                    log(f"Market: {pos.market_name}")
                    log(f"Side: {pos.side}")
                    log(f"Entry: {pos.entry_price * 100:.1f}¢, {pos.shares:.4f} shares, ${pos.cost_basis:.2f} cost")
                    log(f"Exit: {current_price * 100:.1f}¢, ${proceeds:.2f} proceeds")
                    log(f"P&L: ${pnl:+.2f} ({(pnl / pos.cost_basis * 100):+.1f}%)")
                    log(f"Reason: {reason}")
                    if not consensus_hold and consensus_reason:
                        log(f"Consensus hold blocked: {consensus_reason}")
            else:
                action = "HOLD"
                print(f"  HOLD  {pos.market_name}  {current_price * 100:.1f}¢  {pnl_pct:+.1f}%  edge {edge:.1f}%")

                # --- METAR confirmation top-up check ---
                if HAS_METAR and not pos.topped_up and getattr(pos, 'icao', ''):
                    hrs = hours_to_resolution(getattr(pos, 'market_date', ''))
                    open_orders = load_open_orders()
                    live_orders = [o for o in open_orders if o.get('status') == 'OPEN']
                    total_dep = len(positions) + len(live_orders)
                    if check_confirmation_topup(
                        client, pos, current_price, hrs,
                        tracker, balance_usdc, total_dep,
                    ):
                        action = "HOLD + TOPUP"

        log(f"| {pos.market_name} | {pos.entry_price * 100:.1f}¢ | {current_price * 100:.1f}¢ "
            f"| {pnl_pct:+.1f}% | {edge:.1f}% | {action} |")

    log("")


# ---------------------------------------------------------------------------
# STEP 3: NEW OPPORTUNITY SCAN
# ---------------------------------------------------------------------------

def scan_and_trade(client, balance_usdc: float, tracker: PositionTracker):
    """
    Scan for qualifying weather opportunities and place GTC maker orders.
    Only runs if there is capacity (positions + open_orders < 10) and capital.
    """
    print(f"\n{'=' * 70}")
    print("STEP 3: OPPORTUNITY SCAN")
    print(f"{'=' * 70}")

    # --- Capacity check ---
    positions  = tracker.get_active_positions()
    open_orders = load_open_orders()
    live_orders = [o for o in open_orders if o.get('status') == 'OPEN']
    total_deployed = len(positions) + len(live_orders)
    available_slots = 10 - total_deployed
    max_new_orders = min(available_slots, 3)  # per TRADING_RULES.md

    print(f"\n  Positions  : {len(positions)}")
    print(f"  Open orders: {len(live_orders)}")
    print(f"  Slots free : {available_slots}/10")
    print(f"  Max new    : {max_new_orders}")

    if max_new_orders <= 0:
        print("\n  At capacity — skipping scan")
        return

    # --- Capital check ---
    pos_size = position_size_for(balance_usdc)
    if pos_size == 0:
        print("\n  Balance below $10 hard floor — skipping scan")
        return

    # Available capital = balance minus locked orders minus $5 buffer
    locked_capital = len(live_orders) * pos_size
    available_capital = balance_usdc - locked_capital - 5.0
    max_by_capital = math.floor(available_capital / pos_size) if available_capital > 0 else 0
    max_new_orders = min(max_new_orders, max_by_capital)

    print(f"  Available capital: ${available_capital:.2f}")
    print(f"  Max by capital   : {max_by_capital}")
    print(f"  Final max orders : {max_new_orders}")

    if max_new_orders <= 0:
        print("\n  Insufficient capital — skipping scan")
        return

    # --- Build existing condition ID set (no duplicates) ---
    existing_cids = {p.condition_id for p in positions}
    existing_cids |= {o['condition_id'] for o in live_orders if 'condition_id' in o}

    # Also track event_ids to avoid opposing sides in same event
    existing_event_ids = {getattr(p, 'event_id', '') for p in positions}

    # --- Weather scan ---
    print("\n  Fetching weather events...")
    events = get_weather_events(days_ahead=3)
    qualifying = []

    scan_id = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    scan_ts = datetime.now(timezone.utc).isoformat()

    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue

        event_date = parsed.get('date')
        if isinstance(event_date, str):
            try:
                event_date = datetime.fromisoformat(event_date)
            except Exception:
                continue

        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)

        # Must resolve in >4h and ≤72h
        hours_away = (event_date - datetime.now(timezone.utc)).total_seconds() / 3600
        if hours_away < 4 or hours_away > 72:
            continue

        opps = analyze_weather_event(parsed)

        for opp in opps:
            edge  = opp.get('confidence_adjusted_edge', 0)
            conf  = opp.get('forecast_confidence', 0)
            yes_p = opp.get('market_yes_price', 0)
            no_p  = opp.get('market_no_price', 1)
            sources    = opp.get('forecast_sources', [])
            num_sources = len(sources)
            is_us = 'noaa' in [s.lower() for s in sources]
            has_local = opp.get('local_source') is not None
            action = opp.get('action', '')
            side = "YES" if "YES" in action.upper() else "NO"
            buy_price = yes_p if side == "YES" else no_p

            # --- Entry filter per TRADING_RULES.md ---

            # Confidence floor ≥80% (below this is noise — don't log)
            if conf < 0.80:
                continue

            # Disagrement flag: local and global disagree by >2°C → blocks trade
            if opp.get('local_disagrees', False):
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                "local_global_disagree", False)
                continue

            # Edge threshold: ≥20% for US + non-US with local source; ≥25% without local
            min_edge = 20.0 if (is_us or has_local) else 25.0
            if edge < min_edge:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                f"edge_{edge:.1f}%_below_{min_edge:.0f}%_min", False)
                continue

            # Price range 30–70¢ for the side we're buying
            if not (0.30 <= buy_price <= 0.70):
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                f"price_{buy_price*100:.0f}c_outside_30-70c", False)
                continue

            # Source requirements
            if is_us and num_sources < 3:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                f"us_needs_3_sources_has_{num_sources}", False)
                continue
            if not is_us and num_sources < 2:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                f"non_us_needs_2_sources_has_{num_sources}", False)
                continue

            # Non-US: sources must agree within 1°C
            if not is_us:
                indiv = opp.get('individual_forecasts', [])
                if indiv:
                    temps = [f['high_c'] for f in indiv]
                    if max(temps) - min(temps) > 1.0:
                        log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                        f"source_spread_{max(temps)-min(temps):.1f}C_over_1C", False)
                        continue

            # Liquidity ≥$500
            liquidity = opp.get('liquidity', 0) or 0
            if liquidity < 500:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                f"liquidity_${liquidity:.0f}_below_$500", False)
                continue

            # Resolve condition_id from the event's raw market data
            # The opp's 'slug' matches the market slug in the event's markets list
            opp_slug = opp.get('slug', '')
            condition_id = None
            event_id = event.get('id', '')

            for mkt in event.get('markets', []):
                if mkt.get('slug', '') == opp_slug:
                    condition_id = mkt.get('conditionId')
                    break

            if not condition_id:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                "no_condition_id", False)
                continue

            # Duplicate check
            if condition_id in existing_cids:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                "duplicate_position", False)
                continue

            # Opposing side check: skip if we hold any position in the same event
            if event_id and event_id in existing_event_ids:
                log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                                "opposing_side_held", False)
                continue

            # ✅ Passed all filters
            log_scan_detail(scan_id, scan_ts, opp, side, edge, buy_price, conf,
                            None, True)

            qualifying.append({
                'condition_id': condition_id,
                'event_id': event_id,
                'city': opp.get('city', ''),
                'date': event_date,
                'question': opp.get('market_question', ''),
                'slug': opp_slug,
                'edge': edge,
                'conf': conf,
                'sources': sources,
                'is_us': is_us,
                'side': side,
                'buy_price': buy_price,
                'forecast_prob': opp.get('forecast_prob', 0.5),
                'forecast_temp': opp.get('forecast_temp', ''),
                'temp_bucket': opp.get('temp_bucket', ''),
                'icao': opp.get('icao', ''),
                'individual_forecasts': opp.get('individual_forecasts', []),
                'local_source': opp.get('local_source'),
                'local_disagrees': opp.get('local_disagrees', False),
            })

    qualifying.sort(key=lambda x: x['edge'], reverse=True)
    print(f"\n  Qualifying (≥20% edge, 30–70¢, conf ≥80%, liq ≥$500): {len(qualifying)}")

    ts = datetime.now().strftime('%H:%M:%S')
    orders_placed = 0
    placed_list = []
    skipped_list = []

    for opp in qualifying[:max_new_orders * 3]:  # look-ahead buffer for failures
        if orders_placed >= max_new_orders:
            break

        city = opp['city']
        side = opp['side']
        cid  = opp['condition_id']

        # --- Live balance re-check ---
        bal_now = get_balance(client)
        needed = (orders_placed + 1) * pos_size + 5  # +$5 buffer
        if bal_now['balance_usdc'] < needed:
            skipped_list.append(f"{city}: insufficient balance (${bal_now['balance_usdc']:.2f} < ${needed:.2f})")
            break

        # --- Live price re-validation from CLOB ---
        token_id, fresh_price = get_token_price(client, cid, side)

        if token_id is None or fresh_price is None:
            skipped_list.append(f"{city} {side}: no token data from CLOB")
            continue

        # Price still in 30–70¢ range?
        if not (0.30 <= fresh_price <= 0.70):
            skipped_list.append(f"{city} {side}: live price {fresh_price * 100:.1f}¢ outside 30–70¢")
            continue

        # Re-calculate edge at live price
        fp = opp['forecast_prob']
        if side == 'NO':
            fresh_edge = ((1 - fp) - fresh_price) * 100
        else:
            fresh_edge = (fp - fresh_price) * 100
        fresh_edge = fresh_edge * opp['conf']  # confidence-adjusted

        live_min_edge = 20.0 if (opp.get('is_us') or opp.get('local_source') is not None) else 25.0
        if fresh_edge < live_min_edge:
            skipped_list.append(f"{city} {side}: live edge {fresh_edge:.1f}% < {live_min_edge:.0f}%")
            continue

        # --- Place GTC maker order ---
        size = round(pos_size / fresh_price, 2)
        print(f"\n  → {city} {side} @ {fresh_price * 100:.1f}¢  edge {fresh_edge:.1f}%  conf {opp['conf'] * 100:.0f}%  sources {len(opp['sources'])}")

        try:
            order_args = OrderArgs(
                token_id=str(token_id),
                price=fresh_price,
                size=size,
                side=BUY,
            )
            signed = client.create_order(order_args)
            resp   = client.post_order(signed, orderType=OrderType.GTC)
            order_id = resp.get('orderID', 'N/A')

            now = datetime.now(timezone.utc)
            ttl = now + timedelta(minutes=30)

            order_record = {
                'order_id'    : order_id,
                'condition_id': cid,
                'event_id'    : opp['event_id'],
                'token_id'    : str(token_id),
                'market'      : f"{city} - {opp['date'].strftime('%Y-%m-%d')}",
                'city'        : city,
                'date'        : opp['date'].strftime('%Y-%m-%d'),
                'question'    : opp['question'][:80],
                'side'        : side,
                'price'       : fresh_price,
                'size'        : size,
                'amount'      : pos_size,
                'edge'        : fresh_edge,
                'conf'        : opp['conf'],
                'sources'     : opp['sources'],
                'forecast_temp': opp['forecast_temp'],
                'temp_bucket' : opp['temp_bucket'],
                'icao'        : opp.get('icao', ''),
                'time_placed' : now.isoformat(),
                'ttl_expiry'  : ttl.isoformat(),
                'status'      : 'OPEN',
            }

            all_orders = load_open_orders()
            all_orders.append(order_record)
            save_open_orders(all_orders)
            existing_cids.add(cid)
            existing_event_ids.add(opp['event_id'])
            orders_placed += 1

            print(f"     ✅ order {order_id}  TTL {ttl.strftime('%H:%M UTC')}")
            placed_list.append(f"{city} {side} @ {fresh_price * 100:.1f}¢ (edge {fresh_edge:.1f}%)")

        except Exception as e:
            err = str(e)
            print(f"     ❌ {err[:100]}")
            skipped_list.append(f"{city} {side}: {err[:60]}")
            if "403" in err or "regional" in err.lower():
                print("     🚫 Geo-block detected — stopping")
                break

        time.sleep(0.4)

    # --- Journal scan summary ---
    log(f"\n## Scan — {ts}")
    log(f"Balance: ${balance_usdc:.2f}")
    log(f"Markets scanned: {len(events)}")
    log(f"Qualifying (≥20% edge): {len(qualifying)}")
    log(f"Passed live re-validation: {orders_placed}")
    log(f"Orders placed: {orders_placed}")
    for p in placed_list:
        log(f"  - {p}")
    if skipped_list:
        log(f"Skipped: {len(skipped_list)}")
        for s in skipped_list:
            log(f"  - {s}")
    log("")


# ---------------------------------------------------------------------------
# STEP 4: STATE UPDATE
# ---------------------------------------------------------------------------

def update_state(client, tracker: PositionTracker):
    """Write final state to trading_state.json, positions_state.json, open_orders.json."""
    bal = get_balance(client)
    open_orders = load_open_orders()
    positions = tracker.get_active_positions()

    state = {
        "last_updated"  : datetime.now(timezone.utc).isoformat(),
        "wallet"        : f"{bal['wallet'][:6]}...{bal['wallet'][-4:]}",
        "balance_usdc"  : bal['balance_usdc'],
        "open_orders"   : [o for o in open_orders if o.get('status') == 'OPEN'],
        "positions"     : [vars(p) for p in positions],
        "strategy": {
            "min_edge_pct"             : 20.0,
            "position_size_usd"        : 5.0,
            "max_simultaneous"         : 10,
            "order_type"               : "GTC",
            "ttl_minutes"              : 30,
            "profit_target_pct"        : 30.0,
            "stop_loss_pct"            : 20.0,
            "exit_edge_threshold_pct"  : 10.0,
            "min_resolution_hours"     : 4,
            "price_range"              : "30-70¢",
            "confidence_floor"         : 0.80,
            "min_liquidity_usd"        : 500,
        },
    }

    with open(TRADING_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2, default=str)

    tracker.save_state()

    live_open = [o for o in open_orders if o.get('status') == 'OPEN']

    print(f"\n{'=' * 70}")
    print("STEP 4: STATE UPDATED")
    print(f"  Balance   : ${bal['balance_usdc']:.2f}")
    print(f"  Positions : {len(positions)}")
    print(f"  Open orders: {len(live_open)}")
    print(f"  Journal   : {journal_path()}")
    print(f"  State     : {TRADING_STATE_FILE}")
    print(f"{'=' * 70}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # STEP 1: Startup + sync check
    client, balance_usdc, tracker, open_orders = startup()

    if balance_usdc < 10:
        print("\nStopping — balance below $10 hard floor")
        update_state(client, tracker)
        return

    # STEP 2: Monitor existing positions for exit triggers + METAR confirmation top-ups
    monitor_positions(client, tracker, balance_usdc)

    # STEP 3: Scan for new opportunities (reload balance after any exits)
    fresh_bal = get_balance(client)
    scan_and_trade(client, fresh_bal['balance_usdc'], tracker)

    # STEP 4: Final state update
    update_state(client, tracker)


if __name__ == "__main__":
    import io

    # Tee stdout/stderr to ~/.tinyclaw/logs/trader.log
    LOG_PATH = Path(os.path.expanduser("~/.tinyclaw/logs/trader.log"))
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    class Tee:
        def __init__(self, *streams):
            self.streams = streams
        def write(self, data):
            for s in self.streams:
                try:
                    s.write(data)
                    s.flush()
                except Exception:
                    pass
        def flush(self):
            for s in self.streams:
                try:
                    s.flush()
                except Exception:
                    pass

    log_file = open(LOG_PATH, 'a')
    sys.stdout = Tee(sys.__stdout__, log_file)
    sys.stderr = Tee(sys.__stderr__, log_file)

    while True:
        try:
            main()
        except Exception as e:
            print(f"\n[ERROR] Unhandled exception: {e}")
            import traceback
            traceback.print_exc()
            print("Sleeping 60s before retry...")
            time.sleep(60)
            continue
        next_run = datetime.now(timezone.utc) + timedelta(hours=2)
        print(f"\nSleeping 2h — next scan at {next_run:%Y-%m-%d %H:%M} UTC")
        print("=" * 70)
        time.sleep(7200)
