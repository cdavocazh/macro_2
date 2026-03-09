# CLAUDE.md

## What is this project?

Macroeconomic indicators dashboard with large-cap equity financials. Fetches 75+ indicators from financial APIs (yfinance, FRED, SEC EDGAR, Trading Economics, web scrapers, MOF Japan, AAII), displays them in a Streamlit dashboard with 8 tabs, caches locally for fast startup, and exports to CSV.

**Repo:** https://github.com/cdavocazh/macro_2
**Branch:** main

## Quick commands

```bash
# Run the dashboard (loads from cache if available, otherwise fetches live)
streamlit run app.py

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

# Fast extraction — real-time yfinance only (~5s, safe for 5-min polling)
python fast_extract.py                # run once
python fast_extract.py --dry-run      # list what would be extracted
python fast_extract.py --force        # ignore freshness guard

# Install macOS launchd auto-scheduler (both jobs)
bash setup_launchd.sh                 # install scheduled-extract + fast-extract
bash setup_launchd.sh --status        # check both jobs
bash setup_launchd.sh --uninstall     # remove both jobs

# Run data review agent (requires MINIMAX_API_KEY)
python -m agent.openai_agents.agent "Scan all companies for missing data"
python -m agent.langchain_agents.agent "Compare Yahoo vs SEC for AAPL"
```

## Architecture

```
app.py                        Streamlit dashboard (8 tabs, read-only UI)
data_aggregator.py            Orchestrator — fetches all 75+ indicators, saves/loads cache
  ├── data_extractors/
  │   ├── yfinance_extractors.py       14 indicators (VIX, DXY, Russell, ES/RTY futures, JPY, EUR/USD, GBP/USD, EUR/JPY, SPY/RSP)
  │   ├── fred_extractors.py           35 indicators (GDP, yields, ISM PMI, TGA, liquidity, SOFR, spreads, inflation, labor, M2, JOLTS, Sahm, SLOOS, ADP, WALCL, term premia, etc.)
  │   ├── web_scrapers.py               4 indicators (Forward P/E, Put/Call, SKEW, breadth)
  │   ├── shiller_extractor.py          1 indicator  (CAPE ratio from Yale Excel)
  │   ├── openbb_extractors.py          1 indicator  (S&P fundamentals, optional dep)
  │   ├── commodities_extractors.py     7 indicators (gold, silver, oil, copper, natural gas, Cu/Au ratio)
  │   ├── cot_extractor.py              1 indicator  (CFTC COT positioning, gold & silver)
  │   ├── japan_yield_extractor.py      2 indicators (Japan 2Y yield, US-JP spread)
  │   ├── global_yields_extractor.py    4 indicators (Germany/UK/China 10Y yields, ISM Services PMI)
  │   ├── yield_curve_extractor.py      1 indicator  (2s10s spread + regime classification)
  │   ├── equity_financials_extractor.py  Top 20 company financials (Yahoo Finance)
  │   ├── sec_extractor.py              Top 20 company financials (SEC EDGAR XBRL)
  │   ├── thirteenf_extractor.py       13F-HR institutional holdings (5 funds, QoQ changes)
  │   ├── fidenza_extractors.py       13 indicators (Brent, Nikkei, EM indices, SOFR/FF futures, XAU/JPY, Au/Ag ratio, AAII, OPEC, gold reserves)
  │   └── sp500_tickers.py             S&P 500 constituent list (Wikipedia + cache)
  └── utils/helpers.py               Cache serialization, CSV export, formatting

fast_extract.py               5-minute real-time yfinance extraction (20 extractors, ~5s)
scheduled_extract.py          Full catch-up script — FRED, SEC, web scrapers (does NOT touch app.py)
extract_historical_data.py    Append-only historical CSV builder (dual-source equity)
extract_sp500_financials.py   Batch extraction of S&P 500 financials (~30-40 min)
extract_13f_holdings.py       13F institutional fund holdings extraction (~25s)
monitor_earnings.py           Earnings date monitoring — flags stale companies (~45s)
review_data_freshness.py      Weekly SEC filing date comparison — flags stale data (~2 min)
config.py                     API keys, cache settings

agent/                        Financial data discrepancy review agent
  ├── shared/tools.py         8 shared validation tools
  ├── openai_agents/agent.py  OpenAI Agents SDK + Minimax LLM
  └── langchain_agents/agent.py  LangChain + LangGraph + Minimax LLM
```

## Dashboard tabs

