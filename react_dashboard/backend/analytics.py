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


def _series_label(series_id: str) -> str:
    """Display label for a catalog id, keeping the sub-asset when present."""
    if series_id.startswith('hl/'):
        return f'{series_id[3:].upper()} (Hyperliquid)'
    if '/' in series_id:
        parent, sub = series_id.split('/', 1)
        return f'{_label_for(parent)} — {sub.upper()}'
    return _label_for(series_id)


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


# ---------------------------------------------------------------------------
# Series resolver — the shared access layer for every relationship analytic
# ---------------------------------------------------------------------------
# Correlation, beta, lead/lag and pairs all need the same thing: "give me a
# clean daily series for instrument X". Three shapes exist in the cache:
#
#   1. indicators[key]['historical']            → id = key            (58 series)
#   2. indicators[key]['historical_<sub>']      → id = "key/<sub>"    (sector ETFs, crypto)
#   3. Hyperliquid CSV columns                  → id = "hl/<coin>"    (fallback only)
#
# Shape 3 exists because Hyperliquid history starts 2026-03 and is minutely;
# it is deliberately LAST, so BTC resolves to the 5-year yfinance series from
# 87_crypto_majors rather than a 6-month stub.

_HL_PERPS_CSV = ('historical_data', 'hl_perps.csv')


def build_series_catalog(indicators: dict, project_root: str | None = None) -> dict:
    """{series_id: {label, source, n_obs, start, end}} for everything correlatable."""
    catalog: dict[str, dict] = {}

    for key, val in indicators.items():
        if not isinstance(val, dict) or 'error' in val:
            continue

        s = _clean_series(val.get('historical'))
        if s is not None and len(s) >= 30:
            catalog[key] = {
                'label': _label_for(key), 'category': _category_for(key),
                'source': 'cache', 'n_obs': len(s),
                'start': str(s.index[0])[:10], 'end': str(s.index[-1])[:10],
            }

        for field, raw in val.items():
            if not (isinstance(field, str) and field.startswith('historical_')):
                continue
            sub = field[len('historical_'):]
            sub_s = _clean_series(raw)
            if sub_s is None or len(sub_s) < 30:
                continue
            sid = f'{key}/{sub}'
            catalog[sid] = {
                'label': _series_label(sid),
                'category': _category_for(key),
                'source': 'cache', 'n_obs': len(sub_s),
                'start': str(sub_s.index[0])[:10], 'end': str(sub_s.index[-1])[:10],
            }

    # Hyperliquid CSV fallback for coins with no cached daily series.
    if project_root:
        path = os.path.join(project_root, *_HL_PERPS_CSV)
        if os.path.exists(path):
            try:
                cols = pd.read_csv(path, nrows=0).columns.tolist()
                for c in cols:
                    if not (c.startswith('hl_') and c.endswith('_price')):
                        continue
                    coin = c[len('hl_'):-len('_price')]
                    sid = f'hl/{coin}'
                    # Skip when a longer cached series already covers this asset.
                    if f'87_crypto_majors/{coin}' in catalog:
                        continue
                    catalog[sid] = {
                        'label': f'{coin.upper()} (Hyperliquid)',
                        'category': 'Commodities', 'source': 'hl_csv',
                        'n_obs': None, 'start': None, 'end': None,
                    }
            except Exception:
                pass

    return catalog


_HL_CSV_MEMO: dict = {'mtime': None, 'frame': None}


def _hl_daily_frame(project_root: str) -> pd.DataFrame | None:
    """Hyperliquid perp CSV resampled to daily last-price, memoized on mtime."""
    path = os.path.join(project_root, *_HL_PERPS_CSV)
    if not os.path.exists(path):
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _HL_CSV_MEMO['mtime'] == mtime and _HL_CSV_MEMO['frame'] is not None:
        return _HL_CSV_MEMO['frame']

    try:
        cols = pd.read_csv(path, nrows=0).columns.tolist()
        price_cols = [c for c in cols if c.startswith('hl_') and c.endswith('_price')]
        df = pd.read_csv(path, usecols=['date'] + price_cols)
        df['date'] = pd.to_datetime(df['date'], errors='coerce')
        df = df.dropna(subset=['date']).set_index('date')
        daily = df.resample('D').last().dropna(how='all')
    except Exception:
        return None

    _HL_CSV_MEMO['mtime'] = mtime
    _HL_CSV_MEMO['frame'] = daily
    return daily


