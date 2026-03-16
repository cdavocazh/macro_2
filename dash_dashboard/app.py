"""
Plotly Dash Dashboard for Macroeconomic Indicators.
Full 1:1 port of the Streamlit dashboard (8 tabs, 75+ indicators).

Run:  python dash_dashboard/app.py
"""
import os
import sys

# Add parent directory for project imports
PARENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from dash import Dash, html, dcc, callback, Input, Output, State, no_update
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json

from data_loader import get_loader, format_value, fmt_dollar, fmt_pct, CACHE_FILE, to_gmt8, to_gmt8_date

# Progress file written by data_aggregator / fast_extract
PROGRESS_FILE = os.path.join(PARENT_DIR, 'data_cache', '.extract_progress.json')
# Stale threshold: if progress hasn't updated in this many seconds, consider it stuck
_STALL_THRESHOLD_SECS = 120

# On-demand fetchers for custom tickers / SEC source toggle
try:
    from data_extractors.equity_financials_extractor import get_company_financials_yahoo
except ImportError:
    get_company_financials_yahoo = None

try:
    from data_extractors.sec_extractor import get_company_financials_sec
except ImportError:
    get_company_financials_sec = None

# Source URLs for all indicators (matches Streamlit)
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
    'jpy': 'https://finance.yahoo.com/quote/JPY%3DX/',
}

# ─── App init ───────────────────────────────────────────────────────────────
app = Dash(
    __name__,
    title="Macro Indicators Dashboard",
    update_title=None,
    suppress_callback_exceptions=True,
    requests_pathname_prefix=os.environ.get('DASH_PREFIX', '/'),
)
server = app.server  # Expose Flask server for Gunicorn

TOP_20_TICKERS = [
    'AAPL', 'MSFT', 'NVDA', 'GOOGL', 'AMZN', 'META', 'BRK-B', 'TSM',
    'LLY', 'AVGO', 'JPM', 'V', 'WMT', 'MA', 'XOM', 'UNH', 'COST', 'HD', 'PG', 'JNJ',
]

# ─── Helper components ─────────────────────────────────────────────────────


def metric_card(label, value, delta=None, caption=None, border_color='#1f77b4'):
    """Create a compact metric card."""
    delta_class = ''
    if delta is not None:
        try:
            delta_class = 'positive' if float(str(delta).replace('%', '').replace('+', '')) >= 0 else 'negative'
        except (ValueError, TypeError):
            delta_class = ''

    children = [
        html.Div(label, className='metric-label'),
        html.Div(str(value), className='metric-value'),
    ]
    if delta is not None:
        children.append(html.Div(str(delta), className=f'metric-delta {delta_class}'))
    if caption:
        children.append(html.Div(caption, className='metric-caption'))

    return html.Div(children, className='metric-card', style={'borderLeftColor': border_color})


def metric_card_with_components(label, value, components_html, delta=None, caption=None, border_color='#1f77b4'):
    """Metric card with numerator/denominator component display below."""
    delta_class = ''
    if delta is not None:
        try:
            delta_class = 'positive' if float(str(delta).replace('%', '').replace('+', '')) >= 0 else 'negative'
        except (ValueError, TypeError):
            delta_class = ''

    children = [
        html.Div(label, className='metric-label'),
        html.Div(str(value), className='metric-value'),
    ]
    if delta is not None:
        children.append(html.Div(str(delta), className=f'metric-delta {delta_class}'))
    if components_html:
        children.append(dcc.Markdown(components_html, dangerously_allow_html=True,
                                      style={'margin': '0', 'lineHeight': '1.2'}))
    if caption:
        children.append(html.Div(caption, className='metric-caption'))

    return html.Div(children, className='metric-card', style={'borderLeftColor': border_color})


def error_card(label, error_msg, border_color='#c62828'):
    return html.Div([
        html.Div(label, className='metric-label'),
        html.Div(f"Error: {error_msg}", className='metric-value', style={'color': '#c62828', 'fontSize': '0.85rem'}),
    ], className='metric-card error', style={'borderLeftColor': border_color})


def section_header(text):
    return html.H2(text, className='section-header')


def section_subheader(text, url=None):
    if url:
        return html.H3(html.A(text, href=url, target='_blank',
                               style={'color': 'inherit', 'textDecoration': 'none', 'borderBottom': '1px dotted #999'}),
                        className='section-subheader')
    return html.H3(text, className='section-subheader')


def info_badge(text, badge_type='info'):
    """Colored badge matching Streamlit's st.success/info/warning/error."""
    colors = {
        'success': {'bg': '#e8f5e9', 'border': '#4caf50', 'icon': ''},
        'info': {'bg': '#e3f2fd', 'border': '#2196f3', 'icon': ''},
        'warning': {'bg': '#fff3e0', 'border': '#ff9800', 'icon': ''},
        'error': {'bg': '#ffebee', 'border': '#f44336', 'icon': ''},
    }
    c = colors.get(badge_type, colors['info'])
    return html.Div(text, style={
        'backgroundColor': c['bg'], 'borderLeft': f'4px solid {c["border"]}',
        'padding': '6px 12px', 'borderRadius': '4px', 'fontSize': '0.82rem',
        'marginBottom': '6px', 'color': '#333',
    })


def make_history_chart(series, label, color='#1f77b4', height=300, days=92):
    """Build a history line chart from a pd.Series with adaptive range buttons."""
    if series is None or not hasattr(series, 'index') or len(series) == 0:
        return None

    try:
        series = series.copy()
        if not isinstance(series.index, pd.DatetimeIndex):
            series.index = pd.to_datetime(series.index, utc=True)
        if hasattr(series.index, 'tz') and series.index.tz is not None:
            series.index = series.index.tz_convert(None)
    except Exception:
        try:
            series.index = pd.to_datetime(series.index)
        except Exception:
            return None

    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    filtered = series[series.index >= cutoff]
    if len(filtered) < 2:
        filtered = series.tail(max(65, len(series)))

    hex_c = color.lstrip('#')
    r, g, b = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=filtered.index, y=filtered.values,
        name=label, line=dict(color=color, width=1.5),
        fill='tozeroy', fillcolor=f'rgba({r},{g},{b},0.08)',
        hovertemplate='%{x|%b %d, %Y}: %{y:,.2f}<extra></extra>',
    ))

    # Adaptive range buttons based on data span
    buttons = [
        dict(count=7, label="1W", step="day", stepmode="backward"),
        dict(count=1, label="1M", step="month", stepmode="backward"),
        dict(count=3, label="3M", step="month", stepmode="backward"),
    ]
    if days > 180:
        buttons.append(dict(count=6, label="6M", step="month", stepmode="backward"))
    if days > 365:
        buttons.append(dict(count=1, label="1Y", step="year", stepmode="backward"))
    if days > 730:
        buttons.append(dict(count=2, label="2Y", step="year", stepmode="backward"))
    buttons.append(dict(label="All", step="all"))

    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(buttons=buttons, bgcolor='#f0f2f6'),
            rangeslider=dict(visible=True, thickness=0.05),
        ),
        yaxis=dict(title=label),
        height=height,
        margin=dict(l=50, r=20, t=10, b=10),
        showlegend=False,
        hovermode='x unified',
    )
    return fig


def history_expander(data, label, color='#1f77b4', hist_key='historical',
                     convert_fn=None, days=92, summary_label=None):
    """Render a collapsible price history chart (mirrors st.expander)."""
    hist = data.get(hist_key)
    if hist is None or not hasattr(hist, 'index') or len(hist) == 0:
        return None

    if convert_fn is not None:
        try:
            hist = convert_fn(hist)
        except Exception:
            pass

    fig = make_history_chart(hist, label, color, days=days)
    if fig is None:
        return None

    # Dynamic summary label
    if summary_label is None:
        if days <= 92:
            summary_label = "3M Price History"
        elif days <= 182:
            summary_label = "6M Price History"
        elif days <= 365:
            summary_label = "1Y Price History"
        else:
            summary_label = "2Y Price History"

    return html.Details([
        html.Summary(summary_label, style={
            'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666',
            'padding': '4px 0',
        }),
        dcc.Graph(figure=fig, className='dash-graph', config={'displayModeBar': False}),
    ], style={'marginTop': '2px', 'marginBottom': '4px'})


def indicator_with_chart(data, label, value_key, value_fmt=2, delta_key='change_1d',
                          delta_suffix='%', color='#1f77b4', hist_key='historical',
                          caption_key='latest_date', border_color=None, days=92):
    """Render a metric card + optional collapsible history chart."""
    bc = border_color or color
    if 'error' in data:
        return error_card(label, data['error'], bc)

    val = data.get(value_key, 'N/A')
    delta_val = data.get(delta_key)
    delta_str = None
    if delta_val is not None:
        delta_str = f"{format_value(delta_val, value_fmt)}{delta_suffix}"

    cap = f"As of: {to_gmt8_date(data.get(caption_key))}" if caption_key else None
    card = metric_card(label, format_value(val, value_fmt), delta_str, cap, bc)

    expander = history_expander(data, label, color, hist_key, days=days)
    if expander:
        return html.Div([card, expander])
    return card


# ─── Financial table helpers (Tab 6) ──────────────────────────────────────


def _fmt_ratio(v, decimals=2):
    if v is None:
        return 'N/A'
    try:
        return f"{float(v):.{decimals}f}"
    except (ValueError, TypeError):
        return 'N/A'


def _fmt_pct_plus(v):
    if v is None:
        return 'N/A'
    try:
        return f"{float(v):+.1f}%"
    except (ValueError, TypeError):
        return 'N/A'


def _metric_components(numerator_label, numerator_val, denominator_label, denominator_val, annualized=False):
    """Return small HTML showing numerator / denominator below a metric."""
    n_str = fmt_dollar(numerator_val) if numerator_val is not None else "—"
    d_str = fmt_dollar(denominator_val) if denominator_val is not None else "—"
    ann = " (ann.)" if annualized else ""
    return f'<span style="color:#888;font-size:0.72em">{numerator_label}{ann} / {denominator_label}<br/>{n_str} / {d_str}</span>'


def _val_components(label, numerator_val, denominator_label, denominator_val, n_fmt='$', d_fmt='$'):
    """Return small HTML for valuation metric components."""
    if n_fmt == '$':
        n_str = fmt_dollar(numerator_val) if numerator_val is not None else "—"
    elif n_fmt == 'ratio':
        n_str = f"{numerator_val:.2f}" if numerator_val is not None else "—"
    else:
        n_str = f"{numerator_val}" if numerator_val is not None else "—"
    if d_fmt == '$':
        d_str = fmt_dollar(denominator_val) if denominator_val is not None else "—"
    elif d_fmt == 'pct':
        d_str = f"{denominator_val:.1f}%" if denominator_val is not None else "—"
    elif d_fmt == 'eps':
        d_str = f"${denominator_val:.2f}" if denominator_val is not None else "—"
    else:
        d_str = f"{denominator_val}" if denominator_val is not None else "—"
    return f'<span style="color:#888;font-size:0.72em">{label} / {denominator_label}<br/>{n_str} / {d_str}</span>'


def _parse_quarter_key(q):
    try:
        parts = q.split('-Q')
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return None, None


def _fmt_change(current, previous):
    if current is None or previous is None or previous == 0:
        return ""
    try:
        pct = (float(current) - float(previous)) / abs(float(previous)) * 100
        cls = 'change-positive' if pct >= 0 else 'change-negative'
        return f'<span class="{cls}">{pct:+.1f}%</span>'
    except (ValueError, TypeError, ZeroDivisionError):
        return ""


def build_table_html(data_dict, metrics, quarters_list, with_yoy=True):
    """Build an HTML quarterly table with QoQ and optional YoY change indicators."""
    if not data_dict or not quarters_list:
        return None

    q_parsed = [_parse_quarter_key(q) for q in quarters_list] if with_yoy else []

    header = '<thead><tr style="border-bottom:2px solid #555"><th style="text-align:left;padding:6px 8px;min-width:160px">Metric</th>'
    for q in quarters_list:
        header += f'<th style="text-align:right;padding:6px 8px">{q}</th>'
    header += '</tr></thead>'

    rows_html = ''
    for idx, (label, key, fmt) in enumerate(metrics):
        vals = data_dict.get(key, [])
        bg = '#f8f9fa' if idx % 2 == 0 else '#ffffff'
        row = f'<tr style="background:{bg};border-bottom:1px solid #e0e0e0">'
        row += f'<td style="text-align:left;padding:5px 8px;white-space:nowrap">{label}</td>'
        for i in range(len(quarters_list)):
            v = vals[i] if i < len(vals) else None
            if v is None:
                cell = '—'
            elif fmt == '$':
                cell = fmt_dollar(v)
            elif fmt == '%':
                try:
                    cell = f"{float(v) * 100:.1f}%"
                except (ValueError, TypeError):
                    cell = '—'
            elif fmt == 'eps':
                try:
                    cell = f"${float(v):.2f}"
                except (ValueError, TypeError):
                    cell = '—'
            elif fmt == 'shares':
                try:
                    cell = f"{float(v) / 1e9:.2f}B"
                except (ValueError, TypeError):
                    cell = '—'
            else:
                try:
                    cell = f"{float(v):,.2f}"
                except (ValueError, TypeError):
                    cell = '—'

            # QoQ change
            qoq = ''
            if i + 1 < len(vals) and v is not None and vals[i + 1] is not None:
                try:
                    prev = float(vals[i + 1])
                    if prev != 0:
                        pct = (float(v) - prev) / abs(prev) * 100
                        cls = 'change-positive' if pct >= 0 else 'change-negative'
                        qoq = f'<span class="{cls}">{pct:+.1f}% q/q</span>'
                except (ValueError, TypeError):
                    pass

            # YoY change
            yoy = ''
            if with_yoy and q_parsed:
                yr, qn = q_parsed[i] if i < len(q_parsed) else (None, None)
                if yr and qn:
                    for j in range(i + 1, len(quarters_list)):
                        yr_j, qn_j = q_parsed[j] if j < len(q_parsed) else (None, None)
                        if yr_j and qn_j and qn_j == qn and yr_j == yr - 1:
                            prev_yoy = vals[j] if j < len(vals) else None
                            chg = _fmt_change(v, prev_yoy)
                            if chg:
                                yoy = chg.replace('</span>', ' y/y</span>')
                            break

            changes = qoq + yoy
            row += f'<td style="text-align:right;padding:5px 8px;white-space:nowrap">{cell}{changes}</td>'
        row += '</tr>'
        rows_html += row

    return f'<table class="fin-table">{header}<tbody>{rows_html}</tbody></table>'