| Tab | Name | Indicators |
|-----|------|------------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E & P/B, Shiller CAPE, Market Cap/GDP |
| 2 | Market Indices | ES/RTY futures, breadth, Russell 2000 V/G, S&P 500/200MA, SPY/RSP concentration |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, US 2Y, Japan 2Y, yield spread, 10Y yield, ISM PMI |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, CFTC COT positioning |
| 6 | Large-cap Financials | Top 20 dropdown + any-ticker text input, dual-source (Yahoo + SEC EDGAR), quarterly statements |
| 7 | Rates & Credit | Yield curve regime, 2s10s spread, global yields (US 5Y/10Y, DE/UK/CN 10Y), real yield, breakevens, HY/IG OAS, NFCI, Fed Funds, bank reserves, SLOOS, unemployment, claims (initial+continuing), headline/core CPI, PPI, core PCE |
| 8 | Economic Activity | Nonfarm Payrolls, JOLTS, Quits Rate, Sahm Rule, Consumer Sentiment, Retail Sales, ISM Services PMI, Industrial Production, Housing Starts |

## Dashboard features

- **Expandable 3M price charts**: Every indicator in tabs 1, 3, 4, 5 has a collapsible plotly chart with 1W/1M/3M zoom buttons
- **QoQ/YoY indicators**: Quarterly financial tables show colored percentage changes (green positive, red negative)
- **Numerator/denominator display**: Financial analysis and valuation metrics show formula components in small gray text
- **Multi-source switching**: Tab 6 supports Yahoo Finance and SEC EDGAR with radio button toggle
- **Custom ticker input**: Tab 6 has a text input alongside the Top 20 dropdown — type any ticker for on-demand fetching
- **Revenue segments**: SEC EDGAR source shows business segment breakdown from 10-K filings

## Data flow

```
scheduled_extract.py (or app.py Refresh button)
  → data_aggregator.fetch_all_indicators()
    → calls each extractor module
    → saves to data_cache/all_indicators.json  (JSON, 24h TTL)
    → appends to historical_data/*.csv         (append-only, deduplicated)
    → writes data_export/*.csv                 (latest snapshot)

app.py startup
  → tries load_from_local_cache() first       (instant, from JSON)
  → falls back to fetch_all_indicators()      (slow, ~40s)
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

## Top 20 tickers

```python
TOP_20_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'BRK-B', 'TSM',
                  'LLY', 'AVGO', 'JPM', 'V', 'WMT', 'MA', 'XOM', 'UNH', 'COST', 'HD', 'PG', 'JNJ']
