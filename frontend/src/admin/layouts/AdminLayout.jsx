import React from 'react';
import Sidebar from '../components/Sidebar';
import ThemeToggle from '../components/ThemeToggle';
import '../admin.css';

export default function AdminLayout({ children }) {
  return (
    <div className="admin-app">
      {/* Fixed Sidebar */}
      <Sidebar />

      {/* Main content pushed right of sidebar */}
      <main className="admin-layout-main">
        {/* Theme toggle — top-right corner, floating */}
        <div style={{
          position: 'fixed',
          top: '20px',
          right: '24px',
          zIndex: 99,
        }}>
          <ThemeToggle />
        </div>

        {children}
      </main>
    </div>
  );
}
