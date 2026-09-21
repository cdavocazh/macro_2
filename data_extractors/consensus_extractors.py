"""Macro-release consensus snapshots (ForexFactory + Kalshi) and first-release surprises.

Why this exists: none of macro_2's historical_data files carried a consensus expectation, so the
CC trading pipeline's surprise layer and its conditional / post-event initiation
(CLI_OS/Agent_Orchestration/CC/backfill/ROADMAP.md) had nothing to measure "actual - expected"
against. Two free sources fill that: the ForexFactory weekly calendar feed (sell-side consensus
`forecast` and `previous` per release; CURRENT WEEK ONLY, so it has to be snapshotted going
forward) and Kalshi's public market data (market-implied distributions from threshold ladders;
settled markets keep their price history, so the past can be back-filled with
scripts/backfill_kalshi_consensus_20260922.py). Actuals come from FRED/ALFRED first releases.

FILES (historical_data/)
------------------------
macro_consensus.csv - point-in-time snapshot log. Key (date, release_key, release_time_utc,
source): the day's last snapshot wins (append_to_csv(subset=...)); a re-run is idempotent.
    timestamp         when the snapshot was taken (naive UTC, as append_to_csv writes it)
    date              UTC day of `timestamp` (the as-of day)
    release_key       canonical key, see RELEASES / the table below
    release_time_utc  scheduled release time, ISO 8601 'YYYY-MM-DDTHH:MM:SSZ'
    source            'ff' (ForexFactory) | 'kalshi' (market-implied)
    consensus         canonical units (`unit`). ff: the calendar's forecast. kalshi: the implied
                      MEDIAN of the event's threshold ladder, interpolated (method below)
    previous          ff: the calendar's previous value (as ForexFactory shows it, possibly
                      revised); kalshi: blank
    unit              'percent' (percentage points: rates, % changes) | 'thousands' (payrolls,
                      jobless claims). ('index' is parsed but no mapped key uses it yet.)
    detail            compact JSON. ff: title, impact, forecast/previous raw strings, feed date.
                      kalshi: event, series, ladder [[t, yes_bid, yes_ask, p_raw, p_mono], ...]
                      (t = threshold in canonical units, p = P(actual > t)), median (= consensus),
                      median_grid, mean, tail_lo/tail_hi, spread_avg, spread_at_median, volume,
                      open_interest, price_sources, method ('live' quotes, or 'candle_1440' in the
                      back-fill)
    Only releases that are still in the future are recorded (a snapshot taken after the
    release can never be a consensus). ForexFactory rows are kept even when the forecast is
    blank (the previous value is still useful); Kalshi rows are written only when the ladder
    yields a consensus (>= 3 usable strikes and a median inside the ladder).

macro_surprises.csv - one row per release, identified by (release_key, ET release date).
    timestamp         when the row was computed or last changed (naive UTC); an unchanged row
                      keeps its timestamp, so a re-run rewrites nothing
    date              release date (UTC)
    release_key, release_time_utc
    actual            FIRST-RELEASE value as known at release (the ALFRED vintage of that day;
                      live: the FRED value fetched after the release), canonical units
    actual_source     e.g. 'FRED CPIAUCSL first release 2026-09-11 (m/m % of SA index, 1dp)'
    consensus_ff, consensus_kalshi
                      the LAST snapshot of that source taken strictly before release_time_utc
                      with a non-blank consensus - never one taken at or after the release
    surprise_ff, surprise_kalshi   actual - consensus
    surprise_z        preferred surprise (ff if present, else kalshi) / sample sd (ddof=1) of the
                      same key's EARLIER preferred surprises; blank with fewer than 8 earlier
                      surprises, or when that sd is 0
  Columns appended after the fixed schema:
    reference_period  the observation the release published: month or quarter start, the
                      week-ending Saturday (claims), or the FOMC decision date
    consensus_ff_asof, consensus_kalshi_asof
                      timestamp of the snapshot each consensus was taken from (audit trail for
                      the point-in-time rule)
    z_source          'ff' | 'kalshi': the source of the surprise that surprise_z scales
    z_n               number of earlier surprises in that sd
  A release is written once its actual is on FRED; until then it is retried on every run
  (`surprises` looks back 60 days when called from the full extraction). History before the
  deployment day is Kalshi-only (the back-fill; ForexFactory serves no history), so the first
  ForexFactory surprises are scaled by an sd of mostly Kalshi surprises until their own accumulate.

READING IT
    cons = pd.read_csv('historical_data/macro_consensus.csv')
    # consensus in force for each upcoming release: the newest snapshot per release and source
    cur = cons.sort_values('timestamp').groupby(['release_key', 'release_time_utc', 'source']).tail(1)
    sur = pd.read_csv('historical_data/macro_surprises.csv')    # one row per scored release

KEY MAPPING
-----------
 release_key        ForexFactory title (USD)     Kalshi series             FRED actual (first release; half-up rounding)
 cpi_mom            CPI m/m                      KXCPI                     CPIAUCSL  m/m % of the SA index, 1dp
 core_cpi_mom       Core CPI m/m                 KXCPICORE                 CPILFESL  m/m % of the SA index, 1dp
 cpi_yoy            CPI y/y                      KXCPIYOY                  CPIAUCNS  12-month % of the NSA index, 1dp (BLS
                                                                                     computes 12-month changes unadjusted)
 core_cpi_yoy       Core CPI y/y                 KXCPICOREYOY              CPILFENS  12-month % of the NSA index, 1dp
 nfp                Non-Farm Employment Change   KXPAYROLLS                PAYEMS    level(t) - level(t-1) in the SAME vintage
                                                                                     (the prior month as revised that day), thousands
 unemployment_rate  Unemployment Rate            KXU3                      UNRATE    level, 1dp
 retail_sales_mom   Retail Sales m/m             KXUSRETAIL (+KXRETAIL)    MARTSMPCSM44X72USS  Census-published m/m % (advance)
                                                                                     [check: RSAFS m/m %]
 pce_mom            PCE Price Index m/m          KXPCEHEAD                 DPCERGM1M225SBEA  BEA-published m/m %  [check: PCEPI]
 core_pce_mom       Core PCE Price Index m/m     KXPCECORE                 DPCCRGM1M225SBEA  BEA-published m/m %  [check: PCEPILFE]
 ppi_mom            PPI m/m                      KXUSPPI                   PPIFIS    m/m % of the SA final-demand index, 1dp
 core_ppi_mom       Core PPI m/m                 -                         PPIFES    m/m % of SA final demand less foods & energy, 1dp
 jobless_claims     Unemployment Claims          KXJOBLESSCLAIMS (+KXJOBLESS)  ICSA  SA initial claims / 1000 (thousands)
 gdp_qoq_saar       Advance GDP q/q              KXGDP                     A191RL1Q225SBEA  BEA-published SAAR %, first (= advance)
                                                                                     estimate  [check: GDPC1 annualised]
 fomc_rate_upper    Federal Funds Rate           KXFED                     DFEDTARU  target upper bound on the first day after the
                                                                                     decision (the new range takes effect then)
Series in parentheses are history-only (their events are all settled). "Prelim"/"Final" GDP,
core retail, average hourly earnings, ISM and other calendar titles are unmapped: they are
skipped and listed once per run. Scheduled times: 08:30 ET, FOMC 14:00 ET.

KALSHI METHOD
-------------
Each market of an event is a threshold ("Above x", "At least x"): YES pays if the published value
exceeds the strike. Every market is converted to S(t) = P(actual > t) on the publication grid
(`step`: 0.1 pp, 1 thousand, or 0.25 pp for the Fed; "at least k" -> t = k - step). The price is the
mid of the YES bid/ask when the book is two-sided and at most 50c wide (weight 1/spread, floor 1c),
else the last trade (weight 4, i.e. like a 25c-wide quote); a strike with neither is dropped. A
weighted pool-adjacent-violators fit makes S non-increasing. `consensus` is the implied MEDIAN of the
unrounded value: a print above t means the unrounded value reached t + step/2, so S is placed at
t + step/2 and its 0.5 crossing is interpolated linearly between the two bracketing strikes (e.g.
P(CPI > 0.5) = 0.57, P(CPI > 0.6) = 0.245 -> 0.55 + 0.07/0.325 * 0.1 = 0.5715). `detail` adds the
grid median (smallest grid value with CDF >= 0.5) and the implied mean, whose tails are collapsed
onto the ladder's ends (mass below the lowest strike at that strike, above the highest at highest +
step, between two strikes at the midpoint of the grid values in that interval). The mean is NOT the
consensus: ladders stop short of heavy tails (2026-09-21: 22% of the payrolls mass sat above the
top 125K strike, 32.5% of GDP's above 4.0%), which drags the mean toward the ladder - payrolls
74.7K against a median of 86.9K. A ladder with < 3 usable strikes, or whose median falls outside
the strikes, gives no consensus.

CLI (run from the repo root)
----------------------------
  python -m data_extractors.consensus_extractors snapshot  [--data-dir DIR] [--no-ff] [--no-kalshi] [--dry-run]
  python -m data_extractors.consensus_extractors surprises [--since YYYY-MM-DD] [--data-dir DIR] [--dry-run]
  python -m data_extractors.consensus_extractors verify    [--since YYYY-MM-DD]   # FRED-only cross-check
Exit codes: 0 ok, 1 partial (a source or some series failed), 2 failure (nothing usable).
Source etiquette: ForexFactory gets ONE request per run (one retry on a network error or 5xx, none
on 4xx/429 or a non-JSON reply); Kalshi requests are paced >= 0.35 s apart (about 13 per snapshot);
FRED is only asked for series that have a release still waiting for its actual. Inside a run each
of Kalshi and FRED gets a 60 s wall-clock budget and one retry (a hung source costs the 15-minute
full extraction about 3 minutes at worst, not 10); the back-fill script has no budget.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import statistics
import sys
import time
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo

UTC = timezone.utc
ET = ZoneInfo("America/New_York")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USER_AGENT = "macro_2-consensus/1.0 (macro research; low-rate polling)"

CONSENSUS_FILE = "macro_consensus.csv"
SURPRISES_FILE = "macro_surprises.csv"
CONSENSUS_COLUMNS = ["timestamp", "date", "release_key", "release_time_utc", "source",
                     "consensus", "previous", "unit", "detail"]
CONSENSUS_KEY = ["date", "release_key", "release_time_utc", "source"]
CONSENSUS_SORT = ["timestamp", "release_time_utc", "release_key", "source"]
SURPRISES_COLUMNS = ["timestamp", "date", "release_key", "release_time_utc", "actual", "actual_source",
                     "consensus_ff", "consensus_kalshi", "surprise_ff", "surprise_kalshi", "surprise_z",
                     # appended after the fixed schema (documented in the module docstring)
                     "reference_period", "consensus_ff_asof", "consensus_kalshi_asof", "z_source", "z_n"]

# Writer-declared column contracts (extract_historical_data.declare_columns) for both files.
CONSENSUS_CONTRACT = dict(
    active=["release_key", "release_time_utc", "source", "consensus", "previous", "unit", "detail"],
    writer="data_extractors/consensus_extractors.py snapshot",
)
SURPRISES_CONTRACT = dict(
    active=[c for c in SURPRISES_COLUMNS if c not in ("timestamp", "date")],
    writer="data_extractors/consensus_extractors.py surprises",
)

MIN_Z_HISTORY = 8                  # surprise_z needs at least this many earlier surprises
SURPRISE_LOOKBACK_DAYS = 60        # the full extraction refreshes releases this recent
ACTUAL_WINDOW = (-1, 3)            # FRED's first-release date may trail the ET release date by <= 3 days
MAX_SPREAD = 0.50                  # a quote wider than this is not a price
TRADE_WEIGHT = 4.0                 # a last-trade price counts like a quote 25c wide
MIN_STRIKES = 3
SNAPSHOT_DATE_FMT = "%Y-%m-%d %H:%M:%S"


class SourceError(RuntimeError):
    """A data source failed or answered with something unusable (message is safe to print)."""


# ── Release registry ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ActualSpec:
    series: str          # FRED series id
    transform: str       # level | pct1 | pct12 | diff1 | per1000 | fomc_upper (| saar for checks)
    decimals: int        # headline rounding (half-up, as the agencies round)
    label: str           # shown in actual_source
    check: tuple = ()    # (series, transform, label): the headline recomputed from levels (`verify`)


@dataclass(frozen=True)
class ReleaseSpec:
    key: str
    unit: str            # percent | thousands
    step: float          # publication grid in canonical units
    et_time: str         # scheduled release time, America/New_York
    freq: str            # reference period: M | Q | W | FOMC
    ff_titles: tuple     # ForexFactory titles (USD) that are this release
    kalshi: tuple        # ((series_ticker, live), ...); live=False: history only
    kalshi_scale: float  # Kalshi strike units -> canonical units
    actual: ActualSpec


def _spec(key, unit, step, freq, ff, kalshi, actual, et_time="08:30", scale=1.0):
    return ReleaseSpec(key, unit, step, et_time, freq, tuple(ff), tuple(kalshi), scale, actual)


RELEASES = {s.key: s for s in [
    _spec("cpi_mom", "percent", 0.1, "M", ["CPI m/m"], [("KXCPI", True)],
          ActualSpec("CPIAUCSL", "pct1", 1, "m/m % of SA index, 1dp")),
    _spec("core_cpi_mom", "percent", 0.1, "M", ["Core CPI m/m"], [("KXCPICORE", True)],
          ActualSpec("CPILFESL", "pct1", 1, "m/m % of SA index, 1dp")),
    _spec("cpi_yoy", "percent", 0.1, "M", ["CPI y/y"], [("KXCPIYOY", True)],
          ActualSpec("CPIAUCNS", "pct12", 1, "12-month % of NSA index, 1dp")),
    _spec("core_cpi_yoy", "percent", 0.1, "M", ["Core CPI y/y"], [("KXCPICOREYOY", True)],
          ActualSpec("CPILFENS", "pct12", 1, "12-month % of NSA index, 1dp")),
    _spec("nfp", "thousands", 1.0, "M", ["Non-Farm Employment Change"], [("KXPAYROLLS", True)],
          ActualSpec("PAYEMS", "diff1", 0, "m/m change in the same vintage, thousands"), scale=0.001),
    _spec("unemployment_rate", "percent", 0.1, "M", ["Unemployment Rate"], [("KXU3", True)],
          ActualSpec("UNRATE", "level", 1, "level, 1dp")),
    _spec("retail_sales_mom", "percent", 0.1, "M", ["Retail Sales m/m"],
          [("KXUSRETAIL", True), ("KXRETAIL", False)],
          ActualSpec("MARTSMPCSM44X72USS", "level", 1, "Census-published m/m %, 1dp",
                     check=("RSAFS", "pct1", "m/m % of RSAFS"))),
    _spec("pce_mom", "percent", 0.1, "M", ["PCE Price Index m/m"], [("KXPCEHEAD", True)],
          ActualSpec("DPCERGM1M225SBEA", "level", 1, "BEA-published m/m %, 1dp",
                     check=("PCEPI", "pct1", "m/m % of PCEPI"))),
    _spec("core_pce_mom", "percent", 0.1, "M", ["Core PCE Price Index m/m"], [("KXPCECORE", True)],
          ActualSpec("DPCCRGM1M225SBEA", "level", 1, "BEA-published m/m %, 1dp",
                     check=("PCEPILFE", "pct1", "m/m % of PCEPILFE"))),
    _spec("ppi_mom", "percent", 0.1, "M", ["PPI m/m"], [("KXUSPPI", True)],
          ActualSpec("PPIFIS", "pct1", 1, "m/m % of SA index, 1dp")),
    _spec("core_ppi_mom", "percent", 0.1, "M", ["Core PPI m/m"], [],
          ActualSpec("PPIFES", "pct1", 1, "m/m % of SA index, 1dp")),
    _spec("jobless_claims", "thousands", 1.0, "W", ["Unemployment Claims"],
          [("KXJOBLESSCLAIMS", True), ("KXJOBLESS", False)],
          ActualSpec("ICSA", "per1000", 1, "SA initial claims / 1000"), scale=0.001),
    _spec("gdp_qoq_saar", "percent", 0.1, "Q", ["Advance GDP q/q"], [("KXGDP", True)],
          ActualSpec("A191RL1Q225SBEA", "level", 1, "BEA-published SAAR %, 1dp",
                     check=("GDPC1", "saar", "annualised q/q % of GDPC1"))),
    _spec("fomc_rate_upper", "percent", 0.25, "FOMC", ["Federal Funds Rate"], [("KXFED", True)],
          ActualSpec("DFEDTARU", "fomc_upper", 2, "upper bound effective the day after the decision"),
          et_time="14:00"),
]}

UNIT_DECIMALS = {"percent": 4, "thousands": 2, "index": 3}


def normalize_title(title) -> str:
    return re.sub(r"\s+", " ", str(title or "").strip()).lower()


FF_TITLES = {normalize_title(t): s.key for s in RELEASES.values() for t in s.ff_titles}


# ── Small helpers ────────────────────────────────────────────────────────────

def _requests():
    import requests  # lazy: the pure helpers (and their tests) do not need it
    return requests


def _num(x):
    """float(x) for numbers and numeric strings; None for blanks, NaN and junk."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(str(x).strip().replace(",", "")) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


