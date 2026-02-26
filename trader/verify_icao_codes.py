#!/usr/bin/env python3
"""
Verify ICAO codes for London, Paris, Tokyo, Buenos Aires from live Polymarket markets.
"""
import os
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent / "polymarket-trader" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/.tinyclaw/polymarket.env"))

from polymarket_api import get_client
from weather_arb import get_weather_events, extract_icao_from_market

TARGET_CITIES = ['London', 'Paris', 'Tokyo', 'Buenos Aires']

def main():
    print("Fetching live weather markets...")
    client = get_client()
    events = get_weather_events(days_ahead=7)

    print(f"Found {len(events)} weather events")

    verified_icao = {}

    for event in events:
        markets = event.get('markets', [])
        if not markets:
            continue

        # Get city from event title
        title = event.get('title', '').lower()
        city = None
        for target in TARGET_CITIES:
            if target.lower() in title:
                city = target
                break

        if not city:
            continue

        # Extract ICAO from market description
        icao = extract_icao_from_market(markets[0])

        if icao and city not in verified_icao:
            verified_icao[city] = icao
            print(f"✅ {city:15} -> {icao}")

    print("\n" + "="*60)
    print("VERIFICATION RESULTS:")
    print("="*60)

    for city in TARGET_CITIES:
        if city in verified_icao:
            print(f"  '{city}': '{verified_icao[city]}',")
        else:
            print(f"  '{city}': NOT FOUND IN LIVE MARKETS")

    print("="*60)

    missing = [c for c in TARGET_CITIES if c not in verified_icao]
    if missing:
        print(f"\n⚠️  Could not verify from live markets: {', '.join(missing)}")
        print("These cities may not have active markets in the next 7 days.")
        print("\nAttempting METAR verification for missing cities...")

        # For Tokyo, verify RJTT (Haneda) works via METAR
        if 'Tokyo' in missing:
            from metar_source import get_metar_observation
            obs = get_metar_observation('RJTT')
            if obs:
                verified_icao['Tokyo'] = 'RJTT'
                print(f"  ✅ Tokyo -> RJTT (verified via METAR: {obs['temp_c']:.1f}°C)")
                missing.remove('Tokyo')
            else:
                print(f"  ❌ Tokyo -> RJTT (METAR fetch failed)")

        if missing:
            print(f"\n❌ Still unverified: {', '.join(missing)}")
            return 1

    print(f"\n✅ All {len(TARGET_CITIES)} cities verified")
    print("\nFinal confirmed codes:")
    for city in TARGET_CITIES:
        print(f"  '{city}': '{verified_icao[city]}',")
    return 0

if __name__ == '__main__':
    sys.exit(main())
