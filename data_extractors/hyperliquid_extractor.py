"""
Data extractors for Hyperliquid perpetual futures & HIP-3 spot tokens.

Fetches perp data (BTC, ETH, SOL, PAXG, etc.) and HIP-3 spot stock tokens
(TSLA, NVDA, AAPL, etc.) from the Hyperliquid REST API.
No API key required. All markets are 24/7.

API: POST https://api.hyperliquid.xyz/info
Docs: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api
"""

import requests
import pandas as pd
from datetime import datetime, timedelta

HL_API_URL = 'https://api.hyperliquid.xyz/info'
HL_TIMEOUT = 10

# ── Perp instruments to track ─────────────────────────────────────────────────
# These are actual perpetual futures on Hyperliquid with meaningful volume.
# PAXG is a gold-backed token that closely tracks gold price.
HL_PERPS = {
    'BTC': {'key': 'btc', 'name': 'Bitcoin', 'category': 'crypto'},
    'ETH': {'key': 'eth', 'name': 'Ethereum', 'category': 'crypto'},
    'SOL': {'key': 'sol', 'name': 'Solana', 'category': 'crypto'},
    'PAXG': {'key': 'paxg', 'name': 'PAX Gold', 'category': 'commodity'},
    'HYPE': {'key': 'hype', 'name': 'Hyperliquid', 'category': 'crypto'},
    'OIL': {'key': 'oil', 'name': 'WTI Crude Oil', 'category': 'commodity',
            'api_coin': 'flx:OIL'},
    'SP500': {'key': 'sp500', 'name': 'S&P 500', 'category': 'index',
              'api_coin': 'xyz:SP500'},
    'NATGAS': {'key': 'natgas', 'name': 'Natural Gas', 'category': 'commodity',
               'api_coin': 'xyz:NATGAS'},
    'COPPER': {'key': 'copper_hl', 'name': 'Copper', 'category': 'commodity',
               'api_coin': 'xyz:COPPER'},
    'BRENTOIL': {'key': 'brentoil', 'name': 'Brent Crude', 'category': 'commodity',
                 'api_coin': 'xyz:BRENTOIL'},
    'XYZ100': {'key': 'xyz100', 'name': 'Nasdaq 100', 'category': 'index',
               'api_coin': 'xyz:XYZ100'},
}

# Builder-deployed perps (flx:OIL, xyz:SP500 etc.) are not in allMids or metaAndAssetCtxs.
# They need the qualified name for candle requests, and their price/volume comes from
# recent candle data instead of allMids.

# Max lookback days by candle interval (respects 5000 candle API limit)
HL_INTERVAL_LOOKBACK = {
    '1m': 3, '3m': 10, '5m': 17, '15m': 52, '30m': 90,
    '1h': 90, '2h': 90, '4h': 90, '8h': 90, '12h': 90,
    '1d': 90, '3d': 90, '1w': 90, '1M': 90,
}

# ── HIP-3 spot stock tokens (Wagyu.xyz deployed) ─────────────────────────────
# These are tokenized equities on Hyperliquid spot.
# Spot pairs use @{index} naming; we map token index → ticker.
HL_SPOT_STOCKS = {
    'TSLA': {'index': 407, 'name': 'Tesla'},
    'NVDA': {'index': 408, 'name': 'Nvidia'},
    'AAPL': {'index': 413, 'name': 'Apple'},
    'GOOGL': {'index': 412, 'name': 'Alphabet'},
    'AMZN': {'index': 421, 'name': 'Amazon'},
    'META': {'index': 422, 'name': 'Meta'},
    'MSFT': {'index': 429, 'name': 'Microsoft'},
    'SPY': {'index': 420, 'name': 'S&P 500 ETF'},
    'QQQ': {'index': 426, 'name': 'Nasdaq 100 ETF'},
}


def _hl_post(body):
    """POST to Hyperliquid info endpoint."""
    resp = requests.post(HL_API_URL, json=body, timeout=HL_TIMEOUT,
                         headers={'Content-Type': 'application/json'})
    resp.raise_for_status()
    return resp.json()


