# TODO — Macroeconomic Indicators Dashboard

**Last Updated:** March 14, 2026 (v2.5.0 — React+FastAPI + Grafana dashboards + 20 OpenBB indicators)

---

## Completed (This Session)

- [x] **20 OpenBB-based indicators** (#63-#82) in `openbb_extractors.py` — all with fallback paths
- [x] **3 broken indicators fixed** — VIX futures, Put/Call, Forward P/E now have working alternatives
- [x] **React + FastAPI dashboard** (`react_dashboard/`) — full 82-indicator frontend with interactive Tab 6
- [x] **Grafana dashboard** (`grafana_dashboard/`) — 70+ stat panels, Docker + Homebrew deployment
- [x] **Dash dashboard OpenBB indicators** — all 20 indicators displayed across tabs 1-4, 7-8
- [x] **Streamlit dashboard OpenBB indicators** — all 20 indicators displayed across tabs 1-4, 7-8
- [x] **Data aggregator updated** — 82 total indicators registered (was 62)
- [x] **Historical CSV export** — 20 new CSV wrappers in `extract_historical_data.py`
- [x] **CLAUDE.md updated** — architecture, tab tables, known-broken, design decisions, test commands
- [x] **Grafana local deployment** — Homebrew install, provisioning setup, Infinity plugin

## Completed (Previous Sessions)

- [x] **Dash dashboard** (`dash_dashboard/`) — full 1:1 Streamlit port, all 8 tabs
- [x] **Compact CSS layout** — 40% denser than default Streamlit
- [x] **Cache auto-reload** — mtime-based, ~0.1ms
- [x] **Fidenza Macro extractors** — 13 gap-fill functions
- [x] **OHLCV extension** — 2-year history for commodities + futures
- [x] **Sector ETFs** — 11 SPDR ETFs
- [x] **13F holdings** — 5 institutional funds
- [x] **Earnings monitoring** — flag stale data
- [x] **S&P 500 batch extraction** — ~500 tickers

## In Progress

- [ ] **Grafana time-series panels**: Current dashboard uses stat panels only. Graph panels can be added using `/api/timeseries/{key}` endpoints
- [ ] **Grafana Docker first-launch**: Docker Desktop requires GUI license acceptance before daemon starts — no workaround for fully headless setup

## Backlog — Dashboard Improvements

- [ ] **Dark mode toggle**: Add client-side dark/light theme switch (Dash + React)
- [ ] **OHLCV candlestick charts**: React dashboard only shows line charts — add candlestick option for commodities/futures
- [ ] **Mobile responsiveness**: Test compact CSS at smaller viewport widths (5-column FX row may need breakpoints)
- [ ] **CSV export button**: React dashboard has no export — uses parent project's `scheduled_extract.py`
- [ ] **Grafana time-series graphs**: Add Plotly-style history charts to Grafana using timeseries endpoints
- [ ] **Grafana alerts**: Configure threshold-based Grafana alerts (e.g., VIX > 30, Sahm Rule > 0.50)

## Backlog — Data Sources

- [ ] **Finnhub/Simfin sources**: Add 3rd/4th data source options to Tab 6 (requires API keys)
- [ ] **S&P 500 batch update**: Run `extract_sp500_financials.py --source both --resume` for new constituents
- [ ] **13F holdings quarterly update**: Run `extract_13f_holdings.py` after quarterly filing deadline
- [ ] **OpenBB installation**: Install OpenBB Platform for primary data paths (currently all using fallbacks)

## Backlog — Known Broken Indicators

- [ ] **Baltic Dry Index**: yfinance ^BDI/BDIY delisted. Need alternative data source
- [ ] **OPEC Production**: EIA API needs key; Trading Economics page structure changed
- [ ] **Gold Reserves Share**: World Gold Council URL returns 404
- [ ] **SPY ETF expanded fundamentals**: forwardPE/trailingEps return None from yfinance for ETFs

## Backlog — Architecture

- [ ] **WebSocket live data**: Current polling (5-min fast_extract) has inherent lag. Major architectural change.
- [ ] **Unified API layer**: React and Grafana backends duplicate some serialization logic. Consider shared FastAPI app.
- [ ] **CI/CD pipeline**: Automated testing + deployment for all 4 dashboard frontends

---

**Priority Guide:**
- P0 (Critical): None — all dashboards operational
- P1 (High): Grafana time-series panels, OpenBB installation
- P2 (Medium): Data extraction batch updates, dark mode, candlestick charts
- P3 (Low): WebSocket architecture, unified API, CI/CD
