#!/usr/bin/env python3
"""
Quick data refresh demonstration script.

This script shows how the data extraction would work.
For full extraction, run: python extract_historical_data.py
"""

import os
from datetime import datetime
from pathlib import Path

print("=" * 80)
print("MACRO INDICATORS - DATA REFRESH")
print("=" * 80)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

# Check dependencies
print("📦 Checking dependencies...")
required = ['pandas', 'yfinance', 'fredapi', 'requests', 'beautifulsoup4']
missing = []

for pkg in required:
    try:
        __import__(pkg.replace('-', '_'))
        print(f"  ✅ {pkg}")
    except ImportError:
        print(f"  ❌ {pkg} (not installed)")
        missing.append(pkg)

if missing:
    print(f"\n⚠️  Missing dependencies: {', '.join(missing)}")
    print(f"Install with: pip install {' '.join(missing)}")
    print("\nTo perform full data extraction:")
    print("  1. pip install -r requirements.txt")
    print("  2. export FRED_API_KEY='your_key_here'")
    print("  3. python extract_historical_data.py")
else:
    print("\n✅ All dependencies installed!")
    print("\nRunning data extraction...")

    try:
        # Import and run extraction
        from extract_historical_data import extract_all_historical_data

        results = extract_all_historical_data()

        print("\n" + "=" * 80)
        print("✅ DATA EXTRACTION COMPLETE!")
        print("=" * 80)
        print(f"\nExtracted {len(results)} indicator groups")
        print(f"Files saved to: historical_data/")

    except Exception as e:
        print(f"\n❌ Error during extraction: {str(e)}")
        print("\nTroubleshooting:")
        print("  - Ensure FRED_API_KEY is set")
        print("  - Check internet connection")
        print("  - Review extract_historical_data.py for details")

print("\n" + "=" * 80)
print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 80)
print("\n📊 Next steps:")
print("  - View data: python view_data.py summary")
print("  - Update daily: python update_data.py")
print("  - Open dashboard: streamlit run app.py")
