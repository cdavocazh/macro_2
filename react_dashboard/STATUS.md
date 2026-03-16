# STATUS - React Dashboard

**Version:** 1.0.0
**Created:** 2026-03-14
**Status:** Initial release

## Feature Checklist

- [x] FastAPI backend wrapping data_aggregator (no data layer duplication)
- [x] All 82 indicators represented across 8 tabs
- [x] Tab 1: Valuation Metrics (Forward P/E, Trailing P/E, P/B, CAPE, Market Cap/GDP, Multiples, Sector P/E, ERP)
- [x] Tab 2: Market Indices (ES/RTY futures, breadth, Russell 2000, S&P/200MA, SPY/RSP, Fama-French, earnings calendar)
- [x] Tab 3: Volatility & Risk (VIX, MOVE, VIX/MOVE, Put/Call, SKEW, VIX futures curve, SPY P/C OI, IV Skew)
- [x] Tab 4: Macro & Currency (DXY, JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, yields, ISM PMI, money supply)
- [x] Tab 5: Commodities (gold, silver, oil, copper, natural gas, Cu/Au ratio, COT positioning)
- [x] Tab 6: Large-cap Financials (Top 20 dropdown + custom ticker, Yahoo/SEC toggle, quarterly statements, analysis, valuation, segments)
- [x] Tab 7: Rates & Credit (yield curve regime, global yields, real yields, breakevens, credit spreads, labor, CPI, ECB, treasury curve, corporate spreads)
- [x] Tab 8: Economic Activity (NFP, JOLTS, Sahm Rule, sentiment, retail, ISM Services, housing, OECD CLI, intl unemployment/GDP, global PMI)
- [x] Collapsible Plotly charts with 1W/1M/3M range buttons
- [x] Auto-refresh every 60 seconds
- [x] Compact dense layout matching Streamlit dashboard density
- [x] Green/red delta coloring
- [x] Error cards with red left border
- [x] Startup script launching both servers
- [x] Vite proxy config for seamless API calls

## Known Limitations

- Sector ETFs table (indicator `62_sector_etfs`) not in aggregator's `fetch_all_indicators` -- not displayed
- Brent crude (`52_brent_crude`) not in aggregator -- not displayed
- Equity screener (`79_equity_screener`) fetched but not displayed (no clear tab placement in Streamlit app either)
- OHLCV candlestick charts not implemented (only line charts from `historical` series)
- No Streamlit session state equivalent -- Tab 6 re-fetches SEC data on each ticker change
- No CSV export button (use parent project's `scheduled_extract.py` instead)
