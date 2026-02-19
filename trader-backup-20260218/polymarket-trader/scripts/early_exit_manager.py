#!/usr/bin/env python3
"""
Early Exit Manager for Trading System

Implements cost-basis recovery strategy:
- When position reaches 2x entry price, sell HALF to recover cost
- Let remaining half ride risk-free
- Track outcomes for analysis

Exit Rule:
  Entry: 10 shares @ 30¢ = $3.00 cost
  Trigger: Price hits 60¢ (2x entry)
  Action: Sell 5 shares @ 60¢ = $3.00 (cost recovered)
  Result: 5 shares remaining = pure profit

Monitoring:
  - Check positions every scan cycle
  - Execute exits BEFORE scanning for new trades
  - Use FOK market orders
  - Log everything for future analysis
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
class EarlyExit:
    """Represents an early exit that was executed."""
    market_name: str
    condition_id: str
    token_id: str
    side: str
    entry_price: float
    exit_price: float
    total_shares: float
    shares_sold: float
    shares_remaining: float
    cost_recovered: float
    exit_date: str
    exit_order_id: str
    # Resolution tracking (filled in later)
    resolution_date: Optional[str] = None
    resolution_price: Optional[float] = None  # 0 or 1.00
    profit_from_remaining: Optional[float] = None
    profit_if_held_all: Optional[float] = None
    early_exit_cost_benefit: Optional[float] = None


class PositionTracker:
    """Tracks active positions and their entry prices."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.positions: Dict[str, Position] = {}
        self.exits: List[EarlyExit] = []
        self.load_state()

    def load_state(self):
        """Load positions and exits from state file."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                # Load positions
                for pos_dict in data.get('positions', []):
                    pos = Position(**pos_dict)
                    # Use token_id as unique key
                    self.positions[pos.token_id] = pos

                # Load exits
                for exit_dict in data.get('exits', []):
                    self.exits.append(EarlyExit(**exit_dict))

            except Exception as e:
                print(f"    ⚠️  Error loading position state: {e}")
                self.positions = {}
                self.exits = []

    def save_state(self):
        """Save positions and exits to state file."""
        data = {
            'positions': [asdict(pos) for pos in self.positions.values()],
            'exits': [asdict(exit) for exit in self.exits],
            'last_updated': datetime.now().isoformat()
        }

        with open(self.state_file, 'w') as f:
            json.dump(data, f, indent=2)

    def add_position(self, position: Position):
        """Add a new position to tracking."""
        self.positions[position.token_id] = position
        self.save_state()

    def update_position_after_exit(self, token_id: str, shares_remaining: float):
        """Update position after partial exit."""
        if token_id in self.positions:
            self.positions[token_id].shares = shares_remaining
            # Cost basis stays the same (already paid)
            # But effective entry price changes
            if shares_remaining > 0:
                self.positions[token_id].entry_price = (
                    self.positions[token_id].cost_basis / shares_remaining
                )
            self.save_state()

    def remove_position(self, token_id: str):
        """Remove a position (fully exited or resolved)."""
        if token_id in self.positions:
            del self.positions[token_id]
            self.save_state()

    def record_exit(self, exit: EarlyExit):
        """Record an early exit."""
        self.exits.append(exit)
        self.save_state()

    def update_exit_resolution(self, token_id: str, resolution_price: float):
        """
        Update exit record with final resolution data.

        Args:
            token_id: Token that was exited
            resolution_price: Final settlement price (0 or 1.00)
        """
        for exit in self.exits:
            if exit.token_id == token_id and exit.resolution_date is None:
                exit.resolution_date = datetime.now().isoformat()
                exit.resolution_price = resolution_price

                # Calculate actual profit from remaining shares
                exit.profit_from_remaining = exit.shares_remaining * resolution_price

                # Calculate what profit would have been if we held everything
                total_shares_original = exit.shares_sold + exit.shares_remaining
                exit.profit_if_held_all = (
                    (total_shares_original * resolution_price) - exit.cost_recovered
                )

                # Cost/benefit of early exit
                exit.early_exit_cost_benefit = (
                    exit.profit_from_remaining - exit.profit_if_held_all
                )

                self.save_state()
                break

    def get_active_positions(self) -> List[Position]:
        """Get all active positions."""
        return list(self.positions.values())

    def get_unresolved_exits(self) -> List[EarlyExit]:
        """Get exits that haven't resolved yet."""
        return [e for e in self.exits if e.resolution_date is None]


def check_exit_trigger(position: Position, current_price: float) -> bool:
    """
    Check if position qualifies for early exit.

    Exit trigger: current_price >= 2 * entry_price

    Args:
        position: Position to check
        current_price: Current market price

    Returns:
        True if should exit, False otherwise
    """
    exit_threshold = position.entry_price * 2.0

    # Only exit if we've actually doubled (or more)
    return current_price >= exit_threshold


