import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
});

export async function fetchAllIndicators(lite = false) {
  // lite=true strips 5-year historical series server-side (~9 MB → ~0.3 MB raw)
  // for a fast first paint; the full payload is fetched in the background after.
  const resp = await api.get('/indicators', { params: lite ? { lite: 1 } : {} });
  return resp.data;
}

export async function fetchIndicator(key) {
  const resp = await api.get(`/indicators/${key}`);
  return resp.data;
}

export async function fetchStatus() {
  const resp = await api.get('/status');
  return resp.data;
}

export async function refreshData() {
  const resp = await api.get('/refresh');
  return resp.data;
}

export async function fetchFinancials(ticker, source = 'yahoo') {
  const resp = await api.get(`/financials/${ticker}`, { params: { source } });
  return resp.data;
}

export async function fetchHistory(key, histKey = 'historical') {
  const resp = await api.get(`/history/${key}`, { params: { hist_key: histKey } });
  return resp.data;
}

// IBKR — list available expiries for a future symbol (GC, SI, ES, etc.)
export async function fetchIbkrContracts(symbol) {
  const resp = await api.get(`/ibkr/contracts/${symbol}`);
  return resp.data;
}

// IBKR — change which expiry is being streamed for a symbol
// expiry="" or null → reset to front month
export async function changeIbkrExpiry(symbol, expiry) {
  const resp = await api.post('/ibkr/subscribe', { symbol, expiry: expiry || '' });
  return resp.data;
}

export async function fetchIbkrSubscriptions() {
  const resp = await api.get('/ibkr/subscriptions');
  return resp.data;
}

export default api;

// ── Derived analytics (monitor grid, regime, forward returns, calendar, 13F) ──

export async function fetchMonitor() {
  const resp = await api.get('/monitor');
  return resp.data;
}

export async function fetchRegime() {
  const resp = await api.get('/analytics/regime');
  return resp.data;
}

export async function fetchForwardReturns({ conditionKey, op, threshold, targetKey, horizons }) {
  const resp = await api.get('/analytics/forward-returns', {
    params: {
      condition_key: conditionKey,
      op,
      threshold,
      target_key: targetKey,
      horizons: horizons.join(','),
    },
  });
  return resp.data;
}

export async function fetchCalendar(daysAhead = 45, limit = 20) {
  const resp = await api.get('/calendar', { params: { days_ahead: daysAhead, limit } });
  return resp.data;
}

export async function fetchPositioning13F(topN = 8) {
  const resp = await api.get('/positioning/13f', { params: { top_n: topN } });
  return resp.data;
}
