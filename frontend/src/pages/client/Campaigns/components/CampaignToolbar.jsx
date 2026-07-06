import { Tabs } from '../../../../components/enterprise';
import './CampaignToolbar.css';

const SORT_OPTIONS = [
  { value: 'newest', label: 'Newest' },
  { value: 'oldest', label: 'Oldest' },
  { value: 'name', label: 'Name' },
  { value: 'leads', label: 'Leads' },
  { value: 'credits', label: 'Credits used' },
];

const CampaignToolbar = ({
  search,
  onSearchChange,
  sortBy,
  onSortChange,
  tabs,
  activeTab,
  onTabChange,
  selectedCount,
  onBulkPause,
  onBulkResume,
  onBulkCancel,
  onBulkExport,
}) => (
  <div className="cmp-toolbar">
    <div className="cmp-toolbar__row">
      <div className="cmp-toolbar__search">
        <span className="material-symbols-outlined">search</span>
        <input
          type="search"
          placeholder="Search campaigns, IDs…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </div>
      <select
        className="cmp-toolbar__select"
        value={sortBy}
        onChange={(e) => onSortChange(e.target.value)}
        aria-label="Sort campaigns"
      >
        {SORT_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>

    <Tabs tabs={tabs} value={activeTab} onChange={onTabChange} />

    {selectedCount > 0 && onBulkPause && (
      <div className="cmp-toolbar__bulk">
        <span>{selectedCount} selected</span>
        <button type="button" onClick={onBulkPause}>Pause</button>
        <button type="button" onClick={onBulkResume}>Resume</button>
        <button type="button" onClick={onBulkExport}>Export</button>
        <button type="button" className="cmp-toolbar__bulk-danger" onClick={onBulkCancel}>
          Cancel
        </button>
      </div>
    )}
  </div>
);

export default CampaignToolbar;
