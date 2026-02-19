#!/usr/bin/env python3
"""
Night Watch - Automated weather trading on Simmer ($SIM only).

Scans weather markets and executes trades on good opportunities.
Designed to run via cron every 30 minutes.
"""

import json
import os
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import urllib.error

# Paths
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR.parent / "config/simmer_config.json"
STATE_FILE = SCRIPT_DIR.parent / "config/trading_state.json"
JOURNAL_DIR = SCRIPT_DIR.parent / "journal"

# Config
MIN_EDGE = 10.0  # Minimum edge percentage to trade
MAX_BET = 10.0   # $10 per trade
MAX_TRADES_PER_RUN = 2  # Max trades per cron run
MAX_DAILY_TRADES = 6    # Max trades per day

CITY_COORDS = {
    "new york city": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "miami": (25.7617, -80.1918),
    "atlanta": (33.7490, -84.3880),
    "dallas": (32.7767, -96.7970),
    "seattle": (47.6062, -122.3321),
}


def load_config():
    with open(CONFIG_FILE) as f:
        return json.load(f)


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"daily_trades": 0, "last_reset": "", "traded_markets": []}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def log_to_journal(trade_info):
    """Append trade to daily journal."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    journal_file = JOURNAL_DIR / f"{today}.md"
    
    entry = f"""
### Trade @ {trade_info['timestamp']}
- **Market:** {trade_info['question']}
- **Side:** YES
- **Amount:** ${trade_info['cost']:.2f}
- **Shares:** {trade_info['shares']:.2f}
- **Entry Price:** {trade_info['entry_price']*100:.1f}%
- **Forecast:** {trade_info['forecast_temp']}°F
- **Edge:** {trade_info['edge']:.1f}%
- **Thesis:** {trade_info['reasoning']}

