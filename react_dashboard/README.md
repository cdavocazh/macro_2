# Macro Indicators Dashboard (React + FastAPI)

React frontend + FastAPI backend that mirrors all 82 indicators from the existing Streamlit dashboard.

## Quick Start

```bash
# One command to start both backend and frontend:
bash start.sh

# Or start separately:

# Terminal 1 - Backend (port 8000)
cd backend
pip install -r requirements.txt
python main.py

# Terminal 2 - Frontend (port 5173)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Architecture

```
react_dashboard/
  backend/
    main.py              FastAPI app - wraps existing data_aggregator
    requirements.txt     Python dependencies (fastapi, uvicorn)
  frontend/
    src/
      App.jsx            Main app with 8 tabs, auto-refresh
      api.js             Axios API client
      components/        MetricCard, ErrorCard, HistoryChart, etc.
      tabs/              Tab1-8 components (one per dashboard tab)
    vite.config.js       Vite dev server with /api proxy to :8000
  start.sh               Launch both servers
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/indicators` | GET | All 82 cached indicators (JSON) |
| `/api/indicators/{key}` | GET | Single indicator by key |
| `/api/refresh` | GET | Trigger full data refresh (~40s) |
| `/api/status` | GET | Last update, count, errors |
| `/api/financials/{ticker}?source=yahoo` | GET | On-demand company financials |
| `/api/history/{key}?hist_key=historical` | GET | Historical series data |
| `/docs` | GET | Interactive API documentation (Swagger) |

## Dashboard Tabs

| Tab | Indicators |
|-----|------------|
| 1. Valuation | Forward P/E, Trailing P/E, P/B, CAPE, Market Cap/GDP, Multiples, Sector P/E, ERP |
| 2. Market Indices | ES/RTY futures, breadth, Russell 2000 V/G, S&P/200MA, SPY/RSP, Fama-French, earnings |
| 3. Volatility | VIX, MOVE, VIX/MOVE, Put/Call, SKEW, VIX futures curve, SPY P/C OI, IV Skew |
| 4. Macro & Currency | DXY, JPY, EUR/USD, GBP/USD, EUR/JPY, TGA, net liquidity, M2, SOFR, yields, ISM PMI |
| 5. Commodities | Gold, silver, oil, copper, natural gas, Cu/Au ratio, COT positioning |
| 6. Financials | Top 20 + custom ticker, Yahoo/SEC toggle, quarterly statements, analysis, valuation |
| 7. Rates & Credit | Yield curve regime, global yields, real yields, breakevens, credit spreads, labor, CPI |
| 8. Economic Activity | NFP, JOLTS, Sahm Rule, sentiment, retail, ISM Services, housing, OECD CLI, intl data |

## Data Flow

The backend imports directly from the parent project's `data_aggregator.py` and `data_extractors/`. No data layer duplication.

```
Frontend (React)  --/api/indicators-->  FastAPI backend
                                          |
                                          v
                                    data_aggregator.get_aggregator()
                                          |
                                          v
                                    data_cache/all_indicators.json
```

## Production Deployment

```bash
# Build frontend
cd frontend && npm run build

# Serve with gunicorn + static files
pip install gunicorn
cd backend
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# Serve frontend/dist/ with nginx or similar
```

## Requirements

- Python 3.10+ (same environment as parent project)
- Node.js 18+
- Parent project dependencies installed (pandas, yfinance, fredapi, etc.)
