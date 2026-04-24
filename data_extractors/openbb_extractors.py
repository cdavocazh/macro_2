"""
Data extractors using OpenBB Platform for market data.

OpenBB is an optional dependency. Every function has a fallback path that uses
yfinance, FRED, or direct API calls when OpenBB is not installed.

High-value extractors (#1-#10):
  - VIX futures curve (CBOE) — fixes broken VX=F
  - SPY put/call OI (CBOE) — fixes broken put/call ratio
  - S&P 500 multiples (Finviz) — fixes broken Forward P/E scrape
  - ECB policy rates, OECD CLI, CPI components
  - Fama-French factors, IV skew, European yields, global CPI

Medium-value extractors (#11-#20):
  - Earnings calendar, sector P/E, treasury curve, corporate spreads
  - International unemployment/GDP, equity screener, money measures
  - Global PMI, equity risk premium
"""

import pandas as pd
from datetime import datetime, timedelta

try:
    from openbb import obb
    OPENBB_AVAILABLE = True
except ImportError:
    OPENBB_AVAILABLE = False
    # OpenBB is optional - fallback methods will be used automatically


# ══════════════════════════════════════════════════════════════════════════════
# Existing functions (kept for backward compatibility)
# ══════════════════════════════════════════════════════════════════════════════

def get_sp500_fundamentals():
    """
    Get S&P 500 trailing P/E and P/B ratios using OpenBB.
    Falls back to yfinance if OpenBB is not available.
    Returns: dict with P/E and P/B ratios
    """
    if not OPENBB_AVAILABLE:
        return get_sp500_fundamentals_fallback()

    try:
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

    except Exception:
        return get_sp500_fundamentals_fallback()


def get_sp500_fundamentals_fallback():
    """
    Fallback: S&P 500 P/E and P/B using yfinance directly (SPY ETF proxy).
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

        return {'error': 'Could not get S&P 500 fundamentals from any source'}
    except Exception as e:
        return {'error': f"Error in fallback fundamentals method: {str(e)}"}


def get_sp500_fundamentals_historical():
    """
    Expanded S&P 500 fundamental metrics using SPY ETF as proxy.
    Includes: trailing P/E, forward P/E, earnings yield, dividend yield, P/B.
    Returns latest snapshot + 2-year SPY price history.
    """
    try:
        import yfinance as yf

        spy = yf.Ticker("SPY")
        info = spy.info

        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')
        pb_ratio = info.get('priceToBook')
        dividend_yield = info.get('trailingAnnualDividendYield') or info.get('dividendYield')
        trailing_eps = info.get('trailingEps')
        forward_eps = info.get('forwardEps')
        current_price = info.get('previousClose') or info.get('regularMarketPrice')

        earnings_yield = None
        if trailing_pe and trailing_pe > 0:
            earnings_yield = round(1.0 / trailing_pe * 100, 2)

        forward_earnings_yield = None
        if forward_pe and forward_pe > 0:
            forward_earnings_yield = round(1.0 / forward_pe * 100, 2)

        hist = spy.history(period='2y')
        historical_close = None
        if not hist.empty:
            historical_close = hist['Close']

        result = {
            'sp500_pe_trailing': trailing_pe,
            'sp500_pe_forward': forward_pe,
            'sp500_pb': pb_ratio,
            'earnings_yield': earnings_yield,
            'forward_earnings_yield': forward_earnings_yield,
            'dividend_yield_pct': round(dividend_yield * 100, 2) if dividend_yield and dividend_yield < 1 else round(dividend_yield, 2) if dividend_yield else None,
            'trailing_eps': trailing_eps,
            'forward_eps': forward_eps,
            'spy_price': current_price,
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'yfinance (SPY ETF)',
        }

        if historical_close is not None:
            result['historical'] = historical_close

        return result

    except Exception as e:
        return {'error': f"Error fetching expanded S&P 500 fundamentals: {str(e)}"}


def get_russell_2000_via_openbb():
    """
    Alternative method to get Russell 2000 indices via OpenBB.
    Returns: dict with Russell 2000 Value and Growth data
    """
    if not OPENBB_AVAILABLE:
        return {'error': 'OpenBB not available'}

    try:
        value_data = obb.equity.price.historical(symbol="IWN", provider="yfinance", start_date="2023-01-01")
        growth_data = obb.equity.price.historical(symbol="IWO", provider="yfinance", start_date="2023-01-01")

        result = {}
        if value_data and hasattr(value_data, 'results') and value_data.results:
            latest_value = value_data.results[-1]
            result['russell_2000_value'] = {'price': latest_value.close, 'date': str(latest_value.date)}
        if growth_data and hasattr(growth_data, 'results') and growth_data.results:
            latest_growth = growth_data.results[-1]
            result['russell_2000_growth'] = {'price': latest_growth.close, 'date': str(latest_growth.date)}

        return result if result else {'error': 'No data returned from OpenBB'}
    except Exception as e:
        return {'error': f"Error fetching Russell 2000 via OpenBB: {str(e)}"}


# ══════════════════════════════════════════════════════════════════════════════
# HIGH-VALUE EXTRACTORS (#1–#10)
# ══════════════════════════════════════════════════════════════════════════════

# ── #1: VIX Futures Curve (CBOE) ─────────────────────────────────────────────

def get_vix_futures_curve():
    """
    VIX futures term structure from CBOE provider.
    Fixes known-broken VX=F yfinance ticker.

    Returns: dict with front/back month prices, contango ratio, historical VIX spot.
    Fallback: uses ^VIX spot only (no futures curve).
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.derivatives.options.chains(symbol="VIX", provider="cboe")
            if data and hasattr(data, 'results') and data.results:
                df = pd.DataFrame([vars(r) for r in data.results]) if not isinstance(data.results, pd.DataFrame) else data.results
                if hasattr(data, 'to_df'):
                    df = data.to_df()

                # Extract VIX futures from options chain expirations
                if 'expiration' in df.columns and 'underlying_price' in df.columns:
                    vix_spot = float(df['underlying_price'].iloc[0])
                    expirations = sorted(df['expiration'].unique())

                    # Build term structure from implied forward prices
                    futures_curve = {}
                    for i, exp in enumerate(expirations[:6]):
                        exp_df = df[df['expiration'] == exp]
                        # ATM implied vol as proxy for futures level
                        atm = exp_df.iloc[(exp_df['strike'] - vix_spot).abs().argsort()[:1]]
                        if not atm.empty:
                            mid = None
                            if 'bid' in atm.columns and 'ask' in atm.columns:
                                bid = float(atm['bid'].iloc[0] or 0)
                                ask = float(atm['ask'].iloc[0] or 0)
                                if bid > 0 and ask > 0:
                                    mid = (bid + ask) / 2
                            futures_curve[str(exp)] = mid

                    contango = None
                    curve_vals = [v for v in futures_curve.values() if v is not None]
                    if len(curve_vals) >= 2:
                        contango = round((curve_vals[1] / curve_vals[0] - 1) * 100, 2) if curve_vals[0] > 0 else None

                    return {
                        'vix_spot': vix_spot,
                        'futures_curve': futures_curve,
                        'contango_pct': contango,
                        'n_expirations': len(expirations),
                        'latest_date': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'OpenBB/CBOE'
                    }
        except Exception:
            pass  # Fall through to fallback

    return _vix_futures_curve_fallback()


def _vix_futures_curve_fallback():
    """Fallback: VIX spot + existing term structure from yfinance_extractors."""
    try:
        import yfinance as yf

        vix = yf.Ticker("^VIX")
        hist = vix.history(period='5y')
        if hist.empty:
            return {'error': 'No VIX data available'}

        close = hist['Close']
        latest = float(close.iloc[-1])
        change_1d = 0.0
        if len(close) > 1:
            prev = float(close.iloc[-2])
            if prev != 0:
                change_1d = round(((latest / prev) - 1) * 100, 2)

        return {
            'vix_spot': round(latest, 2),
            'futures_curve': None,
            'contango_pct': None,
            'n_expirations': 0,
            'change_1d': change_1d,
            'latest_date': close.index[-1].strftime('%Y-%m-%d'),
            'historical': close,
            'source': 'yfinance (^VIX spot only, no futures)',
            'note': 'VIX futures unavailable — install openbb for CBOE futures curve'
        }
    except Exception as e:
        return {'error': f'Error fetching VIX fallback: {str(e)}'}


