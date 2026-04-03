# Polymarket Financial Bets Extraction Plan

## Goal

Extract all prediction market bets related to financial/economic data from Polymarket, store them locally, and integrate with the macro_2 dashboard ecosystem.

---

## 1. API Architecture Overview

Polymarket exposes four services. **No authentication needed for read-only data.**

| Service | Base URL | Use Case |
|---------|----------|----------|
| **Gamma API** | `https://gamma-api.polymarket.com` | Market discovery, metadata, tags, search |
| **CLOB API** | `https://clob.polymarket.com` | Orderbook, live pricing, historical prices |
| **Data API** | `https://data-api.polymarket.com` | User positions, trades, leaderboards |
| **WebSocket** | `wss://ws-subscriptions-clob.polymarket.com` | Real-time price/trade streams |

We only need **Gamma** (discovery) and **CLOB** (pricing/history) for this project.

---

## 2. Identifying Financial Markets

### 2.1 Primary Filter: Tag ID

The Gamma API supports filtering by category tag. Key tag IDs:

| Category | `tag_id` |
|----------|----------|
| **Finance** | **120** |
| **Crypto** | **21** |
| Economics (subtag) | TBD — discover via `/tags/120/related-tags` |

### 2.2 Discovery Endpoints

```
# All active finance markets, sorted by 24h volume
GET /events?tag_id=120&active=true&closed=false&order=volume_24hr&ascending=false&limit=50

# Search for specific financial topics
GET /public-search?query=federal+reserve
GET /public-search?query=interest+rate
GET /public-search?query=recession
GET /public-search?query=S%26P+500
GET /public-search?query=inflation

# Get related tags to "Finance" for broader coverage
GET /tags/120/related-tags
```

### 2.3 Financial Topic Keywords

To ensure comprehensive coverage, search for markets matching these terms:

| Category | Keywords |
|----------|----------|
| Central Banks | `federal reserve`, `fed`, `interest rate`, `rate cut`, `rate hike`, `ECB`, `BOJ` |
| Indices | `S&P 500`, `nasdaq`, `dow jones`, `stock market`, `bitcoin price` |
| Macro | `recession`, `GDP`, `inflation`, `CPI`, `unemployment`, `jobs report` |
| Commodities | `oil price`, `gold price`, `crude oil` |
| Crypto | `bitcoin`, `ethereum`, `crypto`, `BTC`, `ETH` |
| Corporate | `earnings`, `IPO`, `market cap`, `stock price` |
| Fiscal | `debt ceiling`, `government shutdown`, `tariff` |

---

## 3. Data Model

### 3.1 Fields to Extract per Market

From the **Gamma API** `/events` and `/markets` responses:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Market unique ID |
| `question` | string | The bet question (e.g., "Will the Fed cut rates in June 2026?") |
| `slug` | string | URL-friendly identifier |
| `description` | string | Full market description with resolution criteria |
| `outcomes` | string[] | Outcome names (e.g., `["Yes", "No"]`) |
| `outcomePrices` | string | Current prices per outcome (e.g., `["0.72", "0.28"]`) |
| `volume` | string | Total lifetime volume (USD) |
| `volumeNum` | float | Numeric volume |
| `volume24hr` | float | 24-hour trading volume |
| `liquidity` | string | Current liquidity depth |
| `liquidityNum` | float | Numeric liquidity |
| `lastTradePrice` | float | Most recent trade price |
| `startDate` / `endDate` | string | Market lifetime |
| `active` | boolean | Currently tradable |
| `closed` | boolean | Market resolved/closed |
| `category` | string | Category label |
| `conditionId` | string | CTF contract condition ID (needed for CLOB queries) |
| `clobTokenIds` | string | Token IDs for Yes/No outcomes (needed for price history) |

### 3.2 Fields to Extract per Price History

From the **CLOB API** `/prices-history`:

| Field | Type | Description |
|-------|------|-------------|
| `t` | int | Unix timestamp |
| `p` | float | Price at that timestamp (0.0 - 1.0 = probability) |

---

## 4. Implementation Plan

### Phase 1: Market Discovery & Snapshot

**File:** `polymarket_extractor.py`

