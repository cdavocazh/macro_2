"""
Quick data update script - appends only new data since last extraction.
Reads last_timestamp from metadata and fetches incremental data.
"""

import os
import json
from datetime import datetime
from extract_historical_data import (
    extract_all_historical_data,
    load_metadata,
    OUTPUT_DIR
)


def check_last_update():
    """Check when data was last updated."""
    try:
        metadata = load_metadata()
        last_extraction = metadata.get('last_extraction')

        if last_extraction:
            last_time = datetime.fromisoformat(last_extraction)
            time_since = datetime.now() - last_time

            print("=" * 80)
            print("DATA UPDATE STATUS")
            print("=" * 80)
            print(f"Last extraction: {last_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Time since: {time_since.days} days, {time_since.seconds // 3600} hours")
            print(f"\nData directory: {OUTPUT_DIR}/")

            # Show available files
            if os.path.exists(OUTPUT_DIR):
                files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.csv')]
                print(f"\nAvailable CSV files ({len(files)}):")
                for f in sorted(files):
                    filepath = os.path.join(OUTPUT_DIR, f)
                    size = os.path.getsize(filepath)
                    print(f"  📄 {f:30} ({size:,} bytes)")

            print("\n" + "=" * 80)
            return last_time
        else:
            print("⚠️  No previous extraction found. Running full extraction...")
            return None

    except Exception as e:
        print(f"❌ Error checking update status: {str(e)}")
        return None


def update_data(force_full=False):
    """
    Update data incrementally.

    Args:
        force_full: If True, re-extract all historical data
    """
    last_update = check_last_update()

    if force_full or last_update is None:
        print("\n🔄 Running FULL extraction (this may take a few minutes)...\n")
    else:
        print("\n🔄 Running INCREMENTAL update (appending new data only)...\n")

    # Run extraction (automatically appends to existing files)
    results = extract_all_historical_data()

    return results


if __name__ == "__main__":
    import sys

    # Check for --full flag
    force_full = '--full' in sys.args or '-f' in sys.args

    if force_full:
        print("⚡ Full extraction mode enabled")

    update_data(force_full=force_full)