def resolve_series(indicators: dict, series_id: str,
                   project_root: str | None = None) -> pd.Series | None:
    """Daily, tz-naive, de-duplicated series for a catalog id."""
    s = None

    if series_id.startswith('hl/'):
        if not project_root:
            return None
        coin = series_id[3:]
        frame = _hl_daily_frame(project_root)
        col = f'hl_{coin}_price'
        if frame is None or col not in frame.columns:
            return None
        s = _clean_series(frame[col])
    elif '/' in series_id:
        key, sub = series_id.split('/', 1)
        val = indicators.get(key)
        if not isinstance(val, dict):
            return None
        s = _clean_series(val.get(f'historical_{sub}'))
    else:
        val = indicators.get(series_id)
        if not isinstance(val, dict):
            return None
        s = _clean_series(val.get('historical'))

    if s is None:
        return None

    try:
        idx = pd.to_datetime(s.index, errors='coerce')
        try:
            idx = idx.tz_localize(None)
        except (TypeError, AttributeError):
            idx = idx.tz_convert(None) if getattr(idx, 'tz', None) else idx
        s = pd.Series(s.values, index=idx.normalize()).dropna()
        s = s[~s.index.duplicated(keep='last')].sort_index()
    except Exception:
        return None

    return s if len(s) >= 30 else None


# ---------------------------------------------------------------------------
# Correlation (Phase 1)
# ---------------------------------------------------------------------------

_MIN_OVERLAP = 30      # refuse to report anything below this
_WEAK_OVERLAP = 60     # report, but flag as thin


def _returns(s: pd.Series) -> pd.Series:
    """Log returns. Correlating price LEVELS is the classic error — two assets
    that merely both trend up score near 1.0 with no co-movement at all."""
    positive = s[s > 0]
    if len(positive) < len(s) * 0.9:
        # Series crosses zero or is negative (spreads, real yields, net flows):
        # log returns are undefined, so use first differences instead.
        return s.diff().dropna()
    return np.log(positive / positive.shift(1)).replace([np.inf, -np.inf], np.nan).dropna()


def correlation_analysis(indicators: dict, series_ids: list[str], window: int = 60,
                         project_root: str | None = None) -> dict:
    """Pairwise correlation matrix + rolling correlation for the first pair.

    Computed on returns, never levels. Every pair reports its own overlap count
    because two series can share a catalog but barely share a calendar.
    """
    if len(series_ids) < 2:
        return {'error': 'Select at least two series to correlate.'}
    if len(series_ids) > 12:
        return {'error': 'Select at most 12 series.'}

    resolved, missing = {}, []
    for sid in series_ids:
        s = resolve_series(indicators, sid, project_root)
        if s is None:
            missing.append(sid)
        else:
            resolved[sid] = _returns(s)

    if len(resolved) < 2:
        return {'error': f'Could not resolve enough series. Missing: {", ".join(missing)}'}

    ids = list(resolved.keys())
    frame = pd.DataFrame(resolved).dropna(how='all')

    matrix, pairs = [], []
    for a in ids:
        row = []
        for b in ids:
            joint = frame[[a, b]].dropna()
            n = len(joint)
            if a == b:
                row.append(1.0)
                continue
            if n < _MIN_OVERLAP:
                row.append(None)
            else:
                r = float(joint[a].corr(joint[b]))
                row.append(_safe(r))
                if ids.index(b) > ids.index(a):
                    pairs.append({
                        'a': a, 'b': b,
                        'a_label': _series_label(a), 'b_label': _series_label(b),
                        'corr': _safe(r), 'n_overlap': n,
                        'quality': 'thin' if n < _WEAK_OVERLAP else 'ok',
                    })
        matrix.append(row)

    # Rolling correlation for the first pair, so the UI always has a series to
    # draw — a static coefficient hides regime changes, which are the signal.
    rolling = None
    a, b = ids[0], ids[1]
    joint = frame[[a, b]].dropna()
    if len(joint) >= window + 5:
        rc = joint[a].rolling(window).corr(joint[b]).dropna()
        if not rc.empty:
            latest = float(rc.iloc[-1])
            mu, sd = float(rc.mean()), float(rc.std())
            rolling = {
                'a': a, 'b': b,
                'a_label': _series_label(a), 'b_label': _series_label(b),
                'window': window,
                'dates': [str(d)[:10] for d in rc.index],
                'values': [_safe(v) for v in rc.values],
                'latest': _safe(latest),
                'mean': _safe(mu), 'stdev': _safe(sd),
                'z_vs_own_history': _safe((latest - mu) / sd) if sd else None,
                'min': _safe(rc.min()), 'max': _safe(rc.max()),
            }

    warnings_out = []
    if missing:
        warnings_out.append(f'Unresolved: {", ".join(missing)}')
    thin = [p for p in pairs if p['quality'] == 'thin']
    if thin:
        warnings_out.append(
            f'{len(thin)} pair(s) have fewer than {_WEAK_OVERLAP} overlapping days — '
            f'treat those coefficients as indicative only.')

    return {
        'ids': ids,
        'labels': [_series_label(i) for i in ids],
        'matrix': matrix,
        'pairs': sorted(pairs, key=lambda p: abs(p['corr'] or 0), reverse=True),
        'rolling': rolling,
        'basis': 'log returns (first differences for series that cross zero)',
        'window': window,
        'warnings': warnings_out,
    }


