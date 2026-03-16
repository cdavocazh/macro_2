# Project Status Report: Macroeconomic Indicators Dashboard

**Project:** macro_2 - Real-time Macroeconomic Indicators Dashboard
**Last Updated:** March 13, 2026
**Version:** 2.4.0
**Status:** Production Ready

---

## Summary

A Streamlit dashboard tracking 75+ macroeconomic indicators and quarterly financials for S&P 500 companies from multiple data sources (Yahoo Finance, SEC EDGAR, FRED, Trading Economics, MOF Japan, AAII, web scrapers). Includes 2-year OHLCV history for commodities/futures, global sovereign yields, yield curve regime classification, credit spreads, economic activity indicators (employment, consumer, production), FX pairs, market concentration, sector ETF tracking, high-frequency macro proxies (GDPNow, WEI), dual-source equity financials, 13F institutional holdings, expandable price charts, compact dense layout, auto-reload cache, automated launchd scheduling, earnings monitoring, data freshness review, and a data discrepancy review agent.

---

## Dashboard Tabs (8 tabs)

| Tab | Name | Indicators | Status |
|-----|------|------------|--------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP | Working (Forward P/E unreliable) |
| 2 | Market Indices | ES/RTY futures, market breadth, Russell 2000 V/G, S&P 500/200MA, SPY/RSP concentration | Working |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW | Working (Put/Call unreliable) |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI | Working |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning | Working |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker text input, S&P 500 batch extraction, dual-source (Yahoo + SEC EDGAR) | Working (TSM SEC only fails — IFRS) |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields (US 5Y/10Y, DE/UK/CN 10Y), real yield, breakevens, HY/IG OAS, NFCI, Fed Funds, bank reserves, SLOOS, unemployment, claims (initial+continuing), headline/core CPI, PPI, core PCE | Working |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, Retail Sales, ISM Services PMI, Industrial Production, Housing Starts | Working |

## Recent Features (v2.4.0)

### Dashboard Compact Layout + Cache Auto-Reload

**Cache auto-reload** — Fixed stale dashboard data caused by singleton aggregator pattern. Added `reload_if_stale()` to `data_aggregator.py` that compares cache file mtime against in-memory `last_update` (~0.1ms). Dashboard now picks up `scheduled_extract.py` updates automatically on Streamlit rerun without manual Refresh.

**Compact dense layout** — Custom CSS injection reduces Streamlit default spacing by ~40%:
- Metric padding shrunk to 0.2rem, value font 1.3rem, label 0.72rem
- Column/block gaps reduced to 0.3rem, captions 0.68rem
- 17 tab dividers removed, 21+ verbose captions pruned
- 7 standalone charts collapsed into `st.expander()` (saves ~400px each when collapsed)
- Tab 1: Deleted Historical Valuation section (removed slow `yf.Ticker("SPY")` network call + 500px chart)
- Tab 3: VIX/MOVE/Ratio merged into 3 columns (was 2 + full-width)
- Tab 4: All 5 FX pairs merged into single 5-column row (was 2 + 3 in separate rows)
- Sidebar About collapsed from ~200px into single expander

**Data extraction expansion (v2.3.1)** — 13 new extractors, 75+ total indicators:
- 7 OHLCV CSVs with 2-year history (504 trading days) for commodities + futures
- Sector ETFs (11 SPDR), VIX term structure, GDPNow, WEI
- Fidenza Macro gap-fill: Brent, Nikkei, EM indices, SOFR/FF futures, XAU/JPY, Au/Ag ratio, AAII sentiment
- FRED additions: ADP employment, WALCL, term premia, existing home sales

**Files changed:** `app.py` (2401→2297 lines), `data_aggregator.py` (+`reload_if_stale()`)

### Previous: Economic Activity Tab (Tab 8) + 21 New Indicators (v2.3.0)
Expanded dashboard from 41 to 62+ indicators across 8 tabs.

**New Tab 8: Economic Activity** — 3 sections:
1. **Employment & Recession Risk**: Nonfarm Payrolls, JOLTS Job Openings, Quits Rate, Sahm Rule (with 0.50 recession threshold chart)
2. **Consumer**: UMich Consumer Sentiment, Retail Sales (MoM%)
3. **Production & Housing**: ISM Services PMI (scraped from Trading Economics), Industrial Production (YoY%), Housing Starts