# ── #2: SPY Put/Call Open Interest (CBOE) ────────────────────────────────────

def get_spy_put_call_oi():
    """
    SPY put/call ratio from CBOE options chains.
    Fixes known-broken yfinance ^PCPUT/^PCALL tickers.

    Returns: dict with put/call volume ratio, OI ratio, total volume.
    Fallback: FRED PCERTOT series or SPY options via yfinance.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.derivatives.options.chains(symbol="SPY", provider="cboe")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])

                if 'option_type' in df.columns:
                    calls = df[df['option_type'].str.lower() == 'call']
                    puts = df[df['option_type'].str.lower() == 'put']
                elif 'contract_type' in df.columns:
                    calls = df[df['contract_type'].str.lower() == 'call']
                    puts = df[df['contract_type'].str.lower() == 'put']
                else:
                    return _spy_put_call_fallback()

                call_vol = calls['volume'].sum() if 'volume' in calls.columns else 0
                put_vol = puts['volume'].sum() if 'volume' in puts.columns else 0
                call_oi = calls['open_interest'].sum() if 'open_interest' in calls.columns else 0
                put_oi = puts['open_interest'].sum() if 'open_interest' in puts.columns else 0

                vol_ratio = round(put_vol / call_vol, 3) if call_vol > 0 else None
                oi_ratio = round(put_oi / call_oi, 3) if call_oi > 0 else None

                return {
                    'put_call_volume_ratio': vol_ratio,
                    'put_call_oi_ratio': oi_ratio,
                    'total_call_volume': int(call_vol),
                    'total_put_volume': int(put_vol),
                    'total_call_oi': int(call_oi),
                    'total_put_oi': int(put_oi),
                    'latest_date': datetime.now().strftime('%Y-%m-%d'),
                    'source': 'OpenBB/CBOE'
                }
        except Exception:
            pass

    return _spy_put_call_fallback()


def _spy_put_call_fallback():
    """Fallback: FRED equity put/call ratio, then yfinance SPY options."""
    # Try FRED first
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)
        series = fred.get_series('PCERTOT')
        if series is not None and not series.empty:
            latest = float(series.iloc[-1])
            return {
                'put_call_volume_ratio': round(latest, 3),
                'put_call_oi_ratio': None,
                'total_call_volume': None,
                'total_put_volume': None,
                'total_call_oi': None,
                'total_put_oi': None,
                'latest_date': series.index[-1].strftime('%Y-%m-%d'),
                'historical': series,
                'source': 'FRED (PCERTOT equity put/call)',
                'note': 'OI breakdown unavailable — install openbb for CBOE chains'
            }
    except Exception:
        pass

    # yfinance SPY options fallback
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY")
        expirations = spy.options
        if not expirations:
            return {'error': 'No SPY options data available from any source'}

        # Use nearest expiration
        chain = spy.option_chain(expirations[0])
        call_vol = chain.calls['volume'].sum() if 'volume' in chain.calls.columns else 0
        put_vol = chain.puts['volume'].sum() if 'volume' in chain.puts.columns else 0
        call_oi = chain.calls['openInterest'].sum() if 'openInterest' in chain.calls.columns else 0
        put_oi = chain.puts['openInterest'].sum() if 'openInterest' in chain.puts.columns else 0

        vol_ratio = round(put_vol / call_vol, 3) if call_vol > 0 else None
        oi_ratio = round(put_oi / call_oi, 3) if call_oi > 0 else None

        return {
            'put_call_volume_ratio': vol_ratio,
            'put_call_oi_ratio': oi_ratio,
            'total_call_volume': int(call_vol),
            'total_put_volume': int(put_vol),
            'total_call_oi': int(call_oi),
            'total_put_oi': int(put_oi),
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': f'yfinance SPY options ({expirations[0]})',
            'note': 'Single expiry only — install openbb for full CBOE chains'
        }
    except Exception as e:
        return {'error': f'Put/call ratio unavailable from all sources: {str(e)}'}


# ── #3: S&P 500 Historical Multiples (Finviz) ───────────────────────────────

def get_sp500_historical_multiples():
    """
    S&P 500 valuation multiples via OpenBB/Finviz (Top 20 market-cap weighted).
    Fixes known-broken Forward P/E (MacroMicro 403).

    Source cascade: OpenBB/Finviz (per-stock) → multpl.com (index) → yfinance (SPY ETF).
    Returns: forward P/E, PEG, price/sales, price/cash, price/book, EPS growth.
    """
    if OPENBB_AVAILABLE:
        try:
            return _sp500_multiples_openbb()
        except Exception:
            pass

    return _sp500_multiples_fallback()


def _sp500_multiples_openbb():
    """Primary: OpenBB/Finviz per-stock metrics for Top 20, market-cap weighted.

    Uses obb.equity.fundamental.metrics (Finviz) for core valuation ratios,
    plus direct Finviz page scrape for PEG and EPS growth (not in OpenBB API).
    """
    import time
    import requests
    from bs4 import BeautifulSoup
    import re

    TOP_20 = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'BRK-B', 'TSM',
              'LLY', 'AVGO', 'JPM', 'V', 'WMT', 'MA', 'XOM', 'UNH', 'COST', 'HD', 'PG', 'JNJ']

    def _scrape_finviz_extra(ticker):
        """Scrape PEG and EPS growth from Finviz quote page (not in OpenBB API)."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            resp = requests.get(f'https://finviz.com/quote.ashx?t={ticker}', headers=headers, timeout=8)
            if resp.status_code != 200:
                return {}
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table', class_='snapshot-table2')
            if not table:
                return {}
            extra = {}
            for row in table.find_all('tr'):
                cells = row.find_all('td')
                for i in range(0, len(cells) - 1, 2):
                    label = cells[i].get_text(strip=True)
                    value = cells[i + 1].get_text(strip=True)
                    if label == 'PEG':
                        try:
                            extra['peg'] = float(value)
                        except ValueError:
                            pass
                    elif label == 'EPS next 5Y':
                        m = re.match(r'([\d.]+)%', value)
                        if m:
                            extra['eps_growth_next_5y'] = float(m.group(1))
                    elif label == 'EPS past 5Y':
                        # Format: "6.89% 17.91%" (3Y and 5Y)
                        parts = value.split()
                        for p in reversed(parts):
                            m = re.match(r'([\d.]+)%', p)
                            if m:
                                extra['eps_growth_past_5y'] = float(m.group(1))
                                break
            return extra
        except Exception:
            return {}

    stocks = {}
    for ticker in TOP_20:
        try:
            data = obb.equity.fundamental.metrics(symbol=ticker, provider="finviz")
            if data and hasattr(data, 'results') and data.results:
                r = data.results[0] if isinstance(data.results, list) else data.results
                mcap = getattr(r, 'market_cap', None)
                if mcap and mcap > 0:
                    stocks[ticker] = {
                        'forward_pe': getattr(r, 'forward_pe', None),
                        'pe_ratio': getattr(r, 'pe_ratio', None),
                        'price_to_sales': getattr(r, 'price_to_sales', None),
                        'price_to_book': getattr(r, 'price_to_book', None),
                        'price_to_cash': getattr(r, 'price_to_cash', None),
                        'price_to_fcf': getattr(r, 'price_to_free_cash_flow', None),
                        'market_cap': mcap,
                    }
                    # Supplement with PEG + EPS growth from Finviz page scrape
                    extra = _scrape_finviz_extra(ticker)
                    stocks[ticker].update(extra)
            time.sleep(0.15)  # Rate limit for Finviz
        except Exception:
            continue

    if len(stocks) < 5:
        raise ValueError(f"Only got {len(stocks)} stocks from Finviz, need at least 5")

    # Compute market-cap weighted averages
    total_mcap = sum(s['market_cap'] for s in stocks.values())
    metrics = ['forward_pe', 'pe_ratio', 'peg', 'price_to_sales', 'price_to_book', 'price_to_cash']
    weighted = {}
    for m in metrics:
        w_sum = 0
        w_mcap = 0
        for s in stocks.values():
            val = s.get(m)
            mcap = s['market_cap']
            if val is not None and val > 0:
                w_sum += val * mcap
                w_mcap += mcap
        weighted[m] = round(w_sum / w_mcap, 2) if w_mcap > 0 else None

    # EPS growth (simple average of available)
    eps_next5 = [s.get('eps_growth_next_5y') for s in stocks.values() if s.get('eps_growth_next_5y') is not None]
    eps_past5 = [s.get('eps_growth_past_5y') for s in stocks.values() if s.get('eps_growth_past_5y') is not None]

    return {
        'forward_pe': weighted.get('forward_pe'),
        'trailing_pe': weighted.get('pe_ratio'),
        'peg_ratio': weighted.get('peg'),
        'price_to_sales': weighted.get('price_to_sales'),
        'price_to_book': weighted.get('price_to_book'),
        'price_to_cash': weighted.get('price_to_cash'),
        'eps_growth_next_5y': round(sum(eps_next5) / len(eps_next5), 2) if eps_next5 else None,
        'eps_growth_past_5y': round(sum(eps_past5) / len(eps_past5), 2) if eps_past5 else None,
        'latest_date': datetime.now().strftime('%Y-%m-%d'),
        'source': f'OpenBB/Finviz (Top {len(stocks)} mcap-weighted, ${total_mcap/1e12:.1f}T)',
        'stock_count': len(stocks),
    }