_FRACTION = re.compile(r"\.(\d+)")


def parse_utc(value):
    """An ISO-8601 string ('Z', an offset, or naive = UTC; any fraction length) -> aware UTC datetime.

    Python 3.10 (the laptop) rejects 'Z' and fractions other than 3/6 digits; 3.13 (the VPS) does not.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        d = value
    else:
        s = str(value).strip()
        if not s:
            return None
        if s[-1] in "Zz":
            s = s[:-1] + "+00:00"
        s = _FRACTION.sub(lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC)


def iso_z(d: datetime) -> str:
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_ts(d: datetime) -> str:
    """Naive-UTC text, the layout append_to_csv writes timestamps in."""
    return d.astimezone(UTC).strftime(SNAPSHOT_DATE_FMT)


def et_date(d: datetime) -> date:
    return d.astimezone(ET).date()


def release_at(day: date, et_hhmm: str) -> datetime:
    """The scheduled release instant (UTC) for an ET calendar day and an ET wall-clock time."""
    hh, mm = (int(x) for x in et_hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET).astimezone(UTC)


def half_up(x: Decimal, decimals: int) -> Decimal:
    return x.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def _snap(t: float, step: float) -> float:
    """Snap a threshold onto the publication grid when it is within float noise of it (4.099999 -> 4.1)."""
    g = round(t / step)
    if abs(t - g * step) <= 1e-4 * step:
        return round(g * step, 10)
    return round(t, 10)


def _finite(obj):
    """obj with every NaN/inf float replaced by None (JSON has no NaN)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_finite(v) for v in obj]
    return obj


