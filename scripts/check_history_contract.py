#!/usr/bin/env python3
"""Guard for docs/HISTORY_CONTRACT.md: the price history the CC trading pipeline reads from here.

The CC pipeline (CLI_OS/Agent_Orchestration/CC) scores its forecasts and derives stop / target
geometry from 12 daily series: the 11 files in SERIES plus btc-enhanced-streak-mitigation's BTC
hourly file. Its reader (CC agents/volmath.py) anchors on the last bar STRICTLY before the
pipeline date and needs, at that anchor, 20 close-to-close changes for sigma_1d and 14 true
ranges for ATR14. When it cannot compute them the idea is rejected (no_sigma / no_atr) rather
than traded, so a thin, gappy or half-written file silently shrinks the book. This checks the
files against that contract.

Per file it FAILs (exit 1) on: a missing file or required column; a collector's lock held
for more than 10 s; any row whose date (or timestamp) is blank or unparseable — the shape of the
2026-09-01 gold.csv fragment (QA_SOP.md Bug Log, 2026-09-16); a blank trailing row; dates that
step backwards; fewer than 21 valid bars before --as-of; the most recent 21 spanning more than
45 calendar days; a non-finite price among them. It WARNs (exit 0) on: a date carrying more
than one daily bar; OHLC bars in that window with high < max(open, close) or
low > min(open, close); rows whose field count differs from the header; no final newline; a
last bar 5 or more days before --as-of (a FAIL with --strict-fresh).

The bars are counted exactly as the reader builds them (last row per date wins, unparseable
values skipped; the rules are restated in reader_bars()). Stdlib only and read-only: it never
imports from CC or from extract_historical_data (pandas), never creates a lock file, and takes
a shared lock on .<file>.lock only when a collector has already created one.

  python3 scripts/check_history_contract.py --data-dir historical_data
  python3 scripts/check_history_contract.py --data-dir /root/macro_2/historical_data \\
      --btc /root/btc-enhanced-streak-mitigation/BTC_OHLC_1h_gmt8_updated.csv --json /tmp/hc.json

Exit: 0 pass (warnings allowed), 1 any FAIL, 2 usage error or --data-dir missing.
"""
from __future__ import annotations

import argparse
import csv
import errno
import io
import json
import math
import os
import sys
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

try:
    import fcntl
except ImportError:  # no advisory locks (Windows); the collectors' _csv_lock skips them too
    fcntl = None

TOOL = "check_history_contract"
SCHEMA = "macro2_history_contract_v1"

# Mirrors of CC agents/volmath.py — VOL_WINDOW, ATR_WINDOW, MAX_ANCHOR_AGE_DAYS. If CC changes
# one of them, change it here and in docs/HISTORY_CONTRACT.md.
VOL_WINDOW = 20
ATR_WINDOW = 14
MIN_BARS = VOL_WINDOW + 1           # 21 bars = 20 changes; covers ATR14's 15 bars too
MIN_ATR_BARS = ATR_WINDOW + 1
MAX_WINDOW_SPAN_DAYS = 45           # the most recent MIN_BARS bars must fit in this many days
STALE_DAYS = 5                      # volmath: stale when age_days > MAX_ANCHOR_AGE_DAYS (4)
LOCK_TIMEOUT_S = 10.0
BTC_FILE = "BTC_OHLC_1h_gmt8_updated.csv"
OHLC_KEYS = (("o", "open"), ("h", "high"), ("l", "low"), ("c", "close"))

# (CC symbol, file, kind, OHLC column prefix / close column), in CC's UNIVERSE order.
# kind: ohlc = date + <prefix>_open/high/low/close; close = date + one value column;
# btc = hourly GMT+8 bars (timestamp, open, high, low, close) that the reader rolls up to UTC days.
SERIES = (
    ("ES", "es_futures_ohlcv.csv", "ohlc", "es"),
    ("RTY", "rty_futures_ohlcv.csv", "ohlc", "rty"),
    ("GC", "gold_ohlcv.csv", "ohlc", "gold"),
    ("SI", "silver_ohlcv.csv", "ohlc", "silver"),
    ("HG", "copper_ohlcv.csv", "ohlc", "copper"),
    ("CL", "crude_oil_ohlcv.csv", "ohlc", "crude_oil"),
    ("BZ", "brent_crude_ohlcv.csv", "ohlc", "brent"),
    ("BTC", BTC_FILE, "btc", None),
    ("VIX", "vix_move.csv", "close", "vix"),
    ("DXY", "dxy.csv", "close", "dxy"),
    ("USDJPY", "jpy.csv", "close", "jpy_rate"),
    ("UST10Y_YIELD", "10y_treasury_yield.csv", "close", "10y_yield"),
)


