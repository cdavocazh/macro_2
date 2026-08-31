# CLAUDE.md

## What is this project?

Macroeconomic indicators dashboard with large-cap equity financials. Fetches 88+ indicators from financial APIs (yfinance, FRED, SEC EDGAR, OpenBB/Finviz, web scrapers, MOF Japan, AAII, Hyperliquid, CheckOnChain), displays them across **4 dashboard frontends** (Streamlit, Plotly Dash, Grafana, React), caches locally for fast startup, and exports to CSV. Includes 5-year OHLCV history for commodities and futures (back to 2021), sector ETF tracking, high-frequency macro proxies, Hyperliquid DeFi perpetual futures with 1-minute refresh and multi-interval OHLCV candlestick charts, and BTC on-chain metrics (MVRV, NUPL, SOPR, NVT, realised price).

**Repo:** https://github.com/cdavocazh/macro_2
**Branch:** main

## Quick commands

```bash
# Run the Streamlit dashboard (loads from cache if available, otherwise fetches live)
streamlit run app.py

# Run the Plotly Dash dashboard (standalone, reads from same cache)
python dash_dashboard/app.py              # http://localhost:8050

# Run the Grafana dashboard (local mode with API bridge)
bash grafana_dashboard/start.sh local     # http://localhost:3000

# Run the React dashboard (Vite + FastAPI)
bash react_dashboard/start.sh             # http://localhost:5173

# Refresh data manually (updates cache + CSVs, skips if <15min old)
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard

# Extract all historical data to CSV (dual-source equity financials)
python extract_historical_data.py

# Batch extract S&P 500 financials (~30-40 min for full run)
python extract_sp500_financials.py                              # full S&P 500, Yahoo
python extract_sp500_financials.py --source both                # Yahoo + SEC
python extract_sp500_financials.py --resume --exclude-top20     # skip existing + Top 20
python extract_sp500_financials.py --tickers CRM,AMD,NFLX      # specific tickers
python extract_sp500_financials.py --index midcap400            # S&P MidCap 400 (~400 tickers)
python extract_sp500_financials.py --index russell1000 --resume # Russell 1000 (~1000 tickers), incremental

# Monitor earnings dates and flag stale data
python monitor_earnings.py                          # scan all companies in database
python monitor_earnings.py --auto-update            # scan + re-extract stale tickers
python monitor_earnings.py --tickers AAPL,MSFT      # check specific tickers only

# Weekly data freshness review (compares local data vs SEC EDGAR)
python review_data_freshness.py                     # full S&P 500 review
python review_data_freshness.py --auto-update       # review + re-extract stale
python review_data_freshness.py --top20-only        # only Top 20
python review_data_freshness.py --report            # save CSV to data_export/

# Extract 13F institutional fund holdings (SEC EDGAR)
python extract_13f_holdings.py                              # all 5 funds, last 8 quarters
python extract_13f_holdings.py --funds berkshire_hathaway,citadel
python extract_13f_holdings.py --max-filings 4              # only last 4 quarters
python extract_13f_holdings.py --list-funds                 # show available funds

# Test individual Fidenza Macro gap-fill extractors
python -c "from data_extractors.fidenza_extractors import get_brent_crude; print(get_brent_crude())"
python -c "from data_extractors.fidenza_extractors import get_sofr_futures_term_structure; print(get_sofr_futures_term_structure())"
python -c "from data_extractors.fidenza_extractors import get_aaii_sentiment; print(get_aaii_sentiment())"
python -c "from data_extractors.fred_extractors import get_adp_employment; print(get_adp_employment())"

# Test OpenBB-based extractors (all use fallbacks if OpenBB not installed)
python -c "from data_extractors.openbb_extractors import get_vix_futures_curve; print(get_vix_futures_curve())"
python -c "from data_extractors.openbb_extractors import get_ecb_policy_rates; print(get_ecb_policy_rates())"
python -c "from data_extractors.openbb_extractors import get_fama_french_factors; print(get_fama_french_factors())"
python -c "from data_extractors.openbb_extractors import get_equity_risk_premium; print(get_equity_risk_premium())"

# Fast extraction — real-time yfinance only (~5s, safe for 5-min polling)
python fast_extract.py                # run once
python fast_extract.py --dry-run      # list what would be extracted
python fast_extract.py --force        # ignore freshness guard

# Hyperliquid extraction — 1-minute perp + spot data (~0.5s)
python hl_extract.py                  # run once
python hl_extract.py --dry-run        # show what would be extracted
python hl_extract.py --force          # ignore freshness guard

# CheckOnChain BTC on-chain data extraction (daily)
python onchain_extract.py                     # extract all 8 priority charts
python onchain_extract.py --chart mvrv_zscore # single chart
python onchain_extract.py --list              # list available charts
python onchain_extract.py --force             # ignore freshness guard
python onchain_extract.py --verify            # check data freshness
python onchain_extract.py --dry-run           # show what would be extracted

# Install macOS launchd auto-scheduler (5 jobs)
bash setup_launchd.sh                 # install all jobs
bash setup_launchd.sh --status        # check all jobs
bash setup_launchd.sh --uninstall     # remove all jobs

# IBKR real-time streaming daemon (VPS, requires IB Gateway)
python ibkr_fast_extract.py                   # auto-detect port
python ibkr_fast_extract.py --port 4001       # specify port
python ibkr_fast_extract.py --dry-run         # list instruments, no connect

# Macro catalyst calendar (FRED release dates + FOMC)
python -c "from data_extractors.macro_calendar_extractor import build_macro_calendar; print(build_macro_calendar())"

# Run data review agent (requires MINIMAX_API_KEY)
python -m agent.openai_agents.agent "Scan all companies for missing data"
python -m agent.langchain_agents.agent "Compare Yahoo vs SEC for AAPL"

# Run dashboard data QA agent (scheduled on VPS every 12h)
python -m agent.openai_agents.qa_agent
python -m agent.openai_agents.qa_agent --check C3   # single check
```

## Architecture