```python
# Step 1: Fetch all finance-tagged events
def get_financial_markets() -> list[dict]:
    """
    Fetch all markets tagged as Finance (tag_id=120).
    Paginate through results (limit=50, offset increments).
    Also search by keyword list for markets that may not be tagged Finance.
    Deduplicate by market ID.
    """

# Step 2: Enrich with related tags
def get_related_financial_tags() -> list[int]:
    """
    GET /tags/120/related-tags to find subtags
    (e.g., Economics, Crypto, Stocks).
    Return list of tag_ids to also query.
    """

# Step 3: Keyword search fallback
def search_financial_markets(keywords: list[str]) -> list[dict]:
    """
    GET /public-search?query={keyword} for each keyword.
    Merge with tag-based results, deduplicate.
    """
```

### Phase 2: Price History Extraction

```python
# Step 4: Get historical prices for each market
def get_price_history(token_id: str, interval: str = "1d") -> pd.DataFrame:
    """
    GET https://clob.polymarket.com/prices-history
    Params: market={token_id}, interval=1d, startTs=..., endTs=...
    Returns DataFrame with columns: [timestamp, price]
    """

# Step 5: Get current orderbook snapshot
def get_orderbook(token_id: str) -> dict:
    """
    GET https://clob.polymarket.com/book?token_id={token_id}
    Returns bids, asks, spread, midpoint.
    """
```

### Phase 3: Storage & Caching

**Directory structure:**

```
data_cache/
  polymarket/
    markets.json              # All financial market metadata (refreshed daily)
    price_history/
      {market_id}_yes.csv     # Daily price history for Yes token
      {market_id}_no.csv      # Daily price history for No token

data_export/
  polymarket_financial_bets.csv   # Flat summary export
```

**Cache strategy:**
- Market metadata: refresh every 4 hours (new markets appear, prices change)
- Price history: append-only CSVs, deduplicated by timestamp
- Use same `_serialize_value()` / `_deserialize_value()` pattern as existing extractors

### Phase 4: Classification & Filtering

Not all markets tagged "Finance" are macro-relevant. Apply a secondary filter:

```python
MACRO_CATEGORIES = {
    "rates": ["fed", "interest rate", "rate cut", "rate hike", "fomc", "ecb", "boj"],
    "indices": ["s&p", "nasdaq", "dow", "stock market", "spy", "qqq"],
    "macro": ["recession", "gdp", "inflation", "cpi", "unemployment", "jobs", "nonfarm"],
    "commodities": ["oil", "gold", "crude", "natural gas", "copper"],
    "crypto": ["bitcoin", "ethereum", "btc", "eth", "crypto"],
    "fiscal": ["debt ceiling", "shutdown", "tariff", "treasury"],
    "corporate": ["earnings", "ipo", "market cap", "revenue"],
}

def classify_market(market: dict) -> str | None:
    """
    Match market question against MACRO_CATEGORIES keywords.
    Returns category string or None if not macro-relevant.
    """
```

### Phase 5: Integration with macro_2 Dashboard

**Option A — New indicator in `data_aggregator.py`:**
- Register as indicator key `86_polymarket_financial`
- Return dict with top markets, prices, volumes
- Display in Tab 2 (Market Indices) or new Tab 9

**Option B — Standalone extraction script:**
- `polymarket_extract.py` (similar to `hl_extract.py`)
- Runs on its own schedule (every 15 min or hourly)
- Merges into `all_indicators.json` cache

**Recommended: Option B** — keeps it decoupled, avoids slowing down main extraction.

---

## 5. Rate Limit Management

| Endpoint | Limit | Strategy |
|----------|-------|----------|
| `GET /events` | 500/10s | Paginate with 50/page, ~10 pages max, well within limit |
| `GET /markets` | 300/10s | Use `/events` instead (includes nested markets) |
| `GET /public-search` | 350/10s | Batch keywords with 0.5s delay between |
| `GET /prices-history` | 1000/10s | Batch with 0.1s delay, ~100 markets feasible |
| `GET /book` | 1500/10s | Only fetch for top markets by volume |

**Total estimated extraction time:** ~30-60 seconds for full snapshot.

---

## 6. Extraction Script Skeleton

