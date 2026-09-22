"""Tests for the Hyperliquid registries as the single source of truth:

  * the column contracts hl_extract.py declares for hl_perps.csv / hl_spot_stocks.csv
    (data_extractors.hyperliquid_extractor.hl_column_contracts + hl_extract._declare), checked
    against the headers the VPS files had on 2026-09-21 and against what the writer emits;
  * the dashboard relay (react_dashboard/backend/hl_ws_service.py) building its snapshots from
    the extractor's registries and rules, offline, from recorded-shape API replies.

Stdlib unittest; sidecars go to a temp dir (OUTPUT_DIR is patched), no network is used.

  python3 -m unittest discover -s tests -p 'test_hl_contracts.py' -v

The scanner test reads the sidecars back with CC's feed scanner (backfill/data_guard.py) from
$CC_BACKFILL_DIR, default ~/Github/CLI_OS/Agent_Orchestration/CC/backfill, and skips when absent.
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import extract_historical_data as ehd  # noqa: E402
import hl_extract  # noqa: E402
from data_extractors import hyperliquid_extractor as hx  # noqa: E402

CC_BACKFILL = Path(os.environ.get("CC_BACKFILL_DIR",
                                  Path.home() / "Github/CLI_OS/Agent_Orchestration/CC/backfill"))

# The headers of /root/macro_2/historical_data/hl_{perps,spot_stocks}.csv on 2026-09-21 15:12 UTC.
VPS_PERPS_HEADER = (
    "timestamp,date,hl_btc_price,hl_btc_funding,hl_btc_oi,hl_btc_volume_24h,hl_eth_price,hl_eth_funding,hl_eth_oi,"
    "hl_eth_volume_24h,hl_sol_price,hl_sol_funding,hl_sol_oi,hl_sol_volume_24h,hl_paxg_price,hl_paxg_funding,"
    "hl_paxg_oi,hl_paxg_volume_24h,hl_hype_price,hl_hype_funding,hl_hype_oi,hl_hype_volume_24h,hl_xrp_price,"
    "hl_xrp_funding,hl_xrp_oi,hl_xrp_volume_24h,hl_link_price,hl_link_funding,hl_link_oi,hl_link_volume_24h,"
    "hl_doge_price,hl_doge_funding,hl_doge_oi,hl_doge_volume_24h,hl_avax_price,hl_avax_funding,hl_avax_oi,"
    "hl_avax_volume_24h,hl_sui_price,hl_sui_funding,hl_sui_oi,hl_sui_volume_24h,hl_btc_premium,hl_eth_premium,"
    "hl_sol_premium,hl_paxg_premium,hl_hype_premium,hl_xrp_premium,hl_link_premium,hl_doge_premium,"
    "hl_avax_premium,hl_sui_premium,hl_oil_price,hl_oil_funding,hl_oil_oi,hl_oil_volume_24h,hl_oil_premium,"
    "hl_sp500_price,hl_sp500_funding,hl_sp500_oi,hl_sp500_volume_24h,hl_natgas_price,hl_natgas_funding,"
    "hl_natgas_oi,hl_natgas_volume_24h,hl_copper_hl_price,hl_copper_hl_funding,hl_copper_hl_oi,"
    "hl_copper_hl_volume_24h,hl_brentoil_price,hl_brentoil_funding,hl_brentoil_oi,hl_brentoil_volume_24h,"
    "hl_xyz100_price,hl_xyz100_funding,hl_xyz100_oi,hl_xyz100_volume_24h,hl_brentoil_premium,hl_sp500_premium,"
    "hl_natgas_premium,hl_copper_hl_premium,hl_xyz100_premium").split(",")
VPS_SPOT_HEADER = (
    "timestamp,date,hl_tsla_price,hl_tsla_volume_24h,hl_aapl_price,hl_aapl_volume_24h,hl_googl_price,"
    "hl_googl_volume_24h,hl_amzn_price,hl_amzn_volume_24h,hl_meta_price,hl_meta_volume_24h,hl_msft_price,"
    "hl_msft_volume_24h,hl_qqq_price,hl_qqq_volume_24h,hl_spy_price,hl_spy_volume_24h").split(",")


def full_snapshot():
    """A get_hl_snapshot()-shaped result in which every instrument has a price and a context."""
    perps = {info["key"]: {"price": 100.0, "funding_rate": 10.95, "open_interest": 1e8, "volume_24h": 2e8,
                           "premium": 0.01, "oracle_price": 100.0, "illiquid": False}
             for info in hx.HL_PERPS.values()}
    spot = {t.lower(): {"price": 50.0, "volume_24h": 1000.0} for t in hx.HL_SPOT_STOCKS}
    return perps, spot


class ContractTest(unittest.TestCase):
    def test_contracts_are_valid_for_declare_columns(self):
        for name, con in hx.hl_column_contracts().items():
            ehd._validate_contract(name, con["active"], con["retired"], con["unavailable"], "hl_extract.py")

    def test_every_vps_header_column_is_declared_exactly_once(self):
        for name, header in ((hx.HL_PERPS_CSV, VPS_PERPS_HEADER), (hx.HL_SPOT_STOCKS_CSV, VPS_SPOT_HEADER)):
            con = hx.hl_column_contracts()[name]
            lists = [set(con["active"]), set(con["retired"]), set(con["unavailable"])]
            for c in header[2:]:
                self.assertEqual(sum(c in s for s in lists), 1, (name, c))

    def test_retired_spot_tickers(self):
        con = hx.hl_column_contracts()[hx.HL_SPOT_STOCKS_CSV]
        self.assertEqual(set(con["retired"]), {f"hl_{t}_{f}" for t in ("aapl", "googl", "msft")
                                               for f in ("price", "volume_24h")})
        self.assertTrue(all(m["since"] == "2026-09-21" for m in con["retired"].values()))
        self.assertFalse(set(hx.HL_SPOT_STOCKS) & set(hx.HL_SPOT_STOCKS_RETIRED))
        self.assertFalse(set(hx.HL_PERPS) & set(hx.HL_PERPS_RETIRED))
        self.assertNotIn("hl_nvda_price", con["retired"])           # NVDA never had columns
        self.assertIn("NVDA", hx.HL_SPOT_STOCKS_RETIRED)

    def test_the_writer_emits_exactly_the_active_columns(self):
        perps, spot = full_snapshot()
        now = datetime(2026, 9, 21, 16, 0, 0)
        con = hx.hl_column_contracts()
        self.assertEqual(set(hl_extract._perp_row(perps, now)) - {"timestamp", "date"},
                         set(con[hx.HL_PERPS_CSV]["active"]))
        self.assertEqual(set(hl_extract._spot_row(spot, now)) - {"timestamp", "date"},
                         set(con[hx.HL_SPOT_STOCKS_CSV]["active"]))

    def test_writer_withholds_illiquid_contextless_and_untraded(self):
        perps, spot = full_snapshot()
        perps["oil"]["illiquid"] = True
        perps["btc"]["oracle_price"] = 0.0          # context did not load: price only
        spot["amzn"] = {"error": "untraded", "illiquid": True, "stale_mid": 180.5, "volume_24h": 0.0}
        row = hl_extract._perp_row(perps, datetime(2026, 9, 21))
        self.assertFalse(any(k.startswith("hl_oil_") for k in row))
        self.assertEqual([k for k in row if k.startswith("hl_btc_")], ["hl_btc_price"])
        srow = hl_extract._spot_row(spot, datetime(2026, 9, 21))
        self.assertFalse(any(k.startswith("hl_amzn_") for k in srow))


class DeclareTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        p = mock.patch.object(ehd, "OUTPUT_DIR", self.tmp.name)
        p.start()
        self.addCleanup(p.stop)

    def run_append(self, perps, spot):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hl_extract._append_to_csv(perps, spot)
        return out.getvalue()

    def test_append_then_declare_both_files(self):
        self.run_append(*full_snapshot())
        for name in (hx.HL_PERPS_CSV, hx.HL_SPOT_STOCKS_CSV):
            stem = name[:-4]
            self.assertTrue((self.dir / name).exists())
            side = json.loads((self.dir / f".{stem}.columns.json").read_text())
            con = hx.hl_column_contracts()[name]
            self.assertEqual((side["file"], side["writer"]), (name, "hl_extract.py"))
            self.assertEqual(side["active"], con["active"])
            self.assertEqual(side["retired"], con["retired"])

    def test_no_declaration_without_a_row(self):
        perps, _ = full_snapshot()
        self.run_append(perps, {"tsla": {"error": "untraded"}})
        self.assertTrue((self.dir / ".hl_perps.columns.json").exists())
        self.assertFalse((self.dir / "hl_spot_stocks.csv").exists())
        self.assertFalse((self.dir / ".hl_spot_stocks.columns.json").exists())

    def test_a_failing_declaration_never_stops_the_spot_append(self):
        with mock.patch.object(ehd, "declare_columns", side_effect=ValueError("bad contract")):
            out = self.run_append(*full_snapshot())
        self.assertIn("declare_columns(hl_perps.csv) error", out)
        self.assertTrue((self.dir / "hl_spot_stocks.csv").exists())

    def test_a_failed_append_is_not_declared(self):
        with mock.patch.object(ehd, "append_to_csv", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.run_append(*full_snapshot())
        self.assertFalse((self.dir / ".hl_perps.columns.json").exists())

    @unittest.skipUnless((CC_BACKFILL / "data_guard.py").exists(), "CC backfill/data_guard.py not found")
    def test_scanner_reads_the_contracts_and_finds_no_orphans_in_the_vps_headers(self):
        spec = importlib.util.spec_from_file_location("cc_data_guard", CC_BACKFILL / "data_guard.py")
        dg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dg)
        self.run_append(*full_snapshot())
        for name, header in ((hx.HL_PERPS_CSV, VPS_PERPS_HEADER), (hx.HL_SPOT_STOCKS_CSV, VPS_SPOT_HEADER)):
            con, problem = dg.load_contract(self.dir / name)
            self.assertIsNone(problem, name)
            scan = {"columns": header[2:], "last_value_dates": {c: "2026-09-21" for c in header[2:]
                                                              if c not in con["retired"]},
                    "blank_columns": {}, "last": "2026-09-21", "typical_gap_days": 1}
            flags, _ = dg.contract_findings(scan, con)
            self.assertEqual(flags, [], name)


# ── the dashboard relay ──────────────────────────────────────────────────────

def _load_relay():
    try:
        from react_dashboard.backend import hl_ws_service
    except ImportError as e:            # websockets not installed
        raise unittest.SkipTest(f"relay not importable: {e}")
    return hl_ws_service


def ctx(px, oi, vol, funding="0.0000125"):
    return {"funding": funding, "openInterest": str(oi), "dayNtlVlm": str(vol), "markPx": str(px),
            "oraclePx": str(px), "prevDayPx": str(px), "premium": "0.0", "midPx": str(px)}


def perp_replies(dead_copper=False):
    main = [{"universe": [{"name": n, "maxLeverage": 20} for n in ("BTC", "ETH", "SOL", "PAXG", "HYPE", "XRP",
                                                                  "LINK", "DOGE", "AVAX", "SUI", "ZZZ")]},
            [ctx(p, 100, 1e6) for p in (86000, 2700, 118, 4340, 93, 1.5, 13, 0.097, 11.2, 1.03, 5)]]
    names = ("xyz:CL", "xyz:BRENTOIL", "xyz:SP500", "xyz:NATGAS", "xyz:COPPER", "xyz:XYZ100", "xyz:TSLA")
    ctxs = [ctx(p, 1000, 2e8) for p in (92.2, 96.3, 7725, 3.0, 6.78, 30256, 363.8)]
    if dead_copper:
        ctxs[4] = ctx(6.33, 0, 0)
    xyz = [{"universe": [{"name": n, "maxLeverage": 10} for n in names]}, ctxs]
    return [main, xyz]


def spot_reply():
    """A FILTERED universe beside the full ctxs list, as spotMetaAndAssetCtxs returns it: position
    and pair name disagree, and the retired tickers' pairs trade (they must still not appear)."""
    pairs = {"@264": 407, "@280": 421, "@287": 422, "@279": 420, "@288": 426, "@268": 413, "@266": 412, "@289": 429}
    universe = [{"name": "PURR/USDC", "index": 0, "tokens": [1, 0]}] + \
        [{"name": n, "index": int(n[1:]), "tokens": [t, 0]} for n, t in pairs.items()]
    ctxs = [{"coin": "PURR/USDC", "midPx": "0.1", "dayNtlVlm": "5", "prevDayPx": "0.1"}]
    for i in range(1, 300):
        name = f"@{i}"
        if name == "@264":
            ctxs.append({"coin": name, "midPx": "422.5", "dayNtlVlm": "81.0", "prevDayPx": "300.0"})
        elif name == "@279":
            ctxs.append({"coin": name, "midPx": "776.5", "dayNtlVlm": "0.0", "prevDayPx": "770.0"})   # untraded
        elif name in pairs:
            ctxs.append({"coin": name, "midPx": "500.0", "dayNtlVlm": "900.0", "prevDayPx": "500.0"})
        else:
            ctxs.append({"coin": name, "midPx": "1.0", "dayNtlVlm": "12345.0", "prevDayPx": "1.0"})
    return [{"tokens": [], "universe": universe}, ctxs]


