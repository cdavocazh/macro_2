"""
CFTC Commitment of Traders (COT) data extractor for Gold and Silver.

Fetches weekly positioning data from CFTC public reports:
- Managed money (hedge fund) long/short positions
- Commercial (producer/merchant) positions
- Open interest
- Net positioning and ratios

Data source: CFTC public reporting via cot-reports library (free, no API key).
Frequency: Weekly (Tuesday snapshots, released Friday).

Adapted from: /Users/kriszhang/Github/silver/data/cftc_cot/extract_cot_data.py
"""

import pandas as pd
from datetime import datetime

try:
    from cot_reports import cot_reports
except ImportError:
    cot_reports = None


def _fetch_cot_year(year, report_type='disaggregated_fut'):
    """Fetch COT data for a single year."""
    try:
        df = cot_reports.cot_year(year=year, cot_report_type=report_type)
        return df
    except Exception as e:
        print(f"    Warning: COT fetch failed for {year}: {e}")
        return pd.DataFrame()


def _filter_metal(df, metal_name):
    """Filter COT DataFrame for a specific COMEX metal."""
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

    if metal_name.upper() == 'GOLD':
        mask = (df[name_col].str.contains('GOLD', case=False, na=False) &
                df[name_col].str.contains('COMMODITY EXCHANGE', case=False, na=False) &
                ~df[name_col].str.contains('MICRO', case=False, na=False))
    elif metal_name.upper() == 'SILVER':
        mask = (df[name_col].str.contains('SILVER', case=False, na=False) &
                df[name_col].str.contains('COMMODITY EXCHANGE', case=False, na=False))
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


def _process_metal(all_data, metal_name):
    """Filter, standardize, and compute metrics for one metal. Returns a result dict."""
    metal_df = _filter_metal(all_data, metal_name)
    if metal_df.empty:
        return {'error': f'No CFTC COT data found for {metal_name}'}

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

    # Historical series for charting (managed money net or noncommercial net)
    if 'date' in metal_df.columns:
        if 'managed_money_net' in metal_df.columns:
            hist = metal_df.set_index('date')['managed_money_net'].dropna()
            result['historical'] = hist
            result['historical_label'] = 'Managed Money Net'
        elif 'noncommercial_net' in metal_df.columns:
            hist = metal_df.set_index('date')['noncommercial_net'].dropna()
            result['historical'] = hist
            result['historical_label'] = 'Non-Commercial Net'

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

    gold_result = _process_metal(all_data, 'GOLD')
    silver_result = _process_metal(all_data, 'SILVER')

    result = {
        'gold': gold_result,
        'silver': silver_result,
        'source': 'CFTC Commitments of Traders',
    }

    # Use gold's date as the overall latest date
    if 'latest_date' in gold_result:
        result['latest_date'] = gold_result['latest_date']

    return result
