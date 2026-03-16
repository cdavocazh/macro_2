# Project Status Report: Macroeconomic Indicators Dashboard

**Project:** macro_2 - Real-time Macroeconomic Indicators Dashboard
**Last Updated:** March 14, 2026
**Version:** 2.5.0
**Status:** Production Ready

---

## Summary

A multi-frontend macroeconomic indicators dashboard tracking 82+ indicators and quarterly financials for S&P 500 companies from multiple data sources (Yahoo Finance, SEC EDGAR, FRED, Trading Economics, MOF Japan, AAII, CBOE, ECB, OECD, Ken French, web scrapers). Available as **4 dashboard frontends**: Streamlit, Dash, React+FastAPI, and Grafana. Includes 2-year OHLCV history for commodities/futures, global sovereign yields, yield curve regime classification, credit spreads, economic activity indicators, FX pairs, market concentration, sector ETF tracking, high-frequency macro proxies (GDPNow, WEI), 20 OpenBB-based indicators (with full fallback paths), dual-source equity financials, 13F institutional holdings, expandable price charts, compact dense layout, auto-reload cache, automated launchd scheduling, earnings monitoring, data freshness review, and a data discrepancy review agent.

---

## Dashboard Frontends (4 implementations)

| Frontend | Folder | Port(s) | Status | Notes |
|----------|--------|---------|--------|-------|
| **Streamlit** | `app.py` | 8501 | ✅ Production | Primary dashboard, compact CSS, 82 indicators |
| **Dash** | `dash_dashboard/` | 8050 | ✅ Production | 1:1 Streamlit port, all 8 tabs including OpenBB indicators |
| **React + FastAPI** | `react_dashboard/` | 5173 + 8000 | ✅ v1.0.0 | Vite + React 18, all 82 indicators, Tab 6 interactive financials |
| **Grafana** | `grafana_dashboard/` | 3000 + 8001 | ✅ v1.0.0 | Docker or Homebrew, 70+ stat panels, Infinity plugin |

## Dashboard Tabs (8 tabs, all frontends)

| Tab | Name | Indicators | Status |
|-----|------|------------|--------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP, S&P 500 Multiples (Finviz), Sector P/E Ratios, Equity Risk Premium | Working |
| 2 | Market Indices | ES/RTY futures, breadth, Russell 2000 V/G, S&P 500/200MA, SPY/RSP concentration, Fama-French 5 Factors, Earnings Calendar | Working |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW, VIX Futures Curve, SPY Put/Call OI, IV Skew | Working |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI, Money Supply (M1/M2) | Working |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning | Working |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker text input, dual-source (Yahoo + SEC EDGAR), quarterly statements | Working (Streamlit/Dash/React only — Grafana excluded) |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields, real yield, breakevens, HY/IG OAS, NFCI, Fed Funds, bank reserves, SLOOS, unemployment, claims, CPI, PPI, PCE, ECB Rates, CPI Components, EU Yields, Global CPI, Full Treasury Curve, Corporate Spreads | Working |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, Retail Sales, ISM Services PMI, Industrial Production, Housing Starts, OECD CLI, Intl Unemployment, Intl GDP, Global PMI | Working |

## Recent Features (v2.5.0)

### React + FastAPI Dashboard (NEW)
Full React 18 + Vite + FastAPI implementation of the dashboard with all 82 indicators.

- **Backend** (`react_dashboard/backend/main.py`): FastAPI with 6 endpoints wrapping `data_aggregator`. Full pandas/numpy serialization. Zero data layer duplication.
- **Frontend**: 8 tab components, 5 reusable UI components (MetricCard, ErrorCard, HistoryChart, SectionHeader, TabPanel)
- **Tab 6 interactive financials**: Top 20 dropdown + custom ticker input + Yahoo/SEC toggle — full quarterly statements, financial analysis, valuation, revenue segments
- **Collapsible Plotly charts**: 1W/1M/3M range buttons, matching Streamlit behavior
- **Auto-refresh**: 60-second polling interval
- **Startup**: `bash start.sh` launches both backend (:8000) and frontend (:5173)

