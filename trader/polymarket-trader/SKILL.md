---
name: polymarket-trader
description: Trade on Polymarket prediction markets. Scan markets, track whale traders, detect arbitrage opportunities, and execute trades. Use when asked about Polymarket, prediction markets, betting odds, whale tracking, or copy trading.
---

# Polymarket Trader

Trade profitably on Polymarket by tracking smart money and detecting mispriced odds.

## Strategy Overview

1. **Whale Tracking** — Follow top traders' positions and copy high-conviction bets
2. **Internal Arbitrage** — Find related markets where odds don't sum correctly
3. **Cross-Platform Arbitrage** — Compare Polymarket vs Kalshi/PredictIt odds (manual)

## Quick Commands

### Scan Active Markets
```bash
python3 scripts/scan_markets.py --active --limit 50
```

### Check Leaderboard / Top Traders
```bash
python3 scripts/track_whales.py --leaderboard
```

### Track Specific Wallet
```bash
python3 scripts/track_whales.py --wallet 0x123...
```

### Find Arbitrage Opportunities
```bash
python3 scripts/find_arbitrage.py --threshold 2
```

### Micro-Arbitrage Scanner (Short-Duration/Crypto)
```bash
# One-shot scan
python3 scripts/micro_arb_scanner.py --min-edge 0.5

# Continuous monitoring (checks every 30s)
python3 scripts/micro_arb_scanner.py --watch --interval 30

# Crypto markets only, with live orderbook prices
python3 scripts/micro_arb_scanner.py --crypto-only --check-orderbook

# Short-duration markets only (resolving within 24h)
python3 scripts/micro_arb_scanner.py --short-only --min-edge 0.3
```

### Cross-Market Arbitrage (Related Events)
```bash
# Scan for pricing inconsistencies across related markets
python3 scripts/cross_market_arb.py --min-edge 2

# Filter by keyword (Iran, Bitcoin, etc.)
python3 scripts/cross_market_arb.py --event "iran" --min-edge 1

# JSON output for programmatic use
python3 scripts/cross_market_arb.py --json
```

**Types detected:**
- **Date mispricing:** "by March" YES > "by June" YES (illogical)
- **All-NO bets:** High return if event never happens (NOT risk-free)
- **Mutual exclusivity:** Related markets summing wrong

### Weather Arbitrage (High-Frequency)
```bash
# Scan weather markets vs ensemble forecasts (3-source triangulation)
python3 scripts/weather_arb.py --min-edge 5

# Lower threshold for more results
python3 scripts/weather_arb.py --min-edge 3 --verbose

# Test all API connections
python3 scripts/weather_arb.py --test-apis

# Update local forecast cache
python3 scripts/forecast_cache.py --update
python3 scripts/forecast_cache.py --compare
```

**Strategy:** Compare Polymarket weather markets to ensemble forecast from 3 sources:
- **Open-Meteo** (free, global, no key) — baseline forecast
- **Visual Crossing** (high accuracy, API key in config/weather_api.json) — 1,000 calls/day free tier
- **NOAA/weather.gov** (US cities only, gold standard, no key) — government data

Weather markets are daily — check morning for same-day opportunities.
Best edge when forecast confidence is high (24-48h out).

#### Weather API Triangulation Strategy

| Source | Strengths | Best Use |
|--------|-----------|----------|
| NOAA/weather.gov | Gold standard for US cities, official government data, high accuracy 24-48h out | Primary source for US markets |
| Open-Meteo | Free, global coverage, hourly data, multiple model ensemble | Baseline/fallback, international |
| Visual Crossing | Historical accuracy tracking, confidence scores, good 7-day | Confirmation source |

**Statistical Benefit:**
1. **Consensus = Confidence** — If all 3 sources agree (e.g., 85°F +/- 2°), high confidence. If Polymarket prices differ, strong edge.
2. **Disagreement = Caution** — If sources diverge, market uncertainty justified. No trade.
3. **Weighted scoring** — NOAA highest weight for US (0.35), Visual Crossing for confirmation (0.40), Open-Meteo baseline (0.25). Non-US: NOAA weight redistributed to VC/OM.