```
app.py                        Streamlit dashboard (9 tabs, compact layout, ~2,300 lines)
data_aggregator.py            Orchestrator — fetches all 88+ indicators, saves/loads cache, auto-reload
  ├── data_extractors/
  │   ├── yf_safe.py                   yfinance wrapper — trims trailing bars with no price (Yahoo serves OHLC=NaN/Volume-only bars); all yf.Ticker calls route through it
  │   ├── yfinance_extractors.py       18+ indicators (VIX, DXY, Russell, ES/RTY futures w/ OHLCV, JPY, EUR/USD, GBP/USD, EUR/JPY, SPY/RSP, sector ETFs, VIX term structure, put/call ratio, BDI)
  │   ├── fred_extractors.py           38 indicators (GDP, yields, ISM PMI, TGA, liquidity, SOFR, spreads, inflation, labor, M2, JOLTS, Sahm, SLOOS, ADP, WALCL, term premia, home sales, GDPNow, WEI)
  │   ├── web_scrapers.py               4 indicators (Forward P/E, Put/Call, SKEW, breadth)
  │   ├── shiller_extractor.py          1 indicator  (CAPE ratio — multpl.com primary, Yale Excel fallback)
  │   ├── openbb_extractors.py         21 indicators (S&P fundamentals + 20 OpenBB-based: VIX futures, put/call, multiples, ECB rates, OECD CLI, CPI components, Fama-French, IV skew, EU yields, global CPI, earnings, sector P/E, treasury curve, corp spreads, intl unemployment/GDP, screener, money measures, PMI, ERP; optional dep)
  │   ├── commodities_extractors.py     7 indicators (gold, silver, oil, copper, natural gas, Cu/Au ratio) — all with 5y OHLCV
  │   ├── cot_extractor.py              2 indicators (CFTC COT positioning: gold/silver + crude oil/Brent/copper/nat gas via SODA API)
  │   ├── japan_yield_extractor.py      2 indicators (Japan 2Y yield, US-JP spread)
  │   ├── global_yields_extractor.py    4 indicators (Germany/UK/China 10Y yields, ISM Services PMI)
  │   ├── yield_curve_extractor.py      1 indicator  (2s10s spread + regime classification)
  │   ├── equity_financials_extractor.py  Top 20 company financials (Yahoo Finance)
  │   ├── sec_extractor.py              Top 20 company financials (SEC EDGAR XBRL)
  │   ├── thirteenf_extractor.py       13F-HR institutional holdings (5 funds, QoQ changes)
  │   ├── fidenza_extractors.py       13 indicators (Brent, Nikkei, EM indices, SOFR/FF futures, XAU/JPY, Au/Ag ratio, AAII, OPEC, gold reserves)
  │   ├── hyperliquid_extractor.py    2 indicators (HL perps: BTC/ETH/SOL/PAXG/HYPE/OIL + HIP-3 spot stocks)
  │   ├── macro_calendar_extractor.py 1 output (forward-looking US macro release calendar + FOMC dates)
  │   ├── ibkr_streaming.py           IBKR real-time streaming module (ib_async, tick-level futures/FX/indices)
  │   └── sp500_tickers.py             S&P 500 constituent list (Wikipedia + cache)
  └── utils/helpers.py               Cache serialization, CSV export, formatting

dash_dashboard/               Plotly Dash dashboard (standalone, ~2,300 lines)
  ├── app.py                  Main Dash app with 8 tabs, expandable historical charts
  ├── data_loader.py          Singleton cache reader with lazy loading + mtime auto-reload
  ├── assets/style.css        Custom CSS for compact layout
  ├── wsgi.py                 Gunicorn WSGI entry point
  └── deploy/                 AWS Lightsail deployment (systemd, nginx, deploy.sh)

grafana_dashboard/            Grafana dashboard (111 panels, Docker + local mode)
  ├── api_bridge/main.py      FastAPI bridge translating data_aggregator → Grafana JSON
  ├── dashboards/             Pre-built dashboard JSON (auto-provisioned)
  ├── provisioning/           Grafana datasource + dashboard provider configs
  ├── docker-compose.yml      Docker mode (Grafana + API bridge containers)
  └── start.sh                Start script (supports `local` and `docker` modes)

react_dashboard/              React + Vite dashboard with FastAPI backend
  ├── backend/main.py         FastAPI server reading from data_aggregator cache
  ├── frontend/src/           React components (9 tab panels, metric cards, charts)
  └── start.sh                Start script (backend + frontend concurrently)

fast_extract.py               5-minute real-time yfinance extraction (31 extractors, ~5s) + cache merge into all_indicators.json
hl_extract.py                 1-minute Hyperliquid extraction (perps + spot, ~0.5s) + partial cache merge
onchain_extract.py            Daily CheckOnChain BTC on-chain data (8 charts: MVRV, NUPL, SOPR, NVT, realised price)
ibkr_fast_extract.py          IBKR real-time streaming daemon (VPS, ib_async, 3s snapshot writes)
scheduled_extract.py          Full catch-up script — FRED, SEC, web scrapers (does NOT touch app.py)
extract_historical_data.py    Append-only historical CSV builder (dual-source equity)
extract_sp500_financials.py   Batch extraction of S&P 500 financials (~30-40 min)
extract_13f_holdings.py       13F institutional fund holdings extraction (~25s)
monitor_earnings.py           Earnings date monitoring — flags stale companies (~45s)
review_data_freshness.py      Weekly SEC filing date comparison — flags stale data (~2 min)
config.py                     API keys, cache settings

deploy/systemd/               VPS systemd unit files (IBKR stream, data QA, cache repair)
scripts/                      Utility scripts (repair_cache_errors.py)

agent/                        Financial data QA agents (equity cross-source + dashboard health)
  ├── shared/tools.py         8 equity QA tools
  ├── shared/qa_tools.py      11 dashboard data QA tools
  ├── shared/freshness_sla.py Per-indicator SLA definitions
  ├── openai_agents/agent.py  Equity QA — OpenAI Agents SDK + Minimax LLM
  ├── openai_agents/qa_agent.py  Dashboard QA — scheduled 12h health check + Telegram alerts
  └── langchain_agents/agent.py  Equity QA — LangChain + LangGraph + Minimax LLM
```

## Dashboard tabs

| Tab | Name | Indicators |
|-----|------|------------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP, S&P 500 Multiples (Finviz), Sector P/E Ratios, Equity Risk Premium |
| 2 | Market Indices | ES/RTY futures, breadth, Russell 2000 V/G, S&P 500/200MA, SPY/RSP concentration, Fama-French 5 Factors, Earnings Calendar |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW, VIX Futures Curve, SPY Put/Call OI, IV Skew |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI, Money Supply (M1/M2) |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning (gold/silver + energy/copper via SODA API), Hyperliquid perps (BTC, ETH, SOL, PAXG, HYPE, OIL) + HIP-3 spot stocks |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker text input, dual-source (Yahoo + SEC EDGAR), quarterly statements |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields (US 5Y/10Y, DE/UK/CN 10Y), real yield, breakevens, HY/IG OAS, NFCI, Fed Funds, bank reserves, SLOOS, unemployment, claims, CPI, PPI, PCE, ECB Rates, CPI Components, EU Yields, Global CPI, Full Treasury Curve, Corporate Spreads |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, Retail Sales, ISM Services PMI, Industrial Production, Housing Starts, OECD CLI, Intl Unemployment, Intl GDP, Global PMI |
| 9 | Polymarket | Prediction market events (politics, crypto, macro), YES/NO prices, volume, multi-outcome markets |

## Dashboard frontends

All 4 frontends read from the same `data_cache/all_indicators.json` (populated by `data_aggregator.py`):

| Frontend | Directory | Port | Best for |
|----------|-----------|------|----------|
| **Streamlit** | `app.py` (root) | 8501 | Quick local dev, interactive widgets, Streamlit Cloud deploy |
| **Plotly Dash** | `dash_dashboard/` | 8050 | Production deploy (gunicorn), expandable historical charts, AWS Lightsail |
| **Grafana** | `grafana_dashboard/` | 3000 | Time-series panels, alerting, multi-user monitoring |
| **React + Vite** | `react_dashboard/` | 5173 | Custom SPA, modern UI, extensibility |

## Dashboard features (Streamlit)

- **Compact dense layout**: Custom CSS injection shrinks metrics (1.3rem value, 0.72rem label), reduces column/block gaps to 0.3rem, and compresses captions (0.68rem). ~40% more indicators visible per screen vs default Streamlit spacing.
- **Expandable 3M price charts**: Every indicator in tabs 1, 3, 4, 5 has a collapsible plotly chart with 1W/1M/3M zoom buttons
- **Collapsible standalone charts**: 7 large standalone charts (Net Liquidity, US-JP Yield Spread, 10Y vs ISM PMI, COT Positioning, 2s10s Spread, Global 10Y Yields, Nominal vs Real vs Breakeven) are wrapped in `st.expander()` — collapsed by default, saving ~400px each
- **QoQ/YoY indicators**: Quarterly financial tables show colored percentage changes (green positive, red negative)
- **Numerator/denominator display**: Financial analysis and valuation metrics show formula components in small gray text
- **Multi-source switching**: Tab 6 supports Yahoo Finance and SEC EDGAR with radio button toggle
- **Custom ticker input**: Tab 6 has a text input alongside the Top 20 dropdown — type any ticker for on-demand fetching
- **Revenue segments**: SEC EDGAR source shows business segment breakdown from 10-K filings
- **Auto-reload on rerun**: Dashboard detects when `scheduled_extract.py` has updated the cache file (via file mtime) and reloads automatically — no manual Refresh needed

## Dashboard features (Plotly Dash)

- **Expandable historical charts**: `html.Details` + `html.Summary` pattern for click-to-expand charts across Valuation, Indices, Volatility, Macro & FX tabs (hidden by default)
- **Range selectors**: 1W/1M/3M/6M/1Y/2Y buttons on historical charts
- **S&P 500 Multiples**: 3-tier data cascade — OpenBB/Finviz per-stock weighted → multpl.com scrape → yfinance SPY
- **ERP with forward PE**: Uses OpenBB/Finviz forward_pe data for forward ERP computation
- **Production-ready**: Gunicorn WSGI, systemd services, nginx reverse proxy, AWS Lightsail deploy script
- **Auto-reload**: `data_loader.py` checks cache file mtime every 60 seconds, reloads if stale

## Data flow

```
scheduled_extract.py (or app.py Refresh button)
  → data_aggregator.fetch_all_indicators()
    → calls each extractor module
    → saves to data_cache/all_indicators.json  (JSON, 24h TTL)
    → appends to historical_data/*.csv         (append-only, deduplicated)
    → writes data_export/*.csv                 (latest snapshot)

app.py startup / rerun
  → calls reload_if_stale()                   (compares file mtime vs in-memory, ~0.1ms)
  → re-reads JSON only if cache file is newer  (picks up scheduled_extract.py updates)
  → falls back to fetch_all_indicators()      (slow, ~40s, only when no cache exists)
```

