"""Tests for data_extractors/consensus_extractors.py (macro_consensus.csv / macro_surprises.csv) and the
helpers of scripts/backfill_kalshi_consensus_20260922.py.

Stdlib unittest; no network (FRED is faked, ForexFactory is mocked). File tests write to a temp dir,
never to historical_data/.

  python3 -m unittest discover -s tests -p 'test_consensus.py' -v
"""
from __future__ import annotations

import contextlib
import csv
import importlib.util
import io
import json
import os
import statistics
import sys
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data_extractors import consensus_extractors as cx  # noqa: E402

UTC = timezone.utc
CPI, NFP, CLAIMS, FED = (cx.RELEASES[k] for k in ("cpi_mom", "nfp", "jobless_claims", "fomc_rate_upper"))


def T(s):
    return cx.parse_utc(s)


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _load_backfill():
    spec = importlib.util.spec_from_file_location(
        "backfill_kalshi_consensus", ROOT / "scripts" / "backfill_kalshi_consensus_20260922.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ParseFFValueTest(unittest.TestCase):
    def test_calendar_strings(self):
        self.assertEqual(cx.parse_ff_value("201K", "thousands"), 201.0)
        self.assertEqual(cx.parse_ff_value("0.3%", "percent"), 0.3)
        self.assertEqual(cx.parse_ff_value("-0.1%", "percent"), -0.1)
        self.assertEqual(cx.parse_ff_value("4.3%", "percent"), 4.3)
        self.assertEqual(cx.parse_ff_value("47.5", "index"), 47.5)
        self.assertIsNone(cx.parse_ff_value("", "percent"))
        self.assertIsNone(cx.parse_ff_value("   ", "thousands"))
        self.assertIsNone(cx.parse_ff_value(None, "percent"))

    def test_scaling_and_padding(self):
        self.assertEqual(cx.parse_ff_value("1.95M", "thousands"), 1950.0)
        self.assertEqual(cx.parse_ff_value("-12K", "thousands"), -12.0)
        self.assertEqual(cx.parse_ff_value(" 4.00% ", "percent"), 4.0)
        self.assertEqual(cx.parse_ff_value("4.3", "percent"), 4.3)          # bare number is still a percent

    def test_wrong_unit_or_junk_is_rejected(self):
        self.assertIsNone(cx.parse_ff_value("0.3%", "thousands"))
        self.assertIsNone(cx.parse_ff_value("201", "thousands"))           # persons or thousands? refuse
        self.assertIsNone(cx.parse_ff_value("201K", "percent"))
        self.assertIsNone(cx.parse_ff_value("47.5%", "index"))
        self.assertIsNone(cx.parse_ff_value("<0.1%", "percent"))
        self.assertIsNone(cx.parse_ff_value("n/a", "percent"))


class TitleMappingTest(unittest.TestCase):
    REQUIRED = ["cpi_mom", "core_cpi_mom", "cpi_yoy", "core_cpi_yoy", "nfp", "unemployment_rate",
                "retail_sales_mom", "pce_mom", "core_pce_mom", "ppi_mom", "core_ppi_mom", "jobless_claims",
                "gdp_qoq_saar", "fomc_rate_upper"]

    def test_every_required_key_exists(self):
        for k in self.REQUIRED:
            self.assertIn(k, cx.RELEASES)
            self.assertTrue(cx.RELEASES[k].ff_titles, k)

    def test_titles(self):
        cases = {"CPI m/m": "cpi_mom", "Core CPI m/m": "core_cpi_mom", "CPI y/y": "cpi_yoy",
                 "Non-Farm Employment Change": "nfp", "Unemployment Rate": "unemployment_rate",
                 "Retail Sales m/m": "retail_sales_mom", "Federal Funds Rate": "fomc_rate_upper",
                 "Unemployment Claims": "jobless_claims", "Advance GDP q/q": "gdp_qoq_saar",
                 "Core PCE Price Index m/m": "core_pce_mom", "PCE Price Index m/m": "pce_mom",
                 "PPI m/m": "ppi_mom", "Core PPI m/m": "core_ppi_mom", "  cpi   M/M ": "cpi_mom"}
        for title, key in cases.items():
            self.assertEqual(cx.map_ff_event({"country": "USD", "title": title}), key, title)

    def test_unmapped_and_foreign(self):
        for title in ("Core Retail Sales m/m", "Prelim GDP q/q", "Final GDP q/q", "ISM Manufacturing PMI",
                      "Average Hourly Earnings m/m", "FOMC Member Williams Speaks"):
            self.assertIsNone(cx.map_ff_event({"country": "USD", "title": title}), title)
        self.assertIsNone(cx.map_ff_event({"country": "EUR", "title": "CPI m/m"}))
        self.assertIsNone(cx.map_ff_event({"country": "CAD", "title": "Unemployment Rate"}))

    EVENTS = [
        {"title": "Unemployment Claims", "country": "USD", "date": "2026-09-24T08:30:00-04:00",
         "impact": "Medium", "forecast": "201K", "previous": "196K"},
        {"title": "CPI m/m", "country": "USD", "date": "2026-09-21T08:30:00-04:00",     # already released
         "impact": "High", "forecast": "0.3%", "previous": "0.2%"},
        {"title": "New Home Sales", "country": "USD", "date": "2026-09-24T10:00:00-04:00",
         "impact": "Low", "forecast": "619K", "previous": "607K"},
        {"title": "New Home Sales", "country": "USD", "date": "2026-09-25T10:00:00-04:00",
         "impact": "Low", "forecast": "", "previous": ""},
        {"title": "CPI m/m", "country": "EUR", "date": "2026-09-24T05:00:00-04:00",
         "impact": "High", "forecast": "0.1%", "previous": "0.2%"},
    ]

    def test_snapshot_rows(self):
        now = T("2026-09-22T09:00:00Z")
        rows, info = cx.ff_snapshot_rows(self.EVENTS, now)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["release_key"], r["release_time_utc"], r["source"]),
                         ("jobless_claims", "2026-09-24T12:30:00Z", "ff"))
        self.assertEqual((r["consensus"], r["previous"], r["unit"], r["date"]), (201.0, 196.0, "thousands", "2026-09-22"))
        self.assertEqual(json.loads(r["detail"])["forecast"], "201K")
        self.assertEqual(info["unmapped"], ["New Home Sales"])
        self.assertEqual(info["past"], 1)

    def test_unmapped_logged_once(self):
        out = io.StringIO()
        with mock.patch.object(cx, "fetch_ff_calendar", return_value=self.EVENTS), contextlib.redirect_stdout(out):
            res = cx.run_snapshot(data_dir=tempfile.gettempdir(), now=T("2026-09-22T09:00:00Z"),
                                  use_kalshi=False, dry_run=True)
        lines = [ln for ln in out.getvalue().splitlines() if "unmapped" in ln]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].count("New Home Sales"), 1)
        self.assertEqual((res["status"], res["rows"], res["written"]), ("ok", 1, 0))

    def test_ff_failure_is_partial_or_failed(self):
        with mock.patch.object(cx, "fetch_ff_calendar", side_effect=cx.SourceError("ForexFactory HTTP 429")):
            res = quiet(cx.run_snapshot, data_dir=tempfile.gettempdir(), use_kalshi=False, dry_run=True)
        self.assertEqual(res["status"], "failed")


