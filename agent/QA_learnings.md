# QA Learnings — Data Issue Fix Log

**Purpose:** Every time a data quality issue is fixed (broken extractor, stale source, wrong series, SLA misconfiguration), record the root cause and fix here. This prevents repeating the same investigations and documents the history of data reliability decisions.

**Rule:** When any extractor bug is fixed or a data source is replaced, add a row to this file AND update the "Known-broken indicators" section in the root `CLAUDE.md`.

---

## Format

Each entry should include:
- **Indicator key** and display name
- **Symptom** observed (what the QA agent or user reported)
- **Root cause** (what was actually broken)
- **Fix applied** (what changed in the code)
- **Date fixed** and verification result

---

## Fix Log

### 2026-04-15

#### `7_shiller_cape` — Shiller CAPE Ratio
- **Symptom:** QA agent reported 957 days stale (`latest_date: 2023-09-01`)
- **Root cause:** Robert Shiller's Yale Excel file (`ie_data.xls`) has not been updated since October 2023. The source URL at `econ.yale.edu/~shiller/data/ie_data.xls` still serves the old file.
- **Fix:** Rewrote `data_extractors/shiller_extractor.py` to scrape **multpl.com/shiller-pe/table/by-month** as primary source (live monthly data, BeautifulSoup table parse). Yale Excel kept as fallback with a "may be stale" label.
- **Verified:** `shiller_cape: 40.24` for `2026-04-14` on both local and VPS.
- **File changed:** `data_extractors/shiller_extractor.py`

---

#### `72_global_cpi` — Global CPI Comparison (US/EU/JP/UK)
- **Symptom:** QA agent reported 775 days stale (`latest_date: 2024-03-01`). EU value showing `129.49` (completely wrong — was returning index level as if it were a percent).
- **Root cause (multiple):**
  1. `CPALTT01USM657N` (FRED) — **discontinued March 2024**. Series metadata says "Percent Change from Year Ago" but FRED stopped updating it. Fix: switch US to `CPIAUCSL` (index) + compute `pct_change(12) * 100`.
  2. `CP0000EZ19M086NEST` (FRED) — returns **HICP index levels** (2015=100, values ~120-130), **not YoY%**. The code was calling `float(s.iloc[-1])` directly, returning the index level (129.49) instead of inflation. Fix: compute `pct_change(12) * 100`.
  3. `CPALTT01JPM657N` — **froze at June 2021** (OECD stopped submitting JP data to FRED). Fix: switched to `JPNCPIALLMINMEI` (also dead at Jun 2021 — FRED has no live JP CPI series).
  4. `CPALTT01GBM657N` — **froze at February 2024**. Fix: switched to `GBRCPIALLMINMEI` (available through March 2025, better than Feb 2024).
- **Status after fix:** US 3.32%, EU 1.94%, UK 3.42% (all from 2026-03-01). JP still shows stale -0.4% from 2021 — no live FRED series available for Japan CPI (all OECD MEI Japan series frozen at June 2021).
- **File changed:** `data_extractors/openbb_extractors.py` → `_global_cpi_fallback()`
- **Known limitation:** Japan CPI will remain stale until a non-FRED source (e.g., Bank of Japan API or OECD direct API) is wired in.

---

#### `67_oecd_cli` — OECD Composite Leading Indicator
- **Symptom:** QA agent reported 835 days stale (`latest_date: 2024-01-01`)
- **Root cause:** FRED series `USALOLITONOSTSAM` (OECD CLI for US) **froze at January 2024**. OECD stopped submitting this series to FRED when they migrated to a new SDMX data platform.
- **Fix:** Added direct OECD SDMX-JSON API call (`sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_CLI@DF_CLI,1.0/USA.M.LI.AA.AA.A`) with 45-second timeout as primary path. FRED fallback retained (still provides historical data even if stale).
- **Limitation:** VPS network could not reach `sdmx.oecd.org` at time of fix (ReadTimeout). If OECD API is blocked by the VPS provider, the indicator will continue showing Jan 2024 data. Monitor in future QA runs.
- **File changed:** `data_extractors/openbb_extractors.py` → `_oecd_cli_fallback()`

---

