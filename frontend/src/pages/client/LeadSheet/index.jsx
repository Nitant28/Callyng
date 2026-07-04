import { useCallback, useEffect, useMemo, useState } from 'react';
import { useDashboardData } from '../../../contexts/DashboardDataContext';
import { useToast } from '../../../contexts/ToastContext';
import { Modal, Button } from '../../../components/enterprise';
import CustomMetadataFields from '../../../components/client/CustomMetadataFields';
import { buildMetadataFromCustomFields } from '../../../utils/leadFormHelpers';
import useLeads from '../../../hooks/useLeads';
import useAgentControl from '../../../hooks/useAgentControl';
import leadService from '../../../services/leadService';
import {
  leadsToCsv,
  campaignLabel,
  canImportToCampaign,
  parseLeadApiError,
} from './leadUtils';
import LeadHeader from './LeadHeader';
import LeadStats from './LeadStats';
import LeadToolbar from './LeadToolbar';
import LeadTable from './LeadTable';
import BulkToolbar from './BulkToolbar';
import CsvUploader from './CsvUploader';
import LeadDrawer from './LeadDrawer';
import './LeadSheet.css';

const LeadSheetPage = () => {
  const { campaigns = [], refresh: refreshDashboard } = useDashboardData() ?? {};
  const { showToast } = useToast();

  const dialerLive = useMemo(
    () => campaigns.some((c) => c.status === 'running' || c.status === 'pausing'),
    [campaigns],
  );

  const {
    rows,
    total,
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
  } = useLeads({}, { live: dialerLive });

  const agent = useAgentControl(campaigns, { campaignId: filters.campaignId || undefined });

  const handleAgentToggle = useCallback(async () => {
    try {
      const onRefresh = async () => {
        refresh();
        refreshDashboard?.();
      };
      if (agent.agentActive && !agent.isPausing) {
        await agent.stop(onRefresh);
        showToast('Agent stopping — current call will finish first.', 'success');
      } else if (!agent.agentActive) {
        const started = await agent.start(onRefresh);
        showToast(`Agent started on ${campaignLabel(started)}`, 'success');
      }
    } catch (err) {
      showToast(err.message || 'Agent action failed', 'error');
    }
  }, [agent, refresh, refreshDashboard, showToast]);

  const [drawerLead, setDrawerLead] = useState(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [newLead, setNewLead] = useState({ campaignId: '', name: '', phone: '' });
  const [addLeadCustomColumns, setAddLeadCustomColumns] = useState([]);
  const [saving, setSaving] = useState(false);
  const [exporting, setExporting] = useState(false);

  const modifiableCampaigns = useMemo(
    () => campaigns.filter(canImportToCampaign),
    [campaigns],
  );

  const openDrawer = useCallback((lead) => {
    setDrawerLead(lead);
    setDrawerOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setDrawerLead(null);
  }, []);

  useEffect(() => {
    if (!drawerOpen || !drawerLead?.id) return;
    const fresh = rows.find((r) => r.id === drawerLead.id);
    if (fresh) setDrawerLead(fresh);
  }, [rows, drawerOpen, drawerLead?.id]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      let exportRows;
      if (selected.size > 0) {
        exportRows = rows.filter((r) => selected.has(r.id));
      } else if (total <= rows.length) {
        exportRows = rows;
      } else {
        showToast(`Exporting ${total.toLocaleString('en-IN')} leads…`, 'success');
        exportRows = await leadService.listAll({
          search: search || undefined,
          campaignId: filters.campaignId || undefined,
          status: filters.status || undefined,
          sort: sort.field,
          order: sort.direction,
        });
      }

      if (!exportRows.length) {
        showToast('No leads to export', 'error');
        return;
      }

      leadService.triggerCsvDownload(
        `leads-export-${new Date().toISOString().slice(0, 10)}.csv`,
        leadsToCsv(exportRows),
      );
      showToast(`Exported ${exportRows.length.toLocaleString('en-IN')} leads`, 'success');
    } catch (err) {
      showToast(parseLeadApiError(err), 'error');
    } finally {
      setExporting(false);
    }
  }, [rows, selected, total, search, filters, sort, showToast]);

  const handleDelete = useCallback(async (lead) => {
    if (!lead?.campaignId) return;
    if (!window.confirm(`Delete ${lead.name || lead.phone}?`)) return;
    try {
      await leadService.delete(lead.campaignId, lead.id);
      showToast('Lead deleted', 'success');
      closeDrawer();
      refresh();
      refreshDashboard?.();
    } catch (err) {
      showToast(parseLeadApiError(err), 'error');
    }
  }, [closeDrawer, refresh, refreshDashboard, showToast]);

  const handleBulkDelete = useCallback(async () => {
    const targets = rows.filter((r) => selected.has(r.id));
    if (!targets.length) return;
    if (!window.confirm(`Delete ${targets.length} leads?`)) return;
    try {
      await Promise.all(targets.map((l) => leadService.delete(l.campaignId, l.id)));
      showToast(`${targets.length} leads deleted`, 'success');
      refresh();
      refreshDashboard?.();
    } catch (err) {
      showToast(parseLeadApiError(err), 'error');
    }
  }, [rows, selected, refresh, refreshDashboard, showToast]);

  const handleAddLead = useCallback(async () => {
    if (!newLead.campaignId || !newLead.phone.trim()) {
      showToast('Campaign and phone are required', 'error');
      return;
    }
    setSaving(true);
    try {
      const created = await leadService.add(newLead.campaignId, {
        name: newLead.name.trim() || null,
        phone: newLead.phone.trim(),
        metadata: buildMetadataFromCustomFields({}, addLeadCustomColumns),
      });
      showToast(`Added ${created.name || created.phone}`, 'success');
      setAddOpen(false);
      setNewLead({ campaignId: '', name: '', phone: '' });
      setAddLeadCustomColumns([]);
      setFilters((f) => ({ ...f, campaignId: String(newLead.campaignId) }));
      leadService.invalidateApiCache();
      refresh();
      refreshDashboard?.();
    } catch (err) {
      showToast(parseLeadApiError(err), 'error');
    } finally {
      setSaving(false);
    }
  }, [newLead, addLeadCustomColumns, filters.campaignId, setFilters, refresh, refreshDashboard, showToast]);

  const handleImport = useCallback(async (campaignId, file, onProgress) => {
    const data = await leadService.importCsv(campaignId, file, onProgress);
    setFilters((f) => ({ ...f, campaignId: String(campaignId) }));
    leadService.invalidateApiCache();
    refresh();
    refreshDashboard?.();
    return data;
  }, [setFilters, refresh, refreshDashboard]);

  const handleImportSuccess = useCallback(({ imported, campaignId }) => {
    if (imported > 0) {
      showToast(`${imported.toLocaleString('en-IN')} leads imported`, 'success');
    } else {
      showToast('No new leads imported (duplicates or invalid rows skipped)', 'error');
    }
    if (campaignId) {
      setFilters((f) => ({ ...f, campaignId: String(campaignId) }));
    }
    leadService.invalidateApiCache();
    refresh();
    refreshDashboard?.();
  }, [setFilters, refresh, refreshDashboard, showToast]);

  const handleSaveLead = useCallback(async (leadId, campaignId, patch) => {
    const updated = await leadService.update(campaignId, leadId, patch);
    setDrawerLead(updated);
    refresh();
    showToast('Lead updated', 'success');
    return updated;
  }, [refresh, showToast]);

  return (
    <div className="app-page lead-sheet">
      <LeadHeader
        agentActive={agent.agentActive}
        isPausing={agent.isPausing}
        isRunning={agent.isRunning}
        agentLoading={agent.loading}
        canStart={agent.canStart}
        onAgentToggle={handleAgentToggle}
        runningCampaignName={agent.runningCampaign ? campaignLabel(agent.runningCampaign) : ''}
      />
      <LeadStats stats={stats} loading={statsLoading} />
      <LeadToolbar
        search={search}
        onSearchChange={setSearch}
        filters={filters}
        onFilterChange={(patch) => setFilters((f) => ({ ...f, ...patch }))}
        onResetFilters={resetFilters}
        campaigns={campaigns}
        onImport={() => setImportOpen(true)}
        onExport={handleExport}
        onAddLead={() => setAddOpen(true)}
        exporting={exporting}
      />

      {error && <div className="lead-sheet__error">{error}</div>}

      <BulkToolbar
        count={selected.size}
        onExport={handleExport}
        onDelete={handleBulkDelete}
        onClear={clearSelection}
      />

      <LeadTable
        rows={rows}
        loading={loading}
        total={total}
        page={page}
        limit={limit}
        sort={sort}
        onSort={toggleSort}
        selected={selected}
        onToggleSelect={toggleSelect}
        onToggleSelectAll={toggleSelectAll}
        onRowClick={openDrawer}
        onEdit={openDrawer}
        onDelete={handleDelete}
        onPageChange={setPage}
        onLimitChange={setLimit}
        onImport={() => setImportOpen(true)}
        onAddLead={() => setAddOpen(true)}
      />

      <LeadDrawer
        open={drawerOpen}
        lead={drawerLead}
        onClose={closeDrawer}
        onDelete={handleDelete}
        onSave={handleSaveLead}
      />

      <CsvUploader
        open={importOpen}
        campaigns={campaigns}
        defaultCampaignId={filters.campaignId || modifiableCampaigns[0]?.id || ''}
        onClose={() => setImportOpen(false)}
        onUpload={handleImport}
        onSuccess={handleImportSuccess}
      />

      <Modal
        open={addOpen}
        onClose={() => { setAddOpen(false); setAddLeadCustomColumns([]); }}
        title="Add New Lead"
        subtitle="Add a lead manually to start AI outreach instantly."
        icon="person_add"
        width={480}
        footer={(
          <>
            <Button variant="ghost" onClick={() => { setAddOpen(false); setAddLeadCustomColumns([]); }}>Cancel</Button>
            <Button variant="primary" loading={saving} onClick={handleAddLead}>Add Contact</Button>
          </>
        )}
      >
        <div className="ent-form">
          {modifiableCampaigns.length === 0 && (
            <p className="ent-form__warn">
              No importable campaigns. Create a draft or pause a running campaign first.
            </p>
          )}
          <label>
            Campaign
            <select
              value={newLead.campaignId}
              onChange={(e) => setNewLead((l) => ({ ...l, campaignId: e.target.value }))}
            >
              <option value="">Select campaign…</option>
              {modifiableCampaigns.map((c) => (
                <option key={c.id} value={c.id}>{campaignLabel(c)}</option>
              ))}
            </select>
          </label>
          <label>
            Name
            <input
              type="text"
              value={newLead.name}
              onChange={(e) => setNewLead((l) => ({ ...l, name: e.target.value }))}
              placeholder="John Smith"
            />
          </label>
          <label>
            Phone Number (with prefix)
            <input
              type="tel"
              value={newLead.phone}
              onChange={(e) => setNewLead((l) => ({ ...l, phone: e.target.value }))}
              placeholder="e.g. +919988776655"
            />
          </label>
          <CustomMetadataFields fields={addLeadCustomColumns} onChange={setAddLeadCustomColumns} />
        </div>
      </Modal>
    </div>
  );
};

export default LeadSheetPage;
