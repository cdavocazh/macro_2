# Macroeconomic Indicators Dashboard

A multi-frontend dashboard tracking **88+ macroeconomic indicators** and **quarterly financials for S&P 500 companies** from multiple data sources. Available as **4 dashboard frontends** (Streamlit, Plotly Dash, Grafana, React). Features economic activity indicators, global sovereign yields, yield curve regime classification, credit spreads, FX pairs, OHLCV candlestick charts, Hyperliquid DeFi perpetual futures, dual-source equity financials (Yahoo Finance + SEC EDGAR), CFTC COT positioning, 13F institutional holdings, sector ETFs, automated launchd scheduling, earnings monitoring, and data freshness review.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run dashboards (all read from same cache)
streamlit run app.py                          # Streamlit  → http://localhost:8501
python dash_dashboard/app.py                  # Plotly Dash → http://localhost:8050
bash grafana_dashboard/start.sh local         # Grafana    → http://localhost:3000
bash react_dashboard/start.sh                 # React      → http://localhost:5173

# Refresh data manually
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard

# Batch extract S&P 500 financials (~30-40 min)
python extract_sp500_financials.py --source both

# Extract 13F institutional holdings
python extract_13f_holdings.py

# Monitor earnings & data freshness
python monitor_earnings.py --auto-update
python review_data_freshness.py --report

# Install macOS launchd auto-scheduler (3 jobs)
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
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning, Hyperliquid perps (BTC, ETH, SOL, PAXG, HYPE, OIL) + HIP-3 spot stocks |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker input, S&P 500 batch extraction, dual-source (Yahoo + SEC EDGAR), 13F institutional holdings |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields, real yield, breakevens, HY/IG OAS, NFCI, ECB rates, corp spreads, CPI components, full treasury curve, intl unemployment/GDP |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, ISM Services, OECD CLI, Global PMI, Fama-French 5 Factors |
| 9 | Polymarket | Prediction market events, YES/NO prices, volume, multi-outcome markets |

### Features

- **4 Dashboard Frontends** — Streamlit, Plotly Dash, Grafana (111 panels), React + Vite — all share the same data cache
- **OHLCV Candlestick Charts** — Multi-interval (1m-1W) for Hyperliquid perps and yfinance instruments (TradingView/Plotly)
- **Hyperliquid DeFi Perps** — 1-minute refresh for BTC, ETH, SOL, PAXG, HYPE, OIL + HIP-3 spot stocks, WebSocket relay
- **Yield curve regime classification** — automated bull/bear steepener/flattener detection
- **Global sovereign bond yields** — US, Germany, UK, China 10Y
- **Expandable 3M price charts** for every indicator with 1W/1M/3M zoom
- **Dual-source equity financials** with radio button toggle (Yahoo Finance vs SEC EDGAR)
- **13F Institutional Holdings** — 5 funds (Berkshire, Bridgewater, Citadel, Renaissance, Situational Awareness), QoQ changes
- **CFTC COT positioning** for gold, silver, crude oil, Brent, copper, natural gas (SODA API)
- **20 OpenBB-based indicators** — VIX futures, ECB rates, Fama-French, ERP, corp spreads, intl data
- **5-year OHLCV history** — Commodities and futures back to 2021
- **Sector ETFs** — 11 SPDR ETFs (XLK, XLF, XLV, XLE, etc.)
- **Cache-first startup** with auto-reload on external cache updates

## Data Sources

| Source | What It Provides | Key Required |
|--------|-----------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, Russell 2000, ES/RTY futures, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, SPY/RSP, S&P 500, commodities (incl. NG), equity financials | No |
| FRED API | GDP, yields (2Y/5Y/10Y), ISM PMI, TGA, liquidity, SOFR, HY/IG OAS, breakevens, real yield, NFCI, Fed Funds, claims, unemployment, CPI, PCE, PPI, M2, NFP, JOLTS, Sahm Rule, bank reserves, SLOOS, etc. | Yes (free) |
| Trading Economics | Germany/UK/China 10Y yields, ISM Services PMI (web scrape) | No |
| SEC EDGAR XBRL | Quarterly financials for S&P 500 companies | No (User-Agent only) |
| MOF Japan | Japan 2Y/10Y yields (CSV download) | No |
| Robert Shiller (Yale) | CAPE ratio (Excel download) | No |
| CFTC (SODA API) | COT positioning (gold, silver, crude, Brent, copper, nat gas) | No |
| OpenBB/Finviz | S&P multiples, sector P/E, VIX futures, ECB rates, Fama-French, ERP | No (optional) |
| Hyperliquid | DeFi perpetual futures (BTC, ETH, SOL, PAXG, HYPE, OIL + spot stocks) | No |
| AAII | Investor sentiment survey (web scrape) | No |

