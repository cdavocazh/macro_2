import React, { useEffect, useState } from 'react';
import { fetchBeta, fetchLeadLag } from '../api';
import Sparkline from './Sparkline';

const f3 = (v) => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(3)}`);
const f2 = (v) => (v === null || v === undefined ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}`);

/**
 * Lag profile as inline SVG bars. The shaded band is ±2/√n — bars that don't
 * clear it are sampling noise, which on daily data is most of them.
 */
function LagChart({ profile, band, width = 320, height = 90 }) {
  const pts = (profile || []).filter((p) => p.corr !== null && p.corr !== undefined);
  if (!pts.length) return null;
  const maxAbs = Math.max(0.1, ...pts.map((p) => Math.abs(p.corr)), band);
  const mid = height / 2;
  const scale = (mid - 6) / maxAbs;
  const bw = width / pts.length;
  const bandPx = band * scale;
  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <rect x={0} y={mid - bandPx} width={width} height={bandPx * 2} fill="#edf2f7" />
      <line x1={0} x2={width} y1={mid} y2={mid} stroke="#a0aec0" strokeWidth={1} />
      {pts.map((p, i) => {
        const h = Math.abs(p.corr) * scale;
        const y = p.corr >= 0 ? mid - h : mid;
        const isZero = p.lag === 0;
        return (
          <g key={p.lag}>
            <rect
              x={i * bw + 1} y={y} width={Math.max(bw - 2, 1)} height={h}
              fill={isZero ? '#1a202c' : p.corr >= 0 ? '#2b6cb0' : '#c53030'}
              opacity={Math.abs(p.corr) > band ? 0.9 : 0.35}
            >
              <title>{`lag ${p.lag >= 0 ? '+' : ''}${p.lag}: ${p.corr.toFixed(3)} (n=${p.n})`}</title>
            </rect>
            {(p.lag % 5 === 0) && (
              <text x={i * bw + bw / 2} y={height - 1} fontSize={9} fill="#718096" textAnchor="middle">
                {p.lag > 0 ? `+${p.lag}` : p.lag}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/**
 * Phase-2 pair analytics for the first two selected series: beta (the hedge
 * ratio — HOW MUCH a moves per 1% of b) and lead/lag (does one move first).
 */
export default function PairAnalytics({ a, b, window = 60 }) {
  const [beta, setBeta] = useState(null);
  const [lag, setLag] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!a || !b) return;
    let cancelled = false;
    setBeta(null); setLag(null); setError(null);
    Promise.all([fetchBeta(a, b, window), fetchLeadLag(a, b, 10)])
      .then(([bt, ll]) => { if (!cancelled) { setBeta(bt); setLag(ll); } })
      .catch((e) => !cancelled && setError(e.response?.data?.detail || e.message));
    return () => { cancelled = true; };
  }, [a, b, window]);

  if (error) return <div className="error-note" style={{ marginTop: 8 }}>{error}</div>;
  if (!beta || !lag) return <div className="metric-caption">Computing beta and lead/lag…</div>;

  const r = beta.rolling;
  const r2 = beta.r_squared ?? 0;

  return (
    <div className="pair-grid">
      <div className="pair-card">
        <div className="pair-card-title">Beta — hedge ratio · {beta.n_overlap} overlapping days</div>
        <div className="pair-stats">
          <div>
            <div className="regime-score-label">{beta.a_label} on {beta.b_label}</div>
            <div className={`pair-big ${beta.beta_a_on_b >= 0 ? 'pos' : 'neg'}`}>{f3(beta.beta_a_on_b)}</div>
          </div>
          <div>
            <div className="regime-score-label">reverse</div>
            <div className="mono">{f3(beta.beta_b_on_a)}</div>
          </div>
          <div>
            <div className="regime-score-label">R²</div>
            <div className={`mono ${r2 >= 0.5 ? 'pos' : r2 >= 0.2 ? '' : 'dim'}`}>{r2.toFixed(2)}</div>
          </div>
        </div>
        <div className="pair-note">{beta.hedge_note}</div>
        {r && (
          <div className="pair-stats" style={{ marginTop: 8 }}>
            <div>
              <div className="regime-score-label">Rolling {r.window}d β now</div>
              <div className="mono">{f2(r.latest)}</div>
            </div>
            <div>
              <div className="regime-score-label">its average</div>
              <div className="mono dim">{f2(r.mean)}</div>
            </div>
            <div>
              <div className="regime-score-label">deviation</div>
              <div className={`mono ${Math.abs(r.z_vs_own_history || 0) >= 2 ? 'neg' : 'dim'}`}>
                {f2(r.z_vs_own_history)}σ
              </div>
            </div>
            <Sparkline values={r.values} width={150} height={32} />
          </div>
        )}
      </div>

      <div className="pair-card">
        <div className="pair-card-title">Lead / lag — corr({lag.a_label}ₜ, {lag.b_label}ₜ₊ₖ)</div>
        <LagChart profile={lag.profile} band={lag.noise_band} />
        <div className="metric-caption">
          Shaded band ±{lag.noise_band?.toFixed(3)} is sampling noise at n={lag.n_overlap}. Black bar = same day.
          Positive lag ⇒ {lag.a_label} leads.
        </div>
        <div className={`lag-verdict ${lag.leader ? 'lead' : ''}`}>{lag.verdict}</div>
      </div>
    </div>
  );
}
