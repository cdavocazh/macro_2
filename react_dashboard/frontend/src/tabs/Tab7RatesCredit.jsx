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

export default function Tab7RatesCredit({ indicators }) {
  if (!indicators) return null;

  const yc = indicators['33_yield_curve'] || {};
  const us10y = indicators['11_10y_yield'] || {};
  const us5y = indicators['61_5y_yield'] || {};
  const de10y = indicators['30_germany_10y'] || {};
  const uk10y = indicators['31_uk_10y'] || {};
  const cn10y = indicators['32_china_10y'] || {};
  const realYield = indicators['36_real_yield'] || {};
  const breakeven = indicators['35_breakeven_inflation'] || {};
  const hy = indicators['34_hy_oas'] || {};
  const nfci = indicators['37_nfci'] || {};
  const ff = indicators['38_fed_funds'] || {};
  const ig = indicators['45_ig_oas'] || {};
  const reserves = indicators['58_bank_reserves'] || {};
  const sloos = indicators['62_sloos'] || {};
  const unemp = indicators['40_unemployment'] || {};
  const claims = indicators['39_initial_claims'] || {};
  const coreInfl = indicators['41_core_inflation'] || {};
  const cclaims = indicators['49_continuing_claims'] || {};
  const hcpi = indicators['53_headline_cpi'] || {};
  const ppi = indicators['52_ppi'] || {};
  const ecb = indicators['66_ecb_rates'] || {};
  const cpiComp = indicators['68_cpi_components'] || {};
  const euYields = indicators['71_eu_yields'] || {};
  const gCpi = indicators['72_global_cpi'] || {};
  const tCurve = indicators['75_treasury_curve'] || {};
  const corpSpreads = indicators['76_corporate_spreads'] || {};

  return (
    <div>
      <SectionHeader title="Rates & Credit" />

      {/* Yield Curve & Regime */}
      <SectionHeader title="Yield Curve & Regime" sub />
      {yc.error ? (
        <ErrorCard title="Yield Curve" error={yc.error} />
      ) : (
        <>
          <div className="grid-2">
            <div>
              <MetricCard
                label="2s10s Spread"
                value={yc.spread_2s10s}
                suffix="%"
                delta={yc.change_1d}
                caption={`As of: ${yc.latest_date || 'N/A'}`}
              />
              {yc.is_inverted && (
                <div className="badge badge-danger" style={{ marginTop: 4 }}>
                  Yield curve is INVERTED (recession signal)
                </div>
              )}
              <HistoryChart data={yc.historical} label="2s10s Spread (%)" color="#ff7f0e" suffix="%" />
            </div>

            <div
              className="regime-card"
              style={{ background: `${yc.regime_color || '#9e9e9e'}22`, borderLeft: `4px solid ${yc.regime_color || '#9e9e9e'}` }}
            >
              <div className="regime-title">
                {yc.regime_emoji || ''} {yc.regime || 'Neutral'}
              </div>
              <div className="regime-signal" style={{ color: yc.regime_color || '#555' }}>
                {yc.regime_signal || ''}
              </div>
              <div className="regime-detail">{yc.regime_detail || ''}</div>
              <div className="metric-caption" style={{ marginTop: 8 }}>
                {yc.lookback_days || 20}-day changes:
                2Y: {yc.delta_2y >= 0 ? '+' : ''}{fmt(yc.delta_2y)}% |
                10Y: {yc.delta_10y >= 0 ? '+' : ''}{fmt(yc.delta_10y)}% |
                Spread: {yc.delta_spread >= 0 ? '+' : ''}{fmt(yc.delta_spread)}%
              </div>
            </div>
          </div>
        </>
      )}

      {/* Global 10Y Sovereign Yields */}
      <SectionHeader title="Global 10-Year Sovereign Yields" sub />
      <div className="grid-5">
        {us10y.error ? <ErrorCard title="US 10Y" error="Unavailable" /> : (
          <div>
            <MetricCard label="US 10Y" value={us10y['10y_yield']} suffix="%" caption={`As of: ${us10y.latest_date || 'N/A'}`} />
            <HistoryChart data={us10y.historical} label="US 10Y Yield (%)" color="#1565c0" suffix="%" />
          </div>
        )}
        {us5y.error ? <ErrorCard title="US 5Y" error="Unavailable" /> : (
          <div>
            <MetricCard label="US 5Y" value={us5y['5y_yield']} suffix="%" delta={us5y.change_1d} caption={`As of: ${us5y.latest_date || 'N/A'}`} />
            <HistoryChart data={us5y.historical} label="US 5Y Yield (%)" color="#0d47a1" suffix="%" />
          </div>
        )}
        {de10y.error ? <ErrorCard title="Germany 10Y" error={de10y.error} /> : (
          <div>
            <MetricCard label="Germany 10Y" value={de10y.germany_10y_yield} suffix="%" delta={de10y.change_1d} />
            <HistoryChart data={de10y.historical} label="Germany 10Y (%)" color="#d32f2f" suffix="%" />
          </div>
        )}
        {uk10y.error ? <ErrorCard title="UK 10Y" error={uk10y.error} /> : (
          <div>
            <MetricCard label="UK 10Y" value={uk10y.uk_10y_yield} suffix="%" delta={uk10y.change_1d} />
            <HistoryChart data={uk10y.historical} label="UK 10Y (%)" color="#1b5e20" suffix="%" />
          </div>
        )}
        {cn10y.error ? <ErrorCard title="China 10Y" error={cn10y.error} /> : (
          <MetricCard label="China 10Y" value={cn10y.china_10y_yield} suffix="%" delta={cn10y.change_1d} caption={cn10y.note} />
        )}
      </div>

      {/* Real Yields & Inflation Expectations */}
      <SectionHeader title="Real Yields & Inflation Expectations" sub />
      <div className="grid-3">
        {realYield.error ? <ErrorCard title="Real Yield" error={realYield.error} /> : (
          <div>
            <MetricCard label="10Y Real Yield (TIPS)" value={realYield.real_yield_10y} suffix="%" delta={realYield.change_1d}
              caption={`As of: ${realYield.latest_date || 'N/A'}${realYield.interpretation ? ' | ' + realYield.interpretation : ''}`} />
            <HistoryChart data={realYield.historical} label="Real Yield (%)" color="#6a1b9a" suffix="%" />
          </div>
        )}
        {breakeven.error ? <ErrorCard title="Breakeven" error={breakeven.error} /> : (
          <div>
            <MetricCard label="5Y Breakeven Inflation" value={breakeven.breakeven_5y} suffix="%" delta={breakeven.change_5y_1d}
              caption={`As of: ${breakeven.latest_date || 'N/A'}`} />
            <HistoryChart data={breakeven.historical_5y} label="5Y Breakeven (%)" color="#e65100" suffix="%" />
          </div>
        )}
        {!breakeven.error && (
          <div>
            <MetricCard label="10Y Breakeven Inflation" value={breakeven.breakeven_10y} suffix="%" delta={breakeven.change_10y_1d}
              caption={`As of: ${breakeven.latest_date || 'N/A'}${breakeven.interpretation ? ' | ' + breakeven.interpretation : ''}`} />
            <HistoryChart data={breakeven.historical_10y} label="10Y Breakeven (%)" color="#bf360c" suffix="%" />
          </div>
        )}
      </div>

      {/* Credit & Financial Conditions */}
      <SectionHeader title="Credit & Financial Conditions" sub />
      <div className="grid-4">
        {hy.error ? <ErrorCard title="HY OAS" error={hy.error} /> : (
          <div>
            <MetricCard label="HY Credit Spread (OAS)" value={hy.hy_oas} suffix="%" delta={hy.change_1d}
              caption={`As of: ${hy.latest_date || 'N/A'}${hy.interpretation ? ' | ' + hy.interpretation : ''}`} />
            <HistoryChart data={hy.historical} label="HY OAS (%)" color="#c62828" suffix="%" />
          </div>
        )}
        {nfci.error ? <ErrorCard title="NFCI" error={nfci.error} /> : (
          <div>
            <MetricCard label="NFCI" value={nfci.nfci} delta={nfci.change_1w} deltaLabel=" WoW"
              caption={`As of: ${nfci.latest_date || 'N/A'}${nfci.interpretation ? ' | ' + nfci.interpretation : ''}`} />
            <HistoryChart data={nfci.historical} label="NFCI" color="#4527a0" />
          </div>
        )}
        {ff.error ? <ErrorCard title="Fed Funds" error={ff.error} /> : (
          <div>
            <MetricCard label="Fed Funds Rate" value={ff.fed_funds_rate} suffix="%" delta={ff.change_1d}
              caption={`As of: ${ff.latest_date || 'N/A'}`} />
            <HistoryChart data={ff.historical} label="Fed Funds Rate (%)" color="#00695c" suffix="%" />
          </div>
        )}
        {ig.error ? <ErrorCard title="IG OAS" error={ig.error} /> : (
          <div>
            <MetricCard label="IG Credit Spread (OAS)" value={ig.ig_oas} suffix="%" delta={ig.change_1d}
              caption={`As of: ${ig.latest_date || 'N/A'}${ig.interpretation ? ' | ' + ig.interpretation : ''}`} />
            <HistoryChart data={ig.historical} label="IG OAS (%)" color="#4e342e" suffix="%" />
          </div>
        )}
      </div>

      {/* Bank Reserves + SLOOS */}
      <div className="grid-2">
        {reserves.error ? <ErrorCard title="Bank Reserves" error={reserves.error} /> : (
          <div>
            <MetricCard label="Bank Reserves ($T)" value={reserves.reserves_trillions} delta={reserves.change_wow_pct} deltaLabel="% WoW"
              caption={`As of: ${reserves.latest_date || 'N/A'}${reserves.interpretation ? ' | ' + reserves.interpretation : ''}`} />
            <HistoryChart data={reserves.historical} label="Bank Reserves ($T)" color="#1a237e" />
          </div>
        )}
        {sloos.error ? (
          <div className="metric-caption">SLOOS: {sloos.error || 'Data unavailable'} (quarterly, may be delayed)</div>
        ) : (
          <div>
            <MetricCard label="SLOOS Lending Standards" value={sloos.sloos_tightening} suffix="%" delta={sloos.change_qoq} deltaLabel=" QoQ"
              caption={`As of: ${sloos.latest_date || 'N/A'}${sloos.interpretation ? ' | ' + sloos.interpretation : ''}`} />
            <HistoryChart data={sloos.historical} label="SLOOS Net Tightening (%)" color="#3e2723" suffix="%" />
          </div>
        )}
      </div>

      {/* Labor Market & Inflation */}
      <SectionHeader title="Labor Market & Inflation" sub />
      <div className="grid-4">
        {unemp.error ? <ErrorCard title="Unemployment" error={unemp.error} /> : (
          <div>
            <MetricCard label="Unemployment Rate" value={unemp.unemployment_rate} suffix="%" delta={unemp.change_mom} deltaLabel=" MoM"
              caption={`As of: ${unemp.latest_date || 'N/A'}`} />
            <HistoryChart data={unemp.historical} label="Unemployment (%)" color="#283593" suffix="%" />
          </div>
        )}
        {claims.error ? <ErrorCard title="Initial Claims" error={claims.error} /> : (
          <div>
            <MetricCard label="Initial Claims (K)" value={claims.initial_claims_k} delta={claims.change_wow_pct} deltaLabel="% WoW"
              caption={`As of: ${claims.latest_date || 'N/A'}${claims.interpretation ? ' | ' + claims.interpretation : ''}`} />
            <HistoryChart data={claims.historical} label="Initial Claims" color="#37474f" />
          </div>
        )}
        {coreInfl.error ? <ErrorCard title="Core CPI" error={coreInfl.error} /> : (
          <div>
            <MetricCard label="Core CPI YoY%" value={coreInfl.core_cpi_yoy} suffix="%" delta={coreInfl.core_cpi_change_mom} deltaLabel=" MoM"
              caption={`As of: ${coreInfl.latest_date || 'N/A'}`} />
            <HistoryChart data={coreInfl.historical_core_cpi} label="Core CPI YoY (%)" color="#e65100" suffix="%" />
          </div>
        )}
        {!coreInfl.error && (
          <div>
            <MetricCard label="Core PCE YoY%" value={coreInfl.core_pce_yoy} suffix="%" delta={coreInfl.core_pce_change_mom} deltaLabel=" MoM"
              caption={coreInfl.interpretation || ''} />
            <HistoryChart data={coreInfl.historical_core_pce} label="Core PCE YoY (%)" color="#bf360c" suffix="%" />
          </div>
        )}
      </div>

      {/* Continuing Claims, Headline CPI, PPI */}
      <div className="grid-3">
        {cclaims.error ? <ErrorCard title="Continuing Claims" error={cclaims.error} /> : (
          <div>
            <MetricCard label="Continuing Claims (K)" value={cclaims.continuing_claims_k} delta={cclaims.change_wow_pct} deltaLabel="% WoW"
              caption={`As of: ${cclaims.latest_date || 'N/A'}${cclaims.interpretation ? ' | ' + cclaims.interpretation : ''}`} />
            <HistoryChart data={cclaims.historical} label="Continuing Claims (K)" color="#455a64" />
          </div>
        )}
        {hcpi.error ? <ErrorCard title="Headline CPI" error={hcpi.error} /> : (
          <div>
            <MetricCard label="Headline CPI YoY%" value={hcpi.headline_cpi_yoy} suffix="%" delta={hcpi.change_mom} deltaLabel=" MoM"
              caption={`As of: ${hcpi.latest_date || 'N/A'}`} />
            <HistoryChart data={hcpi.historical} label="Headline CPI YoY (%)" color="#ff6f00" suffix="%" />
          </div>
        )}
        {ppi.error ? <ErrorCard title="PPI" error={ppi.error} /> : (
          <div>
            <MetricCard label="PPI YoY%" value={ppi.ppi_yoy} suffix="%" delta={ppi.change_mom} deltaLabel=" MoM"
              caption={`As of: ${ppi.latest_date || 'N/A'}${ppi.interpretation ? ' | ' + ppi.interpretation : ''}`} />
            <HistoryChart data={ppi.historical} label="PPI YoY (%)" color="#ad1457" suffix="%" />
          </div>
        )}
      </div>

      {/* ECB Rates */}
      <SectionHeader title="ECB Policy Rates" sub />
      {ecb.error ? <ErrorCard error={ecb.error} /> : (
        <>
          <div className="grid-3">
            <MetricCard label="Deposit Rate" value={ecb.deposit_rate} suffix="%" />
            <MetricCard label="Refi Rate" value={ecb.refi_rate} suffix="%" />
            <MetricCard label="Marginal Rate" value={ecb.marginal_rate} suffix="%" />
          </div>
          <div className="metric-caption">As of: {ecb.latest_date || 'N/A'} | Source: {ecb.source || 'N/A'}</div>
          <HistoryChart data={ecb.historical} label="ECB Deposit Rate" color="#1565c0" />
        </>
      )}

      {/* CPI Components */}
      <SectionHeader title="CPI Components Breakdown" sub />
      {cpiComp.error ? <ErrorCard error={cpiComp.error} /> : (
        <>
          <div className="grid-5">
            <MetricCard label="Headline CPI YoY%" value={cpiComp.headline_cpi_yoy} suffix="%" />
            <MetricCard label="Core CPI YoY%" value={cpiComp.core_cpi_yoy} suffix="%" />
            <MetricCard label="Food CPI YoY%" value={cpiComp.food_cpi_yoy} suffix="%" />
            <MetricCard label="Energy CPI YoY%" value={cpiComp.energy_cpi_yoy} suffix="%" />
            <MetricCard label="Shelter CPI YoY%" value={cpiComp.shelter_cpi_yoy} suffix="%" />
          </div>
          <div className="metric-caption">As of: {cpiComp.latest_date || 'N/A'} | Source: {cpiComp.source || 'N/A'}</div>
          <HistoryChart data={cpiComp.historical} label="Headline CPI YoY (%)" color="#e65100" suffix="%" />
        </>
      )}

      {/* EU Yields and Global CPI */}
      <div className="grid-2">
        <div>
          <SectionHeader title="European Government Yields" sub />
          {euYields.error ? <ErrorCard error={euYields.error} /> : (
            <>
              <div className="grid-3">
                <MetricCard label="Germany 10Y" value={euYields.de_10y} suffix="%" />
                <MetricCard label="France 10Y" value={euYields.fr_10y} suffix="%" />
                <MetricCard label="Italy 10Y" value={euYields.it_10y} suffix="%" />
              </div>
              {euYields.it_de_spread != null && (
                <div className="metric-caption">IT-DE Spread: {fmt(euYields.it_de_spread)}% | Source: {euYields.source || 'N/A'}</div>
              )}
            </>
          )}
        </div>

        <div>
          <SectionHeader title="Global CPI Comparison" sub />
          {gCpi.error ? <ErrorCard error={gCpi.error} /> : (
            <>
              <div className="grid-4">
                <MetricCard label="US CPI" value={gCpi.us_cpi_yoy} suffix="%" />
                <MetricCard label="EU CPI" value={gCpi.eu_cpi_yoy} suffix="%" />
                <MetricCard label="Japan CPI" value={gCpi.jp_cpi_yoy} suffix="%" />
                <MetricCard label="UK CPI" value={gCpi.uk_cpi_yoy} suffix="%" />
              </div>
              <div className="metric-caption">Source: {gCpi.source || 'N/A'}</div>
              <HistoryChart data={gCpi.historical} label="US CPI YoY (%)" color="#e65100" suffix="%" />
            </>
          )}
        </div>
      </div>

      {/* Full Treasury Yield Curve */}
      <SectionHeader title="Full Treasury Yield Curve" sub />
      {tCurve.error ? <ErrorCard error={tCurve.error} /> : (
        tCurve.curve && Object.keys(tCurve.curve).length > 0 && (
          <div className="full-chart">
            <Plot
              data={[{
                x: Object.keys(tCurve.curve),
                y: Object.values(tCurve.curve),
                type: 'scatter',
                mode: 'lines+markers',
                line: { color: '#1565c0' },
                name: 'Yield',
              }]}
              layout={{
                title: 'US Treasury Yield Curve',
                xaxis: { title: 'Maturity' },
                yaxis: { title: 'Yield (%)' },
                height: 300,
                margin: { l: 50, r: 20, t: 40, b: 30 },
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: '100%' }}
            />
            <div className="metric-caption">As of: {tCurve.latest_date || 'N/A'} | Source: {tCurve.source || 'N/A'}</div>
          </div>
        )
      )}

      {/* Corporate Spreads */}
      <SectionHeader title="Corporate Bond Spreads (AAA/BBB)" sub />
      {corpSpreads.error ? <ErrorCard error={corpSpreads.error} /> : (
        <>
          <div className="grid-3">
            <MetricCard label="AAA OAS" value={corpSpreads.aaa_oas} suffix="%" />
            <MetricCard label="BBB OAS" value={corpSpreads.bbb_oas} suffix="%" />
            <MetricCard label="Credit Spread (BBB-AAA)" value={corpSpreads.credit_spread} suffix="%" />
          </div>
          <div className="metric-caption">As of: {corpSpreads.latest_date || 'N/A'} | Source: {corpSpreads.source || 'N/A'}</div>
        </>
      )}
    </div>
  );
}
