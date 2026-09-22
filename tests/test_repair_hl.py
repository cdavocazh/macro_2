"""Tests for scripts/repair_hl_20260921.py on a small synthetic copy of hl_perps.csv /
hl_spot_stocks.csv that carries every defect the script repairs: a Mac (GMT+8) prefix, the
x3/coins unit break, the frozen flx quotes, the 2026-09-19 fake-zero row, context-less builder
fields, back-filled prices with a provenance sidecar, and the wrong-market spot history with a
spot-only stretch and an interleaved second writer.

Stdlib unittest; everything runs in a temp dir, the Hyperliquid API is replaced by synthetic
candles / funding history, and nothing under historical_data/ is touched.

  python3 -m unittest discover -s tests -p 'test_repair_hl.py' -v
"""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
import signal
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_cwd = os.getcwd()
_spec = importlib.util.spec_from_file_location("repair_hl_20260921", ROOT / "scripts" / "repair_hl_20260921.py")
rp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rp)
os.chdir(_cwd)

EPOCH = pd.Timestamp("2026-01-01")
MAIN = {"btc": 1.0, "eth": 30.0, "sol": 700.0, "paxg": 16.0, "hype": 1800.0}   # price = btc / k
COINS = list(MAIN) + ["xrp", "oil", "sp500", "natgas", "copper_hl", "brentoil", "xyz100"]
FIELDS = ("price", "funding", "oi", "volume_24h", "premium")
SPOT_TICKERS = ("tsla", "amzn", "qqq", "spy", "msft")


def btc(t_utc: pd.Timestamp) -> float:
    """A level per UTC hour (golden-ratio scatter over 3%) plus a +-20 wiggle inside the hour,
    so a row's price fits its own hour's candle and, at any wrong offset, almost never another."""
    h = (t_utc - EPOCH).total_seconds() / 3600
    level = 70000 * (1 + 0.03 * ((math.floor(h) * 0.6180339887) % 1))
    return level + 20 * math.sin(2 * math.pi * (h % 1))


def rate(hour: pd.Timestamp) -> float:
    """Synthetic settled hourly funding: the interest-rate baseline most hours."""
    return 0.0000125 if hour.hour % 5 else 0.00002


def stored_funding(t_utc: pd.Timestamp, x: int) -> str:
    return repr(round(rate(t_utc.floor("h") + pd.Timedelta(hours=1)) * x * 365 * 100, 2))


