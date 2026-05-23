"""
Data extractor for Shiller CAPE Ratio.
Primary source: multpl.com (monthly table).
Fallback: Robert Shiller's Yale Excel (often stale).
"""
import pandas as pd
import requests
from io import BytesIO
import config


def get_shiller_cape():
    """
    Get Shiller CAPE Ratio.
    Primary: scrape multpl.com/shiller-pe/table/by-month (live data).
    Fallback: download Robert Shiller's Yale Excel (may be stale).
    Returns: dict with latest CAPE value and date-indexed historical Series.
    """
    result = _get_shiller_cape_multpl()
    if 'error' not in result:
        return result
    return _get_shiller_cape_yale()


def _get_shiller_cape_multpl():
    """Scrape Shiller CAPE from multpl.com."""
    try:
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36'
        }
        resp = requests.get(
            'https://www.multpl.com/shiller-pe/table/by-month',
            headers=headers,
            timeout=30
        )
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        table = soup.find('table', id='datatable')
        if not table:
            return {'error': 'multpl.com: CAPE table not found'}

        dates = []
        values = []
        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            if len(cols) >= 2:
                try:
                    date_str = cols[0].text.strip()
                    val_str = cols[1].text.strip().replace(',', '')
                    date = pd.to_datetime(date_str)
                    val = float(val_str)
                    dates.append(date)
                    values.append(val)
                except (ValueError, TypeError):
                    continue

        if not dates:
            return {'error': 'multpl.com: no CAPE rows parsed'}

        cape_series = pd.Series(values, index=dates).sort_index()
        latest_cape = float(cape_series.iloc[-1])
        latest_date = cape_series.index[-1]

        return {
            'shiller_cape': latest_cape,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'multpl.com (Shiller CAPE)',
            'historical': cape_series,
            'interpretation': {
                'low': '< 15 (Undervalued)',
                'normal': '15-25 (Fair value)',
                'high': '25-35 (Overvalued)',
                'very_high': '> 35 (Extremely overvalued)'
            }
        }
    except ImportError:
        return {'error': 'multpl.com: beautifulsoup4 not installed'}
    except requests.RequestException as e:
        return {'error': f'multpl.com request error: {str(e)}'}
    except Exception as e:
        return {'error': f'multpl.com parse error: {str(e)}'}


def _get_shiller_cape_yale():
    """Fallback: download Shiller's Yale Excel file (may be stale post-2023)."""
    try:
        response = requests.get(config.SHILLER_DATA_URL, timeout=30)
        response.raise_for_status()

        excel_data = pd.read_excel(
            BytesIO(response.content),
            sheet_name='Data',
            skiprows=7
        )

        excel_data.columns = excel_data.columns.str.strip()

        cape_column = None
        for col in excel_data.columns:
            if 'CAPE' in str(col).upper() or 'P/E10' in str(col).upper() or 'CYCLICALLY' in str(col).upper():
                cape_column = col
                break

        if cape_column is None:
            if len(excel_data.columns) > 9:
                cape_column = excel_data.columns[9]
            else:
                return {'error': 'Yale Excel: CAPE column not found'}

        date_column = excel_data.columns[0]
        raw_dates = excel_data[date_column]

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
        mask = excel_data['_parsed_date'].notna() & excel_data[cape_column].notna()
        valid_data = excel_data.loc[mask]

        if valid_data.empty:
            return {'error': 'Yale Excel: no valid CAPE data'}

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
            'source': 'Robert Shiller (Yale) — may be stale',
            'historical': cape_series,
            'interpretation': {
                'low': '< 15 (Undervalued)',
                'normal': '15-25 (Fair value)',
                'high': '25-35 (Overvalued)',
                'very_high': '> 35 (Extremely overvalued)'
            }
        }
    except requests.RequestException as e:
        return {'error': f'Yale Excel download error: {str(e)}'}
    except Exception as e:
        return {'error': f'Yale Excel parse error: {str(e)}'}
