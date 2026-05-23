"""
IBKR Real-Time Streaming Module for macro_2.

Self-contained IBKR streaming service — no imports from the IBKR repo.
Provides real-time tick-level market data for futures, FX, and indices.

Uses ib_async (the renamed successor of ib_insync).
Falls back to ib_insync if ib_async is not available.

Classes:
    StreamingQuote:        In-memory quote with session tracking
    IBKRContractFactory:   Contract creation with auto-expiry
    IBKRStreamingService:  Connection, streaming, and quote management
"""

import json
import logging
import math
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Callable

# Import ib_async (preferred) or fall back to ib_insync
try:
    from ib_async import IB, ContFuture, Future, Forex, Index, Contract, Ticker
except ImportError:
    from ib_insync import IB, ContFuture, Future, Forex, Index, Contract, Ticker

logger = logging.getLogger(__name__)

# ── Ports to try for auto-detection ──────────────────────────────────────
AUTO_DETECT_PORTS = [7496, 7497, 4001, 4002]

PORT_LABELS = {
    7496: "TWS Live",
    7497: "TWS Paper",
    4001: "Gateway Live",
    4002: "Gateway Paper",
}

# ── Instrument definitions ───────────────────────────────────────────────

# Trading class overrides for ambiguous symbols
# SI on COMEX has both SI (5000oz full) and SIL (1000oz micro) — we want SI.
_TRADING_CLASS_OVERRIDES = {
    "SI": "SI",
}


@dataclass
class InstrumentSpec:
    """Specification for a streamable instrument."""
    symbol: str
    name: str
    contract_type: str  # "future", "forex", "index"
    exchange: str
    csv_file: Optional[str]     # Target CSV in historical_data/ (None = summary only)
    csv_column: str             # Column name for the price value
    multiplier: Optional[float] = None

    def create_contract(self):
        """Create the ib_async/ib_insync Contract object.

        Futures use ContFuture (continuous front-month) — IBKR automatically
        resolves to the nearest-expiry contract. No manual expiry calculation.
        """
        if self.contract_type == "future":
            kwargs = dict(
                symbol=self.symbol,
                exchange=self.exchange,
                currency="USD",
            )
            # Disambiguate ambiguous symbols
            if self.symbol in _TRADING_CLASS_OVERRIDES:
                kwargs["tradingClass"] = _TRADING_CLASS_OVERRIDES[self.symbol]
            return ContFuture(**kwargs)
        elif self.contract_type == "forex":
            return Forex(pair=self.symbol)
        elif self.contract_type == "index":
            return Index(symbol=self.symbol, exchange=self.exchange, currency="USD")
        else:
            raise ValueError(f"Unknown contract type: {self.contract_type}")


# Master instrument map — all symbols to stream
INSTRUMENTS: dict[str, InstrumentSpec] = {
    # Index futures
    "ES":  InstrumentSpec("ES",  "E-mini S&P 500",       "future", "CME",   "es_futures.csv",   "es_price",         50),
    "NQ":  InstrumentSpec("NQ",  "E-mini Nasdaq 100",    "future", "CME",   None,               "nq_price",         20),
    "RTY": InstrumentSpec("RTY", "E-mini Russell 2000",  "future", "CME",   "rty_futures.csv",   "rty_price",        50),
    # Precious metals
    "GC":  InstrumentSpec("GC",  "Gold Futures",         "future", "COMEX", "gold.csv",          "gold_price",       100),
    "SI":  InstrumentSpec("SI",  "Silver Futures",       "future", "COMEX", "silver.csv",         "silver_price",     5000),
    "HG":  InstrumentSpec("HG",  "Copper Futures",       "future", "COMEX", "copper.csv",         "copper_price",     25000),
    # Energy
    "CL":  InstrumentSpec("CL",  "Crude Oil Futures",    "future", "NYMEX", "crude_oil.csv",      "crude_oil_price",  1000),
    "NG":  InstrumentSpec("NG",  "Natural Gas Futures",  "future", "NYMEX", "natural_gas_fred.csv","natural_gas",     10000),
    # Treasury futures
    "ZN":  InstrumentSpec("ZN",  "10-Year T-Note",       "future", "CBOT",  None,               "zn_price",         1000),
    "ZB":  InstrumentSpec("ZB",  "30-Year T-Bond",       "future", "CBOT",  None,               "zb_price",         1000),
    "ZF":  InstrumentSpec("ZF",  "5-Year T-Note",        "future", "CBOT",  None,               "zf_price",         1000),
    "ZT":  InstrumentSpec("ZT",  "2-Year T-Note",        "future", "CBOT",  None,               "zt_price",         2000),
    # Micro treasury yield (quote directly in yield terms)
    "10Y": InstrumentSpec("10Y", "Micro 10Y Yield",      "future", "CBOT",  None,               "micro_10y_yield",  1000),
    "2YY": InstrumentSpec("2YY", "Micro 2Y Yield",       "future", "CBOT",  None,               "micro_2y_yield",   2000),
    # VIX index
    "VIX": InstrumentSpec("VIX", "CBOE VIX Index",       "index",  "CBOE",  None,               "vix_ibkr"),
    # FX
    "EURUSD": InstrumentSpec("EURUSD", "EUR/USD",        "forex",  "IDEALPRO", None,            "eurusd"),
    "USDJPY": InstrumentSpec("USDJPY", "USD/JPY",        "forex",  "IDEALPRO", "jpy.csv",       "jpy_rate"),
}


