import React, { useState, useCallback } from 'react';
import Plot from 'react-plotly.js';
import api from '../api';

const INTERVALS = [
  { label: '1H', value: '1h' },
  { label: '6H', value: '6h' },
  { label: '1D', value: '1d' },
  { label: 'All', value: 'all' },
];

// Color palette for multi-outcome lines
const OUTCOME_COLORS = [
  '#1976d2', '#26a69a', '#ef5350', '#ff9800', '#9c27b0',
  '#00bcd4', '#e91e63', '#4caf50', '#ff5722', '#607d8b',
  '#3f51b5', '#cddc39',
];

/**
 * Polymarket prediction price chart using Plotly.
 * Supports both single-outcome and multi-outcome events.
 *
 * Props:
 *   outcomes: [{label, token_id, yes_price}] — outcome list with token IDs
 *   label: string — event title for chart header
 */
export default function PolymarketPriceChart({ outcomes, label }) {
  const [interval, setInterval_] = useState('1d');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [traces, setTraces] = useState([]);
  const [fetched, setFetched] = useState(false);

  const fetchData = useCallback(async (intv) => {
    if (!outcomes || outcomes.length === 0) return;
    setLoading(true);
    setError(null);

    try {
      // Fetch history for each outcome in parallel (limit to top 8)
      const toFetch = outcomes.filter(o => o.token_id).slice(0, 8);
      const results = await Promise.all(
        toFetch.map(async (o) => {
          try {
            const resp = await api.get(`/polymarket/history/${o.token_id}`, {
              params: { interval: intv },
            });
            return { outcome: o, data: resp.data || [] };
          } catch {
            return { outcome: o, data: [] };
          }
        })
      );

      const newTraces = results
        .filter(r => r.data.length > 0)
        .map((r, i) => {
          // Deduplicate by timestamp (keep last value per timestamp)
          const seen = new Map();
          for (const pt of r.data) {
            seen.set(pt.time, pt.value);
          }
          const dedupedEntries = [...seen.entries()].sort((a, b) => a[0] - b[0]);

          return {
            x: dedupedEntries.map(([t]) => new Date(t * 1000)),
            y: dedupedEntries.map(([, v]) => v * 100),
            type: 'scatter',
            mode: 'lines',
            name: r.outcome.label?.length > 35
              ? r.outcome.label.substring(0, 35) + '...'
              : r.outcome.label || `Outcome ${i + 1}`,
            line: { color: OUTCOME_COLORS[i % OUTCOME_COLORS.length], width: 2 },
            hovertemplate: '%{y:.1f}%<extra>%{fullData.name}</extra>',
          };
        });

      setTraces(newTraces);
      if (newTraces.length === 0) {
        setError('No price data available');
      }
    } catch (e) {
      setError(e.message || 'Failed to load price history');
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [outcomes]);

  const handleToggle = (e) => {
    if (e.target.open && !fetched) {
      fetchData(interval);
    }
  };

  const handleIntervalChange = (intv) => {
    setInterval_(intv);
    fetchData(intv);
  };

  return (
    <details className="chart-expander" style={{ marginTop: 4, marginBottom: 8 }} onToggle={handleToggle}>
      <summary style={{ cursor: 'pointer', fontSize: '0.78rem', color: '#666', padding: '2px 0' }}>
        ▸ Price Chart
      </summary>
      <div style={{ marginTop: 4 }}>
        {/* Interval selector */}
        <div style={{ display: 'flex', gap: 4, marginBottom: 4, alignItems: 'center' }}>
          {INTERVALS.map(({ label: lbl, value }) => (
            <button
              key={value}
              onClick={() => handleIntervalChange(value)}
              style={{
                padding: '2px 8px',
                fontSize: '0.7rem',
                border: `1px solid ${interval === value ? '#1976d2' : '#ccc'}`,
                borderRadius: 3,
                background: interval === value ? '#1976d2' : 'transparent',
                color: interval === value ? '#fff' : '#666',
                cursor: 'pointer',
              }}
            >
              {lbl}
            </button>
          ))}
          {loading && <span style={{ fontSize: '0.7rem', color: '#999', marginLeft: 8 }}>Loading...</span>}
          {error && <span style={{ fontSize: '0.7rem', color: '#ef5350', marginLeft: 8 }}>{error}</span>}
        </div>

        {/* Plotly chart */}
        {traces.length > 0 && (
          <Plot
            data={traces}
            layout={{
              height: 300,
              margin: { l: 45, r: 15, t: 10, b: 30 },
              hovermode: 'x unified',
              xaxis: {
                type: 'date',
                gridcolor: '#eee',
                linecolor: '#ddd',
              },
              yaxis: {
                title: { text: 'Probability (%)', font: { size: 11 } },
                range: [0, 100],
                gridcolor: '#eee',
                linecolor: '#ddd',
                ticksuffix: '%',
              },
              legend: {
                orientation: 'h',
                yanchor: 'bottom',
                y: 1.02,
                xanchor: 'left',
                x: 0,
                font: { size: 10 },
              },
              paper_bgcolor: '#fff',
              plot_bgcolor: '#fafafa',
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        )}
      </div>
    </details>
  );
}