## Local storage (3 directories, all gitignored)

| Directory | Purpose | Format |
|-----------|---------|--------|
| `data_cache/` | Fast dashboard startup cache | Single JSON file, 24h TTL |
| `historical_data/` | Append-only archival data | Per-indicator CSVs + equity_financials/{source}/ |
| `data_export/` | Latest snapshot for export | Per-indicator CSVs + summary |

### Equity financials storage (dual-source)

```
historical_data/equity_financials/
  ├── yahoo_finance/
  │   ├── AAPL_quarterly.csv
  │   ├── MSFT_quarterly.csv
  │   ├── ... (up to ~500 tickers via extract_sp500_financials.py)
  │   └── _valuation_snapshot.csv
  └── sec_edgar/
      ├── AAPL_quarterly.csv
      ├── MSFT_quarterly.csv
      ├── ... (up to ~500 tickers, TSM excluded — IFRS)
      └── _valuation_snapshot.csv
```

### 13F institutional holdings storage

```
historical_data/13F/
  ├── situational_awareness/     Situational Awareness LP (CIK 0002045724)
  ├── berkshire_hathaway/        Berkshire Hathaway Inc (CIK 0001067983)
  ├── bridgewater/               Bridgewater Associates LP (CIK 0001350694)
  ├── citadel/                   Citadel Advisors LLC (CIK 0001423053)
  └── renaissance_technologies/  Renaissance Technologies LLC (CIK 0001037389)
      ├── holdings_2025Q4.csv    Per-quarter holdings snapshot
      ├── holdings_2025Q3.csv
      └── changes.csv            QoQ position changes (NEW/INCREASED/DECREASED/EXITED)
```

### On-chain BTC data (CheckOnChain)

```
historical_data/onchain/
  ├── mvrv_zscore.csv        MVRV Z-Score (regime detection)
  ├── sth_sopr.csv           Short-Term Holder SOPR (profit/loss indicator)
  ├── nupl.csv               Net Unrealized Profit/Loss (mood bands)
  ├── nvt_premium.csv        Coinblock NVT Premium (network value vs throughput)
  ├── lth_mvrv.csv           Long-Term Holder MVRV
  ├── lth_sopr.csv           Long-Term Holder SOPR
  ├── lth_aviv.csv           Long-Term Holder AVIV ratio
  └── realised_price.csv     BTC Realised Price
```

## Top 20 tickers

```python
TOP_20_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'BRK-B', 'TSM',
                  'LLY', 'AVGO', 'JPM', 'V', 'WMT', 'MA', 'XOM', 'UNH', 'COST', 'HD', 'PG', 'JNJ']
```

## Key design decisions

- **Cache-first startup with auto-reload:** Dashboard loads from `data_cache/all_indicators.json` instantly. `reload_if_stale()` in `data_aggregator.py` compares file mtime against in-memory `last_update` (~0.1ms syscall) and re-reads JSON only when the cache file is newer. Both `scheduled_extract.py` (full, 5x/day) and `fast_extract.py` (yfinance subset, every 5 min) update the cache file, so dashboards stay fresh even if the full extraction fails. `load_from_cache()` falls back to stale data when the cache is expired (>24h), preventing 503 errors.
- **Fast extract cache merge:** `fast_extract.py` merges ~18 yfinance-based indicators into `all_indicators.json` after each run using atomic write (`os.rename`). This keeps the cache timestamp fresh so dashboards never see an expired cache during market hours. The extractors are called a second time but yfinance's internal HTTP cache makes this near-free.
- **Pandas serialization:** `helpers.py` has `_serialize_value()` / `_deserialize_value()` to handle `pd.Series`, `pd.DataFrame`, numpy types in JSON cache. These must stay in sync.
- **Freshness guard:** `scheduled_extract.py` skips if cache is <15 minutes old. Prevents duplicate API calls.
- **Append-only CSVs:** `extract_historical_data.py` uses `append_to_csv()` which deduplicates by timestamp column. Never overwrites.
- **Graceful degradation:** Every extractor returns `{'error': msg}` on failure. Dashboard renders green cards for success, red for errors.
- **FY-end quarter derivation (SEC):** Q4 = Annual 10-K value minus (Q1+Q2+Q3). Searches across ALL XBRL concept alternatives to handle companies that switch concepts mid-year (e.g. GOOGL).
- **Cumulative YTD cash flow (SEC):** NVDA reports cumulative cash flows. `_get_cashflow_quarterly_values()` detects monotonic growth and subtracts prior quarters.
- **Cross-concept merging (SEC):** Revenue, net income can use different XBRL concepts per company. Merged from all alternatives; first non-None wins.
- **Dual-source equity storage:** Historical data saves per-company quarterly CSVs into `yahoo_finance/` and `sec_edgar/` subdirectories for cross-validation.
- **Singleton aggregator with auto-reload:** `get_aggregator()` returns a single global instance. `reload_if_stale()` uses `os.path.getmtime()` to detect when the cache file has been updated externally (by `scheduled_extract.py`) and re-reads it without requiring a full fetch. This fixed a bug where the singleton pattern caused stale dashboard data (the `if not aggregator.indicators` guard was always False after first load).
- **Network connectivity check:** `scheduled_extract.py` probes Yahoo/FRED/SEC hosts before starting extraction. Retries up to 6 times (10s apart, 60s max) to ride out VPN reconnections. Aborts cleanly if no network.
- **S&P 500 ticker list:** `sp500_tickers.py` scrapes Wikipedia and caches to `data_cache/sp500_tickers.json` (7-day TTL). Falls back to hardcoded list if Wikipedia is unreachable.
- **On-demand custom tickers:** Tab 6 text input fetches any ticker on-demand via `get_company_financials_yahoo()` and auto-saves to `historical_data/` via `save_single_company()`.
- **Earnings monitoring:** `monitor_earnings.py` uses lightweight `yfinance ticker.info` calls (~45s for 500 companies) to compare `mostRecentQuarter` against local CSVs. No full financial fetching.
- **SEC freshness review:** `review_data_freshness.py` uses the SEC submissions endpoint (~100KB per call, <200ms) via `get_latest_filing_dates()` to compare filing dates without downloading full companyfacts data.
- **13F holdings extraction:** `thirteenf_extractor.py` parses SEC 13F-HR XML infotables for 5 tracked institutional funds. Reuses `_rate_limit()` and `SEC_HEADERS` from `sec_extractor.py`. Handles 13F-HR/A amendments (prefers latest per quarter). Computes QoQ changes keyed by `(cusip, put_call)`. XML `<value>` field is in dollars (not thousands despite SEC form instructions).
- **Fidenza Macro gap-fill extractors:** `fidenza_extractors.py` adds 10 functions for instruments/indicators from the Fidenza Macro trading newsletter. Includes yfinance price series (Brent, Nikkei, EM indices, SOFR/Fed Funds futures), computed ratios (XAU/JPY, Gold/Silver), and web scrapes (AAII sentiment, OPEC production, gold reserves share). FRED additions (ADP, WALCL, term premia) live in `fred_extractors.py`. All 13 extraction wrappers are registered in `extract_historical_data.py`. SOFR futures use dynamic quarterly contract ticker generation (SR3{H/M/U/Z}{YY}.CME format). XAU/JPY and Gold/Silver ratio use `.tz_localize(None).normalize()` to handle cross-timezone yfinance index joins.
- **CFTC COT SODA API:** `cot_extractor.py` uses CFTC SODA API (`publicreporting.cftc.gov/resource/72hh-3qpy.json`) as fast primary path for COT positioning data (crude oil `067651`, Brent `06765T`, copper `085692`, natural gas `023651`, gold `088691`, silver `084691`). Falls back to `cot-reports` bulk download if SODA fails. Returns managed money long/short/net, producer net, swap positions, and historical series. Disaggregated futures report format.
- **OHLCV extension (Data Extraction Requirements):** Commodities (GC=F, SI=F, CL=F, HG=F), ES/RTY futures, and Brent crude now return `historical_ohlcv` (DataFrame with Open/High/Low/Close/Volume) alongside existing `historical` (Close-only Series) for backward compatibility. All use `period='5y'` for ~1,260 trading days of history (back to 2021). OHLCV CSVs use `{prefix}_open/high/low/close/volume` column naming. `_extract_ohlcv_series()` helper in `extract_historical_data.py` handles the DataFrame → CSV conversion.
- **Sector ETFs:** 11 SPDR sector ETFs (XLK, XLF, XLV, XLE, XLI, XLC, XLY, XLP, XLB, XLRE, XLU) tracked via `get_sector_etfs()` in `yfinance_extractors.py`. Wide-format CSV with one column per ETF.
- **High-frequency macro proxies:** GDPNow (Atlanta Fed, FRED GDPNOW), WEI (NY Fed Weekly Economic Index, FRED WEI) for macro nowcasting. VIX term structure (spot vs futures, contango ratio). BDI and put/call ratio attempted but not available on yfinance (known limitation).
- **Compact dashboard layout:** Custom CSS via `st.markdown(unsafe_allow_html=True)` overrides Streamlit's default spacing. Key rules: metric padding 0.2rem, value font 1.3rem, label 0.72rem, caption 0.68rem, column gap 0.3rem. Tab dividers removed, verbose captions pruned, sidebar About collapsed into expander. Tab 3 uses 3 columns (VIX/MOVE/Ratio), Tab 4 FX uses 5 columns (DXY/JPY/EUR-USD/GBP-USD/EUR-JPY). Tab 1 Historical Valuation section removed (was making a slow `yf.Ticker("SPY")` network call on every page load).

