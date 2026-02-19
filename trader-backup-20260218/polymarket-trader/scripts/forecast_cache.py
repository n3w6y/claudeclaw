#!/usr/bin/env python3
"""
Local forecast cache for weather arbitrage.

Updates forecasts periodically and stores locally.
Enables fast odds comparison without API delays.

Usage:
  python3 forecast_cache.py --update          # Update all forecasts
  python3 forecast_cache.py --update --city seoul  # Update one city
  python3 forecast_cache.py --show            # Show cached forecasts
  python3 forecast_cache.py --compare         # Compare cache vs Polymarket odds
"""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
CACHE_DIR = SCRIPT_DIR.parent / "cache"
CACHE_FILE = CACHE_DIR / "forecasts.json"

# Priority cities for NOAA (US) - best accuracy
US_CITIES = [
    ("nyc", 40.7128, -74.0060),
    ("chicago", 41.8781, -87.6298),
    ("miami", 25.7617, -80.1918),
    ("atlanta", 33.7490, -84.3880),
    ("seattle", 47.6062, -122.3321),
    ("dallas", 32.7767, -96.7970),
]

# International cities - Open-Meteo + Visual Crossing only
INTL_CITIES = [
    ("london", 51.5074, -0.1278),
    ("seoul", 37.5665, 126.9780),
    ("tokyo", 35.6762, 139.6503),
    ("buenos aires", -34.6037, -58.3816),
    ("toronto", 43.6532, -79.3832),
    ("ankara", 39.9334, 32.8597),
    ("wellington", -41.2866, 174.7756),
]

def load_cache():
    """Load forecast cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    if CACHE_FILE.exists():
        with open(CACHE_FILE) as f:
            return json.load(f)
    return {"forecasts": {}, "last_updated": None}

def save_cache(cache):
    """Save forecast cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache["last_updated"] = datetime.now().isoformat()
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2, default=str)

def update_forecast(city_name, lat, lon, is_us=False):
    """Fetch and cache forecast for a city."""
    from weather_arb import (
        get_forecast_open_meteo, 
        get_forecast_visual_crossing,
        get_forecast_noaa
    )
    
    today = datetime.now()
    forecasts = {}
    
    for days_ahead in range(0, 3):  # Today + 2 days
        target_date = today + timedelta(days=days_ahead)
        date_key = target_date.strftime("%Y-%m-%d")
        
        sources = []
        temps = []
        
        # Open-Meteo (always)
        om = get_forecast_open_meteo(lat, lon, target_date)
        if om:
            sources.append("open_meteo")
            temps.append(om["high_c"])
        
        # Visual Crossing (always)
        vc = get_forecast_visual_crossing(lat, lon, target_date)
        if vc:
            sources.append("visual_crossing")
            temps.append(vc["high_c"])
        
        # NOAA (US only)
        if is_us:
            noaa = get_forecast_noaa(lat, lon, target_date)
            if noaa:
                sources.append("noaa")
                temps.append(noaa["high_c"])
        
        if temps:
            avg_temp = sum(temps) / len(temps)
            spread = max(temps) - min(temps) if len(temps) > 1 else 0
            confidence = max(0.5, min(0.95, 1.0 - spread / 8))
            
            forecasts[date_key] = {
                "high_c": round(avg_temp, 1),
                "temps_by_source": {s: round(t, 1) for s, t in zip(sources, temps)},
                "sources": sources,
                "spread_c": round(spread, 1),
                "confidence": round(confidence, 2),
                "fetched_at": datetime.now().isoformat()
            }
    
    return forecasts

def update_all(city_filter=None):
    """Update forecasts for all cities."""
    cache = load_cache()
    
    all_cities = [(c, lat, lon, True) for c, lat, lon in US_CITIES] + \
                 [(c, lat, lon, False) for c, lat, lon in INTL_CITIES]
    
    if city_filter:
        all_cities = [(c, lat, lon, us) for c, lat, lon, us in all_cities 
                      if city_filter.lower() in c.lower()]
    
    for city_name, lat, lon, is_us in all_cities:
        print(f"Updating {city_name}...", end=" ", flush=True)
        try:
            forecasts = update_forecast(city_name, lat, lon, is_us)
            cache["forecasts"][city_name] = forecasts
            print(f"✓ ({len(forecasts)} days)")
        except Exception as e:
            print(f"✗ ({e})")
    
    save_cache(cache)
    print(f"\nCache saved: {CACHE_FILE}")

