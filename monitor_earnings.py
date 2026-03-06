#!/usr/bin/env python3
"""
Earnings Monitoring Script — Tracks earnings dates and flags stale local data.

Scans companies in the local database (historical_data/equity_financials/) and
compares their latest stored quarter against the most recent earnings reported
online (via yfinance ticker.info). Outputs three lists:

    1. Needs update — company has reported new earnings since last extraction
    2. Upcoming (next N days) — company is about to report earnings
    3. Up to date — local data matches latest available

Usage:
    python monitor_earnings.py                          # scan all companies in database
    python monitor_earnings.py --auto-update            # scan + re-extract stale tickers
    python monitor_earnings.py --days 7                 # show upcoming earnings within 7 days
    python monitor_earnings.py --tickers AAPL,MSFT      # check specific tickers only
    python monitor_earnings.py --top20-only             # only check Top 20 companies
"""

import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import pandas as pd

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HISTORICAL_DIR = 'historical_data'
YAHOO_DIR = os.path.join(HISTORICAL_DIR, 'equity_financials', 'yahoo_finance')
SEC_DIR = os.path.join(HISTORICAL_DIR, 'equity_financials', 'sec_edgar')


def _get_local_tickers(source_dir=YAHOO_DIR):
    """Get all tickers that have local CSV data."""
    tickers = []
    if os.path.isdir(source_dir):
        for f in sorted(os.listdir(source_dir)):
            if f.endswith('_quarterly.csv') and not f.startswith('_'):
                tickers.append(f.replace('_quarterly.csv', ''))
    return tickers


def _get_latest_local_quarter(ticker, source_dir=YAHOO_DIR):
    """Read the latest quarter from local CSV for a ticker.

    Returns quarter string (e.g., '2025-Q4') or None.
    """
    csv_path = os.path.join(source_dir, f'{ticker}_quarterly.csv')
    if not os.path.exists(csv_path):
        return None
    try:
        df = pd.read_csv(csv_path)
        if 'quarter' in df.columns and len(df) > 0:
            # Quarters are sorted descending (most recent first)
            quarters = df['quarter'].dropna().tolist()
            if quarters:
                return quarters[0]
    except Exception:
        pass
    return None


def _parse_quarter(q_str):
    """Parse quarter string like '2025-Q4' into (year, quarter_num).

    Returns (year, quarter) tuple or None if parsing fails.
    """
    if not q_str or not isinstance(q_str, str):
        return None
    try:
        parts = q_str.split('-Q')
        if len(parts) == 2:
            return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError):
        pass
    return None


def _quarter_is_newer(q1_str, q2_str):
    """Returns True if q1 is strictly newer (later) than q2.

    Both are quarter strings like '2025-Q4'.
    """
    q1 = _parse_quarter(q1_str)
    q2 = _parse_quarter(q2_str)
    if q1 is None or q2 is None:
        return False
    return q1 > q2


def check_earnings(tickers, days_ahead=14, quiet=False):
    """
    Check earnings dates for a list of tickers against local data.

    Args:
        tickers: list of ticker symbols
        days_ahead: number of days to look ahead for upcoming earnings
        quiet: suppress per-ticker output

    Returns:
        dict with 'needs_update', 'upcoming', 'up_to_date', 'errors' lists
    """
    import yfinance as yf

    needs_update = []
    upcoming = []
    up_to_date = []
    errors = []

    total = len(tickers)
    batch_size = 25
    batches = [tickers[i:i + batch_size] for i in range(0, total, batch_size)]

    now = datetime.now()
    cutoff = now + timedelta(days=days_ahead)

    for batch_idx, batch in enumerate(batches):
        if not quiet and batch_idx > 0:
            print(f"  Waiting 2s before next batch...")
            time.sleep(2)

        for i, ticker in enumerate(batch):
            idx = batch_idx * batch_size + i + 1
            try:
                # Get local state
                local_quarter = _get_latest_local_quarter(ticker, YAHOO_DIR)

                # Fetch yfinance info (lightweight — no full financials)
                yf_ticker = yf.Ticker(ticker)
                info = yf_ticker.info or {}

                # Extract earnings data
                most_recent_quarter_ts = info.get('mostRecentQuarter')
                earnings_ts_start = info.get('earningsTimestampStart')
                earnings_ts_end = info.get('earningsTimestampEnd')

                # Parse mostRecentQuarter (Unix timestamp of the quarter end date)
                remote_quarter = None
                if most_recent_quarter_ts:
                    try:
                        dt = datetime.fromtimestamp(most_recent_quarter_ts)
                        q = (dt.month - 1) // 3 + 1
                        remote_quarter = f"{dt.year}-Q{q}"
                    except (OSError, ValueError):
                        pass

                # Parse next earnings date
                next_earnings = None
                if earnings_ts_start:
                    try:
                        next_earnings = datetime.fromtimestamp(earnings_ts_start)
                    except (OSError, ValueError):
                        pass

                # Determine status
                status = {
                    'ticker': ticker,
                    'company_name': info.get('longName', info.get('shortName', ticker)),
                    'local_quarter': local_quarter,
                    'remote_quarter': remote_quarter,
                    'next_earnings': next_earnings.strftime('%Y-%m-%d') if next_earnings else None,
                }

                if remote_quarter and local_quarter and _quarter_is_newer(remote_quarter, local_quarter):
                    status['reason'] = f'Remote has {remote_quarter}, local has {local_quarter}'
                    needs_update.append(status)
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: NEEDS UPDATE ({status['reason']})")
                elif next_earnings and next_earnings <= cutoff and next_earnings >= now:
                    days_until = (next_earnings - now).days
                    status['days_until'] = days_until
                    upcoming.append(status)
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: Upcoming in {days_until} days ({next_earnings.strftime('%Y-%m-%d')})")
                else:
                    up_to_date.append(status)
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: Up to date (local: {local_quarter})")

            except Exception as e:
                errors.append({'ticker': ticker, 'error': str(e)})
                if not quiet:
                    print(f"  [{idx}/{total}] {ticker}: ERROR — {e}")

    return {
        'needs_update': needs_update,
        'upcoming': upcoming,
        'up_to_date': up_to_date,
        'errors': errors,
    }


