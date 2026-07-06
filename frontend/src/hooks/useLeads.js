import { useCallback, useEffect, useState } from 'react';
import leadService from '../services/leadService';
import { pinCallingLeadsFirst } from '../pages/client/LeadSheet/leadUtils';

const DEBOUNCE_MS = 400;
const LIVE_POLL_MS = 4000;

export function useLeads(initialFilters = {}, { live = false } = {}) {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [pages, setPages] = useState(1);
  const [page, setPage] = useState(1);
  const [limit, setLimit] = useState(50);
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [filters, setFilters] = useState({
    campaignId: '',
    status: '',
    ...initialFilters,
  });
  const [sort, setSort] = useState({ field: 'created_at', direction: 'desc' });
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [statsLoading, setStatsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selected, setSelected] = useState(() => new Set());
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, filters.campaignId, filters.status, limit]);

  const loadStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      const data = await leadService.stats({ campaignId: filters.campaignId || undefined });
      setStats(data);
    } catch {
      setStats(null);
    } finally {
      setStatsLoading(false);
    }
  }, [filters.campaignId, refreshKey]);

  const loadLeads = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await leadService.list({
        page,
        limit,
        search: debouncedSearch,
        campaignId: filters.campaignId || undefined,
        status: filters.status || undefined,
        sort: sort.field,
        order: sort.direction,
      });

      let displayRows = data.rows;
      if (live && !filters.status) {
        try {
          const callingBatch = await leadService.list({
            page: 1,
            limit: 25,
            search: debouncedSearch,
            campaignId: filters.campaignId || undefined,
            status: 'calling',
            sort: sort.field,
            order: sort.direction,
          });
          const seen = new Set();
          displayRows = pinCallingLeadsFirst([
            ...callingBatch.rows,
            ...data.rows.filter((r) => r.status !== 'calling'),
          ].filter((r) => {
            if (seen.has(r.id)) return false;
            seen.add(r.id);
            return true;
          }));
        } catch {
          displayRows = pinCallingLeadsFirst(data.rows);
        }
      } else if (live) {
        displayRows = pinCallingLeadsFirst(data.rows);
      }

      setRows(displayRows);
      setTotal(data.total);
      setPages(data.pages);
      setSelected(new Set());
    } catch (err) {
      setError(err.customErrorMessage || err.message || 'Failed to load leads');
      setRows([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, limit, debouncedSearch, filters, sort, refreshKey, live]);

  useEffect(() => {
    loadStats();
  }, [loadStats]);

  useEffect(() => {
    loadLeads();
  }, [loadLeads]);

  useEffect(() => {
    if (!live) return undefined;
    const interval = setInterval(() => {
      setRefreshKey((k) => k + 1);
    }, LIVE_POLL_MS);
    return () => clearInterval(interval);
  }, [live]);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const toggleSort = useCallback((field) => {
    setSort((prev) => {
      if (prev.field === field) {
        return { field, direction: prev.direction === 'asc' ? 'desc' : 'asc' };
      }
      return { field, direction: 'desc' };
    });
  }, []);

  const resetFilters = useCallback(() => {
    setFilters({ campaignId: '', status: '' });
    setSearch('');
  }, []);

  const toggleSelect = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelected((prev) => {
      if (prev.size === rows.length) return new Set();
      return new Set(rows.map((r) => r.id));
    });
  }, [rows]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  return {
    rows,
    total,
    pages,
    page,
    limit,
    search,
    setSearch,
    filters,
    setFilters,
    sort,
    toggleSort,
    loading,
    stats,
    statsLoading,
    error,
    selected,
    toggleSelect,
    toggleSelectAll,
    setPage,
    setLimit,
    resetFilters,
    refresh,
    clearSelection,
  };
}

export default useLeads;
