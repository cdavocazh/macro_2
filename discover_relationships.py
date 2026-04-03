"""
Discover non-trivial statistical relationships between macro indicators
using OmniOracle's Mutual Information pipeline on our historical data.

Usage: python discover_relationships.py
"""
import sys
import os
import warnings
import pandas as pd
import numpy as np
from pathlib import Path
from itertools import combinations

warnings.filterwarnings("ignore")

# Add omni-oracle to path
OMNI_ROOT = Path(__file__).resolve().parent.parent / "omni-oracle"
sys.path.insert(0, str(OMNI_ROOT))

from src.discovery.mi_screening import compute_mi_with_pvalue, MIResult
from src.discovery.lagged_mi import detect_direction_lagged_mi
from src.validation.fdr import benjamini_hochberg
from src.validation.temporal_oos import validate_oos

HIST_DIR = Path(__file__).resolve().parent / "historical_data"

# Curated list of single-value time series CSVs and their value columns
# (skip OHLCV, multi-column, and summary files)
SERIES_MAP = {
    # Rates & yields
    "10y_treasury_yield": "us_10y_yield",
    "us_2y_yield": "us_2y_yield",
    "us_5y_yield": "us_5y_yield",
    "us_30y_yield": "us_30y_yield",
    "japan_2y_yield": "japan_2y_yield",
    "fed_funds_rate": "fed_funds_rate",
    "fed_funds_effective": "fed_funds_effective",
    "sofr": "sofr",
    "real_yield_10y": "real_yield_10y",
    "real_yield_5y": "real_yield_5y",
    "breakeven_10y": "breakeven_10y",
    "breakeven_5y": "breakeven_5y",
    "forward_inflation_5y5y": "forward_inflation_5y5y",
    "spread_10y3m": "spread_10y3m",
    "us2y_jp2y_spread": "us2y_jp2y_spread",
    "mortgage_rate_30y": "mortgage_rate_30y",
    "treasury_term_premia": "treasury_term_premia",

    # Credit
    "hy_oas": "hy_oas",
    "ig_oas": "ig_oas",
    "bbb_oas": "bbb_oas",
    "corporate_spreads_aaa": "corporate_spreads_aaa",
    "corporate_spreads_bbb": "corporate_spreads_bbb",
    "nfci": "nfci",

    # Equity & volatility
    "dxy": "dxy",
    "jpy": "jpy",
    "cboe_skew": "cboe_skew",
    "shiller_cape": "shiller_cape",
    "sp500_ma200": "sp500_to_ma200",
    "russell_2000": "russell_2000",
    "es_futures": "es_futures",

    # Commodities
    "gold": "gold",
    "silver": "silver",
    "crude_oil": "crude_oil",
    "copper": "copper",
    "gold_price_fred": "gold_price_fred",
    "copper_price_fred": "copper_price_fred",
    "natural_gas_fred": "natural_gas_fred",
    "gold_silver_ratio": "gold_silver_ratio",
    "xau_jpy": "xau_jpy",

    # Macro
    "us_gdp": "us_gdp",
    "cpi_headline": "cpi_headline",
    "core_cpi": "core_cpi",
    "core_pce": "core_pce",
    "pce_headline": "pce_headline",
    "ppi": "ppi",
    "ism_pmi": "ism_pmi",
    "nonfarm_payrolls": "nonfarm_payrolls",
    "unemployment_rate": "unemployment_rate",
    "initial_claims": "initial_claims",
    "continuing_claims": "continuing_claims",
    "consumer_sentiment": "consumer_sentiment",
    "sahm_rule": "sahm_rule",
    "net_liquidity": "net_liquidity",
    "tga_balance": "tga_balance",
    "fed_balance_sheet": "fed_balance_sheet",

    # Housing
    "housing_starts": "housing_starts",
    "building_permits": "building_permits",
    "existing_home_sales": "existing_home_sales",
    "median_home_price": "median_home_price",
    "case_shiller_index": "case_shiller_index",

    # Labor
    "jolts_openings": "jolts_openings",
    "jolts_quits_rate": "jolts_quits_rate",
    "adp_employment": "adp_employment",

    # Other
    "gdpnow": "gdpnow",
    "wei": "wei",
    "aaii_sentiment": "aaii_sentiment",
    "equity_risk_premium": "equity_risk_premium",
    "oecd_cli": "oecd_cli",
    "vix_move": None,  # auto-detect
}


