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

        # Get historical data (last 5 years)
        value_data = value_ticker.history(period='5y')
        growth_data = growth_ticker.history(period='5y')

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

        # Get 5 years of data (200-day MA needs ~200 trading days)
        hist_data = sp500.history(period='5y')

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

        hist_data = vix.history(period='5y')

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

        hist_data = move.history(period='5y')

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

        hist_data = dxy.history(period='5y')

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
    Get E-mini S&P 500 Futures (ES) data with 2-year OHLCV history.
    Returns: dict with latest price, historical Close series, and historical_ohlcv DataFrame
    """
    try:
        es = yf.Ticker("ES=F")

        hist_data = es.history(period='5y')

        if hist_data.empty:
            hist_data = es.history(period='2y')
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

        # Build OHLCV DataFrame
        ohlcv = hist_data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        if hasattr(ohlcv.index, 'tz') and ohlcv.index.tz is not None:
            ohlcv.index = ohlcv.index.tz_localize(None)
        ohlcv.index = ohlcv.index.normalize()

        result = {
            'price': float(latest_price),
            'latest_date': latest_date.strftime('%Y-%m-%d %H:%M'),
            'change_1d': float(change_1d),
            'historical': hist_data['Close'],
            'historical_ohlcv': ohlcv,
            'source': 'yfinance'
        }

        if expiry_date:
            result['expiry_date'] = expiry_date

        return result
    except Exception as e:
        return {'error': f"Error fetching ES futures: {str(e)}"}


def get_rty_futures():
    """
    Get Russell 2000 E-mini Futures (RTY) data with 2-year OHLCV history.
    Returns: dict with latest price, historical Close series, and historical_ohlcv DataFrame
    """
    try:
        rty = yf.Ticker("RTY=F")

        hist_data = rty.history(period='5y')

        if hist_data.empty:
            hist_data = rty.history(period='2y')
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

        # Build OHLCV DataFrame
        ohlcv = hist_data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        if hasattr(ohlcv.index, 'tz') and ohlcv.index.tz is not None:
            ohlcv.index = ohlcv.index.tz_localize(None)
        ohlcv.index = ohlcv.index.normalize()

        result = {
            'price': float(latest_price),
            'latest_date': latest_date.strftime('%Y-%m-%d %H:%M'),
            'change_1d': float(change_1d),
            'historical': hist_data['Close'],
            'historical_ohlcv': ohlcv,
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

        hist_data = jpy.history(period='5y')

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


# ── v2.3.0: Major FX Pairs + Market Concentration ─────────────────────────


def get_major_fx_pairs():
    """
    Get major FX pairs: EUR/USD, GBP/USD, EUR/JPY.
    Returns all three in a single dict to minimize API calls.
    """
    try:
        pairs = {
            'EURUSD=X': ('eur_usd', 'EUR/USD'),
            'GBPUSD=X': ('gbp_usd', 'GBP/USD'),
            'EURJPY=X': ('eur_jpy', 'EUR/JPY'),
        }

        result = {'source': 'yfinance', 'units': 'Exchange rates'}

        for ticker_symbol, (key, label) in pairs.items():
            try:
                ticker = yf.Ticker(ticker_symbol)
                hist = ticker.history(period='5y')
                if hist.empty:
                    hist = ticker.history(period='2y')

                if not hist.empty:
                    latest = float(hist['Close'].iloc[-1])
                    latest_date = hist.index[-1]
                    prev = float(hist['Close'].iloc[-2]) if len(hist) > 1 else latest
                    change_pct = round(((latest / prev) - 1) * 100, 2)

                    result[key] = round(latest, 4)
                    result[f'{key}_change_1d'] = change_pct
                    result[f'historical_{key}'] = hist['Close']
                    result['latest_date'] = latest_date.strftime('%Y-%m-%d')
                else:
                    result[key] = None
            except Exception:
                result[key] = None

        if all(result.get(k) is None for k in ['eur_usd', 'gbp_usd', 'eur_jpy']):
            return {'error': 'No FX pair data available'}

        return result

    except Exception as e:
        return {'error': f"Error fetching major FX pairs: {str(e)}"}


def get_market_concentration():
    """
    Get SPY/RSP ratio — cap-weighted vs equal-weight S&P 500.
    Rising ratio = increasing mega-cap concentration (Mag 7 dominance).
    Falling ratio = market broadening.
    """
    try:
        spy = yf.Ticker("SPY")
        rsp = yf.Ticker("RSP")

        spy_hist = spy.history(period='5y')
        rsp_hist = rsp.history(period='5y')

        if spy_hist.empty or rsp_hist.empty:
            return {'error': 'No SPY or RSP data available'}

        # Align dates
        spy_close = spy_hist['Close']
        rsp_close = rsp_hist['Close']

        # Compute ratio
        common_idx = spy_close.index.intersection(rsp_close.index)
        if len(common_idx) < 2:
            return {'error': 'Insufficient overlapping data for SPY/RSP ratio'}

        spy_aligned = spy_close[common_idx]
        rsp_aligned = rsp_close[common_idx]
        ratio = spy_aligned / rsp_aligned

        latest = round(float(ratio.iloc[-1]), 4)
        prev = float(ratio.iloc[-2]) if len(ratio) > 1 else latest
        change_1d = round(((latest / prev) - 1) * 100, 2)

        # 30-day change for trend
        if len(ratio) >= 22:
            prev_30d = float(ratio.iloc[-22])
            change_30d = round(((latest / prev_30d) - 1) * 100, 2)
        else:
            change_30d = 0

        return {
            'spy_rsp_ratio': latest,
            'change_1d': change_1d,
            'change_30d': change_30d,
            'latest_date': ratio.index[-1].strftime('%Y-%m-%d'),
            'source': 'yfinance (SPY/RSP)',
            'units': 'Ratio',
            'historical': ratio,
            'interpretation': f"30D: {'+' if change_30d >= 0 else ''}{change_30d}%. Rising = mega-cap dominance. Falling = broadening.",
        }
    except Exception as e:
        return {'error': f"Error fetching market concentration: {str(e)}"}


# ── v3.0: Data Extraction Requirements — P2 New Datasets ─────────────────────


SECTOR_ETFS = {
    'XLK': 'Technology',
    'XLF': 'Financials',
    'XLV': 'Health Care',
    'XLE': 'Energy',
    'XLI': 'Industrials',
    'XLC': 'Communication Services',
    'XLY': 'Consumer Discretionary',
    'XLP': 'Consumer Staples',
    'XLB': 'Materials',
    'XLRE': 'Real Estate',
    'XLU': 'Utilities',
}


def get_sector_etfs():
    """Batch fetch 11 SPDR sector ETF daily Close prices with 2-year history.

    Returns dict with one key per ticker (e.g. 'XLK') holding the latest price,
    plus 'historical_<ticker>' keys with pd.Series of Close prices.
    """
    try:
        result = {'source': 'yfinance (SPDR Sector ETFs)'}
        for ticker, sector_name in SECTOR_ETFS.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period='5y')
                if not hist.empty:
                    close = hist['Close']
                    latest = float(close.iloc[-1])
                    prev = float(close.iloc[-2]) if len(close) > 1 else latest
                    change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0
                    result[ticker.lower()] = round(latest, 2)
                    result[f'{ticker.lower()}_change_1d'] = change
                    result[f'historical_{ticker.lower()}'] = close
                    result['latest_date'] = close.index[-1].strftime('%Y-%m-%d')
                else:
                    result[ticker.lower()] = None
            except Exception:
                result[ticker.lower()] = None

        if all(result.get(k.lower()) is None for k in SECTOR_ETFS):
            return {'error': 'No sector ETF data available'}

        return result

    except Exception as e:
        return {'error': f"Error fetching sector ETFs: {str(e)}"}


def get_vix_term_structure():
    """Get VIX futures term structure to measure contango/backwardation.

    Fetches VIX spot (^VIX) plus generic front- and back-month VIX futures
    contracts. Computes contango ratio (M2/M1) when available.

    Returns dict with spot vix, front/back prices, contango ratio, and historical.
    """
    try:
        # VIX Spot
        vix = yf.Ticker('^VIX')
        vix_hist = vix.history(period='5y')

        # VIX front-month futures (generic)
        vx1 = yf.Ticker('VX=F')
        vx1_hist = vx1.history(period='5y')

        if vix_hist.empty:
            return {'error': 'No VIX spot data available'}

        vix_close = vix_hist['Close']
        latest_vix = float(vix_close.iloc[-1])

        result = {
            'vix_spot': round(latest_vix, 2),
            'latest_date': vix_close.index[-1].strftime('%Y-%m-%d'),
            'source': 'yfinance (^VIX, VX=F)',
            'historical_vix_spot': vix_close,
        }

        if not vx1_hist.empty:
            vx1_close = vx1_hist['Close']
            latest_vx1 = float(vx1_close.iloc[-1])
            result['vix_front_month'] = round(latest_vx1, 2)
            result['historical_vix_front'] = vx1_close

            # Contango = futures / spot (>1 = contango, <1 = backwardation)
            if latest_vix > 0:
                result['contango_ratio'] = round(latest_vx1 / latest_vix, 4)

            # Historical contango ratio
            if hasattr(vix_close.index, 'tz') and vix_close.index.tz is not None:
                vix_close_aligned = vix_close.tz_localize(None)
            else:
                vix_close_aligned = vix_close
            if hasattr(vx1_close.index, 'tz') and vx1_close.index.tz is not None:
                vx1_close_aligned = vx1_close.tz_localize(None)
            else:
                vx1_close_aligned = vx1_close

            vix_close_aligned.index = vix_close_aligned.index.normalize()
            vx1_close_aligned.index = vx1_close_aligned.index.normalize()
            common = vix_close_aligned.index.intersection(vx1_close_aligned.index)
            if len(common) > 1:
                contango_hist = vx1_close_aligned[common] / vix_close_aligned[common]
                contango_hist = contango_hist.replace([float('inf'), float('-inf')], float('nan')).dropna()
                result['historical_contango'] = contango_hist

        return result

    except Exception as e:
        return {'error': f"Error fetching VIX term structure: {str(e)}"}


def get_put_call_ratio():
    """Get CBOE Equity Put/Call ratio via yfinance (^PCPUT).

    Falls back to SPY options-based approximation if ^PCPUT unavailable.
    """
    try:
        # Try CBOE Put/Call index
        pc = yf.Ticker('^PCPUT')
        hist = pc.history(period='5y')

        if not hist.empty:
            close = hist['Close']
            latest = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) > 1 else latest
            change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0

            return {
                'put_call_ratio': round(latest, 4),
                'latest_date': close.index[-1].strftime('%Y-%m-%d'),
                'change_1d': change,
                'historical': close,
                'source': 'CBOE via yfinance (^PCPUT)',
            }

        # Fallback: try total put/call
        for alt_ticker in ['^PCALL', '^PCRATIO']:
            try:
                alt = yf.Ticker(alt_ticker)
                alt_hist = alt.history(start=start_date, end=end_date)
                if not alt_hist.empty:
                    close = alt_hist['Close']
                    latest = float(close.iloc[-1])
                    prev = float(close.iloc[-2]) if len(close) > 1 else latest
                    change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0
                    return {
                        'put_call_ratio': round(latest, 4),
                        'latest_date': close.index[-1].strftime('%Y-%m-%d'),
                        'change_1d': change,
                        'historical': close,
                        'source': f'yfinance ({alt_ticker})',
                    }
            except Exception:
                continue

        return {'error': 'Put/Call ratio not available from yfinance'}

    except Exception as e:
        return {'error': f"Error fetching put/call ratio: {str(e)}"}


def get_baltic_dry_index():
    """Get Baltic Dry Index (^BDI) — shipping cost indicator.

    Rising BDI = increased demand for shipping raw materials = economic growth.
    """
    try:
        bdi = yf.Ticker('^BDI')
        hist = bdi.history(period='5y')

        if hist.empty:
            # Try alternate ticker
            bdi = yf.Ticker('BDIY')
            hist = bdi.history(period='5y')

        if hist.empty:
            return {'error': 'Baltic Dry Index not available from yfinance'}

        close = hist['Close']
        latest = float(close.iloc[-1])
        prev = float(close.iloc[-2]) if len(close) > 1 else latest
        change = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0.0

        return {
            'bdi': round(latest, 0),
            'latest_date': close.index[-1].strftime('%Y-%m-%d'),
            'change_1d': change,
            'historical': close,
            'source': 'yfinance (^BDI)',
        }

    except Exception as e:
        return {'error': f"Error fetching Baltic Dry Index: {str(e)}"}
