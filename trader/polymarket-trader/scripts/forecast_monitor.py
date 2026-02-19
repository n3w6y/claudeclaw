#!/usr/bin/env python3
"""
Forecast Monitoring for Active Positions

Position Thesis Monitoring:
- Every 2 hours, re-check all active positions against fresh forecast data
- We exit when the DATA that justified the trade no longer supports it

Logic:
  HOLD: Forecasts unchanged, edge still ≥ 10%
  EXIT: Edge dropped below 10% → exit FULL position
  STRENGTHEN: Edge increased significantly

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
    """Monitors active positions and checks forecast data every 2 hours."""

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

                last_check = data.get('last_forecast_check')
                if last_check:
                    self.last_check_time = datetime.fromisoformat(last_check)

                for check_dict in data.get('forecast_checks', []):
                    valid = {k: v for k, v in check_dict.items()
                             if k in ForecastCheck.__dataclass_fields__}
                    self.forecast_checks.append(ForecastCheck(**valid))

            except Exception as e:
                print(f"    ⚠️  Error loading forecast monitor state: {e}")

    def save_state(self, full_state_data: dict):
        """Save monitoring state to the main state file."""
        full_state_data['last_forecast_check'] = (
            self.last_check_time.isoformat() if self.last_check_time else None
        )
        full_state_data['forecast_checks'] = [
            asdict(c) for c in self.forecast_checks[-100:]
        ]

        with open(self.state_file, 'w') as f:
            json.dump(full_state_data, f, indent=2)

    def should_run_check(self) -> bool:
        """Run every 2 hours per TRADING_RULES.md monitoring schedule."""
        if self.last_check_time is None:
            return True
        return datetime.now() - self.last_check_time >= timedelta(hours=2)

    def record_check(self, check: ForecastCheck):
        self.forecast_checks.append(check)
        self.last_check_time = datetime.now()


def get_fresh_forecasts_for_market(
    city: str, date: datetime, is_us_market: bool
) -> Tuple[List[ForecastData], float, float]:
    """
    Fetch fresh forecast data for a specific market.

    Returns (forecasts, consensus_temp_c, confidence)
    """
    from weather_arb import get_weather_events, parse_weather_event, analyze_weather_event

    events = get_weather_events(days_ahead=7)

    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue

        event_date = parsed.get('date')
        if isinstance(event_date, str):
            event_date = datetime.fromisoformat(event_date)

        if parsed.get('city') == city and event_date.date() == date.date():
            opps = analyze_weather_event(parsed)

            if opps:
                opp = opps[0]
                individual_forecasts = opp.get('individual_forecasts', [])

                forecasts = [
                    ForecastData(
                        source=fc['source'],
                        high_c=fc['high_c'],
                        forecast_time=datetime.now().isoformat()
                    )
                    for fc in individual_forecasts
                ]

                consensus_temp = opp.get('forecast_high_c', 0)
                confidence = opp.get('forecast_confidence', 0)

                return forecasts, consensus_temp, confidence

    return [], 0, 0


def calculate_current_edge(
    forecast_temp_c: float,
    threshold_temp_f: float,
    confidence: float,
    current_price: float,
    side: str
) -> float:
    """
    Calculate edge using weather_arb.calculate_probability (proper model).

    Args:
        forecast_temp_c: Forecasted temperature in Celsius
        threshold_temp_f: Market threshold in Fahrenheit
        confidence: Forecast confidence (0-1)
        current_price: Current market price (0-1)
        side: Position side (YES or NO)

    Returns:
        Edge as percentage
    """
    from weather_arb import calculate_probability

    # Convert threshold to Celsius for calculate_probability
    threshold_temp_c = (threshold_temp_f - 32) * 5 / 9

    # Determine the market structure: is it "≥ threshold" or "≤ threshold"?
    # is_or_higher = market asks "will temp be >= threshold" (YES side)
    # is_or_below  = market asks "will temp be <= threshold"
    if side == "YES":
        # YES side of "≥ threshold" market
        prob = calculate_probability(
            forecast_temp_c=forecast_temp_c,
            temp_value=threshold_temp_c,
            is_or_below=False,
            is_or_higher=True,
            confidence=confidence
        )
    else:
        # NO side of "≥ threshold" market = probability it will NOT be >= threshold
        prob = 1.0 - calculate_probability(
            forecast_temp_c=forecast_temp_c,
            temp_value=threshold_temp_c,
            is_or_below=False,
            is_or_higher=True,
            confidence=confidence
        )

    return abs(prob - current_price) * 100


def monitor_position_forecast(
    position,
    client,
    get_token_price_func,
    monitor: ForecastMonitor
) -> Optional[ForecastCheck]:
    """
    Monitor a single position's forecast data.

    Returns ForecastCheck result or None.
    """
    try:
        city = getattr(position, 'city', '')
        date_str = getattr(position, 'market_date', '')

        if not city or not date_str:
            parts = position.market_name.split(' - ')
            if len(parts) >= 2:
                city = parts[0]
                date_str = parts[1]
            else:
                print(f"  ⚠️  Cannot extract city/date from: {position.market_name}")
                return None

        try:
            market_date = datetime.fromisoformat(date_str)
        except ValueError:
            print(f"  ⚠️  Invalid date format: {date_str}")
            return None

        # Skip if market resolves within 2 hours
        time_to_resolution = market_date - datetime.now()
        if time_to_resolution < timedelta(hours=2):
            print(f"  ⏭️  Skipping {city} — resolves in {time_to_resolution.total_seconds() / 3600:.1f}h")
            return None

        print(f"\n  📊 {city} on {date_str}")
        print(f"     Entry: {position.shares:.4f} shares @ {position.entry_price * 100:.1f}¢")

        _, current_price = get_token_price_func(client, position.condition_id, position.side)

        if current_price is None:
            print(f"     ⚠️  Could not fetch current price")
            return None

        print(f"     Current price: {current_price * 100:.1f}¢")

        is_us_market = getattr(position, 'is_us_market', True)

        print(f"     Fetching fresh forecasts...")
        forecasts, consensus_temp, confidence = get_fresh_forecasts_for_market(
            city, market_date, is_us_market
        )

        if not forecasts:
            print(f"     ⚠️  No fresh forecast data available")
            return None

        print(f"     Sources: {', '.join(f.source for f in forecasts)} ({len(forecasts)} sources)")
        print(f"     Consensus: {consensus_temp:.1f}°C  confidence: {confidence * 100:.0f}%")

        threshold_temp_f = getattr(position, 'threshold_temp_f', 80.0)
        original_edge = getattr(position, 'original_edge', 10.0)

        # Use proper calculate_probability from weather_arb
        current_edge = calculate_current_edge(
            forecast_temp_c=consensus_temp,
            threshold_temp_f=threshold_temp_f,
            confidence=confidence,
            current_price=current_price,
            side=position.side
        )

        print(f"     Original edge: {original_edge:.1f}%")
        print(f"     Current edge:  {current_edge:.1f}%")

        edge_change = current_edge - original_edge

        if abs(edge_change) < 1.0:
            forecast_summary = "Forecasts unchanged"
        elif edge_change < 0:
            forecast_summary = f"Forecasts shifted against us (edge dropped {abs(edge_change):.1f}%)"
        else:
            forecast_summary = f"Forecasts shifted in our favour (edge increased {edge_change:.1f}%)"

        # EXIT threshold: edge < 10% per TRADING_RULES.md
        if current_edge < 10.0:
            action = "EXIT"
            forecast_summary += f" — edge now {current_edge:.1f}% (below 10% threshold)"
        elif current_edge > 15.0 and edge_change > 5.0:
            action = "STRENGTHEN"
        else:
            action = "HOLD"

        print(f"     {forecast_summary}")
        print(f"     Action: {action}")

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
    Execute FULL position exit due to forecast edge evaporation.

    Uses GTC (not FOK) per TRADING_RULES.md — thin weather markets won't fill FOK.

    Returns (success, order_id, pnl)
    """
    try:
        print(f"\n    🚨 FORECAST EXIT")
        print(f"    Reason: {reason}")
        print(f"    Market: {position.market_name}")
        print(f"    Exiting: {position.shares:.4f} shares @ {current_price * 100:.1f}¢")

        proceeds = position.shares * current_price
        pnl = proceeds - position.cost_basis

        print(f"    Cost: ${position.cost_basis:.2f}  Proceeds: ${proceeds:.2f}  P&L: ${pnl:+.2f}")

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

    print("=" * 70)
    print("FORECAST MONITORING — Position Thesis Validation")
    print("=" * 70)
    print(f"\nChecking {len(positions)} positions against fresh forecasts...")

    checks = []

    for position in positions:
        check = monitor_position_forecast(position, client, get_token_price_func, monitor)

        if check:
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

    print(f"\n✅ Forecast monitoring complete")
    print(f"   HOLD:       {sum(1 for c in checks if c.action == 'HOLD')}")
    print(f"   EXIT:       {sum(1 for c in checks if c.action == 'EXIT')}")
    print(f"   STRENGTHEN: {sum(1 for c in checks if c.action == 'STRENGTHEN')}")

    return checks