#### `78_intl_gdp` — International GDP Growth
- **Symptom:** QA agent reported 196 days stale (`latest_date: 2025-10-01` = Q4 2025)
- **Root cause (two issues):**
  1. **UK series dead:** `CLVMNACSCAB1GQUK` (UK GDP level) **froze at 2020-Q2**. Was returning null/None for UK. Fix: replaced with `NAEXKP01GBQ657S` (UK QoQ % change, updating through Q4 2025).
  2. **SLA too tight:** The quarterly SLA threshold (130 days) was too aggressive for international GDP which can naturally lag 5-6 months from quarter end to availability. Q4 2025 data ending October 2025 was genuinely the latest available in April 2026. Raised quarterly HIGH threshold from 130 → 200 days.
  3. **China GDP:** `RGDPNACNA666NRUG` (World Bank annual) froze at 2023. Replaced with `CHNGDPNQDSMEI` (China nominal quarterly GDP level → compute QoQ %). CHNGDPNQDSMEI currently available through 2023-Q2 — still lagged but not as severely.
- **File changed:** `data_extractors/openbb_extractors.py` → `get_international_gdp()`

---

#### SLA Configuration Mismatches
- **Symptom:** QA agent was applying wrong SLA tiers to several indicators, causing false positive HIGH alerts
- **Root cause:** Key names in `freshness_sla.py` didn't match actual cache keys used by `data_aggregator.py`
- **Fixes applied to `agent/shared/freshness_sla.py`:**
  1. `23_tga_balance` was incorrectly classified as `"daily"` (5d SLA). WTREGEN is **weekly** data. Changed to `"weekly"` (18d SLA).
  2. `69_oecd_cli` in SLA but actual cache key is `67_oecd_cli` — added `67_oecd_cli` alias.
  3. `74_intl_gdp` in SLA but actual cache key is `78_intl_gdp` — added `78_intl_gdp`.
  4. `62_sloos` had no entry (defaulted to "monthly" 75d). SLOOS is **quarterly** — added as `"quarterly"`.
  5. Quarterly SLA HIGH threshold: 130 → 200 days (international GDP, SLOOS release schedules can be 5-6 months from quarter end).
  6. Quarterly SLA LOW threshold: 110 → 150 days.

---

#### `67_oecd_cli` — OECD CLI: CFNAI proxy added (2026-04-15 follow-up)
- **Problem:** FRED `USALOLITONOSTSAM` frozen at Jan 2024. New OECD SDMX API (`sdmx.oecd.org`) returns 404/timeout from Hostinger VPS.
- **Root cause (two issues):**
  1. **FRED freeze**: OECD migrated from SDMX 2.0 to SDMX 3.0 (`sdmx.oecd.org`) in 2023–2024. FRED's data pipeline from OECD broke silently — the series didn't get officially discontinued, it just stopped receiving new observations.
  2. **OECD SDMX API unreachable from VPS**: The old URL (`DSD_CLI@DF_CLI,1.0`) now returns 404. The new URL (`OECD.SDD.STES,DSD_STES@DF_CLI`) requires 9 key dimensions (not 6). Even with corrected URL, Hostinger datacenter IPs are throttled by OECD's new API — connections establish but the server stops sending bytes before the 30-45s timeout, causing `ReadTimeout`. This is a datacenter IP rate-limiting pattern, not a firewall block.
  3. **Legacy redirect**: `stats.oecd.org/sdmx-json/data/MEI_CLI/...` redirects to `sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI/` — but the redirect URL drops the country/series filter, making it a dead end.
- **Fix:** Added CFNAI (Chicago Fed National Activity Index, `FRED:CFNAI`) as Tier 3 fallback.
  - CFNAI is updated monthly by the Chicago Fed, available on FRED through the current period (Feb 2026 at fix time).
  - Scale normalised: `cli_value = 100 + (cfnai_raw × 10)` to match OECD CLI-like units. Above 100 = above-trend growth (equivalent to CFNAI > 0).
  - `historical_raw` field preserves the native CFNAI series for downstream consumers.
  - Added staleness guard on FRED Tier 2: only use `USALOLITONOSTSAM` if < 400 days old; otherwise skip to CFNAI.
- **Result:** `67_oecd_cli` now shows `cli_value: 98.9, latest_date: 2026-02-01` (current), source: `FRED CFNAI (Chicago Fed — OECD CLI unavailable)`. HIGH alert resolved.
- **File changed:** `data_extractors/openbb_extractors.py` → `_oecd_cli_fallback()`
- **Note:** If OECD SDMX API becomes accessible from VPS (e.g., VPS IP whitelist changes, CDN route changes), Tier 1 will automatically take over — the staleness guard won't block it.

---

## Persistent Known Limitations

These issues were investigated but could NOT be fixed with available data sources:

