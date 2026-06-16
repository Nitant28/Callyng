import React from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useTheme } from '../../../hooks/useTheme';
import { useAdminAuth } from '../../../contexts/AdminAuthContext';

export default function AdminLayout({ children }) {
  const { theme, toggleTheme } = useTheme();
  const { logout } = useAdminAuth();
  const navigate = useNavigate();

  const handleLogout = (e) => {
    e.preventDefault();
    logout();
    navigate('/admin/login');
  };

  return (
    <div className="bg-arctic-bg dark:bg-molten-bg transition-colors duration-300 min-h-screen flex flex-col">
      {/* TopNavBar Shell */}
      <header className="fixed top-0 w-full z-50 bg-arctic-bg dark:bg-molten-bg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:border-b dark:border-[#2A345E] transition-all duration-200">
        <div className="flex justify-between items-center h-16 px-gutter max-w-container-max mx-auto">
          <div className="flex items-center gap-4">
            <span className="font-headline-lg text-headline-lg font-extrabold tracking-tighter text-primary dark:text-molten-primary">
              Aakashvani Admin
            </span>
          </div>
          <div className="flex items-center gap-4">
            {/* Theme Toggle */}
            <button 
              className="p-2 rounded-lg text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest transition-all duration-200 active:scale-95"
              onClick={toggleTheme}
            >
              <span className="material-symbols-outlined">
                {theme === 'dark' ? 'light_mode' : 'dark_mode'}
              </span>
            </button>
            {/* Profile and settings icons removed from header */}
          </div>
        </div>
      </header>

      <div className="flex pt-16 flex-1">
        {/* SideNavBar Shell */}
        <aside className="hidden md:flex flex-col h-[calc(100vh-64px)] w-64 fixed left-0 bg-surface dark:bg-molten-bg border-r border-outline-variant dark:border-[#2A345E] py-6 space-y-4">
          <div className="px-6 mb-4">
            <h3 className="font-headline-sm text-headline-sm font-bold text-primary dark:text-molten-primary">Management</h3>
            <p className="font-label-md text-label-md text-on-surface-variant dark:text-molten-text-muted">Global Control Console</p>
          </div>
          <nav className="flex-1 px-2 space-y-1">
            <NavLink 
              to="/admin"
              end
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">dashboard</span>
              <span className="font-label-md text-label-md">Dashboard</span>
            </NavLink>
            <NavLink 
              to="/admin/campaigns"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">campaign</span>
              <span className="font-label-md text-label-md">Campaigns</span>
            </NavLink>
            <NavLink 
              to="/admin/calls"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">call</span>
              <span className="font-label-md text-label-md">Calls</span>
            </NavLink>
            <NavLink 
              to="/admin/clients"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">groups</span>
              <span className="font-label-md text-label-md">Clients</span>
            </NavLink>
            <NavLink 
              to="/admin/bot-configs"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">settings</span>
              <span className="font-label-md text-label-md">Bot Configuration</span>
            </NavLink>
            <NavLink 
              to="/admin/script-configs"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">integration_instructions</span>
              <span className="font-label-md text-label-md">Script Templates</span>
            </NavLink>
            <NavLink 
              to="/admin/webhooks"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">webhook</span>
              <span className="font-label-md text-label-md">Webhooks</span>
            </NavLink>
            <NavLink 
              to="/admin/diagnostics"
              className={({ isActive }) => `flex items-center rounded-lg px-4 py-3 transition-transform hover:translate-x-1 ${isActive ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest'}`}
            >
              <span className="material-symbols-outlined mr-3">monitor_heart</span>
              <span className="font-label-md text-label-md">Diagnostics</span>
            </NavLink>
          </nav>
          
          <div className="px-4 mt-auto space-y-1 pt-4 border-t border-outline-variant dark:border-[#2A345E]">
            {/* Support section removed from footer */}
            <a href="#" onClick={handleLogout} className="flex items-center text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-surface-container-highest rounded-lg px-4 py-2 text-sm">
              <span className="material-symbols-outlined mr-3 text-sm">logout</span>
              Logout
            </a>
          </div>
        </aside>

        {/* Main Content Grid */}
        <main className="flex-1 md:ml-64 relative min-h-full flex flex-col">
          <div className="p-gutter max-w-container-max flex-1">
            {children}
          </div>
          
          {/* Footer Shell */}
          <footer className="w-full py-8 mt-auto bg-arctic-bg dark:bg-molten-bg border-t border-outline-variant dark:border-[#2A345E] relative z-10">
            <div className="flex flex-col md:flex-row justify-between items-center px-gutter max-w-container-max mx-auto space-y-4 md:space-y-0">
              <span className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text">Aakashvani</span>
              <div className="flex gap-6 font-body-sm text-body-sm text-on-surface-variant dark:text-molten-text-muted">
                <a href="#" className="hover:text-primary dark:hover:text-molten-success transition-opacity duration-200">Privacy Policy</a>
                <a href="#" className="hover:text-primary dark:hover:text-molten-success transition-opacity duration-200">Terms of Service</a>
                <a href="#" className="hover:text-primary dark:hover:text-molten-success transition-opacity duration-200">API Status</a>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant dark:text-molten-text-muted">© 2026 Aakashvani. All rights reserved.</p>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
