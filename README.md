# Macroeconomic Indicators Dashboard

A comprehensive Streamlit dashboard for tracking 10 key macroeconomic indicators in real-time. This tool consolidates data from multiple sources including FRED, Yahoo Finance, OpenBB, CBOE, and Robert Shiller's database.

## 🔑 Quick Setup

**Minimum Requirements:**
- Python 3.8+
- `pip install -r requirements.txt`
- **FRED API Key** (free) - Required for GDP/Market Cap data: https://fred.stlouisfed.org/docs/api/api_key.html

**Optional but Recommended:**
- OpenBB Platform (for S&P 500 fundamentals)

**Run Dashboard:**
```bash
export FRED_API_KEY='your_key_here'
streamlit run app.py
```

## 📊 Indicators Tracked & Data Sources

### Detailed Source Information

| # | Indicator | Primary Source | Method | Ticker/Endpoint | API Key | Update Freq | Notes |
|---|-----------|---------------|--------|-----------------|---------|-------------|-------|
| 1 | **S&P 500 Forward P/E** | MacroMicro | Web Scraping | https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio | No | Daily | May require authentication; fallback to trailing P/E recommended |
| 2a | **Russell 2000 Value Index** | Yahoo Finance | yfinance | IWN (ETF proxy) | No | Real-time | Using iShares Russell 2000 Value ETF as proxy |
| 2b | **Russell 2000 Growth Index** | Yahoo Finance | yfinance | IWO (ETF proxy) | No | Real-time | Using iShares Russell 2000 Growth ETF as proxy |
| 3a | **S&P 500 Trailing P/E** | OpenBB / Yahoo Finance | OpenBB Platform | SPY fundamentals | No | Daily | Using SPY ETF as S&P 500 proxy |
| 3b | **S&P 500 P/B Ratio** | OpenBB / Yahoo Finance | OpenBB Platform | SPY fundamentals | No | Daily | Using SPY ETF as S&P 500 proxy |
| 4 | **S&P 500 Put/Call Ratio** | CBOE | Web Scraping | https://www.cboe.com/us/options/market_statistics/daily/ | No | Daily | May require data subscription; web scraping has limitations |
| 5 | **SPX Call Skew (CBOE SKEW)** | CBOE / Yahoo Finance | yfinance | ^SKEW | No | Daily | CBOE SKEW Index measuring tail risk |
| 6a | **S&P 500 / 200-Day MA** | Yahoo Finance (calculated) | yfinance | ^GSPC | No | Real-time | Price divided by 200-day moving average |
| 6b | **S&P 500 Market Cap / GDP** | FRED | FRED API | GDP (series: GDP)<br>Market Cap (series: DDDM01USA156NWDB or WILL5000INDFC) | **Yes** | Quarterly (GDP)<br>Annual (Market Cap) | Buffett Indicator; may use Wilshire 5000 as proxy |
| 7 | **Shiller CAPE Ratio** | Robert Shiller (Yale) | HTTP/Excel Download | http://www.econ.yale.edu/~shiller/data/ie_data.xls | No | Monthly | Cyclically Adjusted P/E Ratio dating back to 1871 |
| 8a | **VIX (Volatility Index)** | Yahoo Finance | yfinance | ^VIX | No | Real-time | CBOE Volatility Index |
| 8b | **VIX/MOVE Ratio** | Yahoo Finance (calculated) | yfinance | ^VIX / ^MOVE | No | Real-time | Equity volatility vs. bond volatility ratio |
| 9 | **MOVE Index** | Yahoo Finance | yfinance | ^MOVE | No | Daily | ICE BofA MOVE Index (Treasury Volatility) |
| 10 | **DXY (US Dollar Index)** | Yahoo Finance | yfinance | DX-Y.NYB | No | Real-time | ICE U.S. Dollar Index |

### Data Source Summary

