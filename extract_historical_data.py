"""
Historical Data Extraction Script for Macroeconomic Indicators

Downloads all 50 indicators and saves to CSV files with:
- Append-only mode (adds new data without overwriting)
- Last timestamp tracking
- Historical data preservation

Each indicator is saved to a separate CSV in historical_data/.
New data is appended (never overwrites existing rows).
"""

import os
import stat
import tempfile
import pandas as pd
from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path

try:  # POSIX advisory locks; the VPS (Linux) and the laptop (macOS) both have them
    import fcntl
except ImportError:  # pragma: no cover — no locking on platforms without fcntl
    fcntl = None

from data_aggregator import get_aggregator
from data_extractors import (
    yfinance_extractors,
    openbb_extractors,
    fred_extractors,
    shiller_extractor,
    web_scrapers,
    commodities_extractors,
    cot_extractor,
    japan_yield_extractor,
    equity_financials_extractor
)
from data_extractors.financial_agent_extractors import (
    SERIES_MAP as FA_SERIES_MAP,
    get_all_financial_agent_series,
    get_gold_price_yfinance,
)
from data_extractors import fidenza_extractors


# Configuration
OUTPUT_DIR = 'historical_data'
METADATA_FILE = 'data_metadata.json'


def ensure_output_directory():
    """Create output directory if it doesn't exist."""
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    print(f"✅ Output directory: {OUTPUT_DIR}/")


def load_metadata():
    """Load metadata about last extraction timestamps."""
    metadata_path = os.path.join(OUTPUT_DIR, METADATA_FILE)

    if os.path.exists(metadata_path):
        with open(metadata_path, 'r') as f:
            return json.load(f)
    else:
        return {
            'last_extraction': None,
            'indicators': {}
        }


def save_metadata(metadata):
    """Save metadata about extraction."""
    metadata_path = os.path.join(OUTPUT_DIR, METADATA_FILE)
    metadata['last_extraction'] = datetime.now().isoformat()

    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2, default=str)


@contextmanager
def _csv_lock(filepath):
    """Hold an exclusive advisory lock for one CSV's read-modify-write.

    Several processes rewrite the same files: macro2-ibkr-stream every 5 min,
    fast_extract every 5 min and the full extraction 5x/day. Without a lock two
    overlapping writers interleave their bytes. On 2026-09-01, during an IBKR
    stream restart, that left gold.csv with a line fragment whose timestamp did
    not parse; it was written back with a blank timestamp and re-sorted to the
    end of the file on every later write, where "last row = latest price"
    readers picked it up for two weeks (QA_SOP.md Bug Log, 2026-09-16).
    """
    if fcntl is None:
        yield
        return
    d, base = os.path.split(filepath)
    lock_path = os.path.join(d, f'.{base}.lock')
    with open(lock_path, 'a') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _atomic_to_csv(df, filepath):
    """Write via a temp file + rename so a reader never sees a half-written CSV."""
    d = os.path.dirname(filepath) or '.'
    mode = stat.S_IMODE(os.stat(filepath).st_mode) if os.path.exists(filepath) else 0o644
    fd, tmp = tempfile.mkstemp(prefix=f'.{os.path.basename(filepath)}.', suffix='.tmp', dir=d)
    try:
        with os.fdopen(fd, 'w', newline='') as fh:
            df.to_csv(fh, index=False)
        os.chmod(tmp, mode)
        os.replace(tmp, filepath)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── Column contracts ─────────────────────────────────────────────────────────
# A header says which columns a file HAS, not which ones anyone still fills. On 2026-03-19 a
# Hyperliquid registry edit stopped 16 hl_perps.csv columns; the header kept them, every new
# row left them blank, and six months passed before anyone noticed, because the feed scanner
# (CLI_OS/Agent_Orchestration/CC/backfill/data_guard.py) cannot tell a column that was retired
# on purpose from one that broke. So each writer declares its columns next to the file.

_DECLARE_REFRESH_SECS = 3600   # an unchanged contract is re-stamped at most hourly


def _contract_path(filename):
    """historical_data/[subdir/].<stem>.columns.json — the leading dot keeps it out of *.csv globs."""
    d, base = os.path.split(filename)
    return os.path.join(OUTPUT_DIR, d, f'.{os.path.splitext(base)[0]}.columns.json')


def _atomic_write_text(path, text):
    """Temp file + rename in the target directory, like _atomic_to_csv."""
    d = os.path.dirname(path) or '.'
    mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else 0o644
    fd, tmp = tempfile.mkstemp(prefix=f'.{os.path.basename(path)}.', suffix='.tmp', dir=d)
    try:
        with os.fdopen(fd, 'w') as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _names(value, what):
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise TypeError(f"declare_columns: {what} must be a list of column names, got {type(value).__name__}")
    for c in value:
        if not isinstance(c, str) or not c.strip():
            raise ValueError(f"declare_columns: {what} holds an empty or non-string column name: {c!r}")
    dup = sorted({c for c in value if list(value).count(c) > 1})
    if dup:
        raise ValueError(f"declare_columns: {what} lists {dup} more than once")
    return list(value)


def _validate_contract(filename, active, retired, unavailable, writer, key=None, active_since=None):
    """Normalised (active, retired, unavailable, key, active_since); raises TypeError/ValueError on misuse."""
    if not isinstance(filename, str) or not filename.lower().endswith('.csv') or not os.path.basename(filename)[:-4]:
        raise ValueError(f"declare_columns: filename must name a .csv file, got {filename!r}")
    if not isinstance(writer, str):
        raise TypeError("declare_columns: writer must be a string")
    active = _names(active, 'active')
    if retired is None:
        retired = {}
    if not isinstance(retired, dict):
        raise TypeError("declare_columns: retired must be a dict {column: {'since': 'YYYY-MM-DD', 'reason': str}}")
    out_retired = {}
    latest = datetime.now(timezone.utc).date().toordinal() + 1      # one day of slack for timezones
    for col, meta in retired.items():
        _names([col], 'retired')
        if not isinstance(meta, dict) or set(meta) != {'since', 'reason'}:
            raise ValueError(f"declare_columns: retired[{col!r}] must be exactly {{'since': 'YYYY-MM-DD', "
                             f"'reason': str}}, got {meta!r}")
        since = meta['since']
        try:
            day = datetime.strptime(since, '%Y-%m-%d').date()
        except (TypeError, ValueError):
            day = None
        if day is None or day.isoformat() != since:
            raise ValueError(f"declare_columns: retired[{col!r}]['since'] must be a YYYY-MM-DD date, got {since!r}")
        if day.toordinal() > latest:
            raise ValueError(f"declare_columns: retired[{col!r}]['since'] {since} is in the future")
        if not isinstance(meta['reason'], str) or not meta['reason'].strip():
            raise ValueError(f"declare_columns: retired[{col!r}] needs a non-empty reason")
        out_retired[col] = {'since': since, 'reason': meta['reason'].strip()}
    if unavailable is None:
        unavailable = {}
    if not isinstance(unavailable, dict):
        raise TypeError("declare_columns: unavailable must be a dict {column: reason}")
    out_unavailable = {}
    for col, reason in unavailable.items():
        _names([col], 'unavailable')
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"declare_columns: unavailable[{col!r}] needs a non-empty reason")
        out_unavailable[col] = reason.strip()
    a, r, u = set(active), set(out_retired), set(out_unavailable)
    both = sorted((a & r) | (a & u) | (r & u))
    if both:
        raise ValueError(f"declare_columns: {both} declared in more than one of active/retired/unavailable")
    out_key = None
    if key is not None:
        out_key = _names(key, 'key')
        bad = [c for c in out_key if c not in a and c not in ('date', 'timestamp')]
        if bad:
            raise ValueError(f"declare_columns: key column(s) {bad} must be active (or date/timestamp)")
    out_since = None
    if active_since is not None:
        if not isinstance(active_since, dict):
            raise TypeError("declare_columns: active_since must be a dict {column: 'YYYY-MM-DD'}")
        out_since = {}
        for col, since in active_since.items():
            if col not in a:
                raise ValueError(f"declare_columns: active_since[{col!r}]: column is not active")
            try:
                day = datetime.strptime(since, '%Y-%m-%d').date()
            except (TypeError, ValueError):
                day = None
            if day is None or day.isoformat() != since:
                raise ValueError(f"declare_columns: active_since[{col!r}] must be a YYYY-MM-DD date, got {since!r}")
            if day.toordinal() > latest:
                raise ValueError(f"declare_columns: active_since[{col!r}] {since} is in the future")
            out_since[col] = since
    return active, out_retired, out_unavailable, out_key, out_since


def declare_columns(filename: str, active: list[str], retired: dict[str, dict] | None = None,
                    unavailable: dict[str, str] | None = None, writer: str = "",
                    key: list[str] | None = None, active_since: dict[str, str] | None = None) -> None:
    """Declare which columns of historical_data/<filename> this writer fills.

    Writes historical_data/.<stem>.columns.json (atomically; the leading dot keeps it out of
    *.csv globs), which the feed scanner (CLI_OS .../CC/backfill/data_guard.py feeds) reads:

        {"file": "<name>.csv", "writer": "<writer>", "declared_at": "2026-09-21T08:00:00Z",
         "active": [...], "retired": {col: {"since": "YYYY-MM-DD", "reason": str}},
         "unavailable": {col: reason}}

    Args:
        filename: the CSV's name under historical_data/, exactly as passed to append_to_csv.
        active: every value column this writer fills (timestamp/date may be listed or left out).
            An active column left blank past the file's cadence is flagged, as before.
        retired: columns the writer USED to fill and stopped on purpose, with the date it stopped
            and why. Not flagged while blank; flagged ("written again") if a row dated after
            `since` has a value.
        unavailable: columns in the header that have no source (never had, or not now), where
            blank IS the correct value, with the reason. Never flagged while blank - the scanner
            prints the reason as a note so the pending decision stays visible - and flagged if
            the newest rows carry a value anyway.
        writer: who declares (module/function), shown when the contract goes stale.
        key: optional - the columns that identify a row (e.g. ['date', 'release_key', 'source']
            for a snapshot log). The scanner then counts conflicts per declared key instead of
            guessing a single-column panel key. Key columns must be active (or date/timestamp).
        active_since: optional {column: 'YYYY-MM-DD'} - the day an active column started being
            written; the scanner judges it blank only on rows from that day on (a source added
            later is not "blank since never").
    Both are written only when given, so existing contracts are unchanged.
    Every header value column (all but timestamp/date) must be in exactly one list; one in none
    is flagged as an orphan. A column may not appear in two lists.

    Call it on every run, after the write (skip it on runs that fail). It is cheap: an
    unchanged contract is re-stamped at most once per hour. Misuse (a bad `since`, an empty
    reason, a column in two lists, a non-list `active`) raises ValueError/TypeError, so a
    unit test that builds the contract catches it; I/O errors are printed and swallowed, so a
    declaration never fails a collector run. The scanner flags a contract whose declared_at
    falls well behind the file's newest row (the writer stopped declaring).

    Example - a writer, right after its append_to_csv('hl_perps.csv', df) (column names and
    reasons are illustrative, not a statement about which hl_perps columns are live):

        declare_columns(
            'hl_perps.csv',
            active=[f'hl_{c}_{f}' for c in ('btc', 'eth') for f in ('price', 'funding', 'oi', 'volume_24h')],
            retired={'hl_xyz_price': {'since': '2026-03-19', 'reason': 'XYZ perp delisted by Hyperliquid'}},
            unavailable={'hl_btc_premium': 'not in the API response this writer uses'},
            writer='hl_extract.py',
        )

    The IBKR daemon (ibkr_fast_extract._column_contracts) and extract_sp500_fundamentals*
    are wired examples.
    """
    active, retired, unavailable, key, active_since = _validate_contract(
        filename, active, retired, unavailable, writer, key, active_since)
    path = _contract_path(filename)
    payload = {'file': os.path.basename(filename), 'writer': writer, 'declared_at': None,
               'active': active, 'retired': retired, 'unavailable': unavailable}
    if key:
        payload['key'] = key
    if active_since:
        payload['active_since'] = active_since
    try:
        now = datetime.now(timezone.utc)
        try:
            with open(path) as fh:
                prev = json.load(fh)
        except (OSError, ValueError):
            prev = None
        if isinstance(prev, dict) and all(prev.get(k) == payload[k] for k in payload if k != 'declared_at'):
            try:
                stamped = datetime.strptime(prev.get('declared_at') or '', '%Y-%m-%dT%H:%M:%SZ')
                age = (now - stamped.replace(tzinfo=timezone.utc)).total_seconds()
            except (TypeError, ValueError):
                age = None
            if age is not None and 0 <= age < _DECLARE_REFRESH_SECS:
                return
        payload['declared_at'] = now.strftime('%Y-%m-%dT%H:%M:%SZ')
        _atomic_write_text(path, json.dumps(payload, indent=1) + '\n')
    except Exception as e:  # never let a declaration fail the run that wrote the data
        print(f"  ⚠️  declare_columns({filename}): could not write {path}: {type(e).__name__}: {e}")


