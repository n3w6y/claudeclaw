#!/usr/bin/env python3
"""
Position Monitor — 10-minute cron cycle

Checks exit conditions on all open positions and unfilled GTC orders.
Does NOT scan for new opportunities or place new buy orders.
Runs via cron every 10 minutes alongside the main 2-hour trader loop.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ── Path setup ───────────────────────────────────────────────────────────
TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))

from polymarket_api import get_client, cancel_order
from weather_arb import (
    get_ensemble_forecast, prepare_forecasts_for_market, WEATHER_CITIES,
)
from early_exit_manager import PositionTracker, execute_full_exit

from autonomous_trader_v2 import (
    check_exit_triggers, check_consensus_hold, recalculate_edge,
    get_batch_prices, parse_resolution_time, hours_to_resolution,
    POSITIONS_FILE, OPEN_ORDERS_FILE, TRADING_STATE_FILE,
    load_open_orders, save_open_orders,
)

# ── Constants ────────────────────────────────────────────────────────────
LOCK_FILE = Path(os.path.expanduser("~/.tinyclaw/trader.lock"))
LOG_FILE = Path(os.path.expanduser("~/.tinyclaw/logs/position_monitor.log"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


# ── Logging ──────────────────────────────────────────────────────────────
def log(msg: str):
    """Single-line structured log entry."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] POSITION_MONITOR | {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


# ── Lock check ───────────────────────────────────────────────────────────
def is_main_loop_running() -> bool:
    """Check if the main trader loop lock is active (< 10 min old)."""
    if not LOCK_FILE.exists():
        return False
    try:
        age = time.time() - LOCK_FILE.stat().st_mtime
        return age < 600  # < 10 minutes → active; >= 10 min → stale
    except Exception:
        return False


