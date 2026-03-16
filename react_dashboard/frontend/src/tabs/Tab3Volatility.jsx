import React from 'react';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';
import HistoryChart from '../components/HistoryChart';

function fmt(v, d = 2) {
  if (v == null || v === 'N/A') return 'N/A';
  return typeof v === 'number' ? v.toFixed(d) : String(v);
}

export default function Tab3Volatility({ indicators }) {
  if (!indicators) return null;

  const vix = indicators['8_vix'] || {};
  const move = indicators['9_move_index'] || {};
  const vixMove = indicators['8b_vix_move_ratio'] || {};
  const putCall = indicators['4_put_call_ratio'] || {};
  const skew = indicators['5_spx_call_skew'] || {};
  const vfc = indicators['63_vix_futures_curve'] || {};
  const pcoi = indicators['64_spy_put_call_oi'] || {};
  const ivSkew = indicators['70_iv_skew'] || {};

  return (
    <div>
      <SectionHeader title="Volatility & Risk Indicators" />

      {/* VIX, MOVE, VIX/MOVE Ratio */}
      <div className="grid-3">
        {vix.error ? (
          <ErrorCard title="VIX" error={vix.error} />
        ) : (
          <div>
            <MetricCard
              label="VIX"
              value={vix.vix}
              delta={vix.change_1d}
              deltaLabel="%"
              caption={`As of: ${vix.latest_date || 'N/A'}`}
              inverse
            />
            <HistoryChart data={vix.historical} label="VIX" color="#e53935" />
          </div>
        )}

        {move.error ? (
          <ErrorCard title="MOVE Index" error={move.error} />
        ) : (
          <div>
            <MetricCard
              label="MOVE Index"
              value={move.move}
              delta={move.change_1d}
              deltaLabel="%"
              caption={`As of: ${move.latest_date || 'N/A'}`}
              inverse
            />
            <HistoryChart data={move.historical} label="MOVE Index" color="#ff9800" />
          </div>
        )}

        {vixMove.error ? (
          <ErrorCard title="VIX/MOVE Ratio" error={vixMove.error} />
        ) : (
          <MetricCard label="VIX/MOVE Ratio" value={vixMove.vix_move_ratio} />
        )}
      </div>

      {/* Put/Call and SKEW */}
      <div className="grid-2" style={{ marginTop: 12 }}>
        {putCall.error ? (
          <ErrorCard title="S&P 500 Put/Call Ratio" error={putCall.error} note={putCall.note} />
        ) : (
          <div>
            <MetricCard label="Put/Call Ratio" value={putCall.sp500_put_call_ratio} />
            <HistoryChart data={putCall.historical} label="Put/Call Ratio" color="#7b1fa2" />
          </div>
        )}

        {skew.error ? (
          <ErrorCard title="CBOE SKEW" error={skew.error} />
        ) : (
          <div>
            <MetricCard label="CBOE SKEW" value={skew.spx_call_skew} />
            {skew.interpretation && (
              <div className="info-box" style={{ marginTop: 4 }}>
                <strong>Interpretation:</strong>
                <ul style={{ paddingLeft: 16, marginTop: 2 }}>
                  {Object.entries(skew.interpretation).map(([k, v]) => (
                    <li key={k}>{k}: {v}</li>
                  ))}
                </ul>
              </div>
            )}
            <HistoryChart data={skew.historical} label="CBOE SKEW" color="#1565c0" />
          </div>
        )}
      </div>

      {/* VIX Futures Curve, SPY Put/Call OI, IV Skew */}
      <div className="grid-3" style={{ marginTop: 12 }}>
        {/* VIX Futures Curve */}
        {vfc.error ? (
          <ErrorCard title="VIX Futures Curve" error={vfc.error} />
        ) : (
          <div>
            <MetricCard label="VIX Spot" value={vfc.vix_spot} />
            {vfc.contango_pct != null && (
              <MetricCard label="Contango" value={vfc.contango_pct} suffix="%" />
            )}
            <div className="metric-caption">
              Expirations: {vfc.n_expirations || 0} | Source: {vfc.source || 'N/A'}
            </div>
            <HistoryChart data={vfc.historical} label="VIX Spot" color="#d32f2f" />
          </div>
        )}

        {/* SPY Put/Call OI */}
        {pcoi.error ? (
          <ErrorCard title="SPY Put/Call OI" error={pcoi.error} />
        ) : (
          <div>
            <MetricCard label="P/C Volume Ratio" value={pcoi.put_call_volume_ratio} />
            {pcoi.put_call_oi_ratio != null && (
              <MetricCard label="P/C OI Ratio" value={pcoi.put_call_oi_ratio} />
            )}
            <div className="metric-caption">Source: {pcoi.source || 'N/A'}</div>
            <HistoryChart data={pcoi.historical} label="Put/Call Ratio" color="#7b1fa2" />
          </div>
        )}

        {/* IV Skew */}
        {ivSkew.error ? (
          <ErrorCard title="SPX IV Skew" error={ivSkew.error} />
        ) : (
          <div>
            {ivSkew.iv_skew_25d != null ? (
              <>
                <MetricCard label="25d Skew" value={ivSkew.iv_skew_25d} suffix="%" />
                {ivSkew.otm_put_iv && ivSkew.otm_call_iv && (
                  <div className="metric-caption">
                    OTM Put IV: {ivSkew.otm_put_iv}% | OTM Call IV: {ivSkew.otm_call_iv}%
                  </div>
                )}
              </>
            ) : ivSkew.skew_index != null ? (
              <MetricCard label="SKEW Index" value={ivSkew.skew_index} />
            ) : null}
            <div className="metric-caption">Source: {ivSkew.source || 'N/A'}</div>
            <HistoryChart data={ivSkew.historical} label="IV Skew" color="#1565c0" />
          </div>
        )}
      </div>
    </div>
  );
}
