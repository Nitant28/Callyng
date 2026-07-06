import React from 'react';
import { useTheme } from '../../hooks/useTheme';

export const ThemeToggle = ({ className = '' }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className={`p-2 rounded-lg bg-surface-container dark:bg-molten-surface text-primary dark:text-molten-primary hover:opacity-80 transition-all active:scale-95 cursor-pointer ${className}`}
      aria-label="Toggle Theme"
    >
      <span className="material-symbols-outlined">
        {theme === 'dark' ? 'light_mode' : 'dark_mode'}
      </span>
    </button>
  );
};
