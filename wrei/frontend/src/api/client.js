import axios from 'axios';

const BASE = import.meta.env.VITE_API_URL || '/api';

const client = axios.create({ baseURL: BASE });

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
};

export const statsApi = {
  get: () => client.get('/stats'),
};

// SSE helper
export function createHuntStream(jobId, onEvent, onDone, onError) {
  const url = `${BASE}/hunt/stream/${jobId}`;
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