**Edge Calculation:**
- Forecast confidence = (agreement across sources) x (time to event proximity)
- Market edge = |forecast probability - market price|
- Trade if: edge > 5% AND confidence > 80%

**Free Tier Limits:**
- Open-Meteo: 10,000 calls/day (no concern)
- Visual Crossing: 1,000 calls/day (keep scans to <20/day with 16 cities)
- NOAA: No hard limit, but be polite (US cities only)

### Execute Trade (Browser)
Use browser automation to place trades on polymarket.com. Requires logged-in session.

## Alert Thresholds

- **Arbitrage alert**: >2% edge (adjustable)
- **Whale alert**: Top-50 trader takes >$10k position
- **Odds movement**: >5% swing in 1 hour

## Workflow

### Daily Scan
1. Run `scan_markets.py` to get active markets
2. Run `track_whales.py` to see recent whale activity
3. Run `find_arbitrage.py` to check for mispricing
4. Alert user on Telegram if opportunities found

### Trade Execution
1. Identify opportunity (whale copy or arbitrage)
2. Confirm with user (unless autonomous mode enabled)
3. Open Polymarket in browser
4. Navigate to market, place order
5. Log trade in workspace

## API Reference

See `references/api.md` for full endpoint documentation.

### Key Endpoints (No Auth Required)
- `GET https://gamma-api.polymarket.com/events?active=true` — List active events
- `GET https://gamma-api.polymarket.com/markets?slug=<slug>` — Market details
- `GET https://clob.polymarket.com/price?token_id=<id>&side=buy` — Current price
- `GET https://clob.polymarket.com/book?token_id=<id>` — Order book

### Data API (For Positions)
- `GET https://data-api.polymarket.com/positions?user=<wallet>` — User positions
- `GET https://data-api.polymarket.com/activity?user=<wallet>` — User activity

## Risk Management

- **Tiered position sizing:** $5 max under $100 balance, $10 at $100-200, $15 at $200-300, etc. (5% of the next $100 tier)
- Daily loss limit: $100 hard cap
- Max 2 trades/hour, 10 trades/session, 3 weather trades/day
- Log all trades to journal/

## Configuration

Actual live config in `config/trading_limits.json` + `scripts/risk_manager.py`:
```json
{
  "max_order_usd": 55,
  "daily_limit_usd": 100,
  "require_confirmation": false,
  "min_liquidity": 1000,
  "max_trades_per_session": 10
}
```
`max_order_usd` is a safety ceiling — actual per-trade limits are tier-based in `risk_manager.py`.

## Browser Trading

Trading requires browser automation since Polymarket doesn't have a public trading API for retail users.

1. Ensure browser is running (`browser start`)
2. Navigate to polymarket.com
3. Login should persist if session exists
4. Navigate to market URL
5. Click Buy/Sell, enter amount, confirm

## Files

- `scripts/scan_markets.py` — Fetch and analyze markets
- `scripts/track_whales.py` — Track top traders and wallets
- `scripts/find_arbitrage.py` — Detect arbitrage opportunities
- `scripts/micro_arb_scanner.py` — Short-duration micro-arbitrage scanner
- `scripts/cross_market_arb.py` — Cross-market arbitrage on related events
- `scripts/weather_arb.py` — Weather forecast vs market odds arbitrage (3-source ensemble)
- `scripts/forecast_cache.py` — Local forecast cache manager
- `scripts/polymarket_api.py` — CLOB API client (auth, orders, balance)
- `scripts/risk_manager.py` — Tiered position sizing and risk limits
- `scripts/auto_trader.py` — Automated paper trading scanner
- `scripts/batch_trader.py` — Batch trade execution
- `scripts/simmer_weather_scanner.py` — Simmer venue weather scanner
- `scripts/night_watch.py` — Overnight monitoring
- `scripts/status_report.py` — Status report generator
- `references/api.md` — API documentation