#### 1. S&P 500 Forward P/E Ratio
- **Source**: MacroMicro (S&P Dow Jones Indices LLC)
- **URL**: https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio
- **Access Method**: Web scraping (with limitations)
- **Implemented In**: `data_extractors/web_scrapers.py::get_sp500_forward_pe_macromicro()`
- **API Key Required**: No
- **Limitations**: MacroMicro may require authentication or have rate limits. Consider manual download or using trailing P/E as alternative.

#### 2. Russell 2000 Value & Growth Indices
- **Source**: Yahoo Finance (via yfinance)
- **Tickers**:
  - Value: `IWN` (iShares Russell 2000 Value ETF)
  - Growth: `IWO` (iShares Russell 2000 Growth ETF)
- **Access Method**: Yahoo Finance API via `yfinance` Python library
- **Implemented In**: `data_extractors/yfinance_extractors.py::get_russell_2000_indices()`
- **Alternative**: `data_extractors/openbb_extractors.py::get_russell_2000_via_openbb()` (using OpenBB Platform)
- **API Key Required**: No
- **Update Frequency**: Real-time during market hours

#### 3. S&P 500 Trailing P/E & P/B Ratios
- **Source**: OpenBB Platform (via Yahoo Finance provider)
- **Ticker**: `SPY` (S&P 500 ETF as proxy)
- **Access Method**: OpenBB `equity.fundamental.metrics()` with yfinance provider
- **Implemented In**: `data_extractors/openbb_extractors.py::get_sp500_fundamentals()`
- **API Key Required**: No
- **Data Points**: Trailing P/E ratio, Price-to-Book ratio
- **Note**: Uses SPY ETF fundamentals as proxy for S&P 500

#### 4. S&P 500 Put/Call Ratio
- **Source**: CBOE (Chicago Board Options Exchange)
- **URL**: https://www.cboe.com/us/options/market_statistics/daily/
- **Access Method**: Web scraping
- **Implemented In**: `data_extractors/web_scrapers.py::get_sp500_put_call_ratio()`
- **API Key Required**: No (but access limited)
- **Limitations**: CBOE website scraping may fail. Professional market data subscriptions recommended for reliable access.
- **Alternative Sources**: Options chain analysis, professional data providers (Bloomberg, Refinitiv)

#### 5. SPX Call Skew (CBOE SKEW Index)
- **Source**: CBOE via Yahoo Finance
- **Ticker**: `^SKEW`
- **Access Method**: Yahoo Finance API via `yfinance`
- **Implemented In**: `data_extractors/web_scrapers.py::get_spx_call_skew()` and `get_cboe_skew_index()`
- **API Key Required**: No
- **Description**: Measures tail risk in S&P 500 options (higher = more tail risk)
- **Interpretation**: 100-115 (normal), 115-135 (elevated), >135 (high tail risk)

#### 6a. S&P 500 / 200-Day Moving Average
- **Source**: Yahoo Finance (calculated)
- **Ticker**: `^GSPC` (S&P 500 Index)
- **Access Method**: Yahoo Finance API via `yfinance`, with 200-day MA calculated
- **Implemented In**: `data_extractors/yfinance_extractors.py::get_sp500_data()`
- **API Key Required**: No
- **Calculation**: Current S&P 500 price divided by 200-day simple moving average
- **Interpretation**: >1.1 (overbought), <0.9 (oversold)

#### 6b. S&P 500 Market Cap / US GDP (Buffett Indicator)
- **Source**: FRED (Federal Reserve Economic Data)
- **FRED Series**:
  - GDP: `GDP` (Gross Domestic Product)
  - Market Cap: `DDDM01USA156NWDB` (Market Cap of Listed Companies) or `WILL5000INDFC` (Wilshire 5000 as proxy)
- **Access Method**: FRED API via `fredapi` Python library
- **Implemented In**: `data_extractors/fred_extractors.py::calculate_sp500_marketcap_to_gdp()`
- **API Key Required**: **YES** (free FRED API key)
- **Get API Key**: https://fred.stlouisfed.org/docs/api/api_key.html
- **Update Frequency**: Quarterly (GDP), varies (Market Cap)
- **Interpretation**: >100% suggests overvaluation (Buffett Indicator)

