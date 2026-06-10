import React, { useState, useEffect, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import adminApi from '../../api/admin';
import './AdminClientDetail.css';

export default function AdminClientDetail() {
  const { id } = useParams();
  
  const [activeTab, setActiveTab] = useState('overview'); // 'overview', 'ledger', 'webhooks'
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalClosing, setModalClosing] = useState(false);
  const [adjustAmount, setAdjustAmount] = useState('');
  const [adjustNote, setAdjustNote] = useState('');
  const [isPulse, setIsPulse] = useState(false);

  const [client, setClient] = useState(null);
  const [ledger, setLedger] = useState([]);
  const [webhooks, setWebhooks] = useState([]);

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

        setClient(mappedClient);
        setLedger(txsMapped);
        setWebhooks(mappedWebhooks);
      } catch (error) {
        console.error("Failed to fetch client details", error);
      }
    };
    
    fetchDetails();
  }, [id]);

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
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
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
              <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6 shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none flex flex-col justify-center">
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
                <div className="font-headline-lg text-headline-lg tabular-nums text-on-surface dark:text-molten-text">
                  {client.total_calls?.toLocaleString()}
                </div>
              </div>
            </div>
          </div>

          {/* Ledger Tab */}
          <div className={`tab-content ${activeTab === 'ledger' ? 'active' : ''}`}>
            <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden">
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
            <div className="bg-arctic-surface dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg shadow-[0_4px_20px_rgba(22,71,232,0.05)] dark:shadow-none overflow-hidden">
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
        </div>
      </div>

      {/* Adjust Balance Modal Overlay */}
      {isModalOpen && (
        <div 
          className="fixed inset-0 bg-[#0c1941]/40 dark:bg-black/60 backdrop-blur-sm z-[100] flex items-center justify-center p-4"
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
    </>
  );
}
