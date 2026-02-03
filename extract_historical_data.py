"""
Historical Data Extraction Script for Macroeconomic Indicators

Downloads all 10 indicators and saves to CSV files with:
- Append-only mode (adds new data without overwriting)
- Last timestamp tracking
- Historical data preservation
"""

import os
import pandas as pd
from datetime import datetime
import json
from pathlib import Path

from data_aggregator import get_aggregator
from data_extractors import (
    yfinance_extractors,
    openbb_extractors,
    fred_extractors,
    shiller_extractor,
    web_scrapers
)


# Configuration
OUTPUT_DIR = 'historical_data'
METADATA_FILE = 'data_metadata.json'


def ensure_output_directory():
    """Create output directory if it doesn't exist."""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"✅ Output directory: {OUTPUT_DIR}/")


def load_metadata():
    """Load metadata about last extraction timestamps."""
    metadata_path = os.path.join(OUTPUT_DIR, METADATA_FILE)

    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            return json.load(f)
    else:
        return {
            'last_extraction': None,
            'indicators': {}
        }


def save_metadata(metadata):
    """Save metadata about extraction."""
    metadata_path = os.path.join(OUTPUT_DIR, METADATA_FILE)
    metadata['last_extraction'] = datetime.now().isoformat()

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)


def append_to_csv(filename, new_data, timestamp_col='timestamp'):
    """
    Append new data to CSV file, avoiding duplicates.

    Args:
        filename: CSV filename
        new_data: DataFrame with new data
        timestamp_col: Name of timestamp column for deduplication
    """
    filepath = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(filepath):
        # Load existing data
        existing_data = pd.read_csv(filepath)

        # Combine and remove duplicates based on timestamp
        if timestamp_col in new_data.columns and timestamp_col in existing_data.columns:
            combined = pd.concat([existing_data, new_data], ignore_index=True)
            combined = combined.drop_duplicates(subset=[timestamp_col], keep='last')
            combined = combined.sort_values(timestamp_col)
        else:
            # If no timestamp column, just append
            combined = pd.concat([existing_data, new_data], ignore_index=True)
    else:
        combined = new_data

    # Save
    combined.to_csv(filepath, index=False)
    print(f"  💾 Saved to: {filename} ({len(combined)} total rows)")


