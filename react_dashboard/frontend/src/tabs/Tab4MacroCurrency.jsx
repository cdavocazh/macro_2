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

function SeriesChart({ title, series1, series2, label1, label2, color1, color2, height = 380 }) {
  if (!series1 && !series2) return null;
  const traces = [];
  if (series1 && series1.index) {
    traces.push({
      x: series1.index, y: series1.values,
      type: 'scatter', mode: 'lines',
      name: label1, line: { color: color1, width: 2 },
    });
  }
  if (series2 && series2.index) {
    traces.push({
      x: series2.index, y: series2.values,
      type: 'scatter', mode: 'lines',
      name: label2, line: { color: color2, width: 1.5, dash: 'dash' },
    });
  }
  if (traces.length === 0) return null;
  return (
    <details className="chart-expander">
      <summary>{title}</summary>
      <div className="full-chart">
        <Plot
          data={traces}
          layout={{
            title: { text: title, font: { size: 13 } },
            hovermode: 'x unified',
            height,
            margin: { l: 50, r: 20, t: 40, b: 30 },
            showlegend: traces.length > 1,
            legend: { orientation: 'h', y: 1.1 },
          }}
          config={{ responsive: true, displayModeBar: false }}
          style={{ width: '100%' }}
        />
      </div>
    </details>
  );
}

