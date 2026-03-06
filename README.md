# Macroeconomic Indicators Dashboard

A Streamlit dashboard tracking **62+ macroeconomic indicators** and **quarterly financials for S&P 500 companies** from multiple data sources. Features economic activity indicators (employment, consumer, production), global sovereign yields, yield curve regime classification, credit spreads, FX pairs, market concentration, expandable 3M price charts, dual-source equity financials (Yahoo Finance + SEC EDGAR), CFTC COT positioning, automated launchd scheduling, earnings monitoring, and data freshness review.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard (loads from cache if available)
streamlit run app.py

# Refresh data manually
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard

# Batch extract S&P 500 financials (~30-40 min)
python extract_sp500_financials.py --source both

# Monitor earnings & data freshness
python monitor_earnings.py --auto-update
python review_data_freshness.py --report

# Install macOS launchd auto-scheduler
bash setup_launchd.sh
```

**FRED API Key** (free): Set `FRED_API_KEY` env var or edit `config.py`. Get one at https://fred.stlouisfed.org/docs/api/api_key.html

## Dashboard Tabs

| Tab | Name | Indicators |
|-----|------|------------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP |
| 2 | Market Indices | ES/RTY futures, market breadth, Russell 2000 V/G, S&P 500/200MA, SPY/RSP concentration |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker input, S&P 500 batch extraction, dual-source (Yahoo + SEC EDGAR) |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields (US 5Y/10Y, DE/UK/CN 10Y), real yield, breakevens, HY/IG OAS, NFCI, Fed Funds, bank reserves, SLOOS, unemployment, claims, headline/core CPI, PPI, core PCE |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, Retail Sales, ISM Services PMI, Industrial Production, Housing Starts |

### Features

- **Yield curve regime classification** — automated bull/bear steepener/flattener detection with color-coded badges
- **Global sovereign bond yields** — US, Germany, UK, China 10Y with overlay charts
- **Expandable 3M price charts** for every indicator (tabs 1, 3, 4, 5, 7) with 1W/1M/3M zoom and range slider
- **Dual-source equity financials** with radio button toggle (Yahoo Finance vs SEC EDGAR)
- **QoQ/YoY colored percentage changes** in quarterly tables
- **Financial analysis** with numerator/denominator display
- **Revenue segments** from SEC EDGAR 10-K XBRL filings
- **CFTC COT positioning** for gold, silver, oil, copper
- **Custom ticker input** in Tab 6 — type any ticker for on-demand financial data
- **Cache-first startup** with instant load from local JSON cache

## Data Sources

| Source | What It Provides | Key Required |
|--------|-----------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, Russell 2000, ES/RTY futures, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, SPY/RSP, S&P 500, commodities (incl. NG), equity financials | No |
| FRED API | GDP, yields (2Y/5Y/10Y), ISM PMI, TGA, liquidity, SOFR, HY/IG OAS, breakevens, real yield, NFCI, Fed Funds, claims, unemployment, CPI, PCE, PPI, M2, NFP, JOLTS, Sahm Rule, bank reserves, SLOOS, etc. | Yes (free) |
| Trading Economics | Germany/UK/China 10Y yields, ISM Services PMI (web scrape) | No |
| SEC EDGAR XBRL | Quarterly financials for S&P 500 companies | No (User-Agent only) |
| MOF Japan | Japan 2Y/10Y yields (CSV download) | No |
| Robert Shiller (Yale) | CAPE ratio (Excel download) | No |
| CFTC | COT positioning (weekly report) | No |
| MacroMicro | Forward P/E (unreliable, 403 errors) | No |
| CBOE/ycharts | Put/Call ratio (unreliable, blocked) | No |

## Project Structure

```
macro_2/
├── app.py                          # Streamlit dashboard (8 tabs, ~2,350+ lines)
├── data_aggregator.py              # Orchestrator — fetches all 62+ indicators, manages cache
├── config.py                       # API keys, cache settings
├── scheduled_extract.py            # Standalone catch-up script (launchd or manual)
├── extract_historical_data.py      # Append-only historical CSV builder
├── extract_sp500_financials.py     # Batch S&P 500 financial extraction (~30-40 min)
├── monitor_earnings.py             # Earnings date monitoring — flags stale companies
├── review_data_freshness.py        # Weekly SEC filing date comparison
├── data_extractors/
│   ├── yfinance_extractors.py      # 14 indicators (VIX, DXY, Russell, futures, FX pairs, SPY/RSP, etc.)
│   ├── fred_extractors.py          # 32 indicators (GDP, yields, spreads, inflation, labor, M2, JOLTS, Sahm, SLOOS, etc.)
│   ├── web_scrapers.py             # 4 indicators (Forward P/E, Put/Call, SKEW, breadth)
│   ├── shiller_extractor.py        # 1 indicator (CAPE from Yale Excel)
│   ├── commodities_extractors.py   # 7 indicators (gold, silver, oil, copper, natural gas, Cu/Au ratio)
│   ├── cot_extractor.py            # CFTC COT positioning data
│   ├── global_yields_extractor.py  # 4 indicators (Germany/UK/China 10Y yields, ISM Services PMI)
│   ├── yield_curve_extractor.py    # 1 indicator (2s10s spread + regime classification)
│   ├── equity_financials_extractor.py  # Yahoo Finance quarterly financials
│   ├── sec_extractor.py            # SEC EDGAR XBRL quarterly financials
│   ├── japan_yield_extractor.py    # MOF Japan yield data
│   ├── sp500_tickers.py            # S&P 500 constituent list (Wikipedia + cache)
│   └── openbb_extractors.py        # S&P fundamentals (optional dep)
├── utils/helpers.py                # Cache serialization, CSV export, formatting
├── agent/                          # Data discrepancy review agent (OpenAI Agents + LangChain)
├── com.macro2.scheduled-extract.plist  # launchd job definition
├── setup_launchd.sh                # One-command launchd installer
└── data_cache/                     # Local JSON cache (gitignored)
```

## Equity Financials (Tab 6)

**Top 20 dropdown:** AAPL, MSFT, NVDA, GOOGL, AMZN, META, BRK-B, TSM, LLY, AVGO, JPM, V, WMT, MA, XOM, UNH, COST, HD, PG, JNJ
**Any ticker:** Type any ticker symbol in the text input for on-demand data

- **S&P 500 batch extraction**: `extract_sp500_financials.py` downloads financials for all ~500 companies
- **Dual data source**: Yahoo Finance (primary) and SEC EDGAR XBRL (secondary) with radio button toggle
- **Quarterly statements**: Income Statement, Balance Sheet, Cash Flow with QoQ/YoY colored changes
- **Financial analysis**: Profitability, turnover, returns with numerator/denominator display
- **Valuation**: P/E, P/B, P/S, EV/EBITDA, EV/FCF with component breakdown
- **Revenue segments**: From 10-K XBRL instance documents (SEC EDGAR source)
- **SEC specifics**: FY-end Q4 derivation, cumulative YTD cash flow correction, cross-concept merging

## Monitoring Scripts

**Earnings Monitor** (`monitor_earnings.py`) — Compares local data against yfinance earnings dates:
```bash
python monitor_earnings.py                    # scan all companies in database
python monitor_earnings.py --auto-update      # scan + re-extract stale tickers
python monitor_earnings.py --days 7           # show upcoming within 7 days
```

**Data Freshness Review** (`review_data_freshness.py`) — Weekly check against SEC EDGAR filing dates:
```bash
python review_data_freshness.py               # full S&P 500 review (~2 min)
python review_data_freshness.py --auto-update # review + re-extract stale
python review_data_freshness.py --report      # save CSV to data_export/
```

## Scheduling

**macOS launchd** runs `scheduled_extract.py` at 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8, Mon-Sat. Catches up missed runs after sleep (unlike cron). Freshness guard prevents redundant fetches within 15 minutes. A 10-minute timeout auto-kills hung processes to prevent blocking subsequent runs.

```bash
bash setup_launchd.sh              # Install
bash setup_launchd.sh --status     # Check status
bash setup_launchd.sh --uninstall  # Remove
```

## Historical Data Storage

```
historical_data/
├── data_metadata.json
├── russell_2000.csv, sp500_ma200.csv, vix_move.csv, dxy.csv, ...
├── commodities_gold.csv, commodities_silver.csv, ...
├── cot_positioning.csv
├── equity_financials/
│   ├── yahoo_finance/{TICKER}_quarterly.csv
│   └── sec_edgar/{TICKER}_quarterly.csv
└── _summary_latest.csv
```

## Data Discrepancy Agent

AI agent in `/agent/` that reviews financial data quality using 8 shared tools. Two implementations:
- **OpenAI Agents SDK** + Minimax LLM
- **LangChain + LangGraph** + Minimax LLM

```bash
export MINIMAX_API_KEY=your_key
python -m agent.openai_agents.agent "Scan all companies for missing SEC data"
python -m agent.langchain_agents.agent "Compare Yahoo vs SEC for AAPL"
```

## Known Limitations

| Issue | Workaround |
|-------|------------|
| Forward P/E 403 errors (MacroMicro) | Falls back to trailing P/E |
| Put/Call ratio unreliable (CBOE) | Falls back to FRED PCERTOT |
| TSM (IFRS) no SEC EDGAR data | Yahoo Finance only |
| ISM PMI uses proxy | Industrial Production normalized to PMI scale |

## Disclaimer

This dashboard is for informational and educational purposes only. It does not constitute financial advice.

## Acknowledgments

Data sources: FRED, Yahoo Finance, SEC EDGAR, Trading Economics, CFTC, Robert Shiller (Yale), MOF Japan, CBOE, MacroMicro.

---

**Last Updated:** March 2026
