#!/usr/bin/env python3
"""
Risk management module for Polymarket trading.

Implements tier-based max bet system and position limits.
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

# Config paths
CONFIG_DIR = Path(__file__).parent.parent / "config"
STATE_FILE = CONFIG_DIR / "trading_state.json"
JOURNAL_DIR = Path(__file__).parent.parent / "journal"

# Tier-based max bet table: 5% of the ceiling of the $100 range
# Balance $0-99 → ceil is $100, 5% = $5
# Balance $100-199 → ceil is $200, 5% = $10
# Balance $200-299 → ceil is $300, 5% = $15, etc.
BET_TIERS = [
    (0,    100,  5),
    (100,  200,  10),
    (200,  300,  15),
    (300,  400,  20),
    (400,  500,  25),
    (500,  600,  30),
    (600,  700,  35),
    (700,  800,  40),
    (800,  900,  45),
    (900,  1000, 50),
    (1000, float('inf'), 55),
]

# Daily trade limits by max bet tier
DAILY_LIMITS = {
    5: 10,
    10: 20,
    15: 30,
    20: 40,
    25: 50,
    30: 60,
    35: 70,
    40: 80,
    45: 90,
    50: 100,
    55: 110,
}

# Hard limits
MAX_TRADES_PER_HOUR = 2
MAX_DAILY_LOSS = 100
SESSION_LOSS_STOP = 50
MAX_TRADES_PER_SESSION = 10  # Live trial: stop after 10 trades
MAX_WEATHER_MARKETS_PER_DAY = 3


def load_state():
    """Load trading state from file."""
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "balance": 10000.0,  # Starting $SIM
        "high_water_mark": 10000.0,
        "session_pnl": 0.0,
        "daily_pnl": 0.0,
        "daily_trades": 0,
        "hourly_trades": [],
        "weather_trades_today": 0,
        "last_reset_date": datetime.utcnow().strftime("%Y-%m-%d"),
        "trades": [],
    }


def save_state(state):
    """Save trading state to file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_max_bet(balance: float) -> float:
    """Calculate max bet based on current balance tier."""
    for low, high, max_bet in BET_TIERS:
        if low <= balance < high:
            return max_bet
    return BET_TIERS[-1][2]  # Fallback to highest tier


def get_daily_limit(balance: float) -> float:
    """Get daily loss limit based on max bet tier."""
    max_bet = get_max_bet(balance)
    return DAILY_LIMITS.get(max_bet, 100)


def check_can_trade(state: dict, amount: float, market_type: str = "general") -> dict:
    """
    Check if a trade is allowed based on risk rules.
    
    Returns:
        dict with keys:
        - allowed: bool
        - reason: str (if not allowed)
        - max_allowed: float (suggested max bet)
    """
    now = datetime.utcnow()
    today = now.strftime("%Y-%m-%d")
    
    # Reset daily counters if new day
    if state.get("last_reset_date") != today:
        state["daily_pnl"] = 0.0
        state["daily_trades"] = 0
        state["weather_trades_today"] = 0
        state["hourly_trades"] = []
        state["session_pnl"] = 0.0
        state["last_reset_date"] = today
        save_state(state)
    
    balance = state.get("balance", 0)
    max_bet = get_max_bet(balance)
    daily_limit = get_daily_limit(balance)
    
    # Check 1: Balance > 0
    if balance <= 0:
        return {"allowed": False, "reason": "Balance is zero", "max_allowed": 0}
    
    # Check 2: Amount within max bet
    if amount > max_bet:
        return {
            "allowed": False,
            "reason": f"Amount ${amount} exceeds max bet ${max_bet} for balance ${balance:.2f}",
            "max_allowed": max_bet
        }
    
    # Check 3: Daily loss limit
    if abs(state.get("daily_pnl", 0)) >= MAX_DAILY_LOSS:
        return {
            "allowed": False,
            "reason": f"Daily loss limit ${MAX_DAILY_LOSS} reached",
            "max_allowed": 0
        }
    
    # Check 4: Session loss limit
    if abs(state.get("session_pnl", 0)) >= SESSION_LOSS_STOP:
        return {
            "allowed": False,
            "reason": f"Session loss ${SESSION_LOSS_STOP} reached. Stop trading.",
            "max_allowed": 0
        }
    
    # Check 5: Hourly trade limit
    hour_ago = (now - timedelta(hours=1)).isoformat()
    recent_trades = [t for t in state.get("hourly_trades", []) if t > hour_ago]
    state["hourly_trades"] = recent_trades  # Clean up old entries
    
    if len(recent_trades) >= MAX_TRADES_PER_HOUR:
        return {
            "allowed": False,
            "reason": f"Max {MAX_TRADES_PER_HOUR} trades per hour reached",
            "max_allowed": max_bet
        }
    
    # Check 6: Weather-specific limit
    
    # Check 7: Session trading limit
    if state.get("daily_trades", 0) >= MAX_TRADES_PER_SESSION:
        return {
            "allowed": False,
            "reason": f"Max {MAX_TRADES_PER_SESSION} trades per session reached",
            "max_allowed": max_bet
        }
    
    if market_type == "weather":
        if state.get("weather_trades_today", 0) >= MAX_WEATHER_MARKETS_PER_DAY:
            return {
                "allowed": False,
                "reason": f"Max {MAX_WEATHER_MARKETS_PER_DAY} weather trades per day reached",
                "max_allowed": max_bet
            }
    
    return {"allowed": True, "reason": None, "max_allowed": max_bet}