## Project Structure

```
macro_2/
├── app.py                          # Streamlit dashboard (8 tabs, ~2,350+ lines)
├── data_aggregator.py              # Orchestrator — fetches all 88+ indicators, manages cache
├── config.py                       # API keys, cache settings
├── scheduled_extract.py            # Standalone catch-up script (launchd or manual)
├── extract_historical_data.py      # Append-only historical CSV builder
├── extract_sp500_financials.py     # Batch S&P 500 financial extraction (~30-40 min)
├── monitor_earnings.py             # Earnings date monitoring — flags stale companies
├── review_data_freshness.py        # Weekly SEC filing date comparison
├── data_extractors/
│   ├── yfinance_extractors.py      # 18+ indicators (VIX, DXY, futures, FX, sector ETFs, VIX term structure)
│   ├── fred_extractors.py          # 38 indicators (GDP, yields, spreads, inflation, labor, M2, JOLTS, Sahm, ADP, etc.)
│   ├── web_scrapers.py             # 4 indicators (Forward P/E, Put/Call, SKEW, breadth)
│   ├── shiller_extractor.py        # 1 indicator (CAPE from Yale Excel)
│   ├── commodities_extractors.py   # 7 indicators (gold, silver, oil, copper, natural gas, Cu/Au — all with 5y OHLCV)
│   ├── cot_extractor.py            # CFTC COT positioning (SODA API + bulk fallback)
│   ├── openbb_extractors.py        # 21 indicators (VIX futures, ECB, Fama-French, ERP, corp spreads, etc.)
│   ├── fidenza_extractors.py       # 13 indicators (Brent, Nikkei, EM, SOFR futures, XAU/JPY, AAII)
│   ├── hyperliquid_extractor.py    # 2 indicators (HL perps + HIP-3 spot stocks)
│   ├── thirteenf_extractor.py      # 13F institutional holdings (5 funds)
│   ├── global_yields_extractor.py  # 4 indicators (Germany/UK/China 10Y yields, ISM Services PMI)
│   ├── yield_curve_extractor.py    # 1 indicator (2s10s spread + regime classification)
│   ├── equity_financials_extractor.py  # Yahoo Finance quarterly financials
│   ├── sec_extractor.py            # SEC EDGAR XBRL quarterly financials
│   ├── japan_yield_extractor.py    # MOF Japan yield data
│   └── sp500_tickers.py            # S&P 500 constituent list (Wikipedia + cache)
├── utils/helpers.py                # Cache serialization, CSV export, formatting
├── fast_extract.py                 # 5-minute real-time yfinance extraction (~5s)
├── hl_extract.py                   # 1-minute Hyperliquid extraction (~0.5s)
├── ibkr_fast_extract.py            # IBKR real-time streaming daemon (VPS, ib_async)
├── extract_13f_holdings.py         # 13F institutional fund holdings extraction
├── dash_dashboard/                 # Plotly Dash frontend (standalone, production-ready)
├── grafana_dashboard/              # Grafana frontend (111 panels, Docker + local mode)
├── react_dashboard/                # React + Vite frontend (FastAPI backend, 9 tabs)
├── agent/                          # Data QA agents (equity cross-source + dashboard health)
├── deploy/systemd/                 # VPS systemd units (IBKR stream, data QA, cache repair)
├── scripts/                        # Utility scripts (cache repair, etc.)
├── setup_launchd.sh                # One-command launchd installer (3 jobs)
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

Three launchd jobs at different frequencies:

| Job | Schedule | What |
|-----|----------|------|
| **hl-extract** | Every 1 minute (24/7) | Hyperliquid perps + HIP-3 spot stocks |
| **fast-extract** | Every 5 minutes (24/7) | Real-time yfinance (31 extractors, ~5s) |
| **scheduled-extract** | 5x/day Mon-Sat | Full extraction: FRED, SEC, web scrapers, all CSVs |

All catch up missed runs after sleep (unlike cron). Freshness guards prevent redundant fetches.

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

## Documentation

### User Guides
- [`QUICKSTART.md`](QUICKSTART.md) — 5-minute setup guide
- [`DATA_EXTRACTION_GUIDE.md`](DATA_EXTRACTION_GUIDE.md) — Comprehensive data extraction and CSV management
- [`ARTICLE_SUMMARIZER_GUIDE.md`](ARTICLE_SUMMARIZER_GUIDE.md) — Article extraction and summarization toolkit

### Deployment
- [`DEPLOY_LIGHTSAIL.md`](DEPLOY_LIGHTSAIL.md) — AWS Lightsail VPS deployment
- [`STREAMLIT_CLOUD_SETUP.md`](STREAMLIT_CLOUD_SETUP.md) — Streamlit Cloud deployment
- [`dash_dashboard/deploy/DEPLOY.md`](dash_dashboard/deploy/DEPLOY.md) — Dash dashboard AWS deployment
- [`deploy/systemd/README.md`](deploy/systemd/README.md) — VPS systemd unit files (IBKR stream, data QA, cache repair)
- [`GIT_PRIVACY_GUIDE.md`](GIT_PRIVACY_GUIDE.md) — Git privacy scrubbing template

### Plans & Tracking
- [`TODO.md`](TODO.md) — Feature/enhancement tracking
- [`PolyM/PLAN.md`](PolyM/PLAN.md) — Polymarket extraction implementation plan
- [`todo/menu_bar_btc_app_plan.md`](todo/menu_bar_btc_app_plan.md) — macOS menu bar BTC price app (draft)
- [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) — Dashboard enhancement plan (historical)
- [`data_sources_todo.md`](data_sources_todo.md) — Fidenza Macro data source gap analysis

### Historical Fix Logs
- [`FIXES_SUMMARY.md`](FIXES_SUMMARY.md) — Data source issues and fixes
- [`MACRO_CURRENCY_FIXES.md`](MACRO_CURRENCY_FIXES.md) — Tab 4 macro/currency data fixes

### Research
- [`research/Dashboard_Research.md`](research/Dashboard_Research.md) — Multi-frontend implementation research
- [`research/financial_data_sources.md`](research/financial_data_sources.md) — API/broker data source survey
- [`research/OmniOracle_Relationship_Discovery.md`](research/OmniOracle_Relationship_Discovery.md) — Macro indicator correlation analysis
- [`research/CheckOnChain Data Extraction Guide.md`](research/CheckOnChain%20Data%20Extraction%20Guide.md) — On-chain BTC data scraping guide

## Known Limitations

| Issue | Workaround |
|-------|------------|
| Forward P/E 403 errors (MacroMicro) | Falls back to Finviz/OpenBB or trailing P/E |
| Shiller CAPE | ~~Yale Excel stuck at Sep 2023~~ **FIXED** — now scrapes multpl.com |
| Global CPI (US) | ~~FRED OECD series discontinued~~ **FIXED** — uses `CPIAUCSL` + YoY computation |
| TSM (IFRS) no SEC EDGAR data | Yahoo Finance only |
| VIX Futures (VX=F) | Not on yfinance; OpenBB/CBOE fallback |

## Pending TODO

- [ ] Grafana time-series panels (currently stat panels only; graph panels via `/api/timeseries/{key}`)


## Disclaimer

This dashboard is for informational and educational purposes only. It does not constitute financial advice.

## Acknowledgments

Data sources: FRED, Yahoo Finance, SEC EDGAR, Trading Economics, CFTC, Robert Shiller (Yale), MOF Japan, CBOE, MacroMicro.

---

**Last Updated:** May 2026

---

## Downstream consumer: Opportunity_scanner

[`Opportunity_scanner/`](../Opportunity_scanner/) consumes outputs of this repo read-only under a **parallel-pipeline contract** — no edits to scripts, schemas, or timers. The scanner sidesteps any per-ticker JSON schema mutation by writing its own sibling files. It either reads `data_cache/all_indicators.json` and `historical_data/equity_financials/<TICKER>_quarterly.csv`, or runs its own scripts against shared upstream APIs (FRED, yfinance, EDGAR, CFTC) with independent budgets. See [`Opportunity_scanner/CLAUDE.md`](../Opportunity_scanner/CLAUDE.md) for the design rule.

Scanner strategies that depend on this repo:
- [strategy 01 — news-event equity overlay](../Opportunity_scanner/strategies/01_news_event_equity_overlay/README.md) (read-only fundamentals)
- [strategy 02 — crypto funding carry](../Opportunity_scanner/strategies/02_crypto_funding_carry/README.md) (read-only HL fields)
- [strategy 03 — HIP-3 ↔ IBKR basis](../Opportunity_scanner/strategies/03_hip3_ibkr_basis/README.md) (read-only HIP-3 listings)
- [strategy 05 — Treasury curve / COT extremes](../Opportunity_scanner/strategies/05_treasury_curve_cot/README.md) (read-only yield curve; own CFTC pull)
- [strategy 06 — Earnings drift](../Opportunity_scanner/strategies/06_earnings_drift/README.md) (read-only actuals; own consensus-EPS sibling files)
- [strategy 09 — Sector rotation](../Opportunity_scanner/strategies/09_sector_rotation/README.md) (read-only sector ETF prices; own shares-out fetch)
