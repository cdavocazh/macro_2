import React, { useEffect, useState } from 'react';
import { fetchPositioning13F } from '../api';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';
import { toGMT8 } from '../utils/time';

const fmt = (v, d = 2) => (v === null || v === undefined || v === 'N/A' ? 'N/A'
  : typeof v === 'number' ? v.toFixed(d) : String(v));
const usdM = (v) => (v === null || v === undefined ? '—'
  : Math.abs(v) >= 1e9 ? `$${(v / 1e9).toFixed(2)}B` : `$${(v / 1e6).toFixed(0)}M`);

/** COT block for one commodity — managed-money net is the speculative read. */
function CotBlock({ data, label }) {
  if (!data || typeof data !== 'object') return null;
  const net = data.managed_money_net ?? data.mm_net;
  const long = data.managed_money_long ?? data.mm_long;
  const short = data.managed_money_short ?? data.mm_short;
  const ratio = data.long_ratio;
  return (
    <div className="pos-cot">
      <div className="pos-cot-head">{label}</div>
      <div className="grid-4">
        <MetricCard label="MM Net" value={net != null ? Number(net).toLocaleString() : 'N/A'} />
        <MetricCard label="MM Long" value={long != null ? Number(long).toLocaleString() : 'N/A'} />
        <MetricCard label="MM Short" value={short != null ? Number(short).toLocaleString() : 'N/A'} />
        <MetricCard label="Long Ratio" value={ratio != null ? `${fmt(ratio * (ratio <= 1 ? 100 : 1), 1)}%` : 'N/A'} />
      </div>
    </div>
  );
}

/**
 * Consolidated positioning view. Everything here was already extracted but was
 * scattered across four tabs — COT in Commodities, put/call and SKEW in
 * Volatility, breadth in Indices, and 13F written only to CSV and never shown.
 * Positioning is read as one picture, so it belongs on one screen.
 */
export default function Tab11Positioning({ indicators }) {
  const [f13, setF13] = useState(null);
  const [f13err, setF13err] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchPositioning13F(6)
      .then((d) => {
        if (cancelled) return;
        if (d.error) setF13err(d.error); else setF13(d);
      })
      .catch((e) => !cancelled && setF13err(e.message));
    return () => { cancelled = true; };
  }, []);

  if (!indicators) return null;

  const cot = indicators['22_cot_positioning'] || {};
  const cotEnergy = indicators['83_cot_energy_metals'] || {};
  const putCall = indicators['4_put_call_ratio'] || {};
  const pcoi = indicators['64_spy_put_call_oi'] || {};
  const skew = indicators['5_spx_call_skew'] || {};
  const breadth = indicators['19_sp500_breadth'] || {};
  const screener = indicators['79_equity_screener'] || {};

  return (
    <div>
      <SectionHeader title="Market Breadth & Participation" />
      {breadth.error ? <ErrorCard title="S&P 500 Breadth" error={breadth.error} /> : (
        <div className="grid-4">
          <MetricCard label="Advancing" value={breadth.advancing_stocks ?? 'N/A'} />
          <MetricCard label="Declining" value={breadth.declining_stocks ?? 'N/A'} />
          <MetricCard label="Breadth %" value={breadth.breadth_percentage != null ? `${fmt(breadth.breadth_percentage, 1)}%` : 'N/A'}
            caption={breadth.interpretation} />
          <MetricCard label="Above 200-day MA" value={screener.pct_above_200ma != null ? `${fmt(screener.pct_above_200ma, 1)}%` : 'N/A'}
            caption={screener.note} />
        </div>
      )}

      <SectionHeader title="Options Positioning" />
      <div className="grid-4">
        <MetricCard label="Put/Call Ratio" value={fmt(putCall.sp500_put_call_ratio)} caption={putCall.source} />
        <MetricCard label="SPY P/C Volume" value={fmt(pcoi.put_call_volume_ratio, 3)} />
        <MetricCard label="SPY P/C Open Interest" value={fmt(pcoi.put_call_oi_ratio, 3)} caption={pcoi.source} />
        <MetricCard label="CBOE SKEW" value={fmt(skew.spx_call_skew, 2)}
          caption={skew.latest_date ? `As of: ${toGMT8(skew.latest_date)}` : ''} />
      </div>

      <SectionHeader title="CFTC Commitment of Traders — Metals" />
      {cot.error ? <ErrorCard title="COT" error={cot.error} /> : (
        <>
          <CotBlock data={cot.gold} label="Gold" />
          <CotBlock data={cot.silver} label="Silver" />
        </>
      )}

      <SectionHeader title="CFTC Commitment of Traders — Energy & Industrial" />
      {cotEnergy.error ? <ErrorCard title="COT Energy/Metals" error={cotEnergy.error} /> : (
        <>
          <CotBlock data={cotEnergy.crude_oil} label="Crude Oil (WTI)" />
          <CotBlock data={cotEnergy.brent} label="Brent" />
          <CotBlock data={cotEnergy.copper} label="Copper" />
          <CotBlock data={cotEnergy.natural_gas} label="Natural Gas" />
        </>
      )}

      <SectionHeader title="Institutional Positioning — 13F Filings" />
      {f13err && <div className="error-note">13F unavailable: {f13err}</div>}
      {!f13 && !f13err && <div className="metric-caption">Loading 13F holdings…</div>}
      {f13 && (
        <>
          <div className="metric-caption">
            13F filings are disclosed with a ~45-day lag and only quarterly — treat as
            slow-moving context, never as a current position.
          </div>
          {f13.funds.map((fund) => (
            <details key={fund.fund} className="chart-expander" style={{ marginTop: 6 }}>
              <summary style={{ cursor: 'pointer', fontSize: '0.85rem' }}>
                {fund.fund_label} — {fund.quarter} ({fund.n_positions} positions)
              </summary>
              <div style={{ overflowX: 'auto', marginTop: 4 }}>
                <table className="monitor-table">
                  <thead>
                    <tr>
                      <th>Holding</th><th>Action</th>
                      <th style={{ textAlign: 'right' }}>Shares Δ</th>
                      <th style={{ textAlign: 'right' }}>Value Δ</th>
                      <th style={{ textAlign: 'right' }}>Position value</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fund.moves.map((m, i) => (
                      <tr key={`${fund.fund}-${i}`}>
                        <td>{m.ticker_name}</td>
                        <td className={
                          m.action === 'INCREASED' || m.action === 'NEW' ? 'pos'
                            : m.action === 'DECREASED' || m.action === 'EXITED' ? 'neg' : 'dim'
                        }>{m.action}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>
                          {m.shares_change_pct != null ? `${m.shares_change_pct > 0 ? '+' : ''}${fmt(m.shares_change_pct, 1)}%` : '—'}
                        </td>
                        <td className={`mono ${m.value_change_usd > 0 ? 'pos' : m.value_change_usd < 0 ? 'neg' : 'dim'}`}
                            style={{ textAlign: 'right' }}>
                          {usdM(m.value_change_usd)}
                        </td>
                        <td className="mono" style={{ textAlign: 'right' }}>{usdM(m.current_value_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ))}
        </>
      )}
    </div>
  );
}
