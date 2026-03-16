import React, { useState, useMemo } from 'react';
import Plot from 'react-plotly.js';

/**
 * Collapsible Plotly line chart with 1W/1M/3M range buttons.
 * Accepts serialized series data { __type__: 'series', index: [...], values: [...] }
 * or a raw object with index/values arrays.
 */
export default function HistoryChart({ data, label, color = '#1f77b4', suffix = '' }) {
  const [open, setOpen] = useState(false);

  const chartData = useMemo(() => {
    if (!data) return null;
    let idx, vals;
    if (data.__type__ === 'series' || (data.index && data.values)) {
      idx = data.index;
      vals = data.values;
    } else if (Array.isArray(data)) {
      return null;
    } else {
      return null;
    }
    if (!idx || !vals || idx.length < 2) return null;
    return { x: idx, y: vals };
  }, [data]);

  if (!chartData) return null;

  const hexToRgba = (hex, alpha) => {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return `rgba(${r},${g},${b},${alpha})`;
  };

  return (
    <details className="chart-expander" open={open} onToggle={(e) => setOpen(e.target.open)}>
      <summary>3M Price History</summary>
      {open && (
        <div className="chart-container">
          <Plot
            data={[
              {
                x: chartData.x,
                y: chartData.y,
                type: 'scatter',
                mode: 'lines',
                name: label,
                line: { color, width: 1.5 },
                fill: 'tozeroy',
                fillcolor: hexToRgba(color, 0.08),
                hovertemplate: `%{x|%b %d, %Y}: %{y:,.2f}${suffix}<extra></extra>`,
              },
            ]}
            layout={{
              xaxis: {
                rangeselector: {
                  buttons: [
                    { count: 7, label: '1W', step: 'day', stepmode: 'backward' },
                    { count: 1, label: '1M', step: 'month', stepmode: 'backward' },
                    { count: 3, label: '3M', step: 'month', stepmode: 'backward' },
                  ],
                  bgcolor: '#f0f2f6',
                },
                rangeslider: { visible: true, thickness: 0.05 },
              },
              yaxis: { title: label },
              height: 300,
              margin: { l: 50, r: 20, t: 10, b: 10 },
              showlegend: false,
              hovermode: 'x unified',
            }}
            config={{ responsive: true, displayModeBar: false }}
            style={{ width: '100%' }}
          />
        </div>
      )}
    </details>
  );
}
