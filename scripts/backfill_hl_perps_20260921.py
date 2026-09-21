#!/usr/bin/env python3
"""One-off: back-fill hl_perps.csv PRICES for the perps HL_PERPS dropped.

XRP, LINK, DOGE, AVAX and SUI were removed from HL_PERPS between the 2026-03-19 23:29 and
23:34 (GMT+8) runs of hl_extract.py, the same edit that added the first builder perp (the
row after LINK's last value is the first to carry hl_oil_*). hl_extract.py only writes the
coins in HL_PERPS, and append_to_csv keeps every column the file already has, so the
header kept hl_{xrp,link,doge,avax,sui}_* while every later row left them blank. XRP was
restored 2026-09-20 (0697893), the other four on 2026-09-21. Brent (xyz:BRENTOIL) went
the same way after its last value on 2026-03-22 14:40 (GMT+8) and was deleted from the
registry on 2026-08-30 on the mistaken belief that the market did not exist; its 39
March values sit inside xyz:BRENTOIL's own hourly ranges, so the fill is the same
instrument. (hl_oil/sp500/natgas/copper_hl are not touched: their Jun-Aug blanks are
followed by three weeks of frozen flx quotes that only a separate, explicit repair may
replace.)

What the public API can give back for those blank rows, and what it cannot:

    hl_*_price       FILLED from candleSnapshot: the close of the last candle that had
                     COMPLETED by the row's timestamp (as-of, never a later price). The
                     API keeps only the newest ~5000 candles per interval, so the finest
                     interval that still covers the row is used: 1m (last ~3.5 days),
                     5m (~17 days), 15m (~52 days), 1h (~208 days). A candle close is
                     the last trade; the column otherwise holds the mid.
    hl_*_funding     LEFT BLANK. fundingHistory is the SETTLED hourly rate; the column
                     is the instantaneous predicted rate from metaAndAssetCtxs. After
                     2026-08-30 they correlate 0.76-0.93 (BTC/ETH/SOL/HYPE, even aligned
                     to the next settlement, which is look-ahead) and agree exactly on
                     only 50-77% of rows. Before 2026-08-30 15:33 UTC the column was also
                     annualised x3x365 instead of x24x365, so no single fill is right.
    hl_*_oi          LEFT BLANK: the info API has no open-interest history.
    hl_*_volume_24h  LEFT BLANK: dayNtlVlm is a rolling 24h notional the API does not
                     serve historically; rebuilding it from candle base volume would be
                     an estimate, not the published figure.
    hl_*_premium     LEFT BLANK: needs mark and oracle history, which the API does not serve.

THE FILLED PRICES ARE A STEP FUNCTION, NOT A 5-MINUTE SERIES
------------------------------------------------------------
One candle close is the only price the API still has for a whole candle, while the rows
are ~5 min apart (~70 s in March). Run on 2026-09-21, the 1h tier holds ~56% of the
fillable cells (2026-03-19 to about 2026-07-31) with ~12 rows per candle, and the 15m
tier ~29% with ~3. What goes into the other rows of a candle is a choice, and --apply
refuses to run until it is made with --fill (the dry run prints both):

  --fill first   Write each close only into the FIRST row at or after that candle's
                 close (no other row of the file lies between the close and it) and leave
                 the rest of that candle's rows blank. Every written value is then at most
                 one row interval old, and consecutive written values are consecutive
                 closes, so the returns between them are real. Coverage: ~1 row in 12 in
                 the 1h tier (1 in ~50 of the 70-second March rows), ~1 in 3 in the 15m
                 tier, nearly every row in the 5m and 1m tiers.
  --fill all     Write the close into EVERY row of the candle (except rows that follow a
                 newer collector value, which neither mode fills: the close is not the
                 price as of those rows). The column is dense, but a value can be a whole
                 candle old, and inside the 1h tier ~11 of every 12 consecutive 5-minute
                 returns are exactly zero (hl_link_price on 2026-07-01: 24 distinct values
                 in 260 rows, 91% zero returns, against 1.5% for the collector's own
                 hl_btc_price); in the 15m tier ~2 of 3. 5-minute volatility, intraday
                 correlation, lead-lag and funding-vs-return studies on these columns are
                 biased over that span.
--fill first loses nothing: an as-of forward fill of its column in timestamp order gives
--fill all's value on every row --fill all writes (checked on the VPS file: 0 differing
cells), and on the few rows after a collector value it carries that newer mid instead.
Given the same candles, both modes give identical hourly and daily last-price resamples
(checked on the VPS file; analytics.py reads it through resample('D').last(), which skips
blanks). Two runs minutes apart can differ in a few boundary hours, because the API's
1m/5m/15m windows slide and push the oldest rows of a tier to the next coarser one. With
--fill first, take returns from s.dropna(): pandas' pct_change() pads blanks forward by
default (2.3.3, the VPS version) and would put the zeros straight back.

Accuracy: |candle close / collector mid - 1| on rows where the column already holds the
collector's own mid, each row scored at the candle interval the fill would use for it, over
every such row ("all") and over the rows --fill first would write ("first"). The dry run
prints this table for the day it runs; on 2026-09-21 against the VPS file (median / p95, %;
BTC/ETH/SOL/HYPE: 17,622 rows in the 1h tier, 8,952 in 15m, 1,461 and 3,305 of them "first"):

                1h all        1h first      15m all       15m first     5m all        1m all
    BTC         0.14 / 0.67   0.04 / 0.24   0.05 / 0.27   0.03 / 0.18   0.03 / 0.15   0.01 / 0.05
    ETH         0.17 / 0.89   0.06 / 0.31   0.06 / 0.35   0.04 / 0.23
    SOL         0.20 / 1.04   0.07 / 0.37   0.08 / 0.45   0.05 / 0.29
    HYPE        0.33 / 1.52   0.11 / 0.51   0.12 / 0.60   0.08 / 0.38
    XRP (own)   0.42 / 0.95   n=7                                                     0.03 / 0.15
    LINK (own)  0.36 / 0.86   n=7
    DOGE (own)  0.29 / 0.91   n=7
    AVAX (own)  0.35 / 0.80   n=7
    SUI (own)   0.33 / 0.86   n=7
    BRENT (own) 0.22 / 0.43   n=1
BTC is the best case: an alt's 1h-tier error runs 1.2-2.4x BTC's (ETH to HYPE). The
filled coins' own samples are small (47 March rows each for xrp/link/doge/avax/sui, all in
the 1h tier, 39 for brentoil; XRP's ~170 rows since its 2026-09-20 restore sit in the 1m
tier), so ETH/SOL/HYPE stand in for them at scale. "first" cuts the error ~3x because its
value is at most one row interval old; "all" carries values up to a whole candle old.

Provenance: every --apply records what it wrote in .hl_perps.provenance.json NEXT TO
hl_perps.csv (a dot-file that is not *.csv, so the loaders, data_guard and health_checks
skip it). Each span {column, from, to, interval, utc_offset_h, cells, ...} of each run
means: every NON-BLANK cell of `column` in the rows whose timestamp lies in [from, to]
(the file's own naive timestamps, compared as datetimes) is a back-filled candle close,
not a collector mid. A span never contains a collector value. A reader that needs the
collector's data only drops those cells:

    prov = json.load(open("historical_data/.hl_perps.provenance.json"))
    ts = pd.to_datetime(df["timestamp"], format="ISO8601")
    for run in prov["runs"]:
        for s in run["spans"]:
            df.loc[ts.between(pd.Timestamp(s["from"]), pd.Timestamp(s["to"])), s["column"]] = None

`interval` is the candle interval of the cells that run wrote; a later --fill all on top
of a --fill first run can leave both intervals inside one span. Spans are cut in TIMESTAMP
order (a reader selects by timestamp, not row position), a fill whose timestamp equals a
collector value's in the same column is not written (no range could separate the two), and
before anything is written the script applies the recipe above to its own result and
refuses unless it removes exactly the back-filled cells and no collector value. The sidecar
is written before the CSV, so a crash cannot leave unrecorded fills, and it allows an exact
undo that keeps rows appended after the backup: blank the non-blank cells inside every span.

The file mixes timezones: rows up to 2026-03-24 were written on the Mac (naive GMT+8)
and copied to the VPS, whose rows from 2026-06-03 are naive UTC. Each contiguous run of
rows (split at gaps > 6 h) gets its UTC offset from the data itself: the offset under
which the file's own hl_btc_price lies inside the BTC hourly candle's range. A run
with no clear winner is skipped, not guessed.

Only blank cells are written; a non-blank value is never changed (checked before the
write). Dry run by default. With --apply the file is copied to
.deploy_backup_20260921/data/ next to the data directory (the repo root for
historical_data/) before it is rewritten (the first, pristine copy is kept; so is any
earlier sidecar), under the collectors' per-file lock, via an atomic replace; the full
report goes to hl_perps.backfill_manifest.json beside the backup. A second --apply with
the same --fill writes nothing; --fill all after --fill first tops up the skipped rows
(given the same candles the result is byte-identical to a direct --fill all).
To undo: blank the cells the sidecar lists, or restore the backup (which also drops the
rows appended since) and delete the sidecar if the backup dir holds no copy of it.

The API forgets: it serves the newest ~5000 candles per interval, so the 2026-03-19..24
rows drop out of the 1h window around 2026-10-14, and every day of delay moves recent rows
to a coarser interval. Run it soon after the collector fix is deployed.

  python scripts/backfill_hl_perps_20260921.py                     # dry run, both modes
  python scripts/backfill_hl_perps_20260921.py --fill first --apply
  python scripts/backfill_hl_perps_20260921.py --fill all --apply
  python scripts/backfill_hl_perps_20260921.py --data-dir /path/to/copy/historical_data --fill first --apply
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone

import pandas as pd
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from extract_historical_data import OUTPUT_DIR, _atomic_to_csv, _csv_lock  # noqa: E402

FILE = "hl_perps.csv"
PROVENANCE = ".hl_perps.provenance.json"
HL_API_URL = "https://api.hyperliquid.xyz/info"
# column key -> Hyperliquid coin
COINS = {"xrp": "XRP", "link": "LINK", "doge": "DOGE", "avax": "AVAX", "sui": "SUI",
         "brentoil": "xyz:BRENTOIL"}
# Liquid alts the collector always wrote: the method check at scale for the steppy tiers.
REF_ALTS = {"eth": "ETH", "sol": "SOL", "hype": "HYPE"}
TIERS = [("1m", 60_000), ("5m", 300_000), ("15m", 900_000), ("1h", 3_600_000)]
TIER_MS = dict(TIERS)
FILL_MODES = ("first", "all")
REF_COIN, REF_COL = "BTC", "hl_btc_price"
SEGMENT_BREAK = pd.Timedelta(hours=6)
OFFSETS_H = range(-12, 15)
FIT_TOL = 0.0005          # mid vs trade range: 5 bp slack on the hourly high/low
FIT_MIN, FIT_MARGIN, FIT_MIN_ROWS = 0.95, 0.15, 20
BACKUP_TAG = ".deploy_backup_20260921"
API_WEIGHT_PER_MIN = 1200
SOURCE = ("Hyperliquid candleSnapshot: close (last trade) of the last candle completed by "
          "the row's time, at the finest interval the API still served")


def _post(body: dict):
    for attempt in range(6):
        r = requests.post(HL_API_URL, json=body, timeout=30)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"Hyperliquid kept rate-limiting {body.get('type')}")


def fetch_candles(coin: str, start_ms: int, end_ms: int, intervals=None) -> dict[str, dict[int, dict]]:
    """{interval: {open_ms: candle}}; the API returns the newest <=5000 per interval."""
    out = {}
    for interval, _ in TIERS:
        if intervals is not None and interval not in intervals:
            continue
        rows = _post({"type": "candleSnapshot", "req": {
            "coin": coin, "interval": interval, "startTime": start_ms, "endTime": end_ms}}) or []
        out[interval] = {int(c["t"]): c for c in rows}
        # candleSnapshot costs 20 + 1 per 60 candles of the 1200-per-minute IP budget
        # that the live collector shares; a full 5000-candle reply is ~103. Pace to
        # stay inside it, so hl_extract's own requests are not the ones throttled.
        time.sleep(max(0.25, (20 + len(rows) / 60) / API_WEIGHT_PER_MIN * 60 * 1.25))
    return out


def as_of_close(candles: dict[str, dict[int, dict]], utc_ms: int):
    """(close, interval, close_ms) of the last candle completed by utc_ms, finest interval first."""
    for interval, ms in TIERS:
        key = (utc_ms // ms) * ms - ms          # the candle that closed at floor(utc_ms)
        c = candles.get(interval, {}).get(key)
        if c is not None:
            return c["c"], interval, key + ms
    return None, None, None


def segments(ts: pd.Series) -> list[tuple[int, int]]:
    """[start, end) row ranges with no gap > SEGMENT_BREAK and no step backwards."""
    step = ts.diff()
    cut = [0] + [i for i in range(1, len(ts)) if step.iloc[i] > SEGMENT_BREAK or step.iloc[i] < pd.Timedelta(0)]
    cut.append(len(ts))
    return [(cut[i], cut[i + 1]) for i in range(len(cut) - 1) if cut[i + 1] > cut[i]]


def detect_offset(ts: pd.Series, px: pd.Series, ref_1h: dict[int, dict]):
    """(offset_hours, fit, runner_up_fit, rows_checked) or offset None when ambiguous."""
    ok = px.notna() & ts.notna()
    ts, px = ts[ok], px[ok]
    if len(ts) > 600:                            # evenly spaced sample is plenty
        pick = [round(i * (len(ts) - 1) / 599) for i in range(600)]
        ts, px = ts.iloc[pick], px.iloc[pick]
    fits = {}
    for off in OFFSETS_H:
        hit = n = 0
        for t, p in zip(ts, px):
            u = int((t - pd.Timedelta(hours=off)).value // 1_000_000)
            c = ref_1h.get((u // 3_600_000) * 3_600_000)
            if c is None:
                continue
            n += 1
            if float(c["l"]) * (1 - FIT_TOL) <= p <= float(c["h"]) * (1 + FIT_TOL):
                hit += 1
        if n >= FIT_MIN_ROWS:
            fits[off] = (hit / n, n)
    if not fits:
        return None, 0.0, 0.0, 0
    ranked = sorted(fits.items(), key=lambda kv: kv[1][0], reverse=True)
    best_off, (best, n) = ranked[0]
    second = ranked[1][1][0] if len(ranked) > 1 else 0.0
    if best >= FIT_MIN and best - second >= FIT_MARGIN:
        return best_off, best, second, n
    return None, best, second, n


def row_keys(d: pd.DataFrame) -> pd.Series:
    """A key per row that survives a collector rewrite: parsed time + rank among equal times."""
    ts = pd.to_datetime(d["timestamp"], format="ISO8601", errors="coerce")
    ns = ts.map(lambda t: None if pd.isna(t) else str(t.value))
    rank = ns.groupby(ns.fillna("")).cumcount().astype(str)
    return pd.Series([None if n is None else f"{n}#{r}" for n, r in zip(ns, rank)], index=d.index, dtype=object)


def _numbers(s: pd.Series) -> list:
    v = pd.to_numeric(s, errors="coerce")
    return [None if pd.isna(x) or x <= 0 else float(x) for x in v]


def _q(xs: list, q: float) -> float:
    return round(float(pd.Series(xs, dtype=float).quantile(q)), 4)


def fill_tiers(candles, utc: list) -> list:
    """Per row, the interval as_of_close takes the value from (None: no candle / no timezone)."""
    return [None if u is None else as_of_close(candles, u)[1] for u in utc]


def method_check(candles, px: list, utc: list, prev: list, tiers: list) -> dict:
    """|close/mid-1| in % on rows that hold a collector mid, each row checked at the interval
    the fill would use for it (tiers[i]), so every figure describes the fill actually made:
    over every such row ("all") and over the rows that are first after their candle's close
    (what --fill first would write)."""
    acc: dict[str, tuple[list, list]] = {}
    for p, u, pu, iv in zip(px, utc, prev, tiers):
        if p is None or u is None or iv is None:
            continue
        ms = TIER_MS[iv]
        key = (u // ms) * ms - ms
        c = (candles.get(iv) or {}).get(key)
        if c is None:
            continue
        e = abs(float(c["c"]) / p - 1) * 100
        e_all, e_first = acc.setdefault(iv, ([], []))
        e_all.append(e)
        if pu is None or pu < key + ms:
            e_first.append(e)
    res = {}
    for iv, _ in TIERS:
        if iv not in acc:
            continue
        e_all, e_first = acc[iv]
        r = {"rows": len(e_all), "median_abs_pct": _q(e_all, .5), "p95_abs_pct": _q(e_all, .95),
             "first_rows": len(e_first)}
        if e_first:
            r.update(first_median_abs_pct=_q(e_first, .5), first_p95_abs_pct=_q(e_first, .95))
        res[iv] = r
    return res


def mode_stats(cand: dict, native: list, order: list, mode: str) -> dict:
    """What --fill <mode> would write into one column, and how steppy the result is."""
    sel = {i: c for i, c in cand.items() if mode == "all" or c["first"]}
    out = {"filled": len(sel), "by_interval": {}, "age_min": {}, "zero_return_pct": {}}
    if not sel:
        return out
    age, zero = {}, {}
    last = None                                   # last non-blank value in time order
    for i in order:
        if i in sel:
            v = float(sel[i]["value"])
            iv = sel[i]["interval"]
            age.setdefault(iv, []).append(sel[i]["age_s"] / 60)
            if last is not None:
                zero.setdefault(iv, []).append(v == last)
            last = v
        elif native[i] is not None:
            last = native[i]
    for iv, _ in TIERS:
        if iv in age:
            out["by_interval"][iv] = len(age[iv])
            out["age_min"][iv] = {"median": _q(age[iv], .5), "max": round(max(age[iv]), 2)}
        if zero.get(iv):
            out["zero_return_pct"][iv] = round(100 * sum(zero[iv]) / len(zero[iv]), 1)
    allz = [z for zs in zero.values() for z in zs]
    out["zero_return_pct"]["overall"] = round(100 * sum(allz) / len(allz), 1) if allz else None
    return out


def plan(d: pd.DataFrame, prior: list = ()):
    """Work out every candidate fill for the blank price cells of COINS. Reads the API, not the disk.

    Returns ({column: {row_key: candidate}}, report). A candidate carries both modes: its
    `first` flag says whether --fill first writes it."""
    ts = pd.to_datetime(d["timestamp"], format="ISO8601", errors="coerce")
    keys = row_keys(d)
    ref_px = pd.to_numeric(d[REF_COL], errors="coerce")
    targets = {k: f"hl_{k}_price" for k in COINS if f"hl_{k}_price" in d.columns}
    missing_cols = [k for k in COINS if k not in targets]
    blank = {k: d[col].str.strip() == "" for k, col in targets.items()}
    need = pd.Series(False, index=d.index)
    for m in blank.values():
        need |= m
    report = {"segments": [], "coins": {}, "missing_columns": missing_cols, "method_check": {}}
    if not need.any():
        return {}, report

    start_ms = int((ts[need].min() - pd.Timedelta(days=1)).value // 1_000_000)
    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    ref = fetch_candles(REF_COIN, start_ms, end_ms)

    n = len(d)
    offset, seg = [None] * n, [None] * n
    for si, (a, b) in enumerate(segments(ts)):
        off, fit, second, checked = detect_offset(ts.iloc[a:b], ref_px.iloc[a:b], ref["1h"])
        report["segments"].append({
            "from": d["timestamp"].iloc[a], "to": d["timestamp"].iloc[b - 1], "rows": b - a,
            "blank_rows": int(need.iloc[a:b].sum()),
            "utc_offset_h": off, "fit": round(fit, 3), "runner_up_fit": round(second, 3), "checked": checked})
        for i in range(a, b):
            offset[i], seg[i] = off, si

    utc = [int((t - pd.Timedelta(hours=o)).value // 1_000_000) if o is not None and not pd.isna(t) else None
           for t, o in zip(ts, offset)]
    # Time order (ties in file order) and, per row, the UTC time of the row just before it:
    # a row is "first after a candle's close" when that previous row is older than the close.
    order = sorted((i for i in range(n) if utc[i] is not None), key=lambda i: (utc[i], i))
    prev = [None] * n
    last = None
    for i in order:
        prev[i] = last
        last = utc[i]

    # How close is "as-of candle close" to the mid the file holds? Measured per interval on
    # the collector's own rows, so the operator sees the method's error before applying.
    # Each row is scored at the interval the fill uses for it (the reference alts take BTC's,
    # since the API's window per interval is the same for every liquid coin).
    mc = report["method_check"]
    ref_tiers = fill_tiers(ref, utc)
    mc[REF_COIN] = method_check(ref, _numbers(ref_px), utc, prev, ref_tiers)
    coarse = [t if t in ("15m", "1h") else None for t in ref_tiers]
    for k, coin in REF_ALTS.items():
        col = f"hl_{k}_price"
        if col in d.columns:
            mc[coin] = method_check(fetch_candles(coin, start_ms, end_ms, ("15m", "1h")),
                                    _numbers(d[col]), utc, prev, coarse)

    cands: dict[str, dict[str, dict]] = {}
    for k, col in targets.items():
        rows = list(d.index[blank[k]])
        rec = {"blank": len(rows), "no_offset": 0, "no_candle": 0, "superseded": 0, "modes": {}}
        report["coins"][k] = rec
        if not rows:
            continue
        candles = fetch_candles(COINS[k], start_ms, end_ms)
        native = _numbers(d[col])
        mc[f"{COINS[k]} (own rows)"] = method_check(candles, native, utc, prev, fill_tiers(candles, utc))
        # UTC of the newest collector value of this column before each row (time order). A
        # close older than that value is not the price as of the row: without this, --fill
        # all wrote the 23:00 close into the 2026-03-19 23:34-23:59 rows that follow LINK's
        # last collector mid (23:29), stepping the column back in time. Cells an earlier run
        # of this script wrote (`prior` spans) are not collector values: counting them would
        # make every row skipped by --fill first look superseded and block the --fill all top-up.
        has = collector_cells(d, ts, col, list(prior)).tolist()
        last_obs, seen = [None] * n, None
        for i in order:
            last_obs[i] = seen
            if has[i]:
                seen = utc[i]
        cand = {}
        for i in rows:
            if utc[i] is None:
                rec["no_offset"] += 1
                continue
            v, interval, close_ms = as_of_close(candles, utc[i])
            if v is None:
                rec["no_candle"] += 1
                continue
            if last_obs[i] is not None and last_obs[i] >= close_ms:
                rec["superseded"] += 1
                continue
            cand[i] = {"value": v, "interval": interval, "age_s": (utc[i] - close_ms) / 1000,
                       "first": prev[i] is None or prev[i] < close_ms,
                       "seg": seg[i], "utc_offset_h": offset[i]}
        for mode in FILL_MODES:
            rec["modes"][mode] = mode_stats(cand, native, order, mode)
        if cand:
            cands[col] = {keys[i]: c for i, c in cand.items()}
    return cands, report


def _read(path: str) -> pd.DataFrame:
    # Everything as text: untouched values go back byte-for-byte.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _atomic_json(obj, path: str) -> None:
    fd, tmp = tempfile.mkstemp(prefix=f"{os.path.basename(path)}.", suffix=".tmp", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh, indent=1)
            fh.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _load_provenance(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return {"file": FILE, "written_by": "scripts/backfill_hl_perps_20260921.py",
            "meaning": ("Every NON-BLANK cell of span.column in the rows of hl_perps.csv whose timestamp "
                        "lies in [span.from, span.to] (naive, compared as datetimes) is a back-filled "
                        "candle close, not a collector mid; no collector value lies inside a span. "
                        "fill=first: only the first row at/after each candle close holds a value; "
                        "fill=all: every row repeats its candle's close (an hourly step in the 1h tier). "
                        "span.interval = candle interval of the cells that run wrote."),
            "runs": []}


def _prior_spans(prov: dict) -> list:
    return [s for run in prov.get("runs", []) for s in run.get("spans", [])]


def _covered(ts: pd.Series, spans: list, col: str) -> pd.Series:
    """Rows the reader recipe in the docstring treats as back-filled for `col`."""
    m = pd.Series(False, index=ts.index)
    for s in spans:
        if s["column"] == col:
            m |= ts.between(pd.Timestamp(s["from"]), pd.Timestamp(s["to"]))
    return m


def collector_cells(d: pd.DataFrame, ts: pd.Series, col: str, prior: list) -> pd.Series:
    """Non-blank cells of `col` that no earlier run of this script wrote: the collector's own."""
    return (d[col].str.strip() != "") & ~_covered(ts, prior, col)


