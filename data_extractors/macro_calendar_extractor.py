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

# FRED release IDs for the macro events that move equity vol
# Source: https://fred.stlouisfed.org/releases
# cadence_days: typical inter-release gap (30 = monthly, 90 = quarterly, ~28 = NFP first-Friday)
FRED_RELEASES = {
    10:  ("CPI",                       "high", 30),
    11:  ("Employment Situation",      "high", 28),    # NFP first Friday
    50:  ("GDP",                       "high", 90),    # quarterly
    21:  ("PPI",                       "med",  30),
    53:  ("Personal Income & Outlays", "high", 30),    # PCE
    175: ("JOLTS",                     "med",  30),
    200: ("Retail Sales",              "med",  30),
    197: ("Consumer Sentiment",        "low",  15),    # preliminary + final mid- and end-month
    18:  ("Industrial Production",     "low",  30),
    51:  ("Housing Starts",            "low",  30),
}

FOMC_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FRED_API_BASE = "https://api.stlouisfed.org/fred"


def _fred_release_dates(release_id: int, cadence_days: int, days_ahead: int = 180) -> list[str]:
    """Return projected release dates (YYYY-MM-DD).

    FRED's `/release/dates` returns historical releases AND revisions, so the
    raw API can't be used for cadence inference. We pull the most-recent
    actual release date and project forward at the known cadence
    (`cadence_days`). For most US macro releases this is monthly (30) or
    quarterly (90); NFP is first-Friday (~28).

    The projection is coarse — the consumer cares about "is there a macro
    event inside the option window", not the exact minute. The calendar
    refreshes weekly; once a real date materializes in FRED's history the
    projection is replaced.
    """
    today = dt.date.today()
    end = today + dt.timedelta(days=days_ahead)

    params = {
        "release_id": release_id,
        "api_key": config.FRED_API_KEY,
        "file_type": "json",
        "include_release_dates_with_no_data": "false",
        "limit": 24,
        "sort_order": "desc",
    }
    r = requests.get(f"{FRED_API_BASE}/release/dates", params=params, timeout=20)
    r.raise_for_status()
    history = [e["date"] for e in r.json().get("release_dates", []) if e.get("date")]
    if not history:
        return []

    # Group by month and take the FIRST (earliest) release per month — that's
    # the original data release; later same-month dates are revisions.
    history_dt = sorted(dt.datetime.strptime(d, "%Y-%m-%d").date() for d in history)
    by_month: dict[tuple[int, int], dt.date] = {}
    for d in history_dt:
        key = (d.year, d.month)
        if key not in by_month or d < by_month[key]:
            by_month[key] = d
    monthly_releases = sorted(by_month.values())

    if not monthly_releases:
        return []

    last_release = monthly_releases[-1]

    # Project forward at the known cadence
    out: list[str] = []
    cur = last_release
    while True:
        cur = cur + dt.timedelta(days=cadence_days)
        if cur > end:
            break
        if cur >= today:
            out.append(cur.isoformat())
    return out


def _scrape_fomc_meetings() -> list[str]:
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
        if date_obj >= today:
            out.append(date_obj.isoformat())
    return sorted(set(out))


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
    """Refresh the calendar CSV. Append-only on past dates, replace future window."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "macro_catalyst_calendar.csv"

    new_df = build_calendar(days_ahead=180)
    today = dt.date.today().isoformat()

    if out_path.exists():
        existing = pd.read_csv(out_path)
        # Keep only past dates from existing (history); replace future dates with new pull
        past = existing[existing["date"] < today]
        merged = pd.concat([past, new_df], ignore_index=True)
        # De-dup by (date, release_name)
        merged = merged.drop_duplicates(subset=["date", "release_name"], keep="last")
    else:
        merged = new_df

    merged = merged.sort_values(["date", "importance"]).reset_index(drop=True)
    merged.to_csv(out_path, index=False)
    print(f"Wrote {len(merged)} rows ({len(new_df)} fresh) to {out_path}")
    return out_path


if __name__ == "__main__":
    refresh_calendar()
