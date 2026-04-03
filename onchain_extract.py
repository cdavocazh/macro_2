#!/usr/bin/env python3
"""
Daily CheckOnChain on-chain BTC data extraction.

Scrapes Plotly-based charts from charts.checkonchain.com (static HTML,
no auth required, robots.txt allows scraping). Data is base64-encoded
float64 arrays embedded in Plotly trace objects.

Standalone script — not coupled to data_aggregator.py or the macro
dashboard cache. Output goes to historical_data/onchain/*.csv.

Usage:
    python onchain_extract.py                # extract all priority charts
    python onchain_extract.py --chart mvrv_zscore  # single chart
    python onchain_extract.py --list         # list available charts
    python onchain_extract.py --force        # ignore freshness guard
    python onchain_extract.py --cron         # quiet mode for launchd
    python onchain_extract.py --dry-run      # show what would be extracted

Schedule: com.macro2.onchain-extract.plist (daily at 14:00 GMT+8 / 06:00 UTC)
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from datetime import datetime

import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(_SCRIPT_DIR, "historical_data", "onchain")
_FRESHNESS_FILE = os.path.join(_SCRIPT_DIR, "data_cache", ".onchain_extract_timestamp")
_FRESHNESS_HOURS = 20  # skip if last run < 20 hours ago

BASE_URL = "https://charts.checkonchain.com/btconchain"
REQUEST_DELAY = 2  # seconds between requests
REQUEST_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Chart registry
# ---------------------------------------------------------------------------
# merge_mode:
#   None      — single trace, use "trace" key
#   "sopr"    — merge two SOPR traces (>1 / <1)
#   "concat"  — concatenate mood-band traces
#   "all"     — extract all non-constant traces into one wide CSV

CHARTS = {
    # ── Priority 1: Core regime metrics (proven working) ──
    "mvrv_zscore": {
        "url": f"{BASE_URL}/unrealised/mvrv_all_zscore/mvrv_all_zscore_light.html",
        "trace": "MVRV Z-Score",
        "output": "mvrv_zscore.csv",
        "column": "mvrv_zscore",
    },
    "sth_sopr": {
        "url": f"{BASE_URL}/realised/sthsopr_indicator/sthsopr_indicator_light.html",
        "traces": ["STH-SOPR > 1", "STH-SOPR < 1"],
        "output": "sth_sopr.csv",
        "column": "sth_sopr",
        "merge_mode": "sopr",
    },
    "nupl": {
        "url": f"{BASE_URL}/unrealised/nupl/nupl_light.html",
        "traces": ["Euphoria-Greed", "Belief-Denial", "Optimism", "Hope-Fear", "Capitulation"],
        "output": "nupl.csv",
        "column": "nupl",
        "merge_mode": "concat",
    },
    "nvt_premium": {
        "url": f"{BASE_URL}/pricing/pricing_nvtprice/pricing_nvtprice_light.html",
        "trace": "Coinblock NVT Premium",
        "output": "nvt_premium.csv",
        "column": "coinblock_nvt_premium",
    },
    "lth_mvrv": {
        "url": f"{BASE_URL}/unrealised/mvrv_lth/mvrv_lth_light.html",
        "trace": "LTH-MVRV",
        "output": "lth_mvrv.csv",
        "column": "lth_mvrv",
    },
    "lth_sopr": {
        "url": f"{BASE_URL}/unrealised/mvrv_lth/mvrv_lth_light.html",
        "trace": "LTH-SOPR",
        "output": "lth_sopr.csv",
        "column": "lth_sopr",
    },
    "lth_aviv": {
        "url": f"{BASE_URL}/unrealised/mvrv_lth/mvrv_lth_light.html",
        "trace": "LTH-AVIV",
        "output": "lth_aviv.csv",
        "column": "lth_aviv",
    },
    "realised_price": {
        "url": f"{BASE_URL}/unrealised/mvrv_all_zscore/mvrv_all_zscore_light.html",
        "trace": "Realised Price",
        "output": "realised_price.csv",
        "column": "realised_price",
    },
}

# ---------------------------------------------------------------------------
# Core extraction engine
# ---------------------------------------------------------------------------

def _decode_y_data(y_raw):
    """Decode Plotly y-axis data (base64 binary or plain list)."""
    if isinstance(y_raw, dict) and "bdata" in y_raw:
        dtype_map = {"f8": np.float64, "f4": np.float32, "i4": np.int32, "i8": np.int64}
        np_dtype = dtype_map.get(y_raw.get("dtype", "f8"), np.float64)
        raw = base64.b64decode(y_raw["bdata"])
        return np.frombuffer(raw, dtype=np_dtype)
    elif isinstance(y_raw, list):
        return np.array(y_raw, dtype=float)
    return None


def _is_constant_trace(y_arr, tol=1e-10):
    """Check if a trace is a constant band line (e.g. threshold at 1.0)."""
    finite = y_arr[np.isfinite(y_arr)]
    if len(finite) == 0:
        return True
    return np.ptp(finite) < tol


def extract_traces(url):
    """Fetch a CheckOnChain chart and return {trace_name: DataFrame}.

    Each DataFrame has columns: date, <trace_name>.
    """
    r = requests.get(url, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()

    match = re.search(
        r'Plotly\.newPlot\(\s*"[^"]+"\s*,\s*(\[.*?\])\s*,\s*\{',
        r.text, re.DOTALL,
    )
    if not match:
        raise ValueError(f"No Plotly.newPlot data found in {url}")

    traces = json.loads(match.group(1))
    results = {}

    for i, trace in enumerate(traces):
        name = trace.get("name", f"trace_{i}")
        if not name or name.startswith("trace_"):
            continue

        x = trace.get("x", [])
        y_raw = trace.get("y", {})

        try:
            y = _decode_y_data(y_raw)
        except Exception:
            continue

        if y is None or len(x) != len(y):
            continue

        if _is_constant_trace(y):
            continue

        df = pd.DataFrame({"date": pd.to_datetime(x), name: y})
        df[name] = df[name].replace([np.inf, -np.inf], np.nan)
        results[name] = df

    return results


# ---------------------------------------------------------------------------
# Merge helpers (special chart types)
# ---------------------------------------------------------------------------

def _merge_sopr(traces, trace_names, column):
    """Merge two SOPR traces (>1 and <1) into one series.

    Each day only has a value in one of the two traces. The other trace
    shows 1.0 (the threshold). Take the non-1.0 value.
    """
    dfs = []
    for tn in trace_names:
        if tn in traces:
            df = traces[tn].rename(columns={tn: column})
            dfs.append(df)
    if not dfs:
        return None

    merged = dfs[0]
    for df in dfs[1:]:
        merged = pd.merge(merged, df, on="date", how="outer", suffixes=("", "_other"))

    # When there are two value columns, pick the non-1.0 one
    cols = [c for c in merged.columns if c != "date"]
    if len(cols) == 2:
        c1, c2 = cols
        merged[column] = merged.apply(
            lambda row: row[c2] if (pd.isna(row[c1]) or abs(row[c1] - 1.0) < 1e-6) else row[c1],
            axis=1,
        )
        merged = merged[["date", column]]
    elif len(cols) == 1 and cols[0] != column:
        merged = merged.rename(columns={cols[0]: column})

    return merged.sort_values("date").reset_index(drop=True)


def _merge_concat(traces, trace_names, column):
    """Concatenate mood-band traces (NUPL style) into one series."""
    dfs = []
    for tn in trace_names:
        if tn in traces:
            df = traces[tn].rename(columns={tn: column})
            dfs.append(df)
    if not dfs:
        return None
    merged = pd.concat(dfs, ignore_index=True)
    merged = merged.sort_values("date").reset_index(drop=True)
    # Drop duplicates — some mood boundaries overlap
    merged = merged.drop_duplicates(subset="date", keep="first")
    return merged


def _merge_all(traces, column=None):
    """Merge all non-constant traces into a single wide DataFrame."""
    if not traces:
        return None
    dfs = list(traces.values())
    merged = dfs[0]
    for df in dfs[1:]:
        merged = pd.merge(merged, df, on="date", how="outer")
    return merged.sort_values("date").reset_index(drop=True)


# ---------------------------------------------------------------------------
# Single-chart extraction
# ---------------------------------------------------------------------------

def extract_chart(chart_key, config, quiet=False):
    """Extract one chart and return a DataFrame (or None on failure)."""
    url = config["url"]
    merge_mode = config.get("merge_mode")
    column = config.get("column", chart_key)

    if not quiet:
        print(f"  Fetching {chart_key} ... ", end="", flush=True)

    try:
        traces = extract_traces(url)
    except Exception as e:
        if not quiet:
            print(f"FAILED ({e})")
        return None

    if not traces:
        if not quiet:
            print("FAILED (no traces found)")
        return None

    # Apply merge strategy
    if merge_mode == "sopr":
        df = _merge_sopr(traces, config["traces"], column)
    elif merge_mode == "concat":
        df = _merge_concat(traces, config["traces"], column)
    elif merge_mode == "all":
        df = _merge_all(traces, column)
    else:
        # Single trace extraction
        trace_name = config.get("trace")
        if trace_name and trace_name in traces:
            df = traces[trace_name].rename(columns={trace_name: column})
        elif trace_name:
            # Try case-insensitive / partial match
            match = None
            for tn in traces:
                if trace_name.lower() in tn.lower():
                    match = tn
                    break
            if match:
                df = traces[match].rename(columns={match: column})
            else:
                if not quiet:
                    available = list(traces.keys())
                    print(f"FAILED (trace '{trace_name}' not found, available: {available})")
                return None
        else:
            # No trace specified — use first non-constant trace
            df = list(traces.values())[0]

    if df is None or df.empty:
        if not quiet:
            print("FAILED (empty result)")
        return None

    # Normalize date to date-only (no time component)
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df = df.drop_duplicates(subset="date", keep="last")
    df = df.sort_values("date").reset_index(drop=True)

    if not quiet:
        latest = df["date"].max().strftime("%Y-%m-%d")
        print(f"OK ({len(df)} rows, latest={latest})")

    return df


# ---------------------------------------------------------------------------
# Freshness guard
# ---------------------------------------------------------------------------

def _check_freshness(force=False):
    """Return True if extraction should proceed."""
    if force:
        return True
    try:
        if os.path.exists(_FRESHNESS_FILE):
            mtime = os.path.getmtime(_FRESHNESS_FILE)
            age_hours = (time.time() - mtime) / 3600
            if age_hours < _FRESHNESS_HOURS:
                return False
    except OSError:
        pass
    return True


def _update_freshness():
    """Touch the freshness file."""
    os.makedirs(os.path.dirname(_FRESHNESS_FILE), exist_ok=True)
    with open(_FRESHNESS_FILE, "w") as f:
        f.write(datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Main extraction loop
# ---------------------------------------------------------------------------

def extract_all(charts=None, force=False, quiet=False, dry_run=False):
    """Extract all (or specified) charts and save to CSV.

    Returns dict of {chart_key: row_count} for successful extractions.
    """
    chart_registry = charts if charts else CHARTS
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if dry_run:
        for key, cfg in chart_registry.items():
            print(f"  Would extract: {key} -> {cfg.get('output', key + '.csv')}")
        return {}

    if not _check_freshness(force):
        if not quiet:
            print("Skipping — last extraction was less than 20 hours ago. Use --force to override.")
        return {}

    # Group by URL to avoid re-fetching the same page
    url_cache = {}
    results = {}
    total = len(chart_registry)

    for idx, (key, cfg) in enumerate(chart_registry.items(), 1):
        url = cfg["url"]

        # Rate-limit between distinct URLs
        if url not in url_cache and idx > 1:
            time.sleep(REQUEST_DELAY)

        if not quiet:
            print(f"[{idx}/{total}] ", end="")

        df = extract_chart(key, cfg, quiet=quiet)

        if df is not None:
            output_file = os.path.join(OUTPUT_DIR, cfg.get("output", f"{key}.csv"))
            df.to_csv(output_file, index=False)
            results[key] = len(df)
        else:
            results[key] = 0

    _update_freshness()
    return results


def verify_data(quiet=False):
    """Verify extracted data freshness and integrity."""
    if not os.path.isdir(OUTPUT_DIR):
        print("No data directory found.")
        return

    yesterday = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    stale_threshold = yesterday - pd.Timedelta(days=3)

    for key, cfg in CHARTS.items():
        output_file = os.path.join(OUTPUT_DIR, cfg.get("output", f"{key}.csv"))
        if not os.path.exists(output_file):
            print(f"  MISSING  {key}")
            continue
        try:
            df = pd.read_csv(output_file)
            df["date"] = pd.to_datetime(df["date"])
            latest = df["date"].max()
            stale = latest < stale_threshold
            status = "STALE" if stale else "OK"
            icon = "\u26a0\ufe0f" if stale else "\u2705"
            if not quiet:
                print(f"  {icon} {status:6s} {key:20s} {len(df):>6,} rows  latest={latest.date()}")
        except Exception as e:
            print(f"  ERROR  {key}: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract CheckOnChain on-chain BTC data")
    parser.add_argument("--chart", help="Extract a single chart by key")
    parser.add_argument("--list", action="store_true", help="List available charts")
    parser.add_argument("--force", action="store_true", help="Ignore freshness guard")
    parser.add_argument("--cron", action="store_true", help="Quiet mode for launchd")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be extracted")
    parser.add_argument("--verify", action="store_true", help="Verify data freshness")
    args = parser.parse_args()

    if args.list:
        print("Available charts:")
        for key, cfg in CHARTS.items():
            print(f"  {key:25s} -> {cfg.get('output', key + '.csv')}")
        return

    if args.verify:
        print("Verifying on-chain data:")
        verify_data(quiet=args.cron)
        return

    quiet = args.cron

    if not quiet:
        print(f"CheckOnChain extraction — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Output: {OUTPUT_DIR}")
        print()

    if args.chart:
        if args.chart not in CHARTS:
            print(f"Unknown chart: {args.chart}. Use --list to see available charts.")
            sys.exit(1)
        charts = {args.chart: CHARTS[args.chart]}
    else:
        charts = CHARTS

    results = extract_all(
        charts=charts,
        force=args.force,
        quiet=quiet,
        dry_run=args.dry_run,
    )

    if results and not quiet:
        ok = sum(1 for v in results.values() if v > 0)
        total = len(results)
        print(f"\nDone: {ok}/{total} charts extracted successfully.")
        if ok < total:
            failed = [k for k, v in results.items() if v == 0]
            print(f"Failed: {', '.join(failed)}")


if __name__ == "__main__":
    main()