def _sp500_multiples_fallback():
    """Fallback: scrape multpl.com for S&P 500 valuation multiples, then yfinance."""
    import re

    def _scrape_multpl(url_path):
        """Scrape a single value from multpl.com."""
        try:
            import requests
            from bs4 import BeautifulSoup
            headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
            resp = requests.get(f'https://www.multpl.com/{url_path}', headers=headers, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                current = soup.find('div', id='current')
                if current:
                    text = current.get_text(strip=True)
                    match = re.search(r'(?:Ratio|Value|Yield)[:\s]*(\d+\.?\d*)', text)
                    if match:
                        return float(match.group(1))
        except Exception:
            pass
        return None

    # Try multpl.com first (S&P 500 index-level multiples)
    trailing_pe = _scrape_multpl('s-p-500-pe-ratio')
    price_to_sales = _scrape_multpl('s-p-500-price-to-sales')
    price_to_book = _scrape_multpl('s-p-500-price-to-book')
    earnings_yield = _scrape_multpl('s-p-500-earnings-yield')

    # Compute forward P/E from earnings yield if available, else from yfinance
    forward_pe = None
    if earnings_yield and earnings_yield > 0:
        forward_pe = round(100.0 / earnings_yield, 2)

    if trailing_pe is not None:
        return {
            'forward_pe': forward_pe,
            'peg_ratio': None,
            'price_to_sales': price_to_sales,
            'price_to_cash': None,
            'price_to_book': price_to_book,
            'eps_growth_next_y': None,
            'eps_growth_past_5y': None,
            'trailing_pe': trailing_pe,
            'earnings_yield': earnings_yield,
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'multpl.com (S&P 500 index)',
            'note': 'PEG and Price/Cash unavailable from multpl.com'
        }

    # Final fallback: yfinance SPY ETF
    try:
        import yfinance as yf
        spy = yf.Ticker("SPY")
        info = spy.info
        return {
            'forward_pe': info.get('forwardPE'),
            'peg_ratio': info.get('pegRatio'),
            'price_to_sales': info.get('priceToSalesTrailing12Months'),
            'price_to_cash': info.get('priceToFreeCashflow') or info.get('priceToCashflow'),
            'eps_growth_next_y': None,
            'eps_growth_past_5y': None,
            'trailing_pe': info.get('trailingPE'),
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'yfinance (SPY ETF)',
            'note': 'Limited metrics for ETFs'
        }
    except Exception as e:
        return {'error': f'S&P 500 multiples unavailable: {str(e)}'}


# ── #4: ECB Policy Rates ─────────────────────────────────────────────────────

def get_ecb_policy_rates():
    """
    ECB deposit facility, main refinancing, and marginal lending rates.
    Returns: dict with current rates + historical series.
    Fallback: direct ECB SDW API.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.fixedincome.rate.ecb(provider="ecb")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty:
                    latest = df.iloc[-1]
                    result = {
                        'deposit_rate': float(latest.get('deposit_facility', latest.iloc[1])) if len(latest) > 1 else None,
                        'refi_rate': float(latest.get('main_refinancing', latest.iloc[2])) if len(latest) > 2 else None,
                        'marginal_rate': float(latest.get('marginal_lending', latest.iloc[3])) if len(latest) > 3 else None,
                        'latest_date': str(latest.name) if hasattr(latest, 'name') else datetime.now().strftime('%Y-%m-%d'),
                        'source': 'OpenBB/ECB'
                    }
                    if 'deposit_facility' in df.columns:
                        result['historical'] = df['deposit_facility']
                    return result
        except Exception:
            pass

    return _ecb_rates_fallback()


def _ecb_rates_fallback():
    """Fallback: ECB Statistical Data Warehouse API."""
    try:
        import requests
        # ECB SDW REST API for deposit facility rate
        url = "https://data-api.ecb.europa.eu/service/data/FM/D.U2.EUR.4F.KR.DFR.LEV"
        headers = {'Accept': 'application/json'}
        resp = requests.get(url, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            obs = data.get('dataSets', [{}])[0].get('series', {}).get('0:0:0:0:0:0:0', {}).get('observations', {})
            time_periods = data.get('structure', {}).get('dimensions', {}).get('observation', [{}])[0].get('values', [])

            if obs and time_periods:
                dates = []
                values = []
                for idx, tp in enumerate(time_periods):
                    if str(idx) in obs:
                        dates.append(tp['id'])
                        values.append(float(obs[str(idx)][0]))

                if values:
                    series = pd.Series(values, index=pd.to_datetime(dates))
                    return {
                        'deposit_rate': values[-1],
                        'refi_rate': None,
                        'marginal_rate': None,
                        'latest_date': dates[-1],
                        'historical': series,
                        'source': 'ECB SDW API (deposit rate only)',
                        'note': 'Refi/marginal rates unavailable — install openbb for full ECB data'
                    }

        return {'error': 'ECB rates unavailable from all sources'}
    except Exception as e:
        return {'error': f'ECB rates fetch error: {str(e)}'}


# ── #5: OECD Composite Leading Indicator ─────────────────────────────────────

def get_oecd_leading_indicator():
    """
    OECD Composite Leading Indicator (CLI) for the US.
    Forward-looking macro indicator (6-9 month lead on GDP).
    Returns: dict with latest CLI value + historical.
    Fallback: FRED USALOLITONOSTSAM series.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.economy.composite_leading_indicator(country="united_states", provider="oecd")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty:
                    val_col = [c for c in df.columns if c not in ('date',)]
                    if val_col:
                        series = df.set_index('date')[val_col[0]] if 'date' in df.columns else df[val_col[0]]
                        latest = float(series.iloc[-1])
                        return {
                            'cli_value': round(latest, 2),
                            'above_100': latest > 100,
                            'latest_date': str(series.index[-1])[:10],
                            'historical': series,
                            'source': 'OpenBB/OECD'
                        }
        except Exception:
            pass

    return _oecd_cli_fallback()


def _oecd_cli_fallback():
    """Fallback for OECD CLI.

    Tries in order:
      1. Direct OECD SDMX-JSON API — new STES dataset (9-dimension key with wildcards).
         URL: OECD.SDD.STES,DSD_STES@DF_CLI / USA.M.LI.AA.AA...
         Note: stats.oecd.org (legacy) redirects here; old DSD_CLI@DF_CLI endpoint → 404.
         VPS note: Hostinger datacenter IPs can get throttled by OECD — expect 5-30s response.
      2. FRED USALOLITONOSTSAM (froze Jan 2024 — OECD stopped pushing to FRED when they
         migrated to SDMX 3.0 in 2023-2024; still useful for historical baseline).
      3. CFNAI (Chicago Fed National Activity Index, FRED:CFNAI) — updated monthly through
         the current period. Different scale (centered at 0, not 100) but same macro purpose:
         leading indicator of US economic activity. Above 0 = above-trend growth.
    """
    # ── 1. Direct OECD SDMX 3.0 REST API (STES dataset, 9-dim key) ──────────
    try:
        # The new STES DF_CLI dataset requires 9 dimensions; trailing wildcards fill unknowns.
        # USA.M.LI.AA.AA... → USA + Monthly + Leading Indicator + Amplitude Adjusted + AA + 3 wildcards
        for url in [
            # Primary: STES dataset (correct post-2024 location)
            ('https://sdmx.oecd.org/public/rest/data/'
             'OECD.SDD.STES,DSD_STES@DF_CLI/'
             'USA.M.LI.AA.AA...'
             '?startPeriod=2020-01&format=jsondata'),
            # Fallback URL: older NAD/DSD_CLI dataset still served by some mirrors
            ('https://sdmx.oecd.org/public/rest/data/'
             'OECD.SDD.NAD,DSD_CLI@DF_CLI,1.0/'
             'USA.M.LI.AA.AA.A'
             '?startPeriod=2020-01&format=jsondata'),
        ]:
            try:
                resp = requests.get(url, timeout=30, headers={'Accept': 'application/json'})
                if resp.status_code == 200:
                    payload = resp.json()
                    ds = payload.get('dataSets', [{}])[0]
                    series_dict = ds.get('series', {})
                    if series_dict:
                        obs = list(series_dict.values())[0].get('observations', {})
                        time_periods = payload['structure']['dimensions']['observation'][0]['values']
                        dates, values = [], []
                        for idx, tp in enumerate(time_periods):
                            key = str(idx)
                            if key in obs:
                                val = obs[key][0]
                                if val is not None:
                                    try:
                                        dates.append(pd.to_datetime(tp['id']))
                                        values.append(float(val))
                                    except (ValueError, TypeError):
                                        pass
                        if dates:
                            series = pd.Series(values, index=dates).sort_index()
                            latest = float(series.iloc[-1])
                            return {
                                'cli_value': round(latest, 2),
                                'above_100': latest > 100,
                                'latest_date': series.index[-1].strftime('%Y-%m-%d'),
                                'historical': series,
                                'source': 'OECD SDMX API'
                            }
            except Exception:
                continue
    except Exception:
        pass

    # ── 2. FRED USALOLITONOSTSAM (frozen Jan 2024) ────────────────────────────
    # Root cause: OECD stopped pushing MEI data to FRED when they migrated to SDMX 3.0.
    # Only use if data is reasonably fresh (< 400 days) — if stale, fall through to CFNAI.
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)
        series = fred.get_series('USALOLITONOSTSAM').dropna()
        if series is not None and not series.empty:
            age_days = (pd.Timestamp.now() - series.index[-1]).days
            if age_days < 400:   # only trust if updated within ~13 months
                latest = float(series.iloc[-1])
                return {
                    'cli_value': round(latest, 2),
                    'above_100': latest > 100,
                    'latest_date': series.index[-1].strftime('%Y-%m-%d'),
                    'historical': series,
                    'source': 'FRED (USALOLITONOSTSAM)'
                }
            # else: stale (frozen Jan 2024) — fall through to CFNAI proxy
    except Exception:
        pass

    # ── 3. CFNAI proxy (Chicago Fed National Activity Index) ─────────────────
    # CFNAI is updated monthly (~4-5 weeks lag), released by Chicago Fed.
    # Scale: centered at 0 (not 100). Above 0 = above-trend growth; below -0.7 during
    # contraction signals high recession probability. Used here when OECD CLI unavailable.
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)
        series = fred.get_series('CFNAI').dropna()
        if series is not None and not series.empty:
            latest = float(series.iloc[-1])
            # Normalise to OECD CLI-like scale: CFNAI 0 → 100, ±1 → ±10
            # This keeps the dashboard display compatible (above_100 = expansion signal)
            cli_equiv = round(100 + (latest * 10), 2)
            return {
                'cli_value': cli_equiv,
                'cfnai_raw': round(latest, 3),
                'above_100': latest > 0,
                'latest_date': series.index[-1].strftime('%Y-%m-%d'),
                'historical': (series * 10 + 100),    # rescaled to CLI-like units
                'historical_raw': series,
                'source': 'FRED CFNAI (Chicago Fed — OECD CLI unavailable)'
            }
        return {'error': 'OECD CLI unavailable — all sources exhausted'}
    except Exception as e:
        return {'error': f'OECD CLI fetch error: {str(e)}'}