### Grafana Dashboard (NEW)
Grafana-based dashboard with 70+ stat panels and threshold-based coloring.

- **API Bridge** (`grafana_dashboard/api_bridge/main.py`): FastAPI with `/api/metrics/summary` (flat ~150 key-value dict), `/api/timeseries/{key}`, SimpleJSON endpoints, and grouped indicator endpoints
- **Pre-built dashboard**: 111 stat panels in 7 rows (tabs 1-5, 7-8) with auto-provisioning
- **Deployment options**: Docker Compose (recommended) or local Homebrew install
- **Infinity plugin**: JSON API data source for querying the API bridge
- **Tab 6 excluded**: Interactive ticker selection not suited for Grafana's static panel model

### 20 OpenBB-Based Indicators (#63-#82)
Added 20 new extractors in `openbb_extractors.py`. All have fallback paths — dashboard works without OpenBB installed.

**Fixes 3 known-broken indicators:**
- VIX Futures → `63_vix_futures_curve` (CBOE/yfinance fallback)
- Put/Call Ratio → `64_spy_put_call_oi` (FRED PCERTOT/yfinance fallback)
- Forward P/E → `65_sp500_multiples` (Finviz/yfinance fallback)

**17 new indicators:**
- Tab 1: S&P 500 Multiples (Finviz), Sector P/E Ratios, Equity Risk Premium
- Tab 2: Fama-French 5 Factors, Earnings Calendar
- Tab 3: VIX Futures Curve, SPY Put/Call OI, IV Skew
- Tab 4: Money Supply M1/M2
- Tab 7: ECB Rates, CPI Components, EU Yields, Global CPI, Full Treasury Curve, Corporate Spreads
- Tab 8: OECD CLI, Intl Unemployment, Intl GDP, Global PMI

**Fallback highlights:**
- ECB rates: Direct ECB SDW REST API
- Fama-French: Ken French data library ZIP download
- European yields: ECB SDW SDMX REST API
- All FRED-based fallbacks: Existing FRED API key

### Deployment

| Frontend | How to start | Prerequisites |
|----------|-------------|--------------|
| Streamlit | `streamlit run app.py` | Python deps |
| Dash | `cd dash_dashboard && python app.py` | Python deps |
| React+FastAPI | `cd react_dashboard && bash start.sh` | Node.js 18+, Python deps |
| Grafana (Docker) | `cd grafana_dashboard && ./start.sh` | Docker Desktop |
| Grafana (local) | `cd grafana_dashboard && ./start.sh local` | Homebrew (macOS) |

## Previous Features (v2.4.0)

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

**Data extraction expansion (v2.3.1)** — 13 new extractors, 62+ total indicators:
- 7 OHLCV CSVs with 2-year history (504 trading days) for commodities + futures
- Sector ETFs (11 SPDR), VIX term structure, GDPNow, WEI
- Fidenza Macro gap-fill: Brent, Nikkei, EM indices, SOFR/FF futures, XAU/JPY, Au/Ag ratio, AAII sentiment
- FRED additions: ADP employment, WALCL, term premia, existing home sales

### Previous: Economic Activity Tab (Tab 8) + 21 New Indicators (v2.3.0)
Expanded dashboard from 41 to 62+ indicators across 8 tabs.

### Previous: Rates & Credit Tab (Tab 7) — v2.2.0 — 12 New Indicators
New dashboard tab with 5 sections covering rates, credit, and macro fundamentals.

### Previous: Large-cap Equity Financials (Tab 6) — v2.0.0
- 20 companies tracked with dual data source (Yahoo + SEC EDGAR)
- Quarterly statements, financial analysis, valuation, revenue segments

### Previous: S&P 500 Expansion & Monitoring (v2.1.0)
- S&P 500 ticker list, batch extraction, custom ticker input
- Earnings monitoring, data freshness review, auto-update

