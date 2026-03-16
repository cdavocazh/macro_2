import React from 'react';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';
import HistoryChart from '../components/HistoryChart';

function fmt(v, decimals = 2) {
  if (v === null || v === undefined || v === 'N/A') return 'N/A';
  return typeof v === 'number' ? v.toFixed(decimals) : String(v);
}

export default function Tab1Valuation({ indicators }) {
  if (!indicators) return null;

  const fwdPE = indicators['1_sp500_forward_pe'] || {};
  const fundamentals = indicators['3_sp500_fundamentals'] || {};
  const cape = indicators['7_shiller_cape'] || {};
  const mcapGdp = indicators['6b_marketcap_to_gdp'] || {};
  const multiples = indicators['65_sp500_multiples'] || {};
  const sectorPE = indicators['74_sector_pe'] || {};
  const erp = indicators['82_erp'] || {};

  return (
    <div>
      <SectionHeader title="Valuation Metrics" />

      {/* Forward P/E and Trailing P/E & P/B */}
      <div className="grid-4">
        {fwdPE.error ? (
          <ErrorCard title="S&P 500 Forward P/E" error={fwdPE.error} note={fwdPE.note} />
        ) : (
          <MetricCard label="Forward P/E Ratio" value={fwdPE.sp500_forward_pe} />
        )}

        {fundamentals.error ? (
          <ErrorCard title="S&P 500 Trailing P/E & P/B" error={fundamentals.error} />
        ) : (
          <>
            <MetricCard label="Trailing P/E" value={fundamentals.sp500_pe_trailing} />
            <MetricCard label="P/B Ratio" value={fundamentals.sp500_pb} />
          </>
        )}
      </div>

      {/* Shiller CAPE */}
      <SectionHeader title="Shiller CAPE Ratio" sub />
      {cape.error ? (
        <ErrorCard error={cape.error} />
      ) : (
        <div className="grid-3">
          <MetricCard
            label="CAPE Ratio"
            value={cape.shiller_cape}
            caption={`As of: ${cape.latest_date || 'N/A'}`}
          />
          <div>
            {cape.interpretation && (
              <div className="info-box">
                <strong>Interpretation:</strong>
                <ul style={{ marginTop: 4, paddingLeft: 16 }}>
                  {Object.entries(cape.interpretation).map(([k, v]) => (
                    <li key={k}>{k}: {v}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div>
            <HistoryChart data={cape.historical} label="Shiller CAPE" color="#8e24aa" />
          </div>
        </div>
      )}

      {/* Market Cap / GDP */}
      <SectionHeader title="Market Cap / GDP (Buffett Indicator)" sub />
      {mcapGdp.error ? (
        <ErrorCard error={mcapGdp.error} note={mcapGdp.note} />
      ) : (
        <div className="grid-2">
          <MetricCard
            label="Market Cap / GDP (%)"
            value={mcapGdp.marketcap_to_gdp_ratio}
            suffix="%"
          />
          {mcapGdp.interpretation && (
            <div className="info-box">{mcapGdp.interpretation}</div>
          )}
        </div>
      )}

      {/* S&P 500 Multiples (OpenBB/Finviz) */}
      <SectionHeader title="S&P 500 Valuation Multiples" sub />
      {multiples.error ? (
        <ErrorCard error={multiples.error} />
      ) : (
        <>
          <div className="grid-4">
            <MetricCard label="Forward P/E" value={multiples.forward_pe} />
            <MetricCard label="PEG Ratio" value={multiples.peg_ratio} />
            <MetricCard label="Price/Sales" value={multiples.price_to_sales} />
            <MetricCard label="Price/Cash" value={multiples.price_to_cash} />
          </div>
          <div className="metric-caption">Source: {multiples.source || 'N/A'}</div>
        </>
      )}

      {/* Sector P/E and ERP side by side */}
      <div className="grid-2" style={{ marginTop: 12 }}>
        <div>
          <SectionHeader title="Sector P/E Ratios" sub />
          {sectorPE.error ? (
            <ErrorCard error={sectorPE.error} />
          ) : (
            sectorPE.sectors && (
              <table className="sector-table">
                <thead>
                  <tr><th>Sector</th><th>P/E</th></tr>
                </thead>
                <tbody>
                  {Object.entries(sectorPE.sectors)
                    .sort(([, a], [, b]) => (b || 0) - (a || 0))
                    .map(([sector, pe]) => (
                      <tr key={sector}>
                        <td>{sector}</td>
                        <td>{fmt(pe)}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            )
          )}
        </div>

        <div>
          <SectionHeader title="Equity Risk Premium" sub />
          {erp.error ? (
            <ErrorCard error={erp.error} />
          ) : (
            <div className="grid-2">
              <MetricCard
                label="ERP (Trailing)"
                value={erp.equity_risk_premium}
                suffix="%"
                caption={`Earnings Yield: ${fmt(erp.earnings_yield)}%`}
              />
              <MetricCard
                label="ERP (Forward)"
                value={erp.forward_erp}
                suffix="%"
                caption={`10Y Real Yield: ${fmt(erp.real_yield_10y)}%`}
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
