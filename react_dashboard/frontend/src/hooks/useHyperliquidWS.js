/**
 * useHyperliquidWS — React hook for real-time Hyperliquid data via WebSocket.
 *
 * Connects to the backend's /ws/hl endpoint which relays from Hyperliquid's
 * WebSocket API. Provides ~1-second price updates for perps and HIP-3 spot stocks.
 *
 * Features:
 * - Auto-reconnect with exponential backoff (1s → 30s)
 * - Sends initial snapshot on connect (no blank state)
 * - Only active when `enabled` is true (controlled by toggle button)
 * - Cleans up WebSocket on unmount or disable
 *
 * Usage:
 *   const { perps, spot, connected, lastUpdate } = useHyperliquidWS(enabled);
 */

import { useState, useEffect, useRef, useCallback } from 'react';

const RECONNECT_BASE = 1000;   // 1 second
const RECONNECT_MAX = 30000;   // 30 seconds

/**
 * Determine the WebSocket URL based on the current page location.
 * In dev (Vite proxy), connect to ws://localhost:8000/ws/hl.
 * In production, use the page's origin with ws:// or wss://.
 */
function getWsUrl() {
  // In dev mode, Vite proxies /api but not /ws, so connect directly to backend
  if (import.meta.env.DEV) {
    const backendPort = import.meta.env.VITE_BACKEND_PORT || '8000';
    return `ws://localhost:${backendPort}/ws/hl`;
  }
  // Production: derive from page URL
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws/hl`;
}


export default function useHyperliquidWS(enabled = false) {
  const [perps, setPerps] = useState(null);
  const [spot, setSpot] = useState(null);
  const [connected, setConnected] = useState(false);
  const [lastUpdate, setLastUpdate] = useState(null);

  const wsRef = useRef(null);
  const reconnectDelay = useRef(RECONNECT_BASE);
  const reconnectTimer = useRef(null);
  const enabledRef = useRef(enabled);

  // Keep ref in sync so the reconnect closure sees latest value
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const connect = useCallback(() => {
    if (!enabledRef.current) return;
    if (wsRef.current && wsRef.current.readyState <= 1) return; // already open/connecting

    const url = getWsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      reconnectDelay.current = RECONNECT_BASE;
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        // Both 'hl_snapshot' (initial) and 'hl_update' (streaming) have same shape
        if (data.type === 'hl_snapshot' || data.type === 'hl_update') {
          if (data.perps) setPerps(data.perps);
          if (data.spot) setSpot(data.spot);
          if (data.timestamp) setLastUpdate(data.timestamp);
        }
      } catch {
        // ignore parse errors
      }
    };

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      // Auto-reconnect if still enabled
      if (enabledRef.current) {
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(reconnectDelay.current * 2, RECONNECT_MAX);
          connect();
        }, reconnectDelay.current);
      }
    };

    ws.onerror = () => {
      // onclose will fire after this, triggering reconnect
    };
  }, []);

  const disconnect = useCallback(() => {
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current);
      reconnectTimer.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnected(false);
  }, []);

  // Connect/disconnect based on enabled flag
  useEffect(() => {
    if (enabled) {
      connect();
    } else {
      disconnect();
    }
    return () => disconnect();
  }, [enabled, connect, disconnect]);

  return { perps, spot, connected, lastUpdate };
}