def record_trade(state: dict, trade: dict) -> dict:
    """
    Record a trade and update state.
    
    trade should have:
    - market_id: str
    - market_type: str (weather, copytrading, etc.)
    - side: yes/no
    - amount: float
    - price: float
    - reasoning: str
    - timestamp: str (ISO format)
    """
    now = datetime.utcnow()
    
    # Update hourly trades
    state.setdefault("hourly_trades", []).append(now.isoformat())
    
    # Update daily trades
    state["daily_trades"] = state.get("daily_trades", 0) + 1
    
    # Update weather-specific counter
    if trade.get("market_type") == "weather":
        state["weather_trades_today"] = state.get("weather_trades_today", 0) + 1
    
    # Add to trade history
    trade["timestamp"] = now.isoformat()
    state.setdefault("trades", []).append(trade)
    
    # Update balance (subtract cost)
    state["balance"] = state.get("balance", 0) - trade.get("amount", 0)
    
    save_state(state)
    
    # Log to journal
    log_trade_to_journal(trade)
    
    return state


def record_outcome(state: dict, trade_id: str, pnl: float) -> dict:
    """Record the outcome of a resolved trade."""
    state["balance"] = state.get("balance", 0) + pnl
    state["daily_pnl"] = state.get("daily_pnl", 0) + pnl
    state["session_pnl"] = state.get("session_pnl", 0) + pnl
    
    # Update high water mark
    if state["balance"] > state.get("high_water_mark", 0):
        state["high_water_mark"] = state["balance"]
    
    save_state(state)
    return state


def log_trade_to_journal(trade: dict):
    """Append trade to daily journal."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    
    today = datetime.utcnow().strftime("%Y-%m-%d")
    journal_file = JOURNAL_DIR / f"{today}.md"
    
    entry = f"""
### Trade @ {trade.get('timestamp', 'unknown')[:19]}
- **Market:** {trade.get('question', trade.get('market_id', 'Unknown'))}
- **Side:** {trade.get('side', 'unknown').upper()}
- **Amount:** ${trade.get('amount', 0):.2f}
- **Price:** {trade.get('price', 0)*100:.1f}%
- **Type:** {trade.get('market_type', 'general')}
- **Thesis:** {trade.get('reasoning', 'No reasoning provided')}
- **Outcome:** *pending*

"""
    
    # Create or append to journal
    if not journal_file.exists():
        header = f"""# Trade Journal - {today}

## Summary
*Updated at end of day*

---

## Trades

"""
        with open(journal_file, "w") as f:
            f.write(header)
    
    with open(journal_file, "a") as f:
        f.write(entry)


def get_status(state: dict = None) -> dict:
    """Get current trading status."""
    if state is None:
        state = load_state()
    
    balance = state.get("balance", 0)
    max_bet = get_max_bet(balance)
    daily_limit = get_daily_limit(balance)
    
    return {
        "balance": balance,
        "max_bet": max_bet,
        "daily_limit": daily_limit,
        "daily_pnl": state.get("daily_pnl", 0),
        "session_pnl": state.get("session_pnl", 0),
        "daily_trades": state.get("daily_trades", 0),
        "weather_trades_today": state.get("weather_trades_today", 0),
        "high_water_mark": state.get("high_water_mark", 0),
        "can_trade": check_can_trade(state, max_bet)["allowed"],
    }


if __name__ == "__main__":
    # CLI usage
    import sys
    
    state = load_state()
    status = get_status(state)
    
    print("📊 Trading Status")
    print(f"   Balance: ${status['balance']:.2f}")
    print(f"   Max bet: ${status['max_bet']}")
    print(f"   Daily limit: ${status['daily_limit']}")
    print(f"   Daily PnL: ${status['daily_pnl']:+.2f}")
    print(f"   Session PnL: ${status['session_pnl']:+.2f}")
    print(f"   Trades today: {status['daily_trades']}")
    print(f"   Weather trades: {status['weather_trades_today']}/{MAX_WEATHER_MARKETS_PER_DAY}")
    print(f"   High water mark: ${status['high_water_mark']:.2f}")
    print(f"   Can trade: {'✅ Yes' if status['can_trade'] else '❌ No'}")
