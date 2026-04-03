# Implementation Plan for Dashboard Enhancements

## Requirements Overview

### Requirement 1: Commodities Tab ✅ DONE
Add continuous price data for Gold, Silver, Crude Oil, Copper.

### Requirement 2: 10Y Yield vs ISM Chart ✅ DONE
Dual-axis chart in Macro & Currency tab.

### Requirement 3: Source URLs ✅ DONE
Embedded links to data sources beside each indicator title.

### Requirement 4: Historical Charts ✅ DONE
Historical price chart with weekly/monthly toggle in Valuation Metrics tab.

### Requirement 5: Hyperliquid Perpetual Futures ✅ DONE (v2.6.0)
Add DeFi perpetual futures from Hyperliquid to Tab 5 (Commodities).

**Tracked perps (11 instruments):**

| Coin | API Name | Category | Deployer |
|------|----------|----------|----------|
| BTC | `BTC` | Crypto | Native |
| ETH | `ETH` | Crypto | Native |
| SOL | `SOL` | Crypto | Native |
| PAXG | `PAXG` | Commodity (Gold) | Native |
| HYPE | `HYPE` | Crypto | Native |
| OIL | `flx:OIL` | Commodity (WTI Crude) | Felix (builder) |
| SP500 | `xyz:SP500` | Index | Trade.xyz (builder) |
| XYZ100 | `xyz:XYZ100` | Index (Nasdaq 100) | Trade.xyz (builder) |
| NATGAS | `xyz:NATGAS` | Commodity | Trade.xyz (builder) |
| COPPER | `xyz:COPPER` | Commodity | Trade.xyz (builder) |
| BRENTOIL | `xyz:BRENTOIL` | Commodity | Trade.xyz (builder) |

**Implementation:**
- [x] `data_extractors/hyperliquid_extractor.py` — Core extractor with allMids + metaAndAssetCtxs + candleSnapshot
- [x] Builder perps (flx:, xyz:) handled via 1m candle close for price (not in allMids)
- [x] `data_aggregator.py` — Indicators 84_hl_perps, 85_hl_spot_stocks registered
- [x] `hl_extract.py` — 1-minute extraction with partial cache merge
- [x] `com.macro2.hl-extract.plist` — Launchd job (StartInterval: 60)
- [x] All 4 dashboards display HL perps in Tab 5

### Requirement 6: OHLCV Candlestick Charts ✅ DONE (v2.6.0)
Multi-interval OHLCV candlestick charts for all price indicators.

**Implementation:**
- [x] React: TradingView lightweight-charts (`HLCandlestickChart.jsx`, `IntradayCandlestickChart.jsx`)
- [x] Dash/Streamlit: Plotly `go.Candlestick()` with volume bars
- [x] Backend: `GET /api/hl/ohlcv/{coin}?interval=` and `GET /api/intraday/{key}?interval=`
- [x] Intervals: 1m–1D (HL), 1H–1W (yfinance)
- [x] 17 yfinance instruments: DXY, 4 FX pairs, VIX, MOVE, 5 commodities, ES/RTY, SPY, 10Y, HYG, LQD

### Requirement 7: Real-time WebSocket ✅ DONE (v2.6.0)
Per-second Hyperliquid price updates via WebSocket relay in React dashboard.

**Implementation:**
- [x] `hl_ws_service.py` — WebSocket relay (subscribes to allMids, fetches builder perps via REST)
- [x] `/ws/hl` FastAPI WebSocket endpoint
- [x] `useHyperliquidWS.js` React hook with auto-reconnect
- [x] Toggle button: "Start Live (~1s)" / "Stop Live (~1s)"
- [x] All 11 perps update via WS when toggle is enabled

## Data Source URLs

```python
SOURCE_URLS = {
    'sp500_forward_pe': 'https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio',
    'russell_2000': 'https://finance.yahoo.com/quote/IWN/',
    'sp500_fundamentals': 'https://finance.yahoo.com/quote/SPY/',
    'put_call_ratio': 'https://ycharts.com/indicators/cboe_equity_put_call_ratio',
    'skew': 'https://www.cboe.com/tradable_products/vix/skew_index/',
    'sp500_ma200': 'https://finance.yahoo.com/quote/%5EGSPC/',
    'marketcap_gdp': 'https://fred.stlouisfed.org/series/DDDM01USA156NWDB',
    'shiller_cape': 'http://www.econ.yale.edu/~shiller/data.htm',
    'vix': 'https://www.cboe.com/tradable_products/vix/',
    'move': 'https://fred.stlouisfed.org/series/BAMLHYH0A0HYM2TRIV',
    'dxy': 'https://finance.yahoo.com/quote/DX-Y.NYB/',
    '10y_yield': 'https://fred.stlouisfed.org/series/DGS10',
    'ism_pmi': 'https://fred.stlouisfed.org/series/NAPM',
    'gold': 'https://finance.yahoo.com/quote/GC%3DF/',
    'silver': 'https://finance.yahoo.com/quote/SI%3DF/',
    'crude_oil': 'https://finance.yahoo.com/quote/CL%3DF/',
    'copper': 'https://finance.yahoo.com/quote/HG%3DF/',
    'hyperliquid': 'https://app.hyperliquid.xyz/',
    'trade_xyz': 'https://docs.trade.xyz/consolidated-resources/specification-index',
}
```

---

**All requirements complete.** Last updated: March 22, 2026.