def candles(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    out, h = {}, start.floor("h")
    while h <= end:
        xs = [btc(h + pd.Timedelta(seconds=15 * m)) for m in range(0, 240)]
        out[int(h.value // 1_000_000)] = {"o": xs[0], "c": xs[-1], "h": max(xs), "l": min(xs), "t": int(h.value // 1_000_000)}
        h += pd.Timedelta(hours=1)
    return out


def fmt(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")


def grid(start: str, n: int, step_s: float) -> list:
    t0 = pd.Timestamp(start)
    return [t0 + pd.Timedelta(seconds=step_s * i) for i in range(n)]


class Synthetic:
    """Builds the two CSVs and the provenance sidecar; remembers what each row is."""

    def __init__(self):
        mac = grid("2026-03-19 17:38:05.953235", 60, 66.5)                        # naive GMT+8
        p1 = grid("2026-06-03 14:51:00.469464", 30, 300)
        p2 = grid("2026-08-30 13:00:03.100000", 31, 300) + [rp.UNIT_BREAK] + grid("2026-08-30 15:38:09.476935", 6, 300)
        p3 = grid("2026-09-19 07:00:01.000000", 19, 300) + [pd.Timestamp("2026-09-19 08:36:01.338629")] + \
            grid("2026-09-19 08:41:40.327893", 17, 300)
        p4 = grid("2026-09-20 15:00:17.000000", 19, 300) + [rp.SPOT_FIX] + grid("2026-09-20 16:37:08.502034", 16, 300)
        p5 = grid("2026-09-21 13:00:11.000000", 24, 300) + [rp.NEW_CODE] + grid("2026-09-21 15:06:57.205261", 3, 300)
        self.mac = mac
        rows = []
        for i, t in enumerate(mac):
            rows.append(self.perp_row(t, t - pd.Timedelta(hours=8), mac_index=i))
        for t in p1 + p2 + p3 + p4 + p5:
            rows.append(self.perp_row(t, t))
        self.perps = pd.DataFrame(rows)
        self.fake_zero = "2026-09-19 08:36:01.338629"
        # Spot: the same runs' timestamps (partners), a spot-only stretch of the same writer,
        # then a second writer interleaved 30 s off; then VPS rows of p3/p4/p5.
        cont = grid(fmt(mac[-1] + pd.Timedelta(seconds=66.5)), 20, 66.5)
        a = cont[-1] + pd.Timedelta(seconds=66.5)
        inter = sorted(grid(fmt(a), 10, 66.5) + grid(fmt(a + pd.Timedelta(seconds=30)), 10, 66.5))
        self.spot_cont, self.spot_inter = cont, inter
        srows = [self.spot_row(t) for t in mac + cont + inter + p3 + p4 + p5]
        self.spot = pd.DataFrame(srows)
        self.prov = {"file": "hl_perps.csv", "written_by": "scripts/backfill_hl_perps_20260921.py", "meaning": "test",
                     "runs": [{"applied_at": "2026-09-21T15:10:00Z", "fill": "first", "source": "test", "cells_written": 0,
                               "columns": {}, "spans": [
                                   {"column": "hl_xrp_price", "from": fmt(mac[40]), "to": fmt(mac[55]), "interval": "1h",
                                    "utc_offset_h": 8, "cells": 16, "rows": 16, "max_value_age_min": 1.0},
                                   {"column": "hl_xrp_price", "from": fmt(p3[0]), "to": fmt(p3[5]), "interval": "1m",
                                    "utc_offset_h": 0, "cells": 6, "rows": 6, "max_value_age_min": 1.0}]}]}

    def perp_row(self, naive: pd.Timestamp, utc: pd.Timestamp, mac_index: int | None = None) -> dict:
        r = {"timestamp": fmt(naive), "date": naive.strftime("%Y-%m-%d")}
        for c in COINS:
            for f in FIELDS:
                r[f"hl_{c}_{f}"] = ""
        pre = utc < rp.UNIT_BREAK
        x = 3 if pre else 24
        b = btc(utc)
        for c, k in MAIN.items():
            px = round(b / k, 4)
            r[f"hl_{c}_price"] = repr(px)
            r[f"hl_{c}_funding"] = stored_funding(utc, x)
            coins = 30000.0 * k
            r[f"hl_{c}_oi"] = repr(round(coins, 2)) if pre else repr(round(coins * px, 2))
            r[f"hl_{c}_volume_24h"] = "2000000000.0"
        # XRP: collector values in the first 40 Mac rows, back-filled price in 40..55
        if mac_index is not None and mac_index < 40:
            r.update(hl_xrp_price="1.46", hl_xrp_funding=stored_funding(utc, 3), hl_xrp_oi="56686510.0",
                     hl_xrp_volume_24h="62015045.81")
        elif mac_index is not None and mac_index <= 55:
            r["hl_xrp_price"] = "1.45"
            if mac_index == 50:
                r["hl_xrp_oi"] = "56000000.0"        # an OI cell whose only price is back-filled
        elif utc >= rp.SPOT_FIX:
            r.update(hl_xrp_price="1.40", hl_xrp_funding="10.95", hl_xrp_oi="268000000.0", hl_xrp_volume_24h="148000000.0")
        elif utc.month == 9 and utc.day == 19 and utc.hour < 8:
            r["hl_xrp_price"] = "1.41"               # back-filled (second provenance span)
        # Builder perps before the break: context-less zeros and day-to-date base volume
        if mac_index is not None:
            for c in ("oil", "sp500", "natgas", "copper_hl", "brentoil", "xyz100"):
                r.update({f"hl_{c}_price": "97.0", f"hl_{c}_funding": "0.0", f"hl_{c}_oi": "0.0",
                          f"hl_{c}_volume_24h": repr(1000.0 + mac_index)})
            r["hl_oil_premium"] = "0.0"
            if mac_index == 30:
                r["hl_natgas_volume_24h"] = "0.0"   # criterion true outside the frozen window
        # Frozen window and live xyz markets after cb00e56
        if rp.UNIT_BREAK <= utc < rp.NEW_CODE:
            for c, v in rp.FROZEN.items():
                r.update({f"hl_{c}_price": repr(v), f"hl_{c}_funding": "0.0", f"hl_{c}_oi": "0.0", f"hl_{c}_volume_24h": "0.0"})
            r.update(hl_xyz100_price="29545.5", hl_xyz100_funding="5.48", hl_xyz100_oi="195392977.42",
                     hl_xyz100_volume_24h="264032945.54")
        elif utc >= rp.NEW_CODE:
            for c in ("oil", "sp500", "natgas", "copper_hl", "brentoil", "xyz100"):
                r.update({f"hl_{c}_price": "92.2", f"hl_{c}_funding": "5.48", f"hl_{c}_oi": "183000000.0",
                          f"hl_{c}_volume_24h": "243000000.0", f"hl_{c}_premium": "-0.03"})
        if fmt(naive) == "2026-09-19 08:36:01.338629":
            for c in MAIN:
                r.update({f"hl_{c}_funding": "0.0", f"hl_{c}_oi": "0.0", f"hl_{c}_volume_24h": "0.0"})
            r.update(hl_xyz100_price="", hl_xyz100_funding="", hl_xyz100_oi="", hl_xyz100_volume_24h="")
        return r

    @staticmethod
    def spot_row(t: pd.Timestamp) -> dict:
        r = {"timestamp": fmt(t), "date": t.strftime("%Y-%m-%d")}
        for k in SPOT_TICKERS:
            r[f"hl_{k}_price"] = "" if (k == "msft" and t >= rp.SPOT_FIX) else "123.4"
            r[f"hl_{k}_volume_24h"] = "" if (k == "msft" and t >= rp.SPOT_FIX) else "10.0"
        return r

    def write(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.perps.to_csv(data_dir / "hl_perps.csv", index=False)
        self.spot.to_csv(data_dir / "hl_spot_stocks.csv", index=False)
        (data_dir / ".hl_perps.provenance.json").write_text(json.dumps(self.prov, indent=1) + "\n")

    def ref(self) -> dict:
        return candles(pd.Timestamp("2026-03-18"), pd.Timestamp("2026-09-22"))


def fake_funding_history(coin, start, end):
    out, h = {}, start.floor("h")
    while h <= end + pd.Timedelta(hours=2):
        out[h] = rate(h)
        h += pd.Timedelta(hours=1)
    return out


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


class _Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.syn = Synthetic()
        cls.ref = cls.syn.ref()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "historical_data"
        self.syn.write(self.data)
        # the backfill's pre-backfill original: must never be overwritten
        self.backup_dir = self.root / ".deploy_backup_20260921" / "data"
        self.backup_dir.mkdir(parents=True)
        (self.backup_dir / "hl_perps.csv").write_text("pristine pre-backfill original\n")
        p = mock.patch.object(rp, "fetch_funding_history", side_effect=fake_funding_history)
        self.funding = p.start()
        self.addCleanup(p.stop)

    def run_cli(self, *args) -> tuple:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = rp.main(["--data-dir", str(self.data), *args], ref_candles=self.ref)
        return code, out.getvalue()

    def read(self, name) -> pd.DataFrame:
        return pd.read_csv(self.data / name, dtype=str, keep_default_na=False)

    def digests(self) -> dict:
        return {n: md5(self.data / n) for n in ("hl_perps.csv", "hl_spot_stocks.csv", ".hl_perps.provenance.json")}


class DryRunTest(_Base):
    def test_dry_run_writes_nothing_and_reports_every_repair(self):
        before = self.digests()
        code, out = self.run_cli()
        self.assertEqual(code, 0, out)
        self.assertEqual(before, self.digests())
        self.assertFalse((self.data / ".hl_perps.repairs.json").exists())
        for name in rp.NAMES.values():
            self.assertIn(name, out)
        self.assertIn("DRY RUN", out)
        self.assertIn("UTC+8", out)
        self.assertIn("identical: True", out)


class ApplyTest(_Base):
    def setUp(self):
        super().setUp()
        self.p0, self.s0 = self.read("hl_perps.csv"), self.read("hl_spot_stocks.csv")
        code, self.out = self.run_cli("--apply")
        self.assertEqual(code, 0, self.out)
        self.p, self.s = self.read("hl_perps.csv"), self.read("hl_spot_stocks.csv")
        self.prov = json.loads((self.data / ".hl_perps.provenance.json").read_text())

    def test_mac_rows_shift_to_utc_and_file_stays_ordered(self):
        n = len(self.syn.mac)
        for i in (0, 17, n - 1):
            want = self.syn.mac[i] - pd.Timedelta(hours=8)
            self.assertEqual(self.p.timestamp[i], fmt(want))
            self.assertEqual(self.p.date[i], want.strftime("%Y-%m-%d"))
        self.assertEqual(list(self.p.timestamp[n:]), list(self.p0.timestamp[n:]))
        ts = pd.to_datetime(self.p.timestamp, format="ISO8601")
        self.assertTrue(ts.is_monotonic_increasing)
        self.assertFalse(ts.duplicated().any())

    def test_spot_partner_and_continuity_rows_shift_interleaved_rows_stay(self):
        s0, s = self.s0.set_index(self.s0.index), self.s
        mac_n, cont_n, inter_n = len(self.syn.mac), len(self.syn.spot_cont), len(self.syn.spot_inter)
        for i in list(range(mac_n)) + list(range(mac_n, mac_n + cont_n)):
            self.assertEqual(s.timestamp[i], fmt(pd.Timestamp(s0.timestamp[i]) - pd.Timedelta(hours=8)))
        # the first interleaved row is still the old writer's (its predecessor is 66.5 s back)
        self.assertEqual(s.timestamp[mac_n + cont_n], fmt(pd.Timestamp(s0.timestamp[mac_n + cont_n]) - pd.Timedelta(hours=8)))
        inter = set(range(mac_n + cont_n + 1, mac_n + cont_n + inter_n))
        self.assertEqual({s0.timestamp[i] for i in inter} & set(s.timestamp), {s0.timestamp[i] for i in inter})
        rec = json.loads((self.data / ".hl_spot_stocks.repairs.json").read_text())
        un = rec["runs"][0]["repairs"]["timezone"]["unresolved"]
        self.assertEqual(un["rows"], inter_n - 1)   # the first interleaved row is the writer's own last one

    def test_provenance_spans_shift_and_select_the_same_cells(self):
        span_mac, span_vps = self.prov["runs"][0]["spans"]
        self.assertEqual(span_mac["from"], fmt(self.syn.mac[40] - pd.Timedelta(hours=8)))
        self.assertEqual(span_mac["to"], fmt(self.syn.mac[55] - pd.Timedelta(hours=8)))
        self.assertEqual(span_mac["utc_offset_h"], 0)
        self.assertEqual(span_mac["tz_normalised"]["utc_offset_h_before"], 8)
        self.assertEqual(span_vps["from"], self.syn.prov["runs"][0]["spans"][1]["from"])
        self.assertNotIn("tz_normalised", span_vps)

        def selected(df, prov):
            ts = pd.to_datetime(df.timestamp, format="ISO8601")
            out = set()
            for sp in prov["runs"][0]["spans"]:
                m = ts.between(pd.Timestamp(sp["from"]), pd.Timestamp(sp["to"])) & (df[sp["column"]] != "")
                out |= {(i, sp["column"]) for i in df.index[m]}
            return out
        self.assertEqual(selected(self.p0, self.syn.prov), selected(self.p, self.prov))
        self.assertEqual(len(selected(self.p, self.prov)), 16 + 6)

    def test_frozen_builder_quotes_blank_only_in_the_window(self):
        ts = pd.to_datetime(self.p.timestamp, format="ISO8601")
        win = (ts >= rp.UNIT_BREAK) & (ts < rp.NEW_CODE)
        for c in rp.FROZEN:
            for f in ("price", "funding", "oi", "volume_24h"):
                self.assertTrue((self.p.loc[win, f"hl_{c}_{f}"] == "").all(), (c, f))
            self.assertTrue((self.p.loc[ts >= rp.NEW_CODE, f"hl_{c}_price"] == "92.2").all())
        self.assertTrue((self.p.loc[win & (self.p.timestamp != self.syn.fake_zero), "hl_xyz100_price"] != "").all())
        ev = json.loads((self.data / ".hl_perps.repairs.json").read_text())["runs"][0]["repairs"]["frozen_builder_quotes"]
        self.assertEqual(ev["evidence"]["natgas"]["frozen_valued_not_caught"], [])
        self.assertEqual(ev["evidence"]["oil"]["caught"], int(win.sum()))
        self.assertEqual(len(ev["evidence"]["natgas"]["criterion_outside_window_untouched"]), 1)

    def test_fake_zero_row_blanked_price_kept(self):
        r = self.p[self.p.timestamp == self.syn.fake_zero].iloc[0]
        r0 = self.p0[self.p0.timestamp == self.syn.fake_zero].iloc[0]
        for c in MAIN:
            self.assertEqual((r[f"hl_{c}_funding"], r[f"hl_{c}_oi"], r[f"hl_{c}_volume_24h"]), ("", "", ""))
            self.assertEqual(r[f"hl_{c}_price"], r0[f"hl_{c}_price"])
        ev = json.loads((self.data / ".hl_perps.repairs.json").read_text())["runs"][0]["repairs"]["fake_zero_context"]
        self.assertEqual(ev["evidence"]["rows"], [self.syn.fake_zero])

    def test_contextless_builder_fields_blank_before_break_price_kept(self):
        n = len(self.syn.mac)
        for c in ("oil", "sp500", "natgas", "copper_hl", "brentoil", "xyz100"):
            for f in ("funding", "oi", "volume_24h", "premium"):
                self.assertTrue((self.p.loc[:n - 1, f"hl_{c}_{f}"] == "").all(), (c, f))
            self.assertTrue((self.p.loc[:n - 1, f"hl_{c}_price"] == "97.0").all())

    def test_units_converted_before_break_only(self):
        ts = pd.to_datetime(self.p.timestamp, format="ISO8601")
        pre = ts < rp.UNIT_BREAK
        for c, k in MAIN.items():
            f0, f1 = pd.to_numeric(self.p0.loc[pre, f"hl_{c}_funding"]), pd.to_numeric(self.p.loc[pre, f"hl_{c}_funding"])
            self.assertTrue(((f1 - f0 * 8).abs() < 1e-9).all(), c)
            o0 = pd.to_numeric(self.p0.loc[pre, f"hl_{c}_oi"])
            px = pd.to_numeric(self.p0.loc[pre, f"hl_{c}_price"])
            o1 = pd.to_numeric(self.p.loc[pre, f"hl_{c}_oi"])
            self.assertTrue(((o1 - (o0 * px).round(2)).abs() < 0.02).all(), c)
            post = ~pre & (self.p.timestamp != self.syn.fake_zero)
            self.assertEqual(list(self.p.loc[post, f"hl_{c}_oi"]), list(self.p0.loc[post, f"hl_{c}_oi"]))
        self.assertTrue((self.p.loc[pre, "hl_btc_funding"].isin(["10.96", "17.52"])).all())

    def test_oi_with_backfilled_price_is_blanked_and_listed(self):
        self.assertEqual(self.p.hl_xrp_oi[50], "")
        self.assertEqual(self.p.hl_xrp_price[50], "1.45")
        ev = json.loads((self.data / ".hl_perps.repairs.json").read_text())["runs"][0]["repairs"]["unit_break"]["evidence"]
        self.assertEqual(ev["oi_not_convertible"]["hl_xrp_oi"]["cells"], 1)
        self.assertEqual(ev["oi_not_convertible"]["hl_xrp_oi"]["why"]["price_backfilled"], 1)
        self.assertEqual(self.p.hl_xrp_oi[0], repr(round(56686510.0 * 1.46, 2)))
        self.assertIn("proof", ev)

    def test_spot_values_before_fix_blanked_columns_kept(self):
        ts = pd.to_datetime(self.s.timestamp, format="ISO8601")
        vcols = [c for c in self.s.columns if c not in ("timestamp", "date")]
        self.assertEqual(list(self.s.columns), list(self.s0.columns))
        self.assertTrue((self.s.loc[ts < rp.SPOT_FIX, vcols] == "").all().all())
        self.assertTrue((self.s.loc[ts >= rp.SPOT_FIX, "hl_spy_price"] == "123.4").all())
        rec = json.loads((self.data / ".hl_spot_stocks.repairs.json").read_text())["runs"][0]
        per_col = rec["repairs"]["spot_wrong_market"]["evidence"]["values_blanked_per_column"]
        self.assertEqual(per_col["hl_tsla_price"], int((pd.to_datetime(self.s0.timestamp, format="ISO8601") < rp.SPOT_FIX).sum()))

    def test_backups_and_record(self):
        self.assertEqual((self.backup_dir / "hl_perps.csv").read_text(), "pristine pre-backfill original\n")
        suffixed = list(self.backup_dir.glob("hl_perps.csv.repair-*"))
        self.assertEqual(len(suffixed), 1)
        self.assertTrue((self.backup_dir / "hl_spot_stocks.csv").exists())
        self.assertTrue((self.backup_dir / ".hl_perps.provenance.json").exists())
        rec = json.loads((self.data / ".hl_perps.repairs.json").read_text())
        run = rec["runs"][0]
        self.assertEqual((run["kind"], run["state"]), ("apply", "complete"))
        self.assertEqual(run["output_md5"], md5(self.data / "hl_perps.csv"))
        self.assertEqual(run["order"], [f"{k}_{rp.NAMES[k]}" for k in rp.ORDER])
        # every span names changed rows only
        frozen = run["repairs"]["frozen_builder_quotes"]["columns"]["hl_oil_price"]
        self.assertEqual(sum(s[2] for s in frozen["spans"]), frozen["cells"])
        self.assertEqual(frozen["values_blanked_top"], {"76.4": frozen["cells"]})

    def test_second_apply_is_a_no_op(self):
        before = self.digests()
        rec_before = (self.data / ".hl_perps.repairs.json").read_text()
        n_backups = len(list(self.backup_dir.iterdir()))
        code, out = self.run_cli("--apply")
        self.assertEqual(code, 0, out)
        self.assertIn("nothing to do", out)
        self.assertEqual(before, self.digests())
        self.assertEqual(rec_before, (self.data / ".hl_perps.repairs.json").read_text())
        self.assertEqual(n_backups, len(list(self.backup_dir.iterdir())))


class RollbackTest(_Base):
    def test_round_trip_is_byte_identical(self):
        before = self.digests()
        self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assertNotEqual(before, self.digests())
        code, out = self.run_cli("--rollback")
        self.assertEqual(code, 0, out)
        self.assertEqual(before, self.digests())
        self.assertEqual((self.backup_dir / "hl_perps.csv").read_text(), "pristine pre-backfill original\n")
        rec = json.loads((self.data / ".hl_perps.repairs.json").read_text())
        self.assertEqual([r["kind"] for r in rec["runs"]], ["apply", "rollback"])
        self.assertIn("nothing to roll back", self.run_cli("--rollback")[1])
        # after a rollback the repairs apply again, from a fresh backup
        self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assertEqual(self.run_cli("--rollback")[0], 0)
        self.assertEqual(before, self.digests())

    def test_rows_written_after_the_apply_survive_a_rollback(self):
        before = self.read("hl_perps.csv")
        self.assertEqual(self.run_cli("--apply")[0], 0)
        cur = self.read("hl_perps.csv")
        extra = cur.iloc[[-1]].copy()
        extra["timestamp"] = "2026-09-21 15:30:00.000001"
        pd.concat([cur, extra], ignore_index=True).to_csv(self.data / "hl_perps.csv", index=False)
        code, out = self.run_cli("--rollback")
        self.assertEqual(code, 0, out)
        after = self.read("hl_perps.csv")
        self.assertEqual(len(after), len(before) + 1)
        self.assertTrue(after.iloc[:-1].equals(before))
        self.assertEqual(after.timestamp.iloc[-1], "2026-09-21 15:30:00.000001")

    def test_refuses_when_the_provenance_changed_since_the_apply(self):
        self.assertEqual(self.run_cli("--apply")[0], 0)
        pv = self.data / ".hl_perps.provenance.json"
        pv.write_text(pv.read_text().replace('"fill": "first"', '"fill": "all"'))
        before = self.digests()
        code, out = self.run_cli("--rollback")
        self.assertEqual(code, 2, out)
        self.assertEqual(before, self.digests())


class CompositionTest(_Base):
    def test_repairs_compose_across_separate_runs(self):
        self.assertEqual(self.run_cli("--apply", "--only", "4")[0], 0)
        self.assertEqual(self.run_cli("--apply", "--only", "5,6")[0], 0)
        self.assertEqual(self.run_cli("--apply", "--skip", "3")[0], 0)
        self.assertEqual(self.run_cli("--apply")[0], 0)
        staged = self.digests()
        with tempfile.TemporaryDirectory() as t:
            other = Path(t) / "historical_data"
            self.syn.write(other)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(rp.main(["--data-dir", str(other), "--apply"], ref_candles=self.ref), 0)
            once = {n: md5(other / n) for n in staged}
        self.assertEqual(staged["hl_perps.csv"], once["hl_perps.csv"])
        self.assertEqual(staged["hl_spot_stocks.csv"], once["hl_spot_stocks.csv"])
        rec = json.loads((self.data / ".hl_perps.repairs.json").read_text())
        self.assertEqual([r["kind"] for r in rec["runs"]], ["apply"] * 4)     # every run changed hl_perps
        first_backup = rec["runs"][0]["backup"]
        self.assertIsNone(rec["runs"][0].get("provenance_backup"))     # only the timezone run moved spans
        self.assertEqual(self.run_cli("--rollback")[0], 0)
        self.assertEqual(md5(self.data / "hl_perps.csv"), md5(self.root / first_backup))
        with tempfile.TemporaryDirectory() as t:
            self.syn.write(Path(t))
            self.assertEqual(md5(self.data / ".hl_perps.provenance.json"), md5(Path(t) / ".hl_perps.provenance.json"))
            self.assertEqual(md5(self.data / "hl_spot_stocks.csv"), md5(Path(t) / "hl_spot_stocks.csv"))


class SafetyTest(_Base):
    def test_takes_both_collector_locks_while_writing(self):
        seen = []
        real = rp._csv_lock

        @contextlib.contextmanager
        def spy(path):
            seen.append(os.path.basename(path))
            with real(path):
                yield
        with mock.patch.object(rp, "_csv_lock", spy), \
                mock.patch.object(rp, "_atomic_to_csv", wraps=rp._atomic_to_csv) as w:
            self.assertEqual(self.run_cli("--apply")[0], 0)
        self.assertEqual(seen, ["hl_perps.csv", "hl_spot_stocks.csv"])
        self.assertEqual(sorted(os.path.basename(c.args[1]) for c in w.call_args_list),
                         ["hl_perps.csv", "hl_spot_stocks.csv"])

    def test_refuses_after_an_interrupted_apply(self):
        self.assertEqual(self.run_cli("--apply", "--only", "4")[0], 0)
        rpath = self.data / ".hl_perps.repairs.json"
        rec = json.loads(rpath.read_text())
        rec["runs"][-1]["state"] = "writing"
        rpath.write_text(json.dumps(rec))
        before = self.digests()
        code, out = self.run_cli("--apply")
        self.assertEqual(code, 2, out)
        self.assertIn("never completed", out)
        self.assertEqual(before, self.digests())

    def test_unit_proof_refuses_when_history_says_x24(self):
        self.funding.side_effect = lambda coin, a, b: {h: v / 8 for h, v in fake_funding_history(coin, a, b).items()}
        before = self.digests()
        code, out = self.run_cli("--apply", "--only", "2")
        self.assertEqual(code, 2, out)
        self.assertIn("refusing repair 2", out)
        self.assertEqual(before, self.digests())

    def test_unknown_timezone_near_a_threshold_refuses(self):
        naive = pd.Series(pd.to_datetime(["2026-03-01 00:00", "2026-08-30 10:00", "2026-09-30 00:00"]))
        off = pd.Series([float("nan"), float("nan"), float("nan")])
        with self.assertRaises(rp.Refuse):
            rp.side_of(naive, off, rp.UNIT_BREAK)
        ok = rp.side_of(naive.iloc[[0, 2]].reset_index(drop=True), off.iloc[:2], rp.UNIT_BREAK)
        self.assertEqual(list(ok), [True, False])

    def test_interleave_detection(self):
        import numpy as np
        one = np.arange(0, 66 * 40, 66.0)
        self.assertEqual(rp._interleave_start(one, 0, len(one)), len(one))
        spike = np.sort(np.append(one, [66 * 5 + 9]))            # one manual extra run is not a writer
        self.assertEqual(rp._interleave_start(spike, 0, len(spike)), len(spike))
        two = np.sort(np.concatenate([one, one[20:] + 30]))
        self.assertEqual(rp._interleave_start(two, 0, len(two)), 21)


class _Killed(BaseException):
    """Stands in for SIGKILL / OOM / power loss right after a chosen file write. Nothing of the
    script runs after it except unwinding (which a real death replaces with the OS dropping the
    flocks), so the files and records are left exactly as a kill at that point leaves them."""


class InterruptedTest(_Base):
    """Recovery after a kill anywhere inside the write window of --apply or --rollback (review
    2026-09-22: --rollback raised IndexError after an interrupted apply that had backed up the
    provenance sidecar, so the recovery path that --apply names was itself broken)."""

    RECORDS = (".hl_perps.repairs.json", ".hl_spot_stocks.repairs.json")

    def fresh(self):
        """Back to the synthetic originals: data dir, records and backups (backfill original kept)."""
        for p in sorted(self.root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            p.rmdir() if p.is_dir() else p.unlink()
        self.syn.write(self.data)
        self.backup_dir.mkdir(parents=True)
        (self.backup_dir / "hl_perps.csv").write_text("pristine pre-backfill original\n")

    def killed(self, k, *args) -> None:
        """Run the CLI and kill it right after its k-th file write (record, CSV, sidecar, restore)."""
        n = {"writes": 0}

        def after(fn):
            def inner(*a, **kw):
                fn(*a, **kw)
                n["writes"] += 1
                if n["writes"] == k:
                    raise _Killed(k)
            return inner
        with mock.patch.object(rp, "_atomic_json", after(rp._atomic_json)), \
                mock.patch.object(rp, "_atomic_to_csv", after(rp._atomic_to_csv)), \
                mock.patch.object(rp, "_atomic_copy", after(rp._atomic_copy)), \
                self.assertRaises(_Killed):
            self.run_cli(*args)

    def kinds(self, name) -> list:
        p = self.data / name
        return [r["kind"] for r in json.loads(p.read_text())["runs"]] if p.exists() else []

    def assert_pristine(self, pristine):
        self.assertEqual(pristine, self.digests())
        self.assertEqual((self.backup_dir / "hl_perps.csv").read_text(), "pristine pre-backfill original\n")

    def test_a_kill_anywhere_in_the_apply_window_rolls_back_byte_identical(self):
        pristine = self.digests()
        # A full apply writes, in this order: record hl_perps "writing", record hl_spot "writing",
        # hl_perps.csv, hl_spot_stocks.csv, the provenance sidecar, record hl_perps "complete",
        # record hl_spot "complete". k = 5 is the reviewers' case (sidecar rewritten, records not
        # complete); k = 6 leaves hl_perps complete and hl_spot "writing".
        for k in range(1, 7):
            with self.subTest(kill_after_write=k):
                self.fresh()
                self.killed(k, "--apply")
                self.assertEqual(self.kinds(self.RECORDS[0]), ["apply"])
                code, out = self.run_cli("--apply")
                self.assertEqual(code, 2, out)
                self.assertIn("never completed", out)
                code, out = self.run_cli("--rollback")
                self.assertEqual(code, 0, out)
                self.assert_pristine(pristine)
                self.assertEqual(self.kinds(self.RECORDS[0]), ["apply", "rollback"])
                # the way is clear again: an apply completes, a second finds nothing, a rollback undoes it
                code, out = self.run_cli("--apply")
                self.assertEqual(code, 0, out)
                self.assertIn("nothing to do", self.run_cli("--apply")[1])
                self.assertEqual(self.run_cli("--rollback")[0], 0)
                self.assert_pristine(pristine)

    def test_record_left_writing_after_the_sidecar_was_written(self):
        """The reviewers' reproduction: records set back to "writing" without their output md5s,
        the sidecar already rewritten. --apply refuses, --rollback restores byte-identical."""
        pristine = self.digests()
        self.assertEqual(self.run_cli("--apply")[0], 0)
        for name in self.RECORDS:
            p = self.data / name
            rec = json.loads(p.read_text())
            rec["runs"][-1]["state"] = "writing"
            rec["runs"][-1].pop("output_md5", None)
            rec["runs"][-1].pop("provenance_output_md5", None)
            p.write_text(json.dumps(rec))
        half = self.digests()
        code, out = self.run_cli()                          # a dry run says so and writes nothing
        self.assertEqual(code, 0, out)
        self.assertIn("WARNING: the last --apply recorded in", out)
        self.assertEqual(half, self.digests())
        api_calls = self.funding.call_count
        code, out = self.run_cli("--apply")                 # refuses before any API read
        self.assertEqual(code, 2, out)
        self.assertIn("never completed; run --rollback first", out)
        self.assertEqual(self.funding.call_count, api_calls)
        self.assertEqual(half, self.digests())
        code, out = self.run_cli("--rollback")
        self.assertEqual(code, 0, out)
        self.assertIn("undid an --apply interrupted mid-write", out)
        self.assert_pristine(pristine)

    def test_record_without_a_planned_sidecar_md5_refuses_cleanly(self):
        """A 'writing' record that cannot vouch for the rewritten sidecar (no planned md5): refuse
        with a message, not a traceback; once the sidecar is back to the apply's input, go on."""
        pristine = self.digests()
        self.assertEqual(self.run_cli("--apply")[0], 0)
        p = self.data / self.RECORDS[0]
        rec = json.loads(p.read_text())
        run = rec["runs"][-1]
        run["state"] = "writing"
        for key in ("output_md5", "provenance_output_md5", "provenance_planned_md5"):
            run.pop(key, None)
        p.write_text(json.dumps(rec))
        before = self.digests()
        code, out = self.run_cli("--rollback")
        self.assertEqual(code, 2, out)
        self.assertIn("by hand", out)
        self.assertEqual(before, self.digests())
        (self.data / ".hl_perps.provenance.json").write_bytes((self.root / run["provenance_backup"]).read_bytes())
        code, out = self.run_cli("--rollback")
        self.assertEqual(code, 0, out)
        self.assert_pristine(pristine)

    def test_a_kill_in_the_rollback_window_can_be_rerun(self):
        pristine = self.digests()
        # A rollback writes: hl_perps.csv, hl_spot_stocks.csv, the sidecar, record hl_perps, record hl_spot.
        # k = 3 left the sidecar restored but unrecorded, which the old guard refused for good.
        for k in range(1, 5):
            with self.subTest(kill_after_write=k):
                self.fresh()
                self.assertEqual(self.run_cli("--apply")[0], 0)
                self.killed(k, "--rollback")
                code, out = self.run_cli("--rollback")
                self.assertEqual(code, 0, out)
                self.assert_pristine(pristine)
                for name in self.RECORDS:
                    self.assertEqual(self.kinds(name), ["apply", "rollback"], name)

    def test_a_kill_while_backing_up_leaves_no_record_and_no_partial_backup(self):
        pristine = self.digests()
        whole = {n: (self.data / n).read_bytes() for n in ("hl_perps.csv", "hl_spot_stocks.csv", ".hl_perps.provenance.json")}
        real, n = rp.shutil.copy2, {"calls": 0}

        def copy_then_die(src, dst, **kw):
            n["calls"] += 1
            if n["calls"] == 2:                       # the second backup: half written, then death
                Path(dst).write_bytes(Path(src).read_bytes()[:100])
                raise _Killed(2)
            return real(src, dst, **kw)
        with mock.patch.object(rp.shutil, "copy2", copy_then_die), self.assertRaises(_Killed):
            self.run_cli("--apply")
        self.assertEqual([self.kinds(r) for r in self.RECORDS], [[], []])
        self.assertEqual(pristine, self.digests())

        def only_whole_backups():
            for p in self.backup_dir.iterdir():
                if p.name == "hl_perps.csv":
                    self.assertEqual(p.read_text(), "pristine pre-backfill original\n")
                    continue
                self.assertFalse(p.name.endswith(".tmp"), p.name)
                self.assertEqual(p.read_bytes(), whole[p.name.split(".repair-")[0]], p.name)
        only_whole_backups()
        code, out = self.run_cli("--apply")
        self.assertEqual(code, 0, out)
        only_whole_backups()
        self.assertEqual(self.run_cli("--rollback")[0], 0)
        self.assert_pristine(pristine)

    def test_sigint_in_the_write_window_waits_for_the_window_to_close(self):
        """Ctrl-C / a dropped session's SIGHUP mid-write: the window runs to its end, then the
        signal reaches the handler that was installed before, once."""
        acted = []

        def handler(signum, frame):     # what the records said when the signal was acted on
            acted.append([json.loads((self.data / r).read_text())["runs"][-1]["state"] for r in self.RECORDS])
        prev = signal.signal(signal.SIGINT, handler)     # own handler: other test modules install theirs
        self.addCleanup(signal.signal, signal.SIGINT, prev)
        real = rp._atomic_to_csv

        def poke(df, path):
            os.kill(os.getpid(), signal.SIGINT)
            real(df, path)
        with mock.patch.object(rp, "_atomic_to_csv", poke), contextlib.redirect_stderr(io.StringIO()) as err:
            code, out = self.run_cli("--apply")
        self.assertEqual(code, 0, out)
        self.assertEqual(acted, [["complete", "complete"]])     # held through both CSV writes, delivered once
        self.assertIn("SIGINT arrived while writing", err.getvalue())
        self.assertIs(signal.getsignal(signal.SIGINT), handler)
        self.assertIn("nothing to do", self.run_cli("--apply")[1])

    def test_backups_never_overwrite_each_other_within_one_second(self):
        pristine = self.digests()
        t = datetime(2026, 9, 21, 16, 0, 0, tzinfo=timezone.utc)
        with mock.patch.object(rp, "_utcnow", return_value=t):
            self.assertEqual(self.run_cli("--apply", "--only", "4")[0], 0)
            self.assertEqual(self.run_cli("--apply", "--only", "6")[0], 0)
        names = sorted(p.name for p in self.backup_dir.glob("hl_perps.csv*"))
        self.assertEqual(len(names), 3, names)          # backfill original + one per apply
        self.assertEqual(self.run_cli("--rollback")[0], 0)
        self.assert_pristine(pristine)

    def test_json_bytes_match_the_backfill_writer(self):
        obj = json.loads((self.data / ".hl_perps.provenance.json").read_text())
        obj["runs"][0]["spans"][0]["note"] = "non-ascii → kept as an escape"
        with tempfile.TemporaryDirectory() as t:
            path = os.path.join(t, ".x.json")
            rp.bf._atomic_json(obj, path)
            self.assertEqual(Path(path).read_bytes(), rp._json_bytes(obj))


if __name__ == "__main__":
    unittest.main()
