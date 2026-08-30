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
