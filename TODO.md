# TODO — Macroeconomic Indicators Dashboard

**Last Updated:** March 13, 2026 (Full 1:1 Dash port — comprehensive rewrite complete)

---

## Dash Dashboard Migration (Complete)

- [x] **Create dash_dashboard/ subfolder** with isolated codebase
- [x] **Data loader**: Reuse existing `data_aggregator.py` cache (JSON) for zero-duplication data flow
- [x] **Tab 1 — Valuation Metrics**: Forward P/E, Trailing P/E & P/B, Shiller CAPE (with interpretation), Market Cap/GDP
- [x] **Tab 2 — Market Indices**: ES/RTY futures, breadth (with conditional badges), A/D ratio, R2K V/G, S&P/200MA (with signal), SPY/RSP concentration (with caption)
- [x] **Tab 3 — Volatility & Risk**: VIX, MOVE, VIX/MOVE ratio, Put/Call (with info note), CBOE SKEW (with interpretation bullets), 3-col layout
- [x] **Tab 4 — Macro & Currency**: 5-col FX row (all with history expanders), TGA/Net Liq/M2/SOFR/2Y with expanders, Japan 2Y + US-JP Spread (with standalone chart + zero line), 10Y-ISM gap computed metric, 10Y vs ISM dual-axis chart, Net Liquidity 365-day chart
- [x] **Tab 5 — Commodities**: All 5 commodities + Cu/Au with history expanders, COT positioning (with OI change), COT dual-line chart (gold vs silver)
- [x] **Tab 6 — Large-cap Financials**: Full port — 12 income metrics, 23 balance sheet metrics (3 sub-tables), 9 cash flow metrics, Turnover & Leverage section, Growth section, 3-row valuation with numerator/denominator, Returns with components, revenue segments
- [x] **Tab 6 — Custom ticker input**: Text input for any ticker with on-demand Yahoo Finance fetch
- [x] **Tab 6 — Source toggle**: Yahoo Finance / SEC EDGAR radio toggle with on-demand SEC fetching
- [x] **Tab 7 — Rates & Credit**: Yield curve regime (with 20-day changes caption), 2s10s spread (with chart), global yields (with 🇺🇸🇩🇪🇬🇧🇨🇳 flags + individual expanders), Global 10Y overlay chart, real yield/breakevens (with expanders), Nominal vs Real vs Breakeven chart (with Fed 2% target), credit spreads (with expanders), bank reserves/SLOOS (with expanders), labor/inflation (with expanders), continuing claims/headline CPI/PPI (with expanders)
- [x] **Tab 8 — Economic Activity**: NFP, JOLTS, Quits Rate, Sahm Rule (with threshold chart), Consumer Sentiment, Retail Sales, ISM Services, Industrial Production, Housing Starts — all with history expanders
- [x] **Auto-refresh callback**: `dcc.Interval` 60s + `loader.load()` mtime-based cache reload
- [x] **Compact CSS**: Grid layouts (cols-2 through cols-5), metric cards, fin-tables, responsive breakpoints
- [x] **Collapsible history charts**: `html.Details/Summary` wrapper (matches Streamlit `st.expander`)
- [x] **Interpretive UI elements**: info_badge() for success/info/warning/error, conditional styling, computed metrics
- [x] **Source URL links**: Clickable subheaders linking to data sources
- [x] **Standalone charts**: US-JP Spread, Net Liquidity, 10Y vs ISM, Global Yields, Nominal vs Real vs Breakeven, COT positioning
- [x] **Numerator/denominator display**: metric_card_with_components() for valuation ratios and financial analysis
- [x] **Live testing**: All 8 tabs verified rendering correctly (March 13, 2026)
- [ ] **Dark mode toggle**: Add client-side dark/light theme switch
- [ ] **Finnhub/Simfin sources**: Add 3rd/4th data source options to Tab 6 (requires API keys)

## Known Broken Indicators (Needs Fix)

- [ ] **Forward P/E**: MacroMicro returns 403 (bot detection). Currently falls back to SPY trailing P/E. Explore alternative sources (Wisesheets, Quandl, FactSet).
- [ ] **Put/Call Ratio**: yfinance ^PCPUT/^PCALL delisted. CBOE/ycharts scrape unreliable. FRED PCERTOT is the current fallback but has multi-day lag.
- [ ] **Baltic Dry Index**: yfinance ^BDI/BDIY delisted. Need alternative data source.
- [ ] **VIX Futures (VX=F)**: Not available on yfinance. VIX spot works. Consider CBOE direct data or alternative provider.
- [ ] **OPEC Production**: EIA API needs key; Trading Economics page structure changed. Consider paid data source.
- [ ] **Gold Reserves Share**: World Gold Council URL returns 404. Need updated endpoint.
- [ ] **SPY ETF expanded fundamentals**: forwardPE/trailingEps/forwardEps return None from yfinance for ETFs. Known yfinance limitation. Low priority — 5 basic fields work.

## Dashboard Improvements

- [ ] **Visual verification**: Run `streamlit run app.py` and verify compact layout renders correctly across all 8 tabs, especially the new 5-column FX row (Tab 4) and 3-column VIX row (Tab 3)
- [ ] **Mobile responsiveness**: Test compact CSS at smaller viewport widths — 5-column FX row may need responsive breakpoints
- [ ] **Dark mode CSS**: Compact CSS uses `!important` overrides — verify no conflicts with Streamlit dark theme

## Data Extraction

- [ ] **S&P 500 batch update**: Run `extract_sp500_financials.py --source both --resume` to backfill any new S&P 500 constituents
- [ ] **13F holdings quarterly update**: Run `extract_13f_holdings.py` after each quarter's 13F-HR filing deadline (45 days after quarter end)

## Architecture

- [ ] **WebSocket live data**: Current polling architecture (5-min fast_extract) has inherent lag. WebSocket feeds from exchanges would enable true real-time. Major architectural change.

## Documentation

- [ ] **README.md**: Update to reflect v2.4.0 changes (compact layout, auto-reload, new extractors)

---

**Priority Guide:**
- P0 (Critical): Complete Dash dashboard, visual verification
- P1 (High): Fix broken indicators with viable alternatives
- P2 (Medium): Data extraction batch updates, documentation
- P3 (Low): WebSocket architecture, dark mode