**Expanded existing tabs:**
- Tab 2: SPY/RSP Market Concentration ratio (mega-cap vs equal-weight)
- Tab 4: EUR/USD, GBP/USD, EUR/JPY FX pairs + M2 Money Supply
- Tab 5: Natural Gas futures + Copper/Gold ratio (economic sentiment indicator)
- Tab 7: 5Y Treasury Yield, IG Credit Spread (OAS), Bank Reserves, SLOOS Lending Standards, Continuing Claims, Headline CPI YoY%, PPI YoY%

**New extractors:**
- 16 new functions in `fred_extractors.py` (NFP, JOLTS, Sahm, M2, quits, retail sales, housing starts, industrial production, 5Y yield, bank reserves, IG OAS, continuing claims, headline CPI, PPI, SLOOS, consumer sentiment)
- 2 new functions in `yfinance_extractors.py` (major FX pairs, SPY/RSP concentration)
- 2 new functions in `commodities_extractors.py` (natural gas, Cu/Au ratio)
- 1 new function in `global_yields_extractor.py` (ISM Services PMI scrape)

### Previous: Rates & Credit Tab (Tab 7) — v2.2.0 — 12 New Indicators
New dashboard tab with 5 sections covering rates, credit, and macro fundamentals:

1. **Yield Curve & Regime Classification**: 2s10s spread with automated regime detection (Bull/Bear Steepener/Flattener) using 20-business-day lookback. Color-coded badge with signal and detail explanation.
2. **Global 10Y Sovereign Yields**: US, Germany, UK, China 10Y government bond yields. Trading Economics scrape for daily values, FRED OECD for historical charts (Germany/UK).
3. **Real Yields & Inflation Expectations**: 10Y TIPS real yield, 5Y & 10Y breakeven inflation rates. Includes Nominal vs Real vs Breakeven overlay chart with Fed 2% target line.
4. **Credit & Financial Conditions**: ICE BofA HY OAS spread, Chicago Fed NFCI, Effective Fed Funds Rate.
5. **Labor Market & Inflation**: Unemployment rate, initial jobless claims, Core CPI YoY%, Core PCE YoY%.

### New Extractors
- `global_yields_extractor.py` — Scrapes Trading Economics for Germany/UK/China 10Y yields, FRED OECD monthly fallback
- `yield_curve_extractor.py` — FRED T10Y2Y + DGS2/DGS10 with regime classification logic
- 8 new functions in `fred_extractors.py` — HY OAS, breakevens, real yield, NFCI, Fed Funds, claims, unemployment, core inflation (CPI+PCE YoY%)

## Previous Features (v2.0.0)

### Expandable 3M Price Charts
Every indicator in tabs 1, 3, 4, 5 has a collapsible plotly chart below the metric card. Users click to expand/collapse. Charts include 1W/1M/3M range selector buttons and a range slider for manual date selection.

### Large-cap Equity Financials (Tab 6)
- **20 companies** tracked: AAPL, MSFT, NVDA, GOOGL, AMZN, META, BRK-B, TSM, LLY, AVGO, JPM, V, WMT, MA, XOM, UNH, COST, HD, PG, JNJ
- **Dual data source**: Yahoo Finance (primary) and SEC EDGAR XBRL (secondary) with radio button toggle
- **Quarterly statements**: Income Statement, Balance Sheet, Cash Flow with QoQ/YoY colored percentage changes
- **Financial analysis**: Profitability, turnover, returns with numerator/denominator display
- **Valuation**: P/E, P/B, P/S, EV/EBITDA, EV/FCF with component breakdown
- **Revenue segments**: From 10-K XBRL instance documents (SEC EDGAR source)

### SEC EDGAR XBRL Integration
- Free API, 10 req/sec, no key needed
- FY-end quarter derivation: Q4 = Annual - (Q1+Q2+Q3)
- Cumulative YTD cash flow detection and correction (NVDA)
- Cross-concept merging for companies using different XBRL concepts (GOOGL, AVGO, MA, JPM)
- 19/19 US companies have full 5/5 coverage (Revenue, Net Income, Cash Flow, Balance Sheet)

### Dual-Source Historical Data Storage
Equity financial CSVs are now organized by data source:
```
historical_data/equity_financials/
  ├── yahoo_finance/{TICKER}_quarterly.csv
  └── sec_edgar/{TICKER}_quarterly.csv
```

