#!/usr/bin/env python3
"""Find moderate-priced opportunities with real edge."""

import sys
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from weather_arb import get_weather_events, parse_weather_event

def main():
    events = get_weather_events(days_ahead=3)
    print(f'Scanning {len(events)} weather events...\n')

    moderate_markets = []

    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue

        # Look at each market in the event
        for market in parsed.get('markets', []):
            yes_price = market.get('yes_price')

            # Filter for moderate prices (30-70¢)
            if yes_price and 0.30 <= yes_price <= 0.70:
                moderate_markets.append({
                    'city': parsed['city'],
                    'date': parsed['date'].strftime('%Y-%m-%d'),
                    'question': market.get('question', ''),
                    'yes_price': yes_price,
                    'no_price': 1 - yes_price,
                    'temp_value': market.get('temp_value'),
                    'is_or_below': market.get('is_or_below'),
                    'is_or_higher': market.get('is_or_higher'),
                    'url': event.get('slug', '')
                })

    print(f'Found {len(moderate_markets)} markets priced 30-70¢:\n')

    for i, m in enumerate(moderate_markets[:15], 1):
        print(f'{i}. {m["city"]} on {m["date"]}')
        print(f'   {m["question"]}')
        print(f'   Market: YES {m["yes_price"]*100:.0f}¢ / NO {m["no_price"]*100:.0f}¢')

        # Show threshold info
        if m['temp_value']:
            threshold_type = "≤" if m['is_or_below'] else "≥" if m['is_or_higher'] else "="
            print(f'   Threshold: {threshold_type}{m["temp_value"]}°')

        print(f'   URL: https://polymarket.com/event/{m["url"]}')
        print()

if __name__ == "__main__":
    main()
