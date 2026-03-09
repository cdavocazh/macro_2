# Data Sources TODO — Fidenza Macro Gap Analysis

**Generated:** 2026-03-07
**Updated:** 2026-03-08 — 13 indicators implemented (see ✅ markers below)
**Source files:** 12 Fidenza Macro newsletter/trade alert files (Sep 2025 – Mar 2026)
**Compared against:** macro_2 codebase (v2.3.0+, 75+ indicators, 8 dashboard tabs, 13F holdings)

---

## Summary

After reviewing ~144 trade alerts and ~12 newsletter posts from Geo Chen (Fidenza Macro), the following data sources, instruments, and indicators are referenced in the newsletter but **not currently tracked** in the macro_2 codebase. Items are organized by priority (actively traded vs. referenced in analysis vs. third-party research).

---

## Category 1: Actively Traded Instruments (Not in Codebase)

These are instruments Geo Chen actively trades with specific entries, stops, and exits. Adding price tracking for these would enable portfolio replication and signal validation.

| Instrument | Ticker / Symbol | Source | Notes |
|-----------|----------------|--------|-------|
| ✅ **SOFR Futures (term structure)** | SR3 (various maturities) | CME via yfinance | **DONE** — `fidenza_extractors.get_sofr_futures_term_structure()` → `sofr_futures_term_structure.csv`. 9 contracts with implied rates. |
| ✅ **Brent Crude Oil Futures** | BZ=F | yfinance | **DONE** — `fidenza_extractors.get_brent_crude()` → `brent_crude.csv` |
| ✅ **Nikkei 225 Mini Futures** | ^N225 | yfinance | **DONE** — `fidenza_extractors.get_nikkei_225()` → `nikkei_225.csv` |
| **US Treasury Bond Futures (30Y)** | ZB=F | yfinance | Actively traded ("short US Treasury futures 112'10"). Not tracked. |
| **US Treasury Note Futures (10Y)** | ZN=F | yfinance | Referenced in trades alongside ZB. Not tracked. |
| ✅ **Fed Funds Futures** | ZQ=F (various months) | CME via yfinance | **DONE** — `fidenza_extractors.get_fed_funds_futures()` → `fed_funds_futures.csv` (price + implied rate) |
| ✅ **XAU/JPY (Gold in Yen)** | Computed: GC=F × JPY=X | yfinance (compute) | **DONE** — `fidenza_extractors.get_xau_jpy()` → `xau_jpy.csv` |
| **BTC (Bitcoin)** | BTC-USD | yfinance | Frequently traded (long/short BTC with specific levels). Not in dashboard. |
| **ETH (Ethereum)** | ETH-USD | yfinance | Traded ("close ETHUSD at 3580"). Not tracked. |
| ✅ **EWY (South Korea)** → KOSPI | ^KS11 | yfinance | **DONE** — `fidenza_extractors.get_em_indices()` → `kospi_index.csv` (underlying index, not ETF) |
| ✅ **EWZ (Brazil)** → Bovespa | ^BVSP | yfinance | **DONE** — `fidenza_extractors.get_em_indices()` → `bovespa_index.csv` (underlying index, not ETF) |
| ✅ **EEM (Emerging Markets)** → MSCI EM | EEM (proxy) | yfinance | **DONE** — `fidenza_extractors.get_em_indices()` → `msci_em.csv` (EEM as proxy, no free MSCI index ticker) |
| **OIH (Oil Services ETF)** | OIH | yfinance | Thematic long ("most capital-starved sector"). Not tracked. |
| **XLE (Energy Select Sector ETF)** | XLE | yfinance | Referenced as energy play. Not tracked. |
| **KWEB (China Internet ETF)** | KWEB | yfinance | Traded ("close long KWEB"). Not tracked. |
| **GLD (Gold ETF)** | GLD | yfinance | Long-term holding. Codebase tracks GC=F futures but not the ETF. |
| **Metaplanet** | 3350.T | yfinance | Traded (Japanese BTC treasury stock). Not tracked. |
| **BMNR (Bitmine Immersion)** | BMNR | yfinance | Shorted ("short digital asset treasuries"). Not tracked. |

---

## Category 2: Macro Indicators & Data Series (Not in Codebase)

