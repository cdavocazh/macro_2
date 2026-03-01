"""
Data extractors using FRED (Federal Reserve Economic Data) API.
"""
from fredapi import Fred
import pandas as pd
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


def get_10y_treasury_yield():
    """
    Get 10-Year Treasury Constant Maturity Rate from FRED with Yahoo Finance fallback.
    Returns: dict with latest yield value
    """
    try:
        fred = get_fred_client()

        # 10-Year Treasury Yield series: DGS10
        yield_data = fred.get_series('DGS10')

        if yield_data.empty:
            return get_10y_treasury_yield_fallback()

        latest_yield = yield_data.iloc[-1]
        latest_date = yield_data.index[-1]

        return {
            '10y_yield': latest_yield,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED',
            'units': 'Percent',
            'historical': yield_data
        }
    except ValueError as e:
        return get_10y_treasury_yield_fallback()
    except Exception as e:
        return get_10y_treasury_yield_fallback()


def get_10y_treasury_yield_fallback():
    """
    Fallback method to get 10-Year Treasury Yield from Yahoo Finance.
    Returns: dict with latest yield value
    """
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        # Use Yahoo Finance ticker ^TNX (10-Year Treasury Yield)
        tnx = yf.Ticker("^TNX")

        # Get recent historical data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365*10)  # 10 years of data

        hist_data = tnx.history(start=start_date, end=end_date)

        if hist_data.empty:
            return {'error': 'No 10-Year Treasury yield data available from Yahoo Finance'}

        latest_yield = hist_data['Close'].iloc[-1]
        latest_date = hist_data.index[-1]

        return {
            '10y_yield': latest_yield,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'Yahoo Finance (^TNX)',
            'units': 'Percent',
            'historical': hist_data['Close']
        }
    except Exception as e:
        return {'error': f"Error fetching 10-Year Treasury yield from fallback: {str(e)}"}


def get_ism_pmi():
    """
    Get ISM Manufacturing PMI from web sources or use manufacturing proxy.
    ISM PMI is a proprietary index - subscription required for official data.
    Returns: dict with manufacturing activity indicator
    """
    # Try web scraping first
    try:
        import requests
        from bs4 import BeautifulSoup
        import re

        # Try Trading Economics
        url = 'https://tradingeconomics.com/united-states/manufacturing-pmi'
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')

            # Look for PMI value in various common locations
            for element in soup.find_all(['span', 'div', 'td']):
                text = element.get_text().strip()
                # Look for a number that looks like ISM PMI (typically 40-60)
                match = re.search(r'\b(\d{2}\.\d{1,2})\b', text)
                if match:
                    value = float(match.group(1))
                    if 35 < value < 70:  # Reasonable ISM PMI range
                        # Verify this is in PMI context
                        parent_text = soup.get_text()[:2000]
                        if 'PMI' in parent_text or 'Manufacturing' in parent_text:
                            # Get historical data from FRED as proxy
                            fred = get_fred_client()
                            hist_data = fred.get_series('IPMAN')  # For charting purposes

                            # Normalize historical Industrial Production to PMI scale
                            # Formula: PMI_estimate = 50 + (IP - 100) * 0.5
                            normalized_hist = 50 + (hist_data - 100) * 0.5

                            return {
                                'ism_pmi': value,
                                'latest_date': 'Recent',
                                'source': 'Trading Economics (ISM PMI)',
                                'units': 'Index',
                                'historical': normalized_hist,  # Normalized IP data to PMI scale
                                'interpretation': 'Above 50 indicates expansion, below 50 indicates contraction',
                                'note': 'Latest PMI from Trading Economics. Historical data uses Industrial Production as proxy.'
                            }
    except Exception as e:
        pass

    # Fallback: Use manufacturing proxy indicator
    try:
        fred = get_fred_client()

        # Use Chicago Fed National Activity Index - Manufacturing component
        # or Industrial Production: Manufacturing
        ism_data = fred.get_series('IPMAN')  # Industrial Production: Manufacturing

        if ism_data.empty:
            return {'error': 'No manufacturing data available'}

        latest_ism = ism_data.iloc[-1]
        latest_date = ism_data.index[-1]

        # Convert Industrial Production index to PMI-like scale
        # IP index base = 100, typical range 95-105
        # ISM PMI typical range 45-55, base = 50
        # Formula: PMI_estimate = 50 + (IP - 100) * 0.5
        pmi_estimate = 50 + (latest_ism - 100) * 0.5

        # Normalize historical data to PMI scale
        normalized_hist = 50 + (ism_data - 100) * 0.5

        return {
            'ism_pmi': pmi_estimate,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED Industrial Production (Proxy)',
            'units': 'Index (Estimated)',
            'historical': normalized_hist,
            'interpretation': 'Above 50 indicates expansion, below 50 indicates contraction',
            'note': 'Using Industrial Production Manufacturing as proxy for ISM PMI (subscription required for official data)'
        }
    except ValueError as e:
        return {'error': str(e)}
    except Exception as e:
        return {'error': f"Error fetching manufacturing indicator: {str(e)}"}


