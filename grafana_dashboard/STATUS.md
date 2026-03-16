# Grafana Macro Dashboard — Status

**Version:** 1.0.0
**Date:** 2026-03-14
**Status:** Initial release

## Feature Checklist

### Infrastructure
- [x] FastAPI API bridge with JSON serialization
- [x] Docker Compose deployment (Grafana + API bridge)
- [x] Grafana provisioning (data source + dashboard auto-load)
- [x] Infinity data source plugin integration
- [x] SimpleJSON-compatible endpoints (`/search`, `/query`, `/annotations`)
- [x] Health check endpoint
- [x] Startup script (`start.sh`)

### Dashboard Panels (by Tab)

#### Tab 1 — Valuation Metrics
- [x] Forward P/E
- [x] Trailing P/E
- [x] P/B Ratio
- [x] Shiller CAPE
- [x] Market Cap / GDP (Buffett Indicator)
- [x] PEG Ratio
- [x] Equity Risk Premium (Trailing + Forward)
- [x] Sector P/E Ratios (table)

#### Tab 2 — Market Indices
- [x] ES Futures (S&P 500 E-mini) + 1D change
- [x] RTY Futures (Russell 2000 E-mini)
- [x] Breadth %
- [x] S&P 500 / MA200 Ratio
- [x] SPY/RSP Concentration
- [x] Fama-French 5 Factors (Mkt-RF, SMB, HML, RMW, CMA)

#### Tab 3 — Volatility & Risk
- [x] VIX
- [x] MOVE Index
- [x] VIX/MOVE Ratio
- [x] Put/Call Ratio
- [x] CBOE SKEW
- [x] VIX Contango %
- [x] SPY Put/Call Volume + OI Ratio

#### Tab 4 — Macro & Currency
- [x] DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY
- [x] TGA Balance, Net Liquidity, M2
- [x] SOFR, US 2Y, Japan 2Y, 10Y Yield
- [x] ISM Manufacturing PMI
- [x] M1/M2 YoY%

#### Tab 5 — Commodities
- [x] Gold, Silver, Crude Oil, Copper, Natural Gas (price + 1D change)
- [x] Cu/Au Ratio
- [x] Brent Crude

#### Tab 6 — Large-cap Financials
- [ ] Not included (requires interactive UI — use Streamlit/React)

#### Tab 7 — Rates & Credit
- [x] 2s10s Spread
- [x] US 5Y, DE/UK/CN 10Y yields
- [x] Real Yield 10Y
- [x] HY OAS, IG OAS
- [x] NFCI, Fed Funds Rate
- [x] Unemployment Rate, Initial Claims
- [x] Core PCE, Headline CPI, PPI
- [x] ECB Deposit + Refi Rate
- [x] CPI Components (Core, Food, Energy, Shelter)
- [x] European Yields (DE, IT)
- [x] Global CPI (US, EU, JP, UK)
- [x] Corporate Spreads (AAA, BBB)

#### Tab 8 — Economic Activity
- [x] Nonfarm Payrolls, JOLTS, Quits Rate
- [x] Sahm Rule (with recession threshold)
- [x] Consumer Sentiment, Retail Sales
- [x] ISM Services PMI, Industrial Production, Housing Starts
- [x] OECD CLI
- [x] International Unemployment (US/EU/JP/UK)
- [x] International GDP Growth (US/EU/JP/CN)
- [x] Global Manufacturing PMI (US/EU/JP/CN/UK)

### API Endpoints
- [x] `/api/metrics/summary` — flat metrics for stat panels
- [x] `/api/timeseries/{key}` — historical series
- [x] `/api/indicator/{key}` — single indicator
- [x] `/api/group/{group}` — grouped by tab
- [x] `/api/indicators` — all indicators
- [x] `/api/status` — dashboard status
- [x] `/api/financials/{ticker}` — company financials
- [x] `/api/refresh` — trigger refresh

## Known Limitations

1. **Tab 6 not in Grafana** — Company financials require interactive ticker selection; not suited for static Grafana panels. Use Streamlit or React dashboard instead.
2. **Sector P/E table** — Requires Infinity plugin's JSON parsing for nested objects; may need manual query adjustment depending on Grafana/Infinity version.
3. **No time-series graphs yet** — Current dashboard uses stat panels only. Time-series graph panels can be added by pointing to `/api/timeseries/{key}` endpoints.
4. **Earnings Calendar** — Not included (requires table with dynamic rows).
5. **COT Positioning** — Not included (requires chart with gold/silver overlay).
6. **Breakeven Inflation** — Available via API but not paneled yet.

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-14 | Initial release — 70+ stat panels, API bridge, Docker setup |
