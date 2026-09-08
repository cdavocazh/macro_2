"""Derived analytics for the React dashboard.

Everything here is computed from data the repo already extracts — the cached
indicator payload (`data_cache/all_indicators.json`), the macro catalyst
calendar CSV, and the 13F holdings CSVs. No new upstream calls.

Kept out of `main.py` so the route handlers stay thin; `main.py` memoizes the
expensive ones on the cache file's mtime, exactly like `_serialized_snapshot`.
"""
from __future__ import annotations

import math
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Category map — mirrors the documented tab layout so the monitor grid can be
# grouped the same way the dashboard is.
# ---------------------------------------------------------------------------
_CATEGORIES = [
    ('Valuation', {'1', '2', '3', '5', '6a', '6b', '7', '65', '74', '82'}),
    ('Indices', {'17', '18', '19', '55', '69', '73', '79'}),
    ('Volatility', {'4', '8', '9', '8b', '63', '64', '70'}),
    ('Macro & FX', {'10', '20', '23', '24', '25', '47', '54', '80'}),
    ('Commodities', {'13', '14', '15', '16', '21', '22', '56', '57', '83', '84', '85'}),
    ('Rates & Credit', {'11', '26', '27', '28', '30', '31', '32', '33', '34', '35',
                        '36', '37', '38', '45', '58', '61', '62', '66', '68', '71',
                        '72', '75', '76'}),
    ('Economic Activity', {'12', '39', '40', '41', '42', '43', '44', '46', '48', '49',
                           '50', '51', '52', '53', '59', '60', '67', '77', '78', '81'}),
]

_LABEL_OVERRIDES = {
    '8_vix': 'VIX', '9_move': 'MOVE Index', '10_dxy': 'Dollar Index (DXY)',
    '34_hy_oas': 'High-Yield OAS', '45_ig_oas': 'Investment-Grade OAS',
    '37_nfci': 'Chicago Fed NFCI', '33_yield_curve': '2s10s Spread',
    '57_cu_au_ratio': 'Copper / Gold Ratio', '5_spx_call_skew': 'CBOE SKEW',
    '55_market_concentration': 'SPY / RSP Concentration',
    '36_real_yield': '10Y Real Yield', '17_es_futures': 'S&P 500 E-mini (ES)',
    '18_rty_futures': 'Russell 2000 E-mini (RTY)', '11_10y_yield': 'US 10Y Yield',
    '28_us2y_jp2y_spread': 'US 2Y − Japan 2Y', '46_sahm_rule': 'Sahm Rule',
}


def _category_for(key: str) -> str:
    num = key.split('_', 1)[0]
    for name, members in _CATEGORIES:
        if num in members:
            return name
    return 'Other'


def _label_for(key: str) -> str:
    if key in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[key]
    body = key.split('_', 1)[1] if '_' in key else key
    return body.replace('_', ' ').title()


def _clean_series(value) -> pd.Series | None:
    """Return a sorted, NaN-free float Series, or None when unusable."""
    if not isinstance(value, pd.Series) or value.empty:
        return None
    s = pd.to_numeric(value, errors='coerce').dropna()
    if s.empty:
        return None
    try:
        s = s.sort_index()
    except Exception:
        return None
    return s


def _safe(x):
    """JSON-safe float (NaN/inf → None) — json.dumps emits bare NaN otherwise."""
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)


# ---------------------------------------------------------------------------
# Monitor grid
# ---------------------------------------------------------------------------