#### 7. Shiller CAPE Ratio
- **Source**: Professor Robert Shiller, Yale University
- **URL**: http://www.econ.yale.edu/~shiller/data/ie_data.xls
- **Access Method**: Direct Excel file download via HTTP
- **Implemented In**: `data_extractors/shiller_extractor.py::get_shiller_cape()`
- **API Key Required**: No
- **Data Format**: Excel (.xls) file with historical data since 1871
- **Update Frequency**: Monthly
- **Description**: Cyclically Adjusted Price-to-Earnings Ratio (10-year average earnings)
- **Interpretation**: <15 (undervalued), 15-25 (normal), 25-35 (overvalued), >35 (extremely overvalued)

#### 8a. VIX (CBOE Volatility Index)
- **Source**: Yahoo Finance / CBOE
- **Ticker**: `^VIX`
- **Access Method**: Yahoo Finance API via `yfinance`
- **Implemented In**: `data_extractors/yfinance_extractors.py::get_vix()`
- **Alternative**: `data_extractors/fred_extractors.py::get_vix_from_fred()` (FRED series: VIXCLS)
- **API Key Required**: No (Yahoo Finance), Yes (FRED alternative)
- **Update Frequency**: Real-time during market hours
- **Interpretation**: <15 (low volatility), 15-25 (normal), >25 (elevated risk)

#### 8b. VIX/MOVE Ratio
- **Source**: Calculated from Yahoo Finance data
- **Components**: VIX (^VIX) / MOVE (^MOVE)
- **Access Method**: Yahoo Finance API via `yfinance`, ratio calculated
- **Implemented In**: `data_extractors/yfinance_extractors.py::calculate_vix_move_ratio()`
- **API Key Required**: No
- **Description**: Compares equity volatility (VIX) to bond volatility (MOVE)
- **Interpretation**: Higher ratio = equity volatility elevated relative to bond volatility

#### 9. ICE BofA MOVE Index
- **Source**: Yahoo Finance (ICE Data Indices)
- **Ticker**: `^MOVE`
- **Access Method**: Yahoo Finance API via `yfinance`
- **Implemented In**: `data_extractors/yfinance_extractors.py::get_move_index()`
- **API Key Required**: No
- **Description**: Treasury volatility index (bond market equivalent of VIX)
- **Update Frequency**: Daily

