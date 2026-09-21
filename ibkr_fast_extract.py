#!/usr/bin/env python3
"""
IBKR Real-Time Streaming Daemon for macro_2.

Long-running service that streams real-time market data from IBKR
TWS/Gateway and maintains:
  1. data_cache/ibkr_realtime.json  — Atomic JSON snapshot every 3s
  2. historical_data/*.csv          — 5-min summary rows to existing CSVs

Designed to run on VPS alongside IB Gateway (Docker).
yfinance fast_extract.py continues running independently as fallback.

Connection retry: if IBKR is unavailable, retries every 1 hour.
Graceful shutdown on SIGTERM/SIGINT.

Usage:
    python ibkr_fast_extract.py                   # auto-detect port
    python ibkr_fast_extract.py --port 4001       # specify port
    python ibkr_fast_extract.py --dry-run         # list instruments, no connect
    python ibkr_fast_extract.py --client-id 31    # custom client ID

Deployment (VPS):
    systemctl start macro2-ibkr-stream
"""

import argparse
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_extractors.ibkr_streaming import (
    INSTRUMENTS,
    RETIRED_COLUMNS,
    IBKRStreamingService,
    write_realtime_json,
)

# ── Configuration ────────────────────────────────────────────────────────

try:
    import config
    IBKR_HOST = getattr(config, 'IBKR_HOST', '127.0.0.1')
    IBKR_PORT = getattr(config, 'IBKR_PORT', '')
    IBKR_CLIENT_ID = getattr(config, 'IBKR_CLIENT_ID', 31)
    IBKR_JSON_INTERVAL = getattr(config, 'IBKR_JSON_INTERVAL', 3)
    IBKR_CSV_INTERVAL = getattr(config, 'IBKR_CSV_INTERVAL', 300)
    IBKR_RECONNECT_DELAY = getattr(config, 'IBKR_RECONNECT_DELAY', 3600)
    CACHE_DIR = getattr(config, 'CACHE_DIR', 'data_cache')
except ImportError:
    IBKR_HOST = os.getenv('IBKR_HOST', '127.0.0.1')
    IBKR_PORT = os.getenv('IBKR_PORT', '')
    IBKR_CLIENT_ID = int(os.getenv('IBKR_CLIENT_ID', '31'))
    IBKR_JSON_INTERVAL = 3
    IBKR_CSV_INTERVAL = 300
    IBKR_RECONNECT_DELAY = 3600
    CACHE_DIR = 'data_cache'

REALTIME_JSON = os.path.join(CACHE_DIR, 'ibkr_realtime.json')
SUBSCRIPTIONS_JSON = os.path.join(CACHE_DIR, 'ibkr_subscriptions.json')
AVAILABLE_CONTRACTS_JSON = os.path.join(CACHE_DIR, 'ibkr_available_contracts.json')
SUMMARY_CSV = 'ibkr_realtime_summary.csv'
HISTORICAL_DIR = 'historical_data'

# How often to check the manifest file (subscription overrides) for changes
MANIFEST_POLL_SECS = 5
# How often to refresh the available contracts list per symbol (1 hour)
CONTRACTS_REFRESH_SECS = 3600
# Max seconds per symbol for the hourly front-month roll check's qualify request
ROLL_QUALIFY_TIMEOUT = 10

# ── Logging ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    stream=sys.stdout,
)
logger = logging.getLogger('ibkr_extract')

# ── Shutdown event ───────────────────────────────────────────────────────

_shutdown = threading.Event()


def _signal_handler(signum, frame):
    sig_name = signal.Signals(signum).name
    logger.info(f"Received {sig_name}, shutting down...")
    _shutdown.set()


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# ── Manifest / contracts JSON helpers ───────────────────────────────────

def _atomic_write_json(path: str, data: dict):
    """Atomic JSON write via tempfile + os.replace."""
    import json
    import tempfile
    dir_path = os.path.dirname(path) or "."
    os.makedirs(dir_path, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, default=str, indent=2)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _read_json(path: str) -> dict | None:
    """Read JSON file, return None on missing/invalid."""
    import json
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read {path}: {e}")
        return None


def _load_manifest() -> dict:
    """Load subscription manifest, return dict of {symbol: {expiry, ...}}."""
    data = _read_json(SUBSCRIPTIONS_JSON)
    if not data:
        return {}
    return data.get("subscriptions", {})


