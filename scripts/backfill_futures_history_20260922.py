#!/usr/bin/env python3
"""One-off: build the tradable-instrument history the CC pipeline needs to execute VIX and 10Y
views ("instrument realism", CC backfill/ROADMAP.md Phase 2), then leave the daily appends to
data_extractors/futures_history_extractors.extract_futures_history().

Files (historical_data/, schemas and rules in the module docstring):
  vx_cfe_curve.csv      CBOE VX monthly futures, 1st/2nd/3rd contract per trade date, from 2014-01-02
  vx_front_ohlcv.csv    front-month VX, rolled 5 sessions before expiry, FORWARD-adjusted, from 2021-01-04
  ief_ohlcv.csv         IEF OHLCV + distributions + forward total-return adjclose, from 2021-01-04
  zn_futures_ohlcv.csv  Yahoo ZN=F, LTD sessions omitted, FORWARD-adjusted, from 2021-01-04
                        (+ .zn_futures_ohlcv.rolls.json: every roll gap, measured or estimated)

Per file:
  missing          -> created with the full history (the only way the files come into being;
                      the daily updater refuses to bootstrap).
  present          -> append-only, exactly like the daily updater: the new finished days,
                      continuing the file's own roll_adjust_cum / adjclose. The from-scratch build
                      is compared with the stored rows and differences are REPORTED, not written.
  --rebuild FILE   -> explicit repair: the file (and, for ZN, its roll log) is rewritten from the
                      from-scratch build. This rewrites history; use it only to fix a known defect.
Nothing is written without --apply. With --apply, a present file is first copied to
.deploy_backup_20260922/data/ next to the data directory (the first, pristine copy is kept),
every write holds the collectors' per-file lock (extract_historical_data._csv_lock) and goes
through a temp file + rename, the column contracts are declared
(extract_historical_data.declare_columns) and a manifest of the run is appended to
.deploy_backup_20260922/data/futures_history.backfill_manifest.json.

Sources are read with plain GETs: CBOE's listing + one CSV per monthly contract (~0.7 s apart;
--raw-cache DIR keeps copies and re-reads contracts that expired over a week ago from it),
and Yahoo via yf_safe (ZN=F, IEF, and the live ZN contract of each roll Yahoo still lists).
A CBOE refusal (401/403/429 or a non-CSV body) stops the VX part; nothing is retried harder.

The report (always printed; --report-json to save it) covers: row counts, ranges, roll dates and
gaps, sample rows, data anomalies, the calendar check against CBOE's own sessions, the evidence
for the 5-session VX roll, how VX front tracks VIX spot, and how ZN and IEF daily returns track
-(duration x change in the 10Y yield) (--yield-file, default historical_data/10y_treasury_yield.csv).

  python scripts/backfill_futures_history_20260922.py                                  # dry run
  python scripts/backfill_futures_history_20260922.py --apply
  python scripts/backfill_futures_history_20260922.py --data-dir /path/to/copy --raw-cache /path/cache --apply
  python scripts/backfill_futures_history_20260922.py --rebuild zn_futures_ohlcv.csv --apply   # repair
  python scripts/backfill_futures_history_20260922.py --only zn --zn-allow-estimate --apply     # unstick a ZN roll
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import statistics
import sys
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import extract_historical_data as ehd  # noqa: E402
from data_extractors import futures_history_extractors as fhe  # noqa: E402

BACKUP_TAG = '.deploy_backup_20260922'
MANIFEST = 'futures_history.backfill_manifest.json'
ORDER = [fhe.VX_CURVE_FILE, fhe.VX_FRONT_FILE, fhe.IEF_FILE, fhe.ZN_FILE]
GROUP = {fhe.VX_CURVE_FILE: 'vx', fhe.VX_FRONT_FILE: 'vx', fhe.IEF_FILE: 'ief', fhe.ZN_FILE: 'zn'}


def _d(s):
    return date.fromisoformat(s)


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as fh:
        h.update(fh.read())
    return h.hexdigest()


# ── builds (from scratch) ─────────────────────────────────────────────────────────────────

def build_vx(cutoff, starts, cache_dir, report):
    src = fhe.CboeVX(cache_dir=cache_dir)
    listing = src.listing()
    expiries = list(listing)
    lo = min(starts[fhe.VX_CURVE_FILE], starts[fhe.VX_FRONT_FILE])
    later = [e for e in expiries if e > cutoff][:3]
    needed = [e for e in expiries if e > lo - timedelta(days=40) and e <= later[-1]]
    bars = {}
    for e in needed:
        bars[e] = src.contract(e, listing[e], cutoff)
    report['vx_source'] = {'listing_monthly_contracts': len(expiries), 'contracts_used': len(needed),
                           'http_requests': src.requests, 'first_expiry': str(needed[0]), 'last_expiry': str(needed[-1])}
    sessions = fhe.vx_sessions(bars, None, cutoff)
    curve, stop_c = fhe.vx_curve_rows([d for d in sessions if d >= starts[fhe.VX_CURVE_FILE]], expiries, bars)
    front, rolls, stop_f = fhe.vx_front_rows([d for d in sessions if d >= starts[fhe.VX_FRONT_FILE]], expiries, bars)
    return {'listing': listing, 'expiries': expiries, 'bars': bars, 'sessions': sessions,
            fhe.VX_CURVE_FILE: {'rows': curve, 'stop': stop_c},
            fhe.VX_FRONT_FILE: {'rows': front, 'stop': stop_f, 'rolls': rolls}}


def build_yahoo(cutoff, starts, groups):
    out = {}
    ief_raw, ief_nan = fhe.fetch_yahoo(fhe.IEF_SYMBOL, starts[fhe.IEF_FILE] - timedelta(days=400))
    ief_all, ief_off = fhe.final_bars(ief_raw, cutoff)
    out['ief_bars_all'] = ief_all
    if 'ief' in groups:
        ief = {d: b for d, b in ief_all.items() if d >= starts[fhe.IEF_FILE]}
        rows, stop = fhe.ief_rows(ief)
        out[fhe.IEF_FILE] = {'rows': rows, 'stop': stop, 'dropped_nan': ief_nan, 'dropped_non_trading': ief_off,
                             'bars': ief}
    if 'zn' in groups:
        zn_raw, zn_nan = fhe.fetch_yahoo(fhe.ZN_GENERIC, starts[fhe.ZN_FILE] - timedelta(days=400))
        zn_all, zn_off = fhe.final_bars(zn_raw, cutoff)
        zn = {d: b for d, b in zn_all.items() if d >= starts[fhe.ZN_FILE]}
        # beta windows need history before the file's first row, so estimates see zn_all
        gaps = fhe.zn_gaps(zn_all, starts[fhe.ZN_FILE] - timedelta(days=1), ief=ief_all, allow_estimate=True)
        gaps = {k: v for k, v in gaps.items() if _d(v['last_old_date']) >= starts[fhe.ZN_FILE]}
        rows, rolls, stop = fhe.zn_rows(zn, None, gaps)
        ltd_omitted = [d for d in zn if fhe.zn_contract_on(d) is None]
        out[fhe.ZN_FILE] = {'rows': rows, 'rolls': rolls, 'stop': stop, 'dropped_nan': zn_nan,
                            'dropped_non_trading': zn_off, 'ltd_omitted': ltd_omitted, 'bars': zn,
                            'gaps': gaps}
    return out


# ── incremental continuation of an existing file (what the daily updater would append) ────

def continue_rows(fname, existing, vx, yh, zn_allow_estimate=False):
    if fname == fhe.VX_CURVE_FILE:
        rows, stop = fhe.vx_curve_rows(vx['sessions'], vx['expiries'], vx['bars'], _d(existing[-1]['date']))
        return rows, stop, []
    if fname == fhe.VX_FRONT_FILE:
        rows, rolls, stop = fhe.vx_front_rows(vx['sessions'], vx['expiries'], vx['bars'], fhe.vx_front_state(existing))
        return rows, stop, rolls
    if fname == fhe.IEF_FILE:
        rows, stop = fhe.ief_rows(yh[fname]['bars'], fhe.ief_state(existing))
        return rows, stop, []
    last = _d(existing[-1]['date'])
    # measured only, like the updater - unless the operator explicitly allows an IEF estimate
    gaps = fhe.zn_gaps(yh[fname]['bars'], last, ief=yh.get('ief_bars_all'), allow_estimate=zn_allow_estimate)
    rows, rolls, stop = fhe.zn_rows(yh[fname]['bars'], fhe.zn_state(existing), gaps)
    return rows, stop, rolls


def compare(existing, built, columns):
    """Stored rows vs the from-scratch build, by date: (same, differing dates, stored-only, built-only)."""
    b = {r['date']: r for r in built}
    same, diff, only_stored = 0, [], []
    for r in existing:
        x = b.get(r['date'])
        if x is None:
            only_stored.append(r['date'])
        elif all(r.get(c) == x.get(c) for c in columns):
            same += 1
        else:
            diff.append(r['date'])
    stored = {r['date'] for r in existing}
    return same, diff, only_stored, [d for d in b if d not in stored and d <= (existing[-1]['date'] if existing else '')]


# ── evidence / analysis ───────────────────────────────────────────────────────────────────

def calendar_check(vx):
    sessions = set(d for b in vx['bars'].values() for d in b)
    lo, hi = min(sessions), max(sessions)
    rule_only, data_only = [], []
    x = lo
    while x <= hi:
        t = fhe.is_trading_day(x)
        if t and x not in sessions:
            rule_only.append(str(x))
        if not t and x in sessions:
            data_only.append(str(x))
        x += timedelta(days=1)
    return {'range': [str(lo), str(hi)], 'cboe_sessions': len(sessions),
            'rule_calendar_sessions_cboe_lacks': rule_only, 'cboe_sessions_rule_calendar_lacks': data_only}


def roll_evidence(vx, since=date(2014, 1, 1)):
    exps = [e for e in vx['expiries'] if e in vx['bars']]
    sessions = sorted(set(d for b in vx['bars'].values() for d in b))
    cut = sessions[-1]
    vol_x, oi_x, share = [], [], {}
    for e, e2 in zip(exps, exps[1:]):
        if e < since or e > cut:
            continue
        v = o = None
        for d in [d for d in sessions if d < e and fhe.sessions_after(d, e) <= 20]:
            f, s = vx['bars'][e].get(d), vx['bars'][e2].get(d)
            if not f or not s:
                continue
            k = fhe.sessions_after(d, e)
            if v is None and (s['volume'] or 0) > (f['volume'] or 0):
                v = k
            if o is None and (s['open_interest'] or 0) > (f['open_interest'] or 0):
                o = k
            if e >= date(2021, 1, 1) and k <= 10 and (f['volume'] or 0) + (s['volume'] or 0) > 0:
                share.setdefault(k, []).append(f['volume'] / (f['volume'] + s['volume']))
        if v is not None:
            vol_x.append(v)
        if o is not None:
            oi_x.append(o)
    q = lambda xs: [round(x, 1) for x in statistics.quantiles(xs, n=4)] if len(xs) > 3 else None
    return {'expiries': len(vol_x), 'volume_crossover_sessions_before_expiry': {'median': statistics.median(vol_x), 'quartiles': q(vol_x)},
            'oi_crossover_sessions_before_expiry': {'median': statistics.median(oi_x), 'quartiles': q(oi_x)},
            'front_volume_share_by_sessions_left_2021_on': {k: round(statistics.median(v), 2) for k, v in sorted(share.items())}}


def read_series(path, col):
    out = {}
    with open(path, newline='') as fh:
        for r in csv.DictReader(fh):
            v = fhe._num(r.get(col))
            if v is not None and r.get('date'):
                out[_d(r['date'][:10])] = v
    return out


def tracking(yh, yield_file, years=3):
    if not os.path.exists(yield_file):
        return {'error': f'{yield_file} not found'}
    y = read_series(yield_file, '10y_yield')
    res = {'yield_file': yield_file, 'yield_last': str(max(y))}
    inst = {}
    if fhe.IEF_FILE in yh:
        rows = yh[fhe.IEF_FILE]['rows']
        inst['IEF'] = dict(prices={_d(r['date']): float(r['close']) for r in rows},
                           dividends={_d(r['date']): float(r['dividend']) for r in rows if float(r['dividend'])},
                           raw=None, breaks=())
    if fhe.ZN_FILE in yh:
        rows = yh[fhe.ZN_FILE]['rows']
        inst['ZN'] = dict(prices={_d(r['date']): float(r['close']) for r in rows},
                          raw={_d(r['date']): float(r['close']) - float(r['roll_adjust_cum']) for r in rows},
                          dividends=None, breaks=[_d(x['ltd']) for x in yh[fhe.ZN_FILE]['rolls']])
    for name, s in inst.items():
        end = min(max(s['prices']), max(y))
        start = end - timedelta(days=365 * years)
        out = {}
        for label, step in (('daily', 1), ('weekly_5_session', 5)):
            out[label] = fhe.duration_tracking(s['prices'], y, start, end, breaks=s['breaks'], raw=s['raw'],
                                               dividends=s['dividends'], step=step)
        by_year = {}
        a = start
        while a < end:
            b = min(a + timedelta(days=365), end)
            by_year[f'{a}..{b}'] = fhe.duration_tracking(s['prices'], y, a, b, breaks=s['breaks'], raw=s['raw'],
                                                         dividends=s['dividends'])
            a = b
        out['daily_by_year'] = by_year
        # a 1 bp rise in the 10Y moves the instrument by D * 0.01 % of its price
        last = max(s['prices'])
        px = (s['raw'] or s['prices'])[last]
        d_eff = out['daily']['effective_duration'] if out['daily'] else None
        if d_eff:
            out['per_bp_at_last_price'] = {'price': px, 'pct': round(d_eff / 100, 4),
                                           'points': round(px * d_eff / 1e4, 4)}
            if name == 'ZN':
                out['per_bp_at_last_price']['usd_per_contract'] = round(px * d_eff / 1e4 * 1000, 1)
        res[name] = out
    return res


def vx_vs_vix(vx_front_rows, vix_file, years=3):
    if not os.path.exists(vix_file):
        return {'error': f'{vix_file} not found'}
    vix = read_series(vix_file, 'vix_spot')
    f = {_d(r['date']): r for r in vx_front_rows}
    end = min(max(f), max(vix))
    start = end - timedelta(days=365 * years)
    common = sorted(d for d in f if d in vix and start <= d <= end)
    xs, ys, buckets = [], [], {'dte<=14': ([], []), '15-28': ([], []), 'dte>28': ([], [])}
    for a, b in zip(common, common[1:]):
        dy = float(f[b]['settle']) - float(f[a]['settle'])       # adjusted: a roll day is the new contract's own change
        dx = vix[b] - vix[a]
        xs.append(dx)
        ys.append(dy)
        dte = int(f[b]['days_to_expiry'])
        k = 'dte<=14' if dte <= 14 else '15-28' if dte <= 28 else 'dte>28'
        buckets[k][0].append(dx)
        buckets[k][1].append(dy)
    slope, icpt, r2, sd = fhe._ols(xs, ys)
    out = {'window': [str(common[0]), str(common[-1])], 'n': len(xs), 'beta_vx_front_on_vix_spot': round(slope, 3),
           'r2': round(r2, 3), 'resid_sd_pts': round(sd, 3)}
    for k, (bx, by) in buckets.items():
        if len(bx) > 30:
            s2, _, r22, _ = fhe._ols(bx, by)
            out[f'beta_{k}'] = {'n': len(bx), 'beta': round(s2, 3), 'r2': round(r22, 3)}
    return out


def anomalies_ohlc(rows, prefix=''):
    blank, bad = 0, []
    for r in rows:
        v = [r.get(prefix + k) for k in ('open', 'high', 'low', 'close')]
        if any(x == '' for x in v):
            blank += 1
            continue
        o, h, lo, c = map(float, v)
        if h < max(o, c) - 1e-9 or lo > min(o, c) + 1e-9 or h < lo:
            bad.append(r['date'])
    return {'rows_without_ohlc': blank, 'ohlc_inconsistent': len(bad), 'ohlc_inconsistent_dates': bad[:10]}


def summarize(fname, rows, info):
    s = {'rows': len(rows), 'first': rows[0]['date'] if rows else None, 'last': rows[-1]['date'] if rows else None,
         'sample_first': rows[:2], 'sample_last': rows[-3:], 'stop': info.get('stop')}
    if fname == fhe.VX_CURVE_FILE:
        s['anomalies'] = {f'vx{k}': anomalies_ohlc(rows, f'vx{k}_') for k in (1, 2, 3)}
    else:
        s['anomalies'] = anomalies_ohlc(rows)
    if fname in (fhe.VX_FRONT_FILE, fhe.ZN_FILE):
        rolls = info.get('rolls') or []
        s['rolls'] = len(rolls)
        key = 'first_date' if fname == fhe.VX_FRONT_FILE else 'first_new_date'
        s['roll_first_dates_last_8'] = [r[key] for r in rolls[-8:]]
        s['roll_adjust_cum_last'] = rows[-1]['roll_adjust_cum'] if rows else None
        if fname == fhe.VX_FRONT_FILE and rows:
            adj = [float(r['settle']) for r in rows]
            s['adjusted_settle_min_max'] = [min(adj), max(adj)]
            s['rows_with_adjusted_settle_le_0'] = sum(a <= 0 for a in adj)
            s['gap_mean'] = round(statistics.fmean(r['gap'] for r in rolls), 4) if rolls else None
        if fname == fhe.ZN_FILE:
            s['roll_methods'] = {m: sum(r['method'] == m for r in rolls) for m in sorted({r['method'] for r in rolls})}
            s['ltd_sessions_omitted'] = [str(d) for d in info.get('ltd_omitted', [])]
            s['rolls_detail'] = [{k: r.get(k) for k in ('ltd', 'old', 'new', 'last_old_date', 'first_new_date', 'gap',
                                                        'method', 'volume_ratio', 'est_error_sd_pts', 'roll_adjust_cum')}
                                 for r in rolls]
            s['zero_volume_rows'] = sum(r['volume'] in ('', '0') for r in rows)
    if fname in (fhe.ZN_FILE, fhe.IEF_FILE):
        s['dropped_nan_bars'] = [str(d) for d in info.get('dropped_nan', []) if str(d) >= (rows[0]['date'] if rows else '')]
        s['dropped_non_trading_bars'] = [str(d) for d in info.get('dropped_non_trading', []) if str(d) >= (rows[0]['date'] if rows else '')]
    if fname == fhe.IEF_FILE:
        s['distributions'] = sum(float(r['dividend']) > 0 for r in rows)
    return s


# ── writes ────────────────────────────────────────────────────────────────────────────────

def backup(path, backup_dir):
    os.makedirs(backup_dir, exist_ok=True)
    dst = os.path.join(backup_dir, os.path.basename(path))
    if os.path.exists(dst):
        return dst, False
    shutil.copy2(path, dst)
    return dst, True


def rewrite(path, columns, rows, pre_write=None):
    """Explicit repair: replace the whole file (under its lock, atomically)."""
    with ehd._csv_lock(path):
        if pre_write:
            pre_write(rows)
        ehd._atomic_write_text(path, fhe._line(columns) + ''.join(fhe._line([r[c] for c in columns]) for r in rows))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='write (default: dry run, report only)')
    ap.add_argument('--data-dir', default=os.path.join(ROOT, ehd.OUTPUT_DIR),
                    help="directory for the CSVs (default: the repo's historical_data/)")
    ap.add_argument('--only', default='vx,ief,zn', help='comma list of vx, ief, zn (default all)')
    ap.add_argument('--rebuild', nargs='*', default=[], choices=ORDER, metavar='FILE',
                    help='explicit repair: rewrite these files from the from-scratch build')
    ap.add_argument('--raw-cache', help='keep CBOE raw files here; expired contracts are re-read from it')
    ap.add_argument('--zn-allow-estimate', action='store_true',
                    help='append mode only: if a ZN roll gap cannot be measured (the new contract is not on '
                         'Yahoo), estimate it from IEF instead of waiting; recorded as estimated_ief in the roll log')
    ap.add_argument('--yield-file', default=os.path.join(ROOT, ehd.OUTPUT_DIR, '10y_treasury_yield.csv'))
    ap.add_argument('--vix-file', default=os.path.join(ROOT, ehd.OUTPUT_DIR, 'vix_futures_curve.csv'),
                    help='VIX SPOT history (vix_futures_curve.csv holds spot only) for the VX-vs-VIX beta')
    ap.add_argument('--report-json', help='also write the full report here')
    for f, key in ((fhe.VX_CURVE_FILE, 'start-curve'), (fhe.VX_FRONT_FILE, 'start-front'),
                   (fhe.ZN_FILE, 'start-zn'), (fhe.IEF_FILE, 'start-ief')):
        ap.add_argument(f'--{key}', type=date.fromisoformat, default=fhe.DEFAULT_START[f],
                        help=f'first date of a from-scratch {f} (default {fhe.DEFAULT_START[f]})')
    a = ap.parse_args()
    groups = {g.strip() for g in a.only.split(',') if g.strip()}
    if not groups <= {'vx', 'ief', 'zn'}:
        ap.error('--only takes vx, ief, zn')
    starts = {fhe.VX_CURVE_FILE: a.start_curve, fhe.VX_FRONT_FILE: a.start_front, fhe.ZN_FILE: a.start_zn,
              fhe.IEF_FILE: a.start_ief}
    data_dir = os.path.abspath(a.data_dir)
    if not os.path.isdir(data_dir):
        ap.error(f'--data-dir {data_dir} does not exist')
    backup_dir = os.path.join(os.path.dirname(data_dir), BACKUP_TAG, 'data')
    cutoff = fhe.final_cutoff()
    run_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    report = {'run_at': run_at, 'data_dir': data_dir, 'final_cutoff_exclusive': str(cutoff), 'apply': a.apply,
              'files': {}}
    print(f'[backfill] data dir {data_dir}; bars dated before {cutoff} (New York) are final')

    built, vx, yh = {}, None, {}
    if 'vx' in groups:
        try:
            vx = build_vx(cutoff, starts, a.raw_cache, report)
            built[fhe.VX_CURVE_FILE] = vx[fhe.VX_CURVE_FILE]
            built[fhe.VX_FRONT_FILE] = vx[fhe.VX_FRONT_FILE]
            report['calendar_check'] = calendar_check(vx)
            report['vx_roll_evidence'] = roll_evidence(vx)
            report['vx_front_vs_vix_spot'] = vx_vs_vix(vx[fhe.VX_FRONT_FILE]['rows'], a.vix_file)
        except fhe.SourceBlocked as e:
            print(f'  ❌ CBOE BLOCKED: {e}\n  !!! VX files NOT built. Fallback: VIXY via yfinance (not done automatically)')
            report['vx_blocked'] = str(e)
    if groups & {'ief', 'zn'}:
        yh = build_yahoo(cutoff, starts, groups)
        for f in (fhe.IEF_FILE, fhe.ZN_FILE):
            if f in yh:
                built[f] = yh[f]
        report['duration_tracking'] = tracking(yh, a.yield_file)

    plans = {}
    for f in ORDER:
        if f not in built:
            continue
        path = os.path.join(data_dir, f)
        header, existing, _ = fhe.read_table(path)
        info = built[f]
        rep = summarize(f, info['rows'], info)
        if not existing:
            plans[f] = ('create', info['rows'], info.get('rolls'))
        elif f in a.rebuild:
            plans[f] = ('rebuild', info['rows'], info.get('rolls'))
        else:
            if header != fhe.COLUMNS[f]:
                raise SystemExit(f'{f}: header {header} differs from the schema; --rebuild it or fix by hand')
            rows, stop, rolls = continue_rows(f, existing, vx, yh, a.zn_allow_estimate)
            same, diff, only_stored, missing = compare(existing, info['rows'], fhe.COLUMNS[f])
            rep['existing'] = {'rows': len(existing), 'last': existing[-1]['date'], 'identical_to_scratch_build': same,
                               'differ_from_scratch_build': diff[:20], 'n_differ': len(diff),
                               'stored_only': only_stored[:20], 'scratch_only': missing[:20]}
            plans[f] = ('append', rows, rolls)
            rep['append_rows'] = len(rows)
            rep['append_stop'] = stop
        rep['plan'] = plans[f][0]
        report['files'][f] = rep

    _print(report)
    if a.report_json:
        with open(a.report_json, 'w') as fh:
            json.dump(report, fh, indent=1, default=str)
    if not a.apply:
        print('\n  DRY RUN - nothing written. ' + '; '.join(f'{f}: {p[0]} {len(p[1])} row(s)' for f, p in plans.items())
              + '. Re-run with --apply.')
        return 0

    written = {}
    for f in ORDER:
        if f not in plans:
            continue
        kind, rows, rolls = plans[f]
        path = os.path.join(data_dir, f)
        if kind in ('append', 'rebuild') and os.path.exists(path):
            dst, fresh = backup(path, backup_dir)
            print(f'    {"backed up" if fresh else "backup already present"}: {dst}')
            if f == fhe.ZN_FILE and os.path.exists(os.path.join(data_dir, fhe.ZN_ROLL_LOG)):
                backup(os.path.join(data_dir, fhe.ZN_ROLL_LOG), backup_dir)
        pre = None
        if f == fhe.ZN_FILE and rolls:
            def pre(_new, rolls=rolls, kind=kind):
                rl = fhe.load_roll_log(data_dir) if kind == 'append' else {'file': fhe.ZN_FILE, 'rolls': []}
                rl['rolls'].extend(rolls)
                rl['updated_at'] = run_at
                rl['note'] = ('gap = old - new at last_old_date; method measured = from the new contract\'s own '
                              'Yahoo history, estimated_ief = backed out of IEF (see futures_history_extractors.'
                              'estimate_zn_gap); LTD sessions are omitted from the CSV')
                fhe._atomic_json(os.path.join(data_dir, fhe.ZN_ROLL_LOG), rl)
        if kind == 'rebuild':
            rewrite(path, fhe.COLUMNS[f], rows, pre)
            n = len(rows)
        else:
            new, _ = fhe.append_rows(path, fhe.COLUMNS[f], lambda existing, rows=rows: rows, pre_write=pre)
            n = len(new)
        fhe.declare(data_dir, f)
        written[f] = {'kind': kind, 'rows_written': n, 'md5': md5(path) if os.path.exists(path) else None}
        print(f'  ✅ {f}: {kind}, {n} row(s) written')
    os.makedirs(backup_dir, exist_ok=True)
    mf = os.path.join(backup_dir, MANIFEST)
    runs = []
    if os.path.exists(mf):
        with open(mf) as fh:
            old = json.load(fh)
        runs = old if isinstance(old, list) else [old]
    runs.append({'run_at': run_at, 'data_dir': data_dir, 'written': written,
                 'files': {f: {k: v for k, v in r.items() if not k.startswith('sample')} for f, r in report['files'].items()}})
    fhe._atomic_json(mf, runs)
    print(f'  manifest -> {mf}')
    return 0


def _print(report):
    for f, r in report['files'].items():
        print(f"\n== {f}: plan {r['plan']} — {r['rows']} row(s) {r['first']} .. {r['last']}" + (f"  [stopped: {r['stop']}]" if r['stop'] else ''))
        for k in ('existing', 'append_rows', 'append_stop', 'rolls', 'roll_first_dates_last_8', 'roll_adjust_cum_last',
                  'gap_mean', 'adjusted_settle_min_max', 'rows_with_adjusted_settle_le_0', 'roll_methods',
                  'ltd_sessions_omitted', 'zero_volume_rows', 'distributions', 'dropped_nan_bars',
                  'dropped_non_trading_bars', 'anomalies'):
            if k in r and r[k] not in (None, [], {}):
                print(f'   {k}: {r[k]}')
        if 'rolls_detail' in r:
            for x in r['rolls_detail']:
                print(f"   roll {x}")
        for row in r['sample_first'][:1] + r['sample_last'][-2:]:
            print(f"   sample {row}")
    for k in ('vx_source', 'calendar_check', 'vx_roll_evidence', 'vx_front_vs_vix_spot', 'duration_tracking'):
        if k in report:
            print(f'\n== {k}:\n   ' + json.dumps(report[k], default=str)[:3000])


if __name__ == '__main__':
    raise SystemExit(main())
