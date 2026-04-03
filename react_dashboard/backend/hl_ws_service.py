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
  We use 1 connection + 2 subscriptions — well within limits.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger("hl_ws_relay")

HL_WS_URL = "wss://api.hyperliquid.xyz/ws"
PING_INTERVAL = 50  # seconds (HL timeout is 60s)
RECONNECT_BASE = 1.0
RECONNECT_MAX = 60.0

# Tracked perps (same as hyperliquid_extractor.py)
HL_PERPS = {
    'BTC': 'btc', 'ETH': 'eth', 'SOL': 'sol', 'PAXG': 'paxg',
    'HYPE': 'hype',
}
# Builder-deployed perps not in allMids WebSocket — fetched via REST candles instead.
BUILDER_PERPS = {
    'flx:OIL': 'oil',
    'xyz:SP500': 'sp500',
    'xyz:NATGAS': 'natgas',
    'xyz:COPPER': 'copper_hl',
    'xyz:BRENTOIL': 'brentoil',
    'xyz:XYZ100': 'xyz100',
}

# HIP-3 spot stock token indices (same as hyperliquid_extractor.py)
HL_SPOT_STOCKS = {
    'TSLA': 407, 'NVDA': 408, 'AAPL': 413, 'GOOGL': 412,
    'AMZN': 421, 'META': 422, 'MSFT': 429, 'SPY': 420, 'QQQ': 426,
}


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
        self._contexts: Dict = {}
        self._spot_contexts: Dict = {}
        self._context_task: Optional[asyncio.Task] = None

        # Builder perps (not in allMids, fetched via REST candles)
        self._builder_prices: Dict[str, float] = {}  # api_coin → price
        self._builder_volumes: Dict[str, float] = {}  # api_coin → volume

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

    async def _fetch_contexts_rest(self):
        """
        Periodically fetch full context data (funding, OI, volume) via REST.
        allMids WebSocket only gives prices; contexts come from REST.
        Runs every 5 seconds to keep funding/OI/volume fresh.
        """
        import httpx

        while self._running:
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    # Perp contexts (1 call)
                    try:
                        resp = await client.post(
                            "https://api.hyperliquid.xyz/info",
                            json={"type": "metaAndAssetCtxs"},
                        )
                        if resp.status_code == 429:
                            logger.debug("HL rate limited, backing off")
                            await asyncio.sleep(30)
                            continue
                        raw = resp.json()
                        if isinstance(raw, list) and len(raw) >= 2 and raw[0] is not None:
                            meta = raw[0]
                            ctxs = raw[1]
                            universe = meta.get('universe', []) if isinstance(meta, dict) else []
                            contexts = {}
                            for i, asset in enumerate(universe):
                                coin = asset.get('name', '')
                                if i < len(ctxs) and ctxs[i] is not None:
                                    ctx = ctxs[i]
                                    contexts[coin] = {
                                        'funding': ctx.get('funding', '0'),
                                        'open_interest': ctx.get('openInterest', '0'),
                                        'volume_24h': ctx.get('dayNtlVlm', '0'),
                                        'mark_price': ctx.get('markPx', '0'),
                                        'oracle_price': ctx.get('oraclePx', '0'),
                                        'prev_day_px': ctx.get('prevDayPx', '0'),
                                    }
                            self._contexts = contexts
                    except Exception:
                        pass  # Keep using cached contexts

                    await asyncio.sleep(0.3)  # Brief pause between API calls

                    # Fetch builder perps (6 calls with spacing)
                    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    start_ms = int((datetime.now(timezone.utc) - timedelta(minutes=5)).timestamp() * 1000)
                    for api_coin in BUILDER_PERPS:
                        try:
                            bp_resp = await client.post(
                                "https://api.hyperliquid.xyz/info",
                                json={
                                    "type": "candleSnapshot",
                                    "req": {
                                        "coin": api_coin,
                                        "interval": "1m",
                                        "startTime": start_ms,
                                        "endTime": now_ms,
                                    }
                                },
                            )
                            if bp_resp.status_code == 200:
                                bp_candles = bp_resp.json()
                                if bp_candles and isinstance(bp_candles, list) and len(bp_candles) > 0:
                                    last = bp_candles[-1]
                                    self._builder_prices[api_coin] = float(last['c'])
                                    self._builder_volumes[api_coin] = float(last['v'])
                            await asyncio.sleep(0.2)  # 200ms between candle requests
                        except Exception:
                            pass

                    await asyncio.sleep(0.3)

                    # Spot contexts (1 call)
                    try:
                        resp2 = await client.post(
                            "https://api.hyperliquid.xyz/info",
                            json={"type": "spotMetaAndAssetCtxs"},
                        )
                        if resp2.status_code == 200:
                            raw2 = resp2.json()
                            if isinstance(raw2, list) and len(raw2) >= 2 and raw2[0] is not None:
                                spot_meta = raw2[0]
                                if isinstance(spot_meta, dict):
                                    tokens = spot_meta.get('tokens', [])
                                    spot_universe = spot_meta.get('universe', [])
                                    spot_ctxs = raw2[1] if raw2[1] is not None else []
                                    pair_for_token = {}
                                    for i, u in enumerate(spot_universe):
                                        for ti in u.get('tokens', []):
                                            if ti != 0:
                                                pair_for_token[ti] = (i, u, spot_ctxs[i] if i < len(spot_ctxs) else {})
                                    self._spot_contexts = pair_for_token
                    except Exception:
                        pass  # Keep using cached spot contexts

            except Exception as e:
                logger.debug(f"REST context fetch cycle error: {e}")

            await asyncio.sleep(10)  # 10s between full context cycles

    def _build_perp_snapshot(self, mids: Dict[str, str]) -> Dict:
        """Build perp data from allMids + cached contexts."""
        result = {}
        for hl_ticker, key in HL_PERPS.items():
            mid_str = mids.get(hl_ticker)
            if mid_str is None:
                continue
            try:
                price = float(mid_str)
            except (ValueError, TypeError):
                continue

            ctx = self._contexts.get(hl_ticker, {})
            funding_raw = float(ctx.get('funding', '0'))
            funding_ann = funding_raw * 3 * 365 * 100
            oi = float(ctx.get('open_interest', '0'))
            vol = float(ctx.get('volume_24h', '0'))
            mark = float(ctx.get('mark_price', '0'))
            oracle = float(ctx.get('oracle_price', '0'))
            prev = float(ctx.get('prev_day_px', '0'))

            change_24h = ((price - prev) / prev * 100) if prev > 0 else 0.0
            premium = ((mark - oracle) / oracle * 100) if oracle > 0 else 0.0

            result[key] = {
                'price': price,
                'change_1d': round(change_24h, 2),
                'mark_price': mark,
                'oracle_price': oracle,
                'funding_rate': round(funding_ann, 2),
                'funding_rate_8h': round(funding_raw * 100, 6),
                'open_interest': round(oi, 2),
                'volume_24h': round(vol, 2),
                'premium': round(premium, 4),
                'latest_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
            }

        # Add builder-deployed perps (not in allMids)
        for api_coin, key in BUILDER_PERPS.items():
            price = self._builder_prices.get(api_coin)
            if price:
                result[key] = {
                    'price': price,
                    'change_1d': 0.0,
                    'mark_price': price,
                    'oracle_price': 0.0,
                    'funding_rate': 0.0,
                    'funding_rate_8h': 0.0,
                    'open_interest': 0.0,
                    'volume_24h': self._builder_volumes.get(api_coin, 0.0),
                    'premium': 0.0,
                    'latest_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                    'api_coin': api_coin,
                }

        result['latest_date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        result['source'] = 'Hyperliquid WS'
        return result

    def _build_spot_snapshot(self) -> Dict:
        """Build spot stock data from cached spot contexts."""
        result = {}
        for ticker, idx in HL_SPOT_STOCKS.items():
            key = ticker.lower()
            pair_info = self._spot_contexts.get(idx)
            if pair_info is None:
                continue
            _, pair_meta, ctx = pair_info
            mid_px = ctx.get('midPx')
            if mid_px is None or mid_px == 'N/A':
                continue
            try:
                price = float(mid_px)
            except (ValueError, TypeError):
                continue

            vol = float(ctx.get('dayNtlVlm', '0'))
            prev = float(ctx.get('prevDayPx', '0')) if ctx.get('prevDayPx') else 0
            change = ((price - prev) / prev * 100) if prev > 0 else 0.0

            result[key] = {
                'price': price,
                'change_1d': round(change, 2),
                'volume_24h': round(vol, 2),
                'latest_date': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'),
                'source': 'Hyperliquid HIP-3 WS',
            }

        result['latest_date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
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