def _ensure_default_manifest():
    """If no manifest exists, write an empty one so the backend can edit it."""
    if os.path.exists(SUBSCRIPTIONS_JSON):
        return
    _atomic_write_json(SUBSCRIPTIONS_JSON, {
        "updated_at": datetime.now().isoformat(),
        "subscriptions": {},
        "_note": "Edit via POST /api/ibkr/subscribe. Empty subscriptions = front month for all.",
    })


def _refresh_available_contracts(service: IBKRStreamingService, args):
    """Query available expiries for all future symbols and write to JSON.

    Uses a SEPARATE short-lived IB connection (clientId = stream + 100) on the
    main thread to avoid threading deadlocks with the streaming daemon's
    long-lived ib.sleep() loop.  The streaming connection is left untouched.
    """
    from datetime import datetime as _dt
    try:
        from ib_async import IB, Future
    except ImportError:
        from ib_insync import IB, Future

    # Separate clientId so the streaming subscription isn't disturbed
    side_client_id = (args.client_id or 31) + 100

    ib = IB()
    try:
        # Reuse the same port the streaming service connected on
        port = args.port or 4001
        ib.connect(args.host, port, clientId=side_client_id, readonly=True, timeout=10)
    except Exception as e:
        logger.warning(f"Could not open side connection for contracts refresh: {e}")
        return

    contracts = {}
    today_str = _dt.now().strftime("%Y%m%d")

    try:
        from data_extractors.ibkr_streaming import _TRADING_CLASS_OVERRIDES
        for sym, spec in INSTRUMENTS.items():
            if spec.contract_type != "future":
                continue
            try:
                partial = Future(symbol=spec.symbol, exchange=spec.exchange, currency="USD")
                if spec.symbol in _TRADING_CLASS_OVERRIDES:
                    partial.tradingClass = _TRADING_CLASS_OVERRIDES[spec.symbol]
                details = ib.reqContractDetails(partial)
                if not details:
                    logger.warning(f"No contracts for {sym}")
                    continue

                seen = set()
                rows = []
                for d in details:
                    c = d.contract
                    exp = c.lastTradeDateOrContractMonth or ""
                    exp_cmp = exp if len(exp) >= 8 else (exp + "01")
                    if exp_cmp < today_str:
                        continue  # expired
                    if c.conId in seen:
                        continue
                    seen.add(c.conId)
                    rows.append({
                        "expiry": exp,
                        "local_symbol": c.localSymbol,
                        "contract_id": c.conId,
                        "trading_class": c.tradingClass,
                        "multiplier": c.multiplier,
                    })
                rows.sort(key=lambda r: r["expiry"])
                contracts[sym] = rows[:12]
            except Exception as e:
                logger.warning(f"Contract list failed for {sym}: {e}")
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

    if contracts:
        _atomic_write_json(AVAILABLE_CONTRACTS_JSON, {
            "updated_at": datetime.now().isoformat(),
            "contracts": contracts,
        })
        total = sum(len(v) for v in contracts.values())
        logger.info(f"Refreshed available contracts: {len(contracts)} symbols, {total} total expiries")


def _resolve_front_month(symbol: str) -> str | None:
    """Look up the earliest available expiry for a symbol from the contracts file.

    Returns YYYYMMDD string, or None if file missing/empty.
    Used to translate reset_to_front_month=True into an explicit expiry,
    which avoids using ContFuture in the daemon thread (deadlocks during qualify).
    """
    contracts_data = _read_json(AVAILABLE_CONTRACTS_JSON)
    if not contracts_data:
        return None
    rows = contracts_data.get("contracts", {}).get(symbol, [])
    if not rows:
        return None
    # rows are already sorted by expiry asc; first one is front month
    return rows[0].get("expiry")