MIDS = {"BTC": "86000", "ETH": "2700", "SOL": "118", "PAXG": "4340", "HYPE": "93", "XRP": "1.5", "LINK": "13",
        "DOGE": "0.097", "AVAX": "11.2", "SUI": "1.03", "ZZZ": "5"}


class RelayTest(unittest.TestCase):
    def setUp(self):
        self.ws = _load_relay()
        self.relay = self.ws.HyperliquidWSRelay()

    def test_registries_are_the_extractors(self):
        ws = self.ws
        self.assertEqual(set(ws.HL_PERPS) | {k for k in hx.HL_PERPS if "api_coin" in hx.HL_PERPS[k]}, set(hx.HL_PERPS))
        self.assertEqual(set(ws.BUILDER_PERPS), {i["api_coin"] for i in hx.HL_PERPS.values() if "api_coin" in i})
        self.assertFalse(any(c.startswith("flx:") for c in ws.BUILDER_PERPS))
        self.assertEqual(ws.HL_SPOT_STOCKS, {t: i["index"] for t, i in hx.HL_SPOT_STOCKS.items()})
        for gone in hx.HL_SPOT_STOCKS_RETIRED:
            self.assertNotIn(gone, ws.HL_SPOT_STOCKS)
        # The relay iterates the extractor's own dict: a perp added there is published with no
        # edit to hl_ws_service.py.
        self.relay._ingest_perp_contexts(perp_replies())
        with mock.patch.dict(hx.HL_PERPS, {"ZZZ": {"key": "zzz", "name": "Zzz", "category": "crypto"}}):
            self.assertIn("zzz", self.relay._build_perp_snapshot(MIDS))
        self.assertNotIn("zzz", self.relay._build_perp_snapshot(MIDS))

    def test_perp_snapshot_covers_every_registered_perp(self):
        self.relay._ingest_perp_contexts(perp_replies())
        snap = self.relay._build_perp_snapshot(MIDS)
        keys = {k for k, v in snap.items() if isinstance(v, dict)}
        self.assertEqual(keys, {i["key"] for i in hx.HL_PERPS.values()})
        self.assertEqual(snap["oil"]["api_coin"], "xyz:CL")
        self.assertAlmostEqual(snap["oil"]["price"], 92.2)
        self.assertAlmostEqual(snap["btc"]["funding_rate"], 10.95)          # x24x365
        self.assertAlmostEqual(snap["btc"]["open_interest"], 100 * 86000)   # coins -> USD
        self.assertNotIn("zzz", snap)
        self.assertEqual(snap["source"], "Hyperliquid WS")

    def test_illiquid_builder_is_flagged_like_the_cache(self):
        self.relay._ingest_perp_contexts(perp_replies(dead_copper=True))
        snap = self.relay._build_perp_snapshot(MIDS)
        self.assertTrue(snap["copper_hl"]["illiquid"])
        self.assertIn("stale", snap["copper_hl"]["note"])
        self.assertFalse(snap["oil"]["illiquid"])

    def test_no_context_means_none_not_zero(self):
        snap = self.relay._build_perp_snapshot(MIDS)
        self.assertEqual(snap["btc"]["price"], 86000.0)
        for f in ("funding_rate", "open_interest", "volume_24h", "premium"):
            self.assertIsNone(snap["btc"][f])
        self.assertNotIn("oil", snap)                   # builder perps have no mid without a context

    def test_a_failed_dex_keeps_its_previous_contexts(self):
        self.relay._ingest_perp_contexts(perp_replies())
        self.relay._ingest_perp_contexts([perp_replies()[0]])
        self.assertIn("xyz:CL", self.relay._contexts)

    def test_spot_by_name_untraded_withheld_retired_absent(self):
        self.relay._ingest_spot(spot_reply())
        snap = self.relay._build_spot_snapshot()
        self.assertEqual(snap["tsla"]["price"], 422.5)       # @264 by NAME, not position 1
        self.assertNotIn("spy", snap)                        # 0 24h volume: stale mid withheld
        for gone in ("aapl", "googl", "msft", "nvda"):
            self.assertNotIn(gone, snap)
        self.assertEqual(snap["amzn"]["price"], 500.0)
        self.assertEqual(snap["source"], "Hyperliquid HIP-3 WS")

    def test_handle_message_broadcasts_both(self):
        import asyncio
        self.relay._ingest_perp_contexts(perp_replies())
        self.relay._ingest_spot(spot_reply())
        q = asyncio.Queue()
        self.relay.add_client(q)
        asyncio.run(self.relay._handle_message(json.dumps({"channel": "allMids", "data": {"mids": MIDS}})))
        msg = q.get_nowait()
        self.assertEqual(msg["type"], "hl_update")
        self.assertIn("xrp", msg["perps"])
        self.assertIn("tsla", msg["spot"])
        self.assertEqual(self.relay.get_snapshot()["perps"], msg["perps"])