class LockTimeout(Exception):
    pass


def required_columns(kind: str, col: str | None) -> list[str]:
    if kind == "ohlc":
        return ["date"] + [f"{col}_{n}" for _, n in OHLC_KEYS]
    if kind == "close":
        return ["date", col]
    return ["timestamp", "open", "high", "low", "close"]


# ── reading ────────────────────────────────────────────────────────────────────────────
def read_text(path: Path, timeout: float = LOCK_TIMEOUT_S) -> tuple[str, str]:
    """Return (text, lock_mode). lock_mode: shared | none | unavailable.

    The collectors hold LOCK_EX on .<file>.lock for the whole read-modify-write. Take LOCK_SH
    on it, but only if it exists: the lock file is opened read-only and never created. The
    write itself is an atomic rename, so an unlocked read is still a whole file — the lock only
    keeps us from reading the version a writer is about to replace."""
    lock = path.parent / f".{path.name}.lock"
    fd = None
    mode = "none"
    if fcntl is not None and lock.exists():
        try:
            fd = os.open(lock, os.O_RDONLY)
        except FileNotFoundError:
            fd = None
        except OSError:
            mode = "unavailable"
    try:
        if fd is not None:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    mode = "shared"
                    break
                except OSError as e:
                    if e.errno not in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
                        raise
                    if time.monotonic() >= deadline:
                        raise LockTimeout(f"{lock.name} held for more than {timeout:g}s") from None
                    time.sleep(0.05)
        with open(path, "rb") as f:
            data = f.read()
    finally:
        if fd is not None:
            os.close(fd)  # closing the descriptor releases the flock
    return data.decode("utf-8"), mode


def _d(s: str) -> date | None:
    """The reader's date rule (volmath._d): the first 10 characters as YYYY-MM-DD."""
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _btc_ts(s) -> datetime | None:
    """The reader's BTC rule: the first 19 characters as 'YYYY-MM-DD HH:MM:SS' (GMT+8)."""
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def reader_bars(text: str, kind: str, col: str | None) -> list:
    """[(date, {o,h,l,c})] exactly as CC volmath.PriceStore.series() builds them from text.

    ohlc:  date from `date`, else `timestamp`; the LAST raw row per date wins, and only then is
           the date dropped if one of its four prices does not parse — so a blank close on a
           date's last row hides that date even when an earlier row was complete. A literal
           'nan' / 'inf' parses and is kept (and would poison sigma / ATR).
    close: rows with a blank / unparseable / NaN value are skipped first; the last remaining
           row per date wins; the bar is padded o = h = l = c.
    btc:   hourly GMT+8 rows shifted to UTC days: first open, max high, min low, last close,
           in file order."""
    rows = csv.DictReader(io.StringIO(text, newline=""))
    if kind == "btc":
        days: dict = {}
        for r in rows:
            try:
                ts = datetime.strptime(r["timestamp"][:19], "%Y-%m-%d %H:%M:%S") - timedelta(hours=8)
                o, h, l, c = (float(r[k]) for k in ("open", "high", "low", "close"))
            except Exception:
                continue
            d = ts.date()
            if d not in days:
                days[d] = {"o": o, "h": h, "l": l, "c": c}
            else:
                days[d]["h"] = max(days[d]["h"], h)
                days[d]["l"] = min(days[d]["l"], l)
                days[d]["c"] = c
        return sorted(days.items())
    out: dict = {}
    for r in rows:
        d = _d(r.get("date") or r.get("timestamp") or "")
        if d is None:
            continue
        if kind == "close":
            try:
                v = float(r[col])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isnan(v):
                continue
            out[d] = {"o": v, "h": v, "l": v, "c": v}
        else:
            out[d] = r
    if kind == "close":
        return sorted(out.items())
    bars = []
    for d, r in sorted(out.items()):
        try:
            bars.append((d, {k: float(r[f"{col}_{n}"]) for k, n in OHLC_KEYS}))
        except (KeyError, TypeError, ValueError):
            continue
    return bars