| Indicator | Why it's hard to fix | Suggested path forward |
|-----------|---------------------|------------------------|
| `67_oecd_cli` | OECD SDMX API blocked on VPS (ReadTimeout) | Investigate if VPS firewall can be configured, or find a proxy/mirror |
| `jp_cpi_yoy` (in `72_global_cpi`) | All FRED Japan CPI series frozen at June 2021 | Wire in Bank of Japan API or OECD direct API |
| `cn_gdp_growth` (in `78_intl_gdp`) | China quarterly GDP on FRED last updated 2023-Q2 | Consider NBS China data or alternative provider |
| `51_housing_starts` | FRED HOUST series showing Jan 2026 despite Feb/Mar releases existing | FRED update lag for Census Bureau data — recheck in next cycle |
| forward P/E / forward EPS (`65_sp500_multiples`, `3_sp500_fundamentals`, forward ERP) | No free forward-estimate source is live: SPY's yfinance `info` has no forward fields, Finviz is dead, and `_sp500_multiples_fallback()` computes `forward_pe = 100 / multpl earnings yield` — multpl's earnings yield is *trailing*, so the "forward" P/E equals the trailing P/E (25.91 vs 25.92 on 2026-09-16) and the forward ERP is a trailing ERP | Label it trailing (or blank it) and find a real forward source (e.g. a FactSet/Yardeni weekly forward P/E) |

---

## Maintenance Checklist

When the QA agent reports HIGH stale indicators:
1. Check if the **FRED series is still active**: `fred.get_series(series_id).dropna().index[-1]`
2. Check if the **series is returning level data instead of %**: compare value to expected range
3. Check if the source **URL changed or redirects**: use `requests.get(url, allow_redirects=True).url`
4. Check if the **OECD API is accessible** from VPS: `curl -I https://sdmx.oecd.org/public/rest/data/...`
5. Check the **FRED series search** for replacement series: `fred.search('indicator_name country monthly 2025')`
6. After any fix, run `python3 scheduled_extract.py --force` on VPS to update cache
7. Re-run QA agent: `python3 -m agent.openai_agents.qa_agent --no-llm --no-telegram`

### 2026-08-30

#### `2_russell_2000`, `6a_sp500_to_ma200`, `55_market_concentration`, `19_sp500_breadth` — Market Indices tab
- **Symptom:** User reported N/A across the Market Indices tab. Breadth showed 0 advancing / 0 declining / 50 unchanged and printed "Weak bearish breadth — broad market weakness".
- **Root cause:** Yahoo served the 2026-08-28 daily bar with Open/High/Low/Close all `NaN` and only Volume populated — simultaneously for every US cash equity, ETF and index (`^GSPC`, `SPY`, `RSP`, `IWN`, `IWO`, `XLK`, `AAPL`, `MSFT`), while futures (`ES=F`, `GC=F`) and FX (`JPY=X`) were fine. Extractors took `.iloc[-1]` on the raw frame. In breadth, NaN comparisons are always False, so `NaN > prev` and `NaN < prev` both failed and every stock fell into the `else: unchanged` branch — turning missing data into a confident bearish signal.
- **Fix:** Added `data_extractors/yf_safe.py`, a `yf.Ticker` proxy whose `.history()` trims trailing rows with no price; routed all 45 `yf.Ticker(` sites across 9 modules through it. Breadth now returns an error dict when no stock yields a valid comparison, and `ad_ratio` returns `None` instead of `float('inf')`.
- **Verified:** Live on awehawk.cloud — breadth 14/36 (28%), Russell V/G 224.74/386.90 (0.5809), S&P/MA200 7730.99/7114.32 (1.0867), SPY/RSP 3.4821 (+0.96% 1d, +2.98% 30d).
- **Files changed:** `data_extractors/yf_safe.py` (new), `yfinance_extractors.py`, `web_scrapers.py`, `commodities_extractors.py`, `openbb_extractors.py`, `fred_extractors.py`, `fidenza_extractors.py`, `equity_financials_extractor.py`, `financial_agent_extractors.py`, `sec_extractor.py`
- **QA agent implication:** A null `latest` value and a *plausible but fabricated* reading look identical to a freshness check. Consider a check that flags any breadth/ratio indicator whose component counts are all-zero or whose denominator is zero.

