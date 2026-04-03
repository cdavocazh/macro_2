"""
Polymarket prediction market extractor.

Fetches financial/economic prediction market events from Polymarket's
Gamma API (market discovery) and CLOB API (price history).
No API key required — all endpoints are public.
"""

import requests
import json
import time
from datetime import datetime

# ── API endpoints ────────────────────────────────────────────────────────────
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

# ── Tag IDs (confirmed via API) ──────────────────────────────────────────────
FINANCE_TAG = 120
GEOPOLITICS_TAG = 100265
FED_RATES_TAG = 100196
CRYPTO_TAG = 21
POLITICS_TAG = 2
TECH_TAG = 1401

TRENDING_TAGS = {
    POLITICS_TAG: 'Politics',
    CRYPTO_TAG: 'Crypto',
    FINANCE_TAG: 'Finance',
    GEOPOLITICS_TAG: 'Geopolitics',
    TECH_TAG: 'Tech',
}

# ── Keyword filters ─────────────────────────────────────────────────────────
ECONOMY_KEYWORDS = ['inflation', 'fed rate', 'fomc', 'sofr', 'unemployment',
                    'gdp', 'recession', 'interest rate', 'rate cut', 'rate hike',
                    'cpi', 'jobs report', 'nonfarm', 'payroll', 'federal reserve',
                    'ecb', 'boj', 'debt ceiling', 'government shutdown', 'tariff']

FINANCE_KEYWORDS = ['rate cut', 'gold', 'gold price', 'silver', 'spx', 's&p 500',
                    's&p500', 'crude oil', 'oil price', 'nasdaq', 'dow jones',
                    'stock market', 'bitcoin price', 'btc price', 'treasury',
                    'bond', 'yield', 'bitcoin', 'ethereum', 'btc', 'eth',
                    'crypto', 'earnings', 'ipo', 'market cap', 'stock price']

_SESSION = None


def _get_session():
    """Reuse requests session for connection pooling."""
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
        _SESSION.headers.update({'Accept': 'application/json'})
    return _SESSION


def get_events_by_tag(tag_id, limit=50, related_tags=False):
    """Fetch active events for a tag, sorted by 24h volume descending."""
    session = _get_session()
    all_events = []
    offset = 0
    max_pages = 4  # Safety limit

    while len(all_events) < limit and max_pages > 0:
        params = {
            'tag_id': tag_id,
            'active': 'true',
            'closed': 'false',
            'limit': min(limit - len(all_events), 50),
            'offset': offset,
        }
        if related_tags:
            params['related_tags'] = 'true'

        try:
            resp = session.get(f"{GAMMA_BASE}/events", params=params, timeout=15)
            resp.raise_for_status()
            events = resp.json()
        except Exception as e:
            print(f"[Polymarket] Error fetching tag {tag_id} offset {offset}: {e}")
            break

        if not events:
            break

        all_events.extend(events)
        offset += len(events)
        max_pages -= 1
        time.sleep(0.05)

    # Sort by 24h volume descending
    all_events.sort(key=lambda e: float(e.get('volume24hr') or 0), reverse=True)
    return all_events[:limit]


def _matches_keywords(event, keywords):
    """Check if event title or description contains any keyword (case-insensitive)."""
    title = (event.get('title') or '').lower()
    desc = (event.get('description') or '').lower()
    text = title + ' ' + desc
    return any(kw in text for kw in keywords)


def _extract_market_summary(event):
    """Extract a compact summary from an event for dashboard display."""
    markets = event.get('markets', [])

    # For single-market events: get the one market's yes price
    # For multi-market events: find the highest-probability outcome
    best_market = None
    best_yes_price = 0
    yes_token_id = None
    all_outcomes = []

    for m in markets:
        if m.get('closed'):
            continue

        try:
            prices = json.loads(m.get('outcomePrices', '[]'))
            token_ids = json.loads(m.get('clobTokenIds', '[]'))
        except (json.JSONDecodeError, TypeError):
            continue

        if not prices or not token_ids:
            continue

        yes_price = float(prices[0]) if prices else 0

        # Collect all outcomes for multi-market events
        group_title = m.get('groupItemTitle', '')
        question = m.get('question', '')
        outcome_label = group_title or question
        all_outcomes.append({
            'label': outcome_label,
            'yes_price': yes_price,
            'token_id': token_ids[0] if token_ids else None,
        })

        if yes_price > best_yes_price:
            best_yes_price = yes_price
            best_market = m
            yes_token_id = token_ids[0] if token_ids else None

    if not best_market:
        return None

    volume_24h = float(event.get('volume24hr') or 0)

    # Sort outcomes by probability descending, keep top 5
    all_outcomes.sort(key=lambda o: o['yes_price'], reverse=True)

    return {
        'event_id': event.get('id'),
        'title': event.get('title', ''),
        'slug': event.get('slug', ''),
        'yes_price': round(best_yes_price, 4),
        'yes_pct': round(best_yes_price * 100, 1),
        'volume_24h': volume_24h,
        'volume_total': float(event.get('volume') or 0),
        'liquidity': float(event.get('liquidity') or 0),
        'end_date': event.get('endDate', ''),
        'image': event.get('image', ''),
        'yes_token_id': yes_token_id,
        'num_markets': len([m for m in markets if not m.get('closed')]),
        'outcomes': all_outcomes[:8],  # Top 8 outcomes for multi-market events
    }