These are economic indicators or data series explicitly used in the newsletter's analysis framework but not currently fetched or displayed.

| Indicator | Source | FRED Series / Method | Notes |
|-----------|--------|---------------------|-------|
| ✅ **AAII Bull/Bear Sentiment Survey** | AAII website | Web scrape (aaii.com/sentimentsurvey) | **DONE** — `fidenza_extractors.get_aaii_sentiment()` → `aaii_sentiment.csv` (bullish/neutral/bearish/ratio) |
| ✅ **ADP Employment Change** | ADP / FRED | ADPWNUSNERSA | **DONE** — `fred_extractors.get_adp_employment()` → `adp_employment.csv` |
| **Durable Goods Orders** | FRED | DGORDER | Referenced ("durable goods was 0.4% vs 0.0% expected"). Already in Financial Agent extractors but not in dashboard. |
| ⚠️ **OPEC Spare Capacity / Output** | EIA or OPEC reports | Web scrape or API | **ATTEMPTED** — `fidenza_extractors.get_opec_production()`. Fails: no EIA_API_KEY, Trading Economics page changed. Graceful error. |
| ⚠️ **Gold Share of Global Reserves (%)** | IMF / World Gold Council | Web scrape or IMF data | **ATTEMPTED** — `fidenza_extractors.get_gold_reserves_share()`. Fails: WGC URL 404. Graceful error. |
| **Fed Speaker Hawkish/Dovish Tracker** | Manual / NLP | Could scrape from CME FedWatch or Citadel | "6 out of 12 voting members prefer a hold." Used for FOMC prediction. |
| ✅ **US 30-Year Treasury Yield** | FRED | DGS30 | **ALREADY EXISTS** — `fred_extractors.py:1400`, extracted at `extract_historical_data.py:1144` |
| **Fed Funds Futures Implied Rate Path** | CME FedWatch | CME API or scrape | "32 bp of cuts are priced in until March." Critical for rate expectations. |
| ✅ **Treasury Term Premia** | NY Fed ACM model | FRED THREEFYTP10 / ACMTP10 | **DONE** — `fred_extractors.get_treasury_term_premia()` → `treasury_term_premia.csv` (10Y + 5Y) |
| **Corporate Bond Issuance (Tech/AI)** | SIFMA or Fed data | Web scrape | "Meta, Oracle, and Google have issued $27B, $18B, and $25B of debt." AI capex financing signal. |
| **Private Credit Market Indicators** | Various | Web scrape | Referenced in themes discussion. Growing alternative lending market. |
| **Uranium Prices** | Trading Economics or Cameco | Web scrape | Iran nuclear enrichment context. Energy commodity not tracked. |
| ✅ **Fed Balance Sheet (WALCL)** | FRED | WALCL | **DONE** — `fred_extractors.get_fed_balance_sheet()` → `fed_balance_sheet.csv` |

---

## Category 3: Derived / Computed Indicators (Not in Codebase)

These are ratios, spreads, or composite indicators that can be computed from existing or new data.

| Indicator | Computation | Notes |
|-----------|-------------|-------|
| ✅ **Gold/Silver Ratio** | GC=F / SI=F | **DONE** — `fidenza_extractors.get_gold_silver_ratio()` → `gold_silver_ratio.csv` |
| **Brent-WTI Spread** | BZ=F - CL=F | Requires Brent (Category 1). Useful for oil market structure. |
| **SOFR Futures Implied Terminal Rate** | From SOFR futures curve | "Market today is pricing in a terminal rate of 3.10%." Key trading signal. |
| **CTA Positioning Estimate** | External data | GS/UBS provide estimates. No public free source. See Category 4. |
| **Options Dealer Gamma/Delta Exposure** | SpotGamma or compute from options chain | Charm/vanna analysis for ES swing trading. See Category 4. |
| **SPX Rolling Put Protection Cost** | SPX options chain | "Rolling 3-month SPX puts struck 5-10% below market." Hedging cost tracker. |
| **Bitcoin vs Gold Ratio** | BTC-USD / GC=F | "Even gold and silver have outshone bitcoin." Narrative tracker. |

---

## Category 4: Third-Party / Paid Research Data Sources (Referenced)

