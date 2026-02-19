#!/usr/bin/env python3
"""
Forecast Monitoring for Active Positions

Position Thesis Monitoring:
- Every 4 hours, re-check all active positions against fresh forecast data
- This is NOT a stop-loss based on price movement
- We exit when the DATA that justified the trade no longer supports it

Logic:
  HOLD: Forecasts unchanged, edge still > 5%
  EXIT: Forecasts shifted, edge dropped below 5% → exit FULL position
  STRENGTHEN: Forecasts shifted in our favor, edge increased

Key principle: We never exit because market price moved against us.
We only exit because our forecast data no longer supports the trade.
Price is noise. Data is signal.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import SELL


@dataclass
class ForecastCheck:
    """Represents a forecast monitoring check for a position."""
    position_token_id: str
    market_name: str
    check_time: str
    entry_price: float
    current_price: float
    original_edge: float
    current_edge: float
    forecast_change_summary: str
    action: str  # HOLD, EXIT, STRENGTHEN
    exit_executed: bool = False
    exit_order_id: Optional[str] = None
    exit_pnl: Optional[float] = None


@dataclass
class ForecastData:
    """Forecast data for a market."""
    source: str
    high_c: float
    forecast_time: str


class ForecastMonitor:
    """Monitors active positions and checks forecast data every 4 hours."""

    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.last_check_time: Optional[datetime] = None
        self.forecast_checks: List[ForecastCheck] = []
        self.load_state()

    def load_state(self):
        """Load monitoring state including last check time."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                # Load last check time
                last_check = data.get('last_forecast_check')
                if last_check:
                    self.last_check_time = datetime.fromisoformat(last_check)

                # Load historical checks
                for check_dict in data.get('forecast_checks', []):
                    self.forecast_checks.append(ForecastCheck(**check_dict))

            except Exception as e:
                print(f"    ⚠️  Error loading forecast monitor state: {e}")

    def save_state(self, full_state_data: dict):
        """Save monitoring state to the main state file."""
        # Add forecast monitoring data to existing state
        full_state_data['last_forecast_check'] = self.last_check_time.isoformat() if self.last_check_time else None
        full_state_data['forecast_checks'] = [asdict(check) for check in self.forecast_checks[-100:]]  # Keep last 100

        with open(self.state_file, 'w') as f:
            json.dump(full_state_data, f, indent=2)

    def should_run_check(self) -> bool:
        """Determine if we should run a forecast check (every 4 hours)."""
        if self.last_check_time is None:
            return True

        time_since_last = datetime.now() - self.last_check_time
        return time_since_last >= timedelta(hours=4)

    def record_check(self, check: ForecastCheck):
        """Record a forecast check."""
        self.forecast_checks.append(check)
        self.last_check_time = datetime.now()


def get_fresh_forecasts_for_market(city: str, date: datetime, is_us_market: bool) -> Tuple[List[ForecastData], float, float]:
    """
    Fetch fresh forecast data for a specific market.

    Args:
        city: City name
        date: Market resolution date
        is_us_market: Whether this is a US market (needs NOAA)

    Returns:
        (forecasts, consensus_temp_c, confidence)
    """
    from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event

    # Fetch all weather events
    events = get_weather_events(days_ahead=7)

    # Find the matching event
    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue

        # Match by city and date
        event_date = parsed.get('date')
        if isinstance(event_date, str):
            event_date = datetime.fromisoformat(event_date)

        if parsed.get('city') == city and event_date.date() == date.date():
            # Analyze to get forecast data
            opps = analyze_weather_event(parsed)

            if opps:
                # Get individual forecasts from first opportunity
                opp = opps[0]
                individual_forecasts = opp.get('individual_forecasts', [])

                forecasts = []
                for fc in individual_forecasts:
                    forecasts.append(ForecastData(
                        source=fc['source'],
                        high_c=fc['high_c'],
                        forecast_time=datetime.now().isoformat()
                    ))

                # Get consensus temperature and confidence
                consensus_temp = opp.get('forecast_high_c', 0)
                confidence = opp.get('forecast_confidence', 0)

                return forecasts, consensus_temp, confidence

    return [], 0, 0


def calculate_edge_from_forecast(forecast_temp_c: float, threshold_temp_f: float, current_price: float, side: str) -> float:
    """
    Calculate edge based on forecast and current market price.

    Args:
        forecast_temp_c: Forecasted temperature in Celsius
        threshold_temp_f: Market threshold in Fahrenheit
        current_price: Current market price (0-1)
        side: Position side (YES or NO)

    Returns:
        Edge as percentage
    """
    # Convert forecast to Fahrenheit
    forecast_temp_f = (forecast_temp_c * 9/5) + 32

    # Determine our probability based on forecast
    if side == "YES":
        # We're betting it WILL be >= threshold
        if forecast_temp_f >= threshold_temp_f:
            our_prob = 0.85  # High confidence YES
        else:
            our_prob = 0.15  # Low confidence YES
    else:
        # We're betting it will NOT be >= threshold
        if forecast_temp_f < threshold_temp_f:
            our_prob = 0.85  # High confidence NO
        else:
            our_prob = 0.15  # Low confidence NO

    # Calculate edge
    edge = abs(our_prob - current_price) * 100

    return edge


