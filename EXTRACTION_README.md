# Data Extraction - Quick Reference

## Refresh/Download Historical Data

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export FRED_API_KEY='your_key_here'

# Full extraction (all indicators + equity financials)
python extract_historical_data.py

# Scheduled refresh (skips if cache < 1h old)
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard
```

## What Gets Created

```
historical_data/
├── data_metadata.json              # Tracks last_extraction timestamp
├── russell_2000.csv                # Russell 2000 Value/Growth indices
├── sp500_ma200.csv                 # S&P 500 / 200-day MA
├── vix_move.csv                    # VIX, MOVE, VIX/MOVE ratio
├── dxy.csv                         # US Dollar Index
├── usdjpy.csv                      # USD/JPY exchange rate
├── shiller_cape.csv                # CAPE ratio (since 1871)
├── sp500_fundamentals.csv          # Trailing P/E, P/B
├── cboe_skew.csv                   # CBOE SKEW tail risk index
├── us_gdp.csv                      # US GDP (quarterly)
├── market_cap.csv                  # Market capitalization
├── marketcap_to_gdp.csv            # Buffett Indicator
├── treasury_10y.csv                # 10Y Treasury yield
├── us_2y_yield.csv                 # US 2Y yield
├── japan_2y_yield.csv              # Japan 2Y yield
├── sofr.csv                        # SOFR rate
├── tga_balance.csv                 # Treasury General Account
├── net_liquidity.csv               # Fed net liquidity
├── ism_pmi.csv                     # ISM PMI proxy
├── commodities_gold.csv            # Gold (GC=F)
├── commodities_silver.csv          # Silver (SI=F)
├── commodities_crude_oil.csv       # Crude Oil (CL=F)
├── commodities_copper.csv          # Copper (HG=F)
├── cot_positioning.csv             # CFTC COT data
├── equity_financials/
│   ├── yahoo_finance/
│   │   └── {TICKER}_quarterly.csv  # 20 companies
│   └── sec_edgar/
│       └── {TICKER}_quarterly.csv  # 19 companies (no TSM)
└── _summary_latest.csv             # Latest values from all indicators
```

## Automation (macOS launchd)

```bash
# Install scheduled extraction (catches up missed runs after sleep)
bash setup_launchd.sh

# Check status
bash setup_launchd.sh --status

# Uninstall
bash setup_launchd.sh --uninstall
```

Schedule: 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8, Mon-Sat.

## Key Features

- **Append-only** - Never overwrites existing data
- **Deduplication** - Removes duplicates by timestamp
- **Freshness guard** - Skips if cache < 1h old
- **Dual-source equity** - Yahoo Finance + SEC EDGAR in separate directories
- **Standard CSV format** - Works with Excel, pandas, SQL, etc.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `FRED_API_KEY not set` | `export FRED_API_KEY='your_key'` or edit `config.py` |
| Missing module | `pip install -r requirements.txt` |
| SEC rate limit errors | Built-in 0.15s delay; retry after a minute |
| TSM SEC data empty | Expected (IFRS company, uses Yahoo Finance only) |

---

**For complete documentation:** See `DATA_EXTRACTION_GUIDE.md`
