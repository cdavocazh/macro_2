#!/usr/bin/env python3
"""One-off: split the two ADP cadences apart, and turn earnings_calendar.csv into a keyed log.

adp_employment.csv
    Held two FRED series. Rows to 2026-01-17 came from the WEEKLY series ADPWNUSNERSA
    (week-ending Saturdays); on 2026-03-09 get_adp_employment() was switched to the MONTHLY
    series ADPMNUSNERSA (dated the 1st) and its 200 rows (2010-01 -> 2026-08) were merged
    into the same file. Checked against FRED on 2026-09-21: all 810 non-1st rows equal
    ADPWNUSNERSA exactly, all 200 1st-of-month rows equal ADPMNUSNERSA exactly. 28 monthly
    rows fall on a Saturday; 27 of those dates are also ADPWNUSNERSA weeks, and all 27 hold
    the monthly value (the monthly write replaced the weekly one), so "dated the 1st"
    identifies a monthly row.
    The feed scanner read the mix as a 7-day series gone stale ("stale 51d").
    -> adp_employment.csv keeps the monthly rows, labelled series_id=ADPMNUSNERSA;
       the weekly rows move to adp_employment_weekly.csv (column adp_employment_weekly,
       series_id=ADPWNUSNERSA). Rows already in that file win: they are a newer FRED
       vintage. Nothing is dropped; the collector back-fills the 27 weekly values the
       monthly rows had displaced on its next run.

earnings_calendar.csv
    Each run appended its 10 rows verbatim as `symbol,date,extraction_date`, date being the
    REPORT date: 6,720 rows for 1,470 distinct (extraction day, symbol) facts, read by the
    scanner as 1,036 conflicting repeat-dates and 671 out-of-order rows.
    -> rewritten as the snapshot log extract_earnings_calendar() now writes,
       `timestamp,date,symbol,report_date,source`, one row per (date = as-of day, symbol),
       the day's LAST run winning (the file is in append order). 17 same-day values are
       superseded that way; 16 were report dates already in the past that the provider
       rolled to the next quarter later that day, one (AVGO, 2026-08-03) an estimate that
       moved from 09-03 to 09-02. The original is kept in the backup.

Code from before 2026-09-21 writing to the repaired files
    A stray old-code run (one that started before the new code was copied in) or a
    code-only rollback leaves two recognisable states, and this script repairs both:
      * adp_employment.csv rows with a blank series_id — old append_to_csv rewrites every
        row it fetched without the label. Old code fetches ADPMNUSNERSA, so those rows are
        on the 1st and are relabelled; any unlabelled Saturday row is moved to the weekly
        file exactly as above.
      * earnings_calendar.csv with a trailing extraction_date column — old code appends
        its `symbol,date,extraction_date` rows (no timestamp) after the snapshot log. They
        are converted like the legacy file and folded in, the later run winning per day.

--rollback (use it when rolling the code back to before 2026-09-21)
    Puts both files back in the layouts the old code writes, without losing anything:
      * earnings_calendar.csv -> `symbol,date,extraction_date`, one row per (day, symbol)
        (every row the old code wrote came from the yfinance fallback, so no source is lost);
      * adp_employment.csv -> `timestamp,date,adp_employment`, still monthly-only (the old
        code fetches ADPMNUSNERSA, so it keeps the file monthly; the label is re-derived
        from the date grid on the way back).
    adp_employment_weekly.csv is left in place; old code ignores it. Re-running this script
    without --rollback when the new code goes back in restores the new layouts, folding in
    whatever the old code appended meanwhile. This script only needs helpers that both code
    versions have, so it runs before or after the code is swapped.

Dry run by default. With --apply each file is copied to .deploy_backup_20260921/data/ (next
to the data directory, i.e. the repo root for historical_data/) before it is rewritten —
the first copy keeps the plain name, later ones get a UTC time suffix — under the per-file
lock the collectors take, via an atomic replace. A second --apply is a no-op.

  python scripts/repair_adp_earnings_20260921.py
  python scripts/repair_adp_earnings_20260921.py --apply
  python scripts/repair_adp_earnings_20260921.py --data-dir /path/to/copy/historical_data --apply
  python scripts/repair_adp_earnings_20260921.py --rollback --apply
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

# Only helpers that exist both before and after the 2026-09-21 change, so the script also
# runs after a code rollback.
import extract_historical_data as ehd  # noqa: E402
from extract_historical_data import OUTPUT_DIR, _atomic_to_csv, _csv_lock  # noqa: E402

MONTHLY_ID, WEEKLY_ID = "ADPMNUSNERSA", "ADPWNUSNERSA"
ADP, ADP_WEEKLY, EARNINGS = "adp_employment.csv", "adp_employment_weekly.csv", "earnings_calendar.csv"
ADP_LEGACY_COLS = ["timestamp", "date", "adp_employment"]
ADP_COLS = ADP_LEGACY_COLS + ["series_id"]
ADP_WEEKLY_COLS = ["timestamp", "date", "adp_employment_weekly", "series_id"]
LEGACY_EARNINGS_COLS = ["symbol", "date", "extraction_date"]
EARNINGS_CALENDAR_COLUMNS = ["timestamp", "date", "symbol", "report_date", "source"]
# The snapshot log with old-code rows appended after it (pd.concat adds the new column last).
MIXED_EARNINGS_COLS = EARNINGS_CALENDAR_COLUMNS + ["extraction_date"]
assert getattr(ehd, "EARNINGS_CALENDAR_COLUMNS", EARNINGS_CALENDAR_COLUMNS) == EARNINGS_CALENDAR_COLUMNS

APPLY = False
BACKUP_DIR = ""


def _read(path: str) -> pd.DataFrame:
    # Everything as text: values are written back byte-for-byte, whatever pandas version.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _backup(path: str) -> None:
    """Copy `path` into BACKUP_DIR before it is rewritten. The first copy keeps the plain
    name (the pristine pre-repair file); a later rewrite of different content — a repair
    after a stray old-code run, or a rollback — gets a UTC time suffix instead."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    dst = os.path.join(BACKUP_DIR, os.path.basename(path))
    if os.path.exists(dst):
        if filecmp.cmp(path, dst, shallow=False):
            print(f"    backup already present: {dst}")
            return
        dst = f"{dst}.{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    shutil.copy2(path, dst)
    print(f"    backed up -> {dst}")


