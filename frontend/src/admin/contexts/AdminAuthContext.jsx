import React, { createContext, useContext, useState, useEffect } from 'react';
import { setGlobalAdminKey, registerLogoutCallback } from '../../shared/api/admin';

const AdminAuthContext = createContext(null);

export function AdminAuthProvider({ children }) {
  const [adminKey, setAdminKey] = useState(() => {
    const saved = localStorage.getItem('aakashvani_admin_key');
    if (saved) {
      setGlobalAdminKey(saved);
      return saved;
    }
    return null;
  });

  const login = (key) => {
    localStorage.setItem('aakashvani_admin_key', key);
    setAdminKey(key);
    setGlobalAdminKey(key);
  };

  const logout = () => {
    localStorage.removeItem('aakashvani_admin_key');
    setAdminKey(null);
    setGlobalAdminKey(null);
  };

  const isAuthenticated = !!adminKey;

  // Register the logout callback to clear state when Axios receives 403 or 503
  useEffect(() => {
    registerLogoutCallback(logout);
    return () => {
      registerLogoutCallback(null);
    };
  }, []);

  return (
    <AdminAuthContext.Provider value={{ adminKey, login, logout, isAuthenticated }}>
      {children}
    </AdminAuthContext.Provider>
  );
}

export function useAdminAuth() {
  const context = useContext(AdminAuthContext);
  if (!context) {
    throw new Error('useAdminAuth must be used within an AdminAuthProvider');
  }
  return context;
}