def _parse_timestamps(series):
    """Parse a timestamp column strictly as ISO 8601, returning naive UTC.

    An explicit format matters: with an inferred format, pandas turns any row
    whose layout differs from the first row (fractional seconds, a fragment)
    into NaT under errors='coerce', silently.
    """
    parsed = pd.to_datetime(series, errors='coerce', utc=True, format='ISO8601')
    return parsed.dt.tz_localize(None)


def append_to_csv(filename, new_data, timestamp_col='timestamp', replace_daily_dates=False, subset=None,
                  guard=None, sort_by=None):
    """
    Append new data to CSV file, avoiding duplicates.

    The read-modify-write runs under a per-file lock and is written atomically.
    Rows whose timestamp cannot be parsed are dropped with a warning: they can be
    neither de-duplicated nor ordered, and a sort would park them at the end of
    the file where "latest row" readers would take them for current data.

    Args:
        filename: CSV filename
        new_data: DataFrame with new data
        timestamp_col: Name of timestamp column for deduplication
        subset: columns identifying a unique row. Defaults to [timestamp_col]. A file whose
            writer emits SEVERAL rows per run sharing one timestamp needs the extra key, or
            de-duplication keeps exactly one of them: _summary_latest.csv lost 11 of its 12
            indicators on every write for seven months this way, and the concat means each
            run also retro-collapsed the previous run's rows.
        replace_daily_dates: new_data holds daily bars. Existing whole-hour rows on
            the same dates are replaced even when their timestamps differ: the same
            bar re-fetched under another timezone convention (yfinance 1.2.0 dates
            ^VIX at Chicago midnight, 05:00/06:00 UTC; older rows sat at New York
            midnight, 04:00/05:00) was otherwise kept twice — the source of the
            10Y/2Y/VIX same-date duplicates. Intraday rows (IBKR 5-minute
            snapshots) are never touched.
        guard: optional callable(existing_df_or_None, new_df) -> new_df, run under the lock
            before the merge. It returns the rows that may be written, or raises to abort
            the write and leave the file untouched — the hook a collector uses to refuse
            mixing a second series or schema into a file (see _series_guard).
        sort_by: columns to order the result by (default [timestamp_col]). The sort is
            stable, so rows tied on these keep their order.
    """
    filepath = os.path.join(OUTPUT_DIR, filename)

    with _csv_lock(filepath):
        existing_data = None
        if os.path.exists(filepath):
            # Load existing data. A previously-truncated (0-byte) or otherwise
            # corrupt CSV would raise EmptyDataError/ParserError here and wedge the
            # indicator permanently — every subsequent run would fail to read and
            # therefore never rewrite. Guard against it so the next run self-heals
            # by writing fresh data instead of staying empty forever.
            try:
                existing_data = pd.read_csv(filepath)
                if existing_data.shape[1] == 0:  # no columns parsed
                    existing_data = None
            except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
                print(f"  ⚠️  Existing {filename} unreadable ({type(e).__name__}); rewriting fresh")
                existing_data = None

        if guard is not None:
            new_data = guard(existing_data, new_data)

        if existing_data is not None:
            # Combine and remove duplicates based on timestamp
            if timestamp_col in new_data.columns and timestamp_col in existing_data.columns:
                existing_data[timestamp_col] = _parse_timestamps(existing_data[timestamp_col])
                new_data = new_data.copy()
                new_data[timestamp_col] = _parse_timestamps(new_data[timestamp_col])
                if replace_daily_dates and 'date' in new_data.columns and 'date' in existing_data.columns:
                    ets = existing_data[timestamp_col]
                    whole_hour = ets.notna() & (ets.dt.minute == 0) & (ets.dt.second == 0) & (ets.dt.microsecond == 0)
                    # Daily bars recur at the same hour across many dates; an IBKR
                    # snapshot that happens to land on hh:00:00 is a one-off.
                    counts = ets[whole_hour].dt.hour.value_counts()
                    bar_hours = set(counts[counts >= max(2, 0.01 * int(whole_hour.sum()))].index)
                    bar_hours |= set(new_data[timestamp_col].dropna().dt.hour)
                    is_bar = whole_hour & ets.dt.hour.isin(bar_hours)
                    new_dates = set(pd.to_datetime(new_data['date'], errors='coerce').dropna().dt.date)
                    old_dates = pd.to_datetime(existing_data['date'], errors='coerce').dt.date
                    existing_data = existing_data[~(is_bar & old_dates.isin(new_dates))]
                combined = pd.concat([existing_data, new_data], ignore_index=True)
                unparseable = combined[timestamp_col].isna()
                if unparseable.any():
                    print(f"  ⚠️  {filename}: dropped {int(unparseable.sum())} row(s) with an unparseable timestamp")
                    combined = combined[~unparseable]
                combined = combined.drop_duplicates(subset=subset or [timestamp_col], keep='last')
                if sort_by:
                    combined = combined.sort_values(list(sort_by), kind='stable')
                else:
                    combined = combined.sort_values(timestamp_col)
            else:
                # If no timestamp column, just append
                combined = pd.concat([existing_data, new_data], ignore_index=True)
        else:
            combined = new_data

        # Save
        _atomic_to_csv(combined, filepath)
    print(f"  💾 Saved to: {filename} ({len(combined)} total rows)")


_WEEKDAYS = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}


def _off_cadence(timestamps, cadence):
    """Mask of observations that do NOT sit on a series' date grid.

    cadence: 'MS' — dated midnight on the 1st of the month (how FRED dates monthly series);
             'W-<DAY>' — dated midnight on one weekday, e.g. 'W-SAT' for week-ending Saturday.
    Explicit checks rather than pandas offset aliases, whose names changed between
    pandas 2.2 and 3.0 (the VPS runs both). Unparseable timestamps count as off-grid.
    """
    ts = _parse_timestamps(timestamps)
    if cadence == 'MS':
        on = ts.dt.day == 1
    elif cadence.startswith('W-') and cadence[2:] in _WEEKDAYS:
        on = ts.dt.dayofweek == _WEEKDAYS[cadence[2:]]
    else:
        raise ValueError(f"unknown cadence {cadence!r}")
    return ~(on & (ts == ts.dt.normalize()))


def _series_guard(filename, series_id, cadence, timestamp_col='timestamp'):
    """append_to_csv guard for a file that must hold exactly ONE source series.

    adp_employment.csv held two FRED series for six months — weekly ADPWNUSNERSA rows to
    2026-01-17, then monthly ADPMNUSNERSA rows after the fetch was switched — because
    nothing tied the file to a series. Now every row carries its series_id, and:
      * new rows off the series' date grid are rejected (warned, not written);
      * the write is refused outright when the existing file holds another series,
        rows off the grid, or no series_id at all (a file from before 2026-09-21 that
        scripts/repair_adp_earnings_20260921.py has not split yet).
    Refusing leaves the file untouched and surfaces as a failed indicator in the run.
    """
    def guard(existing, new):
        off = _off_cadence(new[timestamp_col], cadence)
        if off.any():
            print(f"  ⚠️  {filename}: rejected {int(off.sum())} row(s) off the {series_id} {cadence} "
                  f"date grid (first: {new.loc[off, timestamp_col].iloc[0]})")
            new = new[~off]
        if new.empty:
            raise ValueError(f"{filename}: no rows on the {series_id} {cadence} grid — nothing written")
        if existing is not None and len(existing):
            if 'series_id' not in existing.columns:
                raise ValueError(f"{filename} has no series_id column (pre-2026-09-21 layout) — "
                                 f"run scripts/repair_adp_earnings_20260921.py, then with --apply; not written")
            labels = existing['series_id'].where(existing['series_id'].notna(), '').astype(str).str.strip()
            blank = labels == ''
            if blank.any():
                # Code from before 2026-09-21 rewrites the rows it fetched without a label
                # (a stray old-code run, or a code-only rollback). The repair script
                # re-derives the label from the date grid.
                raise ValueError(f"{filename}: {int(blank.sum())} existing row(s) without a series_id "
                                 f"(written by pre-2026-09-21 code) — run scripts/repair_adp_earnings_20260921.py, "
                                 f"then with --apply; not written")
            other = labels != series_id
            if other.any():
                raise ValueError(f"{filename}: {int(other.sum())} existing row(s) labelled "
                                 f"{sorted(set(labels[other]))}, not {series_id} — refusing to mix series; "
                                 f"inspect by hand")
            off_existing = _off_cadence(existing[timestamp_col], cadence)
            if off_existing.any():
                raise ValueError(f"{filename}: {int(off_existing.sum())} existing row(s) off the "
                                 f"{series_id} {cadence} grid — refusing to append; inspect by hand")
        return new
    return guard


