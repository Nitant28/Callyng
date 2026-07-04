import axios from 'axios';
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const clientApi = axios.create({
  baseURL: API_BASE_URL,
});

clientApi.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('client_api_key');
  if (apiKey && !config.headers.Authorization) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});

clientApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && (error.response.status === 401 || error.response.status === 403)) {
      const path = window.location.pathname;
      // Only redirect away from protected client routes (not login itself).
      if (path.startsWith('/app')) {
        localStorage.removeItem('client_api_key');
        localStorage.removeItem('client_name');
        window.location.href = '/login';
      }
    }
    
    // Parse backend error detail
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      if (typeof detail === 'string') {
        error.customErrorMessage = detail;
      } else if (Array.isArray(detail)) {
        error.customErrorMessage = detail.map((e) => e.msg || String(e)).join(', ');
      } else if (detail && typeof detail === 'object') {
        if (Array.isArray(detail.errors)) {
          error.customErrorMessage = detail.errors
            .map((e) => (typeof e === 'string' ? e : e.msg || JSON.stringify(e)))
            .join('; ');
        } else {
          error.customErrorMessage = detail.message || JSON.stringify(detail);
        }
      }
    }
    
    return Promise.reject(error);
  }
);

export default clientApi;
