# Project Status Report: Macroeconomic Indicators Dashboard

**Project:** macro_2 - Real-time Macroeconomic Indicators Dashboard
**Last Updated:** March 30, 2026
**Version:** 2.7.0
**Status:** Production Ready

---

## Summary

A multi-frontend macroeconomic indicators dashboard tracking 88+ indicators and quarterly financials for S&P 500 companies from multiple data sources (Yahoo Finance, SEC EDGAR, FRED, Hyperliquid, Trading Economics, MOF Japan, AAII, CBOE, ECB, OECD, Ken French, Finviz, CFTC, web scrapers). Available as **4 dashboard frontends**: Streamlit, Dash, React+FastAPI, and Grafana. Includes 5-year OHLCV history for commodities/futures (back to 2021), Hyperliquid DeFi perpetual futures with per-second WebSocket updates and multi-interval OHLCV candlestick charts, global sovereign yields, yield curve regime classification, credit spreads, economic activity indicators, FX pairs, market concentration, sector ETF tracking, high-frequency macro proxies (GDPNow, WEI), 20 OpenBB-based indicators (with full fallback paths), dual-source equity financials, 13F institutional holdings, expandable price charts, compact dense layout, auto-reload cache, automated launchd scheduling, earnings monitoring, data freshness review, and a data discrepancy review agent.

---

## Dashboard Frontends (4 implementations)

| Frontend | Folder | Port(s) | Status | Notes |
|----------|--------|---------|--------|-------|
| **Streamlit** | `app.py` | 8501 | Production | Primary dashboard, compact CSS, 88+ indicators |
| **Dash** | `dash_dashboard/` | 8050 | Production | 1:1 Streamlit port, all 8 tabs, candlestick charts |
| **React + FastAPI** | `react_dashboard/` | 5173 + 8002 | Production | Vite + React 18, WebSocket HL live, lightweight-charts |
| **Grafana** | `grafana_dashboard/` | 3000 + 8001 | v1.0.0 | Docker or Homebrew, 70+ stat panels, Infinity plugin |

## Dashboard Tabs (8 tabs, all frontends)

| Tab | Name | Indicators | Status |
|-----|------|------------|--------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP, S&P 500 Multiples (Finviz), Sector P/E Ratios, Equity Risk Premium | Working |
| 2 | Market Indices | ES/RTY futures, breadth, Russell 2000 V/G, S&P 500/200MA, SPY/RSP concentration, Fama-French 5 Factors, Earnings Calendar + OHLCV charts (ES, RTY) | Working |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW, VIX Futures Curve, SPY Put/Call OI, IV Skew + OHLCV charts (VIX, MOVE) | Working |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI, Money Supply + OHLCV charts (DXY, FX, 10Y) | Working |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning (gold/silver + energy/copper via SODA API), **Hyperliquid perps** (BTC, ETH, SOL, PAXG, HYPE, OIL, SP500, XYZ100, NATGAS, COPPER, BRENTOIL) + HIP-3 spot stocks + OHLCV candlestick charts | Working |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker text input, dual-source (Yahoo + SEC EDGAR), quarterly statements | Working |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields, real yield, breakevens, HY/IG OAS, NFCI, Fed Funds, bank reserves, SLOOS, unemployment, claims, CPI, PPI, PCE, ECB Rates, CPI Components, EU Yields, Global CPI, Full Treasury Curve, Corporate Spreads | Working |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, Retail Sales, ISM Services PMI, Industrial Production, Housing Starts, OECD CLI, Intl Unemployment, Intl GDP, Global PMI | Working |

## Recent Features (v2.7.0)

### 5-Year Historical Data Extension
All yfinance-based indicators now fetch 5 years of data (back to March 2021), up from 1-2 years previously.

- **Affected extractors**: `yfinance_extractors.py`, `commodities_extractors.py`, `fidenza_extractors.py`
- **68 CSVs** now have 1,000+ rows of daily data
- **Indicators extended**: Russell 2000, S&P 500/MA200, ES/RTY futures, DXY, JPY, FX pairs, market concentration, sector ETFs, VIX term structure, all commodities, Brent, Nikkei, EM indices, credit ETFs, XAU/JPY, gold/silver ratio, fed funds futures
- **COT energy/copper positioning**: Added indicator 83 via CFTC SODA API (crude oil, Brent, copper, natural gas)
- **Dash COT display**: Tab 5 shows MM Long/Short/Net, Long Ratio, Producer Net for all energy/metals commodities
- **GMT+8 timestamps**: All Dash dashboard timestamps display in GMT+8

## Previous Features (v2.6.0)

### Hyperliquid Perpetual Futures
11 DeFi perpetual futures from Hyperliquid added to Tab 5 across all dashboards.