class KalshiThresholdTest(unittest.TestCase):
    def test_greater_and_scaling(self):
        self.assertEqual(cx.market_threshold({"strike_type": "greater", "floor_strike": 0.3}, CPI), (0.3, True))
        self.assertEqual(cx.market_threshold({"strike_type": "greater", "floor_strike": 50000}, NFP), (50.0, True))
        self.assertEqual(cx.market_threshold({"strike_type": "greater", "floor_strike": -0.4}, CPI), (-0.4, True))

    def test_at_least_moves_one_step_down(self):
        m = {"strike_type": "greater_or_equal", "floor_strike": 185000, "yes_sub_title": "At least 185,000"}
        self.assertEqual(cx.market_threshold(m, CLAIMS), (184.0, True))

    def test_float_noise_snaps_to_grid(self):
        self.assertEqual(cx.market_threshold({"strike_type": "greater", "floor_strike": 4.099999},
                                             cx.RELEASES["unemployment_rate"]), (4.1, True))

    def test_legacy_markets_without_strike_fields(self):
        self.assertEqual(cx.market_threshold({"yes_sub_title": "Above 1.3%", "ticker": "CPI-22JUN-T1.3"}, CPI), (1.3, True))
        self.assertEqual(cx.market_threshold({"yes_sub_title": "Above 350,000", "ticker": "JOBLESS-21JUL17-C350"},
                                             CLAIMS), (350.0, True))
        self.assertEqual(cx.market_threshold({"yes_sub_title": "", "ticker": "PCECORE-22NOV-TN0.1"}, CPI), (-0.1, True))
        self.assertEqual(cx.market_threshold({"yes_sub_title": "Above 0.9%%"}, CPI), (0.9, True))

    def test_less_and_unsupported(self):
        self.assertEqual(cx.market_threshold({"strike_type": "less_or_equal", "cap_strike": 0.2}, CPI), (0.2, False))
        self.assertEqual(cx.market_threshold({"strike_type": "less", "cap_strike": 0.2}, CPI), (0.1, False))
        self.assertIsNone(cx.market_threshold({"strike_type": "between", "floor_strike": 0.1, "cap_strike": 0.2}, CPI))
        self.assertIsNone(cx.market_threshold({"strike_type": "custom"}, CPI))


class QuoteProbTest(unittest.TestCase):
    def test_mid_and_weight(self):
        p, w, src, bid, ask = cx.quote_prob(0.56, 0.58, 0.5)
        self.assertAlmostEqual(p, 0.57)
        self.assertAlmostEqual(w, 50.0)
        self.assertEqual(src, "mid")

    def test_fallbacks(self):
        self.assertEqual(cx.quote_prob(0.10, 0.90, 0.40)[:3], (0.40, cx.TRADE_WEIGHT, "last"))   # 80c wide
        self.assertEqual(cx.quote_prob(None, None, None, 0.3)[2], "prev")
        self.assertIsNone(cx.quote_prob(0.0, 0.0, None))              # empty book, never traded
        self.assertIsNone(cx.quote_prob(None, None, 0.0, 1.0))        # 0/1 are not prices
        self.assertEqual(cx.quote_prob(0.0, 0.01)[0], 0.005)          # a 0/1c tail is a price


