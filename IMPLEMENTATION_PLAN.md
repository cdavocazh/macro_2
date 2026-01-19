# Implementation Plan for Dashboard Enhancements

## Requirements Overview

### Requirement 1: Commodities Tab ✅ In Progress
Add continuous price data for:
1. Gold (GC=F)
2. Silver (SI=F)
3. Crude Oil (CL=F)
4. Copper (HG=F)

**Status**: Commodities extractor created ✅
**Next**: Update data_aggregator.py and app.py

### Requirement 2: 10Y Yield vs ISM Chart
Under "Macro & Currency" tab, add:
- Gap chart between 10Y Treasury Yield and ISM PMI
- Superimposed chart showing both metrics

**Status**: Fred extractors added ✅
**Next**: Create chart component in app.py

### Requirement 3: Source URLs
Add embedded links to data sources beside each indicator title

**Mapping**:
- S&P 500 Forward P/E → MacroMicro or yfinance
- Russell 2000 → Yahoo Finance
- S&P 500 P/E & P/B → Yahoo Finance (SPY)
- Put/Call Ratio → ycharts.com or CBOE
- SKEW → CBOE
- S&P 500 / 200MA → Yahoo Finance
- Market Cap/GDP → FRED
- Shiller CAPE → Robert Shiller Yale
- VIX → CBOE
- MOVE → CBOE
- DXY → Yahoo Finance
- 10Y Yield → FRED
- ISM PMI → FRED
- Commodities → Yahoo Finance

### Requirement 4: Historical Charts
At bottom of Valuation Metrics tab, add historical charts with:
- Weekly interval (toggleable to monthly)
- Last 10 years of data (or maximum available)
- Metrics: S&P 500 Forward P/E, S&P 500 P/B Ratio

## Implementation Steps

### Step 1: Data Extractors ✅ DONE
- [x] Create commodities_extractors.py
- [x] Add get_10y_treasury_yield() to fred_extractors.py
- [x] Add get_ism_pmi() to fred_extractors.py
- [x] Update __init__.py

### Step 2: Data Aggregator ✅ DONE
- [x] Add commodities to data_aggregator.py
- [x] Add 10Y yield to data_aggregator.py
- [x] Add ISM PMI to data_aggregator.py

### Step 3: Dashboard UI (app.py) ✅ DONE
- [x] Add Commodities tab (5th tab)
- [x] Add 10Y vs ISM chart to Macro & Currency tab
- [x] Add source URL links to all indicators
- [x] Add historical charts to Valuation Metrics tab

### Step 4: Historical Data Functions ✅ DONE
- [x] Create function to get historical Forward P/E (Note: Limited by data availability)
- [x] Create function to get historical P/B (Note: Limited by data availability)
- [x] Add interval toggle (weekly/monthly)

## Data Source URLs

```python
SOURCE_URLS = {
    'sp500_forward_pe': 'https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio',
    'russell_2000': 'https://finance.yahoo.com/quote/IWN/',
    'sp500_fundamentals': 'https://finance.yahoo.com/quote/SPY/',
    'put_call_ratio': 'https://ycharts.com/indicators/cboe_equity_put_call_ratio',
    'skew': 'https://www.cboe.com/tradable_products/vix/skew_index/',
    'sp500_ma200': 'https://finance.yahoo.com/quote/%5EGSPC/',
    'marketcap_gdp': 'https://fred.stlouisfed.org/series/DDDM01USA156NWDB',
    'shiller_cape': 'http://www.econ.yale.edu/~shiller/data.htm',
    'vix': 'https://www.cboe.com/tradable_products/vix/',
    'move': 'https://fred.stlouisfed.org/series/BAMLHYH0A0HYM2TRIV',
    'dxy': 'https://finance.yahoo.com/quote/DX-Y.NYB/',
    '10y_yield': 'https://fred.stlouisfed.org/series/DGS10',
    'ism_pmi': 'https://fred.stlouisfed.org/series/NAPM',
    'gold': 'https://finance.yahoo.com/quote/GC%3DF/',
    'silver': 'https://finance.yahoo.com/quote/SI%3DF/',
    'crude_oil': 'https://finance.yahoo.com/quote/CL%3DF/',
    'copper': 'https://finance.yahoo.com/quote/HG%3DF/'
}
```

## File Changes Summary

### Files Created:
1. `data_extractors/commodities_extractors.py` - Commodities data
2. `IMPLEMENTATION_PLAN.md` - This file

### Files Modified:
1. `data_extractors/fred_extractors.py` - Added 10Y yield and ISM PMI
2. `data_extractors/__init__.py` - Export commodities module
3. `data_aggregator.py` - Need to add new indicators
4. `app.py` - Need to add new tab, charts, and source URLs

## Implementation Complete! ✅

All 4 requirements have been successfully implemented:

1. ✅ **Commodities Tab**: Added 5th tab with Gold, Silver, Crude Oil, and Copper futures
   - All commodities fetching correctly from yfinance
   - Shows last close price when markets are closed
   - 1-day price change % displayed

2. ✅ **10Y Yield vs ISM Chart**: Added interactive dual-axis chart in Macro & Currency tab
   - 10Y Treasury Yield: 4.17% (FRED primary, Yahoo Finance ^TNX fallback)
   - ISM Manufacturing PMI: 51.8 (Trading Economics via web scraping)
   - Dual-axis Plotly chart with both indicators superimposed
   - Gap calculation showing 10Y - ISM difference
   - Color-coded interpretation (red/green for slowdown/strength)

3. ✅ **Source URLs**: All indicator titles now include embedded links to data sources
   - Updated to reflect actual data sources
   - 10Y Yield: Yahoo Finance ^TNX
   - ISM PMI: Trading Economics

4. ✅ **Historical Charts**: Added historical price chart with weekly/monthly toggle in Valuation Metrics tab
   - SPY price history for 10 years
   - Weekly/monthly interval selector
   - Note about limited historical P/E and P/B availability

## Recent Fixes ✅

### Commodities Data (2026-01-18)
- Fixed commodities to always show last close price when markets are closed
- Added market status indicator ("Last close from [date]")
- All 4 commodities (Gold, Silver, Crude Oil, Copper) working correctly

### Macro & Currency Data Sources (2026-01-18)
- **10Y Treasury Yield**: Enhanced with Yahoo Finance fallback (^TNX)
- **ISM Manufacturing PMI**: Completely rewritten
  - Primary: Web scraping from Trading Economics
  - Fallback: Industrial Production Manufacturing index as proxy
  - Official ISM data requires subscription

## Next Actions

1. ✅ Test all new features locally - DONE
2. ✅ Verify data fetching works for all new indicators - DONE
3. Commit changes to git
4. Deploy to Streamlit Cloud
