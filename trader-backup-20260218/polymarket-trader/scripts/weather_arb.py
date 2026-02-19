#!/usr/bin/env python3
"""
Weather arbitrage scanner for Polymarket.

Compares Polymarket weather markets to ensemble meteorological forecasts.
Uses three sources for triangulation:
  - Open-Meteo (free, global)
  - Visual Crossing (high accuracy, requires API key)
  - NOAA/weather.gov (US only, gold standard)

Usage:
  python3 weather_arb.py                    # Scan for opportunities
  python3 weather_arb.py --min-edge 5       # Only show >5% edge
  python3 weather_arb.py --json             # JSON output for automation
  python3 weather_arb.py --test-apis        # Test all API connections
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
import statistics

GAMMA_API = "https://gamma-api.polymarket.com"
OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"
VISUAL_CROSSING_API = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
NOAA_API = "https://api.weather.gov"

# Config file path
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR.parent / "config" / "weather_api.json"

# Cities with weather markets (lowercase for matching)
WEATHER_CITIES = [
    ("seoul", 37.5665, 126.9780, False),
    ("london", 51.5074, -0.1278, False),
    ("nyc", 40.7128, -74.0060, True),
    ("new york", 40.7128, -74.0060, True),
    ("tokyo", 35.6762, 139.6503, False),
    ("paris", 48.8566, 2.3522, False),
    ("chicago", 41.8781, -87.6298, True),
    ("miami", 25.7617, -80.1918, True),
    ("atlanta", 33.7490, -84.3880, True),
    ("seattle", 47.6062, -122.3321, True),
    ("dallas", 32.7767, -96.7970, True),
    ("toronto", 43.6532, -79.3832, False),
    ("ankara", 39.9334, 32.8597, False),
    ("wellington", -41.2866, 174.7756, False),
    ("buenos aires", -34.6037, -58.3816, False),
    ("sydney", -33.8688, 151.2093, False),
]

def load_config():
    """Load API configuration."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return json.load(f)
    return {
        "visual_crossing_api_key": None,
        "weights": {"open_meteo": 0.33, "visual_crossing": 0.34, "noaa": 0.33},
        "noaa_boost_for_us": True
    }

CONFIG = load_config()

