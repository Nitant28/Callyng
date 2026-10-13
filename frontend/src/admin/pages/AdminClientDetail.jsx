import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, Link } from 'react-router-dom';
import adminApi from '../../shared/api/admin';


export default function AdminClientDetail() {
  const { id } = useParams();
  
  const [activeTab, setActiveTab] = useState('overview'); // 'overview', 'ledger', 'webhooks', 'campaigns'
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalClosing, setModalClosing] = useState(false);
  const [adjustAmount, setAdjustAmount] = useState('');
  const [adjustNote, setAdjustNote] = useState('');
  const [isPulse, setIsPulse] = useState(false);

  const [client, setClient] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [webhooks, setWebhooks] = useState([]);

  // Campaigns-related state
  const [campaigns, setCampaigns] = useState([]);
  const [botConfigs, setBotConfigs] = useState([]);
  const [isCampaignModalOpen, setIsCampaignModalOpen] = useState(false);
  const [campaignModalClosing, setCampaignModalClosing] = useState(false);
  const [createCampaignData, setCreateCampaignData] = useState({
    bot_config_id: '',
    name: '',
    budget_credits: 0,
    max_concurrent_calls: 5,
    calls_per_minute: 10,
    max_attempts: 3,
    retry_delay_minutes: 120,
    max_call_minutes: 10
  });
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [copiedCampaignId, setCopiedCampaignId] = useState(null);

  const fetchCampaigns = useCallback(async () => {
    try {
      const campaignsRes = await adminApi.get('/internal/campaigns', { params: { client_id: id } });
      setCampaigns(campaignsRes.data.campaigns || []);
    } catch (error) {
      console.error("Failed to fetch campaigns", error);
    }
  }, [id]);

  useEffect(() => {
    const fetchDetails = async () => {
      try {
        const clientRes = await adminApi.get(`/internal/clients/${id}`);
        const clientData = clientRes.data.client || clientRes.data;
        const mappedClient = {
          ...clientData,
          balance: clientData.balance_credits,
          status: clientData.active ? 'Active' : 'Suspended'
        };

        const ledgerRes = await adminApi.get(`/internal/clients/${id}/credits`);
        const rawTxs = ledgerRes.data.transactions || [];
        let currentBal = mappedClient.balance || 0;
        const txsMapped = [];
        for (let i = 0; i < rawTxs.length; i++) {
          const tx = rawTxs[i];
          txsMapped.push({
            id: tx.id,
            date: tx.created_at ? new Date(tx.created_at).toLocaleString() : 'N/A',
            amount: parseFloat(tx.amount || 0),
            note: tx.note || '',
            balance_after: currentBal
          });
          currentBal -= parseFloat(tx.amount || 0);
        }

        const webhooksRes = await adminApi.get(`/internal/clients/${id}/webhooks`);
        const mappedWebhooks = (webhooksRes.data.webhooks || []).map(wh => ({
          ...wh,
          status: wh.active ? 'Active' : 'Disabled'
        }));

        const botsRes = await adminApi.get('/internal/bot-configs', { params: { client_id: id } });

        setClient(mappedClient);
        setLedger(txsMapped);
        setWebhooks(mappedWebhooks);
        setBotConfigs((botsRes.data.bot_configs || []).filter(b => b.active));
        await fetchCampaigns();
      } catch (error) {
        console.error("Failed to fetch client details", error);
      }
    };
    
    fetchDetails();
  }, [id, fetchCampaigns]);

  const openModal = () => {
    setIsModalOpen(true);
    setModalClosing(false);
  };

  const closeModal = () => {
    setModalClosing(true);
    setTimeout(() => {
      setIsModalOpen(false);
      setModalClosing(false);
    }, 200);
  };

  const handleAdjustBalance = async () => {
    if (!adjustAmount) return;
    
    try {
      const response = await adminApi.patch(`/internal/clients/${id}/credits`, {
        amount: parseFloat(adjustAmount),
        note: adjustNote || "Manual top-up"
      });
      
      const newBalance = response.data.balance_credits;
      
      if (client) {
        setClient(prev => ({
          ...prev,
          balance_credits: newBalance,
          balance: newBalance
        }));
      }
      
      const ledgerRes = await adminApi.get(`/internal/clients/${id}/credits`);
      const rawTxs = ledgerRes.data.transactions || [];
      let currentBal = newBalance;
      const txsMapped = [];
      for (let i = 0; i < rawTxs.length; i++) {
        const tx = rawTxs[i];
        txsMapped.push({
          id: tx.id,
          date: tx.created_at ? new Date(tx.created_at).toLocaleString() : 'N/A',
          amount: parseFloat(tx.amount || 0),
          note: tx.note || '',
          balance_after: currentBal
        });
        currentBal -= parseFloat(tx.amount || 0);
      }
      setLedger(txsMapped);

      closeModal();
      
      setTimeout(() => {
        setActiveTab('overview');
        setIsPulse(false);
        setTimeout(() => setIsPulse(true), 50);
      }, 300);
      
    } catch (error) {
      console.error("Failed to adjust balance", error);
      closeModal();
    }
  };

  const handleToggleStatus = async () => {
    try {
      const newActiveState = !(client.active);
      const res = await adminApi.patch(`/internal/clients/${id}/status`, { active: newActiveState });
      setClient(prev => ({
        ...prev,
        active: newActiveState,
        status: newActiveState ? 'Active' : 'Suspended'
      }));
    } catch (err) {
      console.error("Failed to toggle status", err);
      alert("Failed to toggle client status.");
    }
  };

  const openCampaignModal = () => {
    setIsCampaignModalOpen(true);
    setCampaignModalClosing(false);
  };

  const closeCampaignModal = () => {
    setCampaignModalClosing(true);
    setTimeout(() => {
      setIsCampaignModalOpen(false);
      setCampaignModalClosing(false);
    }, 200);
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    try {
      await adminApi.post('/internal/campaigns', {
        client_id: id,
        bot_config_id: createCampaignData.bot_config_id,
        name: createCampaignData.name,
        budget_credits: Number(createCampaignData.budget_credits),
        max_concurrent_calls: Number(createCampaignData.max_concurrent_calls),
        calls_per_minute: Number(createCampaignData.calls_per_minute),
        max_attempts: Number(createCampaignData.max_attempts),
        retry_delay_minutes: Number(createCampaignData.retry_delay_minutes),
        max_call_minutes: Number(createCampaignData.max_call_minutes) || null
      });
      closeCampaignModal();
      setCreateCampaignData({
        bot_config_id: '', name: '', budget_credits: 0,
        max_concurrent_calls: 5, calls_per_minute: 10, max_attempts: 3, retry_delay_minutes: 120, max_call_minutes: 10
      });
      fetchCampaigns();
      
      // Update balance
      const clientRes = await adminApi.get(`/internal/clients/${id}`);
      const clientData = clientRes.data.client || clientRes.data;
      setClient(prev => ({
        ...prev,
        balance_credits: clientData.balance_credits,
        balance: clientData.balance_credits
      }));
    } catch (err) {
      console.error("Failed to create campaign", err);
      alert(err.customErrorMessage || "Failed to create campaign. Check client balance.");
    }
  };

  const handleCampaignAction = async (action, campId) => {
    let confirmMsg = "";
    if (action === 'stop') confirmMsg = "Pause this campaign and release stuck leads?";
    else if (action === 'cancel') confirmMsg = "Cancel this campaign, fail pending leads, and refund budget?";
    
    if (confirmMsg && !window.confirm(confirmMsg)) return;

    try {
      const res = await adminApi.patch(`/internal/campaigns/${campId}/${action}`);
      if (action === 'cancel') {
        alert(`Cancelled! Refunded ₹${res.data.credits_returned?.toFixed(2)}`);
      }
      fetchCampaigns();
      if (selectedCampaign && selectedCampaign.id === campId) {
        const campRes = await adminApi.get(`/internal/campaigns/${campId}`);
        if (campRes.data.campaign) setSelectedCampaign(campRes.data.campaign);
      }
      
      if (action === 'cancel') {
        const clientRes = await adminApi.get(`/internal/clients/${id}`);
        const clientData = clientRes.data.client || clientRes.data;
        setClient(prev => ({
          ...prev,
          balance_credits: clientData.balance_credits,
          balance: clientData.balance_credits
        }));
      }
    } catch (err) {
      alert(err.customErrorMessage || `Failed to ${action} campaign`);
    }
  };

  const openCampaignDrawer = async (camp) => {
    setSelectedCampaign(camp);
    setIsDrawerOpen(true);
    try {
      const res = await adminApi.get(`/internal/campaigns/${camp.id}`);
      if (res.data.campaign) setSelectedCampaign(res.data.campaign);
    } catch (e) {
      console.error("Failed to refresh campaign drawer", e);
    }
  };

  const handleCopyCampaignId = (e, campaignId) => {
    e.stopPropagation();
    navigator.clipboard.writeText(campaignId);
    setCopiedCampaignId(campaignId);
    setTimeout(() => setCopiedCampaignId(null), 2000);
  };

  const renderCampaignStatus = (status) => {
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

  if (!client) {
    return <div className="p-8 text-center">Loading...</div>;
  }

  return (
    <>
      <div className="w-full flex flex-col gap-stack-lg">
        {/* Breadcrumb & Header */}
        <div className="flex flex-col gap-stack-sm">
          <nav className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted flex items-center gap-2">
            <Link to="/admin" className="hover:text-primary dark:hover:text-molten-primary transition-colors">Admin</Link>
            <span className="material-symbols-outlined text-[16px]">chevron_right</span>
            <Link to="/admin/clients" className="hover:text-primary dark:hover:text-molten-primary transition-colors">Clients</Link>
            <span className="material-symbols-outlined text-[16px]">chevron_right</span>
            <span className="text-on-surface dark:text-molten-text font-medium">Client Detail</span>
          </nav>
          
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mt-2">
            <h2 className="font-headline-lg text-headline-lg-mobile md:text-headline-lg font-extrabold text-on-surface dark:text-molten-text">
              {client.name}
            </h2>
            <div className="flex gap-3">
              <button 
                className={`rounded-lg py-2 px-5 font-label-md text-label-md flex items-center gap-2 border transition-all ${
                  client.active 
                    ? 'border-error text-error hover:bg-error/10' 
                    : 'border-primary text-primary hover:bg-primary/10'
                }`}
                onClick={handleToggleStatus}
              >
                <span className="material-symbols-outlined text-[20px]">
                  {client.active ? 'block' : 'check_circle'}
                </span>
                {client.active ? 'Suspend' : 'Reactivate'}
              </button>
              <button 
                className="bg-primary text-on-primary dark:bg-molten-primary rounded-lg py-2 px-5 font-label-md text-label-md flex items-center gap-2 shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:-translate-y-[1px] transition-transform active:scale-95"
                onClick={openModal}
              >
                <span className="material-symbols-outlined text-[20px]">account_balance_wallet</span>
                Adjust Balance
              </button>
            </div>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="border-b border-outline-variant dark:border-[#2A345E] flex gap-8">
          <button 
            className={`font-label-md text-label-md pb-3 px-1 transition-colors ${activeTab === 'overview' ? 'text-primary dark:text-molten-primary font-bold border-b-2 border-primary dark:border-molten-primary' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text'}`}
            onClick={() => setActiveTab('overview')}
          >
            Overview
          </button>
          <button 
            className={`font-label-md text-label-md pb-3 px-1 transition-colors ${activeTab === 'campaigns' ? 'text-primary dark:text-molten-primary font-bold border-b-2 border-primary dark:border-molten-primary' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text'}`}
            onClick={() => setActiveTab('campaigns')}
          >
            Campaigns
          </button>
          <button 
            className={`font-label-md text-label-md pb-3 px-1 transition-colors ${activeTab === 'ledger' ? 'text-primary dark:text-molten-primary font-bold border-b-2 border-primary dark:border-molten-primary' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text'}`}
            onClick={() => setActiveTab('ledger')}
          >
            Billing Ledger
          </button>
          <button 
            className={`font-label-md text-label-md pb-3 px-1 transition-colors ${activeTab === 'webhooks' ? 'text-primary dark:text-molten-primary font-bold border-b-2 border-primary dark:border-molten-primary' : 'text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text'}`}
            onClick={() => setActiveTab('webhooks')}
          >
            Webhooks
          </button>
        </div>

        {/* Tabs Container */}
        <div className="relative min-h-[400px]">
          
          {/* Overview Tab */}
          <div className={`tab-content ${activeTab === 'overview' ? 'active' : ''}`}>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 section">
              {/* Balance Card (Largest) */}
              <div className={`md:col-span-1 md:row-span-2 bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6 shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none flex flex-col justify-between transition-all duration-300 ${isPulse ? 'pulse-success' : ''}`}>
                <div>
                  <h3 className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider mb-2">Current Credit Balance</h3>
                  <div className="font-headline-xl text-headline-xl tabular-nums text-on-surface dark:text-molten-text mb-1">
                    ₹{client.balance?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-label-sm text-label-sm bg-surface-container-high text-on-surface dark:bg-inverse-surface dark:text-molten-text">
                      {client.status || 'Active'}
                    </span>
                    <span className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">Auto-recharge enabled</span>
                  </div>
                </div>
                <div className="mt-8 pt-6 border-t border-outline-variant dark:border-[#2A345E]">
                  <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted mb-3">Projected run-rate: ~{client.run_rate_days || 14} days</p>
                  <div className="w-full bg-surface-container-high dark:bg-inverse-surface rounded-full h-2">
                    <div className="bg-primary dark:bg-molten-primary h-2 rounded-full" style={{ width: `${client.run_rate_percent || 65}%` }}></div>
                  </div>
                </div>
              </div>

              {/* Metrics */}
              <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-none p-6 shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none flex flex-col justify-center">
                <h3 className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]">payments</span> Total Spent YTD
                </h3>
                <div className="font-headline-lg text-headline-lg tabular-nums text-on-surface dark:text-molten-text">
                  ₹{client.total_spent?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
              </div>
              <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6 shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none flex flex-col justify-center">
                <h3 className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider mb-2 flex items-center gap-2">
                  <span className="material-symbols-outlined text-[16px]">call</span> Total Calls
                </h3>
                <div className="font-headline-xl text-headline-xl tabular-nums text-on-surface dark:text-molten-text">
                  {client.total_calls?.toLocaleString()}
                </div>
              </div>
            </div>
          </div>

          {/* Ledger Tab */}
          <div className={`tab-content ${activeTab === 'ledger' ? 'active' : ''}`}>
            <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden section">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36]">
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">Date</th>
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider text-right">Amount</th>
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">Note</th>
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider text-right">Balance After</th>
                  </tr>
                </thead>
                <tbody className="font-body-md text-body-md text-on-surface dark:text-molten-text tabular-nums">
                  {ledger.map((tx, idx) => (
                    <tr key={tx.id || idx} className="border-b border-outline-variant dark:border-[#2A345E] last:border-0 hover:bg-surface-container-lowest dark:hover:bg-inverse-surface transition-colors">
                      <td className="py-3 px-4">{tx.date}</td>
                      <td className={`py-3 px-4 text-right font-medium ${tx.amount < 0 ? 'text-arctic-error dark:text-molten-error' : 'text-[#006b5c] dark:text-secondary-fixed-dim'}`}>
                        {tx.amount < 0 ? '-' : '+'}₹{Math.abs(tx.amount).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className="py-3 px-4 text-on-surface-variant dark:text-molten-text-muted">{tx.note}</td>
                      <td className="py-3 px-4 text-right">₹{tx.balance_after?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Webhooks Tab */}
          <div className={`tab-content ${activeTab === 'webhooks' ? 'active' : ''}`}>
            <div className="section bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36]">
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">Event</th>
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">URL</th>
                    <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">Status</th>
                    <th className="py-3 px-4"></th>
                  </tr>
                </thead>
                <tbody className="font-body-md text-body-md text-on-surface dark:text-molten-text">
                  {webhooks.map((wh, idx) => (
                    <tr key={wh.id || idx} className="border-b border-outline-variant dark:border-[#2A345E] last:border-0 hover:bg-surface-container-lowest dark:hover:bg-inverse-surface transition-colors">
                      <td className="py-3 px-4 font-medium">{wh.event}</td>
                      <td className="py-3 px-4 font-mono text-sm text-arctic-text-muted dark:text-molten-text-muted">{wh.url}</td>
                      <td className="py-3 px-4">
                        {wh.status === 'Active' ? (
                          <span className="inline-flex items-center px-2 py-1 rounded-full font-label-sm text-label-sm bg-[#5cf7db]/15 text-[#007060] dark:text-secondary-fixed-dim">Active</span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-1 rounded-full font-label-sm text-label-sm bg-surface-container-high text-on-surface-variant dark:bg-inverse-surface dark:text-molten-text-muted">Disabled</span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button className="text-on-surface-variant hover:text-primary dark:text-molten-text-muted dark:hover:text-molten-primary">
                          <span className="material-symbols-outlined text-[20px]">more_vert</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Campaigns Tab */}
          <div className={`tab-content ${activeTab === 'campaigns' ? 'active' : ''}`}>
            <div className="flex flex-col gap-4">
              <div className="flex justify-between items-center mb-2">
                <div>
                  <h3 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text">Campaigns</h3>
                  <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">Monitor and create campaigns for this client.</p>
                </div>
                <button 
                  className="bg-primary text-on-primary dark:bg-molten-primary rounded-lg py-2 px-4 font-label-md flex items-center gap-2 hover:-translate-y-[1px] transition-transform active:scale-95 shadow-[inset_0_1px_0_rgba(255,255,255,0.2)]"
                  onClick={openCampaignModal}
                >
                  <span className="material-symbols-outlined text-[18px]">add</span>
                  Create Campaign
                </button>
              </div>
              
              <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden section">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse min-w-[700px]">
                    <thead>
                      <tr className="border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36]">
                        <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">Name</th>
                        <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider text-right">Budget</th>
                        <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider text-right">Leads</th>
                        <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider">Status</th>
                        <th className="py-3 px-4 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="font-body-md text-body-md text-on-surface dark:text-molten-text divide-y divide-outline-variant/50 dark:divide-[#2A345E]/50">
                      {campaigns.map(camp => (
                        <tr 
                          key={camp.id} 
                          onClick={() => openCampaignDrawer(camp)}
                          className="border-b border-outline-variant dark:border-[#2A345E] last:border-0 hover:bg-surface-container dark:hover:bg-[#2A345E]/50 transition-colors cursor-pointer"
                        >
                          <td className="py-3 px-4 font-medium">
                            <div className="flex flex-col">
                              <span>{camp.name}</span>
                              <div className="flex items-center gap-1.5 mt-0.5 group/uuid" onClick={(e) => handleCopyCampaignId(e, camp.id)}>
                                <span className="text-xs text-arctic-text-muted dark:text-molten-text-muted font-mono select-all">
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
                          <td className="py-3 px-4 text-right tabular-nums">
                            ₹{camp.budget_credits?.toFixed(2)}<br/>
                            <span className="text-xs text-arctic-text-muted dark:text-molten-text-muted">Used: ₹{camp.budget_used_credits?.toFixed(2)}</span>
                          </td>
                          <td className="py-3 px-4 text-right tabular-nums">
                            {camp.total_leads}<br/>
                            <span className="text-xs text-arctic-text-muted dark:text-molten-text-muted">{camp.completed_leads} done</span>
                          </td>
                          <td className="py-3 px-4">{renderCampaignStatus(camp.status)}</td>
                          <td className="py-3 px-4 text-right">
                            <div className="flex justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                              {(camp.status === 'running' || camp.status === 'pausing') && (
                                <button 
                                  onClick={(e) => { e.stopPropagation(); handleCampaignAction('stop', camp.id); }}
                                  className="px-2 py-1 text-xs rounded bg-arctic-warning/20 dark:bg-molten-warning/20 text-arctic-warning dark:text-molten-warning hover:opacity-80"
                                >Stop</button>
                              )}
                              {(camp.status === 'draft' || camp.status === 'paused') && (
                                <button 
                                  onClick={(e) => { e.stopPropagation(); handleCampaignAction('start', camp.id); }}
                                  className="px-2 py-1 text-xs rounded bg-primary/20 dark:bg-molten-primary/20 text-primary dark:text-molten-primary hover:opacity-80"
                                >Start</button>
                              )}
                              {(camp.status !== 'completed' && camp.status !== 'cancelled') && (
                                <button 
                                  onClick={(e) => { e.stopPropagation(); handleCampaignAction('cancel', camp.id); }}
                                  className="px-2 py-1 text-xs rounded bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error hover:opacity-80"
                                >Cancel</button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                      {campaigns.length === 0 && (
                        <tr>
                          <td colSpan="5" className="p-8 text-center text-arctic-text-muted dark:text-molten-text-muted">No campaigns found for this client.</td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Adjust Balance Modal Overlay */}
      {isModalOpen && (
        <div 
          className="fixed inset-0 bg-[#064E3B]/40 dark:bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeModal();
          }}
        >
          {/* Modal Content */}
          <div className={`bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col ${modalClosing ? 'modal-exit-active' : 'modal-enter-active'}`}>
            <div className="px-6 py-5 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-center bg-surface-container-lowest dark:bg-[#1A1E36]">
              <h3 className="font-headline-sm text-headline-sm font-bold text-on-surface dark:text-molten-text">Adjust Balance</h3>
              <button 
                className="text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text transition-colors"
                onClick={closeModal}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <div className="p-6 flex flex-col gap-5">
              <div>
                <label className="block font-label-md text-label-md text-on-surface dark:text-molten-text mb-2">Amount</label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant dark:text-molten-text-muted font-body-md">₹</span>
                  <input 
                    className="w-full bg-surface dark:bg-molten-bg border border-outline-variant dark:border-[#2A345E] rounded-lg pl-8 pr-4 py-2 font-body-md text-body-md text-on-surface dark:text-molten-text focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary focus:border-primary dark:focus:border-molten-primary dark:shadow-[inset_0_2px_4px_rgba(0,0,0,0.2)] transition-shadow" 
                    placeholder="0.00" 
                    type="number"
                    value={adjustAmount}
                    onChange={(e) => setAdjustAmount(e.target.value)}
                  />
                </div>
                <p className="mt-1 font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">Use negative values to deduct (e.g. -50.00)</p>
              </div>
              <div>
                <label className="block font-label-md text-label-md text-on-surface dark:text-molten-text mb-2">Note (Internal)</label>
                <textarea 
                  className="w-full bg-surface dark:bg-molten-bg border border-outline-variant dark:border-[#2A345E] rounded-lg px-4 py-2 font-body-md text-body-md text-on-surface dark:text-molten-text focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary focus:border-primary dark:focus:border-molten-primary dark:shadow-[inset_0_2px_4px_rgba(0,0,0,0.2)] transition-shadow resize-none" 
                  placeholder="Reason for adjustment..." 
                  rows="3"
                  value={adjustNote}
                  onChange={(e) => setAdjustNote(e.target.value)}
                ></textarea>
              </div>
            </div>
            <div className="px-6 py-4 border-t border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36] flex justify-end gap-3">
              <button 
                className="px-4 py-2 font-label-md text-label-md text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-inverse-surface rounded-lg transition-colors"
                onClick={closeModal}
              >
                Cancel
              </button>
              <button 
                className="bg-primary text-on-primary dark:bg-molten-primary rounded-lg py-2 px-5 font-label-md text-label-md shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:-translate-y-[1px] transition-transform active:scale-95 disabled:opacity-50"
                onClick={handleAdjustBalance}
                disabled={!adjustAmount}
              >
                Save Adjustment
              </button>
            </div>
          </div>
        </div>
      )}



      {/* Create Campaign Modal Overlay */}
      {isCampaignModalOpen && (
        <div 
          className="fixed inset-0 bg-[#064E3B]/40 dark:bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeCampaignModal();
          }}
        >
          <div className={`bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-xl shadow-2xl w-full max-w-lg overflow-hidden flex flex-col ${campaignModalClosing ? 'modal-exit-active' : 'modal-enter-active'}`}>
            <div className="px-6 py-5 border-b border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36] flex justify-between items-center">
              <h3 className="font-headline-sm font-bold text-on-surface dark:text-molten-text">Create Campaign</h3>
              <button 
                className="text-on-surface-variant dark:text-molten-text-muted hover:text-on-surface dark:hover:text-molten-text transition-colors"
                onClick={closeCampaignModal}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            <form onSubmit={handleCreateCampaign} className="p-6 flex flex-col gap-4 max-h-[70vh] overflow-y-auto">
              <div>
                <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Client</label>
                <input 
                  disabled
                  className="w-full bg-surface-container-high dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-4 py-2 font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted opacity-60" 
                  type="text" 
                  value={client.name} 
                />
              </div>
              <div>
                <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Bot Config</label>
                <select 
                  required
                  className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                  value={createCampaignData.bot_config_id}
                  onChange={e => setCreateCampaignData({...createCampaignData, bot_config_id: e.target.value})}
                >
                  <option className="dark:bg-[#1A1C24]" value="">Select a bot config...</option>
                  {botConfigs.map(b => (
                    <option className="dark:bg-[#1A1C24]" key={b.id} value={b.id}>
                      {b.name} ({b.route})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Campaign Name</label>
                <input 
                  required 
                  className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                  type="text" 
                  value={createCampaignData.name} 
                  onChange={e => setCreateCampaignData({...createCampaignData, name: e.target.value})} 
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Budget (₹)</label>
                  <input 
                    required 
                    className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                    type="number" 
                    step="0.01" 
                    min="0" 
                    value={createCampaignData.budget_credits} 
                    onChange={e => setCreateCampaignData({...createCampaignData, budget_credits: e.target.value})} 
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Concurrent Calls</label>
                  <input 
                    required 
                    className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                    type="number" 
                    min="1" 
                    value={createCampaignData.max_concurrent_calls} 
                    onChange={e => setCreateCampaignData({...createCampaignData, max_concurrent_calls: e.target.value})} 
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Calls / Min</label>
                  <input 
                    required 
                    className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                    type="number" 
                    min="1" 
                    value={createCampaignData.calls_per_minute} 
                    onChange={e => setCreateCampaignData({...createCampaignData, calls_per_minute: e.target.value})} 
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Max Call Mins</label>
                  <input 
                    className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                    type="number" 
                    min="1" 
                    value={createCampaignData.max_call_minutes} 
                    onChange={e => setCreateCampaignData({...createCampaignData, max_call_minutes: e.target.value})} 
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Max Attempts</label>
                  <input 
                    required 
                    className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                    type="number" 
                    min="1" 
                    value={createCampaignData.max_attempts} 
                    onChange={e => setCreateCampaignData({...createCampaignData, max_attempts: e.target.value})} 
                  />
                </div>
                <div>
                  <label className="block text-sm mb-1 font-label-md text-on-surface dark:text-molten-text">Retry Delay (min)</label>
                  <input 
                    required 
                    className="w-full p-2 rounded-lg bg-surface dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary" 
                    type="number" 
                    min="0" 
                    value={createCampaignData.retry_delay_minutes} 
                    onChange={e => setCreateCampaignData({...createCampaignData, retry_delay_minutes: e.target.value})} 
                  />
                </div>
              </div>
              <div className="pt-4 flex justify-end gap-2 border-t border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1E36] mt-2">
                <button 
                  type="button" 
                  onClick={closeCampaignModal} 
                  className="px-4 py-2 rounded-lg text-on-surface-variant dark:text-molten-text border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-[#2A345E]/50 transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  className="px-5 py-2 bg-primary dark:bg-molten-primary text-on-primary rounded-lg hover:opacity-90 transition-opacity"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Campaign Details Drawer */}
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
                  {renderCampaignStatus(selectedCampaign.status)}
                  {(selectedCampaign.status === 'running' || selectedCampaign.status === 'pausing') && (
                    <button onClick={() => handleCampaignAction('stop', selectedCampaign.id)} className="px-2 py-1 text-xs rounded bg-arctic-warning/20 dark:bg-molten-warning/20 text-arctic-warning dark:text-molten-warning hover:opacity-80">Stop</button>
                  )}
                  {(selectedCampaign.status === 'draft' || selectedCampaign.status === 'paused') && (
                    <button onClick={() => handleCampaignAction('start', selectedCampaign.id)} className="px-2 py-1 text-xs rounded bg-primary/20 dark:bg-molten-primary/20 text-primary dark:text-molten-primary hover:opacity-80">Start</button>
                  )}
                  {(selectedCampaign.status !== 'completed' && selectedCampaign.status !== 'cancelled') && (
                    <button onClick={() => handleCampaignAction('cancel', selectedCampaign.id)} className="px-2 py-1 text-xs rounded bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error hover:opacity-80">Cancel</button>
                  )}
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
    </>
  );
}
