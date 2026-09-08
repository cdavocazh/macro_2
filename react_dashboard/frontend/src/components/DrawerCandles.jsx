import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import api from '../api';

// lightweight-charts takes raw Unix timestamps with no timezone support, so we
// shift into GMT+8 to match every other timestamp on the dashboard.
const GMT8_OFFSET = 8 * 3600;

const YF_INTERVALS = [
  { label: '1H', value: '1h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' },
  { label: '1W', value: '1wk' },
];
const HL_INTERVALS = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1H', value: '1h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' },
];

/**
 * Native OHLCV chart for the drawer — plots THIS repo's data via the existing
 * /api/intraday and /api/hl/ohlcv endpoints.
 *
 * Distinct from IntradayCandlestickChart / HLCandlestickChart: those are the
 * small inline `<details>` strips. This one is always-open, fills whatever
 * height the drawer gives it, and covers both sources behind one component.
 */
export default function DrawerCandles({ source, instrumentKey, label }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);
  const candleRef = useRef(null);
  const volumeRef = useRef(null);
  const roRef = useRef(null);

  const isHL = source === 'hl';
  const intervals = isHL ? HL_INTERVALS : YF_INTERVALS;

  const [interval, setInterval_] = useState(isHL ? '1h' : '1d');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async (intv) => {
    if (!chartRef.current) return;
    setLoading(true);
    setError(null);
    try {
      const url = isHL
        ? `/hl/ohlcv/${instrumentKey.toLowerCase()}`
        : `/intraday/${instrumentKey}`;
      const resp = await api.get(url, { params: { interval: intv } });
      const data = resp.data;

      if (!data || data.length === 0) {
        setError('No candle data available for this interval');
        setLoading(false);
        return;
      }

      // Deduplicate by timestamp — lightweight-charts asserts strictly
      // ascending unique times (see QA_SOP.md §2).
      const seen = new Map();
      for (const d of data) seen.set(d.time + GMT8_OFFSET, d);
      const rows = [...seen.entries()].sort((a, b) => a[0] - b[0]);

      candleRef.current?.setData(rows.map(([t, d]) => ({
        time: t, open: d.open, high: d.high, low: d.low, close: d.close,
      })));
      volumeRef.current?.setData(rows.map(([t, d]) => ({
        time: t,
        value: d.volume,
        color: d.close >= d.open ? 'rgba(38,166,154,0.4)' : 'rgba(239,83,80,0.4)',
      })));
      chartRef.current?.timeScale().fitContent();
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'Failed to load candles');
    } finally {
      setLoading(false);
    }
  }, [isHL, instrumentKey]);

  // Create the chart once per mount. The drawer unmounts this component on
  // close, so there is no re-entrancy concern; init state lives in refs (never
  // useState) so it cannot trigger the re-render → cleanup → chart-destroyed
  // failure documented in QA_SOP.md §1.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#333' },
      grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#d6dcde', scaleMargins: { top: 0.08, bottom: 0.25 } },
      timeScale: { borderColor: '#d6dcde', timeVisible: true, secondsVisible: false },
      autoSize: true,
    });
    chartRef.current = chart;

    candleRef.current = chart.addCandlestickSeries({
      upColor: '#26a69a', downColor: '#ef5350',
      borderUpColor: '#26a69a', borderDownColor: '#ef5350',
      wickUpColor: '#26a69a', wickDownColor: '#ef5350',
    });
    volumeRef.current = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
    });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

    fetchData(interval);

    return () => {
      roRef.current?.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleInterval = (v) => {
    setInterval_(v);
    fetchData(v);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="drawer-toolbar">
        {intervals.map((iv) => (
          <button
            key={iv.value}
            className={`interval-btn ${interval === iv.value ? 'active' : ''}`}
            onClick={() => handleInterval(iv.value)}
          >
            {iv.label}
          </button>
        ))}
        {loading && <span className="drawer-hint">Loading…</span>}
        {error && <span className="drawer-hint drawer-hint-err">{error}</span>}
        <span className="drawer-hint" style={{ marginLeft: 'auto' }}>
          {label} · this dashboard's own data
        </span>
      </div>
      <div ref={containerRef} style={{ flex: 1, minHeight: 0 }} />
    </div>
  );
}