# ── Quote storage ────────────────────────────────────────────────────────

def _valid_float(value) -> Optional[float]:
    """Validate a ticker float field (handles None, NaN, non-positive)."""
    if value is None:
        return None
    try:
        f = float(value)
        if math.isnan(f) or f <= 0:
            return None
        return f
    except (ValueError, TypeError):
        return None


def _optional_float(value) -> Optional[float]:
    """Extract float that may be NaN (allows zero/negative)."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _valid_int(value) -> Optional[int]:
    """Validate a ticker integer field."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if math.isnan(f) else int(f)
    except (ValueError, TypeError):
        return None


@dataclass
class StreamingQuote:
    """In-memory real-time quote with session tracking."""
    symbol: str

    # Resolved contract identifiers (filled at subscription time)
    local_symbol: Optional[str] = None    # e.g. "GCM6" (front-month)
    expiry: Optional[str] = None          # e.g. "20260626" (YYYYMMDD)
    contract_id: Optional[int] = None     # IBKR conId

    # Core price fields
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    volume: Optional[int] = None

    # Session tracking
    open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    prev_close: Optional[float] = None

    # Derived (computed on each tick)
    change: Optional[float] = None
    change_pct: Optional[float] = None

    # Generic tick fields (106=IV, 411=HV, 588=OI)
    implied_volatility: Optional[float] = None
    hist_volatility: Optional[float] = None
    futures_open_interest: Optional[int] = None

    # Metadata
    tick_count: int = 0
    last_update: Optional[datetime] = None

    @property
    def mid(self) -> Optional[float]:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "local_symbol": self.local_symbol,
            "expiry": self.expiry,
            "contract_id": self.contract_id,
            "last": self.last,
            "bid": self.bid,
            "ask": self.ask,
            "mid": self.mid,
            "change": self.change,
            "change_pct": self.change_pct,
            "open": self.open,
            "session_high": self.session_high,
            "session_low": self.session_low,
            "prev_close": self.prev_close,
            "volume": self.volume,
            "implied_volatility": self.implied_volatility,
            "hist_volatility": self.hist_volatility,
            "futures_open_interest": self.futures_open_interest,
            "tick_count": self.tick_count,
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }


# ── Streaming service ────────────────────────────────────────────────────

