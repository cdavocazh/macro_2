"""
Grafana JSON API Data Source Bridge

Translates the macro dashboard's data_aggregator into a Grafana-compatible
JSON API data source. Supports the Infinity/JSON API plugin format.

Endpoints:
  GET  /                     → Health check
  GET  /api/indicators       → All indicators (JSON-safe)
  GET  /api/indicator/{key}  → Single indicator
  GET  /api/timeseries/{key} → Historical time series for Grafana
  GET  /api/table/{key}      → Table-format data for Grafana
  POST /api/refresh          → Trigger data refresh
  GET  /api/status           → Dashboard status
  GET  /api/financials/{ticker} → Company financials
"""

import sys
import os
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add parent project to path so we can import data_aggregator
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data_aggregator import get_aggregator

app = FastAPI(
    title="Macro Dashboard — Grafana Bridge",
    description="JSON API bridge for Grafana dashboards",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Serialization helpers ─────────────────────────────────────────────────

def _safe_float(v):
    """Convert numpy/pandas scalars to Python float, handle NaN/Inf."""
    if v is None:
        return None
    try:
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating, np.bool_)):
            f = float(v)
            if math.isnan(f) or math.isinf(f):
                return None
            return f
        if isinstance(v, float):
            if math.isnan(v) or math.isinf(v):
                return None
            return v
        return v
    except (TypeError, ValueError):
        return v


def _serialize(obj: Any) -> Any:
    """Recursively serialize an object for JSON output."""
    if obj is None:
        return None
    if isinstance(obj, (str, int, bool)):
        return obj
    if isinstance(obj, float):
        return _safe_float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return _safe_float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, (np.ndarray,)):
        return [_serialize(x) for x in obj.tolist()]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, pd.Series):
        # Convert to {iso_timestamp: value} dict
        result = {}
        for idx, val in obj.items():
            try:
                ts = pd.Timestamp(idx).isoformat()
            except Exception:
                ts = str(idx)
            result[ts] = _safe_float(val)
        return result
    if isinstance(obj, pd.DataFrame):
        return json.loads(obj.to_json(orient='records', date_format='iso'))
    if isinstance(obj, dict):
        return {str(k): _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(x) for x in obj]
    # Fallback
    try:
        return str(obj)
    except Exception:
        return None


def _series_to_timeseries(series_data, value_key='value'):
    """Convert a pd.Series or dict-of-timestamps to Grafana timeseries format.

    Returns list of [value, epoch_ms] for Grafana graph panels.
    """
    if series_data is None:
        return []

    points = []
    if isinstance(series_data, pd.Series):
        for idx, val in series_data.items():
            try:
                ts_ms = int(pd.Timestamp(idx).timestamp() * 1000)
                v = _safe_float(val)
                if v is not None:
                    points.append([v, ts_ms])
            except Exception:
                continue
    elif isinstance(series_data, dict):
        for ts_str, val in series_data.items():
            try:
                ts_ms = int(pd.Timestamp(ts_str).timestamp() * 1000)
                v = _safe_float(val)
                if v is not None:
                    points.append([v, ts_ms])
            except Exception:
                continue

    points.sort(key=lambda x: x[1])
    return points


# ─── API Endpoints ──────────────────────────────────────────────────────────

@app.get("/")
def health():
    """Health check for Grafana data source connectivity test."""
    return {"status": "ok", "service": "macro-grafana-bridge", "version": "1.0.0"}


@app.get("/api/status")
def get_status():
    """Dashboard status: last update, indicator count, errors."""
    agg = get_aggregator()
    agg.reload_if_stale()
    return {
        "last_update": agg.last_update.isoformat() if agg.last_update else None,
        "indicator_count": len(agg.indicators),
        "loaded_from_cache": agg.loaded_from_cache,
        "errors": [str(e) for e in agg.errors],
    }


