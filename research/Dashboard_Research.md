# Dashboard Implementation Research

**Date:** March 30, 2026
**Context:** Evaluation of all 4 dashboard frontends in the macro_2 project to determine strengths, weaknesses, and best use case for each.

---

## Overview

The macro_2 project implements 4 independent dashboard frontends, all reading from the same data layer (`data_aggregator.py` -> `data_cache/all_indicators.json`). No frontend has its own data fetching logic. This document evaluates each implementation.

---

## 1. Streamlit (`app.py`) — ~2,612 lines

### Strengths
- **Fastest to develop and iterate** — single-file, declarative Python. No frontend build step, no callbacks to wire.
- **Rich interactivity out of the box** — `st.metric()`, `st.expander()`, `st.selectbox()`, `st.text_input()` with zero boilerplate.
- **Most feature-complete** — all 88 indicators displayed, custom ticker input with on-demand fetching, dual-source financials toggle, QoQ/YoY colored tables.
- **Compact layout** — custom CSS injection achieves ~40% more density than default Streamlit.
- **Zero-config deployment** — `streamlit run app.py` or push to Streamlit Cloud.
- **Auto-reload** — detects `scheduled_extract.py` cache updates via mtime check.

### Weaknesses
- **Fragile CSS** — relies on `[data-testid="stMetric"]` selectors that can break on Streamlit version upgrades. No stable public CSS API.
- **No production web server** — Streamlit's built-in Tornado server is not designed for multi-user concurrent access. No gunicorn, no workers.
- **Full page rerun model** — every interaction re-executes the entire script top-to-bottom. On complex tabs this adds latency.
- **Limited customization ceiling** — constrained to Streamlit's widget palette. Complex layouts (multi-column grids, nested collapsibles, custom hover interactions) require HTML injection hacks.
- **No API layer** — the dashboard IS the application. Can't separate data serving from rendering. No way for other tools to consume the same endpoints.
- **Session isolation** — each browser tab gets its own Python process. Memory scales linearly with users.

### Best Use Case
Rapid prototyping and local development. Test new indicator display logic in Streamlit first (5 minutes), then port to Dash (20 minutes).

---

## 2. Plotly Dash (`dash_dashboard/`) — ~3,300+ lines

### Strengths
- **Production-ready deployment** — full gunicorn + systemd + nginx stack with deploy script. Rate limiting, static asset caching, security headers, log rotation all pre-configured.
- **Callback architecture** — fine-grained reactivity. Only affected components re-render, not the entire page. Better UX for Tab 6 ticker switching.
- **Non-disruptive refresh** — "Fresh data available" banner with explicit "Apply" button. User isn't interrupted mid-analysis by auto-reload.
- **Proper CSS** — dedicated `assets/style.css` with CSS Grid (`cols-2` through `cols-6`), responsive breakpoints at 768px. No test-ID hacking.
- **Shared Flask server** — can extend with custom REST endpoints. The WSGI interface means standard Python web tooling (reverse proxy, load balancing, monitoring) all works.
- **Expandable charts** — native HTML5 `<details>/<summary>` for collapsible sections. No JavaScript, no framework dependency.
- **GMT+8 timezone support** — `to_gmt8()` / `to_gmt8_date()` helpers applied consistently across all tabs.

### Weaknesses
- **Callback complexity** — 5 callbacks with `allow_duplicate=True` and `prevent_initial_call=True` flags. Adding new interactive features requires careful state management to avoid circular dependencies.
- **Steeper learning curve** — Dash's `html.Div(children=[...])` nesting is more verbose than Streamlit's `st.metric()`. Tab builders are 200-300 lines each.
- **No hot-reload in production** — `use_reloader=False` required to prevent OOM (fixed, but means dev experience is slightly worse).
- **Higher code surface** — ~30% more code than Streamlit for equivalent features because layout is explicit (no implicit column management).

### Best Use Case
Primary production dashboard. Best balance of features, deployment readiness, and maintainability for a personal/small-team macro monitoring dashboard.

---

## 3. Grafana (`grafana_dashboard/`) — ~6,181 lines (mostly JSON)