def compute_monitor_rows(indicators: dict) -> list[dict]:
    """One row per indicator that carries a usable history.

    Returns latest value, 1d/5d/21d change (absolute AND percent — a percent
    change on a yield or a spread is close to meaningless, so the UI picks),
    the latest value's percentile within the trailing year, and a sparkline.
    """
    rows = []
    for key, val in indicators.items():
        if not isinstance(val, dict) or 'error' in val:
            continue
        s = _clean_series(val.get('historical'))
        if s is None or len(s) < 30:
            continue

        latest = float(s.iloc[-1])

        def _chg(n):
            if len(s) <= n:
                return None, None
            prev = float(s.iloc[-1 - n])
            abs_chg = latest - prev
            pct = (abs_chg / abs(prev) * 100) if prev != 0 else None
            return abs_chg, pct

        c1a, c1p = _chg(1)
        c5a, c5p = _chg(5)
        c21a, c21p = _chg(21)

        # Percentile of the latest reading within the trailing ~1y of observations
        window = s.iloc[-252:] if len(s) >= 252 else s
        pct_rank = float((window < latest).sum()) / max(len(window) - 1, 1) * 100

        # Sparkline: last 60 observations, downsampled to <=60 points
        tail = s.iloc[-60:]
        spark = [_safe(v) for v in tail.values.tolist()]

        try:
            last_date = str(s.index[-1])[:10]
        except Exception:
            last_date = None

        rows.append({
            'key': key,
            'label': _label_for(key),
            'category': _category_for(key),
            'latest': _safe(latest),
            'chg_1d_abs': _safe(c1a), 'chg_1d_pct': _safe(c1p),
            'chg_5d_abs': _safe(c5a), 'chg_5d_pct': _safe(c5p),
            'chg_21d_abs': _safe(c21a), 'chg_21d_pct': _safe(c21p),
            'pct_1y': _safe(pct_rank),
            'n_obs': int(len(s)),
            'last_date': last_date,
            'spark': spark,
        })

    rows.sort(key=lambda r: (r['category'], r['label']))
    return rows


# ---------------------------------------------------------------------------
# Regime composite
# ---------------------------------------------------------------------------
# (indicator key, polarity, display name). polarity = +1 when a HIGH reading is
# risk-ON, -1 when a HIGH reading is risk-OFF. The composite is the mean of the
# sign-adjusted z-scores, so positive = risk-on.
_REGIME_COMPONENTS = [
    ('8_vix', -1, 'VIX'),
    ('34_hy_oas', -1, 'High-Yield OAS'),
    ('45_ig_oas', -1, 'Investment-Grade OAS'),
    ('37_nfci', -1, 'Financial Conditions (NFCI)'),
    ('5_spx_call_skew', -1, 'CBOE SKEW'),
    ('57_cu_au_ratio', +1, 'Copper / Gold'),
    ('55_market_concentration', -1, 'SPY / RSP Concentration'),
    ('17_es_futures', +1, 'S&P 500 E-mini'),
]

_Z_WINDOW = 252  # ~1 trading year