def get_hl_all_mids():
    """Fetch all mid prices. Returns dict like {'BTC': '70200.5', 'ETH': '2177.7', ...}."""
    return _hl_post({"type": "allMids"})


def get_hl_meta_and_contexts():
    """
    Fetch perp metadata + per-asset contexts (funding, OI, volume, mark price).
    Returns dict keyed by coin name.
    """
    raw = _hl_post({"type": "metaAndAssetCtxs"})
    meta = raw[0]
    ctxs = raw[1]
    universe = meta.get('universe', [])

    result = {}
    for i, asset_meta in enumerate(universe):
        coin = asset_meta.get('name', '')
        if i < len(ctxs):
            ctx = ctxs[i]
            result[coin] = {
                'funding': ctx.get('funding', '0'),
                'open_interest': ctx.get('openInterest', '0'),
                'volume_24h': ctx.get('dayNtlVlm', '0'),
                'mark_price': ctx.get('markPx', '0'),
                'oracle_price': ctx.get('oraclePx', '0'),
                'prev_day_px': ctx.get('prevDayPx', '0'),
                'premium': ctx.get('premium', '0'),
                'max_leverage': asset_meta.get('maxLeverage', 0),
            }
    return result


def get_hl_spot_meta():
    """
    Fetch HIP-3 spot token metadata + contexts.
    Returns (tokens_by_index, universe_pairs, pair_contexts).
    """
    raw = _hl_post({"type": "spotMetaAndAssetCtxs"})
    tokens = raw[0].get('tokens', [])
    universe = raw[0].get('universe', [])
    ctxs = raw[1]

    tokens_by_idx = {}
    for t in tokens:
        tokens_by_idx[t.get('index', -1)] = t

    return tokens_by_idx, universe, ctxs


def get_hl_candles(coin, interval='1d', lookback_days=None):
    """
    Fetch OHLCV candles for a perp coin.
    Returns pd.DataFrame with Open, High, Low, Close, Volume columns.

    Supported intervals: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 8h, 12h, 1d, 3d, 1w, 1M
    Max 5000 candles per request. lookback_days auto-capped per interval if not specified.
    """
    if lookback_days is None:
        lookback_days = HL_INTERVAL_LOOKBACK.get(interval, 90)
    else:
        max_days = HL_INTERVAL_LOOKBACK.get(interval, 90)
        lookback_days = min(lookback_days, max_days)

    end_ms = int(datetime.now().timestamp() * 1000)
    start_ms = int((datetime.now() - timedelta(days=lookback_days)).timestamp() * 1000)

    data = _hl_post({
        "type": "candleSnapshot",
        "req": {
            "coin": coin,
            "interval": interval,
            "startTime": start_ms,
            "endTime": end_ms,
        }
    })

    if not data:
        return pd.DataFrame()

    rows = []
    for c in data:
        rows.append({
            'timestamp': pd.Timestamp(c['t'], unit='ms'),
            'Open': float(c['o']),
            'High': float(c['h']),
            'Low': float(c['l']),
            'Close': float(c['c']),
            'Volume': float(c['v']),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df = df.set_index('timestamp').sort_index()
    # Only strip timezone; do NOT normalize to midnight (would collapse intraday candles)
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep='last')]
    return df