# ─── Tab builders ───────────────────────────────────────────────────────────


def build_tab1(loader):
    """Valuation Metrics."""
    children = [section_header("Valuation Metrics")]

    # Forward P/E + Trailing P/E & P/B
    pe_data = loader.get('1_sp500_forward_pe')
    fund_data = loader.get('3_sp500_fundamentals')

    row1 = []
    if 'error' in pe_data:
        row1.append(error_card("S&P 500 Forward P/E", pe_data['error']))
    else:
        pe_card = metric_card("S&P 500 Forward P/E",
                                format_value(pe_data.get('sp500_forward_pe'), 2))
        pe_exp = history_expander(pe_data, 'S&P 500 Forward P/E', '#1f77b4', days=730)
        row1.append(html.Div([pe_card, pe_exp]) if pe_exp else pe_card)

    if 'error' in fund_data:
        row1.append(error_card("S&P 500 Trailing P/E & P/B", fund_data['error']))
    else:
        pe_trailing_card = metric_card("Trailing P/E", format_value(fund_data.get('sp500_pe_trailing'), 2))
        pb_card = metric_card("P/B Ratio", format_value(fund_data.get('sp500_pb'), 2))
        # Historical charts for trailing P/E and P/B
        pe_exp = history_expander(fund_data, 'S&P 500 Trailing P/E', '#1f77b4',
                                   hist_key='historical_pe', days=730)
        pb_exp = history_expander(fund_data, 'S&P 500 P/B', '#e65100',
                                   hist_key='historical_pb', days=730)
        sub_children = [pe_trailing_card, pb_card]
        if pe_exp:
            sub_children.append(pe_exp)
        if pb_exp:
            sub_children.append(pb_exp)
        row1.append(html.Div(sub_children))
    children.append(html.Div(row1, className='metrics-row cols-2'))

    # Shiller CAPE — with interpretation
    cape_data = loader.get('7_shiller_cape')
    if 'error' in cape_data:
        children.append(error_card("Shiller CAPE", cape_data['error']))
    else:
        cape_row = []
        cape_row.append(html.Div([
            metric_card("Shiller CAPE", format_value(cape_data.get('shiller_cape'), 2),
                         caption=f"As of: {to_gmt8_date(cape_data.get('latest_date'))}",
                         border_color='#8e24aa'),
        ]))
        # Interpretation info box
        interp = cape_data.get('interpretation')
        if interp and isinstance(interp, dict):
            bullets = [html.Li(f"{k}: {v}") for k, v in interp.items()]
            cape_row.append(info_badge("", 'info'))
            cape_row[-1] = html.Div([
                html.Strong("Interpretation:", style={'fontSize': '0.8rem'}),
                html.Ul(bullets, style={'fontSize': '0.78rem', 'margin': '4px 0', 'paddingLeft': '16px'}),
            ], style={
                'backgroundColor': '#e3f2fd', 'borderLeft': '4px solid #2196f3',
                'padding': '8px 12px', 'borderRadius': '4px', 'fontSize': '0.82rem',
            })
        children.append(html.Div(cape_row, className='metrics-row cols-2'))
        exp = history_expander(cape_data, 'Shiller CAPE', '#8e24aa')
        if exp:
            children.append(exp)

    # Market Cap / GDP
    mcap_data = loader.get('6b_marketcap_to_gdp')
    if 'error' in mcap_data:
        children.append(error_card("Market Cap / GDP", mcap_data['error']))
    else:
        interp = mcap_data.get('interpretation', '')
        mcap_card = metric_card("Market Cap / GDP (%)",
                                     format_value(mcap_data.get('marketcap_to_gdp_ratio'), 2),
                                     caption=interp if interp else None)
        mcap_exp = history_expander(mcap_data, 'Market Cap / GDP (%)', '#00695c', days=730)
        children.append(html.Div([mcap_card, mcap_exp]) if mcap_exp else mcap_card)

    # ── OpenBB Valuation Indicators ─────────────────────────────────────
    children.append(section_header("S&P 500 Valuation Multiples"))
    mult_data = loader.get('65_sp500_multiples')
    if 'error' in mult_data:
        children.append(error_card("S&P 500 Multiples", mult_data['error']))
    else:
        src = mult_data.get('source', '')
        children.append(html.Div([
            metric_card("Forward P/E", format_value(mult_data.get('forward_pe'), 2)),
            metric_card("Trailing P/E", format_value(mult_data.get('trailing_pe'), 2)),
            metric_card("PEG Ratio", format_value(mult_data.get('peg_ratio'), 2)),
            metric_card("Price/Sales", format_value(mult_data.get('price_to_sales'), 2)),
            metric_card("Price/Book", format_value(mult_data.get('price_to_book'), 2)),
            metric_card("Price/Cash", format_value(mult_data.get('price_to_cash'), 2)),
        ], className='metrics-row cols-6'))
        # EPS growth row (if available from OpenBB/Finviz)
        eps_next = mult_data.get('eps_growth_next_5y') or mult_data.get('eps_growth_next_y')
        eps_past = mult_data.get('eps_growth_past_5y')
        if eps_next or eps_past:
            children.append(html.Div([
                metric_card("EPS Growth (Next 5Y)", f"{format_value(eps_next, 2)}%") if eps_next else html.Div(),
                metric_card("EPS Growth (Past 5Y)", f"{format_value(eps_past, 2)}%") if eps_past else html.Div(),
            ], className='metrics-row cols-4'))
        if src:
            children.append(html.Div(src, style={'fontSize': '0.7rem', 'color': '#999', 'marginTop': '2px'}))

    # Sector P/E and ERP side by side
    spe_data = loader.get('74_sector_pe')
    erp_data = loader.get('82_erp')
    side_row = []

    if 'error' in spe_data:
        side_row.append(error_card("Sector P/E", spe_data['error']))
    else:
        sectors = spe_data.get('sectors', {})
        if sectors:
            rows = [html.Tr([html.Td(s, style={'padding': '2px 8px'}), html.Td(str(v), style={'padding': '2px 8px'})]) for s, v in sorted(sectors.items(), key=lambda x: -x[1])]
            side_row.append(html.Div([
                html.H4("Sector P/E Ratios", style={'fontSize': '0.9rem', 'marginBottom': '4px'}),
                html.Table([html.Thead(html.Tr([html.Th("Sector"), html.Th("P/E")])), html.Tbody(rows)],
                           style={'fontSize': '0.78rem', 'width': '100%'}),
            ], style={'flex': '1', 'padding': '8px'}))

    if 'error' in erp_data:
        side_row.append(error_card("Equity Risk Premium", erp_data['error']))
    else:
        erp_children = [
            html.H4("Equity Risk Premium", style={'fontSize': '0.9rem', 'marginBottom': '4px'}),
            metric_card("ERP (Trailing)", f"{format_value(erp_data.get('equity_risk_premium'))}%",
                         caption=f"Earnings Yield: {format_value(erp_data.get('earnings_yield'))}%"),
            metric_card("ERP (Forward)", f"{format_value(erp_data.get('forward_erp'))}%",
                         caption=f"Fwd PE: {format_value(erp_data.get('forward_pe'))} | 10Y Real Yield: {format_value(erp_data.get('real_yield_10y'))}%"),
        ]
        erp_exp = history_expander(erp_data, 'Equity Risk Premium (%)', '#1565c0', days=730)
        if erp_exp:
            erp_children.append(erp_exp)
        side_row.append(html.Div(erp_children, style={'flex': '1', 'padding': '8px'}))

    if side_row:
        children.append(html.Div(side_row, className='metrics-row cols-2'))

    return html.Div(children, className='tab-content')


def build_tab2(loader):
    """Market Indices."""
    children = [section_header("Market Indices")]

    # Futures
    children.append(section_subheader("Futures Indices"))
    es = loader.get('17_es_futures')
    rty = loader.get('18_rty_futures')
    row = []
    for data, label, vk, clr in [(es, "ES - S&P 500 E-mini", 'price', '#1565c0'),
                                   (rty, "RTY - Russell 2000", 'price', '#e65100')]:
        if 'error' in data:
            row.append(error_card(label, data['error']))
        else:
            card = metric_card(label, format_value(data.get(vk), 2),
                                    f"{format_value(data.get('change_1d', 0), 2)}%",
                                    f"As of: {to_gmt8_date(data.get('latest_date'))}", border_color=clr)
            exp = history_expander(data, label, clr, days=365)
            row.append(html.Div([card, exp]) if exp else card)
    children.append(html.Div(row, className='metrics-row cols-2'))

    # Breadth — with interpretation badge
    children.append(section_subheader("S&P 500 Market Breadth"))
    breadth = loader.get('19_sp500_breadth')
    if 'error' in breadth:
        children.append(error_card("Breadth", breadth['error']))
    else:
        children.append(html.Div([
            metric_card("Advancing", breadth.get('advancing_stocks', 'N/A')),
            metric_card("Declining", breadth.get('declining_stocks', 'N/A')),
            metric_card("Net Advances", breadth.get('net_advances', 'N/A')),
            metric_card("Breadth %", f"{format_value(breadth.get('breadth_percentage'), 1)}%"),
        ], className='metrics-row cols-4'))

        # Conditional interpretation badge
        interp = breadth.get('interpretation', '')
        if interp:
            if 'Strong bullish' in interp:
                children.append(info_badge(f"✅ {interp}", 'success'))
            elif 'Moderate bullish' in interp:
                children.append(info_badge(f"ℹ️ {interp}", 'info'))
            elif 'Moderate bearish' in interp:
                children.append(info_badge(f"⚠️ {interp}", 'warning'))
            else:
                children.append(info_badge(f"🔴 {interp}", 'error'))

        # A/D ratio + sample count
        extra = []
        ad_ratio = breadth.get('ad_ratio', 'N/A')
        if ad_ratio != 'N/A' and ad_ratio != float('inf'):
            extra.append(f"A/D Ratio: {format_value(ad_ratio, 2)}")
        total = breadth.get('total_stocks', 'N/A')
        if total != 'N/A':
            extra.append(f"Sample: {total} stocks")
        if extra:
            children.append(html.Div(' | '.join(extra),
                                      style={'fontSize': '0.75rem', 'color': '#888', 'marginBottom': '6px'}))

    # Russell 2000 V/G
    children.append(section_subheader("Russell 2000 Value vs Growth", SOURCE_URLS['russell_2000']))
    r2k = loader.get('2_russell_2000')
    if 'error' in r2k:
        children.append(error_card("Russell 2000", r2k['error']))
    else:
        val_d = r2k.get('russell_2000_value', {})
        gro_d = r2k.get('russell_2000_growth', {})
        children.append(html.Div([
            metric_card("R2K Value", format_value(val_d.get('latest_price'), 2),
                         f"{format_value(val_d.get('change_1d', 0), 2)}%"),
            metric_card("R2K Growth", format_value(gro_d.get('latest_price'), 2),
                         f"{format_value(gro_d.get('change_1d', 0), 2)}%"),
            metric_card("Value/Growth Ratio", format_value(r2k.get('value_growth_ratio'), 3)),
        ], className='metrics-row cols-3'))

    # S&P 500 / 200MA
    children.append(section_subheader("S&P 500 / 200-Day MA", SOURCE_URLS['sp500_ma200']))
    sp_ma = loader.get('6a_sp500_to_ma200')
    if 'error' in sp_ma:
        children.append(error_card("S&P 500 / 200MA", sp_ma['error']))
    else:
        ratio = sp_ma.get('sp500_to_ma200_ratio', 'N/A')
        signal = ''
        try:
            r = float(ratio)
            if r > 1.1:
                signal = '🔴 Overbought territory'
            elif r < 0.9:
                signal = '🟢 Oversold territory'
            else:
                signal = '🟡 Normal range'
        except (ValueError, TypeError):
            pass
        children.append(html.Div([
            metric_card("S&P 500 Price", format_value(sp_ma.get('sp500_price'), 2)),
            metric_card("200-Day MA", format_value(sp_ma.get('sp500_ma200'), 2)),
            metric_card("Price / MA200", format_value(ratio, 4), caption=signal),
        ], className='metrics-row cols-3'))

    # SPY/RSP concentration
    children.append(section_subheader("Market Concentration (SPY/RSP)"))
    conc = loader.get('55_market_concentration')
    if 'error' in conc:
        children.append(error_card("Concentration", conc['error']))
    else:
        children.append(html.Div([
            metric_card("SPY/RSP Ratio", format_value(conc.get('spy_rsp_ratio'), 4),
                         f"{format_value(conc.get('change_1d', 0), 2)}%",
                         f"As of: {to_gmt8_date(conc.get('latest_date'))}", '#7b1fa2'),
            metric_card("30-Day Change", f"{format_value(conc.get('change_30d', 0), 2)}%",
                         caption=conc.get('interpretation', ''), border_color='#7b1fa2'),
        ], className='metrics-row cols-2'))
        children.append(html.Div(
            "SPY (cap-weighted) vs RSP (equal-weight) — rising = increasing concentration",
            style={'fontSize': '0.72rem', 'color': '#888', 'marginBottom': '4px'}))
        exp = history_expander(conc, 'SPY/RSP Ratio', '#7b1fa2')
        if exp:
            children.append(exp)

    # ── OpenBB Market Indicators ────────────────────────────────────────
    children.append(section_header("Fama-French 5-Factor Returns"))
    ff = loader.get('69_fama_french')
    if 'error' in ff:
        children.append(error_card("Fama-French", ff['error']))
    else:
        children.append(html.Div([
            metric_card("Mkt-RF", f"{format_value(ff.get('mkt_rf'))}%"),
            metric_card("SMB", f"{format_value(ff.get('smb'))}%"),
            metric_card("HML", f"{format_value(ff.get('hml'))}%"),
            metric_card("RMW", f"{format_value(ff.get('rmw'))}%"),
            metric_card("CMA", f"{format_value(ff.get('cma'))}%"),
        ], className='metrics-row cols-5'))
        children.append(html.Div(
            f"Monthly factor returns | RF: {format_value(ff.get('rf'))}% | Source: {ff.get('source', 'N/A')}",
            style={'fontSize': '0.72rem', 'color': '#888'}))

    children.append(section_header("Upcoming Earnings Calendar"))
    earn = loader.get('73_earnings_calendar')
    if 'error' in earn:
        children.append(error_card("Earnings Calendar", earn['error']))
    else:
        earnings_list = earn.get('earnings', [])
        if earnings_list:
            rows = [html.Tr([html.Td(e.get('symbol', ''), style={'padding': '2px 6px', 'fontWeight': 'bold'}),
                             html.Td(e.get('date', ''), style={'padding': '2px 6px'})])
                    for e in earnings_list[:15]]
            children.append(html.Table([
                html.Thead(html.Tr([html.Th("Ticker"), html.Th("Date")])),
                html.Tbody(rows)
            ], style={'fontSize': '0.78rem', 'width': '100%', 'maxWidth': '400px'}))
        else:
            children.append(info_badge("No upcoming earnings in the next 7 days", 'info'))
        children.append(html.Div(
            f"Source: {earn.get('source', 'N/A')}",
            style={'fontSize': '0.72rem', 'color': '#888'}))

    return html.Div(children, className='tab-content')


