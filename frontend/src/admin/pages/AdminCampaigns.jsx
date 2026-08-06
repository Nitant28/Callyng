import React, { useState, useEffect, useCallback, useMemo } from 'react';
import adminApi from '../../shared/api/admin';
import { useAdminData } from '../contexts/AdminDataContext';
import AdminCustomerFilter from '../components/AdminCustomerFilter';

export default function AdminCampaigns() {
  const { clients, clientsMap, botConfigs, botConfigsMap } = useAdminData();
  
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [clientFilter, setClientFilter] = useState('');
  
  const [copiedCampaignId, setCopiedCampaignId] = useState(null);

  const handleCopyCampaignId = (e, id) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    setCopiedCampaignId(id);
    setTimeout(() => setCopiedCampaignId(null), 2000);
  };
  
  // Create Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [createData, setCreateData] = useState({
    client_id: '',
    bot_config_id: '',
    name: '',
    budget_credits: 0,
    max_concurrent_calls: 5,
    calls_per_minute: 10,
    max_attempts: 3,
    retry_delay_minutes: 120,
    max_call_minutes: 10
  });

  // Drawer state
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const fetchCampaigns = useCallback(async () => {
    setLoading(true);
    try {
      const res = await adminApi.get('/internal/campaigns', {
        params: {
          search: search || undefined,
          client_id: clientFilter || undefined,
        },
      });
      setCampaigns(res.data.campaigns || []);
    } catch (err) {
      console.error("Failed to fetch campaigns", err);
    } finally {
      setLoading(false);
    }
  }, [search, clientFilter]);

  useEffect(() => {
    fetchCampaigns();
  }, [fetchCampaigns]);

  // Derived Bot Configs for Create Form
  const availableBotConfigs = useMemo(() => {
    if (!createData.client_id) return [];
    return botConfigs.filter(b => b.client_id === createData.client_id && b.active);
  }, [createData.client_id, botConfigs]);

  const selectedClient = useMemo(() => {
    return createData.client_id ? clientsMap[createData.client_id] : null;
  }, [createData.client_id, clientsMap]);

  const isFormValid = useMemo(() => {
    if (!selectedClient) return false;
    const requestedBudget = Number(createData.budget_credits) || 0;
    if (requestedBudget <= 0) return false;
    if (selectedClient.balance_credits <= 0) return false;
    if (selectedClient.balance_credits < requestedBudget) return false;
    if (!createData.bot_config_id || !createData.name) return false;
    if (!createData.max_concurrent_calls || !createData.calls_per_minute || !createData.max_attempts) return false;
    return true;
  }, [selectedClient, createData]);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!isFormValid) {
      alert("Please ensure client balance is sufficient for the requested budget and all required fields are filled.");
      return;
    }
    try {
      await adminApi.post('/internal/campaigns', {
        client_id: createData.client_id,
        bot_config_id: createData.bot_config_id,
        name: createData.name,
        budget_credits: Number(createData.budget_credits),
        max_concurrent_calls: Number(createData.max_concurrent_calls),
        calls_per_minute: Number(createData.calls_per_minute),
        max_attempts: Number(createData.max_attempts),
        retry_delay_minutes: Number(createData.retry_delay_minutes),
        max_call_minutes: Number(createData.max_call_minutes) || null
      });
      setIsCreateOpen(false);
      setCreateData({
        client_id: '', bot_config_id: '', name: '', budget_credits: 0,
        max_concurrent_calls: 5, calls_per_minute: 10, max_attempts: 3, retry_delay_minutes: 120, max_call_minutes: 10
      });
      fetchCampaigns();
    } catch (err) {
      console.error("Failed to create campaign", err);
      alert(err.customErrorMessage || "Failed to create campaign. Check client balance.");
    }
  };

  const handleAction = async (action, id) => {
    let confirmMsg = "";
    if (action === 'stop') confirmMsg = "Pause this campaign and release stuck leads?";
    else if (action === 'cancel') confirmMsg = "Cancel this campaign, fail pending leads, and refund budget?";
    
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    try {
      const res = await adminApi.patch(`/internal/campaigns/${id}/${action}`);
      if (action === 'cancel') {
        alert(`Cancelled! Refunded ₹${res.data.credits_returned?.toFixed(2)}`);
      }
      fetchCampaigns();
      if (selectedCampaign && selectedCampaign.id === id) {
        const campRes = await adminApi.get(`/internal/campaigns/${id}`);
        if (campRes.data.campaign) setSelectedCampaign(campRes.data.campaign);
      }
    } catch (err) {
      alert(err.customErrorMessage || `Failed to ${action} campaign`);
    }
  };

  const handleDeleteCampaign = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      await adminApi.delete(`/internal/campaigns/${deleteTarget.id}`);
      setDeleteTarget(null);
      if (selectedCampaign?.id === deleteTarget.id) {
        setIsDrawerOpen(false);
        setSelectedCampaign(null);
      }
      fetchCampaigns();
    } catch (err) {
      alert(err.customErrorMessage || 'Failed to delete campaign');
    } finally {
      setDeleting(false);
    }
  };

  const openDrawer = async (camp) => {
    setSelectedCampaign(camp);
    setIsDrawerOpen(true);
    try {
      const res = await adminApi.get(`/internal/campaigns/${camp.id}`);
      if (res.data.campaign) {
        setSelectedCampaign(res.data.campaign);
      }
    } catch (e) {
      console.error("Failed to refresh campaign drawer", e);
    }
  };

  const renderStatus = (status) => {
    const colors = {
      draft: 'bg-surface-container-high dark:bg-inverse-surface text-on-surface dark:text-molten-text',
      running: 'bg-primary/20 dark:bg-molten-primary/20 text-primary dark:text-molten-primary border-primary/30 dark:border-molten-primary/30',
      pausing: 'bg-arctic-warning/20 dark:bg-molten-warning/20 text-arctic-warning dark:text-molten-warning border-arctic-warning/30 dark:border-molten-warning/30',
      paused: 'bg-arctic-warning/10 dark:bg-molten-warning/10 text-arctic-warning dark:text-molten-warning',
      completed: 'bg-secondary/20 dark:bg-[#5cf7db]/20 text-secondary dark:text-[#5cf7db] border-secondary/30 dark:border-[#5cf7db]/30',
      cancelled: 'bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error border-error/30 dark:border-molten-error/30'
    };
    const c = colors[status] || 'bg-surface-container dark:bg-inverse-surface text-on-surface dark:text-molten-text';
    return <span className={`px-2 py-1 text-xs rounded-full border border-transparent capitalize ${c}`}>{status}</span>;
  };

  return (
    <div className="w-full relative">
      <div className="flex flex-col lg:flex-row lg:items-center justify-between mb-6 gap-4">
        <div className="min-w-0">
          <h2 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">Campaigns</h2>
          <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted mt-1">Manage global dialing jobs and monitor progress.</p>
        </div>
        <div className="flex flex-nowrap items-center gap-3 shrink-0">
          <AdminCustomerFilter
            clients={clients}
            value={clientFilter}
            onChange={setClientFilter}
          />
          <input
            type="text"
            placeholder="Search campaigns"
            className="h-10 w-[220px] px-3 bg-surface-container-lowest dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button
            className="h-10 shrink-0 bg-primary text-on-primary dark:bg-molten-primary rounded-lg px-4 font-label-md flex items-center gap-2 hover:-translate-y-[1px] transition-transform active:scale-95 whitespace-nowrap"
            onClick={() => setIsCreateOpen(true)}
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            Create Campaign
          </button>
        </div>
      </div>

      <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[800px]">
            <thead className="bg-surface-container-low dark:bg-[#1A1C24] border-b border-outline-variant dark:border-[#2A345E]">
              <tr>
                <th className="p-3 pl-4 font-label-sm text-on-surface-variant dark:text-molten-text-muted">Name</th>
                <th className="p-3 font-label-sm text-on-surface-variant dark:text-molten-text-muted">Client</th>
                <th className="p-3 font-label-sm text-on-surface-variant dark:text-molten-text-muted text-right">Budget</th>
                <th className="p-3 font-label-sm text-on-surface-variant dark:text-molten-text-muted text-right">Leads</th>
                <th className="p-3 font-label-sm text-on-surface-variant dark:text-molten-text-muted">Status</th>
                <th className="p-3 pr-4 font-label-sm text-on-surface-variant dark:text-molten-text-muted text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant/50 dark:divide-[#2A345E]/50">
              {campaigns.map(camp => (
                <tr key={camp.id} onClick={() => openDrawer(camp)} className="hover:bg-surface-container/30 dark:hover:bg-molten-bg/50 transition-colors cursor-pointer group">
                  <td className="p-3 pl-4 font-medium text-on-surface dark:text-molten-text">
                    <div className="flex flex-col">
                      <span>{camp.name}</span>
                      <div className="flex items-center gap-1.5 mt-0.5 group/uuid" onClick={(e) => handleCopyCampaignId(e, camp.id)}>
                        <span className="text-xs text-on-surface-variant/70 dark:text-molten-text-muted font-mono select-all">
                          {camp.id.substring(0, 8)}...
                        </span>
                        <button 
                          className="opacity-0 group-hover/uuid:opacity-100 p-0.5 hover:bg-surface-container dark:hover:bg-[#2A345E]/50 rounded text-on-surface-variant dark:text-molten-text transition-all"
                          title="Copy Full Campaign UUID"
                        >
                          <span className="material-symbols-outlined text-[12px]">
                            {copiedCampaignId === camp.id ? 'check' : 'content_copy'}
                          </span>
                        </button>
                      </div>
                    </div>
                  </td>
                  <td className="p-3 text-sm text-on-surface-variant dark:text-molten-text-muted">{clientsMap[camp.client_id]?.name || 'Unknown'}</td>
                  <td className="p-3 text-right text-sm tabular-nums text-on-surface dark:text-molten-text">
                    ₹{camp.budget_credits?.toFixed(2)}<br/>
                    <span className="text-xs text-on-surface-variant">Used: ₹{camp.budget_used_credits?.toFixed(2)}</span>
                  </td>
                  <td className="p-3 text-right text-sm tabular-nums text-on-surface dark:text-molten-text">
                    {camp.total_leads}<br/>
                    <span className="text-xs text-on-surface-variant">{camp.completed_leads} done</span>
                  </td>
                  <td className="p-3">{renderStatus(camp.status)}</td>
                  <td className="p-3 pr-4 text-right">
                    <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                      {(camp.status === 'running' || camp.status === 'pausing') && (
                        <button 
                          onClick={(e) => { e.stopPropagation(); handleAction('stop', camp.id); }}
                          className="px-2 py-1 text-xs rounded bg-arctic-warning/20 dark:bg-molten-warning/20 text-arctic-warning dark:text-molten-warning hover:opacity-80"
                        >Stop</button>
                      )}
                      {(camp.status === 'draft' || camp.status === 'paused') && (
                        <button 
                          onClick={(e) => { e.stopPropagation(); handleAction('start', camp.id); }}
                          className="px-2 py-1 text-xs rounded bg-primary/20 dark:bg-molten-primary/20 text-primary dark:text-molten-primary hover:opacity-80"
                        >Start</button>
                      )}
                      {(camp.status !== 'completed' && camp.status !== 'cancelled') && (
                        <button 
                          onClick={(e) => { e.stopPropagation(); handleAction('cancel', camp.id); }}
                          className="px-2 py-1 text-xs rounded bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error hover:opacity-80"
                        >Cancel</button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); setDeleteTarget(camp); }}
                        className="px-2 py-1 text-xs rounded bg-error/10 dark:bg-molten-error/10 text-error dark:text-molten-error hover:opacity-80"
                      >Delete</button>
                    </div>
                  </td>
                </tr>
              ))}
              {campaigns.length === 0 && !loading && (
                <tr>
                  <td colSpan="6" className="p-8 text-center text-on-surface-variant">No campaigns found.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create Modal Overlay */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-[#0c1941]/40 dark:bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4" onClick={(e) => e.target === e.currentTarget && setIsCreateOpen(false)}>
          <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col">
            <div className="px-6 py-5 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36] flex justify-between items-center">
              <h3 className="font-headline-sm font-bold text-on-surface dark:text-molten-text">Create Campaign</h3>
              <button onClick={() => setIsCreateOpen(false)} className="text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <form onSubmit={handleCreate} className="p-6 flex flex-col gap-4 max-h-[70vh] overflow-y-auto">
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Client</label>
                <select 
                  required
                  className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                  value={createData.client_id}
                  onChange={e => setCreateData({...createData, client_id: e.target.value, bot_config_id: ''})}
                >
                  <option className="dark:bg-[#1A1C24]" value="">Select a client...</option>
                  {clients.map(c => <option className="dark:bg-[#1A1C24]" key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Bot Config</label>
                <select 
                  required
                  disabled={!createData.client_id}
                  className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary disabled:opacity-50"
                  value={createData.bot_config_id}
                  onChange={e => setCreateData({...createData, bot_config_id: e.target.value})}
                >
                  <option className="dark:bg-[#1A1C24]" value="">Select a bot config...</option>
                  {availableBotConfigs.map(b => <option className="dark:bg-[#1A1C24]" key={b.id} value={b.id}>{b.name} ({b.route})</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Campaign Name</label>
                <input required className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="text" value={createData.name} onChange={e => setCreateData({...createData, name: e.target.value})} />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">
                    Budget (₹) {selectedClient && <span className={`ml-2 text-xs ${selectedClient.balance_credits < (Number(createData.budget_credits) || 0) ? 'text-error dark:text-molten-error font-bold' : 'text-primary dark:text-molten-primary'}`}>(Balance: ₹{selectedClient.balance_credits.toFixed(2)})</span>}
                  </label>
                  <input required className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="number" step="0.01" min="0.01" value={createData.budget_credits} onChange={e => setCreateData({...createData, budget_credits: e.target.value})} />
                </div>
                <div>
                  <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Concurrent Calls</label>
                  <input required className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="number" min="1" value={createData.max_concurrent_calls} onChange={e => setCreateData({...createData, max_concurrent_calls: e.target.value})} />
                </div>
                <div>
                  <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Calls / Min</label>
                  <input required className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="number" min="1" value={createData.calls_per_minute} onChange={e => setCreateData({...createData, calls_per_minute: e.target.value})} />
                </div>
                <div>
                  <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Max Call Mins</label>
                  <input className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="number" min="1" value={createData.max_call_minutes} onChange={e => setCreateData({...createData, max_call_minutes: e.target.value})} />
                </div>
                <div>
                  <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Max Attempts</label>
                  <input required className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="number" min="1" value={createData.max_attempts} onChange={e => setCreateData({...createData, max_attempts: e.target.value})} />
                </div>
                <div>
                  <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Retry Delay (min)</label>
                  <input required className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" type="number" min="0" value={createData.retry_delay_minutes} onChange={e => setCreateData({...createData, retry_delay_minutes: e.target.value})} />
                </div>
              </div>
              <div className="pt-4 flex justify-end gap-2">
                <button type="button" onClick={() => setIsCreateOpen(false)} className="px-4 py-2 rounded-lg text-on-surface-variant dark:text-molten-text border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#2A345E]/50 transition-colors">Cancel</button>
                <button type="submit" disabled={!isFormValid} className="px-4 py-2 bg-primary dark:bg-molten-primary text-on-primary rounded-lg hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Drawer */}
      {isDrawerOpen && selectedCampaign && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/50" onClick={() => setIsDrawerOpen(false)}></div>
          <div className="relative w-full max-w-md bg-surface-container-lowest dark:bg-molten-surface h-full shadow-2xl flex flex-col">
            <div className="p-6 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-center bg-surface-container-low dark:bg-[#1A1C24]">
              <h3 className="font-headline-sm text-on-surface dark:text-molten-text">Campaign Details</h3>
              <button onClick={() => setIsDrawerOpen(false)} className="p-2 rounded-full hover:bg-surface-container-highest dark:hover:bg-[#2A345E] text-on-surface dark:text-molten-text">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-6 text-on-surface dark:text-molten-text">
              <div>
                <h4 className="text-lg font-bold dark:text-molten-text">{selectedCampaign.name}</h4>
                <p className="text-sm text-on-surface-variant dark:text-molten-text-muted font-mono">{selectedCampaign.id}</p>
                <div className="mt-2 flex items-center gap-2">
                  {renderStatus(selectedCampaign.status)}
                  {(selectedCampaign.status === 'running' || selectedCampaign.status === 'pausing') && (
                    <button onClick={() => handleAction('stop', selectedCampaign.id)} className="px-2 py-1 text-xs rounded bg-arctic-warning/20 dark:bg-molten-warning/20 text-arctic-warning dark:text-molten-warning hover:opacity-80">Stop</button>
                  )}
                  {(selectedCampaign.status === 'draft' || selectedCampaign.status === 'paused') && (
                    <button onClick={() => handleAction('start', selectedCampaign.id)} className="px-2 py-1 text-xs rounded bg-primary/20 dark:bg-molten-primary/20 text-primary dark:text-molten-primary hover:opacity-80">Start</button>
                  )}
                  {(selectedCampaign.status !== 'completed' && selectedCampaign.status !== 'cancelled') && (
                    <button onClick={() => handleAction('cancel', selectedCampaign.id)} className="px-2 py-1 text-xs rounded bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error hover:opacity-80">Cancel</button>
                  )}
                  <button
                    onClick={() => setDeleteTarget(selectedCampaign)}
                    className="px-2 py-1 text-xs rounded bg-error/10 dark:bg-molten-error/10 text-error dark:text-molten-error hover:opacity-80"
                  >
                    Delete
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="bg-surface-container dark:bg-[#1A1C24] p-3 rounded-lg text-sm">
                  <div className="text-on-surface-variant dark:text-molten-text-muted">Budget</div>
                  <div className="font-bold dark:text-molten-text">₹{selectedCampaign.budget_credits?.toFixed(2)}</div>
                </div>
                <div className="bg-surface-container dark:bg-[#1A1C24] p-3 rounded-lg text-sm">
                  <div className="text-on-surface-variant dark:text-molten-text-muted">Used</div>
                  <div className="font-bold dark:text-molten-text">₹{selectedCampaign.budget_used_credits?.toFixed(2)}</div>
                </div>
              </div>

              <h5 className="font-bold border-b border-outline-variant dark:border-[#2A345E] pb-2 dark:text-molten-text">Leads Pipeline</h5>
              <div className="grid grid-cols-2 gap-2 text-sm text-on-surface-variant dark:text-molten-text-muted">
                <div className="flex justify-between"><span>Total:</span> <span className="dark:text-molten-text">{selectedCampaign.total_leads}</span></div>
                <div className="flex justify-between"><span>Pending / Retry:</span> <span className="dark:text-molten-text">{selectedCampaign.pending_leads}</span></div>
                <div className="flex justify-between"><span>Calling:</span> <span className="dark:text-molten-text">{selectedCampaign.calling_leads}</span></div>
                <div className="flex justify-between"><span>Callback:</span> <span className="dark:text-molten-text">{selectedCampaign.callback_leads}</span></div>
                <div className="flex justify-between"><span>Completed:</span> <span className="dark:text-molten-text">{selectedCampaign.completed_leads}</span></div>
                <div className="flex justify-between"><span>Failed:</span> <span className="dark:text-molten-text">{selectedCampaign.failed_leads}</span></div>
              </div>

              <h5 className="font-bold border-b border-outline-variant dark:border-[#2A345E] pb-2 mt-4 dark:text-molten-text">Settings</h5>
              <div className="grid grid-cols-2 gap-2 text-sm text-on-surface-variant dark:text-molten-text-muted">
                <div className="flex justify-between"><span>Concurrency:</span> <span className="dark:text-molten-text">{selectedCampaign.max_concurrent_calls}</span></div>
                <div className="flex justify-between"><span>Rate (CPM):</span> <span className="dark:text-molten-text">{selectedCampaign.calls_per_minute}</span></div>
                <div className="flex justify-between"><span>Max Attempts:</span> <span className="dark:text-molten-text">{selectedCampaign.max_attempts}</span></div>
                <div className="flex justify-between"><span>Retry Delay:</span> <span className="dark:text-molten-text">{selectedCampaign.retry_delay_minutes}m</span></div>
                <div className="flex justify-between"><span>Max Call Length:</span> <span className="dark:text-molten-text">{selectedCampaign.max_call_minutes}m</span></div>
              </div>
            </div>
          </div>
        </div>
      )}

      {deleteTarget && (
        <div className="fixed inset-0 bg-black/50 z-[110] flex items-center justify-center p-4" onClick={() => !deleting && setDeleteTarget(null)}>
          <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl shadow-2xl w-full max-w-md p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-headline-sm text-on-surface dark:text-molten-text mb-2">Delete campaign?</h3>
            <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-6">
              Remove <strong>{deleteTarget.name}</strong> from the Client Panel and admin Campaigns list?
              This action requires confirmation.
            </p>
            <div className="flex justify-end gap-2">
              <button type="button" disabled={deleting} onClick={() => setDeleteTarget(null)} className="px-4 py-2 rounded-lg border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text">Keep</button>
              <button type="button" disabled={deleting} onClick={handleDeleteCampaign} className="px-4 py-2 rounded-lg bg-error text-white disabled:opacity-60">
                {deleting ? 'Deleting...' : 'Delete campaign'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
