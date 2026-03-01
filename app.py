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
    - TGA Balance, Net Liquidity
    - SOFR, US 2Y Yield

    **Commodities:**
    - Gold, Silver, Crude Oil, Copper
    - CFTC COT Positioning
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

# Check if data needs to be fetched - try local cache first for fast startup
if not aggregator.indicators:
    if aggregator.load_from_local_cache():
        pass  # loaded from cache
    else:
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
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📈 Valuation Metrics",
    "📊 Market Indices",
    "⚡ Volatility & Risk",
    "🌍 Macro & Currency",
    "💰 Commodities",
    "🏢 Large-cap Financials"
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
            _render_history_expander(data, 'VIX', '#e53935')

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
            _render_history_expander(data, 'MOVE Index', '#ff9800')

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
            _render_history_expander(data, 'DXY', '#2e7d32')

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
            _render_history_expander(data, 'USD/JPY', '#d84315')

    st.markdown("---")

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
            st.caption(f"As of: {data.get('latest_date', 'N/A')} | Source: {data.get('source', 'N/A')}")
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
            st.caption("= Fed Assets - TGA - ON RRP")
            if 'interpretation' in data:
                st.caption(f"ℹ️ {data['interpretation']}")
            _render_history_expander(data, 'Net Liquidity ($M)', '#1565c0')

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
            st.caption(f"As of: {data.get('latest_date', 'N/A')} | Source: {data.get('source', 'N/A')}")
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
            st.caption(f"As of: {data.get('latest_date', 'N/A')} | Source: {data.get('source', 'N/A')}")
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
            st.caption(f"As of: {data.get('latest_date', 'N/A')} | Source: {data.get('source', 'N/A')}")
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
            st.caption(f"Source: {data.get('source', 'N/A')}")
            if 'interpretation' in data:
                st.caption(f"ℹ️ {data['interpretation']}")
            _render_history_expander(data, 'US-JP 2Y Spread (%)', '#ff7f0e', value_suffix='%')

    # US-JP 2Y Spread historical chart
    spread_data = aggregator.get_indicator('28_us2y_jp2y_spread')
    if 'error' not in spread_data and 'historical' in spread_data:
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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
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
            if 'expiry_date' in data:
                st.caption(f"📅 Contract Expiry: {data['expiry_date']}")
            if 'note' in data:
                st.caption(f"ℹ️ {data['note']}")
            _render_history_expander(data, 'Copper (USD/lb)', '#B87333')

    # CFTC COT Positioning
    st.divider()
    st.header("CFTC Commitment of Traders — Gold & Silver")
    st.caption("Weekly positioning data from CFTC. Managed money = hedge funds. Commercial = producers/hedgers.")

    cot_data = aggregator.get_indicator('22_cot_positioning')
    if 'error' in cot_data:
        st.error(f"⚠️ {cot_data['error']}")
        if 'suggestion' in cot_data:
            st.info(cot_data['suggestion'])
    else:
        st.caption(f"As of: {cot_data.get('latest_date', 'N/A')} | Source: {cot_data.get('source', 'N/A')}")

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

def _fetch_source_data(source_name, ticker, eq_data):
    """Fetch company data from the selected source."""
    if source_name == "Yahoo Finance":
        companies = eq_data.get('companies', {})
        return companies.get(ticker)
    elif source_name == "SEC EDGAR":
        cache_key = f'sec_{ticker}'
        if cache_key not in st.session_state:
            with st.spinner(f"Fetching SEC data for {ticker}..."):
                from data_extractors.sec_extractor import get_company_financials_sec
                st.session_state[cache_key] = get_company_financials_sec(ticker)
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
    st.header("Large-cap Financials (Top 20 by Market Cap)")

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

            # Ticker selector
            available = [t for t in tickers if t in companies and 'error' not in companies[t]]
            if not available:
                st.warning("No company data available.")
            else:
                selected = st.selectbox(
                    "Select Company",
                    available,
                    format_func=lambda t: f"{t} — {companies[t].get('company_name', t)}",
                )

                # Fetch data from selected source
                co = _fetch_source_data(data_source, selected, eq_data)

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

                    st.divider()

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

                    st.divider()

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

                    st.divider()

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

                    st.divider()

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

                    st.divider()

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

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666;'>
    <p>📊 Macroeconomic Indicators Dashboard | Data sources: FRED, Yahoo Finance, OpenBB, CBOE, Robert Shiller</p>
    <p>⚠️ For informational purposes only. Not financial advice.</p>
</div>
""", unsafe_allow_html=True)