def extract_russell_2000_historical():
    """Extract Russell 2000 Value & Growth historical data."""
    print("\n📊 Extracting Russell 2000 indices...")

    try:
        data = yfinance_extractors.get_russell_2000_indices()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        # Extract historical data for both indices
        value_hist = data['russell_2000_value']['historical']
        growth_hist = data['russell_2000_growth']['historical']

        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': value_hist.index,
            'date': value_hist.index.date,
            'russell_2000_value': value_hist.values,
            'russell_2000_growth': growth_hist.values,
            'value_growth_ratio': value_hist.values / growth_hist.values
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('russell_2000.csv', df)

        return {
            'indicator': 'Russell 2000',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sp500_with_ma200():
    """Extract S&P 500 with 200-day moving average."""
    print("\n📊 Extracting S&P 500 / 200MA...")

    try:
        data = yfinance_extractors.get_sp500_data()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': hist.index.date,
            'sp500_close': hist['Close'],
            'sp500_ma200': hist['MA200'],
            'price_to_ma200_ratio': hist['Close'] / hist['MA200']
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('sp500_ma200.csv', df)

        return {
            'indicator': 'S&P 500 / 200MA',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_vix_move():
    """Extract VIX and MOVE indices with ratio."""
    print("\n📊 Extracting VIX and MOVE...")

    try:
        vix_data = yfinance_extractors.get_vix()
        move_data = yfinance_extractors.get_move_index()

        if 'error' in vix_data or 'error' in move_data:
            print(f"  ❌ Error fetching data")
            return

        vix_hist = vix_data['historical']
        move_hist = move_data['historical']

        # Align timestamps
        df_vix = pd.DataFrame({
            'timestamp': vix_hist.index,
            'vix': vix_hist.values
        })

        df_move = pd.DataFrame({
            'timestamp': move_hist.index,
            'move': move_hist.values
        })

        # Merge on timestamp
        df = pd.merge(df_vix, df_move, on='timestamp', how='outer')
        df = df.sort_values('timestamp')

        # Calculate ratio where both exist
        df['vix_move_ratio'] = df['vix'] / df['move']
        df['date'] = df['timestamp'].dt.date

        append_to_csv('vix_move.csv', df)

        return {
            'indicator': 'VIX / MOVE',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_dxy():
    """Extract US Dollar Index (DXY)."""
    print("\n📊 Extracting DXY...")

    try:
        data = yfinance_extractors.get_dxy()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': hist.index.date,
            'dxy': hist.values
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('dxy.csv', df)

        return {
            'indicator': 'DXY',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_shiller_cape():
    """Extract Shiller CAPE historical data."""
    print("\n📊 Extracting Shiller CAPE...")

    try:
        data = shiller_extractor.get_shiller_cape()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'date': hist.index,
            'cape_ratio': hist.values
        })

        # Convert to timestamp (assuming end of month)
        df['timestamp'] = pd.to_datetime(df['date'])

        append_to_csv('shiller_cape.csv', df, timestamp_col='date')

        return {
            'indicator': 'Shiller CAPE',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sp500_fundamentals():
    """Extract S&P 500 P/E and P/B ratios (snapshot only)."""
    print("\n📊 Extracting S&P 500 Fundamentals...")

    try:
        data = openbb_extractors.get_sp500_fundamentals()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        # Create single-row DataFrame with current values
        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'pe_ratio_trailing': data.get('sp500_pe_trailing'),
            'pb_ratio': data.get('sp500_pb')
        }])

        append_to_csv('sp500_fundamentals.csv', df)

        return {
            'indicator': 'S&P 500 P/E & P/B',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_cboe_skew():
    """Extract CBOE SKEW index."""
    print("\n📊 Extracting CBOE SKEW...")

    try:
        data = web_scrapers.get_cboe_skew_index()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': hist.index.date,
            'cboe_skew': hist.values
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('cboe_skew.csv', df)

        return {
            'indicator': 'CBOE SKEW',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_fred_indicators():
    """Extract FRED indicators (GDP, Market Cap)."""
    print("\n📊 Extracting FRED indicators...")

    try:
        # Get GDP
        gdp_data = fred_extractors.get_us_gdp()

        if 'error' not in gdp_data:
            hist = gdp_data['historical']

            df_gdp = pd.DataFrame({
                'timestamp': hist.index,
                'date': hist.index.date,
                'us_gdp': hist.values
            })

            df_gdp['timestamp'] = pd.to_datetime(df_gdp['timestamp'])
            append_to_csv('us_gdp.csv', df_gdp)
        else:
            print(f"  ⚠️  GDP: {gdp_data['error']}")

        # Get Market Cap
        marketcap_data = fred_extractors.get_sp500_market_cap()

        if 'error' not in marketcap_data:
            hist = marketcap_data['historical']

            df_mc = pd.DataFrame({
                'timestamp': hist.index,
                'date': hist.index.date,
                'market_cap': hist.values
            })

            df_mc['timestamp'] = pd.to_datetime(df_mc['timestamp'])
            append_to_csv('market_cap.csv', df_mc)
        else:
            print(f"  ⚠️  Market Cap: {marketcap_data['error']}")

        # Calculate Market Cap / GDP ratio
        if 'error' not in gdp_data and 'error' not in marketcap_data:
            # Merge on date (quarterly data)
            df_ratio = pd.merge(df_gdp, df_mc, on='date', how='outer', suffixes=('_gdp', '_mc'))
            df_ratio['marketcap_to_gdp_ratio'] = (df_ratio['market_cap'] / df_ratio['us_gdp']) * 100
            df_ratio = df_ratio[['date', 'timestamp_gdp', 'us_gdp', 'market_cap', 'marketcap_to_gdp_ratio']]
            df_ratio.rename(columns={'timestamp_gdp': 'timestamp'}, inplace=True)

            append_to_csv('marketcap_to_gdp.csv', df_ratio, timestamp_col='date')

        return {
            'indicator': 'FRED (GDP, Market Cap)',
            'last_date': datetime.now().date(),
            'rows': 'varies'
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def create_summary_file(results):
    """Create a summary CSV with latest values from all indicators."""
    print("\n📊 Creating summary file...")

    try:
        aggregator = get_aggregator()
        aggregator.fetch_all_indicators()

        summary_data = []

        indicator_names = {
            '1_sp500_forward_pe': 'S&P 500 Forward P/E',
            '2_russell_2000': 'Russell 2000 Value/Growth',
            '3_sp500_fundamentals': 'S&P 500 P/E & P/B',
            '4_put_call_ratio': 'S&P 500 Put/Call Ratio',
            '5_spx_call_skew': 'SPX Call Skew',
            '6a_sp500_to_ma200': 'S&P 500 / 200MA',
            '6b_marketcap_to_gdp': 'Market Cap / GDP',
            '7_shiller_cape': 'Shiller CAPE',
            '8_vix': 'VIX',
            '8b_vix_move_ratio': 'VIX/MOVE Ratio',
            '9_move_index': 'MOVE Index',
            '10_dxy': 'DXY'
        }

        timestamp = datetime.now()

        for key, name in indicator_names.items():
            data = aggregator.get_indicator(key)

            row = {
                'timestamp': timestamp,
                'date': timestamp.date(),
                'indicator': name,
                'indicator_key': key,
                'status': 'success' if 'error' not in data else 'failed'
            }

            # Extract values based on indicator type
            if key == '2_russell_2000':
                row['value_main'] = data.get('russell_2000_value', {}).get('latest_price')
                row['value_secondary'] = data.get('russell_2000_growth', {}).get('latest_price')
                row['value_ratio'] = data.get('value_growth_ratio')
            elif key == '3_sp500_fundamentals':
                row['value_main'] = data.get('sp500_pe_trailing')
                row['value_secondary'] = data.get('sp500_pb')
            elif key == '6a_sp500_to_ma200':
                row['value_main'] = data.get('sp500_price')
                row['value_secondary'] = data.get('sp500_ma200')
                row['value_ratio'] = data.get('sp500_to_ma200_ratio')
            elif key == '6b_marketcap_to_gdp':
                row['value_main'] = data.get('marketcap_to_gdp_ratio')
            elif key == '7_shiller_cape':
                row['value_main'] = data.get('shiller_cape')
            elif key == '8_vix':
                row['value_main'] = data.get('vix')
            elif key == '8b_vix_move_ratio':
                row['value_main'] = data.get('vix_move_ratio')
                row['value_secondary'] = data.get('vix')
                row['value_tertiary'] = data.get('move')
            elif key == '9_move_index':
                row['value_main'] = data.get('move')
            elif key == '10_dxy':
                row['value_main'] = data.get('dxy')
            else:
                row['value_main'] = None

            summary_data.append(row)

        df_summary = pd.DataFrame(summary_data)
        append_to_csv('_summary_latest.csv', df_summary)

        print(f"  ✅ Summary file created")

    except Exception as e:
        print(f"  ❌ Error creating summary: {str(e)}")


def extract_all_historical_data():
    """
    Extract all available historical data and save to CSV files.

    Each indicator is saved to a separate CSV file with timestamps.
    New data is appended to existing files (no overwrite).
    """
    print("=" * 80)
    print("HISTORICAL DATA EXTRACTION")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    ensure_output_directory()

    # Load metadata
    metadata = load_metadata()
    print(f"\nLast extraction: {metadata.get('last_extraction', 'Never')}")

    results = []

    # Extract each indicator
    result = extract_russell_2000_historical()
    if result:
        results.append(result)
        metadata['indicators']['russell_2000'] = result

    result = extract_sp500_with_ma200()
    if result:
        results.append(result)
        metadata['indicators']['sp500_ma200'] = result

    result = extract_vix_move()
    if result:
        results.append(result)
        metadata['indicators']['vix_move'] = result

    result = extract_dxy()
    if result:
        results.append(result)
        metadata['indicators']['dxy'] = result

    result = extract_shiller_cape()
    if result:
        results.append(result)
        metadata['indicators']['shiller_cape'] = result

    result = extract_sp500_fundamentals()
    if result:
        results.append(result)
        metadata['indicators']['sp500_fundamentals'] = result

    result = extract_cboe_skew()
    if result:
        results.append(result)
        metadata['indicators']['cboe_skew'] = result

    result = extract_fred_indicators()
    if result:
        results.append(result)
        metadata['indicators']['fred'] = result

    # Create summary file
    create_summary_file(results)

    # Save metadata
    save_metadata(metadata)

    # Print summary
    print("\n" + "=" * 80)
    print("EXTRACTION SUMMARY")
    print("=" * 80)
    print(f"Successfully extracted {len(results)} indicator groups")
    print(f"\nFiles saved to: {OUTPUT_DIR}/")
    print("\nExtracted indicators:")
    for result in results:
        print(f"  ✅ {result['indicator']:30} | Last date: {result['last_date']} | Rows: {result['rows']}")

    print("\n" + "=" * 80)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    return results


if __name__ == "__main__":
    extract_all_historical_data()