def fetch_json(url, timeout=15):
    """Fetch JSON from URL."""
    default_headers = {"User-Agent": "WeatherArb/1.0 (Polymarket trading bot)"}
    req = Request(url, headers=default_headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 503:
            return None
        return None
    except Exception as e:
        return None

# ============================================================================
# Weather API Implementations
# ============================================================================

def get_forecast_open_meteo(lat, lon, date):
    """Get forecast from Open-Meteo (free, global)."""
    date_str = date.strftime("%Y-%m-%d")
    url = f"{OPEN_METEO_API}?latitude={lat}&longitude={lon}&daily=temperature_2m_max,temperature_2m_min&timezone=auto&start_date={date_str}&end_date={date_str}"
    
    data = fetch_json(url)
    if not data or "daily" not in data:
        return None
    
    daily = data["daily"]
    if daily.get("temperature_2m_max") and daily.get("temperature_2m_min"):
        high_c = daily["temperature_2m_max"][0]
        low_c = daily["temperature_2m_min"][0]
        return {
            "source": "open_meteo",
            "high_c": high_c,
            "low_c": low_c,
            "high_f": high_c * 9/5 + 32,
            "low_f": low_c * 9/5 + 32,
        }
    return None

def get_forecast_visual_crossing(lat, lon, date):
    """Get forecast from Visual Crossing (high accuracy)."""
    api_key = CONFIG.get("visual_crossing_api_key")
    if not api_key:
        return None
    
    date_str = date.strftime("%Y-%m-%d")
    url = f"{VISUAL_CROSSING_API}/{lat},{lon}/{date_str}?unitGroup=metric&key={api_key}&include=days"
    
    data = fetch_json(url)
    if not data or "days" not in data or not data["days"]:
        return None
    
    day = data["days"][0]
    high_c = day.get("tempmax")
    low_c = day.get("tempmin")
    
    if high_c is not None and low_c is not None:
        return {
            "source": "visual_crossing",
            "high_c": high_c,
            "low_c": low_c,
            "high_f": high_c * 9/5 + 32,
            "low_f": low_c * 9/5 + 32,
        }
    return None

def get_forecast_noaa(lat, lon, date):
    """Get forecast from NOAA/weather.gov (US only, gold standard)."""
    points_url = f"{NOAA_API}/points/{lat},{lon}"
    points_data = fetch_json(points_url)
    
    if not points_data or "properties" not in points_data:
        return None
    
    forecast_url = points_data["properties"].get("forecast")
    if not forecast_url:
        return None
    
    forecast_data = fetch_json(forecast_url)
    if not forecast_data or "properties" not in forecast_data:
        return None
    
    periods = forecast_data["properties"].get("periods", [])
    if not periods:
        return None
    
    target_date = date.strftime("%Y-%m-%d")
    highs = []
    lows = []
    
    for period in periods:
        start_time = period.get("startTime", "")
        if target_date not in start_time:
            continue
        
        temp = period.get("temperature")
        unit = period.get("temperatureUnit", "F")
        is_daytime = period.get("isDaytime", True)
        
        if temp is not None:
            temp_f = temp if unit == "F" else temp * 9/5 + 32
            if is_daytime:
                highs.append(temp_f)
            else:
                lows.append(temp_f)
    
    if not highs and not lows:
        temp = periods[0].get("temperature")
        unit = periods[0].get("temperatureUnit", "F")
        if temp is not None:
            temp_f = temp if unit == "F" else temp * 9/5 + 32
            high_f = temp_f + 5
            low_f = temp_f - 5
            return {
                "source": "noaa",
                "high_f": high_f,
                "low_f": low_f,
                "high_c": (high_f - 32) * 5/9,
                "low_c": (low_f - 32) * 5/9,
                "approximate": True
            }
        return None
    
    high_f = max(highs) if highs else (max(lows) + 10 if lows else None)
    low_f = min(lows) if lows else (min(highs) - 10 if highs else None)
    
    if high_f is None or low_f is None:
        return None
    
    return {
        "source": "noaa",
        "high_f": high_f,
        "low_f": low_f,
        "high_c": (high_f - 32) * 5/9,
        "low_c": (low_f - 32) * 5/9,
    }

# ============================================================================
# Ensemble Forecasting
# ============================================================================

def get_ensemble_forecast(lat, lon, date, is_us=False):
    """Get ensemble forecast from all available sources."""
    forecasts = []
    
    om = get_forecast_open_meteo(lat, lon, date)
    if om:
        forecasts.append(om)
    
    vc = get_forecast_visual_crossing(lat, lon, date)
    if vc:
        forecasts.append(vc)
    
    if is_us:
        noaa = get_forecast_noaa(lat, lon, date)
        if noaa:
            forecasts.append(noaa)
    
    if not forecasts:
        return None
    
    weights = CONFIG.get("weights", {})
    
    if is_us and CONFIG.get("noaa_boost_for_us"):
        w = {
            "open_meteo": weights.get("open_meteo", 0.25),
            "visual_crossing": weights.get("visual_crossing", 0.35),
            "noaa": weights.get("noaa", 0.40)
        }
    else:
        noaa_w = weights.get("noaa", 0.33)
        w = {
            "open_meteo": weights.get("open_meteo", 0.33) + noaa_w/2,
            "visual_crossing": weights.get("visual_crossing", 0.34) + noaa_w/2,
            "noaa": 0
        }
    
    available_sources = [f["source"] for f in forecasts]
    total_weight = sum(w.get(s, 0) for s in available_sources)
    
    if total_weight == 0:
        total_weight = len(forecasts)
        for f in forecasts:
            w[f["source"]] = 1
    
    high_c_values = [f["high_c"] for f in forecasts]
    
    weighted_high_c = sum(f["high_c"] * w.get(f["source"], 1) for f in forecasts) / total_weight
    weighted_low_c = sum(f["low_c"] * w.get(f["source"], 1) for f in forecasts) / total_weight
    
    if len(forecasts) >= 2:
        high_spread = max(high_c_values) - min(high_c_values)
        confidence = max(0.3, min(0.95, 1.0 - (high_spread - 1) / 8))
        if len(forecasts) == 3 and high_spread <= 2:
            confidence = min(0.98, confidence + 0.1)
    else:
        confidence = 0.6
        high_spread = None
    
    return {
        "high_c": weighted_high_c,
        "low_c": weighted_low_c,
        "high_f": weighted_high_c * 9/5 + 32,
        "low_f": weighted_low_c * 9/5 + 32,
        "confidence": confidence,
        "sources": available_sources,
        "source_count": len(forecasts),
        "spread_c": high_spread,
        "individual": forecasts,
    }

# ============================================================================
# Polymarket Weather Market Discovery
# ============================================================================

def generate_weather_slugs(days_ahead=3):
    """Generate potential weather market slugs for upcoming days."""
    slugs = []
    today = datetime.now()
    
    for days in range(0, days_ahead + 1):
        target_date = today + timedelta(days=days)
        month_name = target_date.strftime("%B").lower()
        day = target_date.day
        year = target_date.year
        
        for city, lat, lon, is_us in WEATHER_CITIES:
            # Format: highest-temperature-in-seoul-on-february-10-2026
            city_slug = city.replace(" ", "-")
            slug = f"highest-temperature-in-{city_slug}-on-{month_name}-{day}-{year}"
            slugs.append({
                "slug": slug,
                "city": city.title(),
                "date": target_date,
                "lat": lat,
                "lon": lon,
                "is_us": is_us
            })
    
    return slugs

def fetch_weather_event(slug):
    """Fetch a specific weather event by slug."""
    url = f"{GAMMA_API}/events?slug={slug}"
    events = fetch_json(url)
    if events and len(events) > 0:
        return events[0]
    return None

def get_weather_events(days_ahead=3):
    """Get all available weather events from the weather tag."""
    # Much faster: use tag_slug=weather endpoint
    url = f"{GAMMA_API}/events?tag_slug=weather&closed=false&limit=100"
    events = fetch_json(url) or []
    
    weather_events = []
    today = datetime.now()
    
    for event in events:
        title = event.get("title", "").lower()
        
        # Filter to temperature markets only
        if "temperature" not in title or "highest" not in title:
            continue
        
        # Extract city and date from title
        # Pattern: "Highest temperature in Seoul on February 10?"
        import re
        city_match = re.search(r'highest temperature in ([a-z\s]+) on', title)
        date_match = re.search(r'on (january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d+)', title)
        
        if not city_match or not date_match:
            continue
        
        city_name = city_match.group(1).strip()
        month_name = date_match.group(1)
        day = int(date_match.group(2))
        
        # Find city coordinates
        city_info = None
        for c_name, lat, lon, is_us in WEATHER_CITIES:
            if c_name in city_name or city_name in c_name:
                city_info = {"city": c_name.title(), "lat": lat, "lon": lon, "is_us": is_us}
                break
        
        if not city_info:
            # Try to add unknown city with approximate coords
            city_info = {"city": city_name.title(), "lat": 0, "lon": 0, "is_us": False}
        
        # Parse date
        months = {'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                  'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12}
        year = today.year
        try:
            target_date = datetime(year, months[month_name], day)
            if target_date < today - timedelta(days=1):
                target_date = datetime(year + 1, months[month_name], day)
        except ValueError:
            continue
        
        # Only include events within days_ahead
        if (target_date - today).days > days_ahead:
            continue
        
        city_info["date"] = target_date
        event["_city_info"] = city_info
        weather_events.append(event)
    
    return weather_events

def parse_weather_event(event):
    """Parse a weather event to extract temperature ranges for each market."""
    city_info = event.get("_city_info")
    if not city_info:
        return None
    
    title = event.get("title", "")
    
    # Determine if Celsius or Fahrenheit from market questions
    markets = event.get("markets", [])
    if not markets:
        return None
    
    # Check first market question for unit
    first_q = markets[0].get("question", "").lower()
    is_celsius = "°c" in first_q
    
    markets_data = []
    for market in markets:
        question = market.get("question", "")
        
        # Parse temperature from question
        # Patterns: "be -1°C or below", "be 0°C on", "be 5°C or higher"
        temp_range = None
        is_or_below = "or below" in question.lower() or "or lower" in question.lower()
        is_or_higher = "or higher" in question.lower() or "or above" in question.lower()
        
        # Match temperature value (handles negative)
        temp_match = re.search(r'be\s+(-?\d+)°', question)
        if temp_match:
            temp = int(temp_match.group(1))
            if is_or_below:
                temp_range = (None, temp)
            elif is_or_higher:
                temp_range = (temp, None)
            else:
                temp_range = (temp, temp)
        
        if temp_range:
            try:
                prices = json.loads(market.get("outcomePrices", "[]"))
                yes_price = float(prices[0]) if prices else None
                no_price = float(prices[1]) if len(prices) > 1 else None
            except:
                yes_price = None
                no_price = None
            
            markets_data.append({
                "question": question,
                "slug": market.get("slug", ""),
                "condition_id": market.get("conditionId", ""),
                "token_id": market.get("clobTokenIds", ""),
                "temp_value": temp_range[0] if temp_range[0] is not None else temp_range[1],
                "temp_range": temp_range,
                "is_or_below": is_or_below,
                "is_or_higher": is_or_higher,
                "yes_price": yes_price,
                "no_price": no_price,
                "liquidity": float(market.get("liquidity", 0) or 0),
            })
    
    return {
        "event_id": event.get("id"),
        "title": title,
        "slug": event.get("slug"),
        "city": city_info["city"],
        "coords": (city_info["lat"], city_info["lon"]),
        "is_us": city_info["is_us"],
        "date": city_info["date"],
        "is_celsius": is_celsius,
        "markets": sorted(markets_data, key=lambda x: x["temp_value"] if x["temp_value"] is not None else 999),
    }

def calculate_probability(forecast_temp_c, temp_value, is_or_below, is_or_higher, confidence):
    """Calculate probability that temperature matches a market bucket."""
    # Forecast uncertainty in °C
    base_std = 1.5  # Base ±1.5°C
    adjusted_std = base_std * (1.5 - confidence)
    
    if is_or_below:
        # Probability that actual <= temp_value
        diff = temp_value - forecast_temp_c
        if diff >= adjusted_std:
            prob = 0.90
        elif diff >= 0:
            prob = 0.50 + (diff / adjusted_std) * 0.40
        elif diff >= -adjusted_std:
            prob = 0.10 + ((diff + adjusted_std) / adjusted_std) * 0.40
        else:
            prob = 0.05
            
    elif is_or_higher:
        # Probability that actual >= temp_value
        diff = forecast_temp_c - temp_value
        if diff >= adjusted_std:
            prob = 0.90
        elif diff >= 0:
            prob = 0.50 + (diff / adjusted_std) * 0.40
        elif diff >= -adjusted_std:
            prob = 0.10 + ((diff + adjusted_std) / adjusted_std) * 0.40
        else:
            prob = 0.05
            
    else:
        # Exact temperature bucket
        diff = abs(forecast_temp_c - temp_value)
        if diff <= 0.5:
            prob = 0.45
        elif diff <= 1.0:
            prob = 0.30
        elif diff <= adjusted_std:
            prob = 0.15
        else:
            prob = 0.05
    
    return max(0.02, min(0.98, prob))

def analyze_weather_event(event_data):
    """Analyze a weather event against ensemble forecast."""
    forecast = get_ensemble_forecast(
        event_data["coords"][0],
        event_data["coords"][1],
        event_data["date"],
        event_data["is_us"]
    )
    
    if not forecast:
        return []
    
    # Use high temp forecast (these markets are for "highest temperature")
    forecast_temp_c = forecast["high_c"]
    
    opportunities = []
    
    is_celsius = event_data.get("is_celsius", True)

    for market in event_data["markets"]:
        if market["yes_price"] is None:
            continue

        temp_value = market["temp_value"]
        if temp_value is None:
            continue

        # Convert market threshold to Celsius if market uses Fahrenheit
        temp_value_c = temp_value if is_celsius else (temp_value - 32) * 5 / 9

        # Calculate probability
        prob = calculate_probability(
            forecast_temp_c,
            temp_value_c,
            market["is_or_below"],
            market["is_or_higher"],
            forecast["confidence"]
        )
        
        market_yes_prob = market["yes_price"]
        if market_yes_prob is None or market_yes_prob <= 0:
            continue
        
        # Calculate edge
        min_edge_mult = 1.5 - forecast["confidence"]
        
        if prob > market_yes_prob + 0.03 * min_edge_mult:
            edge = (prob - market_yes_prob) * 100
            action = "BUY YES"
            ev = prob / market_yes_prob
        elif (1 - prob) > (1 - market_yes_prob) + 0.03 * min_edge_mult:
            edge = ((1 - prob) - (1 - market_yes_prob)) * 100
            action = "BUY NO"
            ev = (1 - prob) / (1 - market_yes_prob) if market_yes_prob < 1 else 0
        else:
            continue
        
        confidence_adjusted_edge = edge * forecast["confidence"]
        
        opportunities.append({
            "event_title": event_data["title"],
            "market_question": market["question"],
            "slug": market["slug"],
            "city": event_data["city"],
            "date": event_data["date"].strftime("%Y-%m-%d"),
            "is_us": event_data["is_us"],
            "temp_bucket": f"{temp_value}{'°C' if is_celsius else '°F'}",
            "forecast_temp": f"{forecast_temp_c:.1f}°C ({forecast_temp_c * 9/5 + 32:.1f}°F)",
            "forecast_sources": forecast["sources"],
            "forecast_confidence": forecast["confidence"],
            "forecast_spread": forecast.get("spread_c"),
            "market_yes_price": market["yes_price"],
            "market_no_price": market["no_price"],
            "forecast_prob": prob,
            "action": action,
            "edge_pct": edge,
            "confidence_adjusted_edge": confidence_adjusted_edge,
            "expected_value": ev,
            "liquidity": market["liquidity"],
            "url": f"https://polymarket.com/event/{event_data['slug']}",
            "individual_forecasts": forecast.get("individual", []),
        })
    
    return opportunities

# ============================================================================
# CLI
# ============================================================================

def test_apis():
    """Test all API connections."""
    print("🧪 Testing Weather APIs\n")
    
    lat, lon = 40.7128, -74.0060
    test_date = datetime.now() + timedelta(days=1)
    
    print(f"   Test location: New York ({lat}, {lon})")
    print(f"   Test date: {test_date.strftime('%Y-%m-%d')}\n")
    
    print("1. Open-Meteo (free, no key):")
    om = get_forecast_open_meteo(lat, lon, test_date)
    if om:
        print(f"   ✅ High: {om['high_c']:.1f}°C / {om['high_f']:.1f}°F")
    else:
        print("   ❌ Failed")
    
    print("\n2. Visual Crossing (API key required):")
    if CONFIG.get("visual_crossing_api_key"):
        vc = get_forecast_visual_crossing(lat, lon, test_date)
        if vc:
            print(f"   ✅ High: {vc['high_c']:.1f}°C / {vc['high_f']:.1f}°F")
        else:
            print("   ❌ Failed (check API key)")
    else:
        print("   ⚠️  No API key configured")
    
    print("\n3. NOAA/weather.gov (US only):")
    noaa = get_forecast_noaa(lat, lon, test_date)
    if noaa:
        approx = " (approximate)" if noaa.get("approximate") else ""
        print(f"   ✅ High: {noaa['high_c']:.1f}°C / {noaa['high_f']:.1f}°F{approx}")
    else:
        print("   ❌ Failed (may be rate limited)")
    
    print("\n4. Ensemble Result:")
    ensemble = get_ensemble_forecast(lat, lon, test_date, is_us=True)
    if ensemble:
        print(f"   ✅ High: {ensemble['high_c']:.1f}°C / {ensemble['high_f']:.1f}°F")
        print(f"   📊 Sources: {', '.join(ensemble['sources'])}")
        print(f"   🎯 Confidence: {ensemble['confidence']*100:.0f}%")
    else:
        print("   ❌ No sources available")
    
    print("\n✅ API test complete")

def main():
    parser = argparse.ArgumentParser(description="Weather arbitrage scanner for Polymarket (multi-source ensemble)")
    parser.add_argument("--min-edge", type=float, default=5.0, help="Minimum edge %% (default: 5.0)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show individual forecasts")
    parser.add_argument("--test-apis", action="store_true", help="Test API connections")
    parser.add_argument("--days", type=int, default=3, help="Days ahead to check (default: 3)")
    args = parser.parse_args()
    
    if args.test_apis:
        test_apis()
        return
    
    print("🌡️  Weather Arbitrage Scanner (Ensemble)")
    print("   Sources: Open-Meteo + Visual Crossing + NOAA\n")
    
    # Discover and fetch weather events
    print(f"   Discovering weather markets for next {args.days} days...")
    events = get_weather_events(days_ahead=args.days)
    print(f"   Found {len(events)} weather events\n")
    
    all_opportunities = []
    
    for event in events:
        parsed = parse_weather_event(event)
        if not parsed:
            continue
        
        opps = analyze_weather_event(parsed)
        all_opportunities.extend(opps)
    
    # Filter by confidence-adjusted edge
    filtered = [o for o in all_opportunities if o["confidence_adjusted_edge"] >= args.min_edge]
    
    # Sort by confidence-adjusted edge
    filtered.sort(key=lambda x: x["confidence_adjusted_edge"], reverse=True)
    
    if args.json:
        print(json.dumps(filtered, indent=2, default=str))
    else:
        print(f"   Analyzed {len(events)} events")
        print(f"   Found {len(filtered)} opportunities above {args.min_edge}% adjusted edge\n")
        
        if not filtered:
            print("   No weather arbitrage opportunities found at current threshold.")
            print("   Try --min-edge 3 or check back when forecasts diverge from market odds.")
        else:
            for opp in filtered[:15]:
                conf_emoji = "🟢" if opp['forecast_confidence'] > 0.8 else "🟡" if opp['forecast_confidence'] > 0.6 else "🔴"
                
                print(f"{'='*65}")
                print(f"🎯 {opp['action']} — {opp['edge_pct']:.1f}% edge ({opp['confidence_adjusted_edge']:.1f}% adj)")
                print(f"   {opp['market_question'][:58]}...")
                print(f"   📍 {opp['city']} {'🇺🇸' if opp['is_us'] else '🌍'} on {opp['date']}")
                print(f"   🌡️  Forecast: {opp['forecast_temp']} (from {len(opp['forecast_sources'])} sources)")
                print(f"   {conf_emoji} Confidence: {opp['forecast_confidence']*100:.0f}%", end="")
                if opp['forecast_spread']:
                    print(f" (spread: ±{opp['forecast_spread']:.1f}°C)")
                else:
                    print()
                print(f"   💰 Market: YES {opp['market_yes_price']*100:.0f}¢ / NO {opp['market_no_price']*100:.0f}¢")
                print(f"   📊 Our prob: {opp['forecast_prob']*100:.0f}% YES")
                print(f"   💵 EV: {opp['expected_value']:.2f}x | Liquidity: ${opp['liquidity']:,.0f}")
                print(f"   🔗 {opp['url']}")
                
                if args.verbose and opp['individual_forecasts']:
                    print(f"   📋 Individual forecasts:")
                    for f in opp['individual_forecasts']:
                        print(f"      - {f['source']}: {f['high_c']:.1f}°C high")
                print()
        
        print("\n📝 Notes:")
        print("   - Confidence-adjusted edge accounts for forecast uncertainty")
        print("   - 🟢 >80% | 🟡 60-80% | 🔴 <60% confidence")
        print("   - Markets resolve based on Weather Underground data")
        print("   - Use --verbose to see individual source forecasts")

if __name__ == "__main__":
    main()
