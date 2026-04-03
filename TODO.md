# TODO — Macroeconomic Indicators Dashboard

**Last Updated:** March 22, 2026 (v2.6.0 — Hyperliquid perps + OHLCV candlestick charts)

---

## Completed (This Session — v2.6.0)

- [x] **Hyperliquid perpetual futures** (indicators 84, 85) — 11 perps (BTC, ETH, SOL, PAXG, HYPE, OIL, SP500, XYZ100, NATGAS, COPPER, BRENTOIL) + 9 HIP-3 spot stocks
- [x] **Builder-deployed perp support** — flx:OIL, xyz:SP500/XYZ100/NATGAS/COPPER/BRENTOIL (not in allMids, price from 1m candle)
- [x] **OHLCV candlestick charts** — React (TradingView lightweight-charts), Dash/Streamlit (Plotly go.Candlestick)
- [x] **Multi-interval support** — 1m/5m/15m/1H/4H/1D for HL, 1H/4H/1D/1W for yfinance instruments
- [x] **Intraday OHLCV API endpoints** — `/api/intraday/{key}` (17 yfinance instruments), `/api/hl/ohlcv/{coin}` (11 HL perps)
- [x] **WebSocket relay** — `hl_ws_service.py` for per-second HL price updates in React dashboard
- [x] **Live toggle** — "Start Live (~1s)" button in React Tab 5 for WebSocket activation
- [x] **1-minute HL extraction** — `hl_extract.py` with partial cache merge, `com.macro2.hl-extract.plist` launchd job
- [x] **data_aggregator.py** — Registered indicators 84_hl_perps and 85_hl_spot_stocks (now 87+ total)
- [x] **Fixed pandas FutureWarning** — `pd.to_datetime(utc=True)` in `utils/helpers.py` for mixed timezone deserialization
- [x] **Fixed Dash Tab5 metric_card 'sub' kwarg error** — Rewritten commodities section

## Completed (Previous Sessions)

- [x] **20 OpenBB-based indicators** (#63-#82) in `openbb_extractors.py` — all with fallback paths
- [x] **3 broken indicators fixed** — VIX futures, Put/Call, Forward P/E now have working alternatives
- [x] **React + FastAPI dashboard** (`react_dashboard/`) — full frontend with interactive Tab 6
- [x] **Grafana dashboard** (`grafana_dashboard/`) — 70+ stat panels, Docker + Homebrew deployment
- [x] **Dash dashboard** (`dash_dashboard/`) — full 1:1 Streamlit port, all 8 tabs
- [x] **Compact CSS layout** — 40% denser than default Streamlit
- [x] **Cache auto-reload** — mtime-based, ~0.1ms
- [x] **Fidenza Macro extractors** — 13 gap-fill functions
- [x] **OHLCV extension** — 2-year history for commodities + futures
- [x] **Sector ETFs** — 11 SPDR ETFs
- [x] **13F holdings** — 5 institutional funds
- [x] **Earnings monitoring** — flag stale data
- [x] **S&P 500 batch extraction** — ~500 tickers
- [x] **COT energy/copper** — CFTC SODA API for crude, Brent, copper, natgas

## In Progress

- [ ] **Grafana time-series panels**: Current dashboard uses stat panels only. Graph panels can be added using `/api/timeseries/{key}` endpoints
- [ ] **Grafana HL integration**: `/api/hl/ohlcv/{coin}` endpoint exists but Grafana dashboard JSON needs panels added

## Backlog — Dashboard Improvements

- [ ] **Dark mode toggle**: Add client-side dark/light theme switch (Dash + React)
- [ ] **Mobile responsiveness**: Test compact CSS at smaller viewport widths
- [ ] **CSV export button**: React dashboard has no export — uses parent project's `scheduled_extract.py`
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

## Backlog — Architecture

- [ ] **Unified API layer**: React and Grafana backends duplicate some serialization logic. Consider shared FastAPI app
- [ ] **CI/CD pipeline**: Automated testing + deployment for all 4 dashboard frontends

---

**Priority Guide:**
- P0 (Critical): None — all dashboards operational
- P1 (High): Grafana HL panels, OpenBB installation
- P2 (Medium): Data extraction batch updates, dark mode
- P3 (Low): Unified API, CI/CD
