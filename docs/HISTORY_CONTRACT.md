# Price-history contract: what the CC pipeline reads from `historical_data/`

The CC trading pipeline (`CLI_OS/Agent_Orchestration/CC`, deployed on the VPS at
`/root/Agents/Agent_Orchestration/CC`) reads 12 daily price series. 11 are files in this repo's
`historical_data/`; the 12th is BTC's hourly file from `btc-enhanced-streak-mitigation`. The
pipeline uses them to score forecasts and, from Phase 1 on, to derive stop and target geometry.
This document lists the files, the columns it reads, and the guarantees it depends on.
`scripts/check_history_contract.py` checks those guarantees and exits non-zero when one is broken.

`historical_data/` is git-ignored, so this contract lives in `docs/`.

---

## 1. The reader

Every CC consumer reads through one module, CC `agents/volmath.py`: `build_vol_context.py`,
`build_execution.py` and `check_invalidation.py`. The laptop-only forecast scorer
`backfill/score_forecasts.py` shares its loaders and its `sigma_1d` rule. The data directory is `$CC_PRICE_DATA` if set. Otherwise it is the first that
exists of `/root/macro_2/historical_data` (VPS) and `~/Github/macro_2/historical_data`
(laptop).

**What it computes at pipeline date D:**

| Quantity | Rule | Bars needed at the anchor |
|---|---|---|
| anchor | last bar dated **strictly before** D | 1 |
| `sigma_1d` | stdev of the up-to-20 close-to-close changes ending at the anchor. `None` below 10 changes | **21** for the full 20-change window (11 minimum) |
| `atr14` | mean true range of the 14 bars ending at the anchor. A close-only series is padded o = h = l = c, so its ATR is the mean \|Δclose\| | **15** |
| stale | anchor more than 4 calendar days before D. `build_execution` rejects the asset for that day | — |

An asset without `sigma_1d` or `atr14` is rejected (`no_sigma` / `no_atr`), and so is a stale
one. The idea is dropped rather than traded, which means a thin, gappy or half-written file
quietly shrinks the book. The contract below exists to prevent that.

**How it parses a file.** The guard applies the same rules (`reader_bars()`) and checks them
bar-for-bar against the real reader in its tests.

- The date comes from the `date` column, or from `timestamp` when `date` is blank. Only the
  first 10 characters are read, as `YYYY-MM-DD`. A row whose date does not parse is skipped.
- **OHLC files:** the last raw row for each date wins. After that, the date is dropped if
  any of its four prices fails to parse. A blank close on a date's *last* row therefore
  hides the whole date, even if an earlier row for that date was complete. A literal `nan`
  or `inf` parses and is kept, and it would poison sigma and ATR.
- **Close-only files:** rows whose value is blank, unparseable or NaN are skipped first, and
  then the last remaining row for each date wins.
- **BTC:** the hourly GMT+8 `timestamp` (`YYYY-MM-DD HH:MM:SS`) is shifted to UTC days. Each
  day gets the first open, max high, min low and last close, taken in file order.
- Extra columns (volume, `move`, `vix_move_ratio`) are ignored. So is the order of the columns.

## 2. The files

| CC symbol | File | Columns read | Writer | Refresh (VPS) |
|---|---|---|---|---|
| ES | `es_futures_ohlcv.csv` | `date`, `es_open/high/low/close` | `extract_es_futures_ohlcv` | fast-extract 5 min, full extract 5×/day |
| RTY | `rty_futures_ohlcv.csv` | `date`, `rty_open/high/low/close` | `extract_rty_futures_ohlcv` | same |
| GC | `gold_ohlcv.csv` | `date`, `gold_open/high/low/close` | `extract_gold_ohlcv` | same |
| SI | `silver_ohlcv.csv` | `date`, `silver_open/high/low/close` | `extract_silver_ohlcv` | same |
| HG | `copper_ohlcv.csv` | `date`, `copper_open/high/low/close` | `extract_copper_ohlcv` | same |
| CL | `crude_oil_ohlcv.csv` | `date`, `crude_oil_open/high/low/close` | `extract_crude_oil_ohlcv` | same |
| BZ | `brent_crude_ohlcv.csv` | `date`, `brent_open/high/low/close` | `extract_brent_crude_ohlcv` | same |
| VIX | `vix_move.csv` | `date`, `vix` | `extract_vix_move` | fast-extract 5 min, full extract |
| DXY | `dxy.csv` | `date`, `dxy` | `extract_dxy` | fast-extract 5 min, full extract |
| USDJPY | `jpy.csv` | `date`, `jpy_rate` | `extract_jpy` + `macro2-ibkr-stream` snapshots | fast-extract 5 min + IBKR every 5 min |
| UST10Y_YIELD | `10y_treasury_yield.csv` | `date`, `10y_yield` | `extract_10y_yield` (FRED) | full extract 5×/day Mon–Sat |
| BTC | `/root/btc-enhanced-streak-mitigation/BTC_OHLC_1h_gmt8_updated.csv` | `timestamp`, `open/high/low/close` (hourly, GMT+8) | `update_hourly_ohlc.py` (`btc-hourly-ohlc.timer`) | hourly at :05 |

