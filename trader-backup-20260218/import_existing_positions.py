#!/usr/bin/env python3
"""
Import existing Polymarket positions into the position tracker.

Run this once to add your current positions to the monitoring system.
"""

import sys
from pathlib import Path
from datetime import datetime

# Add scripts to path
TRADER_DIR = Path(__file__).parent
SCRIPTS_DIR = TRADER_DIR / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from early_exit_manager import PositionTracker, Position

STATE_FILE = TRADER_DIR / "polymarket-trader" / "positions_state.json"

def import_positions():
    """Import existing positions."""
    print("="*70)
    print("📊 IMPORTING EXISTING POSITIONS")
    print("="*70)
    print()

    tracker = PositionTracker(STATE_FILE)

    # Position 1: Chicago - February 17
    # NO @ 52¢, 5.0 shares, cost $2.60
    # Question: "Will the highest temperature in Chicago be 54°F or higher on February 17?"
    chicago = Position(
        market_name="Chicago - 2026-02-17",
        condition_id="chicago_feb17_temp",  # Placeholder - will need actual condition_id
        token_id="chicago_no_token",  # Placeholder - will need actual token_id
        side="NO",
        entry_price=0.52,  # 52¢
        shares=5.0,
        cost_basis=2.60,
        entry_date=datetime.now().isoformat(),
        order_id="manual_import_chicago",
        original_edge=10.0,  # Estimate - you'll need to recalculate
        threshold_temp_f=54.0,  # From question
        city="Chicago",
        market_date="2026-02-17",
        is_us_market=True,
        forecast_sources="noaa,open-meteo,visualcrossing"
    )

    # Position 2: Miami - February 16
    # YES @ 30¢, 3.4 shares, cost $1.02
    # Question: "Will the highest temperature in Miami be 81°F or below on February 16?"
    miami = Position(
        market_name="Miami - 2026-02-16",
        condition_id="miami_feb16_temp",  # Placeholder - will need actual condition_id
        token_id="miami_yes_token",  # Placeholder - will need actual token_id
        side="YES",
        entry_price=0.30,  # 30¢
        shares=3.4,
        cost_basis=1.02,
        entry_date=datetime.now().isoformat(),
        order_id="manual_import_miami",
        original_edge=10.0,  # Estimate - you'll need to recalculate
        threshold_temp_f=81.0,  # From question
        city="Miami",
        market_date="2026-02-16",
        is_us_market=True,
        forecast_sources="noaa,open-meteo,visualcrossing"
    )

    print("Adding positions to tracker...")
    print()

    print(f"1. {chicago.market_name}")
    print(f"   Side: {chicago.side}")
    print(f"   Entry: {chicago.shares} shares @ {chicago.entry_price*100:.0f}¢")
    print(f"   Cost: ${chicago.cost_basis:.2f}")
    print(f"   Threshold: {chicago.threshold_temp_f:.0f}°F")
    tracker.add_position(chicago)
    print(f"   ✅ Added")
    print()

    print(f"2. {miami.market_name}")
    print(f"   Side: {miami.side}")
    print(f"   Entry: {miami.shares} shares @ {miami.entry_price*100:.0f}¢")
    print(f"   Cost: ${miami.cost_basis:.2f}")
    print(f"   Threshold: {miami.threshold_temp_f:.0f}°F")
    tracker.add_position(miami)
    print(f"   ✅ Added")
    print()

    print("="*70)
    print("✅ POSITIONS IMPORTED")
    print("="*70)
    print()
    print(f"Total active positions: {len(tracker.get_active_positions())}")
    print(f"State file: {STATE_FILE}")
    print()
    print("⚠️  IMPORTANT: You need to update these positions with actual:")
    print("   - condition_id (from Polymarket API)")
    print("   - token_id (from Polymarket API)")
    print()
    print("You can get these by:")
    print("   1. Running the scanner to find these markets")
    print("   2. Or manually querying the Polymarket API")
    print()
    print("Next steps:")
    print("   - Forecast monitoring will check these positions every 4 hours")
    print("   - Early exit will trigger at 2× entry price:")
    print(f"     • Chicago: Exit at {chicago.entry_price * 2 * 100:.0f}¢ (currently 52¢)")
    print(f"     • Miami: Exit at {miami.entry_price * 2 * 100:.0f}¢ (currently 30¢)")
    print()

if __name__ == "__main__":
    import_positions()
