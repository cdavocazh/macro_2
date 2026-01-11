# Macroeconomic Indicators Dashboard

A comprehensive Streamlit dashboard for tracking 10 key macroeconomic indicators in real-time. This tool consolidates data from multiple sources including FRED, Yahoo Finance, OpenBB, CBOE, and Robert Shiller's database.

## 📊 Indicators Tracked

1. **S&P 500 Forward P/E Ratio** - Forward-looking valuation metric (Source: MacroMicro)
2. **Russell 2000 Value & Growth Indices** - Small-cap market performance (Source: Yahoo Finance)
3. **S&P 500 Trailing P/E & P/B** - Fundamental valuation metrics (Source: OpenBB)
4. **S&P 500 Put/Call Ratio** - Options market sentiment (Source: CBOE)
5. **SPX Call Skew (CBOE SKEW)** - Tail risk indicator (Source: CBOE)
6. **S&P 500 / 200-Day MA** - Technical momentum indicator (Calculated)
7. **S&P 500 Market Cap / US GDP** - Buffett Indicator (Source: FRED)
8. **Shiller CAPE Ratio** - Cyclically adjusted P/E (Source: Robert Shiller/Yale)
9. **VIX & VIX/MOVE Ratio** - Equity and bond volatility (Source: Yahoo Finance/CBOE)
10. **MOVE Index & DXY** - Treasury volatility and US Dollar strength (Source: Yahoo Finance)

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

## 📚 Data Sources

### Primary Sources

- **FRED (Federal Reserve Economic Data)**: US GDP, market capitalization data
- **Yahoo Finance**: Stock indices, VIX, MOVE, DXY
- **OpenBB Platform**: S&P 500 fundamentals
- **Robert Shiller (Yale)**: CAPE ratio data
- **CBOE**: Volatility indices, options data

### Data Refresh Frequency

- Most indicators: Real-time or daily updates
- GDP data: Quarterly updates
- CAPE ratio: Monthly updates

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
