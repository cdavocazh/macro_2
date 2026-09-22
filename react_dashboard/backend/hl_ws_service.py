"""
Hyperliquid WebSocket relay service.

Connects to Hyperliquid's WebSocket API (wss://api.hyperliquid.xyz/ws),
subscribes to real-time data channels (allMids, activeAssetCtx), and
broadcasts updates to connected dashboard clients via FastAPI WebSocket.

Lifecycle: starts when the React dashboard backend starts, stops when it stops.
No standalone launchd service — lives inside the FastAPI process only.

Architecture:
  Hyperliquid WS  →  HyperliquidWSRelay (singleton)  →  FastAPI /ws/hl  →  React clients

Rate limits (per Hyperliquid docs):
  - 10 WebSocket connections per IP
  - 1,000 subscriptions per IP
  - 2,000 messages/min across all WS
  We use 1 connection + 1 subscription — well within limits. The REST context cycle makes
  one metaAndAssetCtxs call per dex (main + each builder dex in HL_PERPS) and one
  spotMetaAndAssetCtxs call every ~10 s.

Instruments and rules come from data_extractors/hyperliquid_extractor.py, the registry
hl_extract.py writes the CSVs from: which perps and spot tickers exist (HL_PERPS,
HL_SPOT_STOCKS), how funding is annualised and OI converted to USD, when a builder listing
is illiquid (flagged, as in the cached indicator) and when a spot pair is untraded (not
published). This module used to keep its own copies, which drifted: XRP/LINK/DOGE/AVAX/SUI
missing, oil on the dead flx:OIL listing, retired spot tickers listed, untraded spot mids
published as prices, and builder perps shown with 0 funding / 0 OI.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _PROJECT_ROOT not in sys.path:     # main.py already adds it; this covers a standalone import
    sys.path.insert(0, _PROJECT_ROOT)

from data_extractors.hyperliquid_extractor import (  # noqa: E402
    HL_API_URL,
    HL_PERPS as _HL_PERPS_REGISTRY,
    HL_SPOT_STOCKS as _HL_SPOT_REGISTRY,
    build_perp_entry,
    context_loaded,
    meta_ctx_payloads,
    parse_meta_and_asset_ctxs,
    spot_pairs_by_token,
    spot_stock_entry,
)

logger = logging.getLogger("hl_ws_relay")

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
PING_INTERVAL = 50  # seconds (HL timeout is 60s)
RECONNECT_BASE = 1.0
RECONNECT_MAX = 60.0

# Views of the extractor registries, kept under the old names. Derived, never edited here.
# Main-universe perps: prices stream over the allMids WebSocket channel.
HL_PERPS = {t: info['key'] for t, info in _HL_PERPS_REGISTRY.items() if 'api_coin' not in info}
# HIP-3 builder perps: absent from allMids; price, funding, OI and volume come from their
# dex's metaAndAssetCtxs context (REST, every ~10 s).
BUILDER_PERPS = {info['api_coin']: info['key'] for info in _HL_PERPS_REGISTRY.values() if 'api_coin' in info}
# HIP-3 spot stocks: ticker -> token index.
HL_SPOT_STOCKS = {t: info['index'] for t, info in _HL_SPOT_REGISTRY.items()}

# Fields of a perp entry the relay publishes (a subset of the extractor's entry).
_PERP_FIELDS = ('price', 'change_1d', 'mark_price', 'oracle_price', 'funding_rate', 'funding_rate_1h',
                'open_interest', 'volume_24h', 'premium', 'illiquid')
# Context-derived fields: None (the dashboard shows N/A) until a context has loaded, rather
# than 0 - the same rule hl_extract.py applies before writing them to hl_perps.csv.
_CONTEXT_FIELDS = ('funding_rate', 'funding_rate_1h', 'open_interest', 'volume_24h', 'premium')


class HyperliquidWSRelay:
    """
    Singleton WebSocket relay that:
    1. Maintains a persistent connection to Hyperliquid WS
    2. Subscribes to allMids for real-time price updates
    3. Holds latest state in memory (no file I/O)
    4. Broadcasts to connected dashboard clients
    """

    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._clients: Set[asyncio.Queue] = set()
        self._reconnect_delay = RECONNECT_BASE
        self._task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None

        # In-memory state: latest data for immediate serving to new clients
        self.latest_perps: Dict = {}
        self.latest_spot: Dict = {}
        self.last_update: Optional[str] = None

        # Context data (from REST, refreshed periodically)
        self._contexts: Dict = {}          # coin (qualified for builder perps) -> parsed context
        self._spot_contexts: Dict = {}     # token index -> (pair index, pair meta, pair context)
        self._context_task: Optional[asyncio.Task] = None

    def add_client(self, queue: asyncio.Queue):
        """Register a dashboard client's message queue."""
        self._clients.add(queue)
        logger.info(f"Client connected. Total: {len(self._clients)}")

    def remove_client(self, queue: asyncio.Queue):
        """Unregister a dashboard client's message queue."""
        self._clients.discard(queue)
        logger.info(f"Client disconnected. Total: {len(self._clients)}")

    async def _broadcast(self, message: dict):
        """Send a message dict to all connected clients."""
        if not self._clients:
            return
        dead = []
        for q in self._clients:
            try:
                q.put_nowait(message)  # Put dict, not string — send_json handles serialization
            except asyncio.QueueFull:
                # Client too slow, drop message
                pass
            except Exception:
                dead.append(q)
        for q in dead:
            self._clients.discard(q)

    def _ingest_perp_contexts(self, replies) -> None:
        """Merge parsed metaAndAssetCtxs replies (main universe + builder dexes) into the cache.

        A dex whose call failed keeps its previous contexts: only coins present in a reply
        are replaced."""
        merged = dict(self._contexts)
        for raw in replies:
            merged.update(parse_meta_and_asset_ctxs(raw))
        self._contexts = merged

    def _ingest_spot(self, raw) -> None:
        """Cache the name-keyed spot pair contexts from one spotMetaAndAssetCtxs reply."""
        if isinstance(raw, list) and len(raw) >= 2 and isinstance(raw[0], dict):
            pairs = spot_pairs_by_token(raw[0].get('universe', []), raw[1] or [])
            if pairs:
                self._spot_contexts = pairs

    async def _fetch_contexts_rest(self):
        """
        Periodically fetch full context data (funding, OI, volume, builder-perp mids) via REST.
        allMids WebSocket only gives main-universe prices; contexts come from REST: one
        metaAndAssetCtxs per dex (meta_ctx_payloads) and one spotMetaAndAssetCtxs per cycle.
        """
        import httpx

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    replies = []
                    limited = False
                    for payload in meta_ctx_payloads():
                        try:
                            resp = await client.post(HL_API_URL, json=payload)
                            if resp.status_code == 429:
                                limited = True
                                break
                            if resp.status_code == 200:
                                replies.append(resp.json())
                        except Exception:
                            pass  # keep this dex's cached contexts
                        await asyncio.sleep(0.3)  # brief pause between API calls
                    if replies:
                        self._ingest_perp_contexts(replies)
                    if limited:
                        logger.debug("HL rate limited, backing off")
                        await asyncio.sleep(30)
                        continue

                    # Spot contexts (1 call)
                    try:
                        resp2 = await client.post(HL_API_URL, json={"type": "spotMetaAndAssetCtxs"})
                        if resp2.status_code == 200:
                            self._ingest_spot(resp2.json())
                    except Exception:
                        pass  # Keep using cached spot contexts

            except Exception as e:
                logger.debug(f"REST context fetch cycle error: {e}")

            await asyncio.sleep(10)  # 10s between full context cycles

    def _perp_entry(self, hl_ticker: str, mids: Dict[str, str], now: str) -> Optional[Dict]:
        """One published perp entry, or None when the extractor has no price for it."""
        try:
            entry = build_perp_entry(hl_ticker, mids, self._contexts)
        except (TypeError, ValueError):
            return None
        if not isinstance(entry, dict) or 'error' in entry or not entry.get('price'):
            return None
        out = {f: entry.get(f) for f in _PERP_FIELDS}
        if not context_loaded(entry):
            out.update({f: None for f in _CONTEXT_FIELDS})
        if entry.get('illiquid'):
            out['note'] = entry.get('note')
        if 'api_coin' in _HL_PERPS_REGISTRY[hl_ticker]:
            out['api_coin'] = entry.get('api_coin')
        out['latest_date'] = now
        return out

    def _build_perp_snapshot(self, mids: Dict[str, str]) -> Dict:
        """Build perp data for every HL_PERPS instrument from allMids + cached contexts.

        Main-universe perps take their price from the allMids message; builder perps take
        theirs from the dex context (they are not in allMids). An illiquid builder listing
        (no OI, no 24h volume) is published with illiquid=True, exactly as the cached
        indicator is, and the dashboard frames it as an inactive market."""
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        result = {}
        for hl_ticker, info in _HL_PERPS_REGISTRY.items():
            entry = self._perp_entry(hl_ticker, mids, now)
            if entry is not None:
                result[info['key']] = entry
        result['latest_date'] = now
        result['source'] = 'Hyperliquid WS'
        return result

    def _build_spot_snapshot(self) -> Dict:
        """Build spot stock data from cached spot contexts. Untraded pairs are not published."""
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        result = {}
        for ticker, info in _HL_SPOT_REGISTRY.items():
            try:
                entry = spot_stock_entry(ticker, info, self._spot_contexts.get(info['index']))
            except (TypeError, ValueError):
                continue
            if 'price' not in entry:
                continue          # pair missing, no mid, or untraded (stale mid withheld)
            result[ticker.lower()] = {
                'price': entry['price'],
                'change_1d': entry.get('change_1d', 0.0),
                'volume_24h': entry.get('volume_24h'),
                'latest_date': now,
                'source': 'Hyperliquid HIP-3 WS',
            }

        result['latest_date'] = now
        result['source'] = 'Hyperliquid HIP-3 WS'
        return result

    async def _handle_message(self, message: str):
        """Process an incoming WebSocket message from Hyperliquid."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            return

        channel = data.get('channel')

        if channel == 'allMids':
            mids = data.get('data', {}).get('mids', {})
            if mids:
                perps = self._build_perp_snapshot(mids)
                spot = self._build_spot_snapshot()
                self.latest_perps = perps
                self.latest_spot = spot
                self.last_update = datetime.now(timezone.utc).isoformat()

                await self._broadcast({
                    'type': 'hl_update',
                    'perps': perps,
                    'spot': spot,
                    'timestamp': self.last_update,
                })

        elif channel == 'pong':
            pass  # heartbeat response, nothing to do

        elif channel == 'subscriptionResponse':
            logger.info(f"Subscription confirmed: {data.get('data', {})}")

        elif channel == 'error':
            logger.warning(f"HL WS error: {data.get('data')}")

    async def _ping_loop(self):
        """Send ping every PING_INTERVAL seconds to keep connection alive."""
        while self._running and self._ws:
            try:
                await asyncio.sleep(PING_INTERVAL)
                if self._ws and self._ws.open:
                    await self._ws.send(json.dumps({"method": "ping"}))
            except Exception:
                break

    async def _connect_and_listen(self):
        """Connect to HL WebSocket, subscribe, and listen for messages."""
        try:
            self._ws = await websockets.connect(
                HL_WS_URL,
                ping_interval=None,  # We handle pings manually
                close_timeout=10,
            )
            logger.info("Connected to Hyperliquid WebSocket")
            self._reconnect_delay = RECONNECT_BASE

            # Subscribe to allMids for real-time price updates
            await self._ws.send(json.dumps({
                "method": "subscribe",
                "subscription": {"type": "allMids"}
            }))

            # Start ping loop
            self._ping_task = asyncio.create_task(self._ping_loop())

            # Listen for messages
            async for message in self._ws:
                if not self._running:
                    break
                await self._handle_message(message)

        except ConnectionClosed as e:
            logger.warning(f"HL WS connection closed: {e}")
        except Exception as e:
            logger.warning(f"HL WS error: {e}")
        finally:
            if self._ping_task:
                self._ping_task.cancel()
                self._ping_task = None
            self._ws = None

    async def start(self):
        """Start the relay: connects to HL WS with auto-reconnect."""
        if self._running:
            return
        self._running = True
        logger.info("Starting Hyperliquid WS relay")

        # Start REST context fetcher
        self._context_task = asyncio.create_task(self._fetch_contexts_rest())

        # Connection loop with exponential backoff
        while self._running:
            await self._connect_and_listen()
            if not self._running:
                break
            logger.info(f"Reconnecting in {self._reconnect_delay:.1f}s...")
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, RECONNECT_MAX)

    async def stop(self):
        """Stop the relay and close connections."""
        self._running = False
        if self._context_task:
            self._context_task.cancel()
            self._context_task = None
        if self._ping_task:
            self._ping_task.cancel()
            self._ping_task = None
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("Hyperliquid WS relay stopped")

    def get_snapshot(self) -> dict:
        """Return current in-memory state for new clients or REST fallback."""
        return {
            'type': 'hl_snapshot',
            'perps': self.latest_perps,
            'spot': self.latest_spot,
            'timestamp': self.last_update,
        }


# Singleton instance
_relay: Optional[HyperliquidWSRelay] = None


def get_relay() -> HyperliquidWSRelay:
    """Get or create the singleton relay instance."""
    global _relay
    if _relay is None:
        _relay = HyperliquidWSRelay()
    return _relay
