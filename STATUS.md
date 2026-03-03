# Project Status Report: Macroeconomic Indicators Dashboard

**Project:** macro_2 - Real-time Macroeconomic Indicators Dashboard
**Last Updated:** March 3, 2026
**Version:** 2.0.1
**Status:** Production Ready

---

## Summary

A Streamlit dashboard tracking 28+ macroeconomic indicators and quarterly financials for 20 large-cap companies from multiple data sources (Yahoo Finance, SEC EDGAR, FRED, MOF Japan, web scrapers). Includes dual-source equity financials, expandable price charts, automated launchd scheduling, and a data discrepancy review agent.

---

## Dashboard Tabs (6 tabs)

| Tab | Name | Indicators | Status |
|-----|------|------------|--------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP | Working (Forward P/E unreliable) |
| 2 | Market Indices | ES/RTY futures, market breadth, Russell 2000 V/G, S&P 500/200MA | Working |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW | Working (Put/Call unreliable) |
| 4 | Macro & Currency | DXY, USD/JPY, TGA, net liquidity, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI | Working |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, CFTC COT positioning | Working |
| 6 | Large-cap Financials | 20 companies, dual-source (Yahoo + SEC EDGAR), income/balance/cash flow, valuation, analysis | Working (TSM SEC only fails — IFRS) |

## Recent Features (v2.0.0)

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

### Data Discrepancy Review Agent
AI agent in `/agent/` subfolder that reviews financial data quality using 8 shared tools. Two implementations:
- OpenAI Agents SDK + Minimax LLM
- LangChain + LangGraph + Minimax LLM

---

## Data Sources

| Source | Indicators | Key Required | Reliability |
|--------|------------|-------------|-------------|
| Yahoo Finance (yfinance) | VIX, MOVE, DXY, Russell 2000, ES/RTY futures, JPY, S&P 500, commodities, equity financials | No | Excellent |
| FRED API | GDP, 10Y yield, ISM PMI, TGA, net liquidity, SOFR, US 2Y yield, Put/Call fallback | Yes (free) | Excellent |
| SEC EDGAR XBRL | Quarterly financials for 20 companies | No (User-Agent only) | Excellent |
| MOF Japan | Japan 2Y/10Y yields (CSV download) | No | Good |
| Robert Shiller (Yale) | CAPE ratio (Excel download) | No | Excellent |
| CFTC | COT positioning (weekly report) | No | Good |
| MacroMicro | Forward P/E | No | Poor (403 errors) |
| CBOE/ycharts | Put/Call ratio | No | Poor (blocked) |

## Known Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Forward P/E 403 errors | MacroMicro bot detection | Falls back to trailing P/E |
| Put/Call ratio unreliable | CBOE/ycharts DOM changes | Falls back to FRED PCERTOT |
| TSM (IFRS) | SEC EDGAR returns no us-gaap data | Yahoo Finance only |
| ISM PMI proxy | Uses Industrial Production normalized to PMI scale | Approximation, ~5% error |
| SEC rate limit | 10 req/sec | Built-in 0.15s delay between requests |

## Scheduling

**macOS launchd** runs `scheduled_extract.py` at 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8, Mon-Sat. Catches up missed runs after sleep. Freshness guard prevents redundant fetches within 15 minutes. A 10-minute `TimeOut` auto-kills hung processes to prevent blocking subsequent runs.

## File Count

- **Python modules**: 15+ files
- **Dashboard**: ~1,400 lines (app.py)
- **SEC extractor**: ~1,150 lines
- **Total LOC**: ~6,000+
- **Documentation**: 10+ markdown files

---

**Document Version:** 2.0.1
**Last Updated:** March 3, 2026
**Repository:** https://github.com/cdavocazh/macro_2
