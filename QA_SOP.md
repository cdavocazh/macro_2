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
| 2026-03-30 | `extract_historical_data.py` crashes on `extract_financial_agent_historical` | `get_all_financial_agent_series()` raises unhandled `ValueError` when `FRED_API_KEY` not set | Wrapped in try/except, return `None` gracefully | `extract_historical_data.py` |
| 2026-03-30 | Shiller CAPE stuck at Sep 2023 | Robert Shiller Yale Excel file (`ie_data.xls`) no longer updated since Oct 2023 | Source is dead — documented in Known-broken indicators | `shiller_extractor.py` |
| 2026-03-30 | Global CPI (US) stuck at Mar 2024 | FRED `CPALTT01USM657N` (OECD CPI YoY) series discontinued | Documented — needs switch to `CPIAUCSL` with manual YoY | `openbb_extractors.py` |
| 2026-03-17 | Natural gas COT filter wrong match | CFTC data lists Henry Hub NG as "NAT GAS NYME" not "NATURAL GAS"; also matched "HENRY HUB" code causing duplicates | Filter on `NAT GAS NYME` only (code `023651`) | `cot_extractor.py` |