def log_forecast_monitoring_to_journal(journal_file: Path, checks: List[ForecastCheck]):
    """
    Log forecast monitoring results to daily journal per TRADING_RULES.md format.

    ## Monitor — HH:MM:SS
    | Market | Entry | Current | P&L % | Edge | Action |
    """
    if not checks:
        return

    with open(journal_file, 'a') as f:
        f.write(f"\n## Monitor — {datetime.now().strftime('%H:%M:%S')}\n\n")
        f.write("| Market | Entry | Current | P&L % | Edge | Action |\n")
        f.write("|--------|-------|---------|-------|------|--------|\n")

        for c in checks:
            if c.entry_price > 0:
                pnl_pct = (c.current_price / c.entry_price - 1) * 100
            else:
                pnl_pct = 0.0

            action_str = {
                "HOLD": "HOLD",
                "EXIT": "EXIT",
                "STRENGTHEN": "STRENGTHEN",
            }.get(c.action, c.action)

            f.write(
                f"| {c.market_name} | {c.entry_price * 100:.1f}¢ "
                f"| {c.current_price * 100:.1f}¢ "
                f"| {pnl_pct:+.1f}% "
                f"| {c.current_edge:.1f}% "
                f"| {action_str} |\n"
            )

        f.write("\n")

        exits = [c for c in checks if c.action == "EXIT"]
        if exits:
            f.write("### Exits\n\n")
            for c in exits:
                f.write(f"**{c.market_name}**\n")
                f.write(f"- {c.forecast_change_summary}\n")
                if c.exit_executed:
                    f.write(f"- Order: {c.exit_order_id}\n")
                    f.write(f"- P&L: ${c.exit_pnl:+.2f}\n")
                f.write("\n")

        f.write("---\n\n")
