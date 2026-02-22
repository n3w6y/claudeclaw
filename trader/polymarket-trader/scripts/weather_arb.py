#!/usr/bin/env python3
"""
Weather arbitrage scanner for Polymarket.

Compares Polymarket weather markets to ensemble meteorological forecasts.
Uses three sources for triangulation:
  - Open-Meteo (free, global)
  - Visual Crossing (high accuracy, requires API key)
  - NOAA/weather.gov (US only, gold standard)
  - MetService (New Zealand national service)
  - BOM (Australian Bureau of Meteorology)

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

try:
    import geohash2
    HAS_GEOHASH2 = True
except ImportError:
    HAS_GEOHASH2 = False

GAMMA_API = "https://gamma-api.polymarket.com"
OPEN_METEO_API = "https://api.open-meteo.com/v1/forecast"
VISUAL_CROSSING_API = "https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline"
NOAA_API = "https://api.weather.gov"

# Config file path
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR.parent / "config" / "weather_api.json"

# Cities with weather markets (lowercase for matching)
# Tuple: (name, lat, lon, is_us, local_source)
# local_source: "noaa" | "metservice" | "bom" | None
WEATHER_CITIES = [
    ("wellington",     -41.2866,  174.7756, False, "metservice"),
    ("auckland",       -36.8485,  174.7633, False, "metservice"),
    ("sydney",         -33.8688,  151.2093, False, "bom"),
    ("brisbane",       -27.4698,  153.0251, False, "bom"),
    ("melbourne",      -37.8136,  144.9631, False, "bom"),
    ("seoul",           37.5665,  126.9780, False, "kma"),
    ("london",          51.5074,   -0.1278, False, None),  # Phase 3: Met Office
    ("tokyo",           35.6762,  139.6503, False, None),  # Phase 3: JMA
    ("paris",           48.8566,    2.3522, False, None),  # Phase 3: Météo-France
    ("toronto",         43.6532,  -79.3832, False, None),  # Phase 3: ECCC
    ("ankara",          39.9334,   32.8597, False, None),
    ("buenos aires",   -34.6037,  -58.3816, False, None),
    ("nyc",             40.7128,  -74.0060, True,  "noaa"),
    ("new york",        40.7128,  -74.0060, True,  "noaa"),
    ("chicago",         41.8781,  -87.6298, True,  "noaa"),
    ("miami",           25.7617,  -80.1918, True,  "noaa"),
    ("atlanta",         33.7490,  -84.3880, True,  "noaa"),
    ("seattle",         47.6062, -122.3321, True,  "noaa"),
    ("dallas",          32.7767,  -96.7970, True,  "noaa"),
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


def fetch_json_with_headers(url, headers, timeout=15):
    """Fetch JSON from URL with custom headers."""
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception:
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

def get_forecast_metservice(city_name, date):
    """Get forecast from MetService (NZ national service). Returns °C."""
    METSERVICE_CITIES = {
        "wellington":   "Wellington",
        "auckland":     "Auckland",
        "christchurch": "Christchurch",
    }
    ms_city = METSERVICE_CITIES.get(city_name.lower())
    if not ms_city:
        return None

    url = f"https://www.metservice.com/publicData/localForecast{ms_city}"
    data = fetch_json(url)

    if not data or "days" not in data:
        return None

    target_str = date.strftime("%Y-%m-%d")
    for day in data["days"]:
        # MetService date field is "19 Feb", check dateISO for YYYY-MM-DD
        date_iso = str(day.get("dateISO", ""))
        date_short = str(day.get("date", ""))
        if target_str in date_iso or target_str in date_short:
            high_c = day.get("max")
            low_c = day.get("min")
            if high_c is not None:
                return {
                    "source": "metservice",
                    "high_c": float(high_c),
                    "low_c": float(low_c) if low_c is not None else None,
                    "high_f": float(high_c) * 9/5 + 32,
                    "low_f": float(low_c) * 9/5 + 32 if low_c is not None else None,
                    "is_local": True,
                }
    return None


def get_forecast_bom(lat, lon, date):
    """Get forecast from BOM (Australian Bureau of Meteorology). Returns °C."""
    if not HAS_GEOHASH2:
        return None

    gh = geohash2.encode(lat, lon, precision=6)
    url = f"https://api.weather.bom.gov.au/v1/locations/{gh}/forecasts/daily"
    headers = {
        "User-Agent": "WeatherArb/1.0",
        "Accept": "application/json",
    }
    data = fetch_json_with_headers(url, headers)
    if not data or "data" not in data:
        return None

    target_str = date.strftime("%Y-%m-%d")
    for day in data["data"]:
        day_date = str(day.get("date", ""))
        if target_str in day_date:
            high_c = day.get("temp_max")
            low_c = day.get("temp_min")
            if high_c is not None:
                return {
                    "source": "bom",
                    "high_c": float(high_c),
                    "low_c": float(low_c) if low_c is not None else None,
                    "high_f": float(high_c) * 9/5 + 32,
                    "low_f": float(low_c) * 9/5 + 32 if low_c is not None else None,
                    "is_local": True,
                }
    return None



def get_forecast_kma(lat, lon, date):
    """
    Get forecast from KMA (Korea Meteorological Administration) KIM 8km model.
    Fetches 2m temperature across the target KST day and returns daily max in °C.
    Requires KMA_API_KEY in environment.
    """
    import os
    auth_key = os.environ.get("KMA_API_KEY") or os.environ.get("KMA_API")
    if not auth_key:
        # Try loading from .tinyclaw/polymarket.env
        env_path = Path.home() / ".tinyclaw/polymarket.env"
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("KMA_API_KEY="):
                    auth_key = line.split("=", 1)[1].strip()
                    break
    if not auth_key:
        return None

    from datetime import timedelta
    # Seoul is UTC+9. KST day = UTC (day-1) 15:00 to UTC (day) 14:00
    # Use 00UTC run from day before target date
    base_date = date - timedelta(days=1)
    tmfc = base_date.strftime("%Y%m%d") + "00"
    # Fetch hours 15..38 (covering full KST day)
    forecast_hours = list(range(15, 39, 3))

    base_url = "https://apihub.kma.go.kr/api/typ01/cgi-bin/url/nph-kim_nc_pt_txt2"
    temps_k = []
    for hf in forecast_hours:
        url = (
            f"{base_url}?group=KIMG&nwp=NE57&data=U&name=t2m"
            f"&tmfc={tmfc}&hf={hf}&disp=A&lat={lat}&lon={lon}&authKey={auth_key}"
        )
        try:
            req = Request(url, headers={"User-Agent": "WeatherArb/1.0"})
            with urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            for line in raw.splitlines():
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        val_k = float(parts[4])
                        if 220 < val_k < 340:  # sanity check — valid Kelvin range
                            temps_k.append(val_k)
                    except ValueError:
                        pass
        except Exception:
            continue

    if not temps_k:
        return None

    high_k = max(temps_k)
    low_k  = min(temps_k)
    high_c = high_k - 273.15
    low_c  = low_k  - 273.15
    return {
        "source":  "kma",
        "high_c":  round(high_c, 2),
        "low_c":   round(low_c,  2),
        "high_f":  round(high_c * 9/5 + 32, 2),
        "low_f":   round(low_c  * 9/5 + 32, 2),
        "is_local": True,
    }

# ============================================================================
# Ensemble Forecasting
# ============================================================================

def get_ensemble_forecast(lat, lon, date, is_us=False, local_source=None, city_name=None):
    """
    Get ensemble forecast from all available sources.

    Weighting per TRADING_RULES.md:
      US markets:              noaa=40%, visual_crossing=35%, open_meteo=25%
      Non-US with local:       local_national=50%, open_meteo=25%, visual_crossing=25%
      Non-US without local:    open_meteo=50%, visual_crossing=50%

    Disagreement flag: if local source disagrees with global average by >2°C,
    confidence is capped at 0.50 (effectively blocks trade at 80% threshold).
    """
    global_forecasts = []
    local_forecast = None

    om = get_forecast_open_meteo(lat, lon, date)
    if om:
        global_forecasts.append(om)

    vc = get_forecast_visual_crossing(lat, lon, date)
    if vc:
        global_forecasts.append(vc)

    # Fetch local national source
    if is_us:
        noaa = get_forecast_noaa(lat, lon, date)
        if noaa:
            local_forecast = noaa
    elif local_source == "metservice" and city_name:
        ms = get_forecast_metservice(city_name, date)
        if ms:
            local_forecast = ms
    elif local_source == "bom":
        bom = get_forecast_bom(lat, lon, date)
        if bom:
            local_forecast = bom
    elif local_source == "kma":
        kma = get_forecast_kma(lat, lon, date)
        if kma:
            local_forecast = kma

    all_forecasts = global_forecasts + ([local_forecast] if local_forecast else [])

    if not all_forecasts:
        return None

    # Build weight map
    if is_us:
        w = {
            "noaa":            0.40,
            "visual_crossing": 0.35,
            "open_meteo":      0.25,
        }
    elif local_forecast:
        src = local_forecast["source"]
        w = {
            src:               0.50,
            "open_meteo":      0.25,
            "visual_crossing": 0.25,
        }
    else:
        w = {
            "open_meteo":      0.50,
            "visual_crossing": 0.50,
        }

    available_sources = [f["source"] for f in all_forecasts]
    total_weight = sum(w.get(s, 0) for s in available_sources)

    if total_weight == 0:
        total_weight = len(all_forecasts)
        for f in all_forecasts:
            w[f["source"]] = 1

    high_c_values = [f["high_c"] for f in all_forecasts]
    low_c_values = [f["low_c"] for f in all_forecasts if f.get("low_c") is not None]

    weighted_high_c = sum(f["high_c"] * w.get(f["source"], 1) for f in all_forecasts) / total_weight
    if low_c_values:
        weighted_low_c = sum(
            f["low_c"] * w.get(f["source"], 1)
            for f in all_forecasts if f.get("low_c") is not None
        ) / total_weight
    else:
        weighted_low_c = weighted_high_c - 10  # fallback estimate

    if len(all_forecasts) >= 2:
        high_spread = max(high_c_values) - min(high_c_values)
        confidence = max(0.3, min(0.95, 1.0 - (high_spread - 1) / 8))
        if len(all_forecasts) == 3 and high_spread <= 2:
            confidence = min(0.98, confidence + 0.1)
    else:
        confidence = 0.6
        high_spread = None

    result = {
        "high_c": weighted_high_c,
        "low_c": weighted_low_c,
        "high_f": weighted_high_c * 9/5 + 32,
        "low_f": weighted_low_c * 9/5 + 32,
        "confidence": confidence,
        "sources": available_sources,
        "source_count": len(all_forecasts),
        "spread_c": high_spread,
        "individual": all_forecasts,
        "local_disagrees": False,
        "disagreement_c": 0.0,
    }

    # Disagreement flag: local vs global average >2°C → cap confidence at 0.50
    if local_forecast and global_forecasts:
        local_temp = local_forecast["high_c"]
        global_avg = sum(f["high_c"] for f in global_forecasts) / len(global_forecasts)
        disagreement = abs(local_temp - global_avg)
        if disagreement > 2.0:
            result["confidence"] = min(result["confidence"], 0.50)
            result["local_disagrees"] = True
            result["disagreement_c"] = round(disagreement, 2)

    return result

def prepare_forecasts_for_market(forecasts, is_us_market):
    """
    Convert all forecast temps to market's native unit for comparison.

    US markets resolve in °F; non-US markets resolve in °C.
    All internal forecast data is stored in °C. This function converts
    to the market's native unit so comparisons use the correct unit system.

    Returns list of forecast dicts with added 'high' and 'low' keys in
    market's native unit, plus the original 'high_c'/'low_c' preserved.
    """
    result = []
    for f in forecasts:
        entry = dict(f)
        if is_us_market:
            entry["high"] = f["high_c"] * 9/5 + 32
            entry["low"]  = f["low_c"] * 9/5 + 32 if f.get("low_c") is not None else None
        else:
            entry["high"] = f["high_c"]
            entry["low"]  = f.get("low_c")
        result.append(entry)
    return result


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
        
        for city, lat, lon, is_us, local_source in WEATHER_CITIES:
            # Format: highest-temperature-in-seoul-on-february-10-2026
            city_slug = city.replace(" ", "-")
            slug = f"highest-temperature-in-{city_slug}-on-{month_name}-{day}-{year}"
            slugs.append({
                "slug": slug,
                "city": city.title(),
                "date": target_date,
                "lat": lat,
                "lon": lon,
                "is_us": is_us,
                "local_source": local_source,
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
        for c_name, lat, lon, is_us, local_source in WEATHER_CITIES:
            if c_name in city_name or city_name in c_name:
                city_info = {"city": c_name.title(), "lat": lat, "lon": lon, "is_us": is_us, "local_source": local_source}
                break
        
        if not city_info:
            # Try to add unknown city with approximate coords
            city_info = {"city": city_name.title(), "lat": 0, "lon": 0, "is_us": False, "local_source": None}
        
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
        "local_source": city_info.get("local_source"),
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
        event_data["is_us"],
        local_source=event_data.get("local_source"),
        city_name=event_data["city"],
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
            "local_source": event_data.get("local_source"),
            "local_disagrees": forecast.get("local_disagrees", False),
            "disagreement_c": forecast.get("disagreement_c", 0.0),
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
    print("Testing Weather APIs\n")

    test_date = datetime.now() + timedelta(days=1)

    # US test: New York
    lat_us, lon_us = 40.7128, -74.0060
    print(f"--- US: New York ({lat_us}, {lon_us}) {test_date.strftime('%Y-%m-%d')} ---")

    om = get_forecast_open_meteo(lat_us, lon_us, test_date)
    om_str = f"High: {om['high_c']:.1f}°C / {om['high_f']:.1f}°F" if om else "FAILED"
    print(f"  Open-Meteo:     {om_str}")

    if CONFIG.get("visual_crossing_api_key"):
        vc = get_forecast_visual_crossing(lat_us, lon_us, test_date)
        vc_str = f"High: {vc['high_c']:.1f}°C / {vc['high_f']:.1f}°F" if vc else "FAILED (check key)"
        print(f"  Visual Crossing: {vc_str}")
    else:
        print("  Visual Crossing: no API key configured")

    noaa = get_forecast_noaa(lat_us, lon_us, test_date)
    if noaa:
        approx = " (approximate)" if noaa.get("approximate") else ""
        print(f"  NOAA:           High: {noaa['high_c']:.1f}°C / {noaa['high_f']:.1f}°F{approx}")
    else:
        print("  NOAA:           FAILED (may be rate limited)")

    ensemble_us = get_ensemble_forecast(lat_us, lon_us, test_date, is_us=True, local_source="noaa")
    if ensemble_us:
        print(f"  Ensemble (US):  High: {ensemble_us['high_c']:.1f}°C / {ensemble_us['high_f']:.1f}°F  "
              f"conf={ensemble_us['confidence']*100:.0f}%  sources={ensemble_us['sources']}")

    # NZ test: Wellington
    lat_nz, lon_nz = -41.2866, 174.7756
    print(f"\n--- NZ: Wellington ({lat_nz}, {lon_nz}) ---")
    ms = get_forecast_metservice("Wellington", test_date)
    ms_str = f"High: {ms['high_c']:.1f}°C" if ms else "FAILED"
    print(f"  MetService:     {ms_str}")
    om_nz = get_forecast_open_meteo(lat_nz, lon_nz, test_date)
    om_nz_str = f"High: {om_nz['high_c']:.1f}°C" if om_nz else "FAILED"
    print(f"  Open-Meteo:     {om_nz_str}")
    ensemble_nz = get_ensemble_forecast(lat_nz, lon_nz, test_date, is_us=False, local_source="metservice", city_name="Wellington")
    if ensemble_nz:
        disagree = f"  LOCAL DISAGREES: {ensemble_nz['disagreement_c']:.1f}°C" if ensemble_nz.get("local_disagrees") else ""
        print(f"  Ensemble (NZ):  High: {ensemble_nz['high_c']:.1f}°C  conf={ensemble_nz['confidence']*100:.0f}%  sources={ensemble_nz['sources']}{disagree}")

    # AU test: Sydney
    lat_au, lon_au = -33.8688, 151.2093
    print(f"\n--- AU: Sydney ({lat_au}, {lon_au}) ---")
    if HAS_GEOHASH2:
        bom = get_forecast_bom(lat_au, lon_au, test_date)
        bom_str = f"High: {bom['high_c']:.1f}°C" if bom else "FAILED"
        print(f"  BOM:            {bom_str}")
    else:
        print("  BOM:            geohash2 not installed")
    om_au = get_forecast_open_meteo(lat_au, lon_au, test_date)
    om_au_str = f"High: {om_au['high_c']:.1f}°C" if om_au else "FAILED"
    print(f"  Open-Meteo:     {om_au_str}")
    ensemble_au = get_ensemble_forecast(lat_au, lon_au, test_date, is_us=False, local_source="bom")
    if ensemble_au:
        print(f"  Ensemble (AU):  High: {ensemble_au['high_c']:.1f}°C  conf={ensemble_au['confidence']*100:.0f}%  sources={ensemble_au['sources']}")

    print("\nAPI test complete")

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