#### `5_spx_call_skew` — CBOE SKEW
- **Symptom:** Rendered N/A on Streamlit, Dash and React simultaneously, while the cache held a valid 144.05.
- **Root cause:** Two writers owned the same cache key with different field names. `data_aggregator.py` wrote `spx_call_skew` via `get_spx_call_skew()`; `fast_extract.py` wrote `cboe_skew` via `get_cboe_skew_index()` and, running every 5 minutes, always won. All three frontends read `spx_call_skew`.
- **Fix:** `get_cboe_skew_index()` now emits the canonical `spx_call_skew` (plus `cboe_skew` as an alias) and the same `interpretation` block.
- **Verified:** CBOE SKEW 144.05 with interpretation rendering on awehawk.cloud.
- **Files changed:** `data_extractors/web_scrapers.py`
- **QA agent implication:** Worth a check that asserts every cache key written by more than one script has a stable field shape between runs.

#### `63_vix_futures_curve`, `64_spy_put_call_oi`, `70_iv_skew`, `66_ecb_rates`, `71_eu_yields`, `79_equity_screener` — OpenBB family
- **Symptom:** Six indicators degraded, all with notes reading "install openbb …". OpenBB *was* installed locally and the notes were misleading; on the VPS it genuinely was not installed at all (0 packages).
- **Root cause:** Four distinct causes hidden behind one note and a bare `except Exception: pass` — (1) missing provider extensions `openbb-cboe` / `openbb-ecb`; (2) `get_vix_futures_curve()` called `vars(r)` on pydantic models *before* `to_df()`, raising `TypeError` that killed the path even with the provider present; (3) upstream schema drift — the Finviz screener lost its `sma200` column; (4) `obb.fixedincome.rate.ecb` is served by FRED (not `openbb-ecb`) and the EU-yield SDW keys `...FR_10Y`/`IT_10Y` never existed in that dataset.
- **Fix:** Installed `openbb`/`openbb-cboe`/`openbb-ecb` into a dedicated VPS `venv-openbb`; fixed the `vars()` ordering; derived the VIX forward via put-call parity instead of reading the ATM option premium; read `ECBDFR`/`ECBMRRFR`/`ECBMLFR` directly from FRED; replaced the EU-yield source with FRED OECD per-country series; replaced the screener stub with a batched yfinance 200-day-MA computation. Notes now route through `_degraded_note()`, which reports the actual import error or names the missing provider.
- **Verified:** VIX curve contango +6.65% (13 expirations, OpenBB/CBOE); ECB 2.25/2.40/2.65; EU yields DE 2.97 / FR 3.68 / IT 3.734, IT-DE 0.764; 25d skew 4.21%; screener 68.0% above 200MA.
- **Files changed:** `data_extractors/openbb_extractors.py`, `data_extractors/web_scrapers.py`, `requirements-openbb.txt` (new)
- **QA agent implication:** A fallback note is evidence, not truth. When an indicator reports "install X", verify X's actual import status before acting on the note.

#### `84_hl_perps` — Hyperliquid perps
- **Symptom:** BTC open interest displayed "$0.0M" alongside $1,177M of 24h volume; 6 of 11 instruments returned "not found on Hyperliquid".
- **Root cause:** (1) HL's `openInterest` is denominated in base coin units while the sibling `dayNtlVlm` is notional USD; the code named it `oi_usd` and the UI divided by 1e6 as dollars. (2) HIP-3 builder perps are absent from the unqualified `metaAndAssetCtxs` response and only appear when the request carries their `dex`; several registry `api_coin` values (`xyz:SP500`, `xyz:NATGAS`, `xyz:COPPER`, `xyz:BRENTOIL`) never existed.
- **Fix:** Multiply OI by mid price in both the extractor and the WS relay; query each builder dex in `get_hl_meta_and_contexts()`; corrected names against the live per-dex universes and dropped `BRENTOIL`. Added an `illiquid` flag for builder listings with zero OI and zero volume.
- **Verified:** BTC OI $2,914.2M (matches API: 37,037 BTC × $78,768), funding 10.95% ann. / 1h 0.00125%, `xyz:XYZ100` live at $195.4M OI, four `flx:*` listings labelled "inactive market".
- **Files changed:** `data_extractors/hyperliquid_extractor.py`, `react_dashboard/backend/hl_ws_service.py`, `react_dashboard/frontend/src/tabs/Tab5Commodities.jsx`

### 2026-08-31

