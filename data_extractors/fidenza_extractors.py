"""
Fidenza Macro gap-fill extractors.

Instruments and indicators referenced in Fidenza Macro newsletters
(Sep 2025 – Mar 2026) but not previously tracked in the dashboard.

Groups:
  - yfinance-based: Brent crude, Nikkei 225, EM indices, SOFR/FF futures
  - Computed: XAU/JPY, Gold/Silver ratio
  - Web scrape: AAII sentiment survey
  - Complex: OPEC production, gold reserves share
"""

import os
import re
import yfinance as yf
import requests
import pandas as pd
from datetime import datetime, timedelta
from bs4 import BeautifulSoup


# ──────────────────────────────────────────────────────────────────────────────
# Helper: generic yfinance price fetcher (replicates commodities_extractors
#         pattern without importing to keep this module self-contained)
# ──────────────────────────────────────────────────────────────────────────────

def _yf_price(symbol, name, key=None, period_days=365, include_ohlcv=False):
    """Fetch latest price + history for a yfinance ticker.

    Args:
        symbol: yfinance ticker (e.g., 'BZ=F', '^N225')
        name: human-readable label
        key: dict key for the latest value (defaults to snake_case of name)
        period_days: primary history window in days (default 365)
        include_ohlcv: if True, also return 'historical_ohlcv' DataFrame

    Returns:
        dict with {key, latest_date, change_1d, historical, source}
        or dict with 'error' on failure.
    """
    if key is None:
        key = name.lower().replace(' ', '_').replace('-', '_')

    try:
        ticker = yf.Ticker(symbol)

        # Use period='2y' for 730+ day requests, else explicit date range
        if period_days >= 730:
            hist = ticker.history(period='2y')
        else:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            # Retry with longer window
            end_date = datetime.now()
            start_date = end_date - timedelta(days=730)
            hist = ticker.history(start=start_date, end=end_date)

        if hist.empty:
            return {'error': f'No data available for {name} ({symbol})'}

        close = hist['Close']
        latest = float(close.iloc[-1])
        latest_date = close.index[-1]

        change_1d = 0.0
        if len(close) > 1:
            prev = float(close.iloc[-2])
            if prev != 0:
                change_1d = round(((latest / prev) - 1) * 100, 2)

        result = {
            key: round(latest, 2),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'change_1d': change_1d,
            'historical': close,
            'source': f'yfinance ({symbol})',
        }

        if include_ohlcv:
            ohlcv = hist[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
            if hasattr(ohlcv.index, 'tz') and ohlcv.index.tz is not None:
                ohlcv.index = ohlcv.index.tz_localize(None)
            ohlcv.index = ohlcv.index.normalize()
            result['historical_ohlcv'] = ohlcv

        return result
    except Exception as e:
        return {'error': f'Error fetching {name}: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 1. Brent Crude Oil Futures
# ──────────────────────────────────────────────────────────────────────────────

def get_brent_crude():
    """Get Brent Crude Oil (BZ=F) futures continuous contract data with 2-year OHLCV."""
    return _yf_price('BZ=F', 'Brent Crude', key='price', period_days=730, include_ohlcv=True)


# ──────────────────────────────────────────────────────────────────────────────
# 2. Nikkei 225 Index
# ──────────────────────────────────────────────────────────────────────────────

def get_nikkei_225():
    """Get Nikkei 225 index (^N225) data."""
    return _yf_price('^N225', 'Nikkei 225', key='nikkei_225')


# ──────────────────────────────────────────────────────────────────────────────
# 3. Emerging Market Indices (batch)
# ──────────────────────────────────────────────────────────────────────────────

def get_em_indices():
    """Get EM index data: KOSPI (^KS11), Bovespa (^BVSP), MSCI EM proxy (EEM).

    Returns all three in one call to minimise API overhead.
    """
    indices = {
        '^KS11': ('kospi', 'KOSPI (S. Korea)'),
        '^BVSP': ('bovespa', 'Bovespa (Brazil)'),
        'EEM':   ('msci_em', 'MSCI EM (EEM proxy)'),
    }

    result = {'source': 'yfinance'}
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    for symbol, (key, label) in indices.items():
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date)
            if hist.empty:
                hist = ticker.history(start=end_date - timedelta(days=730), end=end_date)
            if not hist.empty:
                close = hist['Close']
                latest = float(close.iloc[-1])
                prev = float(close.iloc[-2]) if len(close) > 1 else latest
                change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0
                result[key] = round(latest, 2)
                result[f'{key}_change_1d'] = change
                result[f'historical_{key}'] = close
                result['latest_date'] = close.index[-1].strftime('%Y-%m-%d')
            else:
                result[key] = None
        except Exception as e:
            result[key] = None

    # If nothing worked at all, return error
    if all(result.get(k) is None for k in ('kospi', 'bovespa', 'msci_em')):
        return {'error': 'No EM index data available'}

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 4. SOFR Futures Term Structure
# ──────────────────────────────────────────────────────────────────────────────

def _generate_sofr_contract_tickers():
    """Generate SOFR 3-month futures tickers for the next 8 quarterly expiries.

    CME month codes: H=Mar, M=Jun, U=Sep, Z=Dec
    Ticker format: SR3{code}{yy}.CME  (e.g. SR3H26.CME = Mar 2026)
    """
    month_map = {3: 'H', 6: 'M', 9: 'U', 12: 'Z'}
    now = datetime.now()
    tickers = []

    for offset in range(8):
        # Next quarterly month starting from the current quarter end
        quarter_num = (now.month - 1) // 3 + 1 + offset
        target_month = ((quarter_num - 1) % 4 + 1) * 3
        target_year = now.year + (quarter_num - 1) // 4

        code = month_map[target_month]
        yr = str(target_year)[-2:]
        tickers.append(f'SR3{code}{yr}.CME')

    return tickers


def get_sofr_futures_term_structure():
    """Get SOFR futures term structure from CME via yfinance.

    Tries generic front-month (SR3=F) plus specific quarterly contracts.
    Implied rate = 100 − price.

    Returns:
        dict with 'contracts' list, each having:
            contract, price, implied_rate, latest_date, historical (pd.Series)
        OR dict with 'error' key.
    """
    try:
        # Build candidate ticker list
        candidates = ['SR3=F'] + _generate_sofr_contract_tickers()

        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)

        contracts = []
        for symbol in candidates:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date)
                if hist.empty:
                    continue
                close = hist['Close']
                latest = float(close.iloc[-1])
                contracts.append({
                    'contract': symbol.replace('.CME', '').replace('=F', '_front'),
                    'price': round(latest, 4),
                    'implied_rate': round(100 - latest, 4),
                    'latest_date': close.index[-1].strftime('%Y-%m-%d'),
                    'historical': close,
                })
            except Exception:
                continue

        if not contracts:
            return {'error': 'No SOFR futures data available from yfinance'}

        return {
            'contracts': contracts,
            'source': 'CME via yfinance',
            'latest_date': contracts[0]['latest_date'],
        }
    except Exception as e:
        return {'error': f'Error fetching SOFR futures: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 5. Fed Funds Futures
# ──────────────────────────────────────────────────────────────────────────────

def get_fed_funds_futures():
    """Get Fed Funds Futures (ZQ=F) generic front-month.

    Implied rate = 100 − price.
    """
    try:
        result = _yf_price('ZQ=F', 'Fed Funds Futures', key='price')
        if 'error' in result:
            return result
        # Add implied rate
        result['implied_rate'] = round(100 - result['price'], 4)
        return result
    except Exception as e:
        return {'error': f'Error fetching Fed Funds futures: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 6. XAU/JPY — Gold priced in Japanese Yen
# ──────────────────────────────────────────────────────────────────────────────

def get_xau_jpy():
    """Compute Gold in JPY: GC=F (gold USD) × JPY=X (USD/JPY).

    Uses aligned daily close prices for the product.
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        gold = yf.Ticker('GC=F').history(start=start_date, end=end_date)['Close']
        jpy = yf.Ticker('JPY=X').history(start=start_date, end=end_date)['Close']

        if gold.empty or jpy.empty:
            return {'error': 'No data for GC=F or JPY=X'}

        # Align on common dates (strip timezone before joining)
        gold.index = gold.index.tz_localize(None).normalize()
        jpy.index = jpy.index.tz_localize(None).normalize()
        combined = pd.DataFrame({'gold': gold, 'jpy': jpy}).dropna()

        if combined.empty:
            return {'error': 'No overlapping dates for GC=F and JPY=X'}

        xau_jpy = combined['gold'] * combined['jpy']
        latest = float(xau_jpy.iloc[-1])
        prev = float(xau_jpy.iloc[-2]) if len(xau_jpy) > 1 else latest
        change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0

        return {
            'xau_jpy': round(latest, 0),
            'latest_date': xau_jpy.index[-1].strftime('%Y-%m-%d'),
            'change_1d': change,
            'historical': xau_jpy,
            'source': 'yfinance (GC=F × JPY=X)',
            'units': 'JPY per troy oz',
        }
    except Exception as e:
        return {'error': f'Error computing XAU/JPY: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 7. Gold/Silver Ratio
# ──────────────────────────────────────────────────────────────────────────────

def get_gold_silver_ratio():
    """Compute Gold/Silver ratio: GC=F / SI=F.

    Rising = silver underperformance (risk-off).
    Falling = silver outperformance (risk-on).
    """
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        gold = yf.Ticker('GC=F').history(start=start_date, end=end_date)['Close']
        silver = yf.Ticker('SI=F').history(start=start_date, end=end_date)['Close']

        if gold.empty or silver.empty:
            return {'error': 'No data for GC=F or SI=F'}

        gold.index = gold.index.tz_localize(None).normalize()
        silver.index = silver.index.tz_localize(None).normalize()
        combined = pd.DataFrame({'gold': gold, 'silver': silver}).dropna()

        if combined.empty:
            return {'error': 'No overlapping dates for GC=F and SI=F'}

        ratio = combined['gold'] / combined['silver']
        latest = float(ratio.iloc[-1])
        prev = float(ratio.iloc[-2]) if len(ratio) > 1 else latest
        change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0

        return {
            'gold_silver_ratio': round(latest, 2),
            'latest_date': ratio.index[-1].strftime('%Y-%m-%d'),
            'change_1d': change,
            'historical': ratio,
            'source': 'yfinance (GC=F / SI=F)',
        }
    except Exception as e:
        return {'error': f'Error computing Gold/Silver ratio: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 8. AAII Bull/Bear Sentiment Survey
# ──────────────────────────────────────────────────────────────────────────────

_AAII_URL = 'https://www.aaii.com/sentimentsurvey'
_AAII_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/120.0.0.0 Safari/537.36'),
}


def get_aaii_sentiment():
    """Scrape AAII Investor Sentiment Survey.

    Parses bullish / neutral / bearish percentages from the survey page
    and computes the bull/bear ratio.

    Returns:
        dict with bullish, neutral, bearish, bull_bear_ratio, latest_date, source
        OR dict with 'error'.
    """
    try:
        resp = requests.get(_AAII_URL, headers=_AAII_HEADERS, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # Strategy 1: regex for percentage values near sentiment words
        bullish = neutral = bearish = None

        # Look for patterns like "Bullish: 38.5%" or "bullish</...>38.5%"
        for label, setter in [
            (r'[Bb]ullish', 'bullish'),
            (r'[Nn]eutral', 'neutral'),
            (r'[Bb]earish', 'bearish'),
        ]:
            # Pattern A: label followed by colon/space then percentage
            m = re.search(label + r'[:\s]*(\d+\.?\d*)%', text)
            if m:
                if setter == 'bullish':
                    bullish = float(m.group(1))
                elif setter == 'neutral':
                    neutral = float(m.group(1))
                elif setter == 'bearish':
                    bearish = float(m.group(1))
                continue

            # Pattern B: label in HTML then nearby percentage
            m = re.search(label + r'[^%]{0,100}?(\d+\.?\d*)%', text, re.DOTALL)
            if m:
                if setter == 'bullish':
                    bullish = float(m.group(1))
                elif setter == 'neutral':
                    neutral = float(m.group(1))
                elif setter == 'bearish':
                    bearish = float(m.group(1))

        if bullish is None or bearish is None:
            # Strategy 2: try parsing from BeautifulSoup tables
            soup = BeautifulSoup(text, 'html.parser')
            for table in soup.find_all('table'):
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    cell_text = [c.get_text(strip=True).lower() for c in cells]
                    for i, ct in enumerate(cell_text):
                        if 'bullish' in ct and i + 1 < len(cell_text):
                            m = re.search(r'(\d+\.?\d*)', cell_text[i + 1])
                            if m:
                                bullish = float(m.group(1))
                        elif 'neutral' in ct and i + 1 < len(cell_text):
                            m = re.search(r'(\d+\.?\d*)', cell_text[i + 1])
                            if m:
                                neutral = float(m.group(1))
                        elif 'bearish' in ct and i + 1 < len(cell_text):
                            m = re.search(r'(\d+\.?\d*)', cell_text[i + 1])
                            if m:
                                bearish = float(m.group(1))

        if bullish is None or bearish is None:
            return {'error': 'Could not parse AAII sentiment data from page'}

        bull_bear_ratio = round(bullish / bearish, 2) if bearish and bearish > 0 else float('inf') if bullish and bullish > 0 else None

        return {
            'bullish': bullish,
            'neutral': neutral,
            'bearish': bearish,
            'bull_bear_ratio': bull_bear_ratio,
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'AAII (aaii.com/sentimentsurvey)',
        }
    except Exception as e:
        return {'error': f'Error scraping AAII sentiment: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 9. OPEC Production / Output
# ──────────────────────────────────────────────────────────────────────────────

def get_opec_production():
    """Attempt to get OPEC crude oil production data.

    Primary:  EIA API v2 (requires EIA_API_KEY env var).
    Fallback: Trading Economics scrape.
    """
    eia_key = os.getenv('EIA_API_KEY')

    # --- EIA API v2 --------------------------------------------------------
    if eia_key:
        try:
            url = (
                'https://api.eia.gov/v2/international/data/'
                f'?api_key={eia_key}'
                '&frequency=monthly'
                '&data[0]=value'
                '&facets[productId][]=EPM2F_YCR'
                '&facets[geographyId][]=OPEC'
                '&sort[0][column]=period&sort[0][direction]=desc'
                '&length=120'
            )
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            records = data.get('response', {}).get('data', [])

            if records:
                # Build time series
                rows = []
                for r in records:
                    try:
                        dt = pd.to_datetime(r['period'])
                        val = float(r['value'])
                        rows.append((dt, val))
                    except (KeyError, ValueError, TypeError):
                        continue
                if rows:
                    rows.sort(key=lambda x: x[0])
                    series = pd.Series(
                        [v for _, v in rows],
                        index=pd.DatetimeIndex([d for d, _ in rows]),
                        name='opec_production',
                    )
                    latest = float(series.iloc[-1])
                    return {
                        'opec_production': latest,
                        'latest_date': series.index[-1].strftime('%Y-%m-%d'),
                        'historical': series,
                        'source': 'EIA API v2',
                        'units': 'Thousand Barrels per Day',
                    }
        except Exception:
            pass  # fall through to scrape

    # --- Trading Economics scrape (fallback) --------------------------------
    try:
        te_url = 'https://tradingeconomics.com/country-list/crude-oil-production'
        te_headers = {
            'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
        }
        resp = requests.get(te_url, headers=te_headers, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Look for a table row containing "OPEC" or sum major producers
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                if cells and 'opec' in cells[0].get_text(strip=True).lower():
                    for cell in cells[1:]:
                        m = re.search(r'([\d,.]+)', cell.get_text(strip=True))
                        if m:
                            val = float(m.group(1).replace(',', ''))
                            return {
                                'opec_production': val,
                                'latest_date': datetime.now().strftime('%Y-%m-%d'),
                                'source': 'Trading Economics (scrape)',
                                'units': 'Thousand Barrels per Day',
                            }

        return {'error': 'Could not parse OPEC production from Trading Economics'}
    except Exception as e:
        return {'error': f'Error fetching OPEC production: {str(e)}'}


# ──────────────────────────────────────────────────────────────────────────────
# 10. Gold Share of Global Reserves
# ──────────────────────────────────────────────────────────────────────────────

def get_gold_reserves_share():
    """Scrape gold share of global reserves from World Gold Council.

    Updated quarterly. Returns percentage of total reserves held in gold.
    """
    try:
        # Primary: World Gold Council Goldhub
        url = 'https://www.gold.org/goldhub/data/gold-reserves'
        headers = {
            'User-Agent': ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        text = resp.text

        # Look for percentage near "share" or "reserves"
        m = re.search(r'(\d+\.?\d*)%?\s*(?:of\s+)?(?:total\s+)?reserves', text, re.IGNORECASE)
        if m:
            share = float(m.group(1))
            return {
                'gold_reserves_share_pct': share,
                'latest_date': datetime.now().strftime('%Y-%m-%d'),
                'source': 'World Gold Council',
            }

        # Fallback: look for any prominent percentage on the page
        soup = BeautifulSoup(text, 'html.parser')
        for el in soup.find_all(['span', 'div', 'p', 'td']):
            el_text = el.get_text(strip=True)
            if 'share' in el_text.lower() or 'reserve' in el_text.lower():
                m = re.search(r'(\d+\.?\d*)%', el_text)
                if m:
                    share = float(m.group(1))
                    if 1 < share < 100:  # sanity check
                        return {
                            'gold_reserves_share_pct': share,
                            'latest_date': datetime.now().strftime('%Y-%m-%d'),
                            'source': 'World Gold Council (parsed)',
                        }

        return {'error': 'Could not parse gold reserves share from WGC'}
    except Exception as e:
        return {'error': f'Error fetching gold reserves share: {str(e)}'}


# ── Intraday Credit Spread Proxies ───────────────────────────────────────────

def get_credit_etf_proxies():
    """
    Fetch HYG, LQD, JNK bond ETF prices as intraday credit spread proxies.
    These update in real-time via yfinance (unlike FRED OAS which lags 1-2 days).
    Price drops = spreads widening (inverse relationship).
    """
    etfs = {
        'HYG': ('hyg_price', 'iShares iBoxx High Yield Corp Bond ETF'),
        'LQD': ('lqd_price', 'iShares iBoxx Investment Grade Corp Bond ETF'),
        'JNK': ('jnk_price', 'SPDR Bloomberg High Yield Bond ETF'),
    }
    results = {}
    for ticker, (key, name) in etfs.items():
        data = _yf_price(ticker, name, key=key)
        results[ticker] = data
    return results
