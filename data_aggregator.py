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
    hyperliquid_extractor,
)
from utils.helpers import save_to_cache, load_from_cache, get_cache_timestamp, export_indicators_to_csv
from datetime import datetime
import json
import os
import traceback

CACHE_KEY = 'all_indicators'
CACHE_DIR = 'data_cache'
CACHE_MAX_AGE_HOURS = 24
PROGRESS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), CACHE_DIR, '.extract_progress.json'
)


def _write_progress(current: int, total: int, label: str, status: str = "running"):
    """Write extraction progress to a JSON file for the dashboard to read."""
    try:
        os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({
                "current": current,
                "total": total,
                "label": label,
                "status": status,  # "running", "done", "error"
                "timestamp": datetime.now().isoformat(),
            }, f)
    except Exception:
        pass  # best-effort, don't break extraction


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
        cached = load_from_cache(CACHE_KEY, cache_dir=CACHE_DIR, max_age_hours=CACHE_MAX_AGE_HOURS,
                                 fallback_stale=True)
        if cached is not None:
            self.indicators = cached
            self.last_update = get_cache_timestamp(CACHE_KEY, cache_dir=CACHE_DIR)
            self.loaded_from_cache = True
            self.errors = []
            print(f"Loaded {len(self.indicators)} indicators from local cache (saved {self.last_update})")
            return True
        return False

    def reload_if_stale(self):
        """Reload from cache file if it's newer than in-memory data.

        Uses os.path.getmtime() (~0.1ms syscall) to avoid parsing the 7MB
        JSON on every Streamlit rerun.  Only re-reads when the file is
        actually newer than what is currently loaded.
        """
        import os
        cache_file = os.path.join(CACHE_DIR, f"{CACHE_KEY}.json")

        if not os.path.exists(cache_file):
            return False

        try:
            file_mtime = datetime.fromtimestamp(os.path.getmtime(cache_file))
        except OSError:
            return False

        # No data yet — always load
        if not self.indicators or self.last_update is None:
            return self.load_from_local_cache()

        # File is newer than what we have — reload
        if file_mtime > self.last_update:
            print(f"Cache file is newer ({file_mtime}) than in-memory ({self.last_update}). Reloading...")
            return self.load_from_local_cache()

        return False

    def _save_to_local_cache(self):
        """Save current indicators to local cache."""
        try:
            save_to_cache(self.indicators, CACHE_KEY, cache_dir=CACHE_DIR)
            print(f"Saved {len(self.indicators)} indicators to local cache")
        except Exception as e:
            print(f"Warning: failed to save cache: {e}")

    def fetch_all_indicators(self):
        """Fetch all 82 macroeconomic indicators and save to local cache."""
        self.indicators = {}
        self.errors = []
        self.last_update = datetime.now()
        self.loaded_from_cache = False
        self._indicator_count = 0

        _write_progress(0, 82, "Starting extraction...", "running")
        print("Fetching macroeconomic indicators...")

        # 1. S&P 500 Forward P/E (MacroMicro)
        print("  [1/82] Fetching S&P 500 Forward P/E...")
        self._fetch_with_error_handling(
            '1_sp500_forward_pe',
            web_scrapers.get_sp500_forward_pe_macromicro
        )

        # 2. Russell 2000 Value & Growth Indices
        print("  [2/82] Fetching Russell 2000 indices...")
        self._fetch_with_error_handling(
            '2_russell_2000',
            yfinance_extractors.get_russell_2000_indices
        )

        # 3. S&P 500 Trailing P/E and P/B
        print("  [3/82] Fetching S&P 500 trailing P/E and P/B...")
        self._fetch_with_error_handling(
            '3_sp500_fundamentals',
            openbb_extractors.get_sp500_fundamentals
        )

        # 4. S&P 500 Put/Call Ratio
        print("  [4/82] Fetching S&P 500 Put/Call Ratio...")
        self._fetch_with_error_handling(
            '4_put_call_ratio',
            web_scrapers.get_sp500_put_call_ratio
        )

        # 5. SPX Call Skew
        print("  [5/82] Fetching SPX Call Skew...")
        self._fetch_with_error_handling(
            '5_spx_call_skew',
            web_scrapers.get_spx_call_skew
        )

        # 6a. S&P 500 / 200MA Ratio
        print("  [6a/82] Fetching S&P 500 / 200MA ratio...")
        self._fetch_with_error_handling(
            '6a_sp500_to_ma200',
            yfinance_extractors.get_sp500_data
        )

        # 6b. S&P 500 Market Cap / US GDP
        print("  [6b/82] Fetching Market Cap / GDP ratio...")
        self._fetch_with_error_handling(
            '6b_marketcap_to_gdp',
            fred_extractors.calculate_sp500_marketcap_to_gdp
        )

        # 7. Shiller CAPE Ratio
        print("  [7/82] Fetching Shiller CAPE Ratio...")
        self._fetch_with_error_handling(
            '7_shiller_cape',
            shiller_extractor.get_shiller_cape
        )

        # 8. VIX
        print("  [8/82] Fetching VIX...")
        self._fetch_with_error_handling(
            '8_vix',
            yfinance_extractors.get_vix
        )

        # 8b. VIX/MOVE Ratio
        print("  [8b/82] Fetching VIX/MOVE ratio...")
        self._fetch_with_error_handling(
            '8b_vix_move_ratio',
            yfinance_extractors.calculate_vix_move_ratio
        )

        # 9. MOVE Index
        print("  [9/82] Fetching MOVE Index...")
        self._fetch_with_error_handling(
            '9_move_index',
            yfinance_extractors.get_move_index
        )

        # 10. DXY (U.S. Dollar Index)
        print("  [10/82] Fetching DXY...")
        self._fetch_with_error_handling(
            '10_dxy',
            yfinance_extractors.get_dxy
        )

        # 11. 10-Year Treasury Yield
        print("  [11/82] Fetching 10-Year Treasury Yield...")
        self._fetch_with_error_handling(
            '11_10y_yield',
            fred_extractors.get_10y_treasury_yield
        )

        # 12. ISM Manufacturing PMI
        print("  [12/82] Fetching ISM Manufacturing PMI...")
        self._fetch_with_error_handling(
            '12_ism_pmi',
            fred_extractors.get_ism_pmi
        )

        # 13. Gold Futures
        print("  [13/82] Fetching Gold futures...")
        self._fetch_with_error_handling(
            '13_gold',
            commodities_extractors.get_gold
        )

        # 14. Silver Futures
        print("  [14/82] Fetching Silver futures...")
        self._fetch_with_error_handling(
            '14_silver',
            commodities_extractors.get_silver
        )

        # 15. Crude Oil Futures
        print("  [15/82] Fetching Crude Oil futures...")
        self._fetch_with_error_handling(
            '15_crude_oil',
            commodities_extractors.get_crude_oil
        )

        # 16. Copper Futures
        print("  [16/82] Fetching Copper futures...")
        self._fetch_with_error_handling(
            '16_copper',
            commodities_extractors.get_copper
        )

        # 17. ES Futures (S&P 500 E-mini)
        print("  [17/82] Fetching ES futures (S&P 500 E-mini)...")
        self._fetch_with_error_handling(
            '17_es_futures',
            yfinance_extractors.get_es_futures
        )

        # 18. RTY Futures (Russell 2000 E-mini)
        print("  [18/82] Fetching RTY futures (Russell 2000 E-mini)...")
        self._fetch_with_error_handling(
            '18_rty_futures',
            yfinance_extractors.get_rty_futures
        )

        # 19. S&P 500 Breadth (Advance/Decline)
        print("  [19/82] Fetching S&P 500 market breadth...")
        self._fetch_with_error_handling(
            '19_sp500_breadth',
            web_scrapers.get_sp500_breadth_indicator
        )

        # 20. JPY Exchange Rate
        print("  [20/82] Fetching JPY exchange rate...")
        self._fetch_with_error_handling(
            '20_jpy',
            yfinance_extractors.get_jpy_exchange_rate
        )

        # 21. All Commodities (for convenience)
        print("  [21/82] Fetching all commodities...")
        self._fetch_with_error_handling(
            '21_all_commodities',
            commodities_extractors.get_all_commodities
        )

        # 22. CFTC COT Positioning (Gold & Silver)
        print("  [22/82] Fetching CFTC COT positioning data (Gold & Silver)...")
        self._fetch_with_error_handling(
            '22_cot_positioning',
            cot_extractor.get_cot_gold_silver
        )

        # 23. TGA Balance
        print("  [23/82] Fetching TGA Balance...")
        self._fetch_with_error_handling(
            '23_tga_balance',
            fred_extractors.get_tga_balance
        )

        # 24. Fed Net Liquidity
        print("  [24/82] Fetching Fed Net Liquidity...")
        self._fetch_with_error_handling(
            '24_net_liquidity',
            fred_extractors.get_fed_net_liquidity
        )

        # 25. SOFR
        print("  [25/82] Fetching SOFR...")
        self._fetch_with_error_handling(
            '25_sofr',
            fred_extractors.get_sofr
        )

        # 26. US 2-Year Treasury Yield
        print("  [26/82] Fetching US 2-Year Treasury Yield...")
        self._fetch_with_error_handling(
            '26_us_2y_yield',
            fred_extractors.get_us_2y_yield
        )

        # 27. Japan 2-Year Government Bond Yield
        print("  [27/82] Fetching Japan 2Y Yield...")
        self._fetch_with_error_handling(
            '27_japan_2y_yield',
            japan_yield_extractor.get_japan_2y_yield
        )

        # 28. US 2Y - Japan 2Y Yield Spread
        print("  [28/82] Fetching US2Y-JP2Y Spread...")
        self._fetch_with_error_handling(
            '28_us2y_jp2y_spread',
            japan_yield_extractor.get_us2y_jp2y_spread
        )

        # 29. Large-cap Equity Financials (Top 20)
        print("  [29/82] Fetching Large-cap Equity Financials (Top 20)...")
        self._fetch_with_error_handling(
            '29_equity_financials',
            equity_financials_extractor.get_top20_financials
        )

        # --- Rates & Credit indicators (v2.2.0) ---

        # 30. Germany 10Y Yield
        print("  [30/82] Fetching Germany 10Y Yield...")
        self._fetch_with_error_handling(
            '30_germany_10y',
            global_yields_extractor.get_germany_10y_yield
        )

        # 31. UK 10Y Yield
        print("  [31/82] Fetching UK 10Y Yield...")
        self._fetch_with_error_handling(
            '31_uk_10y',
            global_yields_extractor.get_uk_10y_yield
        )

        # 32. China 10Y Yield
        print("  [32/82] Fetching China 10Y Yield...")
        self._fetch_with_error_handling(
            '32_china_10y',
            global_yields_extractor.get_china_10y_yield
        )

        # 33. Yield Curve (2s10s Spread + Regime Classification)
        print("  [33/82] Fetching Yield Curve & Regime...")
        self._fetch_with_error_handling(
            '33_yield_curve',
            yield_curve_extractor.get_yield_curve_data
        )

        # 34. HY Credit Spread (OAS)
        print("  [34/82] Fetching HY Credit Spread (OAS)...")
        self._fetch_with_error_handling(
            '34_hy_oas',
            fred_extractors.get_hy_credit_spread
        )

        # 35. Breakeven Inflation (5Y + 10Y)
        print("  [35/82] Fetching Breakeven Inflation...")
        self._fetch_with_error_handling(
            '35_breakeven_inflation',
            fred_extractors.get_breakeven_inflation
        )

        # 36. 10Y Real Yield (TIPS)
        print("  [36/82] Fetching 10Y Real Yield (TIPS)...")
        self._fetch_with_error_handling(
            '36_real_yield',
            fred_extractors.get_real_yield_10y
        )

        # 37. Chicago Fed NFCI
        print("  [37/82] Fetching Chicago Fed NFCI...")
        self._fetch_with_error_handling(
            '37_nfci',
            fred_extractors.get_nfci
        )

        # 38. Fed Funds Rate
        print("  [38/82] Fetching Fed Funds Rate...")
        self._fetch_with_error_handling(
            '38_fed_funds',
            fred_extractors.get_fed_funds_rate
        )

        # 39. Initial Jobless Claims
        print("  [39/82] Fetching Initial Jobless Claims...")
        self._fetch_with_error_handling(
            '39_initial_claims',
            fred_extractors.get_initial_jobless_claims
        )

        # 40. Unemployment Rate
        print("  [40/82] Fetching Unemployment Rate...")
        self._fetch_with_error_handling(
            '40_unemployment',
            fred_extractors.get_unemployment_rate
        )

        # 41. Core CPI + Core PCE (YoY%)
        print("  [41/82] Fetching Core Inflation (CPI + PCE)...")
        self._fetch_with_error_handling(
            '41_core_inflation',
            fred_extractors.get_core_inflation
        )

        # --- Economic Activity & Extended indicators (v2.3.0) ---

        # 42. Nonfarm Payrolls
        print("  [42/82] Fetching Nonfarm Payrolls...")
        self._fetch_with_error_handling(
            '42_nfp',
            fred_extractors.get_nonfarm_payrolls
        )

        # 43. ISM Services PMI
        print("  [43/82] Fetching ISM Services PMI...")
        self._fetch_with_error_handling(
            '43_ism_services',
            global_yields_extractor.get_ism_services_pmi
        )

        # 44. Consumer Sentiment (UMich)
        print("  [44/82] Fetching Consumer Sentiment...")
        self._fetch_with_error_handling(
            '44_consumer_sentiment',
            fred_extractors.get_consumer_sentiment
        )

        # 45. IG Credit Spread (OAS)
        print("  [45/82] Fetching IG Credit Spread...")
        self._fetch_with_error_handling(
            '45_ig_oas',
            fred_extractors.get_ig_credit_spread
        )

        # 46. Sahm Rule Recession Indicator
        print("  [46/82] Fetching Sahm Rule...")
        self._fetch_with_error_handling(
            '46_sahm_rule',
            fred_extractors.get_sahm_rule
        )

        # 47. M2 Money Supply
        print("  [47/82] Fetching M2 Money Supply...")
        self._fetch_with_error_handling(
            '47_m2',
            fred_extractors.get_m2_money_supply
        )

        # 48. JOLTS Job Openings
        print("  [48/82] Fetching JOLTS Job Openings...")
        self._fetch_with_error_handling(
            '48_jolts',
            fred_extractors.get_jolts_openings
        )

        # 49. Continuing Claims
        print("  [49/82] Fetching Continuing Claims...")
        self._fetch_with_error_handling(
            '49_continuing_claims',
            fred_extractors.get_continuing_claims
        )

        # 50. Retail Sales
        print("  [50/82] Fetching Retail Sales...")
        self._fetch_with_error_handling(
            '50_retail_sales',
            fred_extractors.get_retail_sales
        )

        # 51. Housing Starts
        print("  [51/82] Fetching Housing Starts...")
        self._fetch_with_error_handling(
            '51_housing_starts',
            fred_extractors.get_housing_starts
        )

        # 52. PPI (Producer Price Index YoY%)
        print("  [52/82] Fetching PPI...")
        self._fetch_with_error_handling(
            '52_ppi',
            fred_extractors.get_ppi
        )

        # 53. Headline CPI (YoY%)
        print("  [53/82] Fetching Headline CPI...")
        self._fetch_with_error_handling(
            '53_headline_cpi',
            fred_extractors.get_headline_cpi
        )

        # 54. Major FX Pairs (EUR/USD, GBP/USD, EUR/JPY)
        print("  [54/82] Fetching Major FX Pairs...")
        self._fetch_with_error_handling(
            '54_fx_pairs',
            yfinance_extractors.get_major_fx_pairs
        )

        # 55. SPY/RSP Market Concentration
        print("  [55/82] Fetching Market Concentration (SPY/RSP)...")
        self._fetch_with_error_handling(
            '55_market_concentration',
            yfinance_extractors.get_market_concentration
        )

        # 56. Natural Gas
        print("  [56/82] Fetching Natural Gas...")
        self._fetch_with_error_handling(
            '56_natural_gas',
            commodities_extractors.get_natural_gas
        )

        # 57. Copper/Gold Ratio
        print("  [57/82] Fetching Copper/Gold Ratio...")
        self._fetch_with_error_handling(
            '57_cu_au_ratio',
            commodities_extractors.get_copper_gold_ratio
        )

        # 58. Bank Reserves
        print("  [58/82] Fetching Bank Reserves...")
        self._fetch_with_error_handling(
            '58_bank_reserves',
            fred_extractors.get_bank_reserves
        )

        # 59. Industrial Production
        print("  [59/82] Fetching Industrial Production...")
        self._fetch_with_error_handling(
            '59_industrial_production',
            fred_extractors.get_industrial_production
        )

        # 60. Quits Rate (JOLTS)
        print("  [60/82] Fetching Quits Rate...")
        self._fetch_with_error_handling(
            '60_quits_rate',
            fred_extractors.get_quits_rate
        )

        # 61. 5Y Treasury Yield
        print("  [61/82] Fetching 5Y Treasury Yield...")
        self._fetch_with_error_handling(
            '61_5y_yield',
            fred_extractors.get_5y_treasury_yield
        )

        # 62. SLOOS Lending Standards (quarterly, may be delayed)
        print("  [62/82] Fetching SLOOS Lending Standards...")
        self._fetch_with_error_handling('62_sloos', fred_extractors.get_sloos_lending)

        # --- OpenBB-based indicators (v2.5.0) ---

        # 63. VIX Futures Curve (CBOE — fixes broken VX=F)
        print("  [63/82] Fetching VIX Futures Curve...")
        self._fetch_with_error_handling('63_vix_futures_curve', openbb_extractors.get_vix_futures_curve)

        # 64. SPY Put/Call OI (CBOE — fixes broken put/call ratio)
        print("  [64/82] Fetching SPY Put/Call OI...")
        self._fetch_with_error_handling('64_spy_put_call_oi', openbb_extractors.get_spy_put_call_oi)

        # 65. S&P 500 Historical Multiples (Finviz — fixes broken Forward P/E)
        print("  [65/82] Fetching S&P 500 Multiples...")
        self._fetch_with_error_handling('65_sp500_multiples', openbb_extractors.get_sp500_historical_multiples)

        # 66. ECB Policy Rates
        print("  [66/82] Fetching ECB Policy Rates...")
        self._fetch_with_error_handling('66_ecb_rates', openbb_extractors.get_ecb_policy_rates)

        # 67. OECD Composite Leading Indicator
        print("  [67/82] Fetching OECD Leading Indicator...")
        self._fetch_with_error_handling('67_oecd_cli', openbb_extractors.get_oecd_leading_indicator)

        # 68. CPI Components Breakdown
        print("  [68/82] Fetching CPI Components...")
        self._fetch_with_error_handling('68_cpi_components', openbb_extractors.get_cpi_components)

        # 69. Fama-French 5-Factor Returns
        print("  [69/82] Fetching Fama-French Factors...")
        self._fetch_with_error_handling('69_fama_french', openbb_extractors.get_fama_french_factors)

        # 70. SPX Implied Volatility Skew
        print("  [70/82] Fetching SPX IV Skew...")
        self._fetch_with_error_handling('70_iv_skew', openbb_extractors.get_spx_iv_skew)

        # 71. European Government Bond Yields
        print("  [71/82] Fetching European Yields...")
        self._fetch_with_error_handling('71_eu_yields', openbb_extractors.get_european_yields)

        # 72. Global CPI Comparison
        print("  [72/82] Fetching Global CPI...")
        self._fetch_with_error_handling('72_global_cpi', openbb_extractors.get_global_cpi_comparison)

        # 73. Upcoming Earnings Calendar
        print("  [73/82] Fetching Earnings Calendar...")
        self._fetch_with_error_handling('73_earnings_calendar', openbb_extractors.get_upcoming_earnings)

        # 74. Sector P/E Ratios
        print("  [74/82] Fetching Sector P/E Ratios...")
        self._fetch_with_error_handling('74_sector_pe', openbb_extractors.get_sector_pe_ratios)

        # 75. Full Treasury Yield Curve
        print("  [75/82] Fetching Treasury Curve...")
        self._fetch_with_error_handling('75_treasury_curve', openbb_extractors.get_full_treasury_curve)

        # 76. Corporate Bond Spreads (AAA/BBB)
        print("  [76/82] Fetching Corporate Spreads...")
        self._fetch_with_error_handling('76_corporate_spreads', openbb_extractors.get_corporate_bond_spreads)

        # 77. International Unemployment Rates
        print("  [77/82] Fetching International Unemployment...")
        self._fetch_with_error_handling('77_intl_unemployment', openbb_extractors.get_international_unemployment)

        # 78. International GDP Growth
        print("  [78/82] Fetching International GDP...")
        self._fetch_with_error_handling('78_intl_gdp', openbb_extractors.get_international_gdp)

        # 79. Equity Market Breadth Screener
        print("  [79/82] Fetching Equity Screener...")
        self._fetch_with_error_handling('79_equity_screener', openbb_extractors.get_equity_screener)

        # 80. Money Supply Measures (M1/M2)
        print("  [80/82] Fetching Money Measures...")
        self._fetch_with_error_handling('80_money_measures', openbb_extractors.get_money_measures)

        # 81. Global Manufacturing PMI
        print("  [81/82] Fetching Global PMI...")
        self._fetch_with_error_handling('81_global_pmi', openbb_extractors.get_global_pmi)

        # 82. Equity Risk Premium
        print("  [82/83] Fetching Equity Risk Premium...")
        self._fetch_with_error_handling('82_erp', openbb_extractors.get_equity_risk_premium)

        # 83. CFTC COT Positioning (Energy & Copper)
        print("  [83/85] Fetching CFTC COT positioning data (Crude Oil, Brent, Copper, Nat Gas)...")
        self._fetch_with_error_handling(
            '83_cot_energy_metals',
            cot_extractor.get_cot_energy_metals
        )

        # 84. Hyperliquid Perpetual Futures
        print("  [84/85] Fetching Hyperliquid perps (BTC, ETH, SOL, PAXG, HYPE, OIL)...")
        self._fetch_with_error_handling(
            '84_hl_perps',
            hyperliquid_extractor.get_hl_perps
        )

        # 85. Hyperliquid HIP-3 Spot Stocks
        print("  [85/85] Fetching Hyperliquid HIP-3 spot stocks (TSLA, NVDA, AAPL, ...)...")
        self._fetch_with_error_handling(
            '85_hl_spot_stocks',
            hyperliquid_extractor.get_hl_spot_stocks
        )

        print(f"\nCompleted! Last update: {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

        if self.errors:
            print(f"\nEncountered {len(self.errors)} errors during fetch:")
            for error in self.errors:
                print(f"  - {error}")

        # Save to local cache after fetching
        self._save_to_local_cache()
        _write_progress(83, 83, "Complete", "done")

        return self.indicators

    def export_to_csv(self, output_dir='data_export'):
        """Export current indicators to CSV files."""
        if not self.indicators:
            return {'error': 'No data to export. Fetch or load data first.'}
        return export_indicators_to_csv(self.indicators, output_dir=output_dir)

    def _fetch_with_error_handling(self, indicator_key, fetch_function):
        """Fetch indicator with error handling."""
        self._indicator_count = getattr(self, '_indicator_count', 0) + 1
        # Strip leading number prefix for display (e.g. '8b_vix_move_ratio' -> 'vix_move_ratio')
        display_name = indicator_key.split('_', 1)[-1] if '_' in indicator_key else indicator_key
        _write_progress(self._indicator_count, 82, display_name, "running")
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
            '83_cot_energy_metals': 'CFTC COT Positioning (Crude Oil, Brent, Copper, Nat Gas)',
            '84_hl_perps': 'Hyperliquid Perpetual Futures (BTC, ETH, SOL, PAXG, HYPE, OIL)',
            '85_hl_spot_stocks': 'Hyperliquid HIP-3 Spot Stocks (TSLA, NVDA, etc.)',
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
