import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

let globalAdminKey = null;
let logoutCallback = null;

export function setGlobalAdminKey(key) {
  globalAdminKey = key;
}

export function registerLogoutCallback(cb) {
  logoutCallback = cb;
}

const adminApi = axios.create({
  baseURL: API_BASE_URL,
});

adminApi.interceptors.request.use((config) => {
  // If the request starts with /admin/, map it to /internal/
  if (config.url && config.url.startsWith('/admin/')) {
    config.url = config.url.replace('/admin/', '/internal/');
  }
  
  // Attach X-Admin-Key header on all /internal/* calls
  if (globalAdminKey && (config.url?.startsWith('/internal/') || config.url?.includes('/internal/'))) {
    config.headers['X-Admin-Key'] = globalAdminKey;
  }
  return config;
});

adminApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && (error.response.status === 403 || error.response.status === 503)) {
      if (logoutCallback) {
        logoutCallback();
      }
      if (window.location.pathname !== '/admin/login') {
        window.location.href = '/admin/login';
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

export async function apiFetch(path, options = {}, adminKey = globalAdminKey) {
  let urlPath = path;
  if (urlPath.startsWith('/admin/')) {
    urlPath = urlPath.replace('/admin/', '/internal/');
  }
  
  const url = `${API_BASE_URL}${urlPath}`;
  
  const headers = {
    ...options.headers,
  };
  
  if (adminKey && (urlPath.startsWith('/internal/') || urlPath.includes('/internal/'))) {
    headers['X-Admin-Key'] = adminKey;
  }
  
  let body = options.body;
  if (body && typeof body === 'object' && !(body instanceof FormData)) {
    body = JSON.stringify(body);
    headers['Content-Type'] = headers['Content-Type'] || 'application/json';
  }
  
  const fetchOptions = {
    ...options,
    headers,
    body,
  };
  
  try {
    const response = await fetch(url, fetchOptions);
    
    if (!response.ok) {
      if (response.status === 403 || response.status === 503) {
        if (logoutCallback) {
          logoutCallback();
        }
        if (window.location.pathname !== '/admin/login') {
          window.location.href = '/admin/login';
        }
      }
      
      let errorMessage = `HTTP error! status: ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData?.detail) {
          if (typeof errorData.detail === 'string') {
            errorMessage = errorData.detail;
          } else if (Array.isArray(errorData.detail)) {
            errorMessage = errorData.detail.map(e => e.msg).join(', ');
          }
        }
      } catch (e) {
        // Ignore JSON parse error
      }
      
      const error = new Error(errorMessage);
      error.status = response.status;
      throw error;
    }
    
    return response;
  } catch (error) {
    throw error;
  }
}

export default adminApi;