# ---------------------------------------------------------------------------
# Phase 2 — beta (hedge ratio) and lead/lag (cross-correlation)
# ---------------------------------------------------------------------------

def _aligned_returns(indicators: dict, a: str, b: str, project_root: str | None):
    sa = resolve_series(indicators, a, project_root)
    sb = resolve_series(indicators, b, project_root)
    if sa is None or sb is None:
        missing = [x for x, s in ((a, sa), (b, sb)) if s is None]
        return None, {'error': f'Could not resolve: {", ".join(missing)}'}
    frame = pd.DataFrame({'a': _returns(sa), 'b': _returns(sb)}).dropna()
    if len(frame) < _MIN_OVERLAP:
        return None, {'error': f'Only {len(frame)} overlapping days — need at least {_MIN_OVERLAP}.'}
    return frame, None


def beta_analysis(indicators: dict, a: str, b: str, window: int = 60,
                  project_root: str | None = None) -> dict:
    """Return sensitivity of `a` to `b` (and the reverse), full-sample and rolling.

    Correlation says how reliably two things move together; beta says by how
    much — which is the number a hedge actually needs. β(a on b) = cov/var(b):
    "a 1% move in b comes with a β% move in a". R² is the share of a's variance
    that b explains; a high β with a low R² is a loose relationship, not a
    hedge.
    """
    frame, err = _aligned_returns(indicators, a, b, project_root)
    if err:
        return err
    ra, rb = frame['a'], frame['b']
    n = len(frame)

    cov = float(ra.cov(rb))
    var_a, var_b = float(ra.var()), float(rb.var())
    if not var_a or not var_b:
        return {'error': 'One series has zero variance over the overlap.'}
    corr = float(ra.corr(rb))
    beta_ab = cov / var_b            # a on b
    beta_ba = cov / var_a            # b on a
    alpha_ab = float(ra.mean() - beta_ab * rb.mean())

    rolling = None
    if n >= window + 5:
        rb_var = rb.rolling(window).var()
        rbeta = (ra.rolling(window).cov(rb) / rb_var).replace([np.inf, -np.inf], np.nan).dropna()
        if not rbeta.empty:
            latest, mu, sd = float(rbeta.iloc[-1]), float(rbeta.mean()), float(rbeta.std())
            rolling = {
                'window': window,
                'dates': [str(d)[:10] for d in rbeta.index],
                'values': [_safe(v) for v in rbeta.values],
                'latest': _safe(latest), 'mean': _safe(mu), 'stdev': _safe(sd),
                'z_vs_own_history': _safe((latest - mu) / sd) if sd else None,
                'min': _safe(rbeta.min()), 'max': _safe(rbeta.max()),
            }

    return {
        'a': a, 'b': b, 'a_label': _series_label(a), 'b_label': _series_label(b),
        'n_overlap': n,
        'beta_a_on_b': _safe(beta_ab),
        'beta_b_on_a': _safe(beta_ba),
        'alpha_daily_pct_a_on_b': _safe(alpha_ab * 100),
        'r_squared': _safe(corr * corr),
        'corr': _safe(corr),
        'hedge_note': (f'A 1% move in {_series_label(b)} has come with a '
                       f'{beta_ab:+.2f}% move in {_series_label(a)} '
                       f'(R² {corr*corr:.2f} — {"tight" if corr*corr >= 0.5 else "loose" if corr*corr >= 0.2 else "weak"} relationship).'),
        'rolling': rolling,
        'basis': 'log returns (first differences for series that cross zero)',
    }


