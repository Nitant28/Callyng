import React from 'react';

export default function SearchBar({ value, onChange, placeholder = 'Search...', className = '' }) {
  return (
    <div className={`relative flex items-center max-w-md w-full ${className}`}>
      <span className="material-symbols-outlined absolute left-3 text-on-surface-variant dark:text-molten-text-muted pointer-events-none select-none">
        search
      </span>
      <input
        type="text"
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className="w-full pl-10 pr-4 py-2 bg-surface-container-low dark:bg-molten-surface border border-outline-variant rounded-lg text-on-background dark:text-molten-text font-body-md focus:outline-none focus:border-primary dark:focus:border-molten-primary transition-colors"
      />
    </div>
  );
}