class PavaTest(unittest.TestCase):
    def test_monotone_unchanged(self):
        self.assertEqual(cx.pava_nonincreasing([0.9, 0.5, 0.1], [1, 1, 1]), [0.9, 0.5, 0.1])

    def test_violation_pooled(self):
        got = cx.pava_nonincreasing([0.9, 0.5, 0.6, 0.1], [1, 1, 1, 1])
        for a, b in zip(got, [0.9, 0.55, 0.55, 0.1]):
            self.assertAlmostEqual(a, b)

    def test_weighted(self):
        got = cx.pava_nonincreasing([0.5, 0.7], [3, 1])
        self.assertAlmostEqual(got[0], 0.55)
        self.assertAlmostEqual(got[1], 0.55)


class ImpliedDistributionTest(unittest.TestCase):
    def dist(self, pts, step):
        return cx.implied_distribution([(t, p, 1.0) for t, p in pts], step)

    def test_contiguous_ladder(self):
        d = self.dist([(0.3, 0.96), (0.4, 0.885), (0.5, 0.57), (0.6, 0.245), (0.7, 0.045)], 0.1)
        self.assertTrue(d["ok"])
        self.assertAlmostEqual(d["median"], 0.55 + (0.57 - 0.5) / (0.57 - 0.245) * 0.1)     # 0.5715...
        self.assertEqual(d["median_grid"], 0.6)
        masses = [(0.3, 0.04), (0.4, 0.075), (0.5, 0.315), (0.6, 0.325), (0.7, 0.2), (0.8, 0.045)]
        self.assertAlmostEqual(d["mean"], sum(v * m for v, m in masses))
        self.assertAlmostEqual(d["tail_lo"], 0.04)
        self.assertAlmostEqual(d["tail_hi"], 0.045)

    def test_ladder_with_gaps(self):
        d = self.dist([(0, 0.9), (50, 0.6), (100, 0.3), (150, 0.1)], 1.0)        # payrolls, thousands
        self.assertTrue(d["ok"])
        self.assertAlmostEqual(d["median"], 50.5 + (0.6 - 0.5) / 0.3 * 50)          # 67.17
        self.assertEqual(d["median_grid"], 67.0)                                     # ceil(50 * 0.1/0.3) = 17
        masses = [(0, 0.1), (25.5, 0.3), (75.5, 0.3), (125.5, 0.2), (151, 0.1)]      # gap midpoints
        self.assertAlmostEqual(d["mean"], sum(v * m for v, m in masses))

    def test_zero_one_tails(self):
        base = [(0.0, 1.0), (0.1, 1.0), (0.2, 0.6), (0.3, 0.0), (0.4, 0.0)]
        d = self.dist(base, 0.1)
        self.assertEqual((d["tail_lo"], d["tail_hi"]), (0.0, 0.0))
        self.assertAlmostEqual(d["mean"], 0.2 * 0.4 + 0.3 * 0.6)
        self.assertAlmostEqual(d["median"], 0.25 + (0.6 - 0.5) / 0.6 * 0.1)
        self.assertEqual(d["median_grid"], 0.3)
        wider = self.dist(base + [(-1.0, 1.0), (2.0, 0.0)], 0.1)                   # certain tails add nothing
        self.assertAlmostEqual(wider["mean"], d["mean"])
        self.assertAlmostEqual(wider["median"], d["median"])

    def test_non_monotone_is_repaired(self):
        d = self.dist([(0.1, 0.90), (0.2, 0.95), (0.3, 0.40), (0.4, 0.45), (0.5, 0.05)], 0.1)
        s = d["p_mono"]
        self.assertTrue(all(a >= b - 1e-12 for a, b in zip(s, s[1:])), s)
        self.assertTrue(d["ok"])
        self.assertAlmostEqual(s[0], 0.925)
        self.assertAlmostEqual(s[2], 0.425)

    def test_median_outside_ladder_or_too_few_strikes(self):
        below = self.dist([(0.3, 0.4), (0.4, 0.2), (0.5, 0.1)], 0.1)
        above = self.dist([(0.3, 0.9), (0.4, 0.8), (0.5, 0.6)], 0.1)
        few = self.dist([(0.3, 0.9), (0.4, 0.2)], 0.1)
        self.assertFalse(below["ok"]); self.assertIn("below", below["reason"])
        self.assertFalse(above["ok"]); self.assertIn("above", above["reason"])
        self.assertFalse(few["ok"]); self.assertIn("< 3", few["reason"])

    def test_duplicate_strikes_pooled(self):
        d = cx.implied_distribution([(0.2, 0.8, 1.0), (0.2, 0.6, 1.0), (0.3, 0.3, 1.0), (0.4, 0.1, 1.0)], 0.1)
        self.assertEqual(d["n"], 3)
        self.assertAlmostEqual(d["p_raw"][0], 0.7)

    # KXCPI-26SEP as served on 2026-09-21 (yes bid/ask, dollars).
    KXCPI_26SEP = [(-0.4, .99, 1.0), (-0.3, .98, .99), (-0.2, .98, .99), (-0.1, .99, 1.0), (0.0, .98, .99),
                   (0.1, .97, .99), (0.2, .98, .99), (0.3, .95, .97), (0.4, .88, .89), (0.5, .56, .58),
                   (0.6, .24, .25), (0.7, .04, .05), (0.8, .01, .02), (0.9, 0.0, .01)]

    def test_real_ladder(self):
        markets = [{"ticker": f"KXCPI-26SEP-T{k}", "strike_type": "greater", "floor_strike": k,
                    "yes_bid_dollars": f"{b:.4f}", "yes_ask_dollars": f"{a:.4f}", "last_price_dollars": "0.5000",
                    "close_time": "2026-10-14T12:25:00Z"} for k, b, a in self.KXCPI_26SEP]
        res = cx.ladder_consensus([(m, cx.live_quote(m), {}) for m in markets], CPI)
        self.assertTrue(res["ok"])
        self.assertEqual(res["consensus"], 0.5715)
        self.assertEqual(res["detail"]["median_grid"], 0.6)
        self.assertEqual(res["detail"]["price_sources"], {"mid": 14})
        s = [row[4] for row in res["detail"]["ladder"]]
        self.assertTrue(all(a >= b for a, b in zip(s, s[1:])))
        self.assertEqual(cx.kalshi_release_time(markets, CPI), T("2026-10-14T12:30:00Z"))


