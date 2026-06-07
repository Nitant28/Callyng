import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const clientApi = axios.create({
  baseURL: API_BASE_URL,
});

clientApi.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('client_api_key');
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});

export default clientApi;
