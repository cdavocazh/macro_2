import React, { useState, useEffect, useCallback, useRef } from 'react';
import { fetchAllIndicators, refreshData } from './api';
import { toGMT8 } from './utils/time';
import TabPanel from './components/TabPanel';
import { ChartDrawerProvider } from './components/ChartDrawer';
import Tab1Valuation from './tabs/Tab1Valuation';
import Tab2MarketIndices from './tabs/Tab2MarketIndices';
import Tab3Volatility from './tabs/Tab3Volatility';
import Tab4MacroCurrency from './tabs/Tab4MacroCurrency';
import Tab5Commodities from './tabs/Tab5Commodities';
import Tab6Financials from './tabs/Tab6Financials';
import Tab7RatesCredit from './tabs/Tab7RatesCredit';
import Tab8EconomicActivity from './tabs/Tab8EconomicActivity';
import Tab9Polymarket from './tabs/Tab9Polymarket';
import Tab10Monitor from './tabs/Tab10Monitor';
import Tab11Positioning from './tabs/Tab11Positioning';
import CalendarStrip from './components/CalendarStrip';
import CommandPalette from './components/CommandPalette';

const TABS = [
  { id: 0, label: 'Valuation Metrics' },
  { id: 1, label: 'Market Indices' },
  { id: 2, label: 'Volatility & Risk' },
  { id: 3, label: 'Macro & Currency' },
  { id: 4, label: 'Commodities' },
  { id: 5, label: 'Large-cap Financials' },
  { id: 6, label: 'Rates & Credit' },
  { id: 7, label: 'Economic Activity' },
  { id: 8, label: 'Polymarket' },
  { id: 9, label: 'Monitor' },
  { id: 10, label: 'Positioning' },
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

  // Recursively overlay `next` onto `prev`, keeping keys that exist only in
  // `prev`. Lets a lite payload (scalars only) refresh metric values without
  // discarding the historical series a previous full payload delivered.
  const mergePreserving = (prev, next) => {
    if (!prev || typeof prev !== 'object' || Array.isArray(prev)
        || !next || typeof next !== 'object' || Array.isArray(next)) {
      return next;
    }
    const out = { ...prev };
    for (const [k, v] of Object.entries(next)) out[k] = mergePreserving(prev[k], v);
    return out;
  };

  const loadData = useCallback(async (showLoading = false, lite = false) => {
    if (showLoading) setLoading(true);
    try {
      const data = await fetchAllIndicators(lite);
      const fresh = data.indicators || {};
      // Lite responses have the series stripped — merge them over what we
      // already hold instead of replacing it, so open charts keep their data.
      setIndicators(prev => (lite && prev ? mergePreserving(prev, fresh) : fresh));
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

  // Initial load: lite payload first (no 5y series, ~36 KB gz) so metric cards
  // paint immediately, then the full payload in the background so the
  // expandable charts have their history. All charts start collapsed, so the
  // brief window without series data is invisible unless a chart is opened
  // within the first seconds.
  useEffect(() => {
    (async () => {
      await loadData(true, true);
      loadData(false, false);
    })();
  }, [loadData]);

  // Auto-refresh polling. A full payload is ~1.5 MB gz per client per tick;
  // scalars change every minute but the 5-year series only refresh on the
  // 5-minute extract jobs. So poll lite (~36 KB, merged over current state)
  // each tick and take a full payload every 5th — same freshness where it
  // matters, ~4x less transfer and server CPU.
  useEffect(() => {
    let tick = 0;
    pollRef.current = setInterval(() => {
      tick += 1;
      loadData(false, tick % 5 !== 0);
    }, POLL_INTERVAL);
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

  const fmtUpdate = lastUpdate ? toGMT8(lastUpdate) : 'Never';

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
              Make sure the FastAPI backend is running.
              <br />
              <code>cd react_dashboard && bash start.sh</code>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <ChartDrawerProvider>
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

      <CalendarStrip />

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
      <TabPanel active={activeTab === 8}>
        <Tab9Polymarket indicators={indicators} />
      </TabPanel>
      <TabPanel active={activeTab === 9}>
        <Tab10Monitor />
      </TabPanel>
      <TabPanel active={activeTab === 10}>
        <Tab11Positioning indicators={indicators} />
      </TabPanel>

      <CommandPalette tabs={TABS} onSelectTab={setActiveTab} />
    </div>
    </ChartDrawerProvider>
  );
}