def _whole_hour(ts: str) -> bool:
    """True for a daily-bar timestamp ('YYYY-MM-DD' or hh:00:00), False for an intraday
    snapshot (IBKR writes jpy.csv every 5 min). Same split as append_to_csv(replace_daily_dates)."""
    try:
        t = datetime.fromisoformat(ts.strip())
    except ValueError:
        return True
    return t.minute == 0 and t.second == 0 and t.microsecond == 0


# ── the checks ─────────────────────────────────────────────────────────────────────────
def scan_rows(text: str, kind: str) -> dict:
    """One pass over the raw rows: key cells, field counts, ordering, duplicate daily bars."""
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = reader.fieldnames or []
    bad_keys, ragged = [], []
    decreasing = None
    prev = None
    rows = 0
    bar_rows: dict = {}     # date -> daily-bar rows on it (duplicates are a WARN)
    all_rows: dict = {}     # date -> rows on it, snapshots included (info only)
    last_key_blank = False
    for r in reader:
        rows += 1
        line = reader.line_num
        if None in r or any(v is None for v in r.values()):
            ragged.append(line)
        if kind == "btc":
            ts = r.get("timestamp")
            key = _btc_ts(ts or "")
            last_key_blank = key is None
            if key is None:
                bad_keys.append((line, "timestamp", ts))
                continue
            order_key, day, daily_bar = key, key, True     # BTC: duplicates = repeated hours
        else:
            bad = [c for c in ("date", "timestamp") if c in header and _d(r.get(c) or "") is None]
            bad_keys.extend((line, c, r.get(c)) for c in bad)
            last_key_blank = bool(bad)
            day = _d(r.get("date") or r.get("timestamp") or "")
            if day is None:
                continue
            order_key = day
            daily_bar = _whole_hour(r.get("timestamp") or "") if "timestamp" in header else True
        if prev is not None and order_key < prev and decreasing is None:
            decreasing = (line, prev, order_key)
        prev = order_key if prev is None else max(prev, order_key)
        all_rows[day] = all_rows.get(day, 0) + 1
        if daily_bar:
            bar_rows[day] = bar_rows.get(day, 0) + 1
    return {"header": header, "rows": rows, "bad_keys": bad_keys, "ragged": ragged,
            "decreasing": decreasing, "last_key_blank": last_key_blank,
            "dup_bar_dates": sorted(d for d, n in bar_rows.items() if n > 1),
            "multi_row_dates": sum(1 for n in all_rows.values() if n > 1)}


def _trailing_line(text: str) -> tuple[str | None, bool]:
    """(last physical line without its newline, file ends with a newline)."""
    if not text:
        return None, True
    ends_nl = text.endswith("\n")
    body = text[:-1] if ends_nl else text
    return body.rsplit("\n", 1)[-1].rstrip("\r"), ends_nl


def _fmt(v) -> str:
    return "<blank>" if v in (None, "") else repr(v)[:40]