def get_price_history(token_id, interval='1d'):
    """Fetch price history for a token from the CLOB API.

    Args:
        token_id: The clobTokenId for the Yes outcome
        interval: One of '1h', '6h', '1d', '1w', '1m', 'all'

    Returns:
        List of {t: unix_timestamp, p: price} dicts
    """
    session = _get_session()
    try:
        resp = session.get(
            f"{CLOB_BASE}/prices-history",
            params={'market': token_id, 'interval': interval},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get('history', [])
    except Exception as e:
        print(f"[Polymarket] Error fetching price history: {e}")
        return []


def get_polymarket_snapshot():
    """Fetch the full Polymarket snapshot for all 5 dashboard parts.

    Returns dict with keys:
        part1_fed_rate: Top 10 Fed Rate events
        part2_economy: Top 10 Economy-keyword events from Finance tag
        part3_finance: Top 10 Finance-keyword events from Finance tag
        part4_geopolitics: Top 20 Geopolitics events
        part5_trending: {tag_label: [top 8 events]} for 5 finance-adjacent tags
        latest_date: ISO timestamp
        source: 'Polymarket Gamma API'
    """
    try:
        return _fetch_snapshot()
    except Exception as e:
        return {'error': str(e), 'source': 'Polymarket Gamma API'}


def _fetch_snapshot():
    """Internal: fetch all parts of the snapshot."""
    # ── Part 1: Fed Rate (tag 100196) ────────────────────────────────────
    fed_events = get_events_by_tag(FED_RATES_TAG, limit=20)
    part1 = []
    for e in fed_events:
        summary = _extract_market_summary(e)
        if summary and summary['volume_24h'] > 0:
            part1.append(summary)
    part1 = part1[:10]

    # ── Part 2: Economy keywords from Finance tag ────────────────────────
    finance_events = get_events_by_tag(FINANCE_TAG, limit=100, related_tags=True)
    part2 = []
    for e in finance_events:
        if _matches_keywords(e, ECONOMY_KEYWORDS):
            summary = _extract_market_summary(e)
            if summary and summary['volume_24h'] > 0:
                part2.append(summary)
    part2.sort(key=lambda s: s['volume_24h'], reverse=True)
    part2 = part2[:10]

    # ── Part 3: Finance keywords from Finance tag ────────────────────────
    part3 = []
    for e in finance_events:
        if _matches_keywords(e, FINANCE_KEYWORDS):
            summary = _extract_market_summary(e)
            if summary and summary['volume_24h'] > 0:
                part3.append(summary)
    part3.sort(key=lambda s: s['volume_24h'], reverse=True)
    part3 = part3[:10]

    # ── Part 4: Geopolitics (tag 100265) ─────────────────────────────────
    geo_events = get_events_by_tag(GEOPOLITICS_TAG, limit=50)
    part4 = []
    for e in geo_events:
        summary = _extract_market_summary(e)
        if summary and summary['volume_24h'] > 0:
            part4.append(summary)
    part4 = part4[:20]

    # ── Part 5: Trending (top 8 per finance-adjacent tag) ────────────────
    part5 = {}
    for tag_id, tag_label in TRENDING_TAGS.items():
        # Reuse finance_events for Finance tag to avoid duplicate API call
        if tag_id == FINANCE_TAG:
            tag_events = finance_events
        else:
            tag_events = get_events_by_tag(tag_id, limit=20)

        summaries = []
        for e in tag_events:
            summary = _extract_market_summary(e)
            if summary and summary['volume_24h'] > 0:
                summaries.append(summary)
        summaries.sort(key=lambda s: s['volume_24h'], reverse=True)
        part5[tag_label] = summaries[:8]

    return {
        'part1_fed_rate': part1,
        'part2_economy': part2,
        'part3_finance': part3,
        'part4_geopolitics': part4,
        'part5_trending': part5,
        'latest_date': datetime.now().isoformat(),
        'source': 'Polymarket Gamma API',
    }
