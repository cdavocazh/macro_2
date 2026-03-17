"""
CFTC Commitment of Traders (COT) data extractor.

Fetches weekly positioning data from CFTC public reports:
- Managed money (hedge fund) long/short positions
- Commercial (producer/merchant) positions
- Open interest
- Net positioning and ratios

Supported commodities:
  Metals:  Gold (COMEX), Silver (COMEX), Copper (COMEX)
  Energy:  WTI Crude Oil (NYMEX), Brent Crude (NYMEX), Natural Gas (NYMEX)

Data sources (in priority order):
  1. CFTC SODA API (fast, targeted JSON queries, no dependencies)
  2. cot-reports library (bulk CSV download, fallback)

Frequency: Weekly (Tuesday snapshots, released Friday).
"""

import pandas as pd
import requests
from datetime import datetime

try:
    from cot_reports import cot_reports
except ImportError:
    cot_reports = None

# CFTC SODA API endpoint (disaggregated futures-only report)
_SODA_URL = 'https://publicreporting.cftc.gov/resource/72hh-3qpy.json'

# CFTC contract market codes for each commodity
_CFTC_CODES = {
    'GOLD': '088691',       # Gold, COMEX
    'SILVER': '084691',     # Silver, COMEX
    'COPPER': '085692',     # Copper-Grade #1, COMEX
    'CRUDE_OIL': '067651',  # WTI-Physical, NYMEX
    'BRENT': '06765T',      # Brent Last Day, NYMEX
    'NATURAL_GAS': '023651',  # Natural Gas (Henry Hub), NYMEX
}


def _fetch_cot_soda(commodity_code, limit=200):
    """Fetch COT data from CFTC SODA API for a specific commodity code.

    Returns DataFrame with standardized columns, or empty DataFrame on failure.
    """
    try:
        params = {
            '$where': f"cftc_contract_market_code='{commodity_code}'",
            '$order': 'report_date_as_yyyy_mm_dd DESC',
            '$limit': str(limit),
        }
        resp = requests.get(_SODA_URL, params=params, timeout=15)
        resp.raise_for_status()
        records = resp.json()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # SODA columns are lowercase with underscores — map to standard names
        soda_rename = {
            'market_and_exchange_names': 'market_name',
            'report_date_as_yyyy_mm_dd': 'date',
            'open_interest_all': 'open_interest',
            'prod_merc_positions_long_all': 'producer_long',
            'prod_merc_positions_short_all': 'producer_short',
            'swap_positions_long_all': 'swap_long',
            'swap__positions_short_all': 'swap_short',
            'm_money_positions_long_all': 'managed_money_long',
            'm_money_positions_short_all': 'managed_money_short',
            'other_rept_positions_long_all': 'other_reportable_long',
            'other_rept_positions_short_all': 'other_reportable_short',
            'tot_rept_positions_long_all': 'total_reportable_long',
            'tot_rept_positions_short_all': 'total_reportable_short',
            'nonrept_positions_long_all': 'non_reportable_long',
            'nonrept_positions_short_all': 'non_reportable_short',
        }
        existing = {k: v for k, v in soda_rename.items() if k in df.columns}
        df = df.rename(columns=existing)

        # Convert numeric columns from strings
        numeric_cols = ['open_interest', 'producer_long', 'producer_short',
                        'swap_long', 'swap_short', 'managed_money_long', 'managed_money_short',
                        'other_reportable_long', 'other_reportable_short',
                        'total_reportable_long', 'total_reportable_short',
                        'non_reportable_long', 'non_reportable_short']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df
    except Exception as e:
        print(f"    SODA API failed for code {commodity_code}: {e}")
        return pd.DataFrame()


def _fetch_cot_year(year, report_type='disaggregated_fut'):
    """Fetch COT data for a single year via cot-reports library (bulk download)."""
    try:
        df = cot_reports.cot_year(year=year, cot_report_type=report_type)
        return df
    except Exception as e:
        print(f"    Warning: COT fetch failed for {year}: {e}")
        return pd.DataFrame()


