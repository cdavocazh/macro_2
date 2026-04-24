"""
S&P 500 Ticker List — Fetches and caches the current S&P 500 constituents.

Sources (in priority order):
1. Wikipedia "List of S&P 500 companies" table via pd.read_html()
2. Hardcoded fallback (last known list, ~500 tickers)

Caches to data_cache/sp500_tickers.json with a 7-day TTL.
Normalizes ticker symbols: dots → dashes (BRK.B → BRK-B).

Usage:
    from data_extractors.sp500_tickers import get_sp500_tickers
    tickers = get_sp500_tickers()               # ~503 tickers
    tickers = get_sp500_tickers(force_refresh=True)  # force re-download
"""

import json
import os
import time

CACHE_DIR = 'data_cache'
CACHE_FILE = os.path.join(CACHE_DIR, 'sp500_tickers.json')
CACHE_TTL_HOURS = 168  # 7 days

WIKIPEDIA_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'

# Hardcoded fallback — last known S&P 500 constituents (March 2026)
# This is used only if Wikipedia is unreachable.
_FALLBACK_TICKERS = [
    'AAPL', 'ABBV', 'ABT', 'ACN', 'ADBE', 'ADI', 'ADM', 'ADP', 'ADSK', 'AEE',
    'AEP', 'AES', 'AFL', 'AIG', 'AIZ', 'AJG', 'AKAM', 'ALB', 'ALGN', 'ALK',
    'ALL', 'ALLE', 'AMAT', 'AMCR', 'AMD', 'AME', 'AMGN', 'AMP', 'AMT', 'AMZN',
    'ANET', 'ANSS', 'AON', 'AOS', 'APA', 'APD', 'APH', 'APTV', 'ARE', 'ATO',
    'ATVI', 'AVGO', 'AVY', 'AWK', 'AXP', 'AZO', 'BA', 'BAC', 'BAX', 'BBWI',
    'BBY', 'BDX', 'BEN', 'BF-B', 'BG', 'BIIB', 'BIO', 'BK', 'BKNG', 'BKR',
    'BLK', 'BMY', 'BR', 'BRK-B', 'BRO', 'BSX', 'BWA', 'BXP', 'C', 'CAG',
    'CAH', 'CARR', 'CAT', 'CB', 'CBOE', 'CBRE', 'CCI', 'CCL', 'CDAY', 'CDNS',
    'CDW', 'CE', 'CEG', 'CF', 'CFG', 'CHD', 'CHRW', 'CHTR', 'CI', 'CINF',
    'CL', 'CLX', 'CMA', 'CMCSA', 'CME', 'CMG', 'CMI', 'CMS', 'CNC', 'CNP',
    'COF', 'COO', 'COP', 'COST', 'CPB', 'CPRT', 'CPT', 'CRL', 'CRM', 'CSCO',
    'CSGP', 'CSX', 'CTAS', 'CTLT', 'CTRA', 'CTSH', 'CTVA', 'CVS', 'CVX', 'CZR',
    'D', 'DAL', 'DD', 'DE', 'DECK', 'DFS', 'DG', 'DGX', 'DHI', 'DHR',
    'DIS', 'DISH', 'DLR', 'DLTR', 'DOV', 'DOW', 'DPZ', 'DRI', 'DTE', 'DUK',
    'DVA', 'DVN', 'DXCM', 'EA', 'EBAY', 'ECL', 'ED', 'EFX', 'EIX', 'EL',
    'EMN', 'EMR', 'ENPH', 'EOG', 'EPAM', 'EQIX', 'EQR', 'EQT', 'ES', 'ESS',
    'ETN', 'ETR', 'ETSY', 'EVRG', 'EW', 'EXC', 'EXPD', 'EXPE', 'EXR', 'F',
    'FANG', 'FAST', 'FBHS', 'FCX', 'FDS', 'FDX', 'FE', 'FFIV', 'FIS', 'FISV',
    'FITB', 'FLT', 'FMC', 'FOX', 'FOXA', 'FRC', 'FRT', 'FTNT', 'FTV', 'GD',
    'GE', 'GEHC', 'GEN', 'GILD', 'GIS', 'GL', 'GLW', 'GM', 'GNRC', 'GOOG',
    'GOOGL', 'GPC', 'GPN', 'GRMN', 'GS', 'GWW', 'HAL', 'HAS', 'HBAN', 'HCA',
    'HD', 'HOLX', 'HON', 'HPE', 'HPQ', 'HRL', 'HSIC', 'HST', 'HSY', 'HUBB',
    'HUM', 'HWM', 'IBM', 'ICE', 'IDXX', 'IEX', 'IFF', 'ILMN', 'INCY', 'INTC',
    'INTU', 'INVH', 'IP', 'IPG', 'IQV', 'IR', 'IRM', 'ISRG', 'IT', 'ITW',
    'IVZ', 'J', 'JBHT', 'JCI', 'JKHY', 'JNJ', 'JNPR', 'JPM', 'K', 'KDP',
    'KEY', 'KEYS', 'KHC', 'KIM', 'KLAC', 'KMB', 'KMI', 'KMX', 'KO', 'KR',
    'L', 'LDOS', 'LEN', 'LH', 'LHX', 'LIN', 'LKQ', 'LLY', 'LMT', 'LNC',
    'LNT', 'LOW', 'LRCX', 'LULU', 'LUV', 'LVS', 'LW', 'LYB', 'LYV', 'MA',
    'MAA', 'MAR', 'MAS', 'MCD', 'MCHP', 'MCK', 'MCO', 'MDLZ', 'MDT', 'MET',
    'META', 'MGM', 'MHK', 'MKC', 'MKTX', 'MLM', 'MMC', 'MMM', 'MNST', 'MO',
    'MOH', 'MOS', 'MPC', 'MPWR', 'MRK', 'MRNA', 'MRO', 'MS', 'MSCI', 'MSFT',
    'MSI', 'MTB', 'MTCH', 'MTD', 'MU', 'NCLH', 'NDAQ', 'NDSN', 'NEE', 'NEM',
    'NFLX', 'NI', 'NKE', 'NOC', 'NOW', 'NRG', 'NSC', 'NTAP', 'NTRS', 'NUE',
    'NVDA', 'NVR', 'NWL', 'NWS', 'NWSA', 'NXPI', 'O', 'ODFL', 'OGN', 'OKE',
    'OMC', 'ON', 'ORCL', 'ORLY', 'OTIS', 'OXY', 'PARA', 'PAYC', 'PAYX', 'PCAR',
    'PCG', 'PEAK', 'PEG', 'PEP', 'PFE', 'PFG', 'PG', 'PGR', 'PH', 'PHM',
    'PKG', 'PKI', 'PLD', 'PM', 'PNC', 'PNR', 'PNW', 'POOL', 'PPG', 'PPL',
    'PRU', 'PSA', 'PSX', 'PTC', 'PVH', 'PWR', 'PXD', 'PYPL', 'QCOM', 'QRVO',
    'RCL', 'RE', 'REG', 'REGN', 'RF', 'RHI', 'RJF', 'RL', 'RMD', 'ROK',
    'ROL', 'ROP', 'ROST', 'RSG', 'RTX', 'RVTY', 'SBAC', 'SBNY', 'SBUX', 'SCHW',
    'SEE', 'SHW', 'SIVB', 'SJM', 'SLB', 'SNA', 'SNPS', 'SO', 'SPG', 'SPGI',
    'SRE', 'STE', 'STLD', 'STT', 'STX', 'STZ', 'SWK', 'SWKS', 'SYF', 'SYK',
    'SYY', 'T', 'TAP', 'TDG', 'TDY', 'TECH', 'TEL', 'TER', 'TFC', 'TFX',
    'TGT', 'TJX', 'TMO', 'TMUS', 'TPR', 'TRGP', 'TRMB', 'TROW', 'TRV', 'TSCO',
    'TSLA', 'TSN', 'TT', 'TTWO', 'TXN', 'TXT', 'TYL', 'UAL', 'UDR', 'UHS',
    'ULTA', 'UNH', 'UNP', 'UPS', 'URI', 'USB', 'V', 'VFC', 'VICI', 'VLO',
    'VMC', 'VRSK', 'VRSN', 'VRTX', 'VTR', 'VTRS', 'VZ', 'WAB', 'WAT', 'WBA',
    'WBD', 'WDC', 'WEC', 'WELL', 'WFC', 'WHR', 'WM', 'WMB', 'WMT', 'WRB',
    'WRK', 'WST', 'WTW', 'WY', 'WYNN', 'XEL', 'XOM', 'XRAY', 'XYL', 'YUM',
    'ZBH', 'ZBRA', 'ZION', 'ZTS',
]