### S&P 500 Expansion & Monitoring (v2.1.0)
- **S&P 500 ticker list**: `sp500_tickers.py` fetches ~503 tickers from Wikipedia, cached with 7-day TTL
- **Batch extraction**: `extract_sp500_financials.py` extracts financials for all S&P 500 companies (~30-40 min)
- **Custom ticker input**: Tab 6 text input allows viewing any ticker on-demand (not just Top 20)
- **Earnings monitoring**: `monitor_earnings.py` compares local data vs yfinance earnings dates, flags stale companies
- **Data freshness review**: `review_data_freshness.py` compares local data vs SEC EDGAR filing dates
- **Auto-update**: Both monitoring scripts support `--auto-update` to re-extract stale tickers
- **Lightweight SEC lookup**: `get_latest_filing_dates()` uses submissions endpoint (~100KB) instead of full companyfacts (~2-10MB)

### Data Discrepancy Review Agent
AI agent in `/agent/` subfolder that reviews financial data quality using 8 shared tools. Two implementations:
- OpenAI Agents SDK + Minimax LLM
- LangChain + LangGraph + Minimax LLM

---

## Data Sources

| Source | Indicators | Key Required | Reliability |
|--------|------------|-------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, Russell 2000, ES/RTY futures, JPY, EUR/USD, GBP/USD, EUR/JPY, SPY/RSP, S&P 500, commodities (incl. NG), equity financials | No | Excellent |
| FRED API | GDP, yields (2Y/5Y/10Y), ISM PMI, TGA, liquidity, SOFR, HY/IG OAS, breakevens, real yield, NFCI, Fed Funds, claims, unemployment, core CPI/PCE, headline CPI, PPI, M2, NFP, JOLTS, Sahm Rule, bank reserves, SLOOS, etc. | Yes (free) | Excellent |
| Trading Economics | Germany/UK/China 10Y yields, ISM Services PMI (web scrape) | No | Good |
| SEC EDGAR XBRL | Quarterly financials for S&P 500 companies | No (User-Agent only) | Excellent |
| MOF Japan | Japan 2Y/10Y yields (CSV download) | No | Good |
| Robert Shiller (Yale) | CAPE ratio (Excel download) | No | Excellent |
| CFTC | COT positioning (weekly report) | No | Good |
| MacroMicro | Forward P/E | No | Poor (403 errors) |
| CBOE/ycharts | Put/Call ratio | No | Poor (blocked) |

## Known Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Forward P/E 403 errors | MacroMicro bot detection | Falls back to trailing P/E |
| Put/Call ratio unreliable | CBOE/ycharts DOM changes + yfinance tickers delisted | Falls back to FRED PCERTOT |
| TSM (IFRS) | SEC EDGAR returns no us-gaap data | Yahoo Finance only |
| ISM PMI proxy | Uses Industrial Production normalized to PMI scale | Approximation, ~5% error |
| SEC rate limit | 10 req/sec | Built-in 0.15s delay between requests |
| Baltic Dry Index | yfinance ^BDI/BDIY tickers delisted | Returns error dict gracefully |
| VIX Futures (VX=F) | Ticker not available on yfinance | VIX spot works, front-month unavailable |
| OPEC Production | No EIA_API_KEY; Trading Economics page changed | Returns error dict gracefully |
| Gold Reserves Share | WGC URL returns 404 | Returns error dict gracefully |
| SPY ETF expanded fundamentals | forwardPE, trailingEps, forwardEps return None from yfinance for ETFs | 5 basic fields work (P/E, P/B, earnings yield, div yield, price) |

## Scheduling

Two **macOS launchd** jobs:
- **fast-extract**: Every 5 minutes (24/7) — real-time yfinance only (31 extractors, ~5s, 4-min timeout)
- **scheduled-extract**: 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) — full FRED/SEC/web scrapers (10-min timeout)

Both catch up missed runs after sleep. Freshness guards (3-min fast, 15-min scheduled) prevent overlap. Dashboard auto-reloads cache via `reload_if_stale()` when `scheduled_extract.py` updates the JSON file.

## File Count

- **Python modules**: 21+ files
- **Dashboard**: ~2,300 lines (app.py, compact layout)
- **SEC extractor**: ~1,250 lines
- **Total LOC**: ~10,000+
- **Documentation**: 10+ markdown files

---

**Document Version:** 2.4.0
**Last Updated:** March 13, 2026
**Repository:** https://github.com/cdavocazh/macro_2