All the macro_2 writers are in `extract_historical_data.py`. The seven OHLC files go through
`_extract_ohlcv_series`, and `jpy.csv` and `10y_treasury_yield.csv` go through
`_extract_simple_series`. Both helpers end in `append_to_csv(..., replace_daily_dates=True)`.
`vix_move.csv` and `dxy.csv` call `append_to_csv` directly. `macro2-ibkr-stream`
(`ibkr_fast_extract.py`, `_write_csv_summary`) also calls `append_to_csv` to add 5-minute
USDJPY snapshots to `jpy.csv`. It dates them by the London date, matching how yfinance dates
FX bars. The full extract is `macro-extract.timer` (17:00, 00:30, 05:00, 09:00 and 14:00 UTC,
Mon–Sat). Fast-extract is `macro-fast-extract.timer`, which runs every 300 s.

BTC is written outside macro_2 and not under `_csv_lock`. The VPS has no `.lock` file for it.

## 3. Guarantees

For every file above, at every pipeline date D:

1. **Present and shaped.** The file exists, is UTF-8, and its header row has the columns in §2.
2. **Enough history.** There are at least **21 valid bars dated before D**, where a valid bar
   is one the reader keeps. That is a full 20-change `sigma_1d` window, and it also covers the
   15 bars `atr14` needs.
3. **No hollow window.** The most recent 21 valid bars span at most **45 calendar days**, and
   none of them carries a non-finite price. A month-long hole inside the window would make
   `sigma_1d` something other than a 20-session sigma.
4. **Every row is dated.** No row has a blank or unparseable `date`, and no row has a blank or
   unparseable `timestamp` where that column exists. This is the shape of the 2026-09-01
   `gold.csv` fragment: two overlapping writers interleaved their bytes, and the fragment was
   written back with a blank timestamp. It was then re-sorted to the end of the file on every
   write, where "last row = latest price" readers picked it up for two weeks (`QA_SOP.md` Bug
   Log, 2026-09-16).
5. **No blank trailing row.** The last line is a complete, dated row. It is not an empty line,
   a line of bare commas, or a row with a blank date.
6. **Dates never step backwards** in file order. (For BTC, the hourly timestamps never do.)
7. **Writes are locked and atomic.** `append_to_csv` holds `_csv_lock` for the whole
   read-modify-write, which is `fcntl.LOCK_EX` on `historical_data/.<file>.lock`. It writes
   through `_atomic_to_csv`: a temp file, then `os.replace`, keeping the file's mode. Rows whose
   timestamp does not parse are dropped on write, with a warning. The one-off repair scripts
   (`scripts/repair_feed_defects_20260916.py`, `scripts/split_natural_gas_20260921.py`) use the
   same pair. As a result a reader never sees a half-written file. A reader that also wants to
   avoid a version that is about to be replaced takes `LOCK_SH` on the existing lock file.
8. **Fresh.** The anchor is at most 4 calendar days before D. The guard reports a stale anchor
   as a WARN, because the builder rejects that asset for the day rather than failing the run.
   `--strict-fresh` turns it into a FAIL.

The following are expected but not guaranteed. The guard reports them as WARN:

- a date carries at most one *daily* bar;
- OHLC bars are internally consistent: `high >= max(open, close)` and `low <= min(open, close)`;
- every row has the header's field count;
- the file ends with a newline.

## 4. The guard: `scripts/check_history_contract.py`