def get_tga_balance():
    """
    Get US Treasury General Account (TGA) balance from FRED.
    Series: WTREGEN (weekly, millions USD).
    High TGA = Treasury draining liquidity; Low TGA = injecting liquidity.
    """
    try:
        fred = get_fred_client()
        tga_data = fred.get_series('WTREGEN')

        if tga_data.empty:
            return {'error': 'No TGA data available from FRED'}

        tga_data = tga_data.dropna()
        latest = tga_data.iloc[-1]
        latest_date = tga_data.index[-1]

        # Calculate week-over-week change
        prev = tga_data.iloc[-2] if len(tga_data) >= 2 else latest
        change_wow = latest - prev
        change_pct = (change_wow / prev * 100) if prev != 0 else 0

        return {
            'tga_balance': latest,
            'tga_balance_billions': round(latest / 1000, 2),
            'change_wow': change_wow,
            'change_wow_pct': round(change_pct, 2),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (WTREGEN)',
            'units': 'Millions USD',
            'historical': tga_data,
        }
    except Exception as e:
        return {'error': f"Error fetching TGA balance: {str(e)}"}


def get_fed_net_liquidity():
    """
    Calculate Fed Net Liquidity = Fed Total Assets - TGA - ON RRP.
    Series: WALCL (weekly, millions), WTREGEN (weekly, millions), RRPONTSYD (daily, billions).
    Rising net liquidity is bullish for risk assets.
    """
    try:
        fred = get_fred_client()

        walcl = fred.get_series('WALCL').dropna()     # Fed Total Assets (millions)
        tga = fred.get_series('WTREGEN').dropna()      # TGA (millions)
        rrp = fred.get_series('RRPONTSYD').dropna()    # ON RRP (billions)

        if walcl.empty or tga.empty or rrp.empty:
            return {'error': 'Missing FRED series for net liquidity calculation'}

        # Convert ON RRP from billions to millions for consistent units
        rrp_millions = rrp * 1000

        # Align all series to a common date index (forward-fill weekly into daily gaps)
        combined = pd.DataFrame({
            'walcl': walcl,
            'tga': tga,
            'rrp': rrp_millions,
        }).ffill().dropna()

        if combined.empty:
            return {'error': 'Could not align FRED series for net liquidity'}

        combined['net_liquidity'] = combined['walcl'] - combined['tga'] - combined['rrp']

        latest = combined.iloc[-1]
        latest_date = combined.index[-1]

        # Week-over-week change (use 5 business days back)
        prev_idx = max(0, len(combined) - 6)
        prev = combined.iloc[prev_idx]
        change = latest['net_liquidity'] - prev['net_liquidity']
        change_pct = (change / abs(prev['net_liquidity']) * 100) if prev['net_liquidity'] != 0 else 0

        return {
            'net_liquidity': latest['net_liquidity'],
            'net_liquidity_trillions': round(latest['net_liquidity'] / 1_000_000, 3),
            'fed_assets': latest['walcl'],
            'tga': latest['tga'],
            'on_rrp': latest['rrp'],
            'change': change,
            'change_pct': round(change_pct, 2),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (WALCL - WTREGEN - RRPONTSYD)',
            'units': 'Millions USD',
            'historical': combined['net_liquidity'],
            'interpretation': 'Rising net liquidity = bullish for risk assets',
        }
    except Exception as e:
        return {'error': f"Error calculating net liquidity: {str(e)}"}