- **IBKR streaming architecture:** `ibkr_fast_extract.py` is a long-running daemon (not a periodic script) that maintains live WebSocket connections to IB Gateway. Writes atomic JSON snapshots to `data_cache/ibkr_realtime.json` every 3 seconds. 17 instruments: 3 index futures (ES/NQ/RTY), 3 metals (GC/SI/HG), 2 energy (CL/NG), 4 treasury futures (ZN/ZB/ZF/ZT), 2 micro yield futures (10Y/2YY), VIX index, 2 FX (EUR/USD, USD/JPY). Connection retry: 1 hour backoff if IBKR unavailable. Manifest pin system allows contract spec overrides via `data_cache/ibkr_subscriptions.json`. CSV overlay writes 5-min summary rows into existing `historical_data/*.csv` files (matches yfinance column names for seamless merge).
- **Macro catalyst calendar:** `macro_calendar_extractor.py` queries FRED `/release/dates` API for 8 key macro releases (CPI, PPI, NFP, GDP, PCE, ISM, JOLTS, retail sales) + scrapes FOMC meeting dates from `federalreserve.gov`. Output: `historical_data/macro_catalyst_calendar.csv`. Consumed by `Finl_Agent_CC/tools/option_strategy.py` for non-earnings catalyst veto logic in sell-vol strategies.
- **Dashboard Data QA agent:** `agent/openai_agents/qa_agent.py` runs 11 checks in a fixed sequence (no agent framework tool-calling), sends aggregated findings to Minimax LLM for triage synthesis, then pushes CRITICAL-severity findings to Telegram. Scheduled every 12h on VPS via systemd timer (00:00 + 12:00 UTC). SLA thresholds in `agent/shared/freshness_sla.py` were calibrated post-first-run: relaxed from strict (monthly=45d) to realistic (monthly=75d) to match actual publication schedules.

- **Multi-frontend architecture:** All 4 dashboards (Streamlit, Dash, Grafana, React) share the same data layer (`data_aggregator.py` → `data_cache/all_indicators.json`). No frontend has its own data fetching logic. Dash uses `data_loader.py` (singleton with mtime check), Grafana uses `api_bridge/main.py` (FastAPI reading aggregator), React uses its own FastAPI backend. This means `scheduled_extract.py` and `fast_extract.py` feed all dashboards simultaneously.
- **S&P 500 Multiples 3-tier cascade:** `_sp500_multiples_openbb()` (OpenBB/Finviz per-stock, market-cap weighted for Top 20) → `_sp500_multiples_fallback()` (multpl.com scraping for index-level ratios) → yfinance SPY ETF (last resort). The OpenBB path also scrapes Finviz quote pages for PEG ratio and EPS growth rates not available via the API.
- **ERP forward PE sourcing:** `get_equity_risk_premium()` checks if indicator `65_sp500_multiples` has a valid `forward_pe` from OpenBB/Finviz before computing forward ERP. Falls back to yfinance SPY `forwardPE` (usually None).

- **CheckOnChain on-chain BTC extraction:** `onchain_extract.py` scrapes Plotly-based charts from `charts.checkonchain.com` (static HTML, no auth). Data is base64-encoded float64 arrays embedded in Plotly trace objects; decoded via `np.frombuffer()`. Standalone script — not coupled to `data_aggregator.py` or the dashboard cache. Output: `historical_data/onchain/*.csv`. 8 charts: MVRV Z-Score, STH/LTH SOPR, NUPL (mood-band concat merge), NVT Premium, LTH MVRV/AVIV, Realised Price. Merge modes handle split traces (SOPR >1/<1 → single series) and mood-band concatenation (NUPL). 20-hour freshness guard. 2-second delay between distinct URLs. Constant-value traces (threshold lines) auto-filtered.
- **OpenBB-based extractors (20 functions):** All live in `openbb_extractors.py` behind `OPENBB_AVAILABLE` guard. Every function has a fallback path (FRED, yfinance, direct API, or computation) so the dashboard works without OpenBB installed. Free providers used: CBOE, Finviz, EconDB, ECB SDW, OECD, Fama-French, Federal Reserve. Fixes 3 known-broken indicators (VIX futures, Put/Call ratio, Forward P/E) and adds 17 new indicators across tabs 1-4, 7-8. Not included in `fast_extract.py` (too slow for 5-min polling). ECB rates fallback uses direct ECB SDW REST API. Fama-French fallback downloads ZIP from Ken French's data library. Indicator keys: 63-82.

## SEC EDGAR XBRL specifics

- **API:** `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` (free, 10 req/sec, User-Agent required)
- **CIK mapping:** Dynamic download from SEC `company_tickers.json`, cached to disk (7-day TTL). Supports any US ticker.
- **Valid forms:** 10-K, 10-Q, 20-F, 6-K
- **Duration detection:** Quarterly = 80-100 days, Annual = 340-380 days
- **TSM exception:** Files under `ifrs-full` namespace, not `us-gaap`. Returns error (known limitation).
- **Company-specific concepts:** JPM uses `RevenuesNetOfInterestExpense`, AVGO/MA use `ProfitLoss` for net income

## Scheduling (launchd)

Five launchd jobs run at different frequencies:

| Job | Plist | Schedule | What it extracts | Timeout |
|-----|-------|----------|-----------------|---------|
| **hl-extract** | `com.macro2.hl-extract.plist` | Every 1 minute (24/7) | Hyperliquid perps (BTC, ETH, SOL, PAXG, HYPE, OIL) + HIP-3 spot stocks. Partial cache merge (keys 84/85 only). | 50s |
| **fast-extract** | `com.macro2.fast-extract.plist` | Every 5 minutes (24/7) | Real-time yfinance only: futures, FX, commodities, indices, credit ETFs, sector ETFs, OHLCV, VIX term structure (31 extractors). Also merges ~18 indicators into `all_indicators.json` cache so dashboards stay fresh. | 4 min |
| **polymarket-extract** | `com.macro2.polymarket-extract.plist` | Every 5 minutes (24/7) | Polymarket prediction markets (politics, crypto, macro events). | 4 min |
| **scheduled-extract** | `com.macro2.scheduled-extract.plist` | 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) | Full extraction: FRED, SEC, web scrapers, yfinance, all CSVs | 20 min |
| **onchain-extract** | `com.macro2.onchain-extract.plist` | Daily at 14:00 GMT+8 (06:00 UTC) | CheckOnChain BTC on-chain data (8 charts: MVRV, NUPL, SOPR, NVT, realised price). Output: `historical_data/onchain/*.csv`. | 5 min |

**Python path:** `~/mambaforge/bin/python3`
**Logs:** `logs/launchd_stdout.log`, `logs/fast_extract_stdout.log`, `logs/hl_extract_stdout.log`, `logs/onchain_extract_stdout.log`

