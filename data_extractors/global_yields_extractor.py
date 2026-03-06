"""
Global sovereign bond yield extractors.
Fetches 10-year government bond yields for Germany, UK, and China.

Primary source: Trading Economics (web scrape, daily)
Fallback: FRED OECD series (monthly, Germany/UK only)
"""
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup

try:
    from fredapi import Fred
    import config
    _HAS_FRED = True
except ImportError:
    _HAS_FRED = False

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
}

_TE_BASE = 'https://tradingeconomics.com'

# FRED OECD monthly series (fallback for historical data)
_FRED_SERIES = {
    'germany': 'IRLTLT01DEM156N',
    'uk': 'IRLTLT01GBM156N',
}


def _scrape_trading_economics_yield(country_slug):
    """
    Scrape current 10Y yield from Trading Economics.

    Args:
        country_slug: URL slug, e.g. 'germany', 'united-kingdom', 'china'

    Returns:
        dict with 'yield_value', 'previous', 'change_day', 'change_month' or None on failure
    """
    url = f'{_TE_BASE}/{country_slug}/government-bond-yield'
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return None

        # Method 1: Extract from script tags (most reliable)
        # Trading Economics embeds data as JSON in script tags
        last_match = re.search(r'"last":([\d.]+)', resp.text)
        prev_match = re.search(r'"previous":([\d.]+)', resp.text)

        if last_match:
            result = {
                'yield_value': float(last_match.group(1)),
            }
            if prev_match:
                prev_val = float(prev_match.group(1))
                result['previous'] = prev_val
                result['change_1d'] = round(result['yield_value'] - prev_val, 4)
            return result

        # Method 2: Parse HTML table (fallback)
        soup = BeautifulSoup(resp.text, 'html.parser')
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                cell_text = [c.text.strip() for c in cells]
                # Look for row containing "10Y" yield
                if any('10Y' in c for c in cell_text) and len(cell_text) >= 2:
                    try:
                        yield_val = float(cell_text[1])
                        return {'yield_value': yield_val}
                    except (ValueError, IndexError):
                        continue

        return None
    except Exception:
        return None


def _get_fred_historical(series_id):
    """Fetch historical data from FRED (monthly OECD series)."""
    if not _HAS_FRED:
        return None
    try:
        fred = Fred(api_key=config.FRED_API_KEY)
        data = fred.get_series(series_id)
        if data is not None and not data.empty:
            return data.dropna()
    except Exception:
        pass
    return None


def get_germany_10y_yield():
    """
    Get Germany 10-Year Government Bond Yield.
    Primary: Trading Economics (daily scrape)
    Historical: FRED IRLTLT01DEM156N (monthly OECD)
    """
    try:
        # Primary: Trading Economics scrape
        scraped = _scrape_trading_economics_yield('germany')

        if scraped and 'yield_value' in scraped:
            result = {
                'germany_10y_yield': scraped['yield_value'],
                'change_1d': scraped.get('change_1d', 0),
                'latest_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                'source': 'Trading Economics (scraped)',
                'units': 'Percent',
            }

            # Add FRED historical for charts
            hist = _get_fred_historical(_FRED_SERIES['germany'])
            if hist is not None:
                result['historical'] = hist
                result['hist_source'] = 'FRED OECD (monthly)'

            return result

        # Fallback: FRED only (monthly, delayed)
        hist = _get_fred_historical(_FRED_SERIES['germany'])
        if hist is not None and not hist.empty:
            latest = hist.iloc[-1]
            latest_date = hist.index[-1]
            prev = hist.iloc[-2] if len(hist) >= 2 else latest
            change = round(float(latest - prev), 4)

            return {
                'germany_10y_yield': round(float(latest), 4),
                'change_1d': change,
                'latest_date': latest_date.strftime('%Y-%m-%d'),
                'source': 'FRED (IRLTLT01DEM156N, monthly)',
                'units': 'Percent',
                'historical': hist,
                'note': 'Monthly OECD data (1-2 month delay). Trading Economics scrape failed.',
            }

        return {'error': 'Could not fetch Germany 10Y yield from any source'}

    except Exception as e:
        return {'error': f'Error fetching Germany 10Y yield: {str(e)}'}