def _build_perp_data(coin, mids, contexts, fetch_candles=True, lookback_days=90,
                     builder_ohlcv_cache=None):
    """Build standard instrument dict for a single perp coin.

    Args:
        builder_ohlcv_cache: pre-fetched {api_coin: DataFrame} for builder perps.
            Avoids redundant API calls when called from get_hl_perps().
    """
    info = HL_PERPS.get(coin, {})
    display_name = info.get('name', coin)
    api_coin = info.get('api_coin', coin)  # Qualified name for builder perps
    is_builder = 'api_coin' in info

    mid_str = mids.get(coin)

    # Builder-deployed perps are not in allMids — use pre-fetched OHLCV or fetch 1d candle
    if mid_str is None and is_builder:
        ohlcv = (builder_ohlcv_cache or {}).get(api_coin, pd.DataFrame())
        if not ohlcv.empty:
            mid_str = str(ohlcv['Close'].iloc[-1])
        if mid_str is None:
            return {'error': f'{coin} not found on Hyperliquid'}

    if mid_str is None:
        return {'error': f'{coin} not found on Hyperliquid'}

    price = float(mid_str)
    ctx = contexts.get(coin, {})

    funding_raw = float(ctx.get('funding', '0'))
    funding_annualized = funding_raw * 3 * 365 * 100

    oi_usd = float(ctx.get('open_interest', '0'))
    volume_24h = float(ctx.get('volume_24h', '0'))
    mark_price = float(ctx.get('mark_price', '0'))
    oracle_price = float(ctx.get('oracle_price', '0'))
    prev_day_px = float(ctx.get('prev_day_px', '0'))

    # For builder perps without context, derive change/volume from pre-fetched 1d candle
    if not ctx and is_builder:
        ohlcv = (builder_ohlcv_cache or {}).get(api_coin, pd.DataFrame())
        if len(ohlcv) >= 2:
            prev_day_px = ohlcv['Close'].iloc[-2]
            volume_24h = ohlcv['Volume'].iloc[-1]

    premium = 0.0
    if oracle_price > 0:
        premium = (mark_price - oracle_price) / oracle_price * 100

    change_24h = 0.0
    if prev_day_px > 0:
        change_24h = (price - prev_day_px) / prev_day_px * 100

    result = {
        'price': price,
        'change_24h': round(change_24h, 2),
        'change_1d': round(change_24h, 2),
        'mark_price': mark_price if mark_price > 0 else price,
        'oracle_price': oracle_price,
        'funding_rate': round(funding_annualized, 2),
        'funding_rate_8h': round(funding_raw * 100, 6),
        'open_interest': round(oi_usd, 2),
        'volume_24h': round(volume_24h, 2),
        'premium': round(premium, 4),
        'max_leverage': ctx.get('max_leverage', 0),
        'latest_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
        'source': 'Hyperliquid',
        'note': f'{display_name} perp | Funding: {funding_annualized:+.1f}% ann.',
        'api_coin': api_coin,
    }

    if fetch_candles:
        # Reuse pre-fetched OHLCV for builder perps
        ohlcv = (builder_ohlcv_cache or {}).get(api_coin, pd.DataFrame()) if is_builder else pd.DataFrame()
        if ohlcv.empty:
            try:
                import time
                time.sleep(0.2)  # Rate limit: 200ms between candle requests
                ohlcv = get_hl_candles(api_coin, interval='1d', lookback_days=lookback_days)
            except Exception:
                pass
        if not ohlcv.empty:
            result['historical'] = ohlcv['Close']
            result['historical_ohlcv'] = ohlcv

    return result


