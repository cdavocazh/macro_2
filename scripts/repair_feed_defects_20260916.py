#!/usr/bin/env python3
"""One-off repair of historical_data/ defects found on 2026-09-16.

The collectors were fixed in the same change (see QA_SOP.md Bug Log, 2026-09-16);
this script cleans up what they had already written. Dry run by default.

  python scripts/repair_feed_defects_20260916.py                 # report only
  python scripts/repair_feed_defects_20260916.py --apply \\
      --aaii 38.0,22.7,39.3,2026-09-09                           # write

Every file is copied to .deploy_backup_20260916/data/ before it is rewritten,
under the same per-file lock the collectors take, and written atomically.

Repairs
  gold.csv                         drop rows whose timestamp is blank/unparseable
                                   (marketcap_to_gdp.csv is keyed on 'date', not
                                   'timestamp' — its blank-timestamp row is valid)
  full_treasury_curve.csv          fold OpenBB month_N/year_N columns into 1M..30Y
  jpy.csv                          date = London date of the timestamp (yfinance FX
                                   convention; IBKR rows had been labelled in UTC)
  aaii_sentiment.csv               drop every pre-fix row: all came from an unanchored
                                   regex (all-time records, or the voting widget's
                                   small-sample fractions such as 33.3/33.3/33.3 that
                                   even pass a sum check); optionally add the verified
                                   current reading, dated by its survey week
  10y_treasury_yield.csv,          one row per date (prefer the 00:00 FRED row over
  us_2y_yield.csv                  legacy 05:00/06:00 rows); drop blank values
  sp500_fundamentals.csv           trailing_eps = spy_price / pe_ratio_trailing
                                   where both are on the row
  vix_futures_curve.csv            collapse same-date daily bars left from two older
                                   timezone conventions (04:00 and 05:00 UTC) on dates
                                   outside today's 5-year refetch window; values must
                                   be identical or the repair aborts
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from extract_historical_data import OUTPUT_DIR, _atomic_to_csv, _csv_lock, _parse_timestamps  # noqa: E402
from data_extractors.fidenza_extractors import _aaii_readings_valid  # noqa: E402

BACKUP_DIR = os.path.join(ROOT, '.deploy_backup_20260916', 'data')
# fidenza_extractors.py with the anchored AAII parser went live at this time on the VPS
# (UTC). Override with --aaii-cutoff on a host whose rows are stamped in local time or
# that picked the fix up later.
AAII_FIX_DEFAULT_CUTOFF = '2026-09-16 09:13:00'
_OPENBB_COL = re.compile(r'^(month|year)_(\d+)$')


def _path(name):
    return os.path.join(OUTPUT_DIR, name)


def _rewrite(name, fix, apply):
    """Run fix(df) -> (df, summary) under the file lock; back up and write if changed."""
    path = _path(name)
    if not os.path.exists(path):
        print(f'  skip {name}: missing')
        return
    with _csv_lock(path):
        before = pd.read_csv(path, dtype=str, keep_default_na=False)
        after, summary = fix(before.copy())
        changed = not after.equals(before)
        print(f'  {name}: {summary}' + ('' if changed else ' (no change)'))
        if changed and apply:
            os.makedirs(BACKUP_DIR, exist_ok=True)
            backup = os.path.join(BACKUP_DIR, name)
            if not os.path.exists(backup):  # keep the first, pre-repair copy
                shutil.copy2(path, backup)
            _atomic_to_csv(after, path)


def fix_bad_timestamps(df):
    ts = _parse_timestamps(df['timestamp'])  # blank strings parse to NaT
    bad = ts.isna()
    dropped = df[bad].values.tolist()
    return df[~bad].reset_index(drop=True), f'dropped {int(bad.sum())} row(s) with a blank/unparseable timestamp {dropped[:3]}'


def fix_treasury_curve(df):
    moved, conflicts, dropped_cols = 0, 0, []
    for col in list(df.columns):
        m = _OPENBB_COL.match(col)
        if not m:
            continue
        canon = f"{int(m.group(2))}{'M' if m.group(1) == 'month' else 'Y'}"
        if canon not in df.columns:
            df[canon] = ''
        src, dst = df[col], df[canon]
        both = (src != '') & (dst != '')
        conflicts += int((both & (pd.to_numeric(src, errors='coerce') != pd.to_numeric(dst, errors='coerce'))).sum())
        fill = (src != '') & (dst == '')
        moved += int(fill.sum())
        df.loc[fill, canon] = src[fill]
        dropped_cols.append(col)
    if conflicts:
        raise SystemExit(f'full_treasury_curve.csv: {conflicts} cells disagree between the two column sets — not merging')
    df = df.drop(columns=dropped_cols)
    order = ['timestamp', 'date'] + sorted([c for c in df.columns if c not in ('timestamp', 'date')],
                                           key=lambda c: (c[-1] != 'M', int(re.sub(r'\D', '', c) or 0)))
    return df[order], f'moved {moved} values into canonical columns, dropped {dropped_cols}'


def fix_jpy_dates(df):
    ts = _parse_timestamps(df['timestamp'])
    london = ts.dt.tz_localize('UTC').dt.tz_convert('Europe/London').dt.strftime('%Y-%m-%d')
    daily = (ts.dt.minute == 0) & (ts.dt.second == 0)
    mismatched_daily = int((daily & (london != df['date'])).sum())
    if mismatched_daily:
        raise SystemExit(f'jpy.csv: {mismatched_daily} yfinance daily rows are not London-dated — convention assumption wrong, not relabelling')
    changed = int((london != df['date']).sum())
    df['date'] = london
    return df, f'relabelled {changed} IBKR row(s) to the London date'


def fix_aaii(df, reading, stamp, cutoff):
    pre_fix = _parse_timestamps(df['timestamp']) < cutoff
    old = df[pre_fix]
    vals = old[['bullish', 'neutral', 'bearish']].apply(pd.to_numeric, errors='coerce')
    passing = int(vals.apply(lambda r: _aaii_readings_valid(r['bullish'], r['neutral'], r['bearish']), axis=1).sum()) if len(old) else 0
    out = df[~pre_fix].reset_index(drop=True)
    note = (f'dropped {len(old)} pre-fix row(s) ({passing} of them pass the sum check but are voting-widget '
            f'fractions, e.g. {vals.drop_duplicates().values.tolist()[:4]}), kept {len(out)} written by the fixed collector')
    if reading:
        bull, neut, bear, week = reading
        if not _aaii_readings_valid(bull, neut, bear):
            raise SystemExit(f'--aaii reading {reading} fails validation')
        if (out['date'] == week).any():
            return out, note + f'; week ending {week} already present'
        row = {'timestamp': stamp, 'date': week, 'bullish': f'{bull}', 'neutral': f'{neut}',
               'bearish': f'{bear}', 'bull_bear_ratio': f'{round(bull / bear, 2)}'}
        out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
        note += f'; added verified reading for week ending {week}'
    return out, note


def fix_yields(df):
    col = df.columns[2]
    n0 = len(df)
    df = df[df[col].str.strip() != '']
    blanks = n0 - len(df)
    ts = _parse_timestamps(df['timestamp'])
    df = df.assign(_midnight=(ts.dt.hour == 0) & (ts.dt.minute == 0), _ts=ts)
    df = df.sort_values(['date', '_midnight', '_ts'])
    kept = df.groupby('date', sort=False).tail(1).sort_values('_ts')
    dupes = len(df) - len(kept)
    return kept.drop(columns=['_midnight', '_ts']).reset_index(drop=True), \
        f'dropped {blanks} blank value row(s) and {dupes} same-date duplicate(s) (kept the 00:00 FRED row)'


def fix_sp500_eps(df):
    price = pd.to_numeric(df['spy_price'], errors='coerce')
    pe = pd.to_numeric(df['pe_ratio_trailing'], errors='coerce')
    fill = (df['trailing_eps'] == '') & price.notna() & pe.notna() & (pe > 0)
    df.loc[fill, 'trailing_eps'] = (price[fill] / pe[fill]).round(2).map(lambda v: f'{v:g}')
    return df, f'derived trailing_eps on {int(fill.sum())} row(s)'


def fix_identical_daily_dupes(df):
    col = df.columns[2]
    ts = _parse_timestamps(df['timestamp'])
    whole = (ts.dt.minute == 0) & (ts.dt.second == 0)
    grp = df[whole].groupby('date')[col]
    multi = grp.transform('size') > 1
    spread = grp.transform(lambda s: pd.to_numeric(s, errors='coerce').max() - pd.to_numeric(s, errors='coerce').min())
    if (multi & (spread > 1e-9)).any():
        raise SystemExit(f'{col}: same-date bars disagree — not collapsing')
    dup_idx = df[whole].assign(_ts=ts[whole]).sort_values('_ts').duplicated('date', keep='last')
    drop = dup_idx[dup_idx].index
    return df.drop(index=drop).reset_index(drop=True), f'collapsed {len(drop)} identical same-date daily bar(s)'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--apply', action='store_true', help='write changes (default: report only)')
    ap.add_argument('--aaii', help='verified current reading: bullish,neutral,bearish,YYYY-MM-DD (survey week ending)')
    ap.add_argument('--aaii-cutoff', default=AAII_FIX_DEFAULT_CUTOFF,
                    help=f'rows stamped before this are pre-fix and are dropped (default {AAII_FIX_DEFAULT_CUTOFF}, VPS/UTC)')
    a = ap.parse_args()
    reading = None
    if a.aaii:
        b, n, br, wk = a.aaii.split(',')
        reading = (float(b), float(n), float(br), wk)
    stamp = pd.Timestamp.now(tz='UTC').tz_localize(None).strftime('%Y-%m-%d %H:%M:%S.%f')
    print(f"{'APPLYING' if a.apply else 'DRY RUN'} — backups to {BACKUP_DIR}")
    _rewrite('gold.csv', fix_bad_timestamps, a.apply)
    _rewrite('full_treasury_curve.csv', fix_treasury_curve, a.apply)
    _rewrite('jpy.csv', fix_jpy_dates, a.apply)
    _rewrite('aaii_sentiment.csv', lambda df: fix_aaii(df, reading, stamp, pd.Timestamp(a.aaii_cutoff)), a.apply)
    for name in ('10y_treasury_yield.csv', 'us_2y_yield.csv'):
        _rewrite(name, fix_yields, a.apply)
    _rewrite('sp500_fundamentals.csv', fix_sp500_eps, a.apply)
    _rewrite('vix_futures_curve.csv', fix_identical_daily_dupes, a.apply)


if __name__ == '__main__':
    main()