These are institutional or subscription data sources cited in the newsletter. Most are not freely accessible but are noted here for completeness.

| Source | Type | Cost | What It Provides |
|--------|------|------|-----------------|
| **Vanda Research** | Institutional research | Paid subscription | Market positioning and sentiment data |
| **SentimenTrader** | Statistical analysis | Paid subscription | Market signals, sentiment extremes |
| **SpotGamma** | Options flow | Paid subscription | Dealer positioning, gamma exposure, charm/vanna flows |
| **Market Ear** | Newsletter/research | Cheap (via ZeroHedge sub) | CTA flows, research aggregation |
| **Citadel Markets News & Insights** | Research | Free | Market commentary and positioning |
| **GS Flow of Funds** | Goldman Sachs research | Institutional access | Equity positioning, CTA triggers |
| **GS Equity Positioning & Key Levels** | Goldman Sachs research | Institutional access | CTA trigger levels, systematic flows |
| **BofA Fund Manager Survey** | BofA research | Institutional access | Global fund manager positioning |
| **BofA Systematic Flows Monitor** | BofA research | Institutional access | Systematic strategy flows |
| **UBS CTA Positioning and Flows** | UBS research | Institutional access | CTA positioning estimates |
| **Variant Perception** | Research | Paid subscription | Capital-starved sector analysis |
| **Adam Mancini's Trade Companion** | Newsletter | Paid subscription | ES day trading levels |
| **Tic Toc's Orderflow Newsletter** | Newsletter | Paid subscription | Orderflow level analysis |

---

## Category 5: Already Tracked (Confirmed Present in Codebase)

For reference, these instruments/indicators from the Fidenza files are **already covered**:

| Instrument/Indicator | Codebase Location |
|---------------------|-------------------|
| ES (S&P 500 e-mini futures) | yfinance_extractors.py (ES=F) |
| RTY (Russell 2000 futures) | yfinance_extractors.py (RTY=F) |
| Gold futures (GC=F) | commodities_extractors.py |
| Silver futures (SI=F) | commodities_extractors.py |
| Copper futures (HG=F) | commodities_extractors.py |
| WTI Crude Oil (CL=F) | commodities_extractors.py |
| Natural Gas (NG=F) | commodities_extractors.py |
| EUR/USD | yfinance_extractors.py |
| GBP/USD | yfinance_extractors.py |
| USD/JPY | yfinance_extractors.py |
| EUR/JPY | yfinance_extractors.py |
| DXY (Dollar Index) | yfinance_extractors.py |
| VIX | yfinance_extractors.py |
| SOFR (overnight rate) | fred_extractors.py |
| US 2Y / 5Y / 10Y yields | fred_extractors.py |
| Germany / UK / China 10Y yields | global_yields_extractor.py |
| 2s10s yield spread | yield_curve_extractor.py |
| ISM Manufacturing PMI | fred_extractors.py |
| ISM Services PMI | global_yields_extractor.py |
| JOLTS Job Openings | fred_extractors.py |
| NFP (Nonfarm Payrolls) | fred_extractors.py |
| CPI (Headline & Core) | fred_extractors.py |
| PPI | fred_extractors.py |
| Retail Sales | fred_extractors.py |
| Consumer Sentiment | fred_extractors.py |
| Sahm Rule | fred_extractors.py |
| S&P 500 Forward P/E | web_scrapers.py |
| Shiller CAPE | shiller_extractor.py |
| Put/Call Ratio | web_scrapers.py |
| CBOE SKEW | web_scrapers.py |
| Market Breadth | web_scrapers.py |
| Cu/Au Ratio | commodities_extractors.py |
| CFTC COT (Gold & Silver) | cot_extractor.py |
| HY/IG Credit Spreads | fred_extractors.py |
| NFCI | fred_extractors.py |
| M2 Money Supply | fred_extractors.py |
| TGA Balance | fred_extractors.py |
| Net Liquidity | fred_extractors.py |
| Bank Reserves | fred_extractors.py |
| SLOOS | fred_extractors.py |
| Housing Starts | fred_extractors.py |
| Unemployment Rate | fred_extractors.py |
| Initial/Continuing Claims | fred_extractors.py |
| Japan 2Y Yield | japan_yield_extractor.py |
| 13F Institutional Holdings | thirteenf_extractor.py |
| S&P 500 Large-cap Financials | equity_financials_extractor.py, sec_extractor.py |
| SOFR Futures Term Structure | fidenza_extractors.py (SR3 contracts) |
| Brent Crude Oil (BZ=F) | fidenza_extractors.py |
| Nikkei 225 (^N225) | fidenza_extractors.py |
| KOSPI (^KS11) | fidenza_extractors.py |
| Bovespa (^BVSP) | fidenza_extractors.py |
| MSCI EM (EEM proxy) | fidenza_extractors.py |
| Fed Funds Futures (ZQ=F) | fidenza_extractors.py |
| XAU/JPY | fidenza_extractors.py (computed) |
| Gold/Silver Ratio | fidenza_extractors.py (computed) |
| AAII Bull/Bear Sentiment | fidenza_extractors.py (web scrape) |
| ADP Employment | fred_extractors.py (ADPWNUSNERSA) |
| Fed Balance Sheet (WALCL) | fred_extractors.py |
| Treasury Term Premia (10Y, 5Y) | fred_extractors.py (THREEFYTP10, ACMTP05) |

