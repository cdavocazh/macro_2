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

from fastapi import FastAPI, Query, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import asyncio
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
# Hyperliquid WebSocket relay (starts/stops with the server)
# ---------------------------------------------------------------------------

_relay = None

def get_relay():
    global _relay
    if _relay is None:
        # Import here to avoid circular imports and allow server to start without it
        try:
            from react_dashboard.backend.hl_ws_service import HyperliquidWSRelay
            _relay = HyperliquidWSRelay()
        except ImportError:
            try:
                from hl_ws_service import HyperliquidWSRelay
                _relay = HyperliquidWSRelay()
            except ImportError:
                pass
    return _relay


@app.on_event("startup")
async def _start_relay():
    relay = get_relay()
    if relay:
        asyncio.create_task(relay.start())


@app.on_event("shutdown")
async def _stop_relay():
    relay = get_relay()
    if relay:
        await relay.stop()


@app.websocket("/ws/hl")
async def ws_hl(websocket: WebSocket):
    """WebSocket endpoint for real-time Hyperliquid data (~1s updates)."""
    relay = get_relay()
    if not relay:
        await websocket.close(code=1011, reason="Relay not available")
        return

    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=50)
    relay.add_client(queue)
    try:
        # Send initial snapshot
        snapshot = relay.get_snapshot()
        if snapshot:
            await websocket.send_json(snapshot)
        # Stream updates
        while True:
            msg = await queue.get()
            await websocket.send_json(msg)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        relay.remove_client(queue)


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
# IBKR realtime overlay
# Reads data_cache/ibkr_realtime.json written by ibkr_fast_extract.py
# and overlays real-time prices on yfinance-based indicator keys.
# ---------------------------------------------------------------------------

_IBKR_REALTIME_FILE = os.path.join(PROJECT_ROOT, "data_cache", "ibkr_realtime.json")

# Mapping: IBKR symbol -> (indicator_key, price_field_in_indicator)
# When an IBKR quote has a valid "last" price, overlay it on the indicator.
_IBKR_OVERLAY_MAP = {
    "ES":  ("17_es_futures", "price"),
    "RTY": ("18_rty_futures", "price"),
    "GC":  ("13_gold", "price"),
    "SI":  ("14_silver", "price"),
    "HG":  ("16_copper", "price"),
    "CL":  ("15_crude_oil", "price"),
    "NG":  ("56_natural_gas", "price"),
    "USDJPY": ("20_jpy", "price"),
}


def _apply_ibkr_overlay(indicators: dict) -> dict:
    """Overlay IBKR real-time prices on yfinance-based indicators.

    Reads /data_cache/ibkr_realtime.json if available and updates the
    price/latest_date fields on mapped indicators. Silently no-ops if
    the file is missing or stale (>10 min old).
    """
    try:
        if not os.path.exists(_IBKR_REALTIME_FILE):
            return indicators

        # Skip if file is stale
        mtime = os.path.getmtime(_IBKR_REALTIME_FILE)
        age_secs = datetime.now().timestamp() - mtime
        if age_secs > 600:  # 10 min
            return indicators

        import json as _json
        with open(_IBKR_REALTIME_FILE) as f:
            ibkr = _json.load(f)

        if ibkr.get("status") != "streaming":
            return indicators

        quotes = ibkr.get("quotes", {})
        snapshot_ts = ibkr.get("timestamp", "")

        for sym, (key, price_field) in _IBKR_OVERLAY_MAP.items():
            q = quotes.get(sym)
            if q is None:
                continue
            last = q.get("last")
            if last is None or last <= 0:
                continue

            # Overlay only if indicator exists and is not in error state
            if key not in indicators:
                continue
            ind = indicators[key]
            if not isinstance(ind, dict) or "error" in ind:
                continue

            # Update price + mark data as real-time from IBKR
            ind[price_field] = last
            # Use the per-quote tick time, not the snapshot timestamp,
            # so the dashboard shows when the price actually last changed.
            ind["latest_date"] = q.get("last_update") or snapshot_ts
            ind["source"] = "IBKR (real-time)"
            # Replace yfinance's stale "Last close from..." note with IBKR-aware note
            ind["note"] = "IBKR live tick"
            # Expose IBKR contract metadata for the dashboard
            ind["ibkr_local_symbol"] = q.get("local_symbol")
            ind["ibkr_expiry"] = q.get("expiry")
            ind["ibkr_contract_id"] = q.get("contract_id")
            ind["ibkr_bid"] = q.get("bid")
            ind["ibkr_ask"] = q.get("ask")
            ind["ibkr_volume"] = q.get("volume")
            ind["ibkr_open_interest"] = q.get("futures_open_interest")
            # Preserve 1d change from yfinance if present
            prev = q.get("prev_close")
            if prev and prev > 0:
                ind["change_1d"] = round((last / prev - 1) * 100, 2)
    except Exception as e:
        # Silently fall back to yfinance data on any error
        pass

    return indicators


