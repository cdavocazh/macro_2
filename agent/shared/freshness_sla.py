"""Freshness SLA per indicator key.

Used by check_indicator_freshness (C1 in SOP_DATA_QA.md).
Each entry = (frequency_tier, optional_sla_override_days).
"""

# Standard SLA tiers (max age in days before HIGH severity)
# Calibrated against actual macro_2 release schedules:
# - Most US monthly indicators publish ~30 days after period end
# - Some (housing starts, retail sales) publish 45-60 days after
# - International (OECD, global PMI) often 60-90 days lagged
SLA_TIERS = {
    "realtime": 0.0208,    # 30 minutes (futures sometimes pause 10-20 min)
    "daily":    5,         # 5 calendar days (covers long weekends)
    "weekly":   21,        # ~3 weeks (FRED initial/continuing claims lag ~2 weeks after period end)
    "monthly":  90,        # ~3 months (most US releases <60d; Census/housing data can lag 3+ months on FRED)
    "quarterly": 200,      # ~6.6 months (international GDP/SLOOS can lag 5-6 months after quarter end)
}

# LOW severity threshold (acceptable lag) per tier
LOW_THRESHOLDS = {
    "realtime": 0.0104,    # 15 min
    "daily":    2,
    "weekly":   10,
    "monthly":  50,
    "quarterly": 150,
}

# Indicator key -> frequency tier
# Keys mirror data_aggregator's numbered scheme.
# Anything not listed here is treated as "monthly" by default.
INDICATOR_FREQUENCY = {
    # ── Real-time IBKR-overlay candidates ─────
    "13_gold": "daily", "14_silver": "daily", "15_crude_oil": "daily",
    "16_copper": "daily", "17_es_futures": "daily", "18_rty_futures": "daily",
    "20_jpy": "daily", "56_natural_gas": "daily",
    # ── Daily market data ─────────────────────
    "8_vix": "daily", "9_move_index": "daily", "8b_vix_move_ratio": "daily",
    "10_dxy": "daily", "5_spx_call_skew": "daily",
    "11_10y_yield": "daily", "26_us_2y_yield": "daily", "27_japan_2y_yield": "daily",
    "28_us2y_jp2y_spread": "daily", "33_yield_curve": "daily",
    "34_hy_oas": "daily", "45_ig_oas": "daily", "76_corporate_spreads": "daily",
    "35_breakeven_inflation": "daily", "36_real_yield": "daily", "61_5y_yield": "daily",
    "23_tga_balance": "weekly", "24_net_liquidity": "daily", "25_sofr": "daily",
    "60_fed_funds_futures": "daily", "62_sofr_futures": "daily",
    "2_russell_2000": "daily", "6a_sp500_to_ma200": "daily",
    "57_cu_au_ratio": "daily", "63_brent_crude": "daily",
    "64_nikkei_225": "daily", "65_em_indices": "daily",
    "66_xau_jpy": "daily", "67_gold_silver_ratio": "daily",
    "82_credit_etf_proxies": "daily", "70_sector_etfs": "daily",
    "73_vix_term_structure": "daily", "78_spx_iv_skew": "daily",
    "71_eu_yields": "daily", "75_treasury_curve": "daily",
    "1_sp500_forward_pe": "daily",
    # ── Weekly ────────────────────────────────
    "37_nfci": "weekly", "49_continuing_claims": "weekly",
    "32_fed_balance_sheet": "weekly", "31_initial_claims": "weekly",
    "22_cot_positioning": "weekly", "55_mortgage_rate_30y": "weekly",
    "44_gasoline_price": "weekly",
    # ── Monthly ───────────────────────────────
    "53_headline_cpi": "monthly", "41_core_inflation": "monthly",
    "42_core_pce": "monthly", "43_pce_headline": "monthly",
    "52_ppi": "monthly", "29_unemployment": "monthly",
    "30_payrolls": "monthly", "39_consumer_sentiment": "monthly",
    "47_m2": "monthly", "46_sahm_rule": "monthly",
    "48_jolts": "monthly", "50_retail_sales": "monthly",
    "51_housing_starts": "monthly", "59_industrial_production": "monthly",
    "58_bank_reserves": "monthly", "68_cpi_components": "monthly",
    "69_oecd_cli": "monthly", "72_global_cpi": "monthly",
    "81_global_pmi": "monthly", "40_ism_pmi": "monthly",
    "54_fx_pairs": "daily", "38_durable_goods": "monthly",
    "16b_natural_gas_fred": "daily",
    # ── Quarterly ─────────────────────────────
    # Note: "quarterly" SLA=130d is too tight for international GDP which can lag 6+ months.
    # 78_intl_gdp uses a custom override below; 62_sloos is quarterly but releases in Jan/Apr/Jul/Oct.
    "21_us_gdp": "quarterly", "74_intl_gdp": "quarterly", "78_intl_gdp": "quarterly",
    "12_shiller_cape": "monthly", "7_shiller_cape": "monthly",
    "6b_marketcap_to_gdp": "quarterly",
    "3_sp500_fundamentals": "monthly",
    "4_put_call_ratio": "daily",
    "62_sloos": "quarterly",        # SLOOS is released quarterly (Jan/Apr/Jul/Oct)
    "77_sector_pe_ratios": "weekly",
    "79_earnings_calendar": "weekly",
    "80_money_measures": "monthly",
    "83_fama_french_5factors": "monthly",
    # ── Key aliases (actual cache keys differ from initial SLA map) ──────────
    "67_oecd_cli": "monthly",       # OECD CLI (was wrongly mapped as 69_oecd_cli)
    "68_cpi_components": "monthly",
    "72_global_cpi": "monthly",
}

# IBKR symbols expected to have fresh ticks during US trading hours
IBKR_LIVE_SYMBOLS = {
    "ES", "NQ", "RTY", "GC", "SI", "HG", "CL", "NG",
    "ZN", "ZB", "ZF", "ZT", "10Y", "2YY",
    "EURUSD", "USDJPY",
    # VIX: index, only ticks during regular session
}


def get_sla_for(indicator_key: str) -> tuple[str, float, float]:
    """Return (tier, high_threshold_days, low_threshold_days) for an indicator."""
    tier = INDICATOR_FREQUENCY.get(indicator_key, "monthly")
    return tier, SLA_TIERS[tier], LOW_THRESHOLDS[tier]
