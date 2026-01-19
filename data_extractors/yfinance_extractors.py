"""
Data extractors using yfinance for various market indices and indicators.
"""
import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta


def get_russell_2000_indices():
    """
    Get Russell 2000 Value and Growth indices.
    Returns: dict with latest values and historical data
    """
    try:
        # Russell 2000 Value Index (IWN ETF as proxy)
        # Russell 2000 Growth Index (IWO ETF as proxy)
        value_ticker = yf.Ticker("IWN")
        growth_ticker = yf.Ticker("IWO")

        # Get historical data (last 2 years)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)

        value_data = value_ticker.history(start=start_date, end=end_date)
        growth_data = growth_ticker.history(start=start_date, end=end_date)

        result = {
            'russell_2000_value': {
                'latest_price': value_data['Close'].iloc[-1] if not value_data.empty else None,
                'latest_date': value_data.index[-1].strftime('%Y-%m-%d') if not value_data.empty else None,
                'change_1d': ((value_data['Close'].iloc[-1] / value_data['Close'].iloc[-2] - 1) * 100) if len(value_data) > 1 else None,
                'historical': value_data['Close']
            },
            'russell_2000_growth': {
                'latest_price': growth_data['Close'].iloc[-1] if not growth_data.empty else None,
                'latest_date': growth_data.index[-1].strftime('%Y-%m-%d') if not growth_data.empty else None,
                'change_1d': ((growth_data['Close'].iloc[-1] / growth_data['Close'].iloc[-2] - 1) * 100) if len(growth_data) > 1 else None,
                'historical': growth_data['Close']
            }
        }

        # Calculate Value/Growth ratio
        if not value_data.empty and not growth_data.empty:
            result['value_growth_ratio'] = value_data['Close'].iloc[-1] / growth_data['Close'].iloc[-1]

        return result
    except Exception as e:
        return {'error': f"Error fetching Russell 2000 indices: {str(e)}"}


def get_sp500_data():
    """
    Get S&P 500 index data for calculating 200MA ratio.
    Returns: dict with price, 200MA, and ratio
    """
    try:
        sp500 = yf.Ticker("^GSPC")

        # Get 2 years of data to calculate 200-day MA
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)

        hist_data = sp500.history(start=start_date, end=end_date)

        if hist_data.empty:
            return {'error': 'No data available for S&P 500'}

        # Calculate 200-day moving average
        hist_data['MA200'] = hist_data['Close'].rolling(window=200).mean()

        latest_price = hist_data['Close'].iloc[-1]
        latest_ma200 = hist_data['MA200'].iloc[-1]
        ratio = (latest_price / latest_ma200) if latest_ma200 else None

        return {
            'sp500_price': latest_price,
            'sp500_ma200': latest_ma200,
            'sp500_to_ma200_ratio': ratio,
            'latest_date': hist_data.index[-1].strftime('%Y-%m-%d'),
            'historical': hist_data[['Close', 'MA200']]
        }
    except Exception as e:
        return {'error': f"Error fetching S&P 500 data: {str(e)}"}


def get_vix():
    """
    Get VIX (Volatility Index) data.
    Returns: dict with latest VIX value
    """
    try:
        vix = yf.Ticker("^VIX")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        hist_data = vix.history(start=start_date, end=end_date)

        if hist_data.empty:
            return {'error': 'No VIX data available'}

        latest_vix = hist_data['Close'].iloc[-1]

        return {
            'vix': latest_vix,
            'latest_date': hist_data.index[-1].strftime('%Y-%m-%d'),
            'change_1d': ((hist_data['Close'].iloc[-1] / hist_data['Close'].iloc[-2] - 1) * 100) if len(hist_data) > 1 else None,
            'historical': hist_data['Close']
        }
    except Exception as e:
        return {'error': f"Error fetching VIX: {str(e)}"}


def get_move_index():
    """
    Get ICE BofA MOVE Index (Treasury Volatility).
    Returns: dict with latest MOVE value
    """
    try:
        move = yf.Ticker("^MOVE")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        hist_data = move.history(start=start_date, end=end_date)

        if hist_data.empty:
            return {'error': 'No MOVE Index data available'}

        latest_move = hist_data['Close'].iloc[-1]

        return {
            'move': latest_move,
            'latest_date': hist_data.index[-1].strftime('%Y-%m-%d'),
            'change_1d': ((hist_data['Close'].iloc[-1] / hist_data['Close'].iloc[-2] - 1) * 100) if len(hist_data) > 1 else None,
            'historical': hist_data['Close']
        }
    except Exception as e:
        return {'error': f"Error fetching MOVE Index: {str(e)}"}


def get_dxy():
    """
    Get U.S. Dollar Index (DXY).
    Returns: dict with latest DXY value
    """
    try:
        dxy = yf.Ticker("DX-Y.NYB")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        hist_data = dxy.history(start=start_date, end=end_date)

        if hist_data.empty:
            return {'error': 'No DXY data available'}

        latest_dxy = hist_data['Close'].iloc[-1]

        return {
            'dxy': latest_dxy,
            'latest_date': hist_data.index[-1].strftime('%Y-%m-%d'),
            'change_1d': ((hist_data['Close'].iloc[-1] / hist_data['Close'].iloc[-2] - 1) * 100) if len(hist_data) > 1 else None,
            'historical': hist_data['Close']
        }
    except Exception as e:
        return {'error': f"Error fetching DXY: {str(e)}"}