def _filter_commodity(df, commodity_name):
    """Filter COT DataFrame for a specific commodity by market name."""
    if df.empty:
        return df

    # Find the market name column
    name_col = None
    for col in df.columns:
        if 'market' in col.lower() and ('name' in col.lower() or 'exchange' in col.lower()):
            name_col = col
            break

    if name_col is None:
        return pd.DataFrame()

    col = df[name_col]
    key = commodity_name.upper()

    if key == 'GOLD':
        mask = (col.str.contains('GOLD', case=False, na=False) &
                col.str.contains('COMMODITY EXCHANGE', case=False, na=False) &
                ~col.str.contains('MICRO', case=False, na=False))
    elif key == 'SILVER':
        mask = (col.str.contains('SILVER', case=False, na=False) &
                col.str.contains('COMMODITY EXCHANGE', case=False, na=False))
    elif key == 'COPPER':
        mask = (col.str.contains('COPPER', case=False, na=False) &
                col.str.contains('COMMODITY EXCHANGE', case=False, na=False))
    elif key in ('CRUDE_OIL', 'WTI', 'CRUDE'):
        # WTI-PHYSICAL on NYMEX (code 067651), exclude Brent/Financial/Calendar/Houston/Midland
        mask = (col.str.contains('WTI', case=False, na=False) &
                col.str.contains('NEW YORK MERCANTILE', case=False, na=False) &
                ~col.str.contains('BRENT', case=False, na=False) &
                ~col.str.contains('FINANCIAL', case=False, na=False) &
                ~col.str.contains('CALENDAR', case=False, na=False) &
                ~col.str.contains('HOUSTON', case=False, na=False) &
                ~col.str.contains('MIDLAND', case=False, na=False))
    elif key == 'BRENT':
        mask = (col.str.contains('BRENT LAST DAY', case=False, na=False) &
                col.str.contains('NEW YORK MERCANTILE', case=False, na=False))
    elif key in ('NATURAL_GAS', 'NATGAS', 'NG'):
        # NAT GAS NYME on NYMEX (code 023651) — the standard Henry Hub NG futures
        mask = (col.str.upper().str.startswith('NAT GAS NYME') &
                col.str.contains('NEW YORK MERCANTILE', case=False, na=False))
    else:
        return pd.DataFrame()

    return df[mask].copy()


def _standardize_columns(df):
    """Normalize CFTC column names to consistent format."""
    if df.empty:
        return df

    rename_map = {
        'Market and Exchange Names': 'market_name',
        'Market_and_Exchange_Names': 'market_name',
        'As of Date in Form YYYY-MM-DD': 'date',
        'As_of_Date_in_Form_YYYY-MM-DD': 'date',
        'Report_Date_as_YYYY-MM-DD': 'date',
        'Open Interest (All)': 'open_interest',
        'Open_Interest_All': 'open_interest',
        'Open Interest': 'open_interest',
        # Disaggregated format
        'Prod/Merc Positions-Long (All)': 'producer_long',
        'Prod/Merc Positions-Short (All)': 'producer_short',
        'Swap Positions-Long (All)': 'swap_long',
        'Swap Positions-Short (All)': 'swap_short',
        'M Money Positions-Long (All)': 'managed_money_long',
        'M Money Positions-Short (All)': 'managed_money_short',
        'Other Rept Positions-Long (All)': 'other_reportable_long',
        'Other Rept Positions-Short (All)': 'other_reportable_short',
        'Tot Rept Positions-Long (All)': 'total_reportable_long',
        'Tot Rept Positions-Short (All)': 'total_reportable_short',
        'NonRept Positions-Long (All)': 'non_reportable_long',
        'NonRept Positions-Short (All)': 'non_reportable_short',
        # Legacy format
        'Noncommercial Positions-Long (All)': 'noncommercial_long',
        'Noncommercial Positions-Short (All)': 'noncommercial_short',
        'Commercial Positions-Long (All)': 'commercial_long',
        'Commercial Positions-Short (All)': 'commercial_short',
        'Total Long': 'total_long',
        'Total Short': 'total_short',
        # Underscore variants
        'Prod_Merc_Positions_Long_All': 'producer_long',
        'Prod_Merc_Positions_Short_All': 'producer_short',
        'Swap_Positions_Long_All': 'swap_long',
        'Swap_Positions_Short_All': 'swap_short',
        'M_Money_Positions_Long_All': 'managed_money_long',
        'M_Money_Positions_Short_All': 'managed_money_short',
        'Other_Rept_Positions_Long_All': 'other_reportable_long',
        'Other_Rept_Positions_Short_All': 'other_reportable_short',
        'Tot_Rept_Positions_Long_All': 'total_reportable_long',
        'Tot_Rept_Positions_Short_All': 'total_reportable_short',
        'NonRept_Positions_Long_All': 'non_reportable_long',
        'NonRept_Positions_Short_All': 'non_reportable_short',
        'NonComm_Positions_Long_All': 'noncommercial_long',
        'NonComm_Positions_Short_All': 'noncommercial_short',
        'Comm_Positions_Long_All': 'commercial_long',
        'Comm_Positions_Short_All': 'commercial_short',
    }

    existing_renames = {k: v for k, v in rename_map.items() if k in df.columns}
    return df.rename(columns=existing_renames)