### Previous: 13F Institutional Holdings + Data Agent
- 13F-HR institutional holdings (5 funds, QoQ changes)
- Data discrepancy review agent (OpenAI Agents SDK + LangChain)

---

## Data Sources

| Source | Indicators | Key Required | Reliability |
|--------|------------|-------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, Russell 2000, ES/RTY futures, JPY, EUR/USD, GBP/USD, EUR/JPY, SPY/RSP, S&P 500, commodities, sector ETFs, equity financials, Fama-French (fallback) | No | Excellent |
| FRED API | GDP, yields, ISM PMI, TGA, liquidity, SOFR, HY/IG OAS, breakevens, real yield, NFCI, Fed Funds, claims, unemployment, CPI/PCE/PPI, M1/M2, NFP, JOLTS, Sahm Rule, OECD CLI, intl unemployment/GDP, corporate spreads, etc. | Yes (free) | Excellent |
| Trading Economics | Germany/UK/China 10Y yields, ISM Services PMI (web scrape) | No | Good |
| SEC EDGAR XBRL | Quarterly financials for S&P 500 companies, 13F holdings | No (User-Agent only) | Excellent |
| ECB SDW | ECB policy rates, European government yields (REST API fallback) | No | Good |
| OECD | Leading indicator (via FRED fallback) | No | Good |
| Ken French Library | Fama-French 5 factors (ZIP download fallback) | No | Good |
| Finviz | S&P 500 multiples (forward P/E, PEG, P/S, P/B) | No | Good |
| MOF Japan | Japan 2Y/10Y yields (CSV download) | No | Good |
| Robert Shiller (Yale) | CAPE ratio (Excel download) | No | Excellent |
| CFTC | COT positioning (weekly report) | No | Good |
| AAII | Investor sentiment survey (web scrape) | No | Good |

## Known Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Forward P/E 403 errors | MacroMicro bot detection | `65_sp500_multiples` (Finviz) provides alternative |
| Put/Call ratio unreliable | CBOE/ycharts DOM changes | `64_spy_put_call_oi` (CBOE/yfinance) provides alternative |
| TSM (IFRS) | SEC EDGAR returns no us-gaap data | Yahoo Finance only |
| VIX Futures (VX=F) | Ticker not available on yfinance | `63_vix_futures_curve` (CBOE/yfinance) provides alternative |
| Baltic Dry Index | yfinance ^BDI/BDIY tickers delisted | Returns error dict gracefully |
| OPEC Production | No EIA_API_KEY; TE page changed | Returns error dict gracefully |
| Gold Reserves Share | WGC URL returns 404 | Returns error dict gracefully |
| Tab 6 in Grafana | Interactive ticker selection not suited | Use Streamlit/Dash/React for financials |
| OpenBB not installed | Optional dependency | All 20 functions have full fallback paths |

## Scheduling

Two **macOS launchd** jobs:
- **fast-extract**: Every 5 minutes (24/7) — real-time yfinance only (31 extractors, ~5s, 4-min timeout)
- **scheduled-extract**: 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) — full FRED/SEC/web scrapers (10-min timeout)

Both catch up missed runs after sleep. Freshness guards (3-min fast, 15-min scheduled) prevent overlap. Dashboard auto-reloads cache via `reload_if_stale()` when `scheduled_extract.py` updates the JSON file.

## File Count

- **Python modules**: 25+ files
- **React components**: 15 JSX files
- **Dashboard frontends**: 4 (Streamlit, Dash, React, Grafana)
- **Streamlit dashboard**: ~2,300 lines (app.py)
- **React frontend**: ~2,500 lines (JSX + CSS)
- **Grafana dashboard JSON**: ~1,300 lines (111 panels)
- **Total LOC**: ~15,000+
- **Documentation**: 15+ markdown files

---

**Document Version:** 2.5.0
**Last Updated:** March 14, 2026
**Repository:** https://github.com/cdavocazh/macro_2
