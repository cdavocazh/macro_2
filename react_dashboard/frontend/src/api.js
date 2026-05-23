import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
});

export async function fetchAllIndicators() {
  const resp = await api.get('/indicators');
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