def _calculate_derived_metrics(df):
    """Calculate net positions and ratios."""
    if df.empty:
        return df

    if 'noncommercial_long' in df.columns and 'noncommercial_short' in df.columns:
        df['noncommercial_net'] = df['noncommercial_long'] - df['noncommercial_short']

    if 'commercial_long' in df.columns and 'commercial_short' in df.columns:
        df['commercial_net'] = df['commercial_long'] - df['commercial_short']

    if 'managed_money_long' in df.columns and 'managed_money_short' in df.columns:
        df['managed_money_net'] = df['managed_money_long'] - df['managed_money_short']
        total = df['managed_money_long'] + df['managed_money_short']
        df['mm_long_ratio'] = df['managed_money_long'] / total.replace(0, 1)
        df['mm_short_ratio'] = df['managed_money_short'] / total.replace(0, 1)

    if 'noncommercial_long' in df.columns and 'noncommercial_short' in df.columns:
        total = df['noncommercial_long'] + df['noncommercial_short']
        df['speculator_long_ratio'] = df['noncommercial_long'] / total.replace(0, 1)
        df['speculator_short_ratio'] = df['noncommercial_short'] / total.replace(0, 1)

    if 'open_interest' in df.columns:
        df = df.sort_values('date')
        df['oi_change'] = df['open_interest'].diff()
        df['oi_change_pct'] = df['open_interest'].pct_change() * 100

    return df


def _process_commodity(all_data, commodity_name):
    """Filter, standardize, and compute metrics for one commodity. Returns a result dict."""
    metal_df = _filter_commodity(all_data, commodity_name)
    if metal_df.empty:
        return {'error': f'No CFTC COT data found for {commodity_name}'}

    metal_df = _standardize_columns(metal_df)
    metal_df = _calculate_derived_metrics(metal_df)

    if 'date' in metal_df.columns:
        metal_df['date'] = pd.to_datetime(metal_df['date'], errors='coerce')
        metal_df = metal_df.sort_values('date').reset_index(drop=True)

    latest = metal_df.iloc[-1]

    result = {
        'source': 'CFTC Commitments of Traders',
        'latest_date': str(latest.get('date', 'N/A'))[:10],
        'open_interest': _safe_int(latest.get('open_interest')),
    }

    # Managed money (hedge funds) — disaggregated reports
    if 'managed_money_net' in metal_df.columns:
        result['managed_money_long'] = _safe_int(latest.get('managed_money_long'))
        result['managed_money_short'] = _safe_int(latest.get('managed_money_short'))
        result['managed_money_net'] = _safe_int(latest.get('managed_money_net'))
        result['mm_long_ratio'] = _safe_float(latest.get('mm_long_ratio'))
        result['mm_short_ratio'] = _safe_float(latest.get('mm_short_ratio'))

    # Non-commercial (speculators) — legacy reports
    if 'noncommercial_net' in metal_df.columns:
        result['noncommercial_long'] = _safe_int(latest.get('noncommercial_long'))
        result['noncommercial_short'] = _safe_int(latest.get('noncommercial_short'))
        result['noncommercial_net'] = _safe_int(latest.get('noncommercial_net'))
        result['speculator_long_ratio'] = _safe_float(latest.get('speculator_long_ratio'))

    # Commercial (producers/hedgers)
    if 'commercial_net' in metal_df.columns:
        result['commercial_net'] = _safe_int(latest.get('commercial_net'))

    # OI change
    if 'oi_change' in metal_df.columns:
        result['oi_change'] = _safe_int(latest.get('oi_change'))
        result['oi_change_pct'] = _safe_float(latest.get('oi_change_pct'))

    # Historical series for charting
    if 'date' in metal_df.columns:
        if 'managed_money_net' in metal_df.columns:
            hist = metal_df.set_index('date')['managed_money_net'].dropna()
            result['historical'] = hist
            result['historical_label'] = 'Managed Money Net'
        elif 'noncommercial_net' in metal_df.columns:
            hist = metal_df.set_index('date')['noncommercial_net'].dropna()
            result['historical'] = hist
            result['historical_label'] = 'Non-Commercial Net'

        # Long/short historical series for stacked charts
        if 'managed_money_long' in metal_df.columns:
            result['historical_long'] = metal_df.set_index('date')['managed_money_long'].dropna()
            result['historical_short'] = metal_df.set_index('date')['managed_money_short'].dropna()

        if 'open_interest' in metal_df.columns:
            result['historical_oi'] = metal_df.set_index('date')['open_interest'].dropna()

    return result


