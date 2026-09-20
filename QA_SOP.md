# QA Standard Operating Procedure

Every code change — new feature, bug fix, or refactor — **MUST** pass through this checklist before being considered complete. This document captures lessons from real production bugs discovered in this codebase.

---

## 1. React `<details>` / Collapsible Chart Pattern

### The Bug (Encountered: 2026-03-22)

Using `useState` for initialization tracking inside a `useEffect` that also creates a chart causes the chart to be immediately destroyed. `setInitialized(true)` triggers a re-render, which fires the effect's cleanup function, removing the chart that was just created.

Additionally, omitting `open={isOpen}` on a controlled `<details>` element causes the browser's native open/close toggle to be overwritten by React's re-render, snapping the element shut.

### Correct Pattern

```jsx
// ✅ CORRECT: Use useRef for initialization (no re-render, no cleanup trigger)
const initializedRef = useRef(false);
const [isOpen, setIsOpen] = useState(false);

useEffect(() => {
  if (!isOpen || initializedRef.current) return;
  const rafId = requestAnimationFrame(() => {
    // ... create chart ...
    initializedRef.current = true;  // ref, not state
  });
  return () => cancelAnimationFrame(rafId);
}, [isOpen]);  // Only depend on isOpen

// ✅ CORRECT: Always pass open={isOpen} to keep React in sync with DOM
<details open={isOpen} onToggle={(e) => setIsOpen(e.target.open)}>
```

### Broken Pattern

```jsx
// ❌ BROKEN: useState triggers re-render → effect cleanup → chart destroyed
const [initialized, setInitialized] = useState(false);

useEffect(() => {
  if (!isOpen || initialized) return;
  requestAnimationFrame(() => {
    // ... create chart ...
    setInitialized(true);  // TRIGGERS RE-RENDER → CLEANUP → CHART GONE
  });
  return () => { chart.remove(); };
}, [isOpen, initialized]);  // initialized in deps = cleanup on change

// ❌ BROKEN: No open prop → React re-render resets DOM state
<details onToggle={handleToggle}>  // Missing open={isOpen}
```

### Checklist

- [ ] Any `<details>` element with React state tracking **MUST** have `open={stateVar}` prop
- [ ] Chart initialization flags **MUST** use `useRef`, never `useState`
- [ ] `useEffect` deps for chart creation **MUST NOT** include the initialization flag
- [ ] Chart cleanup belongs in a **separate** `useEffect(() => { return () => cleanup }, [])` (empty deps = unmount only)

### Files That Use This Pattern

| File | Status |
|------|--------|
| `HLCandlestickChart.jsx` | Uses `initializedRef` + `open={isOpen}` ✅ |
| `IntradayCandlestickChart.jsx` | Uses `initializedRef` + `open={isOpen}` ✅ |
| `PolymarketPriceChart.jsx` | Uncontrolled `<details>`, data fetch on toggle ✅ |
| `HistoryChart.jsx` | `open={open}` with `useState` (no chart library) ✅ |

---

## 2. Duplicate Timestamp Assertion (lightweight-charts)

### The Bug (Encountered: 2026-03-22)

TradingView's `lightweight-charts` throws `"Assertion failed: data must be asc ordered by time"` when two data points share the same Unix timestamp. This happens because:
- API returns duplicate timestamps at data boundaries
- Timezone offset addition can collapse distinct timestamps

### Correct Pattern

```javascript
// ✅ Always deduplicate + sort before passing to lightweight-charts
const seen = new Map();
for (const d of data) {
  const t = d.time + GMT8_OFFSET;
  seen.set(t, d);  // Map: last value wins per timestamp
}
const deduped = [...seen.entries()].sort((a, b) => a[0] - b[0]);
candleSeries.setData(deduped.map(([t, d]) => ({ time: t, open: d.open, ... })));
```

### Checklist

- [ ] **Every** call to `.setData()` on a lightweight-charts series **MUST** deduplicate by timestamp
- [ ] Data **MUST** be sorted ascending by time after deduplication
- [ ] Use `Map` for deduplication (naturally keeps last entry per key)
- [ ] Apply timezone offset **before** deduplication (the offset itself can create collisions)

