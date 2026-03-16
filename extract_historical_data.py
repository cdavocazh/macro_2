"""
Historical Data Extraction Script for Macroeconomic Indicators

Downloads all 50 indicators and saves to CSV files with:
- Append-only mode (adds new data without overwriting)
- Last timestamp tracking
- Historical data preservation

Each indicator is saved to a separate CSV in historical_data/.
New data is appended (never overwrites existing rows).
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
    web_scrapers,
    commodities_extractors,
    cot_extractor,
    japan_yield_extractor,
    equity_financials_extractor
)
from data_extractors.financial_agent_extractors import (
    SERIES_MAP as FA_SERIES_MAP,
    get_all_financial_agent_series,
    get_gold_price_yfinance,
)
from data_extractors import fidenza_extractors


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
        json.dump(metadata, f, indent=2, default=str)


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
            # Normalize timestamp types to avoid comparison errors
            existing_data[timestamp_col] = pd.to_datetime(existing_data[timestamp_col], errors='coerce', utc=True)
            new_data = new_data.copy()
            new_data[timestamp_col] = pd.to_datetime(new_data[timestamp_col], errors='coerce', utc=True)
            # Strip timezone info after normalizing to UTC for clean comparison
            existing_data[timestamp_col] = existing_data[timestamp_col].dt.tz_localize(None)
            new_data[timestamp_col] = new_data[timestamp_col].dt.tz_localize(None)
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

        # Strip timezone to prevent duplicate rows from tz-aware indices
        # yfinance returns America/New_York tz-aware timestamps which cause
        # duplicate entries when DST offset changes (-05:00 vs -04:00)
        if hasattr(vix_hist.index, 'tz') and vix_hist.index.tz is not None:
            vix_hist = vix_hist.tz_localize(None)
        if hasattr(move_hist.index, 'tz') and move_hist.index.tz is not None:
            move_hist = move_hist.tz_localize(None)

        # Normalize to midnight to ensure clean date-based merging
        vix_hist.index = vix_hist.index.normalize()
        move_hist.index = move_hist.index.normalize()

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


def _extract_simple_series(name, fetch_fn, csv_filename, value_col):
    """Generic extraction for indicators returning a 'historical' pd.Series."""
    print(f"\n📊 Extracting {name}...")
    try:
        data = fetch_fn()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        hist = data.get('historical')
        if hist is None:
            print(f"  ⚠️  No historical data for {name}")
            return None

        if isinstance(hist, pd.Series):
            if hist.empty:
                print(f"  ⚠️  Empty historical series for {name}")
                return None
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                value_col: hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        else:
            print(f"  ⚠️  Unexpected historical type for {name}: {type(hist)}")
            return None

        append_to_csv(csv_filename, df)
        return {
            'indicator': name,
            'last_date': df['date'].max(),
            'rows': len(df)
        }
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def _extract_ohlcv_series(name, fetch_fn, csv_filename, prefix):
    """Generic extraction for indicators returning 'historical_ohlcv' DataFrame.

    Writes OHLCV CSV with columns:
        timestamp, date, {prefix}_open, {prefix}_high, {prefix}_low, {prefix}_close, {prefix}_volume
    """
    print(f"\n📊 Extracting {name} OHLCV...")
    try:
        data = fetch_fn()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        ohlcv = data.get('historical_ohlcv')
        if ohlcv is None or (hasattr(ohlcv, 'empty') and ohlcv.empty):
            print(f"  ⚠️  No OHLCV data for {name}")
            return None

        df = pd.DataFrame({
            'timestamp': ohlcv.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in ohlcv.index],
            f'{prefix}_open': ohlcv['Open'].values,
            f'{prefix}_high': ohlcv['High'].values,
            f'{prefix}_low': ohlcv['Low'].values,
            f'{prefix}_close': ohlcv['Close'].values,
            f'{prefix}_volume': ohlcv['Volume'].values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv(csv_filename, df)
        return {
            'indicator': f'{name} OHLCV',
            'last_date': df['date'].max(),
            'rows': len(df)
        }
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_10y_yield():
    """Extract 10-Year Treasury Yield historical data."""
    return _extract_simple_series(
        '10-Year Treasury Yield',
        fred_extractors.get_10y_treasury_yield,
        '10y_treasury_yield.csv',
        '10y_yield'
    )


def extract_ism_pmi():
    """Extract ISM Manufacturing PMI (proxy) historical data."""
    return _extract_simple_series(
        'ISM Manufacturing PMI',
        fred_extractors.get_ism_pmi,
        'ism_pmi.csv',
        'ism_pmi'
    )


def extract_gold():
    """Extract Gold futures historical data."""
    return _extract_simple_series(
        'Gold Futures',
        commodities_extractors.get_gold,
        'gold.csv',
        'gold_price'
    )


def extract_silver():
    """Extract Silver futures historical data."""
    return _extract_simple_series(
        'Silver Futures',
        commodities_extractors.get_silver,
        'silver.csv',
        'silver_price'
    )


def extract_crude_oil():
    """Extract Crude Oil futures historical data."""
    return _extract_simple_series(
        'Crude Oil Futures',
        commodities_extractors.get_crude_oil,
        'crude_oil.csv',
        'crude_oil_price'
    )


def extract_copper():
    """Extract Copper futures historical data."""
    return _extract_simple_series(
        'Copper Futures',
        commodities_extractors.get_copper,
        'copper.csv',
        'copper_price'
    )


def extract_es_futures():
    """Extract ES Futures (S&P 500 E-mini) historical data."""
    return _extract_simple_series(
        'ES Futures',
        yfinance_extractors.get_es_futures,
        'es_futures.csv',
        'es_price'
    )


def extract_rty_futures():
    """Extract RTY Futures (Russell 2000 E-mini) historical data."""
    return _extract_simple_series(
        'RTY Futures',
        yfinance_extractors.get_rty_futures,
        'rty_futures.csv',
        'rty_price'
    )


def extract_jpy():
    """Extract USD/JPY exchange rate historical data."""
    return _extract_simple_series(
        'USD/JPY Exchange Rate',
        yfinance_extractors.get_jpy_exchange_rate,
        'jpy.csv',
        'jpy_rate'
    )


def extract_cot_positioning():
    """Extract CFTC COT positioning data for Gold and Silver."""
    print("\n📊 Extracting CFTC COT Positioning...")
    try:
        data = cot_extractor.get_cot_gold_silver()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        results = []
        for metal_key, csv_name in [('gold', 'cot_gold.csv'), ('silver', 'cot_silver.csv')]:
            metal_data = data.get(metal_key, {})
            if not isinstance(metal_data, dict) or 'error' in metal_data:
                continue

            hist = metal_data.get('historical')
            if hist is None or not isinstance(hist, pd.Series) or hist.empty:
                continue

            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'managed_money_net': hist.values,
            })

            # Add open interest if available
            hist_oi = metal_data.get('historical_oi')
            if hist_oi is not None and isinstance(hist_oi, pd.Series) and not hist_oi.empty:
                oi_df = pd.DataFrame({
                    'timestamp': hist_oi.index,
                    'open_interest': hist_oi.values,
                })
                df = pd.merge(df, oi_df, on='timestamp', how='left')

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv(csv_name, df)
            results.append({
                'indicator': f'COT {metal_key.title()}',
                'last_date': df['date'].max(),
                'rows': len(df)
            })

        return results if results else None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_tga_balance():
    """Extract TGA Balance historical data."""
    return _extract_simple_series(
        'TGA Balance',
        fred_extractors.get_tga_balance,
        'tga_balance.csv',
        'tga_balance'
    )


def extract_net_liquidity():
    """Extract Fed Net Liquidity historical data."""
    return _extract_simple_series(
        'Fed Net Liquidity',
        fred_extractors.get_fed_net_liquidity,
        'net_liquidity.csv',
        'net_liquidity'
    )


def extract_sofr():
    """Extract SOFR historical data."""
    return _extract_simple_series(
        'SOFR',
        fred_extractors.get_sofr,
        'sofr.csv',
        'sofr'
    )


def extract_us_2y_yield():
    """Extract US 2-Year Treasury Yield historical data."""
    return _extract_simple_series(
        'US 2-Year Treasury Yield',
        fred_extractors.get_us_2y_yield,
        'us_2y_yield.csv',
        'us_2y_yield'
    )


def extract_japan_2y_yield():
    """Extract Japan 2-Year Government Bond Yield historical data."""
    return _extract_simple_series(
        'Japan 2Y Government Bond Yield',
        japan_yield_extractor.get_japan_2y_yield,
        'japan_2y_yield.csv',
        'japan_2y_yield'
    )


def extract_us2y_jp2y_spread():
    """Extract US 2Y - Japan 2Y yield spread historical data."""
    return _extract_simple_series(
        'US 2Y - Japan 2Y Spread',
        japan_yield_extractor.get_us2y_jp2y_spread,
        'us2y_jp2y_spread.csv',
        'spread'
    )


def _save_equity_source(companies, source_dir, source_label):
    """Save equity quarterly + valuation data for one source into a directory.

    Args:
        companies: dict of {ticker: company_data}
        source_dir: absolute path to output directory (e.g. .../yahoo_finance)
        source_label: display name for logging (e.g. 'Yahoo Finance')

    Returns:
        list of result dicts
    """
    Path(source_dir).mkdir(parents=True, exist_ok=True)

    INCOME_KEYS = [
        'total_revenue', 'cost_of_revenue', 'gross_profit', 'operating_expense',
        'research_development', 'selling_general_admin', 'operating_income',
        'ebitda', 'ebit', 'pretax_income', 'tax_provision', 'net_income',
        'diluted_eps', 'basic_eps', 'diluted_shares', 'basic_shares',
    ]
    BALANCE_KEYS = [
        'total_assets', 'current_assets', 'cash_and_short_term_investments',
        'cash_and_equivalents', 'accounts_receivable', 'inventory', 'goodwill',
        'net_ppe', 'total_liabilities', 'current_liabilities', 'non_current_liabilities',
        'long_term_debt', 'current_debt', 'total_debt', 'accounts_payable',
        'accrued_expenses', 'net_debt', 'stockholders_equity', 'retained_earnings',
        'invested_capital', 'debt_ratio', 'debt_to_equity', 'current_ratio',
    ]
    CASHFLOW_KEYS = [
        'operating_cash_flow', 'capital_expenditure', 'free_cash_flow',
        'share_repurchases', 'dividends_paid', 'investing_cash_flow',
        'financing_cash_flow', 'depreciation_amortization', 'stock_based_compensation',
    ]

    results = []
    for ticker, co in companies.items():
        if 'error' in co:
            continue

        quarters = co.get('quarters', [])
        if not quarters:
            continue

        rows = []
        for i, q in enumerate(quarters):
            row = {
                'timestamp': datetime.now().isoformat(),
                'quarter': q,
                'ticker': ticker,
                'company_name': co.get('company_name', ticker),
                'source': source_label,
            }
            inc = co.get('income_statement', {}) or {}
            for key in INCOME_KEYS:
                vals = inc.get(key, [])
                row[key] = vals[i] if i < len(vals) else None

            bs = co.get('balance_sheet', {}) or {}
            for key in BALANCE_KEYS:
                vals = bs.get(key, [])
                row[key] = vals[i] if i < len(vals) else None

            cf = co.get('cash_flow', {}) or {}
            for key in CASHFLOW_KEYS:
                vals = cf.get(key, [])
                row[key] = vals[i] if i < len(vals) else None

            rows.append(row)

        if rows:
            df = pd.DataFrame(rows)
            csv_path = os.path.join(source_dir, f"{ticker}_quarterly.csv")

            if os.path.exists(csv_path):
                existing = pd.read_csv(csv_path)
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.drop_duplicates(subset=['quarter'], keep='last')
                combined = combined.sort_values('quarter', ascending=False)
            else:
                combined = df

            combined.to_csv(csv_path, index=False)
            results.append({'indicator': f'Equity {ticker} ({source_label})', 'last_date': quarters[0], 'rows': len(combined)})

    # Save valuation + analysis snapshot
    val_rows = []
    for ticker, co in companies.items():
        if 'error' in co:
            continue
        val = co.get('valuation', {})
        fa = co.get('financial_analysis', {})
        prof = fa.get('profitability', {})
        returns = fa.get('returns', {})
        turnover = fa.get('turnover', {})
        gr = fa.get('growth', {})
        val_rows.append({
            'timestamp': datetime.now().isoformat(),
            'ticker': ticker,
            'company_name': co.get('company_name', ticker),
            'source': source_label,
            'market_cap': co.get('market_cap'),
            'forward_pe': val.get('forward_pe'),
            'trailing_pe': val.get('trailing_pe'),
            'peg_ratio': val.get('peg_ratio'),
            'price_to_book': val.get('price_to_book'),
            'price_to_sales': val.get('price_to_sales'),
            'ev_to_ebitda': val.get('ev_to_ebitda'),
            'ev_to_revenue': val.get('ev_to_revenue'),
            'ev_to_fcf': val.get('ev_to_fcf'),
            'enterprise_value': val.get('enterprise_value'),
            'beta': val.get('beta'),
            'dividend_yield': val.get('dividend_yield'),
            'gross_margin': prof.get('gross_margin'),
            'operating_margin': prof.get('operating_margin'),
            'ebitda_margin': prof.get('ebitda_margin'),
            'fcf_margin': prof.get('fcf_margin'),
            'net_margin': prof.get('net_margin'),
            'roe': returns.get('roe'),
            'roa': returns.get('roa'),
            'roic': returns.get('roic'),
            'asset_turnover': turnover.get('asset_turnover'),
            'debt_to_equity': turnover.get('debt_to_equity'),
            'current_ratio': turnover.get('current_ratio'),
            'eps_growth': gr.get('eps_growth'),
            'revenue_growth': gr.get('revenue_growth'),
            'revenue_qoq': gr.get('revenue_qoq'),
            'revenue_yoy': gr.get('revenue_yoy'),
        })

    if val_rows:
        val_df = pd.DataFrame(val_rows)
        val_path = os.path.join(source_dir, '_valuation_snapshot.csv')
        if os.path.exists(val_path):
            existing = pd.read_csv(val_path)
            existing['timestamp'] = pd.to_datetime(existing['timestamp'], errors='coerce')
            val_df['timestamp'] = pd.to_datetime(val_df['timestamp'], errors='coerce')
            combined = pd.concat([existing, val_df], ignore_index=True)
            combined['date'] = combined['timestamp'].dt.date
            combined = combined.drop_duplicates(subset=['ticker', 'date'], keep='last')
            combined = combined.drop(columns=['date'])
            combined = combined.sort_values(['ticker', 'timestamp'])
        else:
            combined = val_df
        combined.to_csv(val_path, index=False)

    return results


def save_single_company(ticker, company_data, source_label):
    """Save a single company's financial data to the appropriate CSV.

    Thin wrapper around _save_equity_source() for use by the dashboard (on-demand
    fetches) and monitoring scripts (auto-update).

    Args:
        ticker: Ticker symbol (e.g., 'CRM')
        company_data: Dict from get_company_financials_yahoo() or get_company_financials_sec()
        source_label: 'Yahoo Finance' or 'SEC EDGAR'

    Returns:
        list of result dicts, or empty list on error
    """
    eq_base = os.path.join(OUTPUT_DIR, 'equity_financials')
    if source_label == 'Yahoo Finance':
        source_dir = os.path.join(eq_base, 'yahoo_finance')
    elif source_label == 'SEC EDGAR':
        source_dir = os.path.join(eq_base, 'sec_edgar')
    else:
        source_dir = os.path.join(eq_base, source_label.lower().replace(' ', '_'))

    companies = {ticker: company_data}
    return _save_equity_source(companies, source_dir, source_label)


def extract_equity_financials():
    """Extract financial data for top 20 large-cap companies from both Yahoo Finance
    and SEC EDGAR, saving per-company CSVs into source-specific subdirectories.

    Output layout:
        historical_data/equity_financials/yahoo_finance/{TICKER}_quarterly.csv
        historical_data/equity_financials/sec_edgar/{TICKER}_quarterly.csv
    """
    from data_extractors import sec_extractor

    eq_base = os.path.join(OUTPUT_DIR, 'equity_financials')
    all_results = []

    # ── Yahoo Finance ──────────────────────────────────────────
    print("\n📊 Extracting Large-cap Equity Financials — Yahoo Finance...")
    try:
        yf_data = equity_financials_extractor.get_top20_financials()
        if isinstance(yf_data, dict) and 'error' not in yf_data:
            yf_dir = os.path.join(eq_base, 'yahoo_finance')
            yf_results = _save_equity_source(yf_data.get('companies', {}), yf_dir, 'Yahoo Finance')
            all_results.extend(yf_results)
            print(f"  💾 Yahoo Finance: {len(yf_results)} companies → equity_financials/yahoo_finance/")
        else:
            print(f"  ❌ Yahoo Finance error: {yf_data.get('error', 'unknown')}")
    except Exception as e:
        print(f"  ❌ Yahoo Finance error: {e}")

    # ── SEC EDGAR ──────────────────────────────────────────────
    print("\n📊 Extracting Large-cap Equity Financials — SEC EDGAR...")
    try:
        sec_data = sec_extractor.get_top20_financials_sec()
        if isinstance(sec_data, dict) and 'error' not in sec_data:
            sec_dir = os.path.join(eq_base, 'sec_edgar')
            sec_results = _save_equity_source(sec_data.get('companies', {}), sec_dir, 'SEC EDGAR')
            all_results.extend(sec_results)
            print(f"  💾 SEC EDGAR: {len(sec_results)} companies → equity_financials/sec_edgar/")
        else:
            print(f"  ❌ SEC EDGAR error: {sec_data.get('error', 'unknown')}")
    except Exception as e:
        print(f"  ❌ SEC EDGAR error: {e}")

    if all_results:
        return {
            'indicator': 'Equity Financials (Top 20, dual-source)',
            'last_date': datetime.now().strftime('%Y-%m-%d'),
            'rows': len(all_results),
        }
    return None


def create_summary_file(results):
    """Create a summary CSV with latest values from all indicators."""
    print("\n📊 Creating summary file...")

    try:
        aggregator = get_aggregator()
        # Reuse existing data if already fetched (avoids redundant API calls)
        if not aggregator.indicators:
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


# ──────────────────────────────────────────────────────────────────────────────
# Macro-to-Market v1.5 — 22 New Historical CSV Extractors
# ──────────────────────────────────────────────────────────────────────────────

# ── Inflation ─────────────────────────────────────────────────────────────────

def extract_cpi_headline():
    """Extract Headline CPI YoY% (CPIAUCSL) to CSV."""
    return _extract_simple_series(
        'CPI Headline', fred_extractors.get_headline_cpi,
        'cpi_headline.csv', 'cpi'
    )


def extract_core_cpi():
    """Extract Core CPI YoY% (CPILFESL) — special handling for multi-series return."""
    print("\n📊 Extracting Core CPI...")
    try:
        data = fred_extractors.get_core_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_core_cpi')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No Core CPI historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'core_cpi': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('core_cpi.csv', df)
        return {'indicator': 'Core CPI', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_core_pce():
    """Extract Core PCE YoY% (PCEPILFE) — special handling for multi-series return."""
    print("\n📊 Extracting Core PCE...")
    try:
        data = fred_extractors.get_core_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_core_pce')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No Core PCE historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'core_pce': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('core_pce.csv', df)
        return {'indicator': 'Core PCE', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_pce_headline():
    """Extract PCE Headline Price Index (PCEPI) to CSV."""
    return _extract_simple_series(
        'PCE Headline', fred_extractors.get_pce_headline,
        'pce_headline.csv', 'pce'
    )


def extract_ppi():
    """Extract PPI Final Demand YoY% (PPIFIS) to CSV."""
    return _extract_simple_series(
        'PPI Final Demand', fred_extractors.get_ppi,
        'ppi.csv', 'ppi'
    )


def extract_breakeven_5y():
    """Extract 5Y Breakeven Inflation (T5YIE) — special handling for multi-series return."""
    print("\n📊 Extracting 5Y Breakeven Inflation...")
    try:
        data = fred_extractors.get_breakeven_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_5y')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No 5Y breakeven historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'breakeven_5y': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('breakeven_5y.csv', df)
        return {'indicator': '5Y Breakeven', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_breakeven_10y():
    """Extract 10Y Breakeven Inflation (T10YIE) — from get_breakeven_inflation()."""
    print("\n📊 Extracting 10Y Breakeven Inflation...")
    try:
        data = fred_extractors.get_breakeven_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_10y')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No 10Y breakeven historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'breakeven_10y': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('breakeven_10y.csv', df)
        return {'indicator': '10Y Breakeven', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_forward_inflation_5y5y():
    """Extract 5Y5Y Forward Inflation Expectation (T5YIFR) to CSV."""
    return _extract_simple_series(
        '5Y5Y Forward Inflation', fred_extractors.get_5y5y_forward_inflation,
        'forward_inflation_5y5y.csv', 'forward_inflation_5y5y'
    )


# ── Employment ────────────────────────────────────────────────────────────────

def extract_unemployment_rate():
    """Extract Unemployment Rate (UNRATE) to CSV."""
    return _extract_simple_series(
        'Unemployment Rate', fred_extractors.get_unemployment_rate,
        'unemployment_rate.csv', 'unemployment_rate'
    )


def extract_nonfarm_payrolls():
    """Extract Total Nonfarm Payrolls (PAYEMS) to CSV."""
    return _extract_simple_series(
        'Nonfarm Payrolls', fred_extractors.get_nonfarm_payrolls,
        'nonfarm_payrolls.csv', 'nonfarm_payrolls'
    )


def extract_initial_claims():
    """Extract Initial Jobless Claims (ICSA) to CSV."""
    return _extract_simple_series(
        'Initial Claims', fred_extractors.get_initial_jobless_claims,
        'initial_claims.csv', 'initial_claims'
    )


def extract_continuing_claims():
    """Extract Continuing Jobless Claims (CCSA) to CSV."""
    return _extract_simple_series(
        'Continuing Claims', fred_extractors.get_continuing_claims,
        'continuing_claims.csv', 'continuing_claims'
    )


# ── Yield Curve ───────────────────────────────────────────────────────────────

def extract_5y_yield():
    """Extract 5-Year Treasury Yield (DGS5) to CSV."""
    return _extract_simple_series(
        '5Y Treasury Yield', fred_extractors.get_5y_treasury_yield,
        'us_5y_yield.csv', 'us_5y_yield'
    )


def extract_30y_yield():
    """Extract 30-Year Treasury Yield (DGS30) to CSV."""
    return _extract_simple_series(
        '30Y Treasury Yield', fred_extractors.get_30y_treasury_yield,
        'us_30y_yield.csv', 'us_30y_yield'
    )


def extract_spread_10y3m():
    """Extract 10Y-3M Treasury Spread (T10Y3M) to CSV."""
    return _extract_simple_series(
        '10Y-3M Spread', fred_extractors.get_10y3m_spread,
        'spread_10y3m.csv', 'spread_10y3m'
    )


def extract_fed_funds_rate():
    """Extract Effective Fed Funds Rate (DFF) to CSV."""
    return _extract_simple_series(
        'Fed Funds Rate', fred_extractors.get_fed_funds_rate,
        'fed_funds_rate.csv', 'fed_funds_rate'
    )


def extract_fed_target_upper():
    """Extract Fed Funds Target Rate Upper Bound (DFEDTARU) to CSV."""
    return _extract_simple_series(
        'Fed Target Upper', fred_extractors.get_fed_target_upper,
        'fed_target_upper.csv', 'fed_target_upper'
    )


def extract_real_yield_5y():
    """Extract 5Y TIPS Real Yield (DFII5) to CSV."""
    return _extract_simple_series(
        '5Y TIPS Real Yield', fred_extractors.get_real_yield_5y,
        'real_yield_5y.csv', 'real_yield_5y'
    )


def extract_real_yield_10y():
    """Extract 10Y TIPS Real Yield (DFII10) to CSV."""
    return _extract_simple_series(
        '10Y TIPS Real Yield', fred_extractors.get_real_yield_10y,
        'real_yield_10y.csv', 'real_yield_10y'
    )


# ── Credit Spreads ────────────────────────────────────────────────────────────

def extract_hy_oas():
    """Extract ICE BofA HY OAS (BAMLH0A0HYM2) to CSV."""
    return _extract_simple_series(
        'HY OAS', fred_extractors.get_hy_credit_spread,
        'hy_oas.csv', 'hy_oas'
    )


def extract_ig_oas():
    """Extract ICE BofA IG OAS (BAMLC0A0CM) to CSV."""
    return _extract_simple_series(
        'IG OAS', fred_extractors.get_ig_credit_spread,
        'ig_oas.csv', 'ig_oas'
    )


def extract_bbb_oas():
    """Extract ICE BofA BBB OAS (BAMLC0A4CBBB) to CSV."""
    return _extract_simple_series(
        'BBB OAS', fred_extractors.get_bbb_credit_spread,
        'bbb_oas.csv', 'bbb_oas'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fidenza Macro Gap-Fill — 15 New Indicators
# ──────────────────────────────────────────────────────────────────────────────

# ── yfinance-based (simple series) ────────────────────────────────────────────

def extract_brent_crude():
    """Extract Brent Crude Oil futures (BZ=F) historical data."""
    return _extract_simple_series(
        'Brent Crude', fidenza_extractors.get_brent_crude,
        'brent_crude.csv', 'brent_crude_price',
    )


def extract_nikkei_225():
    """Extract Nikkei 225 index (^N225) historical data."""
    return _extract_simple_series(
        'Nikkei 225', fidenza_extractors.get_nikkei_225,
        'nikkei_225.csv', 'nikkei_225',
    )


def extract_fed_funds_futures():
    """Extract Fed Funds Futures (ZQ=F) with price + implied rate."""
    print("\n📊 Extracting Fed Funds Futures...")
    try:
        data = fidenza_extractors.get_fed_funds_futures()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No historical data for Fed Funds Futures")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'ff_futures_price': hist.values,
            'ff_implied_rate': 100 - hist.values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('fed_funds_futures.csv', df)
        return {'indicator': 'Fed Funds Futures', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── EM indices (batch extraction) ─────────────────────────────────────────────

def extract_em_indices():
    """Extract KOSPI, Bovespa, and MSCI EM proxy (EEM) historical data."""
    print("\n📊 Extracting EM indices (KOSPI, Bovespa, EEM)...")
    try:
        data = fidenza_extractors.get_em_indices()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        results = []
        for key, csv_name, col_name in [
            ('kospi', 'kospi_index.csv', 'kospi'),
            ('bovespa', 'bovespa_index.csv', 'bovespa'),
            ('msci_em', 'msci_em.csv', 'msci_em'),
        ]:
            hist = data.get(f'historical_{key}')
            if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
                df = pd.DataFrame({
                    'timestamp': hist.index,
                    'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                    col_name: hist.values,
                })
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                append_to_csv(csv_name, df)
                results.append({
                    'indicator': f'EM {key.upper()}',
                    'last_date': df['date'].max(),
                    'rows': len(df),
                })
            else:
                print(f"  ⚠️  No data for {key}")
        return results if results else None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── SOFR Futures Term Structure (multi-row CSV) ──────────────────────────────

def extract_sofr_futures():
    """Extract SOFR futures term structure to CSV.
    Multi-row format: one row per contract per date.
    Deduplication by (timestamp, contract).
    """
    print("\n📊 Extracting SOFR Futures Term Structure...")
    try:
        data = fidenza_extractors.get_sofr_futures_term_structure()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        contracts = data.get('contracts', [])
        if not contracts:
            print("  ⚠️  No SOFR futures contracts available")
            return None

        all_rows = []
        for c in contracts:
            hist = c.get('historical')
            if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
                for ts, price in hist.items():
                    all_rows.append({
                        'timestamp': ts,
                        'date': ts.date() if hasattr(ts, 'date') else ts,
                        'contract': c['contract'],
                        'price': float(price),
                        'implied_rate': round(100 - float(price), 4),
                    })

        if not all_rows:
            print("  ⚠️  No SOFR futures historical data")
            return None

        df = pd.DataFrame(all_rows)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Custom dedup: by (timestamp, contract) instead of timestamp alone
        filepath = os.path.join(OUTPUT_DIR, 'sofr_futures_term_structure.csv')
        if os.path.exists(filepath):
            existing = pd.read_csv(filepath)
            existing['timestamp'] = pd.to_datetime(existing['timestamp'], errors='coerce')
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['timestamp', 'contract'], keep='last')
            combined = combined.sort_values(['timestamp', 'contract'])
        else:
            combined = df.sort_values(['timestamp', 'contract'])
        combined.to_csv(filepath, index=False)
        print(f"  💾 Saved to: sofr_futures_term_structure.csv ({len(combined)} total rows)")

        return {
            'indicator': 'SOFR Futures Term Structure',
            'last_date': df['date'].max(),
            'rows': len(combined),
        }
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Computed indicators ──────────────────────────────────────────────────────

def extract_xau_jpy():
    """Extract XAU/JPY (Gold in Yen) historical data."""
    return _extract_simple_series(
        'XAU/JPY', fidenza_extractors.get_xau_jpy,
        'xau_jpy.csv', 'xau_jpy',
    )


def extract_gold_silver_ratio():
    """Extract Gold/Silver ratio historical data."""
    return _extract_simple_series(
        'Gold/Silver Ratio', fidenza_extractors.get_gold_silver_ratio,
        'gold_silver_ratio.csv', 'gold_silver_ratio',
    )


# ── FRED-based (new series in fred_extractors) ──────────────────────────────

def extract_adp_employment():
    """Extract ADP Employment (ADPWNUSNERSA) to CSV."""
    return _extract_simple_series(
        'ADP Employment', fred_extractors.get_adp_employment,
        'adp_employment.csv', 'adp_employment',
    )


def extract_fed_balance_sheet():
    """Extract Fed Balance Sheet / Total Assets (WALCL) to CSV."""
    return _extract_simple_series(
        'Fed Balance Sheet', fred_extractors.get_fed_balance_sheet,
        'fed_balance_sheet.csv', 'fed_balance_sheet',
    )


def extract_treasury_term_premia():
    """Extract Treasury Term Premia (10Y, 5Y) to CSV."""
    print("\n📊 Extracting Treasury Term Premia...")
    try:
        data = fred_extractors.get_treasury_term_premia()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        hist_10y = data.get('historical')
        hist_5y = data.get('historical_5y')

        if hist_10y is None or (hasattr(hist_10y, 'empty') and hist_10y.empty):
            print("  ⚠️  No 10Y term premia data")
            return None

        df = pd.DataFrame({
            'timestamp': hist_10y.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist_10y.index],
            'term_premium_10y': hist_10y.values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Merge 5Y if available
        if hist_5y is not None and not hist_5y.empty:
            df_5y = pd.DataFrame({
                'timestamp': hist_5y.index,
                'term_premium_5y': hist_5y.values,
            })
            df_5y['timestamp'] = pd.to_datetime(df_5y['timestamp'])
            df = pd.merge(df, df_5y, on='timestamp', how='left')

        append_to_csv('treasury_term_premia.csv', df)
        return {'indicator': 'Treasury Term Premia', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Web scrape & lower-priority indicators ───────────────────────────────────

def extract_aaii_sentiment():
    """Extract AAII Bull/Bear Sentiment Survey to CSV (snapshot per extraction)."""
    print("\n📊 Extracting AAII Sentiment Survey...")
    try:
        data = fidenza_extractors.get_aaii_sentiment()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        # Handle inf bull_bear_ratio for CSV serialization
        bbr = data.get('bull_bear_ratio')
        if bbr is not None and not isinstance(bbr, (int, float)):
            bbr = None
        if isinstance(bbr, float) and (bbr == float('inf') or bbr != bbr):
            bbr = None

        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'bullish': data.get('bullish'),
            'neutral': data.get('neutral'),
            'bearish': data.get('bearish'),
            'bull_bear_ratio': bbr,
        }])
        append_to_csv('aaii_sentiment.csv', df)
        return {'indicator': 'AAII Sentiment', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_opec_production():
    """Extract OPEC production data to CSV."""
    print("\n📊 Extracting OPEC Production...")
    try:
        data = fidenza_extractors.get_opec_production()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'opec_production_mbpd': hist.values,
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('opec_production.csv', df)
            return {'indicator': 'OPEC Production', 'last_date': df['date'].max(), 'rows': len(df)}
        else:
            # Snapshot only (scrape fallback)
            df = pd.DataFrame([{
                'timestamp': datetime.now(),
                'date': datetime.now().date(),
                'opec_production_mbpd': data.get('opec_production'),
            }])
            append_to_csv('opec_production.csv', df)
            return {'indicator': 'OPEC Production', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_gold_reserves_share():
    """Extract Gold share of global reserves to CSV (snapshot)."""
    print("\n📊 Extracting Gold Reserves Share...")
    try:
        data = fidenza_extractors.get_gold_reserves_share()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'gold_reserves_share_pct': data.get('gold_reserves_share_pct'),
        }])
        append_to_csv('gold_reserves_share.csv', df)
        return {'indicator': 'Gold Reserves Share', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_credit_etf_proxies():
    """Extract HYG, LQD, JNK intraday credit spread proxies to CSVs."""
    print("\n📊 Extracting Credit ETF Proxies (HYG, LQD, JNK)...")
    results = []
    try:
        data = fidenza_extractors.get_credit_etf_proxies()
        mapping = {
            'HYG': ('hyg_price', 'hyg_credit_proxy.csv'),
            'LQD': ('lqd_price', 'lqd_credit_proxy.csv'),
            'JNK': ('jnk_price', 'jnk_credit_proxy.csv'),
        }
        for ticker, (key, csv_name) in mapping.items():
            etf_data = data.get(ticker, {})
            if isinstance(etf_data, dict) and 'error' in etf_data:
                print(f"  ❌ {ticker}: {etf_data['error']}")
                continue
            hist = etf_data.get('historical')
            if hist is not None and not hist.empty:
                df = pd.DataFrame({
                    'timestamp': hist.index,
                    'date': hist.index.date,
                    f'{ticker.lower()}_price': hist.values,
                })
                append_to_csv(csv_name, df)
                print(f"  ✅ {ticker} → {csv_name} | Last: {df['date'].max()} | Rows: {len(df)}")
                results.append({'indicator': ticker, 'last_date': str(df['date'].max()), 'rows': len(df)})
            else:
                print(f"  ⚠️ {ticker}: No historical data")
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
    return results if results else None


# ──────────────────────────────────────────────────────────────────────────────
# Data Extraction Requirements — OHLCV + New Indicators
# ──────────────────────────────────────────────────────────────────────────────

# ── Commodity OHLCV (P0-1) ──────────────────────────────────────────────────

def extract_gold_ohlcv():
    """Extract Gold futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Gold Futures', commodities_extractors.get_gold,
                                 'gold_ohlcv.csv', 'gold')


