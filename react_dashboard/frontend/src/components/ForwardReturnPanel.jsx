import React, { useState } from 'react';
import { fetchForwardReturns } from '../api';

const OPS = [
  { value: 'gt', label: '>' },
  { value: 'gte', label: '≥' },
  { value: 'lt', label: '<' },
  { value: 'lte', label: '≤' },
];

// Instruments worth measuring a forward return on (price series, not levels).
const TARGETS = [
  { key: '17_es_futures', label: 'S&P 500 E-mini (ES)' },
  { key: '18_rty_futures', label: 'Russell 2000 E-mini (RTY)' },
  { key: '13_gold', label: 'Gold' },
  { key: '15_crude_oil', label: 'Crude Oil' },
  { key: '16_copper', label: 'Copper' },
  { key: '10_dxy', label: 'Dollar Index (DXY)' },
];

const PRESETS = [
  { label: 'VIX > 22', conditionKey: '8_vix', op: 'gt', threshold: 22 },
  { label: 'HY OAS > 3.5', conditionKey: '34_hy_oas', op: 'gt', threshold: 3.5 },
  { label: 'Cu/Au < 1.3', conditionKey: '57_cu_au_ratio', op: 'lt', threshold: 1.3 },
  { label: '2s10s < 0', conditionKey: '33_yield_curve', op: 'lt', threshold: 0 },
];

const pct = (v) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}%`);

/**
 * "When X held, what did Y do next?" — computed over the repo's own multi-year
 * history via /api/analytics/forward-returns.
 *
 * The baseline columns are the point: a 60% hit rate is not an edge if the
 * unconditional hit rate over the same sample is also 60%.
 */
export default function ForwardReturnPanel({ rows }) {
  const candidates = (rows || []).filter((r) => r.n_obs >= 250);

  const [conditionKey, setConditionKey] = useState('8_vix');
  const [op, setOp] = useState('gt');
  const [threshold, setThreshold] = useState(22);
  const [targetKey, setTargetKey] = useState('17_es_futures');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = async (over = {}) => {
    const params = {
      conditionKey: over.conditionKey ?? conditionKey,
      op: over.op ?? op,
      threshold: Number(over.threshold ?? threshold),
      targetKey: over.targetKey ?? targetKey,
      horizons: [5, 20, 60],
    };
    setLoading(true); setError(null);
    try {
      setResult(await fetchForwardReturns(params));
    } catch (e) {
      setError(e.response?.data?.detail || e.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const applyPreset = (p) => {
    setConditionKey(p.conditionKey); setOp(p.op); setThreshold(p.threshold);
    run(p);
  };

  return (
    <div className="fwd-panel">
      <div className="fwd-presets">
        {PRESETS.map((p) => (
          <button key={p.label} className="interval-btn" onClick={() => applyPreset(p)}>{p.label}</button>
        ))}
      </div>

      <div className="fwd-controls">
        <span>When</span>
        <select value={conditionKey} onChange={(e) => setConditionKey(e.target.value)}>
          {candidates.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}
        </select>
        <select value={op} onChange={(e) => setOp(e.target.value)} style={{ width: 56 }}>
          {OPS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <input
          type="number" step="any" value={threshold}
          onChange={(e) => setThreshold(e.target.value)} style={{ width: 90 }}
        />
        <span>→ forward return of</span>
        <select value={targetKey} onChange={(e) => setTargetKey(e.target.value)}>
          {TARGETS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
        </select>
        <button className="refresh-btn" onClick={() => run()} disabled={loading}>
          {loading ? 'Computing…' : 'Run'}
        </button>
      </div>

      {error && <div className="error-note">{error}</div>}

      {result && !error && (
        <div>
          <div className="fwd-summary">
            <strong>{result.condition.label} {OPS.find((o) => o.value === result.condition.op)?.label} {result.condition.threshold}</strong>
            {' → '}{result.target.label}{' '}
            <span className={`fwd-live ${result.condition.currently_true ? 'pos' : 'dim'}`}>
              {result.condition.currently_true ? 'CONDITION ACTIVE NOW' : 'not active now'}
              {' · latest '}{result.condition.latest}
            </span>
          </div>
          <div className="metric-caption">
            Sample {result.sample.start} → {result.sample.end} ·
            {' '}{result.sample.n_signal_days} of {result.sample.n_days} days matched
          </div>

          <div style={{ overflowX: 'auto' }}>
            <table className="monitor-table">
              <thead>
                <tr>
                  <th>Horizon</th><th style={{ textAlign: 'right' }}>n</th>
                  <th style={{ textAlign: 'right' }}>Mean</th>
                  <th style={{ textAlign: 'right' }}>Median</th>
                  <th style={{ textAlign: 'right' }}>Hit rate</th>
                  <th style={{ textAlign: 'right' }}>Baseline mean</th>
                  <th style={{ textAlign: 'right' }}>Edge (mean)</th>
                  <th style={{ textAlign: 'right' }}>Edge (hit)</th>
                </tr>
              </thead>
              <tbody>
                {result.horizons.map((h) => (
                  <tr key={h.horizon_days}>
                    <td>{h.horizon_days}d</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{h.n_signal}</td>
                    <td className={`mono ${h.mean_pct > 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>{pct(h.mean_pct)}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{pct(h.median_pct)}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{h.hit_rate_pct?.toFixed(1)}%</td>
                    <td className="mono dim" style={{ textAlign: 'right' }}>{pct(h.baseline_mean_pct)}</td>
                    <td className={`mono ${h.edge_mean_pct > 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>{pct(h.edge_mean_pct)}</td>
                    <td className={`mono ${h.edge_hit_rate_pct > 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>
                      {h.edge_hit_rate_pct > 0 ? '+' : ''}{h.edge_hit_rate_pct?.toFixed(1)}pp
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="metric-caption fwd-caveat">⚠ {result.caveat}</div>
        </div>
      )}
    </div>
  );
}
