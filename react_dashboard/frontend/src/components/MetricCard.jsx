import React from 'react';

/**
 * Compact metric card showing label, value, delta, and optional caption.
 */
export default function MetricCard({ label, value, delta, deltaLabel, caption, suffix = '', inverse = false }) {
  const fmtValue = value === null || value === undefined || value === 'N/A'
    ? 'N/A'
    : typeof value === 'number'
      ? `${value.toLocaleString(undefined, { maximumFractionDigits: 4 })}${suffix}`
      : `${value}${suffix}`;

  let deltaClass = 'neutral';
  if (delta !== null && delta !== undefined && typeof delta === 'number') {
    if (inverse) {
      deltaClass = delta > 0 ? 'negative' : delta < 0 ? 'positive' : 'neutral';
    } else {
      deltaClass = delta > 0 ? 'positive' : delta < 0 ? 'negative' : 'neutral';
    }
  }

  const fmtDelta = delta !== null && delta !== undefined && typeof delta === 'number'
    ? `${delta >= 0 ? '+' : ''}${delta.toLocaleString(undefined, { maximumFractionDigits: 4 })}${deltaLabel || ''}`
    : null;

  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{fmtValue}</div>
      {fmtDelta && <div className={`metric-delta ${deltaClass}`}>{fmtDelta}</div>}
      {caption && <div className="metric-caption">{caption}</div>}
    </div>
  );
}
