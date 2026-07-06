import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import '../client.css';
import Sidebar from '../components/Sidebar';
import clientApi from '../../api/client';

/**
 * ClientLayout
 * ─ Dark sidebar (240px fixed)
 * ─ White topbar (56px) with search + user
 * ─ Content area right of sidebar, below topbar
 */
export default function ClientLayout({ children }) {
  const navigate = useNavigate();
  const [clientName, setClientName] = useState(
    localStorage.getItem('client_name') || 'Client'
  );
  const [balance, setBalance] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const searchRef = useRef(null);

  /* Fetch client name + balance */
  useEffect(() => {
    clientApi.get('/api/credits').then(res => {
      if (res.data) {
        const name = res.data.client_name || clientName;
        setClientName(name);
        localStorage.setItem('client_name', name);
        setBalance(res.data.balance_credits ?? null);
      }
    }).catch(() => {});
  }, []); // eslint-disable-line

  /* Ctrl+K to focus search */
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

  const handleSignOut = () => {
    localStorage.removeItem('client_api_key');
    localStorage.removeItem('client_name');
    window.location.href = '/login';
  };

  /* Avatar initials */
  const initials = clientName
    .split(' ')
    .map(n => n[0])
    .join('')
    .substring(0, 2)
    .toUpperCase();

  return (
    <div className="client-app">
      {/* Sidebar */}
      <Sidebar handleSignOut={handleSignOut} balance={balance} />

      {/* Topbar */}
      <header className="cl-topbar">
        {/* Search */}
        <div className="cl-topbar__search">
          <span className="material-symbols-outlined cl-topbar__search-icon">search</span>
          <input
            ref={searchRef}
            type="search"
            className="cl-topbar__search-input"
            placeholder="Search anything..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            aria-label="Search"
          />
          <span className="cl-topbar__kbd">⌘K</span>
        </div>

        <div className="cl-topbar__spacer" />

        <div className="cl-topbar__spacer" />

        {/* User */}
        <div className="cl-topbar__user">
          <div style={{ position: 'relative', marginRight: '16px', display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
            <span className="material-symbols-outlined" style={{ color: '#64748B', fontSize: '22px' }}>notifications</span>
            <div style={{ position: 'absolute', top: '-2px', right: '-2px', width: '8px', height: '8px', background: '#2563EB', borderRadius: '50%', border: '2px solid #FFF' }}></div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div className="cl-topbar__client-name">{clientName === 'Client' ? 'Dev Client' : clientName}</div>
            <span className="cl-topbar__client-plan">Enterprise Plan</span>
          </div>
          <div className="cl-topbar__avatar" aria-label="Avatar">
            {clientName === 'Client' ? 'DC' : initials}
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="cl-main">
        <div className="cl-content-container">
          {children}
        </div>
      </main>

      {/* Mobile bottom nav */}
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
        <a
          href="/app"
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', color: '#64748B', textDecoration: 'none', fontSize: '11px' }}
        >
          <span className="material-symbols-outlined">dashboard</span>
          Home
        </a>
        <a
          href="/app/campaigns"
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px', color: '#64748B', textDecoration: 'none', fontSize: '11px' }}
        >
          <span className="material-symbols-outlined">campaign</span>
          Campaigns
        </a>
      </nav>
    </div>
  );
}