---

## Implementation Priority Recommendation

### High Priority (enables trade replication & core Fidenza themes)
1. ✅ **SOFR Futures Term Structure** — `fidenza_extractors.py` → `sofr_futures_term_structure.csv`
2. ✅ **Brent Crude** — `fidenza_extractors.py` → `brent_crude.csv`
3. ✅ **Nikkei 225** — `fidenza_extractors.py` → `nikkei_225.csv`
4. ✅ **US 30Y Treasury Yield** — Already existed in `fred_extractors.py`
5. ✅ **AAII Bull/Bear Sentiment** — `fidenza_extractors.py` → `aaii_sentiment.csv`
6. **BTC & ETH** — Not yet implemented (yfinance BTC-USD, ETH-USD)
7. ✅ **EM Indices (KOSPI, Bovespa, MSCI EM)** — `fidenza_extractors.py` → 3 CSVs

### Medium Priority (enhances analysis framework)
8. **Treasury Bond/Note Futures (ZB, ZN)** — Not yet implemented
9. ✅ **Fed Funds Futures** — `fidenza_extractors.py` → `fed_funds_futures.csv`
10. ✅ **XAU/JPY** — `fidenza_extractors.py` → `xau_jpy.csv`
11. ✅ **Gold/Silver Ratio** — `fidenza_extractors.py` → `gold_silver_ratio.csv`
12. ✅ **ADP Employment** — `fred_extractors.py` → `adp_employment.csv`
13. ✅ **Fed Balance Sheet (WALCL)** — `fred_extractors.py` → `fed_balance_sheet.csv`
14. **OIH, XLE, KWEB** — Not yet implemented (sector ETFs)

### Low Priority (nice-to-have or requires paid sources)
15. ⚠️ **OPEC spare capacity** — Implemented but failing (no EIA key, TE page changed)
16. ⚠️ **Gold share of global reserves** — Implemented but failing (WGC 404)
17. ✅ **Treasury term premia** — `fred_extractors.py` → `treasury_term_premia.csv`
18. **Corporate bond issuance** — Manual tracking, no clean API
19. **CTA positioning** — Requires paid GS/UBS access
20. **SpotGamma dealer exposure** — Paid subscription only
21. **Uranium prices** — Niche, web scraping required

---

*This document catalogs data source gaps between the Fidenza Macro trading framework and the macro_2 codebase. It should be updated as new data sources are added.*

---

## Implementation Log

| Date | Items Implemented | Files Modified |
|------|-------------------|---------------|
| 2026-03-08 | 13 indicators (SOFR futures, Brent, Nikkei, EM indices, Fed Funds futures, XAU/JPY, Gold/Silver ratio, AAII sentiment, ADP employment, Fed balance sheet, Treasury term premia, OPEC production*, Gold reserves share*) | `fidenza_extractors.py` (new), `fred_extractors.py`, `__init__.py`, `extract_historical_data.py` |

*\* OPEC production and Gold reserves share are implemented but currently fail due to source access issues (no EIA API key, WGC URL 404). They degrade gracefully.*
