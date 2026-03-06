#!/usr/bin/env python3
"""
Weekly Data Freshness Review — Compares local database against SEC EDGAR filing dates.

For each company, checks the SEC EDGAR submissions endpoint (lightweight, ~100KB per call)
to see if new 10-Q or 10-K filings have been submitted since the last local extraction.
More thorough than monitor_earnings.py — uses authoritative SEC filing dates rather than
yfinance earnings timestamps.

Rate limiting: SEC EDGAR allows 10 req/sec. This script respects the existing 0.15s
per-request rate limit in sec_extractor.py, plus batch-level pauses.
Full S&P 500 review takes ~2 minutes.

Usage:
    python review_data_freshness.py                  # full S&P 500 review
    python review_data_freshness.py --auto-update    # review + re-extract stale tickers
    python review_data_freshness.py --source sec     # only check SEC EDGAR freshness
    python review_data_freshness.py --top20-only     # only review Top 20 companies
    python review_data_freshness.py --report         # save CSV report to data_export/
"""

import argparse
import os
import sys
import time
from datetime import datetime

import pandas as pd

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HISTORICAL_DIR = 'historical_data'
EQUITY_DIR = os.path.join(HISTORICAL_DIR, 'equity_financials')
YAHOO_DIR = os.path.join(EQUITY_DIR, 'yahoo_finance')
SEC_DIR = os.path.join(EQUITY_DIR, 'sec_edgar')
EXPORT_DIR = 'data_export'


def _get_local_state(ticker):
    """Get local data state for a ticker.

    Returns dict with:
        'yahoo_latest_quarter': str or None
        'sec_latest_quarter': str or None
        'yahoo_file_date': str or None (file modification date)
        'sec_file_date': str or None
    """
    state = {
        'yahoo_latest_quarter': None,
        'sec_latest_quarter': None,
        'yahoo_file_date': None,
        'sec_file_date': None,
    }

    # Yahoo
    yahoo_path = os.path.join(YAHOO_DIR, f'{ticker}_quarterly.csv')
    if os.path.exists(yahoo_path):
        try:
            df = pd.read_csv(yahoo_path)
            if 'quarter' in df.columns and len(df) > 0:
                quarters = df['quarter'].dropna().tolist()
                if quarters:
                    state['yahoo_latest_quarter'] = quarters[0]
            state['yahoo_file_date'] = datetime.fromtimestamp(
                os.path.getmtime(yahoo_path)).strftime('%Y-%m-%d')
        except Exception:
            pass

    # SEC
    sec_path = os.path.join(SEC_DIR, f'{ticker}_quarterly.csv')
    if os.path.exists(sec_path):
        try:
            df = pd.read_csv(sec_path)
            if 'quarter' in df.columns and len(df) > 0:
                quarters = df['quarter'].dropna().tolist()
                if quarters:
                    state['sec_latest_quarter'] = quarters[0]
            state['sec_file_date'] = datetime.fromtimestamp(
                os.path.getmtime(sec_path)).strftime('%Y-%m-%d')
        except Exception:
            pass

    return state


def _parse_quarter(q_str):
    """Parse '2025-Q4' into (year, quarter_num) tuple or None."""
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
    """Returns True if q1 is strictly newer than q2."""
    q1 = _parse_quarter(q1_str)
    q2 = _parse_quarter(q2_str)
    if q1 is None or q2 is None:
        return False
    return q1 > q2