"""
    
    if not journal_file.exists():
        header = f"# Trade Journal - {today}\n\n## Trades\n"
        with open(journal_file, "w") as f:
            f.write(header)
    
    with open(journal_file, "a") as f:
        f.write(entry)


def fetch_json(url, headers=None, timeout=45):
    """Fetch JSON from URL."""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"   Error fetching {url}: {e}")
        return None


def get_forecast(city, date):
    """Get temperature forecast for city on date."""
    if city not in CITY_COORDS:
        return None
    
    lat, lon = CITY_COORDS[city]
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&daily=temperature_2m_max&timezone=auto&start_date={date}&end_date={date}&temperature_unit=fahrenheit"
    
    data = fetch_json(url)
    if data and "daily" in data:
        temps = data["daily"].get("temperature_2m_max", [])
        if temps:
            return temps[0]
    return None


def parse_market(market):
    """Parse weather market to extract city and temp range."""
    question = market.get("question", "").lower()
    
    # Find city
    city = None
    for c in CITY_COORDS.keys():
        if c in question:
            city = c
            break
    
    if not city:
        return None
    
    # Find temp range
    range_match = re.search(r'between\s+(\d+)-(\d+)\s*°', question)
    higher_match = re.search(r'(\d+)\s*°[fF]?\s+or\s+higher', question)
    lower_match = re.search(r'(\d+)\s*°[fF]?\s+or\s+(lower|below)', question)
    
    if range_match:
        temp_range = (int(range_match.group(1)), int(range_match.group(2)))
    elif higher_match:
        temp_range = (int(higher_match.group(1)), 150)
    elif lower_match:
        temp_range = (-50, int(lower_match.group(1)))
    else:
        return None
    
    # Find date
    date_match = re.search(r'february\s+(\d+)', question)
    if date_match:
        day = int(date_match.group(1))
        date = f"2026-02-{day:02d}"
    else:
        date = datetime.utcnow().strftime("%Y-%m-%d")
    
    return {
        "city": city,
        "temp_range": temp_range,
        "date": date,
    }


def analyze_opportunity(market):
    """Analyze market for trading opportunity."""
    parsed = parse_market(market)
    if not parsed:
        return None
    
    # Get forecast
    forecast_temp = get_forecast(parsed["city"], parsed["date"])
    if forecast_temp is None:
        return None
    
    temp_low, temp_high = parsed["temp_range"]
    market_prob = market.get("current_probability", 0)
    
    # Calculate our probability estimate
    if temp_low <= forecast_temp <= temp_high:
        our_prob = 0.75  # In range = high confidence
    else:
        distance = min(abs(forecast_temp - temp_low), abs(forecast_temp - temp_high))
        if distance <= 2:
            our_prob = 0.25
        elif distance <= 4:
            our_prob = 0.10
        else:
            our_prob = 0.03
    
    edge = (our_prob - market_prob) * 100
    
    return {
        "market_id": market["id"],
        "question": market["question"],
        "city": parsed["city"].title(),
        "temp_range": parsed["temp_range"],
        "date": parsed["date"],
        "forecast_temp": forecast_temp,
        "market_prob": market_prob,
        "our_prob": our_prob,
        "edge": edge,
        "url": market.get("url", ""),
    }


def execute_trade(api_key, opportunity):
    """Execute trade on Simmer."""
    url = "https://api.simmer.markets/api/sdk/trade"
    
    reasoning = f"Forecast: {opportunity['forecast_temp']}°F. Range {opportunity['temp_range'][0]}-{opportunity['temp_range'][1]}°F. Edge: {opportunity['edge']:.1f}%"
    
    data = json.dumps({
        "market_id": opportunity["market_id"],
        "side": "yes",
        "amount": MAX_BET,
        "venue": "simmer",
        "reasoning": reasoning,
        "source": "sdk:night-watch",
    }).encode()
    
    req = urllib.request.Request(url, data=data, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    })
    
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"success": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def main():
    now = datetime.utcnow()
    print(f"🌙 Night Watch — {now.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    
    # Load config
    config = load_config()
    api_key = config.get("api_key")
    
    if not api_key:
        print("❌ No API key found")
        return
    
    # Load state
    state = load_state()
    today = now.strftime("%Y-%m-%d")
    
    # Reset daily counter if new day
    if state.get("last_reset") != today:
        state["daily_trades"] = 0
        state["traded_markets"] = []
        state["last_reset"] = today
        save_state(state)
    
    # Check daily limit
    if state["daily_trades"] >= MAX_DAILY_TRADES:
        print(f"   Daily limit reached ({MAX_DAILY_TRADES} trades). Skipping.")
        return
    
    # Fetch weather markets
    print("   Fetching weather markets...")
    markets_url = "https://api.simmer.markets/api/sdk/markets?tags=weather&limit=100"
    markets_data = fetch_json(markets_url, {"Authorization": f"Bearer {api_key}"})
    
    if not markets_data:
        print("   ❌ Failed to fetch markets")
        return
    
    markets = markets_data.get("markets", [])
    print(f"   Found {len(markets)} weather markets")
    
    # Analyze opportunities
    opportunities = []
    for market in markets:
        if market.get("status") != "active":
            continue
        if market["id"] in state.get("traded_markets", []):
            continue  # Already traded this market
        
        opp = analyze_opportunity(market)
        if opp and opp["edge"] >= MIN_EDGE:
            opportunities.append(opp)
    
    opportunities.sort(key=lambda x: x["edge"], reverse=True)
    print(f"   Found {len(opportunities)} opportunities ≥{MIN_EDGE}% edge")
    
    # Execute trades
    trades_made = 0
    for opp in opportunities:
        if trades_made >= MAX_TRADES_PER_RUN:
            break
        if state["daily_trades"] >= MAX_DAILY_TRADES:
            break
        
        print(f"\n   🎯 {opp['city']} {opp['temp_range'][0]}-{opp['temp_range'][1]}°F")
        print(f"      Market: {opp['market_prob']*100:.1f}% | Forecast: {opp['forecast_temp']}°F | Edge: {opp['edge']:.1f}%")
        
        result = execute_trade(api_key, opp)
        
        if result.get("success"):
            trades_made += 1
            state["daily_trades"] += 1
            state["traded_markets"].append(opp["market_id"])
            
            print(f"      ✅ Bought {result.get('shares_bought', 0):.2f} shares for ${result.get('cost', 0):.2f}")
            print(f"      💰 Balance: ${result.get('balance', 0):.2f} $SIM")
            
            # Log to journal
            log_to_journal({
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                "question": opp["question"],
                "cost": result.get("cost", 0),
                "shares": result.get("shares_bought", 0),
                "entry_price": opp["market_prob"],
                "forecast_temp": opp["forecast_temp"],
                "edge": opp["edge"],
                "reasoning": f"Forecast {opp['forecast_temp']}°F in {opp['temp_range'][0]}-{opp['temp_range'][1]}°F range",
            })
        else:
            print(f"      ❌ Failed: {result.get('error', 'Unknown')}")
    
    save_state(state)
    print(f"\n   Done. Trades today: {state['daily_trades']}/{MAX_DAILY_TRADES}")


if __name__ == "__main__":
    main()
