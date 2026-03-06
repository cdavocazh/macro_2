"""
Main data aggregator that consolidates all macroeconomic indicators.
Supports local caching for faster dashboard startup and CSV export.
"""
from data_extractors import (
    yfinance_extractors,
    openbb_extractors,
    fred_extractors,
    shiller_extractor,
    web_scrapers,
    commodities_extractors,
    cot_extractor,
    japan_yield_extractor,
    equity_financials_extractor,
    global_yields_extractor,
    yield_curve_extractor,
)
from utils.helpers import save_to_cache, load_from_cache, get_cache_timestamp, export_indicators_to_csv
from datetime import datetime
import traceback

CACHE_KEY = 'all_indicators'
CACHE_DIR = 'data_cache'
CACHE_MAX_AGE_HOURS = 24


class MacroIndicatorAggregator:
    """Aggregates all macroeconomic indicators from various sources."""

    def __init__(self):
        self.indicators = {}
        self.last_update = None
        self.errors = []
        self.loaded_from_cache = False

    def load_from_local_cache(self):
        """
        Try to load indicators from local cache.
        Returns True if cache was loaded, False otherwise.
        """
        cached = load_from_cache(CACHE_KEY, cache_dir=CACHE_DIR, max_age_hours=CACHE_MAX_AGE_HOURS)
        if cached is not None:
            self.indicators = cached
            self.last_update = get_cache_timestamp(CACHE_KEY, cache_dir=CACHE_DIR)
            self.loaded_from_cache = True
            self.errors = []
            print(f"Loaded {len(self.indicators)} indicators from local cache (saved {self.last_update})")
            return True
        return False

    def _save_to_local_cache(self):
        """Save current indicators to local cache."""
        try:
            save_to_cache(self.indicators, CACHE_KEY, cache_dir=CACHE_DIR)
            print(f"Saved {len(self.indicators)} indicators to local cache")
        except Exception as e:
            print(f"Warning: failed to save cache: {e}")

    def fetch_all_indicators(self):
        """Fetch all 62 macroeconomic indicators and save to local cache."""
        self.indicators = {}
        self.errors = []
        self.last_update = datetime.now()
        self.loaded_from_cache = False

        print("Fetching macroeconomic indicators...")

        # 1. S&P 500 Forward P/E (MacroMicro)
        print("  [1/62] Fetching S&P 500 Forward P/E...")
        self._fetch_with_error_handling(
            '1_sp500_forward_pe',
            web_scrapers.get_sp500_forward_pe_macromicro
        )

        # 2. Russell 2000 Value & Growth Indices
        print("  [2/62] Fetching Russell 2000 indices...")
        self._fetch_with_error_handling(
            '2_russell_2000',
            yfinance_extractors.get_russell_2000_indices
        )

        # 3. S&P 500 Trailing P/E and P/B
        print("  [3/62] Fetching S&P 500 trailing P/E and P/B...")
        self._fetch_with_error_handling(
            '3_sp500_fundamentals',
            openbb_extractors.get_sp500_fundamentals
        )

        # 4. S&P 500 Put/Call Ratio
        print("  [4/62] Fetching S&P 500 Put/Call Ratio...")
        self._fetch_with_error_handling(
            '4_put_call_ratio',
            web_scrapers.get_sp500_put_call_ratio
        )

        # 5. SPX Call Skew
        print("  [5/62] Fetching SPX Call Skew...")
        self._fetch_with_error_handling(
            '5_spx_call_skew',
            web_scrapers.get_spx_call_skew
        )

        # 6a. S&P 500 / 200MA Ratio
        print("  [6a/62] Fetching S&P 500 / 200MA ratio...")
        self._fetch_with_error_handling(
            '6a_sp500_to_ma200',
            yfinance_extractors.get_sp500_data
        )

        # 6b. S&P 500 Market Cap / US GDP
        print("  [6b/62] Fetching Market Cap / GDP ratio...")
        self._fetch_with_error_handling(
            '6b_marketcap_to_gdp',
            fred_extractors.calculate_sp500_marketcap_to_gdp
        )

        # 7. Shiller CAPE Ratio
        print("  [7/62] Fetching Shiller CAPE Ratio...")
        self._fetch_with_error_handling(
            '7_shiller_cape',
            shiller_extractor.get_shiller_cape
        )

        # 8. VIX
        print("  [8/62] Fetching VIX...")
        self._fetch_with_error_handling(
            '8_vix',
            yfinance_extractors.get_vix
        )

        # 8b. VIX/MOVE Ratio
        print("  [8b/62] Fetching VIX/MOVE ratio...")
        self._fetch_with_error_handling(
            '8b_vix_move_ratio',
            yfinance_extractors.calculate_vix_move_ratio
        )

        # 9. MOVE Index
        print("  [9/62] Fetching MOVE Index...")
        self._fetch_with_error_handling(
            '9_move_index',
            yfinance_extractors.get_move_index
        )

        # 10. DXY (U.S. Dollar Index)
        print("  [10/62] Fetching DXY...")
        self._fetch_with_error_handling(
            '10_dxy',
            yfinance_extractors.get_dxy
        )

        # 11. 10-Year Treasury Yield
        print("  [11/62] Fetching 10-Year Treasury Yield...")
        self._fetch_with_error_handling(
            '11_10y_yield',
            fred_extractors.get_10y_treasury_yield
        )

        # 12. ISM Manufacturing PMI
        print("  [12/62] Fetching ISM Manufacturing PMI...")
        self._fetch_with_error_handling(
            '12_ism_pmi',
            fred_extractors.get_ism_pmi
        )

        # 13. Gold Futures
        print("  [13/62] Fetching Gold futures...")
        self._fetch_with_error_handling(
            '13_gold',
            commodities_extractors.get_gold
        )

        # 14. Silver Futures
        print("  [14/62] Fetching Silver futures...")
        self._fetch_with_error_handling(
            '14_silver',
            commodities_extractors.get_silver
        )

        # 15. Crude Oil Futures
        print("  [15/62] Fetching Crude Oil futures...")
        self._fetch_with_error_handling(
            '15_crude_oil',
            commodities_extractors.get_crude_oil
        )

        # 16. Copper Futures
        print("  [16/62] Fetching Copper futures...")
        self._fetch_with_error_handling(
            '16_copper',
            commodities_extractors.get_copper
        )

        # 17. ES Futures (S&P 500 E-mini)
        print("  [17/62] Fetching ES futures (S&P 500 E-mini)...")
        self._fetch_with_error_handling(
            '17_es_futures',
            yfinance_extractors.get_es_futures
        )

        # 18. RTY Futures (Russell 2000 E-mini)
        print("  [18/62] Fetching RTY futures (Russell 2000 E-mini)...")
        self._fetch_with_error_handling(
            '18_rty_futures',
            yfinance_extractors.get_rty_futures
        )

        # 19. S&P 500 Breadth (Advance/Decline)
        print("  [19/62] Fetching S&P 500 market breadth...")
        self._fetch_with_error_handling(
            '19_sp500_breadth',
            web_scrapers.get_sp500_breadth_indicator
        )

        # 20. JPY Exchange Rate
        print("  [20/62] Fetching JPY exchange rate...")
        self._fetch_with_error_handling(
            '20_jpy',
            yfinance_extractors.get_jpy_exchange_rate
        )

        # 21. All Commodities (for convenience)
        print("  [21/62] Fetching all commodities...")
        self._fetch_with_error_handling(
            '21_all_commodities',
            commodities_extractors.get_all_commodities
        )

        # 22. CFTC COT Positioning (Gold & Silver)
        print("  [22/62] Fetching CFTC COT positioning data (Gold & Silver)...")
        self._fetch_with_error_handling(
            '22_cot_positioning',
            cot_extractor.get_cot_gold_silver
        )

        # 23. TGA Balance
        print("  [23/62] Fetching TGA Balance...")
        self._fetch_with_error_handling(
            '23_tga_balance',
            fred_extractors.get_tga_balance
        )

        # 24. Fed Net Liquidity
        print("  [24/62] Fetching Fed Net Liquidity...")
        self._fetch_with_error_handling(
            '24_net_liquidity',
            fred_extractors.get_fed_net_liquidity
        )

        # 25. SOFR
        print("  [25/62] Fetching SOFR...")
        self._fetch_with_error_handling(
            '25_sofr',
            fred_extractors.get_sofr
        )

        # 26. US 2-Year Treasury Yield
        print("  [26/62] Fetching US 2-Year Treasury Yield...")
        self._fetch_with_error_handling(
            '26_us_2y_yield',
            fred_extractors.get_us_2y_yield
        )

        # 27. Japan 2-Year Government Bond Yield
        print("  [27/62] Fetching Japan 2Y Yield...")
        self._fetch_with_error_handling(
            '27_japan_2y_yield',
            japan_yield_extractor.get_japan_2y_yield
        )

        # 28. US 2Y - Japan 2Y Yield Spread
        print("  [28/62] Fetching US2Y-JP2Y Spread...")
        self._fetch_with_error_handling(
            '28_us2y_jp2y_spread',
            japan_yield_extractor.get_us2y_jp2y_spread
        )

        # 29. Large-cap Equity Financials (Top 20)
        print("  [29/62] Fetching Large-cap Equity Financials (Top 20)...")
        self._fetch_with_error_handling(
            '29_equity_financials',
            equity_financials_extractor.get_top20_financials
        )

        # --- Rates & Credit indicators (v2.2.0) ---

        # 30. Germany 10Y Yield
        print("  [30/62] Fetching Germany 10Y Yield...")
        self._fetch_with_error_handling(
            '30_germany_10y',
            global_yields_extractor.get_germany_10y_yield
        )

        # 31. UK 10Y Yield
        print("  [31/62] Fetching UK 10Y Yield...")
        self._fetch_with_error_handling(
            '31_uk_10y',
            global_yields_extractor.get_uk_10y_yield
        )

        # 32. China 10Y Yield
        print("  [32/62] Fetching China 10Y Yield...")
        self._fetch_with_error_handling(
            '32_china_10y',
            global_yields_extractor.get_china_10y_yield
        )

        # 33. Yield Curve (2s10s Spread + Regime Classification)
        print("  [33/62] Fetching Yield Curve & Regime...")
        self._fetch_with_error_handling(
            '33_yield_curve',
            yield_curve_extractor.get_yield_curve_data
        )

        # 34. HY Credit Spread (OAS)
        print("  [34/62] Fetching HY Credit Spread (OAS)...")
        self._fetch_with_error_handling(
            '34_hy_oas',
            fred_extractors.get_hy_credit_spread
        )

        # 35. Breakeven Inflation (5Y + 10Y)
        print("  [35/62] Fetching Breakeven Inflation...")
        self._fetch_with_error_handling(
            '35_breakeven_inflation',
            fred_extractors.get_breakeven_inflation
        )

        # 36. 10Y Real Yield (TIPS)
        print("  [36/62] Fetching 10Y Real Yield (TIPS)...")
        self._fetch_with_error_handling(
            '36_real_yield',
            fred_extractors.get_real_yield_10y
        )

        # 37. Chicago Fed NFCI
        print("  [37/62] Fetching Chicago Fed NFCI...")
        self._fetch_with_error_handling(
            '37_nfci',
            fred_extractors.get_nfci
        )

        # 38. Fed Funds Rate
        print("  [38/62] Fetching Fed Funds Rate...")
        self._fetch_with_error_handling(
            '38_fed_funds',
            fred_extractors.get_fed_funds_rate
        )

        # 39. Initial Jobless Claims
        print("  [39/62] Fetching Initial Jobless Claims...")
        self._fetch_with_error_handling(
            '39_initial_claims',
            fred_extractors.get_initial_jobless_claims
        )

        # 40. Unemployment Rate
        print("  [40/62] Fetching Unemployment Rate...")
        self._fetch_with_error_handling(
            '40_unemployment',
            fred_extractors.get_unemployment_rate
        )

        # 41. Core CPI + Core PCE (YoY%)
        print("  [41/62] Fetching Core Inflation (CPI + PCE)...")
        self._fetch_with_error_handling(
            '41_core_inflation',
            fred_extractors.get_core_inflation
        )

        # --- Economic Activity & Extended indicators (v2.3.0) ---

        # 42. Nonfarm Payrolls
        print("  [42/62] Fetching Nonfarm Payrolls...")
        self._fetch_with_error_handling(
            '42_nfp',
            fred_extractors.get_nonfarm_payrolls
        )

        # 43. ISM Services PMI
        print("  [43/62] Fetching ISM Services PMI...")
        self._fetch_with_error_handling(
            '43_ism_services',
            global_yields_extractor.get_ism_services_pmi
        )

        # 44. Consumer Sentiment (UMich)
        print("  [44/62] Fetching Consumer Sentiment...")
        self._fetch_with_error_handling(
            '44_consumer_sentiment',
            fred_extractors.get_consumer_sentiment
        )

        # 45. IG Credit Spread (OAS)
        print("  [45/62] Fetching IG Credit Spread...")
        self._fetch_with_error_handling(
            '45_ig_oas',
            fred_extractors.get_ig_credit_spread
        )

        # 46. Sahm Rule Recession Indicator
        print("  [46/62] Fetching Sahm Rule...")
        self._fetch_with_error_handling(
            '46_sahm_rule',
            fred_extractors.get_sahm_rule
        )

        # 47. M2 Money Supply
        print("  [47/62] Fetching M2 Money Supply...")
        self._fetch_with_error_handling(
            '47_m2',
            fred_extractors.get_m2_money_supply
        )

        # 48. JOLTS Job Openings
        print("  [48/62] Fetching JOLTS Job Openings...")
        self._fetch_with_error_handling(
            '48_jolts',
            fred_extractors.get_jolts_openings
        )

        # 49. Continuing Claims
        print("  [49/62] Fetching Continuing Claims...")
        self._fetch_with_error_handling(
            '49_continuing_claims',
            fred_extractors.get_continuing_claims
        )

        # 50. Retail Sales
        print("  [50/62] Fetching Retail Sales...")
        self._fetch_with_error_handling(
            '50_retail_sales',
            fred_extractors.get_retail_sales
        )

        # 51. Housing Starts
        print("  [51/62] Fetching Housing Starts...")
        self._fetch_with_error_handling(
            '51_housing_starts',
            fred_extractors.get_housing_starts
        )

        # 52. PPI (Producer Price Index YoY%)
        print("  [52/62] Fetching PPI...")
        self._fetch_with_error_handling(
            '52_ppi',
            fred_extractors.get_ppi
        )

        # 53. Headline CPI (YoY%)
        print("  [53/62] Fetching Headline CPI...")
        self._fetch_with_error_handling(
            '53_headline_cpi',
            fred_extractors.get_headline_cpi
        )

        # 54. Major FX Pairs (EUR/USD, GBP/USD, EUR/JPY)
        print("  [54/62] Fetching Major FX Pairs...")
        self._fetch_with_error_handling(
            '54_fx_pairs',
            yfinance_extractors.get_major_fx_pairs
        )

        # 55. SPY/RSP Market Concentration
        print("  [55/62] Fetching Market Concentration (SPY/RSP)...")
        self._fetch_with_error_handling(
            '55_market_concentration',
            yfinance_extractors.get_market_concentration
        )

        # 56. Natural Gas
        print("  [56/62] Fetching Natural Gas...")
        self._fetch_with_error_handling(
            '56_natural_gas',
            commodities_extractors.get_natural_gas
        )

        # 57. Copper/Gold Ratio
        print("  [57/62] Fetching Copper/Gold Ratio...")
        self._fetch_with_error_handling(
            '57_cu_au_ratio',
            commodities_extractors.get_copper_gold_ratio
        )

        # 58. Bank Reserves
        print("  [58/62] Fetching Bank Reserves...")
        self._fetch_with_error_handling(
            '58_bank_reserves',
            fred_extractors.get_bank_reserves
        )

        # 59. Industrial Production
        print("  [59/62] Fetching Industrial Production...")
        self._fetch_with_error_handling(
            '59_industrial_production',
            fred_extractors.get_industrial_production
        )

        # 60. Quits Rate (JOLTS)
        print("  [60/62] Fetching Quits Rate...")
        self._fetch_with_error_handling(
            '60_quits_rate',
            fred_extractors.get_quits_rate
        )

        # 61. 5Y Treasury Yield
        print("  [61/62] Fetching 5Y Treasury Yield...")
        self._fetch_with_error_handling(
            '61_5y_yield',
            fred_extractors.get_5y_treasury_yield
        )

        # 62. SLOOS Lending Standards (quarterly, may be delayed)
        print("  [62/62] Fetching SLOOS Lending Standards...")
        self._fetch_with_error_handling('62_sloos', fred_extractors.get_sloos_lending)

        print(f"\nCompleted! Last update: {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

        if self.errors:
            print(f"\nEncountered {len(self.errors)} errors during fetch:")
            for error in self.errors:
                print(f"  - {error}")

        # Save to local cache after fetching
        self._save_to_local_cache()

        return self.indicators

    def export_to_csv(self, output_dir='data_export'):
        """Export current indicators to CSV files."""
        if not self.indicators:
            return {'error': 'No data to export. Fetch or load data first.'}
        return export_indicators_to_csv(self.indicators, output_dir=output_dir)

    def _fetch_with_error_handling(self, indicator_key, fetch_function):
        """Fetch indicator with error handling."""
        try:
            result = fetch_function()
            self.indicators[indicator_key] = result

            if isinstance(result, dict) and 'error' in result:
                self.errors.append(f"{indicator_key}: {result['error']}")
        except Exception as e:
            error_msg = f"{indicator_key}: {str(e)}"
            self.errors.append(error_msg)
            self.indicators[indicator_key] = {
                'error': str(e),
                'traceback': traceback.format_exc()
            }

    def get_summary(self):
        """Get a summary of all indicators."""
        summary = {
            'last_update': self.last_update.strftime('%Y-%m-%d %H:%M:%S') if self.last_update else 'Never',
            'loaded_from_cache': self.loaded_from_cache,
            'total_indicators': 17,
            'successful': 0,
            'failed': 0,
            'indicators': {}
        }

        indicator_names = {
            '1_sp500_forward_pe': 'S&P 500 Forward P/E',
            '2_russell_2000': 'Russell 2000 Indices',
            '3_sp500_fundamentals': 'S&P 500 Trailing P/E & P/B',
            '4_put_call_ratio': 'S&P 500 Put/Call Ratio',
            '5_spx_call_skew': 'SPX Call Skew',
            '6a_sp500_to_ma200': 'S&P 500 / 200MA',
            '6b_marketcap_to_gdp': 'Market Cap / GDP',
            '7_shiller_cape': 'Shiller CAPE',
            '8_vix': 'VIX',
            '8b_vix_move_ratio': 'VIX/MOVE Ratio',
            '9_move_index': 'MOVE Index',
            '10_dxy': 'DXY (US Dollar Index)',
            '11_10y_yield': '10-Year Treasury Yield',
            '12_ism_pmi': 'ISM Manufacturing PMI',
            '13_gold': 'Gold Futures',
            '14_silver': 'Silver Futures',
            '15_crude_oil': 'Crude Oil Futures',
            '16_copper': 'Copper Futures',
            '17_all_commodities': 'All Commodities',
            '22_cot_positioning': 'CFTC COT Positioning (Gold & Silver)',
            '23_tga_balance': 'TGA Balance',
            '24_net_liquidity': 'Fed Net Liquidity',
            '25_sofr': 'SOFR',
            '26_us_2y_yield': 'US 2-Year Treasury Yield',
            '27_japan_2y_yield': 'Japan 2-Year Government Bond Yield',
            '28_us2y_jp2y_spread': 'US 2Y - Japan 2Y Yield Spread',
            '29_equity_financials': 'Large-cap Equity Financials (Top 20)',
        }

        for key, name in indicator_names.items():
            if key in self.indicators:
                data = self.indicators[key]
                if isinstance(data, dict) and 'error' in data:
                    summary['failed'] += 1
                    summary['indicators'][name] = {
                        'status': 'Failed',
                        'error': data['error']
                    }
                else:
                    summary['successful'] += 1
                    summary['indicators'][name] = {
                        'status': 'Success',
                        'data': data
                    }
            else:
                summary['failed'] += 1
                summary['indicators'][name] = {
                    'status': 'Not fetched'
                }

        return summary

    def get_indicator(self, indicator_key):
        """Get a specific indicator by key."""
        return self.indicators.get(indicator_key, {'error': 'Indicator not found'})


# Singleton instance
_aggregator_instance = None


def get_aggregator():
    """Get or create the aggregator singleton instance."""
    global _aggregator_instance
    if _aggregator_instance is None:
        _aggregator_instance = MacroIndicatorAggregator()
    return _aggregator_instance
