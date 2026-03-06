#!/usr/bin/env python3
"""
Batch extraction of S&P 500 equity financials.

Downloads quarterly financial data for all ~500 S&P 500 companies and saves
to historical_data/equity_financials/{yahoo_finance|sec_edgar}/ CSVs.

This is a long-running script (~30-40 min for full run) and is separate from
scheduled_extract.py (which has a 10-minute timeout).

Usage:
    python extract_sp500_financials.py                              # full S&P 500, Yahoo
    python extract_sp500_financials.py --source both                # Yahoo + SEC
    python extract_sp500_financials.py --source sec                 # SEC only
    python extract_sp500_financials.py --batch-size 10 --delay 3    # custom batching
    python extract_sp500_financials.py --resume                     # skip tickers with existing CSVs
    python extract_sp500_financials.py --exclude-top20              # skip Top 20 (already in scheduled_extract)
    python extract_sp500_financials.py --tickers CRM,AMD,NFLX      # specific tickers only
"""

import warnings
# Suppress pandas FutureWarnings (concat with empty columns) — must be before pandas import
warnings.filterwarnings('ignore', category=FutureWarning)

import argparse
import os
import sys
import time
import shutil
from datetime import datetime

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HISTORICAL_DIR = 'historical_data'
EQUITY_DIR = os.path.join(HISTORICAL_DIR, 'equity_financials')
YAHOO_DIR = os.path.join(EQUITY_DIR, 'yahoo_finance')
SEC_DIR = os.path.join(EQUITY_DIR, 'sec_edgar')

# ── Progress bar ──────────────────────────────────────────────────────

_BAR_FILL = '█'
_BAR_EMPTY = '░'


def _progress_bar(current, total, width=30):
    """Return a progress bar string like: ██████████░░░░░░░░░░  50%"""
    pct = current / total if total > 0 else 0
    filled = int(width * pct)
    bar = _BAR_FILL * filled + _BAR_EMPTY * (width - filled)
    return f"{bar} {pct:>6.1%}"


def _eta_str(elapsed, current, total):
    """Return ETA string like: ETA 4m 32s"""
    if current <= 0:
        return ''
    rate = elapsed / current
    remaining = rate * (total - current)
    if remaining < 60:
        return f"ETA {remaining:.0f}s"
    return f"ETA {remaining / 60:.0f}m {remaining % 60:.0f}s"


_IS_TTY = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


def _print_status_line(current, total, ticker, source_tag, status, elapsed):
    """Print a single-line progress update.

    On a real terminal (TTY), uses \\r to overwrite the previous line
    so you see a live-updating progress bar.
    In non-TTY (piped/redirected/background), only prints on
    completion of each ticker (not the intermediate '...' states)
    to avoid flooding the log.
    """
    bar = _progress_bar(current, total)
    eta = _eta_str(elapsed, current, total)
    counter = f"{current}/{total}"
    tag = f"({source_tag})" if source_tag else ''
    core = f"  {bar}  {counter}  {ticker} {tag} {status}  {eta}"

    if _IS_TTY:
        cols = shutil.get_terminal_size((80, 24)).columns
        line = f"\r{core}"
        line = line[:cols].ljust(cols)
        print(line, end='', flush=True)
    else:
        # Non-TTY: only print finished states (✓, FAIL, ERROR, DONE), skip '...'
        if status not in ('...', ''):
            print(core.strip())


# ── Core extraction ───────────────────────────────────────────────────

def _ensure_dirs():
    """Create output directories."""
    for d in [YAHOO_DIR, SEC_DIR]:
        os.makedirs(d, exist_ok=True)


def _existing_tickers(source_dir):
    """Get set of tickers that already have CSVs in a directory."""
    tickers = set()
    if os.path.isdir(source_dir):
        for f in os.listdir(source_dir):
            if f.endswith('_quarterly.csv') and not f.startswith('_'):
                tickers.add(f.replace('_quarterly.csv', ''))
    return tickers


def _save_single(ticker, company_data, source_dir, source_label):
    """Save a single company's data to CSV using the shared logic."""
    from extract_historical_data import _save_equity_source
    companies = {ticker: company_data}
    return _save_equity_source(companies, source_dir, source_label)


