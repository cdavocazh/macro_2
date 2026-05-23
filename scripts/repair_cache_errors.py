#!/usr/bin/env python3
"""Self-healing FRED cache repair script.

Scans data_cache/all_indicators.json for indicators in error state and
re-fetches them with exponential backoff. Idempotent — does nothing if
the cache is healthy. Safe to run as often as desired (every 5-15 min).

Designed to be resilient against FRED API rate-limits that occasionally
cause Internal Server Error during bulk extractions.
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, "/root/macro_2")

from data_extractors.fred_extractors import (
    get_fed_funds_rate,
    get_hy_credit_spread,
    get_nfci,
    get_real_yield_10y,
    get_breakeven_inflation,
    get_ig_credit_spread,
    get_sahm_rule,
    get_m2_money_supply,
    get_jolts_openings,
    get_continuing_claims,
    get_retail_sales,
    get_headline_cpi,
    get_bank_reserves,
    get_industrial_production,
    calculate_sp500_marketcap_to_gdp,
    get_tga_balance,
    get_fed_net_liquidity,
    get_housing_starts,
    get_ppi,
    get_sofr,
    get_ism_pmi,
    get_5y_treasury_yield,
)
from data_extractors.yield_curve_extractor import get_yield_curve_data
from data_extractors.japan_yield_extractor import get_us2y_jp2y_spread
from data_extractors import openbb_extractors

CACHE = "/root/macro_2/data_cache/all_indicators.json"

# All indicators that can be repaired via FRED re-fetch
REPAIRABLE = {
    "34_hy_oas": get_hy_credit_spread,
    "36_real_yield": get_real_yield_10y,
    "37_nfci": get_nfci,
    "33_yield_curve": get_yield_curve_data,
    "35_breakeven_inflation": get_breakeven_inflation,
    "45_ig_oas": get_ig_credit_spread,
    "46_sahm_rule": get_sahm_rule,
    "47_m2": get_m2_money_supply,
    "48_jolts": get_jolts_openings,
    "49_continuing_claims": get_continuing_claims,
    "50_retail_sales": get_retail_sales,
    "53_headline_cpi": get_headline_cpi,
    "58_bank_reserves": get_bank_reserves,
    "59_industrial_production": get_industrial_production,
    "6b_marketcap_to_gdp": calculate_sp500_marketcap_to_gdp,
    "23_tga_balance": get_tga_balance,
    "24_net_liquidity": get_fed_net_liquidity,
    "25_sofr": get_sofr,
    "38_fed_funds": get_fed_funds_rate,
    "28_us2y_jp2y_spread": get_us2y_jp2y_spread,
    "51_housing_starts": get_housing_starts,
    "52_ppi": get_ppi,
    "81_global_pmi": openbb_extractors.get_global_pmi,
    "12_ism_pmi": get_ism_pmi,
    "61_5y_yield": get_5y_treasury_yield,
}


def _ser(v):
    import pandas as pd
    if isinstance(v, pd.Series):
        return {
            "__type__": "pd.Series",
            "index": [str(i) for i in v.index],
            "values": v.tolist(),
        }
    if isinstance(v, pd.DataFrame):
        return {
            "__type__": "pd.DataFrame",
            "index": [str(i) for i in v.index],
            "columns": list(v.columns),
            "data": v.values.tolist(),
        }
    if isinstance(v, dict):
        return {k: _ser(vv) for k, vv in v.items()}
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _try_fetch(fn, max_retries=3, base_delay=3.0):
    last_err = None
    for attempt in range(max_retries):
        try:
            result = fn()
            if "error" in result:
                err = str(result.get("error", ""))
                if any(x in err for x in ["Internal Server Error", "503", "504", "rate"]):
                    last_err = err
                    time.sleep(base_delay * (attempt + 1))
                    continue
                return result
            return result
        except Exception as e:
            last_err = str(e)
            time.sleep(base_delay * (attempt + 1))
    return {"error": f"After {max_retries} retries: {last_err}"}


def main():
    ts = datetime.now().isoformat(timespec="seconds")
    try:
        with open(CACHE) as f:
            d = json.load(f)
    except Exception as e:
        print(f"[{ts}] Cannot read cache: {e}")
        return 1

    data = d.get("data", {})

    # Find errored keys that we know how to fix
    errored = []
    for key in REPAIRABLE:
        v = data.get(key)
        if isinstance(v, dict) and "error" in v:
            errored.append(key)

    if not errored:
        print(f"[{ts}] Cache healthy — no repair needed")
        return 0

    print(f"[{ts}] Repairing {len(errored)} errored indicators: {errored}")

    updated = 0
    for key in errored:
        fn = REPAIRABLE[key]
        result = _try_fetch(fn)
        if "error" not in result:
            d["data"][key] = _ser(result)
            updated += 1
            print(f"  FIXED: {key}")
        else:
            err = result.get("error", "")
            print(f"  STILL FAILS: {key} -> {err[:120]}")

    if updated > 0:
        d["timestamp"] = datetime.now().isoformat()
        # Atomic write
        tmp = CACHE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(d, f, default=str)
        os.replace(tmp, CACHE)

    print(f"[{ts}] Repaired: {updated}/{len(errored)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