def extract_silver_ohlcv():
    """Extract Silver futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Silver Futures', commodities_extractors.get_silver,
                                 'silver_ohlcv.csv', 'silver')


def extract_crude_oil_ohlcv():
    """Extract Crude Oil futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Crude Oil Futures', commodities_extractors.get_crude_oil,
                                 'crude_oil_ohlcv.csv', 'crude_oil')


def extract_copper_ohlcv():
    """Extract Copper futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Copper Futures', commodities_extractors.get_copper,
                                 'copper_ohlcv.csv', 'copper')


# ── ES/RTY Futures OHLCV (P0-3) ────────────────────────────────────────────

def extract_es_futures_ohlcv():
    """Extract ES Futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('ES Futures', yfinance_extractors.get_es_futures,
                                 'es_futures_ohlcv.csv', 'es')


def extract_rty_futures_ohlcv():
    """Extract RTY Futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('RTY Futures', yfinance_extractors.get_rty_futures,
                                 'rty_futures_ohlcv.csv', 'rty')


# ── Brent Crude OHLCV (P1-4) ───────────────────────────────────────────────

def extract_brent_crude_ohlcv():
    """Extract Brent Crude futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Brent Crude', fidenza_extractors.get_brent_crude,
                                 'brent_crude_ohlcv.csv', 'brent')


