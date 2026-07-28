import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useToast } from '../../../contexts/ToastContext';
import { useCampaigns } from '../../../hooks/useCampaigns';
import {
  filterCampaigns,
  sortCampaigns,
  tabCounts,
} from '../../../utils/campaignHelpers';
import CampaignHeader from './components/CampaignHeader';
import CampaignToolbar from './components/CampaignToolbar';
import CampaignGrid from './components/CampaignGrid';
// CreateCampaignModal intentionally omitted from client UI
import './Campaigns.css';

const PAGE_SIZE = 25;

const CampaignsPage = () => {
  const navigate = useNavigate();
  const { showToast } = useToast();
  const {
    campaigns,
    loading,
    refreshing,
    error,
    botOptions,
    refresh,
  } = useCampaigns();

  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('newest');
  const [activeTab, setActiveTab] = useState('all');
  const [page, setPage] = useState(0);

  const counts = useMemo(() => tabCounts(campaigns), [campaigns]);
  const botNameById = useMemo(() => {
    const map = {};
    botOptions.forEach((b) => {
      map[b.id] = b.name;
    });
    return map;
  }, [botOptions]);
  const tabs = useMemo(
    () => [
      { id: 'all', label: 'All', count: counts.all },
      { id: 'running', label: 'Running', count: counts.running },
      { id: 'paused', label: 'Paused', count: counts.paused },
      { id: 'draft', label: 'Draft', count: counts.draft },
      { id: 'completed', label: 'Completed', count: counts.completed },
    ],
    [counts],
  );

  const filtered = useMemo(() => {
    const list = filterCampaigns(campaigns, { tab: activeTab, search });
    return sortCampaigns(list, sortBy);
  }, [campaigns, activeTab, search, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paged = filtered.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);

  // CSV export is disabled in client UI by design.

  // Campaign creation UI removed from client; server-admin flows only.

  return (
    <div className="cl-page-container app-page cmp-page">
      <CampaignHeader onRefresh={() => refresh(true)} refreshing={refreshing} />

      {error && <p className="cmp-page__error">{error}</p>}

      <CampaignToolbar
        search={search}
        onSearchChange={(v) => { setSearch(v); setPage(0); }}
        sortBy={sortBy}
        onSortChange={setSortBy}
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={(t) => { setActiveTab(t); setPage(0); }}
      />

      <CampaignGrid
        campaigns={paged}
        loading={loading}
        botNameById={botNameById}
        onOpen={(c) => navigate(`/app/campaigns/${c.id}`)}
        activeTab={activeTab}
      />

      {!loading && filtered.length > PAGE_SIZE && (
        <footer className="cmp-page__pagination">
          <span>
            Showing {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} of {filtered.length}
          </span>
          <div>
            <button type="button" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Previous</button>
            <button type="button" disabled={page >= totalPages - 1} onClick={() => setPage((p) => p + 1)}>Next</button>
          </div>
        </footer>
      )}
    </div>
  );
};

export default CampaignsPage;