```
python3 scripts/check_history_contract.py --data-dir DIR [--as-of YYYYMMDD] [--btc PATH]
                                          [--json PATH] [--strict-fresh]
```

| Flag | Meaning |
|---|---|
| `--data-dir` (required) | directory holding the 11 macro_2 files |
| `--as-of` | pipeline date D. Default: today UTC. Bars dated on or after D are ignored, as the reader's anchor rule ignores them |
| `--btc` | BTC hourly file. BTC is reported `SKIP` without it |
| `--json` | also write the machine report (written atomically) |
| `--strict-fresh` | a stale series is a FAIL |

Exit codes: **0** pass (warnings allowed), **1** any FAIL, **2** usage error, a missing
`--data-dir`, or an unwritable `--json`.

It uses only the standard library and runs on any `python3` (tested on 3.10 and 3.13). It never
imports from CC or from `extract_historical_data` (pandas). It does not write into the data
directory.

**Locking.** It takes `fcntl.LOCK_SH` on `.<file>.lock` **only if that lock file already
exists**. It opens the lock read-only and never creates one. It polls for up to 10 s and
reports `lock_timeout` if the lock is still held. It reads the whole file into memory under
the lock, then releases it. The `lock` column shows `shared`, `none` (no lock file) or
`unavailable` (the lock file exists but cannot be opened; the file is then read unlocked, which
is safe because writes are atomic).

**Codes**

| Code | Level | Meaning |
|---|---|---|
| `missing_file` | FAIL | file absent |
| `missing_columns` | FAIL | a §2 column is not in the header (or the file is empty) |
| `unreadable` | FAIL | I/O or UTF-8 decode error |
| `lock_timeout` | FAIL | a writer held the lock for more than 10 s |
| `unparseable_date` | FAIL | row(s) with a blank or unparseable `date`/`timestamp`. The message shows the count and the first line number |
| `blank_trailing_row` | FAIL | the last line is empty, bare commas, or undated |
| `decreasing_dates` | FAIL | a row is dated before an earlier row |
| `insufficient_history` | FAIL | fewer than 21 valid bars before `--as-of` |
| `sparse_window` | FAIL | the last 21 valid bars span more than 45 days |
| `nonfinite_value` | FAIL | NaN/inf among the last 21 bars |
| `stale` | WARN (FAIL with `--strict-fresh`) | anchor 5 or more days before `--as-of` |
| `duplicate_dates` | WARN | a date with more than one daily bar (BTC: a repeated hour) |
| `ohlc_inconsistent` | WARN | an OHLC bar in the last 21 with high < max(o,c) or low > min(o,c) |
| `ragged_rows` | WARN | row(s) whose field count differs from the header |
| `no_final_newline` | WARN | possible torn write |
| `lock_unavailable` | WARN | lock file exists but cannot be opened |

`duplicate_dates` counts **daily bars** only. A daily bar is a row whose `timestamp` is
date-only or on the hour, which is the same split `append_to_csv(replace_daily_dates=True)`
makes. `jpy.csv` on the VPS carries about 300 IBKR 5-minute snapshots per London date by
design, and the reader keeps the last one. Those snapshots are counted in `multi_row_dates` in
the JSON and do not warn.

**Output.** stdout has a table (series, file, rows, bars before as-of, anchor, age, span of the
last 21, lock, status, codes). It ends with one summary line:
`[check_history_contract] PASS|FAIL: n/m series pass …`. Each FAIL goes to stderr as
`[check_history_contract] FAIL <file> (<series>): <code>: <message>`, and each warning as
`[check_history_contract] WARNING: …`. The `--json` report (`schema:
macro2_history_contract_v1`) has `status`, `as_of`, `limits`, `summary`, and one entry per
series. Each entry has `status`, `rows`, `bars`, `bars_total`, `bars_after_as_of`,
`first_date`, `anchor_date`, `age_days`, `window_span_days`, `multi_row_dates`, `lock`, and
`fails`/`warnings` as `[{code, message}]`.

**Tests:** `python3 -m unittest discover -s tests -p 'test_check_history_contract.py'` (24
tests, all on synthetic CSVs in a temp dir). The reader-parity tests import CC `volmath.py`
from `$CC_AGENTS_DIR` (default `~/Github/CLI_OS/Agent_Orchestration/CC/agents`) and skip if
it is absent. They assert, for every series:

- the guard's bars equal the reader's bars;
- the guard's bar count and anchor equal the reader's (`anchor_info()`);
- every series the guard passes is `available` to the builder.

They run on messy synthetic data and on CC's frozen scoring copy (`backfill/inputs/prices`). One
test also fails if the guard's file table or limits drift from `volmath.py`.

## 5. Results, 2026-09-21 (`--as-of 20260921`)

**VPS.** The 11 files and the BTC file were copied with `ssh … cat` at 07:01 UTC. Each copy's
md5 matched the VPS file. The guard ran against that read-only scratch copy.
Result: **PASS, 12/12, exit 0.** Two series warned `ohlc_inconsistent` (see §6). With
`--strict-fresh` the exit is still 0.

| Series | Bars before D | Anchor | Age (days) | Span of last 21 (days) |
|---|---|---|---|---|
| ES / RTY / GC / SI / BZ | 1416 / 1394 / 1277 / 1276 / 1277 | 2026-09-20 | 1 | 24 |
| HG / CL (WARN) | 1277 / 1414 | 2026-09-20 | 1 | 24 |
| BTC | 2456 | 2026-09-20 | 1 | 20 |
| VIX | 1268 | 2026-09-18 | 3 | 28 |
| DXY | 1415 | 2026-09-20 | 1 | 24 |
| USDJPY | 1322 | 2026-09-20 | 1 | 20 |
| UST10Y_YIELD | 16180 | 2026-09-17 | 4 | 29 |

On that copy the guard's bar counts and anchors equal `volmath.anchor_info()`, and all 12
series are `available`.

**Laptop** (`historical_data/`, read under the existing shared locks, no lock file created):
**PASS, 12/12.** It has the same two `ohlc_inconsistent` warnings and the same anchors.

## 6. Known properties (not contract violations)

- **Sunday bars.** The futures OHLC files carry Sunday rows (partial Globex sessions, e.g. ES
  2026-09-20), and the reader counts them as sessions. The scorer and the builder share the
  reader, so the two stay consistent.
- **USDJPY differs by host.** On the VPS, `jpy.csv` gets a Saturday London-date bar every week
  (IBKR snapshots from Friday 23:00 UTC to about 04:00 Saturday) plus a Sunday yfinance bar.
  Its last 21 bars therefore span 20 calendar days, against 25 on the laptop, which has no
  IBKR stream. On the VPS, a USDJPY "close" is the last snapshot of the London date, not the
  yfinance daily close.
- **`vix_move.csv` has MOVE-only rows** with a blank `vix`. The reader skips them.
- **Two Sunday-bar closes sit outside their own range.** yfinance's Sunday bars for HG and CL
  on 2026-09-06 have a close outside the bar's own range: HG closes above its high (6.6825
  against 6.68), and CL closes below its low (91.48 against 91.58). CL's close is exactly the
  Friday 2026-09-04 close. The guard reports both as `ohlc_inconsistent`. The reader uses them
  as they are, and the effect on ATR14 is small.
- **UST10Y_YIELD is at the stale limit every Monday.** FRED lags a business day or two, so a
  Monday run anchors on Thursday at age 4. One more day of lag, such as the Tuesday after a
  Monday holiday, makes it `stale`, and the builder then rejects UST10Y_YIELD for that day.

## 7. Changing anything here

- Renaming one of these files or columns, changing its date convention, or writing to it
  anywhere except through `append_to_csv` (or `_csv_lock` + `_atomic_to_csv`) breaks the
  contract. If you do any of these, update three places: this document, `SERIES` in the guard,
  and CC `volmath.OHLC_SOURCES` / `CLOSE_SOURCES`. Then run the guard and its tests.
- If CC changes `VOL_WINDOW`, `ATR_WINDOW` or `MAX_ANCHOR_AGE_DAYS`, change the guard's
  constants to match. `test_series_table_and_limits_mirror_volmath` fails until they agree.
- To check the VPS without touching it, copy the files out and point `--data-dir` at the copy.
  On the VPS itself the guard is read-only and needs no venv:
  `python3 scripts/check_history_contract.py --data-dir /root/macro_2/historical_data --btc /root/btc-enhanced-streak-mitigation/BTC_OHLC_1h_gmt8_updated.csv`.