launchd catches up missed runs after sleep (unlike cron). `hl_extract.py` has a 45-second freshness guard. `fast_extract.py` has a 3-minute freshness guard. `scheduled_extract.py` has a 15-minute freshness guard. `onchain_extract.py` has a 20-hour freshness guard. The `TimeOut` in each plist auto-kills hung processes.

**VPS scheduling (systemd):** Three additional services run on the Hostinger VPS (`<VPS_HOST>`) via systemd — see `deploy/systemd/README.md` for unit files and deployment instructions:
- `macro2-ibkr-stream.service` — always-on IBKR streaming daemon (3s JSON snapshots)
- `macro-data-qa.timer` — 12h Data QA agent (00:00 + 12:00 UTC)
- `macro-cache-repair.timer` — periodic cache error auto-repair

### VPS Python environments (two venvs, deliberately)

| venv | Used by | Contents |
|------|---------|----------|
| `/root/macro_2/venv` | `macro-fast-extract`, `macro-hl-extract`, `macro-polymarket-extract`, `macro-cache-repair`, `macro-react.service` (uvicorn) | `requirements.txt` only — **no OpenBB** |
| `/root/macro_2/venv-openbb` | `macro-extract.service` (daily full extraction) only | `requirements.txt` + `requirements-openbb.txt` |

**Why two:** `openbb-core` hard-pins `uvicorn<0.41`, so installing OpenBB into the shared venv would downgrade the uvicorn serving `macro-react.service` (0.42.0 → 0.40.0). `yfinance` is pinned to the same version (1.2.0) in both so every extractor behaves identically across jobs; this leaves `openbb-yfinance` unsatisfied, which is harmless — no indicator uses the OpenBB yfinance provider as its serving path.

The service is switched via a systemd drop-in at `/etc/systemd/system/macro-extract.service.d/openbb-venv.conf`. `ExecStartPost` (cache repair) deliberately stays on the shared venv.

Even with OpenBB present, the import is lazy (`_obb()` in `openbb_extractors.py`), so nothing but the daily extraction loads it. Eagerly importing it cost the minutely/5-minutely job chain 6.4 s / 415 MB versus 1.1 s / 140 MB.

## API keys

- **FRED:** Set `FRED_API_KEY` in `.env` file (gitignored), env var, or Streamlit secrets. Get a free key from https://fred.stlouisfed.org/docs/api/api_key.html
- **SEC EDGAR:** No key needed (User-Agent header required, set in `sec_extractor.py`)
- **yfinance:** No key needed
- **Hyperliquid:** No key needed (public REST API + WebSocket)
- **IBKR (VPS streaming):** No API key, but requires IB Gateway (or TWS) running on the same host (default port 4001). `ib_async` connects locally.
- **Polymarket:** No key needed (public CLOB API at `clob.polymarket.com`)
- **CheckOnChain:** No key needed (public static HTML charts at `charts.checkonchain.com`)
- **Minimax (agent only):** `MINIMAX_API_KEY` env var required for agent subfolder
- **Telegram (agent alerts):** `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` in `.env` (optional, for CRITICAL alert push)
- **All others:** No key needed (web scraping or public data)

## Extractor return format

All extractors return a dict. Successful:
```python
{'vix': 15.5, 'change_1d': -2.1, 'latest_date': '2026-02-28', 'source': 'Yahoo Finance', 'historical': pd.Series(...)}
```
Failed:
```python
{'error': 'HTTP 403', 'note': 'Try manual approach', 'suggestion': '...'}
```

Equity financials return a nested dict per company with `income_statement`, `balance_sheet`, `cash_flow`, `valuation`, `financial_analysis` sections, each containing lists aligned to `quarters` list.

## Known-broken indicators

| Indicator | Source | Problem | Fallback |
|-----------|--------|---------|----------|
| S&P 500 Forward P/E | MacroMicro web scrape | 403 Forbidden (bot detection) | Uses SPY trailing P/E via `get_sp500_forward_pe_fallback()`. **Also see** `65_sp500_multiples` (Finviz/yfinance) |
| S&P 500 Put/Call Ratio | CBOE / ycharts scrape | Unreliable, often blocked | Falls back to FRED `PCERTOT` series or SPY options calc. **Also see** `64_spy_put_call_oi` (CBOE/yfinance) |
| TSM (SEC EDGAR) | SEC EDGAR XBRL | IFRS namespace, not us-gaap | Yahoo Finance only |
| OPEC Production | EIA API + Trading Economics | No EIA_API_KEY; TE page structure changed | Returns error dict gracefully |
| Gold Reserves Share | World Gold Council scrape | WGC URL returns 404 | Returns error dict gracefully |
| Put/Call Ratio | yfinance ^PCPUT/^PCALL | Tickers delisted from yfinance | Returns error dict gracefully |
| Baltic Dry Index | yfinance ^BDI/BDIY | Tickers delisted from yfinance | Returns error dict gracefully |
| VIX Futures (VX=F) | yfinance VX=F | Ticker not available on yfinance | VIX spot (^VIX) works. **FIXED 2026-08-30** for `63_vix_futures_curve`: `openbb-cboe` installed on the VPS and the forward is now derived via put-call parity from the CBOE VIX chain. Requires `venv-openbb`. |
| Shiller CAPE | Robert Shiller Yale Excel | ~~`ie_data.xls` last updated Oct 2023 — source is dead~~ **FIXED 2026-04-15** | Now scrapes multpl.com as primary source. Yale Excel retained as fallback. |
| Global CPI (US/EU) | FRED `CPALTT01USM657N` / `CP0000EZ19M086NEST` | ~~US discontinued Mar 2024; EU was returning index level (129) not YoY%~~ **FIXED 2026-04-15** | US: `CPIAUCSL` + compute YoY (3.32%). EU: `CP0000EZ19M086NEST` + compute YoY (1.94%). |
| Global PMI (EU/JP/CN/UK) | OpenBB EconDB / Trading Economics | EconDB carries no manufacturing PMI series (`obb.economy.pmi` removed from the router); Trading Economics now renders the value client-side, so the `"last":` regex no longer matches | Returns `None` for EU/JP/CN/UK with an accurate note. US keeps the Industrial-Production proxy. Needs a paid PMI feed or a headless-browser scrape. |
| ISM Services delta | Trading Economics scrape | Same TE client-side rendering change — Method 1 (JSON regex) no longer matches | Value still parsed via the Method 2 table fallback, but `change_1d` / `interpretation` are absent |
| S&P 500 Multiples PEG / P-to-Cash | OpenBB Finviz + finviz.com scrape | `obb.equity.fundamental.metrics(provider="finviz")` raises `EmptyDataError`; finviz.com's `snapshot-table2` now serves only 14 non-valuation labels | **FIXED 2026-08-31**: `_yf_peg_pcash_supplement()` fills both from yfinance Top-20 per-stock data (mcap-weighted PEG; Σmcap/Σcash P/Cash, ADRs excluded — their `totalCash` is in `financialCurrency`, e.g. TSM in TWD). Source captioned as a blend. |
| Global CPI (JP) | FRED `CPALTT01JPM657N` | OECD/FRED Japan CPI series frozen at Jun 2021 | No live FRED Japan CPI series available. Shows stale -0.4%. BOJ API needed. |
| Global CPI (UK) | FRED `CPALTT01GBM657N` | OECD/FRED UK CPI series frozen at Feb 2024 | Switched to `GBRCPIALLMINMEI` (available Mar 2025). |
| OECD CLI | FRED `USALOLITONOSTSAM` | ~~FRED series froze at Jan 2024; OECD SDMX API unreachable from VPS~~ **FIXED 2026-04-15** | Now uses CFNAI (Chicago Fed National Activity Index, `FRED:CFNAI`) as Tier 3 fallback. Scale normalised to CLI units (100 + cfnai×10). Shows Feb 2026 data. |
| Intl GDP (UK) | FRED `CLVMNACSCAB1GQUK` | ~~Series froze at 2020-Q2~~ **FIXED 2026-04-15** | Replaced with `NAEXKP01GBQ657S` (UK QoQ %, updating through Q4 2025). |
| Housing Starts | FRED `HOUST` | FRED HOUST showing Jan 2026 as latest despite Census Bureau releasing Feb/Mar data | FRED update lag — not a code bug. Monitor for resolution. |

## QA / Testing

**MANDATORY:** Every code change — new feature, bug fix, or refactor — must pass the testing checklist in [`QA_SOP.md`](QA_SOP.md) before being considered complete. This includes:

