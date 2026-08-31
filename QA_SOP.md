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
