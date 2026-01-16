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
    Falls back to using trailing P/E from yfinance as approximation.
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
            # Use fallback method
            return get_sp500_forward_pe_fallback()

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

        # If scraping failed, use fallback
        return get_sp500_forward_pe_fallback()

    except Exception as e:
        # Use fallback on any error
        return get_sp500_forward_pe_fallback()


def get_sp500_forward_pe_fallback():
    """
    Fallback method to get S&P 500 P/E using yfinance.
    Uses trailing P/E from SPY ETF as proxy for S&P 500.
    Returns: dict with P/E ratio
    """
    try:
        import yfinance as yf

        spy = yf.Ticker("^GSPC")  # S&P 500 index
        info = spy.info

        # Try to get trailing P/E
        trailing_pe = info.get('trailingPE')

        if trailing_pe:
            return {
                'sp500_forward_pe': trailing_pe,
                'source': 'yfinance (S&P 500 Trailing P/E)',
                'note': 'Using trailing P/E as forward P/E approximation. Forward P/E typically 10-15% lower than trailing.'
            }

        return {
            'error': 'Could not get S&P 500 P/E from any source',
            'note': 'Both MacroMicro scraping and yfinance fallback failed'
        }
    except Exception as e:
        return {'error': f"Error in fallback P/E method: {str(e)}"}


def get_sp500_put_call_ratio():
    """
    Attempt to get S&P 500 Put/Call Ratio.
    Tries multiple sources: CBOE website, FRED, and options volume calculation.
    Returns: dict with put/call ratio
    """
    try:
        # First try: CBOE website
        url = "https://www.cboe.com/us/options/market_statistics/daily/"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            tables = soup.find_all('table')

            for table in tables:
                text = table.get_text()
                if 'PUT/CALL' in text.upper() or 'PUT-CALL' in text.upper():
                    matches = re.findall(r'(\d+\.?\d*)', text)
                    if matches:
                        for match in matches:
                            value = float(match)
                            if 0.3 < value < 3.0:
                                return {
                                    'sp500_put_call_ratio': value,
                                    'source': 'CBOE (scraped)',
                                    'note': 'Data scraped from website'
                                }

        # If CBOE scraping failed, try FRED fallback
        return get_put_call_ratio_fallback()

    except Exception as e:
        return get_put_call_ratio_fallback()


def get_put_call_ratio_fallback():
    """
    Fallback method to get Put/Call Ratio from FRED or calculate from SPY options.
    Returns: dict with put/call ratio
    """
    try:
        # Try FRED first (CBOE Equity Put/Call Ratio)
        from fredapi import Fred
        import config

        if config.FRED_API_KEY:
            fred = Fred(api_key=config.FRED_API_KEY)
            pc_data = fred.get_series('PCERTOT')  # Total Put/Call Ratio

            if not pc_data.empty:
                latest_pc = pc_data.iloc[-1]
                latest_date = pc_data.index[-1]

                return {
                    'sp500_put_call_ratio': latest_pc,
                    'latest_date': latest_date.strftime('%Y-%m-%d'),
                    'source': 'FRED (CBOE Total Put/Call)',
                    'note': 'Total market put/call ratio, not S&P 500 specific'
                }
    except:
        pass

    # If all else fails, calculate from SPY options volume
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        spy = yf.Ticker("SPY")

        # Get options expirations
        expirations = spy.options

        if expirations:
            # Use first expiration (nearest term)
            exp = expirations[0]
            opt = spy.option_chain(exp)

            # Sum put and call volumes
            put_volume = opt.puts['volume'].sum() if 'volume' in opt.puts.columns else 0
            call_volume = opt.calls['volume'].sum() if 'volume' in opt.calls.columns else 0

            if call_volume > 0:
                pc_ratio = put_volume / call_volume

                return {
                    'sp500_put_call_ratio': pc_ratio,
                    'source': 'Calculated from SPY options volume',
                    'note': f'Based on {exp} expiration. Single expiration snapshot, may not represent full market sentiment.',
                    'put_volume': int(put_volume),
                    'call_volume': int(call_volume)
                }
    except Exception as e:
        pass

    return {
        'error': 'Could not get Put/Call Ratio from any source',
        'note': 'CBOE scraping, FRED, and SPY options calculation all failed. This metric may require paid data access.'
    }


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
