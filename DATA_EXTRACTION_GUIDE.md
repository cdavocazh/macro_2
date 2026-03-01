# Historical Data Extraction Guide

Complete system for downloading and managing historical macroeconomic indicator data and large-cap equity financials in CSV format.

---

## Quick Start

```bash
# Download all historical data (first time, ~5 min)
python extract_historical_data.py

# Update cache + CSVs (skips if <1h old)
python scheduled_extract.py
python scheduled_extract.py --force    # ignore freshness guard
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
| `dxy.csv` | yfinance DX-Y.NYB | timestamp, date, dxy | ~1 year |
| `jpy.csv` | yfinance JPY=X | timestamp, date, jpy_rate | ~1 year |
| `10y_treasury_yield.csv` | FRED DGS10 | timestamp, date, 10y_yield | ~1 year |
| `ism_pmi.csv` | FRED IPMAN (proxy) | timestamp, date, ism_pmi | ~1 year |
| `tga_balance.csv` | FRED WTREGEN | timestamp, date, tga_balance | Weekly |
| `net_liquidity.csv` | FRED WALCL-TGA-RRP | timestamp, date, net_liquidity | Weekly |
| `sofr.csv` | FRED SOFR | timestamp, date, sofr | Daily |
| `us_2y_yield.csv` | FRED DGS2 | timestamp, date, us_2y_yield | Daily |
| `japan_2y_yield.csv` | MOF Japan CSV | timestamp, date, japan_2y_yield | Daily (1974+) |
| `us2y_jp2y_spread.csv` | FRED+MOF calculated | timestamp, date, spread | Daily |

### Volatility & Market Indices (from yfinance)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `vix_move.csv` | ^VIX, ^MOVE | timestamp, date, vix, move, vix_move_ratio | ~1 year |
| `cboe_skew.csv` | ^SKEW | timestamp, date, cboe_skew | ~30 days |
| `russell_2000.csv` | IWN, IWO | timestamp, date, value, growth, ratio | ~2 years |
| `sp500_ma200.csv` | ^GSPC | timestamp, date, close, ma200, ratio | ~2 years |
| `es_futures.csv` | ES=F | timestamp, date, es_price | ~2 years |
| `rty_futures.csv` | RTY=F | timestamp, date, rty_price | ~2 years |

### Commodities & COT (from yfinance, CFTC)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `gold.csv` | GC=F (continuous) | timestamp, date, gold_price | ~2 years |
| `silver.csv` | SI=F (continuous) | timestamp, date, silver_price | ~2 years |
| `crude_oil.csv` | CL=F (continuous) | timestamp, date, crude_oil_price | ~2 years |
| `copper.csv` | HG=F (continuous) | timestamp, date, copper_price | ~2 years |
| `cot_gold.csv` | CFTC weekly | timestamp, date, managed_money_net, open_interest | Weekly |
| `cot_silver.csv` | CFTC weekly | timestamp, date, managed_money_net, open_interest | Weekly |

### Valuation (from Yale, FRED)

| CSV File | Source | Columns | History |
|----------|--------|---------|---------|
| `shiller_cape.csv` | Yale Excel | date, timestamp, cape_ratio | Since 1871 |
| `us_gdp.csv` | FRED GDP | timestamp, date, us_gdp | Quarterly |
| `market_cap.csv` | FRED | timestamp, date, market_cap | Varies |
| `marketcap_to_gdp.csv` | Calculated | date, us_gdp, market_cap, ratio | Quarterly |
| `sp500_fundamentals.csv` | OpenBB/yfinance | timestamp, date, pe_trailing, pb_ratio | Snapshot |

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

## Automation

### macOS launchd (recommended)

```bash
bash setup_launchd.sh           # Install
bash setup_launchd.sh --status  # Check
bash setup_launchd.sh --uninstall  # Remove
```

Runs at 1:00 AM, 8:30 AM, 1:00 PM, 5:00 PM, 10:00 PM GMT+8, Mon-Sat. Catches up missed runs after sleep.

### Manual

```bash
python scheduled_extract.py         # Skip if cache < 1h old
python scheduled_extract.py --force # Force refresh
python extract_historical_data.py   # Full historical extraction
```

---

**Last Updated:** March 1, 2026
