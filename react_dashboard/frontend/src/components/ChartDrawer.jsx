import React, { createContext, useContext, useState, useCallback, useEffect, lazy, Suspense } from 'react';
import DrawerCandles from './DrawerCandles';
import { tvEntry } from '../config/instruments';

// The TradingView embed pulls ~1 MB of third-party script. Code-split it so it
// never lands in the main bundle — same reasoning as LazyPlot for plotly.
const TradingViewWidget = lazy(() => import('./TradingViewWidget'));

const ChartDrawerContext = createContext(null);

/** openChart({ source: 'yf'|'hl', instrumentKey, label }) from anywhere. */
export function useChartDrawer() {
  const ctx = useContext(ChartDrawerContext);
  if (!ctx) throw new Error('useChartDrawer must be used inside <ChartDrawerProvider>');
  return ctx;
}

export function ChartDrawerProvider({ children }) {
  const [target, setTarget] = useState(null); // { source, instrumentKey, label }
  const [engine, setEngine] = useState('tv'); // 'tv' | 'native'

  const openChart = useCallback((next) => {
    // Default to TradingView when the instrument is listed there (indicators +
    // drawing tools), otherwise the native engine is the only option.
    setEngine(tvEntry(next.source, next.instrumentKey) ? 'tv' : 'native');
    setTarget(next);
  }, []);

  const closeChart = useCallback(() => setTarget(null), []);

  // Esc closes; body scroll locked while open.
  useEffect(() => {
    if (!target) return;
    const onKey = (e) => { if (e.key === 'Escape') closeChart(); };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [target, closeChart]);

  const entry = target ? tvEntry(target.source, target.instrumentKey) : null;
  const symbol = entry?.symbol || null;

  return (
    <ChartDrawerContext.Provider value={{ openChart, closeChart }}>
      {children}
      {target && (
        <div className="chart-drawer-backdrop" onClick={closeChart}>
          <div
            className="chart-drawer"
            role="dialog"
            aria-label={`${target.label} chart`}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="chart-drawer-head">
              <strong>{target.label}</strong>

              <div className="engine-toggle">
                <button
                  className={`interval-btn ${engine === 'tv' ? 'active' : ''}`}
                  onClick={() => setEngine('tv')}
                  disabled={!symbol}
                  title={symbol
                    ? 'TradingView: full indicators + drawing tools'
                    : 'Not listed on TradingView — native engine only'}
                >
                  TradingView
                </button>
                <button
                  className={`interval-btn ${engine === 'native' ? 'active' : ''}`}
                  onClick={() => setEngine('native')}
                  title="This dashboard's own OHLCV data"
                >
                  Native data
                </button>
              </div>

              <button className="drawer-close" onClick={closeChart} aria-label="Close chart">
                Esc ✕
              </button>
            </div>

            <div className="chart-drawer-body">
              {engine === 'tv' && symbol ? (
                <>
                  {entry.proxyNote && (
                    <div className="proxy-note">
                      Showing <strong>{symbol}</strong> — {entry.proxyNote}.
                      Switch to <em>Native data</em> for this dashboard's actual series.
                    </div>
                  )}
                  <Suspense fallback={<div className="drawer-hint">Loading TradingView…</div>}>
                    <TradingViewWidget symbol={symbol} height={entry.proxyNote ? 'calc(100% - 26px)' : '100%'} />
                  </Suspense>
                </>
              ) : (
                <DrawerCandles
                  source={target.source}
                  instrumentKey={target.instrumentKey}
                  label={target.label}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </ChartDrawerContext.Provider>
  );
}

/** Small "open large chart" affordance for inline chart summaries. */
export function ExpandChartButton({ source, instrumentKey, label }) {
  const { openChart } = useChartDrawer();
  return (
    <button
      className="expand-chart-btn"
      title="Open large chart (Esc to close)"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        openChart({ source, instrumentKey, label });
      }}
    >
      ⤢
    </button>
  );
}