def get_sofr():
    """
    Get Secured Overnight Financing Rate (SOFR) from FRED.
    Series: SOFR (daily, percent).
    Key short-term funding rate, replacement for LIBOR.
    """
    try:
        fred = get_fred_client()
        sofr_data = fred.get_series('SOFR')

        if sofr_data.empty:
            return {'error': 'No SOFR data available from FRED'}

        sofr_data = sofr_data.dropna()
        latest = sofr_data.iloc[-1]
        latest_date = sofr_data.index[-1]

        # Day-over-day change
        prev = sofr_data.iloc[-2] if len(sofr_data) >= 2 else latest
        change_1d = latest - prev

        return {
            'sofr': latest,
            'change_1d': round(change_1d, 4),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (SOFR)',
            'units': 'Percent',
            'historical': sofr_data,
        }
    except Exception as e:
        return {'error': f"Error fetching SOFR: {str(e)}"}


def get_us_2y_yield():
    """
    Get US 2-Year Treasury Yield from FRED.
    Series: DGS2 (daily, percent).
    Key indicator for Fed rate expectations.
    """
    try:
        fred = get_fred_client()
        yield_data = fred.get_series('DGS2')

        if yield_data.empty:
            return _get_us_2y_yield_fallback()

        yield_data = yield_data.dropna()
        latest = yield_data.iloc[-1]
        latest_date = yield_data.index[-1]

        # Day-over-day change
        prev = yield_data.iloc[-2] if len(yield_data) >= 2 else latest
        change_1d = latest - prev

        # Also get 10Y for spread calculation
        try:
            ten_y = fred.get_series('DGS10').dropna()
            if not ten_y.empty:
                spread_2s10s = ten_y.iloc[-1] - latest
            else:
                spread_2s10s = None
        except Exception:
            spread_2s10s = None

        result = {
            'us_2y_yield': latest,
            'change_1d': round(change_1d, 4),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (DGS2)',
            'units': 'Percent',
            'historical': yield_data,
        }
        if spread_2s10s is not None:
            result['spread_2s10s'] = round(spread_2s10s, 4)
            result['spread_interpretation'] = 'Negative = inverted yield curve (recession signal)'

        return result
    except Exception as e:
        return _get_us_2y_yield_fallback()


def _get_us_2y_yield_fallback():
    """Fallback: get 2Y yield from Yahoo Finance (^IRX proxy or 2YY=F)."""
    try:
        import yfinance as yf
        from datetime import datetime, timedelta

        ticker = yf.Ticker("2YY=F")
        hist = ticker.history(
            start=datetime.now() - timedelta(days=365 * 5),
            end=datetime.now()
        )
        if hist.empty:
            return {'error': 'No 2Y yield data available from FRED or Yahoo Finance'}

        latest = hist['Close'].iloc[-1]
        latest_date = hist.index[-1]
        prev = hist['Close'].iloc[-2] if len(hist) >= 2 else latest

        return {
            'us_2y_yield': latest,
            'change_1d': round(latest - prev, 4),
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'Yahoo Finance (2YY=F)',
            'units': 'Percent',
            'historical': hist['Close'],
        }
    except Exception as e:
        return {'error': f"Error fetching 2Y yield from fallback: {str(e)}"}