class FakeKalshi:
    def __init__(self, events_by_series, fail=()):
        self.events_by_series, self.fail, self.requests = events_by_series, set(fail), 0

    def events(self, series, status, nested=False):
        self.requests += 1
        if series in self.fail:
            raise cx.SourceError(f"Kalshi /events: HTTP 503 ({series})")
        return self.events_by_series.get(series, [])


def _cpi_event(ticker, close):
    return {"event_ticker": ticker, "markets": [
        {"ticker": f"{ticker}-T{k}", "strike_type": "greater", "floor_strike": k, "close_time": close,
         "yes_bid_dollars": f"{b:.4f}", "yes_ask_dollars": f"{a:.4f}", "volume_fp": "10.00", "open_interest_fp": "5.00"}
        for k, b, a in ImpliedDistributionTest.KXCPI_26SEP]}


class KalshiSnapshotTest(unittest.TestCase):
    def test_next_event_per_series_and_partial_failure(self):
        client = FakeKalshi({"KXCPI": [_cpi_event("KXCPI-26OCT", "2026-11-10T13:25:00Z"),
                                       _cpi_event("KXCPI-26AUG", "2026-09-11T12:25:00Z"),     # already released
                                       _cpi_event("KXCPI-26SEP", "2026-10-14T12:25:00Z")]},
                            fail={"KXPAYROLLS"})
        rows, info = cx.kalshi_snapshot_rows(client, T("2026-09-22T09:00:00Z"))
        self.assertEqual([(r["release_key"], r["release_time_utc"]) for r in rows], [("cpi_mom", "2026-10-14T12:30:00Z")])
        self.assertEqual(rows[0]["consensus"], 0.5715)
        detail = json.loads(rows[0]["detail"])
        self.assertEqual((detail["event"], detail["method"], detail["volume"]), ("KXCPI-26SEP", "live", 140.0))
        self.assertEqual(len(info["failed"]), 1)
        self.assertIn("KXU3", info["no_event"])
        self.assertEqual(info["attempted"], sum(1 for s in cx.RELEASES.values() for _x, live in s.kalshi if live))
        res = quiet(cx.run_snapshot, data_dir=tempfile.gettempdir(), now=T("2026-09-22T09:00:00Z"),
                    use_ff=False, kalshi=client, dry_run=True)
        self.assertEqual(res["status"], "partial")

    def test_budget_stops_requests(self):
        c = cx.KalshiClient(budget_s=1)
        c.deadline -= 5
        with self.assertRaises(cx.SourceError) as e:
            c.get("/events", series_ticker="KXCPI")
        self.assertIn("budget", str(e.exception))
        self.assertEqual(c.requests, 0)

    def test_fred_budget_and_key_redaction(self):
        f = cx.FredClient(api_key="SECRETKEY123", budget_s=1)
        f.deadline -= 5
        with self.assertRaises(cx.SourceError) as e:
            f.vintages("CPIAUCSL", date(2020, 1, 1), date(2020, 1, 1))
        self.assertNotIn("SECRETKEY123", str(e.exception))
        self.assertEqual(f._redact("GET /fred/x?series_id=A&api_key=SECRETKEY123&file_type=json"),
                         "GET /fred/x?series_id=A&api_key=***&file_type=json")
        self.assertEqual(f._redact("boom SECRETKEY123 boom"), "boom *** boom")


