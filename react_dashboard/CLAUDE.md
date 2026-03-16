# CLAUDE.md - React Dashboard

React + FastAPI alternative frontend for the Macro Indicators Dashboard.

## What this is

A React frontend (Vite) + FastAPI backend that mirrors all 82 indicators from the parent project's Streamlit app. The backend imports from the parent `data_aggregator.py` directly -- no data layer duplication.

## Quick commands

```bash
bash start.sh                    # start both backend and frontend
cd backend && python main.py     # backend only (port 8000)
cd frontend && npm run dev       # frontend only (port 5173, proxies /api to 8000)
cd frontend && npm run build     # production build to frontend/dist/
```

## Key files

- `backend/main.py` -- FastAPI endpoints, pandas/numpy serialization
- `frontend/src/App.jsx` -- 8 tabs, auto-refresh, loading states
- `frontend/src/tabs/Tab1-8*.jsx` -- one component per tab, all 82 indicators
- `frontend/src/components/` -- MetricCard, ErrorCard, HistoryChart, etc.
- `frontend/src/api.js` -- axios client for `/api/*` endpoints

## Indicator keys

The backend serves indicators using the same keys as `data_aggregator.py`:
`1_sp500_forward_pe`, `2_russell_2000`, `3_sp500_fundamentals`, ..., `82_erp`

See the parent project's `CLAUDE.md` for the full indicator list and data flow.
