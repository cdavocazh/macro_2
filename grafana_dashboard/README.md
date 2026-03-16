# Grafana Macro Dashboard

Grafana-based version of the Macroeconomic Indicators Dashboard, displaying 82+ indicators across 8 categories with auto-refresh, threshold-based coloring, and professional visualization.

## Architecture

```
grafana_dashboard/
├── api_bridge/
│   ├── main.py              FastAPI server bridging data_aggregator → JSON API
│   ├── requirements.txt     Python dependencies
│   └── __init__.py
├── dashboards/
│   └── macro_dashboard.json  Pre-built Grafana dashboard (auto-provisioned)
├── provisioning/
│   ├── dashboards/
│   │   └── dashboard_provider.yaml
│   └── datasources/
│       └── macro_api.yaml
├── docker-compose.yml        Docker Compose for Grafana + API Bridge
├── Dockerfile.api            API Bridge Docker image
├── start.sh                  Convenience startup script
├── README.md                 This file
├── STATUS.md                 Version and feature status
└── CLAUDE.md                 AI assistant context
```

## Quick Start

### Option 1: Docker Compose (Recommended)

```bash
cd grafana_dashboard
./start.sh            # Start both services
# or: docker compose up -d --build
```

Then open **http://localhost:3000** (credentials: `admin` / `macro2024`).

The dashboard auto-provisions on first start — no manual import needed.

### Option 2: Local via Homebrew (macOS, no Docker)

```bash
cd grafana_dashboard
./start.sh local
```

This will:
1. Install Grafana via Homebrew (if not already installed)
2. Install the Infinity plugin
3. Set up provisioning (datasource + dashboard auto-load)
4. Start the API bridge on `:8001`
5. Start Grafana on `:3000`

Then open **http://localhost:3000** (default credentials: `admin` / `admin`).

**Manual setup (if `start.sh local` has path issues):**

```bash
# 1. Install Grafana + plugin
brew install grafana
grafana cli --homepath $(brew --prefix grafana)/share/grafana \
  --pluginsDir /opt/homebrew/var/lib/grafana/plugins \
  plugins install yesoreyeram-infinity-datasource

# 2. Create datasource provisioning
PROV_DIR="$(find /opt/homebrew/Cellar/grafana -path '*/conf/provisioning' -type d | head -1)"
cat > "$PROV_DIR/datasources/macro_api.yaml" <<'YAML'
apiVersion: 1
datasources:
  - name: MacroAPI
    type: yesoreyeram-infinity-datasource
    access: proxy
    url: http://localhost:8001
    isDefault: true
    editable: true
    jsonData:
      url: http://localhost:8001
    version: 1
YAML

# 3. Create dashboard provider
cat > "$PROV_DIR/dashboards/macro_dashboard.yaml" <<YAML
apiVersion: 1
providers:
  - name: "Macro Dashboard"
    orgId: 1
    type: file
    options:
      path: $(pwd)/dashboards
YAML

# 4. Start API bridge
cd /path/to/macro_2
python -m uvicorn grafana_dashboard.api_bridge.main:app --host 0.0.0.0 --port 8001 &

# 5. Start Grafana
brew services start grafana
# Open http://localhost:3000
```

**Stop everything:**

```bash
./start.sh stop
# or manually:
brew services stop grafana
lsof -ti:8001 | xargs kill
```

### Option 3: Local Development (manual, any OS)

```bash
# Terminal 1: Start API Bridge
cd /path/to/macro_2
pip install fastapi uvicorn
python -m uvicorn grafana_dashboard.api_bridge.main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 2: Start Grafana (via Docker)
docker run -d -p 3000:3000 \
  -e GF_INSTALL_PLUGINS=yesoreyeram-infinity-datasource \
  -e GF_SECURITY_ADMIN_PASSWORD=macro2024 \
  -v $(pwd)/grafana_dashboard/provisioning:/etc/grafana/provisioning \
  -v $(pwd)/grafana_dashboard/dashboards:/var/lib/grafana/dashboards \
  grafana/grafana:11.4.0
```

### Option 4: Existing Grafana Instance

1. Install the **Infinity** plugin: `grafana cli plugins install yesoreyeram-infinity-datasource`
2. Add a JSON data source pointing to `http://localhost:8001`
3. Import `dashboards/macro_dashboard.json` via Grafana UI

## Data Flow