class TimeAndReferenceTest(unittest.TestCase):
    def test_parse_utc(self):
        self.assertEqual(T("2026-09-24T08:30:00-04:00"), datetime(2026, 9, 24, 12, 30, tzinfo=UTC))
        self.assertEqual(T("2025-01-30T13:32:57.14518Z"), datetime(2025, 1, 30, 13, 32, 57, 145180, tzinfo=UTC))
        self.assertEqual(T("2026-09-21 17:08:00"), datetime(2026, 9, 21, 17, 8, tzinfo=UTC))
        self.assertIsNone(T("")); self.assertIsNone(T("garbage"))

    def test_kalshi_release_time(self):
        rt = lambda close, spec=CPI: cx.kalshi_release_time([{"close_time": close}], spec)
        self.assertEqual(rt("2026-12-10T13:25:00Z"), T("2026-12-10T13:30:00Z"))      # EST
        self.assertEqual(rt("2026-10-14T12:29:00Z"), T("2026-10-14T12:30:00Z"))      # EDT
        self.assertEqual(rt("2021-07-12T23:00:00Z"), T("2021-07-13T12:30:00Z"))      # closed the evening before
        self.assertEqual(rt("2022-01-12T04:59:00Z"), T("2022-01-12T13:30:00Z"))      # 23:59 EST the day before
        self.assertEqual(rt("2026-10-28T17:55:00Z", FED), T("2026-10-28T18:00:00Z"))
        self.assertIsNone(cx.kalshi_release_time([], CPI))

    def test_reference_periods(self):
        ref = lambda sub, spec, ticker="", title="": cx.kalshi_reference_period(
            {"sub_title": sub, "title": title, "event_ticker": ticker}, spec)
        self.assertEqual(ref("In Jul 2026", CPI), date(2026, 7, 1))
        self.assertEqual(ref("September 2026", CPI), date(2026, 9, 1))
        self.assertEqual(ref("", CPI, title="CPI in June 2022?"), date(2022, 6, 1))
        self.assertEqual(ref("In Q2 2026", cx.RELEASES["gdp_qoq_saar"]), date(2026, 4, 1))
        self.assertEqual(ref("For the week ending Sep 12, 2026", CLAIMS), date(2026, 9, 12))
        self.assertEqual(ref("From Aug 22-28, 2021", CLAIMS), date(2021, 8, 28))
        self.assertEqual(ref("Sep 18 to 24, 2022", CLAIMS), date(2022, 9, 24))
        self.assertEqual(ref("From Aug 28-03", CLAIMS, "JOBLESS-22SEP03"), date(2022, 9, 3))
        self.assertEqual(ref("From Dec 26, 2021-Jan 1, 2022", CLAIMS), date(2022, 1, 1))
        self.assertEqual(ref("From Dec 26, 2021-Jan 1", CLAIMS), date(2022, 1, 1))
        self.assertEqual(ref("Oct 30 to Nov 5, 2022", CLAIMS), date(2022, 11, 5))
        # mislabelled by Kalshi with its Thursday release day; the week ended Saturday Jun 7
        self.assertEqual(ref("For the week ending Jun 12, 2025", CLAIMS, "KXJOBLESSCLAIMS-25JUN12"), date(2025, 6, 7))
        self.assertEqual(ref("On Sep 16, 2026", FED), date(2026, 9, 16))
        self.assertEqual(ref("In Sep 18, 2024", FED), date(2024, 9, 18))
        self.assertIsNone(ref("In Jun 2023", FED))


class FakeFred:
    """vintages()/observations() from in-memory tables; counts calls like FredClient.requests."""

    def __init__(self, vint=None, obs=None):
        self.vint, self.obs, self.requests = vint or {}, obs or {}, 0

    def vintages(self, series_id, obs_start, rt_start):
        self.requests += 1
        return self.vint[series_id]

    def observations(self, series_id, obs_start):
        self.requests += 1
        return self.obs[series_id]


OPEN = "9999-12-31"
PAYEMS = {"2026-06-01": [("2026-07-02", OPEN, "158984")],
          "2026-07-01": [("2026-08-07", "2026-09-03", "158858"), ("2026-09-04", OPEN, "158900")],
          "2026-08-01": [("2026-09-04", OPEN, "159075")]}