# ── S&P 500 Expanded Fundamentals (P0-2) ────────────────────────────────────

def extract_sp500_fundamentals_expanded():
    """Extract expanded S&P 500 fundamentals (forward P/E, earnings yield, etc.)."""
    print("\n📊 Extracting S&P 500 Expanded Fundamentals...")
    try:
        data = openbb_extractors.get_sp500_fundamentals_historical()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'pe_ratio_trailing': data.get('sp500_pe_trailing'),
            'pe_ratio_forward': data.get('sp500_pe_forward'),
            'pb_ratio': data.get('sp500_pb'),
            'earnings_yield': data.get('earnings_yield'),
            'forward_earnings_yield': data.get('forward_earnings_yield'),
            'dividend_yield_pct': data.get('dividend_yield_pct'),
            'trailing_eps': data.get('trailing_eps'),
            'forward_eps': data.get('forward_eps'),
            'spy_price': data.get('spy_price'),
        }])
        append_to_csv('sp500_fundamentals.csv', df)
        return {'indicator': 'S&P 500 Expanded Fundamentals', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Existing Home Sales (P1-5) ──────────────────────────────────────────────

def extract_existing_home_sales():
    """Extract Existing Home Sales (FRED EXHOSLUSM495S) to CSV."""
    return _extract_simple_series(
        'Existing Home Sales', fred_extractors.get_existing_home_sales,
        'existing_home_sales.csv', 'existing_home_sales',
    )


# ── Sector ETFs (P2-12) ────────────────────────────────────────────────────

def extract_sector_etfs():
    """Extract 11 SPDR sector ETF prices to a single wide-format CSV."""
    print("\n📊 Extracting Sector ETFs...")
    try:
        data = yfinance_extractors.get_sector_etfs()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        # Build wide DataFrame from all sector historical series
        sector_tickers = list(yfinance_extractors.SECTOR_ETFS.keys())
        frames = {}
        for ticker in sector_tickers:
            hist = data.get(f'historical_{ticker.lower()}')
            if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
                frames[f'{ticker.lower()}_close'] = hist

        if not frames:
            print("  ⚠️  No sector ETF data")
            return None

        # Merge all series on date
        combined = pd.DataFrame(frames)
        combined.index.name = 'timestamp'
        df = combined.reset_index()
        df['date'] = [d.date() if hasattr(d, 'date') else d for d in df['timestamp']]
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('sector_etfs.csv', df)
        return {'indicator': 'Sector ETFs', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── VIX Term Structure (P2-11) ──────────────────────────────────────────────

def extract_vix_term_structure():
    """Extract VIX term structure (spot, front-month, contango ratio) to CSV."""
    print("\n📊 Extracting VIX Term Structure...")
    try:
        data = yfinance_extractors.get_vix_term_structure()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        hist_spot = data.get('historical_vix_spot')
        hist_front = data.get('historical_vix_front')
        hist_contango = data.get('historical_contango')

        if hist_spot is None or hist_spot.empty:
            print("  ⚠️  No VIX spot data")
            return None

        # Strip tz and normalize
        for s in [hist_spot, hist_front, hist_contango]:
            if s is not None and hasattr(s.index, 'tz') and s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            if s is not None:
                s.index = s.index.normalize()

        df = pd.DataFrame({
            'timestamp': hist_spot.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist_spot.index],
            'vix_spot': hist_spot.values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        if hist_front is not None and not hist_front.empty:
            df_front = pd.DataFrame({
                'timestamp': hist_front.index,
                'vix_front_month': hist_front.values,
            })
            df_front['timestamp'] = pd.to_datetime(df_front['timestamp'])
            df = pd.merge(df, df_front, on='timestamp', how='left')

        if hist_contango is not None and not hist_contango.empty:
            df_contango = pd.DataFrame({
                'timestamp': hist_contango.index,
                'contango_ratio': hist_contango.values,
            })
            df_contango['timestamp'] = pd.to_datetime(df_contango['timestamp'])
            df = pd.merge(df, df_contango, on='timestamp', how='left')

        append_to_csv('vix_term_structure.csv', df)
        return {'indicator': 'VIX Term Structure', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Put/Call Ratio (P2-10) ──────────────────────────────────────────────────

def extract_put_call_ratio():
    """Extract Put/Call ratio to CSV."""
    return _extract_simple_series(
        'Put/Call Ratio', yfinance_extractors.get_put_call_ratio,
        'put_call_ratio.csv', 'put_call_ratio',
    )


# ── High-Frequency Macro Proxies (P2-13) ────────────────────────────────────

def extract_gdpnow():
    """Extract Atlanta Fed GDPNow (FRED GDPNOW) to CSV."""
    return _extract_simple_series(
        'GDPNow', fred_extractors.get_gdpnow,
        'gdpnow.csv', 'gdpnow',
    )


def extract_wei():
    """Extract NY Fed Weekly Economic Index (FRED WEI) to CSV."""
    return _extract_simple_series(
        'Weekly Economic Index', fred_extractors.get_weekly_economic_index,
        'wei.csv', 'wei',
    )


def extract_baltic_dry_index():
    """Extract Baltic Dry Index (^BDI) to CSV."""
    return _extract_simple_series(
        'Baltic Dry Index', yfinance_extractors.get_baltic_dry_index,
        'baltic_dry_index.csv', 'bdi',
    )


# ──────────────────────────────────────────────────────────────────────────────
# Financial Agent v1.5-v1.9 — 27 FRED Series Batch Extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_financial_agent_historical():
    """Batch-extract all 27 Financial Agent FRED series to individual CSVs.

    Uses the SERIES_MAP from financial_agent_extractors.py to fetch all series
    in one pass, then writes each to historical_data/{key}.csv with columns:
    timestamp, date, {value_column}.
    """
    print("\n📊 Extracting Financial Agent FRED series (27 series)...")
    batch_results = get_all_financial_agent_series()
    results = []

    for key, (series_id, col_name) in FA_SERIES_MAP.items():
        data = batch_results.get(key, {})
        if 'error' in data:
            print(f"  ❌ {key} ({series_id}): {data['error']}")
            continue

        hist = data.get('historical')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print(f"  ⚠️  {key}: no historical data")
            continue

        try:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                col_name: hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            csv_filename = f'{key}.csv'
            append_to_csv(csv_filename, df)
            results.append({
                'indicator': f'{key} ({series_id})',
                'last_date': df['date'].max(),
                'rows': len(df),
            })
        except Exception as e:
            print(f"  ❌ {key}: {str(e)}")

    # Gold price via yfinance (FRED LBMA series discontinued)
    try:
        gold_data = get_gold_price_yfinance()
        if 'error' not in gold_data:
            hist = gold_data['historical']
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'gold_price_fred': hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('gold_price_fred.csv', df)
            results.append({
                'indicator': 'gold_price_fred (GC=F via yfinance)',
                'last_date': df['date'].max(),
                'rows': len(df),
            })
        else:
            print(f"  ❌ gold_price_fred: {gold_data['error']}")
    except Exception as e:
        print(f"  ❌ gold_price_fred: {str(e)}")

    print(f"  ✅ Financial Agent: {len(results)}/27 series extracted")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# OpenBB-Based Indicators (v2.5.0) — 20 CSV Export Wrappers
# ──────────────────────────────────────────────────────────────────────────────

def extract_vix_futures_curve():
    """Extract VIX Futures Curve to CSV."""
    return _extract_simple_series(
        'VIX Futures Curve', openbb_extractors.get_vix_futures_curve,
        'vix_futures_curve.csv', 'vix_spot',
    )


def extract_spy_put_call_oi():
    """Extract SPY Put/Call OI to CSV."""
    print("\n📊 Extracting SPY Put/Call OI...")
    try:
        data = openbb_extractors.get_spy_put_call_oi()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'put_call_ratio': hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('spy_put_call_oi.csv', df)
            return {'indicator': 'SPY Put/Call OI', 'last_date': df['date'].max(), 'rows': len(df)}
        # No historical series — save snapshot
        latest = data.get('put_call_volume_ratio')
        if latest is not None:
            df = pd.DataFrame([{
                'timestamp': pd.Timestamp.now(),
                'date': datetime.now().date(),
                'put_call_volume_ratio': latest,
                'put_call_oi_ratio': data.get('put_call_oi_ratio'),
            }])
            append_to_csv('spy_put_call_oi.csv', df)
            return {'indicator': 'SPY Put/Call OI', 'last_date': str(datetime.now().date()), 'rows': 1}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sp500_multiples():
    """Extract S&P 500 Multiples (forward P/E, PEG) to CSV."""
    print("\n📊 Extracting S&P 500 Multiples...")
    try:
        data = openbb_extractors.get_sp500_historical_multiples()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'date': datetime.now().date(),
            'forward_pe': data.get('forward_pe'),
            'peg_ratio': data.get('peg_ratio'),
            'price_to_sales': data.get('price_to_sales'),
        }])
        append_to_csv('sp500_multiples.csv', df)
        return {'indicator': 'S&P 500 Multiples', 'last_date': str(datetime.now().date()), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_ecb_rates():
    """Extract ECB Policy Rates to CSV."""
    return _extract_simple_series(
        'ECB Policy Rates', openbb_extractors.get_ecb_policy_rates,
        'ecb_rates.csv', 'deposit_rate',
    )


def extract_oecd_cli():
    """Extract OECD Composite Leading Indicator to CSV."""
    return _extract_simple_series(
        'OECD CLI', openbb_extractors.get_oecd_leading_indicator,
        'oecd_cli.csv', 'cli_value',
    )


def extract_cpi_components():
    """Extract CPI Components to CSV."""
    return _extract_simple_series(
        'CPI Components', openbb_extractors.get_cpi_components,
        'cpi_components.csv', 'headline_cpi',
    )


def extract_fama_french():
    """Extract Fama-French 5 Factors to CSV."""
    print("\n📊 Extracting Fama-French 5 Factors...")
    try:
        data = openbb_extractors.get_fama_french_factors()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is not None and isinstance(hist, pd.DataFrame) and not hist.empty:
            df = hist.copy()
            if 'date' not in df.columns and df.index is not None:
                df['date'] = df.index
            df['timestamp'] = pd.to_datetime(df['date']) if 'date' in df.columns else pd.to_datetime(df.index)
            append_to_csv('fama_french_5factors.csv', df)
            return {'indicator': 'Fama-French 5 Factors', 'last_date': str(df.index[-1])[:10], 'rows': len(df)}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_iv_skew():
    """Extract SPX IV Skew to CSV."""
    return _extract_simple_series(
        'SPX IV Skew', openbb_extractors.get_spx_iv_skew,
        'spx_iv_skew.csv', 'skew_index',
    )


def extract_eu_yields():
    """Extract European Government Yields to CSV."""
    print("\n📊 Extracting European Yields...")
    try:
        data = openbb_extractors.get_european_yields()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'date': datetime.now().date(),
            'de_10y': data.get('de_10y'),
            'fr_10y': data.get('fr_10y'),
            'it_10y': data.get('it_10y'),
            'it_de_spread': data.get('it_de_spread'),
        }])
        append_to_csv('european_yields.csv', df)
        return {'indicator': 'European Yields', 'last_date': str(datetime.now().date()), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_global_cpi():
    """Extract Global CPI Comparison to CSV."""
    return _extract_simple_series(
        'Global CPI', openbb_extractors.get_global_cpi_comparison,
        'global_cpi.csv', 'us_cpi_yoy',
    )


def extract_earnings_calendar():
    """Extract Upcoming Earnings Calendar to CSV."""
    print("\n📊 Extracting Earnings Calendar...")
    try:
        data = openbb_extractors.get_upcoming_earnings()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        earnings = data.get('earnings', [])
        if earnings:
            df = pd.DataFrame(earnings)
            df['extraction_date'] = datetime.now().date()
            append_to_csv('earnings_calendar.csv', df)
            return {'indicator': 'Earnings Calendar', 'last_date': str(datetime.now().date()), 'rows': len(df)}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sector_pe_ratios():
    """Extract Sector P/E Ratios to CSV."""
    print("\n📊 Extracting Sector P/E Ratios...")
    try:
        data = openbb_extractors.get_sector_pe_ratios()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        sectors = data.get('sectors', {})
        if sectors:
            row = {'timestamp': pd.Timestamp.now(), 'date': datetime.now().date()}
            row.update(sectors)
            df = pd.DataFrame([row])
            append_to_csv('sector_pe_ratios.csv', df)
            return {'indicator': 'Sector P/E Ratios', 'last_date': str(datetime.now().date()), 'rows': 1}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_full_treasury_curve():
    """Extract Full Treasury Yield Curve to CSV."""
    print("\n📊 Extracting Treasury Curve...")
    try:
        data = openbb_extractors.get_full_treasury_curve()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        curve = data.get('curve', {})
        if curve:
            row = {'timestamp': pd.Timestamp.now(), 'date': datetime.now().date()}
            row.update(curve)
            df = pd.DataFrame([row])
            append_to_csv('full_treasury_curve.csv', df)
            return {'indicator': 'Treasury Curve', 'last_date': str(datetime.now().date()), 'rows': 1}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_corporate_spreads():
    """Extract Corporate Bond Spreads (AAA/BBB) to CSV."""
    print("\n📊 Extracting Corporate Spreads...")
    try:
        data = openbb_extractors.get_corporate_bond_spreads()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        # Use AAA historical series if available
        hist = data.get('aaa_historical')
        if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'aaa_oas': hist.values,
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('corporate_spreads_aaa.csv', df)
        # Also save BBB
        bbb_hist = data.get('bbb_historical')
        if bbb_hist is not None and isinstance(bbb_hist, pd.Series) and not bbb_hist.empty:
            df_bbb = pd.DataFrame({
                'timestamp': bbb_hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in bbb_hist.index],
                'bbb_oas': bbb_hist.values,
            })
            df_bbb['timestamp'] = pd.to_datetime(df_bbb['timestamp'])
            append_to_csv('corporate_spreads_bbb.csv', df_bbb)
        return {'indicator': 'Corporate Spreads', 'last_date': data.get('latest_date', ''), 'rows': len(hist) if hist is not None else 0}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_intl_unemployment():
    """Extract International Unemployment Rates to CSV."""
    return _extract_simple_series(
        'International Unemployment', openbb_extractors.get_international_unemployment,
        'intl_unemployment.csv', 'us_unemployment',
    )


