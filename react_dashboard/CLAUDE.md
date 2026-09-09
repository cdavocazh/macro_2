# CLAUDE.md - React Dashboard

React + FastAPI alternative frontend for the Macro Indicators Dashboard.

## What this is

A React frontend (Vite) + FastAPI backend that mirrors all 88+ indicators from the parent project's Streamlit app. The backend imports from the parent `data_aggregator.py` directly -- no data layer duplication. Includes a **WebSocket relay** for real-time (~1s) Hyperliquid data updates.

## Quick commands

```bash
bash start.sh                    # start both backend and frontend
cd backend && python main.py     # backend only (port 8000)
cd frontend && npm run dev       # frontend only (port 5173, proxies /api + /ws to 8000)
cd frontend && npm run build     # production build to frontend/dist/
```

## Key files

- `backend/main.py` -- FastAPI endpoints + `/api/intraday/{key}` + `/api/hl/ohlcv/{coin}` OHLCV endpoints
- `backend/hl_ws_service.py` -- Hyperliquid WebSocket relay (singleton, starts/stops with server)
- `frontend/src/App.jsx` -- 11 tabs, auto-refresh, loading states, calendar strip, ⌘K palette
- `frontend/src/tabs/Tab1-9*.jsx` -- one component per tab (includes Tab9Polymarket)
- `frontend/src/utils/time.js` -- GMT+8 timezone conversion utility
- `frontend/src/hooks/useHyperliquidWS.js` -- React hook for WebSocket HL data (toggle-controlled)
- `frontend/src/components/HLCandlestickChart.jsx` -- OHLCV candlestick chart for HL perps (TradingView lightweight-charts)
- `frontend/src/components/IntradayCandlestickChart.jsx` -- OHLCV candlestick chart for yfinance instruments (TradingView lightweight-charts)
- `frontend/src/components/` -- MetricCard, ErrorCard, HistoryChart, etc.
- `frontend/src/api.js` -- axios client for `/api/*` endpoints (`fetchAllIndicators(lite)`)
- `backend/analytics.py` -- series resolver, correlation, monitor grid, regime composite, forward-return study, calendar + 13F loaders (all derived from already-extracted data). **Correlation runs on log returns, never levels**; `build_series_catalog()` / `resolve_series()` are the shared access layer every relationship analytic should use.
- `frontend/src/components/CorrelationPanel.jsx` -- pair picker, rolling correlation with z-vs-own-history, heatmap
- `frontend/src/components/ChartDrawer.jsx` -- full-width 82vh chart drawer + `useChartDrawer()` + `ExpandChartButton`
- `frontend/src/components/TradingViewWidget.jsx` -- free Advanced Chart embed, lazy-loaded, attribution retained
- `frontend/src/config/instruments.js` -- instrument → TradingView symbol map. **Futures are NOT licensed in the free widget** (`COMEX:GC1!` renders an error), so they map to free proxies carrying a `proxyNote` the drawer shows. Verify any new symbol in the actual widget, not just symbol search.
- `frontend/src/tabs/Tab10Monitor.jsx` / `Tab11Positioning.jsx` -- monitor + consolidated positioning
- `frontend/src/components/LazyPlot.jsx` -- React.lazy wrapper for react-plotly.js; keeps plotly's ~1.47 MB gz out of the main bundle (charts load it on first expand). **Never import `react-plotly.js` directly — import LazyPlot.**

## First-load performance (2026-08-31)

- `/api/indicators?lite=1` strips all serialized pandas series (any depth) → 36 KB gz vs 1.5 MB; `App.jsx` fetches lite first (instant cards), then full in the background.
- Polling: every 60 s tick fetches lite and deep-merges over current state (`mergePreserving` — keeps series the lite payload strips); every 5th tick fetches full. Never let a lite response REPLACE state — open charts would lose their data.
- Backend memoizes the serialized payload on the cache file's mtime (`_serialized_snapshot`); the IBKR overlay copy-on-writes touched indicators so the memo is never mutated.
- nginx: `/assets/` is `Cache-Control: immutable` + `gzip_static` (deploy step: `gzip -k9f dist/assets/*.js *.css` after `vite build`); `index.html` is `no-cache` so post-deploy HTML always revalidates.

## Hyperliquid real-time architecture

```
Hyperliquid WS (wss://api.hyperliquid.xyz/ws)
  → hl_ws_service.py (relay, subscribes to allMids, fetches contexts every 5s via REST)
    → FastAPI /ws/hl endpoint (broadcasts to connected React clients)
      → useHyperliquidWS hook (auto-reconnect, toggle-controlled)
        → Tab5Commodities (live price updates, ~1s when enabled)
```

The relay starts automatically with the FastAPI backend and stops when the backend exits.
No standalone launchd service — the WebSocket connection only lives while the dashboard is running.
Users click "Start Live" in Tab 5 to activate the WebSocket connection in the browser.

## OHLCV Candlestick Charts

All price indicators in tabs 2-5 now have expandable OHLCV candlestick charts using TradingView lightweight-charts (Apache 2.0, Canvas-based, ~45KB).

**Two chart types:**
- `IntradayCandlestickChart` — yfinance-backed (ES, RTY, VIX, MOVE, DXY, FX pairs, commodities, 10Y yield). Intervals: 1H, 4H, 1D, 1W. Endpoint: `GET /api/intraday/{key}?interval=`
- `HLCandlestickChart` — Hyperliquid-backed (BTC, ETH, SOL, PAXG, HYPE, OIL). Intervals: 1m, 5m, 15m, 1H, 4H, 1D. Endpoint: `GET /api/hl/ohlcv/{coin}?interval=`

**Tracked HL perps:** BTC, ETH, SOL, PAXG, HYPE, OIL (flx:OIL — builder-deployed WTI crude oil).
OIL uses qualified coin name `flx:OIL` in API calls (not in allMids, price derived from candle data).
Max candles: 5000 per request. Lookback auto-capped per interval (1m→3d, 1h→90d, 1d→90d).

## Indicator keys

The backend serves indicators using the same keys as `data_aggregator.py`:
`1_sp500_forward_pe`, `2_russell_2000`, ..., `82_erp`, `84_hl_perps`, `85_hl_spot_stocks`, `polymarket`

See the parent project's `CLAUDE.md` for the full indicator list and data flow.

## See also

- [`STATUS.md`](STATUS.md) — React dashboard implementation status and version tracking
- [`README.md`](README.md) — User-facing overview, quick start, directory structure