- React `<details>` chart pattern verification (Section 1)
- Duplicate timestamp deduplication (Section 2)
- API response validation (Section 3)
- Cache merge safety (Section 4)
- React build + tab navigation + console error check (Section 5)
- Dash dashboard render check (Section 6)
- Data extractor round-trip test (Section 7)
- Cross-dashboard consistency (Section 8)

The `QA_SOP.md` file also contains a **Bug Log** documenting every production bug encountered and its root cause, to prevent regressions.

## Common tasks

**Add a new indicator:**
1. Create a function in the appropriate `data_extractors/*.py` module
2. Add a `_fetch_with_error_handling()` call in `data_aggregator.py` `fetch_all_indicators()`
3. Add display logic in `app.py` under the appropriate tab
4. The cache and CSV export will pick it up automatically

**Add a new equity financial metric:**
1. Add the XBRL concept(s) to `sec_extractor.py` in `get_company_financials_sec()`
2. Add the Yahoo Finance key to `equity_financials_extractor.py`
3. Add the column key to `INCOME_KEYS`, `BALANCE_KEYS`, or `CASHFLOW_KEYS` in `extract_historical_data.py`
4. Add display logic in `app.py` tab 6

**Debug a failed indicator:**
```bash
python -c "from data_extractors.yfinance_extractors import get_vix; print(get_vix())"
python -c "from data_extractors.sec_extractor import get_company_financials_sec; print(get_company_financials_sec('AAPL'))"
```

**Batch extract S&P 500 financials:**
```bash
python extract_sp500_financials.py --source both --resume   # incremental update
python extract_sp500_financials.py --tickers CRM,AMD        # specific tickers
```

**Monitor earnings and update stale data:**
```bash
python monitor_earnings.py                    # scan all companies
python monitor_earnings.py --auto-update      # scan + auto re-extract stale
python review_data_freshness.py --report      # weekly freshness report
python review_data_freshness.py --auto-update # review + auto re-extract
```

**Extract 13F institutional holdings:**
```bash
python extract_13f_holdings.py                          # all 5 funds
python extract_13f_holdings.py --funds situational_awareness,berkshire_hathaway
python extract_13f_holdings.py --max-filings 4          # last 4 quarters only
```

**Add a new fund to 13F tracking:**
1. Find the fund's CIK on SEC EDGAR
2. Add entry to `FUND_REGISTRY` in `data_extractors/thirteenf_extractor.py`
3. Run `python extract_13f_holdings.py --funds new_fund_key`

**Deploy Dash dashboard to AWS Lightsail:**
```bash
cd dash_dashboard/deploy
cp .env.example .env && vim .env   # set LIGHTSAIL_IP, SSH_KEY_PATH
bash deploy.sh                     # rsync + systemd setup on remote
```

**Run Grafana locally (no Docker):**
```bash
bash grafana_dashboard/start.sh local   # starts API bridge + Grafana
# Dashboard auto-provisions at http://localhost:3000
```

**Change extraction schedule:**
1. Edit times in `com.macro2.scheduled-extract.plist`
2. Update the echo line in `setup_launchd.sh` to match
3. Run `bash setup_launchd.sh` to reload

## Documentation sync rule

**MANDATORY:** When making ANY code change that affects behavior, configuration, or architecture, you MUST update the relevant documentation in the same commit. Specifically:

| What changed | Update these docs |
|-------------|-------------------|
| Scheduling config (plist, freshness guard, timeouts) | CLAUDE.md "Scheduling" section, STATUS.md "Scheduling" section, README.md "Scheduling" section |
| New/removed indicator or extractor | CLAUDE.md "Architecture" + tab table, STATUS.md tab table, README.md "Dashboard Tabs" + "Project Structure" |
| New/removed agent tool | `agent/README.md` tools table, `agent/CLAUDE.md` tool table, `agent/STATUS.md` checklists |
| requirements.txt changes | CLAUDE.md "Tech stack", README.md if a new data source |
| Key design decisions or bug fixes | CLAUDE.md "Key design decisions", STATUS.md "Known Limitations" if relevant |
| Branch, repo, or deployment changes | All three: CLAUDE.md, STATUS.md, README.md headers/footers |
| Dash dashboard changes | `dash_dashboard/` files, CLAUDE.md "Dashboard features (Plotly Dash)" |
| Grafana dashboard changes | `grafana_dashboard/CLAUDE.md`, `grafana_dashboard/README.md` |
| React dashboard changes | `react_dashboard/CLAUDE.md`, `react_dashboard/README.md` |
| New bug fix or pattern fix | `QA_SOP.md` Bug Log table, relevant checklist section |
| Data extractor fix / broken data source replaced | **`agent/QA_learnings.md`** (add new entry with root cause + fix) + update "Known-broken indicators" table in this file |

**Never commit code changes without checking these docs for staleness.** When in doubt, update. Bump the version in STATUS.md for any non-trivial change.

**After every code change**, run the QA checklist in `QA_SOP.md` Section 10 (Pre-Commit Quick Check).

## Deployment gotcha (Streamlit Cloud)

`requirements.txt` uses `pandas>=2.2.0` (not pinned). Pinning `pandas==2.1.4` breaks on Python 3.13 (compilation fails). All deps use `>=` minimum versions for this reason.

## Tech stack

- Python 3.10 (mambaforge), compatible with 3.8-3.13
- **Data extraction:** pandas, yfinance, fredapi, beautifulsoup4, requests, ib_async (IBKR streaming)
- **OpenBB (optional, extraction host only):** `requirements-openbb.txt` — `openbb`, `openbb-cboe`, `openbb-ecb`. Deliberately outside `requirements.txt` (Streamlit Cloud installs that). Imported lazily, so only `scheduled_extract.py` pays its ~7 s / ~270 MB startup.
- **Streamlit dashboard:** streamlit, plotly
- **Dash dashboard:** dash, plotly, gunicorn
- **Grafana dashboard:** FastAPI (api_bridge), Grafana + Infinity datasource plugin
- **React dashboard:** React, Vite, FastAPI backend
- SEC EDGAR XBRL API (no key needed), Finviz (via OpenBB or direct scrape), Polymarket CLOB API
- macOS launchd for scheduling (local), systemd for VPS scheduling
- Agent: openai-agents, langchain, langgraph, Minimax LLM API

## Changelog

### 2026-08-31
- **Fixed: PEG Ratio and Price/Cash N/A on the Valuation Metrics card** — the serving source (multpl.com) genuinely lacks both, and the original per-stock source (Finviz) is dead in both forms. New `_yf_peg_pcash_supplement()` in `openbb_extractors.py` fills exactly those two gaps from yfinance Top-20 data whenever the serving tier lacks them: PEG as the market-cap-weighted mean of per-stock `trailingPegRatio` (clamped to (0,20) per stock), Price/Cash as Σmcap/Σcash — the index-style aggregate, since a weighted mean of per-stock P/C is dominated by cash-light mega-caps (AAPL ~75, NVDA ~84) and lands near 40. **Currency trap caught during validation:** yfinance reports `totalCash` in `financialCurrency` but `marketCap` in listing currency — TSM's cash arrived as NT$3.5T, 57% of the Top-20 cash sum as a pure FX artifact (P/C read 5.48). Tickers whose two currencies differ are excluded from the cash aggregate → P/C 11.82. Each metric requires ≥10 of 20 tickers or is omitted. `source` becomes `multpl.com (index) + yfinance Top-20 (PEG, P/Cash)` since frontends caption only `source`. Runs in `scheduled_extract.py` only (~50 s of `ticker.info` calls, 5x/day).

