"""
FastAPI backend for the Macro Indicators React Dashboard.
Wraps the existing data_aggregator and data_extractors modules.
"""
import sys
import os
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent project to path so we can import data_aggregator, etc.
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import pandas as pd
import numpy as np

app = FastAPI(title="Macro Indicators API", version="1.0.0")

# CORS for local dev (Vite runs on 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _safe_float(v):
    """Convert numpy/pandas scalar to Python float, handling NaN/Inf."""
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        if math.isnan(v) or math.isinf(v):
            return None
        return float(v)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def _serialize_value(v):
    """Recursively serialize a value to JSON-safe types."""
    if v is None:
        return None

    # pandas Series -> {index: [...], values: [...]}
    if isinstance(v, pd.Series):
        idx = v.index
        # Convert index to strings
        if isinstance(idx, pd.DatetimeIndex):
            index_list = [d.isoformat() for d in idx]
        else:
            index_list = [str(i) for i in idx]
        values_list = [_safe_float(x) for x in v.values]
        return {"__type__": "series", "index": index_list, "values": values_list}

    # pandas DataFrame -> list of records
    if isinstance(v, pd.DataFrame):
        records = []
        for _, row in v.iterrows():
            rec = {}
            for col in v.columns:
                rec[col] = _safe_float(row[col]) if isinstance(row[col], (int, float, np.integer, np.floating)) else str(row[col]) if not pd.isna(row[col]) else None
            records.append(rec)
        return {"__type__": "dataframe", "records": records, "columns": list(v.columns)}

    # numpy types
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(v, np.bool_):
        return bool(v)
    if isinstance(v, np.ndarray):
        return [_safe_float(x) for x in v.tolist()]

    # pd.Timestamp
    if isinstance(v, pd.Timestamp):
        return v.isoformat()

    # datetime
    if isinstance(v, datetime):
        return v.isoformat()

    # dict -> recurse
    if isinstance(v, dict):
        return {str(k): _serialize_value(val) for k, val in v.items()}

    # list/tuple -> recurse
    if isinstance(v, (list, tuple)):
        return [_serialize_value(x) for x in v]

    # float NaN check
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v

    # Fallback: try to convert to string if it's not a basic type
    if not isinstance(v, (str, int, bool)):
        try:
            return str(v)
        except Exception:
            return None

    return v


def _serialize_indicator(data):
    """Serialize a single indicator dict to JSON-safe format."""
    if data is None:
        return None
    return _serialize_value(data)


# ---------------------------------------------------------------------------
# Aggregator access
# ---------------------------------------------------------------------------

def _get_aggregator():
    from data_aggregator import get_aggregator
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()
    return agg


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.get("/api/status")
def get_status():
    """Return dashboard status: last_update, indicator count, errors."""
    agg = _get_aggregator()
    total = len(agg.indicators)
    errors = []
    for key, val in agg.indicators.items():
        if isinstance(val, dict) and "error" in val:
            errors.append({"key": key, "error": val["error"]})
    return {
        "last_update": agg.last_update.isoformat() if agg.last_update else None,
        "loaded_from_cache": agg.loaded_from_cache,
        "total_indicators": total,
        "error_count": len(errors),
        "errors": errors,
    }


@app.get("/api/indicators")
def get_all_indicators():
    """Return all cached indicators, JSON-serialized."""
    agg = _get_aggregator()
    if not agg.indicators:
        return JSONResponse(
            status_code=503,
            content={"error": "No data available. Run scheduled_extract.py or click Refresh."},
        )

    serialized = {}
    for key, val in agg.indicators.items():
        try:
            serialized[key] = _serialize_indicator(val)
        except Exception as e:
            serialized[key] = {"error": f"Serialization failed: {str(e)}"}

    return {
        "last_update": agg.last_update.isoformat() if agg.last_update else None,
        "loaded_from_cache": agg.loaded_from_cache,
        "total": len(serialized),
        "indicators": serialized,
    }


@app.get("/api/indicators/{key}")
def get_indicator(key: str):
    """Return a single indicator by key."""
    agg = _get_aggregator()
    data = agg.get_indicator(key)
    return _serialize_indicator(data)


@app.get("/api/refresh")
def refresh_data():
    """Trigger a full data refresh (slow, ~40s)."""
    agg = _get_aggregator()
    try:
        agg.fetch_all_indicators()
        return {
            "status": "ok",
            "last_update": agg.last_update.isoformat() if agg.last_update else None,
            "total_indicators": len(agg.indicators),
            "errors": len(agg.errors),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/history/{key}")
def get_history(key: str, hist_key: str = "historical"):
    """Return historical series data for a given indicator."""
    agg = _get_aggregator()
    data = agg.get_indicator(key)
    if isinstance(data, dict) and "error" in data:
        raise HTTPException(status_code=404, detail=data["error"])

    hist = data.get(hist_key) if isinstance(data, dict) else None
    if hist is None:
        raise HTTPException(status_code=404, detail=f"No '{hist_key}' data for {key}")

    return _serialize_value(hist)


@app.get("/api/financials/{ticker}")
def get_financials(ticker: str, source: str = Query("yahoo", pattern="^(yahoo|sec)$")):
    """Fetch company financials on demand."""
    ticker = ticker.upper().replace(".", "-")

    if source == "yahoo":
        from data_extractors.equity_financials_extractor import get_company_financials_yahoo
        data = get_company_financials_yahoo(ticker)
    else:
        from data_extractors.sec_extractor import get_company_financials_sec
        data = get_company_financials_sec(ticker)

    if isinstance(data, dict) and "error" in data:
        return JSONResponse(status_code=404, content=_serialize_indicator(data))

    return _serialize_indicator(data)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
