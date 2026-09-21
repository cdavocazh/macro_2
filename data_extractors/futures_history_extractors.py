"""Daily history of TRADABLE instruments for the CC pipeline's VIX and 10Y views.

The CC trading pipeline (CLI_OS/Agent_Orchestration/CC) scored 53 of its first 177 backfilled
trades on VIX spot or on the FRED 10Y yield, and neither can be traded as modelled (CC
backfill/ROADMAP.md, Phase 2 "Instrument realism"). This module keeps the price history of
instruments that can be, in historical_data/:

  vx_cfe_curve.csv      CBOE Futures Exchange VX monthly futures. Per trade date, the first,
                        second and third MONTHLY contract expiring AFTER that date (weeklies are
                        ignored), raw exchange prices:
                        timestamp,date, vx{1,2,3}_{contract,expiry,days_to_expiry,open,high,low,
                        close,settle,volume,open_interest}
  vx_front_ohlcv.csv    Continuous front-month VX for EXECUTION. FIXED SCHEMA (other agents code
                        against it): timestamp,date,open,high,low,close,settle,contract,
                        days_to_expiry,roll_adjust_cum
  zn_futures_ohlcv.csv  10-Year T-Note futures from Yahoo's generic ZN=F, forward-adjusted:
                        timestamp,date,open,high,low,close,volume,roll_adjust_cum
                        (+ .zn_futures_ohlcv.rolls.json: how every roll gap was obtained)
  ief_ohlcv.csv         iShares 7-10 Year Treasury Bond ETF: timestamp,date,open,high,low,close,
                        volume,dividend,adjclose

FORWARD ADJUSTMENT. A back-adjusted continuous series re-prices its whole past at every roll:
gold_ohlcv.csv was, after trades had been scored on it, and 40 historical dates moved, flipping
one trade from -1.15R to +1.42R (CC data_guard.py). Here every price column (open/high/low/close,
and settle for VX) is RAW CONTRACT PRICE + roll_adjust_cum. roll_adjust_cum is 0 on a file's
first row and changes only at a roll, by (old contract - new contract) at the last session
before the switch (VX: settlement; ZN: close). Rows already written never change, the raw
contract price is price - roll_adjust_cum, and a close-to-close difference across a roll is
the P&L of a position rolled at that session's settlement.
  LEVELS DRIFT. VX rolls down ~0.9 point per month in contango, so vx_front_ohlcv's adjusted
  prices fall below zero within about two years of the file's first row (-51 at 2026-09 from a
  2021 start, raw 18). Use differences in POINTS (sigma, ATR, P&L); never percentage returns of
  the adjusted column; convert any level (an order price, a stop, "VX at 20") to the contract
  with raw = price - roll_adjust_cum of the same row.

FINALITY AND APPEND-ONLY. A bar dated D is written only after the New York calendar day D has
ended and the source serves it. Each update appends the new days to the end of the file under
the collectors' per-file lock (extract_historical_data._csv_lock), via temp file + rename; the
bytes already in the file are never rewritten. A source that later revises a day already written
is REPORTED ('drift' in the result), not applied. The only rewrite path is an explicit repair:
scripts/backfill_futures_history_20260922.py --rebuild <file> --apply (backs the file up first).
The updaters here never create a file: run that backfill once first.

VX (CBOE). Per-contract daily files, https://cdn.cboe.com/data/us/futures/market_statistics/
historical_data/VX/VX_<expiry>.csv, listed by .../historical_data/product/list/VX/ (plain GETs,
~0.7 s apart; a 401/403/429 or a non-CSV body raises SourceBlocked and nothing is written).
CBOE publishes day D around 05:05 UTC on D+1. A 0 in Open/High/Low/Close means no trade; on a
zero-volume day CBOE carries placeholder high/low values (low > high happens), so all four are
left blank then. days_to_expiry is CALENDAR days from `date` to the contract's final settlement
date; `contract` is VX + month code + 2-digit year (VXV26 = October 2026).
  ROLL RULE (vx_front): hold the first monthly contract with MORE than VX_ROLL_DAYS = 5 trading
  sessions left to expiry, i.e. switch on the session that is 5 sessions before expiry; the roll
  gap is taken at the settlement of the session before. Why 5: over the monthly expiries
  2014-01..2026-09 (151 with a crossover inside 20 sessions) the second contract's volume first
  exceeds the front's a median 5 sessions before expiry (IQR 3-6), and in 2021-2026 the front's
  share of front+second volume crosses 50% exactly at 5 sessions. Open interest crosses earlier
  (median 9): 5 keeps the book in the contract that trades most while staying out of the expiry
  week, where the front converges on the special opening quotation (SOQ). The held contract had
  8 to 43 calendar days to expiry in 2021-2026.
  Trading sessions are counted on a rule-based US exchange calendar (NYSE holiday rules plus
  EXTRA_SESSIONS). Against CBOE's own 3,452 VX sessions 2013-01-02..2026-09-18 the rules disagree
  on one day, Good Friday 2015 (CFE opened for payrolls), which EXTRA_SESSIONS adds; with it the
  match is exact. An unannounced closure would shift one roll by a session until it is added
  there; rows already written keep their contract.

ZN (Yahoo ZN=F). The generic carries the EXPIRING quarterly contract right up to that contract's
last trading day (LTD = 7th business day before the last business day of the contract month),
i.e. through the delivery month, where it traded a median 2.7k lots a day in 2023-2026 against
~1.9 million otherwise (its price still tracks the 10Y as well: R^2 0.90 vs 0.89). On the LTD
itself Yahoo serves a bar that matches neither contract (2026-06-18: ZNU26's volume, prices that
are not ZNU26's), and from the next session the new contract. So the LTD session is OMITTED
(one missing session per quarter), and the roll is taken between the last session before the
LTD and the first one after. Yahoo lists only live contracts (ZN<m><yy>.CBT,
e.g. ZNZ26.CBT), so a roll gap is MEASURED (generic close - new contract's own close at the
last old session, and the generic must equal the new contract at the first new session) only
while the new contract is listed: every roll from 2026-06 on, and every future roll. Older
gaps cannot be measured from Yahoo; the backfill ESTIMATES them from IEF's total return over
the same two sessions (see estimate_zn_gap: 1-sigma error ~0.14 point; on the one roll that can
be checked, 2026-06, it gave 0.56 against a measured 0.25), and .zn_futures_ohlcv.rolls.json
records the method of every roll. The daily updater never estimates: it waits for the measurement. Yahoo's stray
holiday-dated bars (2023-11-23, 2025-07-04) are dropped.

IEF (Yahoo IEF). open/high/low/close/volume are the traded prices (Yahoo split-adjusts but
does not dividend-adjust them with auto_adjust=False). `dividend` is the cash distribution
(income + capital gains) per share going ex on that date, 0 otherwise. `adjclose` is a
FORWARD-accumulated total-return close: equal to close on the file's first row, then
adjclose[t] = adjclose[t-1] * (close[t] + dividend[t]) / close[t-1], so past values never
change. It is NOT Yahoo's "Adj Close", which is back-adjusted and re-prices every past row at
each monthly distribution. IEF pays ~0.3/share each month (~0.35% of price), so its daily
price return is short by that much on ex-dates; use adjclose for total-return P&L. A split
stops the updater (it would rewrite Yahoo's history) until repaired.

Entry point for extract_historical_data._run: extract_futures_history() (returns a list of
{'indicator','last_date','rows',...} dicts, one per file; never raises).
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import statistics
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

NY = ZoneInfo('America/New_York')
WRITER = 'data_extractors/futures_history_extractors.py'

# ── files and schemas ─────────────────────────────────────────────────────────────────────
VX_CURVE_FILE = 'vx_cfe_curve.csv'
VX_FRONT_FILE = 'vx_front_ohlcv.csv'
ZN_FILE = 'zn_futures_ohlcv.csv'
IEF_FILE = 'ief_ohlcv.csv'
ZN_ROLL_LOG = '.zn_futures_ohlcv.rolls.json'

VX_CURVE_FIELDS = ('contract', 'expiry', 'days_to_expiry', 'open', 'high', 'low', 'close', 'settle',
                   'volume', 'open_interest')
VX_CURVE_COLUMNS = ['timestamp', 'date'] + [f'vx{k}_{f}' for k in (1, 2, 3) for f in VX_CURVE_FIELDS]
VX_FRONT_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'settle', 'contract',
                    'days_to_expiry', 'roll_adjust_cum']
ZN_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume', 'roll_adjust_cum']
IEF_COLUMNS = ['timestamp', 'date', 'open', 'high', 'low', 'close', 'volume', 'dividend', 'adjclose']
COLUMNS = {VX_CURVE_FILE: VX_CURVE_COLUMNS, VX_FRONT_FILE: VX_FRONT_COLUMNS, ZN_FILE: ZN_COLUMNS,
           IEF_FILE: IEF_COLUMNS}

# First row of a from-scratch build (the backfill). The curve is raw exchange data, so it goes
# back to the first full year with settlement prices in every CBOE row (settles are 0 before
# 2013-05-20). The adjusted series start with the rest of macro_2's five-year OHLCV history.
DEFAULT_START = {VX_CURVE_FILE: date(2014, 1, 2), VX_FRONT_FILE: date(2021, 1, 4),
                 ZN_FILE: date(2021, 1, 4), IEF_FILE: date(2021, 1, 4)}

VX_ROLL_DAYS = 5
VX_DECIMALS = 4          # CBOE prints 4 decimals
ZN_DECIMALS = 6          # 1/64 = 0.015625
IEF_DECIMALS = 4         # Yahoo serves float32-ish ETF prices (91.169998 -> 91.17)
TR_DECIMALS = 6
MONTH_CODES = 'FGHJKMNQUVXZ'


class HistoryError(RuntimeError):
    """A file cannot be appended to safely (schema, partial line, ...). Nothing was written;
    resolve it with an explicit repair."""


class SourceBlocked(RuntimeError):
    """The source refused the request or served something that is not data. Stop; do not retry harder."""


# ── trading calendar ──────────────────────────────────────────────────────────────────────
# Sessions that the holiday rules below would close but the exchange opened.
EXTRA_SESSIONS = frozenset({date(2015, 4, 3)})     # Good Friday 2015: CFE open (payrolls day)


def _easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = (h + el - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) given weekday of a month; n=-1 for the last one."""
    if n > 0:
        d = date(year, month, 1)
        return d + timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
    d = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