def build_tab3(loader):
    """Volatility & Risk."""
    children = [section_header("Volatility & Risk Indicators")]

    # VIX, MOVE, VIX/MOVE — 3-column layout
    vix = loader.get('8_vix')
    move = loader.get('9_move_index')
    ratio = loader.get('8b_vix_move_ratio')

    row = []
    row.append(indicator_with_chart(vix, "VIX", 'vix', color='#e53935', days=730))
    row.append(indicator_with_chart(move, "MOVE Index", 'move', color='#ff9800', days=730))
    if 'error' in ratio:
        row.append(error_card("VIX/MOVE Ratio", ratio['error']))
    else:
        row.append(metric_card("VIX/MOVE Ratio", format_value(ratio.get('vix_move_ratio'), 3)))
    children.append(html.Div(row, className='metrics-row cols-3'))

    # Put/Call + SKEW — 2-column layout
    pc = loader.get('4_put_call_ratio')
    skew = loader.get('5_spx_call_skew')
    row2 = []

    # Put/Call with info note
    if 'error' in pc:
        pc_card = error_card("S&P 500 Put/Call Ratio", pc['error'])
        if 'note' in pc:
            pc_card = html.Div([pc_card, info_badge(f"ℹ️ {pc['note']}", 'info')])
        row2.append(pc_card)
    else:
        row2.append(indicator_with_chart(pc, "S&P 500 Put/Call Ratio", 'sp500_put_call_ratio',
                                          value_fmt=3, color='#7b1fa2', days=730))

    # SKEW with interpretation bullets
    if 'error' in skew:
        row2.append(error_card("CBOE SKEW", skew['error']))
    else:
        skew_card = indicator_with_chart(skew, "CBOE SKEW", 'spx_call_skew', color='#1565c0', days=730)
        interp = skew.get('interpretation')
        if interp and isinstance(interp, dict):
            bullets = [html.Li(f"{k}: {v}", style={'fontSize': '0.75rem'})
                       for k, v in interp.items()]
            skew_card = html.Div([
                skew_card,
                html.Div([
                    html.Strong("Interpretation:", style={'fontSize': '0.78rem'}),
                    html.Ul(bullets, style={'margin': '2px 0', 'paddingLeft': '16px'}),
                ], style={'fontSize': '0.75rem', 'color': '#555'}),
            ])
        row2.append(skew_card)
    children.append(html.Div(row2, className='metrics-row cols-2'))

    # ── OpenBB Volatility Indicators ────────────────────────────────────
    children.append(section_header("VIX Futures & Options Analytics"))
    vfc = loader.get('63_vix_futures_curve')
    pcoi = loader.get('64_spy_put_call_oi')
    ivs = loader.get('70_iv_skew')

    vol_row = []
    # VIX Futures
    if 'error' in vfc:
        vol_row.append(error_card("VIX Futures Curve", vfc['error']))
    else:
        contango = vfc.get('contango_pct')
        cap = f"Contango: {format_value(contango)}%" if contango is not None else f"Source: {vfc.get('source', 'N/A')}"
        vol_row.append(metric_card("VIX Spot", format_value(vfc.get('vix_spot'), 2), caption=cap, border_color='#d32f2f'))

    # SPY Put/Call OI
    if 'error' in pcoi:
        vol_row.append(error_card("SPY Put/Call", pcoi['error']))
    else:
        vol_ratio = pcoi.get('put_call_volume_ratio')
        oi_ratio = pcoi.get('put_call_oi_ratio')
        sub = f"OI Ratio: {format_value(oi_ratio, 3)}" if oi_ratio else pcoi.get('source', '')
        vol_row.append(metric_card("P/C Vol Ratio", format_value(vol_ratio, 3), sub, border_color='#7b1fa2'))

    # IV Skew
    if 'error' in ivs:
        vol_row.append(error_card("SPX IV Skew", ivs['error']))
    else:
        skew_25d = ivs.get('iv_skew_25d')
        skew_idx = ivs.get('skew_index')
        if skew_25d is not None:
            vol_row.append(metric_card("25Δ IV Skew", f"{format_value(skew_25d)}%",
                                        caption=f"Put IV: {ivs.get('otm_put_iv')}% | Call IV: {ivs.get('otm_call_iv')}%",
                                        border_color='#1565c0'))
        elif skew_idx is not None:
            vol_row.append(metric_card("SKEW Index", format_value(skew_idx, 2), border_color='#1565c0'))

    children.append(html.Div(vol_row, className='metrics-row cols-3'))

    return html.Div(children, className='tab-content')