@app.get("/api/indicators")
def get_all_indicators():
    """Return all indicators, JSON-safe serialized."""
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()
    if not agg.indicators:
        raise HTTPException(status_code=503, detail="No data available. Run scheduled_extract.py first.")
    return _serialize(agg.indicators)


@app.get("/api/indicator/{key}")
def get_indicator(key: str):
    """Return a single indicator by key."""
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()
    data = agg.indicators.get(key)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Indicator '{key}' not found")
    return _serialize(data)


@app.get("/api/timeseries/{key}")
def get_timeseries(
    key: str,
    hist_key: str = "historical",
    days: Optional[int] = None,
):
    """Return historical time series for a given indicator.

    Query params:
      hist_key: which key in the indicator dict holds the series (default: 'historical')
      days: limit to last N days (default: all)

    Returns Grafana-compatible format:
      {"target": "<key>", "datapoints": [[value, epoch_ms], ...]}
    """
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()

    data = agg.indicators.get(key)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Indicator '{key}' not found")

    series = data.get(hist_key)
    if series is None:
        return {"target": key, "datapoints": []}

    if isinstance(series, pd.Series) and days:
        cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
        try:
            if not isinstance(series.index, pd.DatetimeIndex):
                series.index = pd.to_datetime(series.index)
            if hasattr(series.index, 'tz') and series.index.tz is not None:
                series.index = series.index.tz_convert(None)
            series = series[series.index >= cutoff]
        except Exception:
            pass

    points = _series_to_timeseries(series)
    return {"target": key, "datapoints": points}


@app.get("/api/table/{key}")
def get_table(key: str, fields: Optional[str] = None):
    """Return indicator data in Grafana table format.

    Query params:
      fields: comma-separated list of fields to include (default: all scalar fields)

    Returns:
      {"columns": [...], "rows": [[...]], "type": "table"}
    """
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()

    data = agg.indicators.get(key)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Indicator '{key}' not found")

    # Filter to scalar fields
    field_list = fields.split(",") if fields else None
    columns = []
    values = []

    for k, v in data.items():
        if isinstance(v, (pd.Series, pd.DataFrame, list, dict)):
            continue
        if field_list and k not in field_list:
            continue
        columns.append({"text": k, "type": "string"})
        values.append(_safe_float(v) if isinstance(v, (int, float, np.integer, np.floating)) else str(v) if v is not None else "")

    return {
        "columns": columns,
        "rows": [values],
        "type": "table",
    }


@app.post("/api/refresh")
def refresh_data():
    """Trigger a full data refresh."""
    agg = get_aggregator()
    agg.fetch_all_indicators()
    return {
        "status": "refreshed",
        "indicator_count": len(agg.indicators),
        "timestamp": agg.last_update.isoformat() if agg.last_update else None,
    }