```
data_aggregator.py (cached JSON)
  ↓
API Bridge (FastAPI, port 8001)
  ├── /api/metrics/summary    → flat key-value metrics for stat panels
  ├── /api/timeseries/{key}   → historical data for graph panels
  ├── /api/indicator/{key}    → full indicator data
  ├── /api/group/{group}      → grouped indicators by tab
  └── /api/status             → dashboard status
  ↓
Grafana (port 3000)
  └── Infinity data source → JSON queries → panels
```

## Dashboard Sections

| Row | Category | Indicators |
|-----|----------|------------|
| 1 | Valuation Metrics | Forward P/E, Trailing P/E, P/B, Shiller CAPE, Market Cap/GDP, PEG, ERP, Sector P/E |
| 2 | Market Indices | ES/RTY futures, breadth, S&P/MA200, SPY/RSP concentration, Fama-French 5 factors |
| 3 | Volatility & Risk | VIX, MOVE, VIX/MOVE ratio, Put/Call, SKEW, VIX contango, SPY P/C OI |
| 4 | Macro & Currency | DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, yields, ISM, money supply |
| 5 | Commodities | Gold, Silver, Crude Oil, Copper, Natural Gas, Cu/Au ratio, Brent |
| 7 | Rates & Credit | 2s10s spread, global yields (US/DE/UK/CN), real yield, HY/IG OAS, NFCI, Fed Funds, unemployment, claims, CPI, PPI, PCE, ECB rates, CPI components, EU yields, global CPI, corporate spreads |
| 8 | Economic Activity | NFP, JOLTS, quits rate, Sahm rule, consumer sentiment, retail sales, ISM services, industrial production, housing starts, OECD CLI, intl unemployment/GDP, global PMI |

> **Note:** Tab 6 (Large-cap Financials) is not included in the Grafana dashboard as it requires interactive company selection. Use the Streamlit or React dashboard for financials.

## API Bridge Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/api/status` | GET | Last update, indicator count |
| `/api/indicators` | GET | All indicators (JSON) |
| `/api/indicator/{key}` | GET | Single indicator |
| `/api/metrics/summary` | GET | Flat key-value summary for stat panels |
| `/api/timeseries/{key}?days=90` | GET | Historical time series |
| `/api/table/{key}` | GET | Table-format data |
| `/api/group/{group}` | GET | Grouped indicators (valuation, volatility, etc.) |
| `/api/financials/{ticker}?source=yahoo` | GET | Company financials |
| `/api/refresh` | POST | Trigger data refresh |
| `/search` | POST | Grafana SimpleJSON metric list |
| `/query` | POST | Grafana SimpleJSON query |

## Configuration

### Environment Variables (Docker Compose)

| Variable | Default | Description |
|----------|---------|-------------|
| `GF_SECURITY_ADMIN_USER` | `admin` | Grafana admin username |
| `GF_SECURITY_ADMIN_PASSWORD` | `macro2024` | Grafana admin password |
| `GF_AUTH_ANONYMOUS_ENABLED` | `true` | Allow anonymous read access |

### Grafana Plugins

- **Infinity** (`yesoreyeram-infinity-datasource`) — JSON API data source
- **SimpleJSON** (`grafana-simple-json-datasource`) — Alternative data source

Both are auto-installed via `GF_INSTALL_PLUGINS`.

## Customization

### Adding New Panels

1. Add the metric key to `/api/metrics/summary` in `api_bridge/main.py`
2. Add a panel in `dashboards/macro_dashboard.json` targeting the new key
3. Restart: `docker compose restart grafana`

### Threshold Colors

Panels use Grafana's threshold system for conditional coloring:
- **Green** → normal / healthy
- **Yellow** → caution / elevated
- **Red** → warning / extreme

Thresholds are set per-panel and can be customized in the Grafana UI.

## Prerequisites

- Docker & Docker Compose (for Docker deployment)
- Python 3.10+ (for local API bridge)
- The parent project's data must be populated (`data_cache/all_indicators.json`)
  - Run `python scheduled_extract.py` from the project root first

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "No data" on panels | Ensure API bridge is running: `curl http://localhost:8001/api/status` |
| Empty metrics | Run `python scheduled_extract.py` from project root to populate cache |
| Plugin not found | Restart Grafana: `docker compose restart grafana` |
| Connection refused | Check API bridge logs: `docker compose logs api-bridge` |
