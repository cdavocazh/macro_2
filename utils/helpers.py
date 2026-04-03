"""
Utility functions for data extraction and processing.
"""
import os
import json
from datetime import datetime, timedelta
import pandas as pd
import numpy as np


def _serialize_value(obj):
    """Convert non-JSON-serializable objects for caching."""
    if isinstance(obj, pd.Series):
        return {
            '__type__': 'pd.Series',
            'index': [str(i) for i in obj.index.tolist()],
            'values': [None if (isinstance(v, float) and np.isnan(v)) else v for v in obj.tolist()],
            'name': obj.name,
        }
    elif isinstance(obj, pd.DataFrame):
        return {
            '__type__': 'pd.DataFrame',
            'data': obj.to_dict(orient='list'),
            'index': [str(i) for i in obj.index.tolist()],
        }
    elif isinstance(obj, (pd.Timestamp, datetime)):
        return {'__type__': 'datetime', 'value': obj.isoformat()}
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: _serialize_value(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_serialize_value(v) for v in obj]
    elif isinstance(obj, float) and (np.isnan(obj) or np.isinf(obj)):
        return None
    return obj


def _deserialize_value(obj):
    """Restore pandas objects from cached JSON."""
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
            df = pd.DataFrame(obj['data'], index=idx)
            return df
        elif obj.get('__type__') == 'datetime':
            return obj['value']
        else:
            return {k: _deserialize_value(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_deserialize_value(v) for v in obj]
    return obj


def save_to_cache(data, cache_key, cache_dir='data_cache'):
    """Save data to cache with timestamp. Handles pandas objects."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")

    cache_data = {
        'timestamp': datetime.now().isoformat(),
        'data': _serialize_value(data)
    }

    with open(cache_file, 'w') as f:
        json.dump(cache_data, f, default=str)


def load_from_cache(cache_key, cache_dir='data_cache', max_age_hours=24, fallback_stale=False):
    """Load data from cache if available and not expired.

    If fallback_stale=True, returns expired data instead of None when
    the cache file exists but is older than max_age_hours.
    """
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")

    if not os.path.exists(cache_file):
        return None

    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)

        timestamp = datetime.fromisoformat(cache_data['timestamp'])
        age = datetime.now() - timestamp

        if age < timedelta(hours=max_age_hours):
            return _deserialize_value(cache_data['data'])
        elif fallback_stale:
            return _deserialize_value(cache_data['data'])
        else:
            return None
    except Exception:
        return None


def get_cache_timestamp(cache_key, cache_dir='data_cache'):
    """Get the timestamp of a cached entry, or None if not cached."""
    cache_file = os.path.join(cache_dir, f"{cache_key}.json")
    if not os.path.exists(cache_file):
        return None
    try:
        with open(cache_file, 'r') as f:
            cache_data = json.load(f)
        return datetime.fromisoformat(cache_data['timestamp'])
    except Exception:
        return None


def export_indicators_to_csv(indicators, output_dir='data_export'):
    """
    Export all indicator data to CSV files in a local folder.

    Returns dict with export results.
    """
    os.makedirs(output_dir, exist_ok=True)
    exported_files = []
    summary_rows = []

    for key, data in indicators.items():
        if not isinstance(data, dict):
            continue

        if 'error' in data and not any(
            k for k in data.keys() if k not in ('error', 'traceback', 'note', 'suggestion')
        ):
            continue

        # Build a summary row from scalar values
        row = {'indicator': key}
        for field, value in data.items():
            if isinstance(value, (int, float, str, bool)) and field != 'traceback':
                row[field] = value
        if len(row) > 1:
            summary_rows.append(row)

        # Export historical series if present
        if 'historical' in data and isinstance(data['historical'], pd.Series):
            series = data['historical']
            df = series.to_frame(name='value')
            df.index.name = 'date'
            filepath = os.path.join(output_dir, f"{key}_historical.csv")
            df.to_csv(filepath)
            exported_files.append(filepath)

    # Write summary CSV with latest values
    if summary_rows:
        summary_df = pd.DataFrame(summary_rows)
        summary_path = os.path.join(output_dir, 'indicators_summary.csv')
        summary_df.to_csv(summary_path, index=False)
        exported_files.append(summary_path)

    return {
        'output_dir': output_dir,
        'files': exported_files,
        'count': len(exported_files),
    }


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
