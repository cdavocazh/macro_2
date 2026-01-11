"""
Web scrapers for various macroeconomic indicators.
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re


def get_sp500_forward_pe_macromicro():
    """
    Attempt to get S&P 500 Forward P/E from MacroMicro.
    Note: This may require authentication or have rate limits.
    Returns: dict with forward P/E ratio
    """
    try:
        # MacroMicro URL for S&P 500 Forward P/E
        url = "https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            return {
                'error': f'MacroMicro returned status code {response.status_code}',
                'note': 'MacroMicro may require authentication or API access. Consider using alternative sources.'
            }

        soup = BeautifulSoup(response.content, 'html.parser')

        # Try to extract the latest value from the page
        # This is a generic scraper and may need adjustment based on MacroMicro's HTML structure

        # Look for data in script tags (often contains JSON data)
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string and 'chartData' in script.string:
                # Try to extract data from JavaScript
                # This is a simplified approach
                text = script.string
                # Look for numeric values that might be the forward P/E
                matches = re.findall(r'"value":\s*(\d+\.?\d*)', text)
                if matches:
                    latest_value = float(matches[-1])
                    return {
                        'sp500_forward_pe': latest_value,
                        'source': 'MacroMicro (scraped)',
                        'note': 'Data scraped from website, may not be reliable'
                    }

        return {
            'error': 'Could not extract Forward P/E from MacroMicro',
            'note': 'MacroMicro scraping may not work without API access. Consider manual download or API.',
            'fallback': 'Use S&P 500 trailing P/E as approximation'
        }

    except Exception as e:
        return {'error': f"Error scraping MacroMicro: {str(e)}"}


def get_sp500_put_call_ratio():
    """
    Attempt to get S&P 500 Put/Call Ratio.
    This data is typically available from CBOE or market data providers.
    Returns: dict with put/call ratio
    """
    try:
        # Try to get from CBOE website
        url = "https://www.cboe.com/us/options/market_statistics/daily/"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code != 200:
            return {
                'error': f'CBOE returned status code {response.status_code}',
                'note': 'Put/Call ratio requires market data subscription or alternative source'
            }

        # CBOE website structure may vary, this is a generic approach
        soup = BeautifulSoup(response.content, 'html.parser')

        # Look for tables with put/call data
        tables = soup.find_all('table')

        for table in tables:
            text = table.get_text()
            if 'PUT/CALL' in text.upper() or 'PUT-CALL' in text.upper():
                # Try to extract the ratio
                matches = re.findall(r'(\d+\.?\d*)', text)
                if matches:
                    # Filter for reasonable put/call ratio values (typically 0.5 to 2.0)
                    for match in matches:
                        value = float(match)
                        if 0.3 < value < 3.0:
                            return {
                                'sp500_put_call_ratio': value,
                                'source': 'CBOE (scraped)',
                                'note': 'Data scraped from website, verify accuracy'
                            }

        return {
            'error': 'Could not extract Put/Call Ratio from CBOE',
            'note': 'Put/Call ratio typically requires paid data feed. Consider alternative sources like yfinance options data.',
            'workaround': 'Calculate manually from options chain data'
        }

    except Exception as e:
        return {'error': f"Error fetching Put/Call Ratio: {str(e)}"}


def get_spx_call_skew():
    """
    Attempt to get SPX Call Skew.
    This is an advanced metric that typically requires options market data.
    Returns: dict with call skew value
    """
    try:
        # CBOE publishes SKEW index
        # Try to get from CBOE or use yfinance
        import yfinance as yf

        # CBOE SKEW Index
        skew = yf.Ticker("^SKEW")
        hist = skew.history(period="5d")

        if not hist.empty:
            latest_skew = hist['Close'].iloc[-1]
            return {
                'spx_call_skew': latest_skew,
                'latest_date': hist.index[-1].strftime('%Y-%m-%d'),
                'source': 'CBOE via yfinance',
                'interpretation': {
                    'normal': '100-115 (Normal tail risk)',
                    'elevated': '115-135 (Elevated tail risk)',
                    'high': '> 135 (High tail risk - potential for sharp moves)'
                }
            }

        return {
            'error': 'SKEW index data not available',
            'note': 'SPX call skew requires options market data or CBOE SKEW index'
        }

    except Exception as e:
        return {'error': f"Error fetching SPX Call Skew: {str(e)}"}


def get_cboe_skew_index():
    """
    Get CBOE SKEW Index directly.
    Returns: dict with SKEW value
    """
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        skew = yf.Ticker("^SKEW")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        hist = skew.history(start=start_date, end=end_date)

        if hist.empty:
            return {'error': 'No SKEW index data available'}

        latest_skew = hist['Close'].iloc[-1]

        return {
            'cboe_skew': latest_skew,
            'latest_date': hist.index[-1].strftime('%Y-%m-%d'),
            'source': 'CBOE',
            'historical': hist['Close']
        }
    except Exception as e:
        return {'error': f"Error fetching CBOE SKEW: {str(e)}"}
