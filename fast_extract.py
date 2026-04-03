#!/usr/bin/env python3
"""
Fast extraction of real-time market data (5-minute interval).

Only extracts indicators that update intraday via yfinance (no rate limits).
Skips FRED, web scrapers, SEC, and other slow/rate-limited sources.

Designed to run every 5 minutes via launchd during market hours.

Usage:
    python fast_extract.py             # normal run
    python fast_extract.py --cron      # quiet mode for launchd logs
    python fast_extract.py --force     # ignore freshness guard
    python fast_extract.py --dry-run   # list what would be extracted

Schedule: com.macro2.fast-extract.plist (every 300 seconds)
"""

import argparse
import json
import os
import socket
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Freshness guard: skip if last fast extract was < 3 minutes ago
_FRESHNESS_MINUTES = 3
_FRESHNESS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data_cache', '.fast_extract_timestamp'
)

# ── Real-time yfinance extractors (safe for 5-min polling) ───────────────────
# These all use yfinance with no rate limits and update intraday.
FAST_EXTRACTORS = [
    # Volatility & Risk
    ('vix_move', 'extract_vix_move', 'VIX, MOVE, VIX/MOVE ratio'),
    ('cboe_skew', 'extract_cboe_skew', 'CBOE SKEW index'),
    # Market Indices
    ('es_futures', 'extract_es_futures', 'E-mini S&P 500 futures'),
    ('rty_futures', 'extract_rty_futures', 'E-mini Russell 2000 futures'),
    ('sp500_ma200', 'extract_sp500_with_ma200', 'S&P 500 / 200MA ratio'),
    ('russell_2000', 'extract_russell_2000_historical', 'Russell 2000 V/G'),
    # Currency
    ('dxy', 'extract_dxy', 'US Dollar Index'),
    ('jpy', 'extract_jpy', 'USD/JPY'),
    # Commodities (futures - nearly 24/7)
    ('gold', 'extract_gold', 'Gold futures'),
    ('silver', 'extract_silver', 'Silver futures'),
    ('crude_oil', 'extract_crude_oil', 'WTI Crude Oil futures'),
    ('copper', 'extract_copper', 'Copper futures'),
    # Fidenza Macro (yfinance)
    ('brent_crude', 'extract_brent_crude', 'Brent Crude futures'),
    ('nikkei_225', 'extract_nikkei_225', 'Nikkei 225'),
    ('em_indices', 'extract_em_indices', 'EM indices (KOSPI, Bovespa, MSCI EM)'),
    ('fed_funds_futures', 'extract_fed_funds_futures', 'Fed Funds futures'),
    ('sofr_futures', 'extract_sofr_futures', 'SOFR futures term structure'),
    ('xau_jpy', 'extract_xau_jpy', 'XAU/JPY'),
    ('gold_silver_ratio', 'extract_gold_silver_ratio', 'Gold/Silver ratio'),
    # Credit proxies (bond ETFs - intraday)
    ('credit_etf_proxies', 'extract_credit_etf_proxies', 'HYG/LQD/JNK credit proxies'),
    # Data Extraction Requirements — new real-time datasets
    ('gold_ohlcv', 'extract_gold_ohlcv', 'Gold OHLCV'),
    ('silver_ohlcv', 'extract_silver_ohlcv', 'Silver OHLCV'),
    ('crude_oil_ohlcv', 'extract_crude_oil_ohlcv', 'Crude Oil OHLCV'),
    ('copper_ohlcv', 'extract_copper_ohlcv', 'Copper OHLCV'),
    ('es_futures_ohlcv', 'extract_es_futures_ohlcv', 'ES Futures OHLCV'),
    ('rty_futures_ohlcv', 'extract_rty_futures_ohlcv', 'RTY Futures OHLCV'),
    ('brent_crude_ohlcv', 'extract_brent_crude_ohlcv', 'Brent Crude OHLCV'),
    ('sector_etfs', 'extract_sector_etfs', 'Sector ETFs (11 SPDR)'),
    ('vix_term_structure', 'extract_vix_term_structure', 'VIX term structure'),
    ('put_call_ratio', 'extract_put_call_ratio', 'Put/Call ratio'),
    ('baltic_dry_index', 'extract_baltic_dry_index', 'Baltic Dry Index'),
]


# ── Cache merge: map fast extractors to aggregator indicator keys ──────────
# After CSV extraction, we call these to merge fresh data into
# data_cache/all_indicators.json so dashboards stay updated even when
# scheduled_extract.py hasn't run recently.
_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data_cache', 'all_indicators.json'
)


def _get_cache_indicator_map():
    """Lazy import to avoid loading heavy modules at startup."""
    from data_extractors import yfinance_extractors, commodities_extractors, web_scrapers
    return [
        ('8_vix', yfinance_extractors.get_vix),
        ('9_move_index', yfinance_extractors.get_move_index),
        ('8b_vix_move_ratio', yfinance_extractors.calculate_vix_move_ratio),
        ('6a_sp500_to_ma200', yfinance_extractors.get_sp500_data),
        ('2_russell_2000', yfinance_extractors.get_russell_2000_indices),
        ('10_dxy', yfinance_extractors.get_dxy),
        ('20_jpy', yfinance_extractors.get_jpy_exchange_rate),
        ('54_fx_pairs', yfinance_extractors.get_major_fx_pairs),
        ('55_market_concentration', yfinance_extractors.get_market_concentration),
        ('17_es_futures', yfinance_extractors.get_es_futures),
        ('18_rty_futures', yfinance_extractors.get_rty_futures),
        ('13_gold', commodities_extractors.get_gold),
        ('14_silver', commodities_extractors.get_silver),
        ('15_crude_oil', commodities_extractors.get_crude_oil),
        ('16_copper', commodities_extractors.get_copper),
        ('56_natural_gas', commodities_extractors.get_natural_gas),
        ('57_cu_au_ratio', commodities_extractors.get_copper_gold_ratio),
        ('5_spx_call_skew', web_scrapers.get_cboe_skew_index),
    ]