---

## 3. API Response Validation

### The Bug Pattern

External APIs (Polymarket CLOB, Hyperliquid, yfinance) can return unexpected data shapes: empty arrays, missing fields, duplicate entries, or HTTP errors that don't raise exceptions.

### Checklist

- [ ] Check `data.length === 0` before processing API responses
- [ ] Wrap all API calls in try/catch
- [ ] Validate expected fields exist before accessing (`data.get('history', [])`)
- [ ] Handle both top-level errors (`{'error': msg}`) and partial failures (individual instruments failing)
- [ ] **Test with each valid interval/parameter** — don't assume all API parameters work (e.g., Polymarket CLOB rejects `1w` and `1m` intervals despite documentation)

---

## 4. Cache Merge (Partial Update) Safety

### The Bug Pattern

Multiple extraction scripts (`fast_extract.py`, `hl_extract.py`, `polymarket_extract.py`) independently merge data into `all_indicators.json`. Race conditions or crashes mid-write can corrupt the shared cache.

### Correct Pattern

```python
# ✅ Atomic write: temp file + os.replace (never partially-written cache)
fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix='.json')
try:
    with os.fdopen(fd, 'w') as f:
        json.dump(cache, f, default=str)
    os.replace(tmp_path, _CACHE_FILE)  # Atomic on same filesystem
except Exception:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    raise
```

### Checklist

- [ ] All cache writes **MUST** use atomic write (tempfile + `os.replace`)
- [ ] Read the existing cache, modify only the target key(s), write back the full cache
- [ ] Include `default=str` in `json.dump` to handle datetime/numpy types
- [ ] Freshness guard prevents overlapping runs

---

## 5. React Dashboard Build Verification

### Checklist (run after every frontend change)

```bash
# 1. Build check — catches import errors, missing deps, TypeScript issues
cd react_dashboard/frontend && npx vite build

# 2. Dev server check — catches runtime errors on page load
# Navigate to http://localhost:5173, open browser DevTools Console
# Look for: red errors, failed network requests, blank panels

# 3. Tab navigation — every tab must render without console errors
#    Click through all 9 tabs: Valuation → Indices → Volatility → Macro →
#    Commodities → Financials → Rates → Econ Activity → Polymarket

# 4. Expandable chart check — click at least one <details> expander per tab
#    Verify: chart renders (non-zero height), data loads, interval buttons work

# 5. Console must be clean — no red errors, no uncaught exceptions
#    Warnings are acceptable; errors are not
```

---

## 6. Dash Dashboard Verification

### Checklist (run after every dash_dashboard/ change)

```bash
# 1. Syntax check — catches import errors, indentation, missing functions
python -c "
import sys; sys.path.insert(0, 'dash_dashboard')
from app import app
print('Dash app loaded OK, tabs:', len(app.layout.children))
"

# 2. Tab render check — each build_tab*() must return without error
python -c "
import sys; sys.path.insert(0, '.')
sys.path.insert(0, 'dash_dashboard')
from data_loader import get_loader
loader = get_loader()
from app import build_tab1, build_tab2, build_tab3, build_tab4, build_tab5, build_tab7, build_tab8, build_tab9
for name, fn in [('tab1', build_tab1), ('tab2', build_tab2), ('tab3', build_tab3),
                 ('tab4', build_tab4), ('tab5', build_tab5), ('tab7', build_tab7),
                 ('tab8', build_tab8), ('tab9', build_tab9)]:
    try:
        result = fn(loader)
        print(f'{name}: OK')
    except Exception as e:
        print(f'{name}: FAILED — {e}')
"

# 3. Run dev server, click through all tabs, check for callback errors
python dash_dashboard/app.py
```

---

## 7. Data Extractor Verification

### Checklist (run after adding/modifying any extractor)

