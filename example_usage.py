"""
Example usage of the data extractors.
This script demonstrates how to use individual extractors programmatically.
"""
from data_extractors import yfinance_extractors, shiller_extractor, fred_extractors
from data_aggregator import get_aggregator


def example_individual_extractors():
    """Example: Using individual data extractors."""
    print("=" * 60)
    print("Example 1: Using Individual Extractors")
    print("=" * 60)

    # Get VIX
    print("\nFetching VIX...")
    vix_data = yfinance_extractors.get_vix()
    if 'error' not in vix_data:
        print(f"VIX: {vix_data['vix']:.2f}")
        print(f"Date: {vix_data['latest_date']}")
    else:
        print(f"Error: {vix_data['error']}")

    # Get DXY
    print("\nFetching DXY...")
    dxy_data = yfinance_extractors.get_dxy()
    if 'error' not in dxy_data:
        print(f"DXY: {dxy_data['dxy']:.2f}")
        print(f"1-Day Change: {dxy_data['change_1d']:.2f}%")
    else:
        print(f"Error: {dxy_data['error']}")

    # Get Shiller CAPE
    print("\nFetching Shiller CAPE...")
    cape_data = shiller_extractor.get_shiller_cape()
    if 'error' not in cape_data:
        print(f"CAPE Ratio: {cape_data['shiller_cape']:.2f}")
        print(f"Date: {cape_data['latest_date']}")
    else:
        print(f"Error: {cape_data['error']}")


def example_aggregator():
    """Example: Using the aggregator to fetch all indicators."""
    print("\n" + "=" * 60)
    print("Example 2: Using the Aggregator")
    print("=" * 60)

    # Get the aggregator instance
    aggregator = get_aggregator()

    # Fetch all indicators
    print("\nFetching all indicators...")
    aggregator.fetch_all_indicators()

    # Get summary
    summary = aggregator.get_summary()
    print(f"\nResults:")
    print(f"  Total Indicators: {summary['total_indicators']}")
    print(f"  Successful: {summary['successful']}")
    print(f"  Failed: {summary['failed']}")

    # Access specific indicators
    print("\nSample Indicator Values:")

    # VIX
    vix = aggregator.get_indicator('8_vix')
    if 'error' not in vix:
        print(f"  VIX: {vix['vix']:.2f}")

    # S&P 500 to 200MA
    sp500_ma = aggregator.get_indicator('6a_sp500_to_ma200')
    if 'error' not in sp500_ma:
        ratio = sp500_ma['sp500_to_ma200_ratio']
        print(f"  S&P 500 / 200MA: {ratio:.4f}")


def example_calculated_ratios():
    """Example: Calculating custom ratios."""
    print("\n" + "=" * 60)
    print("Example 3: Calculating Custom Ratios")
    print("=" * 60)

    # Calculate VIX/MOVE ratio
    print("\nCalculating VIX/MOVE ratio...")
    ratio_data = yfinance_extractors.calculate_vix_move_ratio()
    if 'error' not in ratio_data:
        print(f"VIX: {ratio_data['vix']:.2f}")
        print(f"MOVE: {ratio_data['move']:.2f}")
        print(f"VIX/MOVE Ratio: {ratio_data['vix_move_ratio']:.3f}")
    else:
        print(f"Error: {ratio_data['error']}")

    # Get Russell 2000 Value/Growth ratio
    print("\nFetching Russell 2000 Value/Growth ratio...")
    russell_data = yfinance_extractors.get_russell_2000_indices()
    if 'error' not in russell_data:
        ratio = russell_data.get('value_growth_ratio', 'N/A')
        print(f"Value/Growth Ratio: {ratio:.3f}")
    else:
        print(f"Error: {russell_data['error']}")


def example_with_historical_data():
    """Example: Accessing historical data."""
    print("\n" + "=" * 60)
    print("Example 4: Working with Historical Data")
    print("=" * 60)

    # Get S&P 500 with historical data
    print("\nFetching S&P 500 with 200MA...")
    sp500_data = yfinance_extractors.get_sp500_data()

    if 'error' not in sp500_data and 'historical' in sp500_data:
        hist = sp500_data['historical']
        print(f"\nHistorical data points: {len(hist)}")
        print(f"Latest close: {hist['Close'].iloc[-1]:.2f}")
        print(f"Latest 200MA: {hist['MA200'].iloc[-1]:.2f}")

        # Calculate some statistics
        print(f"\nStatistics over the period:")
        print(f"  Min price: {hist['Close'].min():.2f}")
        print(f"  Max price: {hist['Close'].max():.2f}")
        print(f"  Avg price: {hist['Close'].mean():.2f}")
    else:
        print(f"Error or no historical data available")


def main():
    """Run all examples."""
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║   Macroeconomic Indicators - Usage Examples               ║")
    print("╚════════════════════════════════════════════════════════════╝\n")

    # Run examples
    example_individual_extractors()
    example_aggregator()
    example_calculated_ratios()
    example_with_historical_data()

    print("\n" + "=" * 60)
    print("Examples completed!")
    print("=" * 60)
    print("\nFor more details, check:")
    print("  - README.md for full documentation")
    print("  - test_setup.py for testing your configuration")
    print("  - app.py to see how the dashboard uses these extractors")
    print("\n")


if __name__ == "__main__":
    main()