def _apply_manifest_changes(service: IBKRStreamingService,
                            old_manifest: dict, new_manifest: dict):
    """Diff manifests and request swaps for changed symbols."""
    all_symbols = set(old_manifest.keys()) | set(new_manifest.keys())
    swaps = 0
    for sym in all_symbols:
        old_pin = old_manifest.get(sym, {})
        new_pin = new_manifest.get(sym, {})
        old_exp = old_pin.get("expiry")
        new_exp = new_pin.get("expiry")
        old_reset = old_pin.get("reset_to_front_month", False)
        new_reset = new_pin.get("reset_to_front_month", False)

        if old_exp == new_exp and old_reset == new_reset:
            continue  # no change

        # For reset: translate to explicit front-month expiry to avoid
        # ContFuture qualification deadlock in the daemon thread.
        if new_reset:
            target = _resolve_front_month(sym)
            if not target:
                logger.warning(f"Cannot reset {sym}: no available_contracts data")
                continue
        elif new_exp:
            target = new_exp
        else:
            target = None  # daemon will use ContFuture (only safe at startup)

        # Called directly: this thread pumps the IB loop (see _run_main_loop), so queueing
        # the swap and waiting for another thread to drain it would only time out.
        result = service._do_swap_subscription(sym, target)
        if result.get("ok"):
            logger.info(f"Manifest swap applied: {sym} {result.get('old')} -> {result.get('new')}")
            swaps += 1
        else:
            logger.warning(f"Manifest swap failed for {sym}: {result.get('error')}")
    if swaps:
        logger.info(f"Applied {swaps} manifest changes")


def _roll_front_months(service: IBKRStreamingService, manifest: dict):
    """Follow IB's front-month roll for every future not pinned to an expiry.

    ContFuture is resolved once, at subscribe. While the stream pumped nothing, it
    reconnected every ~30 min and so re-resolved (rolled) as a side effect; a stream that
    stays connected for days must re-resolve explicitly, or an expired contract (the
    monthly 10Y/2YY on their last business day) goes silent until the weekend reconnect.
    Each symbol is checked on its own: one that cannot be qualified must not block the rest.
    """
    try:
        from ib_async import util as _ib_util
    except ImportError:
        from ib_insync import util as _ib_util

    for sym, spec in INSTRUMENTS.items():
        if spec.contract_type != "future":
            continue
        pin = manifest.get(sym) or {}
        if pin.get("expiry") and not pin.get("reset_to_front_month"):
            continue  # user-pinned expiry: leave it alone
        current = service._contracts.get(sym)
        try:
            # Bounded: IB.RequestTimeout is 0 (wait forever) and this thread alone pumps
            # the socket, writes JSON/CSV and runs the stale check.
            qualified = _ib_util.run(service.ib.qualifyContractsAsync(spec.create_contract()),
                                     timeout=ROLL_QUALIFY_TIMEOUT)
            # ib_async 2.x returns [None] (does not raise) for a contract it cannot qualify
            new = qualified[0] if qualified else None
            if new is None or not getattr(new, "conId", 0):
                logger.warning(f"Roll check: could not qualify {sym}; keeping "
                               f"{getattr(current, 'localSymbol', None)}")
                continue
            if current is not None and new.conId == getattr(current, "conId", None):
                continue
            result = service._do_swap_subscription(sym, None)
            if result.get("ok"):
                logger.info(f"Rolled {sym}: {result.get('old')} -> {result.get('new')}")
            else:
                logger.warning(f"Roll of {sym} failed: {result.get('error')}")
        except Exception as e:
            logger.warning(f"Roll check failed for {sym}: {e!r}")


# ── Column contracts ─────────────────────────────────────────────────────

# Instruments that stay in INSTRUMENTS (so they come back by themselves the day the data does)
# but have no data now: their summary column is blank by design, not broken.
UNAVAILABLE_COLUMNS = {
    "vix_ibkr": "IB Error 354: no CBOE index market-data subscription (account decision pending)",
}
CONTRACT_WRITER = "ibkr_fast_extract (macro2-ibkr-stream)"


def _column_contracts() -> list[dict]:
    """declare_columns() kwargs for every CSV this daemon writes (pure; no IB connection).

    The per-instrument files also get daily bars from extract_historical_data's yfinance
    extractors, which write the same single column, so this contract covers both writers.
    """
    columns = [spec.csv_column for spec in INSTRUMENTS.values()]
    unavailable = {c: r for c, r in UNAVAILABLE_COLUMNS.items() if c in columns}
    active = [c for c in columns if c not in unavailable]
    # A retired column that is back in INSTRUMENTS is simply active again.
    retired = {c: dict(m) for c, m in RETIRED_COLUMNS.items() if c not in columns}
    contracts = [dict(filename=SUMMARY_CSV, active=active, retired=retired,
                      unavailable=unavailable, writer=CONTRACT_WRITER)]
    for spec in INSTRUMENTS.values():
        if spec.csv_file is None:
            continue
        col = spec.csv_column
        contracts.append(dict(filename=spec.csv_file,
                              active=[] if col in unavailable else [col],
                              unavailable={col: unavailable[col]} if col in unavailable else {},
                              writer=CONTRACT_WRITER))
    return contracts