def _compact(obj) -> str:
    return json.dumps(_finite(obj), separators=(",", ":"), ensure_ascii=True, allow_nan=False)


# ── ForexFactory ─────────────────────────────────────────────────────────────

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
_FF_VALUE = re.compile(r"^([+-]?\d+(?:\.\d+)?)\s*([KMB%]?)$", re.I)
_TO_THOUSANDS = {"K": 1.0, "M": 1e3, "B": 1e6}


def parse_ff_value(raw, unit: str):
    """A ForexFactory forecast/previous string -> float in canonical units, or None.

    percent:   "0.3%" -> 0.3, "-0.1%" -> -0.1, "4.3%" -> 4.3 (a bare "4.3" is accepted too)
    thousands: "201K" -> 201.0, "1.95M" -> 1950.0 (a bare number or a "%" is rejected)
    index:     "47.5" -> 47.5 (a suffix is rejected)
    "" / None / anything else -> None.
    """
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    if not s:
        return None
    m = _FF_VALUE.match(s)
    if not m:
        return None
    v, suffix = float(m.group(1)), m.group(2).upper()
    if unit == "percent":
        out = v if suffix in ("%", "") else None
    elif unit == "thousands":
        out = v * _TO_THOUSANDS[suffix] if suffix in _TO_THOUSANDS else None
    elif unit == "index":
        out = v if suffix == "" else None
    else:
        raise ValueError(f"unknown unit {unit!r}")
    return None if out is None else round(out, 6)


def map_ff_event(event: dict):
    """release_key for a ForexFactory event, or None (non-USD or unmapped title)."""
    if str(event.get("country") or "").upper() != "USD":
        return None
    return FF_TITLES.get(normalize_title(event.get("title")))


def fetch_ff_calendar(session=None, timeout=(8, 15)) -> list:
    """GET the current-week feed: one request, one retry on a network error/5xx, none on 4xx/429."""
    rq = _requests()
    s = session or rq.Session()
    for attempt in range(2):
        try:
            r = s.get(FF_URL, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=timeout)
        except rq.RequestException as e:
            if attempt == 0:
                time.sleep(5)
                continue
            raise SourceError(f"ForexFactory unreachable ({type(e).__name__})") from None
        if r.status_code >= 500 and attempt == 0:
            time.sleep(5)
            continue
        if r.status_code != 200:
            raise SourceError(f"ForexFactory HTTP {r.status_code} (not retried: rate limit or block)")
        try:
            data = r.json()
        except ValueError:
            raise SourceError("ForexFactory answered with non-JSON (a rate-limit page?) - not retried") from None
        if not isinstance(data, list):
            raise SourceError(f"ForexFactory payload is {type(data).__name__}, expected a list")
        return data
    raise SourceError("ForexFactory failed twice")


def _snapshot_row(now, key, rt, source, consensus, previous, unit, detail) -> dict:
    return {"timestamp": now, "date": now.astimezone(UTC).date().isoformat(), "release_key": key,
            "release_time_utc": iso_z(rt), "source": source, "consensus": consensus,
            "previous": previous, "unit": unit, "detail": _compact(detail)}


def ff_snapshot_rows(events: list, now: datetime):
    """Rows for every mapped USD event still in the future; info lists what was skipped."""
    rows, unmapped, past, bad = {}, set(), 0, 0
    for e in events:
        if not isinstance(e, dict) or str(e.get("country") or "").upper() != "USD":
            continue
        title = str(e.get("title") or "").strip()
        key = FF_TITLES.get(normalize_title(title))
        if key is None:
            unmapped.add(title)
            continue
        rt = parse_utc(e.get("date"))
        if rt is None:
            bad += 1
            continue
        if rt <= now:
            past += 1
            continue
        spec = RELEASES[key]
        detail = {"title": title, "impact": e.get("impact"), "forecast": e.get("forecast"),
                  "previous": e.get("previous"), "date": e.get("date")}
        rows[(key, rt)] = _snapshot_row(now, key, rt, "ff", parse_ff_value(e.get("forecast"), spec.unit),
                                        parse_ff_value(e.get("previous"), spec.unit), spec.unit, detail)
    return list(rows.values()), {"unmapped": sorted(unmapped), "past": past, "bad_date": bad}


# ── Kalshi: ladder -> implied distribution ───────────────────────────────────

_WORD_KIND = {"above": "greater", "more than": "greater", "greater than": "greater", "over": "greater",
              "at least": "greater_or_equal", "below": "less", "less than": "less", "under": "less",
              "at most": "less_or_equal"}
_THRESH_TEXT = re.compile(r"^\s*(above|more than|greater than|over|at least|below|less than|under|at most)"
                          r"\s+\$?(-?[\d,]*\.?\d+)", re.I)
_THRESH_TICKER = re.compile(r"-T(N)?(-?\d+(?:\.\d+)?)$")


def market_threshold(market: dict, spec: ReleaseSpec):
    """(t, above) for a threshold market: YES pays iff actual > t (above) or iff actual <= t (not above).

    t is in canonical units on the publication grid. Uses strike_type/floor_strike/cap_strike; the
    historical tier's oldest markets carry none, so "Above 1.3%" / "Above 350,000" and a '-T1.3' /
    '-TN0.1' (N = minus) ticker suffix are read instead. Range, custom and functional markets -> None.
    """
    step, scale = spec.step, spec.kalshi_scale
    st = str(market.get("strike_type") or "").strip().lower()
    kind, k = None, None
    if st in ("greater", "greater_or_equal"):
        k, kind = _num(market.get("floor_strike")), st
    elif st in ("less", "less_or_equal"):
        k, kind = _num(market.get("cap_strike")), st
    elif st in ("", "none"):
        for text in (market.get("yes_sub_title"), market.get("subtitle"), market.get("title")):
            m = _THRESH_TEXT.match(str(text or ""))
            if m:
                kind, k = _WORD_KIND[m.group(1).lower()], _num(m.group(2))
                break
        if kind is None:
            m = _THRESH_TICKER.search(str(market.get("ticker") or ""))
            if m:
                kind, k = "greater", float(m.group(2)) * (-1.0 if m.group(1) else 1.0)
    if kind is None or k is None:
        return None
    kc = k * scale
    t, above = {"greater": (kc, True), "greater_or_equal": (kc - step, True),
                "less": (kc - step, False), "less_or_equal": (kc, False)}[kind]
    return _snap(t, step), above


def quote_prob(bid, ask, last=None, prev=None):
    """(p, weight, source, bid, ask) for a YES contract, or None when it has no usable price."""
    if bid is not None and ask is not None and 0.0 <= bid <= ask <= 1.0 and ask > 0.0 and ask - bid <= MAX_SPREAD:
        return (bid + ask) / 2.0, 1.0 / max(ask - bid, 0.01), "mid", bid, ask
    for v, src in ((last, "last"), (prev, "prev")):
        if v is not None and 0.0 < v < 1.0:
            return v, TRADE_WEIGHT, src, bid, ask
    return None


