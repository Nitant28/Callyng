import React from 'react';
import SearchBar from './SearchBar';
import ThemeToggle from './ThemeToggle';

export default function Topbar({ 
  searchQuery = '', 
  onSearchChange = null, 
  clientName = 'Aakashvani Admin' 
}) {
  return (
    <header className="admin-topbar">
      {onSearchChange ? (
        <SearchBar value={searchQuery} onChange={onSearchChange} placeholder="Search anything..." />
      ) : (
        <div className="w-64"></div> /* spacer if no search bar is needed */
      )}

      {/* Flex Spacer */}
      <div className="flex-1"></div>

      {/* User Actions */}
      <div className="flex items-center gap-4">
        {/* Client Name */}
        <span className="font-label-md text-label-md text-on-surface dark:text-molten-text">
          {clientName}
        </span>

        {/* Avatar */}
        <div className="w-8 h-8 rounded-full bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary flex items-center justify-center font-bold text-sm border border-primary/20 dark:border-molten-primary/20 select-none">
          {clientName.split(' ').map(n => n[0]).join('').substring(0, 2).toUpperCase()}
        </div>

        {/* Theme Toggle */}
        <ThemeToggle />
      </div>
    </header>
  );
}
