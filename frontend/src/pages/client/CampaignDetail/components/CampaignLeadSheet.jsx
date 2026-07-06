import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '../../../../components/enterprise';
import clientApi from '../../../../api/client';
import LeadDrawer from '../../LeadSheet/LeadDrawer';
import LeadStatusBadge from '../../LeadSheet/LeadStatusBadge';
import {
  leadInitials,
  fmtDuration,
  fmtRelative,
  parseLeadApiError,
  sortLeadsCallStack,
} from '../../LeadSheet/leadUtils';
import '../../../../components/ui/Table/table.css';
import './CampaignLeadSheet.css';

const PAGE_SIZE = 25;

const FILTER_OPTIONS = [
  { id: 'all', label: 'All' },
  { id: 'interested', label: 'Interested', outcome: 'Interested' },
  { id: 'pending', label: 'Pending', status: 'pending' },
  { id: 'calling', label: 'Calling', status: 'calling' },
  { id: 'failed', label: 'Failed', status: 'failed' },
  { id: 'completed', label: 'Completed', status: 'completed' },
  { id: 'callbacks', label: 'Callbacks', status: 'callback_scheduled' },
];

const mapLead = (row, campaignId, campaignName) => ({
  id: row.id,
  campaignId,
  campaignName,
  name: row.name,
  phone: row.phone,
  status: row.status,
  outcome: row.outcome || row.last_call_outcome,
  attempts: row.attempts ?? 0,
  maxAttempts: row.max_attempts ?? 3,
  metadata: row.metadata || {},
  nextAttemptAt: row.next_attempt_at,
  scheduledCallbackAt: row.scheduled_callback_at,
  lastCalledAt: row.last_call_ended_at || row.last_attempted_at || row.created_at,
  lastCallDurationSeconds: row.last_call_duration_seconds,
  updatedAt: row.last_call_ended_at || row.last_attempted_at || row.created_at,
  sessionCallId: row.session_call_id || null,
  lastCallInProgress: row.last_call_in_progress ?? false,
});

const isLiveCampaign = (status) =>
  status === 'running' || status === 'pausing' || status === 'paused';

const LiveTimer = ({ startedAt }) => {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const start = new Date(startedAt || Date.now()).getTime();
    setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)));
    const interval = setInterval(() => {
      setElapsed(Math.max(0, Math.floor((Date.now() - start) / 1000)));
    }, 1000);
    return () => clearInterval(interval);
  }, [startedAt]);

  const mm = String(Math.floor(elapsed / 60)).padStart(2, '0');
  const ss = String(elapsed % 60).padStart(2, '0');
  return <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#2563EB' }}>{mm}:{ss}</span>;
};

