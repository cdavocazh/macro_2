import React, { useEffect, useRef, useState, useCallback } from 'react';
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts';
import api from '../api';

const INTERVALS = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '1H', value: '1h' },
  { label: '4H', value: '4h' },
  { label: '1D', value: '1d' },
];

// GMT+8 offset in seconds (lightweight-charts uses raw Unix timestamps, no TZ support)
const GMT8_OFFSET = 8 * 3600;

/**
 * OHLCV candlestick chart for Hyperliquid instruments using TradingView lightweight-charts.
 * Lazy-loaded: chart is only created and data fetched when the user expands the <details>.
 */
export default function HLCandlestickChart({ coin, apiCoin, label, color = '#1f77b4' }) {
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const volumeSeriesRef = useRef(null);
  const initializedRef = useRef(false);
  const resizeHandlerRef = useRef(null);

  const [interval, setInterval_] = useState('1h');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isOpen, setIsOpen] = useState(false);

  const fetchData = useCallback(async (intv) => {
    if (!chartRef.current) return;
    setLoading(true);
    setError(null);

    try {
      const coinParam = coin.toLowerCase();
      const resp = await api.get(`/hl/ohlcv/${coinParam}`, { params: { interval: intv } });
      const data = resp.data;

      if (!data || data.length === 0) {
        setError('No candle data available');
        setLoading(false);
        return;
      }

      // Deduplicate by timestamp (keep last entry per time value)
      const seen = new Map();
      for (const d of data) {
        const t = d.time + GMT8_OFFSET;
        seen.set(t, d);
      }
      const deduped = [...seen.entries()].sort((a, b) => a[0] - b[0]);

      if (candleSeriesRef.current) {
        candleSeriesRef.current.setData(deduped.map(([t, d]) => ({
          time: t, open: d.open, high: d.high, low: d.low, close: d.close,
        })));
      }
      if (volumeSeriesRef.current) {
        volumeSeriesRef.current.setData(deduped.map(([t, d]) => ({
          time: t,
          value: d.volume,
          color: d.close >= d.open ? 'rgba(38, 166, 154, 0.4)' : 'rgba(239, 83, 80, 0.4)',
        })));
      }
      if (chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    } catch (e) {
      if (chartRef.current) {
        setError(e.message || 'Failed to load candles');
      }
    } finally {
      setLoading(false);
    }
  }, [coin]);

  // Create chart when details is opened for the first time
  useEffect(() => {
    if (!isOpen || initializedRef.current) return;

    // Defer to next frame so <details> content is laid out with non-zero width
    const rafId = requestAnimationFrame(() => {
      const container = chartContainerRef.current;
      if (!container || initializedRef.current) return;

      const width = container.clientWidth || 600;

      const chart = createChart(container, {
        width,
        height: 350,
        layout: {
          background: { type: ColorType.Solid, color: '#1e1e1e' },
          textColor: '#d1d4dc',
        },
        grid: {
          vertLines: { color: '#2B2B43' },
          horzLines: { color: '#2B2B43' },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: '#485c7b' },
        timeScale: {
          borderColor: '#485c7b',
          timeVisible: true,
          secondsVisible: false,
        },
      });

      chartRef.current = chart;

      candleSeriesRef.current = chart.addCandlestickSeries({
        upColor: '#26a69a', downColor: '#ef5350',
        borderDownColor: '#ef5350', borderUpColor: '#26a69a',
        wickDownColor: '#ef5350', wickUpColor: '#26a69a',
      });

      const volumeSeries = chart.addHistogramSeries({
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
      });
      chart.priceScale('volume').applyOptions({
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      volumeSeriesRef.current = volumeSeries;

      const handleResize = () => {
        if (chartContainerRef.current && chartRef.current) {
          chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
        }
      };
      window.addEventListener('resize', handleResize);
      resizeHandlerRef.current = handleResize;

      initializedRef.current = true;
      fetchData(interval);
    });

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [isOpen]); // Only depend on isOpen — initializedRef is a ref, not state

  // Cleanup chart on unmount
  useEffect(() => {
    return () => {
      if (resizeHandlerRef.current) {
        window.removeEventListener('resize', resizeHandlerRef.current);
      }
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
        candleSeriesRef.current = null;
        volumeSeriesRef.current = null;
      }
    };
  }, []);

  // Refetch when interval changes (only if chart exists)
  useEffect(() => {
    if (initializedRef.current && chartRef.current) {
      fetchData(interval);
    }
  }, [interval, fetchData]);

  const handleToggle = (e) => {
    setIsOpen(e.target.open);
  };

  return (
    <details className="chart-expander" style={{ marginTop: 4, marginBottom: 8 }} open={isOpen} onToggle={handleToggle}>
      <summary style={{ cursor: 'pointer', fontSize: '0.78rem', color: '#666', padding: '2px 0' }}>
        {label} OHLCV Chart
      </summary>
      <div style={{ marginTop: 4 }}>
        <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
          {INTERVALS.map(({ label: lbl, value }) => (
            <button
              key={value}
              onClick={() => setInterval_(value)}
              style={{
                padding: '2px 8px', fontSize: '0.7rem',
                border: `1px solid ${interval === value ? '#1976d2' : '#555'}`,
                borderRadius: 3,
                background: interval === value ? '#1976d2' : 'transparent',
                color: interval === value ? '#fff' : '#999',
                cursor: 'pointer',
              }}
            >
              {lbl}
            </button>
          ))}
          {loading && <span style={{ fontSize: '0.7rem', color: '#999', marginLeft: 8 }}>Loading...</span>}
          {error && <span style={{ fontSize: '0.7rem', color: '#ef5350', marginLeft: 8 }}>{error}</span>}
        </div>
        <div ref={chartContainerRef} style={{ width: '100%' }} />
      </div>
    </details>
  );
}
