import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAdminAuth } from '../contexts/AdminAuthContext';

export default function Sidebar() {
  const { logout } = useAdminAuth();
  const navigate = useNavigate();

  const handleLogout = (e) => {
    e.preventDefault();
    logout();
    navigate('/admin/login');
  };

  const navItems = [
    { to: '/admin',               label: 'Dashboard',        icon: 'dashboard',               end: true },
    { to: '/admin/campaigns',     label: 'Campaigns',        icon: 'campaign' },
    { to: '/admin/events', label: 'Events', icon: 'event' },
    { to: '/admin/calls',         label: 'Calls',            icon: 'call' },
    { to: '/admin/clients',       label: 'Clients',          icon: 'groups' },
    { to: '/admin/bot-configs',   label: 'Bot Configuration',icon: 'settings' },
    { to: '/admin/script-configs',label: 'Script Templates', icon: 'integration_instructions' },
    { to: '/admin/webhooks',      label: 'Webhooks',         icon: 'webhook' },
    { to: '/admin/diagnostics',   label: 'Diagnostics',      icon: 'monitor_heart' },
  ];

  return (
    <aside className="admin-sidebar">
      {/* Logo / brand */}
      <div className="admin-sidebar__logo">
        <div style={{ fontFamily: 'var(--admin-font-display)', fontSize: '11px', fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--admin-text-muted)', marginBottom: '6px' }}>
          Management
        </div>
        <div className="admin-sidebar__brand">Aakashvani Admin</div>
        <div className="admin-sidebar__tagline">Global Control Console</div>
      </div>

      {/* Navigation */}
      <nav className="admin-sidebar__nav" aria-label="Admin navigation">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              `sidebar-nav-item${isActive ? ' active' : ''}`
            }
          >
            <span className="material-symbols-outlined">{item.icon}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer: Logout */}
      <div className="admin-sidebar__footer">
        <a
          href="#"
          onClick={handleLogout}
          className="sidebar-nav-item"
          style={{ color: 'var(--admin-text-muted)' }}
        >
          <span className="material-symbols-outlined">logout</span>
          <span>Logout</span>
        </a>
      </div>
    </aside>
  );
}
