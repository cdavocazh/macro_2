#!/usr/bin/env python3
"""One-off: repair the history of hl_perps.csv and hl_spot_stocks.csv (2026-09-21 audit).

Dry run by default. --apply writes; --rollback undoes the first --apply. Each repair can be
switched off (--skip 2,5) or run alone (--only 3). The repairs, IN THE ORDER THEY RUN:

  3  TIMEZONE (both files). Rows up to 2026-03-24 (hl_perps) / 2026-03-27 (hl_spot_stocks)
     were written on the Mac, whose hl_extract.py stamps naive LOCAL time (GMT+8); the VPS
     rows from 2026-06-03 / 2026-08-22 are naive UTC. hl_perps: each run of rows without a
     gap > 6 h gets its UTC offset from the file's own hl_btc_price against Hyperliquid's BTC
     1h candles (the method of backfill_hl_perps_20260921.py, reused from it), confirmed on
     every row, not only the 600-row sample. hl_spot_stocks has no BTC column: a spot row
     takes the offset of the hl_perps row the same hl_extract run wrote (timestamp within
     5 s), and the rows between such rows inherit it as long as ONE writer produced them (no
     > 6 h gap, no interleaved second writer). From 2026-03-27 07:17:54 (naive) the Mac-copied
     spot file interleaves two or more writers (steps < 45 s, two families of 24h volumes)
     that no perps row pins down; those rows are left as they are and listed as unresolved.
     Converted rows get timestamp - offset and the date of the new timestamp; the file stays
     in timestamp order. .hl_perps.provenance.json spans get the same shift (utc_offset_h 0,
     the old bounds kept under tz_normalised), and the backfill's reader recipe is applied
     before and after: it must select exactly the same cells, or nothing is written.
     Runs first because every later repair is a threshold on UTC time; with it skipped they
     compare timestamp - detected offset instead, and a row whose offset is unknown only
     counts as before/after a threshold when every offset in -12..+14 h agrees.
  1  FROZEN BUILDER QUOTES (hl_perps). From 2026-08-30 15:33:03 UTC (8a50610 moved oil,
     S&P 500, gas and copper to flx listings dead since June) until the first cb00e56 row
     (2026-09-21 15:01:17 UTC), hl_{oil,sp500,natgas,copper_hl}_{price,funding,oi,volume_24h}
     held the dead listings' last trade (76.4, 7435.0, 3.2429, 6.33) with OI 0 and volume 0.
     Blanks those fields (and premium, blank there anyway) in rows of that window where the
     coin's oi == 0 and volume_24h == 0: the extractor's own illiquid test. The dry run
     cross-checks the criterion against the frozen constants both ways.
  4  FAKE ZEROS (hl_perps). A row where every coin with a funding/OI value has funding == 0
     AND OI == 0 is a failed context fetch (2026-09-19 08:36:01 UTC): its funding, OI,
     volume_24h and premium zeros are blanked. The whole file is scanned. Cells repairs 1 and
     6 own (the frozen coins in their window, builder perps before the unit break) are left
     to them, so 1/4/6 give the same result in any order or combination of runs.
  6  CONTEXT-LESS BUILDER FIELDS (hl_perps; added in review, switch off with --skip 6).
     Before 8a50610 the extractor looked builder perps up in the contexts by their
     UNQUALIFIED name, which never matches, so funding, OI and premium were the '0' defaults
     (all 1,152 pre-break funding/OI cells and 154 premium cells of oil/sp500/natgas/
     copper_hl/brentoil/xyz100 are exactly 0, against <0.5% zeros for the main coins) and volume_24h
     was the 1d candle's UTC-day-to-date volume in base units, not the rolling 24h notional
     the column holds (brentoil 228,286 -> 240,994 within 35 minutes on 2026-03-22; the day
     closed at 1.87M). Blanks funding, OI, premium and volume_24h of those coins before the
     break; the price (a candle close, i.e. a real last trade) stays. Refuses a coin whose
     pre-break funding/OI are not all 0.
  2  UNIT BREAK (hl_perps). Before 2026-08-30 15:33:03 UTC the extractor annualised funding
     x3x365 (Binance's 8-hourly convention) instead of x24x365, and wrote openInterest in
     COINS; later rows are x24x365 and USD. The dry run proves it before converting:
     fundingHistory (settled hourly rate) vs the stored values of BTC and ETH in every
     pre-break segment must show stored / (rate x24x365x100) at ~1/8 and more exact x3 matches
     than x24 ones, and across the break OI_after(USD) / (OI_before(coins) x price) must be
     1 +- 1% for BTC/ETH/SOL/PAXG/HYPE. Then funding x8 (rounded to 2 dp, as the collector
     does) and OI x the same row's price (the collector's own mid; never a back-filled price
     from .hl_perps.provenance.json). An OI cell without a usable price is blanked (a coin
     count in a USD column would be wrong) and listed. Whether a segment is still in the old
     units is read from the data (BTC OI below 1e6 = coins; the funding baseline
     0.00125%/h shows as 1.37 before and 10.95 / 10.96 after), so a second run converts
     nothing. PRECISION: the old values were rounded at the x3 scale, so a converted funding
     cell is exact only to +-0.04 (the interest-rate baseline reads 10.96, not 10.95).
  5  WRONG-MARKET SPOT HISTORY (hl_spot_stocks). Until 0697893 (first row 2026-09-20
     16:34:17.263848 UTC, the same instant hl_xrp_funding first appears in hl_perps.csv)
     every ticker read the context of whatever market sat at its list position. Every value
     before that row is blanked; the columns stay. No column is kept: against each ticker's
     OWN pair's hourly candles, 0 of the Mac-era values and at most 0.5% of the later ones
     (single-trade or fat-finger candles) fall in range; the columns track other markets.

Backups: before the first write each rewritten file (both CSVs, the provenance sidecar) is
copied to .deploy_backup_20260921/data/ next to the data directory, under its own name, or
with a .repair-<UTC time> suffix (then -2, -3, ...) when that name is taken (it is for
hl_perps.csv: the backfill's pre-backfill original). A backup never replaces any file: it is
copied under a temp name and published with os.link, so a kill mid-copy leaves no partial
file under a backup's name. Record: every run that writes appends to
historical_data/.<stem>.repairs.json (dot-files, skipped by the loaders and the feed
scanner): per repair and column, the cells changed as maximal row spans [from, to] of the
file's timestamps after the run (every row in a span changed), counts, the values blanked,
the timezone segments and the evidence. Writing is done under extract_historical_data.
_csv_lock of each CSV (the collector's lock: hl_extract.py waits), in one window: record
first (state "writing", with every backup path and the md5 the sidecar is about to get),
then the CSVs via _atomic_to_csv, then the sidecar, then the record again (state
"complete"). SIGHUP / SIGINT / SIGTERM arriving in that window (a dropped ssh session,
Ctrl-C) are held until it closes. A SIGKILL, OOM or power loss inside it leaves "writing":
the next --apply (and a dry run) says so and refuses until --rollback has run.

--rollback restores, for each file, the backup made by the first --apply since the last
rollback that rewrote it (never the backfill's), under the same locks, and re-appends the rows
the collector wrote since, so no new data is lost; with none, the files are byte-identical to
the backups. It undoes an --apply interrupted mid-write the same way, and a --rollback that is
itself interrupted can simply be run again. Before writing anything it checks that the
provenance sidecar is in a state this script left: the output of the last --apply that
rewrote it (for an interrupted one: its input or its recorded planned output) or already the
backup. Anything else means something else rewrote the sidecar since, and it refuses.

API: the timezone detection reads BTC 1h candles and repair 2's proof reads fundingHistory
(api.hyperliquid.xyz, public, read-only), both outside the locks. Hyperliquid keeps ~5000
1h candles (~208 days): the 2026-03-19 rows stop being checkable around 2026-10-13.

  python scripts/repair_hl_20260921.py                         # dry run, all repairs
  python scripts/repair_hl_20260921.py --apply
  python scripts/repair_hl_20260921.py --skip 6 --apply
  python scripts/repair_hl_20260921.py --rollback
  python scripts/repair_hl_20260921.py --data-dir /copy/historical_data --apply
"""
from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import shutil
import signal
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
for _p in (ROOT, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
_cwd = os.getcwd()
import backfill_hl_perps_20260921 as bf  # noqa: E402  (the proven offset fit; it chdirs to ROOT)
os.chdir(_cwd)
from extract_historical_data import OUTPUT_DIR, _atomic_to_csv, _csv_lock  # noqa: E402

PERPS, SPOT = "hl_perps.csv", "hl_spot_stocks.csv"
PROVENANCE = bf.PROVENANCE                         # .hl_perps.provenance.json
BACKUP_TAG = bf.BACKUP_TAG                         # .deploy_backup_20260921
SCRIPT = "scripts/repair_hl_20260921.py"
HL_API_URL = "https://api.hyperliquid.xyz/info"

UNIT_BREAK = pd.Timestamp("2026-08-30 15:33:03.135890")   # first row written by 8a50610 (UTC)
NEW_CODE = pd.Timestamp("2026-09-21 15:01:17.937393")     # first row written by cb00e56 (UTC)
SPOT_FIX = pd.Timestamp("2026-09-20 16:34:17.263848")     # first row written by 0697893 (UTC)
FROZEN = {"oil": 76.4, "sp500": 7435.0, "natgas": 3.2429, "copper_hl": 6.33}
FROZEN_FIELDS = ("price", "funding", "oi", "volume_24h", "premium")
PRE_BREAK_BUILDERS = ("oil", "sp500", "natgas", "copper_hl", "brentoil", "xyz100")
CONTEXT_FIELDS = ("funding", "oi", "volume_24h", "premium")
MAIN_COINS = ("btc", "eth", "sol", "paxg", "hype")

ORDER = (3, 1, 4, 6, 2, 5)
NAMES = {3: "timezone", 1: "frozen_builder_quotes", 4: "fake_zero_context", 6: "contextless_builder_fields",
         2: "unit_break", 5: "spot_wrong_market"}
PARTNER_TOL_S = 5.0          # a spot row and the perps row of the same hl_extract run
SHORT_STEP_S = 45.0          # one writer never runs twice within 45 s (Mac: ~66 s, VPS: ~5 min)
INTERLEAVE_MIN, INTERLEAVE_WIN = 3, 10
OFF_LO, OFF_HI = -12, 14     # every UTC offset a naive local time can carry
FIT_MIN = bf.FIT_MIN
FUNDING_BASELINE_X3 = "1.37"               # 0.00125%/h x3x365x100 = 1.36875, rounded
FUNDING_BASELINE_X24 = ("10.95", "10.96")  # the same rate x24x365, and 1.37 x 8


class Refuse(SystemExit):
    """Stop without writing anything."""


# ── small helpers ────────────────────────────────────────────────────────────

def _read(path: str) -> pd.DataFrame:
    # Everything as text: untouched values go back byte-for-byte.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _ts(d: pd.DataFrame) -> pd.Series:
    return pd.to_datetime(d["timestamp"], format="ISO8601")


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.where(s.str.strip() != ""), errors="coerce")


