# Financial Data Sources Research

> Consolidated research on APIs, broker APIs, scraping, and data sources for listed companies' financial data.
> Updated: 2026-03-01

---

## Table of Contents

1. [Broker APIs](#1-broker-apis)
2. [Free Data Sources](#2-free-data-sources)
3. [Freemium APIs](#3-freemium-apis)
4. [Paid APIs](#4-paid-apis)
5. [TradingView](#5-tradingview)
6. [Web Scraping Options](#6-web-scraping-options)
7. [Government & Regulatory Sources](#7-government--regulatory-sources)
8. [IEX Data Explained](#8-iex-data-explained)
9. [Japan 2Y Yield Sources](#9-japan-2y-yield-sources)
10. [MooMoo API Pricing](#10-moomoo-api-pricing)
11. [Recommendations](#11-recommendations)

---

## 1. Broker APIs

### Tiger Brokers (Tiger Trade)

- **URL:** https://quant.itigerup.com
- **SDK:** `tigeropen` (pip install tigeropen)
- **Pricing:** Free API with funded account. Commission-based trading.
- **Coverage:** US, HK, SG, Australia, China A-shares (via Stock Connect)
- **Financial Data:** `get_financial_report()`, `get_financial_daily()`, `get_corporate_earnings_calendar()`
- **Data Subscriptions:** API data subscriptions are **separate** from app subscriptions. Exact prices only visible in Tiger Trade APP → Profile → Market Data Store → API tab.
- **Limitations:** No bond yield API endpoint. Rate limits depend on account tier.
- **Key Finding:** Funded account required. Financial data for US and HK stocks available. Good for Asian market access.

### Moomoo / Futu (Futu OpenAPI)

- **URL:** https://openapi.futunn.com
- **SDK:** `futu-api` (pip install futu-api)
- **Pricing:** Free API with funded account. Commission-based.
- **Coverage:** US, HK, China A-shares, Singapore
- **Financial Data:** Income statement, balance sheet, cash flow via financial report endpoints. Key financial metrics and ratios.
- **Requirement:** Must run **OpenD gateway daemon** locally (TCP persistent connection).
- **Rate Limits:** 30 requests/30 seconds for most endpoints. Quotas scale with account assets/trading activity.
- **Cost:** Free for API access itself. No additional data subscription fee. However, real-time quotes may require subscription depending on market.
- **Key Finding:** Strong for HK/China markets. OpenD gateway makes it impractical for headless/scheduled scripts.

### Interactive Brokers (IBKR)

- **URL:** https://www.interactivebrokers.com/en/trading/ib-api.php
- **SDK:** `ibapi` (official), `ib_insync` (popular async wrapper)
- **Pricing:** Free with funded account (no minimum for IBKR Lite)
- **Coverage:** 150+ markets, 33 countries — broadest broker coverage
- **Financial Data:** `reqFundamentalData()` provides financial statements, analyst estimates, company overview (Reuters/Refinitiv sourced)
  - `ReportsFinSummary` — financial summary
  - `ReportsFinStatements` — full financial statements
  - `RESC` — analyst estimates
- **Requirement:** Must run TWS (Trader Workstation) or IB Gateway
- **Key Finding:** Most comprehensive broker API for multi-market data. Fundamental data is decent but not as deep as dedicated data providers.

### Alpaca

- **URL:** https://alpaca.markets
- **SDK:** `alpaca-py` (official)
- **Pricing:** Free for US equity/crypto. No minimum balance. Paper trading available.
- **Coverage:** US stocks and crypto only
- **Data:** Primarily price/market data, news, corporate actions. **No financial statement data** via API.
- **Rate Limits:** 200 requests/minute
- **IEX Data:** Uses IEX for real-time quotes on free (Basic) plan
- **Key Finding:** Best free option for US price data and trading. NOT a source for fundamentals/financials.

### Webull

- **URL:** https://www.webull.com
- **SDK:** `webull` (unofficial, community)
- **Key Finding:** No official developer API. Unofficial library is reverse-engineered and unreliable. Not recommended for programmatic access.

### TD Ameritrade / Charles Schwab

- **URL:** https://developer.schwab.com
- **Note:** Migrated from TD Ameritrade to Schwab API. Still maturing.
- **Coverage:** US stocks
- **Financial Data:** Fundamental data endpoint provides statements, key ratios, earnings
- **Key Finding:** In transition. Was previously one of the better broker APIs. Currently uncertain.

### Tradier

- **URL:** https://tradier.com
- **Coverage:** US equities and options
- **Financial Data:** Company fundamentals, financial ratios, earnings. Basic compared to dedicated providers.

---

## 2. Free Data Sources

### SEC EDGAR API (Authoritative)

- **URL:** https://www.sec.gov/edgar/sec-api-documentation
- **Pricing:** Completely free, no API key (just User-Agent header with email)
- **Coverage:** All US-listed companies (~8,000+ filers)
- **Data:** Full 10-K, 10-Q, 8-K filings; XBRL-tagged financials (income, balance sheet, cash flow); back to ~2009
- **Rate Limit:** 10 requests/second
- **Key Endpoints:**
  - `data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` — all financial facts
  - `data.sec.gov/submissions/` — filing metadata
  - `efts.sec.gov/LATEST/search-index` — full-text search
- **Python:** `edgartools`, `sec-edgar-downloader`, `python-sec-edgar-api`
- **Accuracy:** Authoritative source. XBRL quality depends on company tagging consistency.

### Yahoo Finance (Unofficial)

- **URL:** https://finance.yahoo.com
- **Pricing:** Free (unofficial API, no key)
- **Coverage:** Global — 60,000+ tickers across all major exchanges
- **Data:** Income statement, balance sheet, cash flow (annual + quarterly, 4-5 years), key stats, analyst estimates, earnings, 200+ valuation ratios
- **Python:** `yfinance` (~40k GitHub stars) — `Ticker("AAPL").income_stmt`, `.balance_sheet`, `.cashflow`, `.info`
- **Reliability:** Works most of the time. Periodically breaks when Yahoo changes internal API. Not suitable for production-critical systems.
- **Key Finding:** Best single free source for global financial data. Already in our stack.

### Simfin

- **URL:** https://simfin.com
- **Pricing:** Free tier with bulk downloads and 2,000 API calls/day. Simfin+ $9.99/month.
- **Coverage:** ~5,000 US companies
- **Data:** Income statement, balance sheet, cash flow, derived ratios. All **standardized** into consistent format.
- **Python:** `simfin` (official, pandas integration)
- **Key Finding:** Best for standardized analysis. Clean format. Community-verified data.

### AKShare (China-focused)

- **URL:** https://akshare.akfamily.xyz
- **Pricing:** Completely free, open source
- **Coverage:** China A-shares, HK, US, futures, options, bonds, funds, macro. 200+ data sources.
- **Python:** `akshare`
- **Key Finding:** Best for China A-share financial data. Very active development.

### Tushare (China-focused)

- **URL:** https://tushare.pro
- **Pricing:** Free tier with limited calls. Points-based system.
- **Coverage:** All China A-share companies. Some HK and US.
- **Python:** `tushare`
- **Key Finding:** Standard for China A-share quant data.

### Financial Modeling Prep (Free Tier)

- **URL:** https://financialmodelingprep.com
- **Free:** 250 API calls/day, US stocks only
- **Paid:** From $19/month
- **Data:** Income statement, balance sheet, cash flow, ratios, DCF, estimates, insider trades, screener

---

## 3. Freemium APIs

### Finnhub

- **URL:** https://finnhub.io
- **Free Tier:** 60 calls/minute (most generous free tier)
- **Premium:** From $50/month
- **Coverage:** US + some international (60+ exchanges for price)
- **Data:** Financial statements (as-reported + standardized), ratios (200+ metrics), earnings estimates/surprises, SEC filings, insider transactions, institutional ownership, ESG
- **Python:** `finnhub-python` (official)
- **Key Finding:** Best free-tier API for combined fundamentals + estimates.

### Polygon.io

- **URL:** https://polygon.io
- **Free:** 5 calls/min, delayed. Starter: $29/month. Developer: $79/month.
- **Coverage:** All US-listed stocks, options, forex, crypto
- **Data:** Financial statements via `vX/reference/financials` (sourced from SEC XBRL). Splits, dividends, company details, insider transactions.
- **Python:** `polygon-api-client` (official)
- **Key Finding:** Developer-friendly. Fundamental data is newer addition.

### Twelve Data

- **URL:** https://twelvedata.com
- **Free:** 800 calls/day, 8/min. From $29/month.
- **Coverage:** 50+ exchanges worldwide
- **Data:** Income statement, balance sheet, cash flow, key stats, earnings, estimates
- **Python:** `twelvedata` (official)

### Alpha Vantage

- **URL:** https://www.alphavantage.co
- **Free:** 25 calls/day (very restrictive). Premium from $49.99/month.
- **Data:** Income statement, balance sheet, cash flow, earnings, company overview
- **Python:** `alpha_vantage` (official)
- **Key Finding:** Free limit is too low for scanning multiple stocks.

### EOD Historical Data

- **URL:** https://eodhd.com
- **Free:** 20 calls/day. Fundamentals: $79.99/month. All-in-one: $99.99/month.
- **Coverage:** 70+ exchanges, 150,000+ tickers — best international breadth
- **Data:** Full financial statements, ratios, earnings, dividends, insider trades, ESG, analyst estimates
- **Python:** `eodhd` (official)
- **Key Finding:** Best for international coverage.

### Tiingo

- **URL:** https://www.tiingo.com
- **Pricing:** Free (limited). Power: $10/month. Commercial: $50+/month.
- **Data:** Prices + some fundamentals. Full financial statements on paid plans.
- **Key Finding:** Good quality (founder is ex-hedge fund quant).

---

## 4. Paid APIs

### Nasdaq Data Link (Sharadar)

- **URL:** https://data.nasdaq.com (formerly Quandl)
- **Pricing:** Sharadar Core US Fundamentals ~$25-50/month individual. Institutional higher.
- **Coverage:** ~15,000 US tickers, standardized
- **Data:** Income statement, balance sheet, cash flow, 100+ derived metrics. All standardized.
- **Python:** `nasdaq-data-link` (official)
- **Key Finding:** Best price-to-quality ratio for standardized US fundamentals.

### Intrinio

- **URL:** https://intrinio.com
- **Pricing:** Starter ~$75/month. Professional $150+/month.
- **Coverage:** 20,000 US tickers, 200+ metrics, 20+ years history
- **Data:** Standardized + as-reported financials, Zacks estimates, institutional ownership, insider trades
- **Python:** `intrinio-sdk` (official)
- **Key Finding:** Institutional-grade. Strong customer support.

### IEX Cloud (Nasdaq)

- **URL:** https://iexcloud.io
- **Pricing:** Launch $9/month (50K credits). Grow $49/month. Scale $499/month.
- **Data:** Income statement, balance sheet, cash flow, key stats, earnings, estimates, insider/institutional ownership
- **Key Finding:** Clean API. Credit-based pricing. Now under Nasdaq.

### S&P Capital IQ / Compustat

- **Pricing:** $10,000-$50,000+/year. Academic via WRDS.
- **Coverage:** 80,000+ companies, 100+ countries, back to 1950s
- **Key Finding:** Gold standard. Used by virtually all institutions.

### Bloomberg

- **Pricing:** Terminal ~$24K/year. Data License $50K+/year.
- **Coverage:** Everything everywhere
- **Python:** `blpapi` (requires Terminal or B-PIPE)
- **Key Finding:** Most comprehensive data source in existence.

### Refinitiv (LSEG) / Eikon

- **Pricing:** ~$10K-22K/year
- **Coverage:** Global, 100+ countries
- **Python:** `refinitiv-data` (official)
- **Key Finding:** Comparable to Bloomberg. Strong on international + ESG.

### Morningstar Direct

- **Pricing:** ~$15K-40K/year
- **Key Finding:** Strong on fund analytics and proprietary analysis (moat ratings, fair value).

---

## 5. TradingView

- **URL:** https://www.tradingview.com
- **Official API:** **No public REST API for fundamental data**
- **Pine Script:** Can access financials via `request.financial()` but only within TradingView charts — cannot export data programmatically
- **Screener:** CSV export of screener results (Premium feature only, manual)
- **Widgets:** Display-only embeddable charts
- **Scraping:** Violates ToS, anti-bot protections active
- **Data Quality:** High (licensed from ICE, Morningstar, Refinitiv)
- **Verdict:** **Not viable for programmatic fundamental data access.** Excellent for visual analysis only.

---

## 6. Web Scraping Options

| Source | Difficulty | Data Quality | Historical Depth | Legal Risk |
|--------|-----------|-------------|-----------------|-----------|
| **SEC EDGAR** (XBRL API) | Medium | Authoritative | 2009+ | None (legal, encouraged) |
| **Yahoo Finance** (`yfinance`) | Easy | Good | 4-5 years | IP blocking, periodic breakage |
| **Macrotrends.net** | Easy | Good | 10-20 years | ToS violation, minimal anti-bot |
| **Finviz** (`finvizfinance`) | Easy | Good screener | Snapshot | ToS violation |
| **GuruFocus** | Medium | Excellent | 10+ years | API $49/month, scraping blocked |
| **Stock Analysis** | Medium | Good | Growing | Has paid API $29/month |

### OpenBB Platform

- **URL:** https://openbb.co
- **Note:** Not a data source itself — an open-source aggregator that connects to 90+ providers via unified interface
- **Python:** `openbb`
- **Key Finding:** Good framework for combining multiple sources. Depends on underlying provider quality.

---

## 7. Government & Regulatory Sources

| Regulator | Country | Format | API | Coverage |
|-----------|---------|--------|-----|----------|
| **SEC EDGAR** | US | XBRL (structured) | Free, excellent | 8,000+ filers |
| **CNINFO** | China | Structured | Yes (Chinese) | All A-shares |
| **EDINET** | Japan | XBRL | Yes | All Japanese public cos |
| **HKEX News** | Hong Kong | PDF (mostly) | Limited | ~2,600 listings |
| **Companies House** | UK | XBRL | Free REST API | All UK companies |
| **SEDAR+** | Canada | Mixed | Limited | Canadian public cos |
| **SSE/SZSE** | China | Structured via CNINFO | Registration required | ~5,000 A-shares |

---

## 8. IEX Data Explained

**IEX (Investors Exchange)** is one of 16 registered US stock exchanges.

- **Market Share:** ~2-3% of total US equity volume
- **What It Is:** A real stock exchange (not a data vendor), founded 2012, registered 2016
- **Data Accuracy:** Prices are **100% accurate** for trades executed on IEX. For liquid large-caps (AAPL, MSFT, etc.), IEX prices track NBBO very closely. For illiquid microcaps, IEX may have fewer data points.
- **Coverage:** All US-listed equities (NYSE, NASDAQ, etc.) that trade on IEX
- **Financial Data:** IEX Cloud (now under Nasdaq) provides fundamental data — income statements, balance sheets, cash flow, key stats, earnings, estimates. This is **sourced/licensed data**, not from the exchange itself.
- **Free Access:** Available free through Alpaca's Basic plan (IEX real-time quotes)
- **Key Finding:** IEX price data is accurate for liquid instruments. Their cloud platform provides reliable financial data. Good for real-time US equity data on a budget.

---

## 9. Japan 2Y Yield Sources

Research identified these sources for Japan 2-Year Government Bond (JGB) yield data:

| Source | Availability | Historical | Format | Auth |
|--------|-------------|-----------|--------|------|
| **MOF Japan (Ministry of Finance)** | ✅ Best | 1974–present | Clean CSV | None |
| FRED | ❌ No 2Y JGB series | — | — | — |
| Yahoo Finance | ❌ No JGB ticker | — | — | — |
| Investing.com | ⚠️ Cloudflare blocked | Limited | HTML scrape | Blocked |
| TradingView | ⚠️ No historical API | Visual only | — | No API |
| Tiger Brokers | ⚠️ No bond yield endpoint | — | — | Funded acct |

### MOF Japan Implementation (Used)

- **Historical URL:** `https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/historical/jgbcme_all.csv`
- **Current Month URL:** `https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/jgbcme.csv`
- **Format:** CSV, date format `YYYY/M/D`, yields for 1Y-40Y maturities
- **Coverage:** Daily data from 1974 to present (12,800+ data points for 2Y)
- **Auth:** None required, no bot protection
- **Implemented in:** `data_extractors/japan_yield_extractor.py`

---

## 10. MooMoo API Pricing

- **API Access:** Free with any Moomoo/Futu account
- **Data Subscriptions:** Generally free for basic quotes. Level 2 data may require separate subscriptions.
- **OpenD Gateway:** Required (local daemon). Free to run.
- **Quota System:** API call quotas scale with account assets and trading activity:
  - Higher account balance → more API calls
  - More active trading → higher quotas
- **Financial Statements:** Available for US, HK, and China A-share listed companies
- **Key Limitation:** OpenD gateway must run continuously. Not suitable for serverless/scheduled scripts.

---

## 11. Recommendations

### For This Dashboard (macro_2 project)

| Use Case | Recommended Source | Cost | Why |
|----------|-------------------|------|-----|
| **Large-cap financials** | Yahoo Finance (`yfinance`) | Free | Already installed, global coverage, easy |
| **Authoritative US filings** | SEC EDGAR API | Free | Definitive source, XBRL structured |
| **Estimates & ratings** | Finnhub free tier | Free | 60 calls/min, good coverage |
| **China/HK markets** | AKShare | Free | Best open-source China data |
| **International breadth** | EOD Historical Data | $80/mo | 70+ exchanges |
| **Institutional quality (US)** | Nasdaq Data Link Sharadar | $25-50/mo | Best price/quality |

### Comparison Matrix

| Source | Free? | US | Intl | Statements | Ratios | Estimates | Best For |
|--------|-------|-----|------|-----------|--------|-----------|----------|
| SEC EDGAR | ✅ | ✅ | ❌ | Full XBRL | ❌ | ❌ | Authoritative US |
| yfinance | ✅ | ✅ | ✅ | 4-5yr | ✅ | ✅ | Quick prototyping |
| Simfin | ✅ | ✅ | Limited | ✅ | ✅ | ❌ | Standardized |
| Finnhub | ✅* | ✅ | Some | ✅ | ✅ | ✅ | Generous free tier |
| Polygon | ✅* | ✅ | ❌ | ✅ | Some | ❌ | Developer-friendly |
| Tiger API | Free** | ✅ | HK/CN | ✅ | Some | Some | Asian trading |
| Futu/Moomoo | Free** | ✅ | HK/CN | ✅ | Some | Some | HK/China |
| IBKR | Free** | ✅ | Global | ✅ | Some | ✅ | Multi-market |

\* Free tier with limits
\*\* Requires funded brokerage account