def get_hl_perps():
    """
    Fetch Hyperliquid perpetual futures data for tracked instruments.
    Returns nested dict: {'btc': {...}, 'eth': {...}, 'paxg': {...}, ...}
    Indicator key: 84_hl_perps

    Optimized to minimize API calls:
    - 2 initial calls (allMids + metaAndAssetCtxs)
    - 1 candle call per instrument (with 200ms spacing to avoid 429)
    - Builder perps reuse their 1d candle for price, change, AND history
    """
    import time

    try:
        mids = get_hl_all_mids()
        contexts = get_hl_meta_and_contexts()
    except Exception as e:
        return {'error': f'Hyperliquid API error: {str(e)}'}

    # Pre-fetch 1d candles for builder perps (one call per builder, reused for
    # price derivation, change calculation, AND historical chart)
    builder_ohlcv_cache = {}
    for hl_ticker, info in HL_PERPS.items():
        api_coin = info.get('api_coin')
        if api_coin:
            try:
                time.sleep(0.2)  # 200ms rate limit between calls
                ohlcv = get_hl_candles(api_coin, interval='1d', lookback_days=90)
                if not ohlcv.empty:
                    builder_ohlcv_cache[api_coin] = ohlcv
            except Exception:
                pass

    result = {}
    for hl_ticker, info in HL_PERPS.items():
        key = info['key']
        is_builder = 'api_coin' in info
        try:
            result[key] = _build_perp_data(
                hl_ticker, mids, contexts,
                fetch_candles=True, lookback_days=90,
                builder_ohlcv_cache=builder_ohlcv_cache,
            )
        except Exception as e:
            result[key] = {'error': f'{info["name"]}: {str(e)}'}
        # Rate limit between standard perp candle fetches too
        if not is_builder:
            time.sleep(0.2)

    result['latest_date'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    result['source'] = 'Hyperliquid'
    return result


def get_hl_spot_stocks():
    """
    Fetch HIP-3 tokenized stock data from Hyperliquid spot markets.
    Returns nested dict: {'tsla': {...}, 'nvda': {...}, ...}
    Indicator key: 85_hl_spot_stocks

    Note: HIP-3 stocks are deployed by Wagyu.xyz. Spot pairs use @{index}
    naming convention. Many have low/zero liquidity.
    """
    try:
        tokens_by_idx, universe, ctxs = get_hl_spot_meta()
    except Exception as e:
        return {'error': f'Hyperliquid API error: {str(e)}'}

    # Build mapping: token_index → universe pair index + context
    pair_for_token = {}
    for i, u in enumerate(universe):
        tok_list = u.get('tokens', [])
        for ti in tok_list:
            if ti != 0:  # token 0 is USDC
                pair_for_token[ti] = (i, u, ctxs[i] if i < len(ctxs) else {})

    result = {}
    for ticker, info in HL_SPOT_STOCKS.items():
        key = ticker.lower()
        idx = info['index']
        pair_info = pair_for_token.get(idx)

        if pair_info is None:
            result[key] = {'error': f'{ticker} spot pair not found'}
            continue

        pair_idx, pair_meta, ctx = pair_info
        mid_px = ctx.get('midPx')
        vol = float(ctx.get('dayNtlVlm', '0'))
        prev_day_px_str = ctx.get('prevDayPx', '0')
        prev_day_px = float(prev_day_px_str) if prev_day_px_str else 0

        if mid_px is None or mid_px == 'N/A':
            result[key] = {
                'error': f'{ticker} no mid price (possibly no liquidity)',
                'volume_24h': vol,
            }
            continue

        price = float(mid_px)
        change_24h = 0.0
        if prev_day_px > 0:
            change_24h = (price - prev_day_px) / prev_day_px * 100

        result[key] = {
            'price': price,
            'change_24h': round(change_24h, 2),
            'change_1d': round(change_24h, 2),
            'volume_24h': round(vol, 2),
            'latest_date': datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),
            'source': 'Hyperliquid HIP-3',
            'note': f'{info["name"]} (Wagyu.xyz) | Vol: ${vol:,.0f}',
            'spot_pair': pair_meta.get('name', ''),
        }

    result['latest_date'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    result['source'] = 'Hyperliquid HIP-3'
    return result


def get_hl_snapshot():
    """
    Lightweight snapshot: allMids + metaAndAssetCtxs only (no candle history).
    Used by hl_extract.py for minutely updates (~0.5s, 2 HTTP calls for perps).
    Returns tuple: (perps_dict, spot_stocks_dict)
    """
    # Perps snapshot
    perps = {}
    try:
        mids = get_hl_all_mids()
        contexts = get_hl_meta_and_contexts()
        for hl_ticker, info in HL_PERPS.items():
            key = info['key']
            try:
                perps[key] = _build_perp_data(hl_ticker, mids, contexts,
                                               fetch_candles=False)
            except Exception as e:
                perps[key] = {'error': str(e)}
        perps['latest_date'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
        perps['source'] = 'Hyperliquid'
    except Exception as e:
        perps = {'error': f'Hyperliquid API error: {str(e)}'}

    # Spot stocks snapshot
    spot_stocks = {}
    try:
        spot_stocks = get_hl_spot_stocks()
    except Exception as e:
        spot_stocks = {'error': f'Hyperliquid API error: {str(e)}'}

    return perps, spot_stocks