def build_tab4(loader):
    """Macro & Currency."""
    children = [section_header("Macro & Currency")]

    # FX row: DXY, USD/JPY, EUR/USD, GBP/USD, EUR/JPY — 5 columns
    children.append(section_subheader("Currency Indices"))
    dxy = loader.get('10_dxy')
    jpy = loader.get('20_jpy')
    fx = loader.get('54_fx_pairs')

    fx_row = []
    # DXY
    if 'error' in dxy:
        fx_row.append(error_card("DXY", dxy['error']))
    else:
        fx_row.append(indicator_with_chart(dxy, "DXY", 'dxy', color='#2e7d32', border_color='#2e7d32', days=730))
    # USD/JPY
    if 'error' in jpy:
        fx_row.append(error_card("USD/JPY", jpy['error']))
    else:
        fx_row.append(indicator_with_chart(jpy, "USD/JPY", 'jpy_rate', color='#d84315', border_color='#d84315', days=730))

    # EUR/USD, GBP/USD, EUR/JPY with history expanders
    if 'error' not in fx:
        for pair, vk, chg_key, color, hist_key in [
            ("EUR/USD", 'eur_usd', 'eur_usd_change_1d', '#1565c0', 'historical_eur_usd'),
            ("GBP/USD", 'gbp_usd', 'gbp_usd_change_1d', '#1b5e20', 'historical_gbp_usd'),
            ("EUR/JPY", 'eur_jpy', 'eur_jpy_change_1d', '#e65100', 'historical_eur_jpy'),
        ]:
            card = metric_card(pair, format_value(fx.get(vk), 4),
                                f"{format_value(fx.get(chg_key, 0), 2)}%",
                                border_color=color)
            exp = history_expander(fx, pair, color, hist_key, days=730)
            if exp:
                fx_row.append(html.Div([card, exp]))
            else:
                fx_row.append(card)
    children.append(html.Div(fx_row, className='metrics-row cols-5'))

    # Liquidity & Rates
    children.append(section_subheader("Liquidity & Short-Term Rates"))
    tga = loader.get('23_tga_balance')
    net_liq = loader.get('24_net_liquidity')

    liq_row = []
    if 'error' in tga:
        liq_row.append(error_card("TGA Balance", tga['error']))
    else:
        tga_card = metric_card("TGA Balance ($B)", format_value(tga.get('tga_balance_billions'), 1),
                                f"{format_value(tga.get('change_wow_pct', 0), 1)}% WoW",
                                f"As of: {to_gmt8_date(tga.get('latest_date'))}", '#6a1b9a')
        exp = history_expander(tga, 'TGA Balance ($M)', '#6a1b9a', days=730)
        liq_row.append(html.Div([tga_card, exp]) if exp else tga_card)

    if 'error' in net_liq:
        liq_row.append(error_card("Net Liquidity", net_liq['error']))
    else:
        nl_card = metric_card("Net Liquidity ($T)", format_value(net_liq.get('net_liquidity_trillions'), 3),
                               f"{format_value(net_liq.get('change_pct', 0), 2)}%",
                               f"As of: {to_gmt8_date(net_liq.get('latest_date'))}", '#1565c0')
        exp = history_expander(net_liq, 'Net Liquidity ($M)', '#1565c0', days=730)
        liq_row.append(html.Div([nl_card, exp]) if exp else nl_card)
    children.append(html.Div(liq_row, className='metrics-row cols-2'))

    # M2
    m2 = loader.get('47_m2')
    if 'error' in m2:
        children.append(error_card("M2 Money Supply", m2['error']))
    else:
        m2_card = metric_card("M2 ($T)", format_value(m2.get('m2_trillions'), 2),
                               f"{format_value(m2.get('m2_yoy_growth', 0), 1)}% YoY",
                               f"As of: {to_gmt8_date(m2.get('latest_date'))}", '#00695c')
        exp = history_expander(m2, 'M2 ($T)', '#00695c', days=730)
        children.append(html.Div([m2_card, exp]) if exp else m2_card)

    # SOFR + 2Y Yield
    sofr = loader.get('25_sofr')
    us2y = loader.get('26_us_2y_yield')
    rates_row = []
    if 'error' in sofr:
        rates_row.append(error_card("SOFR", sofr['error']))
    else:
        s_card = metric_card("SOFR Rate (%)", format_value(sofr.get('sofr'), 4),
                              f"{format_value(sofr.get('change_1d', 0), 4)} bps",
                              f"As of: {to_gmt8_date(sofr.get('latest_date'))}", '#00838f')
        exp = history_expander(sofr, 'SOFR (%)', '#00838f', days=730)
        rates_row.append(html.Div([s_card, exp]) if exp else s_card)

    if 'error' in us2y:
        rates_row.append(error_card("US 2Y Yield", us2y['error']))
    else:
        cap_parts = [f"As of: {to_gmt8_date(us2y.get('latest_date'))}"]
        if 'spread_2s10s' in us2y:
            sp = us2y['spread_2s10s']
            clr = "🔴" if sp < 0 else "🟢"
            cap_parts.append(f"{clr} 2s10s: {sp:.2f}%{'(inv)' if sp < 0 else ''}")
        us2y_card = metric_card("2Y Yield (%)", format_value(us2y.get('us_2y_yield'), 3),
                                 f"{format_value(us2y.get('change_1d', 0), 4)}",
                                 ' | '.join(cap_parts), '#1976d2')
        exp = history_expander(us2y, 'US 2Y Yield (%)', '#1976d2', days=730)
        rates_row.append(html.Div([us2y_card, exp]) if exp else us2y_card)
    children.append(html.Div(rates_row, className='metrics-row cols-2'))

    # Japan 2Y + Spread
    jp2y = loader.get('27_japan_2y_yield')
    spread = loader.get('28_us2y_jp2y_spread')
    jp_row = []
    if 'error' in jp2y:
        jp_row.append(error_card("Japan 2Y Yield", jp2y['error']))
    else:
        cap = f"As of: {to_gmt8_date(jp2y.get('latest_date'))}"
        if 'japan_10y_yield' in jp2y:
            cap += f" | JGB 10Y: {jp2y['japan_10y_yield']}%"
        jp_card = metric_card("JGB 2Y Yield (%)", format_value(jp2y.get('japan_2y_yield'), 3),
                               f"{format_value(jp2y.get('change_1d', 0), 4)}", cap, '#e65100')
        exp = history_expander(jp2y, 'JGB 2Y Yield (%)', '#e65100', days=730)
        jp_row.append(html.Div([jp_card, exp]) if exp else jp_card)

    if 'error' in spread:
        jp_row.append(error_card("US-JP 2Y Spread", spread['error']))
    else:
        sp_card = metric_card("US-JP 2Y Spread (%)", format_value(spread.get('spread'), 3),
                               caption=spread.get('interpretation', ''), border_color='#ff7f0e')
        exp = history_expander(spread, 'US-JP 2Y Spread (%)', '#ff7f0e', days=730)
        jp_row.append(html.Div([sp_card, exp]) if exp else sp_card)
    children.append(html.Div(jp_row, className='metrics-row cols-2'))

    # US-JP Spread standalone chart with zero line
    if 'error' not in spread and 'historical' in spread:
        hist_spread = spread['historical']
        if hist_spread is not None and len(hist_spread) > 0:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=hist_spread.index, y=hist_spread.values,
                name='US 2Y - JP 2Y Spread', line=dict(color='#ff7f0e'),
                fill='tozeroy', fillcolor='rgba(255,127,14,0.1)'
            ))
            fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
            fig.update_layout(
                title="US 2Y - Japan 2Y Yield Spread (Carry Trade Indicator)",
                xaxis_title="Date", yaxis_title="Spread (pp)",
                hovermode='x unified', height=400,
            )
            children.append(html.Details([
                html.Summary("US-JP 2Y Yield Spread Chart", style={
                    'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
                dcc.Graph(figure=fig, config={'displayModeBar': False}),
            ]))

    # Net Liquidity standalone chart (365-day)
    if 'error' not in net_liq and 'historical' in net_liq:
        try:
            hist_t = net_liq['historical'] / 1_000_000
            fig = make_history_chart(hist_t, 'Net Liquidity ($T)', '#1f77b4', days=365)
            if fig:
                fig.update_layout(title="Fed Net Liquidity (Fed Assets - TGA - ON RRP)")
                children.append(html.Details([
                    html.Summary("Net Liquidity Chart", style={
                        'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
                    dcc.Graph(figure=fig, config={'displayModeBar': False}),
                ]))
        except Exception:
            pass

    # 10Y Yield vs ISM PMI
    children.append(section_subheader("10Y Yield & ISM Manufacturing PMI"))
    y10 = loader.get('11_10y_yield')
    ism = loader.get('12_ism_pmi')

    if 'error' in y10 or 'error' in ism:
        if 'error' in y10:
            children.append(error_card("10Y Yield", y10['error']))
        if 'error' in ism:
            children.append(error_card("ISM PMI", ism['error']))
    else:
        macro_row = []
        # 10Y with expander
        y10_card = metric_card("10Y Treasury Yield", f"{format_value(y10.get('10y_yield'), 2)}%",
                                caption=f"As of: {to_gmt8_date(y10.get('latest_date'))}", border_color='#1565c0')
        exp_y10 = history_expander(y10, '10Y Yield (%)', '#1565c0', days=730)
        macro_row.append(html.Div([y10_card, exp_y10]) if exp_y10 else y10_card)

        # ISM with expander
        ism_card = metric_card("ISM Manufacturing PMI", format_value(ism.get('ism_pmi'), 1),
                                caption=f"As of: {to_gmt8_date(ism.get('latest_date'))}", border_color='#e65100')
        exp_ism = history_expander(ism, 'ISM PMI', '#e65100', days=730)
        macro_row.append(html.Div([ism_card, exp_ism]) if exp_ism else ism_card)

        # Computed: 10Y-ISM Gap
        yield_val = y10.get('10y_yield')
        ism_val = ism.get('ism_pmi')
        if isinstance(yield_val, (int, float)) and isinstance(ism_val, (int, float)):
            gap = yield_val - ism_val
            gap_cap = "🔴 Yield > ISM (potential slowdown)" if gap > 0 else "🟢 ISM > Yield (economic strength)"
            macro_row.append(metric_card("10Y Yield - ISM Gap", format_value(gap, 2), caption=gap_cap))

        children.append(html.Div(macro_row, className=f'metrics-row cols-{len(macro_row)}'))

        # 10Y vs ISM dual-axis chart
        if 'historical' in y10 and 'historical' in ism:
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(
                go.Scatter(x=y10['historical'].index, y=y10['historical'].values,
                           name="10Y Treasury Yield", line=dict(color='blue')),
                secondary_y=False,
            )
            fig.add_trace(
                go.Scatter(x=ism['historical'].index, y=ism['historical'].values,
                           name="ISM Manufacturing PMI", line=dict(color='orange')),
                secondary_y=True,
            )
            fig.update_layout(
                title_text="10-Year Treasury Yield vs ISM Manufacturing PMI",
                hovermode='x unified', height=450,
            )
            fig.update_yaxes(title_text="10Y Yield (%)", secondary_y=False)
            fig.update_yaxes(title_text="ISM PMI", secondary_y=True)
            children.append(html.Details([
                html.Summary("10Y Yield vs ISM PMI Chart", style={
                    'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
                dcc.Graph(figure=fig, config={'displayModeBar': False}),
            ]))

    # ── OpenBB Money Supply ─────────────────────────────────────────────
    children.append(section_header("Money Supply (M1/M2)"))
    mm = loader.get('80_money_measures')
    if 'error' in mm:
        children.append(error_card("Money Measures", mm['error']))
    else:
        children.append(html.Div([
            metric_card("M1 Level (B)", format_value(mm.get('m1_level'), 0)),
            metric_card("M1 YoY%", f"{format_value(mm.get('m1_yoy'))}%"),
            metric_card("M2 Level (B)", format_value(mm.get('m2_level'), 0)),
            metric_card("M2 YoY%", f"{format_value(mm.get('m2_yoy'))}%"),
        ], className='metrics-row cols-4'))
        children.append(html.Div(
            f"As of: {to_gmt8_date(mm.get('latest_date'))} | Source: {mm.get('source', 'N/A')}",
            style={'fontSize': '0.72rem', 'color': '#888'}))
        # M2 historical chart
        mm_exp = history_expander(mm, 'M2 Money Supply (B$)', '#00695c', days=730)
        if mm_exp:
            children.append(mm_exp)

    return html.Div(children, className='tab-content')


def build_tab5(loader):
    """Commodities."""
    children = [section_header("Commodities Futures")]

    commodities = [
        ('13_gold', "Gold (GC)", 'price', '#FFD700'),
        ('14_silver', "Silver (SI)", 'price', '#C0C0C0'),
        ('15_crude_oil', "Crude Oil (CL)", 'price', '#2c2c2c'),
        ('16_copper', "Copper (HG)", 'price', '#B87333'),
        ('56_natural_gas', "Natural Gas (NG)", 'price', '#4a148c'),
    ]

    row = []
    for key, label, vk, color in commodities:
        data = loader.get(key)
        row.append(indicator_with_chart(data, label, vk, color=color, border_color=color, days=730))

    # Cu/Au ratio
    cu_au = loader.get('57_cu_au_ratio')
    if 'error' in cu_au:
        row.append(error_card("Cu/Au Ratio", cu_au['error']))
    else:
        cu_card = metric_card("Cu/Au Ratio (x1000)", format_value(cu_au.get('cu_au_ratio'), 4),
                               f"{format_value(cu_au.get('change_1d', 0), 2)}%",
                               cu_au.get('interpretation', ''), '#ef6c00')
        exp = history_expander(cu_au, 'Cu/Au Ratio x1000', '#ef6c00', days=730)
        row.append(html.Div([cu_card, exp]) if exp else cu_card)

    children.append(html.Div(row[:2], className='metrics-row cols-2'))
    children.append(html.Div(row[2:4], className='metrics-row cols-2'))
    children.append(html.Div(row[4:], className='metrics-row cols-2'))

    # COT Positioning
    children.append(section_header("CFTC COT Positioning — Gold & Silver"))
    children.append(html.Div(
        "Weekly positioning data from CFTC. Managed money = hedge funds. Commercial = producers/hedgers.",
        style={'fontSize': '0.75rem', 'color': '#888', 'marginBottom': '6px'}))

    cot = loader.get('22_cot_positioning')
    if 'error' in cot:
        children.append(error_card("COT Data", cot['error']))
    else:
        children.append(html.Div(
            f"As of: {to_gmt8_date(cot.get('latest_date'))}",
            style={'fontSize': '0.75rem', 'color': '#888', 'marginBottom': '4px'}))

        for metal, metal_name in [('gold', 'Gold'), ('silver', 'Silver')]:
            m = cot.get(metal, {})
            if 'error' in m:
                children.append(error_card(f"{metal_name} COT", m['error']))
                continue
            items = []
            oi = m.get('open_interest')
            if oi:
                items.append(metric_card("Open Interest", f"{oi:,}" if isinstance(oi, int) else str(oi)))
            mm_net = m.get('managed_money_net') or m.get('noncommercial_net')
            if mm_net is not None:
                items.append(metric_card("Speculator Net", f"{mm_net:,}"))
            comm = m.get('commercial_net')
            if comm is not None:
                items.append(metric_card("Commercial Net", f"{comm:,}"))
            # OI change
            oi_chg = m.get('oi_change')
            if oi_chg is not None:
                oi_pct = m.get('oi_change_pct')
                delta_str = f"{oi_pct:+.1f}%" if oi_pct is not None else ""
                items.append(metric_card("OI Change (1w)", f"{oi_chg:,}", delta_str))
            if items:
                children.append(section_subheader(f"{metal_name} Positioning"))
                children.append(html.Div(items, className=f'metrics-row cols-{min(len(items), 4)}'))

        # COT chart: gold vs silver managed money net positioning
        gold_cot = cot.get('gold', {})
        silver_cot = cot.get('silver', {})
        gold_hist = gold_cot.get('historical') if isinstance(gold_cot, dict) else None
        silver_hist = silver_cot.get('historical') if isinstance(silver_cot, dict) else None

        if gold_hist is not None or silver_hist is not None:
            hist_label = gold_cot.get('historical_label', 'Net Positioning') if isinstance(gold_cot, dict) else 'Net Positioning'
            fig = go.Figure()
            if gold_hist is not None and hasattr(gold_hist, 'index'):
                fig.add_trace(go.Scatter(
                    x=gold_hist.index, y=gold_hist.values,
                    name=f"Gold {hist_label}", line=dict(color='gold', width=2)))
            if silver_hist is not None and hasattr(silver_hist, 'index'):
                fig.add_trace(go.Scatter(
                    x=silver_hist.index, y=silver_hist.values,
                    name=f"Silver {hist_label}", line=dict(color='silver', width=2)))
            fig.update_layout(
                title=f"CFTC COT: {hist_label} (Gold vs Silver)",
                xaxis_title="Date", yaxis_title="Contracts",
                hovermode='x unified', height=420,
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            children.append(html.Details([
                html.Summary("COT Positioning Chart", style={
                    'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
                dcc.Graph(figure=fig, config={'displayModeBar': False}),
            ]))

    return html.Div(children, className='tab-content')


def _fetch_on_demand(ticker, source='yahoo'):
    """Fetch financials on-demand for a ticker not in the cache."""
    if source == 'sec':
        if get_company_financials_sec is None:
            return {'error': 'SEC extractor not available'}
        try:
            return get_company_financials_sec(ticker)
        except Exception as e:
            return {'error': str(e)}
    else:
        if get_company_financials_yahoo is None:
            return {'error': 'Yahoo extractor not available'}
        try:
            return get_company_financials_yahoo(ticker)
        except Exception as e:
            return {'error': str(e)}


def build_tab6(loader, selected_ticker='AAPL', source='yahoo'):
    """Large-cap Financials — full port with expanded tables, analysis, segments."""
    source_label = 'SEC EDGAR' if source == 'sec' else 'Yahoo Finance'
    children = [section_header(f"Large-cap Financials — {source_label}")]

    # Determine company data: cache first, then on-demand fetch
    co = None
    is_custom = False

    eq_data = loader.get('29_equity_financials')
    companies = eq_data.get('companies', {}) if 'error' not in eq_data else {}

    if source == 'yahoo' and selected_ticker in companies and 'error' not in companies.get(selected_ticker, {}):
        co = companies[selected_ticker]
    else:
        is_custom = True
        result = _fetch_on_demand(selected_ticker, source)
        if 'error' in result:
            children.append(error_card(f"{selected_ticker} ({source_label})", result['error']))
            if source == 'sec' and 'IFRS' in str(result.get('error', '')):
                children.append(html.Div(
                    "Note: TSM and some foreign filers use IFRS, not US-GAAP. Try Yahoo Finance source.",
                    style={'fontSize': '0.78rem', 'color': '#888', 'marginTop': '4px'}))
            return html.Div(children, className='tab-content')
        co = result

    if not co or 'error' in co:
        children.append(error_card(selected_ticker, co.get('error', 'No data') if co else 'No data'))
        return html.Div(children, className='tab-content')

    # Company header
    children.append(html.Div([
        metric_card("Market Cap", fmt_dollar(co.get('market_cap'))),
        metric_card("Sector", co.get('sector', 'N/A')),
        metric_card("Industry", co.get('industry', 'N/A')),
    ], className='metrics-row cols-3'))

    quarters = co.get('quarters', [])
    if not quarters:
        children.append(html.Div("No quarterly data."))
        return html.Div(children, className='tab-content')

    children.append(html.Div(
        f"Source: {source_label}{' (on-demand)' if is_custom else ' (cached)'} | "
        f"Ticker: {selected_ticker} | Quarters: {', '.join(quarters)}",
        style={'fontSize': '0.75rem', 'color': '#888', 'marginBottom': '8px'}))

    # ── 1. Income Statement ────────────────────────────────────────────
    inc = co.get('income_statement')
    if inc:
        children.append(section_subheader("1. Income Statement (Quarterly)"))
        inc_metrics = [
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
        table = build_table_html(inc, inc_metrics, quarters)
        if table:
            children.append(html.Div(dcc.Markdown(table, dangerously_allow_html=True)))

    # ── 2. Balance Sheet ──────────────────────────────────────────────
    bs = co.get('balance_sheet')
    if bs:
        children.append(section_subheader("2. Balance Sheet (Quarterly)"))

        # Assets sub-table
        children.append(html.Div("Assets", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        bs_assets = [
            ('Total Assets', 'total_assets', '$'),
            ('&nbsp;&nbsp;Current Assets', 'current_assets', '$'),
            ('&nbsp;&nbsp;&nbsp;&nbsp;Cash & ST Inv.', 'cash_and_short_term_investments', '$'),
            ('&nbsp;&nbsp;&nbsp;&nbsp;Accts Receivable', 'accounts_receivable', '$'),
            ('&nbsp;&nbsp;&nbsp;&nbsp;Inventory', 'inventory', '$'),
            ('&nbsp;&nbsp;Non-Current Assets', 'total_non_current_assets', '$'),
            ('&nbsp;&nbsp;&nbsp;&nbsp;Goodwill', 'goodwill', '$'),
            ('&nbsp;&nbsp;&nbsp;&nbsp;Net PP&E', 'net_ppe', '$'),
        ]
        table = build_table_html(bs, bs_assets, quarters)
        if table:
            children.append(html.Div(dcc.Markdown(table, dangerously_allow_html=True)))

        # Liabilities sub-table
        children.append(html.Div("Liabilities", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        bs_liab = [
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
        table = build_table_html(bs, bs_liab, quarters)
        if table:
            children.append(html.Div(dcc.Markdown(table, dangerously_allow_html=True)))

        # Equity & Ratios sub-table
        children.append(html.Div("Equity & Ratios", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        bs_eq = [
            ("Stockholders' Equity", 'stockholders_equity', '$'),
            ('Retained Earnings', 'retained_earnings', '$'),
            ('Invested Capital', 'invested_capital', '$'),
            ('Debt Ratio (Liab/Assets)', 'debt_ratio', '%'),
            ('Debt/Equity', 'debt_to_equity', '%'),
            ('Current Ratio', 'current_ratio', '%'),
        ]
        table = build_table_html(bs, bs_eq, quarters)
        if table:
            children.append(html.Div(dcc.Markdown(table, dangerously_allow_html=True)))

    # ── 3. Cash Flow ──────────────────────────────────────────────────
    cf = co.get('cash_flow')
    if cf:
        children.append(section_subheader("3. Cash Flow (Quarterly)"))
        cf_metrics = [
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
        table = build_table_html(cf, cf_metrics, quarters)
        if table:
            children.append(html.Div(dcc.Markdown(table, dangerously_allow_html=True)))

    # ── 4. Financial Analysis ─────────────────────────────────────────
    fa = co.get('financial_analysis', {})
    _inc = co.get('income_statement', {})
    _bs = co.get('balance_sheet', {})
    _cf = co.get('cash_flow', {})

    def _q0(d, key):
        vals = d.get(key, [])
        return vals[0] if vals else None

    children.append(section_subheader("4. Financial Analysis"))

    # Profitability with numerator/denominator
    prof = fa.get('profitability', {})
    if prof:
        children.append(html.Div("Profitability", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        _rev0 = _q0(_inc, 'total_revenue')
        prof_cards = [
            metric_card_with_components("Gross Margin", fmt_pct(prof.get('gross_margin')),
                                         _metric_components("Gross Profit", _q0(_inc, 'gross_profit'), "Revenue", _rev0)),
            metric_card_with_components("Op. Margin", fmt_pct(prof.get('operating_margin')),
                                         _metric_components("Op. Income", _q0(_inc, 'operating_income'), "Revenue", _rev0)),
            metric_card_with_components("EBITDA Margin", fmt_pct(prof.get('ebitda_margin')),
                                         _metric_components("EBITDA", _q0(_inc, 'ebitda'), "Revenue", _rev0)),
            metric_card_with_components("FCF Margin", fmt_pct(prof.get('fcf_margin')),
                                         _metric_components("FCF", _q0(_cf, 'free_cash_flow'), "Revenue", _rev0)),
            metric_card_with_components("Net Margin", fmt_pct(prof.get('net_margin')),
                                         _metric_components("Net Income", _q0(_inc, 'net_income'), "Revenue", _rev0)),
        ]
        children.append(html.Div(prof_cards, className='metrics-row cols-5'))

    # Turnover & Leverage
    turnover = fa.get('turnover', {})
    if turnover:
        children.append(html.Div("Turnover & Leverage", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        turn_cards = [
            metric_card_with_components("Debt/Equity", _fmt_ratio(turnover.get('debt_to_equity')),
                                         _metric_components("Total Debt", _q0(_bs, 'total_debt'), "Equity", _q0(_bs, 'stockholders_equity'))),
            metric_card_with_components("Current Ratio", _fmt_ratio(turnover.get('current_ratio')),
                                         _metric_components("Curr. Assets", _q0(_bs, 'current_assets'), "Curr. Liab.", _q0(_bs, 'current_liabilities'))),
            metric_card_with_components("Asset Turnover", _fmt_ratio(turnover.get('asset_turnover'), 4),
                                         _metric_components("Revenue", _rev0, "Total Assets", _q0(_bs, 'total_assets'), annualized=True)),
        ]
        children.append(html.Div(turn_cards, className='metrics-row cols-3'))

    # Growth
    gr = fa.get('growth', {})
    if gr:
        children.append(html.Div("Growth", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        gr_cards = [
            metric_card("EPS Growth", _fmt_pct_plus(gr.get('eps_growth'))),
            metric_card("Revenue Growth", _fmt_pct_plus(gr.get('revenue_growth'))),
            metric_card("Revenue QoQ", _fmt_pct_plus(gr.get('revenue_qoq'))),
            metric_card("Earnings QoQ", _fmt_pct_plus(gr.get('earnings_quarterly_growth'))),
        ]
        children.append(html.Div(gr_cards, className='metrics-row cols-4'))

    # Returns with numerator/denominator
    returns = fa.get('returns', {})
    if returns:
        children.append(html.Div("Returns", style={'fontWeight': '600', 'fontSize': '0.82rem', 'marginTop': '6px'}))
        _ni0 = _q0(_inc, 'net_income')
        _oi0 = _q0(_inc, 'operating_income')
        _tp0 = _q0(_inc, 'tax_provision')
        _pt0 = _q0(_inc, 'pretax_income')
        _nopat = None
        if _oi0:
            _tr = 0.21
            if _tp0 and _pt0 and _pt0 != 0:
                _tr = max(0, min(1, _tp0 / _pt0))
            _nopat = _oi0 * (1 - _tr)

        ret_cards = [
            metric_card_with_components("ROE", fmt_pct(returns.get('roe')),
                                         _metric_components("Net Income", _ni0, "Equity", _q0(_bs, 'stockholders_equity'), annualized=True)),
            metric_card_with_components("ROA", fmt_pct(returns.get('roa')),
                                         _metric_components("Net Income", _ni0, "Total Assets", _q0(_bs, 'total_assets'), annualized=True)),
            metric_card_with_components("ROIC", fmt_pct(returns.get('roic')),
                                         _metric_components("NOPAT", _nopat, "Invested Cap.", _q0(_bs, 'invested_capital'), annualized=True)),
        ]
        children.append(html.Div(ret_cards, className='metrics-row cols-3'))

    # ── 5. Valuation ──────────────────────────────────────────────────
    val = co.get('valuation', {})
    if val:
        children.append(section_subheader("5. Valuation"))

        price_src = val.get('_price_source')
        if price_src and source == 'sec':
            children.append(html.Div(
                f"Price data from {price_src} | {val.get('_note', '')}",
                style={'fontSize': '0.75rem', 'color': '#888', 'marginBottom': '4px'}))

        _price = val.get('current_price') or val.get('price')
        _ev = val.get('enterprise_value')
        _ttm_eps = val.get('diluted_eps_ttm')
        _bvps = val.get('book_value_per_share')
        _mktcap = co.get('market_cap') or val.get('market_cap')

        # Row 1: Forward P/E, Trailing P/E, PEG, P/B
        vr1 = [
            metric_card_with_components("Forward P/E", _fmt_ratio(val.get('forward_pe')),
                                         _val_components("Price", _price, "Fwd EPS", val.get('forward_eps'), d_fmt='eps')),
            metric_card_with_components("Trailing P/E (12M)", _fmt_ratio(val.get('trailing_pe')),
                                         _val_components("Price", _price, "TTM EPS", _ttm_eps, d_fmt='eps')),
            metric_card_with_components("PEG Ratio", _fmt_ratio(val.get('peg_ratio')),
                                         _val_components("P/E", val.get('trailing_pe'), "EPS Growth",
                                                         fa.get('growth', {}).get('eps_growth'), n_fmt='ratio', d_fmt='pct')),
            metric_card_with_components("Price / Book", _fmt_ratio(val.get('price_to_book')),
                                         _val_components("Price", _price, "Book/Share", _bvps, d_fmt='eps')),
        ]
        children.append(html.Div(vr1, className='metrics-row cols-4'))

        # Row 2: P/S, EV/EBITDA, EV/FCF, Enterprise Value
        _td = _q0(_bs, 'total_debt')
        _cash = _q0(_bs, 'cash_and_short_term_investments')
        ev_html = f'<span style="color:#888;font-size:0.72em">Mkt Cap + Debt − Cash<br/>{fmt_dollar(_mktcap)} + {fmt_dollar(_td)} − {fmt_dollar(_cash)}</span>'
        vr2 = [
            metric_card_with_components("Price / Sales", _fmt_ratio(val.get('price_to_sales')),
                                         _val_components("Mkt Cap", _mktcap, "TTM Revenue", val.get('ttm_revenue'))),
            metric_card_with_components("EV / EBITDA", _fmt_ratio(val.get('ev_to_ebitda')),
                                         _val_components("EV", _ev, "TTM EBITDA", val.get('ttm_ebitda'))),
            metric_card_with_components("EV / FCF", _fmt_ratio(val.get('ev_to_fcf')),
                                         _val_components("EV", _ev, "TTM FCF", val.get('ttm_fcf'))),
            metric_card_with_components("Enterprise Value", fmt_dollar(_ev), ev_html),
        ]
        children.append(html.Div(vr2, className='metrics-row cols-4'))

        # Row 3: Beta, Dividend Yield, TTM EPS, Book Value/Share
        vr3 = [
            metric_card("Beta", _fmt_ratio(val.get('beta'))),
            metric_card("Dividend Yield", fmt_pct(val.get('dividend_yield'))),
            metric_card("TTM EPS", f"${val['diluted_eps_ttm']:.2f}" if val.get('diluted_eps_ttm') else "N/A"),
            metric_card("Book Value/Share", f"${val['book_value_per_share']:.2f}" if val.get('book_value_per_share') else "N/A"),
        ]
        children.append(html.Div(vr3, className='metrics-row cols-4'))

    # ── 6. Revenue Segments ───────────────────────────────────────────
    segments = co.get('revenue_segments')
    if segments and isinstance(segments, dict):
        children.append(section_subheader("6. Revenue Segment Breakdown"))
        has_structured = any(k in segments for k in ('product_segments', 'business_segments', 'geographic_segments'))
        if has_structured:
            seg_period = segments.get('_period', '')
            seg_source = segments.get('_source', '')
            if seg_period or seg_source:
                children.append(html.Div(
                    f"Period ending: {seg_period} | Source: {seg_source}",
                    style={'fontSize': '0.75rem', 'color': '#888', 'marginBottom': '4px'}))

            for seg_key, seg_label in [
                ('product_segments', 'Product / Service'),
                ('business_segments', 'Business Segments'),
                ('geographic_segments', 'Geographic'),
            ]:
                seg_data = segments.get(seg_key)
                if not seg_data or not isinstance(seg_data, dict):
                    continue
                children.append(html.Div(seg_label, style={
                    'fontSize': '0.78rem', 'fontWeight': '600', 'color': '#555',
                    'marginTop': '6px', 'marginBottom': '2px'}))
                cards = [metric_card(name, fmt_dollar(value), border_color='#5c6bc0')
                         for name, value in sorted(seg_data.items(), key=lambda x: -(x[1] or 0))]
                if cards:
                    children.append(html.Div(cards, className=f'metrics-row cols-{min(len(cards), 4)}'))
        else:
            # Flat dict format
            cards = [metric_card(k, fmt_dollar(v), border_color='#5c6bc0')
                     for k, v in segments.items() if not k.startswith('_')]
            if cards:
                children.append(html.Div(cards, className=f'metrics-row cols-{min(len(cards), 4)}'))
    elif co.get('revenue_segments_note'):
        children.append(html.Div(
            co['revenue_segments_note'],
            style={'fontSize': '0.75rem', 'color': '#888', 'marginTop': '4px'}))

    return html.Div(children, className='tab-content')


def build_tab7(loader):
    """Rates & Credit."""
    children = [section_header("Rates & Credit")]

    # Yield Curve & Regime
    children.append(section_subheader("Yield Curve & Regime"))
    yc = loader.get('33_yield_curve')
    if 'error' in yc:
        children.append(error_card("Yield Curve", yc['error']))
    else:
        spread_val = yc.get('spread_2s10s', 0)
        inverted = yc.get('is_inverted', False)
        regime = yc.get('regime', 'Neutral')
        emoji = yc.get('regime_emoji', '')
        color = yc.get('regime_color', '#9e9e9e')
        signal = yc.get('regime_signal', '')
        detail = yc.get('regime_detail', '')
        lookback = yc.get('lookback_days', 20)

        inv_label = " | INVERTED" if inverted else ""
        yc_card = metric_card("2s10s Spread", f"{format_value(spread_val, 2)}%",
                               f"{format_value(yc.get('change_1d', 0), 4)}",
                               f"As of: {to_gmt8_date(yc.get('latest_date'))}{inv_label}", '#ff7f0e')

        regime_badge = html.Div([
            html.Span(f"{emoji} ", style={'fontSize': '1.6em'}),
            html.Strong(regime, style={'fontSize': '1.2em'}),
            html.Br(),
            html.Span(signal, style={'color': color, 'fontWeight': '600'}),
            html.Br(),
            html.Span(detail, style={'fontSize': '0.85em', 'color': '#555'}),
        ], className='regime-badge',
           style={'backgroundColor': f'{color}22', 'borderLeft': f'4px solid {color}'})

        children.append(html.Div([yc_card, regime_badge], className='metrics-row cols-2'))

        # 20-day changes caption
        d2y = yc.get('delta_2y', 0)
        d10y = yc.get('delta_10y', 0)
        ds = yc.get('delta_spread', 0)
        children.append(html.Div(
            f"{lookback}-day changes: "
            f"2Y: {'+' if d2y >= 0 else ''}{d2y:.2f}% | "
            f"10Y: {'+' if d10y >= 0 else ''}{d10y:.2f}% | "
            f"Spread: {'+' if ds >= 0 else ''}{ds:.2f}%",
            style={'fontSize': '0.75rem', 'color': '#888', 'fontWeight': '600', 'marginBottom': '6px'}))

        # 2s10s chart with zero line
        hist = yc.get('historical')
        if hist is not None and len(hist) > 0:
            fig = make_history_chart(hist, '2s10s Spread (%)', '#ff7f0e', days=365)
            if fig:
                fig.add_hline(y=0, line_dash="dash", line_color="red", opacity=0.6,
                              annotation_text="Inversion threshold")
                fig.update_layout(title="US Treasury 2s10s Yield Spread (10Y − 2Y)")
                children.append(html.Details([
                    html.Summary("2s10s Spread History", style={
                        'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
                    dcc.Graph(figure=fig, config={'displayModeBar': False}),
                ]))

    # Global 10Y Yields — with country flag emojis
    children.append(section_subheader("Global 10-Year Sovereign Yields"))
    yields_data = [
        (loader.get('11_10y_yield'), '🇺🇸 US 10Y', '10y_yield', '#1565c0'),
        (loader.get('61_5y_yield'), '🇺🇸 US 5Y', '5y_yield', '#0d47a1'),
        (loader.get('30_germany_10y'), '🇩🇪 DE 10Y', 'germany_10y_yield', '#d32f2f'),
        (loader.get('31_uk_10y'), '🇬🇧 UK 10Y', 'uk_10y_yield', '#1b5e20'),
        (loader.get('32_china_10y'), '🇨🇳 CN 10Y', 'china_10y_yield', '#e65100'),
    ]
    y_row = []
    for data, label, vk, clr in yields_data:
        if 'error' in data:
            y_row.append(error_card(label, data['error']))
        else:
            card = metric_card(label, f"{format_value(data.get(vk), 2)}%",
                                f"{format_value(data.get('change_1d', 0), 3)}",
                                f"As of: {to_gmt8_date(data.get('latest_date'))}", clr)
            exp = history_expander(data, label.split(' ', 1)[-1] + ' (%)', clr)
            y_row.append(html.Div([card, exp]) if exp else card)
    children.append(html.Div(y_row, className='metrics-row cols-5'))

    # Global 10Y Yields overlay chart
    us10y = loader.get('11_10y_yield')
    de_data = loader.get('30_germany_10y')
    uk_data = loader.get('31_uk_10y')
    if 'error' not in yc and 'historical_10y' in yc:
        fig = go.Figure()
        h10y = yc['historical_10y']
        fig.add_trace(go.Scatter(x=h10y.index, y=h10y.values,
                                  name='US 10Y', line=dict(color='#1565c0', width=2)))
        if 'error' not in de_data and 'historical' in de_data:
            fig.add_trace(go.Scatter(x=de_data['historical'].index, y=de_data['historical'].values,
                                      name='Germany 10Y', line=dict(color='#d32f2f', width=1.5, dash='dash')))
        if 'error' not in uk_data and 'historical' in uk_data:
            fig.add_trace(go.Scatter(x=uk_data['historical'].index, y=uk_data['historical'].values,
                                      name='UK 10Y', line=dict(color='#1b5e20', width=1.5, dash='dot')))
        fig.update_layout(
            title="Global 10-Year Sovereign Yields",
            xaxis_title="Date", yaxis_title="Yield (%)",
            hovermode='x unified', height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        children.append(html.Details([
            html.Summary("Global 10Y Yields Chart", style={
                'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
            dcc.Graph(figure=fig, config={'displayModeBar': False}),
        ]))

    # Real Yields & Breakevens
    children.append(section_subheader("Real Yields & Inflation Expectations"))
    ry = loader.get('36_real_yield')
    be = loader.get('35_breakeven_inflation')
    ry_row = []
    if 'error' in ry:
        ry_row.append(error_card("10Y Real Yield", ry['error']))
    else:
        ry_card = metric_card("10Y Real Yield (TIPS)", f"{format_value(ry.get('real_yield_10y'), 2)}%",
                               f"{format_value(ry.get('change_1d', 0), 4)}",
                               ry.get('interpretation', ''), '#6a1b9a')
        exp = history_expander(ry, 'Real Yield (%)', '#6a1b9a')
        ry_row.append(html.Div([ry_card, exp]) if exp else ry_card)
    if 'error' in be:
        ry_row.append(error_card("Breakevens", be['error']))
    else:
        be5_card = metric_card("5Y Breakeven", f"{format_value(be.get('breakeven_5y'), 2)}%",
                                f"{format_value(be.get('change_5y_1d', 0), 4)}", border_color='#e65100')
        exp5 = history_expander(be, '5Y Breakeven (%)', '#e65100', hist_key='historical_5y')
        ry_row.append(html.Div([be5_card, exp5]) if exp5 else be5_card)

        be10_card = metric_card("10Y Breakeven", f"{format_value(be.get('breakeven_10y'), 2)}%",
                                 f"{format_value(be.get('change_10y_1d', 0), 4)}",
                                 be.get('interpretation', ''), '#bf360c')
        exp10 = history_expander(be, '10Y Breakeven (%)', '#bf360c', hist_key='historical_10y')
        ry_row.append(html.Div([be10_card, exp10]) if exp10 else be10_card)
    children.append(html.Div(ry_row, className='metrics-row cols-3'))

    # Nominal vs Real vs Breakeven chart
    if ('error' not in yc and 'historical_10y' in yc
            and 'error' not in ry and 'historical' in ry):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=yc['historical_10y'].index, y=yc['historical_10y'].values,
                                  name='Nominal 10Y', line=dict(color='#1565c0', width=2)))
        fig.add_trace(go.Scatter(x=ry['historical'].index, y=ry['historical'].values,
                                  name='Real 10Y (TIPS)', line=dict(color='#6a1b9a', width=2)))
        if 'error' not in be and 'historical_10y' in be:
            fig.add_trace(go.Scatter(x=be['historical_10y'].index, y=be['historical_10y'].values,
                                      name='10Y Breakeven', line=dict(color='#e65100', width=1.5, dash='dash')))
        fig.add_hline(y=2.0, line_dash="dot", line_color="gray", opacity=0.4,
                      annotation_text="Fed 2% target")
        fig.update_layout(
            title="Nominal 10Y vs Real 10Y vs 10Y Breakeven Inflation",
            xaxis_title="Date", yaxis_title="Yield / Rate (%)",
            hovermode='x unified', height=420,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        children.append(html.Details([
            html.Summary("Nominal vs Real vs Breakeven Chart", style={
                'cursor': 'pointer', 'fontSize': '0.78rem', 'color': '#666', 'padding': '4px 0'}),
            dcc.Graph(figure=fig, config={'displayModeBar': False}),
        ]))

    # Credit & Financial Conditions
    children.append(section_subheader("Credit & Financial Conditions"))
    cred_items = [
        (loader.get('34_hy_oas'), 'HY OAS', 'hy_oas', '#c62828'),
        (loader.get('37_nfci'), 'NFCI', 'nfci', '#4527a0'),
        (loader.get('38_fed_funds'), 'Fed Funds', 'fed_funds_rate', '#00695c'),
        (loader.get('45_ig_oas'), 'IG OAS', 'ig_oas', '#4e342e'),
    ]
    cred_row = []
    for data, label, vk, clr in cred_items:
        if 'error' in data:
            cred_row.append(error_card(label, data['error']))
        else:
            val = data.get(vk, 'N/A')
            fmt_val = f"{format_value(val, 2)}%" if vk in ('hy_oas', 'fed_funds_rate', 'ig_oas') else format_value(val, 4)
            card = metric_card(label, fmt_val,
                                f"{format_value(data.get('change_1d', data.get('change_1w', 0)), 3)}",
                                data.get('interpretation', ''), clr)
            exp = history_expander(data, f'{label} (%)', clr)
            cred_row.append(html.Div([card, exp]) if exp else card)
    children.append(html.Div(cred_row, className='metrics-row cols-4'))

    # Bank Reserves + SLOOS
    res = loader.get('58_bank_reserves')
    sloos = loader.get('62_sloos')
    rs_row = []
    if 'error' in res:
        rs_row.append(error_card("Bank Reserves", res['error']))
    else:
        r_card = metric_card("Bank Reserves ($T)", format_value(res.get('reserves_trillions'), 3),
                              f"{format_value(res.get('change_wow_pct', 0), 1)}% WoW",
                              res.get('interpretation', ''), '#1a237e')
        exp = history_expander(res, 'Bank Reserves ($T)', '#1a237e')
        rs_row.append(html.Div([r_card, exp]) if exp else r_card)

    if 'error' in sloos:
        rs_row.append(html.Div(f"SLOOS: {sloos.get('error', 'Unavailable')} (quarterly)",
                                style={'fontSize': '0.78rem', 'color': '#888'}))
    else:
        s_card = metric_card("SLOOS Tightening", f"{format_value(sloos.get('sloos_tightening'), 1)}%",
                              f"{format_value(sloos.get('change_qoq', 0), 1)} QoQ",
                              sloos.get('interpretation', ''), '#3e2723')
        exp = history_expander(sloos, 'SLOOS Net Tightening (%)', '#3e2723')
        rs_row.append(html.Div([s_card, exp]) if exp else s_card)
    children.append(html.Div(rs_row, className='metrics-row cols-2'))

    # Labor Market & Inflation
    children.append(section_subheader("Labor Market & Inflation"))
    labor_items = [
        (loader.get('40_unemployment'), 'Unemployment', 'unemployment_rate', '%', 1, '#283593'),
        (loader.get('39_initial_claims'), 'Initial Claims (K)', 'initial_claims_k', '', 1, '#37474f'),
    ]
    infl = loader.get('41_core_inflation')
    lb_row = []
    for data, label, vk, suffix, dec, clr in labor_items:
        if 'error' in data:
            lb_row.append(error_card(label, data['error']))
        else:
            val = data.get(vk, 'N/A')
            card = metric_card(label, f"{format_value(val, dec)}{suffix}",
                                caption=f"As of: {to_gmt8_date(data.get('latest_date'))}", border_color=clr)
            exp = history_expander(data, label, clr)
            lb_row.append(html.Div([card, exp]) if exp else card)

    if 'error' in infl:
        lb_row.append(error_card("Core Inflation", infl['error']))
    else:
        cpi_card = metric_card("Core CPI YoY", f"{format_value(infl.get('core_cpi_yoy'), 2)}%",
                                border_color='#e65100')
        exp_cpi = history_expander(infl, 'Core CPI YoY (%)', '#e65100', hist_key='historical_core_cpi')
        lb_row.append(html.Div([cpi_card, exp_cpi]) if exp_cpi else cpi_card)

        pce_card = metric_card("Core PCE YoY", f"{format_value(infl.get('core_pce_yoy'), 2)}%",
                                caption=infl.get('interpretation', ''), border_color='#bf360c')
        exp_pce = history_expander(infl, 'Core PCE YoY (%)', '#bf360c', hist_key='historical_core_pce')
        lb_row.append(html.Div([pce_card, exp_pce]) if exp_pce else pce_card)
    children.append(html.Div(lb_row, className='metrics-row cols-4'))

    # Extra: Continuing Claims, Headline CPI, PPI
    extra_row = []
    for data, label, vk, clr in [
        (loader.get('49_continuing_claims'), "Continuing Claims (K)", 'continuing_claims_k', '#455a64'),
        (loader.get('53_headline_cpi'), "Headline CPI YoY", 'headline_cpi_yoy', '#ff6f00'),
        (loader.get('52_ppi'), "PPI YoY", 'ppi_yoy', '#ad1457'),
    ]:
        if 'error' in data:
            extra_row.append(error_card(label, data['error']))
        else:
            val = data.get(vk, 'N/A')
            suffix = '%' if 'cpi' in vk or 'ppi' in vk else ''
            card = metric_card(label, f"{format_value(val, 2 if suffix else 1)}{suffix}",
                                caption=f"As of: {to_gmt8_date(data.get('latest_date'))}", border_color=clr)
            exp = history_expander(data, label, clr)
            extra_row.append(html.Div([card, exp]) if exp else card)
    children.append(html.Div(extra_row, className='metrics-row cols-3'))

    # ── OpenBB Rates & Credit Indicators ────────────────────────────────
    children.append(section_header("ECB Policy Rates"))
    ecb = loader.get('66_ecb_rates')
    if 'error' in ecb:
        children.append(error_card("ECB Rates", ecb['error']))
    else:
        children.append(html.Div([
            metric_card("Deposit Rate", f"{format_value(ecb.get('deposit_rate'))}%"),
            metric_card("Refi Rate", f"{format_value(ecb.get('refi_rate'))}%"),
            metric_card("Marginal Rate", f"{format_value(ecb.get('marginal_rate'))}%"),
        ], className='metrics-row cols-3'))

    children.append(section_header("CPI Components Breakdown"))
    cpic = loader.get('68_cpi_components')
    if 'error' in cpic:
        children.append(error_card("CPI Components", cpic['error']))
    else:
        children.append(html.Div([
            metric_card("Headline CPI YoY", f"{format_value(cpic.get('headline_cpi_yoy'))}%"),
            metric_card("Core CPI YoY", f"{format_value(cpic.get('core_cpi_yoy'))}%"),
            metric_card("Food CPI YoY", f"{format_value(cpic.get('food_cpi_yoy'))}%"),
            metric_card("Energy CPI YoY", f"{format_value(cpic.get('energy_cpi_yoy'))}%"),
            metric_card("Shelter CPI YoY", f"{format_value(cpic.get('shelter_cpi_yoy'))}%"),
        ], className='metrics-row cols-5'))

    # European Yields + Global CPI side by side
    euy = loader.get('71_eu_yields')
    gcpi = loader.get('72_global_cpi')
    eu_row = []

    if 'error' in euy:
        eu_row.append(error_card("European Yields", euy['error']))
    else:
        eu_row.append(html.Div([
            html.H4("European Government Yields", style={'fontSize': '0.88rem', 'marginBottom': '4px'}),
            html.Div([
                metric_card("DE 10Y", f"{format_value(euy.get('de_10y'))}%"),
                metric_card("FR 10Y", f"{format_value(euy.get('fr_10y'))}%"),
                metric_card("IT 10Y", f"{format_value(euy.get('it_10y'))}%"),
            ], className='metrics-row cols-3'),
        ], style={'flex': '1'}))

    if 'error' in gcpi:
        eu_row.append(error_card("Global CPI", gcpi['error']))
    else:
        eu_row.append(html.Div([
            html.H4("Global CPI Comparison", style={'fontSize': '0.88rem', 'marginBottom': '4px'}),
            html.Div([
                metric_card("US", f"{format_value(gcpi.get('us_cpi_yoy'))}%"),
                metric_card("EU", f"{format_value(gcpi.get('eu_cpi_yoy'))}%"),
                metric_card("JP", f"{format_value(gcpi.get('jp_cpi_yoy'))}%"),
                metric_card("UK", f"{format_value(gcpi.get('uk_cpi_yoy'))}%"),
            ], className='metrics-row cols-4'),
        ], style={'flex': '1'}))

    children.append(html.Div(eu_row, className='metrics-row cols-2'))

    # Treasury Curve
    children.append(section_header("Full Treasury Yield Curve"))
    tyc = loader.get('75_treasury_curve')
    if 'error' in tyc:
        children.append(error_card("Treasury Curve", tyc['error']))
    else:
        curve = tyc.get('curve', {})
        if curve:
            import plotly.graph_objects as go_tc
            mats = list(curve.keys())
            yields_v = [curve[m] for m in mats]
            fig_tc = go_tc.Figure(data=go_tc.Scatter(x=mats, y=yields_v, mode='lines+markers', line=dict(color='#1565c0', width=2)))
            fig_tc.update_layout(title="US Treasury Yield Curve", xaxis_title="Maturity", yaxis_title="Yield (%)",
                                  height=280, margin=dict(l=40, r=20, t=30, b=30))
            children.append(dcc.Graph(figure=fig_tc, config={'displayModeBar': False}))

    # Corporate Spreads
    children.append(section_header("Corporate Bond Spreads"))
    cs = loader.get('76_corporate_spreads')
    if 'error' in cs:
        children.append(error_card("Corporate Spreads", cs['error']))
    else:
        children.append(html.Div([
            metric_card("AAA OAS", f"{format_value(cs.get('aaa_oas'))}%"),
            metric_card("BBB OAS", f"{format_value(cs.get('bbb_oas'))}%"),
            metric_card("Credit Spread (BBB-AAA)", f"{format_value(cs.get('credit_spread'))}%"),
        ], className='metrics-row cols-3'))

    return html.Div(children, className='tab-content')


def build_tab8(loader):
    """Economic Activity."""
    children = [section_header("Economic Activity")]

    # Employment & Recession Risk
    children.append(section_subheader("Employment & Recession Risk"))
    emp_items = [
        (loader.get('42_nfp'), 'Nonfarm Payrolls (K)', 'nfp_thousands', 0, '#1565c0', 'nfp_change_mom'),
        (loader.get('48_jolts'), 'JOLTS Openings (M)', 'jolts_openings_m', 2, '#0d47a1', 'change_mom_pct'),
        (loader.get('60_quits_rate'), 'Quits Rate (%)', 'quits_rate', 1, '#1a237e', 'change_mom'),
        (loader.get('46_sahm_rule'), 'Sahm Rule', 'sahm_value', 2, '#c62828', 'change_mom'),
    ]
    emp_row = []
    for data, label, vk, dec, clr, delta_key in emp_items:
        if 'error' in data:
            emp_row.append(error_card(label, data['error']))
        else:
            val = data.get(vk, 'N/A')
            suffix = '%' if 'rate' in vk else ''
            delta = data.get(delta_key, 0)
            delta_suffix = 'K MoM' if 'nfp' in vk else ('% MoM' if 'jolts' in vk else ' MoM')
            cap = f"As of: {to_gmt8_date(data.get('latest_date'))}"
            if vk == 'sahm_value':
                triggered = data.get('triggered', False)
                cap += ' | RECESSION SIGNAL' if triggered else ' | Below threshold'
            interp = data.get('interpretation', '')
            if interp:
                cap += f" | {interp}"
            card = metric_card(label, f"{format_value(val, dec)}{suffix}",
                                f"{format_value(delta, dec)}{delta_suffix}",
                                cap, clr)
            exp = history_expander(data, label, clr)
            emp_row.append(html.Div([card, exp]) if exp else card)
    children.append(html.Div(emp_row, className='metrics-row cols-4'))

    # Sahm Rule chart with threshold
    sahm = loader.get('46_sahm_rule')
    if 'error' not in sahm:
        hist = sahm.get('historical')
        if hist is not None and len(hist) > 0:
            fig = make_history_chart(hist, 'Sahm Rule', '#c62828', days=365)
            if fig:
                fig.add_hline(y=0.50, line_dash="dash", line_color="red", opacity=0.7,
                              annotation_text="Recession threshold (0.50)")
                fig.update_layout(title="Sahm Rule Recession Indicator")
                children.append(dcc.Graph(figure=fig, config={'displayModeBar': False}))

    # Consumer
    children.append(section_subheader("Consumer"))
    cs = loader.get('44_consumer_sentiment')
    rs = loader.get('50_retail_sales')
    cons_row = []
    if 'error' in cs:
        cons_row.append(error_card("Consumer Sentiment", cs['error']))
    else:
        cs_card = metric_card("UMich Consumer Sentiment", format_value(cs.get('consumer_sentiment'), 1),
                               f"{format_value(cs.get('change_mom', 0), 1)} MoM",
                               cs.get('interpretation', ''), '#00695c')
        exp = history_expander(cs, 'Consumer Sentiment', '#00695c')
        cons_row.append(html.Div([cs_card, exp]) if exp else cs_card)

    if 'error' in rs:
        cons_row.append(error_card("Retail Sales", rs['error']))
    else:
        rs_card = metric_card("Retail Sales ($B)", format_value(rs.get('retail_sales_b'), 1),
                               f"{format_value(rs.get('retail_sales_mom_pct', 0), 2)}% MoM",
                               rs.get('interpretation', ''), '#2e7d32')
        exp = history_expander(rs, 'Retail Sales MoM%', '#2e7d32')
        cons_row.append(html.Div([rs_card, exp]) if exp else rs_card)
    children.append(html.Div(cons_row, className='metrics-row cols-2'))

    # Production & Housing
    children.append(section_subheader("Production & Housing"))
    prod_items = [
        (loader.get('43_ism_services'), 'ISM Services PMI', 'ism_services_pmi', 1, '#1565c0'),
        (loader.get('59_industrial_production'), 'Industrial Production', 'indpro_index', 1, '#4a148c'),
        (loader.get('51_housing_starts'), 'Housing Starts (K, ann.)', 'housing_starts_k', 0, '#bf360c'),
    ]
    prod_row = []
    for data, label, vk, dec, clr in prod_items:
        if 'error' in data:
            prod_row.append(error_card(label, data['error']))
        else:
            delta_key = 'change_1d' if 'change_1d' in data else ('indpro_yoy_pct' if 'indpro' in vk else 'change_mom_pct')
            delta = data.get(delta_key, 0)
            suffix = '% YoY' if 'indpro' in vk else ('% MoM' if 'housing' in vk else '')
            card = metric_card(label, format_value(data.get(vk), dec),
                                f"{format_value(delta, 1)}{suffix}",
                                data.get('interpretation', ''), clr)
            exp = history_expander(data, label, clr)
            prod_row.append(html.Div([card, exp]) if exp else card)
    children.append(html.Div(prod_row, className='metrics-row cols-3'))

    # ── OpenBB Economic Activity Indicators ──────────────────────────────
    children.append(section_header("Leading & International Indicators"))

    # OECD CLI
    oecd = loader.get('67_oecd_cli')
    if 'error' in oecd:
        children.append(error_card("OECD CLI", oecd['error']))
    else:
        cli_val = oecd.get('cli_value')
        signal = "Expansion" if cli_val and cli_val > 100 else "Contraction"
        signal_clr = '#2e7d32' if signal == "Expansion" else '#c62828'
        children.append(html.Div([
            metric_card("OECD US Leading Indicator", format_value(cli_val, 2),
                        caption=f"As of: {to_gmt8_date(oecd.get('latest_date'))} | {signal}", border_color='#1565c0'),
            html.Div([
                html.Span("Signal: ", style={'fontSize': '0.78rem', 'color': '#666'}),
                html.Span(signal, style={'fontSize': '0.78rem', 'fontWeight': 'bold', 'color': signal_clr}),
                html.Span(" (>100 = expansion)", style={'fontSize': '0.68rem', 'color': '#999'}),
            ], style={'padding': '4px 8px'}),
        ]))

    # International Unemployment
    intl_u = loader.get('77_intl_unemployment')
    if 'error' in intl_u:
        children.append(error_card("Intl Unemployment", intl_u['error']))
    else:
        children.append(html.Div([
            metric_card("US Unemp.", f"{format_value(intl_u.get('us_unemployment'))}%", border_color='#1565c0'),
            metric_card("EU Unemp.", f"{format_value(intl_u.get('eu_unemployment'))}%", border_color='#0d47a1'),
            metric_card("JP Unemp.", f"{format_value(intl_u.get('jp_unemployment'))}%", border_color='#1a237e'),
            metric_card("UK Unemp.", f"{format_value(intl_u.get('uk_unemployment'))}%", border_color='#283593'),
        ], className='metrics-row cols-4'))

    # International GDP
    intl_g = loader.get('78_intl_gdp')
    if 'error' in intl_g:
        children.append(error_card("Intl GDP", intl_g['error']))
    else:
        children.append(html.Div([
            metric_card("US GDP Growth", f"{format_value(intl_g.get('us_gdp_growth'))}%", border_color='#1565c0'),
            metric_card("EU GDP Growth", f"{format_value(intl_g.get('eu_gdp_growth'))}%", border_color='#0d47a1'),
            metric_card("JP GDP Growth", f"{format_value(intl_g.get('jp_gdp_growth'))}%", border_color='#1a237e'),
            metric_card("CN GDP Growth", f"{format_value(intl_g.get('cn_gdp_growth'))}%", border_color='#283593'),
        ], className='metrics-row cols-4'))

    # Global PMI
    gpmi = loader.get('81_global_pmi')
    if 'error' in gpmi:
        children.append(error_card("Global PMI", gpmi['error']))
    else:
        pmi_row = []
        for key, label, clr in [('us_mfg_pmi', 'US', '#1565c0'), ('eu_mfg_pmi', 'EU', '#0d47a1'),
                                  ('jp_mfg_pmi', 'JP', '#1a237e'), ('cn_mfg_pmi', 'CN', '#283593'),
                                  ('uk_mfg_pmi', 'UK', '#303f9f')]:
            val = gpmi.get(key)
            above = val and val > 50
            pmi_row.append(metric_card(f"{label} Mfg PMI", format_value(val, 1),
                                        caption="Expanding" if above else "Contracting",
                                        border_color=clr))
        children.append(html.Div(pmi_row, className='metrics-row cols-5'))
        children.append(html.Div(
            html.Span(">50 = expansion, <50 = contraction", style={'fontSize': '0.68rem', 'color': '#999'}),
            style={'padding': '2px 8px'}))

    return html.Div(children, className='tab-content')


# ─── Layout ─────────────────────────────────────────────────────────────────

app.layout = html.Div([
    # Hidden intervals
    dcc.Interval(id='refresh-interval', interval=60_000, n_intervals=0),
    dcc.Interval(id='progress-poll', interval=3_000, n_intervals=0),
    # Store: snapshot of cache mtime when data was last applied to the dashboard
    dcc.Store(id='applied-cache-mtime', data=os.path.getmtime(CACHE_FILE) if os.path.exists(CACHE_FILE) else None),

    # Header with controls
    html.Div([
        html.Div([
            html.H1("Macro Indicators Dashboard"),
            html.Div(id='header-status', className='status'),
        ], style={'flex': '1'}),
        html.Div([
            html.Div(id='refresh-status-panel', style={'textAlign': 'right'}),
            html.Div("90+ indicators | FRED, Yahoo Finance, SEC EDGAR, CFTC, MOF Japan, AAII, OpenBB",
                      style={'fontSize': '0.72rem', 'color': '#888', 'textAlign': 'right',
                             'marginTop': '4px'}),
        ], style={'textAlign': 'right', 'paddingRight': '16px', 'minWidth': '350px'}),
    ], className='dash-header', style={'display': 'flex', 'alignItems': 'center'}),

    # Confirmation banner — shown when new data is available
    html.Div(id='refresh-confirm-banner', style={'display': 'none'}),

    # Tabs
    dcc.Tabs(id='main-tabs', value='tab-1', className='custom-tabs', children=[
        dcc.Tab(label='Valuation', value='tab-1', className='tab'),
        dcc.Tab(label='Indices', value='tab-2', className='tab'),
        dcc.Tab(label='Volatility', value='tab-3', className='tab'),
        dcc.Tab(label='Macro & FX', value='tab-4', className='tab'),
        dcc.Tab(label='Commodities', value='tab-5', className='tab'),
        dcc.Tab(label='Financials', value='tab-6', className='tab'),
        dcc.Tab(label='Rates & Credit', value='tab-7', className='tab'),
        dcc.Tab(label='Econ Activity', value='tab-8', className='tab'),
    ]),

    # Financials ticker selector (only visible on tab 6)
    html.Div(id='ticker-selector-container', children=[
        html.Div([
            html.Label("Select Company:", style={'fontSize': '0.82rem', 'marginRight': '8px'}),
            dcc.Dropdown(
                id='ticker-dropdown',
                options=[{'label': t, 'value': t} for t in TOP_20_TICKERS],
                value='AAPL',
                clearable=False,
                style={'width': '200px', 'display': 'inline-block'},
            ),
            dcc.Input(
                id='custom-ticker-input',
                type='text',
                placeholder='Or type any ticker...',
                debounce=True,
                style={'width': '160px', 'marginLeft': '12px', 'padding': '4px 8px',
                       'border': '1px solid #ccc', 'borderRadius': '4px', 'fontSize': '0.82rem'},
            ),
            dcc.RadioItems(
                id='source-toggle',
                options=[
                    {'label': ' Yahoo Finance', 'value': 'yahoo'},
                    {'label': ' SEC EDGAR', 'value': 'sec'},
                ],
                value='yahoo',
                inline=True,
                style={'marginLeft': '20px', 'fontSize': '0.82rem'},
                inputStyle={'marginRight': '4px'},
                labelStyle={'marginRight': '12px'},
            ),
        ], style={'padding': '8px 20px', 'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap', 'gap': '4px'}),
    ], style={'display': 'none'}),

    # Tab content
    html.Div(id='tab-content'),

    # Footer
    html.Div([
        html.P("Macro Indicators Dashboard | Data: FRED, Yahoo Finance, SEC EDGAR, Trading Economics, CFTC, MOF Japan"),
        html.P("For informational purposes only. Not financial advice."),
    ], className='dash-footer'),
])


# ─── Callbacks ──────────────────────────────────────────────────────────────

@callback(
    Output('header-status', 'children'),
    Input('refresh-interval', 'n_intervals'),
)
def update_header_status(n):
    loader = get_loader()
    # Don't auto-reload here — just show the timestamp of currently loaded data
    return f"Last updated: {loader.get_last_update_gmt8()} ({loader.get_cache_age_str()})"


# ── Refresh progress panel (top-right) ─────────────────────────────────────
def _read_progress():
    """Read extraction progress file. Returns dict or None."""
    try:
        if os.path.exists(PROGRESS_FILE):
            with open(PROGRESS_FILE, 'r') as f:
                return json.load(f)
    except Exception:
        pass
    return None


@callback(
    Output('refresh-status-panel', 'children'),
    Output('refresh-confirm-banner', 'children'),
    Output('refresh-confirm-banner', 'style'),
    Input('progress-poll', 'n_intervals'),
    State('applied-cache-mtime', 'data'),
)
def update_refresh_panel(_n, applied_mtime):
    """Poll extraction progress and detect new cache data."""
    from datetime import datetime as _dt

    children = []
    banner_children = no_update
    banner_style = no_update

    # ── Part 1: Extraction progress ──
    prog = _read_progress()
    if prog and prog.get('status') == 'running':
        current = prog.get('current', 0)
        total = prog.get('total', 82)
        label = prog.get('label', '')
        pct = int(current / total * 100) if total else 0

        # Check for stall
        try:
            prog_time = _dt.fromisoformat(prog['timestamp'])
            age_secs = (_dt.now() - prog_time).total_seconds()
        except Exception:
            age_secs = 0

        if age_secs > _STALL_THRESHOLD_SECS:
            # Stalled — show warning + option to apply partial data
            children = [
                html.Div([
                    html.Span("⚠️ ", style={'fontSize': '14px'}),
                    html.Span(f"Extraction stalled at {current}/{total} ",
                              style={'fontSize': '0.75rem', 'color': '#e65100'}),
                    html.Span(f"({label})",
                              style={'fontSize': '0.7rem', 'color': '#999'}),
                ]),
                html.Div(
                    html.Div(style={
                        'width': f'{pct}%', 'height': '4px',
                        'backgroundColor': '#e65100', 'borderRadius': '2px',
                        'transition': 'width 0.5s',
                    }),
                    style={'width': '100%', 'backgroundColor': '#333',
                           'borderRadius': '2px', 'marginTop': '3px'},
                ),
            ]
            # Show banner offering to apply whatever data is available
            banner_children = html.Div([
                html.Span("⚠️ Data extraction appears stuck. ",
                          style={'fontWeight': 'bold', 'color': '#e65100'}),
                html.Span(f"Stalled at {current}/{total} ({label}). "),
                html.Button("Apply Available Data", id='btn-apply-refresh',
                            n_clicks=0,
                            style={'marginLeft': '12px', 'padding': '4px 12px',
                                   'border': '1px solid #e65100', 'borderRadius': '4px',
                                   'backgroundColor': '#fff3e0', 'color': '#e65100',
                                   'cursor': 'pointer', 'fontSize': '0.82rem',
                                   'fontWeight': 'bold'}),
                html.Button("Dismiss", id='btn-dismiss-refresh', n_clicks=0,
                            style={'marginLeft': '8px', 'padding': '4px 12px',
                                   'border': '1px solid #999', 'borderRadius': '4px',
                                   'backgroundColor': '#f5f5f5', 'color': '#666',
                                   'cursor': 'pointer', 'fontSize': '0.82rem'}),
            ], style={'padding': '10px 20px', 'backgroundColor': '#fff3e0',
                      'borderBottom': '2px solid #e65100', 'textAlign': 'center',
                      'fontSize': '0.85rem'})
            banner_style = {'display': 'block'}
        else:
            # Normal progress
            children = [
                html.Div([
                    html.Span("🔄 ", style={'fontSize': '14px'}),
                    html.Span(f"Refreshing {current}/{total} ",
                              style={'fontSize': '0.75rem', 'color': '#90caf9'}),
                    html.Span(f"({label})",
                              style={'fontSize': '0.7rem', 'color': '#999'}),
                ]),
                html.Div(
                    html.Div(style={
                        'width': f'{pct}%', 'height': '4px',
                        'backgroundColor': '#42a5f5', 'borderRadius': '2px',
                        'transition': 'width 0.5s',
                    }),
                    style={'width': '100%', 'backgroundColor': '#333',
                           'borderRadius': '2px', 'marginTop': '3px'},
                ),
            ]
    elif prog and prog.get('status') == 'done':
        children = [
            html.Span("✅ Extraction complete",
                      style={'fontSize': '0.75rem', 'color': '#66bb6a'}),
        ]
    # else: no progress file or unknown status — show nothing

    # ── Part 2: Detect new cache file ──
    try:
        current_mtime = os.path.getmtime(CACHE_FILE) if os.path.exists(CACHE_FILE) else None
    except Exception:
        current_mtime = None

    if (current_mtime and applied_mtime
            and current_mtime > applied_mtime
            and (not prog or prog.get('status') != 'running')):
        # Cache file is newer than what's loaded — offer to apply
        banner_children = html.Div([
            html.Span("📊 Fresh data is available. ",
                      style={'fontWeight': 'bold'}),
            html.Button("Apply Refreshed Data", id='btn-apply-refresh',
                        n_clicks=0,
                        style={'marginLeft': '12px', 'padding': '4px 14px',
                               'border': '1px solid #2e7d32', 'borderRadius': '4px',
                               'backgroundColor': '#e8f5e9', 'color': '#2e7d32',
                               'cursor': 'pointer', 'fontSize': '0.85rem',
                               'fontWeight': 'bold'}),
            html.Button("Dismiss", id='btn-dismiss-refresh', n_clicks=0,
                        style={'marginLeft': '8px', 'padding': '4px 14px',
                               'border': '1px solid #999', 'borderRadius': '4px',
                               'backgroundColor': '#f5f5f5', 'color': '#666',
                               'cursor': 'pointer', 'fontSize': '0.85rem'}),
        ], style={'padding': '10px 20px', 'backgroundColor': '#e8f5e9',
                  'borderBottom': '2px solid #2e7d32', 'textAlign': 'center',
                  'fontSize': '0.85rem'})
        banner_style = {'display': 'block'}

    return children, banner_children, banner_style


# ── Apply refresh: user clicked "Apply Refreshed Data" ─────────────────────
@callback(
    Output('tab-content', 'children', allow_duplicate=True),
    Output('applied-cache-mtime', 'data', allow_duplicate=True),
    Output('refresh-confirm-banner', 'style', allow_duplicate=True),
    Output('header-status', 'children', allow_duplicate=True),
    Input('btn-apply-refresh', 'n_clicks'),
    State('main-tabs', 'value'),
    State('ticker-dropdown', 'value'),
    State('custom-ticker-input', 'value'),
    State('source-toggle', 'value'),
    prevent_initial_call=True,
)
def apply_refresh(n, tab, ticker, custom_ticker, source):
    if not n:
        return no_update, no_update, no_update, no_update
    loader = get_loader()
    loader._file_mtime = None  # Force reload
    loader.load()
    new_mtime = os.path.getmtime(CACHE_FILE) if os.path.exists(CACHE_FILE) else None
    header = f"Last updated: {loader.get_last_update_gmt8()} ({loader.get_cache_age_str()})"
    return _render_tab_content(tab, ticker, custom_ticker, source, loader), new_mtime, {'display': 'none'}, header


# ── Dismiss refresh banner ──────────────────────────────────────────────────
@callback(
    Output('refresh-confirm-banner', 'style', allow_duplicate=True),
    Output('applied-cache-mtime', 'data', allow_duplicate=True),
    Input('btn-dismiss-refresh', 'n_clicks'),
    prevent_initial_call=True,
)
def dismiss_refresh(n):
    if not n:
        return no_update, no_update
    # Update applied_mtime so the banner doesn't keep reappearing
    new_mtime = os.path.getmtime(CACHE_FILE) if os.path.exists(CACHE_FILE) else None
    return {'display': 'none'}, new_mtime


@callback(
    Output('ticker-selector-container', 'style'),
    Input('main-tabs', 'value'),
)
def toggle_ticker_selector(tab):
    if tab == 'tab-6':
        return {'display': 'block', 'borderBottom': '1px solid #e0e0e0'}
    return {'display': 'none'}


def _render_tab_content(tab, ticker, custom_ticker, source, loader):
    """Shared helper to render tab content."""
    if tab == 'tab-1':
        return build_tab1(loader)
    elif tab == 'tab-2':
        return build_tab2(loader)
    elif tab == 'tab-3':
        return build_tab3(loader)
    elif tab == 'tab-4':
        return build_tab4(loader)
    elif tab == 'tab-5':
        return build_tab5(loader)
    elif tab == 'tab-6':
        effective_ticker = custom_ticker.strip().upper() if custom_ticker and custom_ticker.strip() else (ticker or 'AAPL')
        return build_tab6(loader, effective_ticker, source or 'yahoo')
    elif tab == 'tab-7':
        return build_tab7(loader)
    elif tab == 'tab-8':
        return build_tab8(loader)
    return html.Div("Select a tab")


@callback(
    Output('tab-content', 'children'),
    Input('main-tabs', 'value'),
    Input('ticker-dropdown', 'value'),
    Input('custom-ticker-input', 'value'),
    Input('source-toggle', 'value'),
)
def render_tab(tab, ticker, custom_ticker, source):
    loader = get_loader()
    return _render_tab_content(tab, ticker, custom_ticker, source, loader)


# ─── Run ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print("Starting Dash Macro Dashboard on http://127.0.0.1:8050")
    print(f"Cache file: {CACHE_FILE}")
    app.run(debug=True, host='127.0.0.1', port=8050,
            use_reloader=False)  # disable reloader to prevent OOM double-process
