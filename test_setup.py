"""
Test script to verify setup and data extraction functionality.
Run this before launching the dashboard to check if all modules work correctly.
"""
import sys
from datetime import datetime


def test_imports():
    """Test if all required packages can be imported."""
    print("=" * 60)
    print("Testing Package Imports...")
    print("=" * 60)

    packages = [
        ('streamlit', 'Streamlit'),
        ('pandas', 'Pandas'),
        ('yfinance', 'Yahoo Finance'),
        ('fredapi', 'FRED API'),
        ('requests', 'Requests'),
        ('bs4', 'BeautifulSoup4')
    ]

    failed = []

    for package, name in packages:
        try:
            __import__(package)
            print(f"✓ {name:20} - OK")
        except ImportError:
            print(f"✗ {name:20} - FAILED")
            failed.append(package)

    # Test OpenBB (optional)
    try:
        __import__('openbb')
        print(f"✓ {'OpenBB':20} - OK")
    except ImportError:
        print(f"⚠ {'OpenBB':20} - NOT INSTALLED (optional)")

    if failed:
        print(f"\n❌ {len(failed)} package(s) failed to import: {', '.join(failed)}")
        print("Please install missing packages: pip install -r requirements.txt")
        return False
    else:
        print("\n✅ All required packages imported successfully!")
        return True


def test_config():
    """Test configuration and API keys."""
    print("\n" + "=" * 60)
    print("Testing Configuration...")
    print("=" * 60)

    try:
        import config

        # Check FRED API Key
        if config.FRED_API_KEY and config.FRED_API_KEY != '':
            print("✓ FRED API Key is set")
        else:
            print("⚠ FRED API Key is NOT set")
            print("  Set your FRED API key in config.py or as environment variable")
            print("  Get free API key from: https://fred.stlouisfed.org/docs/api/api_key.html")

        print(f"✓ Cache directory: {config.CACHE_DIR}")
        print(f"✓ Cache expiry: {config.CACHE_EXPIRY_HOURS} hours")

        return True
    except Exception as e:
        print(f"❌ Configuration error: {str(e)}")
        return False


def test_data_extractors():
    """Test a few data extractors to ensure they work."""
    print("\n" + "=" * 60)
    print("Testing Data Extractors (Sample)...")
    print("=" * 60)

    tests = []

    # Test 1: Yahoo Finance - DXY
    print("\n1. Testing Yahoo Finance (DXY)...")
    try:
        from data_extractors import yfinance_extractors
        result = yfinance_extractors.get_dxy()
        if 'error' in result:
            print(f"   ⚠ Warning: {result['error']}")
            tests.append(False)
        else:
            dxy = result.get('dxy', 'N/A')
            print(f"   ✓ DXY Value: {dxy}")
            tests.append(True)
    except Exception as e:
        print(f"   ✗ Error: {str(e)}")
        tests.append(False)

    # Test 2: VIX
    print("\n2. Testing Yahoo Finance (VIX)...")
    try:
        from data_extractors import yfinance_extractors
        result = yfinance_extractors.get_vix()
        if 'error' in result:
            print(f"   ⚠ Warning: {result['error']}")
            tests.append(False)
        else:
            vix = result.get('vix', 'N/A')
            print(f"   ✓ VIX Value: {vix}")
            tests.append(True)
    except Exception as e:
        print(f"   ✗ Error: {str(e)}")
        tests.append(False)

    # Test 3: Shiller CAPE
    print("\n3. Testing Shiller CAPE...")
    try:
        from data_extractors import shiller_extractor
        result = shiller_extractor.get_shiller_cape()
        if 'error' in result:
            print(f"   ⚠ Warning: {result['error']}")
            tests.append(False)
        else:
            cape = result.get('shiller_cape', 'N/A')
            print(f"   ✓ CAPE Value: {cape}")
            tests.append(True)
    except Exception as e:
        print(f"   ✗ Error: {str(e)}")
        tests.append(False)

    success_rate = sum(tests) / len(tests) * 100 if tests else 0
    print(f"\n📊 Success Rate: {success_rate:.0f}% ({sum(tests)}/{len(tests)} tests passed)")

    return success_rate > 50


def test_aggregator():
    """Test the main data aggregator."""
    print("\n" + "=" * 60)
    print("Testing Data Aggregator...")
    print("=" * 60)

    try:
        from data_aggregator import get_aggregator

        aggregator = get_aggregator()
        print("✓ Aggregator initialized")

        print("\nFetching sample indicators (this may take a moment)...")
        aggregator.fetch_all_indicators()

        summary = aggregator.get_summary()
        print(f"\n📊 Results:")
        print(f"   Total Indicators: {summary['total_indicators']}")
        print(f"   Successful: {summary['successful']}")
        print(f"   Failed: {summary['failed']}")
        print(f"   Last Update: {summary['last_update']}")

        if summary['failed'] > 0:
            print(f"\n⚠ {summary['failed']} indicator(s) failed. This is normal for some sources.")
            print("   Check the dashboard for specific error messages.")

        return True
    except Exception as e:
        print(f"❌ Aggregator error: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   Macroeconomic Indicators Dashboard - Setup Test         ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(f"\nTest started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Configuration", test_config()))
    results.append(("Data Extractors", test_data_extractors()))
    results.append(("Aggregator", test_aggregator()))

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{test_name:20} {status}")

    all_passed = all(result[1] for result in results)

    print("\n" + "=" * 60)
    if all_passed:
        print("✅ All tests passed! You can now run the dashboard:")
        print("   streamlit run app.py")
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        print("   The dashboard may still work, but some indicators might not load.")
    print("=" * 60)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
