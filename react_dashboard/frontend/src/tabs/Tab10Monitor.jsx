import React, { useEffect, useMemo, useState } from 'react';
import { fetchMonitor, fetchRegime } from '../api';
import SectionHeader from '../components/SectionHeader';
import Sparkline from '../components/Sparkline';
import ForwardReturnPanel from '../components/ForwardReturnPanel';
import CorrelationPanel from '../components/CorrelationPanel';
import EventStudyPanel from '../components/EventStudyPanel';
import { toGMT8 } from '../utils/time';

const fmtNum = (v, d = 2) =>
  v === null || v === undefined ? '—'
    : Math.abs(v) >= 1000 ? v.toLocaleString(undefined, { maximumFractionDigits: 0 })
    : v.toFixed(d);

function Delta({ pct }) {
  if (pct === null || pct === undefined) return <span className="mono dim">—</span>;
  const cls = pct > 0 ? 'pos' : pct < 0 ? 'neg' : 'dim';
  return <span className={`mono ${cls}`}>{pct > 0 ? '+' : ''}{pct.toFixed(2)}%</span>;
}

/** 1-year percentile as a small filled bar — where today sits in its own range. */
function PctBar({ v }) {
  if (v === null || v === undefined) return <span className="dim">—</span>;
  const hue = v >= 80 ? '#c53030' : v <= 20 ? '#2b6cb0' : '#a0aec0';
  return (
    <span className="pctbar" title={`${v.toFixed(0)}th percentile of the trailing year`}>
      <span className="pctbar-fill" style={{ width: `${v}%`, background: hue }} />
      <span className="pctbar-text">{v.toFixed(0)}</span>
    </span>
  );
}

function RegimePanel({ regime }) {
  if (!regime) return null;
  if (regime.error) return <div className="error-note">{regime.error}</div>;

  const score = regime.score;
  const tone = score === null ? 'dim' : score > 0.25 ? 'pos' : score < -0.25 ? 'neg' : 'dim';
  // Map [-2, +2] onto a 0-100% marker position.
  const pos = score === null ? 50 : Math.max(0, Math.min(100, ((score + 2) / 4) * 100));

  return (
    <div className="regime-panel">
      <div className="regime-head">
        <div>
          <div className="regime-score-label">Risk regime</div>
          <div className={`regime-score ${tone}`}>
            {score === null ? '—' : (score > 0 ? '+' : '') + score.toFixed(2)}
            <span className="regime-verdict">{regime.label}</span>
          </div>
        </div>
        <div className="regime-movers">
          <div className="regime-score-label">Largest 1-day moves</div>
          {(regime.top_movers_1d || []).map((m) => (
            <div key={m.label} className="regime-mover">
              <span>{m.label}</span>
              <span className={`mono ${m.z_change_1d > 0 ? 'pos' : 'neg'}`}>
                {m.z_change_1d > 0 ? '+' : ''}{m.z_change_1d?.toFixed(2)}σ
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="regime-scale">
        <span>risk-off</span>
        <div className="regime-track"><div className="regime-marker" style={{ left: `${pos}%` }} /></div>
        <span>risk-on</span>
      </div>

      <div className="regime-components">
        {(regime.components || []).filter((c) => c.status === 'ok').map((c) => (
          <div key={c.key} className="regime-chip" title={`z=${c.z} · contribution ${c.contribution}`}>
            <span className="regime-chip-label">{c.label}</span>
            <span className={`mono ${c.contribution > 0 ? 'pos' : 'neg'}`}>
              {c.contribution > 0 ? '+' : ''}{c.contribution?.toFixed(2)}
            </span>
          </div>
        ))}
      </div>
      <div className="metric-caption">{regime.method}</div>
    </div>
  );
}

export default function Tab10Monitor() {
  const [rows, setRows] = useState(null);
  const [regime, setRegime] = useState(null);
  const [error, setError] = useState(null);
  const [sortKey, setSortKey] = useState('category');
  const [sortDir, setSortDir] = useState(1);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    let cancelled = false;
    Promise.all([fetchMonitor(), fetchRegime()])
      .then(([m, r]) => {
        if (cancelled) return;
        setRows(m.rows || []);
        setRegime(r);
      })
      .catch((e) => !cancelled && setError(e.response?.data?.error || e.message));
    return () => { cancelled = true; };
  }, []);

  const sorted = useMemo(() => {
    if (!rows) return [];
    const q = filter.trim().toLowerCase();
    const out = rows.filter(
      (r) => !q || r.label.toLowerCase().includes(q) || r.category.toLowerCase().includes(q)
    );
    out.sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      if (typeof av === 'string') return av.localeCompare(bv) * sortDir;
      return (av - bv) * sortDir;
    });
    return out;
  }, [rows, sortKey, sortDir, filter]);

  const sortBy = (k) => {
    if (k === sortKey) setSortDir((d) => -d);
    else { setSortKey(k); setSortDir(k === 'category' || k === 'label' ? 1 : -1); }
  };

  const Th = ({ k, children, align = 'left' }) => (
    <th onClick={() => sortBy(k)} style={{ textAlign: align, cursor: 'pointer' }}>
      {children}{sortKey === k ? (sortDir > 0 ? ' ▲' : ' ▼') : ''}
    </th>
  );

  if (error) return <div className="error-card"><div className="error-title">Monitor unavailable</div><div>{error}</div></div>;
  if (!rows) return <div className="metric-caption">Loading monitor…</div>;

  return (
    <div>
      <SectionHeader title="Risk Regime Composite" />
      <RegimePanel regime={regime} />

      <SectionHeader title={`Monitor — ${sorted.length} indicators with history`} />
      <input
        className="monitor-filter"
        placeholder="Filter by name or category…"
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
      />
      <div style={{ overflowX: 'auto' }}>
        <table className="monitor-table">
          <thead>
            <tr>
              <Th k="category">Category</Th>
              <Th k="label">Indicator</Th>
              <Th k="latest" align="right">Latest</Th>
              <Th k="chg_1d_pct" align="right">1D</Th>
              <Th k="chg_5d_pct" align="right">5D</Th>
              <Th k="chg_21d_pct" align="right">1M</Th>
              <Th k="pct_1y" align="right">1Y %ile</Th>
              <th>60-obs trend</th>
              <th>As of</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.key}>
                <td className="dim">{r.category}</td>
                <td>{r.label}</td>
                <td className="mono" style={{ textAlign: 'right' }}>{fmtNum(r.latest)}</td>
                <td style={{ textAlign: 'right' }}><Delta pct={r.chg_1d_pct} /></td>
                <td style={{ textAlign: 'right' }}><Delta pct={r.chg_5d_pct} /></td>
                <td style={{ textAlign: 'right' }}><Delta pct={r.chg_21d_pct} /></td>
                <td style={{ textAlign: 'right' }}><PctBar v={r.pct_1y} /></td>
                <td><Sparkline values={r.spark} /></td>
                <td className="dim mono">{r.last_date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="metric-caption">
        Percent change is shown for every row; on yields and spreads read it as relative, not basis points.
        Percentile ranks the latest reading within its own trailing ~252 observations.
      </div>

      <SectionHeader title="Correlation" />
      <CorrelationPanel />

      <SectionHeader title="Event Study — behaviour around macro catalysts" />
      <EventStudyPanel />

      <SectionHeader title="Conditional Forward Returns" />
      <ForwardReturnPanel rows={rows} />
    </div>
  );
}
