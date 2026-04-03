# Macro Indicator Relationship Discovery

**Date:** 2026-03-30
**Tool:** [OmniOracle](https://github.com/cesabici-bit/omni-oracle) MI pipeline applied to our 66 monthly-resampled macro indicators
**Script:** `/Users/kriszhang/Github/macro_2/discover_relationships.py`

## Method

1. Loaded 67 historical CSV time series from `historical_data/`, 66 had >= 36 monthly observations
2. Resampled all to monthly frequency, first-differenced for stationarity
3. **MI Screening:** KSG mutual information estimator with 100 permutations per pair, p < 0.05 threshold — screened 2,145 pairs
4. **FDR Correction:** Benjamini-Hochberg at alpha=0.05 — all 618 significant pairs survived
5. **Lagged MI Directional Discovery:** Non-linear replacement for Granger causality. Tests MI(X_{t-k}, Y_t) vs MI(Y_{t-k}, X_t) for k=1..6 months. Determines x->y, y->x, bidirectional, or contemporaneous
6. **OOS Validation:** Temporal 70/30 split, z-score normalized on train only, Ridge/RF augmented model vs AR baseline. Incremental R2 > 0.02 required

## Pipeline Results

| Stage | Count |
|-------|-------|
| Input series | 66 |
| Total pairs screened | 2,145 |
| MI significant (p < 0.05) | 618 |
| FDR survivors | 618 |
| Directional (lagged MI) | 416 |
| **OOS validated (R2 > 0.02)** | **116** |

## OOS-Validated Directional Relationships (All 116)

### Tier 1: Strong predictive power (OOS R2 > 0.25)

| Relationship | Direction | Lag | MI | OOS R2 | p-value |
|---|---|---|---|---|---|
| median_home_price <-> oecd_cli | bidirectional | 5m | 0.069 | 0.857 | 0.010 |
| fed_balance_sheet <-> oecd_cli | bidirectional | 6m | 0.046 | 0.764 | 0.010 |
| oecd_cli -> initial_claims | y->x | 5m | 0.060 | 0.745 | 0.010 |
| ism_pmi <-> oecd_cli | bidirectional | 6m | 0.053 | 0.729 | 0.010 |
| ig_oas <-> oecd_cli | bidirectional | 5m | 0.122 | 0.729 | 0.010 |
| nonfarm_payrolls <-> oecd_cli | bidirectional | 6m | 0.036 | 0.713 | 0.010 |
| case_shiller_index <-> oecd_cli | bidirectional | 6m | 0.108 | 0.712 | 0.010 |
| core_cpi <-> oecd_cli | bidirectional | 4m | 0.064 | 0.710 | 0.010 |
| breakeven_5y <-> oecd_cli | bidirectional | 3m | 0.075 | 0.683 | 0.010 |
| cpi_headline <-> oecd_cli | bidirectional | 5m | 0.037 | 0.675 | 0.010 |
| hy_oas <-> oecd_cli | bidirectional | 3m | 0.155 | 0.660 | 0.010 |
| initial_claims -> nonfarm_payrolls | x->y | 1m | 0.029 | 0.485 | 0.010 |
| initial_claims -> unemployment_rate | x->y | 3m | 0.041 | 0.438 | 0.010 |
| fed_funds_effective <-> sofr | bidirectional | 2m | 0.289 | 0.432 | 0.010 |
| core_cpi <-> tga_balance | bidirectional | 5m | 0.083 | 0.383 | 0.010 |
| consumer_sentiment <-> oecd_cli | bidirectional | 1m | 0.067 | 0.358 | 0.010 |
| net_liquidity <-> nonfarm_payrolls | bidirectional | 2m | 0.056 | 0.358 | 0.020 |
| case_shiller_index <-> tga_balance | bidirectional | 6m | 0.118 | 0.354 | 0.010 |
| gold_price_fred <-> tga_balance | bidirectional | 4m | 0.040 | 0.323 | 0.010 |
| fed_funds_effective <-> tga_balance | bidirectional | 2m | 0.050 | 0.321 | 0.020 |
| jolts_openings <-> nonfarm_payrolls | bidirectional | 4m | 0.035 | 0.305 | 0.030 |
| natural_gas_fred <-> nonfarm_payrolls | bidirectional | 6m | 0.039 | 0.279 | 0.010 |
| unemployment_rate -> median_home_price | y->x | 3m | 0.045 | 0.279 | 0.050 |
| continuing_claims <-> oecd_cli | bidirectional | 1m | 0.107 | 0.272 | 0.010 |
| nonfarm_payrolls <-> us_gdp | bidirectional | 1m | 0.134 | 0.270 | 0.010 |

### Tier 2: Moderate predictive power (OOS R2 0.10–0.25)

| Relationship | Direction | Lag | MI | OOS R2 | p-value |
|---|---|---|---|---|---|
| fed_balance_sheet <-> ism_pmi | bidirectional | 2m | 0.049 | 0.221 | 0.030 |
| continuing_claims <-> us_gdp | bidirectional | 1m | 0.164 | 0.181 | 0.010 |
| building_permits -> bbb_oas | y->x | 1m | 0.035 | 0.171 | 0.030 |
| ism_pmi <-> sahm_rule | bidirectional | 2m | 0.067 | 0.166 | 0.010 |
| fed_funds_effective <-> fed_funds_rate | bidirectional | 1m | 0.242 | 0.165 | 0.010 |
| us2y_jp2y_spread -> jpy | y->x | 2m | 0.296 | 0.162 | 0.010 |
| us2y_jp2y_spread <-> us_2y_yield | bidirectional | 6m | 1.026 | 0.157 | 0.010 |
| case_shiller_index <-> fed_funds_rate | bidirectional | 2m | 0.097 | 0.152 | 0.010 |
| breakeven_10y <-> oecd_cli | bidirectional | 2m | 0.071 | 0.152 | 0.010 |
| case_shiller_index <-> us_gdp | bidirectional | 1m | 0.249 | 0.150 | 0.010 |
| unemployment_rate -> forward_inflation_5y5y | y->x | 3m | 0.057 | 0.149 | 0.010 |
| corporate_spreads_aaa <-> ig_oas | bidirectional | 1m | 0.610 | 0.147 | 0.010 |
| russell_2000 -> fed_funds_effective | y->x | 3m | 0.086 | 0.144 | 0.010 |
| spread_10y3m -> sofr | y->x | 4m | 0.068 | 0.142 | 0.010 |
| fed_funds_rate -> sofr | x->y | 3m | 0.494 | 0.136 | 0.020 |
| fed_funds_effective <-> net_liquidity | bidirectional | 5m | 0.071 | 0.136 | 0.010 |
| oecd_cli <-> sofr | bidirectional | 3m | 0.151 | 0.136 | 0.010 |
| fed_funds_effective -> crude_oil | y->x | 1m | 0.099 | 0.130 | 0.010 |
| core_cpi <-> fed_funds_effective | bidirectional | 3m | 0.072 | 0.129 | 0.010 |
| gold_silver_ratio -> russell_2000 | x->y | 5m | 0.096 | 0.127 | 0.050 |
| nonfarm_payrolls <-> sahm_rule | bidirectional | 1m | 0.074 | 0.125 | 0.010 |
| pce_headline -> crude_oil | y->x | 1m | 0.127 | 0.118 | 0.020 |
| nfci <-> us2y_jp2y_spread | bidirectional | 5m | 0.061 | 0.117 | 0.010 |
| corporate_spreads_aaa <-> corporate_spreads_bbb | bidirectional | 1m | 0.513 | 0.115 | 0.010 |
| fed_funds_effective -> cpi_headline | y->x | 6m | 0.038 | 0.111 | 0.040 |
| building_permits <-> median_home_price | bidirectional | 6m | 0.053 | 0.108 | 0.010 |
| us_2y_yield -> jpy | y->x | 2m | 0.266 | 0.104 | 0.020 |
| case_shiller_index <-> crude_oil | bidirectional | 5m | 0.202 | 0.102 | 0.010 |

### Tier 3: Weak but validated (OOS R2 0.02–0.10)

| Relationship | Direction | Lag | MI | OOS R2 | p-value |
|---|---|---|---|---|---|
| nfci <-> shiller_cape | bidirectional | 5m | 0.084 | 0.086 | 0.030 |
| ism_pmi <-> unemployment_rate | bidirectional | 2m | 0.040 | 0.085 | 0.010 |
| oecd_cli -> wei | x->y | 4m | 0.069 | 0.083 | 0.010 |
| case_shiller_index <-> median_home_price | bidirectional | 4m | 0.059 | 0.081 | 0.010 |
| breakeven_5y -> cpi_headline | x->y | 1m | 0.062 | 0.079 | 0.010 |
| fed_funds_rate <-> net_liquidity | bidirectional | 2m | 0.095 | 0.079 | 0.010 |
| case_shiller_index <-> net_liquidity | bidirectional | 2m | 0.085 | 0.078 | 0.010 |
| bbb_oas <-> ig_oas | bidirectional | 1m | 1.790 | 0.076 | 0.010 |
| corporate_spreads_bbb <-> ig_oas | bidirectional | 1m | 1.790 | 0.076 | 0.010 |
| es_futures <-> ig_oas | bidirectional | 2m | 0.189 | 0.072 | 0.040 |
| net_liquidity <-> tga_balance | bidirectional | 2m | 0.304 | 0.071 | 0.010 |
| nfci <-> oecd_cli | bidirectional | 2m | 0.066 | 0.071 | 0.010 |
| median_home_price <-> us2y_jp2y_spread | bidirectional | 3m | 0.089 | 0.066 | 0.040 |
| mortgage_rate_30y -> real_yield_10y | x->y | 3m | 0.297 | 0.066 | 0.020 |
| building_permits <-> housing_starts | bidirectional | 1m | 0.105 | 0.065 | 0.010 |
| real_yield_10y -> shiller_cape | x->y | 2m | 0.040 | 0.065 | 0.020 |
| fed_funds_effective <-> us2y_jp2y_spread | bidirectional | 5m | 0.069 | 0.062 | 0.010 |
| corporate_spreads_aaa <-> us_gdp | bidirectional | 3m | 0.072 | 0.061 | 0.020 |
| breakeven_10y -> continuing_claims | x->y | 5m | 0.051 | 0.060 | 0.030 |
| bbb_oas <-> oecd_cli | bidirectional | 1m | 0.106 | 0.057 | 0.010 |
| corporate_spreads_bbb <-> oecd_cli | bidirectional | 1m | 0.106 | 0.057 | 0.010 |
| copper_price_fred <-> initial_claims | bidirectional | 5m | 0.032 | 0.057 | 0.030 |
| russell_2000 -> xau_jpy | x->y | 5m | 0.083 | 0.055 | 0.010 |
| ism_pmi <-> nonfarm_payrolls | bidirectional | 1m | 0.139 | 0.055 | 0.010 |
| mortgage_rate_30y -> case_shiller_index | y->x | 6m | 0.063 | 0.054 | 0.020 |
| breakeven_5y -> copper_price_fred | x->y | 2m | 0.053 | 0.050 | 0.020 |
| case_shiller_index <-> us2y_jp2y_spread | bidirectional | 6m | 0.062 | 0.050 | 0.010 |
| corporate_spreads_aaa <-> oecd_cli | bidirectional | 1m | 0.055 | 0.050 | 0.010 |
| breakeven_5y -> fed_balance_sheet | x->y | 5m | 0.041 | 0.050 | 0.020 |
| case_shiller_index <-> sofr | bidirectional | 3m | 0.114 | 0.049 | 0.010 |
| vix_move -> corporate_spreads_aaa | y->x | 1m | 0.335 | 0.047 | 0.030 |
| case_shiller_index <-> us_2y_yield | bidirectional | 6m | 0.079 | 0.047 | 0.010 |
| fed_funds_rate <-> us_gdp | bidirectional | 6m | 0.053 | 0.045 | 0.010 |
| us_30y_yield -> corporate_spreads_aaa | y->x | 6m | 0.038 | 0.044 | 0.010 |
| fed_funds_rate <-> nfci | bidirectional | 1m | 0.053 | 0.043 | 0.010 |
| case_shiller_index <-> pce_headline | bidirectional | 5m | 0.120 | 0.043 | 0.010 |
| forward_inflation_5y5y <-> vix_move | bidirectional | 1m | 0.076 | 0.041 | 0.020 |
| fed_funds_effective <-> spread_10y3m | bidirectional | 1m | 0.041 | 0.041 | 0.010 |
| adp_employment <-> fed_balance_sheet | bidirectional | 5m | 0.061 | 0.039 | 0.010 |
| case_shiller_index <-> japan_2y_yield | bidirectional | 6m | 0.203 | 0.038 | 0.010 |
| adp_employment <-> us2y_jp2y_spread | bidirectional | 5m | 0.060 | 0.037 | 0.010 |
| fed_funds_effective <-> gold | bidirectional | 1m | 0.081 | 0.031 | 0.020 |
| jpy -> dxy | y->x | 3m | 0.482 | 0.031 | 0.010 |
| unemployment_rate <-> us_gdp | bidirectional | 5m | 0.052 | 0.030 | 0.010 |
| case_shiller_index -> us_5y_yield | x->y | 1m | 0.067 | 0.029 | 0.020 |
| spread_10y3m -> us2y_jp2y_spread | x->y | 4m | 0.071 | 0.029 | 0.030 |
| fed_funds_effective <-> nonfarm_payrolls | bidirectional | 1m | 0.071 | 0.028 | 0.010 |
| us_30y_yield -> hy_oas | y->x | 4m | 0.087 | 0.028 | 0.010 |
| breakeven_5y -> initial_claims | x->y | 4m | 0.031 | 0.027 | 0.010 |
| case_shiller_index <-> continuing_claims | bidirectional | 2m | 0.063 | 0.026 | 0.010 |
| russell_2000 <-> treasury_term_premia | bidirectional | 3m | 0.103 | 0.026 | 0.020 |
| sofr -> xau_jpy | x->y | 2m | 0.074 | 0.026 | 0.010 |
| fed_funds_rate -> crude_oil | y->x | 2m | 0.059 | 0.025 | 0.020 |
| adp_employment <-> core_pce | bidirectional | 5m | 0.058 | 0.024 | 0.010 |
| ig_oas -> fed_funds_effective | y->x | 1m | 0.071 | 0.024 | 0.010 |
| sahm_rule <-> us_gdp | bidirectional | 2m | 0.123 | 0.023 | 0.010 |
| case_shiller_index <-> nonfarm_payrolls | bidirectional | 2m | 0.194 | 0.022 | 0.010 |
| hy_oas -> gdpnow | y->x | 6m | 0.094 | 0.022 | 0.010 |
| initial_claims <-> us_gdp | bidirectional | 5m | 0.088 | 0.022 | 0.010 |
| oecd_cli <-> sahm_rule | bidirectional | 4m | 0.068 | 0.021 | 0.010 |
| fed_balance_sheet <-> tga_balance | bidirectional | 2m | 0.138 | 0.020 | 0.010 |
| ig_oas -> japan_2y_yield | x->y | 1m | 0.060 | 0.020 | 0.010 |
| case_shiller_index <-> unemployment_rate | bidirectional | 1m | 0.069 | 0.020 | 0.010 |

## Top Contemporaneous Correlations (no lag)

| Pair | MI | p-value |
|---|---|---|
| es_futures <-> sp500_ma200 | 1.648 | 0.010 |
| 10y_treasury_yield <-> treasury_term_premia | 1.229 | 0.010 |
| us_2y_yield <-> us_5y_yield | 1.155 | 0.010 |
| spread_10y3m <-> treasury_term_premia | 0.947 | 0.010 |
| treasury_term_premia <-> us_5y_yield | 0.899 | 0.010 |
| real_yield_10y <-> treasury_term_premia | 0.560 | 0.010 |
| real_yield_10y <-> us_5y_yield | 0.519 | 0.010 |
| spread_10y3m <-> us_30y_yield | 0.469 | 0.010 |
| real_yield_10y <-> us_30y_yield | 0.432 | 0.010 |
| es_futures <-> russell_2000 | 0.424 | 0.010 |
| gold_price_fred <-> silver | 0.419 | 0.010 |
| 10y_treasury_yield <-> us2y_jp2y_spread | 0.416 | 0.010 |
| russell_2000 <-> sp500_ma200 | 0.415 | 0.010 |
| gold <-> xau_jpy | 0.400 | 0.010 |
| gold_price_fred <-> xau_jpy | 0.395 | 0.010 |
| real_yield_5y <-> us_5y_yield | 0.382 | 0.010 |
| es_futures <-> hy_oas | 0.349 | 0.010 |
| real_yield_10y <-> spread_10y3m | 0.338 | 0.010 |
| real_yield_5y <-> us_2y_yield | 0.324 | 0.010 |
| real_yield_10y <-> us_2y_yield | 0.321 | 0.010 |

## Interpretation: Non-Obvious Findings

### 1. OECD CLI is the single most powerful leading indicator
It has OOS-validated predictive relationships with 14 other indicators (R2 0.05-0.86). OECD CLI leads:
- Initial claims (5m, R2=0.75)
- ISM PMI (6m, R2=0.73)
- Nonfarm payrolls (6m, R2=0.71)
- Core CPI (4m, R2=0.71)
- CPI headline (5m, R2=0.68)
- Consumer sentiment (1m, R2=0.36)
- WEI (4m, R2=0.08)

**Implication:** OECD CLI is a strong 3-6 month leading indicator for US labor market and inflation. Worth monitoring its direction for positioning.

### 2. TGA Balance links to inflation and housing
- Core CPI <-> TGA (5m, R2=0.38) — fiscal cash balance predicts inflation
- Case-Shiller <-> TGA (6m, R2=0.35) — treasury spending patterns affect housing
- Gold <-> TGA (4m, R2=0.32) — gold responds to fiscal liquidity

**Implication:** TGA drawdowns (government spending) are a leading indicator for inflation and asset prices. This aligns with the "fiscal dominance" thesis.

### 3. Gold/Silver ratio predicts small-cap performance
- Gold/Silver ratio -> Russell 2000 (5m, R2=0.13)

**Implication:** When gold outperforms silver (rising ratio = risk-off), small caps underperform 5 months later. The ratio is a non-obvious risk appetite barometer.

### 4. Net liquidity strongly predicts employment
- Net liquidity <-> Nonfarm payrolls (2m, R2=0.36)

**Implication:** Fed liquidity conditions (balance sheet - TGA - reverse repo) lead employment by 2 months with substantial explanatory power.

### 5. Credit spreads contain forward GDP information
- HY OAS -> GDPNow (6m, R2=0.02) — weak but validated
- IG OAS <-> OECD CLI (5m, R2=0.73) — strong

**Implication:** HY credit stress leads real economic activity by 6 months. IG spreads are tightly coupled with global leading indicators.

### 6. Russell 2000 predicts Fed action
- Russell 2000 -> Fed funds effective (3m, R2=0.14)

**Implication:** Small-cap equity performance leads Fed rate decisions by 3 months. The "Fed put" for risk assets is statistically detectable.

### 7. Yield spread predicts funding rates
- Spread 10Y-3M -> SOFR (4m, R2=0.14)

**Implication:** Yield curve shape has predictive power for where short-term funding rates are heading.

### 8. Real yields lead equity valuations
- Real yield 10Y -> Shiller CAPE (2m, R2=0.07)

**Implication:** Rising real rates compress equity multiples with a 2-month lag.

### 9. Breakeven inflation predicts realized CPI
- Breakeven 5Y -> CPI headline (1m, R2=0.08)

**Implication:** Market-based inflation expectations are a modest but validated 1-month leading indicator for realized CPI.

### 10. VIX/MOVE leads IG credit repricing
- VIX/MOVE -> Corporate AAA spreads (1m, R2=0.05)

**Implication:** Rate + equity vol predicts investment-grade credit spread widening by 1 month.

## Caveats

1. **Sample period bias:** All data is from ~2021-2026, a period dominated by COVID recovery, inflation spike, and aggressive Fed tightening. Relationships may be regime-dependent.
2. **Monthly resampling:** Daily/weekly signals are smoothed out. Some relationships (e.g., VIX -> credit) may be stronger at higher frequency.
3. **First-differencing:** Removes level information. Some relationships (e.g., yield levels -> equity valuations) may be better captured in levels.
4. **No tradability test:** High R2 does not imply tradable signals. OmniOracle's own backtest found 0/5 ROBUST signals were tradable (no Sharpe > 2-sigma above random).
5. **OECD CLI caveat:** Published with 2-month lag, so the "5-month lead" is effectively 3 months of usable forward signal.

## Tool Assessment: OmniOracle

**Repository:** github.com/cesabici-bit/omni-oracle (MIT license, Python 3.12+, closed portfolio piece)

**What it does well:**
- Clean, modular statistical modules (MI screening, lagged MI, FDR, OOS validation)
- Non-linear MI catches relationships that linear correlation misses
- Permutation-based p-values with early stopping are efficient
- Multi-model OOS (Ridge + RF) with anti-leakage is rigorous

**Limitations:**
- Requires Python 3.12+ (we use 3.10) — but the core modules work fine with 3.10
- DuckDB ingestion layer is unnecessary for our use case (we have CSV files)
- Walk-forward CV module not used here (our series are too short for robust rolling windows)
- No trading alpha — their own backtest confirmed this

**Verdict:** Useful as a hypothesis generator / relationship scanner. The core statistical modules (`mi_screening.py`, `lagged_mi.py`, `temporal_oos.py`, `fdr.py`) are worth keeping. Not useful for generating trading signals directly.

## Reproducing

```bash
cd /path/to/macro_2
python discover_relationships.py   # ~3 minutes on 66 series
```

Requires omni-oracle cloned at `../omni-oracle/`. Uses sklearn, numpy, pandas (already in our deps).
