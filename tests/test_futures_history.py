"""Tests for data_extractors/futures_history_extractors.py (VX CBOE curve + front, ZN=F, IEF).

Stdlib unittest. No network: CBOE and Yahoo are replaced by fakes; every file is written to a
temp dir, nothing under historical_data/ is touched.

  python3 -m unittest discover -s tests -p 'test_futures_history.py' -v

Covered: roll selection around expiry (holidays, expiry day), forward-adjustment invariance
(appending new days and crossing a roll never changes an existing byte; incremental == one-shot
build), CBOE CSV parsing (placeholder rows), yfinance NaN-bar trimming through yf_safe, the ZN
last-trading-day handling and measured gap, IEF forward total return, the updaters' no-op
re-run, drift reporting and refusal to bootstrap.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import extract_historical_data as ehd  # noqa: E402
from data_extractors import futures_history_extractors as fhe  # noqa: E402
from data_extractors import yf_safe  # noqa: E402

D = date.fromisoformat


def sessions(a, b):
    out, x = [], D(a)
    while x <= D(b):
        if fhe.is_trading_day(x):
            out.append(x)
        x += timedelta(days=1)
    return out


def at_ny(d, hour=12):
    """A UTC datetime at `hour`:00 New York time on date d (for final_cutoff)."""
    return datetime(d.year, d.month, d.day, hour, tzinfo=fhe.NY).astimezone(timezone.utc)


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name
        p = mock.patch.object(ehd, 'OUTPUT_DIR', self.tmp.name)   # declare_columns & co. stay in the temp dir
        p.start()
        self.addCleanup(p.stop)

    def path(self, name):
        return os.path.join(self.dir, name)

    def read(self, name):
        with open(self.path(name), 'rb') as fh:
            return fh.read()


# ── calendar ─────────────────────────────────────────────────────────────────────────────

# Weekdays without a CFE session 2021-01-01..2026-09-18, read from CBOE's own VX files.
CFE_CLOSED_WEEKDAYS_2021_2026 = """2021-01-01 2021-01-18 2021-02-15 2021-04-02 2021-05-31 2021-07-05 2021-09-06
2021-11-25 2021-12-24 2022-01-17 2022-02-21 2022-04-15 2022-05-30 2022-06-20 2022-07-04 2022-09-05 2022-11-24
2022-12-26 2023-01-02 2023-01-16 2023-02-20 2023-04-07 2023-05-29 2023-06-19 2023-07-04 2023-09-04 2023-11-23
2023-12-25 2024-01-01 2024-01-15 2024-02-19 2024-03-29 2024-05-27 2024-06-19 2024-07-04 2024-09-02 2024-11-28
2024-12-25 2025-01-01 2025-01-20 2025-02-17 2025-04-18 2025-05-26 2025-06-19 2025-07-04 2025-09-01 2025-11-27
2025-12-25 2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 2026-09-07""".split()


class CalendarTest(unittest.TestCase):
    def test_rule_calendar_matches_cboe_sessions_2021_2026(self):
        closed = [str(x) for x in (D('2021-01-01') + timedelta(days=i) for i in range((D('2026-09-18') - D('2021-01-01')).days + 1))
                  if x.weekday() < 5 and not fhe.is_trading_day(x)]
        self.assertEqual(closed, CFE_CLOSED_WEEKDAYS_2021_2026)

    def test_extra_session_and_special_days(self):
        self.assertTrue(fhe.is_trading_day(D('2015-04-03')))        # Good Friday 2015: CFE open
        self.assertFalse(fhe.is_trading_day(D('2016-03-25')))       # an ordinary Good Friday
        self.assertTrue(fhe.is_trading_day(D('2021-12-31')))        # Saturday New Year: no Friday holiday
        self.assertFalse(fhe.is_trading_day(D('2021-12-24')))       # Saturday Christmas -> Friday
        self.assertTrue(fhe.is_trading_day(D('2025-01-09')))        # CFE opened on the Carter day of mourning

    def test_zn_last_trading_days(self):
        self.assertEqual(fhe.zn_last_trading_day(2026, 6), D('2026-06-18'))    # Juneteenth in the count
        self.assertEqual(fhe.zn_last_trading_day(2026, 9), D('2026-09-21'))
        self.assertEqual(fhe.zn_last_trading_day(2026, 12), D('2026-12-21'))   # Yahoo: ZN=F expireDate 2026-12-21
        self.assertEqual(fhe.zn_last_trading_day(2024, 3), D('2024-03-19'))    # Good Friday 03-29 ends the month
        self.assertEqual(fhe.zn_last_trading_day(2025, 6), D('2025-06-18'))

    def test_zn_contract_on(self):
        self.assertEqual(fhe.zn_contract_on(D('2026-06-17')), 'ZNM26')
        self.assertIsNone(fhe.zn_contract_on(D('2026-06-18')))                  # hybrid LTD bar: omitted
        self.assertEqual(fhe.zn_contract_on(D('2026-06-22')), 'ZNU26')
        self.assertEqual(fhe.zn_contract_on(D('2026-09-18')), 'ZNU26')
        self.assertIsNone(fhe.zn_contract_on(D('2026-09-21')))
        self.assertEqual(fhe.zn_contract_on(D('2026-09-22')), 'ZNZ26')
        self.assertEqual(fhe.zn_contract_on(D('2026-12-28')), 'ZNH27')

    def test_final_cutoff_is_new_york_date(self):
        # 00:30 UTC on 09-23 is still 09-22 in New York: the 09-22 bar is not final yet
        self.assertEqual(fhe.final_cutoff(datetime(2026, 9, 23, 0, 30, tzinfo=timezone.utc)), D('2026-09-22'))
        self.assertEqual(fhe.final_cutoff(datetime(2026, 9, 23, 5, 0, tzinfo=timezone.utc)), D('2026-09-23'))


# ── VX roll selection ─────────────────────────────────────────────────────────────────────

class RollSelectionTest(unittest.TestCase):
    EXP = [D('2026-08-19'), D('2026-09-16'), D('2026-10-21'), D('2026-11-18'), D('2026-12-16')]

    def test_switch_five_sessions_before_expiry(self):
        got = {d: fhe.vx_target_expiry(d, self.EXP) for d in sessions('2026-09-01', '2026-09-16')}
        sep, octo = D('2026-09-16'), D('2026-10-21')
        self.assertEqual([d for d, e in got.items() if e == sep][-1], D('2026-09-08'))   # 6 sessions left
        self.assertEqual([d for d, e in got.items() if e == octo][0], D('2026-09-09'))   # 5 sessions left
        self.assertEqual(fhe.sessions_after(D('2026-09-09'), sep), 5)
        self.assertEqual(fhe.sessions_after(D('2026-09-04'), sep), 7)                    # Labor Day not counted

    def test_holiday_moves_the_roll_a_session_earlier(self):
        exp = [D('2025-01-22'), D('2025-02-19')]
        self.assertEqual(fhe.vx_target_expiry(D('2025-01-13'), exp), D('2025-01-22'))
        self.assertEqual(fhe.vx_target_expiry(D('2025-01-14'), exp), D('2025-02-19'))    # MLK 01-20 in the window

    def test_curve_front_skips_the_contract_expiring_that_day(self):
        days = sessions('2026-09-14', '2026-09-17')
        bars = synthetic_vx(self.EXP, days)
        row = fhe.vx_curve_row(D('2026-09-16'), self.EXP, bars)
        self.assertEqual((row['vx1_contract'], row['vx2_contract'], row['vx3_contract']), ('VXV26', 'VXX26', 'VXZ26'))
        self.assertEqual(row['vx1_days_to_expiry'], '35')
        self.assertEqual(fhe.vx_curve_row(D('2026-09-15'), self.EXP, bars)['vx1_expiry'], '2026-09-16')

    def test_fixed_front_schema(self):
        self.assertEqual(fhe.VX_FRONT_COLUMNS, ['timestamp', 'date', 'open', 'high', 'low', 'close', 'settle',
                                                'contract', 'days_to_expiry', 'roll_adjust_cum'])
        self.assertEqual(fhe.ZN_COLUMNS, ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume', 'roll_adjust_cum'])


def synthetic_vx(expiries, days, base=15.0, step=1.25):
    """Contango curve: contract k settles at base + k*step + 0.01*i; OHLC around it."""
    bars = {}
    for k, e in enumerate(expiries):
        bars[e] = {}
        for i, d in enumerate(days):
            if d > e:
                break
            s = round(base + k * step + 0.01 * i, 4)
            bars[e][d] = {'open': s - 0.1, 'high': s + 0.2, 'low': s - 0.3, 'close': s + 0.05, 'settle': s,
                          'volume': 1000 + k, 'open_interest': 5000 + k, 'futures': ''}
    return bars


# ── forward adjustment: invariance and incremental == one-shot ────────────────────────────

class ForwardAdjustmentTest(_Tmp):
    EXP = [D('2026-07-22'), D('2026-08-19'), D('2026-09-16'), D('2026-10-21'), D('2026-11-18'), D('2026-12-16')]

    def setUp(self):
        super().setUp()
        self.days = sessions('2026-07-01', '2026-10-02')
        self.bars = synthetic_vx(self.EXP, self.days)

    def front(self, ds, state=None):
        rows, rolls, stop = fhe.vx_front_rows(ds, self.EXP, self.bars, state)
        self.assertIsNone(stop)
        return rows, rolls

    def test_roll_adjust_accumulates_forward_only(self):
        rows, rolls = self.front(self.days)
        self.assertEqual([r['first_date'] for r in rolls], ['2026-07-15', '2026-08-12', '2026-09-09'])
        self.assertTrue(all(r['gap'] == -1.25 for r in rolls))                    # old - new = -step
        self.assertEqual(rows[0]['roll_adjust_cum'], '0')
        self.assertEqual(rows[-1]['roll_adjust_cum'], '-3.75')
        for r in rows:                                                            # raw = price - roll_adjust_cum
            d, e = D(r['date']), D(r['date']) + timedelta(days=int(r['days_to_expiry']))
            raw = float(r['settle']) - float(r['roll_adjust_cum'])
            self.assertAlmostEqual(raw, self.bars[e][d]['settle'], places=9)
        # across a roll the adjusted change is the NEW contract's own change
        i = next(i for i, r in enumerate(rows) if r['date'] == '2026-09-09')
        d0, d1 = D(rows[i - 1]['date']), D(rows[i]['date'])
        oct_ = D('2026-10-21')
        self.assertAlmostEqual(float(rows[i]['settle']) - float(rows[i - 1]['settle']),
                               self.bars[oct_][d1]['settle'] - self.bars[oct_][d0]['settle'], places=9)

    def test_appending_across_a_roll_never_changes_written_bytes(self):
        path = self.path(fhe.VX_FRONT_FILE)
        cut = D('2026-09-04')                                                      # before the 09-09 roll
        first, _ = self.front([d for d in self.days if d <= cut])
        fhe.append_rows(path, fhe.VX_FRONT_COLUMNS, lambda ex: first)
        before = self.read(fhe.VX_FRONT_FILE)
        for stop_at in ('2026-09-10', '2026-09-23', '2026-10-02'):                # three later runs
            fhe.append_rows(path, fhe.VX_FRONT_COLUMNS,
                            lambda ex, s=stop_at: self.front([d for d in self.days if d <= D(s)], fhe.vx_front_state(ex))[0])
            after = self.read(fhe.VX_FRONT_FILE)
            self.assertTrue(after.startswith(before), f'existing bytes changed by the run to {stop_at}')
            before = after
        one_shot = self.path('one_shot.csv')
        fhe.append_rows(one_shot, fhe.VX_FRONT_COLUMNS, lambda ex: self.front(self.days)[0])
        self.assertEqual(self.read(fhe.VX_FRONT_FILE), Path(one_shot).read_bytes())

    def test_rerun_is_a_noop(self):
        path = self.path(fhe.VX_FRONT_FILE)
        fhe.append_rows(path, fhe.VX_FRONT_COLUMNS, lambda ex: self.front(self.days)[0])
        st, data = os.stat(path), self.read(fhe.VX_FRONT_FILE)
        new, _ = fhe.append_rows(path, fhe.VX_FRONT_COLUMNS, lambda ex: self.front(self.days, fhe.vx_front_state(ex))[0])
        self.assertEqual(new, [])
        self.assertEqual(self.read(fhe.VX_FRONT_FILE), data)
        self.assertEqual(os.stat(path).st_mtime_ns, st.st_mtime_ns)               # not even rewritten

    def test_stops_before_an_incomplete_session(self):
        bars = {e: dict(b) for e, b in self.bars.items()}
        del bars[D('2026-10-21')][D('2026-09-08')]                                 # the roll's reference day
        rows, rolls, stop = fhe.vx_front_rows(self.days, self.EXP, bars)
        self.assertEqual(rows[-1]['date'], '2026-09-08')
        self.assertIn('needs both settlements', stop)

    def test_append_refuses_foreign_header_or_partial_line(self):
        p = self.path('x.csv')
        Path(p).write_text('timestamp,date,close\n2026-01-02 00:00:00,2026-01-02,1\n')
        with self.assertRaises(fhe.HistoryError):
            fhe.append_rows(p, fhe.ZN_COLUMNS, lambda ex: [])
        Path(p).write_text(','.join(fhe.ZN_COLUMNS) + '\n2026-01-02 00:00:00,2026-01-02,1,1,1,1,1,0')
        with self.assertRaises(fhe.HistoryError):
            fhe.append_rows(p, fhe.ZN_COLUMNS, lambda ex: [])

    def test_ief_adjclose_is_forward_total_return(self):
        days = sessions('2026-08-25', '2026-09-10')
        bars = {d: {'open': 90 + i * .1, 'high': 90.5 + i * .1, 'low': 89.5 + i * .1, 'close': 90 + i * .1,
                    'volume': 100, 'dividend': 0.33 if d == D('2026-09-01') else 0.0, 'split': 0.0}
                for i, d in enumerate(days)}
        rows, stop = fhe.ief_rows(bars)
        self.assertIsNone(stop)
        self.assertEqual(rows[0]['adjclose'], rows[0]['close'])
        for a, b in zip(rows, rows[1:]):
            tr = (float(b['close']) + float(b['dividend'])) / float(a['close'])
            self.assertAlmostEqual(float(b['adjclose']), float(a['adjclose']) * tr, places=5)
        p = self.path(fhe.IEF_FILE)
        fhe.append_rows(p, fhe.IEF_COLUMNS, lambda ex: fhe.ief_rows({d: b for d, b in bars.items() if d <= D('2026-09-01')})[0])
        fhe.append_rows(p, fhe.IEF_COLUMNS, lambda ex: fhe.ief_rows(bars, fhe.ief_state(ex))[0])
        whole = self.path('whole.csv')
        fhe.append_rows(whole, fhe.IEF_COLUMNS, lambda ex: rows)
        self.assertEqual(self.read(fhe.IEF_FILE), Path(whole).read_bytes())
        split = dict(bars)
        split[days[-1]] = {**bars[days[-1]], 'split': 2.0}
        self.assertIn('split', fhe.ief_rows(split)[1])


# ── CBOE parsing ──────────────────────────────────────────────────────────────────────────

CBOE_SAMPLE = """Trade Date,Futures,Open,High,Low,Close,Settle,Change,Total Volume,EFP,Open Interest
2025-12-22,U (Sep 2026),0.0000,19.0000,0.0000,0.0000,21.10,0,0,0,0
2025-12-23,U (Sep 2026),0.0000,21.1000,22.8000,0.0000,21.175,0.075,0,0,0
2026-09-15,U (Sep 2026),16.8500,17.6100,16.6800,16.9700,17.032,0.1811,67703,24,50591
2026-09-16,U (Sep 2026),16.8500,17.2500,16.5000,16.5500,16.79,-0.242,931,0,48855
"""


class CboeParseTest(unittest.TestCase):
    def test_parses_quirks(self):
        bars = fhe.parse_cboe_vx_csv(CBOE_SAMPLE, D('2026-09-16'))
        self.assertEqual(sorted(bars), [D('2025-12-22'), D('2025-12-23'), D('2026-09-15'), D('2026-09-16')])
        q = bars[D('2025-12-23')]                         # zero volume: placeholder high/low (low > high) dropped
        self.assertEqual((q['open'], q['high'], q['low'], q['close']), (None, None, None, None))
        self.assertEqual((q['settle'], q['volume'], q['open_interest']), (21.175, 0, 0))
        b = bars[D('2026-09-15')]
        self.assertEqual((b['open'], b['high'], b['low'], b['close'], b['settle']), (16.85, 17.61, 16.68, 16.97, 17.032))
        self.assertEqual((b['volume'], b['open_interest'], b['futures']), (67703, 50591, 'U (Sep 2026)'))

    def test_zero_settle_is_missing(self):
        t = CBOE_SAMPLE.replace('21.10,0,0,0,0', '0,0,0,0,0')
        self.assertIsNone(fhe.parse_cboe_vx_csv(t)[D('2025-12-22')]['settle'])

    def test_rejects_unexpected_layouts(self):
        with self.assertRaises(ValueError):
            fhe.parse_cboe_vx_csv(CBOE_SAMPLE.replace('Settle', 'SettlePrice'))
        with self.assertRaises(ValueError):
            fhe.parse_cboe_vx_csv(CBOE_SAMPLE, D('2026-09-15'))                   # a row after expiry
        with self.assertRaises(ValueError):
            fhe.parse_cboe_vx_csv('<html><body>Just a moment...</body></html>')

    def test_curve_row_formats(self):
        exp = [D('2026-09-16'), D('2026-10-21'), D('2026-11-18')]
        bars = {e: fhe.parse_cboe_vx_csv(CBOE_SAMPLE) for e in exp}
        row = fhe.vx_curve_row(D('2026-09-15'), exp, bars)
        self.assertEqual(list(row), fhe.VX_CURVE_COLUMNS)
        self.assertEqual((row['vx1_contract'], row['vx1_settle'], row['vx1_volume'], row['vx1_days_to_expiry']),
                         ('VXU26', '17.032', '67703', '1'))
        self.assertIsNone(fhe.vx_curve_row(D('2026-09-14'), exp, bars))            # a contract lacks the day


# ── yfinance via yf_safe ──────────────────────────────────────────────────────────────────

def yahoo_frame(days, trailing_nan=True, interior_nan=None):
    idx = pd.DatetimeIndex([pd.Timestamp(d).tz_localize('America/New_York') for d in days])
    n = len(days)
    df = pd.DataFrame({'Open': [100.0 + i for i in range(n)], 'High': [101.0 + i for i in range(n)],
                       'Low': [99.0 + i for i in range(n)], 'Close': [100.5 + i for i in range(n)],
                       'Volume': [1000 + i for i in range(n)], 'Dividends': [0.0] * n,
                       'Stock Splits': [0.0] * n}, index=idx)
    if trailing_nan:
        df.iloc[-1, df.columns.get_indexer(['Open', 'High', 'Low', 'Close'])] = float('nan')
    if interior_nan is not None:
        df.iloc[interior_nan, df.columns.get_indexer(['Close'])] = float('nan')
    return df


class YahooTrimTest(unittest.TestCase):
    DAYS = sessions('2026-09-14', '2026-09-18')

    def test_trailing_price_less_bar_is_trimmed_by_yf_safe(self):
        df = yahoo_frame(self.DAYS, trailing_nan=True, interior_nan=1)
        bars, dropped = fhe.yahoo_frame_to_bars(yf_safe.trim_incomplete_bars(df))
        self.assertEqual(sorted(bars), [self.DAYS[0], self.DAYS[2], self.DAYS[3]])
        self.assertEqual(dropped, [self.DAYS[1]])                                  # interior NaN: dropped + reported

    def test_fetch_goes_through_yf_safe(self):
        df = yahoo_frame(self.DAYS, trailing_nan=True)

        class FakeTicker:
            def __init__(self, sym):
                self.sym = sym

            def history(self, **kw):
                self.kw = kw
                return df
        with mock.patch.object(yf_safe.yf, 'Ticker', FakeTicker):
            bars, dropped = fhe.fetch_yahoo('IEF', D('2026-09-01'))
        self.assertEqual(sorted(bars), self.DAYS[:-1])                             # 09-18's NaN bar never arrives
        self.assertEqual(dropped, [])
        self.assertEqual(bars[self.DAYS[0]]['close'], 100.5)

    def test_final_bars_drop_unfinished_and_holiday_bars(self):
        bars = {d: {'close': 1} for d in (D('2025-07-03'), D('2025-07-04'), D('2025-07-07'), D('2025-07-08'))}
        keep, off = fhe.final_bars(bars, D('2025-07-08'))
        self.assertEqual(sorted(keep), [D('2025-07-03'), D('2025-07-07')])
        self.assertEqual(off, [D('2025-07-04')])


# ── updaters end to end (fake sources) ────────────────────────────────────────────────────

class FakeCboe:
    def __init__(self, bars):
        self.bars, self.requests = bars, 0

    def listing(self):
        self.requests += 1
        return {e: f'fake/VX_{e}.csv' for e in sorted(self.bars)}

    def contract(self, e, path=None, cutoff=None):
        self.requests += 1
        return self.bars[e]


class UpdaterTest(_Tmp):
    EXP = ForwardAdjustmentTest.EXP

    def bootstrap_vx(self, bars, upto):
        days = [d for d in fhe.vx_sessions(bars, None, upto + timedelta(days=1))]
        curve, _ = fhe.vx_curve_rows(days, self.EXP, bars)
        front, _, _ = fhe.vx_front_rows(days, self.EXP, bars)
        fhe.append_rows(self.path(fhe.VX_CURVE_FILE), fhe.VX_CURVE_COLUMNS, lambda ex: curve)
        fhe.append_rows(self.path(fhe.VX_FRONT_FILE), fhe.VX_FRONT_COLUMNS, lambda ex: front)

    def test_update_vx_appends_then_noop_then_reports_drift(self):
        days = sessions('2026-07-01', '2026-09-18')
        bars = synthetic_vx(self.EXP, days)
        self.bootstrap_vx(bars, D('2026-09-04'))
        before = {f: self.read(f) for f in (fhe.VX_CURVE_FILE, fhe.VX_FRONT_FILE)}
        res = quiet(fhe.update_vx, self.dir, now=at_ny(D('2026-09-21')), source=FakeCboe(bars))
        self.assertEqual([r['last_date'] for r in res], ['2026-09-18', '2026-09-18'])
        self.assertEqual([r['rows'] for r in res], [9, 9])
        self.assertEqual([x['first_date'] for x in res[1]['rolls']], ['2026-09-09'])
        for f, b in before.items():
            self.assertTrue(self.read(f).startswith(b))
        # the 09-18 row is only written once 09-18 is over in New York
        after = {f: self.read(f) for f in before}
        res2 = quiet(fhe.update_vx, self.dir, now=at_ny(D('2026-09-21'), 20), source=FakeCboe(bars))
        self.assertEqual([r['rows'] for r in res2], [0, 0])
        self.assertEqual({f: self.read(f) for f in before}, after)                # byte-identical no-op
        revised = {e: {d: dict(b) for d, b in v.items()} for e, v in bars.items()}
        revised[D('2026-10-21')][D('2026-09-17')]['settle'] += 0.5
        res3 = quiet(fhe.update_vx, self.dir, now=at_ny(D('2026-09-22')), source=FakeCboe(revised))
        self.assertTrue(res3[0]['drift'] and res3[1]['drift'])
        self.assertEqual({f: self.read(f) for f in before}, after)                # reported, not rewritten
        sidecar = json.loads(Path(self.path('.vx_front_ohlcv.columns.json')).read_text())
        self.assertEqual(sidecar['active'], fhe.VX_FRONT_COLUMNS[2:])

    def test_unfinished_day_is_not_written(self):
        days = sessions('2026-07-01', '2026-09-18')
        bars = synthetic_vx(self.EXP, days)
        self.bootstrap_vx(bars, D('2026-09-04'))
        res = quiet(fhe.update_vx, self.dir, now=at_ny(D('2026-09-18'), 20), source=FakeCboe(bars))
        self.assertEqual(res[1]['last_date'], '2026-09-17')

    def test_updaters_refuse_to_bootstrap(self):
        for fn in (fhe.update_vx, fhe.update_ief, fhe.update_zn):
            with self.assertRaises(fhe.HistoryError):
                quiet(fn, self.dir, now=at_ny(D('2026-09-21')), source=FakeCboe({})) if fn is fhe.update_vx else \
                    quiet(fn, self.dir, now=at_ny(D('2026-09-21')), fetch=lambda s, st: ({}, []))
        self.assertEqual(quiet(fhe.extract_futures_history, self.dir, now=at_ny(D('2026-09-21'))), [])

    # ZN: generic = old contract up to LTD-1, hybrid on the LTD, new contract after; new trades 0.25 lower
    def zn_world(self):
        days = sessions('2026-06-01', '2026-06-30')
        ltd = D('2026-06-18')
        old = {d: 110 + 0.1 * i for i, d in enumerate(days)}
        new = {d: v - 0.25 for d, v in old.items()}
        bar = lambda p, v: {'open': p - .05, 'high': p + .1, 'low': p - .1, 'close': p, 'volume': v, 'dividend': 0.0, 'split': 0.0}
        generic = {d: bar(old[d] if d < ltd else new[d], 900 if d < ltd else 2_000_000) for d in days}
        generic[ltd] = {**bar(old[ltd], 2_000_000), 'low': new[ltd] - 0.2}               # hybrid
        newc = {d: bar(new[d], 2_000_000) for d in days}
        return days, ltd, generic, newc

    def test_zn_ltd_omitted_and_gap_measured(self):
        days, ltd, generic, newc = self.zn_world()
        calls = []

        def fetch(sym, start):
            calls.append(sym)
            return ({d: b for d, b in (generic if sym == 'ZN=F' else newc if sym == 'ZNU26.CBT' else {}).items()
                     if d >= start}, [])
        boot, _, _ = fhe.zn_rows({d: b for d, b in generic.items() if d <= D('2026-06-12')})
        fhe.append_rows(self.path(fhe.ZN_FILE), fhe.ZN_COLUMNS, lambda ex: boot)
        before = self.read(fhe.ZN_FILE)
        res = quiet(fhe.update_zn, self.dir, now=at_ny(D('2026-06-30')), fetch=fetch)
        self.assertIn('ZNU26.CBT', calls)
        text = self.read(fhe.ZN_FILE)
        self.assertTrue(text.startswith(before))
        self.assertNotIn(b'2026-06-18', text)                                        # LTD omitted
        self.assertEqual(len(res['rolls']), 1)
        r = res['rolls'][0]
        self.assertEqual((r['method'], r['gap'], r['last_old_date'], r['first_new_date']),
                         ('measured', 0.25, '2026-06-17', '2026-06-22'))
        rows = fhe.read_table(self.path(fhe.ZN_FILE))[1]
        by = {x['date']: x for x in rows}
        self.assertEqual(by['2026-06-17']['roll_adjust_cum'], '0')
        self.assertEqual(by['2026-06-22']['roll_adjust_cum'], '0.25')
        # adjusted change across the roll = the new contract's own change 06-17 -> 06-22
        self.assertAlmostEqual(float(by['2026-06-22']['close']) - float(by['2026-06-17']['close']),
                               newc[D('2026-06-22')]['close'] - newc[D('2026-06-17')]['close'], places=6)
        log = json.loads(Path(self.path(fhe.ZN_ROLL_LOG)).read_text())
        self.assertEqual([x['ltd'] for x in log['rolls']], ['2026-06-18'])
        again = self.read(fhe.ZN_FILE)
        quiet(fhe.update_zn, self.dir, now=at_ny(D('2026-06-30')), fetch=fetch)
        self.assertEqual(self.read(fhe.ZN_FILE), again)

    def test_zn_updater_waits_rather_than_estimates(self):
        days, ltd, generic, newc = self.zn_world()
        fetch = lambda sym, start: ({d: b for d, b in generic.items() if d >= start} if sym == 'ZN=F' else {}, [])
        boot, _, _ = fhe.zn_rows({d: b for d, b in generic.items() if d <= D('2026-06-12')})
        fhe.append_rows(self.path(fhe.ZN_FILE), fhe.ZN_COLUMNS, lambda ex: boot)
        res = quiet(fhe.update_zn, self.dir, now=at_ny(D('2026-06-30')), fetch=fetch)
        self.assertEqual(res['last_date'], '2026-06-17')
        self.assertIn('no measured gap', res['stopped'])
        self.assertFalse(os.path.exists(self.path(fhe.ZN_ROLL_LOG)))

    def test_update_ief(self):
        days = sessions('2026-08-25', '2026-09-18')
        bars = {d: {'open': 90.0 + i / 10, 'high': 90.5 + i / 10, 'low': 89.5 + i / 10, 'close': 90.1 + i / 10,
                    'volume': 100 + i, 'dividend': 0.33 if d == D('2026-09-01') else 0.0, 'split': 0.0}
                for i, d in enumerate(days)}
        fetch = lambda sym, start: ({d: b for d, b in bars.items() if d >= start}, [])
        boot, _ = fhe.ief_rows({d: b for d, b in bars.items() if d <= D('2026-08-28')})
        fhe.append_rows(self.path(fhe.IEF_FILE), fhe.IEF_COLUMNS, lambda ex: boot)
        res = quiet(fhe.update_ief, self.dir, now=at_ny(D('2026-09-21')), fetch=fetch)
        self.assertEqual((res['rows'], res['last_date']), (len(sessions('2026-08-29', '2026-09-18')), '2026-09-18'))
        whole = self.path('w.csv')
        fhe.append_rows(whole, fhe.IEF_COLUMNS, lambda ex: fhe.ief_rows(bars)[0])
        self.assertEqual(self.read(fhe.IEF_FILE), Path(whole).read_bytes())


class FeedScannerRoundTrip(_Tmp):
    """The declared contract is read back by CC's feed scanner (skipped when CC is absent)."""
    CC_BACKFILL = Path(os.environ.get('CC_BACKFILL_DIR', Path.home() / 'Github/CLI_OS/Agent_Orchestration/CC/backfill'))

    def test_scanner_accepts_contract(self):
        if not (self.CC_BACKFILL / 'data_guard.py').exists():
            self.skipTest('CC backfill/data_guard.py not present')
        import importlib.util
        spec = importlib.util.spec_from_file_location('data_guard_ut', self.CC_BACKFILL / 'data_guard.py')
        dg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dg)
        days = sessions('2026-07-01', '2026-09-18')
        bars = synthetic_vx(ForwardAdjustmentTest.EXP, days)
        rows, _, _ = fhe.vx_front_rows(days, ForwardAdjustmentTest.EXP, bars)
        p = self.path(fhe.VX_FRONT_FILE)
        fhe.append_rows(p, fhe.VX_FRONT_COLUMNS, lambda ex: rows)
        fhe.declare(self.dir, fhe.VX_FRONT_FILE)
        con, broken = dg.load_contract(Path(p))
        self.assertIsNone(broken)
        flags, notes = dg.contract_findings(dg.scan(Path(p)), con)
        self.assertEqual(flags, [])


if __name__ == '__main__':
    unittest.main()
