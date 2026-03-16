import React from 'react';
import Plot from 'react-plotly.js';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';
import HistoryChart from '../components/HistoryChart';

function fmt(v, d = 2) {
  if (v == null || v === 'N/A') return 'N/A';
  return typeof v === 'number' ? v.toFixed(d) : String(v);
}

function CommodityCard({ data, label, unit, color }) {
  if (!data) return null;
  if (data.error) return <ErrorCard title={label} error={data.error} note={data.note} />;

  return (
    <div>
      <MetricCard
        label={`${label} (${unit})`}
        value={data.price}
        delta={data.change_1d}
        deltaLabel="%"
        caption={`As of: ${data.latest_date || 'N/A'}${data.note ? ' | ' + data.note : ''}`}
      />
      <HistoryChart data={data.historical} label={`${label} (${unit})`} color={color} />
    </div>
  );
}

export default function Tab5Commodities({ indicators }) {
  if (!indicators) return null;

  const gold = indicators['13_gold'] || {};
  const silver = indicators['14_silver'] || {};
  const oil = indicators['15_crude_oil'] || {};
  const copper = indicators['16_copper'] || {};
  const natGas = indicators['56_natural_gas'] || {};
  const cuAu = indicators['57_cu_au_ratio'] || {};
  const cot = indicators['22_cot_positioning'] || {};

  const goldCot = cot.gold || {};
  const silverCot = cot.silver || {};

  return (
    <div>
      <SectionHeader title="Commodities Futures" />

      <div className="grid-2">
        <CommodityCard data={gold} label="Gold (GC)" unit="USD/oz" color="#FFD700" />
        <CommodityCard data={silver} label="Silver (SI)" unit="USD/oz" color="#C0C0C0" />
      </div>

      <div className="grid-2">
        <CommodityCard data={oil} label="Crude Oil (CL)" unit="USD/bbl" color="#2c2c2c" />
        <CommodityCard data={copper} label="Copper (HG)" unit="USD/lb" color="#B87333" />
      </div>

      <div className="grid-2">
        <CommodityCard data={natGas} label="Natural Gas (NG)" unit="USD/MMBtu" color="#4a148c" />

        {/* Cu/Au Ratio */}
        {cuAu.error ? (
          <ErrorCard title="Cu/Au Ratio" error={cuAu.error} />
        ) : (
          <div>
            <MetricCard
              label="Cu/Au Ratio (x1000)"
              value={cuAu.cu_au_ratio}
              delta={cuAu.change_1d}
              deltaLabel="%"
              caption={`As of: ${cuAu.latest_date || 'N/A'}${cuAu.interpretation ? ' | ' + cuAu.interpretation : ''}`}
            />
            <HistoryChart data={cuAu.historical} label="Cu/Au Ratio x1000" color="#ef6c00" />
          </div>
        )}
      </div>

      {/* CFTC COT Positioning */}
      <SectionHeader title="CFTC Commitment of Traders - Gold & Silver" />
      <div className="metric-caption" style={{ marginBottom: 8 }}>
        Weekly positioning data from CFTC. Managed money = hedge funds. Commercial = producers/hedgers.
      </div>

      {cot.error ? (
        <ErrorCard error={cot.error} note={cot.suggestion} />
      ) : (
        <>
          <div className="metric-caption">As of: {cot.latest_date || 'N/A'}</div>

          <div className="grid-2">
            {/* Gold COT */}
            <div>
              <SectionHeader title="Gold (GC) Positioning" sub />
              {goldCot.error ? (
                <ErrorCard error={goldCot.error} />
              ) : (
                <div className="grid-2">
                  <MetricCard
                    label="Open Interest"
                    value={typeof goldCot.open_interest === 'number' ? goldCot.open_interest.toLocaleString() : 'N/A'}
                  />
                  {goldCot.managed_money_net != null ? (
                    <>
                      <MetricCard label="Managed Money Net" value={goldCot.managed_money_net?.toLocaleString()} />
                      {goldCot.mm_long_ratio != null && (
                        <MetricCard label="MM Long Ratio" value={`${(goldCot.mm_long_ratio * 100).toFixed(1)}%`} />
                      )}
                    </>
                  ) : goldCot.noncommercial_net != null ? (
                    <MetricCard label="Speculator Net" value={goldCot.noncommercial_net?.toLocaleString()} />
                  ) : null}
                  {goldCot.commercial_net != null && (
                    <MetricCard label="Commercial Net" value={goldCot.commercial_net?.toLocaleString()} />
                  )}
                  {goldCot.oi_change != null && (
                    <MetricCard
                      label="OI Change (1w)"
                      value={goldCot.oi_change?.toLocaleString()}
                      delta={goldCot.oi_change_pct}
                      deltaLabel="%"
                    />
                  )}
                </div>
              )}
            </div>

            {/* Silver COT */}
            <div>
              <SectionHeader title="Silver (SI) Positioning" sub />
              {silverCot.error ? (
                <ErrorCard error={silverCot.error} />
              ) : (
                <div className="grid-2">
                  <MetricCard
                    label="Open Interest"
                    value={typeof silverCot.open_interest === 'number' ? silverCot.open_interest.toLocaleString() : 'N/A'}
                  />
                  {silverCot.managed_money_net != null ? (
                    <>
                      <MetricCard label="Managed Money Net" value={silverCot.managed_money_net?.toLocaleString()} />
                      {silverCot.mm_long_ratio != null && (
                        <MetricCard label="MM Long Ratio" value={`${(silverCot.mm_long_ratio * 100).toFixed(1)}%`} />
                      )}
                    </>
                  ) : silverCot.noncommercial_net != null ? (
                    <MetricCard label="Speculator Net" value={silverCot.noncommercial_net?.toLocaleString()} />
                  ) : null}
                  {silverCot.commercial_net != null && (
                    <MetricCard label="Commercial Net" value={silverCot.commercial_net?.toLocaleString()} />
                  )}
                  {silverCot.oi_change != null && (
                    <MetricCard
                      label="OI Change (1w)"
                      value={silverCot.oi_change?.toLocaleString()}
                      delta={silverCot.oi_change_pct}
                      deltaLabel="%"
                    />
                  )}
                </div>
              )}
            </div>
          </div>

          {/* COT Historical Chart */}
          {(goldCot.historical || silverCot.historical) && (
            <details className="chart-expander">
              <summary>COT Positioning Chart</summary>
              <div className="full-chart">
                <Plot
                  data={[
                    ...(goldCot.historical?.index ? [{
                      x: goldCot.historical.index,
                      y: goldCot.historical.values,
                      type: 'scatter', mode: 'lines',
                      name: `Gold ${goldCot.historical_label || 'Net Positioning'}`,
                      line: { color: 'gold' },
                    }] : []),
                    ...(silverCot.historical?.index ? [{
                      x: silverCot.historical.index,
                      y: silverCot.historical.values,
                      type: 'scatter', mode: 'lines',
                      name: `Silver ${silverCot.historical_label || 'Net Positioning'}`,
                      line: { color: 'silver' },
                    }] : []),
                  ]}
                  layout={{
                    title: `CFTC COT: ${goldCot.historical_label || 'Net Positioning'} (Gold vs Silver)`,
                    hovermode: 'x unified',
                    height: 400,
                    margin: { l: 50, r: 20, t: 40, b: 30 },
                    xaxis: { title: 'Date' },
                    yaxis: { title: 'Contracts' },
                  }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              </div>
            </details>
          )}
        </>
      )}
    </div>
  );
}