```

## Key design decisions

- **Cache-first startup:** Dashboard loads from `data_cache/all_indicators.json` instantly. Only fetches live when cache is missing or user clicks Refresh.
- **Pandas serialization:** `helpers.py` has `_serialize_value()` / `_deserialize_value()` to handle `pd.Series`, `pd.DataFrame`, numpy types in JSON cache. These must stay in sync.
- **Freshness guard:** `scheduled_extract.py` skips if cache is <15 minutes old. Prevents duplicate API calls.
- **Append-only CSVs:** `extract_historical_data.py` uses `append_to_csv()` which deduplicates by timestamp column. Never overwrites.
- **Graceful degradation:** Every extractor returns `{'error': msg}` on failure. Dashboard renders green cards for success, red for errors.
- **FY-end quarter derivation (SEC):** Q4 = Annual 10-K value minus (Q1+Q2+Q3). Searches across ALL XBRL concept alternatives to handle companies that switch concepts mid-year (e.g. GOOGL).
- **Cumulative YTD cash flow (SEC):** NVDA reports cumulative cash flows. `_get_cashflow_quarterly_values()` detects monotonic growth and subtracts prior quarters.
- **Cross-concept merging (SEC):** Revenue, net income can use different XBRL concepts per company. Merged from all alternatives; first non-None wins.
- **Dual-source equity storage:** Historical data saves per-company quarterly CSVs into `yahoo_finance/` and `sec_edgar/` subdirectories for cross-validation.
- **Singleton aggregator:** `get_aggregator()` returns a single global instance to prevent duplicate fetches within a Streamlit session.
- **Network connectivity check:** `scheduled_extract.py` probes Yahoo/FRED/SEC hosts before starting extraction. Retries up to 6 times (10s apart, 60s max) to ride out VPN reconnections. Aborts cleanly if no network.
- **S&P 500 ticker list:** `sp500_tickers.py` scrapes Wikipedia and caches to `data_cache/sp500_tickers.json` (7-day TTL). Falls back to hardcoded list if Wikipedia is unreachable.
- **On-demand custom tickers:** Tab 6 text input fetches any ticker on-demand via `get_company_financials_yahoo()` and auto-saves to `historical_data/` via `save_single_company()`.
- **Earnings monitoring:** `monitor_earnings.py` uses lightweight `yfinance ticker.info` calls (~45s for 500 companies) to compare `mostRecentQuarter` against local CSVs. No full financial fetching.
- **SEC freshness review:** `review_data_freshness.py` uses the SEC submissions endpoint (~100KB per call, <200ms) via `get_latest_filing_dates()` to compare filing dates without downloading full companyfacts data.
- **13F holdings extraction:** `thirteenf_extractor.py` parses SEC 13F-HR XML infotables for 5 tracked institutional funds. Reuses `_rate_limit()` and `SEC_HEADERS` from `sec_extractor.py`. Handles 13F-HR/A amendments (prefers latest per quarter). Computes QoQ changes keyed by `(cusip, put_call)`. XML `<value>` field is in dollars (not thousands despite SEC form instructions).
- **Fidenza Macro gap-fill extractors:** `fidenza_extractors.py` adds 10 functions for instruments/indicators from the Fidenza Macro trading newsletter. Includes yfinance price series (Brent, Nikkei, EM indices, SOFR/Fed Funds futures), computed ratios (XAU/JPY, Gold/Silver), and web scrapes (AAII sentiment, OPEC production, gold reserves share). FRED additions (ADP, WALCL, term premia) live in `fred_extractors.py`. All 13 extraction wrappers are registered in `extract_historical_data.py`. SOFR futures use dynamic quarterly contract ticker generation (SR3{H/M/U/Z}{YY}.CME format). XAU/JPY and Gold/Silver ratio use `.tz_localize(None).normalize()` to handle cross-timezone yfinance index joins.

## SEC EDGAR XBRL specifics

- **API:** `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` (free, 10 req/sec, User-Agent required)
- **CIK mapping:** Dynamic download from SEC `company_tickers.json`, cached to disk (7-day TTL). Supports any US ticker.
- **Valid forms:** 10-K, 10-Q, 20-F, 6-K
- **Duration detection:** Quarterly = 80-100 days, Annual = 340-380 days
- **TSM exception:** Files under `ifrs-full` namespace, not `us-gaap`. Returns error (known limitation).
- **Company-specific concepts:** JPM uses `RevenuesNetOfInterestExpense`, AVGO/MA use `ProfitLoss` for net income

## Scheduling (launchd)

Two launchd jobs run at different frequencies:

| Job | Plist | Schedule | What it extracts | Timeout |
|-----|-------|----------|-----------------|---------|
| **fast-extract** | `com.macro2.fast-extract.plist` | Every 5 minutes (24/7) | Real-time yfinance only: futures, FX, commodities, indices, credit ETFs (20 extractors) | 4 min |
| **scheduled-extract** | `com.macro2.scheduled-extract.plist` | 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) | Full extraction: FRED, SEC, web scrapers, yfinance, all CSVs | 10 min |

**Python path:** `/Users/kriszhang/mambaforge/bin/python3`
**Logs:** `logs/launchd_stdout.log`, `logs/fast_extract_stdout.log`

launchd catches up missed runs after sleep (unlike cron). `fast_extract.py` has a 3-minute freshness guard to prevent overlap. `scheduled_extract.py` has a 15-minute freshness guard. The `TimeOut` in each plist auto-kills hung processes.

## API keys

- **FRED:** Hardcoded fallback in `config.py`, overridden by `FRED_API_KEY` env var or Streamlit secrets
- **SEC EDGAR:** No key needed (User-Agent header required, set in `sec_extractor.py`)
- **yfinance:** No key needed
- **Minimax (agent only):** `MINIMAX_API_KEY` env var required for agent subfolder
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
| S&P 500 Forward P/E | MacroMicro web scrape | 403 Forbidden (bot detection) | Uses SPY trailing P/E via `get_sp500_forward_pe_fallback()` |
| S&P 500 Put/Call Ratio | CBOE / ycharts scrape | Unreliable, often blocked | Falls back to FRED `PCERTOT` series or SPY options calc |
| TSM (SEC EDGAR) | SEC EDGAR XBRL | IFRS namespace, not us-gaap | Yahoo Finance only |
| OPEC Production | EIA API + Trading Economics | No EIA_API_KEY; TE page structure changed | Returns error dict gracefully |
| Gold Reserves Share | World Gold Council scrape | WGC URL returns 404 | Returns error dict gracefully |

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

**Never commit code changes without checking these docs for staleness.** When in doubt, update. Bump the version in STATUS.md for any non-trivial change.

## Deployment gotcha (Streamlit Cloud)

`requirements.txt` uses `pandas>=2.2.0` (not pinned). Pinning `pandas==2.1.4` breaks on Python 3.13 (compilation fails). All deps use `>=` minimum versions for this reason.

## Tech stack

- Python 3.10 (mambaforge), compatible with 3.8-3.13
- Streamlit, pandas, yfinance, fredapi, beautifulsoup4, plotly, requests
- SEC EDGAR XBRL API (no key needed)
- macOS launchd for scheduling
- Agent: openai-agents, langchain, langgraph, Minimax LLM API