### Architecture
- FastAPI bridge (`api_bridge/main.py`, 600 lines) translates `data_aggregator` -> Grafana JSON
- 103 stat panels with threshold-based coloring (green/yellow/red)
- 7 row groups covering tabs 1-5, 7-8 (Tab 6 Financials omitted)
- Infinity datasource plugin for JSON API queries
- Docker Compose or local Homebrew deployment
- Single workhorse endpoint: `/api/metrics/summary` returns ~150 flat key-value pairs

### Strengths
- **Purpose-built for monitoring** — 103 stat panels with threshold-based coloring. At a glance you see which indicators are in danger zones.
- **Multi-user ready** — Grafana handles authentication, roles, org separation natively. Multiple users can view simultaneously without extra memory.
- **Alerting infrastructure** — thresholds are visual-only right now, but Grafana can wire them to Slack, PagerDuty, email with minimal config. No other dashboard offers this.
- **Auto-refresh** — native 1-minute poll interval, no custom polling code needed.
- **Minimal custom code** — only 600 lines of Python (FastAPI bridge). The heavy lifting is Grafana's UI engine and the Infinity plugin.
- **Docker deployment** — `docker-compose up` gives you a complete stack. Zero Python environment management.
- **Extensible by non-developers** — anyone familiar with Grafana can add panels, change layouts, create new dashboards without touching code.

### Weaknesses
- **No interactivity** — no custom ticker input, no source toggle, no on-demand fetching. It's read-only monitoring. Grafana panels query a datasource and render results — there's no mechanism for a panel to say "user typed AAPL, now call this API and render a table."
- **Tab 6 (Financials) omitted entirely** — Grafana stat panels can't render quarterly income statements with QoQ changes. No table panels wired.
- **No historical charts** — 0 time-series graph panels despite the `/api/timeseries/{key}` endpoint existing. All 103 panels show point-in-time values only.
- **No COT positioning charts** — energy/copper COT is stat values only, no long vs short overlay.
- **4,896 lines of dashboard JSON** — hand-editing panel configurations is painful. Any layout changes require either the Grafana UI or JSON surgery.
- **External dependency** — requires Grafana installation (Docker or Homebrew) plus the Infinity datasource plugin. Heavier infrastructure than the other three.

### Why Grafana Has No Interactivity
Grafana was built as an observability platform. Panel types are rigid: a stat panel shows a number, a time-series panel shows a line chart. You can't conditionally render a table with QoQ color-coded percentages. Template variables (dropdowns at dashboard top) are limited to predefined lists. Free-text ticker input with on-demand API fetching isn't a natural Grafana pattern. Grafana excels when "what should this panel show?" is fixed at design time.

### Why Grafana Is Good for Alerting
Grafana was born from the Graphite/InfluxDB/Prometheus monitoring ecosystem. Alerting is first-class:
- **Alert rules engine** — define conditions like "if VIX > 30 for 5 minutes" and Grafana evaluates continuously.
- **Contact points** — native integrations with Slack, PagerDuty, email, Discord, Telegram, webhooks.
- **Silence/mute windows** — suppress alerts during weekends or market closures.
- **Alert history** — logs when alerts fired, resolved, and who acknowledged them.
- **Threshold promotion** — the 103 existing stat panel thresholds can be promoted to alert rules trivially.

### Best Use Case
Secondary "wall monitor" for passive monitoring with potential alerting. Best for a second screen showing red/yellow/green status across all indicators. Not suitable as the primary interactive dashboard.

---

## 4. React + Vite (`react_dashboard/`) — ~3,296 lines

### Strengths
- **Modern SPA architecture** — component-based with clear separation (5 reusable components, 8 tab components). Most maintainable long-term if the team knows React.
- **Fastest rendering** — client-side React with virtual DOM. Tab switching is instant (no server roundtrip). Plotly charts render in the browser.
- **Best extensibility ceiling** — can add any UI pattern: drag-and-drop dashboards, real-time WebSocket updates, multi-ticker comparison, date range pickers, saved views.
- **Proper API separation** — FastAPI backend with 6 endpoints. Frontend and backend can be deployed independently. Other tools can consume the same API.
- **Clean responsive design** — CSS Grid with breakpoints at 900px and 600px. Works on mobile out of the box.
- **Build-ready** — `npm run build` produces static assets servable by any CDN/nginx. No Python needed for the frontend in production.

