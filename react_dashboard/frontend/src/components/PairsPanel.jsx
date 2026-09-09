import React, { useEffect, useMemo, useState } from 'react';
import { fetchSeriesCatalog, fetchPairs } from '../api';

const PRESETS = [
  { label: 'RTY / ES', a: '18_rty_futures', b: '17_es_futures' },
  { label: 'Gold / Silver', a: '13_gold', b: '14_silver' },
  { label: 'BTC / ETH', a: '87_crypto_majors/btc', b: '87_crypto_majors/eth' },
  { label: 'Gold / BTC', a: '13_gold', b: '87_crypto_majors/btc' },
  { label: 'Crude / Copper', a: '15_crude_oil', b: '16_copper' },
];

const f = (v, d = 2) => (v === null || v === undefined ? '—' : v.toFixed(d));
const fz = (v) => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}σ`);

/** Spread in trailing-year z units, with ±2σ bands and the zero line. */
function SpreadChart({ dates, z, width = 560, height = 150 }) {
  const vals = (z || []).filter((v) => v !== null && v !== undefined);
  if (vals.length < 2) return null;
  const lo = Math.min(-2.5, ...vals), hi = Math.max(2.5, ...vals);
  const span = hi - lo;
  const padL = 30, padR = 8, padT = 6, padB = 16;
  const w = width - padL - padR, h = height - padT - padB;
  const x = (i) => padL + (i / (vals.length - 1)) * w;
  const y = (v) => padT + (1 - (v - lo) / span) * h;
  const d = vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const last = vals[vals.length - 1];
  return (
    <svg width={width} height={height} style={{ display: 'block', maxWidth: '100%' }}>
      <rect x={padL} y={y(2)} width={w} height={y(-2) - y(2)} fill="#f7fafc" />
      {[2, 0, -2].map((lvl) => (
        <g key={lvl}>
          <line x1={padL} x2={width - padR} y1={y(lvl)} y2={y(lvl)}
            stroke={lvl === 0 ? '#a0aec0' : '#e53e3e'} strokeWidth={1} strokeDasharray={lvl === 0 ? '' : '4,3'} opacity={lvl === 0 ? 1 : 0.6} />
          <text x={padL - 4} y={y(lvl) + 3} fontSize={9} fill="#718096" textAnchor="end">{lvl > 0 ? `+${lvl}σ` : lvl === 0 ? '0' : `${lvl}σ`}</text>
        </g>
      ))}
      <path d={d} fill="none" stroke="#2b6cb0" strokeWidth={1.6} />
      <circle cx={x(vals.length - 1)} cy={y(last)} r={3.5} fill={Math.abs(last) >= 2 ? '#c53030' : '#2b6cb0'} />
      {dates && dates.length > 1 && (
        <>
          <text x={padL} y={height - 3} fontSize={9} fill="#718096">{dates[0]}</text>
          <text x={width - padR} y={height - 3} fontSize={9} fill="#718096" textAnchor="end">{dates[dates.length - 1]}</text>
        </>
      )}
    </svg>
  );
}

/**
 * Phase 3: the hedge-ratio spread between two instruments, and whether it is
 * tradeable. Order of the three headline numbers is deliberate — stationarity
 * first, because without it the z-score is a position on a random walk.
 */
export default function PairsPanel() {
  const [catalog, setCatalog] = useState(null);
  const [a, setA] = useState('18_rty_futures');
  const [b, setB] = useState('17_es_futures');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchSeriesCatalog().then((d) => setCatalog(d.catalog || {})).catch((e) => setError(e.message));
  }, []);

  const run = async (pa = a, pb = b) => {
    if (!pa || !pb || pa === pb) { setError('Pick two different series.'); return; }
    setLoading(true); setError(null);
    try { setResult(await fetchPairs(pa, pb)); }
    catch (e) { setError(e.response?.data?.detail || e.message); setResult(null); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (catalog && !result) run(); // eslint-disable-next-line
  }, [catalog]);

  const options = useMemo(() => {
    if (!catalog) return [];
    return Object.entries(catalog).map(([id, m]) => ({ id, ...m }))
      .sort((x, y) => (x.category || '').localeCompare(y.category || '') || x.label.localeCompare(y.label));
  }, [catalog]);

  const c = result?.cointegration;
  const stationary = c?.stationary;
  const zNow = result?.z_trailing_1y;

  return (
    <div className="fwd-panel">
      <div className="fwd-presets">
        {PRESETS.map((p) => (
          <button key={p.label} className="interval-btn" onClick={() => { setA(p.a); setB(p.b); run(p.a, p.b); }}>{p.label}</button>
        ))}
      </div>
      <div className="fwd-controls">
        <span>Spread of</span>
        <select value={a} onChange={(e) => setA(e.target.value)}>
          {options.map((o) => <option key={o.id} value={o.id}>{o.category ? `${o.category} · ` : ''}{o.label}</option>)}
        </select>
        <span>hedged with</span>
        <select value={b} onChange={(e) => setB(e.target.value)}>
          {options.map((o) => <option key={o.id} value={o.id}>{o.category ? `${o.category} · ` : ''}{o.label}</option>)}
        </select>
        <button className="refresh-btn" onClick={() => run()} disabled={loading}>{loading ? 'Computing…' : 'Compute'}</button>
      </div>

      {error && <div className="error-note">{error}</div>}

      {result && !error && (
        <>
          <div className="ev-stats">
            <div className="ev-stat">
              <div className="ev-stat-label">Stationary? (Engle-Granger)</div>
              <div className={`ev-stat-value ${stationary === true ? 'pos' : stationary === false ? 'neg' : 'dim'}`} style={{ fontSize: '1rem' }}>
                {c?.verdict || c?.error || '—'}
              </div>
              <div className="ev-stat-sub">
                {c?.p_value !== undefined && c?.p_value !== null ? `p = ${c.p_value.toFixed(3)} · t = ${f(c.t_stat, 2)} (5% crit ${f(c.crit_5pct, 2)})` : 'test unavailable'}
              </div>
            </div>
            <div className="ev-stat">
              <div className="ev-stat-label">Spread z — trailing year</div>
              <div className={`ev-stat-value ${Math.abs(zNow || 0) >= 2 ? 'ev-ratio-hot' : ''}`}>{fz(zNow)}</div>
              <div className="ev-stat-sub">full-sample {fz(result.z_full_sample)} · plain ratio {fz(result.ratio_z_trailing_1y)}</div>
            </div>
            <div className="ev-stat">
              <div className="ev-stat-label">Half-life</div>
              <div className="ev-stat-value">{result.half_life_days ? `${result.half_life_days.toFixed(0)}d` : '∞'}</div>
              <div className="ev-stat-sub">time for a deviation to halve (AR(1))</div>
            </div>
            <div className="ev-stat">
              <div className="ev-stat-label">Hedge ratio β</div>
              <div className="ev-stat-value">{f(result.hedge_ratio_beta, 3)}</div>
              <div className="ev-stat-sub">{result.basis} · {result.n_overlap} days</div>
            </div>
          </div>

          <div className={`lag-verdict ${stationary ? 'lead' : ''}`}>{result.reading}</div>

          <div className="ev-chart-wrap" style={{ marginTop: 8 }}>
            <SpreadChart dates={result.chart?.dates} z={result.chart?.z} />
            <div className="ev-legend">
              <span className="mean">spread in trailing-1y z units (last {result.chart?.z?.length} days)</span>
              <span style={{ color: '#e53e3e' }}>- - ±2σ</span>
            </div>
          </div>
          <div className="metric-caption fwd-caveat">⚠ {result.thresholds_note}</div>
        </>
      )}
    </div>
  );
}
