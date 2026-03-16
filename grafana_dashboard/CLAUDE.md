# CLAUDE.md — Grafana Macro Dashboard

## What is this?

Grafana-based frontend for the macro_2 project's 82+ macroeconomic indicators. Uses a FastAPI bridge (`api_bridge/main.py`) to translate the parent project's `data_aggregator` into Grafana-compatible JSON endpoints.

## Quick commands

```bash
# Start with Docker Compose
cd grafana_dashboard && ./start.sh

# Start API bridge locally (for development)
cd /path/to/macro_2
python -m uvicorn grafana_dashboard.api_bridge.main:app --port 8001 --reload

# Stop
cd grafana_dashboard && ./start.sh stop

# Test API
curl http://localhost:8001/api/status
curl http://localhost:8001/api/metrics/summary | python -m json.tool
```

## Architecture

- **API Bridge** (`api_bridge/main.py`): FastAPI app that imports `data_aggregator.get_aggregator()` from the parent project. Serializes pd.Series/DataFrame/numpy types to JSON. Exposes `/api/metrics/summary` (flat key-value), `/api/timeseries/{key}`, `/api/indicator/{key}`, and Grafana SimpleJSON endpoints.
- **Dashboard JSON** (`dashboards/macro_dashboard.json`): Pre-built Grafana dashboard with ~70 stat panels organized in 7 rows (tabs 1-5, 7-8). Uses Infinity data source plugin to query the API bridge.
- **Provisioning**: Auto-configures Infinity data source and dashboard on Grafana startup.

## Key design decisions

- **Stat panels over graphs**: Most macro indicators are point-in-time values, not time series. Stat panels with threshold coloring provide instant visual feedback.
- **Single `/api/metrics/summary` endpoint**: Flat dict of ~150 key-value pairs. All stat panels query this one endpoint, minimizing API calls. Grafana's refresh interval (1 min default) triggers one request that feeds all panels.
- **Tab 6 excluded**: Company financials require interactive ticker selection — not well-suited for Grafana's static panel model. Users should use Streamlit or React dashboard for Tab 6.
- **Docker Compose**: Grafana + API bridge as two containers. API bridge mounts the project root for access to `data_aggregator`, `data_extractors`, and `data_cache`.

## Adding a new panel

1. Add the metric to `_add()` calls in `get_metrics_summary()` in `api_bridge/main.py`
2. Add a panel object in `dashboards/macro_dashboard.json` with `root_selector: "$.your_key"`
3. Restart: `docker compose restart grafana`
