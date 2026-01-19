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

    Returns: dict with latest price and historical data
    """
    try:
        ticker = yf.Ticker(symbol)

        # Get recent historical data (last 60 days to ensure we have data)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=60)

        hist_data = ticker.history(start=start_date, end=end_date)

        if hist_data.empty:
            # Try with longer period if no data
            start_date = end_date - timedelta(days=730)
            hist_data = ticker.history(start=start_date, end=end_date)

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

        result = {
            'price': float(latest_price),
            'latest_date': latest_date.strftime('%Y-%m-%d %H:%M'),
            'change_1d': float(change_1d) if change_1d is not None else 0.0,
            'historical': hist_data['Close'],
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


def get_all_commodities():
    """
    Get all commodity data at once.
    Returns: dict with all commodity data
    """
    return {
        'gold': get_gold(),
        'silver': get_silver(),
        'crude_oil': get_crude_oil(),
        'copper': get_copper()
    }