def extract_russell_2000_historical():
    """Extract Russell 2000 Value & Growth historical data."""
    print("\n📊 Extracting Russell 2000 indices...")

    try:
        data = yfinance_extractors.get_russell_2000_indices()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        # Extract historical data for both indices
        value_hist = data['russell_2000_value']['historical']
        growth_hist = data['russell_2000_growth']['historical']

        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': value_hist.index,
            'date': value_hist.index.date,
            'russell_2000_value': value_hist.values,
            'russell_2000_growth': growth_hist.values,
            'value_growth_ratio': value_hist.values / growth_hist.values
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('russell_2000.csv', df)

        return {
            'indicator': 'Russell 2000',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sp500_with_ma200():
    """Extract S&P 500 with 200-day moving average."""
    print("\n📊 Extracting S&P 500 / 200MA...")

    try:
        data = yfinance_extractors.get_sp500_data()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': hist.index.date,
            'sp500_close': hist['Close'],
            'sp500_ma200': hist['MA200'],
            'price_to_ma200_ratio': hist['Close'] / hist['MA200']
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('sp500_ma200.csv', df)

        return {
            'indicator': 'S&P 500 / 200MA',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_vix_move():
    """Extract VIX and MOVE indices with ratio."""
    print("\n📊 Extracting VIX and MOVE...")

    try:
        vix_data = yfinance_extractors.get_vix()
        move_data = yfinance_extractors.get_move_index()

        if 'error' in vix_data or 'error' in move_data:
            print(f"  ❌ Error fetching data")
            return

        vix_hist = vix_data['historical']
        move_hist = move_data['historical']

        # Strip timezone to prevent duplicate rows from tz-aware indices
        # yfinance returns America/New_York tz-aware timestamps which cause
        # duplicate entries when DST offset changes (-05:00 vs -04:00)
        if hasattr(vix_hist.index, 'tz') and vix_hist.index.tz is not None:
            vix_hist = vix_hist.tz_localize(None)
        if hasattr(move_hist.index, 'tz') and move_hist.index.tz is not None:
            move_hist = move_hist.tz_localize(None)

        # Normalize to midnight to ensure clean date-based merging
        vix_hist.index = vix_hist.index.normalize()
        move_hist.index = move_hist.index.normalize()

        # Align timestamps
        df_vix = pd.DataFrame({
            'timestamp': vix_hist.index,
            'vix': vix_hist.values
        })

        df_move = pd.DataFrame({
            'timestamp': move_hist.index,
            'move': move_hist.values
        })

        # Merge on timestamp
        df = pd.merge(df_vix, df_move, on='timestamp', how='outer')
        df = df.sort_values('timestamp')

        # Calculate ratio where both exist
        df['vix_move_ratio'] = df['vix'] / df['move']
        df['date'] = df['timestamp'].dt.date

        append_to_csv('vix_move.csv', df)

        return {
            'indicator': 'VIX / MOVE',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_dxy():
    """Extract US Dollar Index (DXY)."""
    print("\n📊 Extracting DXY...")

    try:
        data = yfinance_extractors.get_dxy()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': hist.index.date,
            'dxy': hist.values
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('dxy.csv', df)

        return {
            'indicator': 'DXY',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_shiller_cape():
    """Extract Shiller CAPE historical data."""
    print("\n📊 Extracting Shiller CAPE...")

    try:
        data = shiller_extractor.get_shiller_cape()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'date': hist.index,
            'cape_ratio': hist.values
        })

        # Convert to timestamp (assuming end of month)
        df['timestamp'] = pd.to_datetime(df['date'])

        append_to_csv('shiller_cape.csv', df, timestamp_col='date')

        return {
            'indicator': 'Shiller CAPE',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# sp500_fundamentals.csv has two writers (extract_sp500_fundamentals, and the _expanded one
# below); both declare the file's whole contract. The forward fields stay blank on purpose:
# no free S&P 500 forward estimate exists (Yahoo publishes no forwardPE/forwardEps for SPY),
# and the obvious back-fill, sp500_multiples.forward_pe, was trailing P/E in disguise.
_SP500_FORWARD_REASON = ("no free S&P 500 forward estimate: Yahoo publishes no forwardPE/forwardEps for SPY and "
                         "sp500_multiples.forward_pe is trailing P/E in disguise - blank is correct, do not "
                         "back-fill (macro_2 QA_learnings 2026-09-16)")
SP500_FUNDAMENTALS_CONTRACT = dict(
    active=['pe_ratio_trailing', 'pb_ratio', 'earnings_yield', 'dividend_yield_pct', 'trailing_eps', 'spy_price'],
    unavailable={c: _SP500_FORWARD_REASON for c in ('pe_ratio_forward', 'forward_earnings_yield', 'forward_eps')},
    writer='extract_historical_data.extract_sp500_fundamentals(_expanded)',
)


def _declare_sp500_fundamentals():
    try:
        declare_columns('sp500_fundamentals.csv', **SP500_FUNDAMENTALS_CONTRACT)
    except Exception as e:  # a contract bug must not cost the data write that already happened
        print(f"  ⚠️  sp500_fundamentals column contract not declared: {type(e).__name__}: {e}")


def extract_sp500_fundamentals():
    """Extract S&P 500 P/E and P/B ratios (snapshot only)."""
    print("\n📊 Extracting S&P 500 Fundamentals...")

    try:
        data = openbb_extractors.get_sp500_fundamentals()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        # Create single-row DataFrame with current values
        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'pe_ratio_trailing': data.get('sp500_pe_trailing'),
            'pb_ratio': data.get('sp500_pb')
        }])

        append_to_csv('sp500_fundamentals.csv', df)
        _declare_sp500_fundamentals()

        return {
            'indicator': 'S&P 500 P/E & P/B',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_cboe_skew():
    """Extract CBOE SKEW index."""
    print("\n📊 Extracting CBOE SKEW...")

    try:
        data = web_scrapers.get_cboe_skew_index()

        if 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return

        hist = data['historical']

        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': hist.index.date,
            'cboe_skew': hist.values
        })

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('cboe_skew.csv', df)

        return {
            'indicator': 'CBOE SKEW',
            'last_date': df['date'].max(),
            'rows': len(df)
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_fred_indicators():
    """Extract FRED indicators (GDP, Market Cap)."""
    print("\n📊 Extracting FRED indicators...")

    try:
        # Get GDP
        gdp_data = fred_extractors.get_us_gdp()

        if 'error' not in gdp_data:
            hist = gdp_data['historical']

            df_gdp = pd.DataFrame({
                'timestamp': hist.index,
                'date': hist.index.date,
                'us_gdp': hist.values
            })

            df_gdp['timestamp'] = pd.to_datetime(df_gdp['timestamp'])
            append_to_csv('us_gdp.csv', df_gdp)
        else:
            print(f"  ⚠️  GDP: {gdp_data['error']}")

        # Get Market Cap
        marketcap_data = fred_extractors.get_sp500_market_cap()

        if 'error' not in marketcap_data:
            hist = marketcap_data['historical']

            df_mc = pd.DataFrame({
                'timestamp': hist.index,
                'date': hist.index.date,
                'market_cap': hist.values
            })

            df_mc['timestamp'] = pd.to_datetime(df_mc['timestamp'])
            append_to_csv('market_cap.csv', df_mc)
        else:
            print(f"  ⚠️  Market Cap: {marketcap_data['error']}")

        # Calculate Market Cap / GDP ratio
        if 'error' not in gdp_data and 'error' not in marketcap_data:
            # Merge on date (quarterly data)
            df_ratio = pd.merge(df_gdp, df_mc, on='date', how='outer', suffixes=('_gdp', '_mc'))
            df_ratio['marketcap_to_gdp_ratio'] = (df_ratio['market_cap'] / df_ratio['us_gdp']) * 100
            df_ratio = df_ratio[['date', 'timestamp_gdp', 'us_gdp', 'market_cap', 'marketcap_to_gdp_ratio']]
            df_ratio.rename(columns={'timestamp_gdp': 'timestamp'}, inplace=True)

            append_to_csv('marketcap_to_gdp.csv', df_ratio, timestamp_col='date')

        return {
            'indicator': 'FRED (GDP, Market Cap)',
            'last_date': datetime.now().date(),
            'rows': 'varies'
        }

    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def _extract_simple_series(name, fetch_fn, csv_filename, value_col, series_id=None, cadence=None):
    """Generic extraction for indicators returning a 'historical' pd.Series.

    series_id / cadence pin the file to one source series (see _series_guard): the fetch
    must report that series_id, every row is labelled with it, and rows off the cadence's
    date grid are rejected. Pass both or neither.
    """
    print(f"\n📊 Extracting {name}...")
    try:
        data = fetch_fn()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        if series_id is not None and data.get('series_id') != series_id:
            print(f"  ❌ {name}: fetch returned series {data.get('series_id')!r}, "
                  f"{csv_filename} holds {series_id!r} — not written")
            return None

        hist = data.get('historical')
        if hist is None:
            print(f"  ⚠️  No historical data for {name}")
            return None

        if isinstance(hist, pd.Series):
            # FRED returns NaN for holidays; writing them produced blank-value rows
            # (720 in 10y_treasury_yield.csv) that carry no observation.
            hist = hist.dropna()
            if hist.empty:
                print(f"  ⚠️  Empty historical series for {name}")
                return None
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                value_col: hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        else:
            print(f"  ⚠️  Unexpected historical type for {name}: {type(hist)}")
            return None

        guard = None
        if series_id is not None:
            df['series_id'] = series_id
            guard = _series_guard(csv_filename, series_id, cadence)
        append_to_csv(csv_filename, df, replace_daily_dates=True, guard=guard)
        return {
            'indicator': name,
            'last_date': df['date'].max(),
            'rows': len(df)
        }
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def _extract_ohlcv_series(name, fetch_fn, csv_filename, prefix):
    """Generic extraction for indicators returning 'historical_ohlcv' DataFrame.

    Writes OHLCV CSV with columns:
        timestamp, date, {prefix}_open, {prefix}_high, {prefix}_low, {prefix}_close, {prefix}_volume
    """
    print(f"\n📊 Extracting {name} OHLCV...")
    try:
        data = fetch_fn()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        ohlcv = data.get('historical_ohlcv')
        if ohlcv is None or (hasattr(ohlcv, 'empty') and ohlcv.empty):
            print(f"  ⚠️  No OHLCV data for {name}")
            return None

        df = pd.DataFrame({
            'timestamp': ohlcv.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in ohlcv.index],
            f'{prefix}_open': ohlcv['Open'].values,
            f'{prefix}_high': ohlcv['High'].values,
            f'{prefix}_low': ohlcv['Low'].values,
            f'{prefix}_close': ohlcv['Close'].values,
            f'{prefix}_volume': ohlcv['Volume'].values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv(csv_filename, df, replace_daily_dates=True)
        return {
            'indicator': f'{name} OHLCV',
            'last_date': df['date'].max(),
            'rows': len(df)
        }
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_10y_yield():
    """Extract 10-Year Treasury Yield historical data."""
    return _extract_simple_series(
        '10-Year Treasury Yield',
        fred_extractors.get_10y_treasury_yield,
        '10y_treasury_yield.csv',
        '10y_yield'
    )


def extract_ism_pmi():
    """Extract ISM Manufacturing PMI (proxy) historical data."""
    return _extract_simple_series(
        'ISM Manufacturing PMI',
        fred_extractors.get_ism_pmi,
        'ism_pmi.csv',
        'ism_pmi'
    )


def extract_gold():
    """Extract Gold futures historical data."""
    return _extract_simple_series(
        'Gold Futures',
        commodities_extractors.get_gold,
        'gold.csv',
        'gold_price'
    )


def extract_silver():
    """Extract Silver futures historical data."""
    return _extract_simple_series(
        'Silver Futures',
        commodities_extractors.get_silver,
        'silver.csv',
        'silver_price'
    )


def extract_crude_oil():
    """Extract Crude Oil futures historical data."""
    return _extract_simple_series(
        'Crude Oil Futures',
        commodities_extractors.get_crude_oil,
        'crude_oil.csv',
        'crude_oil_price'
    )


def extract_copper():
    """Extract Copper futures historical data."""
    return _extract_simple_series(
        'Copper Futures',
        commodities_extractors.get_copper,
        'copper.csv',
        'copper_price'
    )


def extract_es_futures():
    """Extract ES Futures (S&P 500 E-mini) historical data."""
    return _extract_simple_series(
        'ES Futures',
        yfinance_extractors.get_es_futures,
        'es_futures.csv',
        'es_price'
    )


def extract_rty_futures():
    """Extract RTY Futures (Russell 2000 E-mini) historical data."""
    return _extract_simple_series(
        'RTY Futures',
        yfinance_extractors.get_rty_futures,
        'rty_futures.csv',
        'rty_price'
    )


def extract_jpy():
    """Extract USD/JPY exchange rate historical data."""
    return _extract_simple_series(
        'USD/JPY Exchange Rate',
        yfinance_extractors.get_jpy_exchange_rate,
        'jpy.csv',
        'jpy_rate'
    )


def extract_cot_positioning():
    """Extract CFTC COT positioning data for Gold and Silver."""
    print("\n📊 Extracting CFTC COT Positioning...")
    try:
        data = cot_extractor.get_cot_gold_silver()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        results = []
        for metal_key, csv_name in [('gold', 'cot_gold.csv'), ('silver', 'cot_silver.csv')]:
            metal_data = data.get(metal_key, {})
            if not isinstance(metal_data, dict) or 'error' in metal_data:
                continue

            hist = metal_data.get('historical')
            if hist is None or not isinstance(hist, pd.Series) or hist.empty:
                continue

            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'managed_money_net': hist.values,
            })

            # Add open interest if available
            hist_oi = metal_data.get('historical_oi')
            if hist_oi is not None and isinstance(hist_oi, pd.Series) and not hist_oi.empty:
                oi_df = pd.DataFrame({
                    'timestamp': hist_oi.index,
                    'open_interest': hist_oi.values,
                })
                df = pd.merge(df, oi_df, on='timestamp', how='left')

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv(csv_name, df)
            results.append({
                'indicator': f'COT {metal_key.title()}',
                'last_date': df['date'].max(),
                'rows': len(df)
            })

        return results if results else None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_cot_energy_metals():
    """Extract CFTC COT positioning data for Crude Oil, Brent, Copper, Natural Gas."""
    print("\n📊 Extracting CFTC COT Positioning (Energy & Copper)...")
    try:
        data = cot_extractor.get_cot_energy_metals()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        results = []
        for key, csv_name in [('crude_oil', 'cot_crude_oil.csv'), ('brent', 'cot_brent.csv'),
                               ('copper', 'cot_copper.csv'), ('natural_gas', 'cot_natural_gas.csv')]:
            commodity_data = data.get(key, {})
            if not isinstance(commodity_data, dict) or 'error' in commodity_data:
                print(f"  ⚠️  No data for {key}: {commodity_data.get('error', 'unknown')}")
                continue

            hist = commodity_data.get('historical')
            if hist is None or not isinstance(hist, pd.Series) or hist.empty:
                continue

            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'managed_money_net': hist.values,
            })

            hist_oi = commodity_data.get('historical_oi')
            if hist_oi is not None and isinstance(hist_oi, pd.Series) and not hist_oi.empty:
                oi_df = pd.DataFrame({
                    'timestamp': hist_oi.index,
                    'open_interest': hist_oi.values,
                })
                df = pd.merge(df, oi_df, on='timestamp', how='left')

            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv(csv_name, df)
            results.append({
                'indicator': f'COT {key.replace("_", " ").title()}',
                'last_date': df['date'].max(),
                'rows': len(df)
            })

        return results if results else None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_tga_balance():
    """Extract TGA Balance historical data."""
    return _extract_simple_series(
        'TGA Balance',
        fred_extractors.get_tga_balance,
        'tga_balance.csv',
        'tga_balance'
    )


def extract_net_liquidity():
    """Extract Fed Net Liquidity historical data."""
    return _extract_simple_series(
        'Fed Net Liquidity',
        fred_extractors.get_fed_net_liquidity,
        'net_liquidity.csv',
        'net_liquidity'
    )


def extract_sofr():
    """Extract SOFR historical data."""
    return _extract_simple_series(
        'SOFR',
        fred_extractors.get_sofr,
        'sofr.csv',
        'sofr'
    )


def extract_us_2y_yield():
    """Extract US 2-Year Treasury Yield historical data."""
    return _extract_simple_series(
        'US 2-Year Treasury Yield',
        fred_extractors.get_us_2y_yield,
        'us_2y_yield.csv',
        'us_2y_yield'
    )


def extract_japan_2y_yield():
    """Extract Japan 2-Year Government Bond Yield historical data."""
    return _extract_simple_series(
        'Japan 2Y Government Bond Yield',
        japan_yield_extractor.get_japan_2y_yield,
        'japan_2y_yield.csv',
        'japan_2y_yield'
    )


def extract_us2y_jp2y_spread():
    """Extract US 2Y - Japan 2Y yield spread historical data."""
    return _extract_simple_series(
        'US 2Y - Japan 2Y Spread',
        japan_yield_extractor.get_us2y_jp2y_spread,
        'us2y_jp2y_spread.csv',
        'spread'
    )