def auto_update_stale(stale_tickers, source='both', quiet=False):
    """Re-extract financials for stale tickers.

    Args:
        stale_tickers: list of ticker symbols to update
        source: 'yahoo', 'sec', or 'both'
        quiet: suppress output
    """
    from extract_historical_data import save_single_company

    updated = 0
    failed = 0

    for i, ticker in enumerate(stale_tickers):
        if not quiet:
            print(f"  Updating [{i+1}/{len(stale_tickers)}] {ticker}...")

        # Yahoo Finance
        if source in ('yahoo', 'both'):
            try:
                from data_extractors.equity_financials_extractor import get_company_financials_yahoo
                data = get_company_financials_yahoo(ticker)
                if 'error' not in data:
                    save_single_company(ticker, data, 'Yahoo Finance')
                    if not quiet:
                        print(f"    Yahoo: OK ({len(data.get('quarters', []))} quarters)")
                else:
                    if not quiet:
                        print(f"    Yahoo: FAILED — {data['error']}")
            except Exception as e:
                if not quiet:
                    print(f"    Yahoo: ERROR — {e}")

        # SEC EDGAR
        if source in ('sec', 'both'):
            try:
                from data_extractors.sec_extractor import get_company_financials_sec
                data = get_company_financials_sec(ticker)
                if 'error' not in data:
                    save_single_company(ticker, data, 'SEC EDGAR')
                    if not quiet:
                        print(f"    SEC: OK ({len(data.get('quarters', []))} quarters)")
                else:
                    if not quiet:
                        print(f"    SEC: FAILED — {data['error']}")
            except Exception as e:
                if not quiet:
                    print(f"    SEC: ERROR — {e}")

        updated += 1

        # Rate limiting: pause every 10 tickers
        if (i + 1) % 10 == 0 and i < len(stale_tickers) - 1:
            if not quiet:
                print(f"  Waiting 3s...")
            time.sleep(3)

    return updated


def main():
    parser = argparse.ArgumentParser(
        description='Monitor earnings dates and flag stale local financial data.',
    )
    parser.add_argument(
        '--auto-update', action='store_true',
        help='Automatically re-extract stale tickers after scanning'
    )
    parser.add_argument(
        '--days', type=int, default=14,
        help='Days ahead to show upcoming earnings (default: 14)'
    )
    parser.add_argument(
        '--tickers', type=str, default=None,
        help='Comma-separated list of specific tickers (e.g., AAPL,MSFT)'
    )
    parser.add_argument(
        '--top20-only', action='store_true',
        help='Only check Top 20 companies'
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Minimal output'
    )
    args = parser.parse_args()

    # Determine ticker list
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
    elif args.top20_only:
        from data_extractors.equity_financials_extractor import TOP_20_TICKERS
        tickers = list(TOP_20_TICKERS)
    else:
        tickers = _get_local_tickers(YAHOO_DIR)
        if not tickers:
            print("No local data found. Run extract_sp500_financials.py first.")
            return

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"Earnings Monitor — {ts}")
    print(f"Checking {len(tickers)} tickers (upcoming: {args.days} days ahead)")
    print("=" * 60)

    result = check_earnings(tickers, days_ahead=args.days, quiet=args.quiet)

    # Summary
    print("\n" + "=" * 60)
    print("EARNINGS MONITOR SUMMARY")
    print("=" * 60)

    if result['needs_update']:
        print(f"\n🔴 NEEDS UPDATE ({len(result['needs_update'])}):")
        for item in result['needs_update']:
            print(f"  {item['ticker']:8} | Local: {item['local_quarter'] or 'N/A':8} | "
                  f"Remote: {item['remote_quarter'] or 'N/A':8} | {item.get('company_name', '')}")

    if result['upcoming']:
        print(f"\n🟡 UPCOMING EARNINGS ({len(result['upcoming'])}):")
        for item in sorted(result['upcoming'], key=lambda x: x.get('days_until', 999)):
            days = item.get('days_until', '?')
            print(f"  {item['ticker']:8} | In {days} days ({item['next_earnings']}) | "
                  f"{item.get('company_name', '')}")

    print(f"\n🟢 UP TO DATE: {len(result['up_to_date'])} companies")

    if result['errors']:
        print(f"\n⚠️  ERRORS ({len(result['errors'])}):")
        for item in result['errors']:
            print(f"  {item['ticker']:8} | {item['error']}")

    # Auto-update stale tickers
    if args.auto_update and result['needs_update']:
        stale_tickers = [item['ticker'] for item in result['needs_update']]
        print(f"\n{'=' * 60}")
        print(f"AUTO-UPDATING {len(stale_tickers)} stale tickers...")
        print("=" * 60)
        updated = auto_update_stale(stale_tickers, source='both', quiet=args.quiet)
        print(f"\nUpdated {updated} tickers.")


if __name__ == '__main__':
    main()
