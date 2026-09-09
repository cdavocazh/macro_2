import React, { useEffect, useMemo, useState } from 'react';
import { fetchSeriesCatalog, fetchCorrelation } from '../api';
import Sparkline from './Sparkline';

const WINDOWS = [30, 60, 90, 120];

const PRESETS = [
  { label: 'Gold vs BTC', ids: ['13_gold', '87_crypto_majors/btc'] },
  { label: 'Gold vs DXY', ids: ['13_gold', '10_dxy'] },
  { label: 'BTC vs ES', ids: ['87_crypto_majors/btc', '17_es_futures'] },
  { label: 'Risk basket', ids: ['17_es_futures', '8_vix', '13_gold', '87_crypto_majors/btc', '10_dxy'] },
];

/** Red (negative) → white (0) → blue (positive), like a standard corr heatmap. */
function corrColor(v) {
  if (v === null || v === undefined) return '#f7fafc';
  const a = Math.min(Math.abs(v), 1);
  return v >= 0 ? `rgba(43,108,176,${a * 0.75})` : `rgba(197,48,48,${a * 0.75})`;
}

export default function CorrelationPanel() {
  const [catalog, setCatalog] = useState(null);
  const [selected, setSelected] = useState(['13_gold', '87_crypto_majors/btc']);
  const [window_, setWindow] = useState(60);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSeriesCatalog()
      .then((d) => setCatalog(d.catalog || {}))
      .catch((e) => setError(e.message));
  }, []);

  const run = async (ids = selected, w = window_) => {
    if (ids.length < 2) { setError('Pick at least two series.'); return; }
    setLoading(true); setError(null);
    try {
      setResult(await fetchCorrelation(ids, w));
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setResult(null);
    } finally { setLoading(false); }
  };

  useEffect(() => { if (catalog) run(); /* initial */ // eslint-disable-next-line
  }, [catalog]);

  const options = useMemo(() => {
    if (!catalog) return [];
    return Object.entries(catalog)
      .map(([id, meta]) => ({ id, ...meta }))
      .sort((a, b) => (a.category || '').localeCompare(b.category || '') || a.label.localeCompare(b.label));
  }, [catalog]);

  const toggle = (id) => {
    setSelected((cur) => cur.includes(id) ? cur.filter((x) => x !== id)
      : cur.length >= 12 ? cur : [...cur, id]);
  };

  const applyPreset = (p) => { setSelected(p.ids); run(p.ids, window_); };

  const rolling = result?.rolling;

  return (
    <div className="fwd-panel">
      <div className="fwd-presets">
        {PRESETS.map((p) => (
          <button key={p.label} className="interval-btn" onClick={() => applyPreset(p)}>{p.label}</button>
        ))}
        <span style={{ marginLeft: 12, fontSize: '0.75rem', color: '#718096' }}>Rolling window</span>
        {WINDOWS.map((w) => (
          <button key={w} className={`interval-btn ${window_ === w ? 'active' : ''}`}
            onClick={() => { setWindow(w); run(selected, w); }}>{w}d</button>
        ))}
      </div>

      <div className="corr-picker">
        <select
          className="corr-select"
          value=""
          onChange={(e) => { if (e.target.value) toggle(e.target.value); }}
        >
          <option value="">+ Add a series…</option>
          {options.filter((o) => !selected.includes(o.id)).map((o) => (
            <option key={o.id} value={o.id}>
              {o.category ? `${o.category} · ` : ''}{o.label}{o.n_obs ? ` (${o.n_obs}d)` : ''}
            </option>
          ))}
        </select>
        <div className="corr-chips">
          {selected.map((id) => (
            <span key={id} className="corr-chip">
              {catalog?.[id]?.label || id}
              <button onClick={() => toggle(id)} title="Remove">×</button>
            </span>
          ))}
        </div>
        <button className="refresh-btn" onClick={() => run()} disabled={loading}>
          {loading ? 'Computing…' : 'Compute'}
        </button>
      </div>

      {error && <div className="error-note">{error}</div>}

      {result && (
        <>
          {(result.warnings || []).map((w, i) => (
            <div key={i} className="metric-caption fwd-caveat">⚠ {w}</div>
          ))}

          {rolling && (
            <div className="corr-rolling">
              <div className="corr-rolling-head">
                <strong>{rolling.a_label} vs {rolling.b_label}</strong>
                <span className="metric-caption">
                  {rolling.window}-day rolling correlation · {rolling.dates.length} points
                </span>
              </div>
              <div className="corr-rolling-stats">
                <div>
                  <div className="regime-score-label">Now</div>
                  <div className={`corr-big ${rolling.latest >= 0 ? 'pos' : 'neg'}`}>
                    {rolling.latest >= 0 ? '+' : ''}{rolling.latest?.toFixed(3)}
                  </div>
                </div>
                <div>
                  <div className="regime-score-label">Its own average</div>
                  <div className="mono">{rolling.mean >= 0 ? '+' : ''}{rolling.mean?.toFixed(3)}</div>
                </div>
                <div>
                  <div className="regime-score-label">Range</div>
                  <div className="mono">{rolling.min?.toFixed(2)} … {rolling.max?.toFixed(2)}</div>
                </div>
                <div>
                  <div className="regime-score-label">Deviation</div>
                  <div className={`mono ${Math.abs(rolling.z_vs_own_history) >= 2 ? 'neg' : 'dim'}`}>
                    {rolling.z_vs_own_history >= 0 ? '+' : ''}{rolling.z_vs_own_history?.toFixed(2)}σ
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 160 }}>
                  <Sparkline values={rolling.values} width={220} height={40} />
                </div>
              </div>
              {Math.abs(rolling.z_vs_own_history || 0) >= 2 && (
                <div className="corr-alert">
                  Current {rolling.window}-day correlation is {Math.abs(rolling.z_vs_own_history).toFixed(1)}σ
                  from its own history — these two are behaving
                  {' '}{rolling.latest > rolling.mean ? 'far more' : 'far less'} alike than usual.
                </div>
              )}
            </div>
          )}

          <div style={{ overflowX: 'auto', marginTop: 10 }}>
            <table className="corr-matrix">
              <thead>
                <tr>
                  <th />
                  {result.labels.map((l, i) => <th key={i} title={result.ids[i]}>{l}</th>)}
                </tr>
              </thead>
              <tbody>
                {result.matrix.map((row, i) => (
                  <tr key={i}>
                    <th title={result.ids[i]}>{result.labels[i]}</th>
                    {row.map((v, j) => (
                      <td key={j} style={{ background: i === j ? '#edf2f7' : corrColor(v) }}>
                        {v === null || v === undefined ? '—' : v.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="metric-caption">
            Computed on {result.basis}. Correlating price <em>levels</em> would score any two
            trending assets near 1.0 regardless of co-movement. Each pair's overlap is counted
            separately — hover a cell's row/column header for its series id.
          </div>

          <table className="monitor-table" style={{ marginTop: 6 }}>
            <thead>
              <tr>
                <th>Pair</th>
                <th style={{ textAlign: 'right' }}>Correlation</th>
                <th style={{ textAlign: 'right' }}>Overlap</th>
                <th>Quality</th>
              </tr>
            </thead>
            <tbody>
              {(result.pairs || []).map((p, i) => (
                <tr key={i}>
                  <td>{p.a_label} <span className="dim">vs</span> {p.b_label}</td>
                  <td className={`mono ${p.corr >= 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>
                    {p.corr >= 0 ? '+' : ''}{p.corr?.toFixed(3)}
                  </td>
                  <td className="mono" style={{ textAlign: 'right' }}>{p.n_overlap}d</td>
                  <td className={p.quality === 'thin' ? 'neg' : 'dim'}>
                    {p.quality === 'thin' ? 'thin sample' : 'ok'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