def compute_regime(indicators: dict) -> dict:
    """Risk-on/off composite: mean of sign-adjusted 1-year z-scores.

    Also reports each component's own z-score and its 1-day delta, so the UI
    can answer "what moved the regime since yesterday" rather than only showing
    a number with no attribution.
    """
    comps, zs = [], []
    for key, polarity, name in _REGIME_COMPONENTS:
        val = indicators.get(key)
        s = _clean_series(val.get('historical')) if isinstance(val, dict) else None
        if s is None or len(s) < 60:
            comps.append({'key': key, 'label': name, 'status': 'unavailable'})
            continue

        window = s.iloc[-_Z_WINDOW:]
        mu, sd = float(window.mean()), float(window.std())
        if not sd or math.isnan(sd) or sd == 0:
            comps.append({'key': key, 'label': name, 'status': 'flat'})
            continue

        z_now = (float(s.iloc[-1]) - mu) / sd
        z_prev = ((float(s.iloc[-2]) - mu) / sd) if len(s) >= 2 else z_now
        contrib = z_now * polarity

        comps.append({
            'key': key, 'label': name, 'status': 'ok',
            'polarity': polarity,
            'latest': _safe(s.iloc[-1]),
            'z': _safe(z_now),
            'z_change_1d': _safe(z_now - z_prev),
            'contribution': _safe(contrib),
            'last_date': str(s.index[-1])[:10],
        })
        zs.append(contrib)

    score = float(np.mean(zs)) if zs else None
    if score is None:
        label = 'Unavailable'
    elif score >= 0.75:
        label = 'Strong risk-on'
    elif score >= 0.25:
        label = 'Risk-on'
    elif score > -0.25:
        label = 'Neutral'
    elif score > -0.75:
        label = 'Risk-off'
    else:
        label = 'Strong risk-off'

    movers = sorted(
        [c for c in comps if c.get('status') == 'ok' and c.get('z_change_1d') is not None],
        key=lambda c: abs(c['z_change_1d']), reverse=True,
    )[:3]

    return {
        'score': _safe(score),
        'label': label,
        'n_components': len(zs),
        'components': comps,
        'top_movers_1d': [
            {'label': m['label'], 'z_change_1d': m['z_change_1d'], 'z': m['z']}
            for m in movers
        ],
        'method': (f'Mean of sign-adjusted z-scores over a {_Z_WINDOW}-observation '
                   f'window. Positive = risk-on.'),
        'computed_at': datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Conditional forward-return study
# ---------------------------------------------------------------------------

_OPS = {
    'lt': lambda s, v: s < v,
    'lte': lambda s, v: s <= v,
    'gt': lambda s, v: s > v,
    'gte': lambda s, v: s >= v,
}


def forward_return_study(indicators: dict, condition_key: str, op: str,
                         threshold: float, target_key: str,
                         horizons: list[int]) -> dict:
    """Forward returns of `target_key` on days when `condition_key` op threshold.

    The point of the exercise is the comparison against the unconditional
    baseline over the same sample — a 60% hit rate means nothing if the
    unconditional hit rate is also 60%.

    Overlapping windows are NOT independent observations, so `n_signal` counts
    days, not independent trials; treat the dispersion as indicative.
    """
    if op not in _OPS:
        return {'error': f"Unknown operator '{op}'. Use one of: {', '.join(_OPS)}"}

    cond_raw = indicators.get(condition_key)
    tgt_raw = indicators.get(target_key)
    cond = _clean_series(cond_raw.get('historical')) if isinstance(cond_raw, dict) else None
    tgt = _clean_series(tgt_raw.get('historical')) if isinstance(tgt_raw, dict) else None

    if cond is None:
        return {'error': f'No usable history for condition indicator {condition_key}'}
    if tgt is None:
        return {'error': f'No usable history for target indicator {target_key}'}

    # Normalise both to date granularity, then align the condition onto the
    # target's trading calendar (forward-fill: a monthly macro print stays in
    # force until the next one).
    cond.index = pd.to_datetime(cond.index).tz_localize(None).normalize()
    tgt.index = pd.to_datetime(tgt.index).tz_localize(None).normalize()
    cond = cond[~cond.index.duplicated(keep='last')]
    tgt = tgt[~tgt.index.duplicated(keep='last')]

    aligned = cond.reindex(tgt.index, method='ffill')
    mask = _OPS[op](aligned, threshold) & aligned.notna()

    if int(mask.sum()) == 0:
        return {
            'error': f'No days where {condition_key} {op} {threshold} '
                     f'over the {len(tgt)} observations available.'
        }

    results = []
    for h in horizons:
        if h <= 0 or h >= len(tgt):
            continue
        fwd = (tgt.shift(-h) / tgt - 1.0) * 100.0
        sig = fwd[mask].dropna()
        base = fwd.dropna()
        if sig.empty:
            continue
        results.append({
            'horizon_days': int(h),
            'n_signal': int(len(sig)),
            'mean_pct': _safe(sig.mean()),
            'median_pct': _safe(sig.median()),
            'hit_rate_pct': _safe((sig > 0).mean() * 100),
            'p25_pct': _safe(sig.quantile(0.25)),
            'p75_pct': _safe(sig.quantile(0.75)),
            'stdev_pct': _safe(sig.std()),
            'baseline_mean_pct': _safe(base.mean()),
            'baseline_hit_rate_pct': _safe((base > 0).mean() * 100),
            'edge_mean_pct': _safe(sig.mean() - base.mean()),
            'edge_hit_rate_pct': _safe((sig > 0).mean() * 100 - (base > 0).mean() * 100),
        })

    return {
        'condition': {
            'key': condition_key, 'label': _label_for(condition_key),
            'op': op, 'threshold': threshold,
            'latest': _safe(cond.iloc[-1]),
            'currently_true': bool(_OPS[op](pd.Series([float(cond.iloc[-1])]), threshold).iloc[0]),
        },
        'target': {'key': target_key, 'label': _label_for(target_key)},
        'sample': {
            'start': str(tgt.index[0])[:10], 'end': str(tgt.index[-1])[:10],
            'n_days': int(len(tgt)), 'n_signal_days': int(mask.sum()),
        },
        'horizons': results,
        'caveat': ('Overlapping forward windows are not independent trials. '
                   'Compare against the baseline column, not zero.'),
    }


# ---------------------------------------------------------------------------
# Macro catalyst calendar
# ---------------------------------------------------------------------------

def load_calendar(project_root: str, days_ahead: int = 45, limit: int = 20) -> dict:
    """Upcoming macro releases + FOMC dates from the catalyst-calendar CSV."""
    path = os.path.join(project_root, 'historical_data', 'macro_catalyst_calendar.csv')
    if not os.path.exists(path):
        return {'error': 'macro_catalyst_calendar.csv not found — run '
                         'data_extractors/macro_calendar_extractor.build_macro_calendar()',
                'events': []}

    try:
        df = pd.read_csv(path)
    except Exception as e:
        return {'error': f'Failed to read calendar: {e}', 'events': []}

    if df.empty or 'date' not in df.columns:
        return {'error': 'Calendar CSV is empty or malformed', 'events': []}

    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])

    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    upcoming = df[(df['date'] >= today) &
                  (df['date'] <= today + pd.Timedelta(days=days_ahead))]
    upcoming = upcoming.sort_values('date').head(limit)

    events = [{
        'date': r['date'].strftime('%Y-%m-%d'),
        'days_until': int((r['date'] - today).days),
        'event_type': r.get('event_type'),
        'name': r.get('release_name'),
        'importance': r.get('importance', 'medium'),
        'source': r.get('source'),
    } for _, r in upcoming.iterrows()]

    return {
        'events': events,
        'generated_from': os.path.basename(path),
        'file_mtime': datetime.fromtimestamp(os.path.getmtime(path), timezone.utc).isoformat(),
        'total_future_events': int((df['date'] >= today).sum()),
    }


