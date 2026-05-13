import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || '/api';
const API_KEY = import.meta.env.VITE_API_KEY || '';

const client = axios.create({ baseURL: BASE });

if (API_KEY) {
  client.interceptors.request.use((config) => {
    config.headers['X-API-Key'] = API_KEY;
    return config;
  });
}

export const huntApi = {
  start: (config) => client.post('/hunt/start', { config, save: true }),
  status: () => client.get('/hunt/status'),
  results: (params) => client.get('/hunt/results', { params }),
  getConfig: () => client.get('/get-hunt-config'),
  setConfig: (config) => client.post('/set-hunt-config', config),
  getListings: (params) => client.get('/hunt/listings', { params }),
  runCrawl: (params) => client.post('/run-crawl', null, { params }),
};

export const listingApi = {
  getDetail: (id) => client.get(`/listings/${id}`),
  triggerAI: (id) => client.post(`/listings/${id}/analyze`),
};

export const marketApi = {
  getTrend: (params) => client.get('/market/trend', { params }),
  getDistricts: () => client.get('/market/districts'),
  ingest: (params) => client.post('/market/ingest', null, { params }),
  getRCN: (params) => client.get('/market/rcn-benchmark', { params }),
  getRcnStats: (params) => client.get('/market/rcn-stats', { params }),
};

export const statsApi = {
  get: () => client.get('/stats'),
};

export const alertsApi = {
  get: (params) => client.get('/alerts', { params }),
};

// SSE helper
export function createHuntStream(jobId, onEvent, onDone, onError) {
  let url = `${BASE}/hunt/stream/${jobId}`;
  if (API_KEY) {
    url += `?api_key=${encodeURIComponent(API_KEY)}`;
  }
  const es = new EventSource(url);

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data);
      if (data.type === 'done' || data.type === 'error') {
        onEvent(data);
        onDone(data);
        es.close();
      } else if (data.type !== 'heartbeat') {
        onEvent(data);
      }
    } catch { }
  };

  es.onerror = (e) => {
    onError(e);
    es.close();
  };

  return () => es.close();
}

export default client;