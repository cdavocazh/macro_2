"""
Streamlit Dashboard for Macroeconomic Indicators
Displays 10 key macroeconomic indicators with manual refresh capability.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
from data_aggregator import get_aggregator
from utils.helpers import format_value

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
</style>
""", unsafe_allow_html=True)

# Title and description
st.title("📊 Macroeconomic Indicators Dashboard")
st.markdown("Real-time tracking of 10 key macroeconomic indicators for market analysis")

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

    st.markdown("---")

    st.header("ℹ️ About")
    st.markdown("""
    This dashboard tracks 10 key macroeconomic indicators:

    1. **S&P 500 Forward P/E**
    2. **Russell 2000 Indices**
    3. **S&P 500 Trailing P/E & P/B**
    4. **S&P 500 Put/Call Ratio**
    5. **SPX Call Skew**
    6. **S&P 500 / 200MA**
    7. **Market Cap / GDP Ratio**
    8. **Shiller CAPE**
    9. **VIX & VIX/MOVE**
    10. **MOVE Index & DXY**
    """)

    st.markdown("---")

    # Data sources
    st.subheader("📚 Data Sources")
    st.markdown("""
    - **FRED**: Federal Reserve Economic Data
    - **Yahoo Finance**: Market indices
    - **OpenBB**: Financial data platform
    - **Robert Shiller**: CAPE ratio
    - **CBOE**: Volatility indices
    """)

# Initialize aggregator
aggregator = get_aggregator()

# Check if data needs to be fetched
if not aggregator.indicators:
    with st.spinner("Loading initial data..."):
        aggregator.fetch_all_indicators()

# Display last update time
if aggregator.last_update:
    st.info(f"📅 Last Updated: {aggregator.last_update.strftime('%Y-%m-%d %H:%M:%S')}")

# Create tabs for different indicator categories
tab1, tab2, tab3, tab4 = st.tabs([
    "📈 Valuation Metrics",
    "📊 Market Indices",
    "⚡ Volatility & Risk",
    "🌍 Macro & Currency"
])

# Tab 1: Valuation Metrics
with tab1:
    st.header("Valuation Metrics")

    col1, col2 = st.columns(2)

    # 1. S&P 500 Forward P/E
    with col1:
        st.subheader("1. S&P 500 Forward P/E")
        data = aggregator.get_indicator('1_sp500_forward_pe')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
            if 'note' in data:
                st.info(data['note'])
        else:
            value = data.get('sp500_forward_pe', 'N/A')
            st.metric("Forward P/E Ratio", format_value(value))
            st.caption(f"Source: {data.get('source', 'N/A')}")

    # 3. S&P 500 Trailing P/E & P/B
    with col2:
        st.subheader("3. S&P 500 Trailing P/E & P/B")
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
            st.caption(f"Source: {data.get('source', 'N/A')}")

    # 7. Shiller CAPE Ratio
    st.subheader("7. Shiller CAPE Ratio")
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

    # 6b. Market Cap / GDP
    st.subheader("6b. S&P 500 Market Cap / US GDP (Buffett Indicator)")
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

# Tab 2: Market Indices
with tab2:
    st.header("Market Indices")

    # 2. Russell 2000 Indices
    st.subheader("2. Russell 2000 Value vs Growth")
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
    st.subheader("6a. S&P 500 / 200-Day Moving Average")
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

# Tab 3: Volatility & Risk
with tab3:
    st.header("Volatility & Risk Indicators")

    col1, col2 = st.columns(2)

    # 8. VIX
    with col1:
        st.subheader("8. VIX (Volatility Index)")
        data = aggregator.get_indicator('8_vix')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            vix_value = data.get('vix', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("VIX", format_value(vix_value, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")

    # 9. MOVE Index
    with col2:
        st.subheader("9. MOVE Index (Bond Volatility)")
        data = aggregator.get_indicator('9_move_index')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            move_value = data.get('move', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("MOVE Index", format_value(move_value, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")

    # 8b. VIX/MOVE Ratio
    st.subheader("8b. VIX/MOVE Ratio")
    data = aggregator.get_indicator('8b_vix_move_ratio')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
    else:
        ratio = data.get('vix_move_ratio', 'N/A')
        st.metric("VIX/MOVE Ratio", format_value(ratio, 3))
        st.info("Higher ratio suggests equity volatility is elevated relative to bond volatility")

    col1, col2 = st.columns(2)

    # 4. Put/Call Ratio
    with col1:
        st.subheader("4. S&P 500 Put/Call Ratio")
        data = aggregator.get_indicator('4_put_call_ratio')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
            if 'note' in data:
                st.info(data['note'])
        else:
            pc_ratio = data.get('sp500_put_call_ratio', 'N/A')
            st.metric("Put/Call Ratio", format_value(pc_ratio, 3))

    # 5. SPX Call Skew
    with col2:
        st.subheader("5. SPX Call Skew (CBOE SKEW)")
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

# Tab 4: Macro & Currency
with tab4:
    st.header("Macro & Currency")

    # 10. DXY
    st.subheader("10. U.S. Dollar Index (DXY)")
    data = aggregator.get_indicator('10_dxy')
    if 'error' in data:
        st.error(f"⚠️ {data['error']}")
    else:
        dxy_value = data.get('dxy', 'N/A')
        change = data.get('change_1d', 0)
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            st.metric("DXY", format_value(dxy_value, 2), f"{format_value(change, 2)}%")
        with col2:
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>📊 Macroeconomic Indicators Dashboard | Data sources: FRED, Yahoo Finance, OpenBB, CBOE, Robert Shiller</p>
    <p>⚠️ For informational purposes only. Not financial advice.</p>
</div>
""", unsafe_allow_html=True)
