"""
Utility functions for data extraction and processing.
"""
import os
import json
from datetime import datetime, timedelta
import pandas as pd


def save_to_cache(data, cache_key, cache_dir='data_cache'):
    """Save data to cache with timestamp."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")

    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'data': data
    }

    with open(cache_file, 'w') as f:
        json.dump(cache_data, f)


def load_from_cache(cache_key, cache_dir='data_cache', max_age_hours=24):
    """Load data from cache if available and not expired."""
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)

        timestamp = datetime.fromisoformat(cache_data['timestamp'])
        age = datetime.now() - timestamp

        if age < timedelta(hours=max_age_hours):
            return cache_data['data']
        else:
            return None
    except Exception:
        return None


def format_value(value, decimal_places=2):
    """Format numeric value for display."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimal_places}f}"
    except (ValueError, TypeError):
        return "N/A"


def calculate_moving_average(series, window=200):
    """Calculate moving average for a pandas Series."""
    return series.rolling(window=window).mean()


def get_latest_value(data):
    """Extract the latest value from various data formats."""
    if isinstance(data, (int, float)):
        return data
    elif isinstance(data, pd.Series):
        return data.iloc[-1] if len(data) > 0 else None
    elif isinstance(data, pd.DataFrame):
        return data.iloc[-1, -1] if not data.empty else None
    elif isinstance(data, dict):
        return data.get('value') or data.get('latest')
    return None
