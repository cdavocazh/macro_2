#!/usr/bin/env python3
"""
5-minute extraction of Polymarket prediction market events.

Fetches financial, economic, and geopolitical prediction markets from
the Polymarket Gamma API. No API key required.
Updates the shared cache via partial merge (key 86_polymarket only).

Usage:
    python polymarket_extract.py             # normal run
    python polymarket_extract.py --cron      # quiet mode for launchd logs
    python polymarket_extract.py --force     # ignore freshness guard
    python polymarket_extract.py --dry-run   # show what would be extracted

Schedule: com.macro2.polymarket-extract.plist (every 300 seconds)
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

# Freshness guard: skip if last run was < 3 minutes ago
_FRESHNESS_SECONDS = 180
_FRESHNESS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data_cache', '.polymarket_extract_timestamp'
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
    """Quick network check (Polymarket Gamma API)."""
    try:
        socket.create_connection(('gamma-api.polymarket.com', 443), timeout=5).close()
        return True
    except (socket.timeout, socket.error, OSError):
        return False


def _partial_cache_update(polymarket_data):
    """Merge Polymarket data into existing cache.

    Uses atomic write (tempfile + os.replace) to prevent corruption.
    """
    if not os.path.exists(_CACHE_FILE):
        return False

    from utils.helpers import _serialize_value

    try:
        with open(_CACHE_FILE, 'r') as f:
            cache = json.load(f)

        data = cache.get('data', {})
        data['86_polymarket'] = _serialize_value(polymarket_data)
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
        print(f"  Cache merge error: {e}")
        return False


def run_polymarket_extraction(force=False, quiet=False, dry_run=False):
    """Extract Polymarket data and update cache."""
    start_time = time.time()

    if dry_run:
        print("Polymarket extract: would fetch prediction market events")
        print("  Part 1: Fed Rate events (tag 100196, top 10)")
        print("  Part 2: Economy keyword events (inflation, GDP, etc., top 10)")
        print("  Part 3: Finance keyword events (gold, SPX, etc., top 10)")
        print("  Part 4: Geopolitics events (tag 100265, top 20)")
        print("  Part 5: Trending (Politics, Crypto, Finance, Geopolitics, Tech, top 8 each)")
        return

    if not _check_freshness(force):
        if not quiet:
            print(f"Polymarket extract: skipped (< {_FRESHNESS_SECONDS}s since last run)")
        return

    if not _check_network():
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Polymarket extract: no network")
        return

    from data_extractors.polymarket_extractor import get_polymarket_snapshot

    try:
        snapshot = get_polymarket_snapshot()
    except Exception as e:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Polymarket extract: API error: {e}")
        return

    if isinstance(snapshot, dict) and 'error' in snapshot and len(snapshot) <= 2:
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Polymarket extract: failed: {snapshot['error']}")
        return

    # Update shared cache
    _partial_cache_update(snapshot)
    _update_freshness()

    elapsed = time.time() - start_time
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Count events per part
    counts = {
        'fed': len(snapshot.get('part1_fed_rate', [])),
        'econ': len(snapshot.get('part2_economy', [])),
        'fin': len(snapshot.get('part3_finance', [])),
        'geo': len(snapshot.get('part4_geopolitics', [])),
        'trend': sum(len(v) for v in snapshot.get('part5_trending', {}).values()),
    }

    total = sum(counts.values())

    if quiet:
        print(f"[{ts}] PM: {total} events in {elapsed:.1f}s")
    else:
        print(f"\nPolymarket extraction: {total} events in {elapsed:.1f}s")
        for k, v in counts.items():
            print(f"  {k}: {v}")


def main():
    parser = argparse.ArgumentParser(
        description='5-minute extraction of Polymarket prediction market events.'
    )
    parser.add_argument('--force', '-f', action='store_true',
                        help='Ignore freshness guard')
    parser.add_argument('--cron', action='store_true',
                        help='Quiet mode for launchd logs')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be extracted')
    args = parser.parse_args()

    run_polymarket_extraction(force=args.force, quiet=args.cron, dry_run=args.dry_run)


if __name__ == '__main__':
    main()
    # Force exit — library threads can prevent process termination (blocks launchd)
    os._exit(0)
