"""Macro catalyst calendar extractor.

Builds a forward-looking schedule of US macro releases (CPI, PPI, NFP, GDP, PCE,
ISM, JOLTS, retail sales, consumer sentiment) from the FRED `/release/dates`
API, plus FOMC meeting dates scraped from federalreserve.gov.

Output: `historical_data/macro_catalyst_calendar.csv`
Schema: date, event_type, release_name, importance, source

Consumed by `Finl_Agent_CC/tools/option_strategy.py` to add non-earnings
catalyst events to the earnings-veto logic when scoring sell-vol strategies.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import List, Dict

import pandas as pd
import requests

import config

# FRED release IDs for the macro events that move equity vol.
# Source: https://fred.stlouisfed.org/releases — VERIFY BY NAME via
#   GET /fred/release?release_id=<id>   before adding or changing an entry.
# The previous map was wrong for 9 of 10 entries (11 was the Employment COST
# Index, 21 was M2 money stock, 200 was CBOE statistics, 197 was the Dow Jones
# Averages, ...); only CPI=10 was right. Caught 2026-09-09 when NFP returned 20
# dates in five years. Consumer Sentiment (UMich) is not a FRED release and was
# dropped rather than mapped to something that merely sounds similar.
# cadence_days is the fallback projection gap, used only when FRED has no
# scheduled dates for the window (30 = monthly, 90 = quarterly, 28 = NFP).
FRED_RELEASES = {
    10:  ("CPI",                       "high", 30),
    50:  ("Employment Situation",      "high", 28),    # NFP, first Friday
    53:  ("GDP",                       "high", 90),    # quarterly
    46:  ("PPI",                       "med",  30),
    54:  ("Personal Income & Outlays", "high", 30),    # PCE
    192: ("JOLTS",                     "med",  30),
    9:   ("Retail Sales",              "med",  30),    # Advance Monthly Sales
    13:  ("Industrial Production",     "low",  30),    # G.17
    27:  ("Housing Starts",            "low",  30),    # New Residential Construction
}

FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FRED_API_BASE = "https://api.stlouisfed.org/fred"


def _fred_dates(release_id: int, start: str, end: str, include_no_data: bool) -> list[str]:
    """Raw release dates for one FRED release inside [start, end]."""
    params = {
        "release_id": release_id,
        "api_key": config.FRED_API_KEY,
        "file_type": "json",
        "include_release_dates_with_no_data": "true" if include_no_data else "false",
        "limit": 10000,
        "realtime_start": start,
        "realtime_end": end,
        "sort_order": "asc",
    }
    r = requests.get(f"{FRED_API_BASE}/release/dates", params=params, timeout=30)
    r.raise_for_status()
    return sorted({e["date"] for e in r.json().get("release_dates", []) if e.get("date")})


def _first_per_month(dates: list[str]) -> list[str]:
    """Keep the earliest date in each month — the original print; later
    same-month dates are revisions or re-releases."""
    by_month: dict[str, str] = {}
    for d in sorted(dates):
        by_month.setdefault(d[:7], d)
    return sorted(by_month.values())


def _fred_release_history(release_id: int, since: str) -> list[str]:
    """Actual historical release dates (originals only) since `since`."""
    today = dt.date.today().isoformat()
    return [d for d in _first_per_month(_fred_dates(release_id, since, today, False)) if d < today]


def _fred_release_dates(release_id: int, cadence_days: int, days_ahead: int = 180) -> list[str]:
    """Upcoming release dates (YYYY-MM-DD).

    FRED publishes each release's schedule, and `/release/dates` returns those
    future dates when `include_release_dates_with_no_data=true`. That is used
    first. Only when FRED has nothing scheduled inside the window does this
    fall back to projecting forward from the last actual print at
    `cadence_days` — the old behaviour, which produced dates like a Housing
    Starts print on July 4th.
    """
    today = dt.date.today()
    end = today + dt.timedelta(days=days_ahead)

    try:
        scheduled = _fred_dates(release_id, today.isoformat(), end.isoformat(), True)
    except Exception:
        scheduled = []
    scheduled = [d for d in _first_per_month(scheduled) if d >= today.isoformat()]
    if scheduled:
        return scheduled

    history = _fred_dates(release_id, (today - dt.timedelta(days=400)).isoformat(),
                          today.isoformat(), False)
    originals = _first_per_month(history)
    if not originals:
        return []
    last_release = dt.datetime.strptime(originals[-1], "%Y-%m-%d").date()

    out: list[str] = []
    cur = last_release
    while True:
        cur = cur + dt.timedelta(days=cadence_days)
        if cur > end:
            break
        if cur >= today:
            out.append(cur.isoformat())
    return out


def _scrape_fomc_meetings(include_past: bool = False) -> list[str]:
    """Scrape FOMC meeting dates from federalreserve.gov.

    The page lists meetings as "Month DD-DD" or "Month DD" — we take the last
    day of multi-day meetings (the rate-decision day) since that's when vol
    spikes. Returns YYYY-MM-DD strings, future dates only.
    """
    today = dt.date.today()
    try:
        r = requests.get(FOMC_CALENDAR_URL, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 (macro_2 calendar)"})
        r.raise_for_status()
    except Exception:
        return []

    text = r.text
    # Match patterns like "January 28-29" within fomc-meeting blocks. The page
    # has month names in <div class="fomc-meeting__month"> and days in
    # <div class="fomc-meeting__date">. We do regex-based tolerant extraction
    # for the next 24 months.
    months = ["January","February","March","April","May","June",
              "July","August","September","October","November","December"]
    month_re = "|".join(months)
    out: list[str] = []

    # The Fed page renders pairs like:
    #   fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>March</strong></div>
    #   fomc-meeting__date  col-xs-4 col-sm-9 col-md-10 col-lg-1">17-18*</div>
    block_re = re.compile(
        r'fomc-meeting__month[^>]*>\s*(?:<strong>)?\s*(' + month_re + r')\s*(?:</strong>)?'
        r'.*?fomc-meeting__date[^>]*>([^<]+)<',
        re.DOTALL | re.IGNORECASE,
    )

    # Year headers — match "<h3>2026 FOMC Meetings" or similar containing the year
    year_positions = [(int(m.group(1)), m.start())
                      for m in re.finditer(r'>\s*(20\d\d)\s+FOMC Meetings\s*<', text)]
    if not year_positions:
        year_positions = [(today.year, 0)]

    for m in block_re.finditer(text):
        month_name = m.group(1).strip().capitalize()
        day_part = m.group(2).strip()
        pos = m.start()
        year = year_positions[0][0]
        for yr, ypos in year_positions:
            if ypos <= pos:
                year = yr
        # Extract last day from "28-29*" or "29"
        days = re.findall(r"\d+", day_part)
        if not days:
            continue
        last_day = int(days[-1])
        try:
            date_obj = dt.date(year, months.index(month_name) + 1, last_day)
        except ValueError:
            continue
        if include_past or date_obj >= today:
            out.append(date_obj.isoformat())
    return sorted(set(out))


def _fomc_minutes_dates() -> list[str]:
    """Past FOMC decision dates from the minutes links on the calendars page.

    Every meeting's minutes are linked as fomcminutes<YYYYMMDD>.htm, where the
    date is the meeting's final (decision) day. The page carries these back to
    2021, so it is a clean historical source — unlike FRED release 101 ("FOMC
    Press Release"), which emits a date on the 1st of every month and cannot
    distinguish meetings from other Board releases.
    """
    try:
        r = requests.get(FOMC_CALENDAR_URL, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0 (macro_2 calendar)"})
        r.raise_for_status()
    except Exception:
        return []
    out = set()
    for ymd in re.findall(r"fomcminutes(\d{8})\.htm", r.text):
        try:
            out.add(dt.datetime.strptime(ymd, "%Y%m%d").date().isoformat())
        except ValueError:
            continue
    return sorted(out)


def build_event_history(since: str) -> dict[str, list[str]]:
    """{event name: [actual past dates]} for every tracked release + FOMC."""
    history: dict[str, list[str]] = {}
    for rid, (name, _imp, _cad) in FRED_RELEASES.items():
        try:
            history[name] = _fred_release_history(rid, since)
        except Exception as e:
            print(f"  WARN: FRED history for {rid} ({name}) failed: {e}")
    try:
        today = dt.date.today().isoformat()
        fomc = set(_fomc_minutes_dates()) | set(_scrape_fomc_meetings(include_past=True))
        history["FOMC Meeting (rate decision)"] = sorted(d for d in fomc if since <= d < today)
    except Exception as e:
        print(f"  WARN: FOMC history failed: {e}")
    return history


def build_calendar(days_ahead: int = 180) -> pd.DataFrame:
    """Assemble the full forward calendar."""
    rows: list[dict] = []
    today = dt.date.today().isoformat()

    # FRED economic releases
    for rid, (name, importance, cadence) in FRED_RELEASES.items():
        try:
            for d in _fred_release_dates(rid, cadence_days=cadence, days_ahead=days_ahead):
                rows.append({
                    "date": d,
                    "event_type": "macro_release",
                    "release_name": name,
                    "importance": importance,
                    "source": f"FRED:{rid}",
                })
        except Exception as e:
            print(f"  WARN: FRED release {rid} ({name}) failed: {e}")

    # FOMC meetings
    try:
        for d in _scrape_fomc_meetings():
            rows.append({
                "date": d,
                "event_type": "fomc_meeting",
                "release_name": "FOMC Meeting (rate decision)",
                "importance": "high",
                "source": "federalreserve.gov",
            })
    except Exception as e:
        print(f"  WARN: FOMC scrape failed: {e}")

    if not rows:
        return pd.DataFrame(columns=["date", "event_type", "release_name", "importance", "source"])

    df = pd.DataFrame(rows)
    df = df.sort_values(["date", "importance"]).reset_index(drop=True)
    return df


def refresh_calendar(out_dir: str | Path = "historical_data") -> Path:
    """Rebuild the calendar CSV and the event-history JSON.

    The CSV holds the last year of ACTUAL release dates plus the scheduled
    forward window. It is regenerated, not merged: the old append-only merge
    preserved past rows that were cadence projections under wrong release ids,
    so "history" accumulated dates that never happened.

    The JSON (`macro_event_history.json`) holds five years of actual dates per
    event and is what the dashboard's event study reads.
    """
    import json

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "macro_catalyst_calendar.csv"
    hist_path = out_dir / "macro_event_history.json"

    today = dt.date.today()
    since = (today - dt.timedelta(days=5 * 365)).isoformat()
    year_ago = (today - dt.timedelta(days=365)).isoformat()

    history = build_event_history(since)
    new_df = build_calendar(days_ahead=180)

    meta = {name: (imp, f"FRED:{rid}") for rid, (name, imp, _c) in FRED_RELEASES.items()}
    meta["FOMC Meeting (rate decision)"] = ("high", "federalreserve.gov")
    past_rows = [{
        "date": d,
        "event_type": "fomc_meeting" if name.startswith("FOMC") else "macro_release",
        "release_name": name,
        "importance": meta[name][0],
        "source": meta[name][1],
    } for name, dates in history.items() if name in meta for d in dates if d >= year_ago]

    merged = pd.concat([pd.DataFrame(past_rows), new_df], ignore_index=True)
    merged = merged.drop_duplicates(subset=["date", "release_name"], keep="last")
    merged = merged.sort_values(["date", "importance"]).reset_index(drop=True)
    merged.to_csv(out_path, index=False)

    with open(hist_path, "w") as f:
        json.dump({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "since": since,
            "events": history,
            "note": "Actual historical release / decision dates (originals only, "
                    "revisions dropped). Built by refresh_calendar().",
        }, f, indent=1)

    n_hist = sum(len(v) for v in history.values())
    print(f"Wrote {len(merged)} rows ({len(new_df)} scheduled) to {out_path}; "
          f"{n_hist} historical event dates to {hist_path}")
    return out_path