# ---------------------------------------------------------------------------
# IBKR subscription manifest IPC
# Backend writes to ibkr_subscriptions.json; daemon reads it every 5s and
# applies subscription swaps.  Backend reads ibkr_available_contracts.json
# (refreshed hourly by daemon) to populate the dropdown.
# ---------------------------------------------------------------------------

_IBKR_SUBSCRIPTIONS_FILE = os.path.join(PROJECT_ROOT, "data_cache", "ibkr_subscriptions.json")
_IBKR_AVAILABLE_CONTRACTS_FILE = os.path.join(PROJECT_ROOT, "data_cache", "ibkr_available_contracts.json")
_IBKR_AVAILABLE_CONTRACTS_MAX_AGE_HOURS = 4

# Symbols that the dashboard tabs actually map to indicator keys
_VALID_IBKR_SYMBOLS = {
    "ES", "NQ", "RTY", "GC", "SI", "HG", "CL", "NG",
    "ZN", "ZB", "ZF", "ZT", "10Y", "2YY", "VIX", "EURUSD", "USDJPY",
}


def _read_subscriptions_manifest() -> dict:
    """Read manifest, return dict {subscriptions: {sym: {...}}, updated_at: ...}."""
    import json as _json
    if not os.path.exists(_IBKR_SUBSCRIPTIONS_FILE):
        return {"subscriptions": {}, "updated_at": None}
    try:
        with open(_IBKR_SUBSCRIPTIONS_FILE) as f:
            return _json.load(f)
    except (OSError, _json.JSONDecodeError):
        return {"subscriptions": {}, "updated_at": None}


def _write_subscriptions_manifest(manifest: dict):
    """Atomic write of subscription manifest."""
    import json as _json
    import tempfile
    dir_path = os.path.dirname(_IBKR_SUBSCRIPTIONS_FILE)
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            _json.dump(manifest, f, default=str, indent=2)
        os.replace(tmp, _IBKR_SUBSCRIPTIONS_FILE)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


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