#### `65_sp500_multiples` — PEG Ratio and Price/Cash
- **Symptom:** Both rendered N/A on the Valuation Metrics card of all frontends.
- **Root cause:** The serving source (multpl.com) has neither metric, and the designed per-stock source (Finviz) is dead in both access paths — the OpenBB provider raises `EmptyDataError` and finviz.com's snapshot table no longer carries valuation ratios. The fallback hardcoded `None` for both.
- **Fix:** `_yf_peg_pcash_supplement()` fills the two gaps from yfinance Top-20 per-stock data: mcap-weighted `trailingPegRatio` (per-stock clamp (0,20)) and Σmcap/Σcash. During validation the first P/C read 5.48 because TSM's `totalCash` is reported in TWD (`financialCurrency`) against a USD `marketCap` — NT$3.5T was 57% of the cash denominator. ADR-style currency mismatches are excluded from the aggregate. ≥10/20 tickers required per metric, else omitted.
- **Verified:** Live on awehawk.cloud — PEG 1.79, Price/Cash 11.82, source captioned `multpl.com (index) + yfinance Top-20 (PEG, P/Cash)`.
- **Files changed:** `data_extractors/openbb_extractors.py`
- **QA agent implication:** any ratio built from two fields of one API payload needs a unit/currency check — sibling fields are not guaranteed to share denomination (HL `openInterest` vs `dayNtlVlm` was the same class of bug).

### 2026-09-16

Found by a feed-integrity scan from the CC trading pipeline (`Agent_Orchestration/CC/backfill/data_guard.py feeds`), after a malformed gold price reached a live trade idea ("AT_52W_HIGH 4357.6"). One-off data cleanup: `scripts/repair_feed_defects_20260916.py` (backups in `.deploy_backup_20260916/data/`).

#### `historical_data/*.csv` writer — `append_to_csv`
- **Symptom:** `gold.csv` (VPS) ended with `,2026-09-01,4357.6` — no timestamp, older than the rows above it.
- **Root cause:** Unlocked, non-atomic read-modify-write. `macro2-ibkr-stream` and `fast_extract` both rewrite `gold.csv` every 5 minutes; during the 2026-09-01 load spike their writes overlapped and interleaved bytes. The fragment's timestamp failed pandas' *inferred* format, became NaT, was written back blank, and `sort_values` parked it at the end of the file on every later write. The inferred format was a second trap: a file whose first row has no fractional seconds silently blanks any later row that has them.
- **Fix:** per-file `fcntl` lock, atomic temp-file + `os.replace`, `format='ISO8601'`, unparseable timestamps dropped with a warning. Daily writers pass `replace_daily_dates=True` so one bar re-fetched under a different timezone convention replaces the old copy instead of duplicating it; NaN observations are no longer written.
- **Verified:** 4 processes × 150 appends: old code kept 16/600 rows and produced a blank-timestamp row; new code keeps 600/600. The first collector write after deploy logged "gold.csv: dropped 1 row(s) with an unparseable timestamp".
- **QA agent implication:** check the *tail* of every CSV for blank or out-of-order timestamps — a corrupt row is sorted to the end, exactly where "latest value" readers look.

#### `75_treasury_curve`, `63_vix_futures_curve`, `70_iv_skew` — side effects of `venv-openbb`
- **Symptom:** Since 2026-08-30 the curve's `1M`..`30Y` columns were blank and the VIX / SKEW history CSVs froze on 2026-08-28.
- **Root cause:** Moving the full extraction to `venv-openbb` made the OpenBB branches succeed for the first time. They return a different shape from the fallbacks the CSV writers were built against: `month_N`/`year_N` maturity keys, and no `historical` series.
- **Fix:** `_canonical_maturity()`; `_with_fallback_fields()` attaches the fallback's history to the OpenBB result; the curve reports the Fed's observation date.
- **Verified:** curve dated 2026-09-14 with `1M`=3.94 … `30Y`=5.34; VIX history 1,383 rows through 2026-09-16; SKEW 616 rows through 2026-09-15.
- **QA agent implication:** when an environment change makes a primary path start working, diff its output shape against the fallback's — "more indicators resolve" can mean "the CSVs stop updating".

#### `jpy.csv` — mixed date conventions
- **Root cause:** yfinance FX daily bars are dated in London time; IBKR rows were dated in UTC, so the `date` column stepped backwards 23:00–24:00 UTC each summer night.
- **Fix:** IBKR forex rows use the London date (`ibkr_fast_extract._row_date`). Futures files needed nothing — their bars sit at New York midnight, where UTC agrees.

