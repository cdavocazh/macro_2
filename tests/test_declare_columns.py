"""Tests for extract_historical_data.declare_columns (writer-declared column contracts) and
the writers wired to it (IBKR daemon, sp500_fundamentals).

Stdlib unittest; every sidecar is written to a temp dir (OUTPUT_DIR is patched), nothing under
historical_data/ is touched and no network or IB connection is used.

  python3 -m unittest discover -s tests -p 'test_declare_columns.py' -v

The round-trip test reads the sidecars back with CC's feed scanner (backfill/data_guard.py) from
$CC_BACKFILL_DIR, default ~/Github/CLI_OS/Agent_Orchestration/CC/backfill, and skips when absent.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import extract_historical_data as ehd  # noqa: E402
import ibkr_fast_extract as ibx  # noqa: E402
from data_extractors.ibkr_streaming import INSTRUMENTS  # noqa: E402

CC_BACKFILL = Path(os.environ.get("CC_BACKFILL_DIR",
                                  Path.home() / "Github/CLI_OS/Agent_Orchestration/CC/backfill"))
ISO_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class _TmpOutput(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        patcher = mock.patch.object(ehd, "OUTPUT_DIR", self.tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def sidecar(self, stem):
        return json.loads((self.dir / f".{stem}.columns.json").read_text())

    def quiet(self, fn, *a, **kw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            fn(*a, **kw)
        return out.getvalue()


class DeclareColumnsTest(_TmpOutput):
    def test_writes_the_documented_layout(self):
        ehd.declare_columns("foo.csv", active=["a", "b"],
                            retired={"c": {"since": "2026-03-19", "reason": " registry edit "}},
                            unavailable={"d": "no source"}, writer="unit")
        got = self.sidecar("foo")
        self.assertEqual(list(got), ["file", "writer", "declared_at", "active", "retired", "unavailable"])
        self.assertEqual(got["file"], "foo.csv")
        self.assertEqual(got["writer"], "unit")
        self.assertEqual(got["active"], ["a", "b"])
        self.assertEqual(got["retired"], {"c": {"since": "2026-03-19", "reason": "registry edit"}})
        self.assertEqual(got["unavailable"], {"d": "no source"})
        self.assertRegex(got["declared_at"], ISO_Z)
        stamped = datetime.strptime(got["declared_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        self.assertLess(abs((datetime.now(timezone.utc) - stamped).total_seconds()), 120)

    def test_hidden_from_csv_globs_and_atomic(self):
        ehd.declare_columns("foo.csv", active=["a"])
        self.assertEqual(list(self.dir.glob("*.csv")), [])
        self.assertEqual([p.name for p in self.dir.iterdir()], [".foo.columns.json"])   # no temp left behind
        self.assertEqual(stat.S_IMODE((self.dir / ".foo.columns.json").stat().st_mode), 0o644)

    def test_subdirectory_file(self):
        (self.dir / "equity_financials" / "sec").mkdir(parents=True)
        ehd.declare_columns("equity_financials/sec/AAPL_quarterly.csv", active=["revenue"])
        got = json.loads((self.dir / "equity_financials/sec/.AAPL_quarterly.columns.json").read_text())
        self.assertEqual(got["file"], "AAPL_quarterly.csv")

    def test_unchanged_contract_is_not_rewritten_within_the_hour(self):
        ehd.declare_columns("foo.csv", active=["a"], writer="w")
        path = self.dir / ".foo.columns.json"
        first = path.read_text()
        os.utime(path, (1, 1))
        ehd.declare_columns("foo.csv", active=["a"], writer="w")
        self.assertEqual(path.stat().st_mtime, 1, "rewritten although nothing changed")
        self.assertEqual(path.read_text(), first)

    def test_changed_contract_is_rewritten_at_once(self):
        ehd.declare_columns("foo.csv", active=["a"])
        ehd.declare_columns("foo.csv", active=["a"], unavailable={"b": "gone"})
        self.assertEqual(self.sidecar("foo")["unavailable"], {"b": "gone"})
        ehd.declare_columns("foo.csv", active=["a"], unavailable={"b": "gone"}, writer="other")
        self.assertEqual(self.sidecar("foo")["writer"], "other")

    def test_old_declaration_is_restamped(self):
        ehd.declare_columns("foo.csv", active=["a"])
        path = self.dir / ".foo.columns.json"
        old = self.sidecar("foo")
        old["declared_at"] = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        path.write_text(json.dumps(old))
        ehd.declare_columns("foo.csv", active=["a"])
        self.assertGreater(self.sidecar("foo")["declared_at"], old["declared_at"])

    def test_corrupt_sidecar_is_replaced(self):
        (self.dir / ".foo.columns.json").write_text("{not json")
        ehd.declare_columns("foo.csv", active=["a"])
        self.assertEqual(self.sidecar("foo")["active"], ["a"])

    def test_misuse_raises(self):
        future = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%d")
        cases = {
            "not a csv": dict(filename="foo.json", active=["a"]),
            "active is a string": dict(filename="f.csv", active="a"),
            "empty column name": dict(filename="f.csv", active=["a", " "]),
            "duplicate active": dict(filename="f.csv", active=["a", "a"]),
            "since not a date": dict(filename="f.csv", active=["a"], retired={"b": {"since": "2026-13-01", "reason": "x"}}),
            "since not zero-padded": dict(filename="f.csv", active=["a"], retired={"b": {"since": "2026-9-1", "reason": "x"}}),
            "since in the future": dict(filename="f.csv", active=["a"], retired={"b": {"since": future, "reason": "x"}}),
            "empty retired reason": dict(filename="f.csv", active=["a"], retired={"b": {"since": "2026-09-01", "reason": " "}}),
            "missing reason": dict(filename="f.csv", active=["a"], retired={"b": {"since": "2026-09-01"}}),
            "typo key": dict(filename="f.csv", active=["a"], retired={"b": {"since": "2026-09-01", "reason": "x", "note": 1}}),
            "retired not a dict": dict(filename="f.csv", active=["a"], retired=["b"]),
            "empty unavailable reason": dict(filename="f.csv", active=["a"], unavailable={"b": ""}),
            "active and retired": dict(filename="f.csv", active=["a"], retired={"a": {"since": "2026-09-01", "reason": "x"}}),
            "active and unavailable": dict(filename="f.csv", active=["a"], unavailable={"a": "x"}),
            "retired and unavailable": dict(filename="f.csv", active=[], retired={"b": {"since": "2026-09-01", "reason": "x"}},
                                            unavailable={"b": "x"}),
            "writer not a string": dict(filename="f.csv", active=["a"], writer=None),
        }
        for label, kw in cases.items():
            with self.subTest(label):
                with self.assertRaises((ValueError, TypeError)):
                    ehd.declare_columns(**kw)
        self.assertEqual(list(self.dir.iterdir()), [], "a rejected contract left a file behind")

    def test_io_error_is_logged_not_raised(self):
        with mock.patch.object(ehd, "OUTPUT_DIR", str(self.dir / "does-not-exist")):
            out = self.quiet(ehd.declare_columns, "foo.csv", active=["a"])
        self.assertIn("could not write", out)
        (self.dir / "ro").mkdir()
        os.chmod(self.dir / "ro", 0o500)
        self.addCleanup(os.chmod, self.dir / "ro", 0o700)
        if not os.access(self.dir / "ro", os.W_OK):          # root ignores the mode bits
            with mock.patch.object(ehd, "OUTPUT_DIR", str(self.dir / "ro")):
                out = self.quiet(ehd.declare_columns, "foo.csv", active=["a"])
            self.assertIn("could not write", out)


class IbkrContractTest(_TmpOutput):
    def test_summary_contract(self):
        contracts = {c["filename"]: c for c in ibx._column_contracts()}
        summary = contracts["ibkr_realtime_summary.csv"]
        columns = [s.csv_column for s in INSTRUMENTS.values()]
        self.assertEqual(summary["unavailable"], {"vix_ibkr": ibx.UNAVAILABLE_COLUMNS["vix_ibkr"]})
        self.assertIn("Error 354", summary["unavailable"]["vix_ibkr"])
        self.assertEqual(summary["active"], [c for c in columns if c != "vix_ibkr"])
        self.assertEqual(summary["retired"]["micro_2y_yield"]["since"], "2026-09-21")
        self.assertIn("us_2y_yield.csv", summary["retired"]["micro_2y_yield"]["reason"])
        self.assertNotIn("micro_2y_yield", columns)
        # The legacy natural_gas column was merged into natural_gas_futures (split_natural_gas,
        # 2026-09-21); a copy that still has it should surface as an orphan, not pass as retired.
        self.assertNotIn("natural_gas", summary["retired"])

    def test_every_per_instrument_file_is_declared(self):
        contracts = {c["filename"]: c for c in ibx._column_contracts()}
        for spec in INSTRUMENTS.values():
            if spec.csv_file:
                self.assertEqual(contracts[spec.csv_file]["active"], [spec.csv_column], spec.csv_file)

    def test_contracts_are_valid_and_written(self):
        self.quiet(ibx._declare_column_contracts)
        names = sorted(p.name for p in self.dir.iterdir())
        self.assertIn(".ibkr_realtime_summary.columns.json", names)
        self.assertEqual(len(names), 1 + sum(1 for s in INSTRUMENTS.values() if s.csv_file))
        self.assertEqual(self.sidecar("ibkr_realtime_summary")["retired"]["micro_2y_yield"]["since"], "2026-09-21")

    def test_restored_instrument_is_active_not_retired(self):
        with mock.patch.dict(ibx.RETIRED_COLUMNS, {"es_price": {"since": "2026-01-01", "reason": "x"}}):
            summary = ibx._column_contracts()[0]
        self.assertIn("es_price", summary["active"])
        self.assertNotIn("es_price", summary["retired"])

    def test_declaration_failure_never_escapes(self):
        with mock.patch.object(ehd, "declare_columns", side_effect=ValueError("boom")):
            with self.assertLogs("ibkr_extract", level="WARNING"):
                ibx._declare_column_contracts()

    def test_summary_row_matches_contract(self):
        """Run the real 5-minute writer against a fake snapshot; every column it writes is declared."""
        now = datetime.now(timezone.utc).isoformat()
        snapshot = {sym: {"last": 1.0 + i, "last_price_time": now} for i, sym in enumerate(INSTRUMENTS)}
        snapshot["VIX"] = {"last": None}
        service = mock.Mock(get_snapshot=mock.Mock(return_value=snapshot))
        written = {}
        with mock.patch.object(ehd, "append_to_csv", side_effect=lambda f, df, **kw: written.setdefault(f, df)):
            self.quiet(ibx._write_csv_summary, service)
        for fname, df in written.items():
            con = self.sidecar(fname[:-4])
            declared = set(con["active"]) | set(con["retired"]) | set(con["unavailable"]) | {"timestamp", "date"}
            self.assertLessEqual(set(df.columns), declared, fname)


class Sp500ContractTest(_TmpOutput):
    def test_contract(self):
        c = ehd.SP500_FUNDAMENTALS_CONTRACT
        self.assertEqual(set(c["unavailable"]), {"pe_ratio_forward", "forward_earnings_yield", "forward_eps"})
        self.assertTrue(all("forward estimate" in r for r in c["unavailable"].values()))

    def test_both_writers_declare_what_they_write(self):
        fake = {"sp500_pe_trailing": 24.6, "sp500_pb": 1.77, "sp500_pe_forward": None, "earnings_yield": 4.06,
                "forward_earnings_yield": None, "dividend_yield_pct": 0.74, "trailing_eps": 30.9,
                "forward_eps": None, "spy_price": 760.7}
        written = []
        with mock.patch.object(ehd, "append_to_csv", side_effect=lambda f, df, **kw: written.append((f, df))), \
             mock.patch.object(ehd.openbb_extractors, "get_sp500_fundamentals_historical", return_value=fake), \
             mock.patch.object(ehd.openbb_extractors, "get_sp500_fundamentals", return_value=fake):
            self.quiet(ehd.extract_sp500_fundamentals)
            self.quiet(ehd.extract_sp500_fundamentals_expanded)
        self.assertEqual([f for f, _ in written], ["sp500_fundamentals.csv"] * 2)
        con = self.sidecar("sp500_fundamentals")
        declared = set(con["active"]) | set(con["unavailable"]) | {"timestamp", "date"}
        for _, df in written:
            self.assertLessEqual(set(df.columns), declared)
        self.assertEqual(set(written[1][1].columns), declared)   # the expanded writer defines the schema

    def test_failed_fetch_does_not_declare(self):
        with mock.patch.object(ehd.openbb_extractors, "get_sp500_fundamentals_historical",
                               return_value={"error": "down"}):
            self.quiet(ehd.extract_sp500_fundamentals_expanded)
        self.assertFalse((self.dir / ".sp500_fundamentals.columns.json").exists())


@unittest.skipUnless((CC_BACKFILL / "data_guard.py").exists(), "CC backfill/data_guard.py not found")
class ScannerRoundTripTest(_TmpOutput):
    def test_scanner_accepts_the_written_contracts(self):
        spec = importlib.util.spec_from_file_location("cc_data_guard", CC_BACKFILL / "data_guard.py")
        dg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dg)
        self.quiet(ibx._declare_column_contracts)
        ehd.declare_columns("sp500_fundamentals.csv", **ehd.SP500_FUNDAMENTALS_CONTRACT)
        for side in self.dir.glob(".*.columns.json"):
            csv_path = self.dir / f"{side.name[1:-len('.columns.json')]}.csv"
            con, problem = dg.load_contract(csv_path)
            self.assertIsNone(problem, side.name)
            self.assertIsNotNone(con, side.name)


if __name__ == "__main__":
    unittest.main()


class DeclareKeyAndActiveSinceTest(unittest.TestCase):
    """key= and active_since= (2026-09-22): written only when given, validated."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = ehd.OUTPUT_DIR
        ehd.OUTPUT_DIR = self.tmp

    def tearDown(self):
        ehd.OUTPUT_DIR = self.old

    def side(self, name):
        with open(os.path.join(self.tmp, f".{name}.columns.json")) as fh:
            return json.load(fh)

    def test_omitted_fields_are_not_written(self):
        ehd.declare_columns("plain.csv", active=["a"])
        self.assertNotIn("key", self.side("plain"))
        self.assertNotIn("active_since", self.side("plain"))

    def test_key_and_active_since_round_trip(self):
        ehd.declare_columns("snap.csv", active=["k", "v"], key=["date", "k"], active_since={"v": "2026-09-22"})
        s = self.side("snap")
        self.assertEqual(s["key"], ["date", "k"])
        self.assertEqual(s["active_since"], {"v": "2026-09-22"})

    def test_key_must_be_active_or_date(self):
        with self.assertRaises(ValueError):
            ehd.declare_columns("x.csv", active=["a"], key=["b"])

    def test_active_since_validation(self):
        with self.assertRaises(ValueError):
            ehd.declare_columns("x.csv", active=["a"], active_since={"b": "2026-01-01"})
        with self.assertRaises(ValueError):
            ehd.declare_columns("x.csv", active=["a"], active_since={"a": "2099-01-01"})
        with self.assertRaises(ValueError):
            ehd.declare_columns("x.csv", active=["a"], active_since={"a": "2026-1-1"})
