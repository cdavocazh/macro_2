#!/usr/bin/env python3
"""
Extract 13F-HR institutional fund holdings from SEC EDGAR.

Downloads and parses 13F filings for tracked institutional investors,
saves per-quarter holdings snapshots and computed QoQ changes to
historical_data/13F/{fund_name}/.

Usage:
    python extract_13f_holdings.py                              # all funds, last 8 quarters
    python extract_13f_holdings.py --funds berkshire_hathaway,citadel
    python extract_13f_holdings.py --max-filings 4              # only last 4 quarters
    python extract_13f_holdings.py --list-funds                 # show available funds
"""

import argparse
import os
import sys
from datetime import datetime

# Ensure we can import project modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_extractors.thirteenf_extractor import (
    FUND_REGISTRY,
    extract_all_funds,
)


def main():
    parser = argparse.ArgumentParser(
        description='Extract 13F-HR institutional fund holdings from SEC EDGAR'
    )
    parser.add_argument(
        '--funds',
        type=str,
        default=None,
        help='Comma-separated fund keys (default: all). Use --list-funds to see options.'
    )
    parser.add_argument(
        '--max-filings',
        type=int,
        default=8,
        help='Number of quarterly filings per fund (default: 8 = ~2 years)'
    )
    parser.add_argument(
        '--list-funds',
        action='store_true',
        help='Show available funds and exit'
    )
    args = parser.parse_args()

    # List funds mode
    if args.list_funds:
        print('Available funds:')
        print(f'  {"Key":<30s} {"Name":<35s} {"CIK"}')
        print('  ' + '-' * 80)
        for key, info in FUND_REGISTRY.items():
            print(f'  {key:<30s} {info["name"]:<35s} {info["cik"]}')
        return

    # Parse fund selection
    funds = None
    if args.funds:
        funds = [f.strip() for f in args.funds.split(',')]
        invalid = [f for f in funds if f not in FUND_REGISTRY]
        if invalid:
            print(f'Error: Unknown fund(s): {", ".join(invalid)}')
            print(f'Valid funds: {", ".join(FUND_REGISTRY.keys())}')
            sys.exit(1)

    # Run extraction
    print('=' * 70)
    print('13F INSTITUTIONAL HOLDINGS EXTRACTION')
    print('=' * 70)
    print(f'Started: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'Funds: {len(funds) if funds else len(FUND_REGISTRY)}')
    print(f'Max filings per fund: {args.max_filings}')

    result = extract_all_funds(
        max_filings=args.max_filings,
        funds=funds,
    )

    # Summary
    print('\n' + '=' * 70)
    print('SUMMARY')
    print('=' * 70)
    for r in result['results']:
        if 'error' in r:
            fund_key = r.get('fund', 'unknown')
            print(f'  ❌ {fund_key}: {r["error"]}')
        else:
            print(f'  ✅ {r["fund_name"]}: {r["holdings_saved"]} quarters, '
                  f'{r["total_changes"]} position changes')

    print(f'\nOutput directory: historical_data/13F/')
    print(f'Elapsed: {result["elapsed"]:.1f}s')


if __name__ == '__main__':
    main()
