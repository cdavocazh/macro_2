import React from 'react';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';
import HistoryChart from '../components/HistoryChart';

function fmt(v, d = 2) {
  if (v == null || v === 'N/A') return 'N/A';
  return typeof v === 'number' ? v.toFixed(d) : String(v);
}

export default function Tab2MarketIndices({ indicators }) {
  if (!indicators) return null;

  const es = indicators['17_es_futures'] || {};
  const rty = indicators['18_rty_futures'] || {};
  const breadth = indicators['19_sp500_breadth'] || {};
  const r2k = indicators['2_russell_2000'] || {};
  const ma200 = indicators['6a_sp500_to_ma200'] || {};
  const conc = indicators['55_market_concentration'] || {};
  const ff = indicators['69_fama_french'] || {};
  const earn = indicators['73_earnings_calendar'] || {};

  const r2kValue = r2k.russell_2000_value || {};
  const r2kGrowth = r2k.russell_2000_growth || {};

  return (
    <div>
      <SectionHeader title="Market Indices" />

      {/* Futures */}
      <SectionHeader title="Futures Indices" sub />
      <div className="grid-2">
        {es.error ? (
          <ErrorCard title="ES Futures" error={es.error} />
        ) : (
          <MetricCard
            label="ES - S&P 500 E-mini"
            value={es.price}
            delta={es.change_1d}
            deltaLabel="%"
            caption={`As of: ${es.latest_date || 'N/A'}`}
          />
        )}
        {rty.error ? (
          <ErrorCard title="RTY Futures" error={rty.error} />
        ) : (
          <MetricCard
            label="RTY - Russell 2000 E-mini"
            value={rty.price}
            delta={rty.change_1d}
            deltaLabel="%"
            caption={`As of: ${rty.latest_date || 'N/A'}`}
          />
        )}
      </div>

      {/* Breadth */}
      <SectionHeader title="S&P 500 Market Breadth" sub />
      {breadth.error ? (
        <ErrorCard error={breadth.error} />
      ) : (
        <>
          <div className="grid-4">
            <MetricCard label="Advancing" value={breadth.advancing_stocks} />
            <MetricCard label="Declining" value={breadth.declining_stocks} />
            <MetricCard label="Net Advances" value={breadth.net_advances} />
            <MetricCard label="Breadth %" value={breadth.breadth_percentage} suffix="%" />
          </div>
          {breadth.interpretation && (
            <div className={`badge ${breadth.interpretation?.includes('bullish') ? 'badge-success' : 'badge-danger'}`} style={{ marginTop: 6 }}>
              {breadth.interpretation}
            </div>
          )}
        </>
      )}

      {/* Russell 2000 V vs G */}
      <SectionHeader title="Russell 2000 Value vs Growth" sub />
      {r2k.error ? (
        <ErrorCard error={r2k.error} />
      ) : (
        <div className="grid-3">
          <MetricCard
            label="Russell 2000 Value"
            value={r2kValue.latest_price}
            delta={r2kValue.change_1d}
            deltaLabel="%"
          />
          <MetricCard
            label="Russell 2000 Growth"
            value={r2kGrowth.latest_price}
            delta={r2kGrowth.change_1d}
            deltaLabel="%"
          />
          <MetricCard label="Value/Growth Ratio" value={r2k.value_growth_ratio} />
        </div>
      )}

      {/* S&P 500 / 200MA */}
      <SectionHeader title="S&P 500 / 200-Day Moving Average" sub />
      {ma200.error ? (
        <ErrorCard error={ma200.error} />
      ) : (
        <div className="grid-3">
          <MetricCard label="S&P 500 Price" value={ma200.sp500_price} />
          <MetricCard label="200-Day MA" value={ma200.sp500_ma200} />
          <MetricCard
            label="Price / MA200"
            value={ma200.sp500_to_ma200_ratio}
            caption={
              typeof ma200.sp500_to_ma200_ratio === 'number'
                ? ma200.sp500_to_ma200_ratio > 1.1
                  ? 'Overbought territory'
                  : ma200.sp500_to_ma200_ratio < 0.9
                    ? 'Oversold territory'
                    : 'Normal range'
                : undefined
            }
          />
        </div>
      )}

      {/* Market Concentration */}
      <SectionHeader title="Market Concentration (SPY/RSP)" sub />
      {conc.error ? (
        <ErrorCard error={conc.error} />
      ) : (
        <>
          <div className="grid-3">
            <MetricCard
              label="SPY/RSP Ratio"
              value={conc.spy_rsp_ratio}
              delta={conc.change_1d}
              deltaLabel="%"
            />
            <MetricCard label="30-Day Change" value={conc.change_30d} suffix="%" />
            {conc.interpretation && (
              <div className="info-box" style={{ alignSelf: 'center' }}>{conc.interpretation}</div>
            )}
          </div>
          <HistoryChart data={conc.historical} label="SPY/RSP Ratio" color="#7b1fa2" />
        </>
      )}

      {/* Fama-French */}
      <SectionHeader title="Fama-French 5-Factor Returns" sub />
      {ff.error ? (
        <ErrorCard error={ff.error} />
      ) : (
        <>
          <div className="grid-5">
            <MetricCard label="Mkt-RF" value={ff.mkt_rf} suffix="%" />
            <MetricCard label="SMB" value={ff.smb} suffix="%" />
            <MetricCard label="HML" value={ff.hml} suffix="%" />
            <MetricCard label="RMW" value={ff.rmw} suffix="%" />
            <MetricCard label="CMA" value={ff.cma} suffix="%" />
          </div>
          <div className="metric-caption">Monthly factor returns | RF: {fmt(ff.rf)}% | Source: {ff.source || 'N/A'}</div>
        </>
      )}

      {/* Earnings Calendar */}
      <SectionHeader title="Upcoming Earnings Calendar" sub />
      {earn.error ? (
        <ErrorCard error={earn.error} />
      ) : (
        <>
          {earn.earnings && earn.earnings.length > 0 ? (
            <table className="data-table">
              <thead>
                <tr>
                  {Object.keys(earn.earnings[0] || {}).map(col => (
                    <th key={col}>{col}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {earn.earnings.map((row, i) => (
                  <tr key={i}>
                    {Object.values(row).map((v, j) => (
                      <td key={j}>{v != null ? String(v) : '-'}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="info-box">No upcoming earnings in the next 7 days.</div>
          )}
          <div className="metric-caption">Period: {earn.period || 'N/A'} | Source: {earn.source || 'N/A'}</div>
        </>
      )}
    </div>
  );
}
