import React, { useState, useEffect, useCallback } from 'react';
import Plot from 'react-plotly.js';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';
import HistoryChart from '../components/HistoryChart';
import HLCandlestickChart from '../components/HLCandlestickChart';
import IntradayCandlestickChart from '../components/IntradayCandlestickChart';
import useHyperliquidWS from '../hooks/useHyperliquidWS';
import { toGMT8 } from '../utils/time';
import { fetchIbkrContracts, changeIbkrExpiry } from '../api';

function fmt(v, d = 2) {
  if (v == null || v === 'N/A') return 'N/A';
  return typeof v === 'number' ? v.toFixed(d) : String(v);
}

// Map dashboard instrumentKey -> IBKR symbol (used by ibkr_streaming.INSTRUMENTS)
const IBKR_SYMBOL_MAP = {
  gold: 'GC', silver: 'SI', copper: 'HG', crude_oil: 'CL', natural_gas: 'NG',
  es_futures: 'ES', rty_futures: 'RTY',
};

const STORAGE_KEY = 'ibkr_expiry_pref_v1';

function _readPrefs() {
  try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}'); }
  catch { return {}; }
}
function _writePrefs(prefs) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs)); } catch {}
}

/**
 * Hook: per-card expiry preference.
 * - On mount: if the local pref differs from the server's currently-active expiry,
 *   POST it so the daemon swaps to the user's preferred expiry.
 * - updatePref(expiry): write to localStorage AND POST to backend
 * - clearPref(): localStorage delete + reset to front-month
 */