export default function Tab4MacroCurrency({ indicators }) {
  if (!indicators) return null;

  const dxy = indicators['10_dxy'] || {};
  const jpy = indicators['20_jpy'] || {};
  const fx = indicators['54_fx_pairs'] || {};
  const tga = indicators['23_tga_balance'] || {};
  const netLiq = indicators['24_net_liquidity'] || {};
  const m2 = indicators['47_m2'] || {};
  const sofr = indicators['25_sofr'] || {};
  const us2y = indicators['26_us_2y_yield'] || {};
  const jp2y = indicators['27_japan_2y_yield'] || {};
  const spread = indicators['28_us2y_jp2y_spread'] || {};
  const yield10y = indicators['11_10y_yield'] || {};
  const ismPmi = indicators['12_ism_pmi'] || {};
  const money = indicators['80_money_measures'] || {};

  return (
    <div>
      <SectionHeader title="Macro & Currency" />

      {/* Currency row */}
      <SectionHeader title="Currency Indices" sub />
      <div className="grid-5">
        {dxy.error ? (
          <ErrorCard title="DXY" error={dxy.error} />
        ) : (
          <div>
            <MetricCard label="DXY" value={dxy.dxy} delta={dxy.change_1d} deltaLabel="%" caption={`As of: ${dxy.latest_date || 'N/A'}`} />
            <HistoryChart data={dxy.historical} label="DXY" color="#2e7d32" />
          </div>
        )}

        {jpy.error ? (
          <ErrorCard title="USD/JPY" error={jpy.error} />
        ) : (
          <div>
            <MetricCard label="USD/JPY" value={jpy.jpy_rate} delta={jpy.change_1d} deltaLabel="%" caption={`As of: ${jpy.latest_date || 'N/A'}`} />
            <HistoryChart data={jpy.historical} label="USD/JPY" color="#d84315" />
          </div>
        )}

        {fx.error ? (
          <>
            <ErrorCard title="EUR/USD" error={fx.error} />
            <ErrorCard title="GBP/USD" error={fx.error} />
            <ErrorCard title="EUR/JPY" error={fx.error} />
          </>
        ) : (
          <>
            <div>
              <MetricCard label="EUR/USD" value={fx.eur_usd} delta={fx.eur_usd_change_1d} deltaLabel="%" />
              <HistoryChart data={fx.historical_eur_usd} label="EUR/USD" color="#1565c0" />
            </div>
            <div>
              <MetricCard label="GBP/USD" value={fx.gbp_usd} delta={fx.gbp_usd_change_1d} deltaLabel="%" />
              <HistoryChart data={fx.historical_gbp_usd} label="GBP/USD" color="#1b5e20" />
            </div>
            <div>
              <MetricCard label="EUR/JPY" value={fx.eur_jpy} delta={fx.eur_jpy_change_1d} deltaLabel="%" />
              <HistoryChart data={fx.historical_eur_jpy} label="EUR/JPY" color="#e65100" />
            </div>
          </>
        )}
      </div>

      {/* Liquidity & Rates */}
      <SectionHeader title="Liquidity & Short-Term Rates" sub />
      <div className="grid-2">
        {tga.error ? (
          <ErrorCard title="TGA Balance" error={tga.error} />
        ) : (
          <div>
            <MetricCard
              label="TGA Balance ($B)"
              value={tga.tga_balance_billions}
              delta={tga.change_wow_pct}
              deltaLabel="% WoW"
              caption={`As of: ${tga.latest_date || 'N/A'} | High TGA = Treasury draining liquidity`}
            />
            <HistoryChart data={tga.historical} label="TGA Balance ($M)" color="#6a1b9a" />
          </div>
        )}

        {netLiq.error ? (
          <ErrorCard title="Fed Net Liquidity" error={netLiq.error} />
        ) : (
          <div>
            <MetricCard
              label="Net Liquidity ($T)"
              value={netLiq.net_liquidity_trillions}
              delta={netLiq.change_pct}
              deltaLabel="%"
              caption={`As of: ${netLiq.latest_date || 'N/A'}${netLiq.interpretation ? ' | ' + netLiq.interpretation : ''}`}
            />
            <HistoryChart data={netLiq.historical} label="Net Liquidity ($M)" color="#1565c0" />
          </div>
        )}
      </div>

      {/* M2 */}
      <div className="grid-2">
        {m2.error ? (
          <ErrorCard title="M2" error={m2.error} />
        ) : (
          <div>
            <MetricCard
              label="M2 ($T)"
              value={m2.m2_trillions}
              delta={m2.m2_yoy_growth}
              deltaLabel="% YoY"
              caption={`As of: ${m2.latest_date || 'N/A'}${m2.interpretation ? ' | ' + m2.interpretation : ''}`}
            />
            <HistoryChart data={m2.historical} label="M2 ($T)" color="#00695c" />
          </div>
        )}
        <div /> {/* spacer */}
      </div>

      {/* SOFR, US 2Y */}
      <div className="grid-2">
        {sofr.error ? (
          <ErrorCard title="SOFR" error={sofr.error} />
        ) : (
          <div>
            <MetricCard
              label="SOFR Rate (%)"
              value={sofr.sofr}
              delta={sofr.change_1d}
              deltaLabel=" bps"
              caption={`As of: ${sofr.latest_date || 'N/A'}`}
            />
            <HistoryChart data={sofr.historical} label="SOFR (%)" color="#00838f" suffix="%" />
          </div>
        )}

        {us2y.error ? (
          <ErrorCard title="US 2Y Yield" error={us2y.error} />
        ) : (
          <div>
            <MetricCard
              label="US 2Y Yield (%)"
              value={us2y.us_2y_yield}
              delta={us2y.change_1d}
              caption={`As of: ${us2y.latest_date || 'N/A'}${us2y.spread_2s10s != null ? ` | 2s10s: ${fmt(us2y.spread_2s10s)}%` : ''}`}
            />
            <HistoryChart data={us2y.historical} label="US 2Y Yield (%)" color="#1976d2" suffix="%" />
          </div>
        )}
      </div>

      {/* Japan 2Y & Spread */}
      <div className="grid-2">
        {jp2y.error ? (
          <ErrorCard title="Japan 2Y Yield" error={jp2y.error} />
        ) : (
          <div>
            <MetricCard
              label="JGB 2Y Yield (%)"
              value={jp2y.japan_2y_yield}
              delta={jp2y.change_1d}
              caption={`As of: ${jp2y.latest_date || 'N/A'}${jp2y.japan_10y_yield != null ? ` | JGB 10Y: ${jp2y.japan_10y_yield}%` : ''}`}
            />
            <HistoryChart data={jp2y.historical} label="JGB 2Y Yield (%)" color="#e65100" suffix="%" />
          </div>
        )}

        {spread.error ? (
          <ErrorCard title="US-JP Spread" error={spread.error} />
        ) : (
          <div>
            <MetricCard
              label="US-JP 2Y Yield Spread (%)"
              value={spread.spread}
              caption={`US 2Y: ${spread.us_2y_yield}% | JP 2Y: ${spread.japan_2y_yield}%${spread.interpretation ? ' | ' + spread.interpretation : ''}`}
            />
            <HistoryChart data={spread.historical} label="US-JP 2Y Spread (%)" color="#ff7f0e" suffix="%" />
          </div>
        )}
      </div>

      {/* Net Liquidity Chart */}
      <SeriesChart
        title="Net Liquidity Chart"
        series1={netLiq.historical}
        label1="Net Liquidity"
        color1="#1f77b4"
      />

      {/* US-JP Spread Chart */}
      <SeriesChart
        title="US-JP 2Y Yield Spread Chart"
        series1={spread.historical}
        label1="US 2Y - JP 2Y Spread"
        color1="#ff7f0e"
      />

      {/* 10Y Yield vs ISM PMI */}
      <SectionHeader title="10-Year Treasury Yield vs ISM Manufacturing PMI" sub />
      <div className="grid-3">
        {yield10y.error ? (
          <ErrorCard title="10Y Yield" error={yield10y.error} />
        ) : (
          <div>
            <MetricCard label="10Y Treasury Yield" value={yield10y['10y_yield']} suffix="%" caption={`As of: ${yield10y.latest_date || 'N/A'}`} />
            <HistoryChart data={yield10y.historical} label="10Y Yield (%)" color="#1565c0" suffix="%" />
          </div>
        )}
        {ismPmi.error ? (
          <ErrorCard title="ISM PMI" error={ismPmi.error} />
        ) : (
          <div>
            <MetricCard label="ISM Manufacturing PMI" value={ismPmi.ism_pmi} caption={`As of: ${ismPmi.latest_date || 'N/A'}${ismPmi.note ? ' | ' + ismPmi.note : ''}`} />
            <HistoryChart data={ismPmi.historical} label="ISM PMI" color="#e65100" />
          </div>
        )}
        {!yield10y.error && !ismPmi.error && typeof yield10y['10y_yield'] === 'number' && typeof ismPmi.ism_pmi === 'number' && (
          <MetricCard
            label="10Y Yield - ISM Gap"
            value={(yield10y['10y_yield'] - ismPmi.ism_pmi)}
            caption={yield10y['10y_yield'] - ismPmi.ism_pmi > 0 ? 'Yield > ISM (potential slowdown)' : 'ISM > Yield (economic strength)'}
          />
        )}
      </div>

      {/* Money Supply M1/M2 */}
      <SectionHeader title="Money Supply (M1/M2)" sub />
      {money.error ? (
        <ErrorCard error={money.error} />
      ) : (
        <>
          <div className="grid-4">
            <MetricCard label="M1 Level (B)" value={money.m1_level} />
            <MetricCard label="M1 YoY%" value={money.m1_yoy} suffix="%" />
            <MetricCard label="M2 Level (B)" value={money.m2_level} />
            <MetricCard label="M2 YoY%" value={money.m2_yoy} suffix="%" />
          </div>
          <div className="metric-caption">As of: {money.latest_date || 'N/A'} | Source: {money.source || 'N/A'}</div>
          <HistoryChart data={money.historical} label="M2 Money Supply" color="#1565c0" />
        </>
      )}
    </div>
  );
}
