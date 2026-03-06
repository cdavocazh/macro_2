"""
FRED extractors for Financial Agent v1.5-v1.9 features.

Self-contained batch fetcher for 27 series (26 FRED + 1 yfinance) needed by
the Financial Agent's macro-to-market analysis tools (market regime,
consumer/housing analysis, Yardeni frameworks).

Covers:
  - Financial stress indicators (NFCI, Sahm Rule, Consumer Sentiment)
  - ISM manufacturing decomposition (DGORDER, MANEMP, ISRATIO)
  - JOLTS labor market (openings, quits, hires, layoffs)
  - Productivity (output per hour, unit labor costs)
  - Consumer health (savings rate, revolving credit, delinquencies, bank lending)
  - Housing (starts, permits, sales, mortgage rate, prices)
  - Commodity prices for Yardeni (copper monthly, gold via yfinance, natural gas)
  - Rates (fed funds monthly effective) and energy (gasoline)
"""

import yfinance as yf
from .fred_extractors import get_fred_client

# Maps logical key → (FRED series ID, CSV column name)
SERIES_MAP = {
    # ── 1. Financial Stress & Recession Signals ───────────────────────────
    'nfci':                     ('NFCI',              'nfci'),
    'sahm_rule':                ('SAHMREALTIME',      'sahm_rule'),
    'consumer_sentiment':       ('UMCSENT',           'consumer_sentiment'),

    # ── 2. ISM Manufacturing Decomposition ────────────────────────────────
    'durable_goods_orders':     ('DGORDER',           'durable_goods_orders'),
    'manufacturing_employment': ('MANEMP',            'manufacturing_employment'),
    'inventories_sales_ratio':  ('ISRATIO',           'inventories_sales_ratio'),

    # ── 3. JOLTS Labor Market ─────────────────────────────────────────────
    'jolts_openings':           ('JTSJOL',            'jolts_openings'),
    'jolts_quits_rate':         ('JTSQUR',            'jolts_quits_rate'),
    'jolts_hires':              ('JTSHIL',            'jolts_hires'),
    'jolts_layoffs':            ('JTSLDL',            'jolts_layoffs'),

    # ── 4. Productivity & Unit Labor Costs ────────────────────────────────
    'productivity':             ('OPHNFB',            'output_per_hour'),
    'unit_labor_costs':         ('ULCNFB',            'unit_labor_costs'),

    # ── 5. Consumer Health ────────────────────────────────────────────────
    'savings_rate':             ('PSAVERT',           'savings_rate'),
    'revolving_credit':         ('REVOLSL',           'revolving_credit'),
    'delinquency_rate':         ('DRALACBS',          'delinquency_rate'),
    'bank_lending_standards':   ('DRTSCILM',          'bank_lending_standards'),

    # ── 6. Housing Market ─────────────────────────────────────────────────
    'housing_starts':           ('HOUST',             'housing_starts'),
    'building_permits':         ('PERMIT',            'building_permits'),
    'existing_home_sales':      ('EXHOSLUSM495S',     'existing_home_sales'),
    'mortgage_rate_30y':        ('MORTGAGE30US',       'mortgage_rate_30y'),
    'median_home_price':        ('MSPUS',             'median_home_price'),
    'case_shiller_index':       ('CSUSHPISA',         'case_shiller_index'),

    # ── 7. Commodity Prices (Yardeni) ─────────────────────────────────────
    'copper_price_fred':        ('PCOPPUSDM',         'copper_price_usd_mt'),
    # gold_price_fred: GOLDAMGBD228NLBM discontinued on FRED (LBMA/ICE licensing).
    # Gold price extracted separately via yfinance GC=F in get_gold_price_yfinance().
    'natural_gas_fred':         ('DHHNGSP',           'natural_gas_price'),

    # ── 8. Rates & Energy ─────────────────────────────────────────────────
    'fed_funds_effective':      ('FEDFUNDS',          'fed_funds_effective'),
    'gasoline_price':           ('GASREGW',           'gasoline_price'),
}


def get_financial_agent_series(key):
    """Fetch a single Financial Agent FRED series by logical key.

    Returns:
        dict with keys: {col_name}, latest_date, historical (pd.Series), source, series_id
        OR dict with 'error' key on failure.
    """
    if key not in SERIES_MAP:
        return {'error': f'Unknown series key: {key}'}

    series_id, col_name = SERIES_MAP[key]
    try:
        fred = get_fred_client()
        data = fred.get_series(series_id)
        data = data.dropna()
        if len(data) == 0:
            return {'error': f'No data for {series_id}'}
        return {
            col_name: float(data.iloc[-1]),
            'latest_date': data.index[-1].strftime('%Y-%m-%d'),
            'historical': data,
            'source': 'FRED',
            'series_id': series_id,
        }
    except Exception as e:
        return {'error': f'Error fetching {series_id}: {str(e)}'}


def get_all_financial_agent_series():
    """Fetch all 27 Financial Agent FRED series in one batch.

    Returns:
        dict[str, dict] — keyed by logical name from SERIES_MAP.
        Each value is the same format as get_financial_agent_series().
    """
    fred = get_fred_client()
    results = {}

    for key, (series_id, col_name) in SERIES_MAP.items():
        try:
            data = fred.get_series(series_id)
            data = data.dropna()
            if len(data) == 0:
                results[key] = {'error': f'No data for {series_id}'}
                continue
            results[key] = {
                col_name: float(data.iloc[-1]),
                'latest_date': data.index[-1].strftime('%Y-%m-%d'),
                'historical': data,
                'source': 'FRED',
                'series_id': series_id,
            }
        except Exception as e:
            results[key] = {'error': f'Error fetching {series_id}: {str(e)}'}

    return results


def get_gold_price_yfinance():
    """Fetch gold price via yfinance GC=F (LBMA FRED series discontinued).

    Returns:
        dict with keys: gold_price_fred, latest_date, historical (pd.Series), source
        OR dict with 'error' key on failure.
    """
    try:
        ticker = yf.Ticker('GC=F')
        hist = ticker.history(period='max')['Close']
        hist = hist.dropna()
        if len(hist) == 0:
            return {'error': 'No data for GC=F'}
        return {
            'gold_price_fred': float(hist.iloc[-1]),
            'latest_date': hist.index[-1].strftime('%Y-%m-%d'),
            'historical': hist,
            'source': 'Yahoo Finance (GC=F)',
        }
    except Exception as e:
        return {'error': f'Error fetching gold price: {str(e)}'}