def build_spans(d: pd.DataFrame, before: pd.DataFrame, wrote: dict, meta: dict, prov: dict) -> list:
    """Maximal TIME ranges per column holding this run's fills and no collector value.

    wrote[col]: mask of cells written now; meta[col]: {row index: candidate}. Rows are walked
    in timestamp order, because readers select a span by timestamp, not by row position.
    Cells written by an earlier run (inside that run's spans) and blank cells do not break a
    span; a collector value does. (A fill that shares its timestamp with a collector value
    is never written, see main(), so a span edge cannot pick one up.)"""
    ts = pd.to_datetime(d["timestamp"], format="ISO8601", errors="coerce")
    order = ts.dropna().sort_values(kind="mergesort").index
    prior = _prior_spans(prov)
    spans = []
    for col, m in wrote.items():
        native = collector_cells(before, ts, col, prior)
        cur = None
        for pos, i in enumerate(order):
            w, nat = bool(m.at[i]), bool(native.at[i])
            if w:
                c = meta[col][i]
                k = (c["interval"], c["seg"])
                if cur is not None and cur["k"] == k:
                    cur.update(to=i, to_pos=pos, cells=cur["cells"] + 1, age=max(cur["age"], c["age_s"]))
                    continue
                if cur is not None:
                    spans.append(cur)
                cur = {"col": col, "k": k, "off": c["utc_offset_h"], "from": i, "to": i,
                       "from_pos": pos, "to_pos": pos, "cells": 1, "age": c["age_s"]}
            elif nat and cur is not None:
                spans.append(cur)
                cur = None
        if cur is not None:
            spans.append(cur)
    return [{"column": s["col"], "from": d.at[s["from"], "timestamp"], "to": d.at[s["to"], "timestamp"],
             "interval": s["k"][0], "utc_offset_h": s["off"], "cells": s["cells"],
             "rows": s["to_pos"] - s["from_pos"] + 1, "max_value_age_min": round(s["age"] / 60, 2)} for s in spans]