def check_series(symbol: str, fname: str, kind: str, col: str | None, path: Path, as_of: date,
                 strict_fresh: bool = False, lock_timeout: float = LOCK_TIMEOUT_S) -> dict:
    res = {"series": symbol, "file": fname, "path": str(path), "kind": kind,
           "required_columns": required_columns(kind, col), "status": "PASS", "lock": None,
           "rows": None, "bars_total": None, "bars": None, "bars_after_as_of": None,
           "first_date": None, "anchor_date": None, "age_days": None, "window_span_days": None,
           "multi_row_dates": None, "fails": [], "warnings": []}

    def fail(code, msg):
        res["fails"].append({"code": code, "message": msg})

    def warn(code, msg):
        res["warnings"].append({"code": code, "message": msg})

    def done():
        res["status"] = "FAIL" if res["fails"] else ("WARN" if res["warnings"] else "PASS")
        return res

    if not path.is_file():
        fail("missing_file", f"{path} does not exist")
        return done()
    try:
        text, res["lock"] = read_text(path, lock_timeout)
    except LockTimeout as e:
        fail("lock_timeout", f"could not take a shared lock: {e}")
        return done()
    except (OSError, UnicodeDecodeError) as e:
        fail("unreadable", f"{type(e).__name__}: {e}"[:200])
        return done()
    if res["lock"] == "unavailable":
        warn("lock_unavailable", f".{fname}.lock exists but cannot be opened; read without the lock")

    scan = scan_rows(text, kind)
    res["rows"] = scan["rows"]
    res["multi_row_dates"] = scan["multi_row_dates"]
    missing = [c for c in res["required_columns"] if c not in scan["header"]]
    if missing:
        fail("missing_columns", f"missing column(s) {', '.join(missing)}"
             + ("" if scan["header"] else " (empty file, no header)"))
        return done()

    if scan["bad_keys"]:
        line, c, v = scan["bad_keys"][0]
        n = len({ln for ln, _, _ in scan["bad_keys"]})
        fail("unparseable_date", f"{n} row(s) with a blank or unparseable date/timestamp; first at line {line} "
             f"({c} = {_fmt(v)})")
    last, ends_nl = _trailing_line(text)
    if scan["rows"] and (last is None or last.strip(" \t\",") == "" or scan["last_key_blank"]):
        what = "is empty" if last is None or last.strip(" \t\",") == "" else "has a blank or unparseable date"
        fail("blank_trailing_row", f"the last line {what}: {_fmt(last)}")
    if scan["decreasing"]:
        line, prev, cur = scan["decreasing"]
        fail("decreasing_dates", f"line {line} is dated {cur} after a row dated {prev}")
    if scan["ragged"]:
        warn("ragged_rows", f"{len(scan['ragged'])} row(s) whose field count differs from the header; "
             f"first at line {scan['ragged'][0]}")
    if text and not ends_nl:
        warn("no_final_newline", "the file does not end with a newline (a torn write?)")
    if scan["dup_bar_dates"]:
        dd = scan["dup_bar_dates"]
        what = "hourly timestamp(s) appear more than once" if kind == "btc" else \
            "date(s) carry more than one daily bar (the reader keeps the last)"
        warn("duplicate_dates", f"{len(dd)} {what}; latest {dd[-1]}")

    bars_all = reader_bars(text, kind, col)
    bars = [b for b in bars_all if b[0] < as_of]
    res.update(bars_total=len(bars_all), bars=len(bars), bars_after_as_of=len(bars_all) - len(bars),
               first_date=bars[0][0].isoformat() if bars else None,
               anchor_date=bars[-1][0].isoformat() if bars else None,
               age_days=(as_of - bars[-1][0]).days if bars else None)
    if len(bars) < MIN_BARS:
        extra = f"; ATR14 needs {MIN_ATR_BARS}" if len(bars) < MIN_ATR_BARS else ""
        fail("insufficient_history", f"{len(bars)} valid bar(s) before {as_of}, need {MIN_BARS} "
             f"({VOL_WINDOW} changes for sigma_1d{extra})")
    else:
        window = bars[-MIN_BARS:]
        span = (window[-1][0] - window[0][0]).days
        res["window_span_days"] = span
        if span > MAX_WINDOW_SPAN_DAYS:
            fail("sparse_window", f"the last {MIN_BARS} bars span {span} days "
                 f"({window[0][0]} .. {window[-1][0]}), limit {MAX_WINDOW_SPAN_DAYS}")
        bad = [d for d, b in window if not all(math.isfinite(v) for v in b.values())]
        if bad:
            fail("nonfinite_value", f"{len(bad)} bar(s) in the last {MIN_BARS} carry NaN/inf; first {bad[0]}")
        if kind != "close":
            incon = [d for d, b in window if all(math.isfinite(v) for v in b.values())
                     and (b["h"] < max(b["o"], b["c"]) - 1e-9 * abs(b["h"])
                          or b["l"] > min(b["o"], b["c"]) + 1e-9 * abs(b["l"]))]
            if incon:
                warn("ohlc_inconsistent", f"{len(incon)} bar(s) in the last {MIN_BARS} with high < max(open, close) "
                     f"or low > min(open, close); latest {incon[-1]}")
    if bars and res["age_days"] >= STALE_DAYS:
        msg = f"last bar before {as_of} is {bars[-1][0]}, {res['age_days']} days old (limit {STALE_DAYS - 1})"
        (fail if strict_fresh else warn)("stale", msg)
    return done()


