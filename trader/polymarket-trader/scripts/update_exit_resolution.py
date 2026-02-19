#!/usr/bin/env python3
"""
Update Early Exit Resolutions

After markets resolve, use this script to update the exit records
with final resolution data and calculate profit/loss metrics.

Usage:
    python update_exit_resolution.py --token-id <TOKEN_ID> --resolution-price <0 or 1.00>

Example:
    # Market resolved YES (price = 1.00)
    python update_exit_resolution.py --token-id 123456 --resolution-price 1.00

    # Market resolved NO (price = 0)
    python update_exit_resolution.py --token-id 123456 --resolution-price 0
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add scripts to path
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from early_exit_manager import PositionTracker

TRADER_DIR = SCRIPT_DIR.parent.parent
STATE_FILE = TRADER_DIR / "polymarket-trader" / "positions_state.json"
JOURNAL_DIR = TRADER_DIR / "polymarket-trader" / "journal"


def update_resolution(token_id: str, resolution_price: float):
    """Update exit resolution and append to journal."""
    tracker = PositionTracker(STATE_FILE)

    # Find the exit
    exit_record = None
    for exit in tracker.exits:
        if exit.token_id == token_id and exit.resolution_date is None:
            exit_record = exit
            break

    if not exit_record:
        print(f"❌ No unresolved exit found for token {token_id}")
        print(f"   Total exits: {len(tracker.exits)}")
        print(f"   Unresolved: {len(tracker.get_unresolved_exits())}")
        return

    print(f"Found exit: {exit_record.market_name}")
    print(f"  Entry: {exit_record.entry_price*100:.1f}¢")
    print(f"  Exit: {exit_record.exit_price*100:.1f}¢")
    print(f"  Shares sold: {exit_record.shares_sold:.1f}")
    print(f"  Shares remaining: {exit_record.shares_remaining:.1f}")
    print(f"  Cost recovered: ${exit_record.cost_recovered:.2f}")
    print()

    # Update with resolution
    tracker.update_exit_resolution(token_id, resolution_price)

    # Re-fetch the updated record
    for exit in tracker.exits:
        if exit.token_id == token_id:
            exit_record = exit
            break

    print(f"✅ Resolution updated")
    print(f"  Resolution price: {exit_record.resolution_price*100:.0f}¢")
    print(f"  Profit from remaining shares: ${exit_record.profit_from_remaining:.2f}")
    print(f"  Profit if held all shares: ${exit_record.profit_if_held_all:.2f}")
    print(f"  Early exit cost/benefit: ${exit_record.early_exit_cost_benefit:.2f}")
    print()

    # Append resolution to journal
    journal_file = JOURNAL_DIR / f"{exit_record.exit_date[:10]}.md"

    with open(journal_file, 'a') as f:
        f.write(f"\n## EARLY EXIT RESOLUTION - {datetime.now().strftime('%H:%M:%S')}\n\n")
        f.write(f"### {exit_record.market_name}\n\n")
        f.write(f"**Original Exit**: {exit_record.exit_date}\n\n")
        f.write(f"**FINAL RESOLUTION**:\n")
        f.write(f"- Resolution price: {exit_record.resolution_price*100:.0f}¢\n")
        f.write(f"- Profit from remaining shares: ${exit_record.profit_from_remaining:.2f}\n")
        f.write(f"- Profit if we had held everything: ${exit_record.profit_if_held_all:.2f}\n")
        f.write(f"- Early exit cost/benefit: ${exit_record.early_exit_cost_benefit:.2f}")

        if exit_record.early_exit_cost_benefit > 0:
            f.write(" ✅ (SAVED MONEY by exiting early)\n")
        elif exit_record.early_exit_cost_benefit < 0:
            f.write(" ❌ (LOST MONEY by exiting early)\n")
        else:
            f.write(" ➖ (NEUTRAL - same outcome)\n")

        f.write(f"\n---\n\n")

    print(f"📝 Appended resolution to {journal_file}")


def list_unresolved():
    """List all unresolved exits."""
    tracker = PositionTracker(STATE_FILE)
    unresolved = tracker.get_unresolved_exits()

    if not unresolved:
        print("✅ No unresolved exits")
        return

    print(f"Found {len(unresolved)} unresolved exits:\n")

    for i, exit in enumerate(unresolved, 1):
        print(f"{i}. {exit.market_name}")
        print(f"   Token ID: {exit.token_id}")
        print(f"   Exit date: {exit.exit_date[:10]}")
        print(f"   Shares remaining: {exit.shares_remaining:.1f}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Update early exit resolutions")
    parser.add_argument("--token-id", help="Token ID of the exited position")
    parser.add_argument("--resolution-price", type=float, choices=[0, 1.0],
                        help="Final resolution price (0 or 1.00)")
    parser.add_argument("--list", action="store_true",
                        help="List all unresolved exits")

    args = parser.parse_args()

    if args.list:
        list_unresolved()
    elif args.token_id and args.resolution_price is not None:
        update_resolution(args.token_id, args.resolution_price)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