def load_series(name: str, col_hint: str | None) -> pd.Series | None:
    """Load a single time series from CSV, return as pd.Series indexed by date."""
    path = HIST_DIR / f"{name}.csv"
    if not path.exists():
        return None

    df = pd.read_csv(path)

    # Find date column
    date_col = None
    for c in ["date", "timestamp", "Date", "Timestamp"]:
        if c in df.columns:
            date_col = c
            break
    if date_col is None:
        return None

    df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=[date_col])
    df = df.set_index(date_col).sort_index()

    # Find value column
    if col_hint and col_hint in df.columns:
        val_col = col_hint
    else:
        # Pick first numeric column that isn't a timestamp
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if not numeric_cols:
            return None
        val_col = numeric_cols[0]

    series = df[val_col].dropna()
    if len(series) < 30:
        return None

    return series


def resample_monthly(series: pd.Series) -> pd.Series:
    """Resample to monthly frequency (last value of month)."""
    return series.resample("ME").last().dropna()


def align_pair(s1: pd.Series, s2: pd.Series) -> tuple[np.ndarray, np.ndarray] | None:
    """Align two series on overlapping dates, return numpy arrays."""
    combined = pd.concat([s1, s2], axis=1, join="inner").dropna()
    if len(combined) < 30:
        return None
    return combined.iloc[:, 0].values, combined.iloc[:, 1].values


def make_stationary(arr: np.ndarray) -> np.ndarray:
    """Simple first-difference to make series approximately stationary."""
    return np.diff(arr)


