"""Tests for scripts/check_history_contract.py (docs/HISTORY_CONTRACT.md).

Stdlib unittest, synthetic CSVs in a temp dir; nothing under historical_data/ is touched.

  python3 -m unittest discover -s tests -p 'test_check_history_contract.py' -v

The parity tests import CC's agents/volmath.py (the reader the contract protects) from
$CC_AGENTS_DIR, default ~/Github/CLI_OS/Agent_Orchestration/CC/agents, and skip when it is absent.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_history_contract.py"
_spec = importlib.util.spec_from_file_location("check_history_contract", SCRIPT)
chc = importlib.util.module_from_spec(_spec)
sys.modules["check_history_contract"] = chc
_spec.loader.exec_module(chc)

CC_AGENTS = Path(os.environ.get("CC_AGENTS_DIR",
                                Path.home() / "Github/CLI_OS/Agent_Orchestration/CC/agents"))
CC_FROZEN = CC_AGENTS.parent / "backfill" / "inputs" / "prices"   # the scorer's frozen copy
AS_OF = date(2026, 9, 17)
LAST = date(2026, 9, 16)          # the anchor the builder would use on AS_OF


def weekdays_ending(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def ohlc_for(i: int, base: float = 100.0) -> tuple[float, float, float, float]:
    o = base + 0.5 * i + math.sin(i)
    c = o + math.cos(1.7 * i)
    return o, max(o, c) + 1.0, min(o, c) - 1.0, c


def write(path: Path, header: str, rows: list[str], trailer: str = "\n") -> None:
    path.write_text(header + "\n" + "\n".join(rows) + (trailer if rows else ""))


def build_dir(root: Path, n: int = 40, end: date = LAST, locks: bool = True) -> Path:
    """The 11 macro_2 files in their real layouts, n weekday bars ending at `end`."""
    root.mkdir(parents=True, exist_ok=True)
    days = weekdays_ending(end, n)
    for sym, fname, kind, col in chc.SERIES:
        if kind == "ohlc":
            write(root / fname, f"timestamp,date,{col}_open,{col}_high,{col}_low,{col}_close,{col}_volume",
                  [f"{d},{d}," + ",".join(repr(v) for v in ohlc_for(i)) + ",1000" for i, d in enumerate(days)])
        elif fname == "vix_move.csv":
            write(root / fname, "timestamp,vix,move,vix_move_ratio,date",
                  [f"{d},{15 + math.sin(i)!r},80.0,0.2,{d}" for i, d in enumerate(days)])
        elif fname == "jpy.csv":     # yfinance bar at 23:00 the day before + IBKR 5-min snapshots
            rows = []
            for i, d in enumerate(days):
                rows.append(f"{d - timedelta(days=1)} 23:00:00,{d},{150 + math.sin(i)!r}")
                rows.append(f"{d} 10:05:58,{d},{150.2 + math.sin(i)!r}")
                rows.append(f"{d} 10:10:58,{d},{150.3 + math.sin(i)!r}")
            write(root / fname, "timestamp,date,jpy_rate", rows)
        elif kind == "close":
            write(root / fname, f"timestamp,date,{col}",
                  [f"{d} 04:00:00,{d},{100 + math.cos(i)!r}" for i, d in enumerate(days)])
        if locks and kind != "btc":
            (root / f".{fname}.lock").touch()
    return root


def build_btc(path: Path, n_days: int = 30, end: date = LAST) -> Path:
    """Hourly GMT+8 bars covering n_days UTC days ending at `end`."""
    start = datetime(end.year, end.month, end.day) - timedelta(days=n_days - 1) + timedelta(hours=8)
    rows = []
    for h in range(n_days * 24):
        o, hi, lo, c = ohlc_for(h, 60000.0)
        rows.append(f"{start + timedelta(hours=h):%Y-%m-%d %H:%M:%S},{o!r},{hi!r},{lo!r},{c!r},1.5")
    write(path, "timestamp,open,high,low,close,volume", rows)
    return path


def replace_lines(path: Path, fn) -> None:
    lines = path.read_text().split("\n")
    path.write_text("\n".join(fn(lines)))


def check(d: Path, fname: str, as_of: date = AS_OF, **kw) -> dict:
    sym, _, kind, col = next(s for s in chc.SERIES if s[1] == fname)
    return chc.check_series(sym, fname, kind, col, d / fname, as_of, **kw)


def codes(res: dict) -> tuple[list[str], list[str]]:
    return [x["code"] for x in res["fails"]], [x["code"] for x in res["warnings"]]


def run_main(*argv) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = chc.main([str(a) for a in argv])
    return rc, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.d = build_dir(self.tmp / "hd")

    def tearDown(self):
        self._tmp.cleanup()


class CleanData(Base):
    def test_clean_dir_passes_and_btc_is_skipped_without_flag(self):
        j = self.tmp / "out" / "report.json"
        rc, out, err = run_main("--data-dir", self.d, "--as-of", "20260917", "--json", j)
        self.assertEqual(rc, 0, out + err)
        rep = json.loads(j.read_text())
        self.assertEqual(rep["schema"], "macro2_history_contract_v1")
        self.assertEqual(rep["status"], "PASS")
        self.assertEqual([s["series"] for s in rep["series"]],
                         ["ES", "RTY", "GC", "SI", "HG", "CL", "BZ", "BTC", "VIX", "DXY", "USDJPY", "UST10Y_YIELD"])
        by = {s["series"]: s for s in rep["series"]}
        self.assertEqual(by["BTC"]["status"], "SKIP")
        for s in rep["series"]:
            if s["series"] != "BTC":
                self.assertEqual(s["status"], "PASS", s)
                self.assertEqual((s["bars"], s["anchor_date"], s["age_days"], s["lock"]), (40, "2026-09-16", 1, "shared"))
        self.assertIn("[check_history_contract] PASS: 11/11 series pass", out)
        self.assertEqual(err, "")

    def test_btc_checked_when_given(self):
        btc = build_btc(self.tmp / "btc.csv")
        rc, out, _ = run_main("--data-dir", self.d, "--as-of", "20260917", "--btc", btc)
        self.assertEqual(rc, 0, out)
        res = chc.check_series("BTC", chc.BTC_FILE, "btc", None, btc, AS_OF)
        self.assertEqual(res["status"], "PASS", res)
        # 720 GMT+8 hours starting at 08:00 = exactly 30 UTC days, the last one the anchor
        self.assertEqual((res["bars"], res["anchor_date"], res["lock"]), (30, "2026-09-16", "none"))

    def test_bars_on_or_after_as_of_are_ignored(self):
        f = self.d / "es_futures_ohlcv.csv"
        replace_lines(f, lambda ls: ls[:-1] + ["2026-09-17,2026-09-17,1,2,0.5,1.5,9", "2026-09-18,2026-09-18,1,2,0.5,1.5,9", ""])
        res = check(self.d, "es_futures_ohlcv.csv")
        self.assertEqual(res["status"], "PASS", res)
        self.assertEqual((res["bars"], res["bars_after_as_of"], res["anchor_date"]), (40, 2, "2026-09-16"))


class Failures(Base):
    def test_missing_file_and_columns(self):
        (self.d / "dxy.csv").unlink()
        self.assertEqual(codes(check(self.d, "dxy.csv"))[0], ["missing_file"])
        replace_lines(self.d / "gold_ohlcv.csv", lambda ls: [ls[0].replace("gold_low", "gold_lo")] + ls[1:])
        res = check(self.d, "gold_ohlcv.csv")
        self.assertEqual(codes(res)[0], ["missing_columns"])
        self.assertIn("gold_low", res["fails"][0]["message"])
        (self.d / "jpy.csv").write_text("")
        self.assertIn("empty file", check(self.d, "jpy.csv")["fails"][0]["message"])

    def test_history_boundary_21_bars(self):
        build_dir(self.d, n=21)
        res = check(self.d, "es_futures_ohlcv.csv")
        self.assertEqual((res["status"], res["bars"]), ("PASS", 21), res)
        build_dir(self.d, n=20)
        res = check(self.d, "es_futures_ohlcv.csv")
        self.assertEqual(codes(res)[0], ["insufficient_history"])
        self.assertIn("20 valid bar(s) before 2026-09-17, need 21", res["fails"][0]["message"])
        build_dir(self.d, n=14)
        self.assertIn("ATR14 needs 15", check(self.d, "dxy.csv")["fails"][0]["message"])

    def test_blank_values_do_not_count_as_bars(self):
        # vix_move.csv carries MOVE-only rows with a blank vix: the reader skips them
        build_dir(self.d, n=25)
        replace_lines(self.d / "vix_move.csv",
                      lambda ls: [ls[0]] + [(",".join(l.split(",")[:1] + [""] + l.split(",")[2:]) if 1 <= i <= 5 else l)
                                            for i, l in enumerate(ls[1:], 1)])
        res = check(self.d, "vix_move.csv")
        self.assertEqual((res["bars"], res["status"]), (20, "FAIL"), res)

    def test_unparseable_date_mid_file(self):
        def insert(ls):
            d = ls[9].split(",")[1]          # same date as the row before: no ordering failure
            return ls[:10] + [f",{d},100.5", f"2026-0,{d},100.5", ",,100.5"] + ls[10:]
        replace_lines(self.d / "dxy.csv", insert)
        res = check(self.d, "dxy.csv")
        self.assertEqual(codes(res)[0], ["unparseable_date"])
        self.assertIn("3 row(s)", res["fails"][0]["message"])     # a row with both blank counts once
        self.assertIn("line 11", res["fails"][0]["message"])

    def test_blank_timestamp_trailing_row_the_2026_09_01_incident_shape(self):
        # a fragment written back with a blank timestamp, re-sorted to the end of the file
        replace_lines(self.d / "gold_ohlcv.csv", lambda ls: ls[:-1] + [",2026-09-01,4357.6,4357.6,4357.6,4357.6,", ""])
        f, _ = codes(check(self.d, "gold_ohlcv.csv"))
        self.assertEqual(f, ["unparseable_date", "blank_trailing_row", "decreasing_dates"])

    def test_blank_trailing_line(self):
        for tail in ("\n\n", "\n,,,,,,\n", "\n   \n"):
            with self.subTest(tail=tail):
                build_dir(self.d)
                f = self.d / "rty_futures_ohlcv.csv"
                f.write_text(f.read_text().rstrip("\n") + tail)
                self.assertIn("blank_trailing_row", codes(check(self.d, "rty_futures_ohlcv.csv"))[0])

    def test_decreasing_dates(self):
        def swap(ls):
            ls[20], ls[21] = ls[21], ls[20]
            return ls
        replace_lines(self.d / "10y_treasury_yield.csv", swap)
        res = check(self.d, "10y_treasury_yield.csv")
        self.assertEqual(codes(res)[0], ["decreasing_dates"])
        self.assertIn("line 22", res["fails"][0]["message"])

    def test_sparse_window(self):
        # 21 bars, but the middle of the window has a 60-day hole
        days = weekdays_ending(LAST, 10)
        early = weekdays_ending(days[0] - timedelta(days=60), 11)
        rows = [f"{d},{d}," + ",".join(repr(v) for v in ohlc_for(i)) + ",1" for i, d in enumerate(early + days)]
        write(self.d / "copper_ohlcv.csv", "timestamp,date,copper_open,copper_high,copper_low,copper_close,copper_volume", rows)
        res = check(self.d, "copper_ohlcv.csv")
        self.assertEqual(codes(res)[0], ["sparse_window"])
        self.assertIn("limit 45", res["fails"][0]["message"])

    def test_nonfinite_price_in_window(self):
        replace_lines(self.d / "silver_ohlcv.csv",
                      lambda ls: ls[:-3] + [",".join(ls[-3].split(",")[:5] + ["nan", "1"])] + ls[-2:])
        self.assertEqual(codes(check(self.d, "silver_ohlcv.csv"))[0], ["nonfinite_value"])

    def test_blank_close_on_a_dates_last_row_hides_the_date(self):
        # reader rule: last raw row per date wins, THEN unparseable prices drop the date
        f = self.d / "brent_crude_ohlcv.csv"
        replace_lines(f, lambda ls: ls[:-1] + ["2026-09-16 12:05:00,2026-09-16,1,2,0.5,,1", ""])
        res = check(self.d, "brent_crude_ohlcv.csv")
        self.assertEqual((res["bars"], res["anchor_date"], res["status"]), (39, "2026-09-15", "PASS"), res)

    def test_stale_warns_and_strict_fresh_fails(self):
        self.assertNotIn("stale", codes(check(self.d, "dxy.csv", as_of=date(2026, 9, 20)))[1])   # age 4
        res = check(self.d, "dxy.csv", as_of=date(2026, 9, 21))                                  # age 5
        self.assertEqual(codes(res), ([], ["stale"]))
        self.assertEqual(res["status"], "WARN")
        self.assertEqual(codes(check(self.d, "dxy.csv", as_of=date(2026, 9, 21), strict_fresh=True))[0], ["stale"])
        rc, _, err = run_main("--data-dir", self.d, "--as-of", "20260921", "--strict-fresh")
        self.assertEqual(rc, 1)
        self.assertIn("[check_history_contract] FAIL dxy.csv (DXY): stale:", err)


class Warnings(Base):
    def test_duplicate_daily_bars_warn_but_snapshots_do_not(self):
        replace_lines(self.d / "dxy.csv", lambda ls: ls[:-1] + [ls[-2].replace("04:00:00", "05:00:00"), ""])
        res = check(self.d, "dxy.csv")
        self.assertEqual(codes(res), ([], ["duplicate_dates"]))
        self.assertIn("latest 2026-09-16", res["warnings"][0]["message"])
        jpy = check(self.d, "jpy.csv")      # three rows per date: one bar + two snapshots
        self.assertEqual((jpy["status"], jpy["multi_row_dates"]), ("PASS", 40), jpy)

    def test_ohlc_inconsistency_in_window(self):
        # close above high: the yfinance Sunday-bar shape seen in copper/crude 2026-09-06
        replace_lines(self.d / "crude_oil_ohlcv.csv",
                      lambda ls: ls[:-3] + [",".join(ls[-3].split(",")[:2] + ["92.26", "92.57", "91.58", "93.0", "1"])] + ls[-2:])
        self.assertEqual(codes(check(self.d, "crude_oil_ohlcv.csv")), ([], ["ohlc_inconsistent"]))

    def test_ragged_row_and_missing_final_newline(self):
        replace_lines(self.d / "dxy.csv", lambda ls: ls[:5] + [ls[5] + ",extra"] + ls[6:-1])
        res = check(self.d, "dxy.csv")
        self.assertEqual(codes(res), ([], ["ragged_rows", "no_final_newline"]))
        rc, _, err = run_main("--data-dir", self.d, "--as-of", "20260917")
        self.assertEqual(rc, 0)
        self.assertIn("[check_history_contract] WARNING: dxy.csv (DXY): ragged_rows:", err)


class Locking(Base):
    def test_shared_lock_only_when_present_and_never_created(self):
        bare = build_dir(self.tmp / "bare", locks=False)
        before = sorted(p.name for p in bare.iterdir())
        rc, out, _ = run_main("--data-dir", bare, "--as-of", "20260917")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(p.name for p in bare.iterdir()), before)
        self.assertEqual(check(bare, "dxy.csv")["lock"], "none")
        self.assertEqual(check(self.d, "dxy.csv")["lock"], "shared")

    @unittest.skipIf(chc.fcntl is None, "no fcntl on this platform")
    def test_lock_timeout_while_a_writer_holds_it(self):
        lock = self.d / ".gold_ohlcv.csv.lock"
        holder = subprocess.Popen(
            [sys.executable, "-c",
             "import fcntl,sys,time; f=open(sys.argv[1],'a'); fcntl.flock(f,fcntl.LOCK_EX); "
             "print('held',flush=True); time.sleep(30)", str(lock)],
            stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(holder.stdout.readline().strip(), "held")
            t0 = time.monotonic()
            res = check(self.d, "gold_ohlcv.csv", lock_timeout=0.3)
            self.assertEqual(codes(res)[0], ["lock_timeout"])
            self.assertLess(time.monotonic() - t0, 5)
        finally:
            holder.kill()
            holder.wait()
            holder.stdout.close()
        self.assertEqual(check(self.d, "gold_ohlcv.csv", lock_timeout=0.3)["status"], "PASS")


class Cli(Base):
    def run_script(self, *argv):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, argv)], capture_output=True, text=True)

    def test_exit_codes(self):
        self.assertEqual(self.run_script("--data-dir", self.d, "--as-of", "20260917").returncode, 0)
        (self.d / "vix_move.csv").unlink()
        p = self.run_script("--data-dir", self.d, "--as-of", "20260917")
        self.assertEqual(p.returncode, 1)
        self.assertIn("[check_history_contract] FAIL vix_move.csv (VIX): missing_file:", p.stderr)
        self.assertIn("[check_history_contract] FAIL: 10/11 series pass", p.stdout)
        self.assertIn("failing: vix_move.csv: missing_file", p.stdout)
        p = self.run_script("--data-dir", self.tmp / "nope")
        self.assertEqual(p.returncode, 2)
        self.assertIn("is not a directory", p.stderr)
        self.assertEqual(self.run_script("--data-dir", self.d, "--as-of", "2026-09-17").returncode, 2)
        self.assertEqual(self.run_script("--as-of", "20260917").returncode, 2)

    def test_stdlib_only_no_cc_or_pandas_import(self):
        code = ("import importlib.util,sys; s=importlib.util.spec_from_file_location('m',sys.argv[1]); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
                "print(sorted(k for k in ('pandas','numpy','volmath','cc_view','extract_historical_data') if k in sys.modules))")
        p = subprocess.run([sys.executable, "-c", code, str(SCRIPT)], capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), "[]", p.stderr)


def _same_bars(a, b) -> bool:
    if len(a) != len(b):
        return False
    for (da, ba), (db, bb) in zip(a, b):
        if da != db or ba.keys() != bb.keys():
            return False
        if any(not (ba[k] == bb[k] or (math.isnan(ba[k]) and math.isnan(bb[k]))) for k in ba):
            return False
    return True


@unittest.skipUnless((CC_AGENTS / "volmath.py").is_file(), f"CC volmath.py not found under {CC_AGENTS}")
class ReaderParity(Base):
    """The guard's bar count must be the reader's, or it guards the wrong thing."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(CC_AGENTS))
        try:
            import volmath  # noqa: E402
        finally:
            sys.path.pop(0)
        cls.vm = volmath

    def assert_parity(self, data_dir: Path, btc: Path, as_of: date):
        store = self.vm.PriceStore(data_dir, btc)
        rep = chc.run_checks(data_dir, as_of, btc)
        for (sym, fname, kind, col), res in zip(chc.SERIES, rep["series"]):
            with self.subTest(series=sym):
                path = btc if kind == "btc" else data_dir / fname
                text, _ = chc.read_text(path)
                self.assertTrue(_same_bars(chc.reader_bars(text, kind, col), store.series(sym)))
                info = self.vm.anchor_info(sym, as_of, store)
                self.assertEqual(res["bars"], info["bars_to_anchor"])
                self.assertEqual(res["anchor_date"], info["anchor_date"])
                if res["status"] in ("PASS", "WARN"):
                    self.assertTrue(info["available"], info)
        return rep

    def test_series_table_and_limits_mirror_volmath(self):
        vm = self.vm
        self.assertEqual([s[0] for s in chc.SERIES], list(vm.UNIVERSE))
        for sym, fname, kind, col in chc.SERIES:
            want = {"ohlc": vm.OHLC_SOURCES, "close": vm.CLOSE_SOURCES}.get(kind, {sym: (vm.BTC_FILE, None)})[sym]
            self.assertEqual((fname, col), want, sym)
        self.assertEqual((chc.VOL_WINDOW, chc.ATR_WINDOW, chc.STALE_DAYS),
                         (vm.VOL_WINDOW, vm.ATR_WINDOW, vm.MAX_ANCHOR_AGE_DAYS + 1))

    def test_parity_on_messy_synthetic_data(self):
        btc = build_btc(self.tmp / "btc.csv")
        # duplicate bars, a blank-close last row, MOVE-only vix rows, a NaN close, jpy snapshots
        replace_lines(self.d / "dxy.csv", lambda ls: ls[:-1] + ["2026-09-16 05:00:00,2026-09-16,101.5", ""])
        replace_lines(self.d / "brent_crude_ohlcv.csv", lambda ls: ls[:-1] + ["2026-09-16 12:00:00,2026-09-16,1,2,0.5,,1", ""])
        replace_lines(self.d / "vix_move.csv", lambda ls: ls[:3] + ["2026-07-01,,81.0,,2026-07-01"] + ls[3:])
        replace_lines(self.d / "silver_ohlcv.csv", lambda ls: ls[:3] + [",".join(ls[3].split(",")[:5] + ["nan", "1"])] + ls[4:])
        self.assert_parity(self.d, btc, AS_OF)

    @unittest.skipUnless((CC_FROZEN / "es_futures_ohlcv.csv").is_file(), "CC backfill/inputs/prices not present")
    def test_parity_on_the_frozen_scoring_copy(self):
        rep = self.assert_parity(CC_FROZEN, CC_FROZEN / chc.BTC_FILE, date(2026, 9, 17))
        self.assertEqual(rep["status"], "PASS", [s["fails"] for s in rep["series"] if s["fails"]])


if __name__ == "__main__":
    unittest.main()
