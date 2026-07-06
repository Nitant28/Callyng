import { Button } from '../../../components/enterprise';
import { campaignLabel, STATUS_OPTIONS } from './leadUtils';

const LeadToolbar = ({
  search,
  onSearchChange,
  filters,
  onFilterChange,
  onResetFilters,
  campaigns,
  onImport,
  onExport,
  onAddLead,
  exporting,
}) => (
  <div className="lead-sheet__toolbar">
    <div className="lead-sheet__toolbar-left">
      <label className="lead-sheet__search">
        <span className="material-symbols-outlined">search</span>
        <input
          type="search"
          placeholder="Search name, phone, email, campaign…"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
        />
      </label>
    </div>
    <div className="lead-sheet__toolbar-mid">
      <select
        className="lead-sheet__select"
        value={filters.campaignId}
        onChange={(e) => onFilterChange({ campaignId: e.target.value })}
      >
        <option value="">All campaigns</option>
        {(campaigns || []).map((c) => (
          <option key={c.id} value={c.id}>{campaignLabel(c)}</option>
        ))}
      </select>
      <select
        className="lead-sheet__select"
        value={filters.status}
        onChange={(e) => onFilterChange({ status: e.target.value })}
      >
        {STATUS_OPTIONS.map((o) => (
          <option key={o.value || 'all'} value={o.value}>{o.label}</option>
        ))}
      </select>
      <button type="button" className="lead-sheet__reset" onClick={onResetFilters}>
        Reset filters
      </button>
    </div>
    <div className="lead-sheet__toolbar-right">
      <Button variant="secondary" size="sm" loading={exporting} onClick={onExport}>Export CSV</Button>
      <Button variant="secondary" size="sm" icon="upload_file" onClick={onImport}>Upload CSV</Button>
      <Button variant="primary" size="sm" icon="add" onClick={onAddLead}>Add Lead</Button>
    </div>
  </div>
);

export default LeadToolbar;