def _declare_column_contracts():
    """Refresh the column contracts; never raises (the stream matters more than its paperwork)."""
    try:
        from extract_historical_data import declare_columns
        for kw in _column_contracts():
            declare_columns(**kw)
    except Exception as e:
        logger.warning(f"Column contract declaration failed: {type(e).__name__}: {e}")


# ── CSV write ────────────────────────────────────────────────────────────

# The 'date' column must follow the convention of the daily bars already in each
# file. yfinance dates FX daily bars in London time (the JPY=X bar for D starts at
# 23:00 UTC on D-1 during BST); futures bars sit at New York midnight, where the
# UTC date agrees. Labelling FX rows with the UTC date made jpy.csv's dates step
# backwards every summer night between 23:00 and 24:00 UTC.
_ROW_DATE_TZ = {"forex": ZoneInfo("Europe/London")}


def _row_date(now_utc, spec) -> str:
    tz = _ROW_DATE_TZ.get(spec.contract_type)
    return (now_utc.astimezone(tz) if tz else now_utc).strftime('%Y-%m-%d')


# A price is only worth recording if it actually traded recently. IB serves the last
# trade print indefinitely once a subscription goes quiet or dies, so without this gate
# the 5-minute writer copies a frozen value into the history forever — micro_2y_yield
# kept writing 4.182 for days, and every per-instrument CSV carried ~6 stale rows in 7.
# Keyed on last_price_time (set only when `last` changes), never on last_update.
STALE_PRICE_FACTOR = 3


def _price_is_stale(quote: dict, now: datetime) -> bool:
    ts = quote.get("last_price_time")
    if not ts:
        return True                      # no price timestamp -> treat as unusable
    try:
        seen = datetime.fromisoformat(ts)
    except ValueError:
        return True
    if seen.tzinfo is None:
        seen = seen.replace(tzinfo=now.tzinfo)
    return (now - seen).total_seconds() > STALE_PRICE_FACTOR * IBKR_CSV_INTERVAL


def _write_csv_summary(service: IBKRStreamingService):
    """Append 5-min summary rows to existing CSVs and summary CSV."""
    import pandas as pd
    from extract_historical_data import append_to_csv

    snapshot = service.get_snapshot()
    # Timestamps are naive UTC, like the yfinance rows append_to_csv normalises
    # to (identical to datetime.now() on the UTC VPS; correct on other hosts too).
    now = datetime.now(timezone.utc)
    ts = now.strftime('%Y-%m-%d %H:%M:%S')
    date_str = now.strftime('%Y-%m-%d')

    # Write to individual existing CSVs (matching yfinance format)
    stale = []
    for sym, spec in INSTRUMENTS.items():
        if spec.csv_file is None:
            continue
        quote = snapshot.get(sym)
        if quote is None or quote.get("last") is None:
            continue
        if _price_is_stale(quote, now):
            stale.append(sym)
            continue

        df = pd.DataFrame([{
            'timestamp': ts,
            'date': _row_date(now, spec),
            spec.csv_column: quote['last'],
        }])
        try:
            append_to_csv(spec.csv_file, df)
        except Exception as e:
            logger.warning(f"CSV write failed for {sym} -> {spec.csv_file}: {e}")

    # Write wide-format summary (all instruments in one row)
    summary_row = {'timestamp': ts, 'date': date_str}
    has_data = False
    for sym, spec in INSTRUMENTS.items():
        quote = snapshot.get(sym)
        if quote is not None and quote.get("last") is not None and not _price_is_stale(quote, now):
            summary_row[spec.csv_column] = quote['last']
            has_data = True
        else:
            summary_row[spec.csv_column] = None

    if has_data:
        df = pd.DataFrame([summary_row])
        try:
            append_to_csv(SUMMARY_CSV, df)
        except Exception as e:
            logger.warning(f"Summary CSV write failed: {e}")

    _declare_column_contracts()   # re-stamped at most hourly

    if stale:
        logger.info(f"CSV snapshot: skipped {len(stale)} instrument(s) with a stale price: {','.join(stale)}")
    logger.info(f"CSV snapshot written ({sum(1 for q in snapshot.values() if q.get('last') and not _price_is_stale(q, now))} instruments)")


# ── Main loop ────────────────────────────────────────────────────────────

