import React from 'react';
import { useTheme } from '../hooks/useTheme';

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      id="admin-theme-toggle"
      onClick={toggleTheme}
      aria-label="Toggle theme"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: '36px',
        height: '36px',
        borderRadius: '8px',
        background: 'var(--admin-surface)',
        border: '1px solid var(--admin-border)',
        boxShadow: 'var(--admin-shadow-card)',
        color: 'var(--admin-text-secondary)',
        cursor: 'pointer',
        transition: 'background 0.15s, color 0.15s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--admin-surface-alt)'; e.currentTarget.style.color = 'var(--admin-text-primary)'; }}
      onMouseLeave={e => { e.currentTarget.style.background = 'var(--admin-surface)'; e.currentTarget.style.color = 'var(--admin-text-secondary)'; }}
    >
      <span className="material-symbols-outlined" style={{ fontSize: '20px' }}>
        {theme === 'dark' ? 'light_mode' : 'dark_mode'}
      </span>
    </button>
  );
}
