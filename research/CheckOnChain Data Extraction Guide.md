# CheckOnChain Data Extraction Guide

> **Purpose**: Instructions for scraping on-chain BTC data from [charts.checkonchain.com](https://charts.checkonchain.com) for use in market regime detection and trading strategy optimization.
> **Frequency**: Daily (charts updated daily)
> **Related**: See `Commute/BTC Regime Detection - Detailed Session Record` for context on how this data is used.

---

## Site Overview

CheckOnChain provides **539 Plotly-based charts across 19 categories** of Bitcoin on-chain data. All charts are static HTML files with embedded Plotly.js data — no authentication required. Data is encoded as base64 float64 arrays in the Plotly trace objects.

**Base URL**: `https://charts.checkonchain.com/btconchain/`
**Chart format**: `{category}/{chart_name}/{chart_name}_light.html`
**Robots.txt**: `Allow: /` (scraping permitted)

---

## Extraction Method (Proven Working)

All charts use the same Plotly embedded data format. The extraction pattern that works:

```python
import requests, json, re, pandas as pd, numpy as np, base64

def extract_checkonchain(url):
    """Extract all data traces from a CheckOnChain Plotly chart.
    
    Returns dict of {trace_name: DataFrame} with date + values columns.
    """
    r = requests.get(url, timeout=30)
    text = r.text
    
    # Find the Plotly.newPlot call containing all trace data
    match = re.search(
        r'Plotly\.newPlot\(\s*"[^"]+"\s*,\s*(\[.*?\])\s*,\s*\{', 
        text, re.DOTALL
    )
    if not match:
        return {}
    
    traces = json.loads(match.group(1))
    results = {}
    
    for i, trace in enumerate(traces):
        name = trace.get("name", f"trace_{i}")
        x = trace.get("x", [])
        y_raw = trace.get("y", {})
        
        # Decode binary data format
        if isinstance(y_raw, dict) and "bdata" in y_raw:
            dtype_map = {"f8": np.float64, "f4": np.float32, "i4": np.int32}
            np_dtype = dtype_map.get(y_raw["dtype"], np.float64)
            try:
                raw = base64.b64decode(y_raw["bdata"])
                y = np.frombuffer(raw, dtype=np_dtype)
            except (ValueError, Exception):
                continue
        elif isinstance(y_raw, list):
            y = np.array(y_raw, dtype=float)
        else:
            continue
        
        if len(x) == len(y) and name:
            df = pd.DataFrame({"date": pd.to_datetime(x), name: y})
            df[name] = df[name].replace([np.inf, -np.inf], np.nan)
            results[name] = df
    
    return results
```

### Key Implementation Notes

1. **Y-data encoding**: Values are stored as `{"dtype": "f8", "bdata": "base64string"}` where `f8` = float64. Must decode with `base64.b64decode()` then `np.frombuffer()`.
2. **NaN handling**: Missing values encoded as ±inf, replace with `np.nan`.
3. **Multi-trace charts**: Many charts have multiple traces (e.g., MVRV has Price, Realised Price, Z-Score, and band lines). Filter by trace name.
4. **Constant traces**: Band lines (e.g., "0.94", "1.02" for SOPR thresholds) have constant values — skip these.
5. **Some traces have mismatched buffer sizes** — wrap in try/except (e.g., LTH chart profit bands fail to decode).

---

## Priority 1: Currently Extracted Data (Already Working)

These charts have been successfully scraped and are saved in `market_regime_data/data/`:

| Chart | URL Suffix | Trace to Extract | Output File | Rows | Coverage |
|-------|-----------|-----------------|-------------|------|----------|
| MVRV Z-Score | `unrealised/mvrv_all_zscore/mvrv_all_zscore_light.html` | "MVRV Z-Score" | `mvrv_zscore.csv` | 4,828 | 2013-01 → 2026-03 |
| STH-SOPR | `realised/sthsopr_indicator/sthsopr_indicator_light.html` | "STH-SOPR > 1" + "STH-SOPR < 1" (merge) | `sth_sopr.csv` | 6,284 | 2009-01 → 2026-03 |
| NUPL | `unrealised/nupl/nupl_light.html` | All mood traces (merge) | `nupl.csv` | 5,734 | 2010-07 → 2026-03 |
| NVT Premium | `pricing/pricing_nvtprice/pricing_nvtprice_light.html` | "Coinblock NVT Premium" | `checkonchain_coinblock_nvt_premium.csv` | 3,830 | 2015-09 → 2026-03 |
| LTH-MVRV | `unrealised/mvrv_lth/mvrv_lth_light.html` | "LTH-MVRV" | `lth_mvrv.csv` | 4,829 | 2013-01 → 2026-03 |
| LTH-SOPR | (same chart as above) | "LTH-SOPR" | `lth_sopr.csv` | 4,829 | 2013-01 → 2026-03 |
| LTH-AVIV | (same chart as above) | "LTH-AVIV" | `lth_aviv.csv` | 4,829 | 2013-01 → 2026-03 |
| Realised Price | (same as MVRV Z-Score) | "Realised Price" | `checkonchain_realised_price.csv` | 6,283 | 2009-01 → 2026-03 |

### Special Handling Notes

**STH-SOPR**: Split into two traces ("STH-SOPR > 1" and "STH-SOPR < 1"). Merge by taking the non-1.0 value from each day — when SOPR > 1, use the "> 1" trace; when < 1, use the "< 1" trace.

**NUPL**: Split into 5 mood-category traces ("Euphoria-Greed", "Belief-Denial", "Optimism", "Hope-Fear", "Capitulation"). Each trace only has values for days in that mood. Concatenate all traces and sort by date to reconstruct the full series.

---

## Priority 2: High-Value Charts for Regime Detection (Extract Next)

These charts contain leading indicators identified in research as high-priority for regime detection:

### Derivatives Category (57 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `derivatives_futures_fundingrate` | Aggregated funding rate | Extreme positive → overcrowded longs → BEAR/DIST warning | 🔴 HIGH |
| `derivatives_btc_liquidations` | Long/short liquidation volumes | Cascade events → CRASH confirmation | 🔴 HIGH |
| `derivatives_futures_oi_byexchange_0` | OI by exchange | OI/price divergence → leverage buildup → crash risk | 🔴 HIGH |
| `derivatives_spotvolume_cvd_0` | Spot Cumulative Volume Delta | CVD diverging from price → distribution signal | 🟡 MEDIUM |
| `leverageratio_0` | Estimated leverage ratio | High leverage → fragility → crash risk | 🟡 MEDIUM |
| `fundingrate_zscore` | Funding rate Z-score (normalized) | Z > 2 → crash warning, Z < -2 → bottom signal | 🟡 MEDIUM |
| `options_putcallratio` | Options put/call ratio | Rising P/C → hedging demand → bearish | 🟡 MEDIUM |
| `options_atmimpliedvolatility` | ATM implied volatility | Vol spike → regime change | 🟢 NICE |
| `etf_cashcarry` | ETF basis/cash-and-carry spread | Basis collapse → institutional demand drying | 🟢 NICE |
| `derivatives_termstructure_0` | Futures term structure | Backwardation → extreme stress / bottoming | 🟢 NICE |

### Supply Category (67 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `lthnetposchange_0` | LTH net position change | Negative → LTH distributing → DISTRIBUTION | 🔴 HIGH |
| `distribution_netposchange_30` | 30d supply net position change by cohort | Whale selling → distribution phase | 🔴 HIGH |
| `distribution_whalexchange_30` | Whale-to-exchange flows (30d) | Whale deposits to exchange → sell pressure | 🔴 HIGH |
| `hodl_waves_0` | HODL waves (supply age bands) | Old coins moving → distribution cycle top | 🟡 MEDIUM |
| `breakdown_lthsth_0` | LTH vs STH supply breakdown | LTH supply declining → distribution | 🟡 MEDIUM |
| `distribution_absorptionrate_30` | Supply absorption rate | Low absorption → weak demand → bearish | 🟡 MEDIUM |

### Realised Category (34 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `sellsideriskratio_all` | Sell-side risk ratio | High ratio → sellers exhausted → bottoming | 🔴 HIGH |
| `realisedpnl_ratio_all` | Realised P&L ratio | Declining from high → distribution | 🟡 MEDIUM |
| `netrealisedpnl` | Net realised P&L (USD) | Large negative → capitulation → CRASH bottom | 🟡 MEDIUM |
| `sopr_fundingrate` | SOPR + funding rate overlay | Combined signal strength | 🟡 MEDIUM |
| `sopr_zscore` | SOPR Z-score | Normalized extremes | 🟢 NICE |

### Unrealised Category (55 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `mvrv_sth` | STH-MVRV | STH-MVRV > 1.33 → local top; < 0.8 → capitulation | 🔴 HIGH |
| `mvrv_sth_zscore` | STH-MVRV Z-score | Normalized extreme readings | 🔴 HIGH |
| `pctsupplyinprofit_all` | % supply in profit | > 95% → euphoria/top; < 50% → capitulation | 🟡 MEDIUM |
| `sthcostbasis_delta` | STH cost basis vs price delta | Price below STH cost basis → bear confirmed | 🟡 MEDIUM |
| `sthmvrv_indicator` | STH-MVRV oscillator | Buy/sell signal indicator | 🟡 MEDIUM |
| `seller_exhaustion_constant_supply` | Seller exhaustion metric | High exhaustion → bottoming signal | 🟡 MEDIUM |
| `supply_profitloss_ratio_sth` | STH supply profit/loss ratio | Extreme readings → regime change | 🟢 NICE |

### Confluence Category (5 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `confluence_cycleextremeoscillators_0` | Combined cycle extreme indicators | Multi-metric confluence → high-confidence regime signal | 🔴 HIGH |
| `confluence_onchainactivity` | On-chain activity confluence | Activity diverging from price → regime warning | 🟡 MEDIUM |

### Demand Category (10 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `rcapliquiditycycle` | Realised cap liquidity cycle | Capital flowing in/out → regime driver | 🔴 HIGH |
| `multipliereffect` | Capital multiplier effect | High multiplier → euphoria; low → bear | 🟡 MEDIUM |

### Stablecoins Category (8 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `stablecoins_ssr` | Stablecoin Supply Ratio | Low SSR → high buying power → bullish | 🟡 MEDIUM |
| `stablecoins_ssr_oscillator` | SSR oscillator | Normalized SSR signal | 🟡 MEDIUM |
| `stablecoin_netposchange_30` | 30d stablecoin net position change | Growing → capital inflows → bullish | 🟡 MEDIUM |

### Lifespan Category (12 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `reserverisk` | Reserve risk indicator | Low → high confidence hodlers → accumulation | 🟡 MEDIUM |
| `vddmultiple` | Value Days Destroyed multiple | High → old coins moving → distribution/top | 🟡 MEDIUM |
| `binarycdd_zscore` | Binary CDD Z-score | Extreme readings → regime change | 🟢 NICE |

### ETFs Category (18 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `etf_flows_0` | Daily ETF net flows | Sustained outflows → bearish; inflows → bullish | 🔴 HIGH |
| `etf_cumflows` | Cumulative ETF flows | Trend direction of institutional capital | 🟡 MEDIUM |
| `etf_mvrv` | ETF MVRV (ETF holder unrealized P&L) | ETF holders underwater → sell pressure | 🟡 MEDIUM |

### Mining Category (11 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `hashribbons` | Hash ribbons (30/60 MA crossover) | Death cross → miner capitulation → bear bottom | 🟡 MEDIUM |
| `puellmultiple` | Puell multiple | > 4 → overvalued; < 0.5 → undervalued | 🟢 NICE |
| `miningpulse` | Mining pulse | Hashrate acceleration/deceleration | 🟢 NICE |

### TradFi Category (33 charts)

| Chart | What It Contains | Regime Signal | Priority |
|-------|-----------------|---------------|----------|
| `correlations_btc_30` | 30d BTC correlations vs assets | Correlation regime shifts | 🟡 MEDIUM |
| `usdollarstrength` | USD strength index | Dollar strength → BTC weakness | 🟡 MEDIUM |

---

## Priority 3: All Available Categories (Complete Index)

| Category | Charts | Description |
|----------|--------|-------------|
| adoption | 21 | Active addresses, fees, inscriptions, transfer volumes |
| capitalrotation | 14 | Cross-asset capital rotation, Sharpe/Sortino ratios |
| cointime | 24 | Cointime economics: liveliness, vaulting, HODL behavior |
| confluence | 5 | Multi-metric confluence indicators |
| demand | 10 | Capital inflows, multiplier effect, liquidity cycles |
| derivatives | 57 | Futures OI/volume/funding, options P/C/IV/skew, liquidations |
| entities | 44 | MSTR, ETF entities, institutional stacking |
| etfs | 18 | ETF flows, balances, MVRV, volume |
| lifespan | 12 | CDD, reserve risk, VDD multiple |
| mining | 11 | Hashrate, difficulty, miner revenue, Puell |
| premium | 18 | URPD heatmaps, options heatmaps (may need premium) |
| pricing | 51 | MVRV bands, Mayer multiple, NVT, power law, drawdowns |
| realised | 34 | SOPR variants, realised P&L, sell-side risk |
| stablecoins | 8 | SSR, stablecoin dominance, net position change |
| supply | 67 | HODL waves, LTH/STH breakdown, whale distribution, UTXO |
| technical | 37 | RSI, MACD, Bollinger, volatility, drawdown analysis |
| tradfi | 33 | Correlations, DXY, gold, equity comparisons |
| unrealised | 55 | MVRV (all/LTH/STH), NUPL, supply in profit, AVIV |
| urpd | 12 | UTXO Realized Price Distribution (heatmaps) |
| **TOTAL** | **539** | |

---

## Daily Extraction Script Template

```python
#!/usr/bin/env python3
"""
Daily CheckOnChain Data Refresh
================================
Run daily via cron/launchd to update on-chain metrics.

Usage:
    python extract_checkonchain.py           # Update all priority charts
    python extract_checkonchain.py --full     # Extract all 539 charts
    python extract_checkonchain.py --chart mvrv_zscore  # Single chart
"""

import requests, json, re, pandas as pd, numpy as np, base64, os, time
from datetime import datetime

BASE_URL = "https://charts.checkonchain.com/btconchain"
OUTPUT_DIR = "market_regime_data/data"

# Priority 1 charts (regime detection core)
PRIORITY_CHARTS = {
    "mvrv_zscore": {
        "url": f"{BASE_URL}/unrealised/mvrv_all_zscore/mvrv_all_zscore_light.html",
        "trace": "MVRV Z-Score",
        "output": "mvrv_zscore.csv",
        "column": "mvrv_zscore",
    },
    "sth_sopr": {
        "url": f"{BASE_URL}/realised/sthsopr_indicator/sthsopr_indicator_light.html",
        "traces": ["STH-SOPR > 1", "STH-SOPR < 1"],  # Merge these
        "output": "sth_sopr.csv",
        "column": "sth_sopr",
        "merge_mode": "sopr",  # Special merge logic
    },
    "nupl": {
        "url": f"{BASE_URL}/unrealised/nupl/nupl_light.html",
        "traces": ["Euphoria-Greed", "Belief-Denial", "Optimism", "Hope-Fear", "Capitulation"],
        "output": "nupl.csv",
        "column": "nupl",
        "merge_mode": "concat",  # Concatenate mood bands
    },
    "nvt_premium": {
        "url": f"{BASE_URL}/pricing/pricing_nvtprice/pricing_nvtprice_light.html",
        "trace": "Coinblock NVT Premium",
        "output": "checkonchain_coinblock_nvt_premium.csv",
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
    "realised_price": {
        "url": f"{BASE_URL}/unrealised/mvrv_all_zscore/mvrv_all_zscore_light.html",
        "trace": "Realised Price",
        "output": "checkonchain_realised_price.csv",
        "column": "realised_price",
    },
}

# Priority 2 charts (high-value additions)
PRIORITY_2_CHARTS = {
    "sth_mvrv": {
        "url": f"{BASE_URL}/unrealised/mvrv_sth/mvrv_sth_light.html",
        "trace": "STH-MVRV",
        "output": "sth_mvrv.csv",
        "column": "sth_mvrv",
    },
    "sth_mvrv_zscore": {
        "url": f"{BASE_URL}/unrealised/mvrv_sth_zscore/mvrv_sth_zscore_light.html",
        "trace": "STH-MVRV Z-Score",
        "output": "sth_mvrv_zscore.csv",
        "column": "sth_mvrv_zscore",
    },
    "lth_net_pos_change": {
        "url": f"{BASE_URL}/supply/lthnetposchange_0/lthnetposchange_0_light.html",
        "trace": "LTH Net Position Change",  # May need to check actual trace name
        "output": "lth_netposchange.csv",
        "column": "lth_netposchange",
    },
    "sellside_risk": {
        "url": f"{BASE_URL}/realised/sellsideriskratio_all/sellsideriskratio_all_light.html",
        "trace": "Sell-Side Risk Ratio",  # Check actual name
        "output": "sellside_risk_ratio.csv",
        "column": "sellside_risk",
    },
    "pct_supply_profit": {
        "url": f"{BASE_URL}/unrealised/pctsupplyinprofit_all/pctsupplyinprofit_all_light.html",
        "trace": "% Supply in Profit",  # Check actual name
        "output": "pct_supply_in_profit.csv",
        "column": "pct_supply_profit",
    },
    "confluence_oscillators": {
        "url": f"{BASE_URL}/confluence/confluence_cycleextremeoscillators_0/confluence_cycleextremeoscillators_0_light.html",
        "trace": None,  # Extract all traces
        "output": "confluence_oscillators.csv",
    },
    "reserve_risk": {
        "url": f"{BASE_URL}/lifespan/reserverisk/reserverisk_light.html",
        "trace": "Reserve Risk",  # Check actual name
        "output": "reserve_risk.csv",
        "column": "reserve_risk",
    },
    "funding_zscore": {
        "url": f"{BASE_URL}/derivatives/fundingrate_zscore/fundingrate_zscore_light.html",
        "trace": None,  # Check actual trace names
        "output": "funding_zscore.csv",
    },
    "spot_cvd": {
        "url": f"{BASE_URL}/derivatives/derivatives_spotvolume_cvd_0/derivatives_spotvolume_cvd_0_light.html",
        "trace": None,
        "output": "spot_cvd.csv",
    },
    "leverage_ratio": {
        "url": f"{BASE_URL}/derivatives/leverageratio_0/leverageratio_0_light.html",
        "trace": None,
        "output": "leverage_ratio.csv",
    },
    "rcap_liquidity": {
        "url": f"{BASE_URL}/demand/rcapliquiditycycle/rcapliquiditycycle_light.html",
        "trace": None,
        "output": "rcap_liquidity_cycle.csv",
    },
    "stablecoin_ssr": {
        "url": f"{BASE_URL}/stablecoins/stablecoins_ssr/stablecoins_ssr_light.html",
        "trace": None,
        "output": "stablecoin_ssr.csv",
    },
    "hash_ribbons": {
        "url": f"{BASE_URL}/mining/hashribbons/hashribbons_light.html",
        "trace": None,
        "output": "hash_ribbons.csv",
    },
    "whale_distribution_30d": {
        "url": f"{BASE_URL}/supply/distribution_whalexchange_30/distribution_whalexchange_30_light.html",
        "trace": None,
        "output": "whale_exchange_30d.csv",
    },
    "etf_flows": {
        "url": f"{BASE_URL}/../etfs/etf_flows_0/etf_flows_0_light.html",
        "trace": None,
        "output": "checkonchain_etf_flows.csv",
    },
}

def extract_chart(url):
    """Generic extraction — same as method proven above."""
    # ... (use the extract_checkonchain function from the Extraction Method section)
    pass

def daily_refresh():
    """Refresh all priority charts."""
    for name, config in {**PRIORITY_CHARTS, **PRIORITY_2_CHARTS}.items():
        print(f"Extracting {name}...")
        # ... extract and save
        time.sleep(2)  # Rate limit: 2s between requests

if __name__ == "__main__":
    daily_refresh()
```

---

## LaunchD / Cron Setup (macOS)

### Cron (simple)
```bash
# Run daily at 6:00 AM UTC (2:00 PM SGT)
0 6 * * * cd /path/to/repo && python market_regime_data/extract_checkonchain.py >> logs/checkonchain.log 2>&1
```

### LaunchD (macOS native)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "...">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.btc.checkonchain</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>/path/to/repo/market_regime_data/extract_checkonchain.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>6</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/repo/logs/checkonchain.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/repo/logs/checkonchain_error.log</string>
</dict>
</plist>
```

---

## Rate Limiting

- No official rate limits documented
- Recommended: **2 seconds between requests**
- Full 539-chart extraction takes ~18 minutes at 2s/chart
- Priority charts (22 charts) take ~45 seconds
- Charts are static HTML (~1-3MB each), no API calls needed
- Consider caching — most charts update once daily, so no need to re-fetch within 24 hours

---

## Data Storage

**Save location**: `market_regime_data/data/`
**Naming convention**: 
- Priority 1: Direct names (e.g., `mvrv_zscore.csv`, `sth_sopr.csv`)
- Priority 2+: Prefixed with `checkonchain_` (e.g., `checkonchain_leverage_ratio.csv`)

**CSV format**:
```
date,metric_name
2013-01-02,1.234
2013-01-03,1.567
...
```

---

## Regime Detection Signal Summary

| On-Chain Metric | CRASH Signal | BEAR Signal | DISTRIBUTION Signal | ACCUMULATION Signal | BULL Signal |
|----------------|-------------|-------------|--------------------|--------------------|-------------|
| **MVRV Z-Score** | — | Z < 0 | Z > 1.5 | -0.5 < Z < 0.5 | Z > 1.0 |
| **STH-SOPR** | < 0.95 | < 1.0 | Declining from > 1.0 | Rising toward 1.0 | > 1.02 |
| **NUPL** | < 0 | < 0.2 | > 0.5 (euphoria) | 0.0 - 0.25 | > 0.25 |
| **LTH-MVRV** | — | < 1.2 | > 3.0 (LTH in profit) | — | > 1.5 |
| **NVT Premium** | — | — | > 0.35 (overvalued) | < 0 | — |
| **LTH Net Pos** | — | — | Negative (selling) | Positive (accumulating) | — |
| **% Supply Profit** | < 50% | < 70% | > 95% | 50-80% | > 80% |
| **Sell-Side Risk** | High | — | — | Very low (exhausted) | — |

---

## Verification

After extraction, verify data integrity:

```python
import pandas as pd

files_to_check = [
    "mvrv_zscore.csv", "sth_sopr.csv", "nupl.csv",
    "lth_mvrv.csv", "lth_sopr.csv",
    "checkonchain_coinblock_nvt_premium.csv"
]

for f in files_to_check:
    df = pd.read_csv(f"market_regime_data/data/{f}")
    df["date"] = pd.to_datetime(df["date"])
    latest = df["date"].max()
    expected_latest = pd.Timestamp.now().normalize() - pd.Timedelta(days=1)
    stale = latest < expected_latest - pd.Timedelta(days=2)
    print(f"{'⚠️' if stale else '✅'} {f}: {len(df)} rows, latest={latest.date()}")
```
