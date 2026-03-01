#!/usr/bin/env python3
"""
Catch-up data extraction script for macroeconomic indicators.

Run this whenever you start your machine to refresh all macro data.
It updates three local stores so the Streamlit dashboard loads instantly:

    data_cache/             -> JSON cache for fast dashboard startup
    historical_data/        -> Append-only CSVs for long-term archival
    data_export/            -> Latest-value CSVs for quick export

Usage:
    python scheduled_extract.py            # normal catch-up
    python scheduled_extract.py --force    # force refresh even if cache is fresh
    python scheduled_extract.py --cron     # quiet mode for cron/launchd

Schedule with cron (macOS/Linux) - runs at 9am, 1pm, 5pm on weekdays:
    crontab -e
    0 9,13,17 * * 1-5 cd /Users/kriszhang/Github/macro_2 && python scheduled_extract.py --cron >> logs/extract.log 2>&1

Schedule with launchd (macOS) - see CLAUDE.md for .plist example.
"""

import argparse
import sys
import os
import time
from datetime import datetime

# Ensure we can import project modules when run from any directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def get_last_cache_time():
    """Read the last cache timestamp. Returns datetime or None."""
    from utils.helpers import get_cache_timestamp
    return get_cache_timestamp('all_indicators', cache_dir='data_cache')


def print_gap_info(last_time, quiet=False):
    """Print how long since last data refresh."""
    if quiet:
        return
    if last_time is None:
        print("No previous data found. Will perform a full extraction.")
        return

    gap = datetime.now() - last_time
    hours = gap.total_seconds() / 3600
    if hours < 1:
        minutes = gap.total_seconds() / 60
        print(f"Last data refresh: {last_time.strftime('%Y-%m-%d %H:%M:%S')} ({minutes:.0f} minutes ago)")
    elif hours < 24:
        print(f"Last data refresh: {last_time.strftime('%Y-%m-%d %H:%M:%S')} ({hours:.1f} hours ago)")
    else:
        days = hours / 24
        print(f"Last data refresh: {last_time.strftime('%Y-%m-%d %H:%M:%S')} ({days:.1f} days ago)")


def run_extraction(force=False, quiet=False):
    """
    Main extraction routine.

    1. Check last cache timestamp
    2. Skip if data is fresh (< 1 hour), unless --force
    3. Fetch all 21 indicators -> saves to data_cache/
    4. Append to historical_data/ CSVs
    5. Export latest to data_export/ CSVs
    6. Print summary
    """
    start_time = time.time()

    # ── Step 1: Check freshness ──────────────────────────────────────
    last_time = get_last_cache_time()
    print_gap_info(last_time, quiet=quiet)

    freshness_threshold_hours = 1
    if last_time is not None and not force:
        gap_hours = (datetime.now() - last_time).total_seconds() / 3600
        if gap_hours < freshness_threshold_hours:
            if not quiet:
                print(f"\nData is fresh (< {freshness_threshold_hours}h old). Skipping.")
                print("Use --force to refresh anyway.")
            return

    if not quiet:
        print("\n" + "=" * 60)
        print("Starting data extraction...")
        print("=" * 60)

    # ── Step 2: Fetch all indicators -> data_cache/ ──────────────────
    if not quiet:
        print("\n[1/3] Fetching all 21 indicators (saves to data_cache/)...")

    from data_aggregator import get_aggregator
    aggregator = get_aggregator()
    aggregator.fetch_all_indicators()  # automatically saves to data_cache/

    successful = len([
        k for k, v in aggregator.indicators.items()
        if not (isinstance(v, dict) and 'error' in v)
    ])
    failed = len(aggregator.indicators) - successful

    # ── Step 3: Append to historical CSVs ────────────────────────────
    if not quiet:
        print(f"\n[2/3] Appending to historical CSVs (historical_data/)...")

    try:
        from extract_historical_data import extract_all_historical_data
        hist_results = extract_all_historical_data()
        if not quiet:
            print(f"  Historical CSV update complete.")
    except Exception as e:
        if not quiet:
            print(f"  Warning: historical CSV update failed: {e}")

    # ── Step 4: Export latest snapshot CSVs ───────────────────────────
    if not quiet:
        print(f"\n[3/3] Exporting latest values to CSV (data_export/)...")

    try:
        export_result = aggregator.export_to_csv(output_dir='data_export')
        if not quiet:
            print(f"  Exported {export_result.get('count', 0)} files to data_export/")
    except Exception as e:
        if not quiet:
            print(f"  Warning: CSV export failed: {e}")

    # ── Summary ──────────────────────────────────────────────────────
    elapsed = time.time() - start_time

    if not quiet:
        print("\n" + "=" * 60)
        print(f"Extraction complete!")
        print(f"  Indicators: {successful} succeeded, {failed} failed")
        print(f"  Time: {elapsed:.1f}s")
        print(f"  Cache: data_cache/all_indicators.json")
        print(f"  CSVs:  historical_data/ + data_export/")
        print("=" * 60)

        if aggregator.errors:
            print(f"\nErrors ({len(aggregator.errors)}):")
            for err in aggregator.errors:
                print(f"  - {err}")

        print(f"\nDashboard will load instantly from cache on next startup:")
        print(f"  streamlit run app.py")
    else:
        # Cron-style one-liner for log files
        ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{ts}] Extracted {successful}/{successful + failed} indicators in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description='Catch-up data extraction for macroeconomic indicators.',
        epilog='Run this whenever you start your machine, or schedule via cron/launchd.'
    )
    parser.add_argument(
        '--force', '-f',
        action='store_true',
        help='Force refresh even if cache is fresh (< 1 hour old)'
    )
    parser.add_argument(
        '--cron',
        action='store_true',
        help='Quiet mode for cron/launchd (minimal output for log files)'
    )
    args = parser.parse_args()

    run_extraction(force=args.force, quiet=args.cron)


if __name__ == '__main__':
    main()
