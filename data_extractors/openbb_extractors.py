"""
Data extractors using OpenBB Platform for market data.
"""
try:
    from openbb import obb
    OPENBB_AVAILABLE = True
except ImportError:
    OPENBB_AVAILABLE = False
    # OpenBB is optional - fallback methods will be used automatically


def get_sp500_fundamentals():
    """
    Get S&P 500 trailing P/E and P/B ratios using OpenBB.
    Falls back to yfinance if OpenBB is not available.
    Returns: dict with P/E and P/B ratios
    """
    if not OPENBB_AVAILABLE:
        return get_sp500_fundamentals_fallback()

    try:
        # Get S&P 500 ETF (SPY) fundamentals as proxy
        data = obb.equity.fundamental.metrics(symbol="SPY", provider="yfinance")

        if data and hasattr(data, 'results'):
            results = data.results[0] if isinstance(data.results, list) else data.results

            pe_ratio = getattr(results, 'pe_ratio', None) or getattr(results, 'trailing_pe', None)
            pb_ratio = getattr(results, 'pb_ratio', None) or getattr(results, 'price_to_book', None)

            return {
                'sp500_pe_trailing': pe_ratio,
                'sp500_pb': pb_ratio,
                'source': 'OpenBB/YFinance'
            }
        else:
            return get_sp500_fundamentals_fallback()

    except Exception as e:
        return get_sp500_fundamentals_fallback()


def get_sp500_fundamentals_fallback():
    """
    Fallback method to get S&P 500 P/E and P/B using yfinance directly.
    Uses SPY ETF as proxy for S&P 500.
    Returns: dict with P/E and P/B ratios
    """
    try:
        import yfinance as yf

        spy = yf.Ticker("SPY")
        info = spy.info

        pe_ratio = info.get('trailingPE')
        pb_ratio = info.get('priceToBook')

        if pe_ratio or pb_ratio:
            return {
                'sp500_pe_trailing': pe_ratio,
                'sp500_pb': pb_ratio,
                'source': 'yfinance (SPY ETF)',
                'note': 'Using SPY ETF as S&P 500 proxy'
            }

        return {
            'error': 'Could not get S&P 500 fundamentals from any source'
        }
    except Exception as e:
        return {'error': f"Error in fallback fundamentals method: {str(e)}"}


def get_russell_2000_via_openbb():
    """
    Alternative method to get Russell 2000 indices via OpenBB.
    Returns: dict with Russell 2000 Value and Growth data
    """
    if not OPENBB_AVAILABLE:
        return {'error': 'OpenBB not available'}

    try:
        # Using ETF proxies for Russell 2000
        # IWN = Russell 2000 Value
        # IWO = Russell 2000 Growth
        value_data = obb.equity.price.historical(
            symbol="IWN",
            provider="yfinance",
            start_date="2023-01-01"
        )

        growth_data = obb.equity.price.historical(
            symbol="IWO",
            provider="yfinance",
            start_date="2023-01-01"
        )

        result = {}

        if value_data and hasattr(value_data, 'results'):
            value_results = value_data.results
            if value_results:
                latest_value = value_results[-1]
                result['russell_2000_value'] = {
                    'price': latest_value.close,
                    'date': str(latest_value.date)
                }

        if growth_data and hasattr(growth_data, 'results'):
            growth_results = growth_data.results
            if growth_results:
                latest_growth = growth_results[-1]
                result['russell_2000_growth'] = {
                    'price': latest_growth.close,
                    'date': str(latest_growth.date)
                }

        return result if result else {'error': 'No data returned from OpenBB'}

    except Exception as e:
        return {'error': f"Error fetching Russell 2000 via OpenBB: {str(e)}"}