class ActualTest(unittest.TestCase):
    def test_half_up_not_bankers(self):
        rows = {"2026-07-01": [("2026-08-12", OPEN, "100.000")], "2026-08-01": [("2026-09-11", OPEN, "100.250")]}
        self.assertEqual(cx.apply_transform("pct1", rows, "2026-08-01", "2026-09-11", 1), (0.3, None))
        self.assertEqual(round(0.25, 1), 0.2)          # what float round() would have said

    def test_same_vintage_prior_month(self):
        # August's print is 159,075 - 158,900 (July as revised on 2026-09-04), not - 158,858.
        self.assertEqual(cx.apply_transform("diff1", PAYEMS, "2026-08-01", "2026-09-04", 0), (175.0, None))
        self.assertEqual(cx.apply_transform("diff1", PAYEMS, "2026-07-01", "2026-08-07", 0), (-126.0, None))

    def test_yoy_and_missing_prior(self):
        rows = {"2025-08-01": [("2025-09-11", OPEN, "300.000")], "2026-08-01": [("2026-09-11", OPEN, "309.900")]}
        self.assertEqual(cx.apply_transform("pct12", rows, "2026-08-01", "2026-09-11", 1), (3.3, None))
        v, why = cx.apply_transform("pct1", rows, "2026-08-01", "2026-09-11", 1)
        self.assertIsNone(v)
        self.assertIn("2026-07-01", why)

    def test_resolve_first_release_window(self):
        fred = FakeFred(vint={"PAYEMS": PAYEMS})
        got = cx.resolve_actuals(fred, "nfp", [date(2026, 9, 4), date(2026, 10, 2), date(2026, 8, 7)])
        self.assertEqual(got[date(2026, 9, 4)]["actual"], 175.0)
        self.assertEqual(got[date(2026, 9, 4)]["reference_period"], "2026-08-01")
        self.assertIn("PAYEMS first release 2026-09-04", got[date(2026, 9, 4)]["actual_source"])
        self.assertEqual(got[date(2026, 8, 7)]["actual"], -126.0)
        self.assertIsNone(got[date(2026, 10, 2)])                  # not on FRED yet: retried later
        self.assertEqual(fred.requests, 1)

    def test_catch_up_release_scores_the_newest_period(self):
        # 2025-12-16 published October AND November payrolls (shutdown catch-up): November is the headline.
        rows = {"2025-09-01": [("2025-11-20", OPEN, "159626")],
                "2025-10-01": [("2025-12-16", OPEN, "159488")],
                "2025-11-01": [("2025-12-16", OPEN, "159552")]}
        got = cx.resolve_actuals(FakeFred(vint={"PAYEMS": rows}), "nfp", [date(2025, 12, 16)])[date(2025, 12, 16)]
        self.assertEqual((got["reference_period"], got["actual"]), ("2025-11-01", 64.0))
        october = cx.actual_for_obs("nfp", rows, cx.first_releases(rows), "2025-10-01")
        self.assertEqual(october["actual"], -138.0)

    def test_missing_prior_month_is_unresolvable(self):
        # October 2025 CPI was never published, so November's m/m cannot be computed.
        rows = {"2025-09-01": [("2025-10-24", OPEN, "324.368")], "2025-10-01": [("2025-12-18", OPEN, ".")],
                "2025-11-01": [("2025-12-18", OPEN, "325.031")]}
        got = cx.resolve_actuals(FakeFred(vint={"CPIAUCSL": rows}), "cpi_mom", [date(2025, 12, 18)])
        self.assertIn("2025-10-01", got[date(2025, 12, 18)]["error"])

    def test_fomc_upper_is_the_next_day(self):
        obs = {"2026-09-15": "3.75", "2026-09-16": "3.75", "2026-09-17": "4", "2026-09-18": "4"}
        fred = FakeFred(obs={"DFEDTARU": obs})
        got = cx.resolve_actuals(fred, "fomc_rate_upper", [date(2026, 9, 16), date(2026, 10, 28)])
        self.assertEqual(got[date(2026, 9, 16)]["actual"], 4.0)
        self.assertIsNone(got[date(2026, 10, 28)])


def snap(ts, key, rt, source, consensus):
    return {"ts": T(ts), "rt": T(rt), "release_key": key, "source": source, "consensus": consensus}


class PointInTimeTest(unittest.TestCase):
    RT = "2026-09-24T12:30:00Z"

    def test_last_snapshot_strictly_before(self):
        snaps = [snap("2026-09-23T09:00:00Z", "jobless_claims", self.RT, "ff", 200.0),
                 snap("2026-09-24T12:29:59Z", "jobless_claims", self.RT, "ff", 201.0),
                 snap("2026-09-24T12:30:00Z", "jobless_claims", self.RT, "ff", 999.0),   # at release: excluded
                 snap("2026-09-24T14:00:00Z", "jobless_claims", self.RT, "ff", 555.0)]
        c, t = cx.point_in_time(snaps, "ff", T(self.RT))
        self.assertEqual((c, t), (201.0, T("2026-09-24T12:29:59Z")))

    def test_blank_consensus_falls_back_to_earlier(self):
        snaps = [snap("2026-09-22T09:00:00Z", "jobless_claims", self.RT, "ff", 200.0),
                 snap("2026-09-23T09:00:00Z", "jobless_claims", self.RT, "ff", None)]
        self.assertEqual(cx.point_in_time(snaps, "ff", T(self.RT))[0], 200.0)
        self.assertEqual(cx.point_in_time(snaps, "kalshi", T(self.RT)), (None, None))

    def test_build_uses_pre_release_snapshots_only(self):
        snaps = [snap("2026-09-23T09:00:00Z", "jobless_claims", self.RT, "ff", 201.0),
                 snap("2026-09-23T09:00:00Z", "jobless_claims", self.RT, "kalshi", 198.94),
                 snap("2026-09-24T14:00:00Z", "jobless_claims", self.RT, "kalshi", 250.0)]
        acts = {("jobless_claims", date(2026, 9, 24)): {"actual": 196.0, "actual_source": "x",
                                                        "reference_period": "2026-09-19"}}
        rows, stats = cx.build_surprises(snaps, [], T("2026-09-25T00:00:00Z"), None, acts)
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["consensus_ff"], r["consensus_kalshi"]), (201.0, 198.94))
        self.assertEqual((r["surprise_ff"], r["surprise_kalshi"]), (-5.0, -2.94))
        self.assertEqual(r["consensus_kalshi_asof"], "2026-09-23 09:00:00")
        self.assertEqual((r["date"], r["release_time_utc"]), ("2026-09-24", self.RT))

    def test_sources_meet_on_the_et_day_ff_time_wins(self):
        snaps = [snap("2026-09-23T09:00:00Z", "retail_sales_mom", "2026-09-24T14:00:00Z", "ff", 0.2),
                 snap("2026-09-23T09:00:00Z", "retail_sales_mom", "2026-09-24T12:30:00Z", "kalshi", 0.3)]
        acts = {("retail_sales_mom", date(2026, 9, 24)): {"actual": 0.5, "actual_source": "x", "reference_period": "r"}}
        rows, _ = cx.build_surprises(snaps, [], T("2026-09-25T00:00:00Z"), None, acts)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["release_time_utc"], "2026-09-24T14:00:00Z")
        self.assertEqual((rows[0]["surprise_ff"], rows[0]["surprise_kalshi"]), (0.3, 0.2))

    def test_pending_and_upcoming(self):
        snaps = [snap("2026-09-23T09:00:00Z", "jobless_claims", self.RT, "ff", 201.0),
                 snap("2026-09-23T09:00:00Z", "cpi_mom", "2026-10-14T12:30:00Z", "kalshi", 0.57),
                 snap("2026-09-24T13:00:00Z", "nfp", "2026-09-24T12:30:00Z", "ff", 50.0)]     # only after release
        now = T("2026-09-24T14:00:00Z")
        self.assertEqual(cx.pending_releases(snaps, [], now), {"jobless_claims": [date(2026, 9, 24)]})
        rows, stats = cx.build_surprises(snaps, [], now, None, {})
        self.assertEqual(rows, [])
        self.assertEqual(stats["actual pending"], 1)
        self.assertEqual(stats["upcoming"], 1)
        self.assertEqual(stats["no pre-release consensus"], 1)


