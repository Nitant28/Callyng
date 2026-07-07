import React from 'react';
import Sidebar from '../components/Sidebar';
import '../admin.css';

export default function AdminLayout({ children }) {
  return (
    <div className="admin-app">
      {/* Fixed Sidebar */}
      <Sidebar />

      {/* Main content pushed right of sidebar */}
      <main className="admin-layout-main">
        {children}
      </main>
    </div>
  );
}
