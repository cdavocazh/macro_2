"""
Data extractor for Shiller CAPE Ratio from Robert Shiller's website.
"""
import pandas as pd
import requests
from io import BytesIO
import config


def get_shiller_cape():
    """
    Get Shiller CAPE Ratio from Robert Shiller's website.
    Downloads the Excel file and extracts the CAPE ratio.
    Returns: dict with latest CAPE value and date-indexed historical Series.
    """
    try:
        # Download the Excel file
        response = requests.get(config.SHILLER_DATA_URL, timeout=30)
        response.raise_for_status()

        # Read the Excel file
        # The data is in the sheet with a specific format
        excel_data = pd.read_excel(
            BytesIO(response.content),
            sheet_name='Data',
            skiprows=7  # Skip header rows
        )

        # The CAPE ratio is typically in column 'CAPE' or 'Cyclically Adjusted PE Ratio'
        # Column structure: Date, P, D, E, CPI, Long Rate, Real Price, Real Dividend, Real Earnings, CAPE

        # Clean column names
        excel_data.columns = excel_data.columns.str.strip()

        # Try to find CAPE column (it might be named differently)
        cape_column = None
        for col in excel_data.columns:
            if 'CAPE' in str(col).upper() or 'P/E10' in str(col).upper() or 'CYCLICALLY' in str(col).upper():
                cape_column = col
                break

        # If not found by name, it's usually the 10th column (index 9)
        if cape_column is None:
            if len(excel_data.columns) > 9:
                cape_column = excel_data.columns[9]
            else:
                return {'error': 'CAPE column not found in data'}

        # Build date index from the first column (fractional year format: YYYY.MM)
        # e.g., 1881.01 = January 1881, 2026.01 = January 2026
        date_column = excel_data.columns[0]
        raw_dates = excel_data[date_column]

        # Convert fractional year (e.g. 2026.03) to proper datetime
        dates = []
        for val in raw_dates:
            try:
                val_f = float(val)
                year = int(val_f)
                month = round((val_f - year) * 100)
                if month < 1:
                    month = 1
                if month > 12:
                    month = 12
                dates.append(pd.Timestamp(year=year, month=month, day=1))
            except (ValueError, TypeError):
                dates.append(pd.NaT)

        excel_data['_parsed_date'] = dates

        # Filter rows that have both valid date and CAPE value
        mask = excel_data['_parsed_date'].notna() & excel_data[cape_column].notna()
        valid_data = excel_data.loc[mask]

        if valid_data.empty:
            return {'error': 'No CAPE data available'}

        # Build a properly date-indexed Series
        cape_series = pd.Series(
            valid_data[cape_column].values.astype(float),
            index=valid_data['_parsed_date'].values,
            name='cape_ratio'
        )
        cape_series.index.name = 'date'

        latest_cape = float(cape_series.iloc[-1])
        latest_date = cape_series.index[-1]

        return {
            'shiller_cape': latest_cape,
            'latest_date': pd.Timestamp(latest_date).strftime('%Y-%m-%d'),
            'source': 'Robert Shiller (Yale)',
            'historical': cape_series,
            'interpretation': {
                'low': '< 15 (Undervalued)',
                'normal': '15-25 (Fair value)',
                'high': '25-35 (Overvalued)',
                'very_high': '> 35 (Extremely overvalued)'
            }
        }
    except requests.RequestException as e:
        return {'error': f"Error downloading Shiller data: {str(e)}"}
    except Exception as e:
        return {'error': f"Error processing Shiller CAPE data: {str(e)}"}
