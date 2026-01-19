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
</style>
""", unsafe_allow_html=True)

# Title and description
st.title("📊 Macroeconomic Indicators Dashboard")
st.markdown("Real-time tracking of 17 key macroeconomic indicators for market analysis")

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
    This dashboard tracks 17 key macroeconomic indicators:

    **Valuation Metrics:**
    - S&P 500 Forward P/E
    - S&P 500 Trailing P/E & P/B
    - Shiller CAPE
    - Market Cap / GDP Ratio

    **Market Indices:**
    - Russell 2000 Value vs Growth
    - S&P 500 / 200MA

    **Volatility & Risk:**
    - VIX
    - MOVE Index
    - VIX/MOVE Ratio
    - Put/Call Ratio
    - SPX Call Skew

    **Macro & Currency:**
    - DXY (US Dollar Index)
    - 10-Year Treasury Yield
    - ISM Manufacturing PMI

    **Commodities:**
    - Gold, Silver, Crude Oil, Copper
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
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📈 Valuation Metrics",
    "📊 Market Indices",
    "⚡ Volatility & Risk",
    "🌍 Macro & Currency",
    "💰 Commodities"
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
            st.caption(f"Source: {data.get('source', 'N/A')}")

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
            st.caption(f"Source: {data.get('source', 'N/A')}")

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

    st.markdown("---")

    # Historical Charts
    st.header("Historical Valuation Metrics")

    # Interval selector
    interval = st.radio("Select Interval", ["Weekly", "Monthly"], horizontal=True, key="interval_selector")
    interval_param = "1wk" if interval == "Weekly" else "1mo"

    # Get 10 years of historical data
    import yfinance as yf
    from datetime import timedelta
    import plotly.graph_objects as go

    end_date = pd.Timestamp.now()
    start_date = end_date - timedelta(days=3650)  # 10 years

    try:
        # Get SPY data for P/B ratio
        spy = yf.Ticker("SPY")
        spy_hist = spy.history(start=start_date, end=end_date, interval=interval_param)

        if not spy_hist.empty:
            # Get P/E and P/B data
            # Note: yfinance doesn't provide historical P/E and P/B in history()
            # We'll need to calculate or use another approach
            # For now, we'll show price history and note that full historical P/E and P/B require additional data sources

            st.subheader("S&P 500 (SPY) Price History")
            st.info("Note: Historical Forward P/E and P/B ratios require specialized data sources. Showing SPY price as reference. For complete historical valuation metrics, consider integrating with MacroMicro API or similar services.")

            # Create price chart
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=spy_hist.index,
                y=spy_hist['Close'],
                name='SPY Price',
                line=dict(color='blue')
            ))

            fig.update_layout(
                title=f"S&P 500 (SPY) Price - Last 10 Years ({interval})",
                xaxis_title="Date",
                yaxis_title="Price (USD)",
                hovermode='x unified',
                height=500
            )

            st.plotly_chart(fig, use_container_width=True)

            # Note about data limitations
            st.caption("""
            **Data Note**: Historical Forward P/E and P/B ratios are not available through free APIs.
            To display complete historical valuation metrics, you would need to:
            1. Subscribe to premium data services (Bloomberg, FactSet, MacroMicro API)
            2. Scrape and store historical data over time
            3. Use specialized financial data providers
            """)
        else:
            st.warning("Unable to fetch historical SPY data")

    except Exception as e:
        st.error(f"Error loading historical data: {str(e)}")

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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")

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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")

    st.divider()

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
            st.caption(f"Source: {data.get('source', 'N/A')}")

    st.divider()

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

# Tab 3: Volatility & Risk
with tab3:
    st.header("Volatility & Risk Indicators")

    col1, col2 = st.columns(2)

    # 8. VIX
    with col1:
        st.subheader(f"8. [VIX (Volatility Index)]({SOURCE_URLS['vix']})")
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
        st.subheader(f"9. [MOVE Index (Bond Volatility)]({SOURCE_URLS['move']})")
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
        st.subheader(f"4. [S&P 500 Put/Call Ratio]({SOURCE_URLS['put_call_ratio']})")
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

# Tab 4: Macro & Currency
with tab4:
    st.header("Macro & Currency")

    # Currency Indices
    st.subheader("Currency Indices")
    col1, col2 = st.columns(2)

    # 10. DXY
    with col1:
        st.subheader(f"[U.S. Dollar Index (DXY)]({SOURCE_URLS['dxy']})")
        data = aggregator.get_indicator('10_dxy')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            dxy_value = data.get('dxy', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("DXY", format_value(dxy_value, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")

    # JPY Exchange Rate
    with col2:
        st.subheader(f"[USD/JPY Exchange Rate]({SOURCE_URLS['jpy']})")
        data = aggregator.get_indicator('20_jpy')
        if 'error' in data:
            st.error(f"⚠️ {data['error']}")
        else:
            jpy_rate = data.get('jpy_rate', 'N/A')
            change = data.get('change_1d', 0)
            st.metric("USD/JPY", format_value(jpy_rate, 2), f"{format_value(change, 2)}%")
            st.caption(f"As of: {data.get('latest_date', 'N/A')}")
            st.caption(f"Units: {data.get('units', 'JPY per USD')}")

    st.markdown("---")

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
        with col2:
            ism_value = ism_data.get('ism_pmi', 'N/A')
            st.metric("ISM Manufacturing PMI", format_value(ism_value, 1))
            st.caption(f"As of: {ism_data.get('latest_date', 'N/A')}")
            if 'note' in ism_data:
                st.caption(f"ℹ️ {ism_data['note']}")
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
            import plotly.graph_objects as go
            from plotly.subplots import make_subplots

            # Align data by date
            yield_hist = yield_data['historical']
            ism_hist = ism_data['historical']

            # Create figure with secondary y-axis
            fig = make_subplots(specs=[[{"secondary_y": True}]])

            # Add 10Y Yield trace
            fig.add_trace(
                go.Scatter(x=yield_hist.index, y=yield_hist.values, name="10Y Treasury Yield", line=dict(color='blue')),
                secondary_y=False,
            )

            # Add ISM PMI trace
            fig.add_trace(
                go.Scatter(x=ism_hist.index, y=ism_hist.values, name="ISM Manufacturing PMI", line=dict(color='orange')),
                secondary_y=True,
            )

            # Update layout
            fig.update_layout(
                title_text="10-Year Treasury Yield vs ISM Manufacturing PMI",
                hovermode='x unified',
                height=500
            )

            # Set y-axes titles
            fig.update_yaxes(title_text="10Y Yield (%)", secondary_y=False)
            fig.update_yaxes(title_text="ISM PMI", secondary_y=True)

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Historical data not available for charting")

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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")

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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")

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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")

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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>📊 Macroeconomic Indicators Dashboard | Data sources: FRED, Yahoo Finance, OpenBB, CBOE, Robert Shiller</p>
    <p>⚠️ For informational purposes only. Not financial advice.</p>
</div>
""", unsafe_allow_html=True)
