import React from 'react';

/**
 * Inline SVG sparkline. Deliberately dependency-free — the monitor grid renders
 * ~58 of these at once and pulling plotly in for them would undo the lazy-chunk
 * work that keeps first paint at ~1.5 s.
 */
export default function Sparkline({ values, width = 90, height = 22, color = '#2b6cb0' }) {
  const pts = (values || []).filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (pts.length < 2) return <svg width={width} height={height} />;

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const span = max - min || 1;
  const dx = width / (pts.length - 1);

  const d = pts
    .map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * dx).toFixed(1)},${(height - ((v - min) / span) * height).toFixed(1)}`)
    .join(' ');

  // Colour by net direction over the window, matching the change columns.
  const stroke = pts[pts.length - 1] >= pts[0] ? '#2f855a' : '#c53030';

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <path d={d} fill="none" stroke={stroke || color} strokeWidth="1.2" />
    </svg>
  );
}