@app.get("/api/ibkr/contracts/{symbol}")
def list_ibkr_contracts(symbol: str):
    """List available expiries for an IBKR future symbol.

    Reads data_cache/ibkr_available_contracts.json (refreshed hourly by daemon).
    Returns 404 if symbol unknown or file missing/stale.
    """
    import json as _json
    sym = symbol.upper()
    if sym not in _VALID_IBKR_SYMBOLS:
        raise HTTPException(status_code=404, detail=f"Unknown IBKR symbol: {symbol}")

    if not os.path.exists(_IBKR_AVAILABLE_CONTRACTS_FILE):
        raise HTTPException(
            status_code=503,
            detail="Available contracts file not found — daemon hasn't refreshed yet.",
        )

    # Staleness check
    age_hours = (datetime.now().timestamp() - os.path.getmtime(_IBKR_AVAILABLE_CONTRACTS_FILE)) / 3600
    if age_hours > _IBKR_AVAILABLE_CONTRACTS_MAX_AGE_HOURS:
        raise HTTPException(
            status_code=503,
            detail=f"Available contracts file stale ({age_hours:.1f}h > {_IBKR_AVAILABLE_CONTRACTS_MAX_AGE_HOURS}h)",
        )

    try:
        with open(_IBKR_AVAILABLE_CONTRACTS_FILE) as f:
            data = _json.load(f)
    except (_json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Could not parse contracts file: {e}")

    contracts = data.get("contracts", {}).get(sym, [])
    if not contracts:
        raise HTTPException(
            status_code=404,
            detail=f"No contracts available for {sym} (not a future or daemon hasn't queried it).",
        )

    # Find the currently active subscription (from manifest or front-month default)
    manifest = _read_subscriptions_manifest().get("subscriptions", {})
    pinned = manifest.get(sym, {})
    current_expiry = pinned.get("expiry") if not pinned.get("reset_to_front_month") else None

    return {
        "symbol": sym,
        "updated_at": data.get("updated_at"),
        "current_expiry": current_expiry,
        "current_is_front_month": not bool(current_expiry),
        "contracts": contracts,
    }


@app.post("/api/ibkr/subscribe")
async def subscribe_ibkr_expiry(req: dict):
    """Pin (or reset) the active IBKR expiry for a symbol.

    Body: {"symbol": "GC", "expiry": "20261229"}
    Or:   {"symbol": "GC", "expiry": ""}  -> reset to front month

    Writes to data_cache/ibkr_subscriptions.json. The daemon picks up
    the change within ~5 seconds and swaps the IBKR subscription.
    """
    sym = (req.get("symbol") or "").upper()
    expiry = (req.get("expiry") or "").strip()

    if sym not in _VALID_IBKR_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Unknown symbol: {sym}")

    # Validate expiry format if provided (YYYYMMDD or YYYYMM)
    if expiry and not (expiry.isdigit() and len(expiry) in (6, 8)):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid expiry format: {expiry} (expected YYYYMMDD or YYYYMM)",
        )

    manifest = _read_subscriptions_manifest()
    subs = manifest.get("subscriptions", {})

    if expiry:
        subs[sym] = {"expiry": expiry}
        action = f"pin to {expiry}"
    else:
        subs[sym] = {"reset_to_front_month": True}
        action = "reset to front month"

    manifest["subscriptions"] = subs
    manifest["updated_at"] = datetime.now().isoformat()
    _write_subscriptions_manifest(manifest)

    return {
        "status": "queued",
        "symbol": sym,
        "expiry": expiry or None,
        "action": action,
        "message": "Daemon will apply within ~5 seconds.",
    }


@app.get("/api/ibkr/subscriptions")
def get_ibkr_subscriptions():
    """Return current subscription manifest (what's pinned vs front-month)."""
    return _read_subscriptions_manifest()


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

    # Overlay IBKR real-time prices where available
    serialized = _apply_ibkr_overlay(serialized)

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
# Intraday OHLCV (yfinance) — multi-granularity candlestick charts
# ---------------------------------------------------------------------------

YF_TICKER_MAP = {
    'dxy': 'DX-Y.NYB', 'usdjpy': 'JPY=X', 'eurusd': 'EURUSD=X',
    'gbpusd': 'GBPUSD=X', 'eurjpy': 'EURJPY=X',
    'vix': '^VIX', 'move': '^MOVE',
    'gold': 'GC=F', 'silver': 'SI=F', 'crude_oil': 'CL=F',
    'copper': 'HG=F', 'natural_gas': 'NG=F',
    'es_futures': 'ES=F', 'rty_futures': 'RTY=F',
    'spy': 'SPY', 'us_10y': '^TNX',
    'hyg': 'HYG', 'lqd': 'LQD',
}
YF_INTERVAL_PERIOD = {
    '1h': '60d', '4h': '60d', '1d': '3mo', '1wk': '2y',
}


@app.get("/api/intraday/{key}")
def get_intraday_ohlcv(key: str, interval: str = Query("1h")):
    """Fetch intraday OHLCV from yfinance for candlestick charts."""
    import yfinance as yf

    yf_ticker = YF_TICKER_MAP.get(key)
    if not yf_ticker:
        raise HTTPException(status_code=404, detail=f"Unknown instrument: {key}")

    period = YF_INTERVAL_PERIOD.get(interval, '60d')
    try:
        ticker = yf.Ticker(yf_ticker)
        df = ticker.history(interval=interval, period=period)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        return []

    # Deduplicate by timestamp (keep last row per time)
    seen = {}
    for idx, row in df.iterrows():
        ts = idx
        if hasattr(ts, 'tz') and ts.tz is not None:
            ts = ts.tz_convert(None)
        t = int(ts.timestamp())
        seen[t] = {
            'time': t,
            'open': round(float(row['Open']), 6),
            'high': round(float(row['High']), 6),
            'low': round(float(row['Low']), 6),
            'close': round(float(row['Close']), 6),
            'volume': round(float(row.get('Volume', 0)), 4),
        }
    return [seen[t] for t in sorted(seen)]


