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

export default function Tab8EconomicActivity({ indicators }) {
  if (!indicators) return null;

  const nfp = indicators['42_nfp'] || {};
  const jolts = indicators['48_jolts'] || {};
  const quits = indicators['60_quits_rate'] || {};
  const sahm = indicators['46_sahm_rule'] || {};
  const sentiment = indicators['44_consumer_sentiment'] || {};
  const retail = indicators['50_retail_sales'] || {};
  const ismSvc = indicators['43_ism_services'] || {};
  const indProd = indicators['59_industrial_production'] || {};
  const housing = indicators['51_housing_starts'] || {};
  const cli = indicators['67_oecd_cli'] || {};
  const intlUnemp = indicators['77_intl_unemployment'] || {};
  const intlGdp = indicators['78_intl_gdp'] || {};
  const pmi = indicators['81_global_pmi'] || {};

  return (
    <div>
      <SectionHeader title="Economic Activity" />

      {/* Employment & Recession Risk */}
      <SectionHeader title="Employment & Recession Risk" sub />
      <div className="grid-4">
        {nfp.error ? <ErrorCard title="NFP" error={nfp.error} /> : (
          <div>
            <MetricCard
              label="Nonfarm Payrolls (K)"
              value={nfp.nfp_thousands}
              delta={nfp.nfp_change_mom}
              deltaLabel="K MoM"
              caption={`As of: ${nfp.latest_date || 'N/A'}${nfp.interpretation ? ' | ' + nfp.interpretation : ''}`}
            />
            <HistoryChart data={nfp.historical} label="Nonfarm Payrolls (K)" color="#1565c0" />
          </div>
        )}

        {jolts.error ? <ErrorCard title="JOLTS" error={jolts.error} /> : (
          <div>
            <MetricCard
              label="JOLTS Openings (M)"
              value={jolts.jolts_openings_m}
              delta={jolts.change_mom_pct}
              deltaLabel="% MoM"
              caption={`As of: ${jolts.latest_date || 'N/A'}${jolts.interpretation ? ' | ' + jolts.interpretation : ''}`}
            />
            <HistoryChart data={jolts.historical} label="JOLTS Openings (M)" color="#0d47a1" />
          </div>
        )}

        {quits.error ? <ErrorCard title="Quits Rate" error={quits.error} /> : (
          <div>
            <MetricCard
              label="Quits Rate (%)"
              value={quits.quits_rate}
              suffix="%"
              delta={quits.change_mom}
              deltaLabel=" MoM"
              caption={`As of: ${quits.latest_date || 'N/A'}${quits.interpretation ? ' | ' + quits.interpretation : ''}`}
            />
            <HistoryChart data={quits.historical} label="Quits Rate (%)" color="#1a237e" suffix="%" />
          </div>
        )}

        {sahm.error ? <ErrorCard title="Sahm Rule" error={sahm.error} /> : (
          <div>
            <MetricCard
              label="Sahm Rule"
              value={sahm.sahm_value}
              delta={sahm.change_mom}
              deltaLabel=" MoM"
              caption={`As of: ${sahm.latest_date || 'N/A'}`}
            />
            {sahm.triggered ? (
              <div className="badge badge-danger" style={{ marginTop: 4 }}>RECESSION SIGNAL TRIGGERED (&ge; 0.50)</div>
            ) : (
              <div className="badge badge-success" style={{ marginTop: 4 }}>Below threshold (&lt; 0.50)</div>
            )}
            {/* Sahm chart with threshold */}
            {sahm.historical?.index && (
              <details className="chart-expander">
                <summary>Sahm Rule History</summary>
                <div className="full-chart">
                  <Plot
                    data={[{
                      x: sahm.historical.index,
                      y: sahm.historical.values,
                      type: 'scatter', mode: 'lines',
                      name: 'Sahm Rule',
                      line: { color: '#c62828', width: 1.5 },
                      fill: 'tozeroy',
                      fillcolor: 'rgba(198,40,40,0.08)',
                    }]}
                    layout={{
                      yaxis: { title: 'Sahm Rule (pp)' },
                      hovermode: 'x unified',
                      height: 280,
                      margin: { l: 50, r: 20, t: 10, b: 30 },
                      showlegend: false,
                      shapes: [{
                        type: 'line', y0: 0.5, y1: 0.5,
                        x0: 0, x1: 1, xref: 'paper',
                        line: { color: 'red', width: 1.5, dash: 'dash' },
                      }],
                      annotations: [{
                        x: 0.02, y: 0.52, xref: 'paper', yref: 'y',
                        text: 'Recession threshold (0.50)',
                        showarrow: false,
                        font: { color: 'red', size: 10 },
                      }],
                    }}
                    config={{ responsive: true, displayModeBar: false }}
                    style={{ width: '100%' }}
                  />
                </div>
              </details>
            )}
          </div>
        )}
      </div>

      {/* Consumer */}
      <SectionHeader title="Consumer" sub />
      <div className="grid-2">
        {sentiment.error ? <ErrorCard title="Consumer Sentiment" error={sentiment.error} /> : (
          <div>
            <MetricCard
              label="UMich Consumer Sentiment"
              value={sentiment.consumer_sentiment}
              delta={sentiment.change_mom}
              deltaLabel=" MoM"
              caption={`As of: ${sentiment.latest_date || 'N/A'}${sentiment.interpretation ? ' | ' + sentiment.interpretation : ''}`}
            />
            <HistoryChart data={sentiment.historical} label="Consumer Sentiment" color="#00695c" />
          </div>
        )}

        {retail.error ? <ErrorCard title="Retail Sales" error={retail.error} /> : (
          <div>
            <MetricCard
              label="Retail Sales ($B)"
              value={retail.retail_sales_b}
              delta={retail.retail_sales_mom_pct}
              deltaLabel="% MoM"
              caption={`As of: ${retail.latest_date || 'N/A'}${retail.interpretation ? ' | ' + retail.interpretation : ''}`}
            />
            <HistoryChart data={retail.historical} label="Retail Sales MoM%" color="#2e7d32" suffix="%" />
          </div>
        )}
      </div>

      {/* Production & Housing */}
      <SectionHeader title="Production & Housing" sub />
      <div className="grid-3">
        {ismSvc.error ? <ErrorCard title="ISM Services" error={ismSvc.error} /> : (
          <MetricCard
            label="ISM Services PMI"
            value={ismSvc.ism_services_pmi}
            delta={ismSvc.change_1d}
            caption={`As of: ${ismSvc.latest_date || 'N/A'}${ismSvc.interpretation ? ' | ' + ismSvc.interpretation : ''}`}
          />
        )}

        {indProd.error ? <ErrorCard title="Industrial Production" error={indProd.error} /> : (
          <div>
            <MetricCard
              label="Industrial Production"
              value={indProd.indpro_index}
              delta={indProd.indpro_yoy_pct}
              deltaLabel="% YoY"
              caption={`As of: ${indProd.latest_date || 'N/A'}${indProd.interpretation ? ' | ' + indProd.interpretation : ''}`}
            />
            <HistoryChart data={indProd.historical} label="Industrial Production (Index)" color="#4a148c" />
          </div>
        )}

        {housing.error ? <ErrorCard title="Housing Starts" error={housing.error} /> : (
          <div>
            <MetricCard
              label="Housing Starts (K, ann.)"
              value={housing.housing_starts_k}
              delta={housing.change_mom_pct}
              deltaLabel="% MoM"
              caption={`As of: ${housing.latest_date || 'N/A'}${housing.interpretation ? ' | ' + housing.interpretation : ''}`}
            />
            <HistoryChart data={housing.historical} label="Housing Starts (K)" color="#bf360c" />
          </div>
        )}
      </div>

      {/* OECD CLI */}
      <SectionHeader title="OECD Composite Leading Indicator" sub />
      {cli.error ? <ErrorCard error={cli.error} /> : (
        <>
          <div className="grid-2">
            <MetricCard
              label="US CLI"
              value={cli.cli_value}
              caption={cli.above_100 ? 'Above 100 = expansion' : 'Below 100 = contraction'}
            />
            <div className="metric-caption" style={{ alignSelf: 'center' }}>
              As of: {cli.latest_date || 'N/A'} | OECD CLI leads GDP by 6-9 months.
            </div>
          </div>
          <HistoryChart data={cli.historical} label="OECD CLI" color="#2e7d32" />
        </>
      )}

      {/* International Unemployment & GDP */}
      <div className="grid-2">
        <div>
          <SectionHeader title="International Unemployment" sub />
          {intlUnemp.error ? <ErrorCard error={intlUnemp.error} /> : (
            <>
              <div className="grid-4">
                <MetricCard label="US" value={intlUnemp.us_unemployment} suffix="%" />
                <MetricCard label="Eurozone" value={intlUnemp.eu_unemployment} suffix="%" />
                <MetricCard label="Japan" value={intlUnemp.jp_unemployment} suffix="%" />
                <MetricCard label="UK" value={intlUnemp.uk_unemployment} suffix="%" />
              </div>
              <div className="metric-caption">Source: {intlUnemp.source || 'N/A'}</div>
            </>
          )}
        </div>

        <div>
          <SectionHeader title="International GDP Growth" sub />
          {intlGdp.error ? <ErrorCard error={intlGdp.error} /> : (
            <>
              <div className="grid-4">
                <MetricCard label="US" value={intlGdp.us_gdp_growth} suffix="%" />
                <MetricCard label="EU" value={intlGdp.eu_gdp_growth} suffix="%" />
                <MetricCard label="Japan" value={intlGdp.jp_gdp_growth} suffix="%" />
                <MetricCard label="China" value={intlGdp.cn_gdp_growth} suffix="%" />
              </div>
              <div className="metric-caption">Source: {intlGdp.source || 'N/A'}</div>
              <HistoryChart data={intlGdp.historical} label="US Real GDP Growth" color="#1565c0" suffix="%" />
            </>
          )}
        </div>
      </div>

      {/* Global PMI */}
      <SectionHeader title="Global Manufacturing PMI" sub />
      {pmi.error ? <ErrorCard error={pmi.error} /> : (
        <>
          <div className="grid-5">
            <MetricCard label="US" value={pmi.us_mfg_pmi} />
            <MetricCard label="EU" value={pmi.eu_mfg_pmi} />
            <MetricCard label="Japan" value={pmi.jp_mfg_pmi} />
            <MetricCard label="China" value={pmi.cn_mfg_pmi} />
            <MetricCard label="UK" value={pmi.uk_mfg_pmi} />
          </div>
          <div className="metric-caption">50 = expansion/contraction threshold | Source: {pmi.source || 'N/A'}</div>
          <HistoryChart data={pmi.historical} label="US Manufacturing PMI" color="#e65100" />
        </>
      )}
    </div>
  );
}