def main():
    print("=" * 70)
    print("MACRO INDICATOR RELATIONSHIP DISCOVERY")
    print("Using OmniOracle MI + Lagged MI + FDR + OOS Validation")
    print("=" * 70)

    # Step 1: Load all series
    print("\n[1/5] Loading historical time series...")
    raw_series = {}
    for name, col in SERIES_MAP.items():
        s = load_series(name, col)
        if s is not None:
            raw_series[name] = s

    print(f"  Loaded {len(raw_series)} series")

    # Step 2: Resample to monthly and make stationary
    print("\n[2/5] Resampling to monthly + first-differencing...")
    monthly = {}
    for name, s in raw_series.items():
        ms = resample_monthly(s)
        if len(ms) >= 36:  # need 3+ years monthly
            monthly[name] = ms

    print(f"  {len(monthly)} series with >= 36 monthly observations")

    # Step 3: MI screening on all pairs
    pairs = list(combinations(sorted(monthly.keys()), 2))
    n_pairs = len(pairs)
    print(f"\n[3/5] MI screening on {n_pairs} pairs (this may take a few minutes)...")

    mi_results = []
    for idx, (n1, n2) in enumerate(pairs):
        if idx % 500 == 0 and idx > 0:
            print(f"  ... {idx}/{n_pairs} pairs screened, {len(mi_results)} significant so far")

        aligned = align_pair(monthly[n1], monthly[n2])
        if aligned is None:
            continue

        x, y = aligned
        # First-difference both
        if len(x) < 32:
            continue
        xd = make_stationary(x)
        yd = make_stationary(y)

        if len(xd) < 24 or np.std(xd) < 1e-10 or np.std(yd) < 1e-10:
            continue

        try:
            result = compute_mi_with_pvalue(xd, yd, n_permutations=100, threshold=0.05)
            if result.significant:
                mi_results.append((n1, n2, result))
        except Exception:
            continue

    print(f"  {len(mi_results)} pairs survived MI screening (p < 0.05)")

    if not mi_results:
        print("\nNo significant pairs found. Exiting.")
        return

    # Step 4: FDR correction
    print(f"\n[4/5] Benjamini-Hochberg FDR correction (alpha=0.05)...")
    pvalues = [r[2].pvalue for r in mi_results]
    fdr_mask = benjamini_hochberg(pvalues, alpha=0.05)
    fdr_pairs = [mi_results[i] for i in range(len(mi_results)) if fdr_mask[i]]
    print(f"  {len(fdr_pairs)} pairs survive FDR correction")

    if not fdr_pairs:
        print("\nNo pairs survived FDR. Showing top MI pairs anyway:")
        fdr_pairs = sorted(mi_results, key=lambda x: -x[2].mi)[:30]

    # Step 5: Lagged MI direction + OOS validation on FDR survivors
    print(f"\n[5/5] Lagged MI directional analysis + OOS validation on {len(fdr_pairs)} pairs...")
    discoveries = []

    for idx, (n1, n2, mi_res) in enumerate(fdr_pairs):
        aligned = align_pair(monthly[n1], monthly[n2])
        if aligned is None:
            continue
        x, y = aligned
        xd = make_stationary(x)
        yd = make_stationary(y)

        if len(xd) < 30:
            continue

        try:
            lag_result = detect_direction_lagged_mi(
                xd, yd, max_lag=6, n_permutations=100, threshold=0.05
            )
        except Exception:
            continue

        # OOS validation
        oos_r2 = 0.0
        oos_valid = False
        if lag_result.direction != "none":
            try:
                oos = validate_oos(xd, yd, lag=lag_result.best_lag, train_ratio=0.7)
                oos_r2 = oos.r2_incremental
                oos_valid = oos.valid
            except Exception:
                pass

        discoveries.append({
            "x": n1,
            "y": n2,
            "mi": mi_res.mi,
            "mi_pvalue": mi_res.pvalue,
            "direction": lag_result.direction,
            "best_lag": lag_result.best_lag,
            "dir_pvalue": lag_result.best_pvalue,
            "oos_r2": oos_r2,
            "oos_valid": oos_valid,
        })

    # Sort by MI strength
    discoveries.sort(key=lambda d: -d["mi"])

    # Print results
    print("\n" + "=" * 70)
    print("RESULTS: Discovered Relationships")
    print("=" * 70)

    # Separate directional from non-directional
    directional = [d for d in discoveries if d["direction"] != "none"]
    validated = [d for d in directional if d["oos_valid"]]

    print(f"\nTotal significant pairs: {len(discoveries)}")
    print(f"Directional (lagged MI): {len(directional)}")
    print(f"OOS validated (R2 > 0.02): {len(validated)}")

    if validated:
        print("\n--- OOS-VALIDATED DIRECTIONAL RELATIONSHIPS ---")
        print(f"{'X → Y':<55} {'Dir':>4} {'Lag':>3} {'MI':>6} {'OOS R²':>7} {'p-val':>7}")
        print("-" * 90)
        for d in sorted(validated, key=lambda x: -x["oos_r2"]):
            if d["direction"] == "x->y":
                label = f"{d['x']} → {d['y']}"
            elif d["direction"] == "y->x":
                label = f"{d['y']} → {d['x']}"
            else:
                label = f"{d['x']} ↔ {d['y']}"
            print(f"{label:<55} {d['direction']:>4} {d['best_lag']:>3}m {d['mi']:>6.3f} {d['oos_r2']:>7.3f} {d['dir_pvalue']:>7.4f}")

    if directional:
        print("\n--- ALL DIRECTIONAL RELATIONSHIPS (top 40) ---")
        print(f"{'X → Y':<55} {'Dir':>4} {'Lag':>3} {'MI':>6} {'OOS R²':>7} {'p-val':>7}")
        print("-" * 90)
        for d in sorted(directional, key=lambda x: -x["mi"])[:40]:
            if d["direction"] == "x->y":
                label = f"{d['x']} → {d['y']}"
            elif d["direction"] == "y->x":
                label = f"{d['y']} → {d['x']}"
            else:
                label = f"{d['x']} ↔ {d['y']}"
            valid_mark = " ✓" if d["oos_valid"] else ""
            print(f"{label:<55} {d['direction']:>4} {d['best_lag']:>3}m {d['mi']:>6.3f} {d['oos_r2']:>7.3f} {d['dir_pvalue']:>7.4f}{valid_mark}")

    # Also show top non-directional (contemporaneous) relationships
    contemp = [d for d in discoveries if d["direction"] == "none"]
    if contemp:
        print(f"\n--- TOP CONTEMPORANEOUS CORRELATIONS (no lag, top 20) ---")
        print(f"{'Pair':<55} {'MI':>6} {'p-val':>7}")
        print("-" * 70)
        for d in sorted(contemp, key=lambda x: -x["mi"])[:20]:
            print(f"{d['x']} ↔ {d['y']:<30} {d['mi']:>6.3f} {d['mi_pvalue']:>7.4f}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    main()