def calculate_vix_move_ratio():
    """
    Calculate VIX/MOVE ratio.
    Returns: dict with ratio
    """
    try:
        vix_data = get_vix()
        move_data = get_move_index()

        if 'error' in vix_data or 'error' in move_data:
            return {'error': 'Cannot calculate VIX/MOVE ratio due to data unavailability'}

        vix_value = vix_data['vix']
        move_value = move_data['move']

        ratio = vix_value / move_value if move_value else None

        return {
            'vix_move_ratio': ratio,
            'vix': vix_value,
            'move': move_value
        }
    except Exception as e:
        return {'error': f"Error calculating VIX/MOVE ratio: {str(e)}"}


def get_es_futures():
    """
    Get E-mini S&P 500 Futures (ES) data.
    Returns: dict with latest price and contract info
    """
    try:
        es = yf.Ticker("ES=F")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        hist_data = es.history(start=start_date, end=end_date)

        if hist_data.empty:
            start_date = end_date - timedelta(days=730)
            hist_data = es.history(start=start_date, end=end_date)
            if hist_data.empty:
                return {'error': 'No ES futures data available'}

        latest_price = hist_data['Close'].iloc[-1]
        latest_date = hist_data.index[-1]

        # Calculate 1-day change
        if len(hist_data) > 1:
            prev_price = hist_data['Close'].iloc[-2]
            change_1d = ((latest_price / prev_price - 1) * 100)
        else:
            change_1d = 0.0

        # Get contract expiry
        expiry_date = None
        try:
            info = es.info
            if 'expireIsoDate' in info:
                expiry_date = info['expireIsoDate']
            elif 'expireDate' in info and info['expireDate']:
                expiry_date = datetime.fromtimestamp(info['expireDate']).strftime('%Y-%m-%d')
        except:
            pass

        result = {
            'price': float(latest_price),
            'latest_date': latest_date.strftime('%Y-%m-%d %H:%M'),
            'change_1d': float(change_1d),
            'historical': hist_data['Close'],
            'source': 'yfinance'
        }

        if expiry_date:
            result['expiry_date'] = expiry_date

        return result
    except Exception as e:
        return {'error': f"Error fetching ES futures: {str(e)}"}


def get_rty_futures():
    """
    Get Russell 2000 E-mini Futures (RTY) data.
    Returns: dict with latest price and contract info
    """
    try:
        rty = yf.Ticker("RTY=F")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        hist_data = rty.history(start=start_date, end=end_date)

        if hist_data.empty:
            start_date = end_date - timedelta(days=730)
            hist_data = rty.history(start=start_date, end=end_date)
            if hist_data.empty:
                return {'error': 'No RTY futures data available'}

        latest_price = hist_data['Close'].iloc[-1]
        latest_date = hist_data.index[-1]

        # Calculate 1-day change
        if len(hist_data) > 1:
            prev_price = hist_data['Close'].iloc[-2]
            change_1d = ((latest_price / prev_price - 1) * 100)
        else:
            change_1d = 0.0

        # Get contract expiry
        expiry_date = None
        try:
            info = rty.info
            if 'expireIsoDate' in info:
                expiry_date = info['expireIsoDate']
            elif 'expireDate' in info and info['expireDate']:
                expiry_date = datetime.fromtimestamp(info['expireDate']).strftime('%Y-%m-%d')
        except:
            pass

        result = {
            'price': float(latest_price),
            'latest_date': latest_date.strftime('%Y-%m-%d %H:%M'),
            'change_1d': float(change_1d),
            'historical': hist_data['Close'],
            'source': 'yfinance'
        }

        if expiry_date:
            result['expiry_date'] = expiry_date

        return result
    except Exception as e:
        return {'error': f"Error fetching RTY futures: {str(e)}"}


def get_jpy_exchange_rate():
    """
    Get USD/JPY exchange rate.
    Returns: dict with latest exchange rate
    """
    try:
        jpy = yf.Ticker("JPY=X")

        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)

        hist_data = jpy.history(start=start_date, end=end_date)

        if hist_data.empty:
            return {'error': 'No JPY exchange rate data available'}

        latest_rate = hist_data['Close'].iloc[-1]
        latest_date = hist_data.index[-1]

        # Calculate 1-day change
        if len(hist_data) > 1:
            prev_rate = hist_data['Close'].iloc[-2]
            change_1d = ((latest_rate / prev_rate - 1) * 100)
        else:
            change_1d = 0.0

        return {
            'jpy_rate': latest_rate,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'change_1d': float(change_1d),
            'historical': hist_data['Close'],
            'source': 'yfinance',
            'units': 'JPY per USD'
        }
    except Exception as e:
        return {'error': f"Error fetching JPY exchange rate: {str(e)}"}
