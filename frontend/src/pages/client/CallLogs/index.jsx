import { useCallback, useEffect, useMemo, useState } from 'react';
import clientApi from '../../../api/client';
import { useDashboardData } from '../../../contexts/DashboardDataContext';
import {
  groupCallsByTimeline,
  mapCallListRow,
} from '../../../utils/callLogsHelpers';
import CallCard from './components/CallCard';
import TranscriptDrawer from './components/TranscriptDrawer';
import SearchBar from './components/SearchBar';
import FilterBar from './components/FilterBar';
import Timeline from './components/Timeline';
import EmptyState from './components/EmptyState';
import LoadingSkeleton from './components/LoadingSkeleton';
import PageHeader from '../../../components/ui/PageHeader';
import './CallLogs.css';

const LIMIT = 25;

const matchesDuration = (seconds, filter) => {
  if (!filter) return true;
  if (filter === 'short') return seconds < 60;
  if (filter === 'medium') return seconds >= 60 && seconds <= 180;
  if (filter === 'long') return seconds > 180;
  return true;
};

const CallLogsPage = () => {
  const { campaigns = [] } = useDashboardData() ?? {};
  const [calls, setCalls] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [filters, setFilters] = useState({
    campaignId: '',
    outcome: '',
    duration: '',
    dateFrom: '',
  });
  const [selected, setSelected] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const campaignMap = useMemo(() => {
    const m = {};
    campaigns.forEach((c) => {
      if (c?.id) m[c.id] = c.title;
    });
    return m;
  }, [campaigns]);

  const loadCalls = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const res = await clientApi.get('/api/calls', {
        params: { limit: LIMIT, offset, search: debouncedSearch || undefined },
      });
      const rows = (res.data?.calls || []).map(mapCallListRow);
      setCalls(rows);
      setTotalCount(res.data?.total_count ?? rows.length);
    } catch (err) {
      console.warn('Failed to load call logs', err);
      setCalls([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [offset, debouncedSearch]);

  useEffect(() => {
    loadCalls();
  }, [loadCalls]);

  useEffect(() => {
    setOffset(0);
  }, [debouncedSearch]);

  const filteredCalls = useMemo(() => {
    return calls.filter((c) => {
      if (filters.campaignId && c.campaignId !== filters.campaignId) return false;
      if (filters.outcome && c.outcome !== filters.outcome) return false;
      if (!matchesDuration(c.durationSeconds, filters.duration)) return false;
      if (filters.dateFrom && c.createdAt) {
        const day = c.createdAt.slice(0, 10);
        if (day < filters.dateFrom) return false;
      }
      return true;
    });
  }, [calls, filters]);

  const groups = useMemo(() => groupCallsByTimeline(filteredCalls), [filteredCalls]);

  const handleOpen = (call) => {
    setSelected(call);
    setDrawerOpen(true);
  };

  const handleExport = () => {
    const header = ['Name', 'Phone', 'Campaign', 'Outcome', 'Duration', 'Cost', 'Time'];
    const lines = filteredCalls.map((c) => [
      c.leadName,
      c.leadPhone,
      campaignMap[c.campaignId] || '',
      c.outcome || '',
      c.durationSeconds,
      c.creditsCharged ?? '',
      c.createdAt || '',
    ]);
    const csv = [header, ...lines].map((r) => r.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(',')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'call-logs.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="app-page cl-page">
      <PageHeader
        eyebrow="Call Logs"
        title="Recent Calls"
        subtitle="Review conversations, recordings, and lead outcomes."
      />

      <div className="cl-toolbar">
        <SearchBar value={search} onChange={setSearch} />
        <FilterBar
          campaigns={campaigns}
          filters={filters}
          onChange={setFilters}
          onExport={handleExport}
          onRefresh={() => loadCalls(true)}
          refreshing={refreshing}
        />
      </div>

      <div className="cl-list">
        {loading && <LoadingSkeleton />}
        {!loading && filteredCalls.length === 0 && <EmptyState />}
        {!loading && groups.map((group) => (
          <section key={group.label}>
            <Timeline label={group.label} />
            <div className="cl-list__cards">
              {group.calls.map((call) => (
                <CallCard
                  key={call.sessionCallId}
                  call={call}
                  campaignName={campaignMap[call.campaignId]}
                  selected={selected?.sessionCallId === call.sessionCallId && drawerOpen}
                  onClick={handleOpen}
                />
              ))}
            </div>
          </section>
        ))}
      </div>

      {!loading && totalCount > LIMIT && (
        <footer className="cl-pagination">
          <span>
            Showing {offset + 1}–{Math.min(offset + LIMIT, totalCount)} of {totalCount}
          </span>
          <div className="cl-pagination__btns">
            <button type="button" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - LIMIT))}>
              <span className="material-symbols-outlined">chevron_left</span>
            </button>
            <button
              type="button"
              disabled={offset + LIMIT >= totalCount}
              onClick={() => setOffset((o) => o + LIMIT)}
            >
              <span className="material-symbols-outlined">chevron_right</span>
            </button>
          </div>
        </footer>
      )}

      <TranscriptDrawer
        open={drawerOpen}
        call={selected}
        campaignName={selected ? campaignMap[selected.campaignId] : ''}
        onClose={() => setDrawerOpen(false)}
      />
    </div>
  );
};

export default CallLogsPage;