def _save_equity_source(companies, source_dir, source_label):
    """Save equity quarterly + valuation data for one source into a directory.

    Args:
        companies: dict of {ticker: company_data}
        source_dir: absolute path to output directory (e.g. .../yahoo_finance)
        source_label: display name for logging (e.g. 'Yahoo Finance')

    Returns:
        list of result dicts
    """
    Path(source_dir).mkdir(parents=True, exist_ok=True)

    INCOME_KEYS = [
        'total_revenue', 'cost_of_revenue', 'gross_profit', 'operating_expense',
        'research_development', 'selling_general_admin', 'operating_income',
        'ebitda', 'ebit', 'pretax_income', 'tax_provision', 'net_income',
        'diluted_eps', 'basic_eps', 'diluted_shares', 'basic_shares',
    ]
    BALANCE_KEYS = [
        'total_assets', 'current_assets', 'cash_and_short_term_investments',
        'cash_and_equivalents', 'accounts_receivable', 'inventory', 'goodwill',
        'net_ppe', 'total_liabilities', 'current_liabilities', 'non_current_liabilities',
        'long_term_debt', 'current_debt', 'total_debt', 'accounts_payable',
        'accrued_expenses', 'net_debt', 'stockholders_equity', 'retained_earnings',
        'invested_capital', 'debt_ratio', 'debt_to_equity', 'current_ratio',
    ]
    CASHFLOW_KEYS = [
        'operating_cash_flow', 'capital_expenditure', 'free_cash_flow',
        'share_repurchases', 'dividends_paid', 'investing_cash_flow',
        'financing_cash_flow', 'depreciation_amortization', 'stock_based_compensation',
    ]

    results = []
    for ticker, co in companies.items():
        if 'error' in co:
            continue

        quarters = co.get('quarters', [])
        if not quarters:
            continue

        rows = []
        for i, q in enumerate(quarters):
            row = {
                'timestamp': datetime.now().isoformat(),
                'quarter': q,
                'ticker': ticker,
                'company_name': co.get('company_name', ticker),
                'source': source_label,
            }
            inc = co.get('income_statement', {}) or {}
            for key in INCOME_KEYS:
                vals = inc.get(key, [])
                row[key] = vals[i] if i < len(vals) else None

            bs = co.get('balance_sheet', {}) or {}
            for key in BALANCE_KEYS:
                vals = bs.get(key, [])
                row[key] = vals[i] if i < len(vals) else None

            cf = co.get('cash_flow', {}) or {}
            for key in CASHFLOW_KEYS:
                vals = cf.get(key, [])
                row[key] = vals[i] if i < len(vals) else None

            rows.append(row)

        if rows:
            df = pd.DataFrame(rows)
            csv_path = os.path.join(source_dir, f"{ticker}_quarterly.csv")

            if os.path.exists(csv_path):
                existing = pd.read_csv(csv_path)
                combined = pd.concat([existing, df], ignore_index=True)
                combined = combined.drop_duplicates(subset=['quarter'], keep='last')
                combined = combined.sort_values('quarter', ascending=False)
            else:
                combined = df

            combined.to_csv(csv_path, index=False)
            results.append({'indicator': f'Equity {ticker} ({source_label})', 'last_date': quarters[0], 'rows': len(combined)})

    # Save valuation + analysis snapshot
    val_rows = []
    for ticker, co in companies.items():
        if 'error' in co:
            continue
        val = co.get('valuation', {})
        fa = co.get('financial_analysis', {})
        prof = fa.get('profitability', {})
        returns = fa.get('returns', {})
        turnover = fa.get('turnover', {})
        gr = fa.get('growth', {})
        val_rows.append({
            'timestamp': datetime.now().isoformat(),
            'ticker': ticker,
            'company_name': co.get('company_name', ticker),
            'source': source_label,
            'market_cap': co.get('market_cap'),
            'forward_pe': val.get('forward_pe'),
            'trailing_pe': val.get('trailing_pe'),
            'peg_ratio': val.get('peg_ratio'),
            'price_to_book': val.get('price_to_book'),
            'price_to_sales': val.get('price_to_sales'),
            'ev_to_ebitda': val.get('ev_to_ebitda'),
            'ev_to_revenue': val.get('ev_to_revenue'),
            'ev_to_fcf': val.get('ev_to_fcf'),
            'enterprise_value': val.get('enterprise_value'),
            'beta': val.get('beta'),
            'dividend_yield': val.get('dividend_yield'),
            'gross_margin': prof.get('gross_margin'),
            'operating_margin': prof.get('operating_margin'),
            'ebitda_margin': prof.get('ebitda_margin'),
            'fcf_margin': prof.get('fcf_margin'),
            'net_margin': prof.get('net_margin'),
            'roe': returns.get('roe'),
            'roa': returns.get('roa'),
            'roic': returns.get('roic'),
            'asset_turnover': turnover.get('asset_turnover'),
            'debt_to_equity': turnover.get('debt_to_equity'),
            'current_ratio': turnover.get('current_ratio'),
            'eps_growth': gr.get('eps_growth'),
            'revenue_growth': gr.get('revenue_growth'),
            'revenue_qoq': gr.get('revenue_qoq'),
            'revenue_yoy': gr.get('revenue_yoy'),
        })

    if val_rows:
        val_df = pd.DataFrame(val_rows)
        val_path = os.path.join(source_dir, '_valuation_snapshot.csv')
        if os.path.exists(val_path):
            existing = pd.read_csv(val_path)
            existing['timestamp'] = pd.to_datetime(existing['timestamp'], errors='coerce')
            val_df['timestamp'] = pd.to_datetime(val_df['timestamp'], errors='coerce')
            combined = pd.concat([existing, val_df], ignore_index=True)
            combined['date'] = combined['timestamp'].dt.date
            combined = combined.drop_duplicates(subset=['ticker', 'date'], keep='last')
            combined = combined.drop(columns=['date'])
            combined = combined.sort_values(['ticker', 'timestamp'])
        else:
            combined = val_df
        combined.to_csv(val_path, index=False)

    return results


def save_single_company(ticker, company_data, source_label):
    """Save a single company's financial data to the appropriate CSV.

    Thin wrapper around _save_equity_source() for use by the dashboard (on-demand
    fetches) and monitoring scripts (auto-update).

    Args:
        ticker: Ticker symbol (e.g., 'CRM')
        company_data: Dict from get_company_financials_yahoo() or get_company_financials_sec()
        source_label: 'Yahoo Finance' or 'SEC EDGAR'

    Returns:
        list of result dicts, or empty list on error
    """
    eq_base = os.path.join(OUTPUT_DIR, 'equity_financials')
    if source_label == 'Yahoo Finance':
        source_dir = os.path.join(eq_base, 'yahoo_finance')
    elif source_label == 'SEC EDGAR':
        source_dir = os.path.join(eq_base, 'sec_edgar')
    else:
        source_dir = os.path.join(eq_base, source_label.lower().replace(' ', '_'))

    companies = {ticker: company_data}
    return _save_equity_source(companies, source_dir, source_label)


def extract_equity_financials():
    """Extract financial data for top 20 large-cap companies from both Yahoo Finance
    and SEC EDGAR, saving per-company CSVs into source-specific subdirectories.

    Output layout:
        historical_data/equity_financials/yahoo_finance/{TICKER}_quarterly.csv
        historical_data/equity_financials/sec_edgar/{TICKER}_quarterly.csv
    """
    from data_extractors import sec_extractor

    eq_base = os.path.join(OUTPUT_DIR, 'equity_financials')
    all_results = []

    # ── Yahoo Finance ──────────────────────────────────────────
    print("\n📊 Extracting Large-cap Equity Financials — Yahoo Finance...")
    try:
        yf_data = equity_financials_extractor.get_top20_financials()
        if isinstance(yf_data, dict) and 'error' not in yf_data:
            yf_dir = os.path.join(eq_base, 'yahoo_finance')
            yf_results = _save_equity_source(yf_data.get('companies', {}), yf_dir, 'Yahoo Finance')
            all_results.extend(yf_results)
            print(f"  💾 Yahoo Finance: {len(yf_results)} companies → equity_financials/yahoo_finance/")
        else:
            print(f"  ❌ Yahoo Finance error: {yf_data.get('error', 'unknown')}")
    except Exception as e:
        print(f"  ❌ Yahoo Finance error: {e}")

    # ── SEC EDGAR ──────────────────────────────────────────────
    print("\n📊 Extracting Large-cap Equity Financials — SEC EDGAR...")
    try:
        sec_data = sec_extractor.get_top20_financials_sec()
        if isinstance(sec_data, dict) and 'error' not in sec_data:
            sec_dir = os.path.join(eq_base, 'sec_edgar')
            sec_results = _save_equity_source(sec_data.get('companies', {}), sec_dir, 'SEC EDGAR')
            all_results.extend(sec_results)
            print(f"  💾 SEC EDGAR: {len(sec_results)} companies → equity_financials/sec_edgar/")
        else:
            print(f"  ❌ SEC EDGAR error: {sec_data.get('error', 'unknown')}")
    except Exception as e:
        print(f"  ❌ SEC EDGAR error: {e}")

    if all_results:
        return {
            'indicator': 'Equity Financials (Top 20, dual-source)',
            'last_date': datetime.now().strftime('%Y-%m-%d'),
            'rows': len(all_results),
        }
    return None


