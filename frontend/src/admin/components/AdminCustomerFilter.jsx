import React, { useEffect, useMemo, useRef, useState } from 'react';

export default function AdminCustomerFilter({ clients = [], value, onChange, className = '' }) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);

  const selected = useMemo(
    () => clients.find((c) => String(c.id) === String(value)),
    [clients, value],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return clients;
    return clients.filter((c) => (c.name || '').toLowerCase().includes(q));
  }, [clients, query]);

  useEffect(() => {
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  return (
    <div ref={wrapRef} className={`relative shrink-0 ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="h-10 w-[200px] px-3 bg-surface-container-lowest dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm text-on-surface dark:text-molten-text text-left flex items-center justify-between gap-2"
        aria-label="Filter by customer"
      >
        <span className="truncate">{selected?.name || 'All Customers'}</span>
        <span className="material-symbols-outlined text-[18px] shrink-0">expand_more</span>
      </button>
      {open && (
        <div className="absolute z-50 right-0 mt-1 w-[240px] bg-surface-container-lowest dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg shadow-lg overflow-hidden">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search customers..."
            className="w-full px-3 py-2 text-sm border-b border-outline-variant dark:border-[#2A345E] bg-transparent text-on-surface dark:text-molten-text focus:outline-none"
          />
          <ul className="max-h-56 overflow-y-auto py-1">
            <li>
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-surface-container dark:hover:bg-[#2A345E]/50 text-on-surface dark:text-molten-text"
                onClick={() => {
                  onChange('');
                  setOpen(false);
                  setQuery('');
                }}
              >
                All Customers
              </button>
            </li>
            {filtered.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm hover:bg-surface-container dark:hover:bg-[#2A345E]/50 text-on-surface dark:text-molten-text"
                  onClick={() => {
                    onChange(c.id);
                    setOpen(false);
                    setQuery('');
                  }}
                >
                  {c.name}
                </button>
              </li>
            ))}
            {filtered.length === 0 && (
              <li className="px-3 py-2 text-sm text-on-surface-variant dark:text-molten-text-muted">
                No customers match
              </li>
            )}
          </ul>
        </div>
      )}
    </div>
  );
}