def show_cache():
    """Display cached forecasts."""
    cache = load_cache()
    
    print(f"Last updated: {cache.get('last_updated', 'Never')}\n")
    
    for city, dates in sorted(cache.get("forecasts", {}).items()):
        print(f"📍 {city.title()}")
        for date, data in sorted(dates.items()):
            sources = ", ".join(data.get("sources", []))
            print(f"   {date}: {data['high_c']}°C (±{data['spread_c']}°C) [{sources}]")
        print()

def compare_with_odds():
    """Compare cached forecasts with current Polymarket odds."""
    from weather_arb import get_weather_events, parse_weather_event
    
    cache = load_cache()
    if not cache.get("forecasts"):
        print("No cached forecasts. Run --update first.")
        return
    
    print("Fetching Polymarket weather markets...")
    events = get_weather_events(days_ahead=2)
    print(f"Found {len(events)} markets\n")
    
    opportunities = []
    
    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue
        
        city = parsed["city"].lower()
        date_key = parsed["date"].strftime("%Y-%m-%d")
        
        # Get cached forecast
        city_forecasts = cache.get("forecasts", {}).get(city, {})
        forecast = city_forecasts.get(date_key)
        
        if not forecast:
            continue
        
        forecast_temp = forecast["high_c"]
        confidence = forecast["confidence"]
        
        for market in parsed["markets"]:
            if market["yes_price"] is None:
                continue
            
            temp_value = market["temp_value"]
            if temp_value is None:
                continue
            
            # Convert temp_value to Celsius if market uses Fahrenheit
            market_is_celsius = parsed.get("is_celsius", True)  # Default to Celsius for international
            temp_value_c = temp_value if market_is_celsius else (temp_value - 32) * 5/9
            temp_display = temp_value_c if market_is_celsius else temp_value  # Display in original unit
            
            # Simple probability calc (use Celsius for comparison)
            diff = abs(forecast_temp - temp_value_c)
            if market["is_or_below"]:
                prob = 0.9 if forecast_temp < temp_value_c - 1 else (0.5 if forecast_temp < temp_value_c else 0.1)
            elif market["is_or_higher"]:
                prob = 0.9 if forecast_temp > temp_value_c + 1 else (0.5 if forecast_temp > temp_value_c else 0.1)
            else:
                prob = 0.4 if diff < 0.5 else (0.25 if diff < 1.5 else 0.05)
            
            market_prob = market["yes_price"]
            edge = (prob - market_prob) * 100
            
            if abs(edge) >= 5:
                action = "BUY YES" if edge > 0 else "BUY NO"
                unit_str = "°C" if market_is_celsius else "°F"
                opportunities.append({
                    "city": city.title(),
                    "date": date_key,
                    "bucket": f"{temp_display}{unit_str}",
                    "forecast": f"{forecast_temp}°C",
                    "market_yes": f"{market_prob*100:.0f}¢",
                    "our_prob": f"{prob*100:.0f}%",
                    "edge": abs(edge),
                    "action": action,
                    "confidence": confidence
                })
    
    # Sort by edge
    opportunities.sort(key=lambda x: x["edge"], reverse=True)
    
    print(f"Found {len(opportunities)} opportunities with >5% edge:\n")
    for opp in opportunities[:15]:
        conf_icon = "🟢" if opp["confidence"] > 0.8 else "🟡"
        print(f"{conf_icon} {opp['action']} {opp['city']} {opp['bucket']} @ {opp['edge']:.0f}% edge")
        print(f"   Forecast: {opp['forecast']} | Market: {opp['market_yes']} YES | Our: {opp['our_prob']}")
        print()

def main():
    parser = argparse.ArgumentParser(description="Forecast cache manager")
    parser.add_argument("--update", action="store_true", help="Update forecasts")
    parser.add_argument("--city", type=str, help="Filter to specific city")
    parser.add_argument("--show", action="store_true", help="Show cached forecasts")
    parser.add_argument("--compare", action="store_true", help="Compare with Polymarket odds")
    args = parser.parse_args()
    
    if args.update:
        update_all(args.city)
    elif args.show:
        show_cache()
    elif args.compare:
        compare_with_odds()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