@app.get("/api/financials/{ticker}")
def get_financials(ticker: str, source: str = Query("yahoo", pattern="^(yahoo|sec)$")):
    """Fetch company financials on demand."""
    try:
        if source == "yahoo":
            from data_extractors.equity_financials_extractor import get_company_financials_yahoo
            result = get_company_financials_yahoo(ticker.upper())
        else:
            from data_extractors.sec_extractor import get_company_financials_sec
            result = get_company_financials_sec(ticker.upper())
        return _serialize(result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─── Grafana SimpleJSON-compatible endpoints ────────────────────────────────
# These support the Grafana SimpleJSON / Infinity data source plugin

@app.post("/search")
def grafana_search():
    """Return list of available metrics for Grafana query editor."""
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()
    return sorted(agg.indicators.keys())


@app.post("/query")
def grafana_query(body: dict):
    """Grafana SimpleJSON query endpoint.

    Accepts targets and returns timeseries or table data.
    """
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()

    results = []
    targets = body.get("targets", [])
    range_info = body.get("range", {})

    for target in targets:
        target_name = target.get("target", "")
        target_type = target.get("type", "timeserie")

        data = agg.indicators.get(target_name)
        if data is None:
            continue

        if target_type == "table":
            # Table format
            columns = []
            values = []
            for k, v in data.items():
                if isinstance(v, (pd.Series, pd.DataFrame)):
                    continue
                columns.append({"text": k, "type": "string"})
                sv = _safe_float(v) if isinstance(v, (int, float, np.integer, np.floating)) else str(v) if v is not None else ""
                values.append(sv)
            results.append({"columns": columns, "rows": [values], "type": "table"})
        else:
            # Timeseries format
            series = data.get("historical")
            points = _series_to_timeseries(series)
            results.append({"target": target_name, "datapoints": points})

    return results


@app.post("/annotations")
def grafana_annotations(body: dict):
    """Grafana annotations endpoint (required by SimpleJSON, returns empty)."""
    return []


# ─── Convenience: metrics summary endpoints for dashboard panels ────────

# These return pre-formatted data for specific Grafana panels

INDICATOR_GROUPS = {
    "valuation": [
        "1_sp500_forward_pe", "3_sp500_fundamentals", "7_shiller_cape",
        "6b_marketcap_to_gdp", "65_sp500_multiples", "74_sector_pe", "82_erp",
    ],
    "market_indices": [
        "17_es_futures", "18_rty_futures", "19_sp500_breadth", "2_russell_2000",
        "6a_sp500_to_ma200", "55_market_concentration", "62_sector_etfs",
        "69_fama_french", "73_earnings_calendar",
    ],
    "volatility": [
        "8_vix", "9_move_index", "8b_vix_move_ratio", "4_put_call_ratio",
        "5_spx_call_skew", "63_vix_futures_curve", "64_spy_put_call_oi", "70_iv_skew",
    ],
    "macro_currency": [
        "10_dxy", "20_jpy", "54_fx_pairs", "23_tga_balance", "24_net_liquidity",
        "47_m2", "25_sofr", "26_us_2y_yield", "27_japan_2y_yield",
        "28_us2y_jp2y_spread", "11_10y_yield", "12_ism_pmi", "80_money_measures",
    ],
    "commodities": [
        "13_gold", "14_silver", "15_crude_oil", "16_copper",
        "56_natural_gas", "57_cu_au_ratio", "22_cot_positioning", "52_brent_crude",
    ],
    "rates_credit": [
        "33_yield_curve", "30_germany_10y", "31_uk_10y", "32_china_10y",
        "61_5y_yield", "36_real_yield", "35_breakeven_inflation",
        "34_hy_oas", "37_nfci", "38_fed_funds", "45_ig_oas",
        "58_bank_reserves", "62_sloos", "40_unemployment", "39_initial_claims",
        "41_core_inflation", "49_continuing_claims", "53_headline_cpi", "52_ppi",
        "66_ecb_rates", "68_cpi_components", "71_eu_yields", "72_global_cpi",
        "75_treasury_curve", "76_corporate_spreads",
    ],
    "economic_activity": [
        "42_nfp", "48_jolts", "60_quits_rate", "46_sahm_rule",
        "44_consumer_sentiment", "50_retail_sales", "43_ism_services",
        "59_industrial_production", "51_housing_starts",
        "67_oecd_cli", "77_intl_unemployment", "78_intl_gdp", "81_global_pmi",
    ],
}


@app.get("/api/group/{group}")
def get_indicator_group(group: str):
    """Return all indicators for a dashboard group/tab.

    Groups: valuation, market_indices, volatility, macro_currency,
            commodities, rates_credit, economic_activity
    """
    if group not in INDICATOR_GROUPS:
        raise HTTPException(status_code=404, detail=f"Group '{group}' not found. Available: {list(INDICATOR_GROUPS.keys())}")

    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()

    result = {}
    for key in INDICATOR_GROUPS[group]:
        data = agg.indicators.get(key)
        if data is not None:
            result[key] = _serialize(data)
    return result


@app.get("/api/metrics/summary")
def get_metrics_summary():
    """Return a flat summary of all key metric values for stat panels.

    Returns a dict like:
    {
        "vix": 15.5,
        "vix_change_1d": -2.1,
        "dxy": 103.5,
        "gold_price": 2650.0,
        ...
    }
    """
    agg = get_aggregator()
    agg.reload_if_stale()
    if not agg.indicators:
        agg.load_from_local_cache()

    summary = {}
    # Helper to extract scalar values
    def _add(prefix, data, keys):
        if isinstance(data, dict) and 'error' not in data:
            for k in keys:
                v = data.get(k)
                if v is not None and not isinstance(v, (pd.Series, pd.DataFrame, dict, list)):
                    summary[f"{prefix}_{k}" if prefix else k] = _safe_float(v)

    indicators = agg.indicators

    # Tab 1: Valuation
    _add("", indicators.get("1_sp500_forward_pe", {}), ["sp500_forward_pe"])
    _add("", indicators.get("3_sp500_fundamentals", {}), ["sp500_pe_trailing", "sp500_pb"])
    _add("", indicators.get("7_shiller_cape", {}), ["shiller_cape"])
    _add("", indicators.get("6b_marketcap_to_gdp", {}), ["marketcap_to_gdp_ratio"])
    _add("mult", indicators.get("65_sp500_multiples", {}), ["forward_pe", "trailing_pe", "peg_ratio", "price_to_sales", "price_to_book", "price_to_cash", "eps_growth_next_5y", "eps_growth_past_5y"])
    _add("erp", indicators.get("82_erp", {}), ["equity_risk_premium", "forward_erp", "earnings_yield", "real_yield_10y"])

    # Tab 2: Market Indices
    _add("es", indicators.get("17_es_futures", {}), ["price", "change_1d"])
    _add("rty", indicators.get("18_rty_futures", {}), ["price", "change_1d"])
    _add("breadth", indicators.get("19_sp500_breadth", {}), ["advancing_stocks", "declining_stocks", "net_advances", "breadth_percentage"])
    r2k = indicators.get("2_russell_2000", {})
    if isinstance(r2k, dict) and 'error' not in r2k:
        v_data = r2k.get("russell_2000_value", {})
        g_data = r2k.get("russell_2000_growth", {})
        if isinstance(v_data, dict):
            summary["r2k_value_price"] = _safe_float(v_data.get("latest_price"))
            summary["r2k_value_change"] = _safe_float(v_data.get("change_1d"))
        if isinstance(g_data, dict):
            summary["r2k_growth_price"] = _safe_float(g_data.get("latest_price"))
            summary["r2k_growth_change"] = _safe_float(g_data.get("change_1d"))
        summary["r2k_vg_ratio"] = _safe_float(r2k.get("value_growth_ratio"))
    _add("sp_ma", indicators.get("6a_sp500_to_ma200", {}), ["sp500_price", "sp500_ma200", "sp500_to_ma200_ratio"])
    _add("conc", indicators.get("55_market_concentration", {}), ["spy_rsp_ratio", "change_1d", "change_30d"])
    _add("ff", indicators.get("69_fama_french", {}), ["mkt_rf", "smb", "hml", "rmw", "cma", "rf"])

    # Tab 3: Volatility
    _add("", indicators.get("8_vix", {}), ["vix", "change_1d"])
    _add("move", indicators.get("9_move_index", {}), ["move", "change_1d"])
    _add("", indicators.get("8b_vix_move_ratio", {}), ["vix_move_ratio"])
    _add("pc", indicators.get("4_put_call_ratio", {}), ["sp500_put_call_ratio"])
    _add("skew", indicators.get("5_spx_call_skew", {}), ["spx_call_skew"])
    _add("vfc", indicators.get("63_vix_futures_curve", {}), ["vix_spot", "contango_pct", "n_expirations"])
    _add("pcoi", indicators.get("64_spy_put_call_oi", {}), ["put_call_volume_ratio", "put_call_oi_ratio"])
    _add("ivs", indicators.get("70_iv_skew", {}), ["iv_skew_25d", "skew_index"])

    # Tab 4: Macro & Currency
    _add("", indicators.get("10_dxy", {}), ["dxy", "change_1d"])
    _add("jpy", indicators.get("20_jpy", {}), ["jpy_rate", "change_1d"])
    fx = indicators.get("54_fx_pairs", {})
    if isinstance(fx, dict) and 'error' not in fx:
        for pair in ["eur_usd", "gbp_usd", "eur_jpy"]:
            summary[pair] = _safe_float(fx.get(pair))
            summary[f"{pair}_change"] = _safe_float(fx.get(f"{pair}_change_1d"))
    _add("tga", indicators.get("23_tga_balance", {}), ["tga_balance_billions", "change_wow_pct"])
    _add("nliq", indicators.get("24_net_liquidity", {}), ["net_liquidity_trillions", "change_pct"])
    _add("m2", indicators.get("47_m2", {}), ["m2_trillions", "m2_yoy_growth"])
    _add("sofr", indicators.get("25_sofr", {}), ["sofr", "change_1d"])
    _add("us2y", indicators.get("26_us_2y_yield", {}), ["us_2y_yield", "change_1d", "spread_2s10s"])
    _add("jp2y", indicators.get("27_japan_2y_yield", {}), ["japan_2y_yield", "change_1d"])
    _add("spread", indicators.get("28_us2y_jp2y_spread", {}), ["spread"])
    _add("t10y", indicators.get("11_10y_yield", {}), ["10y_yield"])
    _add("ism", indicators.get("12_ism_pmi", {}), ["ism_pmi"])
    _add("mm", indicators.get("80_money_measures", {}), ["m1_level", "m1_yoy", "m2_level", "m2_yoy"])

    # Tab 5: Commodities
    _add("gold", indicators.get("13_gold", {}), ["price", "change_1d"])
    _add("silver", indicators.get("14_silver", {}), ["price", "change_1d"])
    _add("oil", indicators.get("15_crude_oil", {}), ["price", "change_1d"])
    _add("copper", indicators.get("16_copper", {}), ["price", "change_1d"])
    _add("natgas", indicators.get("56_natural_gas", {}), ["price", "change_1d"])
    _add("cuau", indicators.get("57_cu_au_ratio", {}), ["cu_au_ratio", "change_1d"])
    _add("brent", indicators.get("52_brent_crude", {}), ["price", "change_1d"])

    # Tab 7: Rates & Credit
    _add("de10y", indicators.get("30_germany_10y", {}), ["germany_10y", "change_1d"])
    _add("uk10y", indicators.get("31_uk_10y", {}), ["uk_10y", "change_1d"])
    _add("cn10y", indicators.get("32_china_10y", {}), ["china_10y", "change_1d"])
    _add("us5y", indicators.get("61_5y_yield", {}), ["us_5y_yield"])
    _add("ry", indicators.get("36_real_yield", {}), ["real_yield_10y"])
    _add("be", indicators.get("35_breakeven_inflation", {}), ["breakeven_5y", "breakeven_10y"])
    _add("hy", indicators.get("34_hy_oas", {}), ["hy_oas"])
    _add("nfci", indicators.get("37_nfci", {}), ["nfci"])
    _add("ffr", indicators.get("38_fed_funds", {}), ["fed_funds_rate"])
    _add("ig", indicators.get("45_ig_oas", {}), ["ig_oas"])
    _add("res", indicators.get("58_bank_reserves", {}), ["bank_reserves_billions"])
    _add("sloos", indicators.get("62_sloos", {}), ["sloos_tightening_pct"])
    _add("unemp", indicators.get("40_unemployment", {}), ["unemployment_rate"])
    _add("claims", indicators.get("39_initial_claims", {}), ["initial_claims_thousands"])
    _add("infl", indicators.get("41_core_inflation", {}), ["core_pce_yoy"])
    _add("cclaims", indicators.get("49_continuing_claims", {}), ["continuing_claims_thousands"])
    _add("hcpi", indicators.get("53_headline_cpi", {}), ["headline_cpi_yoy"])
    _add("ppi", indicators.get("52_ppi", {}), ["ppi_yoy"])
    ecb = indicators.get("66_ecb_rates", {})
    if isinstance(ecb, dict) and 'error' not in ecb:
        summary["ecb_deposit"] = _safe_float(ecb.get("deposit_rate"))
        summary["ecb_refi"] = _safe_float(ecb.get("refi_rate"))
        summary["ecb_marginal"] = _safe_float(ecb.get("marginal_rate"))
    cpic = indicators.get("68_cpi_components", {})
    if isinstance(cpic, dict) and 'error' not in cpic:
        for k in ["headline_cpi_yoy", "core_cpi_yoy", "food_cpi_yoy", "energy_cpi_yoy", "shelter_cpi_yoy"]:
            summary[f"cpic_{k}"] = _safe_float(cpic.get(k))
    euy = indicators.get("71_eu_yields", {})
    if isinstance(euy, dict) and 'error' not in euy:
        for k in ["de_10y", "fr_10y", "it_10y"]:
            summary[f"euy_{k}"] = _safe_float(euy.get(k))
    gcpi = indicators.get("72_global_cpi", {})
    if isinstance(gcpi, dict) and 'error' not in gcpi:
        for k in ["us_cpi_yoy", "eu_cpi_yoy", "jp_cpi_yoy", "uk_cpi_yoy"]:
            summary[f"gcpi_{k}"] = _safe_float(gcpi.get(k))
    cs = indicators.get("76_corporate_spreads", {})
    if isinstance(cs, dict) and 'error' not in cs:
        for k in ["aaa_oas", "bbb_oas", "credit_spread"]:
            summary[f"cs_{k}"] = _safe_float(cs.get(k))

    # Tab 8: Economic Activity
    _add("nfp", indicators.get("42_nfp", {}), ["nfp_thousands", "nfp_change_mom"])
    _add("jolts", indicators.get("48_jolts", {}), ["jolts_openings_m", "change_mom_pct"])
    _add("quits", indicators.get("60_quits_rate", {}), ["quits_rate"])
    _add("sahm", indicators.get("46_sahm_rule", {}), ["sahm_value", "triggered"])
    _add("csent", indicators.get("44_consumer_sentiment", {}), ["consumer_sentiment", "change_mom"])
    _add("retail", indicators.get("50_retail_sales", {}), ["retail_sales_b", "retail_sales_mom_pct"])
    _add("ismsvc", indicators.get("43_ism_services", {}), ["ism_services_pmi"])
    _add("ip", indicators.get("59_industrial_production", {}), ["indpro_index", "indpro_yoy_pct"])
    _add("hs", indicators.get("51_housing_starts", {}), ["housing_starts_k"])
    _add("oecd", indicators.get("67_oecd_cli", {}), ["cli_value"])
    iu = indicators.get("77_intl_unemployment", {})
    if isinstance(iu, dict) and 'error' not in iu:
        for k in ["us_unemployment", "eu_unemployment", "jp_unemployment", "uk_unemployment"]:
            summary[f"iu_{k}"] = _safe_float(iu.get(k))
    ig = indicators.get("78_intl_gdp", {})
    if isinstance(ig, dict) and 'error' not in ig:
        for k in ["us_gdp_growth", "eu_gdp_growth", "jp_gdp_growth", "cn_gdp_growth"]:
            summary[f"ig_{k}"] = _safe_float(ig.get(k))
    gpmi = indicators.get("81_global_pmi", {})
    if isinstance(gpmi, dict) and 'error' not in gpmi:
        for k in ["us_pmi", "eu_pmi", "jp_pmi", "cn_pmi", "uk_pmi"]:
            summary[f"gpmi_{k}"] = _safe_float(gpmi.get(k))

    return summary


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
