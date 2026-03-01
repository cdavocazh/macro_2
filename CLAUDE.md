# CLAUDE.md

## What is this project?

Macroeconomic indicators dashboard with large-cap equity financials. Fetches 28+ indicators from financial APIs (yfinance, FRED, SEC EDGAR, web scrapers, MOF Japan), displays them in a Streamlit dashboard with 6 tabs, caches locally for fast startup, and exports to CSV.

**Repo:** https://github.com/cdavocazh/macro_2
**Branch:** claude/explain-codebase-mk9u0ailcf2rvksp-7uAZO

## Quick commands

```bash
# Run the dashboard (loads from cache if available, otherwise fetches live)
streamlit run app.py

# Refresh data manually (updates cache + CSVs, skips if <1h old)
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard

# Extract all historical data to CSV (dual-source equity financials)
python extract_historical_data.py

# Install macOS launchd auto-scheduler
bash setup_launchd.sh
bash setup_launchd.sh --status
bash setup_launchd.sh --uninstall

# Run data review agent (requires MINIMAX_API_KEY)
python -m agent.openai_agents.agent "Scan all companies for missing data"
python -m agent.langchain_agents.agent "Compare Yahoo vs SEC for AAPL"
```

## Architecture

```
app.py                        Streamlit dashboard (6 tabs, read-only UI)
data_aggregator.py            Orchestrator — fetches all 28+ indicators, saves/loads cache
  ├── data_extractors/
  │   ├── yfinance_extractors.py       11 indicators (VIX, DXY, Russell, ES/RTY futures, JPY)
  │   ├── fred_extractors.py            8 indicators (GDP, 10Y yield, ISM PMI, TGA, liquidity, SOFR, 2Y yield)
  │   ├── web_scrapers.py               4 indicators (Forward P/E, Put/Call, SKEW, breadth)
  │   ├── shiller_extractor.py          1 indicator  (CAPE ratio from Yale Excel)
  │   ├── openbb_extractors.py          1 indicator  (S&P fundamentals, optional dep)
  │   ├── commodities_extractors.py     4 indicators (gold, silver, oil, copper)
  │   ├── cot_extractor.py              1 indicator  (CFTC COT positioning, gold & silver)
  │   ├── japan_yield_extractor.py      2 indicators (Japan 2Y yield, US-JP spread)
  │   ├── equity_financials_extractor.py  Top 20 company financials (Yahoo Finance)
  │   └── sec_extractor.py              Top 20 company financials (SEC EDGAR XBRL)
  └── utils/helpers.py               Cache serialization, CSV export, formatting

scheduled_extract.py          Standalone catch-up script (does NOT touch app.py)
extract_historical_data.py    Append-only historical CSV builder (dual-source equity)
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
| 2 | Market Indices | ES/RTY futures, breadth, Russell 2000 V/G, S&P 500/200MA |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, CBOE SKEW |
| 4 | Macro & Currency | DXY, USD/JPY, TGA, net liquidity, SOFR, US 2Y, Japan 2Y, spread, 10Y yield, ISM PMI |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, CFTC COT positioning |
| 6 | Large-cap Financials | Top 20 companies, dual-source (Yahoo + SEC EDGAR), quarterly statements |

## Dashboard features

- **Expandable 3M price charts**: Every indicator in tabs 1, 3, 4, 5 has a collapsible plotly chart with 1W/1M/3M zoom buttons
- **QoQ/YoY indicators**: Quarterly financial tables show colored percentage changes (green positive, red negative)
- **Numerator/denominator display**: Financial analysis and valuation metrics show formula components in small gray text
- **Multi-source switching**: Tab 6 supports Yahoo Finance and SEC EDGAR with radio button toggle
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
  │   ├── ... (20 tickers)
  │   └── _valuation_snapshot.csv
  └── sec_edgar/
      ├── AAPL_quarterly.csv
      ├── MSFT_quarterly.csv
      ├── ... (19 tickers, TSM excluded — IFRS)
      └── _valuation_snapshot.csv
```

## Top 20 tickers

```python
TOP_20_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'BRK-B', 'TSM',
                  'LLY', 'AVGO', 'JPM', 'V', 'WMT', 'MA', 'XOM', 'UNH', 'COST', 'HD', 'PG', 'JNJ']
```

## Key design decisions

- **Cache-first startup:** Dashboard loads from `data_cache/all_indicators.json` instantly. Only fetches live when cache is missing or user clicks Refresh.
- **Pandas serialization:** `helpers.py` has `_serialize_value()` / `_deserialize_value()` to handle `pd.Series`, `pd.DataFrame`, numpy types in JSON cache. These must stay in sync.
- **Freshness guard:** `scheduled_extract.py` skips if cache is <1 hour old. Prevents duplicate API calls.
- **Append-only CSVs:** `extract_historical_data.py` uses `append_to_csv()` which deduplicates by timestamp column. Never overwrites.
- **Graceful degradation:** Every extractor returns `{'error': msg}` on failure. Dashboard renders green cards for success, red for errors.
- **FY-end quarter derivation (SEC):** Q4 = Annual 10-K value minus (Q1+Q2+Q3). Searches across ALL XBRL concept alternatives to handle companies that switch concepts mid-year (e.g. GOOGL).
- **Cumulative YTD cash flow (SEC):** NVDA reports cumulative cash flows. `_get_cashflow_quarterly_values()` detects monotonic growth and subtracts prior quarters.
- **Cross-concept merging (SEC):** Revenue, net income can use different XBRL concepts per company. Merged from all alternatives; first non-None wins.
- **Dual-source equity storage:** Historical data saves per-company quarterly CSVs into `yahoo_finance/` and `sec_edgar/` subdirectories for cross-validation.
- **Singleton aggregator:** `get_aggregator()` returns a single global instance to prevent duplicate fetches within a Streamlit session.

## SEC EDGAR XBRL specifics

- **API:** `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json` (free, 10 req/sec, User-Agent required)
- **CIK mapping:** Hardcoded in `sec_extractor.py` for all 20 tickers
- **Valid forms:** 10-K, 10-Q, 20-F, 6-K
- **Duration detection:** Quarterly = 80-100 days, Annual = 340-380 days
- **TSM exception:** Files under `ifrs-full` namespace, not `us-gaap`. Returns error (known limitation).
- **Company-specific concepts:** JPM uses `RevenuesNetOfInterestExpense`, AVGO/MA use `ProfitLoss` for net income

## Scheduling (launchd)

**Plist:** `com.macro2.scheduled-extract.plist`
**Schedule:** 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8, Mon-Sat
**Python path:** `/Users/kriszhang/mambaforge/bin/python3`
**Logs:** `logs/launchd_stdout.log`, `logs/launchd_stderr.log`

launchd catches up missed runs after sleep (unlike cron). The freshness guard in `scheduled_extract.py` prevents redundant fetches.

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

**Change extraction schedule:**
1. Edit times in `com.macro2.scheduled-extract.plist`
2. Update the echo line in `setup_launchd.sh` to match
3. Run `bash setup_launchd.sh` to reload

## Deployment gotcha (Streamlit Cloud)

`requirements.txt` uses `pandas>=2.2.0` (not pinned). Pinning `pandas==2.1.4` breaks on Python 3.13 (compilation fails). All deps use `>=` minimum versions for this reason.

## Tech stack

- Python 3.10 (mambaforge), compatible with 3.8-3.13
- Streamlit, pandas, yfinance, fredapi, beautifulsoup4, plotly, requests
- SEC EDGAR XBRL API (no key needed)
- macOS launchd for scheduling
- Agent: openai-agents, langchain, langgraph, Minimax LLM API