def execute_early_exit(
    client,
    position: Position,
    current_price: float,
    tracker: PositionTracker
) -> Optional[EarlyExit]:
    """
    Execute early exit for a position.

    Sells HALF the position at current price to recover cost basis.

    Args:
        client: Polymarket CLOB client
        position: Position to exit
        current_price: Current market price
        tracker: Position tracker

    Returns:
        EarlyExit record if successful, None if failed
    """
    try:
        # Calculate shares to sell (half the position)
        shares_to_sell = position.shares / 2.0
        shares_remaining = position.shares - shares_to_sell

        # Expected recovery (should be close to cost basis)
        expected_recovery = shares_to_sell * current_price

        print(f"    🎯 EARLY EXIT TRIGGERED")
        print(f"    Market: {position.market_name}")
        print(f"    Entry: {position.shares:.1f} shares @ {position.entry_price*100:.1f}¢")
        print(f"    Current: {current_price*100:.1f}¢ (≥ 2x entry)")
        print(f"    Selling: {shares_to_sell:.1f} shares")
        print(f"    Expected recovery: ${expected_recovery:.2f} (cost was ${position.cost_basis:.2f})")
        print(f"    Remaining: {shares_remaining:.1f} shares (risk-free)")
        print()

        # Create FOK market order to sell half
        order_args = MarketOrderArgs(
            token_id=str(position.token_id),
            amount=shares_to_sell,  # Number of shares to sell
            side=SELL,
            price=current_price,  # Limit price (won't sell below this)
            order_type=OrderType.FOK  # Fill Or Kill
        )

        # Create and post the order
        signed_order = client.create_market_order(order_args)
        response = client.post_order(signed_order, OrderType.FOK)

        order_id = response.get('orderID', 'N/A')

        print(f"    ✅ EXIT EXECUTED")
        print(f"    Order ID: {order_id}")
        print(f"    Status: HALF position sold, half riding risk-free")
        print()

        # Create exit record
        exit = EarlyExit(
            market_name=position.market_name,
            condition_id=position.condition_id,
            token_id=position.token_id,
            side=position.side,
            entry_price=position.entry_price,
            exit_price=current_price,
            total_shares=position.shares,
            shares_sold=shares_to_sell,
            shares_remaining=shares_remaining,
            cost_recovered=expected_recovery,
            exit_date=datetime.now().isoformat(),
            exit_order_id=order_id
        )

        # Record the exit
        tracker.record_exit(exit)

        # Update position to reflect remaining shares
        tracker.update_position_after_exit(position.token_id, shares_remaining)

        return exit

    except Exception as e:
        print(f"    ❌ Exit failed: {e}")
        return None


def monitor_and_exit(client, tracker: PositionTracker, get_token_price_func) -> List[EarlyExit]:
    """
    Monitor all positions and execute early exits when triggered.

    Args:
        client: Polymarket CLOB client
        tracker: Position tracker
        get_token_price_func: Function to get current token price
            Signature: (client, condition_id, side) -> (token_id, current_price)

    Returns:
        List of exits executed this cycle
    """
    positions = tracker.get_active_positions()

    if not positions:
        return []

    print("="*70)
    print("🔍 CHECKING POSITIONS FOR EARLY EXIT TRIGGERS")
    print("="*70)
    print()

    exits_executed = []

    for position in positions:
        print(f"Position: {position.market_name}")
        print(f"  Entry: {position.shares:.1f} shares @ {position.entry_price*100:.1f}¢ (${position.cost_basis:.2f})")

        # Get current price
        try:
            _, current_price = get_token_price_func(
                client,
                position.condition_id,
                position.side
            )

            if current_price is None:
                print(f"  ⚠️  Could not fetch current price")
                print()
                continue

            print(f"  Current: {current_price*100:.1f}¢")

            # Check exit trigger
            exit_threshold = position.entry_price * 2.0
            print(f"  Exit threshold: {exit_threshold*100:.1f}¢ (2x entry)")

            if check_exit_trigger(position, current_price):
                print(f"  ✅ TRIGGER MET - Executing early exit...")
                print()

                exit_record = execute_early_exit(client, position, current_price, tracker)

                if exit_record:
                    exits_executed.append(exit_record)
            else:
                distance_to_exit = ((exit_threshold / current_price) - 1) * 100
                print(f"  ⏳ Not yet ({distance_to_exit:.1f}% from 2x)")

        except Exception as e:
            print(f"  ❌ Error checking position: {e}")

        print()

    if exits_executed:
        print(f"✅ Executed {len(exits_executed)} early exits")
    else:
        print(f"✅ No positions ready for exit")

    print()

    return exits_executed


def log_early_exits_to_journal(journal_file: Path, exits: List[EarlyExit]):
    """
    Log early exits to daily journal.

    Includes both immediate exit data and placeholder for resolution tracking.
    """
    if not exits:
        return

    with open(journal_file, 'a') as f:
        f.write(f"\n## EARLY EXIT LOG - {datetime.now().strftime('%H:%M:%S')}\n\n")

        for exit in exits:
            f.write(f"### {exit.market_name}\n\n")
            f.write(f"- **Market**: {exit.market_name}\n")
            f.write(f"- **Side**: {exit.side}\n")
            f.write(f"- **Entry price**: {exit.entry_price*100:.1f}¢\n")
            f.write(f"- **Exit price**: {exit.exit_price*100:.1f}¢ (half position)\n")
            f.write(f"- **Total shares originally**: {exit.total_shares:.1f}\n")
            f.write(f"- **Shares sold**: {exit.shares_sold:.1f}\n")
            f.write(f"- **Cost recovered**: ${exit.cost_recovered:.2f}\n")
            f.write(f"- **Remaining shares**: {exit.shares_remaining:.1f} (risk-free)\n")
            f.write(f"- **Exit order ID**: {exit.exit_order_id}\n")
            f.write(f"\n")
            f.write(f"**FINAL RESOLUTION**: _Pending market resolution_\n")
            f.write(f"- Resolution price: _TBD_ (0¢ or 100¢)\n")
            f.write(f"- Profit from remaining shares: _TBD_\n")
            f.write(f"- Profit if we had held everything: _TBD_\n")
            f.write(f"- Early exit cost/benefit: _TBD_\n")
            f.write(f"\n")
            f.write(f"_Will be updated when market resolves_\n")
            f.write(f"\n---\n\n")
