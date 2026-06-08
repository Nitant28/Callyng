import axios from 'axios';
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:7860';

const adminApi = axios.create({
  baseURL: API_BASE_URL,
});

adminApi.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('admin_api_key');
  if (apiKey) {
    config.headers['X-Admin-Key'] = apiKey;
  }
  return config;
});

export default adminApi;