# ── #6: CPI Components Breakdown ─────────────────────────────────────────────

def get_cpi_components():
    """
    CPI breakdown by major category: food, energy, shelter, core.
    Returns: dict with component YoY% changes.
    Fallback: FRED series for each CPI component.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.economy.cpi(country="united_states", provider="fred")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty:
                    latest = df.iloc[-1]
                    return {
                        'headline_cpi': float(latest.get('value', 0)),
                        'latest_date': str(latest.name)[:10] if hasattr(latest, 'name') else datetime.now().strftime('%Y-%m-%d'),
                        'source': 'OpenBB/FRED'
                    }
        except Exception:
            pass

    return _cpi_components_fallback()


def _cpi_components_fallback():
    """Fallback: FRED series for CPI components."""
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        # CPI component FRED series IDs (YoY % change)
        components = {
            'headline_cpi': 'CPIAUCSL',       # All items
            'core_cpi': 'CPILFESL',           # Less food and energy
            'food_cpi': 'CPIUFDSL',           # Food
            'energy_cpi': 'CPIENGSL',         # Energy
            'shelter_cpi': 'CUSR0000SAH1',    # Shelter
        }

        result = {'latest_date': None, 'source': 'FRED (CPI components)'}

        for key, series_id in components.items():
            try:
                s = fred.get_series(series_id)
                if s is not None and not s.empty and len(s) >= 13:
                    # Compute YoY % change
                    latest = float(s.iloc[-1])
                    year_ago = float(s.iloc[-13])  # ~12 months back
                    yoy = round(((latest / year_ago) - 1) * 100, 2) if year_ago != 0 else None
                    result[f'{key}_yoy'] = yoy
                    result[f'{key}_level'] = round(latest, 1)
                    if result['latest_date'] is None:
                        result['latest_date'] = s.index[-1].strftime('%Y-%m-%d')
                    # Store historical for headline
                    if key == 'headline_cpi':
                        # Build YoY series
                        yoy_series = s.pct_change(periods=12) * 100
                        result['historical'] = yoy_series.dropna()
            except Exception:
                result[f'{key}_yoy'] = None

        if result['latest_date'] is None:
            return {'error': 'CPI components unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'CPI components fetch error: {str(e)}'}


# ── #7: Fama-French 5-Factor Returns ─────────────────────────────────────────

def get_fama_french_factors():
    """
    Fama-French 5-factor model returns: Mkt-RF, SMB, HML, RMW, CMA + RF.
    Returns: dict with latest monthly returns + historical DataFrame.
    Fallback: download directly from Ken French's data library.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.equity.discovery.fama_french()
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty:
                    latest = df.iloc[-1]
                    return {
                        'mkt_rf': float(latest.get('mkt_rf', 0)),
                        'smb': float(latest.get('smb', 0)),
                        'hml': float(latest.get('hml', 0)),
                        'rmw': float(latest.get('rmw', 0)),
                        'cma': float(latest.get('cma', 0)),
                        'rf': float(latest.get('rf', 0)),
                        'latest_date': str(latest.name)[:10] if hasattr(latest, 'name') else str(df.index[-1])[:10],
                        'historical': df,
                        'source': 'OpenBB/Fama-French'
                    }
        except Exception:
            pass

    return _fama_french_fallback()


