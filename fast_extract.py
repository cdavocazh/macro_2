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
]


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

    for key, func_name, desc in FAST_EXTRACTORS:
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
