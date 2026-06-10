import axios from 'axios';
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:7860';

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
      // Don't loop infinitely if we're already on login
      if (window.location.pathname !== '/login') {
        localStorage.removeItem('client_api_key');
        window.location.href = '/login';
      }
    }
    
    // Parse backend error detail
    if (error.response?.data?.detail) {
      const detail = error.response.data.detail;
      if (typeof detail === 'string') {
        error.customErrorMessage = detail;
      } else if (Array.isArray(detail)) {
        error.customErrorMessage = detail.map(e => e.msg).join(', ');
      }
    }
    
    return Promise.reject(error);
  }
);

export default clientApi;