def review_freshness(tickers, quiet=False):
    """
    Review data freshness by comparing local data against SEC EDGAR filing dates.

    Args:
        tickers: list of ticker symbols
        quiet: suppress per-ticker output

    Returns:
        dict with 'stale_sec', 'stale_yahoo', 'up_to_date', 'no_local_data', 'errors'
    """
    from data_extractors.sec_extractor import get_latest_filing_dates

    stale_sec = []      # SEC has newer quarter than local SEC data
    stale_yahoo = []    # SEC has newer quarter than local Yahoo data
    up_to_date = []
    no_local_data = []
    errors = []

    total = len(tickers)
    batch_size = 50
    batches = [tickers[i:i + batch_size] for i in range(0, total, batch_size)]

    for batch_idx, batch in enumerate(batches):
        if not quiet and batch_idx > 0:
            print(f"  Waiting 3s before next batch...")
            time.sleep(3)

        for i, ticker in enumerate(batch):
            idx = batch_idx * batch_size + i + 1
            try:
                # Get local state
                local = _get_local_state(ticker)

                # No local data at all?
                if local['yahoo_latest_quarter'] is None and local['sec_latest_quarter'] is None:
                    no_local_data.append({
                        'ticker': ticker,
                        'reason': 'No local CSVs found',
                    })
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: No local data")
                    continue

                # Get SEC filing dates (lightweight)
                sec_info = get_latest_filing_dates(ticker)

                if 'error' in sec_info:
                    # CIK not found — might be a foreign issuer
                    up_to_date.append({
                        'ticker': ticker,
                        'yahoo_quarter': local['yahoo_latest_quarter'],
                        'sec_quarter': local['sec_latest_quarter'],
                        'note': f"SEC lookup failed: {sec_info['error']}",
                    })
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: SEC lookup failed ({sec_info['error']})")
                    continue

                # Determine latest SEC quarter from filing dates
                sec_latest_quarter = None
                latest_10q = sec_info.get('latest_10q')
                latest_10k = sec_info.get('latest_10k')

                if latest_10q and latest_10q.get('quarter'):
                    sec_latest_quarter = latest_10q['quarter']

                # 10-K might indicate a newer FY-end quarter
                if latest_10k and latest_10k.get('report_date'):
                    try:
                        dt = datetime.strptime(latest_10k['report_date'], '%Y-%m-%d')
                        q = (dt.month - 1) // 3 + 1
                        k_quarter = f"{dt.year}-Q{q}"
                        if sec_latest_quarter is None or _quarter_is_newer(k_quarter, sec_latest_quarter):
                            sec_latest_quarter = k_quarter
                    except (ValueError, TypeError):
                        pass

                if sec_latest_quarter is None:
                    up_to_date.append({
                        'ticker': ticker,
                        'yahoo_quarter': local['yahoo_latest_quarter'],
                        'sec_quarter': local['sec_latest_quarter'],
                        'note': 'No SEC quarter info available',
                    })
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: No SEC quarter info")
                    continue

                # Compare: SEC has newer quarter than local?
                entry = {
                    'ticker': ticker,
                    'yahoo_quarter': local['yahoo_latest_quarter'],
                    'sec_local_quarter': local['sec_latest_quarter'],
                    'sec_remote_quarter': sec_latest_quarter,
                    'sec_filing_date': (latest_10q or {}).get('filing_date'),
                    'yahoo_file_date': local['yahoo_file_date'],
                    'sec_file_date': local['sec_file_date'],
                }

                is_sec_stale = _quarter_is_newer(sec_latest_quarter, local['sec_latest_quarter'] or '')
                is_yahoo_stale = _quarter_is_newer(sec_latest_quarter, local['yahoo_latest_quarter'] or '')

                if is_sec_stale:
                    entry['reason'] = f"SEC remote: {sec_latest_quarter}, local SEC: {local['sec_latest_quarter'] or 'N/A'}"
                    stale_sec.append(entry)
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: SEC STALE ({entry['reason']})")
                elif is_yahoo_stale:
                    entry['reason'] = f"SEC remote: {sec_latest_quarter}, local Yahoo: {local['yahoo_latest_quarter'] or 'N/A'}"
                    stale_yahoo.append(entry)
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: YAHOO STALE ({entry['reason']})")
                else:
                    up_to_date.append(entry)
                    if not quiet:
                        print(f"  [{idx}/{total}] {ticker}: Up to date ({sec_latest_quarter})")

            except Exception as e:
                errors.append({'ticker': ticker, 'error': str(e)})
                if not quiet:
                    print(f"  [{idx}/{total}] {ticker}: ERROR — {e}")

    return {
        'stale_sec': stale_sec,
        'stale_yahoo': stale_yahoo,
        'up_to_date': up_to_date,
        'no_local_data': no_local_data,
        'errors': errors,
    }


def save_report(result, output_dir=EXPORT_DIR):
    """Save freshness report as CSV."""
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    for item in result['stale_sec']:
        rows.append({**item, 'status': 'stale_sec'})
    for item in result['stale_yahoo']:
        rows.append({**item, 'status': 'stale_yahoo'})
    for item in result['up_to_date']:
        rows.append({**item, 'status': 'up_to_date'})
    for item in result['no_local_data']:
        rows.append({**item, 'status': 'no_local_data'})
    for item in result['errors']:
        rows.append({**item, 'status': 'error'})

    df = pd.DataFrame(rows)
    report_path = os.path.join(output_dir, 'freshness_report.csv')
    df.to_csv(report_path, index=False)
    return report_path


def auto_update_stale(stale_tickers, source='both', quiet=False):
    """Re-extract financials for stale tickers."""
    from extract_historical_data import save_single_company

    updated = 0
    batch_size = 25
    batches = [stale_tickers[i:i + batch_size] for i in range(0, len(stale_tickers), batch_size)]

    for batch_idx, batch in enumerate(batches):
        if batch_idx > 0:
            if not quiet:
                print(f"  Waiting 5s before next batch...")
            time.sleep(5)

        for ticker in batch:
            if not quiet:
                print(f"  Updating {ticker}...", end=' ', flush=True)

            if source in ('yahoo', 'both'):
                try:
                    from data_extractors.equity_financials_extractor import get_company_financials_yahoo
                    data = get_company_financials_yahoo(ticker)
                    if 'error' not in data:
                        save_single_company(ticker, data, 'Yahoo Finance')
                        if not quiet:
                            print(f"Yahoo OK", end=' ')
                except Exception as e:
                    if not quiet:
                        print(f"Yahoo ERR", end=' ')

            if source in ('sec', 'both'):
                try:
                    from data_extractors.sec_extractor import get_company_financials_sec
                    data = get_company_financials_sec(ticker)
                    if 'error' not in data:
                        save_single_company(ticker, data, 'SEC EDGAR')
                        if not quiet:
                            print(f"SEC OK", end=' ')
                except Exception as e:
                    if not quiet:
                        print(f"SEC ERR", end=' ')

            if not quiet:
                print()
            updated += 1

    return updated