_HOLIDAYS: dict[int, frozenset] = {}


def exchange_holidays(year: int) -> frozenset:
    """Full-day US exchange holidays under the NYSE rules (CFE and CBOT follow them)."""
    if year not in _HOLIDAYS:
        h = set()
        ny = date(year, 1, 1)
        if ny.weekday() == 6:
            h.add(ny + timedelta(days=1))
        elif ny.weekday() < 5:
            h.add(ny)                               # a Saturday New Year is not observed
        h.add(_nth_weekday(year, 1, 0, 3))          # Martin Luther King Jr. Day
        h.add(_nth_weekday(year, 2, 0, 3))          # Washington's Birthday
        h.add(_easter(year) - timedelta(days=2))    # Good Friday
        h.add(_nth_weekday(year, 5, 0, -1))         # Memorial Day
        if year >= 2022:
            h.add(_observed(date(year, 6, 19)))     # Juneteenth
        h.add(_observed(date(year, 7, 4)))
        h.add(_nth_weekday(year, 9, 0, 1))          # Labor Day
        h.add(_nth_weekday(year, 11, 3, 4))         # Thanksgiving
        h.add(_observed(date(year, 12, 25)))
        _HOLIDAYS[year] = frozenset(h)
    return _HOLIDAYS[year]


def is_trading_day(d: date) -> bool:
    if d in EXTRA_SESSIONS:
        return True
    return d.weekday() < 5 and d not in exchange_holidays(d.year)


def sessions_after(d0: date, d1: date) -> int:
    """Trading sessions x with d0 < x <= d1."""
    n, x = 0, d0 + timedelta(days=1)
    while x <= d1:
        n += is_trading_day(x)
        x += timedelta(days=1)
    return n


def shift_sessions(d: date, n: int) -> date:
    """The trading session n sessions after (n > 0) or before (n < 0) d."""
    step = timedelta(days=1 if n > 0 else -1)
    x, left = d, abs(n)
    while left:
        x += step
        left -= is_trading_day(x)
    return x


