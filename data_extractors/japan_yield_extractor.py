"""
Japan Government Bond (JGB) yield extractor.

Data source: Ministry of Finance Japan (official, free, no auth required).
- Historical: https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv
  (1974 to end of previous month)
- Current month: https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv
  (current month, updated daily)

CSV includes yields for 1Y, 2Y, 3Y, 4Y, 5Y, 6Y, 7Y, 8Y, 9Y, 10Y, 15Y, 20Y, 25Y, 30Y, 40Y.
"""

import requests
import pandas as pd
from io import StringIO

MOF_HISTORICAL_URL = 'https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv'
MOF_CURRENT_URL = 'https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv'
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}


def _fetch_mof_csv(url):
    """Fetch and parse a MOF Japan yield CSV."""
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    df = pd.read_csv(StringIO(resp.text), skiprows=1)
    df.columns = df.columns.str.strip()

    # Filter to rows with valid date format (YYYY/M/D)
    date_col = df.columns[0]
    df = df[df[date_col].astype(str).str.match(r'^\d{4}/', na=False)]
    df[date_col] = pd.to_datetime(df[date_col], format='%Y/%m/%d')
    df = df.set_index(date_col)

    # Convert all columns to numeric
    for col in df.columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')

    return df


def get_japan_2y_yield():
    """
    Fetch Japan 2-Year Government Bond Yield from MOF Japan.

    Returns dict with:
    - japan_2y_yield: latest 2Y JGB yield (percent)
    - historical: pd.Series of daily 2Y yields
    - Also includes 10Y yield for reference
    """
    try:
        # Fetch current month first (most up-to-date)
        try:
            df_curr = _fetch_mof_csv(MOF_CURRENT_URL)
        except Exception:
            df_curr = pd.DataFrame()

        # Fetch historical (1974 to end of previous month)
        try:
            df_hist = _fetch_mof_csv(MOF_HISTORICAL_URL)
        except Exception:
            df_hist = pd.DataFrame()

        if df_hist.empty and df_curr.empty:
            return {'error': 'Could not fetch JGB yield data from MOF Japan'}

        # Combine: historical + current month, deduplicate
        if not df_hist.empty and not df_curr.empty:
            df = pd.concat([df_hist, df_curr])
            df = df[~df.index.duplicated(keep='last')]
        elif not df_hist.empty:
            df = df_hist
        else:
            df = df_curr

        df = df.sort_index()

        # Find 2Y column (may be named '2Y', '2', or similar)
        col_2y = None
        for col in df.columns:
            col_str = str(col).strip()
            if col_str in ('2Y', '2'):
                col_2y = col
                break
        if col_2y is None:
            # Try matching pattern
            for col in df.columns:
                if '2' in str(col) and ('y' in str(col).lower() or str(col).strip() == '2'):
                    col_2y = col
                    break

        if col_2y is None:
            return {'error': f'Could not find 2Y column in MOF data. Columns: {list(df.columns[:5])}'}

        series_2y = df[col_2y].dropna()
        if series_2y.empty:
            return {'error': 'No 2Y yield data in MOF CSV'}

        latest = series_2y.iloc[-1]
        latest_date = series_2y.index[-1]

        # Day-over-day change
        prev = series_2y.iloc[-2] if len(series_2y) >= 2 else latest
        change_1d = latest - prev

        result = {
            'japan_2y_yield': round(float(latest), 4),
            'change_1d': round(float(change_1d), 4),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'MOF Japan',
            'units': 'Percent',
            'historical': series_2y,
        }

        # Also grab 10Y for reference
        col_10y = None
        for col in df.columns:
            col_str = str(col).strip()
            if col_str in ('10Y', '10'):
                col_10y = col
                break
        if col_10y is not None:
            series_10y = df[col_10y].dropna()
            if not series_10y.empty:
                result['japan_10y_yield'] = round(float(series_10y.iloc[-1]), 4)

        return result

    except Exception as e:
        return {'error': f'Error fetching Japan 2Y yield: {str(e)}'}


def get_us2y_jp2y_spread():
    """
    Calculate US 2Y - Japan 2Y yield spread.

    Combines FRED DGS2 (US) and MOF Japan (JP) data.
    Widening spread = USD strength vs JPY (carry trade incentive).
    Narrowing spread = JPY strength, potential carry trade unwind.
    """
    try:
        # Get Japan 2Y
        jp_data = get_japan_2y_yield()
        if 'error' in jp_data:
            return {'error': f'Japan 2Y: {jp_data["error"]}'}

        # Get US 2Y from FRED
        from data_extractors.fred_extractors import get_us_2y_yield
        us_data = get_us_2y_yield()
        if 'error' in us_data:
            return {'error': f'US 2Y: {us_data["error"]}'}

        us_2y = us_data['us_2y_yield']
        jp_2y = jp_data['japan_2y_yield']
        spread = round(float(us_2y) - float(jp_2y), 4)

        # Historical spread (align by date, forward-fill)
        us_hist = us_data.get('historical')
        jp_hist = jp_data.get('historical')

        historical_spread = None
        if us_hist is not None and jp_hist is not None:
            combined = pd.DataFrame({
                'us_2y': us_hist,
                'jp_2y': jp_hist,
            }).ffill().dropna()
            if not combined.empty:
                historical_spread = combined['us_2y'] - combined['jp_2y']

        result = {
            'spread': spread,
            'us_2y_yield': round(float(us_2y), 4),
            'japan_2y_yield': jp_2y,
            'us_2y_date': us_data['latest_date'],
            'japan_2y_date': jp_data['latest_date'],
            'source': 'FRED (DGS2) + MOF Japan',
            'units': 'Percentage Points',
            'interpretation': 'Widening = USD strength (carry trade); Narrowing = JPY strength (unwind risk)',
        }

        if historical_spread is not None:
            result['historical'] = historical_spread

        return result

    except Exception as e:
        return {'error': f'Error calculating US2Y-JP2Y spread: {str(e)}'}