def extract_batch(tickers, source='yahoo', batch_size=25, delay=5, quiet=False):
    """
    Extract financials for a list of tickers in batches.

    Args:
        tickers: list of ticker symbols
        source: 'yahoo', 'sec', or 'both'
        batch_size: number of tickers per batch
        delay: seconds to wait between batches
        quiet: suppress per-ticker output

    Returns:
        dict with 'successful', 'failed', 'errors', 'elapsed' keys
    """
    _ensure_dirs()
    start_time = time.time()

    total = len(tickers)
    successful = 0
    failed = 0
    errors = []

    # Split into batches
    batches = [tickers[i:i + batch_size] for i in range(0, total, batch_size)]

    for batch_idx, batch in enumerate(batches):
        for ticker in batch:
            done = successful + failed
            elapsed = time.time() - start_time

            try:
                # Yahoo Finance
                if source in ('yahoo', 'both'):
                    if not quiet:
                        _print_status_line(done, total, ticker, 'Yahoo', '...', elapsed)
                    from data_extractors.equity_financials_extractor import get_company_financials_yahoo
                    yahoo_data = get_company_financials_yahoo(ticker)

                    if 'error' in yahoo_data:
                        if not quiet:
                            _print_status_line(done, total, ticker, 'Yahoo', 'FAIL', elapsed)
                            if _IS_TTY:
                                print()
                        if source == 'yahoo':
                            failed += 1
                            errors.append(f"{ticker} (Yahoo): {yahoo_data['error']}")
                            continue
                    else:
                        _save_single(ticker, yahoo_data, YAHOO_DIR, 'Yahoo Finance')
                        q_count = len(yahoo_data.get('quarters', []))
                        if not quiet:
                            _print_status_line(done, total, ticker, 'Yahoo', f"✓ {q_count}Q", elapsed)

                # SEC EDGAR
                if source in ('sec', 'both'):
                    if not quiet:
                        _print_status_line(done, total, ticker, 'SEC', '...', elapsed)
                    from data_extractors.sec_extractor import get_company_financials_sec
                    sec_data = get_company_financials_sec(ticker)

                    if 'error' in sec_data:
                        if not quiet:
                            _print_status_line(done, total, ticker, 'SEC', 'FAIL', elapsed)
                            if _IS_TTY:
                                print()
                        if source == 'sec':
                            failed += 1
                            errors.append(f"{ticker} (SEC): {sec_data['error']}")
                            continue
                    else:
                        _save_single(ticker, sec_data, SEC_DIR, 'SEC EDGAR')
                        q_count = len(sec_data.get('quarters', []))
                        if not quiet:
                            _print_status_line(done, total, ticker, 'SEC', f"✓ {q_count}Q", elapsed)

                successful += 1

            except Exception as e:
                failed += 1
                errors.append(f"{ticker}: {str(e)}")
                if not quiet:
                    _print_status_line(done, total, ticker, source, 'ERROR', elapsed)
                    if _IS_TTY:
                        print()

        # Delay between batches (not after last batch)
        if batch_idx < len(batches) - 1:
            done = successful + failed
            elapsed = time.time() - start_time
            if not quiet:
                _print_status_line(done, total, '', '', f'batch pause {delay}s', elapsed)
            time.sleep(delay)

    # Final progress line
    if not quiet:
        done = successful + failed
        elapsed = time.time() - start_time
        _print_status_line(done, total, 'DONE', source, f'✓ {successful} ok, {failed} err', elapsed)
        if _IS_TTY:
            print()

    elapsed = time.time() - start_time
    return {
        'successful': successful,
        'failed': failed,
        'total': total,
        'errors': errors,
        'elapsed': elapsed,
    }


def main():
    parser = argparse.ArgumentParser(
        description='Batch extract S&P 500 equity financials.',
        epilog='Long-running (~30-40 min for full S&P 500). Separate from scheduled_extract.py.'
    )
    parser.add_argument(
        '--source', choices=['yahoo', 'sec', 'both'], default='yahoo',
        help='Data source to extract from (default: yahoo)'
    )
    parser.add_argument(
        '--batch-size', type=int, default=25,
        help='Number of tickers per batch (default: 25)'
    )
    parser.add_argument(
        '--delay', type=int, default=5,
        help='Seconds to wait between batches (default: 5)'
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Skip tickers that already have CSV files'
    )
    parser.add_argument(
        '--exclude-top20', action='store_true',
        help='Exclude Top 20 tickers (already handled by scheduled_extract.py)'
    )
    parser.add_argument(
        '--tickers', type=str, default=None,
        help='Comma-separated list of specific tickers (e.g., CRM,AMD,NFLX)'
    )
    parser.add_argument(
        '--quiet', '-q', action='store_true',
        help='Minimal output'
    )
    args = parser.parse_args()

    # Determine ticker list
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(',')]
        print(f"Extracting {len(tickers)} specified tickers")
    else:
        from data_extractors.sp500_tickers import get_sp500_tickers
        tickers = get_sp500_tickers()
        print(f"S&P 500: {len(tickers)} tickers")

    # Exclude Top 20 if requested
    if args.exclude_top20:
        from data_extractors.equity_financials_extractor import TOP_20_TICKERS
        top20_set = set(TOP_20_TICKERS)
        before = len(tickers)
        tickers = [t for t in tickers if t not in top20_set]
        print(f"Excluded Top 20: {before} → {len(tickers)} tickers")

    # Resume: skip tickers with existing CSVs
    if args.resume:
        existing = set()
        if args.source in ('yahoo', 'both'):
            existing |= _existing_tickers(YAHOO_DIR)
        if args.source in ('sec', 'both'):
            existing |= _existing_tickers(SEC_DIR)
        before = len(tickers)
        tickers = [t for t in tickers if t not in existing]
        print(f"Resume: skipping {before - len(tickers)} existing, {len(tickers)} remaining")

    if not tickers:
        print("No tickers to extract.")
        return

    # Run extraction
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"\nStarting extraction at {ts}")
    print(f"Source: {args.source} | Batch size: {args.batch_size} | Delay: {args.delay}s")
    print(f"Tickers: {len(tickers)}")
    print("=" * 60)

    result = extract_batch(
        tickers,
        source=args.source,
        batch_size=args.batch_size,
        delay=args.delay,
        quiet=args.quiet,
    )

    # Summary
    print("\n" + "=" * 60)
    print(f"Extraction complete!")
    print(f"  ✅ Successful: {result['successful']}/{result['total']}")
    print(f"  ❌ Failed:     {result['failed']}/{result['total']}")
    print(f"  ⏱  Time:      {result['elapsed']:.1f}s ({result['elapsed']/60:.1f} min)")
    print(f"  📁 Output:    {EQUITY_DIR}/")

    if result['errors']:
        print(f"\nErrors ({len(result['errors'])}):")
        for err in result['errors'][:20]:
            print(f"  - {err}")
        if len(result['errors']) > 20:
            print(f"  ... and {len(result['errors']) - 20} more")


if __name__ == '__main__':
    main()