def _normalize_ticker(ticker):
    """Normalize ticker: replace dots with dashes (BRK.B → BRK-B)."""
    return ticker.strip().upper().replace('.', '-')


def get_sp500_tickers(force_refresh=False):
    """
    Get current S&P 500 constituent ticker symbols.

    Returns a sorted list of ~503 ticker symbols (some have dual share classes).
    Results are cached to data_cache/sp500_tickers.json with 7-day TTL.

    Args:
        force_refresh: If True, ignore cache and re-download from Wikipedia.

    Returns:
        list[str]: Sorted list of ticker symbols (e.g., ['AAPL', 'ABBV', ...])
    """
    # Check cache (unless force refresh)
    if not force_refresh and os.path.exists(CACHE_FILE):
        try:
            age_hours = (time.time() - os.path.getmtime(CACHE_FILE)) / 3600
            if age_hours < CACHE_TTL_HOURS:
                with open(CACHE_FILE, 'r') as f:
                    data = json.load(f)
                    tickers = data.get('tickers', [])
                    if len(tickers) > 400:  # sanity check
                        return tickers
        except (json.JSONDecodeError, OSError):
            pass

    # Try Wikipedia
    tickers = _fetch_from_wikipedia()

    if tickers and len(tickers) > 400:
        _save_cache(tickers)
        return tickers

    # Fallback to hardcoded list
    print("  Warning: Using hardcoded S&P 500 fallback list.")
    return sorted(_FALLBACK_TICKERS)


