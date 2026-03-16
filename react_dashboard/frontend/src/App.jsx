import React, { useState, useEffect, useCallback, useRef } from 'react';
import { fetchAllIndicators, refreshData } from './api';
import TabPanel from './components/TabPanel';
import Tab1Valuation from './tabs/Tab1Valuation';
import Tab2MarketIndices from './tabs/Tab2MarketIndices';
import Tab3Volatility from './tabs/Tab3Volatility';
import Tab4MacroCurrency from './tabs/Tab4MacroCurrency';
import Tab5Commodities from './tabs/Tab5Commodities';
import Tab6Financials from './tabs/Tab6Financials';
import Tab7RatesCredit from './tabs/Tab7RatesCredit';
import Tab8EconomicActivity from './tabs/Tab8EconomicActivity';

const TABS = [
  { id: 0, label: 'Valuation Metrics' },
  { id: 1, label: 'Market Indices' },
  { id: 2, label: 'Volatility & Risk' },
  { id: 3, label: 'Macro & Currency' },
  { id: 4, label: 'Commodities' },
  { id: 5, label: 'Large-cap Financials' },
  { id: 6, label: 'Rates & Credit' },
  { id: 7, label: 'Economic Activity' },
];

const POLL_INTERVAL = 60000; // 60 seconds

export default function App() {
  const [activeTab, setActiveTab] = useState(0);
  const [indicators, setIndicators] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [fromCache, setFromCache] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const pollRef = useRef(null);

  const loadData = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true);
    try {
      const data = await fetchAllIndicators();
      setIndicators(data.indicators || {});
      setLastUpdate(data.last_update);
      setTotalCount(data.total || 0);
      setFromCache(data.loaded_from_cache || false);
      setError(null);
    } catch (e) {
      if (!indicators) {
        setError(e.response?.data?.error || e.message || 'Failed to connect to backend');
      }
      console.error('Failed to load indicators:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load
  useEffect(() => {
    loadData(true);
  }, [loadData]);

  // Auto-refresh polling
  useEffect(() => {
    pollRef.current = setInterval(() => loadData(false), POLL_INTERVAL);
    return () => clearInterval(pollRef.current);
  }, [loadData]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refreshData();
      await loadData(false);
    } catch (e) {
      console.error('Refresh failed:', e);
    } finally {
      setRefreshing(false);
    }
  };

  const fmtUpdate = lastUpdate
    ? new Date(lastUpdate).toLocaleString()
    : 'Never';

  if (loading && !indicators) {
    return (
      <div>
        <header className="app-header">
          <h1>Macro Indicators Dashboard</h1>
        </header>
        <div className="loading-overlay">
          <div className="spinner" />
          Loading indicators from backend...
        </div>
      </div>
    );
  }

  if (error && !indicators) {
    return (
      <div>
        <header className="app-header">
          <h1>Macro Indicators Dashboard</h1>
        </header>
        <div style={{ padding: 40, textAlign: 'center' }}>
          <div className="error-card" style={{ maxWidth: 500, margin: '0 auto' }}>
            <div className="error-title">Connection Error</div>
            <div>{error}</div>
            <div className="error-note" style={{ marginTop: 8 }}>
              Make sure the FastAPI backend is running on port 8000.
              <br />
              <code>cd react_dashboard/backend && python main.py</code>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <header className="app-header">
        <h1>Macro Indicators Dashboard</h1>
        <div className="header-info">
          <span className="indicator-count">{totalCount} indicators</span>
          <span className="last-update">
            Updated: {fmtUpdate}
            {fromCache ? ' (cache)' : ''}
          </span>
          <button
            className="refresh-btn"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh All'}
          </button>
        </div>
      </header>

      {/* Tab bar */}
      <nav className="tab-bar">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      {/* Tab panels */}
      <TabPanel active={activeTab === 0}>
        <Tab1Valuation indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 1}>
        <Tab2MarketIndices indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 2}>
        <Tab3Volatility indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 3}>
        <Tab4MacroCurrency indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 4}>
        <Tab5Commodities indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 5}>
        <Tab6Financials indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 6}>
        <Tab7RatesCredit indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 7}>
        <Tab8EconomicActivity indicators={indicators} />
      </TabPanel>
    </div>
  );
}