def _fama_french_fallback():
    """Fallback: download Fama-French 5 factors from Ken French's data library."""
    try:
        import io
        import zipfile
        import requests

        url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            return {'error': f'Fama-French download failed: HTTP {resp.status_code}'}

        z = zipfile.ZipFile(io.BytesIO(resp.content))
        csv_name = z.namelist()[0]
        raw = z.read(csv_name).decode('utf-8')

        # Parse CSV: skip header rows, find monthly data section
        lines = raw.strip().split('\n')
        data_start = None
        data_end = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and stripped[0].isdigit() and len(stripped.split(',')[0].strip()) == 6:
                if data_start is None:
                    data_start = i
                data_end = i
            elif data_start is not None and (not stripped or not stripped[0].isdigit()):
                break

        if data_start is None:
            return {'error': 'Could not parse Fama-French CSV'}

        rows = []
        for line in lines[data_start:data_end + 1]:
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 6 and parts[0].isdigit():
                date_str = parts[0]
                try:
                    dt = datetime.strptime(date_str, '%Y%m')
                    rows.append({
                        'date': dt,
                        'mkt_rf': float(parts[1]),
                        'smb': float(parts[2]),
                        'hml': float(parts[3]),
                        'rmw': float(parts[4]),
                        'cma': float(parts[5]),
                        'rf': float(parts[6]) if len(parts) > 6 else 0.0,
                    })
                except (ValueError, IndexError):
                    continue

        if not rows:
            return {'error': 'No valid Fama-French data rows parsed'}

        df = pd.DataFrame(rows).set_index('date')
        latest = df.iloc[-1]

        return {
            'mkt_rf': float(latest['mkt_rf']),
            'smb': float(latest['smb']),
            'hml': float(latest['hml']),
            'rmw': float(latest['rmw']),
            'cma': float(latest['cma']),
            'rf': float(latest['rf']),
            'latest_date': latest.name.strftime('%Y-%m-%d'),
            'historical': df,
            'source': 'Ken French Data Library (direct download)'
        }
    except Exception as e:
        return {'error': f'Fama-French factors fetch error: {str(e)}'}


# ── #8: SPX Implied Volatility Skew ──────────────────────────────────────────

def get_spx_iv_skew():
    """
    SPX options implied volatility skew (25-delta put vs call spread).
    Returns: dict with IV skew metrics.
    Fallback: CBOE SKEW index via yfinance (^SKEW).
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.derivatives.options.chains(symbol="SPX", provider="cboe")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])

                if 'implied_volatility' in df.columns and len(df) > 0:
                    # Get nearest expiry
                    if 'expiration' in df.columns:
                        nearest_exp = sorted(df['expiration'].unique())[0]
                        df = df[df['expiration'] == nearest_exp]

                    underlying = df['underlying_price'].iloc[0] if 'underlying_price' in df.columns else None

                    if underlying:
                        # 25-delta approximation: ~5% OTM
                        otm_put_strike = underlying * 0.95
                        otm_call_strike = underlying * 1.05

                        type_col = 'option_type' if 'option_type' in df.columns else 'contract_type'
                        puts = df[df[type_col].str.lower() == 'put']
                        calls = df[df[type_col].str.lower() == 'call']

                        put_iv = None
                        call_iv = None
                        if not puts.empty:
                            nearest_put = puts.iloc[(puts['strike'] - otm_put_strike).abs().argsort()[:1]]
                            put_iv = float(nearest_put['implied_volatility'].iloc[0])
                        if not calls.empty:
                            nearest_call = calls.iloc[(calls['strike'] - otm_call_strike).abs().argsort()[:1]]
                            call_iv = float(nearest_call['implied_volatility'].iloc[0])

                        skew = round((put_iv - call_iv) * 100, 2) if put_iv and call_iv else None

                        return {
                            'iv_skew_25d': skew,
                            'otm_put_iv': round(put_iv * 100, 2) if put_iv else None,
                            'otm_call_iv': round(call_iv * 100, 2) if call_iv else None,
                            'atm_iv': None,
                            'latest_date': datetime.now().strftime('%Y-%m-%d'),
                            'source': 'OpenBB/CBOE (SPX options)'
                        }
        except Exception:
            pass

    return _spx_iv_skew_fallback()


def _spx_iv_skew_fallback():
    """Fallback: CBOE SKEW index from yfinance."""
    try:
        import yfinance as yf
        skew = yf.Ticker("^SKEW")
        hist = skew.history(period='2y')
        if hist.empty:
            return {'error': 'SKEW index data unavailable'}

        close = hist['Close']
        latest = float(close.iloc[-1])
        change_1d = 0.0
        if len(close) > 1:
            prev = float(close.iloc[-2])
            if prev != 0:
                change_1d = round(((latest / prev) - 1) * 100, 2)

        return {
            'iv_skew_25d': None,
            'otm_put_iv': None,
            'otm_call_iv': None,
            'skew_index': round(latest, 2),
            'change_1d': change_1d,
            'latest_date': close.index[-1].strftime('%Y-%m-%d'),
            'historical': close,
            'source': 'yfinance (^SKEW index)',
            'note': 'SKEW index only — install openbb for strike-level IV data'
        }
    except Exception as e:
        return {'error': f'IV skew fetch error: {str(e)}'}


# ── #9: European Government Bond Yields ──────────────────────────────────────

def get_european_yields():
    """
    European 10Y government bond yields: Germany, France, Italy, Spain.
    Returns: dict with yields + spread vs Bund.
    Fallback: yfinance ETF proxies.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.fixedincome.government.yield_curve(country="germany", provider="ecb")
            # Additional countries would need separate calls
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty and 'rate' in df.columns:
                    # Find 10Y point
                    ten_y = df[df['maturity'].astype(str).str.contains('10')]
                    if not ten_y.empty:
                        de_10y = float(ten_y['rate'].iloc[-1])
                        return {
                            'de_10y': round(de_10y, 3),
                            'fr_10y': None,
                            'it_10y': None,
                            'es_10y': None,
                            'it_de_spread': None,
                            'latest_date': datetime.now().strftime('%Y-%m-%d'),
                            'source': 'OpenBB/ECB',
                            'note': 'Only DE available via ECB yield curve endpoint'
                        }
        except Exception:
            pass

    return _european_yields_fallback()