def _fmt_ts(new: pd.Timestamp, like: str) -> str:
    """new in the layout of the string it replaces (separator, fractional seconds or not)."""
    sep = like[10] if len(like) > 10 else " "
    return new.strftime(f"%Y-%m-%d{sep}%H:%M:%S" + (".%f" if "." in like else ""))


def _fmt_num(x: float) -> str:
    return repr(float(round(x, 2)))


def _md5(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _json_bytes(obj) -> bytes:
    """The bytes the backfill's writer (bf._atomic_json) produces for obj: indent 1, ASCII, newline."""
    return (json.dumps(obj, indent=1) + "\n").encode("ascii")


def _atomic_json(obj, path: str) -> None:
    """Write exactly _json_bytes(obj) via a temp file + rename (mode 0644, as the backfill does)."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=f"{os.path.basename(path)}.", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(_json_bytes(obj))
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _atomic_copy(src: str, dst: str) -> None:
    """Byte copy of src over dst via a temp file + rename, keeping dst's mode."""
    d = os.path.dirname(dst) or "."
    mode = (os.stat(dst).st_mode & 0o7777) if os.path.exists(dst) else 0o644
    fd, tmp = tempfile.mkstemp(prefix=f".{os.path.basename(dst)}.", suffix=".tmp", dir=d)
    os.close(fd)
    try:
        shutil.copyfile(src, tmp)
        os.chmod(tmp, mode)
        os.replace(tmp, dst)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _spans(ts_str: pd.Series, mask: pd.Series) -> list:
    """[[from, to, cells]]: maximal runs of consecutive rows (file order) where mask holds."""
    out, start, prev, n = [], None, None, 0
    for t, m in zip(ts_str.tolist(), mask.tolist()):
        if m:
            if start is None:
                start, n = t, 0
            prev, n = t, n + 1
        elif start is not None:
            out.append([start, prev, n])
            start = None
    if start is not None:
        out.append([start, prev, n])
    return out


def _top_values(s: pd.Series, k: int = 5) -> dict:
    vc = s[s.str.strip() != ""].value_counts()
    return {str(v): int(c) for v, c in vc.head(k).items()}


def _cols(d: pd.DataFrame, coin: str, fields) -> list:
    return [f"hl_{coin}_{f}" for f in fields if f"hl_{coin}_{f}" in d.columns]


def _coins(d: pd.DataFrame) -> list:
    return [c[3:-6] for c in d.columns if c.startswith("hl_") and c.endswith("_price")]


# ── API reads (outside the locks) ────────────────────────────────────────────

def fetch_ref_candles(perps: pd.DataFrame | None) -> dict:
    """BTC 1h candles {open_ms: candle} covering hl_perps.csv (empty when there is no file)."""
    if perps is None or perps.empty:
        return {}
    ts = _ts(perps)
    start_ms = int((ts.min() - pd.Timedelta(days=1)).value // 1_000_000)
    end_ms = int(_utcnow().timestamp() * 1000)
    return bf.fetch_candles(bf.REF_COIN, start_ms, end_ms, ("1h",)).get("1h", {})


def _post(body: dict):
    for attempt in range(6):
        r = requests.post(HL_API_URL, json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Hyperliquid kept rate-limiting {body.get('type')}")


def fetch_funding_history(coin: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """{settlement hour (naive UTC): hourly rate} from fundingHistory, paged."""
    out, s = {}, start
    while s < end:
        rows = _post({"type": "fundingHistory", "coin": coin, "startTime": int(s.value // 1_000_000),
                      "endTime": int(end.value // 1_000_000)}) or []
        for x in rows:
            out[pd.Timestamp(int(x["time"]), unit="ms").floor("h")] = float(x["fundingRate"])
        if len(rows) < 500:
            break
        s = pd.Timestamp(int(rows[-1]["time"]), unit="ms") + pd.Timedelta(seconds=1)
        time.sleep(0.5)
    return out


# ── timezone detection ───────────────────────────────────────────────────────

def _interleave_start(t: np.ndarray, a: int, b: int) -> int:
    """First row of [a, b) from which a second writer interleaves (b if none)."""
    if b - a < 2:
        return b
    step = np.diff(t[a:b])
    short = step < SHORT_STEP_S
    for j in np.nonzero(short)[0]:
        if short[j:j + INTERLEAVE_WIN].sum() >= INTERLEAVE_MIN:
            return a + 1 + int(j)
    return b


def _full_fit(ts: pd.Series, px: pd.Series, ref: dict, off: int) -> tuple:
    hit = n = 0
    for t, p in zip(ts, px):
        if pd.isna(p) or pd.isna(t):
            continue
        u = int((t - pd.Timedelta(hours=off)).value // 1_000_000)
        c = ref.get((u // 3_600_000) * 3_600_000)
        if c is None:
            continue
        n += 1
        hit += float(c["l"]) * (1 - bf.FIT_TOL) <= p <= float(c["h"]) * (1 + bf.FIT_TOL)
    return (hit / n if n else 0.0), n


def perp_offsets(d: pd.DataFrame, ref: dict) -> tuple:
    """(offset per row as float Series, NaN = unresolved; segment report list)."""
    ts = _ts(d)
    px = _num(d[bf.REF_COL]) if bf.REF_COL in d.columns else pd.Series(np.nan, index=d.index)
    t = (ts.astype("int64") // 1_000_000_000).to_numpy(dtype=float)
    off = pd.Series(np.nan, index=d.index)
    report = []
    for a, b in bf.segments(ts):
        cut = _interleave_start(t, a, b)
        parts = [(a, cut, False)] + ([(cut, b, True)] if cut < b else [])
        for pa, pb, interleaved in parts:
            rec = {"from": d["timestamp"].iloc[pa], "to": d["timestamp"].iloc[pb - 1], "rows": pb - pa,
                   "utc_offset_h": None, "source": "btc_fit"}
            if interleaved:
                rec.update(source="unresolved: interleaved writers")
                report.append(rec)
                continue
            o, fit, second, n = bf.detect_offset(ts.iloc[pa:pb], px.iloc[pa:pb], ref)
            rec.update(fit=round(fit, 3), runner_up_fit=round(second, 3), checked=n)
            if o is not None:
                full, nfull = _full_fit(ts.iloc[pa:pb], px.iloc[pa:pb], ref, o)
                rec.update(full_fit=round(full, 4), full_rows=nfull)
                if full < FIT_MIN:
                    o = None
                    rec["source"] = "unresolved: full-row fit below threshold"
            else:
                rec["source"] = "unresolved: no clear BTC fit"
            rec["utc_offset_h"] = o
            if o is not None:
                off.iloc[pa:pb] = o
            report.append(rec)
    return off, report


def spot_offsets(s: pd.DataFrame, p: pd.DataFrame | None, p_off: pd.Series | None) -> tuple:
    """Offsets for hl_spot_stocks rows: same-run perps partner, then single-writer continuity."""
    ts = _ts(s)
    off = pd.Series(np.nan, index=s.index)
    how = pd.Series("unresolved", index=s.index, dtype=object)
    if p is not None and p_off is not None and len(p):
        order = np.argsort(_ts(p).to_numpy(), kind="stable")
        pts = _ts(p).to_numpy()[order]
        po = p_off.to_numpy(dtype=float)[order]
        sts = ts.to_numpy()
        j = np.searchsorted(pts, sts)
        best = np.full(len(sts), np.inf)
        bo = np.full(len(sts), np.nan)
        for k in (j - 1, j):
            ok = (k >= 0) & (k < len(pts))
            kk = np.where(ok, k, 0)
            dt = np.abs((sts - pts[kk]).astype("timedelta64[us]").astype(float) / 1e6)
            dt[~ok] = np.inf
            better = dt < best
            best[better], bo[better] = dt[better], po[kk][better]
        part = (best <= PARTNER_TOL_S) & ~np.isnan(bo)
        off[part] = bo[part]
        how[part] = "partner"
    t = (ts.astype("int64") // 1_000_000_000).to_numpy(dtype=float)
    report = []
    for a, b in bf.segments(ts):
        cut = _interleave_start(t, a, b)
        stretch = off.iloc[a:cut]
        known = set(stretch.dropna().unique())
        rec = {"from": s["timestamp"].iloc[a], "to": s["timestamp"].iloc[b - 1], "rows": b - a,
               "partnered": int((how.iloc[a:b] == "partner").sum())}
        if len(known) == 1:
            o = known.pop()
            fill = stretch.isna()
            idx = stretch.index[fill]
            off.loc[idx] = o
            how.loc[idx] = "continuity"
            rec.update(utc_offset_h=int(o), by_continuity=int(fill.sum()))
        else:
            rec.update(utc_offset_h=None if not known else sorted(int(k) for k in known))
        if cut < b:
            un = off.iloc[cut:b].isna()
            rec.update(interleaved_from=s["timestamp"].iloc[cut], unresolved=int(un.sum()))
        rec["unresolved_total"] = int(off.iloc[a:b].isna().sum())
        report.append(rec)
    return off, how, report


def side_of(naive: pd.Series, off: pd.Series, thr: pd.Timestamp) -> pd.Series:
    """True where the row's UTC time is before thr. Unknown offsets must agree over -12..+14 h."""
    utc = naive - pd.to_timedelta(off.fillna(0), unit="h")
    before = (utc < thr).to_numpy(dtype=bool)
    unk = off.isna().to_numpy(dtype=bool)
    if unk.any():
        lo = (naive - pd.Timedelta(hours=OFF_HI)).to_numpy()
        hi = (naive + pd.Timedelta(hours=-OFF_LO)).to_numpy()
        t = np.datetime64(thr)
        amb = unk & (lo < t) & (hi >= t)
        if amb.any():
            raise Refuse(f"refusing: {int(amb.sum())} row(s) of unknown timezone within 14 h of {thr} "
                         f"(first {naive[amb].iloc[0]})")
        before = np.where(unk, hi < t, before)
    return pd.Series(before, index=naive.index)


# ── the repairs ──────────────────────────────────────────────────────────────

def _changed(before: pd.DataFrame, after: pd.DataFrame, cols) -> dict:
    return {c: before[c] != after[c] for c in cols if c != "_rid" and (before[c] != after[c]).any()}


def _record_cols(before: pd.DataFrame, after: pd.DataFrame, cols, blanked: bool) -> dict:
    out = {}
    for c, m in _changed(before, after, cols).items():
        e = {"cells": int(m.sum()), "spans": _spans(after["timestamp"], m)}
        if blanked:
            e["values_blanked_top"] = _top_values(before.loc[m, c])
        else:
            e["example"] = [before.loc[m, c].iloc[0], after.loc[m, c].iloc[0]]
        out[c] = e
    return out


def repair_timezone(d: pd.DataFrame, off: pd.Series) -> tuple:
    """Shift rows with a non-zero offset to UTC. Returns (new frame, shifted mask, segments)."""
    shift = off.notna() & (off != 0)
    out = d.copy()
    if not shift.any():
        return out, shift, []
    ts = _ts(d)
    new_ts = ts - pd.to_timedelta(off.where(shift, 0), unit="h")
    out.loc[shift, "timestamp"] = [_fmt_ts(n, o) for n, o in zip(new_ts[shift], d.loc[shift, "timestamp"])]
    if "date" in out.columns:
        out.loc[shift, "date"] = new_ts[shift].dt.strftime("%Y-%m-%d")
    segs = []
    pos = np.flatnonzero(shift.to_numpy())
    for run in np.split(pos, np.flatnonzero(np.diff(pos) != 1) + 1):   # maximal runs of shifted rows
        rows = d.index[run]
        segs.append({"from_before": d.at[rows[0], "timestamp"], "to_before": d.at[rows[-1], "timestamp"],
                     "rows": int(len(rows)),
                     "from_after": out.at[rows[0], "timestamp"], "to_after": out.at[rows[-1], "timestamp"],
                     "utc_offset_h_before": [int(x) for x in off[rows].unique()]})
    nts = _ts(out)
    if nts.duplicated().any():
        raise Refuse(f"refusing: the timezone shift makes {int(nts.duplicated().sum())} timestamp(s) collide")
    if not nts.is_monotonic_increasing:
        out = out.iloc[np.argsort(nts.to_numpy(), kind="stable")]
    return out, shift, segs


def _recipe(d: pd.DataFrame, prov: dict) -> dict:
    """The backfill's reader recipe: {column: set of original row ids} it would blank."""
    ts = _ts(d)
    sel = {}
    for run in prov.get("runs", []):
        for sp in run.get("spans", []):
            c = sp["column"]
            if c not in d.columns:
                continue
            m = ts.between(pd.Timestamp(sp["from"]), pd.Timestamp(sp["to"])) & (d[c].str.strip() != "")
            sel.setdefault(c, set()).update(d.loc[m, "_rid"].tolist())
    return sel


def shift_provenance(prov: dict, before: pd.DataFrame, after: pd.DataFrame, off: pd.Series, at: str) -> tuple:
    """(new provenance, spans shifted). Every span's rows must share one offset."""
    new = json.loads(json.dumps(prov))
    ts_b = _ts(before)
    moved = 0
    ts_after_by_rid = dict(zip(after["_rid"], after["timestamp"]))
    for run in new.get("runs", []):
        for sp in run.get("spans", []):
            rows = before.index[ts_b.between(pd.Timestamp(sp["from"]), pd.Timestamp(sp["to"]))]
            if not len(rows):
                continue
            ks = set(off[rows].fillna(0).astype(int).unique())
            if len(ks) != 1:
                raise Refuse(f"refusing: provenance span {sp['column']} {sp['from']}..{sp['to']} covers rows "
                             f"of different UTC offsets {sorted(ks)}")
            k = ks.pop()
            if k == 0:
                continue
            f_rid = before.at[before.index[ts_b == pd.Timestamp(sp["from"])][0], "_rid"] \
                if (ts_b == pd.Timestamp(sp["from"])).any() else None
            t_rid = before.at[before.index[ts_b == pd.Timestamp(sp["to"])][0], "_rid"] \
                if (ts_b == pd.Timestamp(sp["to"])).any() else None
            old_from, old_to = sp["from"], sp["to"]
            sp["from"] = ts_after_by_rid[f_rid] if f_rid is not None else \
                _fmt_ts(pd.Timestamp(old_from) - pd.Timedelta(hours=k), old_from)
            sp["to"] = ts_after_by_rid[t_rid] if t_rid is not None else \
                _fmt_ts(pd.Timestamp(old_to) - pd.Timedelta(hours=k), old_to)
            sp["tz_normalised"] = {"from_before": old_from, "to_before": old_to, "utc_offset_h_before": int(k),
                                   "by": SCRIPT, "at": at}
            sp["utc_offset_h"] = 0
            moved += 1
    if moved:
        new["timestamps"] = (f"naive UTC. The rows written on the Mac in naive GMT+8 and the spans over them were "
                             f"shifted to UTC by {SCRIPT} at {at}; each such span keeps its old bounds under "
                             f"tz_normalised.")
    return new, moved


def repair_frozen(d: pd.DataFrame, in_window: pd.Series) -> tuple:
    out = d.copy()
    ev = {}
    for coin, const in FROZEN.items():
        oi, vol, px = f"hl_{coin}_oi", f"hl_{coin}_volume_24h", f"hl_{coin}_price"
        if oi not in d.columns or vol not in d.columns:
            continue
        crit = (_num(d[oi]) == 0) & (_num(d[vol]) == 0)
        frozen_val = _num(d[px]) == const if px in d.columns else pd.Series(False, index=d.index)
        caught = crit & in_window
        ev[coin] = {"window_rows": int(in_window.sum()), "caught": int(caught.sum()),
                    "frozen_valued": int((frozen_val & in_window).sum()),
                    "caught_not_frozen_valued": d.loc[caught & ~frozen_val, "timestamp"].tolist()[:20],
                    "frozen_valued_not_caught": d.loc[frozen_val & in_window & ~crit, "timestamp"].tolist()[:20],
                    "criterion_outside_window_untouched": d.loc[crit & ~in_window, "timestamp"].tolist()[:20],
                    "frozen_constant": const}
        for c in _cols(d, coin, FROZEN_FIELDS):
            out.loc[caught, c] = ""
    return out, ev


def _owned_by_1_or_6(d: pd.DataFrame, coin: str, in_window: pd.Series, pre_break: pd.Series) -> pd.Series:
    m = pd.Series(False, index=d.index)
    if coin in FROZEN:
        m |= in_window
    if coin in PRE_BREAK_BUILDERS:
        m |= pre_break
    return m


def repair_fake_zeros(d: pd.DataFrame, in_window: pd.Series, pre_break: pd.Series) -> tuple:
    out = d.copy()
    n = pd.Series(0, index=d.index)
    z = pd.Series(0, index=d.index)
    for coin in _coins(d):
        skip = _owned_by_1_or_6(d, coin, in_window, pre_break)
        for f in ("funding", "oi"):
            c = f"hl_{coin}_{f}"
            if c not in d.columns:
                continue
            v = _num(d[c]).where(~skip)
            n += v.notna()
            z += (v == 0)
    rows = (n >= 3) & (n == z)
    for coin in _coins(d):
        skip = _owned_by_1_or_6(d, coin, in_window, pre_break)
        for c in _cols(d, coin, CONTEXT_FIELDS):
            m = rows & ~skip & (_num(d[c]) == 0)
            out.loc[m, c] = ""
    return out, {"rows": d.loc[rows, "timestamp"].tolist(), "coin_fields_per_row": n[rows].tolist()}


def repair_contextless(d: pd.DataFrame, pre_break: pd.Series) -> tuple:
    out = d.copy()
    ev = {}
    for coin in PRE_BREAK_BUILDERS:
        cols = _cols(d, coin, CONTEXT_FIELDS)
        if not cols:
            continue
        fo = [_num(d[c])[pre_break].dropna() for c in _cols(d, coin, ("funding", "oi", "premium"))]
        vals = pd.concat(fo) if fo else pd.Series(dtype=float)
        nonzero = int((vals != 0).sum())
        cells = sum(int((pre_break & (d[c].str.strip() != "")).sum()) for c in cols)
        ev[coin] = {"pre_break_funding_oi_premium_cells": int(len(vals)), "nonzero": nonzero, "cells": cells}
        if nonzero:
            ev[coin]["skipped"] = "premise fails: a pre-break funding/OI/premium value is not 0"
            continue
        for c in cols:
            out.loc[pre_break, c] = ""
    return out, ev


def unit_state(d: pd.DataFrame, rows: pd.Series) -> tuple:
    """('x3', 'coins') / ('x24', 'usd') / something else for the pre-break rows given."""
    f = pd.concat([d.loc[rows, c] for c in (f"hl_{k}_funding" for k in MAIN_COINS) if c in d.columns])
    f = f[f.str.strip() != ""]
    n3 = int((f == FUNDING_BASELINE_X3).sum())
    n24 = int(f.isin(FUNDING_BASELINE_X24).sum())
    fs = "x3" if n3 > max(n24, 0.02 * len(f)) else "x24" if n24 > max(n3, 0.02 * len(f)) else "?"
    oi = _num(d.loc[rows, "hl_btc_oi"]).dropna() if "hl_btc_oi" in d.columns else pd.Series(dtype=float)
    med = float(oi.median()) if len(oi) else float("nan")
    os_ = "coins" if med < 1e6 else "usd" if med > 1e8 else "?"
    return fs, os_, {"funding_cells": int(len(f)), "baseline_x3": n3, "baseline_x24": n24,
                     "btc_oi_median": None if np.isnan(med) else round(med, 2)}


def unit_proof(d: pd.DataFrame, utc: pd.Series, seg_rows: list) -> dict:
    """Premise check of repair 2 (API). Raises Refuse when the evidence is not unambiguous."""
    proof = {"funding": [], "oi_break": {}}
    for rows in seg_rows:
        u = utc[rows]
        start = max(u.min(), u.max() - pd.Timedelta(days=4))       # the last <= 4 days of the segment
        for coin in ("btc", "eth"):
            col = f"hl_{coin}_funding"
            hist = fetch_funding_history(coin.upper(), start - pd.Timedelta(hours=2), u.max() + pd.Timedelta(hours=2))
            m = rows & (utc >= start)
            vals = _num(d.loc[m, col])
            pairs = [(v, hist.get(t.floor("h") + pd.Timedelta(hours=1))) for v, t in zip(vals, utc[m])]
            pairs = [(v, r) for v, r in pairs if not pd.isna(v) and r is not None]
            if len(pairs) < 20:
                raise Refuse(f"refusing repair 2: only {len(pairs)} {coin} funding rows matched fundingHistory "
                             f"in {start}..{u.max()}")
            a = np.array(pairs, dtype=float)
            nz = a[:, 1] != 0
            ratio = float(np.median(a[nz, 0] / (a[nz, 1] * 24 * 365 * 100)))
            eq3 = float((a[:, 0] == np.round(a[:, 1] * 3 * 365 * 100, 2)).mean())
            eq24 = float((a[:, 0] == np.round(a[:, 1] * 24 * 365 * 100, 2)).mean())
            rec = {"coin": coin, "from_utc": str(start), "to_utc": str(u.max()), "rows": len(pairs),
                   "median_stored_over_x24": round(ratio, 4), "exact_x3": round(eq3, 3), "exact_x24": round(eq24, 3)}
            proof["funding"].append(rec)
            if not (0.10 <= ratio <= 0.15 and eq3 > eq24):   # x3 predicts 0.125, x24 predicts 1
                raise Refuse(f"refusing repair 2: funding evidence is not x3x365 for {coin}: {rec}")
    after = d.index[utc >= UNIT_BREAK]
    before = d.index[utc < UNIT_BREAK]
    if len(after) and len(before):
        i, j = before[-1], after[0]
        for coin in MAIN_COINS:
            oi_b, px_b, oi_a = (_num(d[f"hl_{coin}_oi"])[i], _num(d[f"hl_{coin}_price"])[i],
                                _num(d[f"hl_{coin}_oi"])[j])
            r = float(oi_a / (oi_b * px_b)) if oi_b and px_b else float("nan")
            proof["oi_break"][coin] = {"last_before": d.at[i, "timestamp"], "first_after": d.at[j, "timestamp"],
                                       "usd_after_over_coins_x_price_before": round(r, 5)}
            if not abs(r - 1) <= 0.01:
                raise Refuse(f"refusing repair 2: OI across the break is not coins -> USD for {coin} (ratio {r})")
    return proof


def repair_units(d: pd.DataFrame, pre_break: pd.Series, segs: list, prov: dict, prove: bool,
                 utc: pd.Series) -> tuple:
    """segs: [(rows mask)] of pre-break TZ segments. Converts those still in the old units."""
    out = d.copy()
    ev = {"segments": [], "oi_not_convertible": {}}
    todo = pd.Series(False, index=d.index)
    for rows in segs:
        rows = rows & pre_break
        if not rows.any():
            continue
        fs, os_, st = unit_state(d, rows)
        st.update(from_=d.loc[rows, "timestamp"].iloc[0], to=d.loc[rows, "timestamp"].iloc[-1],
                  funding=fs, oi=os_, rows=int(rows.sum()))
        ev["segments"].append(st)
        if (fs, os_) == ("x3", "coins"):
            todo |= rows
        elif (fs, os_) != ("x24", "usd"):
            raise Refuse(f"refusing repair 2: segment {st['from_']}..{st['to']} is in mixed or unknown units: {st}")
    if not todo.any():
        return out, ev
    if prove:
        ev["proof"] = unit_proof(d, utc, [r & todo for r in segs if (r & todo).any()])
    ts = _ts(d)
    spans = bf._prior_spans(prov)
    for coin in _coins(d):
        fcol, ocol, pcol = f"hl_{coin}_funding", f"hl_{coin}_oi", f"hl_{coin}_price"
        if fcol in d.columns:
            m = todo & (d[fcol].str.strip() != "")
            out.loc[m, fcol] = [_fmt_num(float(x) * 8) for x in d.loc[m, fcol]]
        if ocol in d.columns:
            m = todo & (d[ocol].str.strip() != "")
            px = _num(d[pcol]) if pcol in d.columns else pd.Series(np.nan, index=d.index)
            backfilled = bf._covered(ts, spans, pcol)
            usable = px.notna() & (px > 0) & ~backfilled
            conv = m & usable
            out.loc[conv, ocol] = [_fmt_num(float(o) * p) for o, p in zip(d.loc[conv, ocol], px[conv])]
            bad = m & ~usable
            if bad.any():
                out.loc[bad, ocol] = ""
                ev["oi_not_convertible"][ocol] = {
                    "cells": int(bad.sum()), "blanked": dict(zip(d.loc[bad, "timestamp"], d.loc[bad, ocol])),
                    "why": {"price_blank": int((bad & px.isna()).sum()), "price_backfilled": int((bad & backfilled).sum())}}
    return out, ev


def repair_spot(s: pd.DataFrame, before_fix: pd.Series) -> tuple:
    out = s.copy()
    vcols = [c for c in s.columns if c not in ("timestamp", "date", "_rid")]
    for c in vcols:
        out.loc[before_fix, c] = ""
    return out, {"rows_before_fix": int(before_fix.sum())}


# ── plan ─────────────────────────────────────────────────────────────────────

def check_constants(p: pd.DataFrame, p_utc: pd.Series, s: pd.DataFrame | None) -> dict:
    """The hard-coded instants must match the data's own signatures; returns problems per repair."""
    bad = {}
    if not (p_utc == UNIT_BREAK).any():
        bad[2] = bad[1] = f"no hl_perps row at {UNIT_BREAK} (the first 8a50610 row)"
    oi = _num(p["hl_oil_oi"]) if "hl_oil_oi" in p.columns else pd.Series(np.nan, index=p.index)
    first_live = p_utc[(p_utc >= UNIT_BREAK) & (oi > 0)]
    if not len(first_live) or first_live.iloc[0] != NEW_CODE:
        bad[1] = f"first hl_oil_oi > 0 after the break is {first_live.iloc[0] if len(first_live) else None}, not {NEW_CODE}"
    if s is not None:
        xf = p["hl_xrp_funding"] if "hl_xrp_funding" in p.columns else pd.Series("", index=p.index)
        first_xrp = p_utc[(p_utc >= pd.Timestamp("2026-09-01")) & (xf.str.strip() != "")]
        if not len(first_xrp) or first_xrp.iloc[0] != SPOT_FIX:
            bad[5] = f"first hl_xrp_funding since 2026-09-01 is {first_xrp.iloc[0] if len(first_xrp) else None}, not {SPOT_FIX}"
    return bad


def plan(p: pd.DataFrame | None, s: pd.DataFrame | None, prov: dict | None, ref: dict, enabled: set,
         prove: bool = True, at: str | None = None) -> dict:
    """Run the enabled repairs in ORDER on copies. Pure except for repair 2's fundingHistory proof."""
    at = at or _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    res = {"perps": None, "spot": None, "prov": prov, "records": {PERPS: {}, SPOT: {}},
           "tz": {}, "skipped": {}}
    if p is not None:
        p = p.copy()
        p["_rid"] = np.arange(len(p))
    if s is not None:
        s = s.copy()
        s["_rid"] = np.arange(len(s))
    p_off, p_seg = (perp_offsets(p, ref) if p is not None else (None, []))
    s_off, s_how, s_seg = (spot_offsets(s, p, p_off) if s is not None else (None, None, []))
    res["tz"] = {PERPS: p_seg, SPOT: s_seg}
    if s is not None:
        un = s_off.isna()
        res["tz"]["spot_unresolved"] = {"rows": int(un.sum()), "spans": _spans(s["timestamp"], un)}
        res["tz"]["spot_resolution"] = {k: int(v) for k, v in s_how.value_counts().items()}
    bad = check_constants(p, _ts(p) - pd.to_timedelta(p_off.fillna(0), unit="h"), s) if p is not None else {}
    for k, why in bad.items():
        if k in enabled:
            res["skipped"][k] = why
    enabled = enabled - set(bad)

    # 3: timezone
    if 3 in enabled:
        if p is not None:
            p_before, off_before = p, p_off
            p, shifted, segs = repair_timezone(p, p_off)
            p_off = p_off.where(~shifted, 0).reindex(p.index)
            rec = {"segments_shifted": segs, "rows": int(shifted.sum()), "detection": p_seg}
            if prov is not None and shifted.any():
                before_sel = _recipe(p_before, prov)
                new_prov, moved = shift_provenance(prov, p_before, p, off_before.where(shifted, 0), at)
                after_sel = _recipe(p, new_prov)
                same = before_sel == after_sel
                rec["provenance"] = {"spans_shifted": moved,
                                     "recipe_cells_before": sum(map(len, before_sel.values())),
                                     "recipe_cells_after": sum(map(len, after_sel.values())),
                                     "identical_selection": same}
                if not same:
                    raise Refuse("refusing: the provenance recipe would select different cells after the shift")
                res["prov"] = new_prov
            res["records"][PERPS][NAMES[3]] = rec
        if s is not None:
            s, sshift, ssegs = repair_timezone(s, s_off)
            s_off = s_off.where(~sshift, 0).reindex(s.index)
            res["records"][SPOT][NAMES[3]] = {"segments_shifted": ssegs, "rows": int(sshift.sum()),
                                              "detection": s_seg, "unresolved": res["tz"].get("spot_unresolved")}

    if p is not None:
        p_ts = _ts(p)
        pre_break = side_of(p_ts, p_off, UNIT_BREAK)
        in_window = ~pre_break & side_of(p_ts, p_off, NEW_CODE)
        if 1 in enabled:
            new, ev = repair_frozen(p, in_window)
            res["records"][PERPS][NAMES[1]] = {"window_utc": [str(UNIT_BREAK), str(NEW_CODE)],
                                               "criterion": "coin oi == 0 and volume_24h == 0", "evidence": ev,
                                               "columns": _record_cols(p, new, p.columns, True)}
            p = new
        if 4 in enabled:
            new, ev = repair_fake_zeros(p, in_window, pre_break)
            res["records"][PERPS][NAMES[4]] = {"evidence": ev, "columns": _record_cols(p, new, p.columns, True)}
            p = new
        if 6 in enabled:
            new, ev = repair_contextless(p, pre_break)
            res["records"][PERPS][NAMES[6]] = {"before_utc": str(UNIT_BREAK), "evidence": ev,
                                               "columns": _record_cols(p, new, p.columns, True)}
            p = new
        if 2 in enabled:
            utc = p_ts - pd.to_timedelta(p_off.fillna(0), unit="h")
            seg_masks = []
            for sg in bf.segments(p_ts):
                m = pd.Series(False, index=p.index)
                m.iloc[sg[0]:sg[1]] = True
                seg_masks.append(m)
            new, ev = repair_units(p, pre_break, seg_masks, res["prov"] or {}, prove, utc)
            res["records"][PERPS][NAMES[2]] = {"break_utc": str(UNIT_BREAK), "funding_factor": 8,
                                               "oi": "coins x same-row price (collector mid; never a back-filled price)",
                                               "evidence": ev, "columns": _record_cols(p, new, p.columns, False)}
            p = new
    if s is not None and 5 in enabled:
        before_fix = side_of(_ts(s), s_off, SPOT_FIX)
        new, ev = repair_spot(s, before_fix)
        cols = _record_cols(s, new, s.columns, True)
        ev["values_blanked_per_column"] = {c: e["cells"] for c, e in cols.items()}
        res["records"][SPOT][NAMES[5]] = {"first_correct_row_utc": str(SPOT_FIX), "evidence": ev, "columns": cols}
        s = new
    res["perps"] = p.drop(columns="_rid") if p is not None else None
    res["spot"] = s.drop(columns="_rid") if s is not None else None
    return res



# ── report ───────────────────────────────────────────────────────────────────

def cells_changed(res: dict) -> dict:
    """{file: {repair: cells}} (timezone: rows shifted)."""
    out = {}
    for f, recs in res["records"].items():
        for name, r in recs.items():
            n = r.get("rows", 0) if name == NAMES[3] else sum(c["cells"] for c in r.get("columns", {}).values())
            out.setdefault(f, {})[name] = n
    return out


def print_report(res: dict) -> None:
    for f in (PERPS, SPOT):
        for sg in res["tz"].get(f, []):
            o = sg.get("utc_offset_h")
            tz = "UNRESOLVED" if o is None else (f"UTC{o:+d}" if isinstance(o, int) else f"mixed {o}")
            extra = ""
            if "fit" in sg:
                extra = (f" fit {sg['fit']} (runner-up {sg['runner_up_fit']}, {sg['checked']} sampled)"
                         + (f", every row {sg['full_fit']} of {sg['full_rows']}" if "full_fit" in sg else ""))
            if "partnered" in sg:
                extra = (f" {sg['partnered']} rows pinned by a same-run perps row, "
                         f"{sg.get('by_continuity', 0)} by one-writer continuity, {sg['unresolved_total']} unresolved"
                         + (f" (second writer interleaved from {sg['interleaved_from']})" if "interleaved_from" in sg else ""))
            print(f"  [tz] {f:20s} {sg['from'][:19]} -> {sg['to'][:19]} ({sg['rows']:>5} rows): {tz}{extra}"
                  + (f" [{sg['source']}]" if str(sg.get("source", "")).startswith("unresolved") else ""))
    for k, why in res["skipped"].items():
        print(f"  repair {k} ({NAMES[k]}) SKIPPED: {why}")
    for f, recs in res["records"].items():
        for name, r in recs.items():
            if name == NAMES[3]:
                print(f"  {f}: {name}: {r['rows']} row(s) to shift"
                      + "".join(f"\n      {sg['from_before'][:19]}..{sg['to_before'][:19]} ({sg['rows']} rows, "
                                f"UTC{sg['utc_offset_h_before'][0]:+d}) -> {sg['from_after'][:19]}..{sg['to_after'][:19]}"
                                for sg in r["segments_shifted"]))
                if "provenance" in r:
                    pv = r["provenance"]
                    print(f"      provenance: {pv['spans_shifted']} span(s) shifted; recipe selects "
                          f"{pv['recipe_cells_before']} cells before, {pv['recipe_cells_after']} after, identical: "
                          f"{pv['identical_selection']}")
                if r.get("unresolved"):
                    print(f"      left as they are (timezone unresolved): {r['unresolved']['rows']} row(s) "
                          + ", ".join(f"{a[:19]}..{b[:19]} ({n})" for a, b, n in r["unresolved"]["spans"]))
                continue
            cols = r.get("columns", {})
            n = sum(c["cells"] for c in cols.values())
            print(f"  {f}: {name}: {n} cell(s) in {len(cols)} column(s)")
            ev = r.get("evidence", {})
            if name == NAMES[1]:
                for coin, e in ev.items():
                    print(f"      {coin:9s} window rows {e['window_rows']}, caught {e['caught']}, frozen-valued "
                          f"({e['frozen_constant']}) {e['frozen_valued']}; caught but not frozen-valued: "
                          f"{len(e['caught_not_frozen_valued'])}; frozen-valued but not caught: "
                          f"{len(e['frozen_valued_not_caught'])}; criterion true OUTSIDE the window (untouched): "
                          f"{e['criterion_outside_window_untouched']}")
            elif name == NAMES[4]:
                print(f"      rows with every funding & OI exactly 0: {ev['rows']} "
                      f"(coin-fields per row {ev['coin_fields_per_row']})")
            elif name == NAMES[6]:
                for coin, e in ev.items():
                    print(f"      {coin:9s} pre-break funding/OI/premium cells {e['pre_break_funding_oi_premium_cells']}, "
                          f"non-zero {e['nonzero']}, cells to blank {e['cells']}" + (f" SKIPPED ({e['skipped']})" if 'skipped' in e else ""))
            elif name == NAMES[2]:
                for sg in ev.get("segments", []):
                    print(f"      segment {sg['from_'][:19]}..{sg['to'][:19]} ({sg['rows']} rows): funding {sg['funding']} "
                          f"(baseline 1.37: {sg['baseline_x3']}, 10.95/10.96: {sg['baseline_x24']} of "
                          f"{sg['funding_cells']}), OI {sg['oi']} (BTC median {sg['btc_oi_median']})")
                pr = ev.get("proof")
                if pr:
                    for x in pr["funding"]:
                        print(f"      fundingHistory {x['coin']} {x['from_utc'][:16]}..{x['to_utc'][:16]}: n={x['rows']}, "
                              f"median stored/(rate x24x365x100) = {x['median_stored_over_x24']}, exact x3 "
                              f"{x['exact_x3']} vs x24 {x['exact_x24']}")
                    for coin, x in pr["oi_break"].items():
                        print(f"      OI across the break {coin}: USD after / (coins x price before) = "
                              f"{x['usd_after_over_coins_x_price_before']}")
                for c, x in ev.get("oi_not_convertible", {}).items():
                    print(f"      {c}: {x['cells']} OI cell(s) without a usable price, blanked {x['why']}")
            elif name == NAMES[5]:
                print(f"      rows before the first 0697893 row: {ev['rows_before_fix']}; values blanked per column: "
                      f"{ev['values_blanked_per_column']}")


# ── files, backups, record ───────────────────────────────────────────────────

def _paths(data_dir: str) -> dict:
    return {"data": data_dir, PERPS: os.path.join(data_dir, PERPS), SPOT: os.path.join(data_dir, SPOT),
            "prov": os.path.join(data_dir, PROVENANCE),
            "backup": os.path.join(os.path.dirname(data_dir), BACKUP_TAG, "data")}


def record_path(data_dir: str, csv_name: str) -> str:
    return os.path.join(data_dir, f".{os.path.splitext(csv_name)[0]}.repairs.json")


def _load_record(path: str, csv_name: str) -> dict:
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {"file": csv_name, "written_by": SCRIPT,
            "meaning": ("One entry per run that changed the file. repairs.<name>.columns.<column>.spans = "
                        "[[from, to, cells]]: every row whose timestamp lies in [from, to] (the file's own "
                        "naive-UTC timestamps right after that run) had that cell changed by that repair; "
                        "blanked values are summarised in values_blanked_top and kept in full in the backup. "
                        "timezone.segments_shifted maps each shifted block of rows from its old to its new "
                        "timestamps. A rollback entry marks the files restored from that apply's backups."),
            "runs": []}


def _backup_names(backup_dir: str, name: str, stamp: str):
    """name, then name.repair-<UTC stamp>, then name.repair-<stamp>-2, -3, ..."""
    yield os.path.join(backup_dir, name)
    yield os.path.join(backup_dir, f"{name}.repair-{stamp}")
    for i in itertools.count(2):
        yield os.path.join(backup_dir, f"{name}.repair-{stamp}-{i}")


def _backup_copy(src: str, backup_dir: str, name: str, stamp: str) -> str:
    """Copy src into backup_dir under the first free name of _backup_names; returns the path.

    Never replaces a file (the backfill's pre-backfill hl_perps.csv, an earlier apply's backup):
    the copy is made under a temp name and published with os.link, which fails rather than
    overwrite, so a kill mid-copy leaves no partial file under a backup's name either.
    """
    fd, tmp = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=backup_dir)
    os.close(fd)
    try:
        shutil.copy2(src, tmp)
        for dst in _backup_names(backup_dir, name, stamp):
            try:
                os.link(tmp, dst)
                return dst
            except FileExistsError:
                continue
            except OSError:                 # no hard links on this filesystem: exclusive create
                try:
                    with open(tmp, "rb") as i, open(dst, "xb") as o:
                        shutil.copyfileobj(i, o)
                except FileExistsError:
                    continue
                shutil.copystat(tmp, dst)
                return dst
    finally:
        os.unlink(tmp)
    raise AssertionError("unreachable")


class _DeferSignals:
    """Hold SIGHUP, SIGINT and SIGTERM (a dropped ssh session, Ctrl-C, a service stop) while the
    files and the record are being written, and act on them once the window has closed, so a
    signal never leaves the files and the record out of step. A Python-level handler, not a
    thread signal mask, so it holds whichever thread the kernel delivers to. SIGKILL, OOM and
    power loss cannot be held: --rollback recovers from those (see do_rollback).
    """

    NAMES = ("SIGHUP", "SIGINT", "SIGTERM")

    def __enter__(self):
        self.got, self.old = [], {}
        if threading.current_thread() is threading.main_thread():
            for name in self.NAMES:
                sig = getattr(signal, name, None)
                if sig is not None:
                    self.old[sig] = signal.signal(sig, lambda n, _frame: self.got.append(n))
        return self

    def __exit__(self, *exc) -> bool:
        for sig, handler in self.old.items():
            signal.signal(sig, signal.SIG_DFL if handler is None else handler)
        for n in dict.fromkeys(self.got):
            try:
                print(f"  {signal.Signals(n).name} arrived while writing; acting on it now that the write is "
                      "complete", file=sys.stderr, flush=True)
            except (OSError, ValueError):
                pass
            signal.raise_signal(n)
        return False


def _since_rollback(rec: dict) -> list:
    """The apply runs recorded after the last rollback, oldest first."""
    runs = rec.get("runs", [])
    last_rb = max((i for i, r in enumerate(runs) if r.get("kind") == "rollback"), default=-1)
    return [r for r in runs[last_rb + 1:] if r.get("kind") == "apply"]


def _first_with(rec: dict, key: str) -> dict | None:
    """The first apply since the last rollback that made a backup under `key`."""
    return next((r for r in _since_rollback(rec) if r.get(key)), None)


def _last_with(rec: dict, key: str) -> dict | None:
    """The last apply since the last rollback that made a backup under `key`."""
    return next((r for r in reversed(_since_rollback(rec)) if r.get(key)), None)


def _stuck(rec: dict) -> bool:
    """True when the record's last run is an --apply that never reached state "complete"."""
    runs = rec.get("runs", [])
    return bool(runs) and runs[-1].get("kind") == "apply" and runs[-1].get("state") != "complete"


def _interrupted(pa: dict) -> list:
    """Record files whose last run is an --apply interrupted mid-write."""
    return [record_path(pa["data"], f) for f in (PERPS, SPOT)
            if os.path.exists(record_path(pa["data"], f)) and _stuck(_load_record(record_path(pa["data"], f), f))]


def _prov_guard(pa: dict, rec: dict, root: str) -> str | None:
    """Why restoring the provenance sidecar from its backup would be unsafe, or None.

    Safe when the sidecar is what the last --apply that rewrote it left behind (its output; if
    that apply was interrupted mid-write: its input, or the output it had planned and recorded
    before writing) or is already the backup (a rollback interrupted after restoring it).
    Anything else means something else rewrote it since (another backfill run?).
    """
    first, last = _first_with(rec, "provenance_backup"), _last_with(rec, "provenance_backup")
    ok = {_md5(os.path.join(root, first["provenance_backup"]))}
    if last.get("state") == "complete":
        ok.add(last.get("provenance_output_md5"))
    else:
        ok |= {last.get("provenance_input_md5"), last.get("provenance_planned_md5")}
    ok.discard(None)
    cur = _md5(pa["prov"])
    if cur in ok:
        return None
    if last.get("state") != "complete" and not last.get("provenance_planned_md5"):
        why = ("the --apply of {at} was interrupted and its record does not say what it would have written, so the "
               "file cannot be told apart from a change made since").format(at=last.get("applied_at"))
    else:
        why = f"it changed after the --apply of {last.get('applied_at')} (another backfill run?)"
    return (f"{pa['prov']} (md5 {cur}) is not a state this script left: {why}; check it and restore it by hand "
            f"from {first['provenance_backup']} if that is right")


def _locks(stack: ExitStack, paths: list) -> None:
    for p in paths:
        stack.enter_context(_csv_lock(p))


def do_apply(pa: dict, enabled: set, ref: dict, outside: dict) -> int:
    present = [f for f in (PERPS, SPOT) if os.path.exists(pa[f])]
    with ExitStack() as stack:
        _locks(stack, [pa[f] for f in present])           # hl_perps first, as hl_extract writes it first
        t_lock = time.monotonic()
        stack.callback(lambda: print(f"  held the collector's file locks for {time.monotonic() - t_lock:.1f} s"))
        stuck = _interrupted(pa)
        if stuck:
            raise Refuse(f"refusing: the last run recorded in {', '.join(stuck)} never completed; "
                         "run --rollback first")
        p = _read(pa[PERPS]) if PERPS in present else None
        s = _read(pa[SPOT]) if SPOT in present else None
        prov_in = bf._load_provenance(pa["prov"]) if os.path.exists(pa["prov"]) else None
        at = _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        # Re-plan on the files as they are now (the collector may have appended), with the candles
        # fetched outside the lock; repair 2's API proof already passed in the outside plan.
        res = plan(p, s, prov_in, ref, enabled, prove=False, at=at)
        pend2 = [sg["from_"] for sg in res["records"][PERPS].get(NAMES[2], {}).get("evidence", {}).get("segments", [])
                 if (sg["funding"], sg["oi"]) == ("x3", "coins")]
        pend2_out = [sg["from_"] for sg in outside["records"][PERPS].get(NAMES[2], {}).get("evidence", {}).get("segments", [])
                     if (sg["funding"], sg["oi"]) == ("x3", "coins")]
        if set(pend2) - set(pend2_out):
            raise Refuse("refusing: repair 2 has segments pending that the proof did not cover; re-run")
        changed = cells_changed(res)
        write = {f: any(changed.get(f, {}).values()) for f in present}
        prov_changed = res["prov"] is not None and prov_in is not None and res["prov"] != prov_in
        if not any(write.values()) and not prov_changed:
            print("  nothing to do: every enabled repair is already applied")
            return 0

        # Backups before any write: a kill here leaves no record, so the next --apply starts afresh
        # (and never reuses or overwrites these files; see _backup_copy).
        stamp = _utcnow().strftime("%Y%m%dT%H%M%SZ")
        os.makedirs(pa["backup"], exist_ok=True)
        backups = {}
        for f in present:
            if write[f]:
                backups[f] = _backup_copy(pa[f], pa["backup"], f, stamp)
        if prov_changed:
            backups[PROVENANCE] = _backup_copy(pa["prov"], pa["backup"], PROVENANCE, stamp)
        runs = {}
        # The write window: records "writing" -> CSVs -> sidecar -> records "complete". Signals
        # are held until it closes; a kill inside it leaves "writing", which --apply refuses and
        # --rollback undoes (the record carries every backup and the sidecar's planned md5).
        with _DeferSignals():
            for f in present:
                if not write[f] and not (f == PERPS and prov_changed):
                    continue
                rp = record_path(pa["data"], f)
                rec = _load_record(rp, f)
                run = {"kind": "apply", "applied_at": at, "state": "writing", "script": SCRIPT,
                       "order": [f"{k}_{NAMES[k]}" for k in ORDER if k in enabled],
                       "skipped": {str(k): v for k, v in res["skipped"].items()},
                       "backup": os.path.relpath(backups[f], os.path.dirname(pa["data"])) if f in backups else None,
                       "input_md5": _md5(pa[f]), "repairs": res["records"][f]}
                if f == PERPS and prov_changed:
                    run["provenance_backup"] = os.path.relpath(backups[PROVENANCE], os.path.dirname(pa["data"]))
                    run["provenance_input_md5"] = _md5(pa["prov"])
                    run["provenance_planned_md5"] = hashlib.md5(_json_bytes(res["prov"])).hexdigest()
                if f == PERPS and NAMES[2] in res["records"][PERPS] and outside["records"][PERPS].get(
                        NAMES[2], {}).get("evidence", {}).get("proof"):
                    run["repairs"][NAMES[2]]["evidence"]["proof"] = outside["records"][PERPS][NAMES[2]]["evidence"]["proof"]
                rec["runs"].append(run)
                _atomic_json(rec, rp)                     # record first: a kill leaves state "writing"
                runs[f] = (rp, rec, run)
            if write.get(PERPS):
                _atomic_to_csv(res["perps"], pa[PERPS])
            if write.get(SPOT):
                _atomic_to_csv(res["spot"], pa[SPOT])
            if prov_changed:
                _atomic_json(res["prov"], pa["prov"])
            for f, (rp, rec, run) in runs.items():
                run["state"] = "complete"
                run["output_md5"] = _md5(pa[f])
                if f == PERPS and prov_changed:
                    run["provenance_output_md5"] = _md5(pa["prov"])
                _atomic_json(rec, rp)
    print_report(res)
    for f, n in changed.items():
        print(f"  wrote {f}: " + ", ".join(f"{k} {v}" for k, v in n.items()) + (f"; backup {backups.get(f)}" if f in backups else ""))
    if prov_changed:
        print(f"  wrote {PROVENANCE}; backup {backups[PROVENANCE]}")
    for f, (rp, _, _) in runs.items():
        print(f"  record -> {rp}")
    return 0


def do_rollback(pa: dict) -> int:
    """Undo every --apply since the last rollback, complete or interrupted mid-write.

    Everything is checked before the first write (backups present, the provenance sidecar in a
    state this script left, no new columns), so a refusal changes nothing. The restores and the
    rollback entries are written with signals held; a kill in between leaves files that are
    already backups or still the applied state, which a re-run of --rollback accepts.
    """
    present = [f for f in (PERPS, SPOT) if os.path.exists(pa[f])]
    root = os.path.dirname(pa["data"])
    done = []
    with ExitStack() as stack:
        _locks(stack, [pa[f] for f in present])
        plans = {}
        for f in present:
            rp = record_path(pa["data"], f)
            rec = _load_record(rp, f)
            run, prov_run = _first_with(rec, "backup"), _first_with(rec, "provenance_backup")
            if run is None and prov_run is None:
                continue
            plans[f] = (rp, rec, run, prov_run)
        if not plans:
            print("  nothing to roll back: no --apply recorded since the last rollback")
            return 0
        out = {}
        for f, (rp, rec, run, prov_run) in plans.items():
            if prov_run is not None:
                src = os.path.join(root, prov_run["provenance_backup"])
                if not os.path.exists(src):
                    raise Refuse(f"refusing: backup {src} is missing")
                why = _prov_guard(pa, rec, root)
                if why:
                    raise Refuse(f"refusing: {why}")
            if run is None:
                continue
            src = os.path.join(root, run["backup"])
            if not os.path.exists(src):
                raise Refuse(f"refusing: backup {src} is missing")
            old, cur = _read(src), _read(pa[f])
            newer = _ts(cur) > _ts(old).max()
            carried = int(newer.sum())
            if carried and list(cur.columns) != list(old.columns):
                raise Refuse(f"refusing: {f} gained columns since the apply; restore {src} by hand")
            out[f] = (src, cur[newer], carried)
        with _DeferSignals():
            for f, (src, extra, carried) in out.items():
                if carried:
                    _atomic_to_csv(pd.concat([_read(src), extra], ignore_index=True), pa[f])
                else:
                    _atomic_copy(src, pa[f])
                done.append(f"  restored {f} from {src}" + (f", re-appended {carried} newer row(s)" if carried else ""))
            for f, (rp, rec, run, prov_run) in plans.items():
                if prov_run is not None:
                    _atomic_copy(os.path.join(root, prov_run["provenance_backup"]), pa["prov"])
                    done.append(f"  restored {PROVENANCE} from {prov_run['provenance_backup']}")
                undone = _since_rollback(rec)
                rec["runs"].append({"kind": "rollback", "rolled_back_at": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                                    "applies_undone": [r["applied_at"] for r in undone],
                                    "interrupted_applies": [r["applied_at"] for r in undone
                                                            if r.get("state") != "complete"],
                                    "restored_from": run.get("backup") if run else None,
                                    "provenance_restored_from": prov_run.get("provenance_backup") if prov_run else None,
                                    "rows_reappended": out.get(f, (None, None, 0))[2], "output_md5": _md5(pa[f])})
                _atomic_json(rec, rp)
                done.append(f"  record -> {rp}"
                            + (f" (undid an --apply interrupted mid-write: {rec['runs'][-1]['interrupted_applies']})"
                               if rec["runs"][-1]["interrupted_applies"] else ""))
    for line in done:
        print(line)
    return 0


def _parse_set(v: str | None) -> set:
    if not v:
        return set()
    out = {int(x) for x in v.replace(" ", "").split(",") if x}
    if out - set(ORDER):
        raise argparse.ArgumentTypeError(f"unknown repair(s) {sorted(out - set(ORDER))}; known: {sorted(ORDER)}")
    return out


def main(argv=None, ref_candles: dict | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the repairs (default: report only)")
    ap.add_argument("--rollback", action="store_true",
                    help="restore the backups of the first --apply since the last rollback (also after an "
                         "--apply interrupted mid-write; re-runnable)")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, OUTPUT_DIR),
                    help="directory holding hl_perps.csv / hl_spot_stocks.csv (default: the repo's historical_data/)")
    ap.add_argument("--only", help="comma-separated repairs to run (default: all)")
    ap.add_argument("--skip", help="comma-separated repairs to leave out")
    a = ap.parse_args(argv)
    if a.apply and a.rollback:
        ap.error("--apply and --rollback are exclusive")
    pa = _paths(os.path.abspath(a.data_dir))
    try:
        if a.rollback:
            return do_rollback(pa)
        enabled = (_parse_set(a.only) or set(ORDER)) - _parse_set(a.skip)
        if not os.path.exists(pa[PERPS]) and not os.path.exists(pa[SPOT]):
            print(f"  no {PERPS} / {SPOT} in {pa['data']} - nothing to do")
            return 0
        stuck = _interrupted(pa)
        if stuck and a.apply:
            raise Refuse(f"refusing: the last run recorded in {', '.join(stuck)} never completed; "
                         "run --rollback first")
        if stuck:
            print(f"  WARNING: the last --apply recorded in {', '.join(stuck)} never completed; run --rollback "
                  "before anything else (this dry run reads the half-written files)")
        print("  repairs, in order: " + ", ".join(f"{k} {NAMES[k]}" for k in ORDER if k in enabled))
        p = _read(pa[PERPS]) if os.path.exists(pa[PERPS]) else None
        s = _read(pa[SPOT]) if os.path.exists(pa[SPOT]) else None
        prov = bf._load_provenance(pa["prov"]) if os.path.exists(pa["prov"]) else None
        ref = ref_candles if ref_candles is not None else fetch_ref_candles(p)
        outside = plan(p, s, prov, ref, enabled, prove=True)     # API reads happen here, outside the locks
        if not a.apply:
            print_report(outside)
            changed = cells_changed(outside)
            todo = {f: {k: v for k, v in n.items() if v} for f, n in changed.items()}
            todo = {f: n for f, n in todo.items() if n}
            if not todo:
                print("  nothing to do: every enabled repair is already applied")
            else:
                print("  DRY RUN - would change " + "; ".join(
                    f"{f}: " + ", ".join(f"{k} {v}" for k, v in n.items()) for f, n in todo.items())
                    + "; re-run with --apply")
            return 0
        return do_apply(pa, enabled, ref, outside)
    except Refuse as e:
        print(f"  {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