### Weaknesses
- **Least feature-complete** — missing sector ETFs, Brent crude, OHLCV candlestick charts for many indicators, CSV export. No expandable price charts for individual indicators. Roughly 40% of the indicator display logic in Streamlit/Dash hasn't been ported yet.
- **No production deploy configs** — no systemd services, no nginx config, no Docker setup.
- **Requires Node.js** — adds a build toolchain dependency the other dashboards don't have.
- **No refresh UX** — polls every 60 seconds silently. No progress indicator, no "fresh data available" banner, no stall detection.
- **Tab 6 re-fetches on each change** — no session state equivalent, so switching tickers re-calls the API.
- **Two-process startup** — needs both `uvicorn` (backend) and `npm run dev` (frontend) running.

### Why React Is the Most Feature-Incomplete
This is not a React limitation — it's that less development time was invested. The React frontend has the skeleton (8 tabs, metric cards, basic charts) but the indicator display logic that exists in Streamlit and Dash hasn't been fully ported. It's a younger codebase.

### Best Use Case
Worth investing in only if the project evolves toward a multi-user SaaS product with custom dashboards, saved views, and collaboration features. Its extensibility ceiling is the highest of all four options.

---

## Charting Capabilities Comparison

All four dashboards use the same underlying charting library (Plotly), so **charting capability is identical** across Streamlit, Dash, and React:

```python
# Identical Plotly code works in all three
fig = go.Figure()
fig.add_trace(go.Scatter(x=dates, y=vix, name="VIX", line=dict(color="red")))
fig.add_trace(go.Scatter(x=dates, y=move, name="MOVE", yaxis="y2", line=dict(color="blue")))
fig.update_layout(yaxis2=dict(overlaying="y", side="right"))
```

For custom multi-series overlay charts (2+ series superimposed with dual y-axes), Dash is equally capable as React and already has all 88 indicators wired up. Adding a new overlay chart in Dash is 15 lines of Python. In React it's 15 lines of JSX — same effort, same result.

React genuinely wins when you want interactivity *around* the chart that goes beyond Plotly:
- Checkbox lists to toggle series visibility (React state management is natural)
- Drag-and-drop chart layer reordering
- Linking charts so zooming one auto-zooms another
- Saving chart configurations to localStorage or a backend
- Real-time WebSocket streaming updates

But for "superimpose 2 series with a dual y-axis," Dash is equally capable and has the most complete implementation.

---

## Summary Matrix

| Criteria | Streamlit | Dash | Grafana | React |
|----------|-----------|------|---------|-------|
| **Feature completeness** | 5/5 | 4.5/5 | 2.5/5 | 3/5 |
| **Production readiness** | 2/5 | 5/5 | 4/5 | 2.5/5 |
| **Development speed** | 5/5 | 3/5 | 2/5 | 3/5 |
| **Multi-user scaling** | 2/5 | 4/5 | 5/5 | 4/5 |
| **Monitoring/alerting** | 1/5 | 1/5 | 5/5 | 1/5 |
| **Interactivity** | 4/5 | 4/5 | 1/5 | 5/5 (potential) |
| **Maintainability** | 3/5 | 3.5/5 | 2/5 | 4.5/5 |
| **Infrastructure overhead** | 5/5 | 3/5 | 2/5 | 3/5 |
| **Lines of code** | 2,612 | 3,300 | 6,181 | 3,296 |

---

## Recommendation

**For a personal/small-team macroeconomic monitoring dashboard:**

1. **Primary dashboard: Plotly Dash** — best balance of features, production readiness, and deployment maturity. Already has gunicorn/systemd/nginx stack, GMT+8 timestamps, non-disruptive refresh, and all 88 indicators.

2. **Prototyping: Streamlit** — keep for rapid iteration when adding new indicators. Test display logic in Streamlit first (5 minutes), then port to Dash (20 minutes).

3. **Passive monitoring: Grafana** — use alongside Dash as a "wall monitor" if you want a second screen showing red/yellow/green status with future alerting capability.

4. **Future product: React** — worth investing in only if the project evolves toward a multi-user SaaS product with custom dashboards, saved views, collaboration features, and advanced interactive charting.