# ── State update ─────────────────────────────────────────────────────────
def update_trading_state(client, tracker: PositionTracker):
    """Refresh trading_state.json after any exits or cancellations."""
    try:
        from polymarket_api import get_balance
        bal = get_balance(client)
        balance = bal.get("balance_usdc", 0)
    except Exception:
        balance = 0

    positions = tracker.get_active_positions()
    open_orders = load_open_orders()

    state = {}
    if TRADING_STATE_FILE.exists():
        try:
            with open(TRADING_STATE_FILE) as f:
                state = json.load(f)
        except Exception:
            pass

    from dataclasses import asdict
    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    state["balance_usdc"] = balance
    state["positions"] = [asdict(p) for p in positions]
    state["open_orders"] = [o for o in open_orders if o.get("status") == "OPEN"]

    with open(TRADING_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ── Position monitoring ──────────────────────────────────────────────────
def monitor_positions(client, tracker: PositionTracker):
    """Check exit conditions on all open positions."""
    positions = tracker.get_active_positions()
    if not positions:
        log("No active positions")
        return

    price_map, wide_spread_tokens = get_batch_prices(client, positions, for_exit=True)

    for pos in positions:
        current_price = price_map.get(str(pos.token_id))
        is_wide_spread = str(pos.token_id) in wide_spread_tokens
        label = f"{pos.market_name}"

        if current_price is None:
            # Force time exit if resolution imminent and no price at all
            ttl = hours_to_resolution(getattr(pos, 'market_date', ''))
            if ttl is not None and ttl < 2:
                log(f"{label} | FORCED_EXIT | reason=no_orderbook_resolution_imminent ({ttl:.1f}h)")
                execute_full_exit(client, pos, 0.01, f"Forced time exit: {ttl:.1f}h, no order book", tracker)
            else:
                log(f"{label} | SKIP | reason=no_price")
            continue

        cost = pos.cost_basis
        value = pos.shares * current_price
        pnl_pct = (value / cost - 1) * 100 if cost > 0 else 0

        # ── Priority 0: Consensus Hold ────────────────────────────
        consensus_hold = False
        try:
            pos_city = getattr(pos, "city", "")
            pos_is_us = getattr(pos, "is_us_market", False)
            market_date_str = getattr(pos, "market_date", "")

            pos_lat = pos_lon = pos_local_source = None
            for c_name, lat, lon, is_us, local_source in WEATHER_CITIES:
                if c_name.lower() == pos_city.lower() or c_name.title() == pos_city:
                    pos_lat, pos_lon = lat, lon
                    pos_local_source = local_source
                    break

            if pos_lat is not None:
                pos_date = parse_resolution_time(market_date_str)
                forecast_date = pos_date.replace(tzinfo=None).date()
                forecast_date_dt = datetime.combine(forecast_date, datetime.min.time())
                ensemble = get_ensemble_forecast(
                    pos_lat, pos_lon, forecast_date_dt,
                    is_us=pos_is_us,
                    local_source=pos_local_source,
                    city_name=pos_city,
                    icao=getattr(pos, "icao", None) or None,
                )
                if ensemble:
                    indiv = ensemble.get("individual", [])
                    if indiv:
                        converted = prepare_forecasts_for_market(
                            indiv, is_us_market=pos_is_us
                        )
                        threshold_raw = getattr(pos, "threshold_temp_f", None)
                        if threshold_raw and pos_is_us:
                            threshold = threshold_raw
                        elif threshold_raw and not pos_is_us:
                            threshold = (threshold_raw - 32) * 5 / 9
                        else:
                            threshold = None

                        if threshold is not None:
                            # Wide spread: use entry_price for P&L check (best_bid is unreliable)
                            ch_price = pos.entry_price if is_wide_spread else current_price
                            consensus_hold, _ = check_consensus_hold(
                                pos, converted, threshold, pos_is_us, ch_price
                            )
        except Exception as e:
            log(f"{label} | WARN | consensus_check_error: {e}")

        if consensus_hold:
            log(f"{label} | HOLD | reason=consensus_hold | pnl={pnl_pct:+.1f}%{' (wide spread)' if is_wide_spread else ''}")
            continue

        # Wide spread guard: don't sell at fake 1¢ bid, let resolution handle it
        if is_wide_spread:
            log(f"{label} | HOLD | reason=wide_spread_no_consensus | bid={current_price*100:.0f}¢")
            continue

        # ── Priorities 1-4: Exit triggers ─────────────────────────
        trigger, reason = check_exit_triggers(pos, current_price)

        if trigger:
            exit_record = execute_full_exit(client, pos, current_price, reason, tracker)
            if exit_record:
                pnl = exit_record.pnl
                log(f"{label} | SELL | reason={trigger} | entry={pos.entry_price:.4f} | exit={current_price:.4f} | pnl=${pnl:+.2f}")
            else:
                log(f"{label} | SELL_FAILED | reason={trigger} | entry={pos.entry_price:.4f}")
        else:
            edge = recalculate_edge(pos, current_price)
            log(f"{label} | HOLD | reason=no_trigger | edge={edge:.1f}% | pnl={pnl_pct:+.1f}%")


# ── GTC order monitoring ─────────────────────────────────────────────────
def monitor_orders(client):
    """Check unfilled GTC orders for cancellation conditions."""
    orders = load_open_orders()
    live_orders = [o for o in orders if o.get("status") == "OPEN"]
    if not live_orders:
        log("No open GTC orders")
        return

    changed = False

    for order in live_orders:
        oid = order.get("order_id", "?")
        market = order.get("question", order.get("market", "?"))
        order_price = order.get("price", 0)
        token_id = order.get("token_id", "")
        label = f"{market} order"

        # ── Cancel if resolution < 2 hours away ──────────────────
        market_date = order.get("date", "")
        hrs = hours_to_resolution(market_date) if market_date else None

        if hrs is not None and hrs < 2:
            result = cancel_order(client, oid)
            if result.get("success"):
                order["status"] = "CANCELLED"
                order["cancellation_reason"] = "RESOLUTION_IMMINENT"
                order["cancellation_time"] = datetime.now(timezone.utc).isoformat()
                changed = True
                log(f"{label} | CANCEL | reason=resolution_imminent ({hrs:.1f}h) | order_px={order_price:.4f}")
            else:
                log(f"{label} | CANCEL_FAILED | reason=resolution_imminent | error={result.get('error', '?')[:80]}")
            continue

        # ── Fetch order book for price checks ─────────────────────
        try:
            ob = client.get_order_book(str(token_id))
            asks = ob.asks or []
            bids = ob.bids or []
            best_ask = float(asks[0].price) if asks else None
            best_bid = float(bids[0].price) if bids else None

            # Wide spread → illiquid, warn but don't cancel
            if best_bid and best_ask:
                spread = best_ask - best_bid
                if spread > 0.40:
                    log(f"{label} | WARN | reason=illiquid_market (spread {spread*100:.0f}¢) | order_px={order_price:.4f}")
                    continue

            # Cancel if market moved >15% against the order
            if best_ask and best_ask > order_price * 1.15:
                result = cancel_order(client, oid)
                if result.get("success"):
                    order["status"] = "CANCELLED"
                    order["cancellation_reason"] = "MARKET_MOVED_AGAINST"
                    order["cancellation_time"] = datetime.now(timezone.utc).isoformat()
                    changed = True
                    log(f"{label} | CANCEL | reason=market_moved_against | order_px={order_price:.4f} | market_px={best_ask:.4f}")
                else:
                    log(f"{label} | CANCEL_FAILED | reason=market_moved | error={result.get('error', '?')[:80]}")
            else:
                log(f"{label} | KEEP | order_px={order_price:.4f} | ask={best_ask or 'N/A'}")

        except Exception as e:
            log(f"{label} | ERROR | {str(e)[:100]}")

    if changed:
        save_open_orders(orders)


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    if is_main_loop_running():
        log("Skipping — main loop lock active")
        return

    log("Starting cycle")

    try:
        client = get_client()
    except Exception as e:
        log(f"Failed to connect: {e}")
        return

    tracker = PositionTracker(POSITIONS_FILE)

    try:
        monitor_positions(client, tracker)
    except Exception as e:
        log(f"Position monitoring error: {e}")

    try:
        monitor_orders(client)
    except Exception as e:
        log(f"Order monitoring error: {e}")

    try:
        update_trading_state(client, tracker)
    except Exception as e:
        log(f"State update error: {e}")

    log("Cycle complete")


if __name__ == "__main__":
    main()