```bash
# 1. Direct function test — must return dict, not raise
python -c "from data_extractors.<module> import <function>; print(<function>())"

# 2. Error shape check — failed extractors must return {'error': msg}
# Never raise exceptions to the caller; always return error dict

# 3. Cache integration — key must appear in all_indicators.json after extraction
python <extraction_script>.py --force
python -c "import json; d=json.load(open('data_cache/all_indicators.json')); print('<key>' in d['data'])"

# 4. Serialization round-trip — data must survive JSON save/load
# pd.Series, pd.DataFrame, numpy types must be handled by _serialize_value()
```

---

## 8. Cross-Dashboard Consistency

When adding a new indicator or tab, **all 4 dashboards** read from the same cache. Verify:

- [ ] Cache key is populated by the extraction script
- [ ] Streamlit `app.py` displays the data (if applicable)
- [ ] Dash `dash_dashboard/app.py` displays the data
- [ ] React `react_dashboard/` displays the data
- [ ] Grafana `grafana_dashboard/` API bridge exposes the data (if applicable)

---

## 9. Scheduling / launchd Verification

### Checklist (run after changing any extraction script or schedule)

```bash
# 1. Dry run — must complete without errors
python <script>.py --dry-run

# 2. Force run — must extract data and update cache
python <script>.py --force

# 3. Freshness guard — second immediate run should skip
python <script>.py  # Should print "skipped (< Xs since last run)"

# 4. Network failure — must handle gracefully (no crash, no corrupt cache)
# Disconnect network, run script, verify clean error message

# 5. Plist template — must generate valid plist
bash setup_launchd.sh --status
```

---

## 10. Pre-Commit Quick Check (< 30 seconds)

Run this sequence before considering any change complete:

```bash
# Backend
python -c "from data_extractors.polymarket_extractor import get_polymarket_snapshot; print('extractor OK')"

# React build
cd react_dashboard/frontend && npx vite build 2>&1 | tail -3

# Dash import
cd ../.. && python -c "exec(open('dash_dashboard/app.py').read().split('if __name__')[0])" 2>&1 | tail -1 || echo "Dash app file has no syntax errors"
```

---

## Bug Log

