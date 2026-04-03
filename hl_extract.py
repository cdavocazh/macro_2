#!/usr/bin/env python3
"""
Minutely extraction of Hyperliquid perpetual futures & HIP-3 spot data.

Only calls the Hyperliquid REST API (2-3 HTTP calls, ~0.5s total).
Updates the shared cache via partial merge (only keys 84/85).
Crypto markets are 24/7, so this runs continuously.

Usage:
    python hl_extract.py             # normal run
    python hl_extract.py --cron      # quiet mode for launchd logs
    python hl_extract.py --force     # ignore freshness guard
    python hl_extract.py --dry-run   # show what would be extracted

Schedule: com.macro2.hl-extract.plist (every 60 seconds)
"""

import argparse
import json
import os
import socket
import sys
import tempfile
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Freshness guard: skip if last run was < 45 seconds ago
_FRESHNESS_SECONDS = 45
_FRESHNESS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data_cache', '.hl_extract_timestamp'
)
_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data_cache', 'all_indicators.json'
)


def _check_freshness(force=False):
    """Return True if extraction should proceed."""
    if force:
        return True
    try:
        if os.path.exists(_FRESHNESS_FILE):
            mtime = os.path.getmtime(_FRESHNESS_FILE)
            age_sec = time.time() - mtime
            if age_sec < _FRESHNESS_SECONDS:
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
    """Quick network check (Hyperliquid API)."""
    try:
        socket.create_connection(('api.hyperliquid.xyz', 443), timeout=5).close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False


def _partial_cache_update(perps_data, spot_data):
    """Merge HL data into existing cache without full re-extraction.

    Uses atomic write (tempfile + os.replace) to prevent corruption.
    """
    if not os.path.exists(_CACHE_FILE):
        return False

    from utils.helpers import _serialize_value

    try:
        with open(_CACHE_FILE, 'r') as f:
            cache = json.load(f)

        data = cache.get('data', {})
        data['84_hl_perps'] = _serialize_value(perps_data)
        data['85_hl_spot_stocks'] = _serialize_value(spot_data)
        cache['data'] = data
        cache['timestamp'] = datetime.now().isoformat()

        # Atomic write: write to temp file, then rename
        cache_dir = os.path.dirname(_CACHE_FILE)
        fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.json')
        try:
            with os.fdopen(fd, 'w') as f:
                json.dump(cache, f, default=str)
            os.replace(tmp_path, _CACHE_FILE)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        return True
    except Exception as e:
        # Don't fail silently — log the error
        print(f"  Cache merge error: {e}")
        return False


def _append_to_csv(perps_data, spot_data):
    """Append snapshot to historical CSVs."""
    import pandas as pd
    from extract_historical_data import append_to_csv
    from data_extractors.hyperliquid_extractor import HL_PERPS, HL_SPOT_STOCKS

    ts = datetime.now()

    # Perps CSV
    row = {'timestamp': ts, 'date': ts.date()}
    for hl_ticker, info in HL_PERPS.items():
        k = info['key']
        coin = perps_data.get(k, {})
        if isinstance(coin, dict) and 'price' in coin:
            row[f'hl_{k}_price'] = coin.get('price')
            row[f'hl_{k}_funding'] = coin.get('funding_rate')
            row[f'hl_{k}_oi'] = coin.get('open_interest')
            row[f'hl_{k}_volume_24h'] = coin.get('volume_24h')

    if len(row) > 2:
        df = pd.DataFrame([row])
        append_to_csv('hl_perps.csv', df)

    # Spot stocks CSV
    row2 = {'timestamp': ts, 'date': ts.date()}
    for ticker in HL_SPOT_STOCKS:
        k = ticker.lower()
        coin = spot_data.get(k, {})
        if isinstance(coin, dict) and 'price' in coin:
            row2[f'hl_{k}_price'] = coin.get('price')
            row2[f'hl_{k}_volume_24h'] = coin.get('volume_24h')

    if len(row2) > 2:
        df2 = pd.DataFrame([row2])
        append_to_csv('hl_spot_stocks.csv', df2)


def run_hl_extraction(force=False, quiet=False, dry_run=False):
    """Extract Hyperliquid data and update cache."""
    start_time = time.time()

    if dry_run:
        print("Hyperliquid extract: would fetch perps + HIP-3 spot stocks")
        print("  Perps: BTC, ETH, SOL, PAXG, HYPE, XRP, LINK, DOGE, AVAX, SUI")
        print("  HIP-3 Stocks: TSLA, NVDA, AAPL, GOOGL, AMZN, META, MSFT, SPY, QQQ")
        return

    if not _check_freshness(force):
        if not quiet:
            print(f"HL extract: skipped (< {_FRESHNESS_SECONDS}s since last run)")
        return

    if not _check_network():
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] HL extract: no network")
        return

    from data_extractors.hyperliquid_extractor import get_hl_snapshot

    try:
        perps_data, spot_data = get_hl_snapshot()
    except Exception as e:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] HL extract: API error: {e}")
        return

    # Check for top-level errors
    perps_ok = not (isinstance(perps_data, dict) and 'error' in perps_data
                    and len(perps_data) == 1)
    spots_ok = not (isinstance(spot_data, dict) and 'error' in spot_data
                    and len(spot_data) == 1)

    if not perps_ok and not spots_ok:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] HL extract: both perps and spots failed")
        return

    # Update shared cache
    _partial_cache_update(perps_data, spot_data)

    # Append to historical CSVs
    try:
        _append_to_csv(perps_data, spot_data)
    except Exception:
        pass  # CSV append is best-effort

    _update_freshness()

    elapsed = time.time() - start_time
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Count successful instruments
    perp_count = sum(1 for k, v in perps_data.items()
                     if isinstance(v, dict) and 'price' in v)
    spot_count = sum(1 for k, v in spot_data.items()
                     if isinstance(v, dict) and 'price' in v)

    if quiet:
        print(f"[{ts}] HL: {perp_count}perps+{spot_count}spots in {elapsed:.1f}s")
    else:
        print(f"\nHyperliquid extraction: {perp_count} perps, {spot_count} spots in {elapsed:.1f}s")


def main():
    parser = argparse.ArgumentParser(
        description='Minutely extraction of Hyperliquid perpetual futures data.'
    )
    parser.add_argument('--force', '-f', action='store_true',
                        help='Ignore freshness guard')
    parser.add_argument('--cron', action='store_true',
                        help='Quiet mode for launchd logs')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be extracted')
    args = parser.parse_args()

    run_hl_extraction(force=args.force, quiet=args.cron, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
    # Force exit — library threads can prevent process termination (blocks launchd)
    import os
    os._exit(0)