def _run_main_loop(service: IBKRStreamingService, args=None):
    """Main loop: JSON snapshots every 3s, CSV writes every 5min.

    Blocks until shutdown event or IBKR disconnect.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)

    last_json = 0.0
    last_csv = 0.0

    # The IB socket belongs to the asyncio loop of the thread that connected - this one -
    # and ticks are only read while THAT loop runs, so the pumping happens here via
    # ib.sleep(). It used to happen in a daemon thread, where ib.sleep() spins a fresh,
    # socket-less loop (ib_async's getLoop creates one per thread): ticks then arrived
    # only while this thread happened to run the loop (connect, qualify, the contracts
    # refresh), i.e. one snapshot per 30-min stale-reconnect, repeated in between.
    try:
        service.ib.sleep(3)  # let initial quotes arrive
    except Exception as e:
        logger.error(f"IB event loop error: {e}")
        return

    logger.info("Entering main loop (JSON every %ds, CSV every %ds)",
                IBKR_JSON_INTERVAL, IBKR_CSV_INTERVAL)

    # Stale-subscription detector: if no quote has updated in STALE_WARN_SECS,
    # the IB subscriptions are likely dead (e.g. after a gateway restart).
    # We exit the main loop so the outer retry loop reconnects.
    STALE_WARN_SECS = 1800  # 30 min without ANY tick = likely dead. Was 900s but triggered false reconnects every cycle, stressing gateway. (2026-05-02)
    last_stale_check = time.time()

    # Subscription manifest tracking: poll mtime, apply diffs to IBKR subs
    last_manifest_mtime = 0.0
    last_manifest = _load_manifest()
    last_manifest_check = 0.0

    # Available contracts: refresh hourly so the dashboard dropdown is current
    last_contracts_refresh = 0.0

    # Initial available-contracts refresh (so the dropdown isn't empty)
    try:
        _refresh_available_contracts(service, args)
        last_contracts_refresh = time.time()
    except Exception as e:
        logger.warning(f"Initial contracts refresh failed: {e}")

    while not _shutdown.is_set() and service.is_connected():
        now = time.time()

        # JSON snapshot
        if now - last_json >= IBKR_JSON_INTERVAL:
            snapshot = service.get_snapshot()
            write_realtime_json(snapshot, REALTIME_JSON)
            last_json = now

        # CSV summary
        if now - last_csv >= IBKR_CSV_INTERVAL:
            try:
                _write_csv_summary(service)
            except Exception as e:
                logger.error(f"CSV write error: {e}")
            last_csv = now

        # Subscription manifest watcher: pick up user-driven expiry changes
        if now - last_manifest_check >= MANIFEST_POLL_SECS:
            last_manifest_check = now
            try:
                if os.path.exists(SUBSCRIPTIONS_JSON):
                    mtime = os.path.getmtime(SUBSCRIPTIONS_JSON)
                    if mtime > last_manifest_mtime:
                        new_manifest = _load_manifest()
                        if new_manifest != last_manifest:
                            _apply_manifest_changes(service, last_manifest, new_manifest)
                            last_manifest = new_manifest
                        last_manifest_mtime = mtime
            except Exception as e:
                logger.warning(f"Manifest watch error: {e}")

        # Available-contracts refresh (every CONTRACTS_REFRESH_SECS)
        if now - last_contracts_refresh >= CONTRACTS_REFRESH_SECS:
            last_contracts_refresh = now
            try:
                _refresh_available_contracts(service, args)
            except Exception as e:
                logger.warning(f"Contracts refresh error: {e}")
            try:
                _roll_front_months(service, last_manifest)
            except Exception as e:
                logger.warning(f"Roll check error: {e}")

        # Stale-subscription check every 60s: find the most recent tick across
        # all instruments. If ALL are stale (>15 min old), reconnect.
        if now - last_stale_check >= 60:
            last_stale_check = now
            snapshot = service.get_snapshot()
            most_recent = None
            for q in snapshot.values():
                lu = q.get("last_update")
                if lu:
                    try:
                        t = datetime.fromisoformat(lu).timestamp()
                        if most_recent is None or t > most_recent:
                            most_recent = t
                    except (ValueError, TypeError):
                        pass
            if most_recent is not None:
                age = now - most_recent
                if age > STALE_WARN_SECS:
                    logger.warning(
                        "All IBKR subscriptions appear stale (last tick %ds ago). "
                        "Reconnecting...", int(age)
                    )
                    break  # Exit main loop -> outer loop reconnects

        try:
            service.ib.sleep(0.5)  # pump the IB socket: ticks and request replies
            service._drain_request_queue()
            service.retry_rejected_subscriptions()  # e.g. USDJPY after Error 101
        except Exception as e:  # e.g. ConnectionError("Socket disconnect") -> reconnect
            logger.error(f"IB event loop error: {e}")
            break

    # Write final stopped status
    try:
        import json
        final = {
            "timestamp": datetime.now().isoformat(),
            "status": "stopped",
            "instrument_count": 0,
            "quotes": {},
        }
        with open(REALTIME_JSON, 'w') as f:
            json.dump(final, f)
    except Exception:
        pass


# ── Entry point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='IBKR real-time streaming daemon for macro_2.',
    )
    parser.add_argument('--host', default=IBKR_HOST,
                        help=f'IBKR host (default: {IBKR_HOST})')
    parser.add_argument('--port', type=int, default=None,
                        help='IBKR port (default: auto-detect)')
    parser.add_argument('--client-id', type=int, default=IBKR_CLIENT_ID,
                        help=f'IBKR client ID (default: {IBKR_CLIENT_ID})')
    parser.add_argument('--dry-run', action='store_true',
                        help='List instruments without connecting')
    args = parser.parse_args()

    # Resolve port from args or config
    port = args.port
    if port is None and IBKR_PORT:
        port = int(IBKR_PORT)

    if args.dry_run:
        print(f"IBKR Streaming — {len(INSTRUMENTS)} instruments:")
        print(f"{'Symbol':<8} {'Name':<25} {'Type':<8} {'Exchange':<10} {'CSV':<25} {'Column'}")
        print("-" * 100)
        for sym, spec in INSTRUMENTS.items():
            csv = spec.csv_file or "(summary only)"
            print(f"{sym:<8} {spec.name:<25} {spec.contract_type:<8} {spec.exchange:<10} {csv:<25} {spec.csv_column}")
        return

    logger.info("=" * 60)
    logger.info("IBKR Real-Time Streaming Daemon")
    logger.info(f"  Host: {args.host}")
    logger.info(f"  Port: {port or 'auto-detect'}")
    logger.info(f"  Client ID: {args.client_id}")
    logger.info(f"  Instruments: {len(INSTRUMENTS)}")
    logger.info(f"  JSON interval: {IBKR_JSON_INTERVAL}s")
    logger.info(f"  CSV interval: {IBKR_CSV_INTERVAL}s")
    logger.info(f"  Reconnect delay: {IBKR_RECONNECT_DELAY}s")
    logger.info("=" * 60)

    # Short retry delay for stale-subscription cases (vs. 1hr for auth fail)
    STALE_RETRY_SECS = 30

    # ── Outer retry loop ─────────────────────────────────────────────
    while not _shutdown.is_set():
        # Also while the gateway is down (2FA pending: one pass per hour): the contract says
        # what this writer fills, and a live daemon keeps asserting it.
        _declare_column_contracts()
        service = IBKRStreamingService(
            host=args.host,
            port=port,
            client_id=args.client_id,
        )

        connected_ok = service.connect()
        if connected_ok:
            # Ensure manifest file exists so backend can write to it
            try:
                _ensure_default_manifest()
            except Exception as e:
                logger.warning(f"Could not ensure default manifest: {e}")

            # Load manifest to honor any pinned expiries on first subscribe
            startup_manifest = _load_manifest()

            # Stream all instruments (with manifest pin overrides)
            results = service.start_streaming(INSTRUMENTS, manifest=startup_manifest)
            success = sum(1 for v in results.values() if v)
            failed = sum(1 for v in results.values() if not v)
            logger.info(f"Streaming started: {success} OK, {failed} failed")

            if success > 0:
                _run_main_loop(service, args)
            else:
                logger.error("No instruments connected, will retry shortly")
                connected_ok = False  # treat as bad connection

            # Cleanup
            service.stop_streaming()
            service.disconnect()
        else:
            logger.warning("IBKR connection failed")

        if not _shutdown.is_set():
            # Short retry if connection succeeded once (stale subs / mid-loop exit)
            # Long retry if connection failed (likely 2FA pending, no point hammering)
            delay = STALE_RETRY_SECS if connected_ok else IBKR_RECONNECT_DELAY
            logger.info(f"Retrying in {delay}s...")
            _shutdown.wait(timeout=delay)

    logger.info("IBKR streaming daemon stopped")


if __name__ == '__main__':
    main()