def _fetch_from_wikipedia():
    """Scrape S&P 500 tickers from Wikipedia."""
    try:
        import pandas as pd
        import requests
        import io

        # Wikipedia blocks bare requests; use a browser-like User-Agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        }
        resp = requests.get(WIKIPEDIA_URL, headers=headers, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))

        # The first table on the page is the S&P 500 constituents table
        df = tables[0]

        # The ticker column is usually named 'Symbol' or 'Ticker'
        ticker_col = None
        for col in df.columns:
            col_str = str(col).lower()
            if 'symbol' in col_str or 'ticker' in col_str:
                ticker_col = col
                break

        if ticker_col is None:
            # Fallback: use first column
            ticker_col = df.columns[0]

        raw_tickers = df[ticker_col].dropna().astype(str).tolist()
        tickers = sorted(set(_normalize_ticker(t) for t in raw_tickers if t.strip()))

        if len(tickers) > 400:
            return tickers
        return None

    except Exception as e:
        print(f"  Warning: Wikipedia S&P 500 fetch failed: {e}")
        return None


def _save_cache(tickers):
    """Save tickers to cache file."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump({
                'tickers': tickers,
                'count': len(tickers),
                'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                'source': 'Wikipedia',
            }, f, indent=2)
    except OSError as e:
        print(f"  Warning: Failed to save S&P 500 cache: {e}")


def get_non_top20_sp500():
    """Get S&P 500 tickers excluding the Top 20."""
    from data_extractors.equity_financials_extractor import TOP_20_TICKERS
    all_tickers = get_sp500_tickers()
    top20_set = set(TOP_20_TICKERS)
    return [t for t in all_tickers if t not in top20_set]


# ── Extended indices (MidCap 400, Russell 1000) ───────────────────────────────

_MIDCAP400_CACHE_FILE = os.path.join(CACHE_DIR, 'sp400_tickers.json')
_RUSSELL1000_CACHE_FILE = os.path.join(CACHE_DIR, 'russell1000_tickers.json')

_MIDCAP400_WIKI_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies'
_RUSSELL1000_WIKI_URL = 'https://en.wikipedia.org/wiki/Russell_1000_Index'


def get_midcap400_tickers(force_refresh=False) -> list[str]:
    """Get S&P MidCap 400 constituent ticker symbols.

    Scrapes the Wikipedia "List of S&P 400 companies" page.
    Results cached for 7 days.

    Returns:
        list[str]: ~400 mid-cap ticker symbols
    """
    if not force_refresh and os.path.exists(_MIDCAP400_CACHE_FILE):
        try:
            age_hours = (time.time() - os.path.getmtime(_MIDCAP400_CACHE_FILE)) / 3600
            if age_hours < CACHE_TTL_HOURS:
                with open(_MIDCAP400_CACHE_FILE) as f:
                    data = json.load(f)
                    tickers = data.get('tickers', [])
                    if len(tickers) > 300:
                        return tickers
        except (json.JSONDecodeError, OSError):
            pass

    tickers = _fetch_index_from_wikipedia(_MIDCAP400_WIKI_URL, min_count=300)
    if tickers:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(_MIDCAP400_CACHE_FILE, 'w') as f:
                json.dump({'tickers': tickers, 'count': len(tickers),
                           'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                           'source': 'Wikipedia S&P MidCap 400'}, f, indent=2)
        except OSError:
            pass
        return tickers

    print("  Warning: S&P MidCap 400 Wikipedia fetch failed — returning empty list.")
    return []


def get_russell1000_tickers(force_refresh=False) -> list[str]:
    """Get Russell 1000 ticker symbols.

    The Russell 1000 = largest 1000 US equities by market cap. Approximated
    here as the union of S&P 500 + S&P MidCap 400, which covers ~903 of the
    1000 names (~97% overlap). A Wikipedia scrape of the full Russell 1000 list
    is also attempted as the primary source.

    Returns:
        list[str]: ~1000 large/mid-cap ticker symbols
    """
    if not force_refresh and os.path.exists(_RUSSELL1000_CACHE_FILE):
        try:
            age_hours = (time.time() - os.path.getmtime(_RUSSELL1000_CACHE_FILE)) / 3600
            if age_hours < CACHE_TTL_HOURS:
                with open(_RUSSELL1000_CACHE_FILE) as f:
                    data = json.load(f)
                    tickers = data.get('tickers', [])
                    if len(tickers) > 700:
                        return tickers
        except (json.JSONDecodeError, OSError):
            pass

    # Primary: try Wikipedia Russell 1000 list
    tickers = _fetch_index_from_wikipedia(_RUSSELL1000_WIKI_URL, min_count=700)

    # Fallback: S&P 500 ∪ S&P MidCap 400 union (~903 tickers, 97% of R1000)
    if not tickers:
        sp500 = get_sp500_tickers()
        midcap = get_midcap400_tickers()
        tickers = sorted(set(sp500) | set(midcap))
        print(f"  Info: Using S&P500 + MidCap400 union as Russell 1000 proxy ({len(tickers)} tickers).")

    if tickers:
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(_RUSSELL1000_CACHE_FILE, 'w') as f:
                json.dump({'tickers': tickers, 'count': len(tickers),
                           'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
                           'source': 'Wikipedia Russell 1000 (or SP500+SP400 union)'}, f, indent=2)
        except OSError:
            pass
    return tickers


def _fetch_index_from_wikipedia(url: str, min_count: int = 300) -> list[str]:
    """Generic Wikipedia table scraper for index constituent lists.

    Tries every table on the page, picks the one with the most plausible
    stock ticker column (column named Symbol/Ticker, values matching [A-Z.-]+).
    """
    try:
        import pandas as pd
        import requests
        import io
        import re

        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))

        _ticker_re = re.compile(r'^[A-Z][A-Z0-9\.\-]{0,9}$')

        for df in tables:
            # Find a column that looks like tickers
            for col in df.columns:
                col_s = str(col).lower()
                if 'symbol' not in col_s and 'ticker' not in col_s:
                    continue
                raw = df[col].dropna().astype(str).tolist()
                candidates = [_normalize_ticker(t) for t in raw if _ticker_re.match(t.strip().upper())]
                if len(candidates) >= min_count:
                    return sorted(set(candidates))

        # Second pass: any column where >80% of values look like tickers
        for df in tables:
            for col in df.columns:
                raw = df[col].dropna().astype(str).tolist()
                candidates = [_normalize_ticker(t) for t in raw if _ticker_re.match(t.strip().upper())]
                if len(candidates) >= min_count and len(candidates) / max(len(raw), 1) > 0.7:
                    return sorted(set(candidates))

        return []
    except Exception as e:
        print(f"  Warning: Wikipedia index fetch ({url}) failed: {e}")
        return []


if __name__ == '__main__':
    tickers = get_sp500_tickers(force_refresh=True)
    print(f"S&P 500 tickers: {len(tickers)}")
    print(f"First 20: {tickers[:20]}")
    print(f"Last 20: {tickers[-20:]}")

    midcap = get_midcap400_tickers(force_refresh=True)
    print(f"\nS&P MidCap 400 tickers: {len(midcap)}")

    r1000 = get_russell1000_tickers(force_refresh=True)
    print(f"\nRussell 1000 tickers: {len(r1000)}")
