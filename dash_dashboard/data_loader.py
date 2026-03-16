"""
Data loader for the Dash dashboard.
Reads from the shared JSON cache produced by data_aggregator.py / scheduled_extract.py.
Zero-duplication: no separate extraction logic — reads the same cache file.
"""
import os
import json
import sys
from datetime import datetime

import pandas as pd
import numpy as np

# Add parent directory to path so we can import project modules
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

CACHE_DIR = os.path.join(PARENT_DIR, 'data_cache')
CACHE_KEY = 'all_indicators'
CACHE_FILE = os.path.join(CACHE_DIR, f'{CACHE_KEY}.json')


def _deserialize_value(obj):
    """Restore pandas objects from cached JSON. Mirrors utils/helpers.py."""
    if isinstance(obj, dict):
        if obj.get('__type__') == 'pd.Series':
            idx = pd.to_datetime(obj['index'], utc=True, errors='coerce')
            if idx.isna().all():
                idx = obj['index']
            else:
                idx = idx.tz_localize(None)
            return pd.Series(obj['values'], index=idx, name=obj.get('name'))
        elif obj.get('__type__') == 'pd.DataFrame':
            idx = pd.to_datetime(obj['index'], utc=True, errors='coerce')
            if idx.isna().all():
                idx = obj['index']
            else:
                idx = idx.tz_localize(None)
            return pd.DataFrame(obj['data'], index=idx)
        elif obj.get('__type__') == 'datetime':
            return obj['value']
        else:
            return {k: _deserialize_value(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deserialize_value(v) for v in obj]
    return obj


class DashDataLoader:
    """Loads indicator data from the shared JSON cache."""

    def __init__(self):
        self.indicators = {}
        self.last_update = None
        self._file_mtime = None

    def load(self):
        """Load or reload indicators from cache. Returns True if data was loaded."""
        if not os.path.exists(CACHE_FILE):
            return False

        try:
            mtime = os.path.getmtime(CACHE_FILE)
            # Skip reload if file hasn't changed
            if self._file_mtime and mtime <= self._file_mtime:
                return False

            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)

            self.indicators = _deserialize_value(cache_data.get('data', {}))
            ts = cache_data.get('timestamp')
            self.last_update = datetime.fromisoformat(ts) if ts else None
            self._file_mtime = mtime
            return True
        except Exception as e:
            print(f"[DashDataLoader] Error loading cache: {e}")
            return False

    def get(self, key, default=None):
        """Get an indicator by key."""
        return self.indicators.get(key, default or {'error': 'Not loaded'})

    def get_cache_age_str(self):
        """Return a human-readable cache age string."""
        if not self.last_update:
            return "No data"
        age = datetime.now() - self.last_update
        mins = int(age.total_seconds() / 60)
        if mins < 1:
            return "just now"
        if mins < 60:
            return f"{mins}m ago"
        hrs = mins // 60
        return f"{hrs}h {mins % 60}m ago"


# Singleton
_loader = None


def get_loader():
    global _loader
    if _loader is None:
        _loader = DashDataLoader()
        _loader.load()
    return _loader


def format_value(v, decimals=2):
    """Format a numeric value safely."""
    if v is None or v == 'N/A':
        return 'N/A'
    try:
        return f"{float(v):,.{decimals}f}"
    except (ValueError, TypeError):
        return str(v)


def fmt_dollar(v):
    """Format a dollar value with appropriate scale."""
    if v is None:
        return "—"
    try:
        v = float(v)
        if abs(v) >= 1e12:
            return f"${v / 1e12:.2f}T"
        if abs(v) >= 1e9:
            return f"${v / 1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"${v / 1e6:.1f}M"
        if abs(v) >= 1e3:
            return f"${v / 1e3:.1f}K"
        return f"${v:,.2f}"
    except (ValueError, TypeError):
        return "—"


def fmt_pct(v, plus=False):
    if v is None:
        return "N/A"
    try:
        v = float(v)
        return f"{v:+.1f}%" if plus else f"{v:.1f}%"
    except (ValueError, TypeError):
        return "N/A"
