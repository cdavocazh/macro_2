# Data Extraction Guide

Complete system for downloading and managing historical macroeconomic indicator data, large-cap equity financials, and Hyperliquid perpetual futures in CSV format.

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set API key
export FRED_API_KEY='your_key_here'

# Download all historical data (first time, ~5 min)
python extract_historical_data.py

# Update cache + CSVs (skips if <15min old)
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard

# Fast yfinance-only refresh (~5s, safe for 5-min polling)
python fast_extract.py
python fast_extract.py --force

# Hyperliquid perps + spot (~0.5s, every 1 min)
python hl_extract.py
python hl_extract.py --force
python hl_extract.py --dry-run
```

---

## Output Structure

```
historical_data/
├── data_metadata.json          Tracks last extraction timestamp
├── russell_2000.csv            Russell 2000 Value & Growth
├── sp500_ma200.csv             S&P 500 with 200-day MA
├── vix_move.csv                VIX and MOVE indices
├── dxy.csv                     US Dollar Index
├── jpy.csv                     USD/JPY exchange rate
├── shiller_cape.csv            Shiller CAPE historical
├── sp500_fundamentals.csv      P/E and P/B ratios (snapshot)
├── cboe_skew.csv               CBOE SKEW Index
├── us_gdp.csv                  US GDP (quarterly)
├── market_cap.csv              S&P 500 Market Cap
├── marketcap_to_gdp.csv        Buffett Indicator
├── 10y_treasury_yield.csv      10-Year Treasury Yield
├── ism_pmi.csv                 ISM Manufacturing PMI (proxy)
├── gold.csv                    Gold futures (GC=F continuous)
├── silver.csv                  Silver futures (SI=F continuous)
├── crude_oil.csv               Crude Oil futures (CL=F continuous)
├── copper.csv                  Copper futures (HG=F continuous)
├── es_futures.csv              S&P 500 E-mini futures (ES=F)
├── rty_futures.csv             Russell 2000 E-mini futures (RTY=F)
├── cot_gold.csv                CFTC COT positioning — Gold
├── cot_silver.csv              CFTC COT positioning — Silver
├── tga_balance.csv             Treasury General Account balance
├── net_liquidity.csv           Fed Net Liquidity
├── sofr.csv                    SOFR overnight rate
├── us_2y_yield.csv             US 2-Year Treasury Yield
├── japan_2y_yield.csv          Japan 2Y Government Bond Yield
├── us2y_jp2y_spread.csv        US-Japan 2Y yield spread
├── hl_perps.csv                Hyperliquid perpetual futures
├── hl_spot_stocks.csv          Hyperliquid HIP-3 spot stocks
├── _summary_latest.csv         Latest values from all indicators
│
└── equity_financials/           Large-cap company financials
    ├── yahoo_finance/           Data from Yahoo Finance
    │   ├── AAPL_quarterly.csv
    │   ├── MSFT_quarterly.csv
    │   ├── ... (20 companies)
    │   └── _valuation_snapshot.csv
    └── sec_edgar/               Data from SEC EDGAR XBRL
        ├── AAPL_quarterly.csv
        ├── MSFT_quarterly.csv
        ├── ... (19 companies, TSM excluded — IFRS)
        └── _valuation_snapshot.csv