def pava_nonincreasing(y, w):
    """Weighted least-squares non-increasing fit (pool adjacent violators)."""
    blocks = []                                    # [mean, weight, count]
    for yi, wi in zip(y, w):
        blocks.append([float(yi), float(wi), 1])
        while len(blocks) > 1 and blocks[-2][0] < blocks[-1][0]:
            m2, w2, c2 = blocks.pop()
            m1, w1, c1 = blocks.pop()
            blocks.append([(m1 * w1 + m2 * w2) / (w1 + w2), w1 + w2, c1 + c2])
    out = []
    for m, _w, c in blocks:
        out.extend([m] * c)
    return out


def implied_distribution(points, step: float) -> dict:
    """points: iterable of (t, P(actual > t), weight). Returns the fitted survival function and summary.

    Keys: t, p_raw, p_mono, n, median, median_grid, mean, tail_lo, tail_hi, ok, reason. Duplicate
    thresholds are pooled by weight. `ok` needs >= MIN_STRIKES strikes and a median strictly inside
    the ladder.
      median       interpolated median of the latent (unrounded) value: a print above t means the
                   unrounded value reached t + step/2, so S is placed at u = t + step/2 and the 0.5
                   crossing is interpolated linearly between the two bracketing strikes. This is the
                   Kalshi consensus: it does not depend on the tails beyond the ladder.
      median_grid  smallest grid value whose CDF reaches 0.5 (spread uniformly across a gap)
      mean         of the distribution with each tail collapsed onto its boundary (below the lowest
                   strike -> that strike, above the highest -> highest + step). Biased toward the
                   ladder when a tail is heavy (payrolls, GDP), so it is reported, not used.
    """
    agg = {}
    for t, p, w in points:
        if p is None or w is None or w <= 0 or not math.isfinite(p) or not math.isfinite(t):
            continue
        a = agg.setdefault(float(t), [0.0, 0.0])
        a[0] += p * w
        a[1] += w
    ts = sorted(agg)
    raw = [min(1.0, max(0.0, agg[t][0] / agg[t][1])) for t in ts]
    out = {"t": ts, "p_raw": raw, "n": len(ts), "p_mono": [], "mean": None, "median": None,
           "median_grid": None, "tail_lo": None, "tail_hi": None, "ok": False, "reason": ""}
    if len(ts) < MIN_STRIKES:
        out["reason"] = f"{len(ts)} usable strike(s) < {MIN_STRIKES}"
        return out
    s = [min(1.0, max(0.0, v)) for v in pava_nonincreasing(raw, [agg[t][1] for t in ts])]
    masses = [(ts[0], 1.0 - s[0])]
    masses += [((ts[i] + step + ts[i + 1]) / 2.0, s[i] - s[i + 1]) for i in range(len(ts) - 1)]
    masses.append((ts[-1] + step, s[-1]))
    out.update(p_mono=s, mean=sum(v * m for v, m in masses), tail_lo=1.0 - s[0], tail_hi=s[-1])
    cdf = [1.0 - v for v in s]
    eps = 1e-9
    i = next((j for j, f in enumerate(cdf) if f >= 0.5 - eps), None)
    if i is None:
        out["reason"] = "median above the ladder (P(actual > top strike) > 0.5)"
    elif i == 0:
        out["reason"] = "median below the ladder (P(actual <= bottom strike) >= 0.5)"
    else:
        lo, hi = ts[i - 1], ts[i]
        mass = s[i - 1] - s[i]
        n_grid = max(1, int(round((hi - lo) / step)))
        k = min(n_grid, max(1, math.ceil(n_grid * (0.5 - cdf[i - 1]) / mass - eps)))
        frac = min(1.0, max(0.0, (s[i - 1] - 0.5) / mass))
        out.update(median=lo + step / 2.0 + frac * (hi - lo), median_grid=_snap(lo + k * step, step), ok=True)
    return out


def ladder_consensus(items, spec: ReleaseSpec) -> dict:
    """items: [(market, quote_prob(...) or None, {'volume': v, 'oi': x, 'asof': ts?})] -> summary + detail."""
    pts, rows, srcs = [], [], Counter()
    volume = oi = 0.0
    unparsed = 0
    for m, q, extra in items:
        th = market_threshold(m, spec)
        if th is None:
            unparsed += 1
            continue
        volume += (extra or {}).get("volume") or 0.0
        oi += (extra or {}).get("oi") or 0.0
        if q is None:
            srcs["none"] += 1
            continue
        p, w, src, bid, ask = q
        t, above = th
        pa = p if above else 1.0 - p
        srcs[src] += 1
        pts.append((t, pa, w))
        rows.append((t, bid, ask, pa, (ask - bid) if (src == "mid") else None))
    dist = implied_distribution(pts, spec.step)
    mono = dict(zip(dist["t"], dist["p_mono"])) if dist["p_mono"] else {}
    ladder = [[_r(t, 6), _r(b), _r(a), _r(p), _r(mono.get(t))]
              for t, b, a, p, _s in sorted(rows, key=lambda r: r[0])]
    spreads = [(t, sp) for t, _b, _a, _p, sp in rows if sp is not None]
    near = (min(spreads, key=lambda x: abs(x[0] + spec.step / 2 - dist["median"]))
            if (spreads and dist["median"] is not None) else None)
    nd = UNIT_DECIMALS.get(spec.unit, 4)
    summary = {
        "ok": dist["ok"], "reason": dist["reason"],
        "consensus": _r(dist["median"], nd) if dist["ok"] else None,
        "detail": {"n": dist["n"], "ladder": ladder, "median": _r(dist["median"], nd),
                   "median_grid": dist["median_grid"], "mean": _r(dist["mean"], nd),
                   "tail_lo": _r(dist["tail_lo"]), "tail_hi": _r(dist["tail_hi"]),
                   "spread_avg": _r(statistics.fmean(sp for _t, sp in spreads)) if spreads else None,
                   "spread_at_median": _r(near[1]) if near else None,
                   "volume": _r(volume, 2), "open_interest": _r(oi, 2),
                   "price_sources": dict(srcs), "unparsed_markets": unparsed},
    }
    return summary


def kalshi_release_time(markets, spec: ReleaseSpec):
    """Scheduled release (UTC) from an event's close time: the ET day it closes on, at the key's
    scheduled ET time; a close after 16:00 ET (the oldest events closed the evening before) moves to
    the next day. Kalshi data markets close 1-5 minutes before the 08:30 ET print, Fed markets 5
    minutes before 14:00 ET."""
    closes = [parse_utc(m.get("close_time")) for m in markets or []]
    closes = [c for c in closes if c is not None]
    if not closes:
        return None
    c = max(closes).astimezone(ET)
    day = c.date() + (timedelta(days=1) if c.hour >= 16 else timedelta(0))
    return release_at(day, spec.et_time)


KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
LIVE_BUDGET_S = 60          # wall-clock cap per source inside the full extraction (15-min watchdog)


def _check_deadline(deadline, what):
    if deadline is not None and time.monotonic() > deadline:
        raise SourceError(f"{what}: time budget exhausted - skipped")


