#!/usr/bin/env python3
"""One-off: back-fill macro_consensus.csv and macro_surprises.csv from SETTLED Kalshi markets.

ForexFactory's feed only serves the current week, so the consensus log starts on the day the
snapshot collector is deployed. Kalshi keeps the price history of settled markets, so for every
settled event of each mapped series (data_extractors/consensus_extractors.RELEASES) this rebuilds
the market-implied consensus as of the day before the release and the surprise it implies.

WHICH PRICE, EXACTLY
--------------------
For an event released on ET day D, the snapshot time is T = 00:00 America/New_York on D (04:00
UTC in summer, 05:00 in winter) - the end of the ET day before the release, hours before any
08:30 or 14:00 ET print. Each market's daily candlesticks (period_interval=1440; Kalshi ends a
daily candle at ET midnight) are read for [T - 7 days, T]:
  * candle: the one whose end_period_ts == T; if that day has none, the latest candle ending
    before T (as-of, never after T); detail.asof_fallbacks counts the strikes priced that way.
  * price:  mid of yes_bid.close and yes_ask.close (the best YES bid/ask at the candle's end),
    when both exist, 0 <= bid <= ask <= 1, ask > 0 and ask - bid <= 0.50; otherwise price.close
    (last trade in that candle), then price.previous (last trade before it). A strike with none
    of these is dropped.
The historical tier (/historical/markets/{ticker}/candlesticks, markets settled before Kalshi's
/historical/cutoff) uses unsuffixed fields (close); the live tier (/series/{s}/markets/{t}/
candlesticks) uses *_dollars - both are read. The ladder -> consensus step is the collector's own
(consensus_extractors.ladder_consensus: interpolated median, >= 3 strikes, median inside the
ladder), so back-filled and live rows are the same quantity. Written rows: source 'kalshi',
timestamp = T, date = T's UTC day (= D), release_time_utc = D at the key's scheduled ET time,
detail.method = 'candle_1440'.

Release day D: the FRED/ALFRED first-release date of the event's reference period (parsed from
the event's sub_title: 'In Jul 2026', 'In Q2 2026', 'For the week ending Sep 12, 2026', legacy
'From Aug 22-28, 2021'), because close_time is not reliable for it (some events closed after the
print, the oldest the evening before). Fed events use the meeting date in the sub_title ('On Sep
16, 2026'), else the close time (Kalshi closes Fed markets 5 minutes before 14:00 ET).

Skipped (counted in the report): events with fewer than 3 threshold strikes (all of 2021's single-
strike markets, all legacy KXJOBLESS weeks), no reference period, a reference period FRED never
published (cancelled releases: October 2025 CPI, core CPI and unemployment), no candle as of T (e.g. a market
that closed on a release date the 2025 shutdown cancelled), a median outside the ladder, and
"superseded" events: a catch-up release after the Oct-Nov 2025 shutdown published several periods
on one day (payrolls Oct+Nov 2025 on 2025-12-16, PCE on 2026-01-22, PPI on 2026-01-14, eight claims
weeks on 2025-11-20); the newest period is that day's headline and the only one scored, so only its
event is kept. Surprise rows are then built by consensus_extractors.build_surprises from the merged
snapshot log (point-in-time rule, FRED first-release actuals, surprise_z).

VERIFICATION: every settled event's expiration_value (the value the agency published, which
Kalshi settles on) is compared with the FRED first-release actual of the event's OWN reference
period, computed the collector's way - for all settled events, including the ones skipped for
their ladder. A non-numeric expiration_value ('Yes', 'Above 3.50%') is replaced by the value the
markets' results bracket on the grid. Known source-side difference: KXGDP-25OCT30 (Q3 2025) was
settled on 2025-11-24 at 3.8 - Q2's value - because the shutdown cancelled the Oct-30 advance
release; BEA's first Q3 estimate (4.3) came out 2025-12-23, and that is the actual used.

Idempotent: snapshot rows merge on (date, release_key, release_time_utc, source) with the later
timestamp winning (a live snapshot of the same day beats the back-filled 00:00 ET one); surprise
rows merge per release; a second --apply writes nothing. Dry run by default. With --apply each
file is copied to .deploy_backup_20260922/data/ next to the data directory before its first
rewrite (the first, pristine copy is kept; a file that did not exist is recorded as absent - undo
by deleting it), written under the collectors' per-file lock (_csv_lock) via _atomic_to_csv, and
the run's report goes to .deploy_backup_20260922/kalshi_backfill_manifest.json.

Requests: Kalshi paced --pace seconds apart (default 0.34, about 3/s), ~5,000 GETs for the full
history (one per market candle series; live-tier events take one event-level call); settled data
never changes, so responses are cached in --cache-dir (default: $TMPDIR/kalshi_backfill_cache_
20260922) and an --apply after a dry run re-uses them. FRED: 2-3 ALFRED requests per key.

  python scripts/backfill_kalshi_consensus_20260922.py                          # dry run, all keys
  python scripts/backfill_kalshi_consensus_20260922.py --keys cpi_mom,nfp       # dry run, two keys
  python scripts/backfill_kalshi_consensus_20260922.py --apply
  python scripts/backfill_kalshi_consensus_20260922.py --data-dir /path/to/copy/historical_data --apply
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from data_extractors import consensus_extractors as cx  # noqa: E402

UTC = timezone.utc
BACKUP_TAG = ".deploy_backup_20260922"
MANIFEST = "kalshi_backfill_manifest.json"
CANDLE_PERIOD = 1440
LOOKBACK = timedelta(days=7)
PRICE_FIELD = ("mid(yes_bid.close, yes_ask.close) of the daily candle ending at 00:00 ET on the release "
               "day; else price.close, then price.previous")


def snapshot_time(release_day: date) -> datetime:
    """T: 00:00 America/New_York on the release day, in UTC."""
    return datetime(release_day.year, release_day.month, release_day.day, tzinfo=cx.ET).astimezone(UTC)


def _field(block, name):
    block = block or {}
    v = block.get(name)
    return cx._num(v if v is not None else block.get(name + "_dollars"))


def pick_candle(candles: list, t_end: int):
    """(candle, exact) - the candle ending exactly at t_end, else the latest ending before it; never later."""
    best = None
    for c in candles or []:
        end = c.get("end_period_ts")
        if end is None or end > t_end:
            continue
        if end == t_end:
            return c, True
        if best is None or end > best["end_period_ts"]:
            best = c
    return best, False


def candle_quote(c):
    """cx.quote_prob() from one candlestick (either tier's field names)."""
    if not c:
        return None
    return cx.quote_prob(_field(c.get("yes_bid"), "close"), _field(c.get("yes_ask"), "close"),
                         _field(c.get("price"), "close"), _field(c.get("price"), "previous"))


def parse_expiration(value, spec):
    """Kalshi's expiration_value -> canonical units, or None ('Yes', 'Above 3.50%', '0-0.25')."""
    s = str(value or "").strip().rstrip(",").replace(",", "").replace("%", "").strip()
    if s.startswith("."):
        s = "0" + s
    try:
        return round(float(s) * spec.kalshi_scale, 6)
    except ValueError:
        return None


def bracket_value(markets, spec):
    """The value the markets' results pin on the grid: (highest 'yes' above-strike, lowest 'no'] = one step."""
    lo = hi = None
    for m in markets:
        th = cx.market_threshold(m, spec)
        res = str(m.get("result") or "").lower()
        if th is None or not th[1] or res not in ("yes", "no"):
            continue
        t = th[0]
        if res == "yes":
            lo = t if lo is None else max(lo, t)
        else:
            hi = t if hi is None else min(hi, t)
    if lo is not None and hi is not None and abs((hi - lo) - spec.step) < 1e-6:
        return round(hi, 6)
    return None


def release_day_for(event, markets, spec, first_release):
    """(ET release day, how) or (None, why)."""
    ref = cx.kalshi_reference_period(event, spec)
    if spec.freq == "FOMC":
        if ref is not None:
            return ref, "sub_title date"
        rt = cx.kalshi_release_time(markets, spec)
        if rt is not None:
            return cx.et_date(rt), "close time"
        return None, "no meeting date"
    if ref is None:
        return None, "no reference period in sub_title"
    f = first_release.get(ref.isoformat())
    if f:
        return date.fromisoformat(f), "FRED first release"
    # Never published: the release was cancelled (October 2025 CPI and household survey, in the
    # shutdown). A consensus for a print that never happened would sit in the log unscorable.
    return None, "reference period never published (cancelled release)"


def event_candles(client, event, markets, tier, t_end):
    """{market ticker: [candles]} for [t_end - LOOKBACK, t_end]."""
    start = int((t_end - LOOKBACK).timestamp())
    end = int(t_end.timestamp())
    series = event.get("series_ticker") or ""
    if tier == "live" and series:
        d = client.get(f"/series/{series}/events/{event['event_ticker']}/candlesticks",
                       start_ts=start, end_ts=end, period_interval=CANDLE_PERIOD) or {}
        tickers, cands = d.get("market_tickers") or [], d.get("market_candlesticks") or []
        if tickers and len(tickers) == len(cands):
            return dict(zip(tickers, cands))
    return {m["ticker"]: client.market_candles(series, m["ticker"], start, end, tier, CANDLE_PERIOD)
            for m in markets if m.get("ticker")}


def plan(client, fred, keys):
    """Snapshot rows, per-key report and the per-event verification records."""
    rows, report, checks = [], {}, []
    for key in keys:
        spec = cx.RELEASES[key]
        rep = {"series": [s for s, _ in spec.kalshi], "events": 0, "rows": 0, "skipped": Counter(),
               "release_day_from": Counter(), "asof_fallback_strikes": 0, "first": None, "last": None}
        report[key] = rep
        first = vint = None
        if spec.actual.transform != "fomc_upper":
            vint = fred.vintages(spec.actual.series, date(2019, 1, 1), date(2020, 1, 1))
            first = cx.first_releases(vint)
        # Pass 1 (cheap): every settled event, its markets, reference period and release day.
        found = []
        for series, _live in spec.kalshi:
            for ev in client.events(series, "settled"):
                rep["events"] += 1
                markets, tier = client.event_markets(ev["event_ticker"])
                day, how = release_day_for(ev, markets, spec, first or {})
                if day is None:
                    rep["skipped"][how] += 1
                    continue
                ref = cx.kalshi_reference_period(ev, spec)
                raw = markets[0].get("expiration_value") if markets else None
                checks.append({"key": key, "event": ev["event_ticker"], "day": day, "ref": ref, "raw": raw,
                               "published": (parse_expiration(raw, spec) if parse_expiration(raw, spec) is not None
                                             else bracket_value(markets, spec)), "rows": vint, "first": first})
                found.append((day, ref or day, ev, markets, tier, how))
        # A catch-up release after the 2025 shutdown published two or more periods on one day (payrolls
        # Oct+Nov on 2025-12-16, eight claims weeks on 2025-11-20); the newest period is that day's
        # headline, and it is the only one resolve_actuals scores, so it is the only event kept.
        newest = {}
        for day, ref, *_ in found:
            newest[day] = max(newest.get(day, ref), ref)
        for day, ref, ev, markets, tier, how in sorted(found, key=lambda f: (f[0], f[1])):
            if ref != newest[day]:
                rep["skipped"]["superseded: a newer period was that day's headline"] += 1
                continue
            rep["release_day_from"][how] += 1
            strikes = {cx.market_threshold(m, spec) for m in markets} - {None}
            if len(strikes) < cx.MIN_STRIKES:
                rep["skipped"][f"fewer than {cx.MIN_STRIKES} strikes"] += 1
                continue
            t_end = snapshot_time(day)
            candles = event_candles(client, ev, markets, tier, t_end)
            items, fallbacks, used = [], 0, 0
            for m in markets:
                c, exact = pick_candle(candles.get(m.get("ticker")) or [], int(t_end.timestamp()))
                if c is not None:
                    used += 1
                    fallbacks += 0 if exact else 1
                extra = {"volume": cx._num((c or {}).get("volume")) or cx._num((c or {}).get("volume_fp")),
                         "oi": cx._num((c or {}).get("open_interest")) or cx._num((c or {}).get("open_interest_fp"))}
                items.append((m, candle_quote(c), extra))
            if not used:
                rep["skipped"]["no candle as of T"] += 1
                continue
            res = cx.ladder_consensus(items, spec)
            if not res["ok"]:
                rep["skipped"][res["reason"].split(" (")[0]] += 1
                continue
            rt = cx.release_at(day, spec.et_time)
            detail = {"event": ev["event_ticker"], "series": ev.get("series_ticker") or spec.kalshi[0][0],
                      "method": "candle_1440", "candle_end": cx.iso_z(t_end), "tier": tier,
                      "price_field": PRICE_FIELD, "asof_fallbacks": fallbacks, "release_day_from": how}
            detail.update(res["detail"])
            detail["volume_candle_day"] = detail.pop("volume")
            rows.append(cx._snapshot_row(t_end, key, rt, "kalshi", res["consensus"], None, spec.unit, detail))
            rep["rows"] += 1
            rep["asof_fallback_strikes"] += fallbacks
            rep["first"] = min(rep["first"] or day.isoformat(), day.isoformat())
            rep["last"] = max(rep["last"] or day.isoformat(), day.isoformat())
    return rows, report, checks


def verification(fred, checks):
    """{key: {...}} - each settled event's published value vs the FRED first release of ITS reference period."""
    out = {}
    fomc = defaultdict(list)
    for c in checks:
        if c["rows"] is None:
            fomc[c["key"]].append(c["day"])
    fomc_actuals = {k: cx.resolve_actuals(fred, k, days) for k, days in fomc.items()}
    for c in sorted(checks, key=lambda c: (c["key"], c["day"])):
        v = out.setdefault(c["key"], {"compared": 0, "equal": 0, "mismatches": [], "unresolved": 0,
                                      "no_published_value": 0})
        if c["rows"] is None:
            a = fomc_actuals[c["key"]].get(c["day"])
        else:
            a = cx.actual_for_obs(c["key"], c["rows"], c["first"], c["ref"].isoformat()) if c["ref"] else None
        if not a or a.get("actual") is None:
            v["unresolved"] += 1
            continue
        if c["published"] is None:
            v["no_published_value"] += 1
            continue
        v["compared"] += 1
        if abs(a["actual"] - c["published"]) < 1e-6:
            v["equal"] += 1
        else:
            v["mismatches"].append(f"{c['day']} {c['event']}: FRED {a['actual']} ({a['actual_source']}) "
                                   f"vs Kalshi {c['raw']!r}")
    return out


def _backup(path, backup_dir, manifest_files):
    os.makedirs(backup_dir, exist_ok=True)
    dst = os.path.join(backup_dir, os.path.basename(path))
    if os.path.exists(dst) or os.path.exists(dst + ".absent"):
        return
    if os.path.exists(path):
        shutil.copy2(path, dst)
        manifest_files[os.path.basename(path)] = f"backed up -> {dst}"
    else:
        open(dst + ".absent", "w").close()
        manifest_files[os.path.basename(path)] = "did not exist before the first --apply (undo: delete it)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write (default: dry run, report only)")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, "historical_data"),
                    help="directory holding macro_consensus.csv / macro_surprises.csv (default: the repo's historical_data/)")
    ap.add_argument("--keys", help="comma-separated release keys (default: every key with a Kalshi series)")
    ap.add_argument("--cache-dir", default=os.path.join(tempfile.gettempdir(), "kalshi_backfill_cache_20260922"))
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--pace", type=float, default=0.34, help="seconds between Kalshi requests (default 0.34)")
    a = ap.parse_args()

    keys = [k for k, s in cx.RELEASES.items() if s.kalshi]
    if a.keys:
        want = [k.strip() for k in a.keys.split(",") if k.strip()]
        unknown = [k for k in want if k not in cx.RELEASES or not cx.RELEASES[k].kalshi]
        if unknown:
            ap.error(f"no Kalshi series for {unknown}")
        keys = want
    data_dir = os.path.abspath(a.data_dir)
    if not os.path.isdir(data_dir):
        ap.error(f"{data_dir} does not exist")
    cpath, spath = os.path.join(data_dir, cx.CONSENSUS_FILE), os.path.join(data_dir, cx.SURPRISES_FILE)
    backup_dir = os.path.join(os.path.dirname(data_dir), BACKUP_TAG)

    client = cx.KalshiClient(min_interval=a.pace, cache_dir=None if a.no_cache else a.cache_dir)
    fred = cx.FredClient()
    now = datetime.now(UTC).replace(microsecond=0)
    try:
        rows, report, events = plan(client, fred, keys)
        checks = verification(fred, events)
    except cx.SourceError as e:
        print(f"  ❌ {e} - nothing written")
        return 2

    # Everything below is computed on the merged tables; with --apply they are re-read under the lock.
    merged, cons_changed = cx.merge_snapshot_rows(cx.read_rows(cpath), rows)
    snaps = cx.parse_snapshots(merged)
    todo = cx.pending_releases(snaps, cx.read_rows(spath), now)
    actuals = {}
    for key, days in sorted(todo.items()):
        for day, res in cx.resolve_actuals(fred, key, days).items():
            actuals[(key, day)] = res
    sur_rows, sur_stats = cx.build_surprises(snaps, cx.read_rows(spath), now, None, actuals)
    by_key = Counter(r["release_key"] for r in sur_rows)

    print(f"\n  Kalshi requests {client.requests} (cache hits {client.cache_hits}); FRED requests {fred.requests}")
    print(f"  {'key':18s} {'events':>6s} {'rows':>5s} {'surpr':>5s}  range                     skipped")
    for key in keys:
        r = report[key]
        rng = f"{r['first']} .. {r['last']}" if r["first"] else "-"
        sk = ", ".join(f"{k}: {v}" for k, v in r["skipped"].most_common())
        print(f"  {key:18s} {r['events']:6d} {r['rows']:5d} {by_key.get(key, 0):5d}  {rng:24s}  {sk}")
    print(f"  surprises: {dict(sur_stats)}")
    print("\n  Verification - FRED first-release actual vs the value Kalshi settled on (all settled events):")
    for key in keys:
        v = checks.get(key) or {}
        print(f"  {key:18s} {v.get('equal', 0)}/{v.get('compared', 0)} equal"
              + (f", {v['unresolved']} not on FRED or not computable" if v.get("unresolved") else "")
              + (f", {v['no_published_value']} without a published value" if v.get("no_published_value") else ""))
        for m in v.get("mismatches", []):
            print(f"      MISMATCH {m}")

    if not a.apply:
        print(f"\n  DRY RUN - would merge {len(rows)} snapshot row(s) into {cpath} "
              f"({'changes' if cons_changed else 'no change'}) and write {len(sur_rows)} surprise row(s); "
              f"re-run with --apply")
        return 0

    ehd = cx._ehd()
    manifest_files = {}
    with ehd._csv_lock(cpath):
        merged, changed = cx.merge_snapshot_rows(cx.read_rows(cpath), rows)
        if changed:
            _backup(cpath, os.path.join(backup_dir, "data"), manifest_files)
            cx.write_table(cpath, merged, cx.CONSENSUS_COLUMNS)
    snaps = cx.parse_snapshots(cx.read_rows(cpath))
    with ehd._csv_lock(spath):
        existing = cx.read_rows(spath)
        sur_rows, _ = cx.build_surprises(snaps, existing, now, None, actuals)
        sur_changed = cx.surprises_changed(sur_rows, existing)
        if sur_changed:
            _backup(spath, os.path.join(backup_dir, "data"), manifest_files)
            cx.write_table(spath, sur_rows, cx.SURPRISES_COLUMNS)
    for which in ("consensus", "surprises"):
        cx._declare(data_dir, which)
    if changed or sur_changed:
        mf = os.path.join(backup_dir, MANIFEST)
        runs = []
        if os.path.exists(mf):
            with open(mf) as fh:
                runs = json.load(fh)
        runs.append({"applied_at": cx.iso_z(now), "data_dir": data_dir, "keys": keys, "files": manifest_files,
                     "snapshot_rows_offered": len(rows), "consensus_rows": len(merged),
                     "surprise_rows": len(sur_rows), "price_field": PRICE_FIELD,
                     "report": {k: {**v, "skipped": dict(v["skipped"]), "release_day_from": dict(v["release_day_from"])}
                                for k, v in report.items()},
                     "verification": checks})
        os.makedirs(backup_dir, exist_ok=True)
        with open(mf, "w") as fh:
            json.dump(runs, fh, indent=1, default=str)
        print(f"\n  wrote {cpath} ({len(merged)} rows) and {spath} ({len(sur_rows)} rows); manifest -> {mf}")
    else:
        print("\n  nothing to write (already applied)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