def final_cutoff(now: datetime | None = None) -> date:
    """Bars dated strictly before this date are final: their New York day has ended."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(NY).date()


def contract_code(root: str, month: date) -> str:
    return f'{root}{MONTH_CODES[month.month - 1]}{month.year % 100:02d}'


# ── formatting and the append-only writer ─────────────────────────────────────────────────

def _fmt(x, nd: int) -> str:
    """Deterministic decimal text: fixed nd decimals, trailing zeros dropped, blank for None/NaN."""
    if x is None:
        return ''
    x = float(x)
    if not math.isfinite(x):
        return ''
    s = f'{x:.{nd}f}'
    if '.' in s:
        s = s.rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def _fmt_int(x) -> str:
    if x is None:
        return ''
    x = float(x)
    return str(int(round(x))) if math.isfinite(x) else ''


def _num(s):
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _ts(d: date) -> str:
    """Rows are keyed by trade date; the timestamp is that date at 00:00, not an observation time."""
    return f'{d.isoformat()} 00:00:00'


def _line(values) -> str:
    buf = io.StringIO()
    csv.writer(buf, lineterminator='\n').writerow(values)
    return buf.getvalue()


def _ehd():
    # Imported lazily: extract_historical_data's _run wiring imports this module.
    import extract_historical_data
    return extract_historical_data


def resolve_data_dir(data_dir=None) -> str:
    return os.path.abspath(data_dir if data_dir is not None else _ehd().OUTPUT_DIR)


def read_table(path: str):
    """(header, rows as dicts of str, text); (None, [], '') for a missing or 0-byte file."""
    try:
        with open(path, newline='') as fh:
            text = fh.read()
    except FileNotFoundError:
        return None, [], ''
    if not text:
        return None, [], ''
    rdr = csv.reader(io.StringIO(text))
    header = next(rdr, None)
    rows = [dict(zip(header, r)) for r in rdr if r]
    return header, rows, text


def append_rows(path: str, columns: list, build, *, pre_write=None) -> tuple[list, list]:
    """Append the rows build(existing_rows) returns, under the file's lock, never touching
    the bytes already in the file.

    build gets the existing rows (dicts of str, [] for a new file) and returns new rows (dicts
    of str keyed by `columns`); only rows dated after the file's last row are written, and they
    must be in strictly increasing date order. pre_write(new_rows) runs under the lock right
    before the CSV is replaced (the ZN roll log is written there, so a crash cannot leave rows
    whose roll is unrecorded). No new rows -> no write at all (the file keeps its bytes and
    mtime). Returns (appended, existing)."""
    ehd = _ehd()
    with ehd._csv_lock(path):
        header, existing, text = read_table(path)
        if header is None:
            text = _line(columns)
            last = None
        else:
            if header != list(columns):
                raise HistoryError(f'{os.path.basename(path)}: header {header} != expected {list(columns)}')
            if not text.endswith('\n'):
                raise HistoryError(f'{os.path.basename(path)}: no final newline (partial write?) - repair first')
            last = existing[-1]['date'] if existing else None
        new = [r for r in build(existing) if last is None or r['date'] > last]
        for a, b in zip(new, new[1:]):
            if b['date'] <= a['date']:
                raise HistoryError(f'{os.path.basename(path)}: new rows not in increasing date order '
                                   f'({a["date"]} then {b["date"]})')
        if not new:
            return [], existing
        if pre_write is not None:
            pre_write(new)
        ehd._atomic_write_text(path, text + ''.join(_line([r[c] for c in columns]) for r in new))
    return new, existing


def declare(data_dir: str, filename: str) -> None:
    """Column contract for the CC feed scanner; every value column of these files is filled."""
    cols = [c for c in COLUMNS[filename] if c not in ('timestamp', 'date')]
    _ehd().declare_columns(os.path.join(data_dir, filename), active=cols, writer=WRITER)


def _atomic_json(path: str, obj) -> None:
    _ehd()._atomic_write_text(path, json.dumps(obj, indent=1, default=str) + '\n')


def _drift(stored_rows: list, expected: dict, columns: list, limit: int = 10) -> tuple[int, list]:
    """(rows checked, rows whose stored values differ from what the source gives now). A
    difference is a source revision; the stored row stays. expected: {date_str: row dict}.
    Checks the newest `limit` stored rows."""
    out, checked = [], 0
    for r in stored_rows[-limit:]:
        e = expected.get(r['date'])
        if e is None:
            continue
        checked += 1
        diff = {c: (r.get(c), e.get(c)) for c in columns if c not in ('timestamp',) and r.get(c) != e.get(c)}
        if diff:
            out.append({'date': r['date'], 'stored_vs_source': diff})
    return checked, out


# ── CBOE VX ───────────────────────────────────────────────────────────────────────────────
CBOE_LISTING_URL = 'https://www.cboe.com/us/futures/market_statistics/historical_data/product/list/VX/'
CBOE_CDN = 'https://cdn.cboe.com/'
CBOE_CONTRACT_PATH = 'data/us/futures/market_statistics/historical_data/VX/VX_{expiry}.csv'
USER_AGENT = 'macro_2 futures_history_extractors (daily research collector)'
REQUEST_PAUSE_S = 0.7
CBOE_REQUIRED = ('Trade Date', 'Futures', 'Open', 'High', 'Low', 'Close', 'Settle', 'Total Volume',
                 'Open Interest')


def parse_cboe_vx_csv(text: str, expiry: date | None = None) -> dict:
    """{trade_date: bar} from one CBOE per-contract VX file.

    bar = {open, high, low, close, settle (floats or None), volume, open_interest (int), futures}.
    Prices of 0 are 'no value'; a zero-volume day has no OHLC at all (CBOE fills those rows with
    placeholders such as high 21.1 / low 22.8). Raises ValueError on an unexpected layout."""
    rdr = csv.DictReader(io.StringIO(text))
    missing = [c for c in CBOE_REQUIRED if c not in (rdr.fieldnames or [])]
    if missing:
        raise ValueError(f'CBOE VX file: missing column(s) {missing}; header {rdr.fieldnames}')
    out = {}
    for r in rdr:
        raw = (r.get('Trade Date') or '').strip()
        if not raw:
            continue
        d = date.fromisoformat(raw)

        def px(k):
            v = _num(r.get(k))
            return v if v is not None and v > 0 else None
        vol, oi = _num(r.get('Total Volume')), _num(r.get('Open Interest'))
        o, h, lo, c = (px(k) for k in ('Open', 'High', 'Low', 'Close'))
        if not vol:
            o = h = lo = c = None
        out[d] = {'open': o, 'high': h, 'low': lo, 'close': c, 'settle': px('Settle'),
                  'volume': int(vol) if vol is not None else None,
                  'open_interest': int(oi) if oi is not None else None,
                  'futures': (r.get('Futures') or '').strip()}
    if expiry is not None and out and max(out) > expiry:
        raise ValueError(f'CBOE VX {expiry}: a row dated {max(out)} is after expiry')
    return out


class CboeVX:
    """Plain, paced GETs against CBOE's public historical-data files.

    cache_dir (optional) keeps a copy of every file fetched and serves contracts that expired
    more than a week before `cutoff` from it (those files no longer change)."""

    def __init__(self, session=None, cache_dir=None, pause=REQUEST_PAUSE_S):
        self.s = session or requests.Session()
        if session is None:
            self.s.headers['User-Agent'] = USER_AGENT
        self.cache_dir, self.pause = cache_dir, pause
        self._last = 0.0
        self.requests = 0
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _get(self, url):
        wait = self.pause - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.s.get(url, timeout=30)
        finally:
            self._last = time.monotonic()
            self.requests += 1
        if r.status_code in (401, 403, 429):
            raise SourceBlocked(f'{url}: HTTP {r.status_code} - stopping (no retries)')
        r.raise_for_status()
        return r

    def _cache(self, name, text):
        if self.cache_dir:
            _ehd()._atomic_write_text(os.path.join(self.cache_dir, name), text)

    def listing(self) -> dict:
        """{expiry: cdn path} of the MONTHLY VX contracts, ascending."""
        r = self._get(CBOE_LISTING_URL)
        try:
            data = r.json()
        except ValueError:
            raise SourceBlocked(f'{CBOE_LISTING_URL}: not JSON (content-type {r.headers.get("content-type")})')
        out = {}
        for items in (data.values() if isinstance(data, dict) else []):
            for it in items:
                if it.get('duration_type') == 'M' and it.get('futures_root') == 'VX' and it.get('expire_date'):
                    out[date.fromisoformat(it['expire_date'])] = it.get('path') or CBOE_CONTRACT_PATH.format(
                        expiry=it['expire_date'])
        if not out:
            raise SourceBlocked(f'{CBOE_LISTING_URL}: no monthly VX contracts in the listing')
        self._cache('_listing_VX.json', r.text)
        return dict(sorted(out.items()))

    def contract(self, expiry: date, path: str | None = None, cutoff: date | None = None) -> dict:
        name = f'VX_{expiry.isoformat()}.csv'
        if self.cache_dir and cutoff is not None and expiry < cutoff - timedelta(days=7):
            p = os.path.join(self.cache_dir, name)
            if os.path.exists(p):
                with open(p, newline='') as fh:
                    return parse_cboe_vx_csv(fh.read(), expiry)
        url = CBOE_CDN + (path or CBOE_CONTRACT_PATH.format(expiry=expiry.isoformat()))
        text = self._get(url).text
        if not text.startswith('Trade Date'):
            raise SourceBlocked(f'{url}: not a CBOE CSV (starts {text[:40]!r})')
        bars = parse_cboe_vx_csv(text, expiry)
        self._cache(name, text)
        return bars


def vx_target_expiry(d: date, expiries, roll_days: int = VX_ROLL_DAYS):
    """The monthly contract vx_front holds on session d: the first expiring after d with more
    than roll_days sessions left (d excluded, expiry day included)."""
    for e in expiries:
        if e > d and sessions_after(d, e) > roll_days:
            return e
    return None


def vx_curve_row(d: date, expiries, bars: dict):
    """The vx_cfe_curve row for session d, or None when any of the three contracts lacks d."""
    later = [e for e in expiries if e > d][:3]
    if len(later) < 3:
        return None
    row = {'timestamp': _ts(d), 'date': d.isoformat()}
    for k, e in enumerate(later, 1):
        b = bars.get(e, {}).get(d)
        if b is None or b['settle'] is None:
            return None
        p = f'vx{k}_'
        row[p + 'contract'] = contract_code('VX', e)
        row[p + 'expiry'] = e.isoformat()
        row[p + 'days_to_expiry'] = str((e - d).days)
        for f in ('open', 'high', 'low', 'close', 'settle'):
            row[p + f] = _fmt(b[f], VX_DECIMALS)
        row[p + 'volume'] = _fmt_int(b['volume'])
        row[p + 'open_interest'] = _fmt_int(b['open_interest'])
    return row


def _vx_front_row(d, e, b, adj):
    return {'timestamp': _ts(d), 'date': d.isoformat(),
            **{f: _fmt(None if b[f] is None else b[f] + adj, VX_DECIMALS)
               for f in ('open', 'high', 'low', 'close', 'settle')},
            'contract': contract_code('VX', e), 'days_to_expiry': str((e - d).days),
            'roll_adjust_cum': _fmt(adj, VX_DECIMALS)}


def vx_front_state(rows: list):
    """(last date, held expiry, roll_adjust_cum) from vx_front rows; None for an empty file."""
    if not rows:
        return None
    r = rows[-1]
    d = date.fromisoformat(r['date'])
    return d, d + timedelta(days=int(r['days_to_expiry'])), float(r['roll_adjust_cum'])


def vx_front_rows(sessions, expiries, bars: dict, state=None, roll_days: int = VX_ROLL_DAYS):
    """Continue vx_front over `sessions` (ascending; those at or before the state's date are
    skipped). state = vx_front_state(existing rows) or None to start at roll_adjust_cum 0.

    Returns (rows, rolls, stop): stop is None, or why the run ended early (a session some
    contract does not have yet); the rows before it are complete and may be written."""
    last, held, adj = state if state else (None, None, 0.0)
    rows, rolls = [], []
    for d in sessions:
        if last is not None and d <= last:
            continue
        target = vx_target_expiry(d, expiries, roll_days)
        if target is None:
            return rows, rolls, f'{d}: no listed contract has more than {roll_days} sessions left'
        if held is None:
            held = target
        elif target != held:
            if target < held:
                raise HistoryError(f'vx_front: roll target {target} precedes held contract {held} on {d}')
            ob, nb = bars.get(held, {}).get(last), bars.get(target, {}).get(last)
            if last is None or ob is None or nb is None or ob['settle'] is None or nb['settle'] is None:
                return rows, rolls, f'{d}: roll {held}->{target} needs both settlements on {last}'
            gap = ob['settle'] - nb['settle']
            adj = float(_fmt(adj + gap, VX_DECIMALS))
            rolls.append({'first_date': d.isoformat(), 'ref_date': last.isoformat(),
                          'from': contract_code('VX', held), 'to': contract_code('VX', target),
                          'old_settle': ob['settle'], 'new_settle': nb['settle'],
                          'gap': float(_fmt(gap, VX_DECIMALS)), 'roll_adjust_cum': adj})
            held = target
        b = bars.get(held, {}).get(d)
        if b is None or b['settle'] is None:
            return rows, rolls, f'{d}: {contract_code("VX", held)} has no settlement yet'
        rows.append(_vx_front_row(d, held, b, adj))
        last = d
    return rows, rolls, None


def vx_curve_rows(sessions, expiries, bars: dict, after: date | None = None):
    """Curve rows for the contiguous run of complete sessions after `after`; (rows, stop)."""
    rows = []
    for d in sessions:
        if after is not None and d <= after:
            continue
        r = vx_curve_row(d, expiries, bars)
        if r is None:
            return rows, f'{d}: one of the three contracts has no settlement yet'
        rows.append(r)
    return rows, None


def vx_sessions(bars: dict, after: date | None, cutoff: date) -> list:
    """Every date some fetched contract has, after `after` and before `cutoff`."""
    return sorted({d for b in bars.values() for d in b
                   if (after is None or d > after) and d < cutoff})


def update_vx(data_dir=None, *, now=None, source: CboeVX | None = None, log=print,
              roll_days: int = VX_ROLL_DAYS) -> list:
    """Append the finished sessions to vx_cfe_curve.csv and vx_front_ohlcv.csv."""
    data_dir = resolve_data_dir(data_dir)
    cutoff = final_cutoff(now)
    paths = {f: os.path.join(data_dir, f) for f in (VX_CURVE_FILE, VX_FRONT_FILE)}
    _, curve_rows0, _ = read_table(paths[VX_CURVE_FILE])
    _, front_rows0, _ = read_table(paths[VX_FRONT_FILE])
    if not curve_rows0 or not front_rows0:
        raise HistoryError('vx files not bootstrapped - run scripts/backfill_futures_history_20260922.py --apply')
    last = min(date.fromisoformat(curve_rows0[-1]['date']), date.fromisoformat(front_rows0[-1]['date']))
    src = source or CboeVX()
    listing = src.listing()
    expiries = list(listing)
    later = [e for e in expiries if e > cutoff][:3]
    needed = [e for e in expiries if e > last - timedelta(days=15) and (not later or e <= later[-1])]
    bars = {e: src.contract(e, listing[e], cutoff) for e in needed}
    sessions = vx_sessions(bars, last - timedelta(days=15), cutoff)
    out = []

    def curve_build(existing):
        after = date.fromisoformat(existing[-1]['date'])
        rows, stop = vx_curve_rows(sessions, expiries, bars, after)
        out.append(('curve', rows, stop))
        return rows
    new_c, existing_c = append_rows(paths[VX_CURVE_FILE], VX_CURVE_COLUMNS, curve_build)
    exp_c = {d.isoformat(): vx_curve_row(d, expiries, bars) for d in sessions}
    checked_c, drift_c = _drift(existing_c, {k: v for k, v in exp_c.items() if v}, VX_CURVE_COLUMNS)

    def front_build(existing):
        rows, rolls, stop = vx_front_rows(sessions, expiries, bars, vx_front_state(existing), roll_days)
        out.append(('front', rows, stop, rolls))
        return rows
    new_f, existing_f = append_rows(paths[VX_FRONT_FILE], VX_FRONT_COLUMNS, front_build)
    exp_f = {}
    for r in existing_f[-10:]:
        d = date.fromisoformat(r['date'])
        e = d + timedelta(days=int(r['days_to_expiry']))
        b = bars.get(e, {}).get(d)
        if b is not None:
            exp_f[r['date']] = _vx_front_row(d, e, b, float(r['roll_adjust_cum']))
    checked_f, drift_f = _drift(existing_f, exp_f, VX_FRONT_COLUMNS)
    for f in (VX_CURVE_FILE, VX_FRONT_FILE):
        declare(data_dir, f)
    stops = {o[0]: o[2] for o in out if o[2]}
    rolls = [x for o in out if o[0] == 'front' for x in o[3]]
    res = []
    for f, new, existing, checked, drift, label in (
            (VX_CURVE_FILE, new_c, existing_c, checked_c, drift_c, 'VX futures curve (CBOE)'),
            (VX_FRONT_FILE, new_f, existing_f, checked_f, drift_f, 'VX front month (CBOE, fwd-adjusted)')):
        rows = existing + new
        res.append({'indicator': label, 'file': f, 'last_date': rows[-1]['date'] if rows else None,
                    'rows': len(new), 'total_rows': len(rows), 'drift_checked': checked, 'drift': drift,
                    'stopped': stops.get('curve' if f == VX_CURVE_FILE else 'front'),
                    'rolls': rolls if f == VX_FRONT_FILE else [], 'requests': src.requests})
        log(f"  💾 {f}: +{len(new)} row(s), last {res[-1]['last_date']}"
            + (f" — DRIFT on {len(drift)} stored row(s) (not rewritten)" if drift else ''))
    return res


# ── Yahoo (ZN=F, IEF) ─────────────────────────────────────────────────────────────────────
ZN_GENERIC = 'ZN=F'
IEF_SYMBOL = 'IEF'


def yahoo_frame_to_bars(df):
    """({date: bar}, dropped) from a yfinance history() frame (auto_adjust=False, actions=True).

    Dates are the New York date of each bar. Rows missing any of open/high/low/close are dropped
    and listed in `dropped` (yf_safe already trims the trailing price-less bars Yahoo serves)."""
    bars, dropped = {}, []
    if df is None or len(df) == 0:
        return bars, dropped
    idx = df.index
    if getattr(idx, 'tz', None) is not None:
        idx = idx.tz_convert(NY)
    col = {c: (df[c].tolist() if c in df.columns else [None] * len(df))
           for c in ('Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Capital Gains', 'Stock Splits')}
    for i, ts in enumerate(idx):
        d = date(ts.year, ts.month, ts.day)
        o, h, lo, c = (_num(col[k][i]) for k in ('Open', 'High', 'Low', 'Close'))
        if None in (o, h, lo, c):
            dropped.append(d)
            continue
        vol = _num(col['Volume'][i])
        bars[d] = {'open': o, 'high': h, 'low': lo, 'close': c,
                   'volume': int(vol) if vol is not None else None,
                   'dividend': (_num(col['Dividends'][i]) or 0.0) + (_num(col['Capital Gains'][i]) or 0.0),
                   'split': _num(col['Stock Splits'][i]) or 0.0}
    return bars, dropped


def fetch_yahoo(symbol: str, start: date):
    """Daily bars through yf_safe (never a raw yf.Ticker): ({date: bar}, dropped)."""
    from . import yf_safe
    df = yf_safe.Ticker(symbol).history(start=start.isoformat(), interval='1d', auto_adjust=False, actions=True)
    return yahoo_frame_to_bars(df)


def final_bars(bars: dict, cutoff: date):
    """Only finished sessions on trading days: ({date: bar}, [dropped non-trading dates])."""
    keep, off = {}, []
    for d, b in bars.items():
        if d >= cutoff:
            continue
        if not is_trading_day(d):
            off.append(d)
            continue
        keep[d] = b
    return dict(sorted(keep.items())), sorted(off)


# ── IEF ───────────────────────────────────────────────────────────────────────────────────

def ief_state(rows: list):
    if not rows:
        return None
    r = rows[-1]
    return date.fromisoformat(r['date']), float(r['close']), float(r['adjclose'])


def _ief_row(d, b, adjc):
    return {'timestamp': _ts(d), 'date': d.isoformat(),
            **{f: _fmt(b[f], IEF_DECIMALS) for f in ('open', 'high', 'low', 'close')},
            'volume': _fmt_int(b['volume']), 'dividend': _fmt(b['dividend'], TR_DECIMALS),
            'adjclose': _fmt(adjc, TR_DECIMALS)}


def ief_rows(bars: dict, state=None):
    """Continue ief_ohlcv over the sorted final bars. (rows, stop)."""
    last, pclose, padj = state if state else (None, None, None)
    rows = []
    for d, b in sorted(bars.items()):
        if last is not None and d <= last:
            continue
        if b['split'] not in (0.0, 1.0):
            return rows, f'{d}: stock split {b["split"]} - Yahoo re-bases all history; repair by hand'
        close = float(_fmt(b['close'], IEF_DECIMALS))
        div = float(_fmt(b['dividend'], TR_DECIMALS))
        adjc = close if padj is None else float(_fmt(padj * (close + div) / pclose, TR_DECIMALS))
        rows.append(_ief_row(d, b, adjc))
        last, pclose, padj = d, close, adjc
    return rows, None


def update_ief(data_dir=None, *, now=None, fetch=fetch_yahoo, log=print) -> dict:
    data_dir = resolve_data_dir(data_dir)
    path = os.path.join(data_dir, IEF_FILE)
    _, rows0, _ = read_table(path)
    if not rows0:
        raise HistoryError('ief_ohlcv.csv not bootstrapped - run scripts/backfill_futures_history_20260922.py --apply')
    last = date.fromisoformat(rows0[-1]['date'])
    raw, dropped_nan = fetch(IEF_SYMBOL, last - timedelta(days=20))
    bars, off = final_bars(raw, final_cutoff(now))
    stop = []

    def build(existing):
        rows, s = ief_rows(bars, ief_state(existing))
        stop.append(s)
        return rows
    new, existing = append_rows(path, IEF_COLUMNS, build)
    exp = {d.isoformat(): {'date': d.isoformat(), **{f: _fmt(b[f], IEF_DECIMALS) for f in ('open', 'high', 'low', 'close')},
                           'volume': _fmt_int(b['volume']), 'dividend': _fmt(b['dividend'], TR_DECIMALS)}
           for d, b in bars.items()}
    checked, drift = _drift(existing, exp, ['date', 'open', 'high', 'low', 'close', 'volume', 'dividend'])
    declare(data_dir, IEF_FILE)
    rows = existing + new
    log(f"  💾 {IEF_FILE}: +{len(new)} row(s), last {rows[-1]['date']}"
        + (f" — DRIFT on {len(drift)} stored row(s) (not rewritten)" if drift else ''))
    return {'indicator': 'IEF (7-10y Treasury ETF)', 'file': IEF_FILE, 'last_date': rows[-1]['date'],
            'rows': len(new), 'total_rows': len(rows), 'drift_checked': checked, 'drift': drift,
            'stopped': stop[0] if stop else None, 'dropped_nan': [str(d) for d in dropped_nan], 'dropped_non_trading': [str(d) for d in off]}


# ── ZN ────────────────────────────────────────────────────────────────────────────────────

def last_business_day(year: int, month: int) -> date:
    d = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def zn_last_trading_day(year: int, month: int) -> date:
    """CBOT 10-Year T-Note: the 7th business day preceding the last business day of the month."""
    return shift_sessions(last_business_day(year, month), -7)


def zn_rolls_between(d0: date, d1: date) -> list:
    """[(ltd, old code, new code)] for quarterly LTDs with d0 < ltd < d1."""
    out = []
    for y in range(d0.year, d1.year + 1):
        for m in (3, 6, 9, 12):
            ltd = zn_last_trading_day(y, m)
            if d0 < ltd < d1:
                ny, nm = (y + 1, 3) if m == 12 else (y, m + 3)
                out.append((ltd, contract_code('ZN', date(y, m, 1)), contract_code('ZN', date(ny, nm, 1))))
    return out


def zn_contract_on(d: date):
    """The contract Yahoo's ZN=F carries on session d; None on an LTD (hybrid bar, omitted)."""
    y, m = d.year, ((d.month - 1) // 3 + 1) * 3
    while True:
        ltd = zn_last_trading_day(y, m)
        if d < ltd:
            return contract_code('ZN', date(y, m, 1))
        if d == ltd:
            return None
        y, m = (y + 1, 3) if m == 12 else (y, m + 3)


def zn_symbol(code: str) -> str:
    return f'{code}.CBT'


def zn_state(rows: list):
    if not rows:
        return None
    r = rows[-1]
    return date.fromisoformat(r['date']), float(r['roll_adjust_cum']), float(r['close']) - float(r['roll_adjust_cum'])


def _zn_row(d, b, adj):
    return {'timestamp': _ts(d), 'date': d.isoformat(),
            **{f: _fmt(b[f] + adj, ZN_DECIMALS) for f in ('open', 'high', 'low', 'close')},
            'volume': _fmt_int(b['volume']), 'roll_adjust_cum': _fmt(adj, ZN_DECIMALS)}


def zn_rows(bars: dict, state=None, gaps: dict | None = None):
    """Continue zn_futures_ohlcv over sorted final ZN=F bars.

    gaps: {ltd: {'gap': float, ...}} for every LTD crossed. LTD sessions are omitted.
    Returns (rows, rolls, stop)."""
    last, adj = (state[0], state[1]) if state else (None, 0.0)
    gaps = gaps or {}
    rows, rolls = [], []
    for d, b in sorted(bars.items()):
        if last is not None and d <= last:
            continue
        if zn_contract_on(d) is None:
            continue
        if last is not None:
            for ltd, old, new in zn_rolls_between(last, d):
                g = gaps.get(ltd)
                if g is None:
                    return rows, rolls, f'{d}: roll {old}->{new} (LTD {ltd}) has no measured gap yet'
                if g.get('last_old_date', last.isoformat()) != last.isoformat() or \
                        g.get('first_new_date', d.isoformat()) != d.isoformat():
                    return rows, rolls, (f'{d}: roll {old}->{new} gap was taken {g.get("last_old_date")}->'
                                         f'{g.get("first_new_date")}, the file rolls {last}->{d}; not written')
                adj = float(_fmt(adj + g['gap'], ZN_DECIMALS))
                rolls.append({**g, 'ltd': ltd.isoformat(), 'old': old, 'new': new,
                              'last_old_date': last.isoformat(), 'first_new_date': d.isoformat(),
                              'roll_adjust_cum': adj})
        rows.append(_zn_row(d, b, adj))
        last = d
    return rows, rolls, None


def _ols(x: list, y: list):
    """(slope, intercept, r2, residual sd) of y on x."""
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sxx = sum((a - mx) ** 2 for a in x)
    sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    syy = sum((b - my) ** 2 for b in y)
    if sxx <= 0:
        raise ValueError('_ols: no variation in x')
    slope = sxy / sxx
    icpt = my - slope * mx
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else float('nan')
    resid = [b - icpt - slope * a for a, b in zip(x, y)]
    sd = statistics.stdev(resid) if len(resid) > 2 else float('nan')
    return slope, icpt, r2, sd


def estimate_zn_gap(zn: dict, ief: dict, last_old: date, first_new: date, window: int = 250) -> dict | None:
    """Estimate a roll gap Yahoo can no longer measure (the new contract is delisted).

    The new contract's price at the last old session is backed out of its first price after the
    roll: new(L) = generic(F) / (1 + beta * IEF total return L->F), beta = OLS slope of generic
    ZN on IEF daily total returns over the `window` same-contract sessions up to L. Over
    1,279 two-session windows since 2021 this predictor's error has sd ~0.14 point (MAE 0.10);
    the gaps it gives for 2021-2026 run from -0.66 to +1.19. On the one roll checkable against
    the listed new contract (2026-06, measured 0.25) it gave 0.56. It is an estimate, and the
    roll log says so (est_error_sd_pts is the in-sample residual sd, which understates it)."""
    days = sorted(d for d in zn if d in ief and d <= last_old)
    xs, ys = [], []
    for a, b in zip(days, days[1:]):
        ca, cb = zn_contract_on(a), zn_contract_on(b)
        if ca is None or ca != cb or sessions_after(a, b) != 1:
            continue
        ys.append(zn[b]['close'] / zn[a]['close'] - 1)
        xs.append((ief[b]['close'] + ief[b]['dividend']) / ief[a]['close'] - 1)
    xs, ys = xs[-window:], ys[-window:]
    if len(xs) < 60 or last_old not in ief or first_new not in ief:
        return None
    beta, _, r2, sd = _ols(xs, ys)
    tr = 1.0
    ief_days = sorted(d for d in ief if last_old < d <= first_new)
    prev = last_old
    for d in ief_days:
        tr *= (ief[d]['close'] + ief[d]['dividend']) / ief[prev]['close']
        prev = d
    r = tr - 1
    new_l = zn[first_new]['close'] / (1 + beta * r)
    k = max(1, sessions_after(last_old, first_new))
    return {'gap': float(_fmt(zn[last_old]['close'] - new_l, ZN_DECIMALS)), 'method': 'estimated_ief',
            'generic_close_last_old': zn[last_old]['close'], 'est_new_close_last_old': round(new_l, 6),
            'ief_beta': round(beta, 4), 'ief_beta_r2': round(r2, 3), 'ief_return': round(r, 6),
            'est_error_sd_pts': round(sd * zn[last_old]['close'] * math.sqrt(k), 4), 'beta_obs': len(xs)}


def measure_zn_gap(zn: dict, new_bars: dict, last_old: date, first_new: date) -> dict | None:
    """Exact gap from the new contract's own Yahoo history; None unless the generic equals the
    new contract at the first new session (i.e. Yahoo has switched as expected)."""
    nl, nf = new_bars.get(last_old), new_bars.get(first_new)
    if nl is None or nf is None or last_old not in zn or first_new not in zn:
        return None
    if abs(nf['close'] - zn[first_new]['close']) > 1 / 128:      # within half a tick (ticks are 1/64)
        return None
    return {'gap': float(_fmt(zn[last_old]['close'] - nl['close'], ZN_DECIMALS)), 'method': 'measured',
            'generic_close_last_old': zn[last_old]['close'], 'new_close_last_old': nl['close'],
            'generic_close_first_new': zn[first_new]['close'], 'new_close_first_new': nf['close']}


def _volume_ratio(zn: dict, last_old: date, first_new: date):
    """Generic volume at the first new session over its median in the 5 sessions to last_old:
    >> 1 confirms Yahoo moved from the thin delivery-month contract to the next one."""
    before = [zn[d]['volume'] for d in sorted(zn) if d <= last_old and zn[d]['volume']][-5:]
    v = zn.get(first_new, {}).get('volume')
    if not before or not v:
        return None
    return round(v / statistics.median(before), 1)


def zn_gaps(zn: dict, after: date | None, *, fetch=fetch_yahoo, ief: dict | None = None,
            allow_estimate: bool = False, known: dict | None = None) -> dict:
    """{ltd: gap info} for every roll after `after` whose first new session is in `zn`.
    Measured from the new contract when Yahoo still lists it; otherwise estimated from IEF
    when allow_estimate (backfill only); otherwise absent (the rows after it wait)."""
    days = sorted(zn)
    if not days:
        return {}
    lo = after if after is not None else days[0] - timedelta(days=1)
    out = {}
    for ltd, old, new in zn_rolls_between(lo, days[-1] + timedelta(days=1)):
        if known and ltd in known:
            out[ltd] = known[ltd]
            continue
        pre = [d for d in days if d < ltd]
        post = [d for d in days if d > ltd]
        if not pre or not post:
            continue
        L, F = pre[-1], post[0]
        try:
            nb, _ = fetch(zn_symbol(new), L - timedelta(days=10))
        except Exception:
            nb = {}
        g = measure_zn_gap(zn, nb, L, F)
        if g is None and allow_estimate and ief:
            g = estimate_zn_gap(zn, ief, L, F)
        if g is None:
            continue
        g.update(last_old_date=L.isoformat(), first_new_date=F.isoformat(), volume_ratio=_volume_ratio(zn, L, F))
        out[ltd] = g
    return out


def load_roll_log(data_dir: str) -> dict:
    p = os.path.join(data_dir, ZN_ROLL_LOG)
    try:
        with open(p) as fh:
            log = json.load(fh)
    except (OSError, ValueError):
        return {'file': ZN_FILE, 'rolls': []}
    return log if isinstance(log, dict) and isinstance(log.get('rolls'), list) else {'file': ZN_FILE, 'rolls': []}


def update_zn(data_dir=None, *, now=None, fetch=fetch_yahoo, log=print) -> dict:
    data_dir = resolve_data_dir(data_dir)
    path = os.path.join(data_dir, ZN_FILE)
    _, rows0, _ = read_table(path)
    if not rows0:
        raise HistoryError('zn_futures_ohlcv.csv not bootstrapped - run scripts/backfill_futures_history_20260922.py --apply')
    last = date.fromisoformat(rows0[-1]['date'])
    raw, dropped_nan = fetch(ZN_GENERIC, last - timedelta(days=20))
    bars, off = final_bars(raw, final_cutoff(now))
    gaps = zn_gaps(bars, last, fetch=fetch)
    applied, stop = [], []

    def build(existing):
        rows, rolls, s = zn_rows(bars, zn_state(existing), gaps)
        applied.extend(rolls)
        stop.append(s)
        return rows

    def pre_write(new):
        if applied:
            rl = load_roll_log(data_dir)
            rl['rolls'].extend(applied)
            rl['updated_at'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            _atomic_json(os.path.join(data_dir, ZN_ROLL_LOG), rl)
    new, existing = append_rows(path, ZN_COLUMNS, build, pre_write=pre_write)
    exp = {}
    for r in existing[-10:]:
        d = date.fromisoformat(r['date'])
        if d in bars:
            exp[r['date']] = _zn_row(d, bars[d], float(r['roll_adjust_cum']))
    checked, drift = _drift(existing, exp, ZN_COLUMNS)
    declare(data_dir, ZN_FILE)
    rows = existing + new
    log(f"  💾 {ZN_FILE}: +{len(new)} row(s), last {rows[-1]['date']}"
        + (f", roll(s) {[r['ltd'] for r in applied]}" if applied else '')
        + (f" — waiting: {stop[0]}" if stop and stop[0] else '')
        + (f" — DRIFT on {len(drift)} stored row(s) (not rewritten)" if drift else ''))
    return {'indicator': 'ZN 10Y note futures (Yahoo ZN=F, fwd-adjusted)', 'file': ZN_FILE,
            'last_date': rows[-1]['date'], 'rows': len(new), 'total_rows': len(rows), 'drift_checked': checked,
            'drift': drift, 'rolls': applied if new else [], 'stopped': stop[0] if stop else None,
            'dropped_nan': [str(d) for d in dropped_nan], 'dropped_non_trading': [str(d) for d in off]}


# ── entry point for extract_historical_data._run ──────────────────────────────────────────

def extract_futures_history(data_dir=None, now=None) -> list:
    """Daily update of all four files; one result dict per file that updated. Never raises."""
    print('\n📊 Extracting tradable-instrument history (VX CBOE, IEF, ZN=F)...')
    results = []
    for name, fn in (('vx', update_vx), ('ief', update_ief), ('zn', update_zn)):
        try:
            r = fn(data_dir, now=now)
            results.extend(r if isinstance(r, list) else [r])
        except Exception as e:  # one source failing must not stop the others or the run
            print(f'  ❌ futures history {name}: {type(e).__name__}: {e}')
    return results


# ── analysis helpers (used by the backfill report) ────────────────────────────────────────

def duration_tracking(prices: dict, yields: dict, start: date, end: date, *, breaks=(),
                      raw: dict | None = None, dividends: dict | None = None, step: int = 1) -> dict | None:
    """Regress an instrument's returns (%) on 10Y yield changes (percentage points).

    prices: {date: price} (for a forward-adjusted future, the adjusted close; `raw` then gives
    the raw close used as the return's denominator, so a return is the P&L over the contract's
    notional). dividends: {date: cash} added on ex-dates (total return). Changes are taken
    between consecutive dates common to both series inside [start, end] (every `step`-th one
    for non-overlapping multi-day changes); a change spanning one of `breaks` (dates strictly
    inside it: roll LTDs) is skipped, so roll-gap estimates cannot move the fit. The slope is
    -effective duration (years): a 1 bp rise moves the price by -D/100 %."""
    common = sorted(d for d in prices if d in yields and start <= d <= end)[::step]
    xs, ys = [], []
    breaks = sorted(breaks)
    for a, b in zip(common, common[1:]):
        if any(a < x < b for x in breaks):
            continue
        base = (raw or prices)[a]
        div = sum(v for d, v in (dividends or {}).items() if a < d <= b)
        ys.append(100.0 * (prices[b] - prices[a] + div) / base)
        xs.append(yields[b] - yields[a])
    if len(xs) < 30:
        return None
    slope, icpt, r2, sd = _ols(xs, ys)
    return {'n': len(xs), 'beta': round(slope, 3), 'effective_duration': round(-slope, 2), 'r2': round(r2, 3),
            'corr': round(-math.sqrt(r2) if slope < 0 else math.sqrt(r2), 3), 'resid_sd_pct': round(sd, 3),
            'intercept_pct': round(icpt, 4), 'first': common[0].isoformat(), 'last': common[-1].isoformat()}
