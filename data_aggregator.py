"""
Main data aggregator that consolidates all macroeconomic indicators.
"""
from data_extractors import (
    yfinance_extractors,
    openbb_extractors,
    fred_extractors,
    shiller_extractor,
    web_scrapers
)
from datetime import datetime
import traceback


class MacroIndicatorAggregator:
    """Aggregates all macroeconomic indicators from various sources."""

    def __init__(self):
        self.indicators = {}
        self.last_update = None
        self.errors = []

    def fetch_all_indicators(self):
        """Fetch all 10 macroeconomic indicators."""
        self.indicators = {}
        self.errors = []
        self.last_update = datetime.now()

        print("Fetching macroeconomic indicators...")

        # 1. S&P 500 Forward P/E (MacroMicro)
        print("  [1/10] Fetching S&P 500 Forward P/E...")
        self._fetch_with_error_handling(
            '1_sp500_forward_pe',
            web_scrapers.get_sp500_forward_pe_macromicro
        )

        # 2. Russell 2000 Value & Growth Indices
        print("  [2/10] Fetching Russell 2000 indices...")
        self._fetch_with_error_handling(
            '2_russell_2000',
            yfinance_extractors.get_russell_2000_indices
        )

        # 3. S&P 500 Trailing P/E and P/B
        print("  [3/10] Fetching S&P 500 trailing P/E and P/B...")
        self._fetch_with_error_handling(
            '3_sp500_fundamentals',
            openbb_extractors.get_sp500_fundamentals
        )

        # 4. S&P 500 Put/Call Ratio
        print("  [4/10] Fetching S&P 500 Put/Call Ratio...")
        self._fetch_with_error_handling(
            '4_put_call_ratio',
            web_scrapers.get_sp500_put_call_ratio
        )

        # 5. SPX Call Skew
        print("  [5/10] Fetching SPX Call Skew...")
        self._fetch_with_error_handling(
            '5_spx_call_skew',
            web_scrapers.get_spx_call_skew
        )

        # 6a. S&P 500 / 200MA Ratio
        print("  [6a/10] Fetching S&P 500 / 200MA ratio...")
        self._fetch_with_error_handling(
            '6a_sp500_to_ma200',
            yfinance_extractors.get_sp500_data
        )

        # 6b. S&P 500 Market Cap / US GDP
        print("  [6b/10] Fetching Market Cap / GDP ratio...")
        self._fetch_with_error_handling(
            '6b_marketcap_to_gdp',
            fred_extractors.calculate_sp500_marketcap_to_gdp
        )

        # 7. Shiller CAPE Ratio
        print("  [7/10] Fetching Shiller CAPE Ratio...")
        self._fetch_with_error_handling(
            '7_shiller_cape',
            shiller_extractor.get_shiller_cape
        )

        # 8. VIX
        print("  [8/10] Fetching VIX...")
        self._fetch_with_error_handling(
            '8_vix',
            yfinance_extractors.get_vix
        )

        # 8b. VIX/MOVE Ratio
        print("  [8b/10] Fetching VIX/MOVE ratio...")
        self._fetch_with_error_handling(
            '8b_vix_move_ratio',
            yfinance_extractors.calculate_vix_move_ratio
        )

        # 9. MOVE Index
        print("  [9/10] Fetching MOVE Index...")
        self._fetch_with_error_handling(
            '9_move_index',
            yfinance_extractors.get_move_index
        )

        # 10. DXY (U.S. Dollar Index)
        print("  [10/10] Fetching DXY...")
        self._fetch_with_error_handling(
            '10_dxy',
            yfinance_extractors.get_dxy
        )

        print(f"\nCompleted! Last update: {self.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

        if self.errors:
            print(f"\nEncountered {len(self.errors)} errors during fetch:")
            for error in self.errors:
                print(f"  - {error}")

        return self.indicators

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
            'total_indicators': 10,
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
            '10_dxy': 'DXY (US Dollar Index)'
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
