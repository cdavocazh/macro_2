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
    Get US total equity market capitalization from FRED.
    Primary: BOGZ1FL893064105Q (Corporate Equities; Asset, Market Value Levels)
      - Quarterly, in millions of dollars, from Federal Reserve Z.1 Financial Accounts
      - Covers all domestic corporate equities (broader than S&P 500)
    Fallback: DDDM01USA156NWDB (discontinued 2020, World Bank annual)
    """
    try:
        fred = get_fred_client()

        # Try series in order of preference
        series_configs = [
            # Primary: Fed Z.1 corporate equities market value (quarterly, millions)
            ('BOGZ1FL893064105Q', 'millions'),
            # Fallback: World Bank market cap % of GDP (discontinued 2020, annual, % of GDP)
            ('DDDM01USA156NWDB', 'pct_gdp'),
        ]

        for series_id, units in series_configs:
            try:
                market_cap_data = fred.get_series(series_id)
                if market_cap_data is not None and not market_cap_data.empty:
                    latest_market_cap = market_cap_data.iloc[-1]
                    latest_date = market_cap_data.index[-1]

                    # Convert millions to billions for BOGZ series
                    if units == 'millions':
                        historical_billions = market_cap_data / 1000.0
                        latest_billions = latest_market_cap / 1000.0
                    else:
                        historical_billions = market_cap_data
                        latest_billions = latest_market_cap

                    return {
                        'sp500_market_cap': latest_billions,
                        'latest_date': latest_date.strftime('%Y-%m-%d'),
                        'series_id': series_id,
                        'units': units,
                        'historical': historical_billions
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
    Calculate Market Cap to US GDP ratio (Buffett Indicator).
    Uses BOGZ1FL893064105Q (corporate equities in billions) / GDP (billions) * 100.
    Returns: dict with ratio as percentage.
    """
    try:
        gdp_data = get_us_gdp()
        market_cap_data = get_sp500_market_cap()

        if 'error' in gdp_data or 'error' in market_cap_data:
            errors = []
            if 'error' in gdp_data:
                errors.append(f"GDP: {gdp_data['error']}")
            if 'error' in market_cap_data:
                errors.append(f"Market Cap: {market_cap_data['error']}")
            return {'error': f"Cannot calculate Market Cap/GDP ratio: {'; '.join(errors)}"}

        # If the series is pct_gdp (old World Bank series), it's already a ratio
        if market_cap_data.get('units') == 'pct_gdp':
            ratio = market_cap_data['sp500_market_cap']
            return {
                'marketcap_to_gdp_ratio': ratio,
                'market_cap': ratio,
                'gdp': gdp_data['us_gdp'],
                'interpretation': 'Above 100% suggests overvaluation (Buffett Indicator)'
            }

        # Both are in billions (BOGZ converted in get_sp500_market_cap)
        market_cap = market_cap_data['sp500_market_cap']
        gdp = gdp_data['us_gdp']

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


# ---------------------------------------------------------------------------
# New indicators added in v2.2.0
# ---------------------------------------------------------------------------