class KalshiClient:
    """Paced, read-only GETs against Kalshi's public market-data API (no auth).

    Settled markets older than Kalshi's historical cutoff are served only by the /historical/*
    endpoints (GET /historical/cutoff); cache_dir caches responses (used by the back-fill, whose
    settled data never changes).
    """

    def __init__(self, min_interval=0.35, timeout=(10, 30), retries=3, cache_dir=None, session=None, budget_s=None):
        self.min_interval, self.timeout, self.retries = min_interval, timeout, retries
        self.cache_dir = cache_dir
        self.session = session
        self._last = 0.0
        self.requests = 0
        self.cache_hits = 0
        self.deadline = time.monotonic() + budget_s if budget_s else None
        if cache_dir:
            os.makedirs(cache_dir, exist_ok=True)

    def _cache_path(self, path, params):
        h = hashlib.sha1((path + "?" + json.dumps(params, sort_keys=True)).encode()).hexdigest()
        return os.path.join(self.cache_dir, h + ".json")

    def get(self, path: str, **params):
        """JSON of GET path; None on 404. Retries 429/5xx/network errors with backoff."""
        if self.cache_dir:
            cp = self._cache_path(path, params)
            if os.path.exists(cp):
                self.cache_hits += 1
                with open(cp) as fh:
                    cached = json.load(fh)
                return None if cached == {"__404__": True} else cached
        _check_deadline(self.deadline, f"Kalshi {path}")
        rq = _requests()
        if self.session is None:
            self.session = rq.Session()
        err = None
        for attempt in range(self.retries + 1):
            _check_deadline(self.deadline, f"Kalshi {path}")
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.session.get(KALSHI_BASE + path, params=params, timeout=self.timeout,
                                     headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            except rq.RequestException as e:
                err = type(e).__name__
                if attempt < self.retries:
                    time.sleep(2 ** attempt)
                    continue
                raise SourceError(f"Kalshi {path}: {err}") from None
            self.requests += 1
            if r.status_code == 429 or r.status_code >= 500:
                err = f"HTTP {r.status_code}"
                if attempt < self.retries:
                    time.sleep(2 * 2 ** attempt)
                    continue
                raise SourceError(f"Kalshi {path}: {err}")
            if r.status_code == 404:
                data = None
            elif r.status_code != 200:
                raise SourceError(f"Kalshi {path}: HTTP {r.status_code}")
            else:
                try:
                    data = r.json()
                except ValueError:
                    raise SourceError(f"Kalshi {path}: non-JSON reply") from None
            if self.cache_dir:
                with open(self._cache_path(path, params), "w") as fh:
                    json.dump({"__404__": True} if data is None else data, fh)
            return data
        raise SourceError(f"Kalshi {path}: {err}")

    def events(self, series: str, status: str, nested: bool = False) -> list:
        out, cursor = [], None
        while True:
            p = {"series_ticker": series, "status": status, "limit": 200}
            if nested:
                p["with_nested_markets"] = "true"
            if cursor:
                p["cursor"] = cursor
            d = self.get("/events", **p) or {}
            batch = d.get("events") or []
            out += batch
            cursor = d.get("cursor")
            if not cursor or not batch:
                return out

    def event_markets(self, event_ticker: str):
        """(markets, tier) - 'historical' for events settled before Kalshi's cutoff, else 'live'."""
        d = self.get("/historical/markets", event_ticker=event_ticker, limit=200) or {}
        if d.get("markets"):
            return d["markets"], "historical"
        d = self.get("/markets", event_ticker=event_ticker, limit=200) or {}
        return d.get("markets") or [], "live"

    def market_candles(self, series: str, ticker: str, start_ts: int, end_ts: int, tier: str, period=1440):
        path = (f"/historical/markets/{ticker}/candlesticks" if tier == "historical"
                else f"/series/{series}/markets/{ticker}/candlesticks")
        d = self.get(path, start_ts=int(start_ts), end_ts=int(end_ts), period_interval=period) or {}
        return d.get("candlesticks") or []


def live_quote(market: dict):
    """quote_prob() from a live market record (dollar strings)."""
    return quote_prob(_num(market.get("yes_bid_dollars")), _num(market.get("yes_ask_dollars")),
                      _num(market.get("last_price_dollars")))


def kalshi_snapshot_rows(client: KalshiClient, now: datetime):
    """One row per live series: its NEXT open event (earliest release still in the future)."""
    rows = []
    info = {"attempted": 0, "failed": [], "no_event": [], "unusable": []}
    for spec in RELEASES.values():
        for series, live in spec.kalshi:
            if not live:
                continue
            info["attempted"] += 1
            try:
                events = client.events(series, "open", nested=True)
            except SourceError as e:
                info["failed"].append(str(e))
                continue
            best = None
            for ev in events:
                rt = kalshi_release_time(ev.get("markets"), spec)
                if rt is not None and rt > now and (best is None or rt < best[0]):
                    best = (rt, ev)
            if best is None:
                info["no_event"].append(series)
                continue
            rt, ev = best
            items = [(m, live_quote(m), {"volume": _num(m.get("volume_fp")), "oi": _num(m.get("open_interest_fp"))})
                     for m in ev.get("markets") or []]
            res = ladder_consensus(items, spec)
            if not res["ok"]:
                info["unusable"].append(f"{ev.get('event_ticker')} ({res['reason']})")
                continue
            detail = {"event": ev.get("event_ticker"), "series": series, "method": "live",
                      "close_time": max((m.get("close_time") or "") for m in ev.get("markets") or [])}
            detail.update(res["detail"])
            rows.append(_snapshot_row(now, spec.key, rt, "kalshi", res["consensus"], None, spec.unit, detail))
    return rows, info


# ── Kalshi event metadata (used by the back-fill) ────────────────────────────

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_RE_MONTH_YEAR = re.compile(_MON + r"\s+(\d{4})\b", re.I)
_RE_QUARTER = re.compile(r"\bQ([1-4])\s+(\d{4})\b", re.I)
_RE_DAY = re.compile(_MON + r"\s+(\d{1,2}),\s*(\d{4})\b", re.I)
_RE_WEEK_ENDING = re.compile(r"week ending\s+" + _MON + r"\s+(\d{1,2}),\s*(\d{4})", re.I)
_RE_RANGE = re.compile(_MON + r"\s+(\d{1,2})(?:,\s*(\d{4}))?\s*(?:-|to)\s*(?:" + _MON + r"\s+)?(\d{1,2})(?:,\s*(\d{4}))?", re.I)
_RE_TICKER_YY = re.compile(r"-(\d{2})[A-Z]{3}")


def _mon(name: str) -> int:
    return _MONTHS.index(name[:3].lower()) + 1


def kalshi_reference_period(event: dict, spec: ReleaseSpec):
    """The observation date an event settles on, from its sub_title/title.

    M: 'In Jul 2026' -> 2026-07-01; Q: 'In Q2 2026' -> 2026-04-01; W: 'For the week ending Sep 12,
    2026' or the legacy 'From Aug 22-28, 2021' / 'Sep 18 to 24, 2022' -> the week-ending Saturday
    (a missing year comes from the ticker, JOBLESS-22SEP17; a non-Saturday date is snapped back to
    its Saturday); FOMC: 'On Sep 16, 2026' -> that date
    (older 'In Jun 2023' events carry no day: None, and the caller uses the close time).
    """
    texts = [str(event.get("sub_title") or ""), str(event.get("title") or "")]
    if spec.freq == "M":
        for t in texts:
            m = _RE_MONTH_YEAR.search(t)
            if m:
                return date(int(m.group(2)), _mon(m.group(1)), 1)
    elif spec.freq == "Q":
        for t in texts:
            m = _RE_QUARTER.search(t)
            if m:
                return date(int(m.group(2)), 3 * (int(m.group(1)) - 1) + 1, 1)
    elif spec.freq == "FOMC":
        for t in texts:
            m = _RE_DAY.search(t)
            if m:
                return date(int(m.group(3)), _mon(m.group(1)), int(m.group(2)))
    elif spec.freq == "W":
        for t in texts:
            m = _RE_WEEK_ENDING.search(t)
            if m:
                return _saturday(date(int(m.group(3)), _mon(m.group(1)), int(m.group(2))))
        ty = _RE_TICKER_YY.search(str(event.get("event_ticker") or ""))
        for t in texts:
            m = _RE_RANGE.search(t)
            if not m:
                continue
            m1, d1, y1, m2, d2, y2 = m.groups()
            mon1 = _mon(m1)
            mon2 = _mon(m2) if m2 else (mon1 if int(d2) >= int(d1) else mon1 % 12 + 1)
            if y2:
                year = int(y2)
            elif y1:                                   # 'Dec 26, 2021-Jan 1' ends in the next year
                year = int(y1) + (1 if mon2 < mon1 else 0)
            elif ty:                                   # the ticker's YY is the week-ending year
                year = 2000 + int(ty.group(1))
            else:
                continue
            try:
                return _saturday(date(year, mon2, int(d2)))
            except ValueError:
                continue
    return None


def _saturday(d: date) -> date:
    """Claims weeks end on a Saturday: snap to the Saturday on or before d. Kalshi labelled
    KXJOBLESSCLAIMS-25JUN12 'week ending Jun 12, 2025' (its Thursday release day); it settled on the
    week ending Jun 7."""
    return d - timedelta(days=(d.weekday() - 5) % 7)


# ── FRED / ALFRED ────────────────────────────────────────────────────────────

FRED_BASE = "https://api.stlouisfed.org/fred"


class FredClient:
    """Read-only FRED/ALFRED client. The API key is never printed: every error text is redacted."""

    def __init__(self, api_key=None, min_interval=0.6, timeout=(10, 60), retries=2, session=None, budget_s=None):
        if api_key is None:
            api_key = os.environ.get("FRED_API_KEY", "")
            if not api_key:
                try:
                    import config  # loads the repo's .env
                    api_key = config.FRED_API_KEY or ""
                except Exception:
                    api_key = ""
        self.api_key = api_key
        self.min_interval, self.timeout, self.retries = min_interval, timeout, retries
        self.session = session
        self._last = 0.0
        self._memo = {}
        self.requests = 0
        self.deadline = time.monotonic() + budget_s if budget_s else None

    def _redact(self, text: str) -> str:
        text = re.sub(r"api_key=[^&\s'\"]+", "api_key=***", str(text))
        return text.replace(self.api_key, "***") if self.api_key else text

    def _get(self, path: str, **params) -> dict:
        if not self.api_key:
            raise SourceError("FRED_API_KEY is not set (.env or environment)")
        _check_deadline(self.deadline, f"FRED {path} {params.get('series_id', '')}".strip())
        rq = _requests()
        if self.session is None:
            self.session = rq.Session()
        q = dict(params, api_key=self.api_key, file_type="json")
        what = f"FRED {path} {params.get('series_id', '')}".strip()
        for attempt in range(self.retries + 1):
            _check_deadline(self.deadline, what)
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.session.get(f"{FRED_BASE}/{path}", params=q, timeout=self.timeout)
            except rq.RequestException as e:
                msg = self._redact(f"{type(e).__name__}: {e}")
                if attempt < self.retries:
                    time.sleep(3 * (attempt + 1))
                    continue
                raise SourceError(f"{what}: {msg}") from None
            self.requests += 1
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise SourceError(f"{what}: HTTP {r.status_code} {self._redact(r.text[:200])}")
            try:
                return r.json()
            except ValueError:
                raise SourceError(f"{what}: non-JSON reply") from None
        raise SourceError(f"{what}: failed")

    def vintages(self, series_id: str, obs_start: date, rt_start: date) -> dict:
        """{obs_date: [(realtime_start, realtime_end, value), ...]} for every vintage since rt_start.

        Periods that began before rt_start come back clipped to it, so only first releases after
        rt_start are meaningful; callers keep rt_start well before the releases they resolve.
        """
        k = ("v", series_id, obs_start, rt_start)
        if k not in self._memo:
            d = self._get("series/observations", series_id=series_id, observation_start=obs_start.isoformat(),
                          realtime_start=rt_start.isoformat(), realtime_end="9999-12-31", limit=100000)
            rows = {}
            for o in d.get("observations") or []:
                rows.setdefault(o["date"], []).append((o["realtime_start"], o["realtime_end"], o["value"]))
            for lst in rows.values():
                lst.sort()
            self._memo[k] = rows
        return self._memo[k]

    def observations(self, series_id: str, obs_start: date) -> dict:
        """{obs_date: value} of the current vintage (for never-revised series such as DFEDTARU)."""
        k = ("o", series_id, obs_start)
        if k not in self._memo:
            d = self._get("series/observations", series_id=series_id, observation_start=obs_start.isoformat(),
                          limit=100000)
            self._memo[k] = {o["date"]: o["value"] for o in d.get("observations") or []}
        return self._memo[k]


def _shift_months(obs: str, n: int) -> str:
    y, m = int(obs[:4]), int(obs[5:7]) - n
    while m <= 0:
        m += 12
        y -= 1
    return f"{y:04d}-{m:02d}-01"


def _asof(periods, vintage: str):
    """Decimal value of one observation in the vintage of `vintage` (YYYY-MM-DD), or None."""
    for rs, re_, v in periods or []:
        if rs <= vintage <= re_:
            try:
                return None if v in (".", "") else Decimal(v)
            except InvalidOperation:
                return None
    return None


def first_releases(rows: dict) -> dict:
    """{obs_date: first realtime_start carrying a value}."""
    out = {}
    for obs, lst in rows.items():
        starts = [rs for rs, _re, v in lst if v not in (".", "")]
        if starts:
            out[obs] = min(starts)
    return out


def apply_transform(transform: str, rows: dict, obs: str, vintage: str, decimals: int):
    """(value, None) or (None, why) - the headline for `obs` computed in the vintage of `vintage`."""
    x = _asof(rows.get(obs), vintage)
    if x is None:
        return None, f"{obs} has no value in the {vintage} vintage"
    if transform == "level":
        v = x
    elif transform == "per1000":
        v = x / 1000
    elif transform in ("pct1", "pct12", "diff1", "saar"):
        back = {"pct1": 1, "pct12": 12, "diff1": 1, "saar": 3}[transform]
        prior = _shift_months(obs, back)
        p = _asof(rows.get(prior), vintage)
        if p is None or p == 0:
            return None, f"{prior} is missing in the {vintage} vintage"
        if transform == "diff1":
            v = x - p
        elif transform == "saar":
            v = ((x / p) ** 4 - 1) * 100
        else:
            v = (x / p - 1) * 100
    else:
        raise ValueError(f"unknown transform {transform!r}")
    return float(half_up(v, decimals)), None


def resolve_actuals(fred: FredClient, key: str, release_days) -> dict:
    """{ET release day: {'actual', 'actual_source', 'reference_period'} | {'error': why} | None}.

    None = not on FRED yet (retry later). The release publishes the observation whose FIRST
    release date lies within ACTUAL_WINDOW of the ET release day (the newest one, if a delayed
    release published two); its headline is computed in that first-release vintage, so a revised
    prior month (payrolls, SA revisions) is taken as it stood that day.
    """
    spec = RELEASES[key]
    a = spec.actual
    days = sorted(set(release_days))
    out = {d: None for d in days}
    if not days:
        return out
    if a.transform == "fomc_upper":
        obs = fred.observations(a.series, days[0] - timedelta(days=7))
        avail = sorted((d, v) for d, v in obs.items() if v not in (".", ""))
        for day in days:
            nxt = next(((d, v) for d, v in avail if d > day.isoformat()), None)
            if nxt and (date.fromisoformat(nxt[0]) - day).days <= 7:
                out[day] = {"actual": float(half_up(Decimal(nxt[1]), a.decimals)),
                            "actual_source": f"FRED {a.series} {nxt[0]} ({a.label})",
                            "reference_period": day.isoformat()}
        return out
    rows, first = actual_rows(fred, key, days[0])
    for day in days:
        lo = (day + timedelta(days=ACTUAL_WINDOW[0])).isoformat()
        hi = (day + timedelta(days=ACTUAL_WINDOW[1])).isoformat()
        cands = [o for o, f in first.items() if lo <= f <= hi]
        if cands:           # a catch-up release after a shutdown publishes several periods: the newest is the headline
            out[day] = actual_for_obs(key, rows, first, max(cands))
    return out


def actual_rows(fred: FredClient, key: str, earliest_day: date):
    """(vintage rows, {obs: first release date}) of a key's actual series, good for releases from earliest_day on."""
    rt_start = earliest_day - timedelta(days=400)
    rows = fred.vintages(RELEASES[key].actual.series, rt_start - timedelta(days=100), rt_start)
    return rows, first_releases(rows)


def actual_for_obs(key: str, rows: dict, first: dict, obs: str):
    """The headline of observation `obs` as first published (its first-release vintage); None if unpublished."""
    a = RELEASES[key].actual
    vintage = first.get(obs)
    if vintage is None:
        return None
    v, why = apply_transform(a.transform, rows, obs, vintage, a.decimals)
    return ({"error": why} if v is None else
            {"actual": v, "actual_source": f"FRED {a.series} first release {vintage} ({a.label})",
             "reference_period": obs})


# ── Surprises ────────────────────────────────────────────────────────────────

def read_rows(path: str) -> list:
    """Raw CSV rows as dicts of strings ([] when the file is missing or empty)."""
    if not os.path.exists(path):
        return []
    with open(path, newline="") as fh:
        return [dict(r) for r in csv.DictReader(fh)]


def parse_snapshots(raw_rows: list) -> list:
    out = []
    for r in raw_rows:
        ts, rt = parse_utc(r.get("timestamp")), parse_utc(r.get("release_time_utc"))
        if ts is None or rt is None or not r.get("release_key"):
            continue
        out.append({"ts": ts, "rt": rt, "release_key": r["release_key"], "source": r.get("source") or "",
                    "consensus": _num(r.get("consensus"))})
    return out


def point_in_time(snaps: list, source: str, release_time: datetime):
    """(consensus, snapshot time) of the last `source` snapshot strictly before release_time with a value."""
    c = [s for s in snaps if s["source"] == source and s["consensus"] is not None and s["ts"] < release_time]
    if not c:
        return None, None
    best = max(c, key=lambda s: s["ts"])
    return best["consensus"], best["ts"]


def group_releases(snaps: list) -> dict:
    """{(release_key, ET release day): [snapshots]} - FF and Kalshi labels of one release meet here
    even if their release_time_utc strings differ (a rescheduled print, a non-standard hour)."""
    g = {}
    for s in snaps:
        g.setdefault((s["release_key"], et_date(s["rt"])), []).append(s)
    return g


def release_time_of(snaps: list) -> datetime:
    """ForexFactory's time when it has one (it carries the actual schedule), else Kalshi's."""
    ff = [s for s in snaps if s["source"] == "ff"]
    return max(ff or snaps, key=lambda s: s["ts"])["rt"]


def _surprise_row_from_csv(r: dict) -> dict:
    out = dict(r)
    for c in ("actual", "consensus_ff", "consensus_kalshi", "surprise_ff", "surprise_kalshi", "surprise_z"):
        out[c] = _num(r.get(c))
    n = _num(r.get("z_n"))
    out["z_n"] = int(n) if n is not None else 0
    for c in ("actual_source", "reference_period", "consensus_ff_asof", "consensus_kalshi_asof", "z_source"):
        out[c] = r.get(c) or None
    return out


def _sig(r: dict) -> tuple:
    def f(v):
        if v is None:
            return ""
        if isinstance(v, float):
            return "" if math.isnan(v) else repr(round(v, 6))
        return str(v)
    return tuple(f(r.get(c)) for c in SURPRISES_COLUMNS[1:])


def pending_releases(snaps: list, existing: list, now: datetime, since=None) -> dict:
    """{release_key: [ET release days]} that have passed, have a pre-release consensus and no actual yet."""
    have_days = set()
    for r in existing:
        t = parse_utc(r.get("release_time_utc"))
        if t is not None and _num(r.get("actual")) is not None:
            have_days.add((r.get("release_key"), et_date(t)))
    out = {}
    for (key, day), group in group_releases(snaps).items():
        rt = release_time_of(group)
        if rt > now or (since and day < since) or (key, day) in have_days:
            continue
        if point_in_time(group, "ff", rt)[0] is None and point_in_time(group, "kalshi", rt)[0] is None:
            continue
        out.setdefault(key, []).append(day)
    return out


def assign_z(rows: list) -> None:
    """surprise_z / z_source / z_n in place, per key in release order (see the module docstring)."""
    by_key = {}
    for r in rows:
        by_key.setdefault(r["release_key"], []).append(r)
    for lst in by_key.values():
        lst.sort(key=lambda r: r["release_time_utc"])
        past = []
        for r in lst:
            if r.get("surprise_ff") is not None:
                pref, src = r["surprise_ff"], "ff"
            elif r.get("surprise_kalshi") is not None:
                pref, src = r["surprise_kalshi"], "kalshi"
            else:
                pref, src = None, None
            r["z_source"], r["z_n"], r["surprise_z"] = src, len(past), None
            if pref is not None and len(past) >= MIN_Z_HISTORY:
                sd = statistics.stdev(past)
                r["surprise_z"] = round(pref / sd, 3) if sd > 0 else None
            if pref is not None:
                past.append(pref)


def build_surprises(snaps: list, existing_raw: list, now: datetime, since=None, actuals=None):
    """(rows, stats): the full surprises table after refreshing every passed release in scope.

    Pure: `actuals` = {(release_key, ET day): resolve_actuals() entry} fetched beforehand. Existing
    rows outside the scope are kept as they are; none is ever deleted. A row whose content does not
    change keeps its timestamp.
    """
    actuals = actuals or {}
    existing = [_surprise_row_from_csv(r) for r in existing_raw]
    by_day, before, orphans = {}, {}, []
    for r in existing:
        t = parse_utc(r.get("release_time_utc"))
        if t is None or not r.get("release_key"):
            orphans.append(r)             # never dropped, never touched
            continue
        by_day[(r["release_key"], et_date(t))] = r
        before[(r["release_key"], et_date(t))] = (_sig(r), r.get("timestamp"))
    stats = Counter()
    for (key, day), group in sorted(group_releases(snaps).items(), key=lambda kv: (kv[0][1], kv[0][0])):
        rt = release_time_of(group)
        if rt > now:
            stats["upcoming"] += 1
            continue
        if since and day < since:
            continue
        c_ff, t_ff = point_in_time(group, "ff", rt)
        c_k, t_k = point_in_time(group, "kalshi", rt)
        if c_ff is None and c_k is None:
            stats["no pre-release consensus"] += 1
            continue
        old = by_day.get((key, day))
        if old is not None and old.get("actual") is not None:
            act = {"actual": old["actual"], "actual_source": old.get("actual_source"),
                   "reference_period": old.get("reference_period")}
        else:
            act = actuals.get((key, day))
            if not act or act.get("actual") is None:
                stats["actual pending" if not act else "actual unresolvable"] += 1
                continue
        row = {"timestamp": None, "date": rt.date().isoformat(), "release_key": key,
               "release_time_utc": iso_z(rt), "actual": act["actual"], "actual_source": act.get("actual_source"),
               "consensus_ff": c_ff, "consensus_kalshi": c_k,
               "surprise_ff": None if c_ff is None else round(act["actual"] - c_ff, 4),
               "surprise_kalshi": None if c_k is None else round(act["actual"] - c_k, 4),
               "surprise_z": None, "reference_period": act.get("reference_period"),
               "consensus_ff_asof": fmt_ts(t_ff) if t_ff else None,
               "consensus_kalshi_asof": fmt_ts(t_k) if t_k else None, "z_source": None, "z_n": 0}
        stats["refreshed" if old is not None else "new"] += 1
        by_day[(key, day)] = row
    assign_z(list(by_day.values()))       # z depends on each key's whole history
    stamp = fmt_ts(now)
    for k, r in by_day.items():
        sig, ts = before.get(k, (None, None))
        r["timestamp"] = ts if (sig is not None and sig == _sig(r) and ts) else stamp
    rows = sorted(by_day.values(), key=lambda r: (r["release_time_utc"], r["release_key"]))
    if orphans:
        stats["unparseable rows kept"] = len(orphans)
    return rows + orphans, stats


def surprises_changed(rows: list, existing_raw: list) -> bool:
    old = sorted(((r.get("timestamp") or "",) + _sig(_surprise_row_from_csv(r))) for r in existing_raw)
    new = sorted(((r.get("timestamp") or "",) + _sig(r)) for r in rows)
    return old != new


# ── Writing ──────────────────────────────────────────────────────────────────

def _ehd():
    import extract_historical_data as ehd  # lazy: the collectors' lock/atomic helpers and contracts
    return ehd


@contextmanager
def output_dir(ehd, data_dir):
    """Point extract_historical_data's OUTPUT_DIR at data_dir for the duration (CLI --data-dir)."""
    old = ehd.OUTPUT_DIR
    ehd.OUTPUT_DIR = data_dir
    try:
        yield
    finally:
        ehd.OUTPUT_DIR = old


def _frame(rows: list, columns: list):
    import pandas as pd
    return pd.DataFrame([{c: r.get(c) for c in columns} for r in rows], columns=columns)


def write_snapshots(rows: list, data_dir: str) -> int:
    """append_to_csv under the collectors' lock; the key's last row wins. Returns rows offered."""
    if not rows:
        return 0
    import pandas as pd
    ehd = _ehd()
    df = _frame(rows, CONSENSUS_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True).dt.tz_localize(None)
    df = df.sort_values(CONSENSUS_SORT, kind="stable")
    with output_dir(ehd, data_dir):
        ehd.append_to_csv(CONSENSUS_FILE, df, subset=CONSENSUS_KEY, sort_by=CONSENSUS_SORT)
    return len(df)


def merge_snapshot_rows(existing_raw: list, new_rows: list):
    """(rows, changed) - union keyed on CONSENSUS_KEY; per key the LATEST timestamp wins (ties: new).

    Used by the back-fill, whose rows are dated before any live snapshot of the same day.
    """
    def norm(r):
        out = {c: r.get(c) for c in CONSENSUS_COLUMNS}
        ts = r.get("timestamp")
        out["timestamp"] = fmt_ts(ts) if isinstance(ts, datetime) else (fmt_ts(parse_utc(ts)) if parse_utc(ts) else ts)
        for c in ("consensus", "previous"):
            v = out.get(c)
            out[c] = "" if v is None or v == "" else (repr(float(v)) if not isinstance(v, str) else v)
        return out
    merged = {}
    for r in list(existing_raw) + list(new_rows):          # new rows last: they win timestamp ties
        n = norm(r)
        k = tuple(str(n.get(c) or "") for c in CONSENSUS_KEY)
        if k not in merged or n["timestamp"] >= merged[k]["timestamp"]:
            merged[k] = n
    rows = sorted(merged.values(), key=lambda r: tuple(str(r.get(c) or "") for c in CONSENSUS_SORT))
    old = sorted(tuple(str(norm(r).get(c) or "") for c in CONSENSUS_COLUMNS) for r in existing_raw)
    new = sorted(tuple(str(r.get(c) or "") for c in CONSENSUS_COLUMNS) for r in rows)
    return rows, old != new


def write_table(path: str, rows: list, columns: list) -> None:
    """Atomic rewrite (caller holds _csv_lock for `path`)."""
    _ehd()._atomic_to_csv(_frame(rows, columns), path)


# ── Entry points (full extraction + CLI) ─────────────────────────────────────

def run_snapshot(data_dir=None, now=None, use_ff=True, use_kalshi=True, dry_run=False, kalshi=None, session=None) -> dict:
    """Snapshot ForexFactory + Kalshi into macro_consensus.csv. status: ok | partial | failed."""
    now = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    data_dir = data_dir or _ehd().OUTPUT_DIR
    rows, failures, ok_sources, notes = [], [], 0, []
    if use_ff:
        try:
            events = fetch_ff_calendar(session=session)
            r, info = ff_snapshot_rows(events, now)
            rows += r
            ok_sources += 1
            notes.append(f"ForexFactory: {len(events)} events, {len(r)} mapped upcoming USD release(s)"
                         + (f", {info['past']} already released" if info["past"] else ""))
            if info["unmapped"]:
                notes.append(f"ForexFactory: {len(info['unmapped'])} unmapped USD title(s) skipped: "
                             + "; ".join(info["unmapped"]))
        except SourceError as e:
            failures.append(str(e))
    if use_kalshi:
        client = kalshi or KalshiClient(timeout=(6, 20), retries=1, budget_s=LIVE_BUDGET_S)
        r, info = kalshi_snapshot_rows(client, now)
        rows += r
        failures += info["failed"]
        if info["attempted"] > len(info["failed"]):
            ok_sources += 1
        notes.append(f"Kalshi: {len(r)} ladder(s) from {info['attempted']} series, {client.requests} request(s)"
                     + (f"; no upcoming event: {', '.join(info['no_event'])}" if info["no_event"] else "")
                     + (f"; unusable: {'; '.join(info['unusable'])}" if info["unusable"] else ""))
    for n in notes:
        print(f"  {n}")
    for f in failures:
        print(f"  ⚠️  {f}")
    written = 0
    if rows and not dry_run and ok_sources:
        written = write_snapshots(rows, data_dir)
    status = "failed" if not ok_sources else ("partial" if failures else "ok")
    return {"status": status, "rows": len(rows), "written": written, "failures": failures,
            "asof": now.date().isoformat()}


def run_surprises(data_dir=None, since=None, now=None, dry_run=False, fred=None) -> dict:
    """Refresh macro_surprises.csv from macro_consensus.csv + FRED. status: ok | partial | failed."""
    now = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    ehd = _ehd()
    data_dir = data_dir or ehd.OUTPUT_DIR
    cpath, spath = os.path.join(data_dir, CONSENSUS_FILE), os.path.join(data_dir, SURPRISES_FILE)
    snaps = parse_snapshots(read_rows(cpath))
    if not snaps:
        print(f"  no snapshots in {cpath} yet - nothing to do")
        return {"status": "ok", "rows": 0, "written": False, "failures": []}
    # Network first, outside the lock; the lock only covers re-read + rebuild + write.
    todo = pending_releases(snaps, read_rows(spath), now, since)
    actuals, failures = {}, []
    if todo:
        fred = fred or FredClient(timeout=(8, 30), retries=1, budget_s=LIVE_BUDGET_S)
        for key, days in sorted(todo.items()):
            try:
                for day, res in resolve_actuals(fred, key, days).items():
                    actuals[(key, day)] = res
            except SourceError as e:
                failures.append(f"{key}: {e}")
    with ehd._csv_lock(spath):
        existing = read_rows(spath)
        rows, stats = build_surprises(snaps, existing, now, since, actuals)
        changed = surprises_changed(rows, existing)
        if changed and not dry_run:
            write_table(spath, rows, SURPRISES_COLUMNS)
    unresolvable = [f"{k} {d}: {v['error']}" for (k, d), v in actuals.items() if v and v.get("error")]
    print(f"  surprises: {len(rows)} release row(s); " + ", ".join(f"{k} {v}" for k, v in sorted(stats.items()))
          + (f"; FRED requests {fred.requests}" if todo else "") + ("" if changed else "; unchanged"))
    for u in unresolvable:
        print(f"  ⚠️  not computable: {u}")
    for f in failures:
        print(f"  ⚠️  {f}")
    status = "failed" if failures and len(failures) == len(todo) else ("partial" if failures else "ok")
    return {"status": status, "rows": len(rows), "written": changed and not dry_run, "failures": failures,
            "stats": dict(stats)}


def run_verify(since: date, fred=None) -> int:
    """Primary actual vs the headline recomputed from levels, for every first release since `since`."""
    fred = fred or FredClient()
    bad = 0
    for spec in RELEASES.values():
        a = spec.actual
        if not a.check:
            continue
        csid, ctr, clabel = a.check
        rt_start = since - timedelta(days=400)
        prim = fred.vintages(a.series, rt_start - timedelta(days=100), rt_start)
        chk = fred.vintages(csid, rt_start - timedelta(days=100), rt_start)
        n, mism = 0, []
        for obs, v0 in sorted(first_releases(prim).items()):
            if v0 < since.isoformat():
                continue
            p, _ = apply_transform(a.transform, prim, obs, v0, a.decimals)
            c, _ = apply_transform(ctr, chk, obs, v0, a.decimals)
            if p is None or c is None:
                continue
            n += 1
            if abs(p - c) > 1e-9:
                mism.append(f"{obs} (released {v0}): {a.series} {p} vs {clabel} {c}")
        bad += len(mism)
        print(f"  {spec.key:18s} {a.series} vs {clabel}: {n - len(mism)}/{n} equal")
        for m in mism:
            print(f"      MISMATCH {m}")
    return 1 if bad else 0


def _declare(data_dir: str, which: str) -> None:
    ehd = _ehd()
    fname, contract = ((CONSENSUS_FILE, CONSENSUS_CONTRACT) if which == "consensus"
                       else (SURPRISES_FILE, SURPRISES_CONTRACT))
    if os.path.exists(os.path.join(data_dir, fname)):
        with output_dir(ehd, data_dir):
            ehd.declare_columns(fname, **contract)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("snapshot", help="ForexFactory + Kalshi -> macro_consensus.csv")
    sp.add_argument("--no-ff", action="store_true")
    sp.add_argument("--no-kalshi", action="store_true")
    su = sub.add_parser("surprises", help="macro_consensus.csv + FRED first releases -> macro_surprises.csv")
    su.add_argument("--since", type=date.fromisoformat, help="only (re)compute releases on/after this day")
    for p in (sp, su):
        p.add_argument("--data-dir", default=os.path.join(REPO_ROOT, "historical_data"))
        p.add_argument("--dry-run", action="store_true", help="fetch and report, write nothing")
    ve = sub.add_parser("verify", help="FRED-only: primary actual series vs the headline recomputed from levels")
    ve.add_argument("--since", type=date.fromisoformat, default=date(2021, 1, 1))
    a = ap.parse_args(argv)
    try:
        if a.cmd == "verify":
            return run_verify(a.since)
        data_dir = os.path.abspath(a.data_dir)
        if not os.path.isdir(data_dir):
            print(f"  data dir {data_dir} does not exist")
            return 2
        if a.cmd == "snapshot":
            res = run_snapshot(data_dir, use_ff=not a.no_ff, use_kalshi=not a.no_kalshi, dry_run=a.dry_run)
            if res["status"] != "failed" and not a.dry_run:
                _declare(data_dir, "consensus")
        else:
            res = run_surprises(data_dir, since=a.since, dry_run=a.dry_run)
            if res["status"] != "failed" and not a.dry_run:
                _declare(data_dir, "surprises")
    except SourceError as e:
        print(f"  ❌ {e}")
        return 2
    except Exception as e:  # an I/O or programming error: report it and fail the run
        print(f"  ❌ {type(e).__name__}: {e}")
        return 2
    print(f"  {a.cmd}: {res['status']}")
    return {"ok": 0, "partial": 1}.get(res["status"], 2)


if __name__ == "__main__":
    sys.exit(main())
