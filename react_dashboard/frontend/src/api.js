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

export default api;