- **Tracked perps**: BTC, ETH, SOL, PAXG, HYPE, OIL (flx:OIL), SP500 (xyz:SP500), XYZ100 (xyz:XYZ100), NATGAS (xyz:NATGAS), COPPER (xyz:COPPER), BRENTOIL (xyz:BRENTOIL)
- **Builder-deployed perps** (flx:, xyz:): Not in standard allMids — price derived from 1m candle close
- **HIP-3 spot stocks**: TSLA, NVDA, AAPL, GOOGL, AMZN, META, MSFT, SPY, QQQ
- **WebSocket relay** (React only): Per-second price updates via `hl_ws_service.py` → `/ws/hl` endpoint → `useHyperliquidWS` hook. Toggle-controlled ("Start Live / Stop Live")
- **1-minute extraction**: `hl_extract.py` with partial cache merge (keys 84/85 only), 45s freshness guard

### OHLCV Candlestick Charts (NEW)
Multi-interval OHLCV charts across all dashboards for HL and yfinance instruments.

- **React**: TradingView lightweight-charts (`HLCandlestickChart.jsx`, `IntradayCandlestickChart.jsx`)
- **Dash/Streamlit**: Plotly `go.Candlestick()` with volume bars on secondary y-axis
- **HL intervals**: 1m, 5m, 15m, 1H, 4H, 1D (max 5000 candles, auto-capped lookback)
- **yfinance intervals**: 1H, 4H, 1D, 1W (17 instruments: DXY, FX pairs, VIX, MOVE, commodities, ES/RTY, SPY, 10Y, HYG, LQD)
- **API endpoints**: `GET /api/hl/ohlcv/{coin}?interval=`, `GET /api/intraday/{key}?interval=`

## Data Sources

| Source | Indicators | Key Required | Reliability |
|--------|------------|-------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, futures, FX, commodities, sector ETFs, equity financials | No | Excellent |
| FRED API | GDP, yields, ISM, TGA, liquidity, SOFR, spreads, CPI/PPI/PCE, employment, M1/M2 | Yes (free) | Excellent |
| **Hyperliquid** | **11 perps (BTC, ETH, SOL, PAXG, HYPE, OIL, SP500, XYZ100, NATGAS, COPPER, BRENTOIL) + 9 HIP-3 spot stocks** | **No** | **Excellent** |
| SEC EDGAR XBRL | Quarterly financials for S&P 500, 13F holdings | No (User-Agent) | Excellent |
| Trading Economics | Germany/UK/China 10Y yields, ISM Services PMI | No | Good |
| ECB SDW | ECB policy rates, European government yields | No | Good |
| Finviz | S&P 500 multiples (forward P/E, PEG, P/S, P/B) | No | Good |
| CFTC | COT positioning (gold/silver + energy/copper via SODA API) | No | Good |
| MOF Japan | Japan 2Y/10Y yields | No | Good |
| Robert Shiller (Yale) | CAPE ratio | No | Excellent |
| AAII | Investor sentiment survey | No | Good |

## Known Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Forward P/E 403 errors | MacroMicro bot detection | `65_sp500_multiples` (Finviz) provides alternative |
| Builder perps not in allMids | OIL/SP500/XYZ100/NATGAS/COPPER/BRENTOIL | Price derived from 1m candle close |
| MOVE N/A outside trading hours | No data when Treasury market closed | Expected yfinance behavior |
| TSM (IFRS) | SEC EDGAR returns no us-gaap data | Yahoo Finance only |
| Baltic Dry Index | yfinance ^BDI/BDIY delisted | Returns error dict gracefully |
| Tab 6 in Grafana | Interactive ticker selection not suited | Use Streamlit/Dash/React |
| Shiller CAPE frozen | Yale Excel `ie_data.xls` last updated Oct 2023 | Stuck at Sep 2023 value; needs alternative source |
| Global CPI (US) frozen | FRED `CPALTT01USM657N` discontinued at Mar 2024 | EU/JP/UK still updating; switch US to `CPIAUCSL` |

## Scheduling

Three **macOS launchd** jobs:
- **hl-extract**: Every 1 minute (24/7) — Hyperliquid perps + spot, partial cache merge (keys 84/85), ~0.5s, 50s timeout
- **fast-extract**: Every 5 minutes (24/7) — real-time yfinance only (31 extractors, ~5s, 4-min timeout)
- **scheduled-extract**: 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) — full FRED/SEC/web scrapers (20-min timeout)

All catch up missed runs after sleep. Freshness guards (45s HL, 3-min fast, 15-min scheduled) prevent overlap.

---

**Document Version:** 2.7.0
**Last Updated:** March 30, 2026
**Repository:** https://github.com/cdavocazh/macro_2