def _safe_int(val):
    """Convert to int, return None on failure."""
    try:
        import numpy as np
        if pd.isna(val) or (isinstance(val, float) and np.isinf(val)):
            return None
        return int(val)
    except (ValueError, TypeError):
        return None


def _safe_float(val):
    """Convert to float rounded to 4 decimal places, return None on failure."""
    try:
        import numpy as np
        if pd.isna(val) or (isinstance(val, float) and np.isinf(val)):
            return None
        return round(float(val), 4)
    except (ValueError, TypeError):
        return None


def get_cot_gold_silver(years=4):
    """
    Fetch CFTC COT positioning data for Gold and Silver (COMEX).

    Returns dict matching the extractor return format:
    {
        'gold': { open_interest, managed_money_net, ... , historical: pd.Series },
        'silver': { ... },
        'source': 'CFTC Commitments of Traders',
        'latest_date': '2026-02-25',
    }
    """
    if cot_reports is None:
        return {
            'error': 'cot-reports library not installed. Run: pip install cot-reports',
            'suggestion': 'pip install cot-reports'
        }

    current_year = datetime.now().year
    start_year = current_year - years + 1

    # Fetch raw data (try disaggregated first, fall back to legacy)
    print("    Fetching CFTC COT data...")
    all_data = pd.DataFrame()
    for year in range(start_year, current_year + 1):
        df = _fetch_cot_year(year, report_type='disaggregated_fut')
        if not df.empty:
            all_data = pd.concat([all_data, df], ignore_index=True)

    if all_data.empty:
        # Fallback to legacy format
        print("    Disaggregated reports unavailable, trying legacy format...")
        for year in range(start_year, current_year + 1):
            df = _fetch_cot_year(year, report_type='legacy_fut')
            if not df.empty:
                all_data = pd.concat([all_data, df], ignore_index=True)

    if all_data.empty:
        return {'error': 'Could not fetch any COT data from CFTC'}

    gold_result = _process_commodity(all_data, 'GOLD')
    silver_result = _process_commodity(all_data, 'SILVER')

    result = {
        'gold': gold_result,
        'silver': silver_result,
        'source': 'CFTC Commitments of Traders',
    }

    # Use gold's date as the overall latest date
    if 'latest_date' in gold_result:
        result['latest_date'] = gold_result['latest_date']

    return result


def _fetch_cot_data(years=4):
    """Shared helper: fetch disaggregated COT data (with legacy fallback)."""
    if cot_reports is None:
        return None, 'cot-reports library not installed. Run: pip install cot-reports'

    current_year = datetime.now().year
    start_year = current_year - years + 1

    print("    Fetching CFTC COT data...")
    all_data = pd.DataFrame()
    for year in range(start_year, current_year + 1):
        df = _fetch_cot_year(year, report_type='disaggregated_fut')
        if not df.empty:
            all_data = pd.concat([all_data, df], ignore_index=True)

    if all_data.empty:
        print("    Disaggregated reports unavailable, trying legacy format...")
        for year in range(start_year, current_year + 1):
            df = _fetch_cot_year(year, report_type='legacy_fut')
            if not df.empty:
                all_data = pd.concat([all_data, df], ignore_index=True)

    if all_data.empty:
        return None, 'Could not fetch any COT data from CFTC'

    return all_data, None