const CampaignLeadSheet = ({
  campaignId,
  campaignName,
  campaignStatus,
  callingLeads = 0,
  initialFilter = 'all',
  externalSearch = '',
  onLeadsChanged,
}) => {
  const fileInputRef = useRef(null);
  const [leads, setLeads] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState('');
  const [activeFilter, setActiveFilter] = useState(initialFilter);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [drawerLead, setDrawerLead] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [, setTick] = useState(0);

  const canImport = campaignStatus === 'draft' || campaignStatus === 'paused';
  const filterDef = FILTER_OPTIONS.find((f) => f.id === activeFilter) || FILTER_OPTIONS[0];

  const loadLeads = useCallback(async (spinner = true) => {
    if (!campaignId) return;
    if (spinner) setLoading(true);
    try {
      const res = await clientApi.get(`/api/campaigns/${campaignId}/leads`, {
        params: {
          limit: PAGE_SIZE,
          offset,
          search: search || undefined,
          status: filterDef.status || undefined,
          outcome: filterDef.outcome || undefined,
        },
      });
      const rows = sortLeadsCallStack(
        (res.data?.leads || []).map((r) => mapLead(r, campaignId, campaignName)),
        { live: isLiveCampaign(campaignStatus) },
      );
      setLeads(rows);
      setTotal(res.data?.total_count || 0);
    } catch {
      setLeads([]);
      setTotal(0);
    } finally {
      if (spinner) setLoading(false);
    }
  }, [campaignId, campaignName, offset, search, filterDef]);

  useEffect(() => {
    const t = setTimeout(() => loadLeads(), 0);
    return () => clearTimeout(t);
  }, [loadLeads]);

  useEffect(() => {
    const t = setTimeout(() => setSearch(externalSearch), 300);
    return () => clearTimeout(t);
  }, [externalSearch]);

  useEffect(() => {
    setActiveFilter(initialFilter);
  }, [initialFilter]);

  useEffect(() => {
    setOffset(0);
  }, [search, activeFilter]);

  useEffect(() => {
    if (!drawerOpen || !drawerLead?.id) return;
    const fresh = leads.find((l) => l.id === drawerLead.id);
    if (fresh) setDrawerLead(fresh);
  }, [leads, drawerOpen, drawerLead?.id]);

  useEffect(() => {
    if (!isLiveCampaign(campaignStatus)) return undefined;
    // Poll faster (2s) when there are live calls so calling leads jump to top immediately
    const pollMs = callingLeads > 0 ? 2000 : 5000;
    const interval = setInterval(() => loadLeads(false), pollMs);
    return () => clearInterval(interval);
  }, [campaignStatus, callingLeads, loadLeads]);

  useEffect(() => {
    if (!isLiveCampaign(campaignStatus)) return undefined;
    const interval = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(interval);
  }, [campaignStatus]);

  const displayLeads = leads;

  const handleExport = async () => {
    setExporting(true);
    try {
      const res = await clientApi.get(`/api/campaigns/${campaignId}/leads/export`, {
        params: {
          search: search || undefined,
          status: filterDef.status || undefined,
          outcome: filterDef.outcome || undefined,
        },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${(campaignName || 'campaign').replace(/\s+/g, '_')}_leads.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.warn('Export failed', err);
    } finally {
      setExporting(false);
    }
  };

  const handleUpload = async (file) => {
    if (!file || !canImport) return;
    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    try {
      await clientApi.post(`/api/campaigns/${campaignId}/leads/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setOffset(0);
      await loadLeads();
      onLeadsChanged?.();
    } catch (err) {
      console.warn('Upload failed', parseLeadApiError(err));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const handleDelete = async (lead) => {
    if (!window.confirm(`Delete ${lead.name || lead.phone}?`)) return;
    try {
      await clientApi.delete(`/api/campaigns/${campaignId}/leads/${lead.id}`);
      setDrawerOpen(false);
      setDrawerLead(null);
      await loadLeads();
      onLeadsChanged?.();
    } catch (err) {
      console.warn(parseLeadApiError(err));
    }
  };

  const handleSave = async (leadId, _campaignId, patch) => {
    const res = await clientApi.patch(`/api/campaigns/${campaignId}/leads/${leadId}`, patch);
    const updated = mapLead(res.data?.lead || res.data, campaignId, campaignName);
    setDrawerLead(updated);
    await loadLeads(false);
    onLeadsChanged?.();
    return updated;
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <section className="cdet-lead-sheet" id="campaign-leads">
      <div className="cdet-lead-sheet__head">
        <h2 className="cdet-lead-sheet__title">Lead Sheet</h2>
        <div className="cdet-lead-sheet__actions">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              const csv = 'name,phone\n';
              const blob = new Blob([csv], { type: 'text/csv' });
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `${(campaignName || 'campaign').replace(/\s+/g, '_')}_template.csv`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            Download Template
          </Button>
          <Button
            variant="secondary"
            size="sm"
            icon="upload_file"
            loading={uploading}
            disabled={!canImport}
            onClick={() => fileInputRef.current?.click()}
          >
            Import CSV
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.xlsx"
            hidden
            onChange={(e) => handleUpload(e.target.files?.[0])}
          />
        </div>
      </div>

      <div className="cdet-lead-sheet__toolbar">
        <div className="cdet-lead-sheet__filters">
          {FILTER_OPTIONS.map((f) => (
            <button
              key={f.id}
              type="button"
              className={`cdet-lead-sheet__filter ${activeFilter === f.id ? 'cdet-lead-sheet__filter--active' : ''}`}
              onClick={() => setActiveFilter(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <input
            type="search"
            placeholder="Search leads..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ height: '36px', padding: '8px 12px', borderRadius: '8px', border: '1px solid #E6E9EE', minWidth: '220px' }}
          />
        </div>
      </div>

      <div className="ent-table-wrap">
        <div className="ent-table-scroll">
          <table className="ent-table">
            <thead>
              <tr>
                  <th>Lead Name</th>
                  <th>Phone</th>
                  <th>Status</th>
                  <th>Attempts</th>
                  <th>Duration</th>
                  <th>Outcome</th>
                  <th>Last Updated</th>
                  <th>Actions</th>
                </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={8} className="cdet-lead-sheet__empty">Loading leads…</td>
                </tr>
              )}
              {!loading && leads.length === 0 && (
                <tr>
                  <td colSpan={8} className="cdet-lead-sheet__empty">
                    No leads match your filters. Import a CSV to get started.
                  </td>
                </tr>
              )}
              {!loading && displayLeads.map((lead) => (
                <tr
                  key={lead.id}
                  className={`ent-table__row--clickable ${['calling','ringing','connecting','connected'].includes(lead.status) ? 'cdet-lead-sheet__row--live' : ''}`}
                >
                  <td>
                    <div className="cdet-lead-sheet__identity">
                      <span className="cdet-lead-sheet__avatar">{leadInitials(lead.name)}</span>
                      <span>{lead.name || '—'}</span>
                    </div>
                  </td>
                  <td className="cdet-lead-sheet__mono">{lead.phone}</td>
                  <td><LeadStatusBadge lead={lead} mode="interest" /></td>
                  <td>
                    {lead.status === 'calling' ? (
                      <span className="cl-badge cl-badge--live" style={{ display: 'inline-flex', alignItems: 'center' }}>
                        <span className="material-symbols-outlined pulsing-icon" style={{ fontSize: '14px', marginRight: '4px', verticalAlign: 'middle' }}>call</span>
                        LIVE
                      </span>
                    ) : (
                      <LeadStatusBadge lead={lead} mode="dial" />
                    )}
                  </td>
                  <td>{lead.attempts ?? 0}</td>
                  <td>
                    {lead.status === 'calling' ? (
                      <LiveTimer startedAt={lead.lastCalledAt || lead.updatedAt} />
                    ) : (
                      fmtDuration(lead.lastCallDurationSeconds)
                    )}
                  </td>
                  <td>{lead.outcome || '—'}</td>
                  <td className="cdet-lead-sheet__muted">{fmtRelative(lead.lastCalledAt || lead.updatedAt)}</td>
                  <td>
                    <button
                      type="button"
                      className="cdet-lead-sheet__action"
                      onClick={() => { setDrawerLead(lead); setDrawerOpen(true); }}
                    >
                      View
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <footer className="cdet-lead-sheet__footer">
        <span>
          Showing {total === 0 ? 0 : offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
        </span>
        <div>
          <button type="button" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}>
            Previous
          </button>
          <span className="cdet-lead-sheet__page">Page {currentPage} of {totalPages}</span>
          <button
            type="button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset((o) => o + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      </footer>

      <LeadDrawer
        open={drawerOpen}
        lead={drawerLead}
        onClose={() => { setDrawerOpen(false); setDrawerLead(null); }}
        onDelete={handleDelete}
        onSave={handleSave}
      />
    </section>
  );
};

export default CampaignLeadSheet;