### 2026-08-30
- **Fixed: yfinance trailing-NaN bars nulled out 4 Market Indices cards** — Yahoo served the 2026-08-28 daily bar with OHLC all `NaN` and only Volume populated, for every US cash equity/ETF/index (`^GSPC`, `SPY`, `RSP`, `IWN`, `IWO`, `XLK`, `AAPL`, …) while futures and FX were unaffected. Extractors took `.iloc[-1]` on that frame, so `2_russell_2000`, `6a_sp500_to_ma200` and `55_market_concentration` published nulls. `19_sp500_breadth` was worse: NaN comparisons are always False, so all 50 sampled stocks fell into the `unchanged` branch and the dashboard rendered a **fabricated** "Weak bearish breadth — broad market weakness" from zero data. New `data_extractors/yf_safe.py` wraps `yf.Ticker` and trims trailing price-less bars at the fetch boundary; all 45 `yf.Ticker(` call sites across 9 extractor modules now go through it. Breadth additionally returns an error dict when no stock yields a valid comparison, and `ad_ratio` returns `None` instead of `float('inf')` (which `json.dumps` emits as invalid bare `Infinity`).
- **Fixed: Hyperliquid open interest was off by the coin price** — HL's `openInterest` is denominated in **base coin units** (unlike `dayNtlVlm`, which is already notional USD), but it was stored as `oi_usd` and rendered as `$X.XM`. BTC's 37,037 BTC of OI displayed as **$0.0M** instead of ~$2,917M. Now multiplied by mid price in both `hyperliquid_extractor.py` and `react_dashboard/backend/hl_ws_service.py`.
- **Fixed: 6 HIP-3 builder perps returned "not found on Hyperliquid"** — builder perps are absent from the unqualified `metaAndAssetCtxs` response and only appear when the request carries their `dex`. `get_hl_meta_and_contexts()` now also queries each builder dex referenced by `HL_PERPS`. Registry names corrected against the live per-dex universes: `xyz:SP500`/`xyz:NATGAS`/`xyz:COPPER` never existed (now `flx:USA500`/`flx:GAS`/`flx:COPPER`), and `BRENTOIL` was dropped (no builder lists it). `xyz:XYZ100` (Nasdaq 100) is genuinely live — $195M OI, $22.6M/day. The four `flx:*` listings are deployed but abandoned (zero OI, zero volume, mid ~8% from spot), so they now carry an `illiquid` flag and the React card labels them "inactive market" rather than presenting a stale quote as live.
- **Fixed: CBOE SKEW rendered N/A on all 3 dashboards despite valid data** — two writers owned cache key `5_spx_call_skew` with different shapes: `data_aggregator.py` → `get_spx_call_skew()` emitting `spx_call_skew`, and `fast_extract.py` (every 5 min, so it always won) → `get_cboe_skew_index()` emitting only `cboe_skew`. Streamlit, Dash and React all read `spx_call_skew`. `get_cboe_skew_index()` now emits the canonical `spx_call_skew` (plus `cboe_skew` as an alias) and the same `interpretation` block.
- **Fixed: JOLTS MoM delta never rendered** — extractor emitted absolute `change_mom` (thousands) while the dashboards read `change_mom_pct` and label it "% MoM". Added `change_mom_pct`.
- **Fixed: `_openbb_available()` gate + OpenBB providers on the VPS** — the VPS had **zero** OpenBB packages, so 6 indicators silently degraded. Installed `openbb`, `openbb-cboe`, `openbb-ecb` into a **separate** `venv-openbb` (see Scheduling). Also fixed a swallowed `TypeError`: `get_vix_futures_curve()` called `vars(r)` on pydantic models *before* `to_df()`, so the OpenBB path died even with the provider installed. The VIX curve now derives each expiry's forward via put-call parity (`K + (call − put)` at the strike where they are closest) — reading the ATM option's own bid/ask mid returned the ~0.07 option premium, not the ~15 futures level.
- **Fixed: ECB refi/marginal + France/Italy 10Y were structurally unobtainable** — `obb.fixedincome.rate.ecb` is served by FRED, not `openbb-ecb` (which only ships BalanceOfPayments/CurrencyReferenceRates/YieldCurve); it just maps names onto `ECBDFR`/`ECBMRRFR`/`ECBMLFR`, which the fallback now reads directly. The EU-yields fallback requested ECB SDW keys `...SV_C_YM.FR_10Y`/`IT_10Y` that do not exist in that dataset (it holds only the euro-area AAA curve), so FR/IT were always `None` and the IT-DE spread was never computable; replaced with FRED OECD per-country series (`IRLTLT01{DE,FR,IT,ES}M156N`), which are monthly but consistently dated, making the spread meaningful.
- **Fixed: equity screener claimed "requires openbb with Finviz provider" while Finviz worked** — `obb.equity.screener(provider="finviz")` returns ~85 rows with no `sma200` column, so the guard always fell through to a stub. Replaced with a real computation: one batched yfinance download over the shared `SP500_SAMPLE` gives % above 200-day MA (68.0% at time of fix).
- **Changed: OpenBB import is now lazy** — `data_extractors/__init__.py` imports `openbb_extractors`, so an eager `from openbb import obb` was paid by every script touching the package, including the 5-minute `hl_extract.py`/`fast_extract.py` jobs. Measured on the VPS-class box: eager import took that chain from **1.1 s / 140 MB to 6.4 s / 415 MB**. Deferred behind `_obb()` / `_openbb_available()`; only `scheduled_extract.py` now pays OpenBB's ~7 s / ~270 MB.
- **Changed: fallback notes no longer misdiagnose** — every "install openbb …" note now routes through `_degraded_note()`, which distinguishes "OpenBB not installed (<actual ImportError>)" from "provider unavailable — check `openbb-cboe` is installed and the provider responded".
- **Fixed (regression caught during this work): enabling OpenBB activated 3 untested tier-1 paths that were worse than their fallbacks** — `obb.economy.unemployment` and `obb.fixedincome.government.yield_curve` return rates as **decimal fractions** while every FRED fallback in the module returns percent, so Eurozone unemployment rendered `0.04%` and the full treasury curve collapsed to `0.038`. `obb.economy.cpi` returns only a headline series lagged ~16 months, replacing the 5-component FRED breakdown. The unemployment path also accepted a partial 3-of-4-country result, leaving Eurozone N/A. Added `_as_percent()`, required all four countries, and removed the CPI OpenBB tier outright. **Lesson: a long-serving fallback is a tested path; the tier above it may never have run.**
- **Known limitation (unchanged):** EU/JP/CN/UK manufacturing PMI still have no free source. EconDB carries no manufacturing PMI series (`obb.economy.pmi` no longer exists on the router), and Trading Economics now renders the value client-side, so its `"last":` JSON regex no longer matches. `81_global_pmi` keeps the US Industrial-Production proxy and an accurate note. The same TE change is why `43_ism_services` lost its `change_1d`/`interpretation` — it falls through to the table parser.

### 2026-05-27
- **Fixed: Hyperliquid funding annualization (8h → hourly convention)** — `hyperliquid_extractor.py` and `react_dashboard/backend/hl_ws_service.py` annualized funding with `* 3 * 365` (Binance 8h convention), but Hyperliquid funds **HOURLY** (verified: `fundingHistory` entries are spaced exactly 1.00h, and `metaAndAssetCtxs['funding']` is the per-hour rate). This understated displayed annualized funding for ALL HL perps by 8x. Corrected to `* 24 * 365`. Renamed the raw-period field `funding_rate_8h` → `funding_rate_1h` (it always held the hourly rate, not 8h) and updated the "8h:" caption → "1h:" across all 3 frontends (Streamlit, Dash, React). After the fix, e.g. BTC displays ~+11% ann instead of ~+1.4%. Downstream `Opportunity_scanner` strategy 02 is unaffected — it runs its own per-venue funding pipeline and already handles HL's hourly cadence. Note: `hl_extract.py` writes annualized `funding_rate` into `historical_data/*.csv` (`hl_*_funding` columns), so those CSVs show a one-time ~8x step-up at this date; pre-fix rows remain 8x understated (not backfilled).

### 2026-03-30
- **Extended: All yfinance indicators to 5y history** — Changed `period='2y'` / `timedelta(days=730)` to `period='5y'` across `yfinance_extractors.py`, `commodities_extractors.py`, and `fidenza_extractors.py`. Affects Russell 2000, S&P 500/MA200, ES/RTY futures, DXY, JPY, FX pairs, market concentration, sector ETFs, VIX term structure, commodities (gold/silver/crude/copper), Brent, Nikkei, EM indices, XAU/JPY, gold/silver ratio, credit ETFs. 68 CSVs now have 1,000+ rows (back to March 2021), up from 15 previously.
- **Fixed: extract_historical_data.py crash** — `extract_financial_agent_historical()` crashed with unhandled `ValueError` when `FRED_API_KEY` not set. Now catches gracefully and returns `None`.
- **Identified: 2 broken data sources** — Shiller CAPE stuck at Sep 2023 (Yale Excel file no longer updated), Global CPI stuck at Mar 2024 (FRED `CPALTT01USM657N` series discontinued).

