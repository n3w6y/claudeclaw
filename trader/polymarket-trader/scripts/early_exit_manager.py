#!/usr/bin/env python3
"""
Early Exit Manager for Trading System

Implements exit checks per TRADING_RULES.md:
- Profit target: position value ≥ 130% of cost basis → SELL FULL
- Stop loss:     position value ≤ 80% of cost basis  → SELL FULL

Both execute as GTC sell orders (not FOK — thin weather markets won't fill FOK).
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict

from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import SELL


@dataclass
class Position:
    """Represents an active trading position."""
    market_name: str
    condition_id: str
    token_id: str
    side: str  # YES or NO
    entry_price: float  # Price in dollars (0.30 = 30¢)
    shares: float  # Number of shares held
    cost_basis: float  # Total cost paid
    entry_date: str  # ISO format date
    order_id: str  # Original order ID
    # Forecast monitoring fields
    original_edge: float = 10.0  # Edge at entry
    threshold_temp_f: float = 80.0  # Market threshold temperature
    city: str = ""  # City name
    market_date: str = ""  # Market resolution date
    is_us_market: bool = True  # Whether US market
    forecast_sources: str = ""  # Comma-separated source list


@dataclass
class ExitRecord:
    """Represents a completed exit."""
    market_name: str
    condition_id: str
    token_id: str
    side: str
    entry_price: float
    exit_price: float
    shares: float
    cost_basis: float
    proceeds: float
    pnl: float
    exit_date: str
    exit_order_id: str
    reason: str  # profit_target / stop_loss / edge_evaporation / time_exit


class PositionTracker:
    """Tracks active positions and exit history."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.positions: Dict[str, Position] = {}
        self.exits: List[ExitRecord] = []
        self.load_state()

    def load_state(self):
        """Load positions and exits from state file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                for pos_dict in data.get('positions', []):
                    # Strip keys not in Position dataclass to avoid errors
                    valid = {k: v for k, v in pos_dict.items()
                             if k in Position.__dataclass_fields__}
                    pos = Position(**valid)
                    self.positions[pos.token_id] = pos

                for exit_dict in data.get('exits', []):
                    valid = {k: v for k, v in exit_dict.items()
                             if k in ExitRecord.__dataclass_fields__}
                    self.exits.append(ExitRecord(**valid))

            except Exception as e:
                print(f"    ⚠️  Error loading position state: {e}")
                self.positions = {}
                self.exits = []

    def save_state(self):
        """Save positions and exits to state file."""
        # Preserve extra fields (forecast_checks, last_forecast_check) from existing file
        existing = {}
        if self.state_file.exists():
            try:
                with open(self.state_file) as f:
                    existing = json.load(f)
            except Exception:
                pass

        existing['positions'] = [asdict(pos) for pos in self.positions.values()]
        existing['exits'] = [asdict(e) for e in self.exits]
        existing['last_updated'] = datetime.now().isoformat()

        with open(self.state_file, 'w') as f:
            json.dump(existing, f, indent=2)

    def add_position(self, position: Position):
        self.positions[position.token_id] = position
        self.save_state()

    def remove_position(self, token_id: str):
        if token_id in self.positions:
            del self.positions[token_id]
            self.save_state()

    def record_exit(self, exit_record: ExitRecord):
        self.exits.append(exit_record)
        self.save_state()

    def get_active_positions(self) -> List[Position]:
        return list(self.positions.values())


def check_profit_target(position: Position, current_price: float) -> bool:
    """
    Returns True if position value ≥ 130% of cost basis.

    Example: $5.00 cost → exit when value ≥ $6.50
    """
    value = position.shares * current_price
    return value >= position.cost_basis * 1.30


def check_stop_loss(position: Position, current_price: float) -> bool:
    """
    Returns True if position value ≤ 80% of cost basis.

    Example: $5.00 cost → exit when value ≤ $4.00
    """
    value = position.shares * current_price
    return value <= position.cost_basis * 0.80


def execute_full_exit(
    client,
    position: Position,
    current_price: float,
    reason: str,
    tracker: PositionTracker
) -> Optional[ExitRecord]:
    """
    Execute a full position exit via GTC sell order.

    Args:
        client: Polymarket CLOB client
        position: Position to exit
        current_price: Current market price
        reason: Exit reason (profit_target / stop_loss / edge_evaporation / time_exit)
        tracker: PositionTracker instance

    Returns:
        ExitRecord if successful, None if failed
    """
    proceeds = position.shares * current_price
    pnl = proceeds - position.cost_basis

    print(f"\n    🚨 EXIT: {reason.upper()}")
    print(f"    Market: {position.market_name}")
    print(f"    Entry: {position.shares:.4f} shares @ {position.entry_price * 100:.1f}¢  cost ${position.cost_basis:.2f}")
    print(f"    Exit:  @ {current_price * 100:.1f}¢  proceeds ${proceeds:.2f}  P&L ${pnl:+.2f}")

    try:
        order_args = MarketOrderArgs(
            token_id=str(position.token_id),
            amount=position.shares,
            side=SELL,
            price=current_price,
            order_type=OrderType.GTC
        )

        signed_order = client.create_market_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)

        order_id = response.get('orderID', 'N/A')

        print(f"    ✅ GTC SELL PLACED — order {order_id}")

        exit_record = ExitRecord(
            market_name=position.market_name,
            condition_id=position.condition_id,
            token_id=position.token_id,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=current_price,
            shares=position.shares,
            cost_basis=position.cost_basis,
            proceeds=proceeds,
            pnl=pnl,
            exit_date=datetime.now().isoformat(),
            exit_order_id=order_id,
            reason=reason,
        )

        tracker.record_exit(exit_record)
        tracker.remove_position(position.token_id)

        return exit_record

    except Exception as e:
        print(f"    ❌ Exit failed: {e}")
        return None
