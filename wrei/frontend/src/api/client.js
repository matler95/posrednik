import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
});

export const huntApi = {
  getStatus: () => client.get('/hunt/status'),
  getConfig: () => client.get('/get-hunt-config'),
  setConfig: (config) => client.post('/set-hunt-config', config),
  getListings: (params) => client.get('/hunt/listings', { params }),
  runCrawl: (params) => client.post('/run-crawl', null, { params }),
};

export const listingApi = {
  getDetail: (id) => client.get(`/listings/${id}`),
};

export const marketApi = {
  getTrend: (params) => client.get('/market/trend', { params }),
  getDistricts: () => client.get('/market/districts'),
};

export default client;
