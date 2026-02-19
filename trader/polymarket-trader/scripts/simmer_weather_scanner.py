#!/usr/bin/env python3
"""
Simmer-integrated weather market scanner.

Uses Simmer's API to fetch weather markets and cross-reference with NOAA forecasts.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

# Simmer config path (2 levels up from scripts/)
CONFIG_FILE = Path(__file__).parent.parent / "config/simmer_config.json"

def load_config():
    """Load Simmer config."""
    with open(CONFIG_FILE) as f:
        return json.load(f)

def fetch_simmer_markets(api_key, tags="weather", limit=100):
    """Fetch weather markets from Simmer API."""
    url = f"https://api.simmer.markets/api/sdk/markets?tags={tags}&limit={limit}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        if e.code == 401:
            print("Invalid API key. Check config/simmer_config.json")
        return None
    except Exception as e:
        print(f"Error: {e}")
        return None

def fetch_noaa_forecast(lat, lon, date):
    """Fetch NOAA forecast (simplified - use Open-Meteo as proxy)."""
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&start_date={date}&end_date={date}"
    
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except:
        return None

# City coordinates (simplified for demo)
CITY_COORDS = {
    "new york city": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "miami": (25.7617, -80.1918),
    "atlanta": (33.7490, -84.3880),
    "dallas": (32.7767, -96.7970),
    "seattle": (47.6062, -122.3321),
}

def parse_weather_question(question):
    """
    Parse weather market question.
    Returns: (city, temp_range, temp_unit) or None
    """
    # Example: "Will the highest temperature in Miami be between 70-71°F on February 9?"
    import re
    
    # Find city
    city = None
    for c in CITY_COORDS.keys():
        if c in question.lower():
            city = c
            break
    
    if not city:
        return None
    
    # Find temp range: "between X-Y°F" or "X or higher"
    temp_range = None
    temp_unit = "F"
    
    range_match = re.search(r'between\s+(\d+)-(\d+)\s*°', question.lower())
    if range_match:
        temp_range = (int(range_match.group(1)), int(range_match.group(2)))
    else:
        # Try "X or higher" or "X or lower"
        higher_match = re.search(r'(\d+)\s*°.*higher', question.lower())
        if higher_match:
            temp = int(higher_match.group(1))
            temp_range = (temp, 150)  # Up to 150°F
        else:
            lower_match = re.search(r'(\d+)\s*°.*lower', question.lower())
            if lower_match:
                temp = int(lower_match.group(1))
                temp_range = (-100, temp)
    
    if not temp_range:
        return None
    
    return {
        "city": city,
        "coords": CITY_COORDS[city],
        "temp_range": temp_range,
    }

def analyze_weather_market(market):
    """Analyze a weather market for opportunity."""
    question = market.get("question", "")
    parsed = parse_weather_question(question)
    
    if not parsed:
        return None
    
    city = parsed["city"]
    temp_range = parsed["temp_range"]
    market_prob = market.get("current_probability", 0)
    
    # Get forecast for city
    forecast = fetch_noaa_forecast(parsed["coords"][0], parsed["coords"][1], "2026-02-08")
    
    if not forecast:
        return None
    
    daily = forecast.get("daily", {})
    temp_f = daily.get("temperature_2m_max", [0])[0]
    temp_c = (temp_f - 32) * 5/9
    
    # Calculate probability that temp falls in range
    temp_low, temp_high = temp_range
    forecast_prob = 0.0
    
    if temp_low <= temp_f <= temp_high:
        forecast_prob = 0.80  # Forecast is in range, high confidence
    elif temp_f < temp_low:
        # Temp too low
        diff = temp_low - temp_f
        if diff <= 2:
            forecast_prob = 0.20  # Close
        elif diff <= 4:
            forecast_prob = 0.05
        else:
            forecast_prob = 0.01
    else:
        # Temp too high
        diff = temp_f - temp_high
        if diff <= 2:
            forecast_prob = 0.20
        elif diff <= 4:
            forecast_prob = 0.05
        else:
            forecast_prob = 0.01
    
    # Calculate edge
    edge = (forecast_prob - market_prob) * 100
    
    return {
        "city": city.title(),
        "temp_range": f"{temp_low}-{temp_high}°F",
        "market_question": question,
        "market_prob_pct": market_prob * 100,
        "forecast_temp_f": temp_f,
        "forecast_prob_pct": forecast_prob * 100,
        "edge_pct": edge,
        "market_id": market.get("id"),
        "market_url": market.get("url"),
        "action": "BUY YES" if edge > 0 else "BUY NO" if edge < 0 else "HOLD",
    }

def main():
    parser = argparse.ArgumentParser(description="Simmer weather market scanner")
    parser.add_argument("--min-edge", type=float, default=5.0, help="Minimum edge % (default: 5.0)")
    parser.add_argument("--limit", type=int, default=50, help="Max markets to check")
    args = parser.parse_args()
    
    print("🔮 Simmer Weather Scanner")
    print(f"   Using Simmer API with NOAA forecasts\n")
    
    config = load_config()
    api_key = config.get("api_key")
    
    if not api_key:
        print("❌ No API key found in config/simmer_config.json")
        print("   Run: curl -X POST https://api.simmer.markets/api/sdk/agents/register ...")
        return
    
    # Fetch markets
    markets_data = fetch_simmer_markets(api_key, tags="weather", limit=args.limit)
    
    if not markets_data:
        print("❌ Failed to fetch markets")
        return
    
    markets = markets_data.get("markets", [])
    print(f"   Found {len(markets)} weather markets on Simmer\n")
    
    opportunities = []
    
    for market in markets:
        analysis = analyze_weather_market(market)
        if analysis:
            edge = analysis["edge_pct"]
            if edge >= args.min_edge:
                opportunities.append(analysis)
    
    opportunities.sort(key=lambda x: x["edge_pct"], reverse=True)
    
    # Output
    print(f"   Analyzed {len(markets)} markets")
    print(f"   Found {len(opportunities)} opportunities ≥{args.min_edge}% edge\n")
    
    if opportunities:
        for opp in opportunities[:10]:
            print(f"{'='*60}")
            print(f"🎯 {opp['action']} — {opp['edge_pct']:.1f}% edge")
            print(f"   {opp['market_question'][:55]}...")
            print(f"   📍 {opp['city']}")
            print(f"   🎯 Market: {opp['temp_range']} @ {opp['market_prob_pct']:.1f}%")
            print(f"   🌡️  Forecast: {opp['forecast_temp_f']}°F ({opp['forecast_prob_pct']:.0f}% prob)")
            print(f"   🔗 {opp['market_url']}")
            print()
    else:
        print("   No opportunities found.")
    
    print("\n💡 Tips:")
    print("   - Run again with --min-edge 2 for more results")
    print("   - Check forecast accuracy before trading")

if __name__ == "__main__":
    main()
