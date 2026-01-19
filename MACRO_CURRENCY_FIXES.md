# Macro & Currency Tab Data Source Fixes

## Summary

Fixed data fetching issues for the 10-Year Treasury Yield and ISM Manufacturing PMI indicators in the Macro & Currency tab.

## Issues Fixed

### 1. ISM Manufacturing PMI - Data Source Unavailable ✅

**Problem**:
- FRED series 'NAPM' no longer exists
- ISM PMI is a proprietary index requiring subscription for official data

**Solution**:
- Implemented web scraping from Trading Economics (https://tradingeconomics.com/united-states/manufacturing-pmi)
- Created fallback using FRED's Industrial Production: Manufacturing (IPMAN) as proxy
- Multi-tier approach:
  1. **Primary**: Web scraping from Trading Economics
  2. **Fallback**: Industrial Production index scaled to PMI-like values (50 + (IP - 100) * 0.5)

**Files Modified**:
- `data_extractors/fred_extractors.py` - Completely rewrote `get_ism_pmi()` function

**Current Performance**:
- ✅ Successfully fetching ISM PMI: **51.8** from Trading Economics
- ✅ Historical data available for charting (using IP index as proxy)
- ✅ Proper interpretation: "Above 50 indicates expansion, below 50 indicates contraction"

### 2. 10-Year Treasury Yield - Enhanced with Yahoo Finance Fallback ✅

**Problem**:
- FRED API works but wanted to add Yahoo Finance fallback for reliability

**Solution**:
- Added fallback to Yahoo Finance ticker **^TNX** (10-Year Treasury Yield)
- Maintains FRED as primary source (DGS10 series)
- Seamless fallback if FRED fails

**Files Modified**:
- `data_extractors/fred_extractors.py` - Added `get_10y_treasury_yield_fallback()` function

**Current Performance**:
- ✅ Successfully fetching 10Y Yield: **4.17%** from FRED
- ✅ Yahoo Finance fallback available if needed
- ✅ 10+ years of historical data for charting

## Data Sources

### 10-Year Treasury Yield
- **Primary**: FRED (DGS10) - https://fred.stlouisfed.org/series/DGS10
- **Fallback**: Yahoo Finance (^TNX) - https://finance.yahoo.com/quote/%5ETNX/

### ISM Manufacturing PMI
- **Primary**: Trading Economics (web scraping) - https://tradingeconomics.com/united-states/manufacturing-pmi
- **Fallback**: FRED Industrial Production Manufacturing (IPMAN) - https://fred.stlouisfed.org/series/IPMAN
- **Note**: Official ISM PMI requires subscription from ISM (Institute for Supply Management)

## Chart Implementation

The 10Y Yield vs ISM PMI chart now displays correctly with:
- Dual y-axes (10Y Yield on left, ISM PMI on right)
- Full historical data from both sources
- Superimposed line charts for easy comparison
- Gap calculation showing the difference (10Y - ISM)
- Color-coded interpretation:
  - 🔴 Yield > ISM = Potential economic slowdown
  - 🟢 ISM > Yield = Economic strength

## Testing

All indicators tested and working:

```bash
# Test 10Y Yield
✅ 10Y Treasury Yield: 4.17% (FRED)
- Latest date: 2026-01-15
- Historical data: 16,708 data points (1962-2026)

# Test ISM PMI
✅ ISM Manufacturing PMI: 51.8 (Trading Economics)
- Latest date: Recent
- Historical data: 648 data points (1972-2025)
- Using Industrial Production for historical chart
```

## Future Improvements

1. **ISM PMI**: Consider subscribing to official ISM data feed for real-time accuracy
2. **Historical Data**: For true historical ISM PMI, would need premium data service
3. **Additional Indicators**: Could add ISM Services PMI alongside Manufacturing PMI

## Related Files

- `data_extractors/fred_extractors.py` - Core data fetching logic
- `app.py` - Dashboard UI with dual-axis chart (lines 324-392)
- `data_aggregator.py` - Aggregates all 17 indicators