def verify_provenance(d: pd.DataFrame, before: pd.DataFrame, wrote: dict, prov_after: dict,
                      prior: list) -> None:
    """Apply the docstring's reader recipe to the result: it must blank every cell this run
    wrote and must not touch a single collector value. Refuse to write otherwise."""
    ts = pd.to_datetime(d["timestamp"], format="ISO8601", errors="coerce")
    spans = _prior_spans(prov_after)
    for col, m in wrote.items():
        cover = _covered(ts, spans, col)
        native = collector_cells(before, ts, col, prior)
        if (cover & native).any():
            raise SystemExit(f"refusing to write: a provenance span of {col} would cover "
                             f"{int((cover & native).sum())} collector value(s)")
        if (m & ~cover).any():
            raise SystemExit(f"refusing to write: {int((m & ~cover).sum())} filled cell(s) of {col} "
                             "fall outside every provenance span")


def _print_report(report: dict, modes) -> None:
    for s in report["segments"]:
        tz = "UNRESOLVED - skipped" if s["utc_offset_h"] is None else f"UTC{s['utc_offset_h']:+d}"
        print(f"  rows {s['from'][:16]} -> {s['to'][:16]} ({s['rows']:>5}, {s['blank_rows']:>5} to fill): "
              f"{tz}  [fit {s['fit']}, next best {s['runner_up_fit']}, {s['checked']} checked]")
    print("  method check, |candle close / collector mid - 1| in %, median / p95 (n); "
          "'first' = rows --fill first would write:")
    for coin, tiers in report["method_check"].items():
        for iv, r in tiers.items():
            first = (f"first {r['first_median_abs_pct']} / {r['first_p95_abs_pct']} ({r['first_rows']})"
                     if r.get("first_rows") else "first -")
            print(f"    {coin:<22} {iv:>3}: all {r['median_abs_pct']} / {r['p95_abs_pct']} ({r['rows']});  {first}")
    for k, r in report["coins"].items():
        print(f"  hl_{k}_price: {r['blank']} blank; left blank in both modes: {r['no_offset']} no timezone, "
              f"{r['no_candle']} no candle, {r['superseded']} after a newer collector value")
        for mode in modes:
            st = r["modes"].get(mode)
            if not st:
                continue
            tiers = ", ".join(f"{iv} {c}" for iv, c in st["by_interval"].items()) or "-"
            ages = ", ".join(f"{iv} {a['median']}/{a['max']}" for iv, a in st["age_min"].items())
            zr = ", ".join(f"{iv} {p}%" for iv, p in st["zero_return_pct"].items() if p is not None)
            print(f"    --fill {mode:<5}: {st['filled']:>6} cells ({tiers})")
            if st["filled"]:
                print(f"                   value age min median/max: {ages}")
                print(f"                   zero returns vs the previous value: {zr}")
    if report["missing_columns"]:
        print(f"  columns absent from the file (skipped): {report['missing_columns']}")
    print("  funding / oi / volume_24h / premium are not back-filled (see the docstring)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    ap.add_argument("--fill", choices=FILL_MODES,
                    help="first: only the first row after each candle close; all: every row "
                         "(an hourly step in the 1h tier). Required with --apply; see the docstring")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, OUTPUT_DIR),
                    help="directory holding hl_perps.csv (default: the repo's historical_data/)")
    a = ap.parse_args()
    if a.apply and not a.fill:
        ap.error("--apply needs --fill first|all: the 1h-tier fill is an hourly step function "
                 "(see the docstring); the dry run prints both")

    data_dir = os.path.abspath(a.data_dir)
    path = os.path.join(data_dir, FILE)
    prov_path = os.path.join(data_dir, PROVENANCE)
    backup_dir = os.path.join(os.path.dirname(data_dir), BACKUP_TAG, "data")
    if not os.path.exists(path):
        print(f"  {path} not present — nothing to do")
        return 0

    # The API reads happen outside the lock: hl_extract rewrites this file every 5 min.
    cands, report = plan(_read(path), _prior_spans(_load_provenance(prov_path)))
    modes = (a.fill,) if a.fill else FILL_MODES
    _print_report(report, modes)

    totals = {m: sum(r["modes"].get(m, {}).get("filled", 0) for r in report["coins"].values()) for m in FILL_MODES}
    if not any(totals[m] for m in modes):
        print("  nothing to fill")
        return 0
    if not a.apply:
        print("  DRY RUN — " + "; ".join(f"--fill {m} would fill {totals[m]} cell(s)" for m in modes)
              + "; re-run with --fill first|all --apply")
        return 0

    with _csv_lock(path):
        d = _read(path)                           # re-read: rows may have been appended
        before = d.copy()
        keys = row_keys(d)
        ts = pd.to_datetime(d["timestamp"], format="ISO8601", errors="coerce")
        prov = _load_provenance(prov_path)
        prior = _prior_spans(prov)
        wrote, meta = {}, {}
        written = 0
        tied = {}
        for col, cand in cands.items():
            sel = {k: c for k, c in cand.items() if a.fill == "all" or c["first"]}
            hit = keys.map(lambda k: sel[k]["value"] if k in sel else None)
            m = hit.notna() & (d[col].str.strip() == "")
            # A timestamp range cannot separate two rows with the same timestamp, so a fill
            # that shares one with a collector value would put that value inside a span.
            tie = m & ts.isin(set(ts[collector_cells(d, ts, col, prior)]))
            if tie.any():
                tied[col] = int(tie.sum())
                m &= ~tie
            if not m.any():
                continue
            d.loc[m, col] = hit[m]
            wrote[col] = m
            meta[col] = {i: sel[keys[i]] for i in d.index[m]}
            written += int(m.sum())
        if ((d != before) & (before.apply(lambda c: c.str.strip()) != "")).any().any():
            raise SystemExit("refusing to write: a non-blank value would change")
        if tied:
            print(f"    not written, timestamp shared with a collector value: {tied}")
        if not written:
            print("  nothing left to fill (already done)")
            return 0

        spans = build_spans(d, before, wrote, meta, prov)
        applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        prov["runs"].append({"applied_at": applied_at, "fill": a.fill, "source": SOURCE,
                             "cells_written": written,
                             "columns": {c: int(m.sum()) for c, m in wrote.items()},
                             "spans": spans})
        verify_provenance(d, before, wrote, prov, prior)

        os.makedirs(backup_dir, exist_ok=True)
        dst = os.path.join(backup_dir, FILE)
        if os.path.exists(dst):                   # keep the first, pristine copy
            print(f"    backup already present: {dst}")
        else:
            shutil.copy2(path, dst)
            print(f"    backed up -> {dst}")
        prov_dst = os.path.join(backup_dir, PROVENANCE)
        if os.path.exists(prov_path) and not os.path.exists(prov_dst):
            shutil.copy2(prov_path, prov_dst)
        # Sidecar first: if the CSV write then fails, the spans only claim cells that stay blank.
        _atomic_json(prov, prov_path)
        _atomic_to_csv(d, path)

        report.update(applied_at=applied_at, fill=a.fill, cells_written=written,
                      provenance=prov_path, spans=len(spans), not_written_tied=tied)
        mf = os.path.join(backup_dir, "hl_perps.backfill_manifest.json")
        runs = []
        if os.path.exists(mf):
            with open(mf) as fh:
                old = json.load(fh)
            runs = old if isinstance(old, list) else [old]
        runs.append(report)
        _atomic_json(runs, mf)
    print(f"  wrote {written} price cell(s) (--fill {a.fill}) to {path}")
    print(f"  provenance: {len(spans)} span(s) -> {prov_path}; manifest -> {mf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