def get_uk_10y_yield():
    """
    Get UK 10-Year Government Bond (Gilt) Yield.
    Primary: Trading Economics (daily scrape)
    Historical: FRED IRLTLT01GBM156N (monthly OECD)
    """
    try:
        scraped = _scrape_trading_economics_yield('united-kingdom')

        if scraped and 'yield_value' in scraped:
            result = {
                'uk_10y_yield': scraped['yield_value'],
                'change_1d': scraped.get('change_1d', 0),
                'latest_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                'source': 'Trading Economics (scraped)',
                'units': 'Percent',
            }

            hist = _get_fred_historical(_FRED_SERIES['uk'])
            if hist is not None:
                result['historical'] = hist
                result['hist_source'] = 'FRED OECD (monthly)'

            return result

        # Fallback: FRED only
        hist = _get_fred_historical(_FRED_SERIES['uk'])
        if hist is not None and not hist.empty:
            latest = hist.iloc[-1]
            latest_date = hist.index[-1]
            prev = hist.iloc[-2] if len(hist) >= 2 else latest
            change = round(float(latest - prev), 4)

            return {
                'uk_10y_yield': round(float(latest), 4),
                'change_1d': change,
                'latest_date': latest_date.strftime('%Y-%m-%d'),
                'source': 'FRED (IRLTLT01GBM156N, monthly)',
                'units': 'Percent',
                'historical': hist,
                'note': 'Monthly OECD data (1-2 month delay). Trading Economics scrape failed.',
            }

        return {'error': 'Could not fetch UK 10Y yield from any source'}

    except Exception as e:
        return {'error': f'Error fetching UK 10Y yield: {str(e)}'}


def get_china_10y_yield():
    """
    Get China 10-Year Government Bond Yield.
    Source: Trading Economics only (no FRED series available for China 10Y).
    """
    try:
        scraped = _scrape_trading_economics_yield('china')

        if scraped and 'yield_value' in scraped:
            return {
                'china_10y_yield': scraped['yield_value'],
                'change_1d': scraped.get('change_1d', 0),
                'latest_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                'source': 'Trading Economics (scraped)',
                'units': 'Percent',
                'note': 'No FRED series available for China 10Y. Scraped only, no historical chart.',
            }

        return {
            'error': 'Could not fetch China 10Y yield from Trading Economics',
            'note': 'No FRED fallback available for China government bond yields',
        }

    except Exception as e:
        return {'error': f'Error fetching China 10Y yield: {str(e)}'}


# ── v2.3.0: ISM Services PMI via Trading Economics ────────────────────────


def get_ism_services_pmi():
    """
    Get ISM Services (Non-Manufacturing) PMI from Trading Economics.
    ISM data was removed from FRED in 2016 — web scrape is the only free source.
    Services = ~77% of US GDP, making this a critical economic indicator.
    """
    try:
        url = f'{_TE_BASE}/united-states/non-manufacturing-pmi'
        resp = requests.get(url, headers=_HEADERS, timeout=15)
        if resp.status_code != 200:
            return {'error': f'Trading Economics returned HTTP {resp.status_code}'}

        # Method 1: JSON regex (most reliable)
        last_match = re.search(r'"last":([\d.]+)', resp.text)
        prev_match = re.search(r'"previous":([\d.]+)', resp.text)

        if last_match:
            latest = round(float(last_match.group(1)), 1)
            result = {
                'ism_services_pmi': latest,
                'latest_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                'source': 'Trading Economics (scraped)',
                'units': 'Index',
            }
            if prev_match:
                prev = float(prev_match.group(1))
                result['previous'] = prev
                result['change_1d'] = round(latest - prev, 1)

            # Above/below 50 interpretation
            if latest >= 50:
                result['interpretation'] = f"Services expanding ({latest} > 50). Services = ~77% of GDP."
            else:
                result['interpretation'] = f"Services contracting ({latest} < 50). Watch for economic weakness."
            return result

        # Method 2: BeautifulSoup table fallback
        soup = BeautifulSoup(resp.text, 'html.parser')
        tables = soup.find_all('table')
        for table in tables:
            rows = table.find_all('tr')
            for row in rows:
                cells = row.find_all(['td', 'th'])
                cell_text = [c.text.strip() for c in cells]
                # Look for a row with the PMI value
                for i, ct in enumerate(cell_text):
                    if 'non-manufacturing' in ct.lower() or 'services' in ct.lower():
                        for j in range(i + 1, len(cell_text)):
                            try:
                                val = float(cell_text[j])
                                if 30 < val < 70:  # Reasonable PMI range
                                    return {
                                        'ism_services_pmi': val,
                                        'latest_date': pd.Timestamp.now().strftime('%Y-%m-%d'),
                                        'source': 'Trading Economics (scraped, table)',
                                        'units': 'Index',
                                    }
                            except ValueError:
                                continue

        return {'error': 'Could not parse ISM Services PMI from Trading Economics'}

    except Exception as e:
        return {'error': f'Error fetching ISM Services PMI: {str(e)}'}