def _merge_into_cache(quiet=False):
    """Merge fresh yfinance results into all_indicators.json.

    Loads the existing cache file directly (bypassing TTL), updates only
    the fast-extract indicator keys, and writes back atomically.
    """
    from utils.helpers import _serialize_value

    # Load existing cache or create skeleton
    if os.path.exists(_CACHE_FILE):
        try:
            with open(_CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            cache_data = {'timestamp': datetime.now().isoformat(), 'data': {}}
    else:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        cache_data = {'timestamp': datetime.now().isoformat(), 'data': {}}

    indicator_map = _get_cache_indicator_map()
    merged = 0

    for key, extractor_func in indicator_map:
        try:
            result = extractor_func()
            if result and not isinstance(result, dict) or (isinstance(result, dict) and 'error' not in result):
                cache_data['data'][key] = _serialize_value(result)
                merged += 1
        except Exception:
            pass  # Keep existing cached value for this key

    if merged == 0:
        return

    # Update timestamp and write atomically
    cache_data['timestamp'] = datetime.now().isoformat()
    tmp_file = _CACHE_FILE + '.tmp'
    try:
        with open(tmp_file, 'w') as f:
            json.dump(cache_data, f, default=str)
        os.rename(tmp_file, _CACHE_FILE)
        if not quiet:
            print(f"  Merged {merged}/{len(indicator_map)} indicators into cache")
    except OSError as e:
        if not quiet:
            print(f"  Warning: cache merge failed: {e}")
        # Clean up tmp file
        try:
            os.remove(tmp_file)
        except OSError:
            pass


def _check_freshness(force=False):
    """Return True if extraction should proceed."""
    if force:
        return True
    try:
        if os.path.exists(_FRESHNESS_FILE):
            mtime = os.path.getmtime(_FRESHNESS_FILE)
            age_min = (time.time() - mtime) / 60
            if age_min < _FRESHNESS_MINUTES:
                return False
    except OSError:
        pass
    return True


def _update_freshness():
    """Touch the freshness timestamp file."""
    os.makedirs(os.path.dirname(_FRESHNESS_FILE), exist_ok=True)
    with open(_FRESHNESS_FILE, 'w') as f:
        f.write(datetime.now().isoformat())


def _check_network():
    """Quick network check (yfinance only — single host)."""
    try:
        socket.create_connection(('query1.finance.yahoo.com', 443), timeout=5).close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False


def _write_progress(current, total, label, status="running"):
    """Write extraction progress for the dashboard to read."""
    try:
        progress_file = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                     'data_cache', '.extract_progress.json')
        import json
        with open(progress_file, 'w') as f:
            json.dump({"current": current, "total": total, "label": label,
                       "status": status, "timestamp": datetime.now().isoformat()}, f)
    except Exception:
        pass


def run_fast_extraction(force=False, quiet=False, dry_run=False):
    """Extract only real-time yfinance indicators to historical CSVs."""
    start_time = time.time()

    if dry_run:
        print(f"Fast extract: {len(FAST_EXTRACTORS)} real-time indicators")
        for key, func_name, desc in FAST_EXTRACTORS:
            print(f"  - {key}: {desc} ({func_name})")
        return

    # Freshness guard
    if not _check_freshness(force):
        if not quiet:
            print(f"Fast extract: skipped (< {_FRESHNESS_MINUTES}min since last run)")
        return

    # Network check
    if not _check_network():
        ts = datetime.now().strftime('%H:%M:%S')
        msg = f"[{ts}] Fast extract: no network"
        print(msg)
        return

    # Import extraction functions
    import extract_historical_data as ehd

    succeeded = 0
    failed = 0
    total = len(FAST_EXTRACTORS)

    _write_progress(0, total, "Starting fast extract...", "running")

    for i, (key, func_name, desc) in enumerate(FAST_EXTRACTORS, 1):
        _write_progress(i, total, key, "running")
        try:
            func = getattr(ehd, func_name)
            result = func()
            if result is not None:
                succeeded += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            if not quiet:
                print(f"  ❌ {key}: {e}")

    _update_freshness()

    # Merge fresh results into all_indicators.json so dashboards stay updated
    _merge_into_cache(quiet=quiet)

    _write_progress(total, total, "Complete", "done")

    elapsed = time.time() - start_time
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if quiet:
        print(f"[{ts}] Fast: {succeeded}/{succeeded + failed} in {elapsed:.1f}s")
    else:
        print(f"\nFast extraction complete: {succeeded}/{succeeded + failed} in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description='Fast extraction of real-time market data (5-minute interval).'
    )
    parser.add_argument('--force', '-f', action='store_true',
                        help='Ignore freshness guard')
    parser.add_argument('--cron', action='store_true',
                        help='Quiet mode for launchd logs')
    parser.add_argument('--dry-run', action='store_true',
                        help='List extractors without running')
    args = parser.parse_args()

    run_fast_extraction(force=args.force, quiet=args.cron, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