class SurpriseZTest(unittest.TestCase):
    @staticmethod
    def rows(prefs, key="cpi_mom", both_at=None):
        out = []
        for i, p in enumerate(prefs):
            r = {"release_key": key, "release_time_utc": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}T12:30:00Z",
                 "surprise_ff": None, "surprise_kalshi": p}
            if both_at is not None and i == both_at:
                r["surprise_ff"] = p * 2
            out.append(r)
        return out

    def test_needs_eight_earlier(self):
        prefs = [0.1, -0.1, 0.2, 0.0, -0.2, 0.1, 0.0, -0.1, 0.3, -0.05]
        rows = self.rows(prefs)
        cx.assign_z(rows)
        self.assertEqual([r["z_n"] for r in rows], list(range(10)))
        self.assertTrue(all(r["surprise_z"] is None for r in rows[:8]))
        self.assertAlmostEqual(rows[8]["surprise_z"], round(0.3 / statistics.stdev(prefs[:8]), 3))
        self.assertAlmostEqual(rows[9]["surprise_z"], round(-0.05 / statistics.stdev(prefs[:9]), 3))
        self.assertEqual(rows[9]["z_source"], "kalshi")

    def test_ff_preferred_and_zero_sd(self):
        rows = self.rows([0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.1, -0.1, 0.2], both_at=8)
        cx.assign_z(rows)
        self.assertEqual(rows[8]["z_source"], "ff")
        self.assertAlmostEqual(rows[8]["surprise_z"], round(0.4 / statistics.stdev([0.1, -0.1] * 4), 3))
        flat = self.rows([0.0] * 9)
        cx.assign_z(flat)
        self.assertIsNone(flat[8]["surprise_z"])                     # sd 0: blank, not inf

    def test_keys_do_not_mix(self):
        rows = self.rows([0.1] * 4 + [0.2] * 4) + self.rows([5.0], key="nfp")
        cx.assign_z(rows)
        self.assertEqual(rows[-1]["z_n"], 0)


class IdempotenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = self.tmp.name

    def csv_rows(self, name):
        with open(os.path.join(self.dir, name), newline="") as fh:
            return list(csv.DictReader(fh))

    def test_snapshot_append_is_idempotent_and_last_wins(self):
        now = T("2026-09-22T09:00:00Z")
        rows, _ = cx.ff_snapshot_rows(TitleMappingTest.EVENTS, now)
        quiet(cx.write_snapshots, rows, self.dir)
        quiet(cx.write_snapshots, rows, self.dir)
        self.assertEqual(len(self.csv_rows(cx.CONSENSUS_FILE)), 1)
        later = [dict(rows[0], timestamp=T("2026-09-22T14:00:00Z"), consensus=205.0)]
        quiet(cx.write_snapshots, later, self.dir)
        got = self.csv_rows(cx.CONSENSUS_FILE)
        self.assertEqual(len(got), 1)                                      # same day: replaced
        self.assertEqual((got[0]["timestamp"], got[0]["consensus"]), ("2026-09-22 14:00:00", "205.0"))
        next_day = [dict(rows[0], timestamp=T("2026-09-23T09:00:00Z"), date="2026-09-23")]
        quiet(cx.write_snapshots, next_day, self.dir)
        self.assertEqual(len(self.csv_rows(cx.CONSENSUS_FILE)), 2)          # new day: appended
        self.assertEqual(list(self.csv_rows(cx.CONSENSUS_FILE)[0]), cx.CONSENSUS_COLUMNS)

    def test_merge_latest_timestamp_wins(self):
        live = cx._snapshot_row(T("2026-09-24T09:00:00Z"), "cpi_mom", T("2026-09-24T12:30:00Z"), "kalshi", 0.3, None,
                                "percent", {"method": "live"})
        backfill = cx._snapshot_row(T("2026-09-24T04:00:00Z"), "cpi_mom", T("2026-09-24T12:30:00Z"), "kalshi", 0.2,
                                    None, "percent", {"method": "candle_1440"})
        merged, changed = cx.merge_snapshot_rows([], [live])
        merged2, changed2 = cx.merge_snapshot_rows(merged, [backfill])     # older back-fill loses
        self.assertTrue(changed)
        self.assertFalse(changed2)
        self.assertEqual(merged2[0]["consensus"], "0.3")
        again, changed3 = cx.merge_snapshot_rows(merged2, [live, backfill])
        self.assertFalse(changed3)

    def test_run_surprises_twice_rewrites_nothing(self):
        snaps = [cx._snapshot_row(T("2026-09-03T09:00:00Z"), "nfp", T("2026-09-04T12:30:00Z"), "kalshi", 71.53, None,
                                  "thousands", {}),
                 cx._snapshot_row(T("2026-09-04T09:00:00Z"), "nfp", T("2026-09-04T12:30:00Z"), "ff", 75.0, 22.0,
                                  "thousands", {})]
        quiet(cx.write_snapshots, snaps, self.dir)
        fred = FakeFred(vint={"PAYEMS": PAYEMS})
        r1 = quiet(cx.run_surprises, self.dir, now=T("2026-09-05T00:00:00Z"), fred=fred)
        path = os.path.join(self.dir, cx.SURPRISES_FILE)
        with open(path, "rb") as fh:
            first = fh.read()
        r2 = quiet(cx.run_surprises, self.dir, now=T("2026-09-06T00:00:00Z"), fred=fred)
        with open(path, "rb") as fh:
            second = fh.read()
        self.assertTrue(r1["written"])
        self.assertFalse(r2["written"])
        self.assertEqual(first, second)
        self.assertEqual(fred.requests, 1)                                  # resolved rows never re-fetch
        row = self.csv_rows(cx.SURPRISES_FILE)[0]
        self.assertEqual(list(row), cx.SURPRISES_COLUMNS)
        self.assertEqual((row["actual"], row["consensus_ff"], row["surprise_ff"], row["surprise_kalshi"]),
                         ("175.0", "75.0", "100.0", "103.47"))
        self.assertEqual(row["timestamp"], "2026-09-05 00:00:00")


class BackfillHelpersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bf = _load_backfill()

    def test_snapshot_time_is_et_midnight(self):
        self.assertEqual(self.bf.snapshot_time(date(2026, 9, 11)), T("2026-09-11T04:00:00Z"))
        self.assertEqual(self.bf.snapshot_time(date(2026, 12, 10)), T("2026-12-10T05:00:00Z"))

    def test_pick_candle_never_after(self):
        cs = [{"end_period_ts": 100}, {"end_period_ts": 200}, {"end_period_ts": 300}]
        self.assertEqual(self.bf.pick_candle(cs, 200), ({"end_period_ts": 200}, True))
        self.assertEqual(self.bf.pick_candle(cs, 250), ({"end_period_ts": 200}, False))
        self.assertEqual(self.bf.pick_candle(cs, 50), (None, False))

    def test_candle_quote_both_tiers(self):
        hist = {"yes_bid": {"close": "0.2300"}, "yes_ask": {"close": "0.2500"}, "price": {"close": "0.2400"}}
        live = {"yes_bid": {"close_dollars": "0.9800"}, "yes_ask": {"close_dollars": "1.0000"},
                "price": {"previous_dollars": "0.9800"}}
        self.assertAlmostEqual(self.bf.candle_quote(hist)[0], 0.24)
        self.assertEqual(self.bf.candle_quote(live)[2], "mid")
        thin = {"yes_bid": {"close": "0.0000"}, "yes_ask": {"close": "0.0000"}, "price": {"previous": "0.3100"}}
        self.assertEqual(self.bf.candle_quote(thin)[:3], (0.31, cx.TRADE_WEIGHT, "prev"))

    def test_expiration_values(self):
        pe = self.bf.parse_expiration
        self.assertEqual(pe("1.2%", cx.RELEASES["retail_sales_mom"]), 1.2)
        self.assertEqual(pe("130,000", NFP), 130.0)
        self.assertEqual(pe("225,000,", CLAIMS), 225.0)
        self.assertEqual(pe(".9%", CPI), 0.9)
        self.assertEqual(pe("4.00%", FED), 4.0)
        self.assertIsNone(pe("Above 3.50%", FED))
        self.assertIsNone(pe("Yes", FED))

    def test_bracket_from_results(self):
        ms = [{"strike_type": "greater", "floor_strike": k, "result": r}
              for k, r in ((3.25, "yes"), (3.5, "yes"), (3.75, "no"), (4.0, "no"))]
        self.assertEqual(self.bf.bracket_value(ms, FED), 3.75)
        gap = [{"strike_type": "greater", "floor_strike": k, "result": r} for k, r in ((3.0, "yes"), (3.5, "no"))]
        self.assertIsNone(self.bf.bracket_value(gap, FED))


if __name__ == "__main__":
    unittest.main()