| Date | Bug | Root Cause | Fix | Files Affected |
|------|-----|-----------|-----|---------------|
| 2026-03-22 | HL/Intraday OHLCV charts don't render when `<details>` expanded | `useState` for `initialized` triggers re-render → effect cleanup destroys chart; missing `open={isOpen}` prop causes React to reset DOM state | Changed `initialized` to `useRef`; added `open={isOpen}` to `<details>` | `HLCandlestickChart.jsx`, `IntradayCandlestickChart.jsx` |
| 2026-03-22 | Polymarket price chart: "data must be asc ordered by time" assertion | Duplicate timestamps in CLOB API response; lightweight-charts requires strictly ascending unique times | Switched to Plotly (handles duplicates); added Map-based dedup+sort | `PolymarketPriceChart.jsx` |
| 2026-03-22 | Polymarket CLOB API 400 error on `1w`/`1m` intervals | CLOB API only supports `1h`, `6h`, `1d`, `all` despite docs suggesting more | Removed `1w`/`1m` from interval options; validated on backend | `PolymarketPriceChart.jsx`, `react_dashboard/backend/main.py` |
| 2026-05-05 | QA flagged `12_ism_pmi` and `61_5y_yield` as cache errors; `repair_cache_errors.py` reported "healthy" because these keys were not in its REPAIRABLE list | REPAIRABLE dict in `scripts/repair_cache_errors.py` only listed FRED indicators with explicit extractor mappings; ISM PMI and 5Y Treasury yield extractors existed but were not registered for auto-repair | Added `get_ism_pmi` (line 235) and `get_5y_treasury_yield` (line 1187) of `fred_extractors.py` to the REPAIRABLE dict so `macro-cache-repair.timer` (every ~5 min) fixes them automatically next time | `scripts/repair_cache_errors.py` |
| 2026-05-27 | All Hyperliquid perps showed annualized funding 8x too low (e.g. BTC ~+1.4% instead of ~+11%) | Funding annualized with `* 3 * 365` (Binance 8h convention), but Hyperliquid funds HOURLY — `metaAndAssetCtxs['funding']` is the per-hour rate (verified: `fundingHistory` spacing = 1.00h). Also the raw-period field `funding_rate_8h` mislabeled the hourly rate as 8h | Changed annualization to `* 24 * 365`; renamed `funding_rate_8h` → `funding_rate_1h`; captions "8h:" → "1h:". To catch unit-convention bugs: when annualizing any periodic rate, verify the source's actual period (query its history endpoint and measure timestamp spacing) rather than assuming a venue convention | `data_extractors/hyperliquid_extractor.py`, `react_dashboard/backend/hl_ws_service.py`, `app.py`, `dash_dashboard/app.py`, `react_dashboard/frontend/src/tabs/Tab5Commodities.jsx` |
| 2026-08-30 | 4 Market Indices cards N/A; breadth showed a fabricated "Weak bearish breadth" from zero data | Yahoo served the 2026-08-28 daily bar with OHLC all `NaN` (Volume populated) for every US cash equity/ETF/index; extractors took `.iloc[-1]` on it. In breadth, NaN comparisons are always False, so all 50 stocks fell to the `else: unchanged` branch → 0% breadth → bearish interpretation | Added `data_extractors/yf_safe.py`, a `yf.Ticker` proxy that trims trailing price-less bars; routed all 45 `yf.Ticker(` sites through it. Breadth now errors when no valid comparison exists. **Never take `.iloc[-1]` on a raw upstream frame — a null-latest is indistinguishable from a real reading, and a defaulted `else` branch can turn missing data into a confident signal** | `data_extractors/yf_safe.py` (new) + 9 extractor modules |
| 2026-08-30 | Hyperliquid Open Interest showed "$0.0M" for BTC | HL's `openInterest` is in **base coin units**, unlike `dayNtlVlm` which is notional USD; it was stored as `oi_usd` and divided by 1e6 as dollars | Multiply by mid price before publishing. **When an API returns two size-like fields, confirm each one's denomination separately — sibling fields in the same payload need not share units** | `data_extractors/hyperliquid_extractor.py`, `react_dashboard/backend/hl_ws_service.py` |
| 2026-08-30 | CBOE SKEW rendered N/A on all 3 dashboards while the value (144.05) sat in the cache | Two writers owned cache key `5_spx_call_skew` with different field names — `data_aggregator.py` wrote `spx_call_skew`, `fast_extract.py` wrote `cboe_skew` and, running every 5 min, always won. All frontends read `spx_call_skew` | Made `get_cboe_skew_index()` emit the canonical `spx_call_skew` (+ `cboe_skew` alias). **Any cache key written by more than one script must have a single agreed field shape — add the key to a contract check, not just the writer** | `data_extractors/web_scrapers.py` |
| 2026-08-30 | 6 indicators silently degraded with the note "install openbb" while OpenBB was installed and working | `except Exception: pass` around every OpenBB call, plus a generic fallback note that assumed the only failure mode was a missing package. Real causes were: missing provider extensions (`openbb-cboe`, `openbb-ecb`), a swallowed `TypeError` from `vars()` on pydantic models, upstream schema drift (Finviz screener lost `sma200`), and a removed router endpoint (`obb.economy.pmi`) | Installed the providers; fixed the `vars()`-before-`to_df()` ordering; replaced notes with `_degraded_note()`, which reports the actual import error or names the missing provider. **A fallback note must state the observed failure, not a guessed cause — a wrong note sends the next investigation down the wrong path** | `data_extractors/openbb_extractors.py` |
| 2026-08-30 | Installing OpenBB on the VPS would have regressed the 5-min extract jobs and downgraded a production uvicorn | `data_extractors/__init__.py` eagerly imports `openbb_extractors`, so every script touching the package pays OpenBB's import (measured 1.1 s/140 MB → 6.4 s/415 MB). Separately, `openbb-core` hard-pins `uvicorn<0.41`, and `macro-react.service` runs on the shared venv's uvicorn 0.42.0 | Made the OpenBB import lazy behind `_obb()`; installed OpenBB into a dedicated `venv-openbb` used only by `macro-extract.service`. **Before adding a heavy dependency, measure its import cost against the job that runs most often, and dry-run the install to see what it would upgrade or downgrade under running services** | `data_extractors/openbb_extractors.py`, `requirements-openbb.txt` (new), VPS systemd drop-in |
| 2026-08-30 | Installing OpenBB on the VPS silently regressed 3 previously-healthy indicators | Enabling an optional dependency activated tier-1 code paths that had **never run in production**, so their bugs had never surfaced. `obb.economy.unemployment`/`fixedincome.government.yield_curve` return rates as decimal fractions (0.04) while every FRED fallback returns percent (4.1) → Eurozone unemployment rendered "0.04%" and the treasury curve collapsed to 0.038; `obb.economy.cpi` returns only a headline series lagged ~16 months, replacing a full 5-component FRED breakdown; the unemployment path also accepted a partial 3-of-4-country result | Added `_as_percent()` normalisation, required all four countries before accepting the OpenBB result, and dropped the CPI OpenBB tier entirely (the "fallback" is the better source). **After enabling any optional dependency, diff every indicator's output before vs after — a fallback that has been serving for months is a tested path, and the tier above it may not be** | `data_extractors/openbb_extractors.py` |
| 2026-08-31 | Top-20 Price/Cash aggregate read 5.48 — dominated 57% by a currency artifact | yfinance reports balance-sheet fields (`totalCash`) in `financialCurrency` but market data (`marketCap`) in the listing currency. For ADRs these differ: TSM's cash arrived as NT$3.5T against a USD market cap | Exclude tickers where `financialCurrency != currency` from any cross-field aggregate (P/C → 11.82). **When combining two fields of one API response into a ratio, verify they share a currency/unit — sibling fields need not (see also the HL openInterest row above)** | `data_extractors/openbb_extractors.py` |
| 2026-08-31 | Deploy-correctness + perf traps found while speeding up first load | (a) `index.html` had no `Cache-Control` → browsers heuristically cache it; after a `--delete` deploy, returning visitors' stale HTML references deleted content-hashed bundles → blank page. (b) nginx `add_header` in a location silently drops ALL inherited server-level headers (security headers vanished from the new locations). (c) `.bak` copies saved into `sites-enabled/` are parsed as live config ("conflicting server name" warnings) | `index.html` → `Cache-Control: no-cache`; hashed `/assets/` → `immutable` + `gzip_static`; security headers restated inside each location that sets any header; backups moved to `/root/nginx-backups/`. **Never back up a config into a directory the daemon globs, and re-check inherited headers after adding `add_header` anywhere** | nginx `dashboards` site config |
| 2026-09-01 | A resource figure recorded into STATUS.md was 30x wrong (hl-extract "6 MB" vs ~188 MB actual) | The measurement came from a run whose freshness guard short-circuited the work — the process exited before doing anything, so `MemoryPeak` reflected interpreter startup, not steady state. A single sample was taken and written up as the operating figure | Corrected to ~188 MB from four consecutive real runs. **Before recording any resource figure for a guarded job, confirm the run actually did work — `journalctl -u <unit> \| grep Consumed` and check CPU time (sub-second = guard skipped). Sample several consecutive runs, never one.** Applies to every `MemoryPeak` / timing figure in STATUS.md's production-state table | `STATUS.md` production-state table |
| 2026-09-09 | Macro catalyst calendar labelled the wrong releases for 9 of 10 event types; the calendar strip shipped the day before displayed them | `FRED_RELEASES` in `macro_calendar_extractor.py` carried release ids recalled from memory (11, 21, 50, 53, 175, 200, 197, 18, 51). None of them was the release named in the comment except CPI=10 — e.g. 11 is the Employment Cost Index and 50 is the real Employment Situation. FRED release ids have no pattern, and the wrong series still returned plausible-looking dates, so nothing failed loudly | Verified every id by name via `GET /fred/release?release_id=`; corrected map; dropped Consumer Sentiment (not a FRED release). **Any external id (FRED release/series, exchange symbol, API enum) must be verified by name against the provider before use — a wrong id that returns data is worse than one that errors.** Same class as the TradingView `COMEX:GC1!` and Finviz-provider lessons above | `data_extractors/macro_calendar_extractor.py` |
| 2026-09-16 | `gold.csv` ended with a row that had no timestamp (dated 2026-09-01, 4357.6); "last row = latest price" readers picked it up for two weeks and it reached a CC pipeline trade idea | `append_to_csv` did an unlocked, non-atomic read-modify-write while `macro2-ibkr-stream` and `fast_extract` both rewrite `gold.csv` every 5 min. Overlapping writes interleaved bytes, leaving a line fragment whose timestamp failed pandas' *inferred* format → NaT → written back blank → re-sorted to the end on every write. Reproduced: 4 processes × 150 appends kept 16/600 rows and produced a blank-timestamp row | Per-file `fcntl` lock (`.<file>.lock`) around the read-modify-write; atomic write (temp file + `os.replace`, mode preserved); explicit `format='ISO8601'` parsing (the inferred format also blanked legitimate microsecond timestamps); rows with unparseable timestamps are dropped with a warning. Same race now keeps 600/600 | `extract_historical_data.py` |
| 2026-09-16 | `full_treasury_curve.csv` 1M/3M/6M… blank since 2026-08-30 | The full extraction moved to `venv-openbb` (2026-08-30); OpenBB's `federal_reserve` provider names maturities `month_1`/`year_10`, so the curve landed in a second set of columns | `_canonical_maturity()` maps them to `1M`..`30Y`; `latest_date` is now the Fed observation date. Existing rows merged by `scripts/repair_feed_defects_20260916.py` (836 values, no conflicts) | `data_extractors/openbb_extractors.py` |
| 2026-09-16 | `vix_futures_curve.csv` and `spx_iv_skew.csv` stopped updating on 2026-08-28 | Both CSVs are written from `result['historical']`, which only the fallbacks return; once OpenBB became available the CBOE branches returned snapshots without it ("No historical data") | `_with_fallback_fields()` attaches the fallback's `historical` (and `skew_index`/`change_1d`) to the OpenBB results | `data_extractors/openbb_extractors.py` |
| 2026-09-16 | Same-date duplicate rows in `10y_treasury_yield.csv` (2,545), `us_2y_yield.csv` (1,180) and, after a backfill, `vix_futures_curve.csv` (1,254) | `append_to_csv` de-duplicates on the exact timestamp, so one daily bar written under two timezone conventions (FRED 00:00 vs a legacy 05:00/06:00 writer; older `^VIX` rows at New York midnight, 04:00/05:00 UTC, vs yfinance 1.2.0's Chicago midnight, 05:00/06:00) is kept twice | Daily writers pass `replace_daily_dates=True`: existing whole-hour bars on the dates being written are replaced (hours that recur across dates only, so a one-off IBKR snapshot on hh:00:00 is never touched). Historical duplicates collapsed by the repair script | `extract_historical_data.py` |
| 2026-09-16 | 720 blank-value rows in `10y_treasury_yield.csv` (and a few in 7 other series) | FRED returns NaN for holidays and the simple-series / batch FRED writers wrote them | `hist.dropna()` before writing in `_extract_simple_series` and the batch FRED writer | `extract_historical_data.py` |
| 2026-09-16 | `jpy.csv` dates stepped backwards between 23:00 and 24:00 UTC every summer night | yfinance dates FX daily bars in London time (JPY=X bar for D starts 23:00 UTC on D-1 in BST); IBKR rows were labelled with the UTC date | `macro2-ibkr-stream` labels forex rows with the London date (futures keep UTC, which already agrees with their New-York-midnight bars); 139 rows relabelled | `ibkr_fast_extract.py` |
| 2026-09-16 | AAII sentiment stored 75.0 / 22.7 / 70.3 (a 168% total) since 2026-09-05, and small-sample fractions (66.7/33.3/0.0, 33.3/33.3/33.3) before that | Unanchored regex: the first `Bullish … N%` in the raw HTML is the all-time-records table (Jan 6 2000 75.0%, Mar 5 2009 bearish 70.3%); earlier layouts hit the voting widget. No validation; `date` was the collection date | Parse the labelled `.ssv2-gauge` block; validate (each share 1–95, sum 100±1.5); return an error on the bot-protection page ("Pardon Our Interruption"); `date` = survey week-ending. All 670 pre-fix rows removed; current reading (week ending 2026-09-09: 38.0/22.7/39.3) added | `data_extractors/fidenza_extractors.py`, `extract_historical_data.py` |
| 2026-09-16 | `sp500_fundamentals.csv` `pe_ratio_forward`, `forward_earnings_yield`, `trailing_eps`, `forward_eps` never populated | Source is yfinance `info` for SPY, an ETF: Yahoo gives trailing P/E and price but no forward P/E or EPS | `trailing_eps = price / trailing P/E` (derived, same source; backfilled on 668 rows). Forward fields stay empty on purpose — see Known Limitations: the project's only "forward P/E" is a relabelled trailing P/E | `data_extractors/openbb_extractors.py` |
| 2026-09-21 | The IBKR streamer wrote stale prices into 7 per-instrument CSVs and the summary — ~6 rows in 7 were stale repeats, and `micro_2y_yield` wrote 4.182 for days | IB serves the last trade print indefinitely once a subscription goes quiet, and `last_update` is bumped by a tick of ANY field, so nothing recorded when the PRICE last moved | `StreamingQuote.last_price_time` is stamped only where `last` changes; both write paths skip an instrument whose price is older than 3 × `IBKR_CSV_INTERVAL` and log the skip. These files now show gaps during dead subscriptions — missing beats wrong | `data_extractors/ibkr_streaming.py`, `ibkr_fast_extract.py` |
| 2026-09-21 | `natural_gas_fred.csv` held two instruments in one file | The FRED extractor appended Henry Hub SPOT while the IBKR streamer appended NYMEX front-month FUTURES (separate columns, median 0.7% apart, range −6.5% to +9.0%) | NG routes to `natural_gas_ibkr.csv` (`natural_gas_futures`); `scripts/split_natural_gas_20260921.py` moved 26,812 futures rows out. `discover_relationships`' hint matched no column and only worked via a `numeric_cols[0]` fallback — pinned | `data_extractors/ibkr_streaming.py`, `discover_relationships.py` |
| 2026-09-21 | "Forward" P/E and forward ERP were trailing figures | `_sp500_multiples_fallback` computed `100 / multpl earnings yield`, but that yield is TRAILING, so forward_pe equalled trailing_pe (25.91 vs 25.92) and `get_equity_risk_premium` back-filled from it | Both leave the field empty — no free forward source exists. `web_scrapers` also returned a hardcoded 21.5 "long-term average" on failure, indistinguishable downstream from a live reading; it now returns an error | `data_extractors/openbb_extractors.py`, `data_extractors/web_scrapers.py` |
| 2026-09-21 | `_summary_latest.csv` has been DXY-only since its second write (686 rows) | The writer stamps all 12 indicator rows with one `datetime.now()` and `append_to_csv` de-duplicated on timestamp alone, so 11 of 12 were destroyed per write and the concat retro-collapsed prior runs | `append_to_csv` takes an explicit `subset`; the summary keys on `(timestamp, indicator_key)`. Existing history is not recoverable | `extract_historical_data.py` |
| 2026-09-21 | Hyperliquid spot stock columns blank since 2026-03-27; XRP blank since 03-19 | `spotMetaAndAssetCtxs` returns a filtered universe (328 of 868) beside the full ctxs array, so `ctxs[i]` bound each ticker to an unrelated market from @72 onward; XRP had been dropped from `HL_PERPS` while `hl_extract.py` still advertised it | Look contexts up by the pair name the API supplies, failing closed; XRP restored. The stock pairs have zero 24h volume and stale mids (spot TSLA 180.5 vs 363.8 as a perp), so their mids are now withheld and the columns stay legitimately blank | `data_extractors/hyperliquid_extractor.py`, `react_dashboard/backend/hl_ws_service.py` |
