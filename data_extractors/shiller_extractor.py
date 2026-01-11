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
    Returns: dict with latest CAPE value
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

        # Get the latest non-null CAPE value
        cape_series = excel_data[cape_column].dropna()

        if cape_series.empty:
            return {'error': 'No CAPE data available'}

        latest_cape = cape_series.iloc[-1]

        # Try to get the date
        date_column = excel_data.columns[0]
        date_series = excel_data[date_column].dropna()
        latest_date = date_series.iloc[-1] if not date_series.empty else 'Unknown'

        return {
            'shiller_cape': float(latest_cape),
            'latest_date': str(latest_date),
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