def extract_intl_gdp():
    """Extract International GDP Growth to CSV."""
    return _extract_simple_series(
        'International GDP', openbb_extractors.get_international_gdp,
        'intl_gdp.csv', 'us_gdp_growth',
    )


def extract_money_measures():
    """Extract Money Supply Measures (M1/M2) to CSV."""
    return _extract_simple_series(
        'Money Measures', openbb_extractors.get_money_measures,
        'money_measures.csv', 'm2_level',
    )


def extract_global_pmi_openbb():
    """Extract Global Manufacturing PMI to CSV."""
    return _extract_simple_series(
        'Global PMI', openbb_extractors.get_global_pmi,
        'global_pmi.csv', 'us_mfg_pmi',
    )


def extract_equity_risk_premium():
    """Extract Equity Risk Premium to CSV."""
    print("\n📊 Extracting Equity Risk Premium...")
    try:
        data = openbb_extractors.get_equity_risk_premium()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'date': datetime.now().date(),
            'erp': data.get('equity_risk_premium'),
            'forward_erp': data.get('forward_erp'),
            'earnings_yield': data.get('earnings_yield'),
            'real_yield_10y': data.get('real_yield_10y'),
        }])
        append_to_csv('equity_risk_premium.csv', df)
        return {'indicator': 'Equity Risk Premium', 'last_date': str(datetime.now().date()), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


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

    # Helper to run an extraction and record the result
    def _run(extract_fn, meta_key):
        r = extract_fn()
        if r is not None:
            if isinstance(r, list):
                results.extend(r)
                for item in r:
                    metadata['indicators'][item['indicator']] = item
            else:
                results.append(r)
                metadata['indicators'][meta_key] = r

    # ── Original indicators ──────────────────────────────────
    _run(extract_russell_2000_historical, 'russell_2000')
    _run(extract_sp500_with_ma200, 'sp500_ma200')
    _run(extract_vix_move, 'vix_move')
    _run(extract_dxy, 'dxy')
    _run(extract_shiller_cape, 'shiller_cape')
    _run(extract_sp500_fundamentals, 'sp500_fundamentals')
    _run(extract_cboe_skew, 'cboe_skew')
    _run(extract_fred_indicators, 'fred')

    # ── Indicators 11-12: FRED (10Y yield, ISM PMI) ─────────
    _run(extract_10y_yield, '10y_yield')
    _run(extract_ism_pmi, 'ism_pmi')

    # ── Indicators 13-16: Commodities ────────────────────────
    _run(extract_gold, 'gold')
    _run(extract_silver, 'silver')
    _run(extract_crude_oil, 'crude_oil')
    _run(extract_copper, 'copper')

    # ── Indicators 17-18: Futures ────────────────────────────
    _run(extract_es_futures, 'es_futures')
    _run(extract_rty_futures, 'rty_futures')

    # ── Indicator 20: JPY Exchange Rate ──────────────────────
    _run(extract_jpy, 'jpy')

    # ── Indicator 22: CFTC COT Positioning ───────────────────
    _run(extract_cot_positioning, 'cot_positioning')

    # ── Indicators 23-25: TGA, Net Liquidity, SOFR ──────────
    _run(extract_tga_balance, 'tga_balance')
    _run(extract_net_liquidity, 'net_liquidity')
    _run(extract_sofr, 'sofr')

    # ── Indicators 26-28: US 2Y, Japan 2Y, Spread ───────────
    _run(extract_us_2y_yield, 'us_2y_yield')
    _run(extract_japan_2y_yield, 'japan_2y_yield')
    _run(extract_us2y_jp2y_spread, 'us2y_jp2y_spread')

    # ── Indicator 29: Large-cap Equity Financials ────────────
    _run(extract_equity_financials, 'equity_financials')

    # ── Indicators 30+: Macro-to-Market v1.5 ──────────────────

    # Inflation
    _run(extract_cpi_headline, 'cpi_headline')
    _run(extract_core_cpi, 'core_cpi')
    _run(extract_core_pce, 'core_pce')
    _run(extract_pce_headline, 'pce_headline')
    _run(extract_ppi, 'ppi')
    _run(extract_breakeven_5y, 'breakeven_5y')
    _run(extract_breakeven_10y, 'breakeven_10y')
    _run(extract_forward_inflation_5y5y, 'forward_inflation_5y5y')

    # Employment
    _run(extract_unemployment_rate, 'unemployment_rate')
    _run(extract_nonfarm_payrolls, 'nonfarm_payrolls')
    _run(extract_initial_claims, 'initial_claims')
    _run(extract_continuing_claims, 'continuing_claims')

    # Yield Curve
    _run(extract_5y_yield, 'us_5y_yield')
    _run(extract_30y_yield, 'us_30y_yield')
    _run(extract_spread_10y3m, 'spread_10y3m')
    _run(extract_fed_funds_rate, 'fed_funds_rate')
    _run(extract_fed_target_upper, 'fed_target_upper')
    _run(extract_real_yield_5y, 'real_yield_5y')
    _run(extract_real_yield_10y, 'real_yield_10y')

    # Credit Spreads
    _run(extract_hy_oas, 'hy_oas')
    _run(extract_ig_oas, 'ig_oas')
    _run(extract_bbb_oas, 'bbb_oas')

    # ── Fidenza Macro Gap-Fill Indicators ──────────────────────
    # High priority
    _run(extract_sofr_futures, 'sofr_futures')
    _run(extract_brent_crude, 'brent_crude')
    _run(extract_nikkei_225, 'nikkei_225')
    _run(extract_aaii_sentiment, 'aaii_sentiment')
    _run(extract_em_indices, 'em_indices')

    # Medium priority
    _run(extract_fed_funds_futures, 'fed_funds_futures')
    _run(extract_xau_jpy, 'xau_jpy')
    _run(extract_gold_silver_ratio, 'gold_silver_ratio')
    _run(extract_adp_employment, 'adp_employment')
    _run(extract_fed_balance_sheet, 'fed_balance_sheet')
    _run(extract_treasury_term_premia, 'treasury_term_premia')

    # Lower priority (may fail gracefully — no EIA key / WGC 404)
    _run(extract_opec_production, 'opec_production')
    _run(extract_gold_reserves_share, 'gold_reserves_share')

    # Intraday credit spread proxies
    _run(extract_credit_etf_proxies, 'credit_etf_proxies')

    # ── Data Extraction Requirements — OHLCV + New Indicators ──
    # P0: Commodity + Futures OHLCV (2-year)
    _run(extract_gold_ohlcv, 'gold_ohlcv')
    _run(extract_silver_ohlcv, 'silver_ohlcv')
    _run(extract_crude_oil_ohlcv, 'crude_oil_ohlcv')
    _run(extract_copper_ohlcv, 'copper_ohlcv')
    _run(extract_es_futures_ohlcv, 'es_futures_ohlcv')
    _run(extract_rty_futures_ohlcv, 'rty_futures_ohlcv')
    _run(extract_brent_crude_ohlcv, 'brent_crude_ohlcv')

    # P0: S&P 500 expanded fundamentals
    _run(extract_sp500_fundamentals_expanded, 'sp500_fundamentals_expanded')

    # P1: New FRED series
    _run(extract_existing_home_sales, 'existing_home_sales')

    # P2: New yfinance datasets
    _run(extract_sector_etfs, 'sector_etfs')
    _run(extract_vix_term_structure, 'vix_term_structure')
    _run(extract_put_call_ratio, 'put_call_ratio')
    _run(extract_baltic_dry_index, 'baltic_dry_index')

    # P2: High-frequency macro proxies (FRED)
    _run(extract_gdpnow, 'gdpnow')
    _run(extract_wei, 'wei')

    # ── Financial Agent v1.5-v1.9 — 27 FRED Series ────────────
    _run(extract_financial_agent_historical, 'financial_agent')

    # ── OpenBB-Based Indicators (v2.5.0) ────────────────────────
    _run(extract_vix_futures_curve, 'vix_futures_curve')
    _run(extract_spy_put_call_oi, 'spy_put_call_oi')
    _run(extract_sp500_multiples, 'sp500_multiples')
    _run(extract_ecb_rates, 'ecb_rates')
    _run(extract_oecd_cli, 'oecd_cli')
    _run(extract_cpi_components, 'cpi_components')
    _run(extract_fama_french, 'fama_french')
    _run(extract_iv_skew, 'iv_skew')
    _run(extract_eu_yields, 'eu_yields')
    _run(extract_global_cpi, 'global_cpi')
    _run(extract_earnings_calendar, 'earnings_calendar')
    _run(extract_sector_pe_ratios, 'sector_pe_ratios')
    _run(extract_full_treasury_curve, 'full_treasury_curve')
    _run(extract_corporate_spreads, 'corporate_spreads')
    _run(extract_intl_unemployment, 'intl_unemployment')
    _run(extract_intl_gdp, 'intl_gdp')
    _run(extract_money_measures, 'money_measures')
    _run(extract_global_pmi_openbb, 'global_pmi')
    _run(extract_equity_risk_premium, 'equity_risk_premium')

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