def get_hy_credit_spread():
    """
    Get US High Yield Corporate Bond OAS (Option-Adjusted Spread) from FRED.
    Series: BAMLH0A0HYM2 (ICE BofA US High Yield Index OAS, daily, bps).
    Premier risk appetite indicator — widening spreads signal financial stress.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('BAMLH0A0HYM2')

        if data is None or data.empty:
            return {'error': 'No HY OAS data available from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_1d = round(latest - prev, 2)

        return {
            'hy_oas': latest,
            'change_1d': change_1d,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (BAMLH0A0HYM2)',
            'units': 'Percent (OAS)',
            'historical': data,
            'interpretation': 'Widening = risk aversion; Narrowing = risk appetite',
        }
    except Exception as e:
        return {'error': f"Error fetching HY credit spread: {str(e)}"}


def get_breakeven_inflation():
    """
    Get 5Y and 10Y Breakeven Inflation Rates from FRED.
    Series: T5YIE (5-Year), T10YIE (10-Year). Both daily, percent.
    Market-implied inflation expectations from TIPS spreads.
    """
    try:
        fred = get_fred_client()
        be_5y = fred.get_series('T5YIE')
        be_10y = fred.get_series('T10YIE')

        if (be_5y is None or be_5y.empty) and (be_10y is None or be_10y.empty):
            return {'error': 'No breakeven inflation data from FRED'}

        result = {'source': 'FRED (T5YIE, T10YIE)', 'units': 'Percent'}

        if be_5y is not None and not be_5y.empty:
            be_5y = be_5y.dropna()
            result['breakeven_5y'] = round(float(be_5y.iloc[-1]), 4)
            prev = float(be_5y.iloc[-2]) if len(be_5y) >= 2 else result['breakeven_5y']
            result['change_5y_1d'] = round(result['breakeven_5y'] - prev, 4)
            result['historical_5y'] = be_5y
            result['latest_date'] = be_5y.index[-1].strftime('%Y-%m-%d')

        if be_10y is not None and not be_10y.empty:
            be_10y = be_10y.dropna()
            result['breakeven_10y'] = round(float(be_10y.iloc[-1]), 4)
            prev = float(be_10y.iloc[-2]) if len(be_10y) >= 2 else result['breakeven_10y']
            result['change_10y_1d'] = round(result['breakeven_10y'] - prev, 4)
            result['historical_10y'] = be_10y
            result['latest_date'] = be_10y.index[-1].strftime('%Y-%m-%d')

        result['interpretation'] = 'Above 2.0% = inflation expectations above Fed target'
        return result

    except Exception as e:
        return {'error': f"Error fetching breakeven inflation: {str(e)}"}


def get_real_yield_10y():
    """
    Get 10-Year Real Yield (TIPS) from FRED.
    Series: DFII10 (10-Year Treasury Inflation-Indexed Security, daily, percent).
    The true risk-free real return — key discount rate for all financial assets.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DFII10')

        if data is None or data.empty:
            return {'error': 'No 10Y real yield (TIPS) data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 4)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_1d = round(latest - prev, 4)

        return {
            'real_yield_10y': latest,
            'change_1d': change_1d,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (DFII10)',
            'units': 'Percent',
            'historical': data,
            'interpretation': 'Higher real yields = tighter financial conditions for risk assets',
        }
    except Exception as e:
        return {'error': f"Error fetching 10Y real yield: {str(e)}"}


def get_nfci():
    """
    Get Chicago Fed National Financial Conditions Index from FRED.
    Series: NFCI (weekly). Positive = tighter than average, negative = looser.
    Composite of 105 financial market indicators.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('NFCI')

        if data is None or data.empty:
            return {'error': 'No NFCI data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 4)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_1w = round(latest - prev, 4)

        return {
            'nfci': latest,
            'change_1w': change_1w,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (NFCI)',
            'units': 'Index (0 = average)',
            'historical': data,
            'interpretation': 'Positive = tighter than average; Negative = looser than average',
        }
    except Exception as e:
        return {'error': f"Error fetching NFCI: {str(e)}"}


def get_fed_funds_rate():
    """
    Get Effective Federal Funds Rate from FRED.
    Series: DFF (daily, percent).
    The central policy rate — actual overnight interbank lending rate.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DFF')

        if data is None or data.empty:
            return {'error': 'No Fed Funds Rate data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 4)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_1d = round(latest - prev, 4)

        return {
            'fed_funds_rate': latest,
            'change_1d': change_1d,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (DFF)',
            'units': 'Percent',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching Fed Funds Rate: {str(e)}"}


def get_initial_jobless_claims():
    """
    Get Initial Jobless Claims from FRED.
    Series: ICSA (weekly, seasonally adjusted, number of claims).
    Leading labor market indicator — above 400K signals deterioration.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('ICSA')

        if data is None or data.empty:
            return {'error': 'No Initial Claims data from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_wow = latest - prev
        change_pct = round((change_wow / prev * 100), 1) if prev != 0 else 0

        return {
            'initial_claims': latest,
            'initial_claims_k': round(latest / 1000, 1),
            'change_wow': change_wow,
            'change_wow_pct': change_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (ICSA)',
            'units': 'Number of Claims',
            'historical': data,
            'interpretation': 'Below 250K = strong labor market; Above 400K = warning signal',
        }
    except Exception as e:
        return {'error': f"Error fetching Initial Jobless Claims: {str(e)}"}


def get_unemployment_rate():
    """
    Get U-3 Unemployment Rate from FRED.
    Series: UNRATE (monthly, seasonally adjusted, percent).
    Lagging indicator that confirms recession dating.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('UNRATE')

        if data is None or data.empty:
            return {'error': 'No Unemployment Rate data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 1)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_mom = round(latest - prev, 1)

        return {
            'unemployment_rate': latest,
            'change_mom': change_mom,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (UNRATE)',
            'units': 'Percent',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching Unemployment Rate: {str(e)}"}


def get_core_inflation():
    """
    Get Core CPI and Core PCE year-over-year percentage changes from FRED.
    Series: CPILFESL (Core CPI index, monthly), PCEPILFE (Core PCE index, monthly).
    Computes YoY% from the index levels.
    Core PCE is the Fed's preferred inflation measure.
    """
    try:
        fred = get_fred_client()
        result = {'source': 'FRED (CPILFESL, PCEPILFE)', 'units': 'YoY Percent'}

        # Core CPI
        try:
            cpi = fred.get_series('CPILFESL')
            if cpi is not None and not cpi.empty:
                cpi = cpi.dropna()
                # Compute YoY%: (current / 12-months-ago - 1) * 100
                if len(cpi) >= 13:
                    cpi_yoy = ((cpi / cpi.shift(12)) - 1) * 100
                    cpi_yoy = cpi_yoy.dropna()
                    latest_cpi_yoy = round(float(cpi_yoy.iloc[-1]), 2)
                    prev_cpi_yoy = round(float(cpi_yoy.iloc[-2]), 2) if len(cpi_yoy) >= 2 else latest_cpi_yoy
                    result['core_cpi_yoy'] = latest_cpi_yoy
                    result['core_cpi_change_mom'] = round(latest_cpi_yoy - prev_cpi_yoy, 2)
                    result['historical_core_cpi'] = cpi_yoy
                    result['latest_date'] = cpi_yoy.index[-1].strftime('%Y-%m-%d')
        except Exception:
            pass

        # Core PCE
        try:
            pce = fred.get_series('PCEPILFE')
            if pce is not None and not pce.empty:
                pce = pce.dropna()
                if len(pce) >= 13:
                    pce_yoy = ((pce / pce.shift(12)) - 1) * 100
                    pce_yoy = pce_yoy.dropna()
                    latest_pce_yoy = round(float(pce_yoy.iloc[-1]), 2)
                    prev_pce_yoy = round(float(pce_yoy.iloc[-2]), 2) if len(pce_yoy) >= 2 else latest_pce_yoy
                    result['core_pce_yoy'] = latest_pce_yoy
                    result['core_pce_change_mom'] = round(latest_pce_yoy - prev_pce_yoy, 2)
                    result['historical_core_pce'] = pce_yoy
                    if 'latest_date' not in result:
                        result['latest_date'] = pce_yoy.index[-1].strftime('%Y-%m-%d')
        except Exception:
            pass

        if 'core_cpi_yoy' not in result and 'core_pce_yoy' not in result:
            return {'error': 'Could not compute Core CPI or Core PCE YoY%'}

        result['interpretation'] = "Fed's 2% target. Core PCE is the Fed's preferred measure."
        return result

    except Exception as e:
        return {'error': f"Error fetching core inflation: {str(e)}"}


# ── v2.3.0: Economic Activity & Extended Rates/Credit indicators ──────────


def get_ig_credit_spread():
    """
    Get US Investment Grade Corporate Bond OAS from FRED.
    Series: BAMLC0A0CM (ICE BofA US Corporate Index OAS, daily, %).
    Complement to HY OAS — IG/HY spread differential signals risk appetite.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('BAMLC0A0CM')

        if data is None or data.empty:
            return {'error': 'No IG OAS data available from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 4)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_1d = round(latest - prev, 4)

        return {
            'ig_oas': latest,
            'change_1d': change_1d,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (BAMLC0A0CM)',
            'units': 'Percent (OAS)',
            'historical': data,
            'interpretation': 'Widening = risk aversion; Narrowing = risk appetite',
        }
    except Exception as e:
        return {'error': f"Error fetching IG credit spread: {str(e)}"}


def get_nonfarm_payrolls():
    """
    Get Total Nonfarm Payrolls from FRED.
    Series: PAYEMS (monthly, thousands of persons, seasonally adjusted).
    The single most market-moving economic release.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('PAYEMS')

        if data is None or data.empty:
            return {'error': 'No NFP data available from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_mom = round(latest - prev, 0)  # MoM change in thousands

        return {
            'nfp_thousands': latest,
            'nfp_change_mom': change_mom,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (PAYEMS)',
            'units': 'Thousands of persons',
            'historical': data,
            'interpretation': f"MoM change: {'+' if change_mom >= 0 else ''}{change_mom:.0f}K jobs",
        }
    except Exception as e:
        return {'error': f"Error fetching nonfarm payrolls: {str(e)}"}


def get_consumer_sentiment():
    """
    Get University of Michigan Consumer Sentiment Index from FRED.
    Series: UMCSENT (monthly, index 1966:Q1=100).
    Primary forward-looking consumer confidence indicator.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('UMCSENT')

        if data is None or data.empty:
            return {'error': 'No consumer sentiment data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 1)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_mom = round(latest - prev, 1)

        return {
            'consumer_sentiment': latest,
            'change_mom': change_mom,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (UMCSENT)',
            'units': 'Index (1966:Q1=100)',
            'historical': data,
            'interpretation': 'Historical avg ~85. Below 70 = pessimistic. Below 60 = recession-level.',
        }
    except Exception as e:
        return {'error': f"Error fetching consumer sentiment: {str(e)}"}


def get_sahm_rule():
    """
    Get Sahm Rule Recession Indicator from FRED.
    Series: SAHMREALTIME (monthly, percentage points).
    Signals recession when 3-month moving avg of unemployment rate rises
    ≥0.50 pp above its low over the prior 12 months.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('SAHMREALTIME')

        if data is None or data.empty:
            return {'error': 'No Sahm Rule data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 2)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_mom = round(latest - prev, 2)

        triggered = latest >= 0.50
        return {
            'sahm_value': latest,
            'change_mom': change_mom,
            'triggered': triggered,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (SAHMREALTIME)',
            'units': 'Percentage points',
            'historical': data,
            'threshold': 0.50,
            'interpretation': f"{'🔴 RECESSION SIGNAL (≥0.50)' if triggered else '🟢 Below recession threshold (0.50)'}",
        }
    except Exception as e:
        return {'error': f"Error fetching Sahm Rule: {str(e)}"}


def get_m2_money_supply():
    """
    Get M2 Money Supply from FRED.
    Series: M2SL (monthly, billions of dollars, seasonally adjusted).
    Critical for liquidity analysis — M2 growth rate is a leading indicator.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('M2SL')

        if data is None or data.empty:
            return {'error': 'No M2 data available from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        latest_trillions = round(latest / 1000, 2)

        # YoY growth rate
        yoy_growth = None
        if len(data) >= 13:
            yr_ago = float(data.iloc[-13])
            yoy_growth = round(((latest / yr_ago) - 1) * 100, 2)

        # MoM growth rate
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        mom_growth = round(((latest / prev) - 1) * 100, 2)

        result = {
            'm2_trillions': latest_trillions,
            'm2_yoy_growth': yoy_growth,
            'm2_mom_growth': mom_growth,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (M2SL)',
            'units': 'Trillions USD',
            'historical': data,
        }
        if yoy_growth is not None:
            result['interpretation'] = f"YoY growth: {'+' if yoy_growth >= 0 else ''}{yoy_growth}%"
        return result

    except Exception as e:
        return {'error': f"Error fetching M2 money supply: {str(e)}"}


def get_jolts_openings():
    """
    Get JOLTS Job Openings from FRED.
    Series: JTSJOL (monthly, thousands, seasonally adjusted).
    Fed's preferred labor demand indicator.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('JTSJOL')

        if data is None or data.empty:
            return {'error': 'No JOLTS data from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_mom = round(latest - prev, 0)
        latest_millions = round(latest / 1000, 2)

        return {
            'jolts_openings_k': latest,
            'jolts_openings_m': latest_millions,
            'change_mom': change_mom,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (JTSJOL)',
            'units': 'Thousands',
            'historical': data,
            'interpretation': f"Job openings: {latest_millions}M. Higher = tighter labor market.",
        }
    except Exception as e:
        return {'error': f"Error fetching JOLTS openings: {str(e)}"}


def get_continuing_claims():
    """
    Get Continued Claims (Insured Unemployment) from FRED.
    Series: CCSA (weekly, persons, seasonally adjusted).
    Shows duration of unemployment — are people finding jobs or staying unemployed?
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('CCSA')

        if data is None or data.empty:
            return {'error': 'No continuing claims data from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        latest_k = round(latest / 1000, 1)
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_wow_pct = round(((latest / prev) - 1) * 100, 1) if prev != 0 else 0

        return {
            'continuing_claims_k': latest_k,
            'continuing_claims': latest,
            'change_wow_pct': change_wow_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (CCSA)',
            'units': 'Thousands',
            'historical': data,
            'interpretation': 'Rising = prolonged unemployment; Falling = labor market healing',
        }
    except Exception as e:
        return {'error': f"Error fetching continuing claims: {str(e)}"}


def get_retail_sales():
    """
    Get Advance Retail Sales from FRED.
    Series: RSAFS (monthly, millions of dollars, seasonally adjusted).
    Primary consumer spending indicator — consumer = ~70% of GDP.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('RSAFS')

        if data is None or data.empty:
            return {'error': 'No retail sales data from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        mom_pct = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0
        latest_billions = round(latest / 1000, 1)

        # Compute MoM% series for historical chart
        mom_series = ((data / data.shift(1)) - 1) * 100
        mom_series = mom_series.dropna()

        return {
            'retail_sales_b': latest_billions,
            'retail_sales_mom_pct': mom_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (RSAFS)',
            'units': 'Billions USD',
            'historical': mom_series,  # MoM% for charting
            'historical_level': data,  # Level for reference
            'interpretation': f"MoM: {'+' if mom_pct >= 0 else ''}{mom_pct}%. Consumer spending = ~70% of GDP.",
        }
    except Exception as e:
        return {'error': f"Error fetching retail sales: {str(e)}"}


def get_housing_starts():
    """
    Get Housing Starts from FRED.
    Series: HOUST (monthly, thousands of units, SAAR).
    Most rate-sensitive sector — shows monetary policy transmission.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('HOUST')

        if data is None or data.empty:
            return {'error': 'No housing starts data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 0)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        mom_pct = round(((latest / prev) - 1) * 100, 1) if prev != 0 else 0

        return {
            'housing_starts_k': latest,
            'change_mom_pct': mom_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (HOUST)',
            'units': 'Thousands (SAAR)',
            'historical': data,
            'interpretation': f"MoM: {'+' if mom_pct >= 0 else ''}{mom_pct}%. Rate-sensitive leading indicator.",
        }
    except Exception as e:
        return {'error': f"Error fetching housing starts: {str(e)}"}


def get_industrial_production():
    """
    Get Industrial Production Index from FRED.
    Series: INDPRO (monthly, index 2017=100, seasonally adjusted).
    Broad output indicator for mining, manufacturing, and utilities.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('INDPRO')

        if data is None or data.empty:
            return {'error': 'No industrial production data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 2)
        latest_date = data.index[-1]

        # YoY% change
        yoy_pct = None
        if len(data) >= 13:
            yr_ago = float(data.iloc[-13])
            yoy_pct = round(((latest / yr_ago) - 1) * 100, 2)

        # MoM% change
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        mom_pct = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0

        result = {
            'indpro_index': latest,
            'indpro_yoy_pct': yoy_pct,
            'indpro_mom_pct': mom_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (INDPRO)',
            'units': 'Index (2017=100)',
            'historical': data,
        }
        if yoy_pct is not None:
            result['interpretation'] = f"YoY: {'+' if yoy_pct >= 0 else ''}{yoy_pct}%. Positive = expanding output."
        return result

    except Exception as e:
        return {'error': f"Error fetching industrial production: {str(e)}"}


def get_5y_treasury_yield():
    """
    Get 5-Year Treasury Constant Maturity Rate from FRED.
    Series: DGS5 (daily, percent).
    The belly of the curve — most policy-sensitive tenor.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DGS5')

        if data is None or data.empty:
            return {'error': 'No 5Y yield data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 4)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_1d = round(latest - prev, 4)

        return {
            '5y_yield': latest,
            'change_1d': change_1d,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (DGS5)',
            'units': 'Percent',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching 5Y Treasury yield: {str(e)}"}


def get_bank_reserves():
    """
    Get Reserve Balances with Federal Reserve Banks from FRED.
    Series: WRESBAL (weekly, millions of dollars, not seasonally adjusted).
    Key QT constraint — when reserves hit "ample" boundary, Fed must slow/stop QT.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('WRESBAL')

        if data is None or data.empty:
            return {'error': 'No bank reserves data from FRED'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]
        latest_trillions = round(latest / 1_000_000, 3)
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_wow_pct = round(((latest / prev) - 1) * 100, 2) if prev != 0 else 0

        return {
            'reserves_trillions': latest_trillions,
            'reserves_millions': latest,
            'change_wow_pct': change_wow_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (WRESBAL)',
            'units': 'Trillions USD',
            'historical': data,
            'interpretation': f"${latest_trillions}T in reserves. QT constraint level ~$3T.",
        }
    except Exception as e:
        return {'error': f"Error fetching bank reserves: {str(e)}"}


def get_quits_rate():
    """
    Get JOLTS Quits Rate from FRED.
    Series: JTSQUR (monthly, percent, seasonally adjusted).
    Workers quitting = labor market confidence. Fed's favorite "soft landing" signal.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('JTSQUR')

        if data is None or data.empty:
            return {'error': 'No quits rate data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 1)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change_mom = round(latest - prev, 1)

        return {
            'quits_rate': latest,
            'change_mom': change_mom,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (JTSQUR)',
            'units': 'Percent',
            'historical': data,
            'interpretation': 'Pre-COVID avg ~2.3%. Higher = workers confident in finding new jobs.',
        }
    except Exception as e:
        return {'error': f"Error fetching quits rate: {str(e)}"}


def get_headline_cpi():
    """
    Get Headline CPI (All Items) YoY% from FRED.
    Series: CPIAUCSL (monthly, index 1982-84=100, seasonally adjusted).
    Computes YoY% from index levels. Includes food and energy.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('CPIAUCSL')

        if data is None or data.empty:
            return {'error': 'No headline CPI data from FRED'}

        data = data.dropna()
        if len(data) < 13:
            return {'error': 'Insufficient CPI data for YoY calculation'}

        yoy = ((data / data.shift(12)) - 1) * 100
        yoy = yoy.dropna()
        latest = round(float(yoy.iloc[-1]), 2)
        prev = round(float(yoy.iloc[-2]), 2) if len(yoy) >= 2 else latest
        change_mom = round(latest - prev, 2)

        return {
            'headline_cpi_yoy': latest,
            'change_mom': change_mom,
            'latest_date': yoy.index[-1].strftime('%Y-%m-%d'),
            'source': 'FRED (CPIAUCSL)',
            'units': 'YoY Percent',
            'historical': yoy,
            'interpretation': f"Headline CPI includes food & energy. Fed target: 2%.",
        }
    except Exception as e:
        return {'error': f"Error fetching headline CPI: {str(e)}"}


def get_ppi():
    """
    Get Producer Price Index (Final Demand) YoY% from FRED.
    Series: PPIFIS (monthly, index Nov 2009=100, seasonally adjusted).
    Leading indicator for CPI — pipeline price pressures.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('PPIFIS')

        if data is None or data.empty:
            return {'error': 'No PPI data from FRED'}

        data = data.dropna()
        if len(data) < 13:
            return {'error': 'Insufficient PPI data for YoY calculation'}

        yoy = ((data / data.shift(12)) - 1) * 100
        yoy = yoy.dropna()
        latest = round(float(yoy.iloc[-1]), 2)
        prev = round(float(yoy.iloc[-2]), 2) if len(yoy) >= 2 else latest
        change_mom = round(latest - prev, 2)

        return {
            'ppi_yoy': latest,
            'change_mom': change_mom,
            'latest_date': yoy.index[-1].strftime('%Y-%m-%d'),
            'source': 'FRED (PPIFIS)',
            'units': 'YoY Percent',
            'historical': yoy,
            'interpretation': 'PPI leads CPI by 1-3 months. Rising PPI = margin pressure.',
        }
    except Exception as e:
        return {'error': f"Error fetching PPI: {str(e)}"}


def get_sloos_lending():
    """
    Get Senior Loan Officer Survey — Net % Tightening Standards for C&I Loans from FRED.
    Series: DRTSCILM (quarterly, net percent, not seasonally adjusted).
    Credit availability indicator — tightening standards precede recessions by 2-4 quarters.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DRTSCILM')

        if data is None or data.empty:
            return {'error': 'No SLOOS data from FRED'}

        data = data.dropna()
        latest = round(float(data.iloc[-1]), 1)
        latest_date = data.index[-1]
        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 1)

        return {
            'sloos_tightening': latest,
            'change_qoq': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'source': 'FRED (DRTSCILM)',
            'units': 'Net % Tightening',
            'historical': data,
            'interpretation': 'Positive = banks tightening. Above 40% historically precedes recession.',
            'note': 'Quarterly survey. Data may be 1-2 months delayed.',
        }
    except Exception as e:
        return {'error': f"Error fetching SLOOS lending standards: {str(e)}"}


# ──────────────────────────────────────────────────────────────────────────────
# v2.3.1 — 7 New Extractors for Financial_Agent Macro-to-Market Analysis
# ──────────────────────────────────────────────────────────────────────────────

def get_pce_headline():
    """
    Get PCE Price Index (headline) from FRED.
    Series: PCEPI (Personal Consumption Expenditures Price Index)
    Frequency: Monthly
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('PCEPI')

        if data is None or data.empty:
            return {'error': 'No PCE data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        return {
            'pce': latest,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Index (2017=100)',
            'source': 'FRED (PCEPI)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching PCE headline: {str(e)}"}


def get_30y_treasury_yield():
    """
    Get 30-Year Treasury Yield from FRED.
    Series: DGS30 (Market Yield on U.S. Treasury Securities at 30-Year Constant Maturity)
    Frequency: Daily
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DGS30')

        if data is None or data.empty:
            return {'error': 'No 30Y yield data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 4)

        return {
            'us_30y_yield': latest,
            'change_1d': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Percent',
            'source': 'FRED (DGS30)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching 30Y yield: {str(e)}"}


def get_10y3m_spread():
    """
    Get 10-Year minus 3-Month Treasury Spread from FRED.
    Series: T10Y3M
    Frequency: Daily
    Key recession indicator — inversion (negative) has preceded every recession since 1970.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('T10Y3M')

        if data is None or data.empty:
            return {'error': 'No T10Y3M data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 4)

        return {
            'spread_10y3m': latest,
            'change_1d': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Percent',
            'source': 'FRED (T10Y3M)',
            'historical': data,
            'is_inverted': latest < 0,
        }
    except Exception as e:
        return {'error': f"Error fetching 10Y-3M spread: {str(e)}"}


def get_fed_target_upper():
    """
    Get Federal Funds Target Rate (Upper Bound) from FRED.
    Series: DFEDTARU
    Frequency: Event-based (changes on FOMC decisions)
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DFEDTARU')

        if data is None or data.empty:
            return {'error': 'No DFEDTARU data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        return {
            'fed_target_upper': latest,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Percent',
            'source': 'FRED (DFEDTARU)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching Fed target rate: {str(e)}"}


def get_real_yield_5y():
    """
    Get 5-Year TIPS Real Yield from FRED.
    Series: DFII5 (5-Year Treasury Inflation-Indexed Security, Constant Maturity)
    Frequency: Daily
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('DFII5')

        if data is None or data.empty:
            return {'error': 'No 5Y TIPS data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 4)

        return {
            'real_yield_5y': latest,
            'change_1d': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Percent',
            'source': 'FRED (DFII5)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching 5Y TIPS yield: {str(e)}"}


def get_5y5y_forward_inflation():
    """
    Get 5-Year, 5-Year Forward Inflation Expectation Rate from FRED.
    Series: T5YIFR
    Frequency: Daily
    Measures market expectation of average inflation 5-10 years from now.
    Fed's preferred long-run inflation expectations gauge.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('T5YIFR')

        if data is None or data.empty:
            return {'error': 'No T5YIFR data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 4)

        return {
            'forward_inflation_5y5y': latest,
            'change_1d': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Percent',
            'source': 'FRED (T5YIFR)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching 5Y5Y forward inflation: {str(e)}"}


def get_bbb_credit_spread():
    """
    Get ICE BofA BBB US Corporate Option-Adjusted Spread from FRED.
    Series: BAMLC0A4CBBB
    Frequency: Daily
    NOTE: Values are in percentage points (e.g., 1.50 = 150 bps).
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('BAMLC0A4CBBB')

        if data is None or data.empty:
            return {'error': 'No BBB OAS data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 4)

        return {
            'bbb_oas': latest,
            'change_1d': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Percentage Points (1.50 = 150 bps)',
            'source': 'FRED (BAMLC0A4CBBB)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching BBB OAS: {str(e)}"}


# ──────────────────────────────────────────────────────────────────────────────
# Fidenza Macro Gap-Fill — Additional FRED Series
# ──────────────────────────────────────────────────────────────────────────────

def get_adp_employment():
    """
    Get ADP National Employment Report from FRED.
    Series: ADPMNUSNERSA (ADP Nonfarm Private Payroll Employment, Monthly, SA)
    Note: Previously used ADPWNUSNERSA (weekly), switched to monthly for consistency
    with the standard ADP monthly report and more timely publication.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('ADPMNUSNERSA')

        if data is None or data.empty:
            return {'error': 'No ADP employment data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 1)

        return {
            'adp_employment': latest,
            'change_mom': change,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Persons',
            'source': 'FRED (ADPMNUSNERSA)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching ADP employment: {str(e)}"}


def get_fed_balance_sheet():
    """
    Get Federal Reserve Total Assets (WALCL) from FRED.
    Series: WALCL (All Federal Reserve Banks: Total Assets)
    Frequency: Weekly, millions of USD.
    Distinct from net liquidity — this is the raw balance sheet size.
    """
    try:
        fred = get_fred_client()
        data = fred.get_series('WALCL')

        if data is None or data.empty:
            return {'error': 'No Fed balance sheet data available'}

        data = data.dropna()
        latest = float(data.iloc[-1])
        latest_date = data.index[-1]

        prev = float(data.iloc[-2]) if len(data) >= 2 else latest
        change = round(latest - prev, 0)
        change_pct = round((change / abs(prev)) * 100, 2) if prev != 0 else 0

        return {
            'fed_balance_sheet': latest,
            'fed_balance_sheet_trillions': round(latest / 1_000_000, 3),
            'change_wow': change,
            'change_wow_pct': change_pct,
            'latest_date': latest_date.strftime('%Y-%m-%d'),
            'units': 'Millions USD',
            'source': 'FRED (WALCL)',
            'historical': data,
        }
    except Exception as e:
        return {'error': f"Error fetching Fed balance sheet: {str(e)}"}


def get_treasury_term_premia():
    """
    Get Treasury Term Premia from FRED (NY Fed ACM model).
    Primary: THREEFYTP10 (10-Year Treasury Term Premium)
    Fallback: ACMTP10
    Also: ACMTP05 (5-Year) if available
    Frequency: Daily
    """
    try:
        fred = get_fred_client()
        result = {'source': 'FRED (NY Fed ACM)', 'units': 'Percent'}

        # 10Y term premium (try multiple series IDs)
        for series_id in ['THREEFYTP10', 'ACMTP10']:
            try:
                data = fred.get_series(series_id)
                if data is not None and not data.empty:
                    data = data.dropna()
                    if data.empty:
                        continue
                    latest = float(data.iloc[-1])
                    latest_date = data.index[-1]
                    prev = float(data.iloc[-2]) if len(data) >= 2 else latest
                    result['term_premium_10y'] = latest
                    result['change_1d'] = round(latest - prev, 4)
                    result['latest_date'] = latest_date.strftime('%Y-%m-%d')
                    result['historical'] = data
                    result['series_id'] = series_id
                    break
            except Exception:
                continue

        # 5Y term premium (secondary, optional)
        for series_id_5y in ['ACMTP05', 'THREEFYTP05']:
            try:
                data_5y = fred.get_series(series_id_5y)
                if data_5y is not None and not data_5y.empty:
                    data_5y = data_5y.dropna()
                    if not data_5y.empty:
                        result['term_premium_5y'] = float(data_5y.iloc[-1])
                        result['historical_5y'] = data_5y
                        break
            except Exception:
                continue

        if 'term_premium_10y' not in result:
            return {'error': 'No term premia data available from FRED'}

        return result
    except Exception as e:
        return {'error': f"Error fetching treasury term premia: {str(e)}"}
