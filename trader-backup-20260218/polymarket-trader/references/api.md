# Polymarket API Reference

## Base URLs

| API | URL | Auth Required |
|-----|-----|---------------|
| Gamma API | https://gamma-api.polymarket.com | No |
| CLOB API | https://clob.polymarket.com | No (read), Yes (trade) |
| Data API | https://data-api.polymarket.com | No |
| WebSocket | wss://ws-subscriptions-clob.polymarket.com/ws/ | Optional |

## Gamma API (Market Discovery)

### List Events
```
GET /events?active=true&closed=false&limit=50
GET /events?tag_id=2&active=true
GET /events?series_id=10345  # Sports leagues
```

### Get Market
```
GET /markets?slug=will-bitcoin-reach-100k
GET /markets?id=12345
```

### List Tags
```
GET /tags?limit=100
```

### Sports
```
GET /sports  # List leagues
```

## CLOB API (Prices & Orderbooks)

### Get Price
```
GET /price?token_id=TOKEN_ID&side=buy
GET /price?token_id=TOKEN_ID&side=sell
```

### Get Orderbook
```
GET /book?token_id=TOKEN_ID
```

Response:
```json
{
  "bids": [{"price": "0.64", "size": "500"}],
  "asks": [{"price": "0.66", "size": "300"}]
}
```

### Get Midpoint
```
GET /midpoint?token_id=TOKEN_ID
```

## Data API (Positions & Activity)

### User Positions
```
GET /positions?user=WALLET_ADDRESS
```

### User Activity
```
GET /activity?user=WALLET_ADDRESS&limit=50
```

### Trade History
```
GET /trades?condition_id=CONDITION_ID&limit=100
```

## WebSocket (Real-time)

Connect to: `wss://ws-subscriptions-clob.polymarket.com/ws/`

### Subscribe to Market
```json
{"type": "subscribe", "channel": "market", "market": "TOKEN_ID"}
```

### Unsubscribe
```json
{"type": "unsubscribe", "channel": "market", "market": "TOKEN_ID"}
```

## Data Model

### Event
```json
{
  "id": "123456",
  "slug": "will-bitcoin-reach-100k",
  "title": "Will Bitcoin reach $100k?",
  "active": true,
  "closed": false,
  "markets": [...]
}
```

### Market
```json
{
  "id": "789",
  "question": "Will Bitcoin reach $100k by 2025?",
  "slug": "will-bitcoin-reach-100k-by-2025",
  "clobTokenIds": ["TOKEN_YES", "TOKEN_NO"],
  "outcomes": "[\"Yes\", \"No\"]",
  "outcomePrices": "[\"0.65\", \"0.35\"]",
  "volume": "1234567.89",
  "liquidity": "50000.00"
}
```

### Position
```json
{
  "proxyWallet": "0x...",
  "title": "Market Title",
  "outcome": "Yes",
  "size": 100,
  "avgPrice": 0.45,
  "curPrice": 0.65,
  "currentValue": 65.00,
  "cashPnl": 20.00,
  "percentPnl": 44.4
}
```

## Rate Limits

- Gamma API: 100 requests/minute
- CLOB API: 100 requests/minute
- Data API: 50 requests/minute

## On-Chain Data

For historical/aggregated data, use:
- **Dune Analytics**: https://dune.com/hildobby/polymarket
- **Goldsky**: Real-time streaming to your database
- **Polymarket Subgraph**: GraphQL interface

## Trading (Requires Auth)

Trading requires wallet signature authentication. See:
https://docs.polymarket.com/developers/CLOB/authentication

For retail trading, use browser automation with logged-in session.