def _days(col: pd.Series) -> pd.Series:
    return pd.to_datetime(col.str.slice(0, 10), errors="coerce", format="%Y-%m-%d")


def _by_day(df: pd.DataFrame) -> pd.DataFrame:
    return (df.assign(_day=_days(df["timestamp"])).sort_values("_day", kind="stable")
            .drop(columns="_day").reset_index(drop=True))


# ── ADP ──────────────────────────────────────────────────────────────────────

def repair_adp(data_dir: str) -> bool:
    src = os.path.join(data_dir, ADP)
    dst = os.path.join(data_dir, ADP_WEEKLY)
    if not os.path.exists(src):
        print(f"  {ADP}: not present — nothing to do")
        return False
    with _csv_lock(src), _csv_lock(dst):
        d = _read(src)
        cols = list(d.columns)
        legacy = cols == ADP_LEGACY_COLS
        if legacy:
            d = d.assign(series_id="")
        elif cols != ADP_COLS:
            raise SystemExit(f"{ADP}: unexpected columns {cols} — inspect by hand")
        labels = d["series_id"].str.strip()
        blank = labels == ""
        foreign = ~blank & (labels != MONTHLY_ID)
        if foreign.any():
            raise SystemExit(f"{ADP}: {int(foreign.sum())} row(s) labelled {sorted(set(labels[foreign]))}, "
                             f"not {MONTHLY_ID} — inspect by hand")
        ts = _days(d["timestamp"])
        if ts.isna().any() or (ts != _days(d["date"])).any():
            raise SystemExit(f"{ADP}: unparseable timestamps or timestamp != date — inspect by hand")
        monthly = ts.dt.day == 1
        if (~blank & ~monthly).any():
            raise SystemExit(f"{ADP}: {int((~blank & ~monthly).sum())} {MONTHLY_ID} row(s) not dated the 1st "
                             f"— inspect by hand")
        if ts[monthly].dt.to_period("M").duplicated().any():
            raise SystemExit(f"{ADP}: two monthly rows in one month — inspect by hand")
        if not blank.any():
            print(f"  {ADP}: already split ({len(d)} rows, all {MONTHLY_ID}) — no change")
            return False

        # Unlabelled rows: classified by date grid. The 1st is monthly (28 of those are
        # Saturdays; the 27 that coincide with a weekly observation hold the monthly
        # value); any other Saturday is a week-ending ADPWNUSNERSA observation.
        weekly = blank & ~monthly & (ts.dt.dayofweek == 5)
        stray = blank & ~monthly & ~weekly
        if stray.any():
            raise SystemExit(f"{ADP}: {int(stray.sum())} row(s) on neither the monthly (1st) nor the weekly "
                             f"(Saturday) grid, e.g. {d.loc[stray, 'date'].iloc[0]} — inspect by hand")
        ambiguous = blank & monthly & (ts.dt.dayofweek == 5)
        m = _by_day(d[monthly].assign(series_id=MONTHLY_ID)[ADP_COLS])
        w = (d[weekly].rename(columns={"adp_employment": "adp_employment_weekly"})
             .assign(series_id=WEEKLY_ID)[ADP_WEEKLY_COLS])
        if legacy:
            wk = f" ({w['date'].min()} -> {w['date'].max()})" if len(w) else ""
            print(f"  {ADP}: {len(d)} rows (pre-2026-09-21 layout) = {len(m)} monthly {MONTHLY_ID} "
                  f"({m['date'].min()} -> {m['date'].max()}) + {len(w)} weekly {WEEKLY_ID}{wk}")
        else:
            print(f"  {ADP}: {int(blank.sum())} of {len(d)} rows have no series_id (written by pre-2026-09-21 "
                  f"code after the split): {int((blank & monthly).sum())} dated the 1st relabelled {MONTHLY_ID}, "
                  f"{len(w)} Saturday row(s) moved to {ADP_WEEKLY}")
        if ambiguous.any():
            print(f"    {int(ambiguous.sum())} Saturday-the-1st date(s) stay monthly (they hold the monthly value)")

        existing_w = None
        if os.path.exists(dst):
            existing_w = _read(dst)
            if list(existing_w.columns) != ADP_WEEKLY_COLS or (existing_w["series_id"] != WEEKLY_ID).any():
                raise SystemExit(f"{ADP_WEEKLY}: exists but is not a clean {WEEKLY_ID} file — inspect by hand")
            known = set(_days(existing_w["timestamp"]))
            w_new = w[~_days(w["timestamp"]).isin(known)]
            if len(w):
                print(f"    {ADP_WEEKLY} exists ({len(existing_w)} rows): {len(w) - len(w_new)} of these week(s) "
                      f"already there (kept as is), {len(w_new)} added")
            w = pd.concat([existing_w, w_new], ignore_index=True)
            write_w = len(w_new) > 0
        else:
            write_w = len(w) > 0
        w = _by_day(w)

        if not APPLY:
            print(f"    would write {ADP} ({len(m)} rows)" + (f" and {ADP_WEEKLY} ({len(w)} rows)" if write_w else ""))
            return True
        # Weekly first: if anything stops between the two writes, the source still holds
        # every weekly row and a re-run completes the split.
        if write_w:
            if existing_w is not None:
                _backup(dst)
            _atomic_to_csv(w, dst)
        _backup(src)
        _atomic_to_csv(m, src)
        print(f"    wrote {ADP} ({len(m)} rows)" + (f" and {ADP_WEEKLY} ({len(w)} rows)" if write_w else ""))
        return True