# ---------------------------------------------------------------------------
# 13F institutional positioning
# ---------------------------------------------------------------------------

def load_13f(project_root: str, top_n: int = 8) -> dict:
    """Latest-quarter position changes per tracked fund, biggest moves first."""
    base = os.path.join(project_root, 'historical_data', '13F')
    if not os.path.isdir(base):
        return {'error': '13F directory not found — run extract_13f_holdings.py',
                'funds': []}

    funds = []
    for fund in sorted(os.listdir(base)):
        changes = os.path.join(base, fund, 'changes.csv')
        if not os.path.exists(changes):
            continue
        try:
            df = pd.read_csv(changes)
        except Exception:
            continue
        if df.empty or 'quarter' not in df.columns:
            continue

        latest_q = sorted(df['quarter'].astype(str).unique())[-1]
        q = df[df['quarter'].astype(str) == latest_q].copy()
        q['value_change'] = pd.to_numeric(q.get('value_change'), errors='coerce').fillna(0)
        q['abs_change'] = q['value_change'].abs()
        top = q.sort_values('abs_change', ascending=False).head(top_n)

        funds.append({
            'fund': fund,
            'fund_label': fund.replace('_', ' ').title(),
            'quarter': latest_q,
            'n_positions': int(len(q)),
            'moves': [{
                'ticker_name': str(r.get('name_of_issuer', ''))[:38],
                'action': r.get('action'),
                'shares_change_pct': _safe(r.get('shares_change_pct')),
                'value_change_usd': _safe(r.get('value_change')),
                'current_value_usd': _safe(r.get('current_value')),
            } for _, r in top.iterrows()],
        })

    return {'funds': funds, 'n_funds': len(funds)}