def create_summary_file(results):
    """Create a summary CSV with latest values from all indicators."""
    print("\n📊 Creating summary file...")

    try:
        aggregator = get_aggregator()
        # Reuse existing data if already fetched (avoids redundant API calls)
        if not aggregator.indicators:
            aggregator.fetch_all_indicators()

        summary_data = []

        indicator_names = {
            '1_sp500_forward_pe': 'S&P 500 Forward P/E',
            '2_russell_2000': 'Russell 2000 Value/Growth',
            '3_sp500_fundamentals': 'S&P 500 P/E & P/B',
            '4_put_call_ratio': 'S&P 500 Put/Call Ratio',
            '5_spx_call_skew': 'SPX Call Skew',
            '6a_sp500_to_ma200': 'S&P 500 / 200MA',
            '6b_marketcap_to_gdp': 'Market Cap / GDP',
            '7_shiller_cape': 'Shiller CAPE',
            '8_vix': 'VIX',
            '8b_vix_move_ratio': 'VIX/MOVE Ratio',
            '9_move_index': 'MOVE Index',
            '10_dxy': 'DXY'
        }

        timestamp = datetime.now()

        for key, name in indicator_names.items():
            data = aggregator.get_indicator(key)

            row = {
                'timestamp': timestamp,
                'date': timestamp.date(),
                'indicator': name,
                'indicator_key': key,
                'status': 'success' if 'error' not in data else 'failed'
            }

            # Extract values based on indicator type
            if key == '2_russell_2000':
                row['value_main'] = data.get('russell_2000_value', {}).get('latest_price')
                row['value_secondary'] = data.get('russell_2000_growth', {}).get('latest_price')
                row['value_ratio'] = data.get('value_growth_ratio')
            elif key == '3_sp500_fundamentals':
                row['value_main'] = data.get('sp500_pe_trailing')
                row['value_secondary'] = data.get('sp500_pb')
            elif key == '6a_sp500_to_ma200':
                row['value_main'] = data.get('sp500_price')
                row['value_secondary'] = data.get('sp500_ma200')
                row['value_ratio'] = data.get('sp500_to_ma200_ratio')
            elif key == '6b_marketcap_to_gdp':
                row['value_main'] = data.get('marketcap_to_gdp_ratio')
            elif key == '7_shiller_cape':
                row['value_main'] = data.get('shiller_cape')
            elif key == '8_vix':
                row['value_main'] = data.get('vix')
            elif key == '8b_vix_move_ratio':
                row['value_main'] = data.get('vix_move_ratio')
                row['value_secondary'] = data.get('vix')
                row['value_tertiary'] = data.get('move')
            elif key == '9_move_index':
                row['value_main'] = data.get('move')
            elif key == '10_dxy':
                row['value_main'] = data.get('dxy')
            else:
                row['value_main'] = None

            summary_data.append(row)

        df_summary = pd.DataFrame(summary_data)
        append_to_csv('_summary_latest.csv', df_summary, subset=['timestamp', 'indicator_key'])

        print(f"  ✅ Summary file created")

    except Exception as e:
        print(f"  ❌ Error creating summary: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# Macro-to-Market v1.5 — 22 New Historical CSV Extractors
# ──────────────────────────────────────────────────────────────────────────────

# ── Inflation ─────────────────────────────────────────────────────────────────

def extract_cpi_headline():
    """Extract Headline CPI YoY% (CPIAUCSL) to CSV."""
    return _extract_simple_series(
        'CPI Headline', fred_extractors.get_headline_cpi,
        'cpi_headline.csv', 'cpi'
    )


def extract_core_cpi():
    """Extract Core CPI YoY% (CPILFESL) — special handling for multi-series return."""
    print("\n📊 Extracting Core CPI...")
    try:
        data = fred_extractors.get_core_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_core_cpi')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No Core CPI historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'core_cpi': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('core_cpi.csv', df)
        return {'indicator': 'Core CPI', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_core_pce():
    """Extract Core PCE YoY% (PCEPILFE) — special handling for multi-series return."""
    print("\n📊 Extracting Core PCE...")
    try:
        data = fred_extractors.get_core_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_core_pce')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No Core PCE historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'core_pce': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('core_pce.csv', df)
        return {'indicator': 'Core PCE', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_pce_headline():
    """Extract PCE Headline Price Index (PCEPI) to CSV."""
    return _extract_simple_series(
        'PCE Headline', fred_extractors.get_pce_headline,
        'pce_headline.csv', 'pce'
    )


def extract_ppi():
    """Extract PPI Final Demand YoY% (PPIFIS) to CSV."""
    return _extract_simple_series(
        'PPI Final Demand', fred_extractors.get_ppi,
        'ppi.csv', 'ppi'
    )


def extract_breakeven_5y():
    """Extract 5Y Breakeven Inflation (T5YIE) — special handling for multi-series return."""
    print("\n📊 Extracting 5Y Breakeven Inflation...")
    try:
        data = fred_extractors.get_breakeven_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_5y')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No 5Y breakeven historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'breakeven_5y': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('breakeven_5y.csv', df)
        return {'indicator': '5Y Breakeven', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_breakeven_10y():
    """Extract 10Y Breakeven Inflation (T10YIE) — from get_breakeven_inflation()."""
    print("\n📊 Extracting 10Y Breakeven Inflation...")
    try:
        data = fred_extractors.get_breakeven_inflation()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical_10y')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No 10Y breakeven historical data")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'breakeven_10y': hist.values
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('breakeven_10y.csv', df)
        return {'indicator': '10Y Breakeven', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_forward_inflation_5y5y():
    """Extract 5Y5Y Forward Inflation Expectation (T5YIFR) to CSV."""
    return _extract_simple_series(
        '5Y5Y Forward Inflation', fred_extractors.get_5y5y_forward_inflation,
        'forward_inflation_5y5y.csv', 'forward_inflation_5y5y'
    )


# ── Employment ────────────────────────────────────────────────────────────────

def extract_unemployment_rate():
    """Extract Unemployment Rate (UNRATE) to CSV."""
    return _extract_simple_series(
        'Unemployment Rate', fred_extractors.get_unemployment_rate,
        'unemployment_rate.csv', 'unemployment_rate'
    )


def extract_nonfarm_payrolls():
    """Extract Total Nonfarm Payrolls (PAYEMS) to CSV."""
    return _extract_simple_series(
        'Nonfarm Payrolls', fred_extractors.get_nonfarm_payrolls,
        'nonfarm_payrolls.csv', 'nonfarm_payrolls'
    )


def extract_initial_claims():
    """Extract Initial Jobless Claims (ICSA) to CSV."""
    return _extract_simple_series(
        'Initial Claims', fred_extractors.get_initial_jobless_claims,
        'initial_claims.csv', 'initial_claims'
    )


def extract_continuing_claims():
    """Extract Continuing Jobless Claims (CCSA) to CSV."""
    return _extract_simple_series(
        'Continuing Claims', fred_extractors.get_continuing_claims,
        'continuing_claims.csv', 'continuing_claims'
    )


# ── Yield Curve ───────────────────────────────────────────────────────────────

def extract_5y_yield():
    """Extract 5-Year Treasury Yield (DGS5) to CSV."""
    return _extract_simple_series(
        '5Y Treasury Yield', fred_extractors.get_5y_treasury_yield,
        'us_5y_yield.csv', 'us_5y_yield'
    )


def extract_30y_yield():
    """Extract 30-Year Treasury Yield (DGS30) to CSV."""
    return _extract_simple_series(
        '30Y Treasury Yield', fred_extractors.get_30y_treasury_yield,
        'us_30y_yield.csv', 'us_30y_yield'
    )


def extract_spread_10y3m():
    """Extract 10Y-3M Treasury Spread (T10Y3M) to CSV."""
    return _extract_simple_series(
        '10Y-3M Spread', fred_extractors.get_10y3m_spread,
        'spread_10y3m.csv', 'spread_10y3m'
    )


def extract_fed_funds_rate():
    """Extract Effective Fed Funds Rate (DFF) to CSV."""
    return _extract_simple_series(
        'Fed Funds Rate', fred_extractors.get_fed_funds_rate,
        'fed_funds_rate.csv', 'fed_funds_rate'
    )


def extract_fed_target_upper():
    """Extract Fed Funds Target Rate Upper Bound (DFEDTARU) to CSV."""
    return _extract_simple_series(
        'Fed Target Upper', fred_extractors.get_fed_target_upper,
        'fed_target_upper.csv', 'fed_target_upper'
    )


def extract_real_yield_5y():
    """Extract 5Y TIPS Real Yield (DFII5) to CSV."""
    return _extract_simple_series(
        '5Y TIPS Real Yield', fred_extractors.get_real_yield_5y,
        'real_yield_5y.csv', 'real_yield_5y'
    )


def extract_real_yield_10y():
    """Extract 10Y TIPS Real Yield (DFII10) to CSV."""
    return _extract_simple_series(
        '10Y TIPS Real Yield', fred_extractors.get_real_yield_10y,
        'real_yield_10y.csv', 'real_yield_10y'
    )


# ── Credit Spreads ────────────────────────────────────────────────────────────

def extract_hy_oas():
    """Extract ICE BofA HY OAS (BAMLH0A0HYM2) to CSV."""
    return _extract_simple_series(
        'HY OAS', fred_extractors.get_hy_credit_spread,
        'hy_oas.csv', 'hy_oas'
    )


def extract_ig_oas():
    """Extract ICE BofA IG OAS (BAMLC0A0CM) to CSV."""
    return _extract_simple_series(
        'IG OAS', fred_extractors.get_ig_credit_spread,
        'ig_oas.csv', 'ig_oas'
    )


def extract_bbb_oas():
    """Extract ICE BofA BBB OAS (BAMLC0A4CBBB) to CSV."""
    return _extract_simple_series(
        'BBB OAS', fred_extractors.get_bbb_credit_spread,
        'bbb_oas.csv', 'bbb_oas'
    )


# ──────────────────────────────────────────────────────────────────────────────
# Fidenza Macro Gap-Fill — 15 New Indicators
# ──────────────────────────────────────────────────────────────────────────────

# ── yfinance-based (simple series) ────────────────────────────────────────────

def extract_brent_crude():
    """Extract Brent Crude Oil futures (BZ=F) historical data."""
    return _extract_simple_series(
        'Brent Crude', fidenza_extractors.get_brent_crude,
        'brent_crude.csv', 'brent_crude_price',
    )


def extract_nikkei_225():
    """Extract Nikkei 225 index (^N225) historical data."""
    return _extract_simple_series(
        'Nikkei 225', fidenza_extractors.get_nikkei_225,
        'nikkei_225.csv', 'nikkei_225',
    )


def extract_fed_funds_futures():
    """Extract Fed Funds Futures (ZQ=F) with price + implied rate."""
    print("\n📊 Extracting Fed Funds Futures...")
    try:
        data = fidenza_extractors.get_fed_funds_futures()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print("  ⚠️  No historical data for Fed Funds Futures")
            return None
        df = pd.DataFrame({
            'timestamp': hist.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
            'ff_futures_price': hist.values,
            'ff_implied_rate': 100 - hist.values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        append_to_csv('fed_funds_futures.csv', df)
        return {'indicator': 'Fed Funds Futures', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── EM indices (batch extraction) ─────────────────────────────────────────────

def extract_em_indices():
    """Extract KOSPI, Bovespa, and MSCI EM proxy (EEM) historical data."""
    print("\n📊 Extracting EM indices (KOSPI, Bovespa, EEM)...")
    try:
        data = fidenza_extractors.get_em_indices()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        results = []
        for key, csv_name, col_name in [
            ('kospi', 'kospi_index.csv', 'kospi'),
            ('bovespa', 'bovespa_index.csv', 'bovespa'),
            ('msci_em', 'msci_em.csv', 'msci_em'),
        ]:
            hist = data.get(f'historical_{key}')
            if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
                df = pd.DataFrame({
                    'timestamp': hist.index,
                    'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                    col_name: hist.values,
                })
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                append_to_csv(csv_name, df)
                results.append({
                    'indicator': f'EM {key.upper()}',
                    'last_date': df['date'].max(),
                    'rows': len(df),
                })
            else:
                print(f"  ⚠️  No data for {key}")
        return results if results else None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── SOFR Futures Term Structure (multi-row CSV) ──────────────────────────────

def extract_sofr_futures():
    """Extract SOFR futures term structure to CSV.
    Multi-row format: one row per contract per date.
    Deduplication by (timestamp, contract).
    """
    print("\n📊 Extracting SOFR Futures Term Structure...")
    try:
        data = fidenza_extractors.get_sofr_futures_term_structure()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        contracts = data.get('contracts', [])
        if not contracts:
            print("  ⚠️  No SOFR futures contracts available")
            return None

        all_rows = []
        for c in contracts:
            hist = c.get('historical')
            if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
                for ts, price in hist.items():
                    all_rows.append({
                        'timestamp': ts,
                        'date': ts.date() if hasattr(ts, 'date') else ts,
                        'contract': c['contract'],
                        'price': float(price),
                        'implied_rate': round(100 - float(price), 4),
                    })

        if not all_rows:
            print("  ⚠️  No SOFR futures historical data")
            return None

        df = pd.DataFrame(all_rows)
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Custom dedup: by (timestamp, contract) instead of timestamp alone
        filepath = os.path.join(OUTPUT_DIR, 'sofr_futures_term_structure.csv')
        if os.path.exists(filepath):
            existing = pd.read_csv(filepath)
            existing['timestamp'] = pd.to_datetime(existing['timestamp'], errors='coerce')
            combined = pd.concat([existing, df], ignore_index=True)
            combined = combined.drop_duplicates(subset=['timestamp', 'contract'], keep='last')
            combined = combined.sort_values(['timestamp', 'contract'])
        else:
            combined = df.sort_values(['timestamp', 'contract'])
        combined.to_csv(filepath, index=False)
        print(f"  💾 Saved to: sofr_futures_term_structure.csv ({len(combined)} total rows)")

        return {
            'indicator': 'SOFR Futures Term Structure',
            'last_date': df['date'].max(),
            'rows': len(combined),
        }
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Computed indicators ──────────────────────────────────────────────────────

def extract_xau_jpy():
    """Extract XAU/JPY (Gold in Yen) historical data."""
    return _extract_simple_series(
        'XAU/JPY', fidenza_extractors.get_xau_jpy,
        'xau_jpy.csv', 'xau_jpy',
    )


def extract_gold_silver_ratio():
    """Extract Gold/Silver ratio historical data."""
    return _extract_simple_series(
        'Gold/Silver Ratio', fidenza_extractors.get_gold_silver_ratio,
        'gold_silver_ratio.csv', 'gold_silver_ratio',
    )


# ── FRED-based (new series in fred_extractors) ──────────────────────────────

def extract_adp_employment():
    """Extract ADP Employment, MONTHLY (FRED ADPMNUSNERSA), to adp_employment.csv.

    Monthly is the canonical series for this file: it is the headline ADP report, it is
    what every reader expects (discover_relationships resamples to month-end, the freshness
    SLA treats unlisted keys as monthly) and it is the MORE timely of the two on FRED — the
    weekly series is only updated with the monthly release, 46-74 days after its week.
    """
    return _extract_simple_series(
        'ADP Employment', fred_extractors.get_adp_employment,
        'adp_employment.csv', 'adp_employment',
        series_id=fred_extractors.ADP_MONTHLY_SERIES, cadence='MS',
    )


def extract_adp_employment_weekly():
    """Extract ADP Employment, WEEKLY (FRED ADPWNUSNERSA), to adp_employment_weekly.csv.

    Its own file so the two cadences never share one (they did until 2026-09-21). FRED
    publishes it once a month with the monthly report, so its newest week is normally
    6-11 weeks old — that is the source's lag, not a stalled collector.
    """
    return _extract_simple_series(
        'ADP Employment (weekly)', fred_extractors.get_adp_employment_weekly,
        'adp_employment_weekly.csv', 'adp_employment_weekly',
        series_id=fred_extractors.ADP_WEEKLY_SERIES, cadence='W-SAT',
    )


def extract_fed_balance_sheet():
    """Extract Fed Balance Sheet / Total Assets (WALCL) to CSV."""
    return _extract_simple_series(
        'Fed Balance Sheet', fred_extractors.get_fed_balance_sheet,
        'fed_balance_sheet.csv', 'fed_balance_sheet',
    )


def extract_treasury_term_premia():
    """Extract Treasury Term Premia (10Y, 5Y) to CSV."""
    print("\n📊 Extracting Treasury Term Premia...")
    try:
        data = fred_extractors.get_treasury_term_premia()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        hist_10y = data.get('historical')
        hist_5y = data.get('historical_5y')

        if hist_10y is None or (hasattr(hist_10y, 'empty') and hist_10y.empty):
            print("  ⚠️  No 10Y term premia data")
            return None

        df = pd.DataFrame({
            'timestamp': hist_10y.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist_10y.index],
            'term_premium_10y': hist_10y.values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Merge 5Y if available
        if hist_5y is not None and not hist_5y.empty:
            df_5y = pd.DataFrame({
                'timestamp': hist_5y.index,
                'term_premium_5y': hist_5y.values,
            })
            df_5y['timestamp'] = pd.to_datetime(df_5y['timestamp'])
            df = pd.merge(df, df_5y, on='timestamp', how='left')

        append_to_csv('treasury_term_premia.csv', df)
        return {'indicator': 'Treasury Term Premia', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Web scrape & lower-priority indicators ───────────────────────────────────

def extract_aaii_sentiment():
    """Extract AAII Bull/Bear Sentiment Survey to CSV (snapshot per extraction)."""
    print("\n📊 Extracting AAII Sentiment Survey...")
    try:
        data = fidenza_extractors.get_aaii_sentiment()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        # Handle inf bull_bear_ratio for CSV serialization
        bbr = data.get('bull_bear_ratio')
        if bbr is not None and not isinstance(bbr, (int, float)):
            bbr = None
        if isinstance(bbr, float) and (bbr == float('inf') or bbr != bbr):
            bbr = None

        # 'date' is the survey's week-ending date: a reading collected on Tuesday
        # describes the previous Wednesday, and readers treat 'date' as as-of.
        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': data.get('survey_week_ending') or datetime.now().date(),
            'bullish': data.get('bullish'),
            'neutral': data.get('neutral'),
            'bearish': data.get('bearish'),
            'bull_bear_ratio': bbr,
        }])
        append_to_csv('aaii_sentiment.csv', df)
        return {'indicator': 'AAII Sentiment', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_opec_production():
    """Extract OPEC production data to CSV."""
    print("\n📊 Extracting OPEC Production...")
    try:
        data = fidenza_extractors.get_opec_production()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'opec_production_mbpd': hist.values,
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('opec_production.csv', df)
            return {'indicator': 'OPEC Production', 'last_date': df['date'].max(), 'rows': len(df)}
        else:
            # Snapshot only (scrape fallback)
            df = pd.DataFrame([{
                'timestamp': datetime.now(),
                'date': datetime.now().date(),
                'opec_production_mbpd': data.get('opec_production'),
            }])
            append_to_csv('opec_production.csv', df)
            return {'indicator': 'OPEC Production', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_gold_reserves_share():
    """Extract Gold share of global reserves to CSV (snapshot)."""
    print("\n📊 Extracting Gold Reserves Share...")
    try:
        data = fidenza_extractors.get_gold_reserves_share()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'gold_reserves_share_pct': data.get('gold_reserves_share_pct'),
        }])
        append_to_csv('gold_reserves_share.csv', df)
        return {'indicator': 'Gold Reserves Share', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_credit_etf_proxies():
    """Extract HYG, LQD, JNK intraday credit spread proxies to CSVs."""
    print("\n📊 Extracting Credit ETF Proxies (HYG, LQD, JNK)...")
    results = []
    try:
        data = fidenza_extractors.get_credit_etf_proxies()
        mapping = {
            'HYG': ('hyg_price', 'hyg_credit_proxy.csv'),
            'LQD': ('lqd_price', 'lqd_credit_proxy.csv'),
            'JNK': ('jnk_price', 'jnk_credit_proxy.csv'),
        }
        for ticker, (key, csv_name) in mapping.items():
            etf_data = data.get(ticker, {})
            if isinstance(etf_data, dict) and 'error' in etf_data:
                print(f"  ❌ {ticker}: {etf_data['error']}")
                continue
            hist = etf_data.get('historical')
            if hist is not None and not hist.empty:
                df = pd.DataFrame({
                    'timestamp': hist.index,
                    'date': hist.index.date,
                    f'{ticker.lower()}_price': hist.values,
                })
                append_to_csv(csv_name, df)
                print(f"  ✅ {ticker} → {csv_name} | Last: {df['date'].max()} | Rows: {len(df)}")
                results.append({'indicator': ticker, 'last_date': str(df['date'].max()), 'rows': len(df)})
            else:
                print(f"  ⚠️ {ticker}: No historical data")
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
    return results if results else None


# ──────────────────────────────────────────────────────────────────────────────
# Data Extraction Requirements — OHLCV + New Indicators
# ──────────────────────────────────────────────────────────────────────────────

# ── Commodity OHLCV (P0-1) ──────────────────────────────────────────────────

def extract_gold_ohlcv():
    """Extract Gold futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Gold Futures', commodities_extractors.get_gold,
                                 'gold_ohlcv.csv', 'gold')


def extract_silver_ohlcv():
    """Extract Silver futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Silver Futures', commodities_extractors.get_silver,
                                 'silver_ohlcv.csv', 'silver')


def extract_crude_oil_ohlcv():
    """Extract Crude Oil futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Crude Oil Futures', commodities_extractors.get_crude_oil,
                                 'crude_oil_ohlcv.csv', 'crude_oil')


def extract_copper_ohlcv():
    """Extract Copper futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Copper Futures', commodities_extractors.get_copper,
                                 'copper_ohlcv.csv', 'copper')


# ── ES/RTY Futures OHLCV (P0-3) ────────────────────────────────────────────

def extract_es_futures_ohlcv():
    """Extract ES Futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('ES Futures', yfinance_extractors.get_es_futures,
                                 'es_futures_ohlcv.csv', 'es')


def extract_rty_futures_ohlcv():
    """Extract RTY Futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('RTY Futures', yfinance_extractors.get_rty_futures,
                                 'rty_futures_ohlcv.csv', 'rty')


# ── Brent Crude OHLCV (P1-4) ───────────────────────────────────────────────

def extract_brent_crude_ohlcv():
    """Extract Brent Crude futures OHLCV (2-year history)."""
    return _extract_ohlcv_series('Brent Crude', fidenza_extractors.get_brent_crude,
                                 'brent_crude_ohlcv.csv', 'brent')


# ── S&P 500 Expanded Fundamentals (P0-2) ────────────────────────────────────

def extract_sp500_fundamentals_expanded():
    """Extract expanded S&P 500 fundamentals (forward P/E, earnings yield, etc.)."""
    print("\n📊 Extracting S&P 500 Expanded Fundamentals...")
    try:
        data = openbb_extractors.get_sp500_fundamentals_historical()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'date': datetime.now().date(),
            'pe_ratio_trailing': data.get('sp500_pe_trailing'),
            'pe_ratio_forward': data.get('sp500_pe_forward'),
            'pb_ratio': data.get('sp500_pb'),
            'earnings_yield': data.get('earnings_yield'),
            'forward_earnings_yield': data.get('forward_earnings_yield'),
            'dividend_yield_pct': data.get('dividend_yield_pct'),
            'trailing_eps': data.get('trailing_eps'),
            'forward_eps': data.get('forward_eps'),
            'spy_price': data.get('spy_price'),
        }])
        append_to_csv('sp500_fundamentals.csv', df)
        _declare_sp500_fundamentals()
        return {'indicator': 'S&P 500 Expanded Fundamentals', 'last_date': df['date'].max(), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Existing Home Sales (P1-5) ──────────────────────────────────────────────

def extract_existing_home_sales():
    """Extract Existing Home Sales (FRED EXHOSLUSM495S) to CSV."""
    return _extract_simple_series(
        'Existing Home Sales', fred_extractors.get_existing_home_sales,
        'existing_home_sales.csv', 'existing_home_sales',
    )


# ── Sector ETFs (P2-12) ────────────────────────────────────────────────────

def extract_sector_etfs():
    """Extract 11 SPDR sector ETF prices to a single wide-format CSV."""
    print("\n📊 Extracting Sector ETFs...")
    try:
        data = yfinance_extractors.get_sector_etfs()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        # Build wide DataFrame from all sector historical series
        sector_tickers = list(yfinance_extractors.SECTOR_ETFS.keys())
        frames = {}
        for ticker in sector_tickers:
            hist = data.get(f'historical_{ticker.lower()}')
            if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
                frames[f'{ticker.lower()}_close'] = hist

        if not frames:
            print("  ⚠️  No sector ETF data")
            return None

        # Merge all series on date
        combined = pd.DataFrame(frames)
        combined.index.name = 'timestamp'
        df = combined.reset_index()
        df['date'] = [d.date() if hasattr(d, 'date') else d for d in df['timestamp']]
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        append_to_csv('sector_etfs.csv', df)
        return {'indicator': 'Sector ETFs', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── VIX Term Structure (P2-11) ──────────────────────────────────────────────

def extract_vix_term_structure():
    """Extract VIX term structure (spot, front-month, contango ratio) to CSV."""
    print("\n📊 Extracting VIX Term Structure...")
    try:
        data = yfinance_extractors.get_vix_term_structure()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None

        hist_spot = data.get('historical_vix_spot')
        hist_front = data.get('historical_vix_front')
        hist_contango = data.get('historical_contango')

        if hist_spot is None or hist_spot.empty:
            print("  ⚠️  No VIX spot data")
            return None

        # Strip tz and normalize
        for s in [hist_spot, hist_front, hist_contango]:
            if s is not None and hasattr(s.index, 'tz') and s.index.tz is not None:
                s.index = s.index.tz_localize(None)
            if s is not None:
                s.index = s.index.normalize()

        df = pd.DataFrame({
            'timestamp': hist_spot.index,
            'date': [d.date() if hasattr(d, 'date') else d for d in hist_spot.index],
            'vix_spot': hist_spot.values,
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        if hist_front is not None and not hist_front.empty:
            df_front = pd.DataFrame({
                'timestamp': hist_front.index,
                'vix_front_month': hist_front.values,
            })
            df_front['timestamp'] = pd.to_datetime(df_front['timestamp'])
            df = pd.merge(df, df_front, on='timestamp', how='left')

        if hist_contango is not None and not hist_contango.empty:
            df_contango = pd.DataFrame({
                'timestamp': hist_contango.index,
                'contango_ratio': hist_contango.values,
            })
            df_contango['timestamp'] = pd.to_datetime(df_contango['timestamp'])
            df = pd.merge(df, df_contango, on='timestamp', how='left')

        append_to_csv('vix_term_structure.csv', df)
        return {'indicator': 'VIX Term Structure', 'last_date': df['date'].max(), 'rows': len(df)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Put/Call Ratio (P2-10) ──────────────────────────────────────────────────

def extract_put_call_ratio():
    """Extract Put/Call ratio to CSV."""
    return _extract_simple_series(
        'Put/Call Ratio', yfinance_extractors.get_put_call_ratio,
        'put_call_ratio.csv', 'put_call_ratio',
    )


# ── High-Frequency Macro Proxies (P2-13) ────────────────────────────────────

def extract_gdpnow():
    """Extract Atlanta Fed GDPNow (FRED GDPNOW) to CSV."""
    return _extract_simple_series(
        'GDPNow', fred_extractors.get_gdpnow,
        'gdpnow.csv', 'gdpnow',
    )


def extract_wei():
    """Extract NY Fed Weekly Economic Index (FRED WEI) to CSV."""
    return _extract_simple_series(
        'Weekly Economic Index', fred_extractors.get_weekly_economic_index,
        'wei.csv', 'wei',
    )


def extract_baltic_dry_index():
    """Extract Baltic Dry Index (^BDI) to CSV."""
    return _extract_simple_series(
        'Baltic Dry Index', yfinance_extractors.get_baltic_dry_index,
        'baltic_dry_index.csv', 'bdi',
    )


# ──────────────────────────────────────────────────────────────────────────────
# Financial Agent v1.5-v1.9 — 27 FRED Series Batch Extraction
# ──────────────────────────────────────────────────────────────────────────────

def extract_financial_agent_historical():
    """Batch-extract all 27 Financial Agent FRED series to individual CSVs.

    Uses the SERIES_MAP from financial_agent_extractors.py to fetch all series
    in one pass, then writes each to historical_data/{key}.csv with columns:
    timestamp, date, {value_column}.
    """
    print("\n📊 Extracting Financial Agent FRED series (27 series)...")
    try:
        batch_results = get_all_financial_agent_series()
    except (ValueError, Exception) as e:
        print(f"  ❌ Error: {str(e)}")
        return None
    results = []

    for key, (series_id, col_name) in FA_SERIES_MAP.items():
        data = batch_results.get(key, {})
        if 'error' in data:
            print(f"  ❌ {key} ({series_id}): {data['error']}")
            continue

        hist = data.get('historical')
        if isinstance(hist, pd.Series):
            hist = hist.dropna()  # FRED marks holidays NaN; don't write empty observations
        if hist is None or (hasattr(hist, 'empty') and hist.empty):
            print(f"  ⚠️  {key}: no historical data")
            continue

        try:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                col_name: hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            csv_filename = f'{key}.csv'
            append_to_csv(csv_filename, df, replace_daily_dates=True)
            results.append({
                'indicator': f'{key} ({series_id})',
                'last_date': df['date'].max(),
                'rows': len(df),
            })
        except Exception as e:
            print(f"  ❌ {key}: {str(e)}")

    # Gold price via yfinance (FRED LBMA series discontinued)
    try:
        gold_data = get_gold_price_yfinance()
        if 'error' not in gold_data:
            hist = gold_data['historical']
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'gold_price_fred': hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('gold_price_fred.csv', df)
            results.append({
                'indicator': 'gold_price_fred (GC=F via yfinance)',
                'last_date': df['date'].max(),
                'rows': len(df),
            })
        else:
            print(f"  ❌ gold_price_fred: {gold_data['error']}")
    except Exception as e:
        print(f"  ❌ gold_price_fred: {str(e)}")

    print(f"  ✅ Financial Agent: {len(results)}/27 series extracted")
    return results


# ──────────────────────────────────────────────────────────────────────────────
# OpenBB-Based Indicators (v2.5.0) — 20 CSV Export Wrappers
# ──────────────────────────────────────────────────────────────────────────────

def extract_vix_futures_curve():
    """Extract VIX Futures Curve to CSV."""
    return _extract_simple_series(
        'VIX Futures Curve', openbb_extractors.get_vix_futures_curve,
        'vix_futures_curve.csv', 'vix_spot',
    )


def extract_spy_put_call_oi():
    """Extract SPY Put/Call OI to CSV."""
    print("\n📊 Extracting SPY Put/Call OI...")
    try:
        data = openbb_extractors.get_spy_put_call_oi()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'put_call_ratio': hist.values
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('spy_put_call_oi.csv', df)
            return {'indicator': 'SPY Put/Call OI', 'last_date': df['date'].max(), 'rows': len(df)}
        # No historical series — save snapshot
        latest = data.get('put_call_volume_ratio')
        if latest is not None:
            df = pd.DataFrame([{
                'timestamp': pd.Timestamp.now(),
                'date': datetime.now().date(),
                'put_call_volume_ratio': latest,
                'put_call_oi_ratio': data.get('put_call_oi_ratio'),
            }])
            append_to_csv('spy_put_call_oi.csv', df)
            return {'indicator': 'SPY Put/Call OI', 'last_date': str(datetime.now().date()), 'rows': 1}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sp500_multiples():
    """Extract S&P 500 Multiples (forward P/E, PEG) to CSV."""
    print("\n📊 Extracting S&P 500 Multiples...")
    try:
        data = openbb_extractors.get_sp500_historical_multiples()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'date': datetime.now().date(),
            'forward_pe': data.get('forward_pe'),
            'peg_ratio': data.get('peg_ratio'),
            'price_to_sales': data.get('price_to_sales'),
        }])
        append_to_csv('sp500_multiples.csv', df)
        return {'indicator': 'S&P 500 Multiples', 'last_date': str(datetime.now().date()), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_ecb_rates():
    """Extract ECB Policy Rates to CSV."""
    return _extract_simple_series(
        'ECB Policy Rates', openbb_extractors.get_ecb_policy_rates,
        'ecb_rates.csv', 'deposit_rate',
    )


def extract_oecd_cli():
    """Extract OECD Composite Leading Indicator to CSV."""
    return _extract_simple_series(
        'OECD CLI', openbb_extractors.get_oecd_leading_indicator,
        'oecd_cli.csv', 'cli_value',
    )


def extract_cpi_components():
    """Extract CPI Components to CSV."""
    return _extract_simple_series(
        'CPI Components', openbb_extractors.get_cpi_components,
        'cpi_components.csv', 'headline_cpi',
    )


def extract_fama_french():
    """Extract Fama-French 5 Factors to CSV."""
    print("\n📊 Extracting Fama-French 5 Factors...")
    try:
        data = openbb_extractors.get_fama_french_factors()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        hist = data.get('historical')
        if hist is not None and isinstance(hist, pd.DataFrame) and not hist.empty:
            df = hist.copy()
            if 'date' not in df.columns and df.index is not None:
                df['date'] = df.index
            df['timestamp'] = pd.to_datetime(df['date']) if 'date' in df.columns else pd.to_datetime(df.index)
            append_to_csv('fama_french_5factors.csv', df)
            return {'indicator': 'Fama-French 5 Factors', 'last_date': str(df.index[-1])[:10], 'rows': len(df)}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_iv_skew():
    """Extract SPX IV Skew to CSV."""
    return _extract_simple_series(
        'SPX IV Skew', openbb_extractors.get_spx_iv_skew,
        'spx_iv_skew.csv', 'skew_index',
    )


def extract_eu_yields():
    """Extract European Government Yields to CSV."""
    print("\n📊 Extracting European Yields...")
    try:
        data = openbb_extractors.get_european_yields()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'date': datetime.now().date(),
            'de_10y': data.get('de_10y'),
            'fr_10y': data.get('fr_10y'),
            'it_10y': data.get('it_10y'),
            'it_de_spread': data.get('it_de_spread'),
        }])
        append_to_csv('european_yields.csv', df)
        return {'indicator': 'European Yields', 'last_date': str(datetime.now().date()), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_global_cpi():
    """Extract Global CPI Comparison to CSV."""
    return _extract_simple_series(
        'Global CPI', openbb_extractors.get_global_cpi_comparison,
        'global_cpi.csv', 'us_cpi_yoy',
    )


# earnings_calendar.csv is a point-in-time SNAPSHOT LOG, one row per (as-of date, symbol).
EARNINGS_CALENDAR_COLUMNS = ['timestamp', 'date', 'symbol', 'report_date', 'source']


def _earnings_source_label(source):
    s = (source or '').lower()
    return 'finviz' if 'finviz' in s else 'yfinance' if 'yfinance' in s else (source or 'unknown')


def _earnings_snapshot(earnings, source, asof=None):
    """One day's snapshot of upcoming report dates in the EARNINGS_CALENDAR_COLUMNS layout.

    Accepts either provider's records: the yfinance fallback gives {symbol, date}, the
    OpenBB/Finviz path gives {symbol, report_date, name, eps_consensus, ...}. Only the
    (symbol, report date) pair is kept, so a provider switch cannot change the schema.
    """
    df = pd.DataFrame(earnings)
    rd_col = next((c for c in ('report_date', 'date') if c in df.columns), None)
    if rd_col is None or 'symbol' not in df.columns:
        return pd.DataFrame(columns=EARNINGS_CALENDAR_COLUMNS)
    day = pd.Timestamp(asof if asof is not None else datetime.now()).normalize()
    symbol = df['symbol'].where(df['symbol'].notna(), '').astype(str).str.strip().str.upper()
    # A report date is a calendar day: keep the YYYY-MM-DD part of whatever the provider
    # sent (str, date, or a tz-aware Timestamp) instead of converting between zones.
    report = pd.to_datetime(df[rd_col].astype(str).str.slice(0, 10), errors='coerce', format='%Y-%m-%d')
    snap = pd.DataFrame({
        'timestamp': day,
        'date': day.strftime('%Y-%m-%d'),
        'symbol': symbol,
        'report_date': report.dt.strftime('%Y-%m-%d'),
        'source': _earnings_source_label(source),
    }, index=df.index)
    snap = snap[(snap['symbol'] != '') & report.notna()]
    # One row per symbol: the soonest date if a provider lists a symbol twice.
    snap = snap.sort_values(['report_date', 'symbol'], kind='stable').drop_duplicates('symbol', keep='first')
    return snap.sort_values('symbol', kind='stable')[EARNINGS_CALENDAR_COLUMNS].reset_index(drop=True)


def _earnings_schema_guard(existing, new):
    """Refuse to append to an earnings_calendar.csv in any other layout (never mix schemas)."""
    if existing is not None and len(existing) and list(existing.columns) != EARNINGS_CALENDAR_COLUMNS:
        # Two known causes, both handled by the repair script: the pre-2026-09-21 layout
        # (symbol,date,extraction_date), or that layout's rows appended to this one by
        # pre-2026-09-21 code (adds an extraction_date column). Anything else it refuses.
        raise ValueError(f"earnings_calendar.csv has columns {list(existing.columns)}, expected "
                         f"{EARNINGS_CALENDAR_COLUMNS} — run scripts/repair_adp_earnings_20260921.py "
                         f"(dry run), then with --apply; not written")
    return new


def extract_earnings_calendar():
    """Append today's snapshot of upcoming report dates to earnings_calendar.csv.

    The file is a point-in-time SNAPSHOT LOG with key (date, symbol):
        timestamp, date  the as-of day (midnight) the provider was asked
        symbol           ticker
        report_date      the next report date the provider gave that day
        source           'yfinance' (Top-10 fallback) or 'finviz' (OpenBB)
    A symbol repeats once per day while its report date firms up and rolls to the next
    quarter; that history is the content. The 5 daily runs collapse to one row per
    (date, symbol), last run wins. It is deliberately NOT one row per report: overwriting
    an estimated date with the later confirmed one would leak hindsight into as-of reads.

    Until 2026-09-21 each run appended its rows verbatim as `symbol,date,extraction_date`
    with date = the REPORT date (append_to_csv skips de-duplication without a timestamp
    column): 6,720 rows holding 1,470 (day, symbol) facts, which the feed scanner read as
    1,036 conflicting repeat-dates and 671 out-of-order rows.
    """
    print("\n📊 Extracting Earnings Calendar...")
    try:
        data = openbb_extractors.get_upcoming_earnings()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        earnings = data.get('earnings', [])
        if not earnings:
            return None
        snap = _earnings_snapshot(earnings, data.get('source', ''))
        if snap.empty:
            print("  ⚠️  No usable (symbol, report date) pairs in the earnings response — not written")
            return None
        append_to_csv('earnings_calendar.csv', snap, subset=['timestamp', 'symbol'],
                      guard=_earnings_schema_guard, sort_by=['timestamp', 'symbol'])
        return {'indicator': 'Earnings Calendar', 'last_date': str(snap['date'].iloc[0]), 'rows': len(snap)}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_sector_pe_ratios():
    """Extract Sector P/E Ratios to CSV."""
    print("\n📊 Extracting Sector P/E Ratios...")
    try:
        data = openbb_extractors.get_sector_pe_ratios()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        sectors = data.get('sectors', {})
        if sectors:
            row = {'timestamp': pd.Timestamp.now(), 'date': datetime.now().date()}
            row.update(sectors)
            df = pd.DataFrame([row])
            append_to_csv('sector_pe_ratios.csv', df)
            return {'indicator': 'Sector P/E Ratios', 'last_date': str(datetime.now().date()), 'rows': 1}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_full_treasury_curve():
    """Extract Full Treasury Yield Curve to CSV."""
    print("\n📊 Extracting Treasury Curve...")
    try:
        data = openbb_extractors.get_full_treasury_curve()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        curve = data.get('curve', {})
        if curve:
            row = {'timestamp': pd.Timestamp.now(), 'date': datetime.now().date()}
            row.update(curve)
            df = pd.DataFrame([row])
            append_to_csv('full_treasury_curve.csv', df)
            return {'indicator': 'Treasury Curve', 'last_date': str(datetime.now().date()), 'rows': 1}
        return None
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_corporate_spreads():
    """Extract Corporate Bond Spreads (AAA/BBB) to CSV."""
    print("\n📊 Extracting Corporate Spreads...")
    try:
        data = openbb_extractors.get_corporate_bond_spreads()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        # Use AAA historical series if available
        hist = data.get('aaa_historical')
        if hist is not None and isinstance(hist, pd.Series) and not hist.empty:
            df = pd.DataFrame({
                'timestamp': hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in hist.index],
                'aaa_oas': hist.values,
            })
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            append_to_csv('corporate_spreads_aaa.csv', df)
        # Also save BBB
        bbb_hist = data.get('bbb_historical')
        if bbb_hist is not None and isinstance(bbb_hist, pd.Series) and not bbb_hist.empty:
            df_bbb = pd.DataFrame({
                'timestamp': bbb_hist.index,
                'date': [d.date() if hasattr(d, 'date') else d for d in bbb_hist.index],
                'bbb_oas': bbb_hist.values,
            })
            df_bbb['timestamp'] = pd.to_datetime(df_bbb['timestamp'])
            append_to_csv('corporate_spreads_bbb.csv', df_bbb)
        return {'indicator': 'Corporate Spreads', 'last_date': data.get('latest_date', ''), 'rows': len(hist) if hist is not None else 0}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


def extract_intl_unemployment():
    """Extract International Unemployment Rates to CSV."""
    return _extract_simple_series(
        'International Unemployment', openbb_extractors.get_international_unemployment,
        'intl_unemployment.csv', 'us_unemployment',
    )


def extract_intl_gdp():
    """Extract International GDP Growth to CSV."""
    return _extract_simple_series(
        'International GDP', openbb_extractors.get_international_gdp,
        'intl_gdp.csv', 'us_gdp_growth',
    )


def extract_money_measures():
    """Extract Money Supply Measures (M1/M2) to CSV."""
    return _extract_simple_series(
        'Money Measures', openbb_extractors.get_money_measures,
        'money_measures.csv', 'm2_level',
    )


def extract_global_pmi_openbb():
    """Extract Global Manufacturing PMI to CSV."""
    return _extract_simple_series(
        'Global PMI', openbb_extractors.get_global_pmi,
        'global_pmi.csv', 'us_mfg_pmi',
    )


def extract_equity_risk_premium():
    """Extract Equity Risk Premium to CSV."""
    print("\n📊 Extracting Equity Risk Premium...")
    try:
        data = openbb_extractors.get_equity_risk_premium()
        if isinstance(data, dict) and 'error' in data:
            print(f"  ❌ Error: {data['error']}")
            return None
        df = pd.DataFrame([{
            'timestamp': pd.Timestamp.now(),
            'date': datetime.now().date(),
            'erp': data.get('equity_risk_premium'),
            'forward_erp': data.get('forward_erp'),
            'earnings_yield': data.get('earnings_yield'),
            'real_yield_10y': data.get('real_yield_10y'),
        }])
        append_to_csv('equity_risk_premium.csv', df)
        return {'indicator': 'Equity Risk Premium', 'last_date': str(datetime.now().date()), 'rows': 1}
    except Exception as e:
        print(f"  ❌ Error: {str(e)}")
        return None


# ── Macro-release consensus + surprises (data_extractors/consensus_extractors.py) ──
# ForexFactory's weekly calendar (sell-side forecast/previous, current week only) and Kalshi's threshold
# ladders (market-implied median) are snapshotted into macro_consensus.csv; macro_surprises.csv then
# scores every passed release against its FRED first-release actual. See the module docstring.

def extract_macro_consensus():
    """ForexFactory + Kalshi consensus snapshot -> macro_consensus.csv (the day's last snapshot per release wins)."""
    print("\n📊 Extracting macro-release consensus (ForexFactory + Kalshi)...")
    try:
        from data_extractors import consensus_extractors as cx
        res = cx.run_snapshot(data_dir=OUTPUT_DIR)
        if res['status'] == 'failed':
            print(f"  ❌ Error: every consensus source failed: {'; '.join(res['failures'])}")
            return None
        declare_columns(cx.CONSENSUS_FILE, **cx.CONSENSUS_CONTRACT)
        return {'indicator': 'Macro Consensus (FF+Kalshi)', 'last_date': res['asof'], 'rows': res['rows']}
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        return None


def extract_macro_surprises():
    """macro_consensus.csv + FRED first releases -> macro_surprises.csv (releases of the last 60 days refreshed)."""
    print("\n📊 Extracting macro-release surprises (FRED first-release actuals)...")
    try:
        from datetime import timedelta
        from data_extractors import consensus_extractors as cx
        since = datetime.now(timezone.utc).date() - timedelta(days=cx.SURPRISE_LOOKBACK_DAYS)
        res = cx.run_surprises(data_dir=OUTPUT_DIR, since=since)
        if res['status'] == 'failed':
            print(f"  ❌ Error: FRED failed for every pending release: {'; '.join(res['failures'])}")
            return None
        declare_columns(cx.SURPRISES_FILE, **cx.SURPRISES_CONTRACT)
        return {'indicator': 'Macro Surprises', 'last_date': str(datetime.now(timezone.utc).date()),
                'rows': res['rows']}
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        return None


def extract_futures_history():
    """Append finished sessions to vx_cfe_curve / vx_front_ohlcv / ief_ohlcv / zn_futures_ohlcv."""
    try:
        from data_extractors import futures_history_extractors as fhx
        # _run reads item['indicator'] outside any try: keep only well-formed result dicts
        res = [r for r in (fhx.extract_futures_history(OUTPUT_DIR) or []) if isinstance(r, dict) and r.get('indicator')]
        return res or None
    except Exception as e:
        print(f"  Error: futures history: {type(e).__name__}: {e}")
        return None


def extract_all_historical_data():
    """
    Extract all available historical data and save to CSV files.

    Each indicator is saved to a separate CSV file with timestamps.
    New data is appended to existing files (no overwrite).
    """
    print("=" * 80)
    print("HISTORICAL DATA EXTRACTION")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    ensure_output_directory()

    # Load metadata
    metadata = load_metadata()
    print(f"\nLast extraction: {metadata.get('last_extraction', 'Never')}")

    results = []

    # Helper to run an extraction and record the result
    def _run(extract_fn, meta_key):
        r = extract_fn()
        if r is not None:
            if isinstance(r, list):
                results.extend(r)
                for item in r:
                    metadata['indicators'][item['indicator']] = item
            else:
                results.append(r)
                metadata['indicators'][meta_key] = r

    # ── Original indicators ──────────────────────────────────
    _run(extract_russell_2000_historical, 'russell_2000')
    _run(extract_sp500_with_ma200, 'sp500_ma200')
    _run(extract_vix_move, 'vix_move')
    _run(extract_dxy, 'dxy')
    _run(extract_shiller_cape, 'shiller_cape')
    _run(extract_sp500_fundamentals, 'sp500_fundamentals')
    _run(extract_cboe_skew, 'cboe_skew')
    _run(extract_fred_indicators, 'fred')

    # ── Indicators 11-12: FRED (10Y yield, ISM PMI) ─────────
    _run(extract_10y_yield, '10y_yield')
    _run(extract_ism_pmi, 'ism_pmi')

    # ── Indicators 13-16: Commodities ────────────────────────
    _run(extract_gold, 'gold')
    _run(extract_silver, 'silver')
    _run(extract_crude_oil, 'crude_oil')
    _run(extract_copper, 'copper')

    # ── Indicators 17-18: Futures ────────────────────────────
    _run(extract_es_futures, 'es_futures')
    _run(extract_rty_futures, 'rty_futures')

    # ── Indicator 20: JPY Exchange Rate ──────────────────────
    _run(extract_jpy, 'jpy')

    # ── Indicator 22: CFTC COT Positioning ───────────────────
    _run(extract_cot_positioning, 'cot_positioning')

    # ── Indicator 83: CFTC COT Energy & Copper ────────────────
    _run(extract_cot_energy_metals, 'cot_energy_metals')

    # ── Indicators 23-25: TGA, Net Liquidity, SOFR ──────────
    _run(extract_tga_balance, 'tga_balance')
    _run(extract_net_liquidity, 'net_liquidity')
    _run(extract_sofr, 'sofr')

    # ── Indicators 26-28: US 2Y, Japan 2Y, Spread ───────────
    _run(extract_us_2y_yield, 'us_2y_yield')
    _run(extract_japan_2y_yield, 'japan_2y_yield')
    _run(extract_us2y_jp2y_spread, 'us2y_jp2y_spread')

    # ── Indicator 29: Large-cap Equity Financials ────────────
    _run(extract_equity_financials, 'equity_financials')

    # ── Indicators 30+: Macro-to-Market v1.5 ──────────────────

    # Inflation
    _run(extract_cpi_headline, 'cpi_headline')
    _run(extract_core_cpi, 'core_cpi')
    _run(extract_core_pce, 'core_pce')
    _run(extract_pce_headline, 'pce_headline')
    _run(extract_ppi, 'ppi')
    _run(extract_breakeven_5y, 'breakeven_5y')
    _run(extract_breakeven_10y, 'breakeven_10y')
    _run(extract_forward_inflation_5y5y, 'forward_inflation_5y5y')

    # Employment
    _run(extract_unemployment_rate, 'unemployment_rate')
    _run(extract_nonfarm_payrolls, 'nonfarm_payrolls')
    _run(extract_initial_claims, 'initial_claims')
    _run(extract_continuing_claims, 'continuing_claims')

    # Yield Curve
    _run(extract_5y_yield, 'us_5y_yield')
    _run(extract_30y_yield, 'us_30y_yield')
    _run(extract_spread_10y3m, 'spread_10y3m')
    _run(extract_fed_funds_rate, 'fed_funds_rate')
    _run(extract_fed_target_upper, 'fed_target_upper')
    _run(extract_real_yield_5y, 'real_yield_5y')
    _run(extract_real_yield_10y, 'real_yield_10y')

    # Credit Spreads
    _run(extract_hy_oas, 'hy_oas')
    _run(extract_ig_oas, 'ig_oas')
    _run(extract_bbb_oas, 'bbb_oas')

    # ── Fidenza Macro Gap-Fill Indicators ──────────────────────
    # High priority
    _run(extract_sofr_futures, 'sofr_futures')
    _run(extract_brent_crude, 'brent_crude')
    _run(extract_nikkei_225, 'nikkei_225')
    _run(extract_aaii_sentiment, 'aaii_sentiment')
    _run(extract_em_indices, 'em_indices')

    # Medium priority
    _run(extract_fed_funds_futures, 'fed_funds_futures')
    _run(extract_xau_jpy, 'xau_jpy')
    _run(extract_gold_silver_ratio, 'gold_silver_ratio')
    _run(extract_adp_employment, 'adp_employment')
    _run(extract_adp_employment_weekly, 'adp_employment_weekly')
    _run(extract_fed_balance_sheet, 'fed_balance_sheet')
    _run(extract_treasury_term_premia, 'treasury_term_premia')

    # Lower priority (may fail gracefully — no EIA key / WGC 404)
    _run(extract_opec_production, 'opec_production')
    _run(extract_gold_reserves_share, 'gold_reserves_share')

    # Intraday credit spread proxies
    _run(extract_credit_etf_proxies, 'credit_etf_proxies')

    # ── Data Extraction Requirements — OHLCV + New Indicators ──
    # P0: Commodity + Futures OHLCV (2-year)
    _run(extract_gold_ohlcv, 'gold_ohlcv')
    _run(extract_silver_ohlcv, 'silver_ohlcv')
    _run(extract_crude_oil_ohlcv, 'crude_oil_ohlcv')
    _run(extract_copper_ohlcv, 'copper_ohlcv')
    _run(extract_es_futures_ohlcv, 'es_futures_ohlcv')
    _run(extract_rty_futures_ohlcv, 'rty_futures_ohlcv')
    _run(extract_brent_crude_ohlcv, 'brent_crude_ohlcv')

    # P0: S&P 500 expanded fundamentals
    _run(extract_sp500_fundamentals_expanded, 'sp500_fundamentals_expanded')

    # P1: New FRED series
    _run(extract_existing_home_sales, 'existing_home_sales')

    # P2: New yfinance datasets
    _run(extract_sector_etfs, 'sector_etfs')
    _run(extract_vix_term_structure, 'vix_term_structure')
    _run(extract_put_call_ratio, 'put_call_ratio')
    _run(extract_baltic_dry_index, 'baltic_dry_index')

    # P2: High-frequency macro proxies (FRED)
    _run(extract_gdpnow, 'gdpnow')
    _run(extract_wei, 'wei')

    # ── Financial Agent v1.5-v1.9 — 27 FRED Series ────────────
    _run(extract_financial_agent_historical, 'financial_agent')

    # ── OpenBB-Based Indicators (v2.5.0) ────────────────────────
    _run(extract_vix_futures_curve, 'vix_futures_curve')
    _run(extract_spy_put_call_oi, 'spy_put_call_oi')
    _run(extract_sp500_multiples, 'sp500_multiples')
    _run(extract_ecb_rates, 'ecb_rates')
    _run(extract_oecd_cli, 'oecd_cli')
    _run(extract_cpi_components, 'cpi_components')
    _run(extract_fama_french, 'fama_french')
    _run(extract_iv_skew, 'iv_skew')
    _run(extract_eu_yields, 'eu_yields')
    _run(extract_global_cpi, 'global_cpi')
    _run(extract_earnings_calendar, 'earnings_calendar')
    _run(extract_sector_pe_ratios, 'sector_pe_ratios')
    _run(extract_full_treasury_curve, 'full_treasury_curve')
    _run(extract_corporate_spreads, 'corporate_spreads')
    _run(extract_intl_unemployment, 'intl_unemployment')
    _run(extract_intl_gdp, 'intl_gdp')
    _run(extract_money_measures, 'money_measures')
    _run(extract_global_pmi_openbb, 'global_pmi')
    _run(extract_equity_risk_premium, 'equity_risk_premium')

    # ── Macro-release consensus & surprises (ForexFactory + Kalshi; FRED first-release actuals) ──
    _run(extract_macro_consensus, 'macro_consensus')
    _run(extract_macro_surprises, 'macro_surprises')

    # ── Tradable-instrument history for CC execution (VX CBOE, IEF, ZN=F; append-only) ──
    _run(extract_futures_history, 'futures_history')

    # Create summary file
    create_summary_file(results)

    # Save metadata
    save_metadata(metadata)

    # Print summary
    print("\n" + "=" * 80)
    print("EXTRACTION SUMMARY")
    print("=" * 80)
    print(f"Successfully extracted {len(results)} indicator groups")
    print(f"\nFiles saved to: {OUTPUT_DIR}/")
    print("\nExtracted indicators:")
    for result in results:
        print(f"  ✅ {result['indicator']:30} | Last date: {result['last_date']} | Rows: {result['rows']}")

    print("\n" + "=" * 80)
    print(f"Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    return results


if __name__ == "__main__":
    extract_all_historical_data()
