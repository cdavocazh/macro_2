"""
Equity Financials Extractor — Financial data for top listed companies.

Primary source: Yahoo Finance (yfinance)
Fallback/comparison sources (optional): Finnhub, Simfin, Tiger Brokers

Fetches: income statement, balance sheet, cash flow, valuation, financial analysis
for the top 20 companies by market cap. Data is JSON-serializable for caching.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime
import traceback


# Top 20 companies by market cap (periodically updated)
TOP_20_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN',
    'META', 'BRK-B', 'TSM', 'LLY', 'AVGO',
    'JPM', 'V', 'WMT', 'MA', 'XOM',
    'UNH', 'COST', 'HD', 'PG', 'JNJ',
]


def _safe_get_row(df, row_names, col):
    """
    Safely get a value from a financial statement DataFrame.
    Tries multiple row label variations.

    Args:
        df: financial statement DataFrame (index=line items, columns=dates)
        row_names: str or list of str — row labels to try
        col: column (date) to extract from
    Returns: float or None
    """
    if df is None or df.empty:
        return None
    if isinstance(row_names, str):
        row_names = [row_names]
    for label in row_names:
        try:
            if label in df.index:
                val = df.loc[label, col]
                if pd.notna(val):
                    return float(val)
        except Exception:
            continue
    return None


def _format_quarter_label(ts):
    """Convert a Timestamp to a quarter label like '2024-Q4'."""
    try:
        if hasattr(ts, 'quarter'):
            return f"{ts.year}-Q{ts.quarter}"
        return str(ts)[:10]
    except Exception:
        return str(ts)


def _pct(val):
    """Format a ratio as percentage rounded to 2 decimals, or None."""
    if val is None:
        return None
    try:
        return round(float(val) * 100, 2)
    except (ValueError, TypeError):
        return None


def _safe_round(val, decimals=2):
    """Round a value safely, return None if not numeric."""
    if val is None:
        return None
    try:
        return round(float(val), decimals)
    except (ValueError, TypeError):
        return None


def _safe_divide(numerator, denominator, decimals=4):
    """Safely divide two values, return None if not possible."""
    if numerator is None or denominator is None:
        return None
    try:
        n = float(numerator)
        d = float(denominator)
        if d == 0:
            return None
        return round(n / d, decimals)
    except (ValueError, TypeError, ZeroDivisionError):
        return None


# ── Yahoo Finance (Primary Source) ──────────────────────────────────

def get_company_financials_yahoo(ticker_symbol):
    """
    Fetch comprehensive financial data for a single company via Yahoo Finance.

    Returns a JSON-serializable dict with:
    - income_statement (quarterly, up to 9 quarters)
    - balance_sheet (quarterly)
    - cash_flow (quarterly)
    - valuation (current)
    - financial_analysis (profitability, turnover, growth, returns)
    """
    try:
        ticker = yf.Ticker(ticker_symbol)
        info = ticker.info or {}

        # Get quarterly financial statements
        q_income = ticker.quarterly_income_stmt
        q_balance = ticker.quarterly_balance_sheet
        q_cashflow = ticker.quarterly_cashflow

        # Determine quarter labels (most recent first)
        quarters = []
        if q_income is not None and not q_income.empty:
            quarters = [_format_quarter_label(c) for c in q_income.columns[:9]]

        result = {
            'ticker': ticker_symbol,
            'company_name': info.get('longName', info.get('shortName', ticker_symbol)),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'market_cap': info.get('marketCap'),
            'currency': info.get('currency', 'USD'),
            'latest_date': datetime.now().strftime('%Y-%m-%d'),
            'source': 'Yahoo Finance',
            'quarters': quarters,
        }

        # ── Income Statement ────────────────────────────────
        if q_income is not None and not q_income.empty:
            cols = list(q_income.columns[:9])
            result['income_statement'] = {
                'total_revenue': [_safe_get_row(q_income, ['Total Revenue', 'Operating Revenue'], c) for c in cols],
                'cost_of_revenue': [_safe_get_row(q_income, ['Cost Of Revenue', 'Reconciled Cost Of Revenue'], c) for c in cols],
                'gross_profit': [_safe_get_row(q_income, ['Gross Profit'], c) for c in cols],
                'operating_expense': [_safe_get_row(q_income, ['Operating Expense'], c) for c in cols],
                'research_development': [_safe_get_row(q_income, ['Research And Development'], c) for c in cols],
                'selling_general_admin': [_safe_get_row(q_income, ['Selling General And Administration'], c) for c in cols],
                'operating_income': [_safe_get_row(q_income, ['Operating Income', 'Total Operating Income As Reported'], c) for c in cols],
                'ebitda': [_safe_get_row(q_income, ['EBITDA', 'Normalized EBITDA'], c) for c in cols],
                'ebit': [_safe_get_row(q_income, ['EBIT'], c) for c in cols],
                'pretax_income': [_safe_get_row(q_income, ['Pretax Income'], c) for c in cols],
                'tax_provision': [_safe_get_row(q_income, ['Tax Provision'], c) for c in cols],
                'net_income': [_safe_get_row(q_income, ['Net Income', 'Net Income Common Stockholders'], c) for c in cols],
                'diluted_eps': [_safe_get_row(q_income, ['Diluted EPS'], c) for c in cols],
                'basic_eps': [_safe_get_row(q_income, ['Basic EPS'], c) for c in cols],
                'diluted_shares': [_safe_get_row(q_income, ['Diluted Average Shares'], c) for c in cols],
                'basic_shares': [_safe_get_row(q_income, ['Basic Average Shares'], c) for c in cols],
            }
        else:
            result['income_statement'] = None

        # ── Balance Sheet ───────────────────────────────────
        if q_balance is not None and not q_balance.empty:
            cols = list(q_balance.columns[:9])

            # Assets
            total_assets_list = [_safe_get_row(q_balance, ['Total Assets'], c) for c in cols]
            current_assets_list = [_safe_get_row(q_balance, ['Current Assets'], c) for c in cols]
            cash_list = [_safe_get_row(q_balance, ['Cash Cash Equivalents And Short Term Investments', 'Cash And Cash Equivalents'], c) for c in cols]
            cash_only_list = [_safe_get_row(q_balance, ['Cash And Cash Equivalents'], c) for c in cols]
            short_term_investments = [_safe_get_row(q_balance, ['Other Short Term Investments'], c) for c in cols]
            accounts_receivable_list = [_safe_get_row(q_balance, ['Accounts Receivable', 'Receivables'], c) for c in cols]
            inventory_list = [_safe_get_row(q_balance, ['Inventory'], c) for c in cols]
            goodwill_list = [_safe_get_row(q_balance, ['Goodwill'], c) for c in cols]
            net_ppe_list = [_safe_get_row(q_balance, ['Net PPE'], c) for c in cols]
            total_non_current_assets = [_safe_get_row(q_balance, ['Total Non Current Assets'], c) for c in cols]

            # Liabilities
            total_liab_list = [_safe_get_row(q_balance, [
                'Total Liabilities Net Minority Interest',
                'Total Liabilities',
            ], c) for c in cols]
            current_liab_list = [_safe_get_row(q_balance, ['Current Liabilities'], c) for c in cols]
            non_current_liab_list = [_safe_get_row(q_balance, ['Total Non Current Liabilities Net Minority Interest'], c) for c in cols]
            long_term_debt_list = [_safe_get_row(q_balance, ['Long Term Debt'], c) for c in cols]
            current_debt_list = [_safe_get_row(q_balance, ['Current Debt', 'Current Debt And Capital Lease Obligation'], c) for c in cols]
            total_debt_list = [_safe_get_row(q_balance, ['Total Debt'], c) for c in cols]
            accounts_payable_list = [_safe_get_row(q_balance, ['Accounts Payable'], c) for c in cols]
            accrued_expenses_list = [_safe_get_row(q_balance, ['Current Accrued Expenses'], c) for c in cols]

            # Equity
            stockholders_equity_list = [_safe_get_row(q_balance, [
                'Stockholders Equity',
                'Common Stock Equity',
                'Total Equity Gross Minority Interest',
            ], c) for c in cols]
            retained_earnings_list = [_safe_get_row(q_balance, ['Retained Earnings'], c) for c in cols]
            invested_capital_list = [_safe_get_row(q_balance, ['Invested Capital'], c) for c in cols]

            # Computed ratios
            debt_ratio_list = [_safe_divide(l, a) for a, l in zip(total_assets_list, total_liab_list)]
            debt_to_equity_list = [_safe_divide(td, eq) for td, eq in zip(total_debt_list, stockholders_equity_list)]
            current_ratio_list = [_safe_divide(ca, cl) for ca, cl in zip(current_assets_list, current_liab_list)]
            net_debt_list = [_safe_get_row(q_balance, ['Net Debt'], c) for c in cols]

            result['balance_sheet'] = {
                # Assets
                'total_assets': total_assets_list,
                'current_assets': current_assets_list,
                'cash_and_short_term_investments': cash_list,
                'cash_and_equivalents': cash_only_list,
                'short_term_investments': short_term_investments,
                'accounts_receivable': accounts_receivable_list,
                'inventory': inventory_list,
                'total_non_current_assets': total_non_current_assets,
                'goodwill': goodwill_list,
                'net_ppe': net_ppe_list,
                # Liabilities
                'total_liabilities': total_liab_list,
                'current_liabilities': current_liab_list,
                'non_current_liabilities': non_current_liab_list,
                'long_term_debt': long_term_debt_list,
                'current_debt': current_debt_list,
                'total_debt': total_debt_list,
                'accounts_payable': accounts_payable_list,
                'accrued_expenses': accrued_expenses_list,
                'net_debt': net_debt_list,
                # Equity
                'stockholders_equity': stockholders_equity_list,
                'retained_earnings': retained_earnings_list,
                'invested_capital': invested_capital_list,
                # Ratios
                'debt_ratio': debt_ratio_list,
                'debt_to_equity': debt_to_equity_list,
                'current_ratio': current_ratio_list,
            }

            if not quarters:
                result['quarters'] = [_format_quarter_label(c) for c in cols]
        else:
            result['balance_sheet'] = None

        # ── Cash Flow ───────────────────────────────────────
        if q_cashflow is not None and not q_cashflow.empty:
            cols = list(q_cashflow.columns[:9])
            operating_cf = [_safe_get_row(q_cashflow, [
                'Operating Cash Flow',
                'Cash Flow From Continuing Operating Activities',
            ], c) for c in cols]
            capital_expenditure = [_safe_get_row(q_cashflow, ['Capital Expenditure'], c) for c in cols]
            free_cash_flow = [_safe_get_row(q_cashflow, ['Free Cash Flow'], c) for c in cols]
            share_repurchases = [_safe_get_row(q_cashflow, ['Repurchase Of Capital Stock', 'Common Stock Payments'], c) for c in cols]
            dividends_paid = [_safe_get_row(q_cashflow, ['Cash Dividends Paid', 'Common Stock Dividend Paid'], c) for c in cols]
            investing_cf = [_safe_get_row(q_cashflow, ['Investing Cash Flow', 'Cash Flow From Continuing Investing Activities'], c) for c in cols]
            financing_cf = [_safe_get_row(q_cashflow, ['Financing Cash Flow', 'Cash Flow From Continuing Financing Activities'], c) for c in cols]
            depreciation = [_safe_get_row(q_cashflow, ['Depreciation Amortization Depletion', 'Depreciation And Amortization'], c) for c in cols]
            stock_based_comp = [_safe_get_row(q_cashflow, ['Stock Based Compensation'], c) for c in cols]

            # Compute FCF if not directly available
            if all(v is None for v in free_cash_flow):
                free_cash_flow = [
                    round(o + c, 2) if o is not None and c is not None else None
                    for o, c in zip(operating_cf, capital_expenditure)
                ]

            result['cash_flow'] = {
                'operating_cash_flow': operating_cf,
                'capital_expenditure': capital_expenditure,
                'free_cash_flow': free_cash_flow,
                'share_repurchases': share_repurchases,
                'dividends_paid': dividends_paid,
                'investing_cash_flow': investing_cf,
                'financing_cash_flow': financing_cf,
                'depreciation_amortization': depreciation,
                'stock_based_compensation': stock_based_comp,
            }
        else:
            result['cash_flow'] = None

        # ── Valuation ──────────────────────────────────────
        enterprise_value = info.get('enterpriseValue')
        _current_price = _safe_round(info.get('currentPrice', info.get('regularMarketPrice')))
        result['valuation'] = {
            'forward_pe': _safe_round(info.get('forwardPE')),
            'trailing_pe': _safe_round(info.get('trailingPE')),
            'peg_ratio': _safe_round(info.get('pegRatio')),
            'price_to_book': _safe_round(info.get('priceToBook')),
            'price_to_sales': _safe_round(info.get('priceToSalesTrailing12Months')),
            'ev_to_ebitda': _safe_round(info.get('enterpriseToEbitda')),
            'ev_to_revenue': _safe_round(info.get('enterpriseToRevenue')),
            'enterprise_value': enterprise_value,
            'market_cap': info.get('marketCap'),
            'price': _current_price,
            'current_price': _current_price,
            'forward_eps': _safe_round(info.get('forwardEps')),
            'diluted_eps_ttm': _safe_round(info.get('trailingEps')),
            'book_value_per_share': _safe_round(info.get('bookValue')),
            'ttm_revenue': info.get('totalRevenue'),
            'ttm_ebitda': info.get('ebitda'),
            'ttm_fcf': info.get('freeCashflow'),
            'fifty_two_week_high': _safe_round(info.get('fiftyTwoWeekHigh')),
            'fifty_two_week_low': _safe_round(info.get('fiftyTwoWeekLow')),
            'beta': _safe_round(info.get('beta')),
            'dividend_yield': _pct(info.get('dividendYield')),
            'payout_ratio': _pct(info.get('payoutRatio')),
        }

        # Compute EV/FCF from info or statements
        ev_to_fcf = None
        fcf_info = info.get('freeCashflow')
        if enterprise_value and fcf_info and fcf_info != 0:
            ev_to_fcf = _safe_round(enterprise_value / fcf_info)
        result['valuation']['ev_to_fcf'] = ev_to_fcf

        # ── Financial Analysis ─────────────────────────────
        # Profitability
        profitability = {
            'gross_margin': _pct(info.get('grossMargins')),
            'operating_margin': _pct(info.get('operatingMargins')),
            'ebitda_margin': None,
            'fcf_margin': None,
            'net_margin': _pct(info.get('profitMargins')),
        }

        # Compute EBITDA margin from statements
        if result.get('income_statement'):
            ebitda_0 = result['income_statement']['ebitda'][0] if result['income_statement']['ebitda'] else None
            rev_0 = result['income_statement']['total_revenue'][0] if result['income_statement']['total_revenue'] else None
            if ebitda_0 and rev_0 and rev_0 != 0:
                profitability['ebitda_margin'] = _safe_round(ebitda_0 / rev_0 * 100, 2)

        # Compute FCF margin
        if result.get('cash_flow') and result.get('income_statement'):
            fcf_0 = result['cash_flow']['free_cash_flow'][0] if result['cash_flow']['free_cash_flow'] else None
            rev_0 = result['income_statement']['total_revenue'][0] if result['income_statement']['total_revenue'] else None
            if fcf_0 and rev_0 and rev_0 != 0:
                profitability['fcf_margin'] = _safe_round(fcf_0 / rev_0 * 100, 2)

        # Returns
        returns = {
            'roe': _pct(info.get('returnOnEquity')),
            'roa': _pct(info.get('returnOnAssets')),
            'roic': None,
        }

        # Compute ROIC = NOPAT / Invested Capital
        if result.get('income_statement') and result.get('balance_sheet'):
            op_inc = result['income_statement']['operating_income'][0] if result['income_statement']['operating_income'] else None
            tax_prov = result['income_statement']['tax_provision'][0] if result['income_statement']['tax_provision'] else None
            pretax = result['income_statement']['pretax_income'][0] if result['income_statement']['pretax_income'] else None
            invested_cap = result['balance_sheet']['invested_capital'][0] if result['balance_sheet']['invested_capital'] else None

            if op_inc and invested_cap and invested_cap != 0:
                # Effective tax rate
                tax_rate = 0.21  # default
                if tax_prov and pretax and pretax != 0:
                    tax_rate = max(0, min(1, tax_prov / pretax))
                nopat = op_inc * (1 - tax_rate)
                # Annualize (quarterly data)
                returns['roic'] = _safe_round((nopat * 4) / invested_cap * 100, 2)

        # Turnover / leverage
        turnover = {
            'asset_turnover': None,
            'debt_to_equity': _safe_round(info.get('debtToEquity'), 2),
            'current_ratio': _safe_round(info.get('currentRatio'), 2),
        }

        # Compute asset turnover = Annualized Revenue / Total Assets
        if (result.get('income_statement') and result.get('balance_sheet') and
                result['income_statement']['total_revenue'] and
                result['balance_sheet']['total_assets']):
            rev = result['income_statement']['total_revenue'][0]
            assets = result['balance_sheet']['total_assets'][0]
            if rev and assets and assets != 0:
                turnover['asset_turnover'] = _safe_round((rev * 4) / assets, 4)

        # Growth
        growth = {
            'eps_growth': _pct(info.get('earningsGrowth')),
            'revenue_growth': _pct(info.get('revenueGrowth')),
            'earnings_quarterly_growth': _pct(info.get('earningsQuarterlyGrowth')),
        }

        # Compute QoQ revenue growth from statements
        if result.get('income_statement') and result['income_statement']['total_revenue']:
            revs = result['income_statement']['total_revenue']
            if len(revs) >= 2 and revs[0] is not None and revs[1] is not None and revs[1] != 0:
                growth['revenue_qoq'] = _safe_round((revs[0] - revs[1]) / abs(revs[1]) * 100, 2)
            else:
                growth['revenue_qoq'] = None

            # YoY if 5 quarters available
            if len(revs) >= 5 and revs[0] is not None and revs[4] is not None and revs[4] != 0:
                growth['revenue_yoy'] = _safe_round((revs[0] - revs[4]) / abs(revs[4]) * 100, 2)
            else:
                growth['revenue_yoy'] = None
        else:
            growth['revenue_qoq'] = None
            growth['revenue_yoy'] = None

        result['financial_analysis'] = {
            'profitability': profitability,
            'returns': returns,
            'turnover': turnover,
            'growth': growth,
        }

        # ── Revenue Segments ──────────────────────────────
        # yfinance does not provide segment data; SEC EDGAR is the source for this.
        result['revenue_segments'] = None
        result['revenue_segments_note'] = 'Revenue segment data not available from Yahoo Finance. Use SEC filings source.'

        return result

    except Exception as e:
        return {
            'ticker': ticker_symbol,
            'error': str(e),
            'traceback': traceback.format_exc(),
        }


def get_top20_financials(tickers=None):
    """
    Fetch financial data for the top 20 (or custom) companies.

    Args:
        tickers: optional list of ticker symbols. Defaults to TOP_20_TICKERS.

    Returns dict:
        {
            'companies': { 'AAPL': {...}, 'MSFT': {...}, ... },
            'tickers': ['AAPL', 'MSFT', ...],
            'successful': 18,
            'failed': 2,
            'source': 'Yahoo Finance',
            'latest_date': '2026-03-01',
        }
    """
    if tickers is None:
        tickers = TOP_20_TICKERS

    companies = {}
    errors = []

    for symbol in tickers:
        print(f"    Fetching {symbol}...")
        data = get_company_financials_yahoo(symbol)
        companies[symbol] = data
        if 'error' in data:
            errors.append(f"{symbol}: {data['error']}")

    return {
        'companies': companies,
        'tickers': list(tickers),
        'count': len(tickers),
        'successful': len(tickers) - len(errors),
        'failed': len(errors),
        'errors': errors,
        'source': 'Yahoo Finance',
        'latest_date': datetime.now().strftime('%Y-%m-%d'),
    }


# ── Finnhub (Optional, requires API key) ───────────────────────────

def get_company_financials_finnhub(ticker_symbol, api_key=None):
    """
    Fetch financial data from Finnhub. Requires `finnhub-python` and a free API key.

    To enable:
        pip install finnhub-python
        Set FINNHUB_API_KEY env var or pass api_key parameter.

    Free tier: 60 calls/minute.
    """
    try:
        import finnhub
    except ImportError:
        return {'error': 'finnhub-python not installed. Run: pip install finnhub-python'}

    if api_key is None:
        import os
        api_key = os.environ.get('FINNHUB_API_KEY')
    if not api_key:
        return {'error': 'FINNHUB_API_KEY not set. Get free key at https://finnhub.io'}

    try:
        client = finnhub.Client(api_key=api_key)
        # Fetch basic financials
        metrics = client.company_basic_financials(ticker_symbol, 'all')
        if not metrics or 'metric' not in metrics:
            return {'error': f'No Finnhub data for {ticker_symbol}'}

        m = metrics.get('metric', {})
        return {
            'ticker': ticker_symbol,
            'source': 'Finnhub',
            'valuation': {
                'trailing_pe': m.get('peBasicExclExtraTTM'),
                'price_to_book': m.get('pbQuarterly'),
                'price_to_sales': m.get('psTTM'),
            },
            'profitability': {
                'gross_margin': m.get('grossMarginTTM'),
                'operating_margin': m.get('operatingMarginTTM'),
                'net_margin': m.get('netProfitMarginTTM'),
                'roe': m.get('roeTTM'),
                'roa': m.get('roaTTM'),
            },
            'growth': {
                'revenue_growth': m.get('revenueGrowthTTMYoy'),
                'eps_growth': m.get('epsGrowthTTMYoy'),
            },
        }
    except Exception as e:
        return {'error': f'Finnhub error for {ticker_symbol}: {str(e)}'}


# ── Simfin (Optional, requires API key) ────────────────────────────

def get_company_financials_simfin(ticker_symbol, api_key=None):
    """
    Fetch financial data from Simfin. Requires `simfin` and a free API key.

    To enable:
        pip install simfin
        Set SIMFIN_API_KEY env var or pass api_key parameter.

    Free tier: 2,000 API calls/day.
    """
    try:
        import simfin as sf
    except ImportError:
        return {'error': 'simfin not installed. Run: pip install simfin'}

    if api_key is None:
        import os
        api_key = os.environ.get('SIMFIN_API_KEY')
    if not api_key:
        return {'error': 'SIMFIN_API_KEY not set. Get free key at https://simfin.com'}

    try:
        sf.set_api_key(api_key)
        sf.set_data_dir('~/.simfin_data/')

        # Load income statement
        df_income = sf.load_income(variant='quarterly', market='us')
        df_balance = sf.load_balance(variant='quarterly', market='us')
        df_cashflow = sf.load_cashflow(variant='quarterly', market='us')

        # Filter for the ticker
        inc = df_income.loc[df_income.index.get_level_values('Ticker') == ticker_symbol] if ticker_symbol in df_income.index.get_level_values('Ticker') else pd.DataFrame()
        bal = df_balance.loc[df_balance.index.get_level_values('Ticker') == ticker_symbol] if ticker_symbol in df_balance.index.get_level_values('Ticker') else pd.DataFrame()
        cf = df_cashflow.loc[df_cashflow.index.get_level_values('Ticker') == ticker_symbol] if ticker_symbol in df_cashflow.index.get_level_values('Ticker') else pd.DataFrame()

        if inc.empty:
            return {'error': f'No Simfin data for {ticker_symbol}'}

        return {
            'ticker': ticker_symbol,
            'source': 'Simfin',
            'income_statement_available': not inc.empty,
            'balance_sheet_available': not bal.empty,
            'cash_flow_available': not cf.empty,
            'note': 'Simfin data loaded. Parse specific fields as needed.',
        }
    except Exception as e:
        return {'error': f'Simfin error for {ticker_symbol}: {str(e)}'}


# ── Tiger Brokers (Optional, requires funded account) ──────────────

def get_company_financials_tiger(ticker_symbol, client=None):
    """
    Fetch financial data from Tiger Brokers API. Requires `tigeropen` SDK
    and a funded Tiger Brokers account.

    To enable:
        pip install tigeropen
        Configure Tiger API credentials (private key, tiger_id, account).

    See: https://quant.itigerup.com/openapi/en/python/overview/introduction.html
    """
    try:
        from tigeropen.quote.quote_client import QuoteClient
    except ImportError:
        return {'error': 'tigeropen not installed. Run: pip install tigeropen'}

    if client is None:
        return {
            'error': 'Tiger Brokers client not configured. Requires funded account + API credentials.',
            'setup_guide': 'https://quant.itigerup.com/openapi/en/python/overview/introduction.html',
        }

    try:
        # Tiger API: get_financial_report(symbols, market, fields, period_type)
        report = client.get_financial_report(
            symbols=[ticker_symbol],
            market='US',
            fields=['revenue', 'net_income', 'total_assets', 'total_liabilities'],
            period_type='quarter',
        )
        return {
            'ticker': ticker_symbol,
            'source': 'Tiger Brokers',
            'data': report,
        }
    except Exception as e:
        return {'error': f'Tiger API error for {ticker_symbol}: {str(e)}'}


# ── Parallel Multi-Source Extraction ────────────────────────────────

def get_financials_all_sources(ticker_symbol, sources=None):
    """
    Fetch financial data from multiple sources for comparison.

    Args:
        ticker_symbol: stock ticker
        sources: list of source names to use. Default: ['yahoo']
                 Options: 'yahoo', 'sec', 'finnhub', 'simfin', 'tiger'

    Returns dict keyed by source name.
    """
    if sources is None:
        sources = ['yahoo']

    results = {}

    if 'yahoo' in sources:
        results['yahoo'] = get_company_financials_yahoo(ticker_symbol)

    if 'sec' in sources:
        try:
            from data_extractors.sec_extractor import get_company_financials_sec
            results['sec'] = get_company_financials_sec(ticker_symbol)
        except ImportError:
            results['sec'] = {'error': 'SEC extractor module not available'}

    if 'finnhub' in sources:
        results['finnhub'] = get_company_financials_finnhub(ticker_symbol)

    if 'simfin' in sources:
        results['simfin'] = get_company_financials_simfin(ticker_symbol)

    if 'tiger' in sources:
        results['tiger'] = get_company_financials_tiger(ticker_symbol)

    return results