def run_checks(data_dir: Path, as_of: date, btc_path: Path | None = None, strict_fresh: bool = False,
               lock_timeout: float = LOCK_TIMEOUT_S) -> dict:
    results = []
    for symbol, fname, kind, col in SERIES:
        if kind == "btc":
            if btc_path is None:
                results.append({"series": symbol, "file": fname, "path": None, "kind": kind, "status": "SKIP",
                                "fails": [], "warnings": [], "note": "not checked (pass --btc PATH)"})
                continue
            path = btc_path
        else:
            path = data_dir / fname
        results.append(check_series(symbol, fname, kind, col, path, as_of, strict_fresh, lock_timeout))
    checked = [r for r in results if r["status"] != "SKIP"]
    failed = [r for r in checked if r["status"] == "FAIL"]
    return {"schema": SCHEMA, "contract": "docs/HISTORY_CONTRACT.md",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data_dir": str(data_dir), "btc_path": str(btc_path) if btc_path else None,
            "as_of": as_of.isoformat(), "strict_fresh": strict_fresh,
            "limits": {"min_bars": MIN_BARS, "min_atr_bars": MIN_ATR_BARS,
                       "max_window_span_days": MAX_WINDOW_SPAN_DAYS, "stale_days": STALE_DAYS,
                       "lock_timeout_s": lock_timeout},
            "status": "FAIL" if failed else "PASS",
            "summary": {"checked": len(checked), "failed": len(failed),
                        "warned": sum(1 for r in checked if r["status"] == "WARN"),
                        "skipped": len(results) - len(checked)},
            "series": results}


# ── output ─────────────────────────────────────────────────────────────────────────────
def render_table(report: dict) -> str:
    cols = ("series", "file", "rows", "bars", "anchor", "age", "span21", "lock", "status", "codes")
    lines = []
    for r in report["series"]:
        codes = [x["code"] for x in r["fails"]] + [f"w:{x['code']}" for x in r["warnings"]]
        if r["status"] == "SKIP":
            codes = [r.get("note", "")]
        lines.append((r["series"], r["file"], r.get("rows"), r.get("bars"), r.get("anchor_date"),
                      r.get("age_days"), r.get("window_span_days"), r.get("lock"), r["status"], " ".join(codes)))
    rows = [cols] + [tuple("-" if v is None else str(v) for v in ln) for ln in lines]
    widths = [max(len(row[i]) for row in rows) for i in range(len(cols) - 1)]
    out = [f"history contract: data-dir {report['data_dir']}, as-of {report['as_of']} "
           f"(bars = valid bars before as-of; need {MIN_BARS}, last {MIN_BARS} within "
           f"{MAX_WINDOW_SPAN_DAYS} days)"]
    for row in rows:
        out.append("  ".join(v.ljust(w) for v, w in zip(row, widths)) + "  " + row[-1])
    return "\n".join(line.rstrip() for line in out)


def write_json_atomic(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _as_of(s: str) -> date:
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"--as-of must be YYYYMMDD, got {s!r}") from None


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the CC pipeline's minimum-history contract "
                                             "(docs/HISTORY_CONTRACT.md).")
    ap.add_argument("--data-dir", required=True, type=Path, help="directory holding the macro_2 CSVs")
    ap.add_argument("--as-of", type=_as_of, default=datetime.now(timezone.utc).date(),
                    help="pipeline date YYYYMMDD (default: today UTC); bars on or after it are ignored")
    ap.add_argument("--btc", type=Path, default=None, help="BTC hourly GMT+8 file (skipped when omitted)")
    ap.add_argument("--json", type=Path, default=None, help="also write the machine-readable report here")
    ap.add_argument("--strict-fresh", action="store_true", help="a stale series is a FAIL, not a WARN")
    args = ap.parse_args(argv)

    if not args.data_dir.is_dir():
        print(f"[{TOOL}] ERROR: --data-dir {args.data_dir} is not a directory", file=sys.stderr)
        return 2
    report = run_checks(args.data_dir, args.as_of, args.btc, args.strict_fresh)
    print(render_table(report))
    sys.stdout.flush()      # keep the table ahead of the stderr lines when both are captured
    for r in report["series"]:
        for x in r["fails"]:
            print(f"[{TOOL}] FAIL {r['file']} ({r['series']}): {x['code']}: {x['message']}", file=sys.stderr)
        for x in r["warnings"]:
            print(f"[{TOOL}] WARNING: {r['file']} ({r['series']}): {x['code']}: {x['message']}", file=sys.stderr)
    if args.json:
        try:
            write_json_atomic(args.json, report)
        except OSError as e:
            print(f"[{TOOL}] ERROR: cannot write --json {args.json}: {e}", file=sys.stderr)
            return 2
    s = report["summary"]
    failed = [f"{r['file']}: {','.join(x['code'] for x in r['fails'])}" for r in report["series"] if r["fails"]]
    print(f"[{TOOL}] {report['status']}: {s['checked'] - s['failed']}/{s['checked']} series pass "
          f"({s['warned']} with warnings, {s['skipped']} skipped), as-of {report['as_of']}"
          + (f"; failing: {'; '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