def get_cot_energy_metals(years=4):
    """
    Fetch CFTC COT positioning data for WTI Crude Oil, Brent Crude, Copper, Natural Gas.

    Primary: CFTC SODA API (fast, ~0.5s per commodity, no temp files).
    Fallback: cot-reports bulk download (slower, ~5s per year).

    Returns dict:
    {
        'crude_oil': { open_interest, managed_money_net/long/short, ... , historical: pd.Series },
        'brent': { ... },
        'copper': { ... },
        'natural_gas': { ... },
        'source': 'CFTC Commitments of Traders',
        'latest_date': '2026-03-11',
    }
    """
    commodities = [
        ('crude_oil', 'CRUDE_OIL'),
        ('brent', 'BRENT'),
        ('copper', 'COPPER'),
        ('natural_gas', 'NATURAL_GAS'),
    ]

    # Try SODA API first (fast, targeted)
    result = {'source': 'CFTC Commitments of Traders (SODA API)'}
    latest_date = None
    soda_success = 0

    print("    Trying CFTC SODA API (fast path)...")
    for key, filter_name in commodities:
        code = _CFTC_CODES.get(filter_name)
        if not code:
            result[key] = {'error': f'No CFTC code for {filter_name}'}
            continue

        soda_df = _fetch_cot_soda(code, limit=years * 52)
        if not soda_df.empty:
            soda_df = _calculate_derived_metrics(soda_df)
            if 'date' in soda_df.columns:
                soda_df['date'] = pd.to_datetime(soda_df['date'], errors='coerce')
                soda_df = soda_df.sort_values('date').reset_index(drop=True)
            commodity_result = _build_result(soda_df)
            result[key] = commodity_result
            soda_success += 1
            if 'latest_date' in commodity_result and latest_date is None:
                latest_date = commodity_result['latest_date']
        else:
            result[key] = {'error': f'SODA API returned no data for {filter_name}'}

    # If SODA worked for all, we're done
    if soda_success == len(commodities):
        if latest_date:
            result['latest_date'] = latest_date
        print(f"    SODA API: {soda_success}/{len(commodities)} commodities loaded")
        return result

    # Fall back to bulk download for any failures
    print(f"    SODA partial ({soda_success}/{len(commodities)}), falling back to bulk download...")
    all_data, err = _fetch_cot_data(years)
    if all_data is None:
        # Keep whatever SODA got us
        if latest_date:
            result['latest_date'] = latest_date
        return result

    result['source'] = 'CFTC Commitments of Traders'
    for key, filter_name in commodities:
        if 'error' in result.get(key, {}):
            commodity_result = _process_commodity(all_data, filter_name)
            result[key] = commodity_result
            if 'latest_date' in commodity_result and latest_date is None:
                latest_date = commodity_result['latest_date']

    if latest_date:
        result['latest_date'] = latest_date

    return result


def _build_result(df):
    """Build a result dict from a standardized, metric-computed DataFrame."""
    if df.empty:
        return {'error': 'No data'}

    latest = df.iloc[-1]
    result = {
        'source': 'CFTC Commitments of Traders',
        'latest_date': str(latest.get('date', 'N/A'))[:10],
        'open_interest': _safe_int(latest.get('open_interest')),
    }

    if 'managed_money_net' in df.columns:
        result['managed_money_long'] = _safe_int(latest.get('managed_money_long'))
        result['managed_money_short'] = _safe_int(latest.get('managed_money_short'))
        result['managed_money_net'] = _safe_int(latest.get('managed_money_net'))
        result['mm_long_ratio'] = _safe_float(latest.get('mm_long_ratio'))
        result['mm_short_ratio'] = _safe_float(latest.get('mm_short_ratio'))

    if 'producer_long' in df.columns:
        result['producer_long'] = _safe_int(latest.get('producer_long'))
        result['producer_short'] = _safe_int(latest.get('producer_short'))
        result['producer_net'] = _safe_int(
            (_safe_int(latest.get('producer_long')) or 0) - (_safe_int(latest.get('producer_short')) or 0))

    if 'swap_long' in df.columns:
        result['swap_long'] = _safe_int(latest.get('swap_long'))
        result['swap_short'] = _safe_int(latest.get('swap_short'))

    if 'oi_change' in df.columns:
        result['oi_change'] = _safe_int(latest.get('oi_change'))
        result['oi_change_pct'] = _safe_float(latest.get('oi_change_pct'))

    # Historical series
    if 'date' in df.columns:
        if 'managed_money_net' in df.columns:
            result['historical'] = df.set_index('date')['managed_money_net'].dropna()
            result['historical_label'] = 'Managed Money Net'
        if 'managed_money_long' in df.columns:
            result['historical_long'] = df.set_index('date')['managed_money_long'].dropna()
            result['historical_short'] = df.set_index('date')['managed_money_short'].dropna()
        if 'open_interest' in df.columns:
            result['historical_oi'] = df.set_index('date')['open_interest'].dropna()

    return result