def lead_lag_analysis(indicators: dict, a: str, b: str, max_lag: int = 10,
                      project_root: str | None = None) -> dict:
    """Cross-correlation of `a` with `b` shifted by k days, k in [-max_lag, max_lag].

    corr(a_t, b_{t+k}): a positive peak lag means today's `a` correlates with
    `b` k days LATER, i.e. a leads b. The noise band is ±2/√n; a peak that does
    not beat the lag-0 correlation by more than the band is not a lead — it is
    the same-day relationship plus sampling error, and the verdict says so.
    """
    frame, err = _aligned_returns(indicators, a, b, project_root)
    if err:
        return err
    ra, rb = frame['a'], frame['b']
    n = len(frame)
    band = 2.0 / math.sqrt(n)

    profile = []
    for k in range(-max_lag, max_lag + 1):
        shifted = rb.shift(-k)           # value of b at t+k, aligned to t
        joint = pd.DataFrame({'a': ra, 'b': shifted}).dropna()
        c = float(joint['a'].corr(joint['b'])) if len(joint) >= _MIN_OVERLAP else None
        profile.append({'lag': k, 'corr': _safe(c), 'n': int(len(joint))})

    valid = [p for p in profile if p['corr'] is not None]
    lag0 = next((p['corr'] for p in valid if p['lag'] == 0), None)
    peak = max(valid, key=lambda p: abs(p['corr'])) if valid else None

    if peak is None or lag0 is None:
        verdict, leader = 'insufficient data', None
    elif peak['lag'] == 0 or abs(peak['corr']) - abs(lag0) <= band:
        verdict = (f'No lead/lag beyond noise: the strongest relationship is same-day '
                   f'(lag 0 = {lag0:+.3f}); off-zero peaks fall inside the ±{band:.3f} band.')
        leader = None
    else:
        leader = _series_label(a) if peak['lag'] > 0 else _series_label(b)
        follower = _series_label(b) if peak['lag'] > 0 else _series_label(a)
        verdict = (f'{leader} leads {follower} by {abs(peak["lag"])} day(s): '
                   f'corr {peak["corr"]:+.3f} at lag {peak["lag"]:+d} vs {lag0:+.3f} same-day '
                   f'(band ±{band:.3f}).')

    return {
        'a': a, 'b': b, 'a_label': _series_label(a), 'b_label': _series_label(b),
        'n_overlap': n, 'max_lag': max_lag,
        'noise_band': _safe(band),
        'lag0_corr': _safe(lag0),
        'peak': peak,
        'leader': leader,
        'verdict': verdict,
        'profile': profile,
        'convention': 'corr(a_t, b_{t+k}); positive lag ⇒ a leads b',
    }


# ---------------------------------------------------------------------------
# Event study around macro catalysts
# ---------------------------------------------------------------------------

_EVENT_HISTORY = ('historical_data', 'macro_event_history.json')


def load_event_history(project_root: str) -> dict:
    """{event name: [dates]} written by macro_calendar_extractor.refresh_calendar()."""
    import json
    path = os.path.join(project_root, *_EVENT_HISTORY)
    if not os.path.exists(path):
        return {'error': 'macro_event_history.json not found — run '
                         'data_extractors.macro_calendar_extractor.refresh_calendar()'}
    try:
        with open(path) as f:
            doc = json.load(f)
    except Exception as e:
        return {'error': f'Failed to read event history: {e}'}
    events = doc.get('events') or {}
    return {
        'events': {k: v for k, v in events.items() if v},
        'since': doc.get('since'),
        'generated_at': doc.get('generated_at'),
        'counts': {k: len(v) for k, v in events.items()},
    }


