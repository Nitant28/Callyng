import { useState, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import Sidebar from './Sidebar';
import { DashboardDataProvider, useDashboardData } from '../../contexts/DashboardDataContext';
import { SIDEBAR_NAV } from '../../constants/sidebar';
import '../../client/styles/shell.css';

const MobileNav = () => {
  const location = useLocation();
  const path = location.pathname;

  return (
    <nav
      style={{
        display: 'none',
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        background: '#FFFFFF',
        borderTop: '1px solid #E2E8F0',
        justifyContent: 'space-around',
        padding: '12px 0',
        zIndex: 50,
      }}
      className="md:hidden"
      aria-label="Mobile navigation"
    >
      {SIDEBAR_NAV.map((item) => {
        const isActive = item.match(path);
        return (
          <Link
            key={item.id}
            to={item.path}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              color: isActive ? '#2563EB' : '#64748B',
              textDecoration: 'none',
              fontSize: '11px',
              fontWeight: isActive ? 600 : 500,
            }}
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
};

const MainLayoutInner = ({ children }) => {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { balance } = useDashboardData();
  const clientName = balance?.client_name || localStorage.getItem('client_name') || 'Client';
  const searchRef = useRef(null);

  const handleSignOut = () => {
    localStorage.removeItem('client_api_key');
    localStorage.removeItem('client_name');
    window.location.href = '/login';
  };

  /* Ctrl+K / Cmd+K search focus shortcut */
  useEffect(() => {
    const handler = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const initials = clientName
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="client-app">
      {/* Dark Sidebar */}
      <Sidebar onSignOut={handleSignOut} isOpen={sidebarOpen} />

      {/* Overlay for mobile drawer */}
      {sidebarOpen && (
        <button
          type="button"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.3)',
            zIndex: 45,
            border: 'none',
          }}
          onClick={() => setSidebarOpen(false)}
          aria-label="Close menu"
        />
      )}

      {/* Top Navbar */}
      <header className="cl-topbar">
        {/* Mobile menu toggle */}
        <button
          type="button"
          onClick={() => setSidebarOpen((v) => !v)}
          style={{
            background: 'none',
            border: 'none',
            color: '#64748B',
            cursor: 'pointer',
            padding: '4px',
            marginRight: '8px',
          }}
          className="lg:hidden"
          aria-label="Toggle menu"
        >
          <span className="material-symbols-outlined" style={{ fontSize: '24px' }}>menu</span>
        </button>

        {/* Global Search Bar (56px tall with Ctrl K aligned) */}
        <div className="cl-topbar__search">
          <span className="material-symbols-outlined cl-topbar__search-icon">search</span>
          <input
            ref={searchRef}
            type="search"
            className="cl-topbar__search-input"
            placeholder="Search anything..."
            aria-label="Search"
          />
          <span className="cl-topbar__kbd">⌘K</span>
        </div>

        <div className="cl-topbar__spacer" />

        {/* Client Name + Avatar */}
        <div className="cl-topbar__user">
          <div style={{ textAlign: 'right' }}>
            <div className="cl-topbar__client-name">{clientName}</div>
            <div className="cl-topbar__client-plan">Enterprise Plan</div>
          </div>
          <div className="cl-topbar__avatar" aria-label={`Avatar for ${clientName}`}>
            {initials}
          </div>
        </div>
      </header>

      {/* Main content right of sidebar, below topbar */}
      <main className="cl-main">
        <div className="max-w-container-max mx-auto">
          {children}
        </div>
      </main>

      {/* Mobile nav */}
      <MobileNav />
    </div>
  );
};

const MainLayout = ({ children }) => (
  <DashboardDataProvider>
    <MainLayoutInner>{children}</MainLayoutInner>
  </DashboardDataProvider>
);

export default MainLayout;