#### `aaii_sentiment` — Fidenza AAII scraper
- **Symptom:** 75.0 / 22.7 / 70.3 (168% total) since 2026-09-05; 66.7/33.3/0.0-style readings before; `bull_bear_ratio` blank Apr–Sep, so downstream readers carried the 2026-04-13 value for months.
- **Root cause:** "first `Bullish … N%` in raw HTML" matched the all-time-records table (Jan 6 2000 bullish 75.0%, Mar 5 2009 bearish 70.3%) and, in earlier layouts, the voting widget. No validation. Rows were dated by collection, not survey week.
- **Fix:** parse `.ssv2-gauge` (the labelled current-week block); require shares in 1–95 summing to 100±1.5; error on the bot page; `date` = survey week-ending. Every pre-fix row was removed — 29 of them passed the sum check but were voting-widget fractions (33.3/33.3/33.3, 25/50/25).
- **Backfill:** AAII's history spreadsheet (`/files/surveys/sentiment.xls`) served once, then the VPS IP got the Imperva "Pardon Our Interruption" page. Do not retry from scripts; a manually downloaded copy can backfill the weekly history.
- **QA agent implication:** a sum-to-100 check catches misparses but not every one — also compare against the site's own current-week block.

#### `sp500_fundamentals` — ETF fields that do not exist
- **Root cause:** yfinance `info` for SPY (an ETF) has trailing P/E and price but no forward P/E, trailing EPS or forward EPS.
- **Fix:** trailing EPS = price / trailing P/E. Forward fields deliberately left empty (see Persistent Known Limitations).
- **Not a defect:** `fed_funds_effective` flat at 3.63 since May is FRED `FEDFUNDS` (monthly average) with the Fed on hold — daily DFF 3.62–3.64 over the same period.

#### `adp_employment` — two FRED series in one file (2026-09-21)
- **Symptom:** scanner read the file as a weekly series 51 days stale; the monthly data was in fact current.
- **Root cause:** 82e651f switched the extractor from weekly ADPWNUSNERSA to monthly ADPMNUSNERSA without migrating the file; `append_to_csv` merged the two.
- **Fix:** monthly-only `adp_employment.csv` with a `series_id` on every row; weekly series in `adp_employment_weekly.csv` (FRED publishes it monthly, 6–11 weeks late). The writer asserts series id and date grid.
- **QA agent implication:** a collector whose source series changes must migrate or relabel its file. Label rows with the source id and have the writer assert it.

#### `earnings_calendar` — an unkeyed append log (2026-09-21)
- **Root cause:** `date` held the REPORT date and there was no timestamp, so `append_to_csv` skipped de-duplication.
- **Fix:** snapshot log `timestamp,date,symbol,report_date,source` keyed (as-of day, symbol).
- **QA agent implication:** `append_to_csv` silently skips de-duplication when the frame has no timestamp column — multi-row-per-day writers must pass `subset=`. A `date` column must mean the observation date; store event dates under their own name.

#### IBKR stream — a dead event-loop pump (2026-09-21)
- **Symptom:** a burst of ticks right after every (re)subscribe, then values frozen until the next ~30-min stale-reconnect; 84% of ES rows in US hours repeated the previous row.
- **Root cause:** `ib.sleep()` ran on a daemon thread; ib_async's `getLoop` gave that thread a fresh, socket-less event loop.
- **QA agent implication:** an asyncio / ib_async connection must be pumped by the thread that created it. And once a long-lived connection replaces periodic reconnects, anything the reconnect used to redo as a side effect (contract roll, re-subscribing after transient rejects) needs its own explicit mechanism.

#### Hyperliquid — dead and frozen columns nobody saw (2026-09-21)
- **Symptom:** 31 hl_perps columns blank for up to six months; 4 builder-perp columns frozen at one value for 5,626 rows.
- **Root cause:** a registry edit removed coins while the CSV header kept their columns; a later edit pointed builder perps at listings that no longer traded, and the writer ignored the extractor's own `illiquid` flag.
- **QA agent implication:** a blank column is only a symptom. Look for header columns no writer claims (orphans) and for columns frozen at one value, not just for old blank ones. Registries duplicated across files (a dry-run string, the dashboard relay) drift apart silently.

#### Column contracts (2026-09-21)
- Writers declare their columns with `declare_columns()` → `historical_data/.<stem>.columns.json`. When retiring a column, move it to the writer's RETIRED registry with `since` and `reason` rather than just deleting it from the registry — that is what stops the scanner reporting a deliberate blank as a broken feed, and what makes a column that silently stops (an orphan) visible on the first scan.
