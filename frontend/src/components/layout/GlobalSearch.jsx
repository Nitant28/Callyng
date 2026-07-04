import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDashboardData } from '../../contexts/DashboardDataContext';
import './GlobalSearch.css';

const SECTIONS = [
  { id: 'campaigns', label: 'Campaigns', icon: 'campaign' },
  { id: 'calls', label: 'Calls', icon: 'call' },
];

const GlobalSearch = ({ open, onClose }) => {
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef(null);
  const navigate = useNavigate();
  const { campaigns, calls } = useDashboardData();

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];

    const items = [];

    (campaigns ?? []).forEach((c) => {
      if (c.title?.toLowerCase().includes(q)) {
        items.push({
          id: `campaign-${c.id}`,
          type: 'Campaign',
          title: c.title,
          subtitle: `Status: ${c.status}`,
          path: `/app/campaigns/${c.id}`,
          icon: 'campaign',
        });
      }
    });

    (calls ?? []).forEach((call) => {
      if (
        call.leadName?.toLowerCase().includes(q) ||
        call.outcome?.toLowerCase().includes(q)
      ) {
        items.push({
          id: `call-${call.sessionCallId}`,
          type: 'Call',
          title: call.leadName,
          subtitle: call.outcome ?? 'Call log',
          path: call.campaignId ? `/app/campaigns/${call.campaignId}/calls` : '/app/campaigns',
          icon: 'call',
        });
      }
    });

    return items.slice(0, 8);
  }, [query, campaigns, calls]);

  useEffect(() => {
    if (open) {
      setQuery('');
      setActiveIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    const onKey = (e) => {
      if (!open) return;
      if (e.key === 'Escape') onClose();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, Math.max(results.length - 1, 0)));
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      }
      if (e.key === 'Enter' && results[activeIndex]) {
        navigate(results[activeIndex].path);
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, results, activeIndex, navigate, onClose]);

  if (!open) return null;

  return (
    <div className="gs-overlay" onClick={onClose} role="presentation">
      <div className="gs-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Search">
        <div className="gs-input-wrap">
          <span className="material-symbols-outlined">search</span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setActiveIndex(0); }}
            placeholder="Search campaigns and calls..."
          />
          <kbd>Esc</kbd>
        </div>

        <div className="gs-sections">
          {SECTIONS.map((s) => (
            <span key={s.id} className="gs-section-chip">
              <span className="material-symbols-outlined">{s.icon}</span>
              {s.label}
            </span>
          ))}
        </div>

        <div className="gs-results">
          {query && results.length === 0 && (
            <p className="gs-empty">No results for &ldquo;{query}&rdquo;</p>
          )}
          {results.map((item, i) => (
            <button
              key={item.id}
              type="button"
              className={`gs-result ${i === activeIndex ? 'gs-result--active' : ''}`}
              onClick={() => { navigate(item.path); onClose(); }}
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <div>
                <p>{item.title}</p>
                <span>{item.type} · {item.subtitle}</span>
              </div>
            </button>
          ))}
          {!query && (
            <p className="gs-hint">Type to search across your workspace</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default GlobalSearch;
