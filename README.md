# Macroeconomic Indicators Dashboard

A Streamlit dashboard tracking **28+ macroeconomic indicators** and **quarterly financials for 20 large-cap companies** from multiple data sources. Features expandable 3M price charts, dual-source equity financials (Yahoo Finance + SEC EDGAR), CFTC COT positioning, and automated launchd scheduling.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the dashboard (loads from cache if available)
streamlit run app.py

# Refresh data manually
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard

# Install macOS launchd auto-scheduler
bash setup_launchd.sh
```

**FRED API Key** (free): Set `FRED_API_KEY` env var or edit `config.py`. Get one at https://fred.stlouisfed.org/docs/api/api_key.html

## Dashboard Tabs

| Tab | Name | Indicators |
|-----|------|------------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP |
| 2 | Market Indices | ES/RTY futures, market breadth, Russell 2000 V/G, S&P 500/200MA |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW |
| 4 | Macro & Currency | DXY, USD/JPY, TGA, net liquidity, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, CFTC COT positioning |
| 6 | Large-cap Financials | 20 companies, dual-source (Yahoo + SEC EDGAR), income/balance/cash flow, valuation, analysis |

### Features

- **Expandable 3M price charts** for every indicator (tabs 1, 3, 4, 5) with 1W/1M/3M zoom and range slider
- **Dual-source equity financials** with radio button toggle (Yahoo Finance vs SEC EDGAR)
- **QoQ/YoY colored percentage changes** in quarterly tables
- **Financial analysis** with numerator/denominator display
- **Revenue segments** from SEC EDGAR 10-K XBRL filings
- **CFTC COT positioning** for gold, silver, oil, copper
- **Cache-first startup** with instant load from local JSON cache

## Data Sources

| Source | What It Provides | Key Required |
|--------|-----------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, Russell 2000, ES/RTY futures, USD/JPY, S&P 500, commodities, equity financials | No |
| FRED API | GDP, 10Y yield, ISM PMI, TGA, net liquidity, SOFR, US 2Y yield, Put/Call fallback | Yes (free) |
| SEC EDGAR XBRL | Quarterly financials for 20 companies | No (User-Agent only) |
| MOF Japan | Japan 2Y/10Y yields (CSV download) | No |
| Robert Shiller (Yale) | CAPE ratio (Excel download) | No |
| CFTC | COT positioning (weekly report) | No |
| MacroMicro | Forward P/E (unreliable, 403 errors) | No |
| CBOE/ycharts | Put/Call ratio (unreliable, blocked) | No |

## Project Structure

```
macro_2/
├── app.py                          # Streamlit dashboard (6 tabs, ~1,400 lines)
├── data_aggregator.py              # Orchestrator — fetches all indicators, manages cache
├── config.py                       # API keys, cache settings
├── scheduled_extract.py            # Standalone catch-up script (launchd or manual)
├── extract_historical_data.py      # Append-only historical CSV builder
├── data_extractors/
│   ├── yfinance_extractors.py      # 11 indicators (VIX, DXY, Russell, futures, etc.)
│   ├── fred_extractors.py          # 4 indicators (GDP, 10Y yield, ISM PMI, etc.)
│   ├── web_scrapers.py             # 4 indicators (Forward P/E, Put/Call, SKEW, breadth)
│   ├── shiller_extractor.py        # 1 indicator (CAPE from Yale Excel)
│   ├── commodities_extractors.py   # 4 indicators (gold, silver, oil, copper)
│   ├── cot_extractor.py            # CFTC COT positioning data
│   ├── equity_financials_extractor.py  # Yahoo Finance quarterly financials
│   ├── sec_extractor.py            # SEC EDGAR XBRL quarterly financials
│   ├── japan_yield_extractor.py    # MOF Japan yield data
│   └── openbb_extractors.py        # S&P fundamentals (optional dep)
├── utils/helpers.py                # Cache serialization, CSV export, formatting
├── agent/                          # Data discrepancy review agent (OpenAI Agents + LangChain)
├── com.macro2.scheduled-extract.plist  # launchd job definition
├── setup_launchd.sh                # One-command launchd installer
└── data_cache/                     # Local JSON cache (gitignored)
```

## Large-cap Equity Financials (Tab 6)

**20 companies tracked:** AAPL, MSFT, NVDA, GOOGL, AMZN, META, BRK-B, TSM, LLY, AVGO, JPM, V, WMT, MA, XOM, UNH, COST, HD, PG, JNJ

- **Dual data source**: Yahoo Finance (primary) and SEC EDGAR XBRL (secondary) with radio button toggle
- **Quarterly statements**: Income Statement, Balance Sheet, Cash Flow with QoQ/YoY colored changes
- **Financial analysis**: Profitability, turnover, returns with numerator/denominator display
- **Valuation**: P/E, P/B, P/S, EV/EBITDA, EV/FCF with component breakdown
- **Revenue segments**: From 10-K XBRL instance documents (SEC EDGAR source)
- **SEC specifics**: FY-end Q4 derivation, cumulative YTD cash flow correction, cross-concept merging

## Scheduling

**macOS launchd** runs `scheduled_extract.py` at 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8, Mon-Sat. Catches up missed runs after sleep (unlike cron). Freshness guard prevents redundant fetches within 1 hour.

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

Data sources: FRED, Yahoo Finance, SEC EDGAR, CFTC, Robert Shiller (Yale), MOF Japan, CBOE, MacroMicro.

---

**Last Updated:** March 2026