def _european_yields_fallback():
    """Fallback: direct ECB SDW API for major eurozone 10Y yields."""
    try:
        import requests

        # ECB SDW series for 10Y government bonds
        bonds = {
            'de_10y': 'YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y',
            'fr_10y': 'YC.B.U2.EUR.4F.G_N_A.SV_C_YM.FR_10Y',
            'it_10y': 'YC.B.U2.EUR.4F.G_N_A.SV_C_YM.IT_10Y',
        }

        result = {'source': 'ECB SDW API', 'latest_date': None}

        for key, series_key in bonds.items():
            try:
                # Use the ECB SDMX REST API
                url = f"https://data-api.ecb.europa.eu/service/data/YC/{series_key.split('YC.')[1] if 'YC.' in series_key else series_key}"
                headers = {'Accept': 'application/json'}
                resp = requests.get(url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    obs = list(data.get('dataSets', [{}])[0].get('series', {}).values())
                    if obs:
                        observations = obs[0].get('observations', {})
                        if observations:
                            last_key = max(observations.keys(), key=int)
                            result[key] = round(float(observations[last_key][0]), 3)
                            if result['latest_date'] is None:
                                time_vals = data.get('structure', {}).get('dimensions', {}).get('observation', [{}])[0].get('values', [])
                                if time_vals and int(last_key) < len(time_vals):
                                    result['latest_date'] = time_vals[int(last_key)].get('id')
            except Exception:
                result[key] = None

        # Compute IT-DE spread
        if result.get('it_10y') and result.get('de_10y'):
            result['it_de_spread'] = round(result['it_10y'] - result['de_10y'], 3)

        if result['latest_date'] is None:
            result['latest_date'] = datetime.now().strftime('%Y-%m-%d')

        if not any(result.get(k) for k in ['de_10y', 'fr_10y', 'it_10y']):
            return {'error': 'European yields unavailable from ECB API'}

        return result
    except Exception as e:
        return {'error': f'European yields fetch error: {str(e)}'}


# ── #10: Global CPI Comparison ───────────────────────────────────────────────

def get_global_cpi_comparison():
    """
    CPI YoY% for US, Eurozone, Japan, UK for cross-country comparison.
    Returns: dict with latest CPI for each region.
    Fallback: FRED series for each.
    """
    if OPENBB_AVAILABLE:
        try:
            result = {'source': 'OpenBB/OECD', 'latest_date': datetime.now().strftime('%Y-%m-%d')}
            for country in ['united_states', 'euro_area', 'japan', 'united_kingdom']:
                try:
                    data = obb.economy.cpi(country=country, provider="oecd")
                    if data and hasattr(data, 'results') and data.results:
                        df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                        if not df.empty:
                            key = country.replace(' ', '_').replace('united_states', 'us').replace('euro_area', 'eu').replace('united_kingdom', 'uk')
                            result[f'{key}_cpi_yoy'] = round(float(df.iloc[-1].iloc[-1]), 2)
                except Exception:
                    continue
            if any(k.endswith('_cpi_yoy') for k in result):
                return result
        except Exception:
            pass

    return _global_cpi_fallback()


def _global_cpi_fallback():
    """Fallback: FRED series for multi-country CPI.

    Series notes:
      US:  CPALTT01USM657N was discontinued Mar 2024 → use CPIAUCSL (index) + compute YoY
      EU:  CP0000EZ19M086NEST is an index (2015=100), NOT YoY% → compute YoY
      JP:  CPALTT01JPM657N is already YoY%
      UK:  CPALTT01GBM657N is already YoY%
    """
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        # (series_id, needs_yoy_computation)
        # Series notes (last validated 2026-04):
        #   CPALTT01USM657N  discontinued Mar 2024 → use CPIAUCSL index + compute YoY
        #   CP0000EZ19M086NEST  is index (2015=100), NOT YoY% → compute YoY
        #   CPALTT01JPM657N  OECD/FRED froze at Jun 2021 → use JPNCPIALLMINMEI index
        #   CPALTT01GBM657N  froze Feb 2024 → use GBRCPIALLMINMEI index + compute YoY
        cpi_series = {
            'us_cpi_yoy': ('CPIAUCSL', True),              # All-Urban CPI index → compute YoY
            'eu_cpi_yoy': ('CP0000EZ19M086NEST', True),    # HICP index 2015=100 → compute YoY
            'jp_cpi_yoy': ('JPNCPIALLMINMEI', True),        # Japan CPI index → compute YoY
            'uk_cpi_yoy': ('GBRCPIALLMINMEI', True),        # UK CPI index → compute YoY
        }

        result = {'source': 'FRED (multi-country CPI)', 'latest_date': None}
        historical_series = {}

        for key, (series_id, needs_yoy) in cpi_series.items():
            try:
                s = fred.get_series(series_id)
                if s is None or s.empty:
                    result[key] = None
                    continue
                s = s.dropna()
                if needs_yoy:
                    # Convert index level to YoY % change
                    s = s.pct_change(12).mul(100).dropna()
                if s.empty:
                    result[key] = None
                    continue
                result[key] = round(float(s.iloc[-1]), 2)
                if result['latest_date'] is None:
                    result['latest_date'] = s.index[-1].strftime('%Y-%m-%d')
                historical_series[key] = s
            except Exception:
                result[key] = None

        if historical_series:
            if 'us_cpi_yoy' in historical_series:
                result['historical'] = historical_series['us_cpi_yoy']

        if result['latest_date'] is None:
            return {'error': 'Global CPI comparison unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'Global CPI comparison fetch error: {str(e)}'}


# ══════════════════════════════════════════════════════════════════════════════
# MEDIUM-VALUE EXTRACTORS (#11–#20)
# ══════════════════════════════════════════════════════════════════════════════

# ── #11: Upcoming Earnings Calendar ──────────────────────────────────────────

def get_upcoming_earnings():
    """
    Upcoming earnings announcements for major companies.
    Returns: dict with list of upcoming earnings dates.
    Fallback: yfinance calendar for Top 20 tickers.
    """
    if OPENBB_AVAILABLE:
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            next_week = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')
            data = obb.equity.calendar.earnings(start_date=today, end_date=next_week, provider="finviz")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty:
                    # Take top 20 by market cap or just first 20
                    entries = df.head(20).to_dict('records')
                    return {
                        'earnings': entries,
                        'count': len(entries),
                        'period': f'{today} to {next_week}',
                        'latest_date': today,
                        'source': 'OpenBB/Finviz'
                    }
        except Exception:
            pass

    return _upcoming_earnings_fallback()


def _upcoming_earnings_fallback():
    """Fallback: yfinance earnings dates for Top 20 tickers."""
    try:
        import yfinance as yf

        top_tickers = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'TSM', 'LLY', 'AVGO', 'JPM']
        earnings = []
        today = datetime.now()

        for symbol in top_tickers:
            try:
                t = yf.Ticker(symbol)
                cal = t.calendar
                if cal is not None and isinstance(cal, dict):
                    earn_date = cal.get('Earnings Date')
                    if earn_date:
                        if isinstance(earn_date, list) and earn_date:
                            earn_date = earn_date[0]
                        if hasattr(earn_date, 'strftime'):
                            earnings.append({'symbol': symbol, 'date': earn_date.strftime('%Y-%m-%d')})
            except Exception:
                continue

        # Sort by date, filter to next 30 days
        earnings = [e for e in earnings if e.get('date')]
        earnings.sort(key=lambda x: x['date'])

        return {
            'earnings': earnings,
            'count': len(earnings),
            'period': f"next 30 days from {today.strftime('%Y-%m-%d')}",
            'latest_date': today.strftime('%Y-%m-%d'),
            'source': 'yfinance (Top 10 tickers)',
            'note': 'Limited to top tickers — install openbb for full calendar'
        }
    except Exception as e:
        return {'error': f'Earnings calendar fetch error: {str(e)}'}


# ── #12: Sector P/E Ratios ───────────────────────────────────────────────────

def get_sector_pe_ratios():
    """
    P/E ratios by sector using sector ETFs.
    Returns: dict with sector → P/E mapping.
    """
    try:
        import yfinance as yf

        sector_etfs = {
            'Technology': 'XLK',
            'Financials': 'XLF',
            'Healthcare': 'XLV',
            'Energy': 'XLE',
            'Industrials': 'XLI',
            'Communication': 'XLC',
            'Consumer Disc.': 'XLY',
            'Consumer Staples': 'XLP',
            'Materials': 'XLB',
            'Real Estate': 'XLRE',
            'Utilities': 'XLU',
        }

        result = {'sectors': {}, 'source': 'yfinance (sector ETFs)', 'latest_date': datetime.now().strftime('%Y-%m-%d')}

        for sector, etf in sector_etfs.items():
            try:
                t = yf.Ticker(etf)
                info = t.info
                pe = info.get('trailingPE') or info.get('forwardPE')
                if pe:
                    result['sectors'][sector] = round(pe, 1)
            except Exception:
                continue

        if not result['sectors']:
            return {'error': 'Sector P/E ratios unavailable'}
        return result
    except Exception as e:
        return {'error': f'Sector P/E fetch error: {str(e)}'}


# ── #13: Full Treasury Yield Curve ───────────────────────────────────────────

def get_full_treasury_curve():
    """
    Full US Treasury yield curve (1M to 30Y).
    Returns: dict with maturity → yield mapping.
    Fallback: FRED series for each maturity.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.fixedincome.government.yield_curve(country="united_states", provider="federal_reserve")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty:
                    curve = {}
                    for _, row in df.iterrows():
                        mat = str(row.get('maturity', ''))
                        rate = row.get('rate')
                        if mat and rate is not None:
                            curve[mat] = round(float(rate), 3)
                    if curve:
                        return {
                            'curve': curve,
                            'latest_date': datetime.now().strftime('%Y-%m-%d'),
                            'source': 'OpenBB/Federal Reserve'
                        }
        except Exception:
            pass

    return _treasury_curve_fallback()


def _treasury_curve_fallback():
    """Fallback: FRED series for key Treasury maturities."""
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        maturities = {
            '1M': 'DGS1MO', '3M': 'DGS3MO', '6M': 'DGS6MO',
            '1Y': 'DGS1', '2Y': 'DGS2', '3Y': 'DGS3', '5Y': 'DGS5',
            '7Y': 'DGS7', '10Y': 'DGS10', '20Y': 'DGS20', '30Y': 'DGS30',
        }

        curve = {}
        latest_date = None
        for mat, series_id in maturities.items():
            try:
                s = fred.get_series(series_id)
                if s is not None and not s.empty:
                    val = s.dropna().iloc[-1]
                    curve[mat] = round(float(val), 3)
                    if latest_date is None:
                        latest_date = s.dropna().index[-1].strftime('%Y-%m-%d')
            except Exception:
                continue

        if not curve:
            return {'error': 'Treasury curve unavailable from FRED'}

        return {
            'curve': curve,
            'latest_date': latest_date or datetime.now().strftime('%Y-%m-%d'),
            'source': 'FRED (Treasury constant maturity)'
        }
    except Exception as e:
        return {'error': f'Treasury curve fetch error: {str(e)}'}


# ── #14: Corporate Bond Spreads (AAA/BBB) ────────────────────────────────────

def get_corporate_bond_spreads():
    """
    Corporate bond spreads: AAA and BBB OAS over Treasuries.
    Returns: dict with spreads + credit spread (BBB-AAA).
    Fallback: FRED BAMLC0A1CAAA / BAMLC0A4CBBB series.
    """
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        aaa = fred.get_series('BAMLC0A1CAAA')  # AAA OAS
        bbb = fred.get_series('BAMLC0A4CBBB')  # BBB OAS

        result = {'source': 'FRED (BofA ICE OAS)', 'latest_date': None}

        if aaa is not None and not aaa.empty:
            aaa_clean = aaa.dropna()
            result['aaa_oas'] = round(float(aaa_clean.iloc[-1]), 3)
            result['latest_date'] = aaa_clean.index[-1].strftime('%Y-%m-%d')
            result['aaa_historical'] = aaa_clean

        if bbb is not None and not bbb.empty:
            bbb_clean = bbb.dropna()
            result['bbb_oas'] = round(float(bbb_clean.iloc[-1]), 3)
            result['bbb_historical'] = bbb_clean

        if result.get('bbb_oas') and result.get('aaa_oas'):
            result['credit_spread'] = round(result['bbb_oas'] - result['aaa_oas'], 3)

        if result['latest_date'] is None:
            return {'error': 'Corporate spreads unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'Corporate spreads fetch error: {str(e)}'}


# ── #15: International Unemployment Rates ────────────────────────────────────

def get_international_unemployment():
    """
    Unemployment rates: US, Eurozone, Japan, UK.
    Returns: dict with rates by country.
    Fallback: FRED series.
    """
    if OPENBB_AVAILABLE:
        try:
            result = {'source': 'OpenBB/OECD', 'latest_date': None}
            for country, key in [('united_states', 'us'), ('euro_area', 'eu'), ('japan', 'jp'), ('united_kingdom', 'uk')]:
                try:
                    data = obb.economy.unemployment(country=country, provider="oecd")
                    if data and hasattr(data, 'results') and data.results:
                        df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                        if not df.empty:
                            result[f'{key}_unemployment'] = round(float(df.iloc[-1].iloc[-1]), 2)
                            if result['latest_date'] is None:
                                result['latest_date'] = str(df.index[-1])[:10]
                except Exception:
                    continue
            if any(k.endswith('_unemployment') for k in result):
                return result
        except Exception:
            pass

    return _international_unemployment_fallback()


def _international_unemployment_fallback():
    """Fallback: FRED series for multi-country unemployment."""
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        series_map = {
            'us_unemployment': 'UNRATE',
            'eu_unemployment': 'LRHUTTTTEZM156S',
            'jp_unemployment': 'LRHUTTTTJPM156S',
            'uk_unemployment': 'LRHUTTTTGBM156S',
        }

        result = {'source': 'FRED (multi-country unemployment)', 'latest_date': None}

        for key, series_id in series_map.items():
            try:
                s = fred.get_series(series_id)
                if s is not None and not s.empty:
                    result[key] = round(float(s.iloc[-1]), 2)
                    if key == 'us_unemployment':
                        result['historical'] = s
                    if result['latest_date'] is None:
                        result['latest_date'] = s.index[-1].strftime('%Y-%m-%d')
            except Exception:
                result[key] = None

        if result['latest_date'] is None:
            return {'error': 'International unemployment unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'International unemployment fetch error: {str(e)}'}


# ── #16: International GDP Growth ────────────────────────────────────────────

def get_international_gdp():
    """
    Real GDP growth (QoQ annualized) for US, Eurozone, Japan, UK, China.
    Returns: dict with latest GDP growth by country.
    Fallback: FRED series.
    """
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        # FRED series: real GDP growth rate (QoQ SAAR or QoQ %)
        # Notes on series selection (as of 2026):
        #   CLVMNACSCAB1GQUK (UK level) froze at 2020-Q2 → replaced by NAEXKP01GBQ657S (QoQ %)
        #   RGDPNACNA666NRUG (China annual WB) froze at 2023 → replaced by CHNGDPNQDSMEI (QoQ %)
        series_map = {
            'us_gdp_growth': ('A191RL1Q225SBEA',    False),  # US QoQ SAAR % (already %)
            'eu_gdp_growth': ('CLVMNACSCAB1GQEA19', True),   # Euro area level → compute QoQ %
            'jp_gdp_growth': ('JPNRGDPEXP',          True),   # Japan level → compute QoQ %
            'uk_gdp_growth': ('NAEXKP01GBQ657S',    False),  # UK QoQ % (already %)
            'cn_gdp_growth': ('CHNGDPNQDSMEI',      True),   # China nominal GDP level → compute QoQ %
        }

        result = {'source': 'FRED (multi-country GDP)', 'latest_date': None}

        for key, (series_id, compute_qoq) in series_map.items():
            try:
                s = fred.get_series(series_id)
                if s is None or s.empty:
                    result[key] = None
                    continue
                s = s.dropna()
                if compute_qoq:
                    # Level series: compute QoQ % change
                    if len(s) >= 2:
                        latest = float(s.iloc[-1])
                        prev = float(s.iloc[-2])
                        result[key] = round(((latest / prev) - 1) * 100, 2) if prev != 0 else None
                    else:
                        result[key] = None
                else:
                    # Already a % series
                    result[key] = round(float(s.iloc[-1]), 2)
                if key == 'us_gdp_growth':
                    result['historical'] = s
                if result['latest_date'] is None:
                    result['latest_date'] = s.index[-1].strftime('%Y-%m-%d')
            except Exception:
                result[key] = None

        if result['latest_date'] is None:
            return {'error': 'International GDP data unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'International GDP fetch error: {str(e)}'}


# ── #17: Equity Market Breadth Screener ──────────────────────────────────────

def get_equity_screener():
    """
    Market breadth metrics: % of S&P 500 above 200-day MA, new highs/lows.
    Returns: dict with breadth indicators.
    Fallback: yfinance calculations on SPY components.
    """
    if OPENBB_AVAILABLE:
        try:
            data = obb.equity.screener(provider="finviz")
            if data and hasattr(data, 'results') and data.results:
                df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                if not df.empty and 'sma200' in df.columns:
                    above_200 = (df['price'] > df['sma200']).sum()
                    total = len(df)
                    return {
                        'pct_above_200ma': round(above_200 / total * 100, 1) if total > 0 else None,
                        'total_stocks': total,
                        'new_highs': (df.get('change_from_high', pd.Series()) == 0).sum() if 'change_from_high' in df.columns else None,
                        'latest_date': datetime.now().strftime('%Y-%m-%d'),
                        'source': 'OpenBB/Finviz'
                    }
        except Exception:
            pass

    # Simple fallback — return note that this needs OpenBB
    return {
        'pct_above_200ma': None,
        'total_stocks': None,
        'new_highs': None,
        'latest_date': datetime.now().strftime('%Y-%m-%d'),
        'source': 'unavailable',
        'note': 'Equity screener requires openbb with Finviz provider'
    }


# ── #18: Money Supply Measures (M1/M2/MZM) ──────────────────────────────────

def get_money_measures():
    """
    Money supply: M1, M2, MZM levels and YoY growth.
    Returns: dict with money supply metrics.
    Fallback: FRED series.
    """
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        series_map = {
            'm1': 'M1SL',
            'm2': 'M2SL',
        }

        result = {'source': 'FRED (money supply)', 'latest_date': None}

        for key, series_id in series_map.items():
            try:
                s = fred.get_series(series_id)
                if s is not None and not s.empty:
                    latest = float(s.iloc[-1])
                    result[f'{key}_level'] = round(latest, 1)

                    # YoY growth
                    if len(s) >= 13:
                        year_ago = float(s.iloc[-13])
                        if year_ago != 0:
                            result[f'{key}_yoy'] = round(((latest / year_ago) - 1) * 100, 2)

                    if key == 'm2':
                        result['historical'] = s

                    if result['latest_date'] is None:
                        result['latest_date'] = s.index[-1].strftime('%Y-%m-%d')
            except Exception:
                continue

        if result['latest_date'] is None:
            return {'error': 'Money supply data unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'Money measures fetch error: {str(e)}'}


# ── #19: Global Manufacturing PMI ────────────────────────────────────────────

def get_global_pmi():
    """
    Global manufacturing PMI for major economies.
    Returns: dict with PMI values by country.
    Fallback: FRED ISM Manufacturing PMI + any available international PMIs.
    """
    if OPENBB_AVAILABLE:
        try:
            result = {'source': 'OpenBB/EconDB', 'latest_date': None}
            for country, key in [('united_states', 'us'), ('euro_area', 'eu'), ('japan', 'jp'), ('china', 'cn'), ('united_kingdom', 'uk')]:
                try:
                    data = obb.economy.pmi(country=country, provider="econdb")
                    if data and hasattr(data, 'results') and data.results:
                        df = data.to_df() if hasattr(data, 'to_df') else pd.DataFrame([vars(r) for r in data.results])
                        if not df.empty:
                            result[f'{key}_mfg_pmi'] = round(float(df.iloc[-1].iloc[-1]), 1)
                            if result['latest_date'] is None:
                                result['latest_date'] = str(df.index[-1])[:10]
                except Exception:
                    continue
            if any(k.endswith('_mfg_pmi') for k in result):
                return result
        except Exception:
            pass

    return _global_pmi_fallback()


def _global_pmi_fallback():
    """Fallback: FRED Industrial Production Manufacturing as PMI proxy."""
    try:
        from fredapi import Fred
        import config
        fred = Fred(api_key=config.FRED_API_KEY)

        # NAPM is discontinued; use Industrial Production: Manufacturing as proxy
        ipman = fred.get_series('IPMAN')

        result = {'source': 'FRED (Industrial Production Manufacturing proxy)', 'latest_date': None}

        if ipman is not None and not ipman.empty:
            # Convert IP index to PMI-like scale (IP ~100 base, PMI ~50 base)
            latest_val = float(ipman.iloc[-1])
            prev_val = float(ipman.iloc[-2]) if len(ipman) > 1 else latest_val
            mom_change = ((latest_val / prev_val) - 1) * 100 if prev_val != 0 else 0
            # Map MoM % change to PMI-like: 0% change → 50, each 1% → ~5 PMI points
            pmi_estimate = round(50 + mom_change * 5, 1)
            pmi_estimate = max(30, min(70, pmi_estimate))

            result['us_mfg_pmi'] = pmi_estimate
            result['latest_date'] = ipman.index[-1].strftime('%Y-%m-%d')
            result['historical'] = ipman

        # International PMIs are not readily available on FRED
        result['eu_mfg_pmi'] = None
        result['jp_mfg_pmi'] = None
        result['cn_mfg_pmi'] = None
        result['uk_mfg_pmi'] = None
        result['note'] = 'US PMI estimated from Industrial Production. International PMIs unavailable — install openbb for EconDB global PMI'

        if result['latest_date'] is None:
            return {'error': 'Global PMI data unavailable from FRED'}
        return result
    except Exception as e:
        return {'error': f'Global PMI fetch error: {str(e)}'}


# ── #20: Equity Risk Premium ─────────────────────────────────────────────────

def get_equity_risk_premium():
    """
    Equity Risk Premium = S&P 500 Earnings Yield - 10Y Real Yield.
    Returns: dict with ERP + components.
    Computed from existing data sources (no OpenBB needed).
    """
    try:
        import yfinance as yf
        from fredapi import Fred
        import config

        # Get earnings yield (1/PE)
        spy = yf.Ticker("SPY")
        info = spy.info
        trailing_pe = info.get('trailingPE')
        forward_pe = info.get('forwardPE')

        # If yfinance doesn't provide forward PE, try OpenBB/Finviz via sp500 multiples
        if not forward_pe:
            try:
                multiples = get_sp500_historical_multiples()
                if multiples and 'error' not in multiples:
                    fwd_pe_from_mult = multiples.get('forward_pe')
                    if fwd_pe_from_mult and fwd_pe_from_mult > 0:
                        forward_pe = fwd_pe_from_mult
            except Exception:
                pass

        earnings_yield = round(1.0 / trailing_pe * 100, 2) if trailing_pe and trailing_pe > 0 else None
        forward_earnings_yield = round(1.0 / forward_pe * 100, 2) if forward_pe and forward_pe > 0 else None

        # Get 10Y real yield (TIPS)
        fred = Fred(api_key=config.FRED_API_KEY)
        real_yield_series = fred.get_series('DFII10')  # 10Y TIPS yield
        real_yield = None
        if real_yield_series is not None and not real_yield_series.empty:
            real_yield_clean = real_yield_series.dropna()
            real_yield = round(float(real_yield_clean.iloc[-1]), 2)

        # Compute ERP
        erp = None
        forward_erp = None
        if earnings_yield is not None and real_yield is not None:
            erp = round(earnings_yield - real_yield, 2)
        if forward_earnings_yield is not None and real_yield is not None:
            forward_erp = round(forward_earnings_yield - real_yield, 2)

        return {
            'equity_risk_premium': erp,
            'forward_erp': forward_erp,
            'earnings_yield': earnings_yield,
            'forward_earnings_yield': forward_earnings_yield,
            'real_yield_10y': real_yield,
            'trailing_pe': trailing_pe,
            'forward_pe': forward_pe,
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'Computed (yfinance SPY + FRED DFII10)'
        }
    except Exception as e:
        return {'error': f'Equity risk premium fetch error: {str(e)}'}
