import React, { useEffect, useState } from 'react';
import { fetchCorrRegime } from '../api';
import Sparkline from './Sparkline';

const WINDOWS = [30, 60, 90];
const fc = (v) => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`);

/**
 * Phase 4: which cross-asset relationships have broken from their norm.
 * The level of a correlation is rarely the trade — the change is. Every row
 * shows current ρ next to its own trailing-year norm, and ranks by |z|.
 */
export default function CorrRegimePanel() {
  const [window_, setWindow] = useState(60);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setData(null); setError(null);
    fetchCorrRegime(window_)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(e.response?.data?.detail || e.message));
    return () => { cancelled = true; };
  }, [window_]);

  const chip = (r) => {
    if (r.status === 'break') return <span className={`cr-chip cr-break`}>{r.direction === 'coupling' ? 'COUPLING' : 'DECOUPLING'}</span>;
    if (r.status === 'watch') return <span className="cr-chip cr-watch">watch · {r.direction}</span>;
    return <span className="cr-chip cr-normal">normal</span>;
  };

  return (
    <div className="fwd-panel">
      <div className="fwd-presets">
        <span style={{ fontSize: '0.75rem', color: '#718096' }}>Rolling window</span>
        {WINDOWS.map((w) => (
          <button key={w} className={`interval-btn ${window_ === w ? 'active' : ''}`} onClick={() => setWindow(w)}>{w}d</button>
        ))}
        {data && (
          <span className="metric-caption" style={{ marginLeft: 'auto' }}>
            <strong className={data.n_breaks ? 'neg' : 'dim'}>{data.n_breaks} break{data.n_breaks === 1 ? '' : 's'}</strong>
            {' · '}{data.n_watch} on watch · {data.rows.length} pairs scanned
          </span>
        )}
      </div>

      {error && <div className="error-note">{error}</div>}
      {!data && !error && <div className="metric-caption">Scanning…</div>}

      {data && (
        <div style={{ overflowX: 'auto' }}>
          <table className="monitor-table">
            <thead>
              <tr>
                <th>Pair</th>
                <th>Status</th>
                <th style={{ textAlign: 'right' }}>ρ now</th>
                <th style={{ textAlign: 'right' }}>1y norm</th>
                <th style={{ textAlign: 'right' }}>long-run</th>
                <th style={{ textAlign: 'right' }}>z</th>
                <th>rolling ρ · 120d</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <tr key={`${r.a}~${r.b}`} className={r.status === 'break' ? 'cr-row-break' : ''}>
                  <td>{r.a_label} <span className="dim">vs</span> {r.b_label}</td>
                  <td>{chip(r)}</td>
                  <td className={`mono ${r.corr_now >= 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>{fc(r.corr_now)}</td>
                  <td className="mono dim" style={{ textAlign: 'right' }}>{fc(r.corr_norm_1y)}</td>
                  <td className="mono dim" style={{ textAlign: 'right' }}>{fc(r.corr_long_run)}</td>
                  <td className={`mono ${Math.abs(r.z || 0) >= 2 ? 'neg' : Math.abs(r.z || 0) >= 1.5 ? '' : 'dim'}`} style={{ textAlign: 'right' }}>
                    {r.z === null || r.z === undefined ? '—' : `${r.z >= 0 ? '+' : ''}${r.z.toFixed(2)}σ`}
                  </td>
                  <td><Sparkline values={r.spark} width={110} height={22} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.unavailable?.length > 0 && (
            <div className="metric-caption">
              Not scanned: {data.unavailable.map((u) => `${u.a} ~ ${u.b} (${u.reason})`).join('; ')}
            </div>
          )}
          <div className="metric-caption">{data.method}</div>
        </div>
      )}
    </div>
  );
}