def main():
    parser = argparse.ArgumentParser(
        description='Weekly data freshness review — compares local data against SEC EDGAR.',
    )
    parser.add_argument(
        '--auto-update', action='store_true',
        help='Automatically re-extract stale tickers after review'
    )
    parser.add_argument(
        '--source', choices=['sec', 'yahoo', 'both'], default='both',
        help='Which local source to check freshness for (default: both)'
    )
    parser.add_argument(
        '--top20-only', action='store_true',
        help='Only review Top 20 companies'
    )
    parser.add_argument(
        '--report', action='store_true',
        help='Save CSV report to data_export/freshness_report.csv'
    )
    parser.add_argument(
        '--tickers', type=str, default=None,
        help='Comma-separated list of specific tickers'
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
        # Use all tickers in the S&P 500 list (or fall back to local CSVs)
        try:
            from data_extractors.sp500_tickers import get_sp500_tickers
            tickers = get_sp500_tickers()
        except Exception:
            # Fallback: use tickers from local Yahoo CSVs
            tickers = []
            if os.path.isdir(YAHOO_DIR):
                for f in sorted(os.listdir(YAHOO_DIR)):
                    if f.endswith('_quarterly.csv') and not f.startswith('_'):
                        tickers.append(f.replace('_quarterly.csv', ''))
            if not tickers:
                print("No tickers found. Run extract_sp500_financials.py first.")
                return

    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"Data Freshness Review — {ts}")
    print(f"Checking {len(tickers)} tickers against SEC EDGAR filing dates")
    print("=" * 60)

    result = review_freshness(tickers, quiet=args.quiet)

    # Summary
    print("\n" + "=" * 60)
    print("FRESHNESS REVIEW SUMMARY")
    print("=" * 60)

    if result['stale_sec']:
        print(f"\n🔴 SEC DATA STALE ({len(result['stale_sec'])}):")
        for item in result['stale_sec']:
            print(f"  {item['ticker']:8} | Local SEC: {item.get('sec_local_quarter', 'N/A'):8} | "
                  f"Remote: {item.get('sec_remote_quarter', 'N/A'):8} | "
                  f"Filed: {item.get('sec_filing_date', 'N/A')}")

    if result['stale_yahoo']:
        print(f"\n🟡 YAHOO DATA STALE ({len(result['stale_yahoo'])}):")
        for item in result['stale_yahoo']:
            print(f"  {item['ticker']:8} | Local Yahoo: {item.get('yahoo_quarter', 'N/A'):8} | "
                  f"Remote: {item.get('sec_remote_quarter', 'N/A'):8}")

    if result['no_local_data']:
        print(f"\n⚪ NO LOCAL DATA ({len(result['no_local_data'])}):")
        # Only show first 20
        for item in result['no_local_data'][:20]:
            print(f"  {item['ticker']:8} | {item.get('reason', '')}")
        if len(result['no_local_data']) > 20:
            print(f"  ... and {len(result['no_local_data']) - 20} more")

    print(f"\n🟢 UP TO DATE: {len(result['up_to_date'])} companies")

    if result['errors']:
        print(f"\n⚠️  ERRORS ({len(result['errors'])}):")
        for item in result['errors'][:10]:
            print(f"  {item['ticker']:8} | {item['error']}")
        if len(result['errors']) > 10:
            print(f"  ... and {len(result['errors']) - 10} more")

    total_stale = len(result['stale_sec']) + len(result['stale_yahoo'])
    total_checked = (len(result['stale_sec']) + len(result['stale_yahoo']) +
                     len(result['up_to_date']) + len(result['no_local_data']) +
                     len(result['errors']))
    print(f"\nTotal: {total_checked} checked, {total_stale} stale, "
          f"{len(result['no_local_data'])} missing, {len(result['errors'])} errors")

    # Save report
    if args.report:
        report_path = save_report(result)
        print(f"\nReport saved to: {report_path}")

    # Auto-update stale tickers
    if args.auto_update and total_stale > 0:
        all_stale = ([item['ticker'] for item in result['stale_sec']] +
                     [item['ticker'] for item in result['stale_yahoo']])
        # Deduplicate while preserving order
        seen = set()
        unique_stale = []
        for t in all_stale:
            if t not in seen:
                seen.add(t)
                unique_stale.append(t)

        print(f"\n{'=' * 60}")
        print(f"AUTO-UPDATING {len(unique_stale)} stale tickers...")
        print("=" * 60)
        updated = auto_update_stale(unique_stale, source='both', quiet=args.quiet)
        print(f"\nUpdated {updated} tickers.")


if __name__ == '__main__':
    main()
