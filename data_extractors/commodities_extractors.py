"""
Data extractors for commodities (futures contracts) using yfinance.
"""
import yfinance as yf
from datetime import datetime, timedelta


def get_commodity_data(symbol, name):
    """
    Generic function to get commodity futures data.
    Uses last available close price if market is closed.

    Args:
        symbol: Commodity futures ticker (e.g., 'GC=F' for Gold)
        name: Display name for the commodity

    Returns: dict with latest price, historical Close series, and historical_ohlcv DataFrame
    """
    try:
        ticker = yf.Ticker(symbol)

        # Get 5 years of historical data for full OHLCV
        hist_data = ticker.history(period='5y')

        if hist_data.empty:
            # Fallback: try with shorter period
            hist_data = ticker.history(period='2y')

            if hist_data.empty:
                return {'error': f'No data available for {name}'}

        # Use the most recent close price (whether market is open or closed)
        latest_price = hist_data['Close'].iloc[-1]
        latest_date = hist_data.index[-1]

        # Calculate 1-day change from previous close
        if len(hist_data) > 1:
            prev_price = hist_data['Close'].iloc[-2]
            change_1d = ((latest_price / prev_price - 1) * 100)
        else:
            change_1d = 0.0

        # Determine if this is last close or live price
        now = datetime.now()
        data_age_hours = (now - latest_date.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600

        if data_age_hours > 24:
            note = f'Last close from {latest_date.strftime("%Y-%m-%d")} (market closed)'
        else:
            note = 'Last available price'

        # Get contract expiry date
        expiry_date = None
        try:
            info = ticker.info
            if 'expireIsoDate' in info:
                expiry_date = info['expireIsoDate']
            elif 'expireDate' in info and info['expireDate']:
                # Convert timestamp to date string
                expiry_date = datetime.fromtimestamp(info['expireDate']).strftime('%Y-%m-%d')
        except:
            pass

        # Build OHLCV DataFrame (tz-stripped, normalized to midnight)
        ohlcv = hist_data[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        if hasattr(ohlcv.index, 'tz') and ohlcv.index.tz is not None:
            ohlcv.index = ohlcv.index.tz_localize(None)
        ohlcv.index = ohlcv.index.normalize()

        result = {
            'price': float(latest_price),
            'latest_date': latest_date.strftime('%Y-%m-%d %H:%M'),
            'change_1d': float(change_1d) if change_1d is not None else 0.0,
            'historical': hist_data['Close'],
            'historical_ohlcv': ohlcv,
            'source': 'yfinance',
            'note': note
        }

        if expiry_date:
            result['expiry_date'] = expiry_date

        return result
    except Exception as e:
        return {'error': f"Error fetching {name} data: {str(e)}"}


def get_gold():
    """
    Get Gold (GC) futures continuous contract data.
    Returns: dict with latest price
    """
    return get_commodity_data('GC=F', 'Gold')


def get_silver():
    """
    Get Silver (SI) futures continuous contract data.
    Returns: dict with latest price
    """
    return get_commodity_data('SI=F', 'Silver')


def get_crude_oil():
    """
    Get Crude Oil (CL) futures continuous contract data.
    Returns: dict with latest price
    """
    return get_commodity_data('CL=F', 'Crude Oil')


def get_copper():
    """
    Get Copper (HG) futures continuous contract data.
    Returns: dict with latest price
    """
    return get_commodity_data('HG=F', 'Copper')


def get_natural_gas():
    """
    Get Natural Gas (NG) futures continuous contract data.
    Returns: dict with latest price
    """
    return get_commodity_data('NG=F', 'Natural Gas')


def get_copper_gold_ratio():
    """
    Compute Copper/Gold price ratio — classic economic sentiment indicator.
    Rising = growth optimism (industrial demand). Falling = risk aversion (safe haven demand).
    Uses existing gold and copper data to avoid extra API calls.
    """
    try:
        gold_data = get_gold()
        copper_data = get_copper()

        if 'error' in gold_data or 'error' in copper_data:
            errors = []
            if 'error' in gold_data:
                errors.append(f"Gold: {gold_data['error']}")
            if 'error' in copper_data:
                errors.append(f"Copper: {copper_data['error']}")
            return {'error': f"Cannot compute Cu/Au ratio: {'; '.join(errors)}"}

        gold_price = gold_data.get('price')
        copper_price = copper_data.get('price')
        if gold_price is None or copper_price is None or gold_price == 0:
            return {'error': 'Invalid gold/copper prices for ratio'}

        ratio = copper_price / gold_price
        latest_ratio = round(ratio * 1000, 4)  # Scale ×1000 for readability

        # Compute historical ratio
        gold_hist = gold_data.get('historical')
        copper_hist = copper_data.get('historical')
        hist_ratio = None

        if gold_hist is not None and copper_hist is not None:
            common_idx = gold_hist.index.intersection(copper_hist.index)
            if len(common_idx) > 1:
                g = gold_hist[common_idx]
                c = copper_hist[common_idx]
                hist_ratio = (c / g) * 1000  # Scale ×1000
                hist_ratio = hist_ratio.replace([float('inf'), float('-inf')], float('nan')).dropna()

        # 1D change
        change_1d = 0
        if hist_ratio is not None and len(hist_ratio) >= 2:
            prev = float(hist_ratio.iloc[-2])
            if prev != 0:
                change_1d = round(((latest_ratio / prev) - 1) * 100, 2)

        result = {
            'cu_au_ratio': latest_ratio,
            'change_1d': change_1d,
            'latest_date': gold_data.get('latest_date', ''),
            'source': 'yfinance (HG/GC × 1000)',
            'units': 'Ratio × 1000',
            'interpretation': 'Rising = growth optimism; Falling = risk aversion / flight to safety',
        }
        if hist_ratio is not None and len(hist_ratio) > 0:
            result['historical'] = hist_ratio
        return result

    except Exception as e:
        return {'error': f"Error computing Cu/Au ratio: {str(e)}"}


def get_all_commodities():
    """
    Get all commodity data at once.
    Returns: dict with all commodity data
    """
    return {
        'gold': get_gold(),
        'silver': get_silver(),
        'crude_oil': get_crude_oil(),
        'copper': get_copper(),
        'natural_gas': get_natural_gas(),
    }
