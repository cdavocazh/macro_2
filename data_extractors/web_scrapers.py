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

        # Try SPY ETF first (more reliable for fundamentals)
        spy = yf.Ticker("SPY")
        info = spy.info

        # Try to get trailing P/E
        trailing_pe = info.get('trailingPE')

        if trailing_pe and trailing_pe > 0:
            return {
                'sp500_forward_pe': trailing_pe,
                'source': 'yfinance (SPY Trailing P/E)',
                'note': 'Using SPY trailing P/E as forward P/E approximation. Forward P/E typically 10-15% lower than trailing.'
            }

        # Fallback to S&P 500 index
        gspc = yf.Ticker("^GSPC")
        info = gspc.info

        trailing_pe = info.get('trailingPE')

        if trailing_pe and trailing_pe > 0:
            return {
                'sp500_forward_pe': trailing_pe,
                'source': 'yfinance (S&P 500 Trailing P/E)',
                'note': 'Using S&P 500 trailing P/E as forward P/E approximation. Forward P/E typically 10-15% lower than trailing.'
            }

        # If info doesn't have it, try to calculate from fast_info or estimate
        # Return a reasonable estimate based on typical market conditions
        return {
            'sp500_forward_pe': 21.5,
            'source': 'Historical average estimate',
            'note': 'Could not fetch live data. Using long-term average (~21-22). Please refresh data or check data sources.',
            'warning': 'This is an estimate, not live data'
        }

    except Exception as e:
        return {
            'sp500_forward_pe': 21.5,
            'source': 'Historical average estimate',
            'note': f'Error fetching live data: {str(e)}. Using long-term average (~21-22).',
            'warning': 'This is an estimate, not live data'
        }


def get_sp500_put_call_ratio():
    """
    Get S&P 500 Put/Call Ratio from multiple sources.
    Tries: ycharts.com, CBOE, FRED, and SPY options calculation.
    Returns: dict with put/call ratio
    """
    try:
        # First try: ycharts.com
        url = "https://ycharts.com/indicators/cboe_equity_put_call_ratio"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        response = requests.get(url, headers=headers, timeout=15)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for the current value on ycharts
            # ycharts typically has the value in specific divs or spans
            for div in soup.find_all(['div', 'span', 'td']):
                text = div.get_text().strip()
                # Look for a value that looks like a put/call ratio (0.xx or x.xx)
                match = re.search(r'\b(\d+\.?\d{0,3})\b', text)
                if match:
                    value = float(match.group(1))
                    if 0.3 < value < 3.0:
                        # Verify this looks like put/call context
                        parent_text = div.parent.get_text() if div.parent else text
                        if any(keyword in parent_text.lower() for keyword in ['put', 'call', 'ratio', 'latest', 'current']):
                            return {
                                'sp500_put_call_ratio': value,
                                'source': 'YCharts (CBOE Equity Put/Call)',
                                'note': 'Data from ycharts.com'
                            }

    except Exception as e:
        pass

    # Second try: CBOE website
    try:
        url = "https://www.cboe.com/us/options/market_statistics/daily/"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
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
                                    'source': 'CBOE (website)',
                                    'note': 'Data scraped from CBOE website'
                                }

    except Exception as e:
        pass

    # If web scraping failed, try other methods
    return get_put_call_ratio_fallback()


def get_put_call_ratio_fallback():
    """
    Fallback method to get Put/Call Ratio from FRED or calculate from SPY options.
    Returns: dict with put/call ratio
    """
    # Try FRED (CBOE Equity Put/Call Ratio)
    try:
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
                    'note': 'Total market put/call ratio from FRED'
                }
    except Exception as e:
        pass

    # Calculate from SPY options volume
    try:
        import yfinance as yf

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
                    'note': f'Based on {exp} expiration. Volume-based calculation from nearest-term SPY options.',
                    'put_volume': int(put_volume),
                    'call_volume': int(call_volume)
                }
    except Exception as e:
        pass

    return {
        'error': 'Could not get Put/Call Ratio from any source',
        'note': 'All data sources failed. Please check network connection and API keys.'
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


def get_sp500_breadth_indicator():
    """
    Calculate S&P 500 market breadth using a representative sample of stocks.
    Returns Advance/Decline metrics and breadth ratio.

    Note: Full S&P 500 calculation would be slow. Using top 50 stocks as representative sample.
    """
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        # Representative sample of S&P 500 stocks (top 50 by market cap)
        sp500_sample = [
            'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'BRK-B', 'TSLA', 'LLY', 'V',
            'UNH', 'XOM', 'JPM', 'JNJ', 'WMT', 'MA', 'PG', 'AVGO', 'HD', 'CVX',
            'MRK', 'ABBV', 'COST', 'KO', 'PEP', 'ADBE', 'NFLX', 'CRM', 'TMO', 'MCD',
            'ABT', 'CSCO', 'ACN', 'LIN', 'ORCL', 'NKE', 'DHR', 'WFC', 'TXN', 'DIS',
            'PM', 'VZ', 'INTU', 'CMCSA', 'AMD', 'QCOM', 'IBM', 'AMGN', 'HON', 'UNP'
        ]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=5)

        advancing = 0
        declining = 0
        unchanged = 0
        total_checked = 0

        for symbol in sp500_sample:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date)

                if len(hist) >= 2:
                    last_close = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2]

                    if last_close > prev_close:
                        advancing += 1
                    elif last_close < prev_close:
                        declining += 1
                    else:
                        unchanged += 1
                    total_checked += 1
            except:
                continue

        if total_checked == 0:
            return {'error': 'Unable to calculate market breadth - no stock data available'}

        # Calculate metrics
        net_advances = advancing - declining
        ad_ratio = advancing / declining if declining > 0 else float('inf')
        breadth_pct = (advancing / total_checked * 100) if total_checked > 0 else 0

        # Interpretation
        if breadth_pct > 60:
            interpretation = 'Strong bullish breadth - broad market participation'
        elif breadth_pct > 50:
            interpretation = 'Moderate bullish breadth - more stocks advancing'
        elif breadth_pct >= 40:
            interpretation = 'Moderate bearish breadth - more stocks declining'
        else:
            interpretation = 'Weak bearish breadth - broad market weakness'

        return {
            'advancing_stocks': advancing,
            'declining_stocks': declining,
            'unchanged_stocks': unchanged,
            'total_stocks': total_checked,
            'net_advances': net_advances,
            'ad_ratio': ad_ratio,
            'breadth_percentage': breadth_pct,
            'interpretation': interpretation,
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'Calculated from S&P 500 sample (top 50 stocks)',
            'note': f'Sample size: {total_checked} stocks out of 50'
        }
    except Exception as e:
        return {'error': f"Error calculating S&P 500 breadth: {str(e)}"}