# ── earnings calendar ────────────────────────────────────────────────────────

def _from_legacy(d: pd.DataFrame) -> pd.DataFrame:
    """`symbol,date=report date,extraction_date` rows -> snapshot-log rows."""
    asof = _days(d["extraction_date"])
    if asof.isna().any():
        raise SystemExit(f"{EARNINGS}: unparseable extraction_date — inspect by hand")
    return pd.DataFrame({
        "timestamp": d["extraction_date"].str.slice(0, 10),
        "date": d["extraction_date"].str.slice(0, 10),
        "symbol": d["symbol"].str.strip().str.upper(),
        "report_date": d["date"].str.slice(0, 10),
        # the only provider that ever answered: Finviz rows would carry report_date/name/eps columns
        "source": "yfinance",
    }, index=d.index)


def _earnings_log(d: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Any layout this script knows -> snapshot-log rows in file (= append) order."""
    cols = list(d.columns)
    if cols == LEGACY_EARNINGS_COLS:
        log, layout = _from_legacy(d), "pre-2026-09-21 layout"
    elif cols == EARNINGS_CALENDAR_COLUMNS:
        log, layout = d, "snapshot log"
    elif cols == MIXED_EARNINGS_COLS:
        old = d["timestamp"].str.strip() == ""
        # Old code only ever APPENDS, and new code refuses to write to this layout, so
        # its rows form one trailing block after the snapshot log.
        if not old.any() or (old.cummax() != old).any():
            raise SystemExit(f"{EARNINGS}: rows without a timestamp are not one trailing block — inspect by hand")
        if (d.loc[~old, "extraction_date"] != "").any() or (d.loc[old, "extraction_date"] == "").any() \
                or (d.loc[old, ["report_date", "source"]] != "").any().any():
            raise SystemExit(f"{EARNINGS}: mixed rows do not look like old-code appends — inspect by hand")
        log = pd.concat([d.loc[~old, EARNINGS_CALENDAR_COLUMNS],
                         _from_legacy(d.loc[old, LEGACY_EARNINGS_COLS])])
        layout = f"snapshot log + {int(old.sum())} row(s) appended by pre-2026-09-21 code"
    else:
        raise SystemExit(f"{EARNINGS}: unexpected columns {cols} — inspect by hand")
    if not _days(log["date"]).is_monotonic_increasing:
        # Last-run-wins below relies on the rows being in append order.
        raise SystemExit(f"{EARNINGS}: as-of dates not in append order — inspect by hand")
    usable = (log["symbol"] != "") & _days(log["report_date"]).notna()
    if not usable.all():
        # The collector never writes these; drop them as it would (the backup keeps them).
        print(f"    dropping {int((~usable).sum())} row(s) with a blank symbol or unparseable report date")
        log = log[usable]
    return log.reset_index(drop=True), layout


def _keyed(log: pd.DataFrame) -> pd.DataFrame:
    # Same key and order as the collector (subset ['timestamp','symbol'], sort_by ['timestamp','symbol']).
    k = log.drop_duplicates(["date", "symbol"], keep="last")
    return (k.assign(_day=_days(k["date"])).sort_values(["_day", "symbol"], kind="stable")
            .drop(columns="_day").reset_index(drop=True)[EARNINGS_CALENDAR_COLUMNS])


def repair_earnings(data_dir: str) -> bool:
    src = os.path.join(data_dir, EARNINGS)
    if not os.path.exists(src):
        print(f"  {EARNINGS}: not present — nothing to do")
        return False
    with _csv_lock(src):
        d = _read(src)
        log, layout = _earnings_log(d)
        out = _keyed(log)
        if list(d.columns) == EARNINGS_CALENDAR_COLUMNS and out.equals(d):
            print(f"  {EARNINGS}: already a keyed snapshot log ({len(d)} rows, one per (date, symbol)) — no change")
            return False

        kept = out.set_index(["date", "symbol"])["report_date"]
        joined = log.join(kept.rename("kept"), on=["date", "symbol"])
        superseded = joined[joined["report_date"] != joined["kept"]].drop_duplicates()
        past = int((_days(superseded["report_date"]) <= _days(superseded["date"])).sum())
        print(f"  {EARNINGS}: {len(d)} rows ({layout}) -> {len(out)} rows, one per (as-of date, symbol); "
              f"{out['date'].nunique()} as-of days {out['date'].min()} -> {out['date'].max()}, "
              f"{out['symbol'].nunique()} symbols")
        if len(superseded):
            print(f"    {len(superseded)} same-day value(s) superseded by that day's later run "
                  f"({past} of them a report date already past)")
        if not APPLY:
            print(f"    would write {EARNINGS} ({len(out)} rows, columns {EARNINGS_CALENDAR_COLUMNS})")
            return True
        _backup(src)
        _atomic_to_csv(out, src)
        print(f"    wrote {EARNINGS} ({len(out)} rows)")
        return True


def rollback_adp(data_dir: str) -> bool:
    src = os.path.join(data_dir, ADP)
    if not os.path.exists(src):
        print(f"  {ADP}: not present — nothing to do")
        return False
    with _csv_lock(src):
        d = _read(src)
        cols = list(d.columns)
        if cols == ADP_LEGACY_COLS:
            print(f"  {ADP}: already in the pre-2026-09-21 layout ({len(d)} rows) — no change")
            return False
        if cols != ADP_COLS:
            raise SystemExit(f"{ADP}: unexpected columns {cols} — inspect by hand")
        labels = d["series_id"].str.strip()
        ts = _days(d["timestamp"])
        # Old code cannot tell the series apart, so only a clean monthly file goes back.
        if not labels.isin([MONTHLY_ID, ""]).all() or ts.isna().any() or (ts.dt.day != 1).any():
            raise SystemExit(f"{ADP}: not a clean {MONTHLY_ID} file — inspect by hand")
        print(f"  {ADP}: {len(d)} monthly rows -> pre-2026-09-21 layout {ADP_LEGACY_COLS} "
              f"(series_id dropped; re-derived from the 1st-of-month dates on re-deploy)")
        print(f"  {ADP_WEEKLY}: left in place (old code ignores it)")
        if not APPLY:
            print(f"    would write {ADP} ({len(d)} rows)")
            return True
        _backup(src)
        _atomic_to_csv(d[ADP_LEGACY_COLS], src)
        print(f"    wrote {ADP} ({len(d)} rows)")
        return True


def rollback_earnings(data_dir: str) -> bool:
    src = os.path.join(data_dir, EARNINGS)
    if not os.path.exists(src):
        print(f"  {EARNINGS}: not present — nothing to do")
        return False
    with _csv_lock(src):
        d = _read(src)
        if list(d.columns) == LEGACY_EARNINGS_COLS:
            print(f"  {EARNINGS}: already in the pre-2026-09-21 layout ({len(d)} rows) — no change")
            return False
        log, layout = _earnings_log(d)
        out = _keyed(log)
        other = sorted(set(out["source"]) - {"yfinance"})
        if other:
            # The old layout has no source column and old code wrote Finviz rows with other
            # columns, so these rows cannot go back into it without losing their provider.
            raise SystemExit(f"{EARNINGS}: {int(out['source'].isin(other).sum())} row(s) from {other} — "
                             f"the pre-2026-09-21 layout cannot hold them; inspect by hand")
        legacy = pd.DataFrame({"symbol": out["symbol"], "date": out["report_date"],
                               "extraction_date": out["date"]})
        print(f"  {EARNINGS}: {len(d)} rows ({layout}) -> {len(legacy)} rows in the pre-2026-09-21 layout "
              f"{LEGACY_EARNINGS_COLS}, one per (extraction day, symbol), "
              f"{out['date'].min()} -> {out['date'].max()}")
        if not APPLY:
            print(f"    would write {EARNINGS} ({len(legacy)} rows)")
            return True
        _backup(src)
        _atomic_to_csv(legacy, src)
        print(f"    wrote {EARNINGS} ({len(legacy)} rows)")
        return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    ap.add_argument("--rollback", action="store_true",
                    help="put both files back in the pre-2026-09-21 layouts, for a code rollback")
    ap.add_argument("--data-dir", default=os.path.join(ROOT, OUTPUT_DIR),
                    help="directory holding the CSVs (default: this repo's historical_data/)")
    a = ap.parse_args()
    global APPLY, BACKUP_DIR
    APPLY = a.apply
    data_dir = os.path.abspath(a.data_dir)
    BACKUP_DIR = os.path.join(os.path.dirname(data_dir), ".deploy_backup_20260921", "data")
    mode = ("APPLY" if APPLY else "DRY RUN") + (" --rollback" if a.rollback else "")
    print(f"[repair_adp_earnings_20260921] {mode} on {data_dir}")
    if a.rollback:
        changed = [rollback_adp(data_dir), rollback_earnings(data_dir)]
    else:
        changed = [repair_adp(data_dir), repair_earnings(data_dir)]
    if not APPLY and any(changed):
        print("DRY RUN — re-run with --apply")
    elif not any(changed):
        print("nothing to do")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
