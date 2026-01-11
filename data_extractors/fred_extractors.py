"""
Data extractors using FRED (Federal Reserve Economic Data) API.
"""
from fredapi import Fred
import config


def get_fred_client():
    """Initialize and return FRED API client."""
    if not config.FRED_API_KEY:
        raise ValueError("FRED_API_KEY not set in config.py or environment variables")
    return Fred(api_key=config.FRED_API_KEY)


def get_us_gdp():
    """
    Get US GDP data from FRED.
    Returns: dict with latest GDP value
    """
    try:
        fred = get_fred_client()

        # GDP series: GDP (Gross Domestic Product)
        gdp_data = fred.get_series('GDP')

        if gdp_data.empty:
            return {'error': 'No GDP data available'}

        latest_gdp = gdp_data.iloc[-1]
        latest_date = gdp_data.index[-1]

        return {
            'us_gdp': latest_gdp,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Billions of Dollars',
            'historical': gdp_data
        }
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f"Error fetching US GDP: {str(e)}"}


def get_sp500_market_cap():
    """
    Get S&P 500 Market Cap from FRED.
    Series: DDDM01USA156NWDB (Market Capitalization of Listed Domestic Companies)
    """
    try:
        fred = get_fred_client()

        # Try multiple series for S&P 500 market cap
        series_ids = [
            'DDDM01USA156NWDB',  # Market Cap of Listed Companies
            'WILL5000INDFC',      # Wilshire 5000 Total Market Full Cap Index (as proxy)
        ]

        for series_id in series_ids:
            try:
                market_cap_data = fred.get_series(series_id)
                if not market_cap_data.empty:
                    latest_market_cap = market_cap_data.iloc[-1]
                    latest_date = market_cap_data.index[-1]

                    return {
                        'sp500_market_cap': latest_market_cap,
                        'latest_date': latest_date.strftime('%Y-%m-%d'),
                        'series_id': series_id,
                        'historical': market_cap_data
                    }
            except:
                continue

        return {'error': 'No market cap data available from FRED'}

    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f"Error fetching S&P 500 Market Cap: {str(e)}"}


def calculate_sp500_marketcap_to_gdp():
    """
    Calculate S&P 500 Market Cap to US GDP ratio (Buffett Indicator).
    Returns: dict with ratio
    """
    try:
        gdp_data = get_us_gdp()
        market_cap_data = get_sp500_market_cap()

        if 'error' in gdp_data or 'error' in market_cap_data:
            return {'error': 'Cannot calculate Market Cap/GDP ratio due to data unavailability'}

        # Both should be in billions
        market_cap = market_cap_data['sp500_market_cap']
        gdp = gdp_data['us_gdp']

        # If market cap is in different units, adjust
        # WILL5000INDFC is an index, so we'll need to handle that differently
        if market_cap_data.get('series_id') == 'WILL5000INDFC':
            # This is an index, not actual market cap
            return {
                'error': 'Market cap data is index-based, cannot calculate exact ratio',
                'note': 'Using Wilshire 5000 as proxy'
            }

        ratio = (market_cap / gdp) * 100  # Express as percentage

        return {
            'marketcap_to_gdp_ratio': ratio,
            'market_cap': market_cap,
            'gdp': gdp,
            'interpretation': 'Above 100% suggests overvaluation (Buffett Indicator)'
        }
    except Exception as e:
        return {'error': f"Error calculating Market Cap/GDP ratio: {str(e)}"}


def get_vix_from_fred():
    """
    Get VIX data from FRED as an alternative source.
    Returns: dict with latest VIX value
    """
    try:
        fred = get_fred_client()

        # VIX series: VIXCLS (CBOE Volatility Index: VIX)
        vix_data = fred.get_series('VIXCLS')

        if vix_data.empty:
            return {'error': 'No VIX data available from FRED'}

        latest_vix = vix_data.iloc[-1]
        latest_date = vix_data.index[-1]

        return {
            'vix': latest_vix,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED',
            'historical': vix_data
        }
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f"Error fetching VIX from FRED: {str(e)}"}