# ---------------------------------------------------------------------------
# Hyperliquid OHLCV — multi-interval candlestick charts
# ---------------------------------------------------------------------------

import threading
_hl_ohlcv_lock = threading.Lock()
_hl_ohlcv_cache = {}  # (coin, interval) → (timestamp, records)
_HL_OHLCV_TTL = 30  # Cache OHLCV for 30 seconds to avoid 429s

@app.get("/api/hl/ohlcv/{coin}")
def get_hl_ohlcv(coin: str, interval: str = Query("1h")):
    """Fetch OHLCV candlestick data for a Hyperliquid perp instrument."""
    import time as _time
    from data_extractors.hyperliquid_extractor import get_hl_candles, HL_PERPS, HL_INTERVAL_LOOKBACK

    # Resolve API coin name (e.g. 'oil' → 'flx:OIL')
    api_coin = coin.upper()
    for hl_ticker, info in HL_PERPS.items():
        if info['key'] == coin.lower():
            api_coin = info.get('api_coin', hl_ticker)
            break

    # Check in-memory cache to avoid hammering HL API
    cache_key = (api_coin, interval)
    with _hl_ohlcv_lock:
        cached = _hl_ohlcv_cache.get(cache_key)
        if cached and (_time.time() - cached[0]) < _HL_OHLCV_TTL:
            return cached[1]

    lookback_days = HL_INTERVAL_LOOKBACK.get(interval, 90)
    try:
        df = get_hl_candles(api_coin, interval=interval, lookback_days=lookback_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if df.empty:
        return []

    # Deduplicate by timestamp (keep last row per time)
    seen = {}
    for idx, row in df.iterrows():
        t = int(idx.timestamp())
        seen[t] = {
            'time': t,
            'open': round(float(row['Open']), 6),
            'high': round(float(row['High']), 6),
            'low': round(float(row['Low']), 6),
            'close': round(float(row['Close']), 6),
            'volume': round(float(row['Volume']), 4),
        }
    records = [seen[t] for t in sorted(seen)]

    # Cache the result
    with _hl_ohlcv_lock:
        _hl_ohlcv_cache[cache_key] = (_time.time(), records)

    return records


# ---------------------------------------------------------------------------
# Polymarket price history — prediction market probability charts
# ---------------------------------------------------------------------------

import threading as _pm_threading
_pm_cache_lock = _pm_threading.Lock()
_pm_price_cache = {}  # (token_id, interval) → (timestamp, records)
_PM_CACHE_TTL = 60  # Cache for 60 seconds


@app.get("/api/polymarket/history/{token_id}")
def get_polymarket_history(token_id: str, interval: str = Query("1d")):
    """Proxy price history from Polymarket CLOB API for lightweight-charts."""
    import time as _time
    import requests

    VALID_INTERVALS = {'1h', '6h', '1d', 'all'}
    if interval not in VALID_INTERVALS:
        raise HTTPException(status_code=400, detail=f"Invalid interval: {interval}")

    # Check in-memory cache
    cache_key = (token_id, interval)
    with _pm_cache_lock:
        cached = _pm_price_cache.get(cache_key)
        if cached and (_time.time() - cached[0]) < _PM_CACHE_TTL:
            return cached[1]

    try:
        resp = requests.get(
            "https://clob.polymarket.com/prices-history",
            params={"market": token_id, "interval": interval},
            timeout=15,
        )
        resp.raise_for_status()
        history = resp.json().get("history", [])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"CLOB API error: {e}")

    # Deduplicate by timestamp (keep last value), sort ascending
    seen = {}
    for pt in history:
        seen[pt["t"]] = pt["p"]
    records = [{"time": t, "value": v} for t, v in sorted(seen.items())]

    with _pm_cache_lock:
        _pm_price_cache[cache_key] = (_time.time(), records)

    return records


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