class ExtractorSharedHelpersTest(unittest.TestCase):
    def test_get_hl_spot_stocks_uses_the_shared_helpers(self):
        raw = spot_reply()
        with mock.patch.object(hx, "get_hl_spot_meta", return_value=({}, raw[0]["universe"], raw[1])):
            res = hx.get_hl_spot_stocks()
        self.assertEqual(res["tsla"]["price"], 422.5)
        self.assertTrue(res["spy"]["illiquid"])
        self.assertEqual(res["spy"]["stale_mid"], 776.5)

    def test_get_hl_meta_and_contexts_merges_every_dex(self):
        replies = iter(perp_replies())
        with mock.patch.object(hx, "_hl_post", side_effect=lambda body: next(replies)):
            got = hx.get_hl_meta_and_contexts()
        self.assertIn("BTC", got)
        self.assertIn("xyz:CL", got)
        self.assertEqual(hx.meta_ctx_payloads()[1], {"type": "metaAndAssetCtxs", "dex": "xyz"})

    def test_snapshot_entries_match_the_csv_writer(self):
        contexts = {}
        for r in perp_replies():
            contexts.update(hx.parse_meta_and_asset_ctxs(r))
        entry = hx.build_perp_entry("OIL", MIDS, contexts)
        self.assertTrue(hx.context_loaded(entry))
        row = hl_extract._perp_row({"oil": entry}, datetime(2026, 9, 21))
        self.assertEqual(row["hl_oil_price"], 92.2)
        self.assertEqual(row["hl_oil_oi"], round(1000 * 92.2, 2))
        self.assertAlmostEqual(row["hl_oil_funding"], round(0.0000125 * 24 * 365 * 100, 2))


if __name__ == "__main__":
    unittest.main()