class IBKRStreamingService:
    """Manages IBKR connection, contract streaming, and in-memory quotes.

    Thread-safe: the IB event loop runs in a daemon thread; the main thread
    reads snapshots and writes JSON/CSV via get_snapshot().
    """

    GENERIC_TICK_LIST = "106,411,588"  # IV, HV, Futures OI

    def __init__(self, host: str = "127.0.0.1", port: Optional[int] = None,
                 client_id: int = 31):
        self.host = host
        self.port = port  # None = auto-detect
        self.client_id = client_id
        self.ib = IB()

        self._lock = threading.Lock()
        self._quotes: dict[str, StreamingQuote] = {}
        self._contracts: dict[str, Contract] = {}
        self._tickers: dict[str, Ticker] = {}
        self._instruments: dict[str, InstrumentSpec] = {}  # current spec per symbol
        self._connected = False
        self._ib_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Cross-thread request queue (main thread -> IB event loop thread).
        # Each item: ("swap", symbol, expiry|None) or ("list", symbol, response_list)
        # Only the IB thread may touch self.ib for stateful calls.
        import queue as _queue
        self._request_queue: _queue.Queue = _queue.Queue()

    # ── Connection ────────────────────────────────────────────────────

    def connect(self) -> bool:
        """Connect to IBKR TWS/Gateway. Returns True on success."""
        ports = [self.port] if self.port else AUTO_DETECT_PORTS

        for p in ports:
            label = PORT_LABELS.get(p, f"port {p}")
            try:
                self.ib.connect(
                    host=self.host,
                    port=p,
                    clientId=self.client_id,
                    readonly=True,
                    timeout=10,
                )
                self._connected = True
                logger.info(f"Connected to IBKR on {self.host}:{p} ({label})")
                return True
            except Exception as e:
                logger.debug(f"Port {p} ({label}) failed: {e}")
                continue

        logger.warning(f"Could not connect to IBKR on any port ({ports})")
        return False

    def is_connected(self) -> bool:
        return self._connected and self.ib.isConnected()

    def disconnect(self):
        """Disconnect from IBKR."""
        self._connected = False
        try:
            self.ib.disconnect()
        except Exception:
            pass

    # ── Streaming ─────────────────────────────────────────────────────

    def start_streaming(self, instruments: dict[str, InstrumentSpec],
                        manifest: Optional[dict] = None) -> dict[str, bool]:
        """Start real-time streaming for all instruments.

        Returns dict of {symbol: success_bool}. Failed symbols are logged
        but don't block others.

        Args:
            instruments: dict of symbol -> InstrumentSpec (defaults: front month).
            manifest: optional dict of {symbol: {"expiry": "YYYYMMDD"}} to pin
                      specific expiries instead of using ContFuture front-month.
        """
        results = {}
        # Save instrument specs so swap_subscription can rebuild contracts later
        self._instruments.update(instruments)
        manifest = manifest or {}

        for sym, spec in instruments.items():
            try:
                # Honor manifest pinning: if manifest specifies an expiry for this
                # symbol, build a Future with that explicit expiry instead of
                # ContFuture. Falls back to ContFuture (front month) otherwise.
                pinned = manifest.get(sym)
                if (
                    pinned
                    and not pinned.get("reset_to_front_month")
                    and pinned.get("expiry")
                    and spec.contract_type == "future"
                ):
                    expiry = pinned["expiry"]
                    kwargs = dict(
                        symbol=spec.symbol,
                        lastTradeDateOrContractMonth=expiry,
                        exchange=spec.exchange,
                        currency="USD",
                    )
                    if spec.symbol in _TRADING_CLASS_OVERRIDES:
                        kwargs["tradingClass"] = _TRADING_CLASS_OVERRIDES[spec.symbol]
                    contract = Future(**kwargs)
                    logger.info(f"{sym}: pinned to expiry {expiry} from manifest")
                else:
                    contract = spec.create_contract()
                qualified = self.ib.qualifyContracts(contract)
                if not qualified or qualified[0].conId == 0:
                    logger.warning(f"Could not qualify {sym} ({contract})")
                    results[sym] = False
                    continue

                contract = qualified[0]

                # CRITICAL: ContFuture is a continuous-future SYNTHETIC contract that
                # works for reqHistoricalData but NOT for reqMktData live ticks.
                # Convert to a regular Future using the resolved conId/localSymbol/expiry.
                if spec.contract_type == "future" and isinstance(contract, ContFuture):
                    contract = Future(
                        conId=contract.conId,
                        symbol=contract.symbol,
                        lastTradeDateOrContractMonth=contract.lastTradeDateOrContractMonth,
                        exchange=contract.exchange,
                        currency=contract.currency,
                        localSymbol=contract.localSymbol,
                        multiplier=contract.multiplier,
                        tradingClass=contract.tradingClass,
                    )

                self._contracts[sym] = contract
                self._quotes[sym] = StreamingQuote(
                    symbol=sym,
                    local_symbol=getattr(contract, "localSymbol", None),
                    expiry=getattr(contract, "lastTradeDateOrContractMonth", None) or None,
                    contract_id=getattr(contract, "conId", None) or None,
                )

                ticker = self.ib.reqMktData(
                    contract,
                    genericTickList=self.GENERIC_TICK_LIST,
                )

                def on_update(t, s=sym, c=contract):
                    self._on_ticker_update(t, s)

                ticker.updateEvent += on_update
                self._tickers[sym] = ticker

                local_sym = getattr(contract, "localSymbol", sym)
                logger.info(f"Streaming {sym} ({local_sym})")
                results[sym] = True

            except Exception as e:
                logger.error(f"Failed to stream {sym}: {e}")
                results[sym] = False

        return results

    def _on_ticker_update(self, ticker: Ticker, symbol: str) -> None:
        """Internal callback — updates StreamingQuote from ticker data."""
        with self._lock:
            quote = self._quotes.get(symbol)
            if quote is None:
                return

            bid = _valid_float(ticker.bid)
            ask = _valid_float(ticker.ask)
            last = _valid_float(ticker.last)
            volume = _valid_int(ticker.volume)
            open_price = _valid_float(ticker.open)
            high = _valid_float(ticker.high)
            low = _valid_float(ticker.low)
            close = _valid_float(ticker.close)  # prev session close

            if bid is not None:
                quote.bid = bid
            if ask is not None:
                quote.ask = ask
            if last is not None:
                quote.last = last
            if volume is not None:
                quote.volume = volume
            if open_price is not None:
                quote.open = open_price
            if close is not None:
                quote.prev_close = close
            if high is not None:
                quote.session_high = high
            if low is not None:
                quote.session_low = low

            # Track session extremes from last price
            if last is not None:
                if quote.session_high is None or last > quote.session_high:
                    quote.session_high = last
                if quote.session_low is None or last < quote.session_low:
                    quote.session_low = last

            # Change from previous close
            if quote.last is not None and quote.prev_close is not None and quote.prev_close > 0:
                quote.change = quote.last - quote.prev_close
                quote.change_pct = (quote.change / quote.prev_close) * 100

            # Generic ticks: IV, HV, OI
            iv = _optional_float(getattr(ticker, "impliedVolatility", None))
            if iv is not None:
                quote.implied_volatility = iv
            hv = _optional_float(getattr(ticker, "histVolatility", None))
            if hv is not None:
                quote.hist_volatility = hv
            oi = _valid_int(getattr(ticker, "futuresOpenInterest", None))
            if oi is not None:
                quote.futures_open_interest = oi

            quote.tick_count += 1
            quote.last_update = datetime.now()

    def stop_streaming(self):
        """Cancel all market data subscriptions."""
        for sym, contract in self._contracts.items():
            try:
                self.ib.cancelMktData(contract)
            except Exception:
                pass
        self._tickers.clear()
        logger.info("All market data cancelled")

    # ── Snapshot ──────────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Thread-safe snapshot of all quotes for JSON serialization."""
        with self._lock:
            return {sym: q.to_dict() for sym, q in self._quotes.items()}

    # ── Cross-thread request API ──────────────────────────────────────
    # These methods are CALLED from the main thread but PROCESSED on the
    # IB event loop thread. They enqueue a request and wait for the result.

    def request_swap_subscription(self, symbol: str, expiry: Optional[str],
                                  timeout: float = 20.0) -> dict:
        """Queue a subscription swap. Returns when complete (or timeout).

        Args:
            symbol: instrument symbol (e.g. "GC")
            expiry: YYYYMMDD string to pin, or None to reset to front-month
            timeout: max seconds to wait for IB thread to process

        Returns: {"ok": bool, "symbol": str, "old": str, "new": str, "error": str?}
        """
        result_holder: dict = {}
        done = threading.Event()
        self._request_queue.put(("swap", symbol, expiry, result_holder, done))
        if not done.wait(timeout=timeout):
            return {"ok": False, "symbol": symbol, "error": "Timeout waiting for IB thread"}
        return result_holder

    def request_list_contracts(self, symbol: str,
                               timeout: float = 30.0) -> dict:
        """Queue a contract-list request. Returns when complete (or timeout).

        Returns: {"ok": bool, "symbol": str, "contracts": [...], "error": str?}
        """
        result_holder: dict = {}
        done = threading.Event()
        self._request_queue.put(("list", symbol, None, result_holder, done))
        if not done.wait(timeout=timeout):
            return {"ok": False, "symbol": symbol, "contracts": [],
                    "error": "Timeout waiting for IB thread"}
        return result_holder

    # ── Internal: methods called on IB thread ─────────────────────────

    def _do_swap_subscription(self, symbol: str, expiry: Optional[str]) -> dict:
        """Cancel current subscription for symbol, subscribe to new expiry.

        Runs on IB event loop thread.
        expiry=None or "" means reset to front-month (ContFuture).
        """
        spec = self._instruments.get(symbol)
        if spec is None:
            return {"ok": False, "symbol": symbol,
                    "error": f"Unknown symbol {symbol} (not in INSTRUMENTS)"}

        if spec.contract_type != "future":
            return {"ok": False, "symbol": symbol,
                    "error": f"Cannot swap expiry for non-future {symbol}"}

        old_local = None
        old_contract = self._contracts.get(symbol)
        if old_contract is not None:
            old_local = getattr(old_contract, "localSymbol", None)

        # Build new contract
        try:
            if expiry:
                kwargs = dict(
                    symbol=spec.symbol,
                    lastTradeDateOrContractMonth=expiry,
                    exchange=spec.exchange,
                    currency="USD",
                )
                if spec.symbol in _TRADING_CLASS_OVERRIDES:
                    kwargs["tradingClass"] = _TRADING_CLASS_OVERRIDES[spec.symbol]
                new_contract = Future(**kwargs)
            else:
                # Reset to front-month
                new_contract = spec.create_contract()

            # Use async qualification pumped by ib.sleep — sync wrapper
            # deadlocks here. qualifyContractsAsync returns a coroutine,
            # so wrap in a task to make it a Future.
            import time as _t
            from ib_async import util as _ib_util
            qualified = _ib_util.run(
                self.ib.qualifyContractsAsync(new_contract),
                timeout=10,
            )
            if not qualified or qualified[0].conId == 0:
                return {"ok": False, "symbol": symbol,
                        "error": f"Could not qualify new contract (expiry={expiry})"}
            new_contract = qualified[0]

            # ContFuture -> Future for live data
            if isinstance(new_contract, ContFuture):
                new_contract = Future(
                    conId=new_contract.conId,
                    symbol=new_contract.symbol,
                    lastTradeDateOrContractMonth=new_contract.lastTradeDateOrContractMonth,
                    exchange=new_contract.exchange,
                    currency=new_contract.currency,
                    localSymbol=new_contract.localSymbol,
                    multiplier=new_contract.multiplier,
                    tradingClass=new_contract.tradingClass,
                )
        except Exception as e:
            return {"ok": False, "symbol": symbol, "error": f"Build/qualify error: {e}"}

        # Cancel old subscription
        if old_contract is not None:
            try:
                self.ib.cancelMktData(old_contract)
            except Exception as e:
                logger.warning(f"Cancel old {symbol} failed: {e}")
        self._tickers.pop(symbol, None)

        # Subscribe new
        try:
            ticker = self.ib.reqMktData(
                new_contract,
                genericTickList=self.GENERIC_TICK_LIST,
            )

            def on_update(t, s=symbol):
                self._on_ticker_update(t, s)

            ticker.updateEvent += on_update

            with self._lock:
                self._contracts[symbol] = new_contract
                self._tickers[symbol] = ticker
                # Reset quote with new contract metadata
                self._quotes[symbol] = StreamingQuote(
                    symbol=symbol,
                    local_symbol=getattr(new_contract, "localSymbol", None),
                    expiry=getattr(new_contract, "lastTradeDateOrContractMonth", None) or None,
                    contract_id=getattr(new_contract, "conId", None) or None,
                )

            new_local = getattr(new_contract, "localSymbol", symbol)
            logger.info(f"Swapped {symbol}: {old_local} -> {new_local}")
            return {
                "ok": True,
                "symbol": symbol,
                "old": old_local,
                "new": new_local,
                "expiry": getattr(new_contract, "lastTradeDateOrContractMonth", None),
                "contract_id": getattr(new_contract, "conId", None),
            }
        except Exception as e:
            return {"ok": False, "symbol": symbol, "error": f"Subscribe error: {e}"}

    def _do_list_contracts(self, symbol: str, max_n: int = 12) -> dict:
        """List available future contracts for a symbol via reqContractDetails.

        Runs on IB event loop thread.
        Returns up to `max_n` future expiries sorted ascending.
        """
        spec = self._instruments.get(symbol)
        if spec is None or spec.contract_type != "future":
            return {"ok": False, "symbol": symbol,
                    "contracts": [],
                    "error": f"{symbol} is not a future or not registered"}

        try:
            partial = Future(
                symbol=spec.symbol,
                exchange=spec.exchange,
                currency="USD",
            )
            if spec.symbol in _TRADING_CLASS_OVERRIDES:
                partial.tradingClass = _TRADING_CLASS_OVERRIDES[spec.symbol]

            logger.info(f"[list] calling reqContractDetailsAsync({spec.symbol}, {spec.exchange})...")
            import time as _t
            from ib_async import util as _ib_util
            _t0 = _t.time()
            # Use ib_async.util.run which properly handles nested loop contexts.
            # The plain sync wrapper (reqContractDetails) deadlocks here because
            # we're already inside the IB event loop's owning thread.
            details = _ib_util.run(
                self.ib.reqContractDetailsAsync(partial),
                timeout=25,
            )
            logger.info(f"[list] {symbol}: got {len(details) if details else 0} contracts in {_t.time()-_t0:.2f}s")
            if not details:
                return {"ok": False, "symbol": symbol, "contracts": [],
                        "error": "No contract details returned"}

            # Filter to futures with future expiries; sort by expiry asc
            from datetime import datetime as _dt
            today_str = _dt.now().strftime("%Y%m%d")
            seen_ids = set()
            rows = []
            for d in details:
                c = d.contract
                exp = c.lastTradeDateOrContractMonth or ""
                # Normalize YYYYMM -> YYYYMM01 for comparison
                exp_cmp = exp if len(exp) >= 8 else (exp + "01")
                if exp_cmp < today_str:
                    continue  # already expired
                if c.conId in seen_ids:
                    continue
                seen_ids.add(c.conId)
                rows.append({
                    "expiry": exp,
                    "local_symbol": c.localSymbol,
                    "contract_id": c.conId,
                    "trading_class": c.tradingClass,
                    "multiplier": c.multiplier,
                })

            rows.sort(key=lambda r: r["expiry"])
            return {"ok": True, "symbol": symbol, "contracts": rows[:max_n]}
        except Exception as e:
            return {"ok": False, "symbol": symbol, "contracts": [],
                    "error": f"reqContractDetails error: {e}"}

    def _drain_request_queue(self):
        """Process pending requests on the IB event loop thread."""
        import queue as _queue
        try:
            while True:
                try:
                    item = self._request_queue.get_nowait()
                except _queue.Empty:
                    return

                try:
                    op, sym, arg, result_holder, done = item
                    logger.info(f"[queue] processing op={op} sym={sym}")
                except (ValueError, TypeError) as e:
                    logger.error(f"[queue] bad request format: {item} ({e})")
                    continue

                try:
                    if op == "swap":
                        result = self._do_swap_subscription(sym, arg)
                    elif op == "list":
                        result = self._do_list_contracts(sym)
                    else:
                        result = {"ok": False, "error": f"Unknown op: {op}"}
                except Exception as e:
                    logger.error(f"[queue] handler crashed: {e}", exc_info=True)
                    result = {"ok": False, "error": f"Handler crashed: {e}"}

                result_holder.update(result)
                done.set()
                logger.info(f"[queue] completed op={op} sym={sym} ok={result.get('ok')}")
        except Exception as e:
            logger.error(f"[queue] drain error: {e}", exc_info=True)

    # ── IB event loop (runs in daemon thread) ─────────────────────────

    def run_event_loop(self, stop_event: threading.Event):
        """Blocking IB event loop. Call from a daemon thread.

        Processes IB events (ticker updates) via ib.sleep() AND drains
        the cross-thread request queue.
        Exits when stop_event is set or connection drops.
        """
        logger.info("IB event loop started")
        try:
            while not stop_event.is_set() and self.ib.isConnected():
                self.ib.sleep(0.5)
                self._drain_request_queue()
        except Exception as e:
            logger.error(f"IB event loop error: {e}")
        finally:
            self._connected = False
            logger.info("IB event loop exited")


# ── JSON snapshot writer ─────────────────────────────────────────────────

def write_realtime_json(snapshot: dict, filepath: str):
    """Atomic JSON write (tempfile + os.replace)."""
    data = {
        "timestamp": datetime.now().isoformat(),
        "status": "streaming",
        "instrument_count": len(snapshot),
        "quotes": snapshot,
    }
    dir_path = os.path.dirname(filepath)
    try:
        fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, default=str)
        os.replace(tmp_path, filepath)
    except OSError as e:
        logger.error(f"Failed to write JSON: {e}")
        try:
            os.remove(tmp_path)
        except OSError:
            pass