def monitor_position_forecast(
    position,
    client,
    get_token_price_func,
    monitor: ForecastMonitor
) -> Optional[ForecastCheck]:
    """
    Monitor a single position's forecast data.

    Args:
        position: Position object from PositionTracker
        client: Polymarket CLOB client
        get_token_price_func: Function to get current price
        monitor: ForecastMonitor instance

    Returns:
        ForecastCheck result or None
    """
    try:
        # Get city and date from position metadata (stored separately)
        city = getattr(position, 'city', '')
        date_str = getattr(position, 'market_date', '')

        if not city or not date_str:
            # Fallback: try parsing market_name
            parts = position.market_name.split(' - ')
            if len(parts) >= 2:
                city = parts[0]
                date_str = parts[1]
            else:
                print(f"  ⚠️  Cannot extract city/date from: {position.market_name}")
                return None

        # Parse date
        try:
            market_date = datetime.fromisoformat(date_str)
        except ValueError:
            print(f"  ⚠️  Invalid date format: {date_str}")
            return None

        # Skip if market is within 2 hours of resolution
        time_to_resolution = market_date - datetime.now()
        if time_to_resolution < timedelta(hours=2):
            print(f"  ⏭️  Skipping {city} - resolves in {time_to_resolution.total_seconds()/3600:.1f}h")
            return None

        print(f"\n  📊 {city} on {date_str}")
        print(f"     Entry: {position.shares:.1f} shares @ {position.entry_price*100:.1f}¢")

        # Get current price
        _, current_price = get_token_price_func(client, position.condition_id, position.side)

        if current_price is None:
            print(f"     ⚠️  Could not fetch current price")
            return None

        print(f"     Current price: {current_price*100:.1f}¢")

        # Get US market flag from position metadata
        is_us_market = getattr(position, 'is_us_market', True)

        # Fetch fresh forecasts
        print(f"     Fetching fresh forecasts...")
        forecasts, consensus_temp, confidence = get_fresh_forecasts_for_market(city, market_date, is_us_market)

        if not forecasts:
            print(f"     ⚠️  No fresh forecast data available")
            return None

        print(f"     Sources: {', '.join([f.source for f in forecasts])} ({len(forecasts)} sources)")
        print(f"     Consensus: {consensus_temp:.1f}°C (confidence: {confidence*100:.0f}%)")

        # Get threshold from position metadata
        threshold_temp_f = getattr(position, 'threshold_temp_f', 80.0)

        # Calculate current edge based on fresh forecasts
        current_edge = calculate_edge_from_forecast(
            consensus_temp,
            threshold_temp_f,
            current_price,
            position.side
        )

        # Get original edge from position
        original_edge = getattr(position, 'original_edge', 10.0)

        print(f"     Original edge: {original_edge:.1f}%")
        print(f"     Current edge: {current_edge:.1f}%")

        # Determine forecast change
        edge_change = current_edge - original_edge

        if abs(edge_change) < 1.0:
            forecast_summary = "Forecasts unchanged"
            action = "HOLD"
        elif edge_change < -5.0:
            forecast_summary = f"Forecasts shifted against us (edge dropped {abs(edge_change):.1f}%)"
            action = "EXIT" if current_edge < 5.0 else "HOLD"
        else:
            forecast_summary = f"Forecasts shifted in our favor (edge increased {edge_change:.1f}%)"
            action = "STRENGTHEN" if current_edge > 15.0 else "HOLD"

        # Override: If edge dropped below 5%, always EXIT
        if current_edge < 5.0:
            action = "EXIT"
            forecast_summary += f" — edge now {current_edge:.1f}% (below 5% threshold)"

        print(f"     {forecast_summary}")
        print(f"     Action: {action}")

        # Create check record
        check = ForecastCheck(
            position_token_id=position.token_id,
            market_name=position.market_name,
            check_time=datetime.now().isoformat(),
            entry_price=position.entry_price,
            current_price=current_price,
            original_edge=original_edge,
            current_edge=current_edge,
            forecast_change_summary=forecast_summary,
            action=action
        )

        return check

    except Exception as e:
        print(f"  ❌ Error monitoring {position.market_name}: {e}")
        return None


