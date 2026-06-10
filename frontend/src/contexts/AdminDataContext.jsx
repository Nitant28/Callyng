import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import adminApi from '../api/admin';
import { useAdminAuth } from './AdminAuthContext';

const AdminDataContext = createContext(null);

export function AdminDataProvider({ children }) {
  const { isAuthenticated } = useAdminAuth();
  
  const [clients, setClients] = useState([]);
  const [botConfigs, setBotConfigs] = useState([]);
  
  // Maps for fast O(1) lookup
  const [clientsMap, setClientsMap] = useState({});
  const [botConfigsMap, setBotConfigsMap] = useState({});

  const [loading, setLoading] = useState(false);

  const fetchClients = useCallback(async () => {
    try {
      const res = await adminApi.get('/internal/clients');
      const data = res.data?.clients || [];
      setClients(data);
      const map = {};
      data.forEach(c => { map[c.id] = c; });
      setClientsMap(map);
    } catch (err) {
      console.warn('Failed to fetch clients context', err);
    }
  }, []);

  const fetchBotConfigs = useCallback(async () => {
    try {
      const res = await adminApi.get('/internal/bot-configs');
      const data = res.data?.bot_configs || [];
      setBotConfigs(data);
      const map = {};
      data.forEach(b => { map[b.id] = b; });
      setBotConfigsMap(map);
    } catch (err) {
      console.warn('Failed to fetch bot configs context', err);
    }
  }, []);

  const refreshData = useCallback(async () => {
    if (!isAuthenticated) return;
    setLoading(true);
    await Promise.all([fetchClients(), fetchBotConfigs()]);
    setLoading(false);
  }, [isAuthenticated, fetchClients, fetchBotConfigs]);

  useEffect(() => {
    if (isAuthenticated) {
      refreshData();
    } else {
      setClients([]);
      setBotConfigs([]);
      setClientsMap({});
      setBotConfigsMap({});
    }
  }, [isAuthenticated, refreshData]);

  return (
    <AdminDataContext.Provider 
      value={{ 
        clients, 
        botConfigs, 
        clientsMap, 
        botConfigsMap, 
        refreshData,
        loading 
      }}
    >
      {children}
    </AdminDataContext.Provider>
  );
}

export function useAdminData() {
  const context = useContext(AdminDataContext);
  if (!context) {
    throw new Error('useAdminData must be used within an AdminDataProvider');
  }
  return context;
}