```python
#!/usr/bin/env python3
"""
polymarket_extract.py — Extract financial prediction markets from Polymarket.
No API key required. Read-only Gamma + CLOB APIs.
"""

import requests
import pandas as pd
import json
import time
from pathlib import Path

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
FINANCE_TAG_ID = 120
CRYPTO_TAG_ID = 21

CACHE_DIR = Path("data_cache/polymarket")
EXPORT_DIR = Path("data_export")

def fetch_events_by_tag(tag_id: int, active=True, limit=50) -> list[dict]:
    """Paginate through all events for a given tag."""
    all_events = []
    offset = 0
    while True:
        params = {
            "tag_id": tag_id,
            "active": str(active).lower(),
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": limit,
            "offset": offset,
        }
        resp = requests.get(f"{GAMMA_BASE}/events", params=params)
        resp.raise_for_status()
        events = resp.json()
        if not events:
            break
        all_events.extend(events)
        offset += limit
        time.sleep(0.1)
    return all_events

def search_markets(query: str) -> list[dict]:
    """Search for markets by keyword."""
    resp = requests.get(f"{GAMMA_BASE}/public-search", params={"query": query})
    resp.raise_for_status()
    return resp.json()

def get_price_history(token_id: str, interval="1d") -> list[dict]:
    """Get historical price timeseries for a token."""
    resp = requests.get(f"{CLOB_BASE}/prices-history", params={
        "market": token_id,
        "interval": interval,
    })
    resp.raise_for_status()
    return resp.json().get("history", [])

def extract_all():
    # 1. Discover finance + crypto markets
    finance_events = fetch_events_by_tag(FINANCE_TAG_ID)
    crypto_events = fetch_events_by_tag(CRYPTO_TAG_ID)

    # 2. Keyword search for uncategorized financial markets
    keywords = ["federal reserve", "interest rate", "recession", "S&P 500",
                "inflation", "GDP", "unemployment", "tariff", "bitcoin price"]
    search_results = []
    for kw in keywords:
        search_results.extend(search_markets(kw))
        time.sleep(0.3)

    # 3. Deduplicate, classify, store
    # 4. Fetch price history for top N markets
    # 5. Save to cache + export CSV

if __name__ == "__main__":
    extract_all()
```

---

## 7. Output Format

### `polymarket_financial_bets.csv`

| Column | Description |
|--------|-------------|
| `market_id` | Unique market ID |
| `question` | The prediction question |
| `category` | Classified category (rates, indices, macro, etc.) |
| `yes_price` | Current Yes probability (0-1) |
| `no_price` | Current No probability (0-1) |
| `volume_total` | Lifetime volume in USD |
| `volume_24h` | 24-hour volume |
| `liquidity` | Current liquidity |
| `end_date` | Market resolution date |
| `active` | Whether market is still tradable |
| `slug` | URL slug (construct full URL: `https://polymarket.com/event/{slug}`) |
| `last_updated` | Extraction timestamp |

### Cache JSON structure (in `all_indicators.json`)

```json
{
  "86_polymarket_financial": {
    "source": "Polymarket Gamma API",
    "latest_date": "2026-03-22",
    "total_markets": 47,
    "total_volume_24h": 1250000,
    "top_markets": [
      {
        "question": "Will the Fed cut rates in June 2026?",
        "yes_price": 0.72,
        "volume_24h": 450000,
        "category": "rates",
        "end_date": "2026-06-18"
      }
    ],
    "by_category": {
      "rates": 12,
      "indices": 8,
      "macro": 15,
      "crypto": 7,
      "fiscal": 5
    }
  }
}
```

---

## 8. Schedule

| Frequency | What | Why |
|-----------|------|-----|
| Every 15 min | Market prices snapshot | Odds change with news |
| Every 4 hours | Full market discovery | New markets created |
| Daily | Price history append | Build historical timeseries |

Add to `setup_launchd.sh` as a 4th launchd job: `com.macro2.polymarket-extract.plist`.

---

## 9. Dependencies

```
requests          # Already in requirements.txt
pandas            # Already in requirements.txt
```

No new dependencies needed. No API key required.

---

## 10. Implementation Order

1. **`polymarket_extractor.py`** in `data_extractors/` — core extraction functions
2. **`polymarket_extract.py`** in root — standalone script (like `hl_extract.py`)
3. **Cache merge** — write to `data_cache/polymarket/` + merge key 86 into `all_indicators.json`
4. **CSV export** — `data_export/polymarket_financial_bets.csv`
5. **Dashboard display** — add to React/Dash/Streamlit Tab 2 or new tab
6. **launchd job** — `com.macro2.polymarket-extract.plist` for scheduled extraction
7. **Historical price CSVs** — `historical_data/polymarket/{market_slug}_yes.csv`
