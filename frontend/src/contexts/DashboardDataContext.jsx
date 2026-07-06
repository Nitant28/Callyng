import { createContext, useContext } from 'react';
import useDashboardSource from '../client/hooks/useDashboardData';

const DashboardDataContext = createContext(null);

export function DashboardDataProvider({ children }) {
  const value = useDashboardSource();
  return (
    <DashboardDataContext.Provider value={value}>
      {children}
    </DashboardDataContext.Provider>
  );
}

export function useDashboardData() {
  const ctx = useContext(DashboardDataContext);
  if (!ctx) {
    throw new Error('useDashboardData must be used within DashboardDataProvider');
  }
  return ctx;
}
