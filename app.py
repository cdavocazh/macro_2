"""
Streamlit Dashboard for Macroeconomic Indicators
Displays 10 key macroeconomic indicators with manual refresh capability.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from data_aggregator import get_aggregator
from utils.helpers import format_value

# Source URLs for all indicators
SOURCE_URLS = {
    'sp500_forward_pe': 'https://en.macromicro.me/charts/11/sp-500-forward-pe-ratio',
    'russell_2000': 'https://finance.yahoo.com/quote/IWN/',
    'sp500_fundamentals': 'https://finance.yahoo.com/quote/SPY/',
    'put_call_ratio': 'https://ycharts.com/indicators/cboe_equity_put_call_ratio',
    'skew': 'https://www.cboe.com/tradable_products/vix/skew_index/',
    'sp500_ma200': 'https://finance.yahoo.com/quote/%5EGSPC/',
    'marketcap_gdp': 'https://fred.stlouisfed.org/series/DDDM01USA156NWDB',
    'shiller_cape': 'http://www.econ.yale.edu/~shiller/data.htm',
    'vix': 'https://www.cboe.com/tradable_products/vix/',
    'move': 'https://fred.stlouisfed.org/series/BAMLHYH0A0HYM2TRIV',
    'dxy': 'https://finance.yahoo.com/quote/DX-Y.NYB/',
    '10y_yield': 'https://finance.yahoo.com/quote/%5ETNX/',
    'ism_pmi': 'https://tradingeconomics.com/united-states/manufacturing-pmi',
    'gold': 'https://finance.yahoo.com/quote/GC%3DF/',
    'silver': 'https://finance.yahoo.com/quote/SI%3DF/',
    'crude_oil': 'https://finance.yahoo.com/quote/CL%3DF/',
    'copper': 'https://finance.yahoo.com/quote/HG%3DF/',
    'es_futures': 'https://finance.yahoo.com/quote/ES%3DF/',
    'rty_futures': 'https://finance.yahoo.com/quote/RTY%3DF/',
    'jpy': 'https://finance.yahoo.com/quote/JPY%3DX/'
}

# Page configuration
st.set_page_config(
    page_title="Macro Indicators Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        margin: 10px 0;
    }
    .error-card {
        background-color: #ffebee;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
        border-left: 4px solid #f44336;
    }
    .success-card {
        background-color: #e8f5e9;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
        border-left: 4px solid #4caf50;
    }
    h1 {
        color: #1f77b4;
    }
    .stButton>button {
        width: 100%;
        background-color: #1f77b4;
        color: white;
        font-weight: bold;
    }

    /* ── Compact Layout ── */
    [data-testid="stMetric"] {
        padding: 0.2rem 0.5rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.72rem !important;
        min-height: unset !important;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
        line-height: 1.3 !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 0.7rem !important;
    }
    [data-testid="stHeading"] h2 {
        font-size: 1.0rem !important;
        margin: 0.3rem 0 0.1rem 0 !important;
        padding: 0 !important;
    }
    [data-testid="stHeading"] h3 {
        font-size: 0.88rem !important;
        margin: 0.2rem 0 0.1rem 0 !important;
        padding: 0 !important;
    }
    [data-testid="stCaptionContainer"] {
        margin-top: -0.3rem !important;
        margin-bottom: 0 !important;
    }
    [data-testid="stCaptionContainer"] p {
        font-size: 0.68rem !important;
        line-height: 1.2 !important;
    }
    [data-testid="stExpander"] {
        margin: 0.1rem 0 !important;
    }
    [data-testid="stExpander"] summary {
        font-size: 0.75rem !important;
        padding: 0.2rem 0.5rem !important;
    }
    [data-testid="column"] {
        padding: 0 0.3rem !important;
    }
    [data-testid="stVerticalBlock"] > div {
        gap: 0.3rem !important;
    }
    [data-testid="stAlert"] {
        padding: 0.3rem 0.6rem !important;
        font-size: 0.75rem !important;
        margin: 0.1rem 0 !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 0.3rem !important;
    }
    hr {
        margin: 0.3rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)

# Title and description
st.title("📊 Macroeconomic Indicators Dashboard")
st.markdown("Real-time tracking of 59+ macroeconomic indicators for market analysis")

# Sidebar
with st.sidebar:
    st.header("⚙️ Controls")

    # Refresh button
    if st.button("🔄 Refresh All Data", key="refresh_button"):
        with st.spinner("Fetching latest data..."):
            aggregator = get_aggregator()
            aggregator.fetch_all_indicators()
            st.success("Data refreshed successfully!")
            st.rerun()

    # CSV export button
    if st.button("📥 Export to CSV", key="export_csv_button"):
        aggregator = get_aggregator()
        if aggregator.indicators:
            result = aggregator.export_to_csv()
            if 'error' in result:
                st.error(result['error'])
            else:
                st.success(f"Exported {result['count']} files to `{result['output_dir']}/`")
                for f in result['files']:
                    st.caption(f"  {f}")
        else:
            st.warning("No data loaded yet. Refresh first.")

    st.markdown("---")

    with st.expander("ℹ️ About & Data Sources"):
        st.markdown("**75+ indicators** across 8 tabs: Valuation, Indices, Volatility, Macro/FX, Commodities, Financials, Rates/Credit, Economic Activity")
        st.caption("Sources: FRED, Yahoo Finance, SEC EDGAR, OpenBB, Shiller, CBOE, CFTC, MOF Japan, AAII")

# Initialize aggregator — auto-reload when cache file is newer than in-memory
aggregator = get_aggregator()
aggregator.reload_if_stale()

if not aggregator.indicators:
    with st.spinner("No cached data found. Fetching live data..."):
        aggregator.fetch_all_indicators()

# Display last update time and data source
if aggregator.last_update:
    label = "📅 Last Updated"
    if aggregator.loaded_from_cache:
        label += " (from local cache)"
    st.info(f"{label}: {aggregator.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

import plotly.graph_objects as go


def _render_history_expander(data, label, color='#1f77b4', hist_key='historical',
                             value_suffix='', convert_fn=None):
    """Render an expandable 3-month price history chart below an indicator.

    Args:
        data: indicator dict containing a 'historical' pd.Series
        label: display name for the chart y-axis and hover
        color: hex color for the line
        hist_key: key to pull the pd.Series from data
        value_suffix: appended to hover values (e.g. '%')
        convert_fn: optional function to transform the series (e.g. divide by 1e6)
    """
    hist = data.get(hist_key)
    if hist is None or not hasattr(hist, 'index') or len(hist) == 0:
        return

    # Robustly convert index to tz-naive DatetimeIndex
    try:
        hist = hist.copy()
        if not isinstance(hist.index, pd.DatetimeIndex):
            hist.index = pd.to_datetime(hist.index, utc=True)
        if hasattr(hist.index, 'tz') and hist.index.tz is not None:
            hist.index = hist.index.tz_convert(None)
    except Exception:
        try:
            hist.index = pd.to_datetime(hist.index)
        except Exception:
            return  # cannot parse dates, skip chart

    if convert_fn is not None:
        hist = convert_fn(hist)

    # Filter to 3 months
    cutoff_3m = pd.Timestamp.now() - pd.Timedelta(days=92)
    hist_3m = hist[hist.index >= cutoff_3m]
    if len(hist_3m) < 2:
        hist_3m = hist.tail(65)  # fallback: last ~3 months of data points

    # Compute fill color from hex
    hex_c = color.lstrip('#')
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
    fill_rgba = f'rgba({r},{g},{b},0.08)'

    hover_fmt = '%{y:,.2f}' + value_suffix if value_suffix else '%{y:,.2f}'

    with st.expander("📈 3M Price History"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_3m.index, y=hist_3m.values,
            name=label, line=dict(color=color, width=1.5),
            fill='tozeroy', fillcolor=fill_rgba,
            hovertemplate='%{x|%b %d, %Y}: ' + hover_fmt + '<extra></extra>'
        ))
        fig.update_layout(
            xaxis=dict(
                rangeselector=dict(
                    buttons=[
                        dict(count=7, label="1W", step="day", stepmode="backward"),
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                    ],
                    bgcolor='#f0f2f6',
                ),
                rangeslider=dict(visible=True, thickness=0.05),
            ),
            yaxis=dict(title=label),
            height=320,
            margin=dict(l=50, r=20, t=10, b=10),
            showlegend=False,
            hovermode='x unified',
        )
        st.plotly_chart(fig, use_container_width=True)


# Create tabs for different indicator categories
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📈 Valuation Metrics",
    "📊 Market Indices",
    "⚡ Volatility & Risk",
    "🌍 Macro & Currency",
    "💰 Commodities",
    "🏢 Large-cap Financials",
    "📉 Rates & Credit",
    "📊 Economic Activity",
])

# Tab 1: Valuation Metrics
with tab1:
    st.header("Valuation Metrics")

    col1, col2 = st.columns(2)

    # 1. S&P 500 Forward P/E
    with col1:
        st.subheader(f"1. [S&P 500 Forward P/E]({SOURCE_URLS['sp500_forward_pe']})")
        data = aggregator.get_indicator('1_sp500_forward_pe')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
            if 'note' in data:
                st.info(data['note'])
        else:
            value = data.get('sp500_forward_pe', 'N/A')
            st.metric("Forward P/E Ratio", format_value(value))

    # 3. S&P 500 Trailing P/E & P/B
    with col2:
        st.subheader(f"3. [S&P 500 Trailing P/E & P/B]({SOURCE_URLS['sp500_fundamentals']})")
        data = aggregator.get_indicator('3_sp500_fundamentals')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            pe_value = data.get('sp500_pe_trailing', 'N/A')
            pb_value = data.get('sp500_pb', 'N/A')
            col_a, col_b = st.columns(2)
            with col_a:
                st.metric("Trailing P/E", format_value(pe_value))
            with col_b:
                st.metric("P/B Ratio", format_value(pb_value))

    # 7. Shiller CAPE Ratio
    st.subheader(f"7. [Shiller CAPE Ratio]({SOURCE_URLS['shiller_cape']})")
    data = aggregator.get_indicator('7_shiller_cape')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
    else:
        cape_value = data.get('shiller_cape', 'N/A')
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            st.metric("CAPE Ratio", format_value(cape_value))
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
        with col3:
            if 'interpretation' in data:
                st.info("**Interpretation:**\n" + "\n".join([f"- {k}: {v}" for k, v in data['interpretation'].items()]))
        _render_history_expander(data, 'Shiller CAPE', '#8e24aa')

    # 6b. Market Cap / GDP
    st.subheader(f"6b. [S&P 500 Market Cap / US GDP]({SOURCE_URLS['marketcap_gdp']}) (Buffett Indicator)")
    data = aggregator.get_indicator('6b_marketcap_to_gdp')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
        if 'note' in data:
            st.info(data['note'])
    else:
        ratio = data.get('marketcap_to_gdp_ratio', 'N/A')
        st.metric("Market Cap / GDP (%)", format_value(ratio))
        if 'interpretation' in data:
            st.info(data['interpretation'])

    # ── OpenBB Valuation Metrics ────────────────────────────────────────
    st.subheader("65. S&P 500 Valuation Multiples")
    mult_data = aggregator.get_indicator('65_sp500_multiples')
    if 'error' in mult_data:
        st.error(f"⚠️ {mult_data['error']}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Forward P/E", format_value(mult_data.get('forward_pe')))
        with c2:
            st.metric("PEG Ratio", format_value(mult_data.get('peg_ratio')))
        with c3:
            st.metric("Price/Sales", format_value(mult_data.get('price_to_sales')))
        with c4:
            st.metric("Price/Cash", format_value(mult_data.get('price_to_cash')))
        st.caption(f"Source: {mult_data.get('source', 'N/A')}")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("74. Sector P/E Ratios")
        spe_data = aggregator.get_indicator('74_sector_pe')
        if 'error' in spe_data:
            st.error(f"⚠️ {spe_data['error']}")
        else:
            sectors = spe_data.get('sectors', {})
            if sectors:
                import pandas as pd
                sdf = pd.DataFrame(list(sectors.items()), columns=['Sector', 'P/E'])
                sdf = sdf.sort_values('P/E', ascending=False)
                st.dataframe(sdf.set_index('Sector'), use_container_width=True)

    with col2:
        st.subheader("82. Equity Risk Premium")
        erp_data = aggregator.get_indicator('82_erp')
        if 'error' in erp_data:
            st.error(f"⚠️ {erp_data['error']}")
        else:
            e1, e2 = st.columns(2)
            with e1:
                st.metric("ERP (Trailing)", f"{format_value(erp_data.get('equity_risk_premium'))}%")
                st.caption(f"Earnings Yield: {format_value(erp_data.get('earnings_yield'))}%")
            with e2:
                st.metric("ERP (Forward)", f"{format_value(erp_data.get('forward_erp'))}%")
                st.caption(f"10Y Real Yield: {format_value(erp_data.get('real_yield_10y'))}%")

# Tab 2: Market Indices
with tab2:
    st.header("Market Indices")

    # Futures Indices
    st.subheader("Futures Indices")
    col1, col2 = st.columns(2)

    # ES Futures (S&P 500 E-mini)
    with col1:
        st.subheader(f"[ES - S&P 500 E-mini]({SOURCE_URLS['es_futures']})")
        data = aggregator.get_indicator('17_es_futures')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("ES Futures Price", format_value(price, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")

    # RTY Futures (Russell 2000 E-mini)
    with col2:
        st.subheader(f"[RTY - Russell 2000 E-mini]({SOURCE_URLS['rty_futures']})")
        data = aggregator.get_indicator('18_rty_futures')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("RTY Futures Price", format_value(price, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")

    # S&P 500 Market Breadth (Advance/Decline)
    st.subheader("S&P 500 Market Breadth Indicator")
    data = aggregator.get_indicator('19_sp500_breadth')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
    else:
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            advancing = data.get('advancing_stocks', 'N/A')
            st.metric("Advancing Stocks", advancing)

        with col2:
            declining = data.get('declining_stocks', 'N/A')
            st.metric("Declining Stocks", declining)

        with col3:
            net_advances = data.get('net_advances', 'N/A')
            st.metric("Net Advances", net_advances)

        with col4:
            breadth_pct = data.get('breadth_percentage', 'N/A')
            st.metric("Breadth %", f"{format_value(breadth_pct, 1)}%")

        # Display interpretation
        interpretation = data.get('interpretation', '')
        if 'Strong bullish' in interpretation:
            st.success(f"✅ {interpretation}")
        elif 'Moderate bullish' in interpretation:
            st.info(f"ℹ️ {interpretation}")
        elif 'Moderate bearish' in interpretation:
            st.warning(f"⚠️ {interpretation}")
        else:
            st.error(f"🔴 {interpretation}")

        # Display additional info
        col1, col2 = st.columns(2)
        with col1:
            ad_ratio = data.get('ad_ratio', 'N/A')
            if ad_ratio != 'N/A' and ad_ratio != float('inf'):
                st.caption(f"A/D Ratio: {format_value(ad_ratio, 2)}")
        with col2:
            st.caption(f"Sample: {data.get('total_stocks', 'N/A')} stocks")


    # 2. Russell 2000 Indices
    st.subheader(f"2. [Russell 2000 Value vs Growth]({SOURCE_URLS['russell_2000']})")
    data = aggregator.get_indicator('2_russell_2000')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            value_data = data.get('russell_2000_value', {})
            price = value_data.get('latest_price', 'N/A')
            change = value_data.get('change_1d', 0)
            st.metric("Russell 2000 Value", format_value(price), f"{format_value(change, 2)}%")

        with col2:
            growth_data = data.get('russell_2000_growth', {})
            price = growth_data.get('latest_price', 'N/A')
            change = growth_data.get('change_1d', 0)
            st.metric("Russell 2000 Growth", format_value(price), f"{format_value(change, 2)}%")

        with col3:
            ratio = data.get('value_growth_ratio', 'N/A')
            st.metric("Value/Growth Ratio", format_value(ratio, 3))

    # 6a. S&P 500 / 200MA
    st.subheader(f"6a. [S&P 500 / 200-Day Moving Average]({SOURCE_URLS['sp500_ma200']})")
    data = aggregator.get_indicator('6a_sp500_to_ma200')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            price = data.get('sp500_price', 'N/A')
            st.metric("S&P 500 Price", format_value(price, 2))
        with col2:
            ma200 = data.get('sp500_ma200', 'N/A')
            st.metric("200-Day MA", format_value(ma200, 2))
        with col3:
            ratio = data.get('sp500_to_ma200_ratio', 'N/A')
            st.metric("Price / MA200", format_value(ratio, 4))
            if isinstance(ratio, (int, float)):
                if ratio > 1.1:
                    st.caption("🔴 Overbought territory")
                elif ratio < 0.9:
                    st.caption("🟢 Oversold territory")
                else:
                    st.caption("🟡 Normal range")


    # SPY/RSP Market Concentration Ratio
    st.subheader("Market Concentration (SPY/RSP Ratio)")
    conc_data = aggregator.get_indicator('55_market_concentration')
    if 'error' in conc_data:
        st.error(f"⚠️ {conc_data['error']}")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            spy_rsp = conc_data.get('spy_rsp_ratio', 'N/A')
            chg_1d = conc_data.get('change_1d', 0)
            st.metric("SPY/RSP Ratio", format_value(spy_rsp, 4), f"{format_value(chg_1d, 2)}%")
        with col2:
            chg_30d = conc_data.get('change_30d', 0)
            st.metric("30-Day Change", f"{format_value(chg_30d, 2)}%")
        with col3:
            interp = conc_data.get('interpretation', '')
            if interp:
                st.caption(f"ℹ️ {interp}")
        st.caption(f"As of: {conc_data.get('latest_date', 'N/A')} | SPY (cap-weighted) vs RSP (equal-weight)")
        _render_history_expander(conc_data, 'SPY/RSP Ratio', '#7b1fa2')

    # ── OpenBB Market Indicators ────────────────────────────────────────
    st.subheader("69. Fama-French 5-Factor Returns")
    ff_data = aggregator.get_indicator('69_fama_french')
    if 'error' in ff_data:
        st.error(f"⚠️ {ff_data['error']}")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Mkt-RF", f"{format_value(ff_data.get('mkt_rf'))}%")
        with c2:
            st.metric("SMB", f"{format_value(ff_data.get('smb'))}%")
        with c3:
            st.metric("HML", f"{format_value(ff_data.get('hml'))}%")
        with c4:
            st.metric("RMW", f"{format_value(ff_data.get('rmw'))}%")
        with c5:
            st.metric("CMA", f"{format_value(ff_data.get('cma'))}%")
        st.caption(f"Monthly factor returns | RF: {format_value(ff_data.get('rf'))}% | Source: {ff_data.get('source', 'N/A')}")

    st.subheader("73. Upcoming Earnings Calendar")
    earn_data = aggregator.get_indicator('73_earnings_calendar')
    if 'error' in earn_data:
        st.error(f"⚠️ {earn_data['error']}")
    else:
        earnings = earn_data.get('earnings', [])
        if earnings:
            import pandas as pd
            edf = pd.DataFrame(earnings)
            st.dataframe(edf, use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming earnings in the next 7 days.")
        st.caption(f"Period: {earn_data.get('period', 'N/A')} | Source: {earn_data.get('source', 'N/A')}")

# Tab 3: Volatility & Risk
with tab3:
    st.header("Volatility & Risk Indicators")

    col1, col2, col3 = st.columns(3)

    # 8. VIX
    with col1:
        st.subheader(f"8. [VIX]({SOURCE_URLS['vix']})")
        data = aggregator.get_indicator('8_vix')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            vix_value = data.get('vix', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("VIX", format_value(vix_value, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            _render_history_expander(data, 'VIX', '#e53935')

    # 9. MOVE Index
    with col2:
        st.subheader(f"9. [MOVE]({SOURCE_URLS['move']})")
        data = aggregator.get_indicator('9_move_index')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            move_value = data.get('move', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("MOVE Index", format_value(move_value, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            _render_history_expander(data, 'MOVE Index', '#ff9800')

    # 8b. VIX/MOVE Ratio
    with col3:
        st.subheader("8b. VIX/MOVE Ratio")
        data = aggregator.get_indicator('8b_vix_move_ratio')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            ratio = data.get('vix_move_ratio', 'N/A')
            st.metric("VIX/MOVE Ratio", format_value(ratio, 3))

    col1, col2 = st.columns(2)

    # 4. Put/Call Ratio
    with col1:
        st.subheader(f"4. [S&P 500 Put/Call Ratio]({SOURCE_URLS['put_call_ratio']})")
        data = aggregator.get_indicator('4_put_call_ratio')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
            if 'note' in data:
                st.info(data['note'])
        else:
            pc_ratio = data.get('sp500_put_call_ratio', 'N/A')
            st.metric("Put/Call Ratio", format_value(pc_ratio, 3))
            _render_history_expander(data, 'Put/Call Ratio', '#7b1fa2')

    # 5. SPX Call Skew
    with col2:
        st.subheader(f"5. [SPX Call Skew (CBOE SKEW)]({SOURCE_URLS['skew']})")
        data = aggregator.get_indicator('5_spx_call_skew')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            skew_value = data.get('spx_call_skew', 'N/A')
            st.metric("CBOE SKEW", format_value(skew_value, 2))
            if 'interpretation' in data:
                st.caption("**Interpretation:**")
                for k, v in data['interpretation'].items():
                    st.caption(f"- {k}: {v}")
            _render_history_expander(data, 'CBOE SKEW', '#1565c0')

    # ── OpenBB Volatility Indicators ────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        st.subheader("63. VIX Futures Curve")
        vfc_data = aggregator.get_indicator('63_vix_futures_curve')
        if 'error' in vfc_data:
            st.error(f"⚠️ {vfc_data['error']}")
        else:
            st.metric("VIX Spot", format_value(vfc_data.get('vix_spot')))
            contango = vfc_data.get('contango_pct')
            if contango is not None:
                st.metric("Contango", f"{format_value(contango)}%")
            n_exp = vfc_data.get('n_expirations', 0)
            st.caption(f"Expirations: {n_exp} | Source: {vfc_data.get('source', 'N/A')}")
            _render_history_expander(vfc_data, 'VIX Spot', '#d32f2f')

    with col2:
        st.subheader("64. SPY Put/Call (OI)")
        pcoi_data = aggregator.get_indicator('64_spy_put_call_oi')
        if 'error' in pcoi_data:
            st.error(f"⚠️ {pcoi_data['error']}")
        else:
            vol_ratio = pcoi_data.get('put_call_volume_ratio')
            oi_ratio = pcoi_data.get('put_call_oi_ratio')
            st.metric("P/C Volume Ratio", format_value(vol_ratio, 3))
            if oi_ratio is not None:
                st.metric("P/C OI Ratio", format_value(oi_ratio, 3))
            st.caption(f"Source: {pcoi_data.get('source', 'N/A')}")
            _render_history_expander(pcoi_data, 'Put/Call Ratio', '#7b1fa2')

    with col3:
        st.subheader("70. SPX IV Skew")
        ivs_data = aggregator.get_indicator('70_iv_skew')
        if 'error' in ivs_data:
            st.error(f"⚠️ {ivs_data['error']}")
        else:
            skew_25d = ivs_data.get('iv_skew_25d')
            skew_idx = ivs_data.get('skew_index')
            if skew_25d is not None:
                st.metric("25Δ Skew", f"{format_value(skew_25d)}%")
                put_iv = ivs_data.get('otm_put_iv')
                call_iv = ivs_data.get('otm_call_iv')
                if put_iv and call_iv:
                    st.caption(f"OTM Put IV: {put_iv}% | OTM Call IV: {call_iv}%")
            elif skew_idx is not None:
                st.metric("SKEW Index", format_value(skew_idx))
            st.caption(f"Source: {ivs_data.get('source', 'N/A')}")
            _render_history_expander(ivs_data, 'IV Skew', '#1565c0')

# Tab 4: Macro & Currency
with tab4:
    st.header("Macro & Currency")

    # Currency Indices
    st.subheader("Currency Indices")
    fx_data = aggregator.get_indicator('54_fx_pairs')
    col1, col2, col3, col4, col5 = st.columns(5)

    # DXY
    with col1:
        data = aggregator.get_indicator('10_dxy')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            st.metric("DXY", format_value(data.get('dxy', 'N/A'), 2), f"{format_value(data.get('change_1d', 0), 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            _render_history_expander(data, 'DXY', '#2e7d32')

    # USD/JPY
    with col2:
        data = aggregator.get_indicator('20_jpy')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            st.metric("USD/JPY", format_value(data.get('jpy_rate', 'N/A'), 2), f"{format_value(data.get('change_1d', 0), 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            _render_history_expander(data, 'USD/JPY', '#d84315')

    # EUR/USD
    with col3:
        if 'error' not in fx_data:
            st.metric("EUR/USD", format_value(fx_data.get('eur_usd', 'N/A'), 4), f"{format_value(fx_data.get('eur_usd_change_1d', 0), 2)}%")
            if 'historical_eur_usd' in fx_data:
                _render_history_expander(fx_data, 'EUR/USD', '#1565c0', hist_key='historical_eur_usd')

    # GBP/USD
    with col4:
        if 'error' not in fx_data:
            st.metric("GBP/USD", format_value(fx_data.get('gbp_usd', 'N/A'), 4), f"{format_value(fx_data.get('gbp_usd_change_1d', 0), 2)}%")
            if 'historical_gbp_usd' in fx_data:
                _render_history_expander(fx_data, 'GBP/USD', '#1b5e20', hist_key='historical_gbp_usd')

    # EUR/JPY
    with col5:
        if 'error' not in fx_data:
            st.metric("EUR/JPY", format_value(fx_data.get('eur_jpy', 'N/A'), 4), f"{format_value(fx_data.get('eur_jpy_change_1d', 0), 2)}%")
            if 'historical_eur_jpy' in fx_data:
                _render_history_expander(fx_data, 'EUR/JPY', '#e65100', hist_key='historical_eur_jpy')


    # Liquidity & Rates
    st.subheader("Liquidity & Short-Term Rates")

    col1, col2 = st.columns(2)

    # TGA Balance
    with col1:
        st.subheader("[TGA Balance](https://fred.stlouisfed.org/series/WTREGEN)")
        data = aggregator.get_indicator('23_tga_balance')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            tga_b = data.get('tga_balance_billions', 'N/A')
            change_pct = data.get('change_wow_pct', 0)
            st.metric("TGA Balance ($B)", format_value(tga_b, 1), f"{format_value(change_pct, 1)}% WoW")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            st.caption("High TGA = Treasury draining liquidity")
            _render_history_expander(data, 'TGA Balance ($M)', '#6a1b9a')

    # Net Liquidity
    with col2:
        st.subheader("[Fed Net Liquidity](https://fred.stlouisfed.org/series/WALCL)")
        data = aggregator.get_indicator('24_net_liquidity')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            net_liq_t = data.get('net_liquidity_trillions', 'N/A')
            change_pct = data.get('change_pct', 0)
            st.metric("Net Liquidity ($T)", format_value(net_liq_t, 3), f"{format_value(change_pct, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'interpretation' in data:
                st.caption(f"ℹ️ {data['interpretation']}")
            _render_history_expander(data, 'Net Liquidity ($M)', '#1565c0')

    # M2 Money Supply
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("[M2 Money Supply](https://fred.stlouisfed.org/series/M2SL)")
        m2_data = aggregator.get_indicator('47_m2')
        if 'error' in m2_data:
            st.error(f"⚠️ {m2_data['error']}")
        else:
            m2_val = m2_data.get('m2_trillions', 'N/A')
            m2_yoy = m2_data.get('m2_yoy_growth', 0)
            st.metric("M2 ($T)", format_value(m2_val, 2), f"{format_value(m2_yoy, 1)}% YoY")
            st.caption(f"As of: {m2_data.get('latest_date', 'N/A')}")
            if 'interpretation' in m2_data:
                st.caption(f"ℹ️ {m2_data['interpretation']}")
            _render_history_expander(m2_data, 'M2 ($T)', '#00695c')

    col1, col2 = st.columns(2)

    # SOFR
    with col1:
        st.subheader("[SOFR](https://fred.stlouisfed.org/series/SOFR)")
        data = aggregator.get_indicator('25_sofr')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            sofr_val = data.get('sofr', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("SOFR Rate (%)", format_value(sofr_val, 4), f"{format_value(change, 4)} bps")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            _render_history_expander(data, 'SOFR (%)', '#00838f', value_suffix='%')

    # US 2Y Yield
    with col2:
        st.subheader("[US 2-Year Treasury Yield](https://fred.stlouisfed.org/series/DGS2)")
        data = aggregator.get_indicator('26_us_2y_yield')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            yield_2y = data.get('us_2y_yield', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("2Y Yield (%)", format_value(yield_2y, 3), f"{format_value(change, 4)}")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'spread_2s10s' in data:
                spread = data['spread_2s10s']
                clr = "🔴" if spread < 0 else "🟢"
                st.caption(f"{clr} 2s10s Spread: {spread:.2f}% {'(inverted)' if spread < 0 else ''}")
            _render_history_expander(data, 'US 2Y Yield (%)', '#1976d2', value_suffix='%')

    # Japan 2Y Yield & US-JP Spread
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("[Japan 2Y Yield](https://www.mof.go.jp/english/policy/jgbs/reference/interest_rate/index.htm)")
        data = aggregator.get_indicator('27_japan_2y_yield')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            jp_2y = data.get('japan_2y_yield', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("JGB 2Y Yield (%)", format_value(jp_2y, 3), f"{format_value(change, 4)}")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'japan_10y_yield' in data:
                st.caption(f"JGB 10Y: {data['japan_10y_yield']}%")
            _render_history_expander(data, 'JGB 2Y Yield (%)', '#e65100', value_suffix='%')

    with col2:
        st.subheader("US 2Y - Japan 2Y Spread")
        data = aggregator.get_indicator('28_us2y_jp2y_spread')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            spread = data.get('spread', 'N/A')
            us_2y = data.get('us_2y_yield', 'N/A')
            jp_2y = data.get('japan_2y_yield', 'N/A')
            st.metric("Yield Spread (%)", format_value(spread, 3))
            st.caption(f"US 2Y: {us_2y}% | JP 2Y: {jp_2y}%")
            if 'interpretation' in data:
                st.caption(f"ℹ️ {data['interpretation']}")
            _render_history_expander(data, 'US-JP 2Y Spread (%)', '#ff7f0e', value_suffix='%')

    # US-JP 2Y Spread historical chart
    spread_data = aggregator.get_indicator('28_us2y_jp2y_spread')
    if 'error' not in spread_data and 'historical' in spread_data:
      with st.expander("📈 US-JP 2Y Yield Spread Chart"):
        import plotly.graph_objects as go
        hist_spread = spread_data['historical']

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_spread.index, y=hist_spread.values,
            name='US 2Y - JP 2Y Spread', line=dict(color='#ff7f0e'),
            fill='tozeroy', fillcolor='rgba(255,127,14,0.1)'
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
        fig.update_layout(
            title="US 2Y - Japan 2Y Yield Spread (Carry Trade Indicator)",
            xaxis_title="Date",
            yaxis_title="Spread (percentage points)",
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)

    # Net Liquidity historical chart
    net_liq_data = aggregator.get_indicator('24_net_liquidity')
    if 'error' not in net_liq_data and 'historical' in net_liq_data:
      with st.expander("📈 Net Liquidity Chart"):
        import plotly.graph_objects as go
        hist = net_liq_data['historical']
        # Convert to trillions for readability
        hist_t = hist / 1_000_000

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist_t.index, y=hist_t.values,
            name='Net Liquidity', line=dict(color='#1f77b4'),
            fill='tozeroy', fillcolor='rgba(31,119,180,0.1)'
        ))
        fig.update_layout(
            title="Fed Net Liquidity (Fed Assets - TGA - ON RRP)",
            xaxis_title="Date",
            yaxis_title="Trillions USD",
            hovermode='x unified',
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)


    # 10Y Yield vs ISM PMI Chart
    st.subheader(f"[10-Year Treasury Yield]({SOURCE_URLS['10y_yield']}) vs [ISM Manufacturing PMI]({SOURCE_URLS['ism_pmi']})")

    # Get data
    yield_data = aggregator.get_indicator('11_10y_yield')
    ism_data = aggregator.get_indicator('12_ism_pmi')

    if 'error' in yield_data or 'error' in ism_data:
        if 'error' in yield_data:
            st.error(f"⚠️ 10Y Yield: {yield_data['error']}")
        if 'error' in ism_data:
            st.error(f"⚠️ ISM PMI: {ism_data['error']}")
    else:
        # Display current values
        col1, col2, col3 = st.columns(3)
        with col1:
            yield_value = yield_data.get('10y_yield', 'N/A')
            st.metric("10-Year Treasury Yield", f"{format_value(yield_value, 2)}%")
            st.caption(f"As of: {yield_data.get('latest_date', 'N/A')}")
            _render_history_expander(yield_data, '10Y Yield (%)', '#1565c0', value_suffix='%')
        with col2:
            ism_value = ism_data.get('ism_pmi', 'N/A')
            st.metric("ISM Manufacturing PMI", format_value(ism_value, 1))
            st.caption(f"As of: {ism_data.get('latest_date', 'N/A')}")
            if 'note' in ism_data:
                st.caption(f"ℹ️ {ism_data['note']}")
            _render_history_expander(ism_data, 'ISM PMI', '#e65100')
        with col3:
            if isinstance(yield_value, (int, float)) and isinstance(ism_value, (int, float)):
                gap = yield_value - ism_value
                st.metric("10Y Yield - ISM Gap", format_value(gap, 2))
                if gap > 0:
                    st.caption("🔴 Yield > ISM (potential slowdown)")
                else:
                    st.caption("🟢 ISM > Yield (economic strength)")

        # Historical chart
        if 'historical' in yield_data and 'historical' in ism_data:
          with st.expander("📈 10Y Yield vs ISM PMI Chart"):
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            yield_hist = yield_data['historical']
            ism_hist = ism_data['historical']

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(x=yield_hist.index, y=yield_hist.values, name="10Y Treasury Yield", line=dict(color='blue')),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=ism_hist.index, y=ism_hist.values, name="ISM Manufacturing PMI", line=dict(color='orange')),
                secondary_y=True,
            )
            fig.update_layout(
                title_text="10-Year Treasury Yield vs ISM Manufacturing PMI",
                hovermode='x unified',
                height=500
            )
            fig.update_yaxes(title_text="10Y Yield (%)", secondary_y=False)
            fig.update_yaxes(title_text="ISM PMI", secondary_y=True)

            st.plotly_chart(fig, use_container_width=True)

    # ── OpenBB Money Supply ─────────────────────────────────────────────
    st.subheader("80. Money Supply (M1/M2)")
    mm_data = aggregator.get_indicator('80_money_measures')
    if 'error' in mm_data:
        st.error(f"⚠️ {mm_data['error']}")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("M1 Level (B)", format_value(mm_data.get('m1_level'), 0))
        with c2:
            st.metric("M1 YoY%", f"{format_value(mm_data.get('m1_yoy'))}%")
        with c3:
            st.metric("M2 Level (B)", format_value(mm_data.get('m2_level'), 0))
        with c4:
            st.metric("M2 YoY%", f"{format_value(mm_data.get('m2_yoy'))}%")
        st.caption(f"As of: {mm_data.get('latest_date', 'N/A')} | Source: {mm_data.get('source', 'N/A')}")
        _render_history_expander(mm_data, 'M2 Money Supply', '#1565c0')

# Tab 5: Commodities
with tab5:
    st.header("Commodities Futures")

    col1, col2 = st.columns(2)

    # Gold
    with col1:
        st.subheader(f"[Gold (GC)]({SOURCE_URLS['gold']})")
        data = aggregator.get_indicator('13_gold')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("Gold Price (USD/oz)", format_value(price, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")
            _render_history_expander(data, 'Gold (USD/oz)', '#FFD700')

    # Silver
    with col2:
        st.subheader(f"[Silver (SI)]({SOURCE_URLS['silver']})")
        data = aggregator.get_indicator('14_silver')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("Silver Price (USD/oz)", format_value(price, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")
            _render_history_expander(data, 'Silver (USD/oz)', '#C0C0C0')

    col1, col2 = st.columns(2)

    # Crude Oil
    with col1:
        st.subheader(f"[Crude Oil (CL)]({SOURCE_URLS['crude_oil']})")
        data = aggregator.get_indicator('15_crude_oil')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("Crude Oil Price (USD/barrel)", format_value(price, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")
            _render_history_expander(data, 'Crude Oil (USD/bbl)', '#2c2c2c')

    # Copper
    with col2:
        st.subheader(f"[Copper (HG)]({SOURCE_URLS['copper']})")
        data = aggregator.get_indicator('16_copper')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("Copper Price (USD/lb)", format_value(price, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")
            _render_history_expander(data, 'Copper (USD/lb)', '#B87333')

    col1, col2 = st.columns(2)

    # Natural Gas
    with col1:
        st.subheader("[Natural Gas (NG)](https://finance.yahoo.com/quote/NG%3DF/)")
        data = aggregator.get_indicator('56_natural_gas')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            price = data.get('price', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("Natural Gas Price (USD/MMBtu)", format_value(price, 3), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")
            _render_history_expander(data, 'Natural Gas (USD/MMBtu)', '#4a148c')

    # Copper/Gold Ratio
    with col2:
        st.subheader("Copper/Gold Ratio (Economic Sentiment)")
        cu_au_data = aggregator.get_indicator('57_cu_au_ratio')
        if 'error' in cu_au_data:
            st.error(f"⚠️ {cu_au_data['error']}")
        else:
            ratio_val = cu_au_data.get('cu_au_ratio', 'N/A')
            ratio_chg = cu_au_data.get('change_1d', 0)
            st.metric("Cu/Au Ratio (×1000)", format_value(ratio_val, 4), f"{format_value(ratio_chg, 2)}%")
            st.caption(f"As of: {cu_au_data.get('latest_date', 'N/A')}")
            if 'interpretation' in cu_au_data:
                st.caption(f"ℹ️ {cu_au_data['interpretation']}")
            _render_history_expander(cu_au_data, 'Cu/Au Ratio ×1000', '#ef6c00')

    # CFTC COT Positioning
    st.header("CFTC Commitment of Traders — Gold & Silver")
    st.caption("Weekly positioning data from CFTC. Managed money = hedge funds. Commercial = producers/hedgers.")

    cot_data = aggregator.get_indicator('22_cot_positioning')
    if 'error' in cot_data:
        st.error(f"⚠️ {cot_data['error']}")
        if 'suggestion' in cot_data:
            st.info(cot_data['suggestion'])
    else:
        st.caption(f"As of: {cot_data.get('latest_date', 'N/A')}")

        col1, col2 = st.columns(2)

        # Gold COT
        with col1:
            st.subheader("Gold (GC) Positioning")
            gold_cot = cot_data.get('gold', {})
            if 'error' in gold_cot:
                st.error(f"⚠️ {gold_cot['error']}")
            else:
                st.metric("Open Interest", f"{gold_cot.get('open_interest', 'N/A'):,}" if isinstance(gold_cot.get('open_interest'), int) else "N/A")

                # Managed money or non-commercial
                if gold_cot.get('managed_money_net') is not None:
                    mm_net = gold_cot['managed_money_net']
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("Managed Money Net", f"{mm_net:,}")
                    with col_b:
                        ratio = gold_cot.get('mm_long_ratio')
                        if ratio is not None:
                            st.metric("MM Long Ratio", f"{ratio:.1%}")
                elif gold_cot.get('noncommercial_net') is not None:
                    nc_net = gold_cot['noncommercial_net']
                    st.metric("Speculator Net", f"{nc_net:,}")

                if gold_cot.get('commercial_net') is not None:
                    st.metric("Commercial Net", f"{gold_cot['commercial_net']:,}")

                if gold_cot.get('oi_change') is not None:
                    oi_chg = gold_cot['oi_change']
                    oi_pct = gold_cot.get('oi_change_pct')
                    delta_str = f"{oi_pct:+.1f}%" if oi_pct is not None else ""
                    st.metric("OI Change (1w)", f"{oi_chg:,}", delta_str)

        # Silver COT
        with col2:
            st.subheader("Silver (SI) Positioning")
            silver_cot = cot_data.get('silver', {})
            if 'error' in silver_cot:
                st.error(f"⚠️ {silver_cot['error']}")
            else:
                st.metric("Open Interest", f"{silver_cot.get('open_interest', 'N/A'):,}" if isinstance(silver_cot.get('open_interest'), int) else "N/A")

                if silver_cot.get('managed_money_net') is not None:
                    mm_net = silver_cot['managed_money_net']
                    col_a, col_b = st.columns(2)
                    with col_a:
                        st.metric("Managed Money Net", f"{mm_net:,}")
                    with col_b:
                        ratio = silver_cot.get('mm_long_ratio')
                        if ratio is not None:
                            st.metric("MM Long Ratio", f"{ratio:.1%}")
                elif silver_cot.get('noncommercial_net') is not None:
                    nc_net = silver_cot['noncommercial_net']
                    st.metric("Speculator Net", f"{nc_net:,}")

                if silver_cot.get('commercial_net') is not None:
                    st.metric("Commercial Net", f"{silver_cot['commercial_net']:,}")

                if silver_cot.get('oi_change') is not None:
                    oi_chg = silver_cot['oi_change']
                    oi_pct = silver_cot.get('oi_change_pct')
                    delta_str = f"{oi_pct:+.1f}%" if oi_pct is not None else ""
                    st.metric("OI Change (1w)", f"{oi_chg:,}", delta_str)

        # Historical chart: managed money net positioning
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        gold_hist = gold_cot.get('historical') if isinstance(gold_cot, dict) else None
        silver_hist = silver_cot.get('historical') if isinstance(silver_cot, dict) else None

        if gold_hist is not None or silver_hist is not None:
          with st.expander("📈 COT Positioning Chart"):
            hist_label = gold_cot.get('historical_label', 'Net Positioning') if isinstance(gold_cot, dict) else 'Net Positioning'
            fig = make_subplots(rows=1, cols=1)

            if gold_hist is not None and hasattr(gold_hist, 'index'):
                fig.add_trace(go.Scatter(
                    x=gold_hist.index, y=gold_hist.values,
                    name=f"Gold {hist_label}", line=dict(color='gold')
                ))
            if silver_hist is not None and hasattr(silver_hist, 'index'):
                fig.add_trace(go.Scatter(
                    x=silver_hist.index, y=silver_hist.values,
                    name=f"Silver {hist_label}", line=dict(color='silver')
                ))

            fig.update_layout(
                title=f"CFTC COT: {hist_label} (Gold vs Silver)",
                xaxis_title="Date",
                yaxis_title="Contracts",
                hovermode='x unified',
                height=450
            )
            st.plotly_chart(fig, use_container_width=True)

    # ── Hyperliquid Perpetual Futures ─────────────────────────────────────────
    st.subheader("Hyperliquid Perpetual Futures")
    st.caption("DeFi perpetual futures on Hyperliquid. 24/7 markets, no expiry. Funding rate annualized.")

    hl_perps = aggregator.get_indicator('84_hl_perps')
    if 'error' in hl_perps:
        st.error(f"⚠️ {hl_perps['error']}")
    else:
        hl_coins = [
            ('btc', 'Bitcoin (BTC)', '#F7931A'),
            ('eth', 'Ethereum (ETH)', '#627EEA'),
            ('sol', 'Solana (SOL)', '#9945FF'),
            ('hype', 'Hyperliquid (HYPE)', '#00D4AA'),
            ('paxg', 'PAX Gold (PAXG)', '#FFD700'),
            ('oil', 'WTI Crude Oil (OIL)', '#8B4513'),
            ('sp500', 'S&P 500 (SP500)', '#1565c0'),
            ('xyz100', 'Nasdaq 100 (XYZ100)', '#7b1fa2'),
            ('natgas', 'Natural Gas (NATGAS)', '#4a148c'),
            ('copper_hl', 'Copper (COPPER)', '#B87333'),
            ('brentoil', 'Brent Crude (BRENTOIL)', '#2c2c2c'),
        ]
        for coin_key, label, color in hl_coins:
            coin = hl_perps.get(coin_key, {})
            if not isinstance(coin, dict) or 'price' not in coin:
                continue
            st.markdown(f"**{label}**")
            c1, c2, c3, c4 = st.columns(4)
            price = coin['price']
            with c1:
                price_str = f"${price:,.2f}" if price >= 100 else f"${price:,.4f}"
                st.metric("Mid Price", price_str, f"{coin.get('change_1d', 0):+.2f}%")
            with c2:
                st.metric("Funding (ann.)", f"{coin.get('funding_rate', 0):.2f}%")
                st.caption(f"8h: {coin.get('funding_rate_8h', 0)}%")
            with c3:
                oi = coin.get('open_interest', 0)
                st.metric("Open Interest", f"${oi / 1e6:.1f}M" if oi else "N/A")
            with c4:
                vol = coin.get('volume_24h', 0)
                st.metric("24h Volume", f"${vol / 1e6:.1f}M" if vol else "N/A")
            # HL OHLCV candlestick chart
            _render_history_expander(coin, label, color)

# Tab 6: Large-cap Financials

def _fmt_dollar(v):
    """Format a dollar value with appropriate scale."""
    if v is None:
        return "—"
    try:
        v = float(v)
        if abs(v) >= 1e12:
            return f"${v / 1e12:.2f}T"
        if abs(v) >= 1e9:
            return f"${v / 1e9:.2f}B"
        if abs(v) >= 1e6:
            return f"${v / 1e6:.1f}M"
        if abs(v) >= 1e3:
            return f"${v / 1e3:.1f}K"
        return f"${v:,.2f}"
    except (ValueError, TypeError):
        return "—"

def _fmt_pct(v, plus=False):
    """Format a percentage value."""
    if v is None:
        return "N/A"
    try:
        v = float(v)
        return f"{v:+.1f}%" if plus else f"{v:.1f}%"
    except (ValueError, TypeError):
        return "N/A"

def _fmt_ratio(v, decimals=2):
    """Format a ratio value."""
    if v is None:
        return "N/A"
    try:
        return f"{float(v):.{decimals}f}"
    except (ValueError, TypeError):
        return "N/A"

def _metric_components(numerator_label, numerator_val, denominator_label, denominator_val, annualized=False):
    """Return small HTML showing numerator / denominator below a metric."""
    n_str = _fmt_dollar(numerator_val) if numerator_val is not None else "—"
    d_str = _fmt_dollar(denominator_val) if denominator_val is not None else "—"
    ann = " (ann.)" if annualized else ""
    return f'<span style="color:#888;font-size:0.75em">{numerator_label}{ann} / {denominator_label}<br/>{n_str} / {d_str}</span>'

def _val_components(label, numerator_val, denominator_label, denominator_val, n_fmt='$', d_fmt='$'):
    """Return small HTML for valuation metric components."""
    if n_fmt == '$':
        n_str = _fmt_dollar(numerator_val) if numerator_val is not None else "—"
    elif n_fmt == 'ratio':
        n_str = f"{numerator_val:.2f}" if numerator_val is not None else "—"
    else:
        n_str = f"{numerator_val}" if numerator_val is not None else "—"
    if d_fmt == '$':
        d_str = _fmt_dollar(denominator_val) if denominator_val is not None else "—"
    elif d_fmt == 'pct':
        d_str = f"{denominator_val:.1f}%" if denominator_val is not None else "—"
    elif d_fmt == 'eps':
        d_str = f"${denominator_val:.2f}" if denominator_val is not None else "—"
    else:
        d_str = f"{denominator_val}" if denominator_val is not None else "—"
    return f'<span style="color:#888;font-size:0.75em">{label} / {denominator_label}<br/>{n_str} / {d_str}</span>'

def _fmt_change(current, previous):
    """Format a percentage change as colored HTML span."""
    if current is None or previous is None or previous == 0:
        return ""
    try:
        pct = (float(current) - float(previous)) / abs(float(previous)) * 100
        color = "#2e7d32" if pct >= 0 else "#c62828"  # green / red
        sign = "+" if pct >= 0 else ""
        return f'<span style="color:{color};font-size:0.78em;margin-left:4px">{sign}{pct:.1f}%</span>'
    except (ValueError, TypeError, ZeroDivisionError):
        return ""

def _parse_quarter_key(q):
    """Parse '2025-Q1' into (year, quarter_num). Returns (None, None) on failure."""
    try:
        parts = q.split('-Q')
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None, None

def _build_quarterly_table_html(data_dict, metrics, quarters):
    """Build an HTML quarterly table with QoQ and YoY change indicators."""
    if not data_dict or not quarters:
        return None

    # Pre-parse quarter keys for YoY lookup
    q_parsed = [_parse_quarter_key(q) for q in quarters]

    def _fmt_cell(v, fmt):
        if v is None:
            return "—"
        try:
            if fmt == '$':
                return _fmt_dollar(v)
            elif fmt == '%':
                return f"{float(v) * 100:.1f}%"
            elif fmt == 'eps':
                return f"${float(v):.2f}"
            elif fmt == 'shares':
                return f"{float(v) / 1e9:.2f}B"
            else:
                return f"{float(v):,.2f}"
        except (ValueError, TypeError):
            return "—"

    # Build HTML table
    html = '<table style="width:100%;border-collapse:collapse;font-size:0.88em;font-family:monospace">'
    # Header
    html += '<tr style="border-bottom:2px solid #555">'
    html += '<th style="text-align:left;padding:6px 8px;min-width:160px">Metric</th>'
    for q in quarters:
        html += f'<th style="text-align:right;padding:6px 8px">{q}</th>'
    html += '</tr>'

    for row_idx, (label, key, fmt) in enumerate(metrics):
        vals = data_dict.get(key, [])
        bg = "#f8f9fa" if row_idx % 2 == 0 else "#ffffff"
        html += f'<tr style="background:{bg};border-bottom:1px solid #e0e0e0">'
        html += f'<td style="text-align:left;padding:5px 8px;white-space:nowrap">{label}</td>'
        for i, q in enumerate(quarters):
            v = vals[i] if i < len(vals) else None
            cell_text = _fmt_cell(v, fmt)

            # QoQ: compare to next column (quarters are newest-first, so i+1 is previous quarter)
            qoq_html = ""
            if i + 1 < len(quarters) and i + 1 < len(vals):
                prev_v = vals[i + 1] if (i + 1) < len(vals) else None
                qoq_html = _fmt_change(v, prev_v)

            # YoY: find same quarter number in previous year
            yoy_html = ""
            yr, qn = q_parsed[i]
            if yr and qn:
                for j in range(i + 1, len(quarters)):
                    yr_j, qn_j = q_parsed[j]
                    if yr_j and qn_j and qn_j == qn and yr_j == yr - 1:
                        prev_yoy = vals[j] if j < len(vals) else None
                        chg = _fmt_change(v, prev_yoy)
                        if chg:
                            yoy_html = chg.replace('margin-left:4px', 'margin-left:2px').replace('</span>', ' y/y</span>')
                        break

            # Combine: value + QoQ (q/q) + YoY (y/y)
            changes = ""
            if qoq_html:
                qoq_labeled = qoq_html.replace('</span>', ' q/q</span>')
                changes += qoq_labeled
            if yoy_html:
                changes += yoy_html

            html += f'<td style="text-align:right;padding:5px 8px;white-space:nowrap">{cell_text}{changes}</td>'
        html += '</tr>'

    html += '</table>'
    return html

def _build_quarterly_table(data_dict, metrics, quarters):
    """Build a quarterly data table from a dict of metric lists."""
    if not data_dict or not quarters:
        return None
    rows = []
    for label, key, fmt in metrics:
        vals = data_dict.get(key, [])
        row = {'Metric': label}
        for i, q in enumerate(quarters):
            v = vals[i] if i < len(vals) else None
            if fmt == '$':
                row[q] = _fmt_dollar(v)
            elif fmt == '%':
                row[q] = f"{v * 100:.1f}%" if v is not None else "—"
            elif fmt == 'eps':
                row[q] = f"${v:.2f}" if v is not None else "—"
            elif fmt == 'shares':
                row[q] = f"{v / 1e9:.2f}B" if v is not None else "—"
            else:
                row[q] = f"{v:,.2f}" if v is not None else "—"
        rows.append(row)
    if rows:
        return pd.DataFrame(rows).set_index('Metric')
    return None

def _fetch_source_data(source_name, ticker, eq_data, is_custom=False):
    """Fetch company data from the selected source.

    Args:
        source_name: 'Yahoo Finance', 'SEC EDGAR', 'Finnhub', or 'Simfin'
        ticker: Ticker symbol
        eq_data: The cached equity financials data (from aggregator)
        is_custom: If True, this is a non-Top-20 ticker that needs on-demand fetching
    """
    if source_name == "Yahoo Finance":
        if is_custom:
            # On-demand fetch for custom tickers
            cache_key = f'yahoo_custom_{ticker}'
            if cache_key not in st.session_state:
                with st.spinner(f"Fetching Yahoo Finance data for {ticker}..."):
                    from data_extractors.equity_financials_extractor import get_company_financials_yahoo
                    data = get_company_financials_yahoo(ticker)
                    st.session_state[cache_key] = data
                    # Auto-save to historical_data
                    if 'error' not in data:
                        try:
                            from extract_historical_data import save_single_company
                            save_single_company(ticker, data, 'Yahoo Finance')
                        except Exception:
                            pass
            return st.session_state[cache_key]
        else:
            companies = eq_data.get('companies', {})
            return companies.get(ticker)
    elif source_name == "SEC EDGAR":
        cache_key = f'sec_{ticker}'
        if cache_key not in st.session_state:
            with st.spinner(f"Fetching SEC data for {ticker}..."):
                from data_extractors.sec_extractor import get_company_financials_sec
                data = get_company_financials_sec(ticker)
                st.session_state[cache_key] = data
                # Auto-save to historical_data
                if 'error' not in data:
                    try:
                        from extract_historical_data import save_single_company
                        save_single_company(ticker, data, 'SEC EDGAR')
                    except Exception:
                        pass
        return st.session_state[cache_key]
    elif source_name == "Finnhub":
        cache_key = f'finnhub_{ticker}'
        if cache_key not in st.session_state:
            with st.spinner(f"Fetching Finnhub data for {ticker}..."):
                from data_extractors.equity_financials_extractor import get_company_financials_finnhub
                st.session_state[cache_key] = get_company_financials_finnhub(ticker)
        return st.session_state[cache_key]
    elif source_name == "Simfin":
        cache_key = f'simfin_{ticker}'
        if cache_key not in st.session_state:
            with st.spinner(f"Fetching Simfin data for {ticker}..."):
                from data_extractors.equity_financials_extractor import get_company_financials_simfin
                st.session_state[cache_key] = get_company_financials_simfin(ticker)
        return st.session_state[cache_key]
    return None

with tab6:
    st.header("Large-cap Financials")

    eq_data = aggregator.get_indicator('29_equity_financials')

    # Data source selector
    source_col, info_col = st.columns([3, 2])
    with source_col:
        data_source = st.radio(
            "Data Source",
            ["Yahoo Finance", "SEC EDGAR", "Finnhub", "Simfin"],
            horizontal=True,
            key="financials_source",
        )
    with info_col:
        if data_source == "SEC EDGAR":
            st.caption("SEC EDGAR XBRL — Financials from 10-K/10-Q filings. Price data & valuation supplemented by Yahoo Finance.")
        elif data_source == "Finnhub":
            st.caption("Requires FINNHUB_API_KEY env var. Free tier: 60 calls/min.")
        elif data_source == "Simfin":
            st.caption("Requires SIMFIN_API_KEY env var. Free tier: 2,000 calls/day.")
        else:
            st.caption("Yahoo Finance — Default. Full metrics including valuation.")

    if 'error' in eq_data:
        st.error(f"⚠️ {eq_data['error']}")
    else:
        companies = eq_data.get('companies', {})
        tickers = eq_data.get('tickers', [])

        if not companies:
            st.warning("No equity financial data available. Click 🔄 Refresh to fetch.")
        else:
            # Summary bar
            st.caption(
                f"Yahoo Finance cache: {eq_data.get('latest_date', 'N/A')} | "
                f"✅ {eq_data.get('successful', 0)} succeeded, "
                f"❌ {eq_data.get('failed', 0)} failed"
            )

            # Ticker selector — Top 20 dropdown + custom ticker input
            available = [t for t in tickers if t in companies and 'error' not in companies[t]]
            if not available:
                st.warning("No company data available.")
            else:
                sel_col, custom_col = st.columns([3, 2])
                with sel_col:
                    dropdown_selected = st.selectbox(
                        "Top 20 Companies",
                        available,
                        format_func=lambda t: f"{t} — {companies[t].get('company_name', t)}",
                    )
                with custom_col:
                    custom_ticker = st.text_input(
                        "Or type any ticker",
                        value="",
                        placeholder="e.g. CRM, NFLX, AMD",
                        key="custom_ticker_input",
                    ).strip().upper()

                # Priority: custom ticker > dropdown
                is_custom = False
                if custom_ticker:
                    selected = custom_ticker.replace('.', '-')
                    is_custom = selected not in set(available)
                    if is_custom:
                        st.info(f"Viewing **{selected}** (not in Top 20 — data fetched on demand)")
                else:
                    selected = dropdown_selected

                # Fetch data from selected source
                co = _fetch_source_data(data_source, selected, eq_data, is_custom=is_custom)

                if co is None or (isinstance(co, dict) and 'error' in co):
                    err_msg = co.get('error', 'Unknown error') if co else 'No data returned'
                    st.error(f"⚠️ {data_source}: {err_msg}")
                else:
                    # Company header
                    col_h1, col_h2, col_h3 = st.columns(3)
                    with col_h1:
                        mkt = co.get('market_cap')
                        st.metric("Market Cap", _fmt_dollar(mkt) if mkt else "N/A")
                    with col_h2:
                        st.metric("Sector", co.get('sector', 'N/A'))
                    with col_h3:
                        st.metric("Industry", co.get('industry', 'N/A'))

                    src_label = co.get('source', data_source)
                    quarters = co.get('quarters', [])

                    st.caption(f"Source: {src_label} | Quarters: {', '.join(quarters) if quarters else 'N/A'}")

                    # ── 1. Income Statement ───────────────────────
                    inc = co.get('income_statement')
                    _inc_metrics = [
                        ('Total Revenue', 'total_revenue', '$'),
                        ('Cost of Revenue', 'cost_of_revenue', '$'),
                        ('Gross Profit', 'gross_profit', '$'),
                        ('Operating Expenses', 'operating_expense', '$'),
                        ('&nbsp;&nbsp;R&D', 'research_development', '$'),
                        ('&nbsp;&nbsp;SG&A', 'selling_general_admin', '$'),
                        ('Operating Income', 'operating_income', '$'),
                        ('EBITDA', 'ebitda', '$'),
                        ('Pretax Income', 'pretax_income', '$'),
                        ('Net Income', 'net_income', '$'),
                        ('Diluted EPS', 'diluted_eps', 'eps'),
                        ('Basic EPS', 'basic_eps', 'eps'),
                    ]
                    if inc and quarters:
                        st.subheader("1. Income Statement (Quarterly)")
                        inc_html = _build_quarterly_table_html(inc, _inc_metrics, quarters)
                        if inc_html:
                            st.markdown(inc_html, unsafe_allow_html=True)


                    # ── 2. Balance Sheet ──────────────────────────
                    bs = co.get('balance_sheet')
                    if bs and quarters:
                        st.subheader("2. Balance Sheet (Quarterly)")

                        st.markdown("**Assets**")
                        _bs_assets = [
                            ('Total Assets', 'total_assets', '$'),
                            ('&nbsp;&nbsp;Current Assets', 'current_assets', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Cash & ST Investments', 'cash_and_short_term_investments', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Accounts Receivable', 'accounts_receivable', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Inventory', 'inventory', '$'),
                            ('&nbsp;&nbsp;Non-Current Assets', 'total_non_current_assets', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Goodwill', 'goodwill', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Net PP&E', 'net_ppe', '$'),
                        ]
                        assets_html = _build_quarterly_table_html(bs, _bs_assets, quarters)
                        if assets_html:
                            st.markdown(assets_html, unsafe_allow_html=True)

                        st.markdown("**Liabilities**")
                        _bs_liab = [
                            ('Total Liabilities', 'total_liabilities', '$'),
                            ('&nbsp;&nbsp;Current Liabilities', 'current_liabilities', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Current Debt', 'current_debt', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Accounts Payable', 'accounts_payable', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Accrued Expenses', 'accrued_expenses', '$'),
                            ('&nbsp;&nbsp;Non-Current Liabilities', 'non_current_liabilities', '$'),
                            ('&nbsp;&nbsp;&nbsp;&nbsp;Long-Term Debt', 'long_term_debt', '$'),
                            ('&nbsp;&nbsp;Total Debt', 'total_debt', '$'),
                            ('&nbsp;&nbsp;Net Debt', 'net_debt', '$'),
                        ]
                        liab_html = _build_quarterly_table_html(bs, _bs_liab, quarters)
                        if liab_html:
                            st.markdown(liab_html, unsafe_allow_html=True)

                        st.markdown("**Equity & Ratios**")
                        _bs_eq = [
                            ("Stockholders' Equity", 'stockholders_equity', '$'),
                            ('Retained Earnings', 'retained_earnings', '$'),
                            ('Invested Capital', 'invested_capital', '$'),
                            ('Debt Ratio (Liab/Assets)', 'debt_ratio', '%'),
                            ('Debt/Equity', 'debt_to_equity', '%'),
                            ('Current Ratio', 'current_ratio', '%'),
                        ]
                        eq_html = _build_quarterly_table_html(bs, _bs_eq, quarters)
                        if eq_html:
                            st.markdown(eq_html, unsafe_allow_html=True)


                    # ── 3. Cash Flow ──────────────────────────────
                    cf = co.get('cash_flow')
                    if cf and quarters:
                        st.subheader("3. Cash Flow (Quarterly)")
                        _cf_metrics = [
                            ('Operating Cash Flow', 'operating_cash_flow', '$'),
                            ('Capital Expenditures', 'capital_expenditure', '$'),
                            ('Free Cash Flow', 'free_cash_flow', '$'),
                            ('Share Repurchases', 'share_repurchases', '$'),
                            ('Dividends Paid', 'dividends_paid', '$'),
                            ('Investing Cash Flow', 'investing_cash_flow', '$'),
                            ('Financing Cash Flow', 'financing_cash_flow', '$'),
                            ('D&A', 'depreciation_amortization', '$'),
                            ('Stock-Based Compensation', 'stock_based_compensation', '$'),
                        ]
                        cf_html = _build_quarterly_table_html(cf, _cf_metrics, quarters)
                        if cf_html:
                            st.markdown(cf_html, unsafe_allow_html=True)


                    # ── 4. Financial Analysis ─────────────────────
                    fa = co.get('financial_analysis', {})
                    # Get raw values for numerator/denominator display (latest quarter = index 0)
                    _inc = co.get('income_statement', {})
                    _bs = co.get('balance_sheet', {})
                    _cf = co.get('cash_flow', {})
                    def _q0(d, key):
                        """Get first (latest quarter) value from a statement dict."""
                        vals = d.get(key, [])
                        return vals[0] if vals else None

                    st.subheader("4. Financial Analysis")

                    # Profitability
                    prof = fa.get('profitability', {})
                    st.markdown("**Profitability**")
                    _rev0 = _q0(_inc, 'total_revenue')
                    cp1, cp2, cp3, cp4, cp5 = st.columns(5)
                    with cp1:
                        st.metric("Gross Margin", _fmt_pct(prof.get('gross_margin')))
                        st.markdown(_metric_components("Gross Profit", _q0(_inc, 'gross_profit'), "Revenue", _rev0), unsafe_allow_html=True)
                    with cp2:
                        st.metric("Operating Margin", _fmt_pct(prof.get('operating_margin')))
                        st.markdown(_metric_components("Op. Income", _q0(_inc, 'operating_income'), "Revenue", _rev0), unsafe_allow_html=True)
                    with cp3:
                        st.metric("EBITDA Margin", _fmt_pct(prof.get('ebitda_margin')))
                        st.markdown(_metric_components("EBITDA", _q0(_inc, 'ebitda'), "Revenue", _rev0), unsafe_allow_html=True)
                    with cp4:
                        st.metric("FCF Margin", _fmt_pct(prof.get('fcf_margin')))
                        st.markdown(_metric_components("FCF", _q0(_cf, 'free_cash_flow'), "Revenue", _rev0), unsafe_allow_html=True)
                    with cp5:
                        st.metric("Net Profit Margin", _fmt_pct(prof.get('net_margin')))
                        st.markdown(_metric_components("Net Income", _q0(_inc, 'net_income'), "Revenue", _rev0), unsafe_allow_html=True)

                    # Turnover / Leverage
                    turnover = fa.get('turnover', {})
                    st.markdown("**Turnover & Leverage**")
                    ct1, ct2, ct3 = st.columns(3)
                    with ct1:
                        v = turnover.get('debt_to_equity')
                        st.metric("Debt/Equity", _fmt_ratio(v) if v is not None else "N/A")
                        st.markdown(_metric_components("Total Debt", _q0(_bs, 'total_debt'), "Equity", _q0(_bs, 'stockholders_equity')), unsafe_allow_html=True)
                    with ct2:
                        v = turnover.get('current_ratio')
                        st.metric("Current Ratio", _fmt_ratio(v) if v is not None else "N/A")
                        st.markdown(_metric_components("Curr. Assets", _q0(_bs, 'current_assets'), "Curr. Liab.", _q0(_bs, 'current_liabilities')), unsafe_allow_html=True)
                    with ct3:
                        v = turnover.get('asset_turnover')
                        st.metric("Asset Turnover", _fmt_ratio(v, 4) if v is not None else "N/A")
                        st.markdown(_metric_components("Revenue", _rev0, "Total Assets", _q0(_bs, 'total_assets'), annualized=True), unsafe_allow_html=True)

                    # Growth
                    gr = fa.get('growth', {})
                    st.markdown("**Growth**")
                    cg1, cg2, cg3, cg4 = st.columns(4)
                    with cg1:
                        st.metric("EPS Growth", _fmt_pct(gr.get('eps_growth'), plus=True))
                    with cg2:
                        st.metric("Revenue Growth", _fmt_pct(gr.get('revenue_growth'), plus=True))
                    with cg3:
                        st.metric("Revenue QoQ", _fmt_pct(gr.get('revenue_qoq'), plus=True))
                    with cg4:
                        st.metric("Earnings QoQ", _fmt_pct(gr.get('earnings_quarterly_growth'), plus=True))

                    # Returns
                    returns = fa.get('returns', {})
                    _ni0 = _q0(_inc, 'net_income')
                    st.markdown("**Returns**")
                    cr1, cr2, cr3 = st.columns(3)
                    with cr1:
                        st.metric("ROE", _fmt_pct(returns.get('roe')))
                        st.markdown(_metric_components("Net Income", _ni0, "Equity", _q0(_bs, 'stockholders_equity'), annualized=True), unsafe_allow_html=True)
                    with cr2:
                        st.metric("ROA", _fmt_pct(returns.get('roa')))
                        st.markdown(_metric_components("Net Income", _ni0, "Total Assets", _q0(_bs, 'total_assets'), annualized=True), unsafe_allow_html=True)
                    with cr3:
                        st.metric("ROIC", _fmt_pct(returns.get('roic')))
                        # NOPAT = Op. Income * (1 - tax_rate), approximated
                        _oi0 = _q0(_inc, 'operating_income')
                        _tp0 = _q0(_inc, 'tax_provision')
                        _pt0 = _q0(_inc, 'pretax_income')
                        _nopat = None
                        if _oi0:
                            _tr = 0.21
                            if _tp0 and _pt0 and _pt0 != 0:
                                _tr = max(0, min(1, _tp0 / _pt0))
                            _nopat = _oi0 * (1 - _tr)
                        st.markdown(_metric_components("NOPAT", _nopat, "Invested Cap.", _q0(_bs, 'invested_capital'), annualized=True), unsafe_allow_html=True)


                    # ── 5. Valuation ──────────────────────────────
                    val = co.get('valuation', {})
                    st.subheader("5. Valuation")

                    price_src = val.get('_price_source')
                    if price_src and data_source != "Yahoo Finance":
                        st.caption(f"Price data from **{price_src}** | {val.get('_note', '')}")
                    elif val.get('_note'):
                        st.info(val['_note'])

                    _price = val.get('current_price') or val.get('price')
                    _ev = val.get('enterprise_value')
                    _ttm_eps = val.get('diluted_eps_ttm')
                    _bvps = val.get('book_value_per_share')
                    _mktcap = co.get('market_cap') or val.get('market_cap')

                    vr1, vr2, vr3, vr4 = st.columns(4)
                    with vr1:
                        st.metric("Forward P/E", _fmt_ratio(val.get('forward_pe')))
                        fwd_eps = val.get('forward_eps')
                        if fwd_eps:
                            st.markdown(_val_components("Price", val.get('current_price'), "Fwd EPS", fwd_eps, d_fmt='eps'), unsafe_allow_html=True)
                    with vr2:
                        st.metric("Trailing P/E (12M)", _fmt_ratio(val.get('trailing_pe')))
                        st.markdown(_val_components("Price", val.get('current_price'), "TTM EPS", _ttm_eps, d_fmt='eps'), unsafe_allow_html=True)
                    with vr3:
                        st.metric("PEG Ratio", _fmt_ratio(val.get('peg_ratio')))
                        _eg = fa.get('growth', {}).get('eps_growth')
                        st.markdown(_val_components("P/E", val.get('trailing_pe'), "EPS Growth", _eg, n_fmt='ratio', d_fmt='pct'), unsafe_allow_html=True)
                    with vr4:
                        st.metric("Price / Book", _fmt_ratio(val.get('price_to_book')))
                        st.markdown(_val_components("Price", val.get('current_price'), "Book/Share", _bvps, d_fmt='eps'), unsafe_allow_html=True)

                    vr5, vr6, vr7, vr8 = st.columns(4)
                    with vr5:
                        st.metric("Price / Sales", _fmt_ratio(val.get('price_to_sales')))
                        st.markdown(_val_components("Mkt Cap", _mktcap, "TTM Revenue", val.get('ttm_revenue')), unsafe_allow_html=True)
                    with vr6:
                        st.metric("EV / EBITDA", _fmt_ratio(val.get('ev_to_ebitda')))
                        st.markdown(_val_components("EV", _ev, "TTM EBITDA", val.get('ttm_ebitda')), unsafe_allow_html=True)
                    with vr7:
                        st.metric("EV / FCF", _fmt_ratio(val.get('ev_to_fcf')))
                        st.markdown(_val_components("EV", _ev, "TTM FCF", val.get('ttm_fcf')), unsafe_allow_html=True)
                    with vr8:
                        st.metric("Enterprise Value", _fmt_dollar(_ev))
                        # EV = Market Cap + Total Debt - Cash
                        _td = _q0(_bs, 'total_debt')
                        _cash = _q0(_bs, 'cash_and_short_term_investments')
                        st.markdown(f'<span style="color:#888;font-size:0.75em">Mkt Cap + Debt − Cash<br/>{_fmt_dollar(_mktcap)} + {_fmt_dollar(_td)} − {_fmt_dollar(_cash)}</span>', unsafe_allow_html=True)

                    # Extra valuation info
                    ve1, ve2, ve3, ve4 = st.columns(4)
                    with ve1:
                        st.metric("Beta", _fmt_ratio(val.get('beta')))
                    with ve2:
                        st.metric("Dividend Yield", _fmt_pct(val.get('dividend_yield')))
                    with ve3:
                        st.metric("TTM EPS", f"${val['diluted_eps_ttm']:.2f}" if val.get('diluted_eps_ttm') else "N/A")
                    with ve4:
                        st.metric("Book Value/Share", f"${val['book_value_per_share']:.2f}" if val.get('book_value_per_share') else "N/A")


                    # ── 6. Revenue Segments ───────────────────────
                    st.subheader("6. Revenue Segment Breakdown")
                    segments = co.get('revenue_segments')
                    if segments and isinstance(segments, dict):
                        # Check for structured segments (product, business, geographic)
                        has_structured = any(k in segments for k in ('product_segments', 'business_segments', 'geographic_segments'))
                        if has_structured:
                            seg_period = segments.get('_period', '')
                            seg_source = segments.get('_source', '')
                            if seg_period or seg_source:
                                st.caption(f"Period ending: {seg_period} | Source: {seg_source}")

                            seg_tabs = []
                            seg_labels = []
                            if 'product_segments' in segments:
                                seg_labels.append("Product / Service")
                                seg_tabs.append('product_segments')
                            if 'business_segments' in segments:
                                seg_labels.append("Business Segments")
                                seg_tabs.append('business_segments')
                            if 'geographic_segments' in segments:
                                seg_labels.append("Geographic")
                                seg_tabs.append('geographic_segments')

                            if seg_labels:
                                stabs = st.tabs(seg_labels)
                                for stab, skey in zip(stabs, seg_tabs):
                                    with stab:
                                        seg_data = segments[skey]
                                        seg_df = pd.DataFrame([
                                            {'Segment': k, 'Revenue': _fmt_dollar(v),
                                             'Revenue ($)': v}
                                            for k, v in seg_data.items()
                                        ])
                                        seg_df = seg_df.sort_values('Revenue ($)', ascending=False)
                                        st.dataframe(
                                            seg_df[['Segment', 'Revenue']].set_index('Segment'),
                                            use_container_width=True,
                                        )
                        else:
                            # Flat dict format (Yahoo Finance)
                            seg_df = pd.DataFrame([
                                {'Segment': k, 'Revenue': _fmt_dollar(v)}
                                for k, v in segments.items() if not k.startswith('_')
                            ])
                            if not seg_df.empty:
                                st.dataframe(seg_df.set_index('Segment'), use_container_width=True)
                    else:
                        note = co.get('revenue_segments_note', 'Revenue segment data not available from this source.')
                        st.caption(note)

# Tab 7: Rates & Credit
with tab7:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    st.header("Rates & Credit")

    # ── Section 1: Yield Curve & Regime ──────────────────────────────────
    st.subheader("Yield Curve & Regime")

    yc_data = aggregator.get_indicator('33_yield_curve')

    if 'error' in yc_data:
        st.error(f"⚠️ Yield Curve: {yc_data['error']}")
    else:
        col1, col2 = st.columns([1, 2])

        with col1:
            spread_val = yc_data.get('spread_2s10s', 0)
            change = yc_data.get('change_1d', 0)
            inverted = yc_data.get('is_inverted', False)
            st.metric(
                "2s10s Spread",
                f"{format_value(spread_val, 2)}%",
                f"{format_value(change, 4)}",
            )
            if inverted:
                st.markdown("🔴 **Yield curve is INVERTED** (recession signal)")
            st.caption(f"As of: {yc_data.get('latest_date', 'N/A')}")
            _render_history_expander(yc_data, '2s10s Spread (%)', '#ff7f0e', value_suffix='%')

        with col2:
            regime = yc_data.get('regime', 'Neutral')
            emoji = yc_data.get('regime_emoji', '⚪')
            color = yc_data.get('regime_color', '#9e9e9e')
            signal = yc_data.get('regime_signal', '')
            detail = yc_data.get('regime_detail', '')
            lookback = yc_data.get('lookback_days', 20)

            st.markdown(
                f"<div style='background-color: {color}22; border-left: 4px solid {color}; "
                f"padding: 12px 16px; border-radius: 4px; margin-bottom: 12px;'>"
                f"<span style='font-size: 1.6em;'>{emoji}</span> "
                f"<strong style='font-size: 1.3em;'>{regime}</strong>"
                f"<br><span style='color: {color}; font-weight: 600;'>{signal}</span>"
                f"<br><span style='font-size: 0.9em; color: #555;'>{detail}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            d2y = yc_data.get('delta_2y', 0)
            d10y = yc_data.get('delta_10y', 0)
            ds = yc_data.get('delta_spread', 0)
            st.caption(
                f"**{lookback}-day changes:** "
                f"2Y: {'+' if d2y >= 0 else ''}{d2y:.2f}% | "
                f"10Y: {'+' if d10y >= 0 else ''}{d10y:.2f}% | "
                f"Spread: {'+' if ds >= 0 else ''}{ds:.2f}%"
            )

        # 2s10s Spread historical chart with inverted shading
        hist_spread = yc_data.get('historical')
        if hist_spread is not None and len(hist_spread) > 0:
          with st.expander("📈 2s10s Spread History"):
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist_spread.index, y=hist_spread.values,
                name='2s10s Spread', line=dict(color='#ff7f0e', width=1.5),
                fill='tozeroy', fillcolor='rgba(255,127,14,0.08)',
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="red", opacity=0.6,
                          annotation_text="Inversion threshold")
            fig.update_layout(
                title="US Treasury 2s10s Yield Spread (10Y − 2Y)",
                xaxis_title="Date", yaxis_title="Spread (%)",
                hovermode='x unified', height=400,
            )
            st.plotly_chart(fig, use_container_width=True)


    # ── Section 2: Global 10Y Sovereign Yields ──────────────────────────
    st.subheader("Global 10-Year Sovereign Yields")

    col1, col2, col3, col4, col5 = st.columns(5)

    # US 10Y (reuse existing indicator)
    with col1:
        us10y_data = aggregator.get_indicator('11_10y_yield')
        if 'error' in us10y_data:
            st.error("⚠️ US 10Y unavailable")
        else:
            us10y_val = us10y_data.get('10y_yield', us10y_data.get('value', 'N/A'))
            st.metric("🇺🇸 US 10Y", f"{format_value(us10y_val, 2)}%")
            st.caption(f"As of: {us10y_data.get('latest_date', 'N/A')}")
            _render_history_expander(us10y_data, 'US 10Y Yield (%)', '#1565c0', value_suffix='%')

    # US 5Y
    with col2:
        us5y_data = aggregator.get_indicator('61_5y_yield')
        if 'error' in us5y_data:
            st.error("⚠️ US 5Y unavailable")
        else:
            us5y_val = us5y_data.get('5y_yield', 'N/A')
            us5y_chg = us5y_data.get('change_1d', 0)
            st.metric("🇺🇸 US 5Y", f"{format_value(us5y_val, 2)}%", f"{format_value(us5y_chg, 3)}")
            st.caption(f"As of: {us5y_data.get('latest_date', 'N/A')}")
            _render_history_expander(us5y_data, 'US 5Y Yield (%)', '#0d47a1', value_suffix='%')

    # Germany 10Y
    with col3:
        de_data = aggregator.get_indicator('30_germany_10y')
        if 'error' in de_data:
            st.error(f"⚠️ {de_data['error']}")
        else:
            de_val = de_data.get('germany_10y_yield', 'N/A')
            de_chg = de_data.get('change_1d', 0)
            st.metric("🇩🇪 Germany 10Y", f"{format_value(de_val, 2)}%", f"{format_value(de_chg, 3)}")
            _render_history_expander(de_data, 'Germany 10Y (%)', '#d32f2f', value_suffix='%')

    # UK 10Y
    with col4:
        uk_data = aggregator.get_indicator('31_uk_10y')
        if 'error' in uk_data:
            st.error(f"⚠️ {uk_data['error']}")
        else:
            uk_val = uk_data.get('uk_10y_yield', 'N/A')
            uk_chg = uk_data.get('change_1d', 0)
            st.metric("🇬🇧 UK 10Y", f"{format_value(uk_val, 2)}%", f"{format_value(uk_chg, 3)}")
            _render_history_expander(uk_data, 'UK 10Y (%)', '#1b5e20', value_suffix='%')

    # China 10Y
    with col5:
        cn_data = aggregator.get_indicator('32_china_10y')
        if 'error' in cn_data:
            st.error(f"⚠️ {cn_data['error']}")
        else:
            cn_val = cn_data.get('china_10y_yield', 'N/A')
            cn_chg = cn_data.get('change_1d', 0)
            st.metric("🇨🇳 China 10Y", f"{format_value(cn_val, 2)}%", f"{format_value(cn_chg, 3)}")
            if 'note' in cn_data:
                st.caption(f"ℹ️ {cn_data['note']}")

    # Overlaid global 10Y yields chart
    if 'error' not in yc_data and 'historical_10y' in yc_data:
      with st.expander("📈 Global 10Y Yields Chart"):
        fig = go.Figure()
        h10y = yc_data['historical_10y']
        fig.add_trace(go.Scatter(
            x=h10y.index, y=h10y.values,
            name='US 10Y', line=dict(color='#1565c0', width=2),
        ))
        if 'error' not in de_data and 'historical' in de_data:
            de_h = de_data['historical']
            fig.add_trace(go.Scatter(
                x=de_h.index, y=de_h.values,
                name='Germany 10Y', line=dict(color='#d32f2f', width=1.5, dash='dash'),
            ))
        if 'error' not in uk_data and 'historical' in uk_data:
            uk_h = uk_data['historical']
            fig.add_trace(go.Scatter(
                x=uk_h.index, y=uk_h.values,
                name='UK 10Y', line=dict(color='#1b5e20', width=1.5, dash='dot'),
            ))
        fig.update_layout(
            title="Global 10-Year Sovereign Yields",
            xaxis_title="Date", yaxis_title="Yield (%)",
            hovermode='x unified', height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)


    # ── Section 3: Real Yields & Inflation Expectations ─────────────────
    st.subheader("Real Yields & Inflation Expectations")

    col1, col2, col3 = st.columns(3)

    # 10Y Real Yield (TIPS)
    with col1:
        ry_data = aggregator.get_indicator('36_real_yield')
        if 'error' in ry_data:
            st.error(f"⚠️ {ry_data['error']}")
        else:
            ry_val = ry_data.get('real_yield_10y', 'N/A')
            ry_chg = ry_data.get('change_1d', 0)
            st.metric("10Y Real Yield (TIPS)", f"{format_value(ry_val, 2)}%", f"{format_value(ry_chg, 4)}")
            st.caption(f"As of: {ry_data.get('latest_date', 'N/A')}")
            if 'interpretation' in ry_data:
                st.caption(f"ℹ️ {ry_data['interpretation']}")
            _render_history_expander(ry_data, 'Real Yield (%)', '#6a1b9a', value_suffix='%')

    # 5Y Breakeven
    be_data = aggregator.get_indicator('35_breakeven_inflation')
    with col2:
        if 'error' in be_data:
            st.error(f"⚠️ {be_data['error']}")
        else:
            be5 = be_data.get('breakeven_5y', 'N/A')
            be5_chg = be_data.get('change_5y_1d', 0)
            st.metric("5Y Breakeven Inflation", f"{format_value(be5, 2)}%", f"{format_value(be5_chg, 4)}")
            st.caption(f"As of: {be_data.get('latest_date', 'N/A')}")
            if 'historical_5y' in be_data:
                _render_history_expander(be_data, '5Y Breakeven (%)', '#e65100',
                                         hist_key='historical_5y', value_suffix='%')

    # 10Y Breakeven
    with col3:
        if 'error' not in be_data:
            be10 = be_data.get('breakeven_10y', 'N/A')
            be10_chg = be_data.get('change_10y_1d', 0)
            st.metric("10Y Breakeven Inflation", f"{format_value(be10, 2)}%", f"{format_value(be10_chg, 4)}")
            st.caption(f"As of: {be_data.get('latest_date', 'N/A')}")
            if 'interpretation' in be_data:
                st.caption(f"ℹ️ {be_data['interpretation']}")
            if 'historical_10y' in be_data:
                _render_history_expander(be_data, '10Y Breakeven (%)', '#bf360c',
                                         hist_key='historical_10y', value_suffix='%')

    # Nominal vs Real vs Breakeven chart
    if ('error' not in yc_data and 'historical_10y' in yc_data
            and 'error' not in ry_data and 'historical' in ry_data):
        with st.expander("📈 Nominal vs Real vs Breakeven Chart"):
            fig = go.Figure()
            # Nominal 10Y
            h10 = yc_data['historical_10y']
            fig.add_trace(go.Scatter(
                x=h10.index, y=h10.values,
                name='Nominal 10Y', line=dict(color='#1565c0', width=2),
            ))
            # Real 10Y
            hr = ry_data['historical']
            fig.add_trace(go.Scatter(
                x=hr.index, y=hr.values,
                name='Real 10Y (TIPS)', line=dict(color='#6a1b9a', width=2),
            ))
            # 10Y Breakeven
            if 'error' not in be_data and 'historical_10y' in be_data:
                hbe = be_data['historical_10y']
                fig.add_trace(go.Scatter(
                    x=hbe.index, y=hbe.values,
                    name='10Y Breakeven', line=dict(color='#e65100', width=1.5, dash='dash'),
                ))
            fig.add_hline(y=2.0, line_dash="dot", line_color="gray", opacity=0.4,
                          annotation_text="Fed 2% target")
            fig.update_layout(
                title="Nominal 10Y vs Real 10Y vs 10Y Breakeven Inflation",
                xaxis_title="Date", yaxis_title="Yield / Rate (%)",
                hovermode='x unified', height=420,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            st.plotly_chart(fig, use_container_width=True)


    # ── Section 4: Credit & Financial Conditions ────────────────────────
    st.subheader("Credit & Financial Conditions")

    col1, col2, col3, col4 = st.columns(4)

    # HY OAS
    with col1:
        hy_data = aggregator.get_indicator('34_hy_oas')
        if 'error' in hy_data:
            st.error(f"⚠️ {hy_data['error']}")
        else:
            hy_val = hy_data.get('hy_oas', 'N/A')
            hy_chg = hy_data.get('change_1d', 0)
            st.metric("HY Credit Spread (OAS)", f"{format_value(hy_val, 2)}%", f"{format_value(hy_chg, 2)}")
            st.caption(f"As of: {hy_data.get('latest_date', 'N/A')}")
            if 'interpretation' in hy_data:
                st.caption(f"ℹ️ {hy_data['interpretation']}")
            _render_history_expander(hy_data, 'HY OAS (%)', '#c62828', value_suffix='%')

    # NFCI
    with col2:
        nfci_data = aggregator.get_indicator('37_nfci')
        if 'error' in nfci_data:
            st.error(f"⚠️ {nfci_data['error']}")
        else:
            nfci_val = nfci_data.get('nfci', 'N/A')
            nfci_chg = nfci_data.get('change_1w', 0)
            st.metric("NFCI", format_value(nfci_val, 4), f"{format_value(nfci_chg, 4)} WoW")
            st.caption(f"As of: {nfci_data.get('latest_date', 'N/A')}")
            if 'interpretation' in nfci_data:
                st.caption(f"ℹ️ {nfci_data['interpretation']}")
            _render_history_expander(nfci_data, 'NFCI', '#4527a0')

    # Fed Funds Rate
    with col3:
        ff_data = aggregator.get_indicator('38_fed_funds')
        if 'error' in ff_data:
            st.error(f"⚠️ {ff_data['error']}")
        else:
            ff_val = ff_data.get('fed_funds_rate', 'N/A')
            ff_chg = ff_data.get('change_1d', 0)
            st.metric("Fed Funds Rate", f"{format_value(ff_val, 2)}%", f"{format_value(ff_chg, 4)}")
            st.caption(f"As of: {ff_data.get('latest_date', 'N/A')}")
            _render_history_expander(ff_data, 'Fed Funds Rate (%)', '#00695c', value_suffix='%')

    # IG Credit Spread
    with col4:
        ig_data = aggregator.get_indicator('45_ig_oas')
        if 'error' in ig_data:
            st.error(f"⚠️ {ig_data['error']}")
        else:
            ig_val = ig_data.get('ig_oas', 'N/A')
            ig_chg = ig_data.get('change_1d', 0)
            st.metric("IG Credit Spread (OAS)", f"{format_value(ig_val, 2)}%", f"{format_value(ig_chg, 2)}")
            st.caption(f"As of: {ig_data.get('latest_date', 'N/A')}")
            if 'interpretation' in ig_data:
                st.caption(f"ℹ️ {ig_data['interpretation']}")
            _render_history_expander(ig_data, 'IG OAS (%)', '#4e342e', value_suffix='%')

    # Bank Reserves + SLOOS row
    col1, col2 = st.columns(2)

    with col1:
        reserves_data = aggregator.get_indicator('58_bank_reserves')
        if 'error' in reserves_data:
            st.error(f"⚠️ Bank Reserves: {reserves_data['error']}")
        else:
            res_val = reserves_data.get('reserves_trillions', 'N/A')
            res_chg = reserves_data.get('change_wow_pct', 0)
            st.metric("Bank Reserves ($T)", format_value(res_val, 3), f"{format_value(res_chg, 1)}% WoW")
            st.caption(f"As of: {reserves_data.get('latest_date', 'N/A')}")
            if 'interpretation' in reserves_data:
                st.caption(f"ℹ️ {reserves_data['interpretation']}")
            _render_history_expander(reserves_data, 'Bank Reserves ($T)', '#1a237e')

    with col2:
        sloos_data = aggregator.get_indicator('62_sloos')
        if 'error' in sloos_data:
            st.caption(f"SLOOS: {sloos_data.get('error', 'Data unavailable')} (quarterly, may be delayed)")
        else:
            sloos_val = sloos_data.get('sloos_tightening', 'N/A')
            sloos_chg = sloos_data.get('change_qoq', 0)
            st.metric("SLOOS Lending Standards", f"{format_value(sloos_val, 1)}%", f"{format_value(sloos_chg, 1)} QoQ")
            st.caption(f"As of: {sloos_data.get('latest_date', 'N/A')}")
            if 'interpretation' in sloos_data:
                st.caption(f"ℹ️ {sloos_data['interpretation']}")
            _render_history_expander(sloos_data, 'SLOOS Net Tightening (%)', '#3e2723', value_suffix='%')


    # ── Section 5: Labor Market & Inflation ─────────────────────────────
    st.subheader("Labor Market & Inflation")

    col1, col2, col3, col4 = st.columns(4)

    # Unemployment Rate
    with col1:
        unemp_data = aggregator.get_indicator('40_unemployment')
        if 'error' in unemp_data:
            st.error(f"⚠️ {unemp_data['error']}")
        else:
            unemp_val = unemp_data.get('unemployment_rate', 'N/A')
            unemp_chg = unemp_data.get('change_mom', 0)
            st.metric("Unemployment Rate", f"{format_value(unemp_val, 1)}%", f"{format_value(unemp_chg, 1)} MoM")
            st.caption(f"As of: {unemp_data.get('latest_date', 'N/A')}")
            _render_history_expander(unemp_data, 'Unemployment (%)', '#283593', value_suffix='%')

    # Initial Jobless Claims
    with col2:
        claims_data = aggregator.get_indicator('39_initial_claims')
        if 'error' in claims_data:
            st.error(f"⚠️ {claims_data['error']}")
        else:
            claims_k = claims_data.get('initial_claims_k', 'N/A')
            claims_chg = claims_data.get('change_wow_pct', 0)
            st.metric("Initial Claims (K)", format_value(claims_k, 1), f"{format_value(claims_chg, 1)}% WoW")
            st.caption(f"As of: {claims_data.get('latest_date', 'N/A')}")
            if 'interpretation' in claims_data:
                st.caption(f"ℹ️ {claims_data['interpretation']}")
            _render_history_expander(claims_data, 'Initial Claims', '#37474f')

    # Core CPI YoY%
    infl_data = aggregator.get_indicator('41_core_inflation')
    with col3:
        if 'error' in infl_data:
            st.error(f"⚠️ {infl_data['error']}")
        else:
            cpi_yoy = infl_data.get('core_cpi_yoy', 'N/A')
            cpi_chg = infl_data.get('core_cpi_change_mom', 0)
            st.metric("Core CPI YoY%", f"{format_value(cpi_yoy, 2)}%", f"{format_value(cpi_chg, 2)} MoM")
            st.caption(f"As of: {infl_data.get('latest_date', 'N/A')}")
            if 'historical_core_cpi' in infl_data:
                _render_history_expander(infl_data, 'Core CPI YoY (%)', '#e65100',
                                         hist_key='historical_core_cpi', value_suffix='%')

    # Core PCE YoY%
    with col4:
        if 'error' not in infl_data:
            pce_yoy = infl_data.get('core_pce_yoy', 'N/A')
            pce_chg = infl_data.get('core_pce_change_mom', 0)
            st.metric("Core PCE YoY%", f"{format_value(pce_yoy, 2)}%", f"{format_value(pce_chg, 2)} MoM")
            if 'interpretation' in infl_data:
                st.caption(f"ℹ️ {infl_data['interpretation']}")
            if 'historical_core_pce' in infl_data:
                _render_history_expander(infl_data, 'Core PCE YoY (%)', '#bf360c',
                                         hist_key='historical_core_pce', value_suffix='%')

    # Extra row: Continuing Claims, Headline CPI, PPI
    col1, col2, col3 = st.columns(3)

    # Continuing Claims
    with col1:
        cc_data = aggregator.get_indicator('49_continuing_claims')
        if 'error' in cc_data:
            st.error(f"⚠️ {cc_data['error']}")
        else:
            cc_val = cc_data.get('continuing_claims_k', 'N/A')
            cc_chg = cc_data.get('change_wow_pct', 0)
            st.metric("Continuing Claims (K)", format_value(cc_val, 1), f"{format_value(cc_chg, 1)}% WoW")
            st.caption(f"As of: {cc_data.get('latest_date', 'N/A')}")
            if 'interpretation' in cc_data:
                st.caption(f"ℹ️ {cc_data['interpretation']}")
            _render_history_expander(cc_data, 'Continuing Claims (K)', '#455a64')

    # Headline CPI YoY%
    with col2:
        hcpi_data = aggregator.get_indicator('53_headline_cpi')
        if 'error' in hcpi_data:
            st.error(f"⚠️ {hcpi_data['error']}")
        else:
            hcpi_val = hcpi_data.get('headline_cpi_yoy', 'N/A')
            hcpi_chg = hcpi_data.get('change_mom', 0)
            st.metric("Headline CPI YoY%", f"{format_value(hcpi_val, 2)}%", f"{format_value(hcpi_chg, 2)} MoM")
            st.caption(f"As of: {hcpi_data.get('latest_date', 'N/A')}")
            _render_history_expander(hcpi_data, 'Headline CPI YoY (%)', '#ff6f00', value_suffix='%')

    # PPI YoY%
    with col3:
        ppi_data = aggregator.get_indicator('52_ppi')
        if 'error' in ppi_data:
            st.error(f"⚠️ {ppi_data['error']}")
        else:
            ppi_val = ppi_data.get('ppi_yoy', 'N/A')
            ppi_chg = ppi_data.get('change_mom', 0)
            st.metric("PPI YoY%", f"{format_value(ppi_val, 2)}%", f"{format_value(ppi_chg, 2)} MoM")
            st.caption(f"As of: {ppi_data.get('latest_date', 'N/A')}")
            if 'interpretation' in ppi_data:
                st.caption(f"ℹ️ {ppi_data['interpretation']}")
            _render_history_expander(ppi_data, 'PPI YoY (%)', '#ad1457', value_suffix='%')

    # ── OpenBB Rates & Credit Indicators ────────────────────────────────
    st.subheader("66. ECB Policy Rates")
    ecb_data = aggregator.get_indicator('66_ecb_rates')
    if 'error' in ecb_data:
        st.error(f"⚠️ {ecb_data['error']}")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Deposit Rate", f"{format_value(ecb_data.get('deposit_rate'))}%")
        with c2:
            st.metric("Refi Rate", f"{format_value(ecb_data.get('refi_rate'))}%")
        with c3:
            st.metric("Marginal Rate", f"{format_value(ecb_data.get('marginal_rate'))}%")
        st.caption(f"As of: {ecb_data.get('latest_date', 'N/A')} | Source: {ecb_data.get('source', 'N/A')}")
        _render_history_expander(ecb_data, 'ECB Deposit Rate', '#1565c0')

    st.subheader("68. CPI Components Breakdown")
    cpic_data = aggregator.get_indicator('68_cpi_components')
    if 'error' in cpic_data:
        st.error(f"⚠️ {cpic_data['error']}")
    else:
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Headline CPI YoY%", f"{format_value(cpic_data.get('headline_cpi_yoy'))}%")
        with c2:
            st.metric("Core CPI YoY%", f"{format_value(cpic_data.get('core_cpi_yoy'))}%")
        with c3:
            st.metric("Food CPI YoY%", f"{format_value(cpic_data.get('food_cpi_yoy'))}%")
        with c4:
            st.metric("Energy CPI YoY%", f"{format_value(cpic_data.get('energy_cpi_yoy'))}%")
        with c5:
            st.metric("Shelter CPI YoY%", f"{format_value(cpic_data.get('shelter_cpi_yoy'))}%")
        st.caption(f"As of: {cpic_data.get('latest_date', 'N/A')} | Source: {cpic_data.get('source', 'N/A')}")
        _render_history_expander(cpic_data, 'Headline CPI YoY (%)', '#e65100', value_suffix='%')

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("71. European Government Yields")
        euy_data = aggregator.get_indicator('71_eu_yields')
        if 'error' in euy_data:
            st.error(f"⚠️ {euy_data['error']}")
        else:
            e1, e2, e3 = st.columns(3)
            with e1:
                st.metric("Germany 10Y", f"{format_value(euy_data.get('de_10y'))}%")
            with e2:
                st.metric("France 10Y", f"{format_value(euy_data.get('fr_10y'))}%")
            with e3:
                st.metric("Italy 10Y", f"{format_value(euy_data.get('it_10y'))}%")
            spread = euy_data.get('it_de_spread')
            if spread is not None:
                st.caption(f"IT-DE Spread: {format_value(spread)}% | Source: {euy_data.get('source', 'N/A')}")

    with col2:
        st.subheader("72. Global CPI Comparison")
        gcpi_data = aggregator.get_indicator('72_global_cpi')
        if 'error' in gcpi_data:
            st.error(f"⚠️ {gcpi_data['error']}")
        else:
            g1, g2, g3, g4 = st.columns(4)
            with g1:
                st.metric("US CPI", f"{format_value(gcpi_data.get('us_cpi_yoy'))}%")
            with g2:
                st.metric("EU CPI", f"{format_value(gcpi_data.get('eu_cpi_yoy'))}%")
            with g3:
                st.metric("Japan CPI", f"{format_value(gcpi_data.get('jp_cpi_yoy'))}%")
            with g4:
                st.metric("UK CPI", f"{format_value(gcpi_data.get('uk_cpi_yoy'))}%")
            st.caption(f"Source: {gcpi_data.get('source', 'N/A')}")
            _render_history_expander(gcpi_data, 'US CPI YoY (%)', '#e65100', value_suffix='%')

    st.subheader("75. Full Treasury Yield Curve")
    tyc_data = aggregator.get_indicator('75_treasury_curve')
    if 'error' in tyc_data:
        st.error(f"⚠️ {tyc_data['error']}")
    else:
        curve = tyc_data.get('curve', {})
        if curve:
            import plotly.graph_objects as go_tyc
            mats = list(curve.keys())
            yields_v = [curve[m] for m in mats]
            fig_tyc = go_tyc.Figure(data=go_tyc.Scatter(x=mats, y=yields_v, mode='lines+markers', line=dict(color='#1565c0')))
            fig_tyc.update_layout(title="US Treasury Yield Curve", xaxis_title="Maturity", yaxis_title="Yield (%)", height=300)
            st.plotly_chart(fig_tyc, use_container_width=True)
            st.caption(f"As of: {tyc_data.get('latest_date', 'N/A')} | Source: {tyc_data.get('source', 'N/A')}")

    st.subheader("76. Corporate Bond Spreads (AAA/BBB)")
    cs_data = aggregator.get_indicator('76_corporate_spreads')
    if 'error' in cs_data:
        st.error(f"⚠️ {cs_data['error']}")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("AAA OAS", f"{format_value(cs_data.get('aaa_oas'))}%")
        with c2:
            st.metric("BBB OAS", f"{format_value(cs_data.get('bbb_oas'))}%")
        with c3:
            st.metric("Credit Spread (BBB-AAA)", f"{format_value(cs_data.get('credit_spread'))}%")
        st.caption(f"As of: {cs_data.get('latest_date', 'N/A')} | Source: {cs_data.get('source', 'N/A')}")


# ── Tab 8: Economic Activity ─────────────────────────────────────────────
with tab8:
    import plotly.graph_objects as go

    st.header("Economic Activity")

    # ── Section 1: Employment & Recession Risk ────────────────────────
    st.subheader("Employment & Recession Risk")

    col1, col2, col3, col4 = st.columns(4)

    # Nonfarm Payrolls
    with col1:
        nfp_data = aggregator.get_indicator('42_nfp')
        if 'error' in nfp_data:
            st.error(f"⚠️ {nfp_data['error']}")
        else:
            nfp_k = nfp_data.get('nfp_thousands', 'N/A')
            nfp_chg = nfp_data.get('nfp_change_mom', 0)
            st.metric("Nonfarm Payrolls (K)", f"{format_value(nfp_k, 0)}", f"{format_value(nfp_chg, 0)}K MoM")
            st.caption(f"As of: {nfp_data.get('latest_date', 'N/A')}")
            if 'interpretation' in nfp_data:
                st.caption(f"ℹ️ {nfp_data['interpretation']}")
            _render_history_expander(nfp_data, 'Nonfarm Payrolls (K)', '#1565c0')

    # JOLTS Job Openings
    with col2:
        jolts_data = aggregator.get_indicator('48_jolts')
        if 'error' in jolts_data:
            st.error(f"⚠️ {jolts_data['error']}")
        else:
            jolts_m = jolts_data.get('jolts_openings_m', 'N/A')
            jolts_chg = jolts_data.get('change_mom_pct', 0)
            st.metric("JOLTS Openings (M)", format_value(jolts_m, 2), f"{format_value(jolts_chg, 1)}% MoM")
            st.caption(f"As of: {jolts_data.get('latest_date', 'N/A')}")
            if 'interpretation' in jolts_data:
                st.caption(f"ℹ️ {jolts_data['interpretation']}")
            _render_history_expander(jolts_data, 'JOLTS Openings (M)', '#0d47a1')

    # Quits Rate
    with col3:
        quits_data = aggregator.get_indicator('60_quits_rate')
        if 'error' in quits_data:
            st.error(f"⚠️ {quits_data['error']}")
        else:
            quits_val = quits_data.get('quits_rate', 'N/A')
            quits_chg = quits_data.get('change_mom', 0)
            st.metric("Quits Rate (%)", f"{format_value(quits_val, 1)}%", f"{format_value(quits_chg, 1)} MoM")
            st.caption(f"As of: {quits_data.get('latest_date', 'N/A')}")
            if 'interpretation' in quits_data:
                st.caption(f"ℹ️ {quits_data['interpretation']}")
            _render_history_expander(quits_data, 'Quits Rate (%)', '#1a237e', value_suffix='%')

    # Sahm Rule Recession Indicator
    with col4:
        sahm_data = aggregator.get_indicator('46_sahm_rule')
        if 'error' in sahm_data:
            st.error(f"⚠️ {sahm_data['error']}")
        else:
            sahm_val = sahm_data.get('sahm_value', 'N/A')
            sahm_chg = sahm_data.get('change_mom', 0)
            triggered = sahm_data.get('triggered', False)
            st.metric("Sahm Rule", format_value(sahm_val, 2), f"{format_value(sahm_chg, 2)} MoM")
            if triggered:
                st.markdown("🔴 **RECESSION SIGNAL TRIGGERED** (≥ 0.50)")
            else:
                st.markdown(f"🟢 Below threshold (< 0.50)")
            st.caption(f"As of: {sahm_data.get('latest_date', 'N/A')}")

            # Sahm Rule chart with 0.50 threshold line
            sahm_hist = sahm_data.get('historical')
            if sahm_hist is not None and len(sahm_hist) > 0:
                with st.expander("📈 Sahm Rule History"):
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=sahm_hist.index, y=sahm_hist.values,
                        name='Sahm Rule', line=dict(color='#c62828', width=1.5),
                        fill='tozeroy', fillcolor='rgba(198,40,40,0.08)',
                    ))
                    fig.add_hline(y=0.50, line_dash="dash", line_color="red", opacity=0.7,
                                  annotation_text="Recession threshold (0.50)")
                    fig.update_layout(
                        yaxis_title="Sahm Rule (pp)",
                        hovermode='x unified', height=320,
                        margin=dict(l=50, r=20, t=10, b=10),
                        showlegend=False,
                    )
                    st.plotly_chart(fig, use_container_width=True)


    # ── Section 2: Consumer ───────────────────────────────────────────
    st.subheader("Consumer")

    col1, col2 = st.columns(2)

    # Consumer Sentiment (UMich)
    with col1:
        cs_data = aggregator.get_indicator('44_consumer_sentiment')
        if 'error' in cs_data:
            st.error(f"⚠️ {cs_data['error']}")
        else:
            cs_val = cs_data.get('consumer_sentiment', 'N/A')
            cs_chg = cs_data.get('change_mom', 0)
            st.metric("UMich Consumer Sentiment", format_value(cs_val, 1), f"{format_value(cs_chg, 1)} MoM")
            st.caption(f"As of: {cs_data.get('latest_date', 'N/A')}")
            if 'interpretation' in cs_data:
                st.caption(f"ℹ️ {cs_data['interpretation']}")
            _render_history_expander(cs_data, 'Consumer Sentiment', '#00695c')

    # Retail Sales
    with col2:
        rs_data = aggregator.get_indicator('50_retail_sales')
        if 'error' in rs_data:
            st.error(f"⚠️ {rs_data['error']}")
        else:
            rs_b = rs_data.get('retail_sales_b', 'N/A')
            rs_mom = rs_data.get('retail_sales_mom_pct', 0)
            st.metric("Retail Sales ($B)", format_value(rs_b, 1), f"{format_value(rs_mom, 2)}% MoM")
            st.caption(f"As of: {rs_data.get('latest_date', 'N/A')}")
            if 'interpretation' in rs_data:
                st.caption(f"ℹ️ {rs_data['interpretation']}")
            _render_history_expander(rs_data, 'Retail Sales MoM%', '#2e7d32', value_suffix='%')


    # ── Section 3: Production & Housing ───────────────────────────────
    st.subheader("Production & Housing")

    col1, col2, col3 = st.columns(3)

    # ISM Services PMI
    with col1:
        ism_svc_data = aggregator.get_indicator('43_ism_services')
        if 'error' in ism_svc_data:
            st.error(f"⚠️ {ism_svc_data['error']}")
        else:
            ism_svc_val = ism_svc_data.get('ism_services_pmi', 'N/A')
            ism_svc_chg = ism_svc_data.get('change_1d', 0)
            st.metric("ISM Services PMI", format_value(ism_svc_val, 1), f"{format_value(ism_svc_chg, 1)}")
            st.caption(f"As of: {ism_svc_data.get('latest_date', 'N/A')}")
            if 'interpretation' in ism_svc_data:
                st.caption(f"ℹ️ {ism_svc_data['interpretation']}")

    # Industrial Production
    with col2:
        ip_data = aggregator.get_indicator('59_industrial_production')
        if 'error' in ip_data:
            st.error(f"⚠️ {ip_data['error']}")
        else:
            ip_idx = ip_data.get('indpro_index', 'N/A')
            ip_yoy = ip_data.get('indpro_yoy_pct', 0)
            st.metric("Industrial Production", format_value(ip_idx, 1), f"{format_value(ip_yoy, 1)}% YoY")
            st.caption(f"As of: {ip_data.get('latest_date', 'N/A')}")
            if 'interpretation' in ip_data:
                st.caption(f"ℹ️ {ip_data['interpretation']}")
            _render_history_expander(ip_data, 'Industrial Production (Index)', '#4a148c')

    # Housing Starts
    with col3:
        hs_data = aggregator.get_indicator('51_housing_starts')
        if 'error' in hs_data:
            st.error(f"⚠️ {hs_data['error']}")
        else:
            hs_k = hs_data.get('housing_starts_k', 'N/A')
            hs_chg = hs_data.get('change_mom_pct', 0)
            st.metric("Housing Starts (K, ann.)", format_value(hs_k, 0), f"{format_value(hs_chg, 1)}% MoM")
            st.caption(f"As of: {hs_data.get('latest_date', 'N/A')}")
            if 'interpretation' in hs_data:
                st.caption(f"ℹ️ {hs_data['interpretation']}")
            _render_history_expander(hs_data, 'Housing Starts (K)', '#bf360c')

    # ── OpenBB Economic Activity Indicators ─────────────────────────────
    st.subheader("67. OECD Composite Leading Indicator")
    cli_data = aggregator.get_indicator('67_oecd_cli')
    if 'error' in cli_data:
        st.error(f"⚠️ {cli_data['error']}")
    else:
        c1, c2 = st.columns(2)
        with c1:
            cli_val = cli_data.get('cli_value')
            st.metric("US CLI", format_value(cli_val), "Above 100 = expansion" if cli_data.get('above_100') else "Below 100 = contraction")
        with c2:
            st.caption(f"As of: {cli_data.get('latest_date', 'N/A')}")
            st.caption("OECD CLI leads GDP by 6-9 months. Above 100 = expansion phase.")
        _render_history_expander(cli_data, 'OECD CLI', '#2e7d32')

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("77. International Unemployment")
        iu_data = aggregator.get_indicator('77_intl_unemployment')
        if 'error' in iu_data:
            st.error(f"⚠️ {iu_data['error']}")
        else:
            u1, u2, u3, u4 = st.columns(4)
            with u1:
                st.metric("US", f"{format_value(iu_data.get('us_unemployment'))}%")
            with u2:
                st.metric("Eurozone", f"{format_value(iu_data.get('eu_unemployment'))}%")
            with u3:
                st.metric("Japan", f"{format_value(iu_data.get('jp_unemployment'))}%")
            with u4:
                st.metric("UK", f"{format_value(iu_data.get('uk_unemployment'))}%")
            st.caption(f"Source: {iu_data.get('source', 'N/A')}")

    with col2:
        st.subheader("78. International GDP Growth")
        ig_data = aggregator.get_indicator('78_intl_gdp')
        if 'error' in ig_data:
            st.error(f"⚠️ {ig_data['error']}")
        else:
            g1, g2, g3, g4 = st.columns(4)
            with g1:
                st.metric("US", f"{format_value(ig_data.get('us_gdp_growth'))}%")
            with g2:
                st.metric("EU", f"{format_value(ig_data.get('eu_gdp_growth'))}%")
            with g3:
                st.metric("Japan", f"{format_value(ig_data.get('jp_gdp_growth'))}%")
            with g4:
                st.metric("China", f"{format_value(ig_data.get('cn_gdp_growth'))}%")
            st.caption(f"Source: {ig_data.get('source', 'N/A')}")
            _render_history_expander(ig_data, 'US Real GDP Growth', '#1565c0', value_suffix='%')

    st.subheader("81. Global Manufacturing PMI")
    pmi_data = aggregator.get_indicator('81_global_pmi')
    if 'error' in pmi_data:
        st.error(f"⚠️ {pmi_data['error']}")
    else:
        p1, p2, p3, p4, p5 = st.columns(5)
        with p1:
            st.metric("US", format_value(pmi_data.get('us_mfg_pmi'), 1))
        with p2:
            st.metric("EU", format_value(pmi_data.get('eu_mfg_pmi'), 1))
        with p3:
            st.metric("Japan", format_value(pmi_data.get('jp_mfg_pmi'), 1))
        with p4:
            st.metric("China", format_value(pmi_data.get('cn_mfg_pmi'), 1))
        with p5:
            st.metric("UK", format_value(pmi_data.get('uk_mfg_pmi'), 1))
        st.caption(f"50 = expansion/contraction threshold | Source: {pmi_data.get('source', 'N/A')}")
        _render_history_expander(pmi_data, 'US Manufacturing PMI', '#e65100')


# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>📊 Macroeconomic Indicators Dashboard | Data sources: FRED, Yahoo Finance, OpenBB, CBOE, Robert Shiller, Trading Economics, SEC EDGAR</p>
    <p>⚠️ For informational purposes only. Not financial advice.</p>
</div>
""", unsafe_allow_html=True)