#### 10. U.S. Dollar Index (DXY)
- **Source**: Yahoo Finance (ICE)
- **Ticker**: `DX-Y.NYB`
- **Access Method**: Yahoo Finance API via `yfinance`
- **Implemented In**: `data_extractors/yfinance_extractors.py::get_dxy()`
- **API Key Required**: No
- **Description**: Measures value of USD against basket of foreign currencies
- **Update Frequency**: Real-time during market hours

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- FRED API Key (free - get it from [https://fred.stlouisfed.org/docs/api/api_key.html](https://fred.stlouisfed.org/docs/api/api_key.html))

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd macro_2
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Set up your FRED API key:
```bash
# Option 1: Set as environment variable
export FRED_API_KEY='your_api_key_here'

# Option 2: Edit config.py and add your key directly
# Edit config.py and set: FRED_API_KEY = 'your_api_key_here'
```

### Running the Dashboard

Launch the Streamlit dashboard:
```bash
streamlit run app.py
```

The dashboard will open in your default web browser at `http://localhost:8501`

## 📱 Using the Dashboard

### Main Features

- **Automatic Data Loading**: Dashboard loads all indicators on startup
- **Manual Refresh**: Click the "🔄 Refresh All Data" button in the sidebar to update all indicators
- **Organized Tabs**: Indicators are grouped into 4 categories:
  - 📈 Valuation Metrics
  - 📊 Market Indices
  - ⚡ Volatility & Risk
  - 🌍 Macro & Currency
- **Error Handling**: Indicators that fail to load show error messages with explanations

### Navigation

1. **Sidebar**: Contains the refresh button and information about data sources
2. **Tabs**: Click on different tabs to view specific categories of indicators
3. **Metrics**: Each indicator displays its current value, with historical context where available

## 🏗️ Project Structure

```
macro_2/
├── app.py                          # Main Streamlit dashboard
├── config.py                       # Configuration and API keys
├── data_aggregator.py             # Main data consolidation module
├── requirements.txt               # Python dependencies
├── data_extractors/               # Data extraction modules
│   ├── __init__.py
│   ├── yfinance_extractors.py    # Yahoo Finance data (indices, VIX, MOVE, DXY)
│   ├── openbb_extractors.py      # OpenBB Platform data (fundamentals)
│   ├── fred_extractors.py        # FRED API data (GDP, market cap)
│   ├── shiller_extractor.py      # Shiller CAPE data
│   └── web_scrapers.py           # Web scraping (MacroMicro, CBOE)
├── utils/                         # Utility functions
│   ├── __init__.py
│   └── helpers.py                # Helper functions
└── data_cache/                   # Cached data (auto-created)
```

## 📚 Data Sources Reference

### Quick Reference by Source

#### Yahoo Finance (via yfinance library)
**API Key Required**: ❌ No
**Indicators**:
- Russell 2000 Value (IWN) & Growth (IWO) indices
- S&P 500 Index (^GSPC) for 200-day MA calculation
- VIX (^VIX) - Volatility Index
- MOVE Index (^MOVE) - Treasury Volatility
- DXY (DX-Y.NYB) - US Dollar Index
- CBOE SKEW (^SKEW) - Tail Risk Index

**Update Frequency**: Real-time during market hours
**Reliability**: ⭐⭐⭐⭐⭐ Excellent (free, no authentication required)

#### OpenBB Platform
**API Key Required**: ❌ No
**Indicators**:
- S&P 500 Trailing P/E Ratio (via SPY fundamentals)
- S&P 500 P/B Ratio (via SPY fundamentals)

**Update Frequency**: Daily
**Reliability**: ⭐⭐⭐⭐ Good (requires OpenBB installation)

#### FRED (Federal Reserve Economic Data)
**API Key Required**: ✅ **Yes** (free)
**Get API Key**: https://fred.stlouisfed.org/docs/api/api_key.html
**Indicators**:
- US GDP (series: GDP)
- Market Capitalization (series: DDDM01USA156NWDB or WILL5000INDFC)
- Market Cap / GDP Ratio (calculated)
- VIX (alternative source, series: VIXCLS)

**Update Frequency**: Quarterly (GDP), varies by series
**Reliability**: ⭐⭐⭐⭐⭐ Excellent (official government data)

#### Robert Shiller / Yale University
**API Key Required**: ❌ No
**Indicators**:
- Shiller CAPE Ratio (Cyclically Adjusted P/E)

**URL**: http://www.econ.yale.edu/~shiller/data/ie_data.xls
**Update Frequency**: Monthly
**Reliability**: ⭐⭐⭐⭐⭐ Excellent (academic source, historical data since 1871)

#### MacroMicro
**API Key Required**: ❌ No (but limited access)
**Indicators**:
- S&P 500 Forward P/E Ratio

**URL**: https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio
**Update Frequency**: Daily
**Reliability**: ⭐⭐ Limited (web scraping, may require authentication)
**Note**: Consider using trailing P/E as fallback

#### CBOE (Chicago Board Options Exchange)
**API Key Required**: ❌ No (but limited access)
**Indicators**:
- S&P 500 Put/Call Ratio
- SPX Call Skew (available via Yahoo Finance as ^SKEW)

**URL**: https://www.cboe.com/us/options/market_statistics/daily/
**Update Frequency**: Daily
**Reliability**: ⭐⭐ Limited (web scraping for Put/Call ratio)
**Note**: SKEW index accessible via Yahoo Finance; Put/Call ratio may require subscription

### API Key Requirements Summary

| Source | API Key Required | Cost | How to Obtain |
|--------|-----------------|------|---------------|
| Yahoo Finance | ❌ No | Free | No registration needed |
| OpenBB | ❌ No | Free | `pip install openbb` |
| FRED | ✅ **Yes** | Free | https://fred.stlouisfed.org/docs/api/api_key.html |
| Robert Shiller | ❌ No | Free | Public data file |
| MacroMicro | ❌ No* | Free* | *May require account for reliable access |
| CBOE | ❌ No* | Free* | *Limited web access; subscriptions available |

### Data Refresh Frequency by Indicator

- **Real-time**: Russell 2000, S&P 500/200MA, VIX, MOVE, DXY (during market hours)
- **Daily**: Forward P/E, Trailing P/E, P/B, Put/Call Ratio, SKEW
- **Monthly**: Shiller CAPE
- **Quarterly**: US GDP
- **Annual/Varies**: Market Capitalization data

## 🔧 Configuration

### API Keys

Edit `config.py` to set your API keys:

```python
# FRED API Key (required for GDP and market cap data)
FRED_API_KEY = 'your_api_key_here'

# Cache settings
CACHE_EXPIRY_HOURS = 24  # How long to cache data
```

### Alternative: Environment Variables

```bash
export FRED_API_KEY='your_api_key_here'
```

## 📝 Notes on Data Availability

### Known Limitations

1. **MacroMicro Forward P/E**: May require authentication or manual download. Web scraping fallback provided.
2. **Put/Call Ratio**: Requires market data subscription or CBOE website access. Best obtained from professional data providers.
3. **Market Cap/GDP**: Uses Wilshire 5000 as proxy when S&P 500 market cap is unavailable.

### Fallback Options

The dashboard includes error handling and fallback data sources:
- If a primary source fails, the dashboard displays an error message with suggested alternatives
- Some indicators may use proxy data (e.g., SPY ETF for S&P 500 fundamentals)

## 🛠️ Troubleshooting

### Common Issues

1. **"FRED_API_KEY not set" error**
   - Solution: Set your FRED API key in `config.py` or as environment variable

2. **"No data available" errors**
   - Solution: Check your internet connection and try refreshing
   - Some data sources may have rate limits

3. **OpenBB import errors**
   - Solution: Ensure OpenBB is properly installed: `pip install openbb`

4. **Web scraping failures**
   - Solution: Some sources (MacroMicro, CBOE) may block automated access
   - Consider using alternative data sources or manual downloads

## 📊 Interpretation Guide

### Valuation Metrics

- **P/E Ratios**: Historical average ~15-16. Above 25 suggests overvaluation.
- **CAPE Ratio**: Mean ~17. Above 30 indicates potential overvaluation.
- **Market Cap/GDP**: Above 100% suggests overvaluation (Buffett Indicator).

### Volatility Indicators

- **VIX**: Below 15 (low vol), 15-25 (normal), above 25 (elevated risk)
- **MOVE Index**: Higher values indicate increased bond market uncertainty
- **VIX/MOVE Ratio**: Compares equity vs. bond volatility

### Market Indices

- **Russell Value/Growth**: Ratio helps identify style rotation
- **S&P 500/200MA**: Above 1.1 (overbought), below 0.9 (oversold)

## 🤝 Contributing

Contributions are welcome! Areas for improvement:
- Additional indicators
- Enhanced data visualization
- Alternative data sources
- Performance optimizations

## ⚠️ Disclaimer

This dashboard is for informational and educational purposes only. It does not constitute financial advice. Always conduct your own research and consult with qualified financial professionals before making investment decisions.

## 📄 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

Data sources:
- Federal Reserve Bank of St. Louis (FRED)
- Yahoo Finance
- OpenBB Foundation
- Professor Robert Shiller (Yale University)
- Chicago Board Options Exchange (CBOE)

---

**Last Updated**: January 2026