```

---

## Indicators Extracted

### Macro & Currency (from FRED, yfinance, MOF Japan)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `dxy.csv` | yfinance DX-Y.NYB | timestamp, date, dxy | ~5 years |
| `jpy.csv` | yfinance JPY=X | timestamp, date, jpy_rate | ~5 years |
| `10y_treasury_yield.csv` | FRED DGS10 | timestamp, date, 10y_yield | ~5 years |
| `ism_pmi.csv` | FRED IPMAN (proxy) | timestamp, date, ism_pmi | ~5 years |
| `tga_balance.csv` | FRED WTREGEN | timestamp, date, tga_balance | Weekly |
| `net_liquidity.csv` | FRED WALCL-TGA-RRP | timestamp, date, net_liquidity | Weekly |
| `sofr.csv` | FRED SOFR | timestamp, date, sofr | Daily |
| `us_2y_yield.csv` | FRED DGS2 | timestamp, date, us_2y_yield | Daily |
| `japan_2y_yield.csv` | MOF Japan CSV | timestamp, date, japan_2y_yield | Daily (1974+) |
| `us2y_jp2y_spread.csv` | FRED+MOF calculated | timestamp, date, spread | Daily |

### Volatility & Market Indices (from yfinance)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `vix_move.csv` | ^VIX, ^MOVE | timestamp, date, vix, move, vix_move_ratio | ~5 years |
| `cboe_skew.csv` | ^SKEW | timestamp, date, cboe_skew | ~30 days |
| `russell_2000.csv` | IWN, IWO | timestamp, date, value, growth, ratio | ~5 years |
| `sp500_ma200.csv` | ^GSPC | timestamp, date, close, ma200, ratio | ~5 years |
| `es_futures.csv` | ES=F | timestamp, date, es_price | ~5 years |
| `rty_futures.csv` | RTY=F | timestamp, date, rty_price | ~5 years |

### Commodities & COT (from yfinance, CFTC)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `gold.csv` | GC=F (continuous) | timestamp, date, gold_price | ~5 years |
| `silver.csv` | SI=F (continuous) | timestamp, date, silver_price | ~5 years |
| `crude_oil.csv` | CL=F (continuous) | timestamp, date, crude_oil_price | ~5 years |
| `copper.csv` | HG=F (continuous) | timestamp, date, copper_price | ~5 years |
| `cot_gold.csv` | CFTC weekly | timestamp, date, managed_money_net, open_interest | Weekly |
| `cot_silver.csv` | CFTC weekly | timestamp, date, managed_money_net, open_interest | Weekly |
| `cot_crude_oil.csv` | CFTC SODA API | timestamp, date, mm_long, mm_short, mm_net, oi, producer_net | Weekly (~4 years) |
| `cot_brent.csv` | CFTC SODA API | timestamp, date, mm_long, mm_short, mm_net, oi, producer_net | Weekly (~4 years) |
| `cot_copper.csv` | CFTC SODA API | timestamp, date, mm_long, mm_short, mm_net, oi, producer_net | Weekly (~4 years) |
| `cot_natural_gas.csv` | CFTC SODA API | timestamp, date, mm_long, mm_short, mm_net, oi, producer_net | Weekly (~4 years) |

### Valuation (from Yale, FRED)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `shiller_cape.csv` | Yale Excel | date, timestamp, cape_ratio | Since 1871 |
| `us_gdp.csv` | FRED GDP | timestamp, date, us_gdp | Quarterly |
| `market_cap.csv` | FRED | timestamp, date, market_cap | Varies |
| `marketcap_to_gdp.csv` | Calculated | date, us_gdp, market_cap, ratio | Quarterly |
| `sp500_fundamentals.csv` | OpenBB/yfinance | timestamp, date, pe_trailing, pb_ratio | Snapshot |

---

## Hyperliquid Data Extraction

`hl_extract.py` runs every 1 minute to extract Hyperliquid perpetual futures prices and HIP-3 spot stock prices via the Hyperliquid REST API (2-3 HTTP calls, ~0.5s total).

### Tracked Perps

| Ticker | Notes |
|--------|-------|
| BTC, ETH, SOL, PAXG, HYPE | Standard perps (available in allMids) |
| OIL | Builder-deployed (`flx:OIL`) |
| SP500, XYZ100, NATGAS, COPPER, BRENTOIL | Builder-deployed (`xyz:` prefixed) |

Builder-deployed perps (`flx:`, `xyz:` prefixed) are not present in the allMids response. Their prices are derived from the 1-minute candle close instead.

### How It Works

- **Partial cache merge**: Updates only keys `84_hl_perps` and `85_hl_spot_stocks` in `all_indicators.json`. Does not touch other indicator data.
- **Freshness guard**: 45-second minimum interval between runs.
- **Launchd plist**: `com.macro2.hl-extract.plist` (`StartInterval: 60`)
- **Logs**: `logs/hl_extract_stdout.log`

### Commands

```bash
python hl_extract.py             # normal run
python hl_extract.py --force     # ignore freshness guard
python hl_extract.py --dry-run   # show what would be extracted
```

---

## Equity Financials (Dual-Source)

### Per-Company Quarterly CSV Columns

Each `{TICKER}_quarterly.csv` contains:

**Income Statement**: total_revenue, cost_of_revenue, gross_profit, operating_expense, research_development, selling_general_admin, operating_income, ebitda, ebit, pretax_income, tax_provision, net_income, diluted_eps, basic_eps, diluted_shares, basic_shares

**Balance Sheet**: total_assets, current_assets, cash_and_short_term_investments, cash_and_equivalents, accounts_receivable, inventory, goodwill, net_ppe, total_liabilities, current_liabilities, non_current_liabilities, long_term_debt, current_debt, total_debt, accounts_payable, accrued_expenses, net_debt, stockholders_equity, retained_earnings, invested_capital, debt_ratio, debt_to_equity, current_ratio

**Cash Flow**: operating_cash_flow, capital_expenditure, free_cash_flow, share_repurchases, dividends_paid, investing_cash_flow, financing_cash_flow, depreciation_amortization, stock_based_compensation

**Metadata**: timestamp, quarter (e.g. "2025-Q4"), ticker, company_name, source

### Valuation Snapshot CSV

`_valuation_snapshot.csv` contains daily snapshots of all 20 companies with forward_pe, trailing_pe, peg_ratio, price_to_book, price_to_sales, ev_to_ebitda, ev_to_fcf, enterprise_value, margins, returns, growth rates.

### Yahoo Finance vs SEC EDGAR Differences

| Aspect | Yahoo Finance | SEC EDGAR |
|--------|--------------|-----------|
| Speed | Fast (~2s/company) | Slower (~3s/company, rate limited) |
| Coverage | All 20 tickers | 19 tickers (TSM excluded — IFRS) |
| Data source | yfinance Python API | XBRL companyfacts JSON API |
| Quarter derivation | Yahoo provides quarterly directly | FY-end Q4 derived from Annual - (Q1+Q2+Q3) |
| Cash flow | Quarterly standalone | May need cumulative YTD correction (NVDA) |
| Revenue segments | Not available | Available from 10-K instance documents |

---

## Append-Only Mechanism

1. **First run**: Downloads all historical data, creates CSV files
2. **Subsequent runs**: Loads existing CSV, appends new data, deduplicates by timestamp, saves
3. **Deduplication**: `drop_duplicates(subset=[timestamp_col], keep='last')` keeps most recent value

---

## Automation (macOS launchd)

### Setup

```bash
bash setup_launchd.sh              # Install all 3 jobs
bash setup_launchd.sh --status     # Check status
bash setup_launchd.sh --uninstall  # Remove all jobs
```

### Three Extraction Jobs

| Job | Plist | Interval | What it extracts |
|-----|-------|----------|-----------------|
| **hl-extract** | `com.macro2.hl-extract.plist` | Every 60 seconds | Hyperliquid perps + HIP-3 spot stocks (keys 84/85 only) |
| **fast-extract** | `com.macro2.fast-extract.plist` | Every 5 minutes | Real-time yfinance: futures, FX, commodities, indices, sector ETFs, OHLCV (31 extractors) |
| **scheduled-extract** | `com.macro2.scheduled-extract.plist` | 5x/day Mon-Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) | Full extraction: FRED, SEC, web scrapers, yfinance, all CSVs |

Logs: `logs/hl_extract_stdout.log`, `logs/fast_extract_stdout.log`, `logs/launchd_stdout.log`

launchd catches up missed runs after sleep (unlike cron).

### Manual

```bash
python hl_extract.py               # Hyperliquid only
python fast_extract.py             # yfinance only (~5s)
python scheduled_extract.py       # Full extraction (skips if <15min old)
python scheduled_extract.py --force
python extract_historical_data.py  # Full historical CSV build
```

---

## Data Update Frequency

Understanding the difference between **how often your system fetches** and **how often upstream sources publish new data** is important for interpreting dashboard freshness.

### System Fetch Frequency

| Job | Schedule | Freshness Guard | Indicators Fetched |
|-----|----------|----------------|--------------------|
| **hl-extract** | Every 60 seconds (24/7) | 45 seconds | Hyperliquid perps + HIP-3 spot stocks (keys 84/85 only) |
| **fast-extract** | Every 5 minutes (24/7) | 3 minutes | 31 yfinance extractors: ES/RTY futures, VIX, DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, gold, silver, oil, copper, natural gas, Cu/Au ratio, SPY/RSP, Russell 2000, sector ETFs (×11), VIX term structure, OHLCV series. Also merges ~18 indicators into `all_indicators.json` cache. |
| **scheduled-extract** | 5×/day Mon–Sat (1am, 8:30am, 1pm, 5pm, 10pm GMT+8) | 15 minutes | All 86+ indicators: FRED (38), web scrapers (4), OpenBB (21), COT, Shiller CAPE, Japan yields, global yields, equity financials, Fidenza extractors (13) |

### Upstream Source Publish Frequency

| Frequency | Indicators | Upstream Source |
|-----------|-----------|----------------|
| **Real-time / Intraday** | VIX, DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY, ES/RTY futures, SPY/RSP, sector ETFs (×11), gold, silver, oil, copper, natural gas, Russell 2000 V/G, Hyperliquid perps + spot | yfinance (5-min polling), Hyperliquid API (1-min polling) |
| **Daily** | SOFR, Fed Funds rate, Treasury yields (2Y/5Y/10Y), DGS series, real yield, breakevens, TGA balance, bank reserves (WRESBAL), WALCL, HY/IG OAS, NFCI, VIX futures curve, IV skew, put/call ratio | FRED / CBOE / yfinance |
| **Weekly** | WEI (Weekly Economic Index), initial claims, COT positioning (CFTC, Friday release), Fama-French factors, AAII sentiment (Wednesday release) | FRED / CFTC SODA API / Ken French / AAII |
| **Monthly** | CPI, PPI, PCE, nonfarm payrolls, ADP employment, JOLTS, quits rate, ISM Manufacturing PMI, ISM Services PMI, industrial production, housing starts, retail sales, consumer sentiment, M1/M2 money supply, SLOOS, OECD CLI, global CPI, intl unemployment, ECB rates, EU yields, CPI components, term premia, home sales | FRED / ECB SDW / OECD |
| **Quarterly** | GDP, GDPNow (updated ~daily but tracks quarterly GDP), Sahm Rule, equity financials (Top 20 + S&P 500), SEC 10-Q/10-K filings, 13F institutional holdings, intl GDP, corporate spreads | FRED / SEC EDGAR / yfinance |
| **Infrequent / Static** | Shiller CAPE (monthly from Yale), Market Cap/GDP, S&P 500 Multiples (Finviz), sector P/E ratios, equity risk premium, Forward P/E, OPEC production, gold reserves | Yale / Finviz / EIA / WGC |

### Important Nuances

- **FRED series** are fetched 5×/day but most only publish new data monthly or weekly — the fetched value is the same most of the time.
- **COT data** is released Friday afternoon by CFTC; the 5×/day fetch picks it up on the next Saturday 1am run.
- **Equity financials** only change when companies file 10-Q/10-K (~4× per year per company). Use `monitor_earnings.py` and `review_data_freshness.py` to detect staleness.
- **13F holdings** are filed ~45 days after quarter-end; `extract_13f_holdings.py` is run manually.
- **fast_extract merges into cache** — even if `scheduled_extract` fails, the 31 yfinance indicators stay fresh every 5 minutes via atomic cache merge.
- **Cache TTL is 24 hours** — if neither `fast_extract` nor `scheduled_extract` updates the cache for >24h, dashboards fall back to stale data (with `fallback_stale=True`) instead of returning 503 errors.

---

## Key Features

- **Append-only** -- Never overwrites existing data
- **Deduplication** -- Removes duplicates by timestamp
- **Freshness guards** -- hl-extract 45s, fast-extract 3min, scheduled-extract 15min
- **Dual-source equity** -- Yahoo Finance + SEC EDGAR in separate directories
- **Partial cache merge** -- hl-extract and fast-extract update only their keys in the shared cache
- **Stale cache fallback** -- Dashboards serve expired data instead of 503 when cache is >24h old
- **Standard CSV format** -- Works with Excel, pandas, SQL, etc.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `FRED_API_KEY not set` | `export FRED_API_KEY='your_key'` or edit `config.py` |
| Missing module | `pip install -r requirements.txt` |
| SEC rate limit errors | Built-in 0.15s delay; retry after a minute |
| TSM SEC data empty | Expected (IFRS company, uses Yahoo Finance only) |

---

**Last Updated:** March 22, 2026