### 2026-03-22
- **Added: Hyperliquid perpetual futures (indicators 84, 85)** — New `hyperliquid_extractor.py` fetches perp data (BTC, ETH, SOL, PAXG, HYPE, OIL) and HIP-3 spot stock tokens (TSLA, NVDA, AAPL, GOOGL, AMZN, META, MSFT, SPY, QQQ). OIL (`flx:OIL`) is a Felix-deployed WTI crude oil perp — price derived from 1m candle close since it's not in standard allMids.
- **Added: OHLCV candlestick charts** — All 4 dashboards now show multi-interval OHLCV candlestick charts for HL instruments AND yfinance instruments (DXY, FX pairs, commodities, VIX, MOVE, ES/RTY). React uses TradingView lightweight-charts; Dash/Streamlit use Plotly `go.Candlestick()`. Intervals: 1m–1D (HL) and 1H–1W (yfinance).
- **Added: Intraday OHLCV API endpoints** — `GET /api/intraday/{key}?interval=` (yfinance, 17 instruments) and `GET /api/hl/ohlcv/{coin}?interval=` (Hyperliquid, 6 perps) in React and Grafana backends.
- **Added: 1-minute Hyperliquid extraction** (`hl_extract.py`) — Standalone minutely script with partial cache merge (updates only keys 84/85 in shared JSON cache via atomic write). 45-second freshness guard. New `com.macro2.hl-extract.plist` launchd job.
- **Added: Real-time WebSocket relay (React)** — `hl_ws_service.py` connects to Hyperliquid WebSocket, relays ~1s price updates. OIL price fetched via REST (not in WS allMids). Toggle-controlled.
- **Added: Live toggle (Dash/Streamlit)** — 1-minute on-demand HL data refresh via toggle button (no background service).
- **Fixed: Candle timestamp normalization** — `get_hl_candles()` no longer calls `.normalize()` on timestamps (was collapsing intraday candles to midnight).
- **Fixed: Dash Tab5 metric_card 'sub' kwarg error** — Rewritten commodities section to use `indicator_with_chart()` pattern.

### 2026-03-17
- **Added: COT energy/copper positioning (indicator 83)** — Extended `cot_extractor.py` with CFTC SODA API as fast primary path for crude oil, Brent, copper, natural gas positioning. Falls back to `cot-reports` bulk download. Returns managed money long/short/net, producer net, swap positions, long ratio, and historical series.
- **Added: Dash dashboard COT display** — Tab 5 shows positioning metrics (OI, MM Long/Short/Net, Long Ratio, Producer Net) for all 4 energy/metals commodities, plus expandable historical long vs short chart.
- **Added: GMT+8 timezone display (Dash)** — All timestamps in the Dash dashboard now display in GMT+8 via `to_gmt8()` / `to_gmt8_date()` helpers.
- **Fixed: S&P 500 Multiples layout** — Added CSS `cols-6` grid rule for horizontal layout instead of vertical stacking.

### 2026-03-16
- **Added: Plotly Dash dashboard** (`dash_dashboard/`) — Full 8-tab dashboard with expandable historical charts, production deploy configs (gunicorn, systemd, nginx), AWS Lightsail deployment script. Fixed Tab 8 callback error (`color=` → `border_color=`), Global PMI key mismatch (`us_pmi` → `us_mfg_pmi`).
- **Added: Grafana dashboard** (`grafana_dashboard/`) — 111 panels with FastAPI API bridge, Docker + local mode support, Infinity datasource. Fixed `"format": 1` → `"format": "table"` and Docker hostname → localhost for local mode.
- **Added: React dashboard** (`react_dashboard/`) — Vite + React SPA with FastAPI backend, 8 tab panels, metric cards, history charts.
- **Fixed: S&P 500 Multiples N/A** — Added 3-tier cascade: OpenBB/Finviz per-stock market-cap weighted → multpl.com scrape → yfinance SPY. Now shows Forward P/E, Trailing P/E, PEG, P/S, P/B, P/Cash.
- **Fixed: ERP Forward N/A** — `get_equity_risk_premium()` now pulls `forward_pe` from OpenBB/Finviz multiples data (indicator 65) when available, instead of relying on yfinance SPY (which doesn't expose forward PE).
- **Fixed: Fama-French parser crash** — Empty line between monthly/annual sections caused `IndexError`. Added empty-string guard.
- **Fixed: Global PMI discontinued series** — FRED `NAPM` series discontinued. Replaced with `IPMAN` (Industrial Production: Manufacturing) with PMI-like scaling.
- **Updated: Architecture section** — Added 3 new dashboard frontends, updated indicator count to 85.

### 2026-03-15
- **Fixed: OOM kill on dashboard startup** — `debug=True` with Dash spawns a reloader subprocess that doubles memory usage. Added `use_reloader=False` to prevent the second process. Also fixes the "leaked semaphore objects" warning.
- **Added: Extraction progress tracking** — `data_aggregator.py` and `fast_extract.py` now write progress to `data_cache/.extract_progress.json` (current/total indicator, label, status). Dashboard polls this file every 3 seconds.
- **Added: Refresh status panel (top-right header)** — Shows live extraction progress bar with indicator name and count (e.g., "🔄 Refreshing 45/82 (gold)"). Detects stalled extractions (>2 min since last progress update) and displays a warning with "Apply Available Data" option.
- **Changed: Dashboard no longer auto-refreshes on new cache data** — Removed `refresh-interval` from `render_tab` inputs. When the cache file changes, a green confirmation banner appears ("📊 Fresh data is available") with "Apply Refreshed Data" / "Dismiss" buttons. Data is only swapped in when the user clicks Apply, preventing disruption during active use.

---

## Downstream consumer: Opportunity_scanner

[`Opportunity_scanner/`](../Opportunity_scanner/) consumes outputs of this repo as a **read-only downstream**, following the **parallel-pipeline contract** (see [`../Opportunity_scanner/CLAUDE.md`](../Opportunity_scanner/CLAUDE.md)):

- **No edits** are made to `data_aggregator.py`, the per-source extractors, the launchd timers, the dashboard frontends, or any cache file in this repo.
- **No schema mutations** to per-ticker `equity_financials/<TICKER>_quarterly.csv` files. The scanner sidesteps that risk entirely by writing its own sibling files (e.g. `consensus_history/<TICKER>.json` under the scanner's strategy folder).
- The scanner reads cache files this repo writes anyway, or runs its own scripts against the same upstream APIs (FRED, yfinance, EDGAR, CFTC) with independent rate-limit budgets.

### Cache files / outputs the scanner reads

| File / output | Consumed by |
|---|---|
| `data_cache/all_indicators.json` (yield curve, sector ETFs, HL perps, HIP-3, 13F, FX) | [strategy 02](../Opportunity_scanner/strategies/02_crypto_funding_carry/README.md), [strategy 03](../Opportunity_scanner/strategies/03_hip3_ibkr_basis/README.md), [strategy 05](../Opportunity_scanner/strategies/05_treasury_curve_cot/README.md), [strategy 09](../Opportunity_scanner/strategies/09_sector_rotation/README.md) |
| `historical_data/equity_financials/<TICKER>_quarterly.csv` (read-only — actuals only) | [strategy 01](../Opportunity_scanner/strategies/01_news_event_equity_overlay/README.md), [strategy 06](../Opportunity_scanner/strategies/06_earnings_drift/README.md) |

### Scanner's independent fetches that share upstream APIs with this repo

| Upstream API | Scanner script | Coordination |
|---|---|---|
| **yfinance** (sector ETF shares-out) | [strategy 09 — `fetch_shares_out.py`](../Opportunity_scanner/strategies/09_sector_rotation/README.md) | Daily, scanner-owned cadence; independent rate budget |
| **CFTC SODA** (treasury COT) | [strategy 05 — `fetch_cot_treasuries.py`](../Opportunity_scanner/strategies/05_treasury_curve_cot/README.md) | Weekly Tuesday post-release; free public API |
| **EDGAR XBRL** (consensus EPS history) | [strategy 06 — `fetch_consensus_eps.py`](../Opportunity_scanner/strategies/06_earnings_drift/README.md) | Polite backoff, ~10 req/sec EDGAR limit; scanner-side schema (does NOT mutate this repo's per-ticker JSONs) |

**No expected changes** to this repo from the scanner's side beyond doc-only updates to this section.