def event_study(indicators: dict, event_name: str, target_id: str, window: int = 3,
                project_root: str | None = None) -> dict:
    """How `target_id` has behaved around every past `event_name` date.

    For each event, take the target's daily returns from t=-window to
    t=+window (t=0 is the first trading day on or after the event date) and
    accumulate them. Report the average path, the event-day return
    distribution, and — the load-bearing comparison — event-day absolute moves
    against a normal day. Without that baseline, "gold moved 0.6% on CPI days"
    means nothing; if gold moves 0.6% on every day, CPI is not a catalyst for
    gold.

    This is UNCONDITIONAL on the surprise: a CPI beat and a CPI miss land in
    the same bucket, so the mean path is often near zero while the absolute
    move is large. That asymmetry is the finding, not a flaw.
    """
    if not project_root:
        return {'error': 'project_root required'}
    hist = load_event_history(project_root)
    if 'error' in hist:
        return hist
    dates = hist['events'].get(event_name)
    if not dates:
        return {'error': f"No history for event '{event_name}'. "
                         f"Available: {', '.join(sorted(hist['events']))}"}

    s = resolve_series(indicators, target_id, project_root)
    if s is None:
        return {'error': f'Could not resolve target {target_id}'}
    r = _returns(s)
    idx = r.index
    if len(r) < 2 * window + 30:
        return {'error': 'Target series too short for this window.'}

    w = int(window)
    paths, r0s, rows, skipped = [], [], [], 0
    for d in dates:
        ts = pd.Timestamp(d)
        pos = int(idx.searchsorted(ts))
        if pos >= len(idx) or (idx[pos] - ts).days > 4:
            skipped += 1
            continue
        if pos - w < 0 or pos + w >= len(idx):
            skipped += 1
            continue
        seg = r.iloc[pos - w: pos + w + 1].to_numpy(dtype=float)
        cum = np.cumsum(seg)
        paths.append(cum)
        r0s.append(seg[w])
        rows.append({
            'event_date': d,
            'trading_day': str(idx[pos])[:10],
            'event_day_pct': _safe((math.exp(seg[w]) - 1) * 100),
            'window_pct': _safe((math.exp(cum[-1]) - 1) * 100),
        })

    if len(paths) < 5:
        return {'error': f'Only {len(paths)} usable events for {event_name} — need at least 5.'}

    P = np.array(paths)
    r0 = np.array(r0s)
    to_pct = lambda x: (np.exp(x) - 1.0) * 100.0
    mean_path = to_pct(P.mean(axis=0))
    median_path = to_pct(np.median(P, axis=0))

    baseline_abs = float(r.abs().mean())
    event_abs = float(np.abs(r0).mean())
    baseline_abs_pct = (math.exp(baseline_abs) - 1) * 100
    event_abs_pct = (math.exp(event_abs) - 1) * 100
    ratio = (event_abs / baseline_abs) if baseline_abs else None

    return {
        'event': event_name,
        'target': {'id': target_id, 'label': _series_label(target_id)},
        'window': w,
        'n_events': int(len(paths)),
        'n_skipped': int(skipped),
        'first_event': rows[0]['event_date'],
        'last_event': rows[-1]['event_date'],
        'offsets': list(range(-w, w + 1)),
        'mean_path_pct': [_safe(v) for v in mean_path],
        'median_path_pct': [_safe(v) for v in median_path],
        'event_day': {
            'mean_pct': _safe((math.exp(r0.mean()) - 1) * 100),
            'median_pct': _safe((math.exp(np.median(r0)) - 1) * 100),
            'hit_rate_pct': _safe((r0 > 0).mean() * 100),
            'mean_abs_pct': _safe(event_abs_pct),
            'baseline_mean_abs_pct': _safe(baseline_abs_pct),
            'abs_move_ratio': _safe(ratio),
            'stdev_pct': _safe((math.exp(r0.std()) - 1) * 100),
        },
        'window_end': {
            'mean_pct': _safe(float(mean_path[-1])),
            'hit_rate_pct': _safe((P[:, -1] > 0).mean() * 100),
        },
        'recent_events': rows[-8:][::-1],
        'caveats': [
            'Unconditional on the surprise — beats and misses share a bucket, so the mean '
            'is muted while the absolute move is the informative number.',
            f'{len(paths)} events is a small sample; treat hit rates as indicative.',
        ],
    }
