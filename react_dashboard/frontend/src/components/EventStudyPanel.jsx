import React, { useEffect, useState } from 'react';
import { fetchEventCatalog, fetchEventStudy } from '../api';

const TARGETS = [
  { key: '17_es_futures', label: 'S&P 500 E-mini (ES)' },
  { key: '18_rty_futures', label: 'Russell 2000 E-mini (RTY)' },
  { key: '13_gold', label: 'Gold' },
  { key: '10_dxy', label: 'Dollar Index (DXY)' },
  { key: '15_crude_oil', label: 'Crude Oil' },
  { key: '16_copper', label: 'Copper' },
  { key: '87_crypto_majors/btc', label: 'Bitcoin' },
  { key: '8_vix', label: 'VIX' },
  { key: '11_10y_yield', label: 'US 10Y Yield' },
];
const WINDOWS = [1, 3, 5, 10];

const pct = (v, d = 2) => (v === null || v === undefined ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}%`);

/** Mean and median cumulative path around t=0, inline SVG. */
function PathChart({ offsets, mean, median, width = 520, height = 150 }) {
  const all = [...mean, ...median].filter((v) => v !== null && v !== undefined);
  if (!all.length) return null;
  const lo = Math.min(0, ...all), hi = Math.max(0, ...all);
  const span = hi - lo || 1;
  const padL = 36, padR = 10, padT = 8, padB = 18;
  const w = width - padL - padR, h = height - padT - padB;
  const x = (i) => padL + (i / (offsets.length - 1)) * w;
  const y = (v) => padT + (1 - (v - lo) / span) * h;
  const path = (vals) => vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const zeroIdx = offsets.indexOf(0);
  return (
    <svg width={width} height={height} style={{ display: 'block', maxWidth: '100%' }}>
      <line x1={padL} x2={width - padR} y1={y(0)} y2={y(0)} stroke="#a0aec0" strokeWidth={1} />
      {zeroIdx >= 0 && (
        <line x1={x(zeroIdx)} x2={x(zeroIdx)} y1={padT} y2={height - padB} stroke="#c53030" strokeDasharray="3,3" />
      )}
      <path d={path(median)} fill="none" stroke="#a0aec0" strokeWidth={1.2} strokeDasharray="4,3" />
      <path d={path(mean)} fill="none" stroke="#2b6cb0" strokeWidth={2} />
      {offsets.map((o, i) => (
        <text key={o} x={x(i)} y={height - 4} fontSize={9} fill="#718096" textAnchor="middle">
          {o === 0 ? 'event' : o > 0 ? `+${o}` : o}
        </text>
      ))}
      {[lo, 0, hi].filter((v, i, arr) => arr.indexOf(v) === i).map((v) => (
        <text key={v} x={padL - 4} y={y(v) + 3} fontSize={9} fill="#718096" textAnchor="end">{v.toFixed(2)}%</text>
      ))}
    </svg>
  );
}

/**
 * Behaviour of an instrument around every past occurrence of a macro catalyst,
 * computed over five years of actual release / FOMC dates. The comparison
 * that matters is event-day |move| vs a normal day — a big number there means
 * the release genuinely moves the instrument; a ratio near 1 means it doesn't.
 */
export default function EventStudyPanel() {
  const [catalog, setCatalog] = useState(null);
  const [event, setEvent] = useState('CPI');
  const [target, setTarget] = useState('17_es_futures');
  const [window_, setWindow] = useState(3);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchEventCatalog()
      .then((d) => setCatalog(d))
      .catch((e) => setError(e.response?.data?.detail || e.message));
  }, []);

  const run = async (ev = event, tg = target, w = window_) => {
    setLoading(true); setError(null);
    try { setResult(await fetchEventStudy({ event: ev, target: tg, window: w })); }
    catch (e) { setError(e.response?.data?.detail || e.message); setResult(null); }
    finally { setLoading(false); }
  };

  useEffect(() => { if (catalog && !result) run(); // initial
    // eslint-disable-next-line
  }, [catalog]);

  const ed = result?.event_day;
  const ratio = ed?.abs_move_ratio;

  return (
    <div className="fwd-panel">
      {error && <div className="error-note">{error}</div>}
      {catalog && (
        <div className="ev-controls">
          <span>Around</span>
          <select value={event} onChange={(e) => { setEvent(e.target.value); run(e.target.value, target, window_); }}>
            {catalog.events.map((ev) => (
              <option key={ev} value={ev}>{ev} ({catalog.counts?.[ev] ?? '?'})</option>
            ))}
          </select>
          <span>what does</span>
          <select value={target} onChange={(e) => { setTarget(e.target.value); run(event, e.target.value, window_); }}>
            {TARGETS.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
          </select>
          <span>do, ±</span>
          {WINDOWS.map((w) => (
            <button key={w} className={`interval-btn ${window_ === w ? 'active' : ''}`}
              onClick={() => { setWindow(w); run(event, target, w); }}>{w}d</button>
          ))}
          {loading && <span className="drawer-hint">Computing…</span>}
          <span className="metric-caption" style={{ marginLeft: 'auto' }}>
            actual dates since {catalog.since?.slice(0, 7)}
          </span>
        </div>
      )}

      {result && !error && (
        <>
          <div className="ev-stats">
            <div className="ev-stat">
              <div className="ev-stat-label">Events</div>
              <div className="ev-stat-value">{result.n_events}</div>
              <div className="ev-stat-sub">{result.first_event} → {result.last_event}</div>
            </div>
            <div className="ev-stat">
              <div className="ev-stat-label">Event-day |move| vs normal day</div>
              <div className={`ev-stat-value ${ratio >= 1.5 ? 'ev-ratio-hot' : ''}`}>
                {ratio ? `${ratio.toFixed(2)}×` : '—'}
              </div>
              <div className="ev-stat-sub">{pct(ed.mean_abs_pct)} vs {pct(ed.baseline_mean_abs_pct)} typical</div>
            </div>
            <div className="ev-stat">
              <div className="ev-stat-label">Event-day mean · hit rate</div>
              <div className={`ev-stat-value ${ed.mean_pct > 0 ? 'pos' : ed.mean_pct < 0 ? 'neg' : ''}`}>{pct(ed.mean_pct)}</div>
              <div className="ev-stat-sub">up {ed.hit_rate_pct?.toFixed(0)}% of events · median {pct(ed.median_pct)}</div>
            </div>
            <div className="ev-stat">
              <div className="ev-stat-label">By t = +{result.window}</div>
              <div className={`ev-stat-value ${result.window_end.mean_pct > 0 ? 'pos' : 'neg'}`}>{pct(result.window_end.mean_pct)}</div>
              <div className="ev-stat-sub">up {result.window_end.hit_rate_pct?.toFixed(0)}% of events</div>
            </div>
          </div>

          <div className="ev-chart-wrap">
            <PathChart offsets={result.offsets} mean={result.mean_path_pct} median={result.median_path_pct} />
            <div className="ev-legend">
              <span className="mean">mean cumulative % from t=−{result.window}</span>
              <span className="median">median</span>
              <span style={{ color: '#c53030' }}>| event day</span>
            </div>
          </div>

          <details className="chart-expander" style={{ marginTop: 8 }}>
            <summary style={{ cursor: 'pointer', fontSize: '0.8rem' }}>Most recent {result.recent_events.length} events</summary>
            <table className="monitor-table" style={{ marginTop: 4 }}>
              <thead>
                <tr><th>Event date</th><th>Trading day</th><th style={{ textAlign: 'right' }}>Event-day</th><th style={{ textAlign: 'right' }}>−{result.window}…+{result.window}</th></tr>
              </thead>
              <tbody>
                {result.recent_events.map((r) => (
                  <tr key={r.event_date}>
                    <td className="mono">{r.event_date}</td>
                    <td className="mono dim">{r.trading_day}</td>
                    <td className={`mono ${r.event_day_pct > 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>{pct(r.event_day_pct)}</td>
                    <td className={`mono ${r.window_pct > 0 ? 'pos' : 'neg'}`} style={{ textAlign: 'right' }}>{pct(r.window_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>

          {(result.caveats || []).map((c, i) => <div key={i} className="metric-caption fwd-caveat">⚠ {c}</div>)}
        </>
      )}
    </div>
  );
}
