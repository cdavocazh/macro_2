import React, { useState, useEffect, useCallback } from 'react';
import { fetchFinancials } from '../api';
import MetricCard from '../components/MetricCard';
import ErrorCard from '../components/ErrorCard';
import SectionHeader from '../components/SectionHeader';

const TOP_20 = ['AAPL','MSFT','NVDA','GOOGL','AMZN','META','BRK-B','TSM',
  'LLY','AVGO','JPM','V','WMT','MA','XOM','UNH','COST','HD','PG','JNJ'];

function fmtDollar(v) {
  if (v == null) return '-';
  const n = Number(v);
  if (isNaN(n)) return '-';
  if (Math.abs(n) >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  if (Math.abs(n) >= 1e3) return `$${(n / 1e3).toFixed(1)}K`;
  return `$${n.toFixed(2)}`;
}

function fmtPct(v) {
  if (v == null) return 'N/A';
  const n = Number(v);
  return isNaN(n) ? 'N/A' : `${(n * 100).toFixed(1)}%`;
}

function fmtPctRaw(v) {
  if (v == null) return 'N/A';
  return `${Number(v).toFixed(1)}%`;
}

function fmtRatio(v, d = 2) {
  if (v == null) return 'N/A';
  return Number(v).toFixed(d);
}

function fmtEps(v) {
  if (v == null) return 'N/A';
  return `$${Number(v).toFixed(2)}`;
}

function pctChange(curr, prev) {
  if (curr == null || prev == null || prev === 0) return null;
  return ((Number(curr) - Number(prev)) / Math.abs(Number(prev))) * 100;
}

function ChangeSpan({ val }) {
  if (val == null) return null;
  const cls = val >= 0 ? 'change-positive' : 'change-negative';
  return <span className={cls}>{val >= 0 ? '+' : ''}{val.toFixed(1)}%</span>;
}

function QuarterlyTable({ data, metrics, quarters }) {
  if (!data || !quarters || quarters.length === 0) return null;

  return (
    <table className="data-table">
      <thead>
        <tr>
          <th>Metric</th>
          {quarters.map(q => <th key={q}>{q}</th>)}
        </tr>
      </thead>
      <tbody>
        {metrics.map(([label, key, fmt]) => {
          const vals = data[key] || [];
          return (
            <tr key={key}>
              <td dangerouslySetInnerHTML={{ __html: label }} />
              {quarters.map((q, i) => {
                const v = i < vals.length ? vals[i] : null;
                const prev = i + 1 < vals.length ? vals[i + 1] : null;
                const qoq = pctChange(v, prev);
                let cellText = '-';
                if (v != null) {
                  if (fmt === '$') cellText = fmtDollar(v);
                  else if (fmt === '%') cellText = `${(Number(v) * 100).toFixed(1)}%`;
                  else if (fmt === 'eps') cellText = fmtEps(v);
                  else if (fmt === 'shares') cellText = `${(Number(v) / 1e9).toFixed(2)}B`;
                  else cellText = Number(v).toFixed(2);
                }
                return (
                  <td key={q}>
                    {cellText}
                    <ChangeSpan val={qoq} />
                  </td>
                );
              })}
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

export default function Tab6Financials({ indicators }) {
  const [ticker, setTicker] = useState('AAPL');
  const [customTicker, setCustomTicker] = useState('');
  const [source, setSource] = useState('yahoo');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Use cached equity financials from aggregator for Top 20
  const eqData = indicators?.['29_equity_financials'] || {};
  const companies = eqData.companies || {};
  const availableTickers = eqData.tickers?.filter(t => companies[t] && !companies[t]?.error) || TOP_20;

  const activeTicker = customTicker.trim().toUpperCase() || ticker;
  const isCustom = customTicker.trim() && !availableTickers.includes(activeTicker);

  const loadData = useCallback(async () => {
    const t = activeTicker;
    if (!t) return;

    // For Yahoo source and Top 20, use cached data
    if (source === 'yahoo' && !isCustom && companies[t]) {
      setData(companies[t]);
      setError(null);
      return;
    }

    // Otherwise fetch on demand
    setLoading(true);
    setError(null);
    try {
      const result = await fetchFinancials(t, source);
      if (result?.error) {
        setError(result.error);
        setData(null);
      } else {
        setData(result);
      }
    } catch (e) {
      setError(e.response?.data?.error || e.message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [activeTicker, source, isCustom, companies]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const incMetrics = [
    ['Total Revenue', 'total_revenue', '$'],
    ['Cost of Revenue', 'cost_of_revenue', '$'],
    ['Gross Profit', 'gross_profit', '$'],
    ['Operating Expenses', 'operating_expense', '$'],
    ['&nbsp;&nbsp;R&D', 'research_development', '$'],
    ['&nbsp;&nbsp;SG&A', 'selling_general_admin', '$'],
    ['Operating Income', 'operating_income', '$'],
    ['EBITDA', 'ebitda', '$'],
    ['Pretax Income', 'pretax_income', '$'],
    ['Net Income', 'net_income', '$'],
    ['Diluted EPS', 'diluted_eps', 'eps'],
    ['Basic EPS', 'basic_eps', 'eps'],
  ];

  const bsAssets = [
    ['Total Assets', 'total_assets', '$'],
    ['&nbsp;&nbsp;Current Assets', 'current_assets', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Cash & ST Investments', 'cash_and_short_term_investments', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Accounts Receivable', 'accounts_receivable', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Inventory', 'inventory', '$'],
    ['&nbsp;&nbsp;Non-Current Assets', 'total_non_current_assets', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Goodwill', 'goodwill', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Net PP&E', 'net_ppe', '$'],
  ];

  const bsLiab = [
    ['Total Liabilities', 'total_liabilities', '$'],
    ['&nbsp;&nbsp;Current Liabilities', 'current_liabilities', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Current Debt', 'current_debt', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Accounts Payable', 'accounts_payable', '$'],
    ['&nbsp;&nbsp;Non-Current Liabilities', 'non_current_liabilities', '$'],
    ['&nbsp;&nbsp;&nbsp;&nbsp;Long-Term Debt', 'long_term_debt', '$'],
    ['&nbsp;&nbsp;Total Debt', 'total_debt', '$'],
    ['&nbsp;&nbsp;Net Debt', 'net_debt', '$'],
  ];

  const bsEquity = [
    ["Stockholders' Equity", 'stockholders_equity', '$'],
    ['Retained Earnings', 'retained_earnings', '$'],
    ['Invested Capital', 'invested_capital', '$'],
    ['Debt Ratio (Liab/Assets)', 'debt_ratio', '%'],
    ['Debt/Equity', 'debt_to_equity', '%'],
    ['Current Ratio', 'current_ratio', '%'],
  ];

  const cfMetrics = [
    ['Operating Cash Flow', 'operating_cash_flow', '$'],
    ['Capital Expenditures', 'capital_expenditure', '$'],
    ['Free Cash Flow', 'free_cash_flow', '$'],
    ['Share Repurchases', 'share_repurchases', '$'],
    ['Dividends Paid', 'dividends_paid', '$'],
    ['Investing Cash Flow', 'investing_cash_flow', '$'],
    ['Financing Cash Flow', 'financing_cash_flow', '$'],
    ['D&A', 'depreciation_amortization', '$'],
    ['Stock-Based Compensation', 'stock_based_compensation', '$'],
  ];

  const quarters = data?.quarters || [];
  const inc = data?.income_statement;
  const bs = data?.balance_sheet;
  const cf = data?.cash_flow;
  const fa = data?.financial_analysis || {};
  const val = data?.valuation || {};
  const prof = fa.profitability || {};
  const turnover = fa.turnover || {};
  const growth = fa.growth || {};
  const returns = fa.returns || {};

  return (
    <div>
      <SectionHeader title="Large-cap Financials" />

      {/* Controls */}
      <div className="financials-controls">
        <label>
          Top 20 Companies
          <select value={ticker} onChange={(e) => { setTicker(e.target.value); setCustomTicker(''); }}>
            {availableTickers.map(t => (
              <option key={t} value={t}>
                {t}{companies[t]?.company_name ? ` - ${companies[t].company_name}` : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          Or type any ticker
          <input
            type="text"
            placeholder="e.g. CRM, NFLX, AMD"
            value={customTicker}
            onChange={(e) => setCustomTicker(e.target.value)}
          />
        </label>
        <label>
          Data Source
          <div className="source-toggle">
            <button className={source === 'yahoo' ? 'active' : ''} onClick={() => setSource('yahoo')}>Yahoo Finance</button>
            <button className={source === 'sec' ? 'active' : ''} onClick={() => setSource('sec')}>SEC EDGAR</button>
          </div>
        </label>
      </div>

      {isCustom && (
        <div className="info-box">Viewing <strong>{activeTicker}</strong> (not in Top 20 - data fetched on demand)</div>
      )}

      {loading && (
        <div className="loading-overlay">
          <div className="spinner" />
          Loading {activeTicker} from {source === 'yahoo' ? 'Yahoo Finance' : 'SEC EDGAR'}...
        </div>
      )}

      {error && <ErrorCard title={`${source} error`} error={error} />}

      {data && !loading && !error && (
        <>
          {/* Company header */}
          <div className="grid-3">
            <MetricCard label="Market Cap" value={fmtDollar(data.market_cap)} />
            <MetricCard label="Sector" value={data.sector || 'N/A'} />
            <MetricCard label="Industry" value={data.industry || 'N/A'} />
          </div>
          <div className="metric-caption" style={{ marginTop: 4 }}>
            Source: {data.source || source} | Quarters: {quarters.join(', ') || 'N/A'}
          </div>

          {/* 1. Income Statement */}
          {inc && quarters.length > 0 && (
            <>
              <SectionHeader title="1. Income Statement (Quarterly)" sub />
              <QuarterlyTable data={inc} metrics={incMetrics} quarters={quarters} />
            </>
          )}

          {/* 2. Balance Sheet */}
          {bs && quarters.length > 0 && (
            <>
              <SectionHeader title="2. Balance Sheet (Quarterly)" sub />
              <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Assets</h4>
              <QuarterlyTable data={bs} metrics={bsAssets} quarters={quarters} />
              <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Liabilities</h4>
              <QuarterlyTable data={bs} metrics={bsLiab} quarters={quarters} />
              <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Equity & Ratios</h4>
              <QuarterlyTable data={bs} metrics={bsEquity} quarters={quarters} />
            </>
          )}

          {/* 3. Cash Flow */}
          {cf && quarters.length > 0 && (
            <>
              <SectionHeader title="3. Cash Flow (Quarterly)" sub />
              <QuarterlyTable data={cf} metrics={cfMetrics} quarters={quarters} />
            </>
          )}

          {/* 4. Financial Analysis */}
          <SectionHeader title="4. Financial Analysis" sub />

          <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Profitability</h4>
          <div className="analysis-row">
            <div className="analysis-item">
              <div className="a-label">Gross Margin</div>
              <div className="a-value">{fmtPctRaw(prof.gross_margin)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Operating Margin</div>
              <div className="a-value">{fmtPctRaw(prof.operating_margin)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">EBITDA Margin</div>
              <div className="a-value">{fmtPctRaw(prof.ebitda_margin)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">FCF Margin</div>
              <div className="a-value">{fmtPctRaw(prof.fcf_margin)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Net Margin</div>
              <div className="a-value">{fmtPctRaw(prof.net_margin)}</div>
            </div>
          </div>

          <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Turnover & Leverage</h4>
          <div className="analysis-row">
            <div className="analysis-item">
              <div className="a-label">Debt/Equity</div>
              <div className="a-value">{fmtRatio(turnover.debt_to_equity)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Current Ratio</div>
              <div className="a-value">{fmtRatio(turnover.current_ratio)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Asset Turnover</div>
              <div className="a-value">{fmtRatio(turnover.asset_turnover, 4)}</div>
            </div>
          </div>

          <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Growth</h4>
          <div className="analysis-row">
            <div className="analysis-item">
              <div className="a-label">EPS Growth</div>
              <div className="a-value">{fmtPctRaw(growth.eps_growth)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Revenue Growth</div>
              <div className="a-value">{fmtPctRaw(growth.revenue_growth)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Revenue QoQ</div>
              <div className="a-value">{fmtPctRaw(growth.revenue_qoq)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">Earnings QoQ</div>
              <div className="a-value">{fmtPctRaw(growth.earnings_quarterly_growth)}</div>
            </div>
          </div>

          <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '8px 0 4px' }}>Returns</h4>
          <div className="analysis-row">
            <div className="analysis-item">
              <div className="a-label">ROE</div>
              <div className="a-value">{fmtPctRaw(returns.roe)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">ROA</div>
              <div className="a-value">{fmtPctRaw(returns.roa)}</div>
            </div>
            <div className="analysis-item">
              <div className="a-label">ROIC</div>
              <div className="a-value">{fmtPctRaw(returns.roic)}</div>
            </div>
          </div>

          {/* 5. Valuation */}
          <SectionHeader title="5. Valuation" sub />
          <div className="grid-4">
            <MetricCard label="Forward P/E" value={fmtRatio(val.forward_pe)} />
            <MetricCard label="Trailing P/E (12M)" value={fmtRatio(val.trailing_pe)} />
            <MetricCard label="PEG Ratio" value={fmtRatio(val.peg_ratio)} />
            <MetricCard label="Price / Book" value={fmtRatio(val.price_to_book)} />
          </div>
          <div className="grid-4" style={{ marginTop: 8 }}>
            <MetricCard label="Price / Sales" value={fmtRatio(val.price_to_sales)} />
            <MetricCard label="EV / EBITDA" value={fmtRatio(val.ev_to_ebitda)} />
            <MetricCard label="EV / FCF" value={fmtRatio(val.ev_to_fcf)} />
            <MetricCard label="Enterprise Value" value={fmtDollar(val.enterprise_value)} />
          </div>
          <div className="grid-4" style={{ marginTop: 8 }}>
            <MetricCard label="Beta" value={fmtRatio(val.beta)} />
            <MetricCard label="Dividend Yield" value={fmtPctRaw(val.dividend_yield)} />
            <MetricCard label="TTM EPS" value={fmtEps(val.diluted_eps_ttm)} />
            <MetricCard label="Book Value/Share" value={fmtEps(val.book_value_per_share)} />
          </div>

          {/* 6. Revenue Segments */}
          {data.revenue_segments && (
            <>
              <SectionHeader title="6. Revenue Segment Breakdown" sub />
              {data.revenue_segments.product_segments || data.revenue_segments.business_segments || data.revenue_segments.geographic_segments ? (
                <>
                  {['product_segments', 'business_segments', 'geographic_segments'].map(segKey => {
                    const segments = data.revenue_segments[segKey];
                    if (!segments) return null;
                    const title = segKey.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
                    return (
                      <div key={segKey} style={{ marginBottom: 8 }}>
                        <h4 style={{ fontSize: '0.82rem', fontWeight: 600, margin: '6px 0 4px' }}>{title}</h4>
                        <table className="sector-table">
                          <thead><tr><th>Segment</th><th>Revenue</th></tr></thead>
                          <tbody>
                            {Object.entries(segments)
                              .sort(([, a], [, b]) => (Number(b) || 0) - (Number(a) || 0))
                              .map(([name, val]) => (
                                <tr key={name}><td>{name}</td><td>{fmtDollar(val)}</td></tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    );
                  })}
                </>
              ) : (
                <table className="sector-table">
                  <thead><tr><th>Segment</th><th>Revenue</th></tr></thead>
                  <tbody>
                    {Object.entries(data.revenue_segments)
                      .filter(([k]) => !k.startsWith('_'))
                      .sort(([, a], [, b]) => (Number(b) || 0) - (Number(a) || 0))
                      .map(([name, val]) => (
                        <tr key={name}><td>{name}</td><td>{fmtDollar(val)}</td></tr>
                      ))}
                  </tbody>
                </table>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