function useIbkrExpiryPref(ibkrSymbol, currentExpiry) {
  const [pref, setPref] = useState(() => _readPrefs()[ibkrSymbol] || null);

  // On mount: re-apply local pref if it diverges from server state.
  // Debounce: only re-apply if the current server expiry differs.
  useEffect(() => {
    if (!ibkrSymbol || !pref) return;
    if (pref === currentExpiry) return;
    if (!currentExpiry) return; // server hasn't loaded yet, skip
    changeIbkrExpiry(ibkrSymbol, pref).catch(err => {
      console.warn(`[IBKR] Failed to re-apply pref ${ibkrSymbol}=${pref}:`, err);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ibkrSymbol]);

  const updatePref = useCallback((newExpiry) => {
    const all = _readPrefs();
    if (newExpiry) all[ibkrSymbol] = newExpiry;
    else delete all[ibkrSymbol];
    _writePrefs(all);
    setPref(newExpiry || null);
  }, [ibkrSymbol]);

  const clearPref = useCallback(() => updatePref(null), [updatePref]);

  return { pref, updatePref, clearPref };
}

/** Format YYYYMMDD or YYYYMM -> YYYY-MM-DD or YYYY-MM */
function formatExpiry(e) {
  if (!e) return '';
  if (e.length === 8) return `${e.slice(0,4)}-${e.slice(4,6)}-${e.slice(6,8)}`;
  if (e.length === 6) return `${e.slice(0,4)}-${e.slice(4,6)}`;
  return e;
}

function ExpiryDropdown({ ibkrSymbol, currentExpiry }) {
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);
  const { pref, updatePref, clearPref } = useIbkrExpiryPref(ibkrSymbol, currentExpiry);

  // Load available contracts on mount
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetchIbkrContracts(ibkrSymbol)
      .then(data => { if (!cancelled) setContracts(data.contracts || []); })
      .catch(err => {
        if (!cancelled) {
          console.warn(`[IBKR] fetchIbkrContracts(${ibkrSymbol}) failed:`, err);
          setContracts([]);
        }
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [ibkrSymbol]);

  const handleChange = async (e) => {
    const newExpiry = e.target.value;
    if (newExpiry === currentExpiry) return;
    setBusy(true);
    setMsg('Switching...');
    try {
      await changeIbkrExpiry(ibkrSymbol, newExpiry);
      updatePref(newExpiry);
      setMsg('Switched - daemon applying...');
      // Clear the message after a few seconds so the dashboard refreshes
      setTimeout(() => setMsg(null), 8000);
    } catch (err) {
      console.error(`[IBKR] changeIbkrExpiry(${ibkrSymbol}, ${newExpiry}) failed:`, err);
      setMsg('Failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setBusy(false);
    }
  };

  const handleReset = async () => {
    setBusy(true);
    setMsg('Resetting...');
    try {
      await changeIbkrExpiry(ibkrSymbol, '');
      clearPref();
      setMsg('Reset - daemon applying front-month...');
      setTimeout(() => setMsg(null), 8000);
    } catch (err) {
      setMsg('Failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <span style={{ fontSize: '0.8em', opacity: 0.6 }}> | loading expiries...</span>;
  if (!contracts.length) return null;

  return (
    <span style={{ fontSize: '0.85em', marginLeft: 6 }}>
      {' | '}
      <label style={{ marginRight: 4 }}>Expiry:</label>
      <select
        value={currentExpiry || ''}
        onChange={handleChange}
        disabled={busy}
        style={{ fontSize: '0.95em', padding: '1px 4px' }}
      >
        {contracts.map(c => (
          <option key={c.contract_id} value={c.expiry}>
            {c.local_symbol} ({formatExpiry(c.expiry)})
          </option>
        ))}
      </select>
      {pref && (
        <button
          onClick={handleReset}
          disabled={busy}
          style={{
            marginLeft: 6, fontSize: '0.85em', padding: '0 6px',
            cursor: 'pointer', border: '1px solid #888', background: '#f5f5f5',
            borderRadius: 3,
          }}
          title="Reset to front-month auto-roll"
        >↺ Reset</button>
      )}
      {msg && <span style={{ marginLeft: 6, opacity: 0.7, fontStyle: 'italic' }}>{msg}</span>}
    </span>
  );
}

function CommodityCard({ data, label, unit, color, instrumentKey }) {
  if (!data) return null;
  if (data.error) return <ErrorCard title={label} error={data.error} note={data.note} />;

  // Build IBKR contract info badge if real-time data is available
  const isIbkr = data.source && data.source.includes('IBKR');
  const ibkrTicker = data.ibkr_local_symbol;
  const ibkrExpiry = data.ibkr_expiry;
  const ibkrSymbol = IBKR_SYMBOL_MAP[instrumentKey];

  let badge = '';
  if (isIbkr && ibkrTicker) {
    badge = ` | Ticker: ${ibkrTicker}${ibkrExpiry ? ' (exp ' + formatExpiry(ibkrExpiry) + ')' : ''}`;
  }

  // Bid/ask line for IBKR tickers
  const bidAskLine = (isIbkr && data.ibkr_bid && data.ibkr_ask)
    ? `Bid ${data.ibkr_bid} / Ask ${data.ibkr_ask}${data.ibkr_volume ? ' | Vol ' + data.ibkr_volume.toLocaleString() : ''}${data.ibkr_open_interest ? ' | OI ' + data.ibkr_open_interest.toLocaleString() : ''}`
    : '';

  return (
    <div>
      <MetricCard
        label={`${label} (${unit})`}
        value={data.price}
        delta={data.change_1d}
        deltaLabel="%"
        caption={
          <>
            {`As of: ${toGMT8(data.latest_date) || 'N/A'}${badge}${data.note ? ' | ' + data.note : ''}`}
            {isIbkr && ibkrSymbol && (
              <ExpiryDropdown ibkrSymbol={ibkrSymbol} currentExpiry={ibkrExpiry} />
            )}
          </>
        }
      />
      {bidAskLine && (
        <div className="metric-caption" style={{ fontSize: '0.85em', opacity: 0.85, marginTop: '-8px', marginBottom: '8px' }}>
          {bidAskLine}
        </div>
      )}
      <HistoryChart data={data.historical} label={`${label} (${unit})`} color={color} />
      {instrumentKey && <IntradayCandlestickChart instrumentKey={instrumentKey} label={label} color={color} />}
    </div>
  );
}

function PerpCoinRow({ coinKey, label, color, cacheData, wsData }) {
  // Use WS live data if available, otherwise fall back to cache
  const data = (wsData && wsData[coinKey]) || cacheData;
  if (!data || data.error || !data.price) return null;

  const isLive = !!(wsData && wsData[coinKey]);

  return (
    <div style={{ marginBottom: 12 }}>
      <SectionHeader title={label} sub />
      <div className="grid-4">
        <MetricCard
          label={isLive ? 'Mid Price (LIVE)' : 'Mid Price'}
          value={data.price >= 100
            ? `$${Number(data.price).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`
            : `$${fmt(data.price, 4)}`}
          delta={data.change_1d}
          deltaLabel="%"
          caption={`As of: ${toGMT8(data.latest_date)}`}
        />
        <MetricCard
          label="Funding (ann.)"
          value={data.funding_rate != null ? `${fmt(data.funding_rate)}%` : 'N/A'}
          caption={data.funding_rate_8h != null ? `8h: ${data.funding_rate_8h}%` : ''}
        />
        <MetricCard
          label="Open Interest"
          value={data.open_interest != null ? `$${(data.open_interest / 1e6).toFixed(1)}M` : 'N/A'}
        />
        <MetricCard
          label="24h Volume"
          value={data.volume_24h != null ? `$${(data.volume_24h / 1e6).toFixed(1)}M` : 'N/A'}
        />
      </div>
      <HLCandlestickChart
        coin={coinKey}
        apiCoin={data.api_coin || (cacheData && cacheData.api_coin)}
        label={label}
        color={color}
      />
    </div>
  );
}

export default function Tab5Commodities({ indicators }) {
  if (!indicators) return null;

  // ── Live WebSocket toggle ──
  const [liveEnabled, setLiveEnabled] = useState(false);
  const { perps: wsPerps, connected, lastUpdate: wsLastUpdate } = useHyperliquidWS(liveEnabled);

  const gold = indicators['13_gold'] || {};
  const silver = indicators['14_silver'] || {};
  const oil = indicators['15_crude_oil'] || {};
  const copper = indicators['16_copper'] || {};
  const natGas = indicators['56_natural_gas'] || {};
  const cuAu = indicators['57_cu_au_ratio'] || {};
  const cot = indicators['22_cot_positioning'] || {};

  const goldCot = cot.gold || {};
  const silverCot = cot.silver || {};

  // Hyperliquid perps (cache-based fallback)
  const hlPerps = indicators['84_hl_perps'] || {};

  const hlCoins = [
    ['btc', 'Bitcoin (BTC)', '#F7931A'],
    ['eth', 'Ethereum (ETH)', '#627EEA'],
    ['sol', 'Solana (SOL)', '#9945FF'],
    ['hype', 'Hyperliquid (HYPE)', '#00D4AA'],
    ['paxg', 'PAX Gold (PAXG)', '#FFD700'],
    ['oil', 'WTI Crude Oil (OIL)', '#8B4513'],
    ['sp500', 'S&P 500 (SP500)', '#1565c0'],
    ['xyz100', 'Nasdaq 100 (XYZ100)', '#7b1fa2'],
    ['natgas', 'Natural Gas (NATGAS)', '#4a148c'],
    ['copper_hl', 'Copper (COPPER)', '#B87333'],
    ['brentoil', 'Brent Crude (BRENTOIL)', '#2c2c2c'],
  ];

  return (
    <div>
      <SectionHeader title="Commodities Futures" />

      <div className="grid-2">
        <CommodityCard data={gold} label="Gold (GC)" unit="USD/oz" color="#FFD700" instrumentKey="gold" />
        <CommodityCard data={silver} label="Silver (SI)" unit="USD/oz" color="#C0C0C0" instrumentKey="silver" />
      </div>

      <div className="grid-2">
        <CommodityCard data={oil} label="Crude Oil (CL)" unit="USD/bbl" color="#2c2c2c" instrumentKey="crude_oil" />
        <CommodityCard data={copper} label="Copper (HG)" unit="USD/lb" color="#B87333" instrumentKey="copper" />
      </div>

      <div className="grid-2">
        <CommodityCard data={natGas} label="Natural Gas (NG)" unit="USD/MMBtu" color="#4a148c" instrumentKey="natural_gas" />

        {/* Cu/Au Ratio */}
        {cuAu.error ? (
          <ErrorCard title="Cu/Au Ratio" error={cuAu.error} />
        ) : (
          <div>
            <MetricCard
              label="Cu/Au Ratio (x1000)"
              value={cuAu.cu_au_ratio}
              delta={cuAu.change_1d}
              deltaLabel="%"
              caption={`As of: ${toGMT8(cuAu.latest_date)}${cuAu.interpretation ? ' | ' + cuAu.interpretation : ''}`}
            />
            <HistoryChart data={cuAu.historical} label="Cu/Au Ratio x1000" color="#ef6c00" />
          </div>
        )}
      </div>

      {/* CFTC COT Positioning */}
      <SectionHeader title="CFTC Commitment of Traders - Gold & Silver" />
      <div className="metric-caption" style={{ marginBottom: 8 }}>
        Weekly positioning data from CFTC. Managed money = hedge funds. Commercial = producers/hedgers.
      </div>

      {cot.error ? (
        <ErrorCard error={cot.error} note={cot.suggestion} />
      ) : (
        <>
          <div className="metric-caption">As of: {toGMT8(cot.latest_date)}</div>

          <div className="grid-2">
            {/* Gold COT */}
            <div>
              <SectionHeader title="Gold (GC) Positioning" sub />
              {goldCot.error ? (
                <ErrorCard error={goldCot.error} />
              ) : (
                <div className="grid-2">
                  <MetricCard
                    label="Open Interest"
                    value={typeof goldCot.open_interest === 'number' ? goldCot.open_interest.toLocaleString() : 'N/A'}
                  />
                  {goldCot.managed_money_net != null ? (
                    <>
                      <MetricCard label="Managed Money Net" value={goldCot.managed_money_net?.toLocaleString()} />
                      {goldCot.mm_long_ratio != null && (
                        <MetricCard label="MM Long Ratio" value={`${(goldCot.mm_long_ratio * 100).toFixed(1)}%`} />
                      )}
                    </>
                  ) : goldCot.noncommercial_net != null ? (
                    <MetricCard label="Speculator Net" value={goldCot.noncommercial_net?.toLocaleString()} />
                  ) : null}
                  {goldCot.commercial_net != null && (
                    <MetricCard label="Commercial Net" value={goldCot.commercial_net?.toLocaleString()} />
                  )}
                  {goldCot.oi_change != null && (
                    <MetricCard
                      label="OI Change (1w)"
                      value={goldCot.oi_change?.toLocaleString()}
                      delta={goldCot.oi_change_pct}
                      deltaLabel="%"
                    />
                  )}
                </div>
              )}
            </div>

            {/* Silver COT */}
            <div>
              <SectionHeader title="Silver (SI) Positioning" sub />
              {silverCot.error ? (
                <ErrorCard error={silverCot.error} />
              ) : (
                <div className="grid-2">
                  <MetricCard
                    label="Open Interest"
                    value={typeof silverCot.open_interest === 'number' ? silverCot.open_interest.toLocaleString() : 'N/A'}
                  />
                  {silverCot.managed_money_net != null ? (
                    <>
                      <MetricCard label="Managed Money Net" value={silverCot.managed_money_net?.toLocaleString()} />
                      {silverCot.mm_long_ratio != null && (
                        <MetricCard label="MM Long Ratio" value={`${(silverCot.mm_long_ratio * 100).toFixed(1)}%`} />
                      )}
                    </>
                  ) : silverCot.noncommercial_net != null ? (
                    <MetricCard label="Speculator Net" value={silverCot.noncommercial_net?.toLocaleString()} />
                  ) : null}
                  {silverCot.commercial_net != null && (
                    <MetricCard label="Commercial Net" value={silverCot.commercial_net?.toLocaleString()} />
                  )}
                  {silverCot.oi_change != null && (
                    <MetricCard
                      label="OI Change (1w)"
                      value={silverCot.oi_change?.toLocaleString()}
                      delta={silverCot.oi_change_pct}
                      deltaLabel="%"
                    />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* COT Historical Chart */}
          {(goldCot.historical || silverCot.historical) && (
            <details className="chart-expander">
              <summary>COT Positioning Chart</summary>
              <div className="full-chart">
                <Plot
                  data={[
                    ...(goldCot.historical?.index ? [{
                      x: goldCot.historical.index,
                      y: goldCot.historical.values,
                      type: 'scatter', mode: 'lines',
                      name: `Gold ${goldCot.historical_label || 'Net Positioning'}`,
                      line: { color: 'gold' },
                    }] : []),
                    ...(silverCot.historical?.index ? [{
                      x: silverCot.historical.index,
                      y: silverCot.historical.values,
                      type: 'scatter', mode: 'lines',
                      name: `Silver ${silverCot.historical_label || 'Net Positioning'}`,
                      line: { color: 'silver' },
                    }] : []),
                  ]}
                  layout={{
                    title: `CFTC COT: ${goldCot.historical_label || 'Net Positioning'} (Gold vs Silver)`,
                    hovermode: 'x unified',
                    height: 400,
                    margin: { l: 50, r: 20, t: 40, b: 30 },
                    xaxis: { title: 'Date' },
                    yaxis: { title: 'Contracts' },
                  }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              </div>
            </details>
          )}
        </>
      )}

      {/* ── Hyperliquid Perpetual Futures ─────────────────────────────── */}
      <SectionHeader title="Hyperliquid Perpetual Futures" />
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <div className="metric-caption" style={{ flex: 1 }}>
          DeFi perpetual futures on Hyperliquid. 24/7 markets, no expiry. Funding rate annualized.
          {liveEnabled && wsLastUpdate && <> | Live: {toGMT8(wsLastUpdate)}</>}
          {!liveEnabled && hlPerps.latest_date && <> | As of: {toGMT8(hlPerps.latest_date)}</>}
        </div>
        <button
          onClick={() => setLiveEnabled(!liveEnabled)}
          style={{
            padding: '4px 14px',
            fontSize: '0.78rem',
            fontWeight: 600,
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            background: liveEnabled ? '#ef5350' : '#26a69a',
            color: '#fff',
          }}
        >
          {liveEnabled ? (connected ? 'Stop Live (~1s)' : 'Connecting...') : 'Start Live (~1s)'}
        </button>
      </div>

      {hlPerps.error ? (
        <ErrorCard error={hlPerps.error} />
      ) : (
        hlCoins.map(([key, label, color]) => (
          <PerpCoinRow
            key={key}
            coinKey={key}
            label={label}
            color={color}
            cacheData={hlPerps[key]}
            wsData={wsPerps}
          />
        ))
      )}
    </div>
  );
}