def execute_forecast_exit(
    client,
    position,
    current_price: float,
    reason: str,
    tracker
) -> Tuple[bool, Optional[str], Optional[float]]:
    """
    Execute FULL position exit due to forecast change.

    This exits the ENTIRE position, including any "risk-free" half from 2× exits.

    Args:
        client: Polymarket CLOB client
        position: Position to exit
        current_price: Current market price
        reason: Reason for exit
        tracker: PositionTracker instance

    Returns:
        (success, order_id, pnl)
    """
    try:
        print(f"\n    🚨 FORECAST EXIT TRIGGERED")
        print(f"    Reason: {reason}")
        print(f"    Market: {position.market_name}")
        print(f"    Exiting FULL position: {position.shares:.1f} shares @ {current_price*100:.1f}¢")

        # Calculate expected proceeds and P&L
        expected_proceeds = position.shares * current_price
        pnl = expected_proceeds - position.cost_basis

        print(f"    Cost basis: ${position.cost_basis:.2f}")
        print(f"    Expected proceeds: ${expected_proceeds:.2f}")
        print(f"    P&L: ${pnl:+.2f}")
        print()

        # Create FOK market order to sell entire position
        order_args = MarketOrderArgs(
            token_id=str(position.token_id),
            amount=position.shares,
            side=SELL,
            price=current_price,
            order_type=OrderType.FOK
        )

        signed_order = client.create_market_order(order_args)
        response = client.post_order(signed_order, OrderType.FOK)

        order_id = response.get('orderID', 'N/A')

        print(f"    ✅ FULL EXIT EXECUTED")
        print(f"    Order ID: {order_id}")
        print(f"    Status: Position closed, thesis no longer supported by data")
        print()

        # Remove position from tracker
        tracker.remove_position(position.token_id)

        return True, order_id, pnl

    except Exception as e:
        print(f"    ❌ Exit failed: {e}")
        return False, None, None


def monitor_all_positions(
    client,
    tracker,
    get_token_price_func,
    monitor: ForecastMonitor
) -> List[ForecastCheck]:
    """
    Monitor all active positions for forecast changes.

    Returns list of forecast checks performed.
    """
    positions = tracker.get_active_positions()

    if not positions:
        return []

    print("="*70)
    print("🔬 FORECAST MONITORING - Position Thesis Validation")
    print("="*70)
    print()
    print(f"Checking {len(positions)} active positions against fresh forecast data...")
    print()

    checks = []

    for position in positions:
        check = monitor_position_forecast(position, client, get_token_price_func, monitor)

        if check:
            # Execute exit if needed
            if check.action == "EXIT":
                success, order_id, pnl = execute_forecast_exit(
                    client,
                    position,
                    check.current_price,
                    check.forecast_change_summary,
                    tracker
                )

                check.exit_executed = success
                check.exit_order_id = order_id
                check.exit_pnl = pnl

            checks.append(check)
            monitor.record_check(check)

    print()
    print(f"✅ Forecast monitoring complete")
    print(f"   HOLD: {sum(1 for c in checks if c.action == 'HOLD')}")
    print(f"   EXIT: {sum(1 for c in checks if c.action == 'EXIT')}")
    print(f"   STRENGTHEN: {sum(1 for c in checks if c.action == 'STRENGTHEN')}")
    print()

    return checks


def log_forecast_monitoring_to_journal(journal_file: Path, checks: List[ForecastCheck]):
    """
    Log forecast monitoring results to daily journal.

    Format:
    ## POSITION MONITOR — [timestamp]
    | Market | Entry Price | Current Price | Original Edge | Current Edge | Forecast Change | Action |
    """
    if not checks:
        return

    with open(journal_file, 'a') as f:
        f.write(f"\n## POSITION MONITOR — {datetime.now().strftime('%H:%M:%S')}\n\n")

        # Write table header
        f.write("| Market | Entry Price | Current Price | Original Edge | Current Edge | Forecast Change | Action |\n")
        f.write("|--------|-------------|---------------|---------------|--------------|-----------------|--------|\n")

        # Write each check
        for check in checks:
            market = check.market_name
            entry = f"{check.entry_price*100:.1f}¢"
            current = f"{check.current_price*100:.1f}¢"
            orig_edge = f"{check.original_edge:.1f}%"
            curr_edge = f"{check.current_edge:.1f}%"
            change = check.forecast_change_summary[:40]
            action = check.action

            # Add emoji for action
            if action == "HOLD":
                action = "✓ HOLD"
            elif action == "EXIT":
                action = "🚨 EXIT"
            elif action == "STRENGTHEN":
                action = "📈 STRENGTHEN"

            f.write(f"| {market} | {entry} | {current} | {orig_edge} | {curr_edge} | {change} | {action} |\n")

        f.write("\n")

        # Write detailed forecast changes
        exits = [c for c in checks if c.action == "EXIT"]
        strengthens = [c for c in checks if c.action == "STRENGTHEN"]

        if exits or strengthens:
            f.write("### Forecast Details\n\n")

            for check in exits:
                f.write(f"**{check.market_name}** (EXITED):\n")
                f.write(f"- {check.forecast_change_summary}\n")
                if check.exit_executed:
                    f.write(f"- Exit order: {check.exit_order_id}\n")
                    f.write(f"- P&L: ${check.exit_pnl:+.2f}\n")
                f.write("\n")

            for check in strengthens:
                f.write(f"**{check.market_name}** (STRENGTHENED):\n")
                f.write(f"- {check.forecast_change_summary}\n")
                f.write(f"- Potential add opportunity (if criteria met and capacity available)\n")
                f.write("\n")

        f.write("---\n\n")
