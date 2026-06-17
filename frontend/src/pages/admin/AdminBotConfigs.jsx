import React, { useState, useEffect } from 'react';
import adminApi from '../../api/admin';
import './AdminBotConfigs.css';

export default function AdminBotConfigs() {
  const [bots, setBots] = useState([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalClosing, setModalClosing] = useState(false);
  const [editingBot, setEditingBot] = useState(null);
  const [editPrice, setEditPrice] = useState('');
  const [search, setSearch] = useState('');
  
  // Create Bot Config states
  const [clients, setClients] = useState([]);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [createClosing, setCreateClosing] = useState(false);
  const [newBotClientId, setNewBotClientId] = useState('');
  const [newBotName, setNewBotName] = useState('');
  const [newBotRoute, setNewBotRoute] = useState('sts');
  const [newBotScriptId, setNewBotScriptId] = useState('');
  const [newBotScriptConfigId, setNewBotScriptConfigId] = useState('');
  const [newBotTelephonyNumber, setNewBotTelephonyNumber] = useState('');
  const [newBotCreditsPerMinute, setNewBotCreditsPerMinute] = useState('');
  const [createError, setCreateError] = useState('');
  const [scriptConfigs, setScriptConfigs] = useState([]);

  useEffect(() => {
    fetchBots();
  }, []);

  const fetchBots = async () => {
    try {
      const response = await adminApi.get('/internal/bot-configs');
      const botConfigs = response.data.bot_configs || [];
      const mapped = botConfigs.map(bot => {
        const isOnline = bot.active;
        return {
          id: bot.id,
          name: bot.name,
          code: `${bot.route?.toUpperCase() || ''} // ${bot.script_id || ''}`,
          status: isOnline ? 'ONLINE' : 'STANDBY',
          stateText: bot.script_id?.toUpperCase() || 'IDLE_STATE',
          colorTheme: isOnline ? 'secondary-container' : 'arctic-warning',
          textColorClass: isOnline ? 'text-secondary dark:text-secondary-container' : 'text-arctic-warning dark:text-arctic-warning',
          bgColorClass: isOnline ? 'bg-secondary/15 dark:bg-[#0a0e17]' : 'bg-arctic-warning/15 dark:bg-[#0a0e17]',
          borderColorClass: isOnline ? 'border-secondary/20 dark:border-[#2a345e]' : 'border-arctic-warning/20 dark:border-[#2a345e]',
          price: bot.credits_per_minute || 0,
          active: bot.active,
          route: bot.route,
          script_id: bot.script_id,
          telephony_number: bot.telephony_number
        };
      });
      setBots(mapped);
    } catch (error) {
      console.error("Failed to fetch bots", error);
    }
  };

  const fetchClients = async () => {
    try {
      const res = await adminApi.get('/internal/clients');
      setClients(res.data.clients || res.data || []);
      
      const scRes = await adminApi.get('/internal/script-configs');
      setScriptConfigs(scRes.data.script_configs || []);
    } catch (error) {
      console.error("Failed to fetch clients or script configs", error);
    }
  };

  const openPriceModal = (bot) => {
    setEditingBot(bot);
    setEditPrice(bot.price.toFixed(2));
    setModalClosing(false);
    setIsModalOpen(true);
  };

  const closePriceModal = () => {
    setModalClosing(true);
    setTimeout(() => {
      setIsModalOpen(false);
      setEditingBot(null);
      setModalClosing(false);
    }, 200);
  };

  const savePrice = async () => {
    if (!editingBot || !editPrice) return;
    try {
      const newPrice = parseFloat(editPrice) || 0;
      await adminApi.patch(`/internal/bot-configs/${editingBot.id}`, {
        credits_per_minute: newPrice
      });
      
      setBots(bots.map(b => b.id === editingBot.id ? { ...b, price: newPrice } : b));
      closePriceModal();
    } catch (error) {
      console.error("Failed to save price", error);
      closePriceModal();
    }
  };

  const openCreateModal = () => {
    fetchClients();
    setCreateClosing(false);
    setIsCreateModalOpen(true);
  };
  
  const closeCreateModal = () => {
    setCreateClosing(true);
    setTimeout(() => {
      setIsCreateModalOpen(false);
      setNewBotClientId('');
      setNewBotName('');
      setNewBotRoute('sts');
      setNewBotScriptId('');
      setNewBotScriptConfigId('');
      setNewBotTelephonyNumber('');
      setNewBotCreditsPerMinute('');
      setCreateError('');
      setCreateClosing(false);
    }, 200);
  };

  const handleCreateBotConfig = async (e) => {
    e.preventDefault();
    setCreateError('');
    
    if (!newBotClientId || !newBotName || !newBotRoute || !newBotScriptId || !newBotTelephonyNumber || !newBotCreditsPerMinute) {
      setCreateError('All fields are required.');
      return;
    }
    
    const scriptIdRegex = /^[a-z][a-z0-9_]*$/;
    if (!scriptIdRegex.test(newBotScriptId)) {
      setCreateError('Script ID must start with a lowercase letter and contain only lowercase letters, numbers, and underscores (e.g. ^[a-z][a-z0-9_]*$).');
      return;
    }
    
    try {
      await adminApi.post('/internal/bot-configs', {
        client_id: newBotClientId,
        name: newBotName,
        route: newBotRoute,
        script_id: newBotScriptId,
        script_config_id: newBotScriptConfigId || null,
        telephony_number: newBotTelephonyNumber,
        credits_per_minute: parseFloat(newBotCreditsPerMinute)
      });
      
      fetchBots();
      closeCreateModal();
    } catch (error) {
      console.error("Failed to create bot config", error);
      setCreateError(error.customErrorMessage || error.message || 'Failed to create bot config.');
    }
  };

  return (
    <>
      <div className="flex justify-between items-end mb-stack-lg">
        <div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text mb-2">Active Synthesizers</h2>
          <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted">Configure pricing and monitor neural output for deployed agents.</p>
        </div>
        <div className="flex gap-2">
          <input 
            type="text"
            placeholder="Search bots"
            className="px-4 py-2 bg-surface-container-lowest dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm text-on-surface dark:text-molten-text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button 
            onClick={openCreateModal}
            className="px-4 py-2 rounded-lg bg-primary dark:bg-molten-primary text-white dark:text-molten-bg font-label-md text-label-md hover:brightness-110 hover:-translate-y-px active:translate-y-0 transition-all flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">add</span> Create Bot Config
          </button>
        </div>
      </div>

      {/* Grid of Audio Rack Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-gutter">
        {bots.filter(b => b.name.toLowerCase().includes(search.toLowerCase()) || b.code.toLowerCase().includes(search.toLowerCase())).map((bot) => (
          <div key={bot.id} className="bot-card bg-arctic-surface dark:bg-molten-surface rounded-lg p-stack-md relative border border-outline-variant/30 dark:border-[#2A345E] flex flex-col min-h-[250px]">
            <div className="rack-screw top-2 left-2"></div>
            <div className="rack-screw top-2 right-2"></div>
            <div className="rack-screw bottom-2 left-2"></div>
            <div className="rack-screw bottom-2 right-2"></div>
            
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="font-headline-sm text-headline-sm text-on-surface dark:text-molten-text">{bot.name}</h3>
                <p className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted mt-1 uppercase tracking-wider">{bot.code}</p>
              </div>
              <div className={`flex items-center gap-1.5 ${bot.bgColorClass} px-2 py-1 rounded border ${bot.borderColorClass}`}>
                <div className={`w-2 h-2 rounded-full bg-${bot.colorTheme === 'secondary-container' ? 'secondary' : bot.colorTheme} dark:bg-${bot.colorTheme} shadow-[0_0_8px_var(--color-${bot.colorTheme})]`}></div>
                <span className={`font-label-sm text-label-sm ${bot.textColorClass}`}>{bot.status}</span>
              </div>
            </div>

            <div className="waveform-container h-16 bg-surface-container-low dark:bg-[#0a0e17] rounded border border-outline-variant/50 dark:border-[#2a345e] mb-4 flex items-center justify-center relative overflow-hidden">
              <svg className="absolute inset-0 px-2 pt-2 pb-2" height="100%" preserveAspectRatio="none" viewBox="0 0 100 40" width="100%">
                {[5, 15, 25, 35, 45, 55, 65, 75, 85, 95].map((x, i) => (
                  <rect key={i} className={`waveform-bar fill-${bot.colorTheme === 'arctic-warning' ? 'arctic-warning' : bot.colorTheme === 'secondary-container' ? 'secondary' : 'primary-container'} dark:fill-${bot.colorTheme === 'arctic-warning' ? 'arctic-warning' : bot.colorTheme === 'secondary-container' ? 'secondary-container' : 'primary-container'}`} height="80%" rx="1" width="3%" x={`${x}%`} y="10%"></rect>
                ))}
              </svg>
              <span className={`font-label-sm text-label-sm ${bot.textColorClass} z-10 font-mono tracking-widest opacity-70 dark:opacity-50`}>
                {bot.stateText}
              </span>
            </div>

            <div className="flex justify-between items-center border-t border-outline-variant/50 dark:border-[#2a345e] pt-4 mt-auto">
              <div className="flex flex-col">
                <span className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted">RATE (INR/HR)</span>
                <span className="font-body-lg text-body-lg text-on-surface dark:text-molten-text tabular-nums font-medium">₹{bot.price?.toFixed(2)}</span>
              </div>
              <button 
                className="px-4 py-2 bg-primary dark:bg-molten-primary text-on-primary font-label-md text-label-md rounded-lg shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:bg-primary-fixed-variant dark:hover:brightness-90 transition-colors flex items-center gap-2"
                onClick={() => openPriceModal(bot)}
              >
                <span className="material-symbols-outlined text-[18px]" data-icon="tune">tune</span> Edit Price
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Edit Price Modal */}
      {isModalOpen && (
        <div 
          className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) closePriceModal();
          }}
        >
          <div className={`bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-lg shadow-[0_10px_40px_rgba(22,71,232,0.1)] dark:shadow-2xl w-full max-w-md border border-outline-variant/50 dark:border-[#2A345E] transition-all duration-200 ${modalClosing ? 'scale-95 opacity-0' : 'scale-100 opacity-100'}`}>
            <div className="flex justify-between items-center mb-stack-md">
              <h3 className="font-headline-md text-headline-md text-on-surface dark:text-molten-text">Edit: {editingBot?.name}</h3>
              <button 
                className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"
                onClick={closePriceModal}
              >
                <span className="material-symbols-outlined" data-icon="close">close</span>
              </button>
            </div>
            <p className="font-body-sm text-body-sm text-on-surface-variant dark:text-molten-text-muted mb-stack-md">Adjust the hourly billing rate for this neural agent. Changes take effect immediately for new sessions.</p>
            <div className="mb-stack-lg">
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-2 uppercase tracking-wide">Hourly Rate (INR)</label>
              <div className="relative">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 font-body-md text-on-surface-variant dark:text-molten-text-muted">₹</span>
                <input 
                  className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg pl-8 pr-4 py-2.5 font-body-md text-body-md text-on-surface dark:text-molten-text tabular-nums focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors" 
                  type="text" 
                  value={editPrice}
                  onChange={(e) => setEditPrice(e.target.value)}
                />
              </div>
            </div>
            <div className="flex justify-end gap-3">
              <button 
                className="px-5 py-2.5 rounded-lg border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text font-label-md text-label-md hover:bg-surface-container-low dark:hover:bg-molten-surface transition-colors"
                onClick={closePriceModal}
              >
                Cancel
              </button>
              <button 
                className="px-5 py-2.5 rounded-lg bg-primary dark:bg-molten-primary text-on-primary font-label-md text-label-md shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:bg-primary-fixed-variant dark:hover:brightness-90 transition-colors"
                onClick={savePrice}
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Create Bot Config Modal */}
      {isCreateModalOpen && (
        <div 
          className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) closeCreateModal();
          }}
        >
          <div className={`bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-lg shadow-[0_10px_40px_rgba(22,71,232,0.1)] dark:shadow-2xl w-full max-w-md border border-outline-variant/50 dark:border-[#2A345E] transition-all duration-200 ${createClosing ? 'scale-95 opacity-0' : 'scale-100 opacity-100'}`}>
            <div className="flex justify-between items-center mb-stack-md">
              <h3 className="font-headline-md text-headline-md text-on-surface dark:text-molten-text">Create Bot Config</h3>
              <button 
                className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"
                onClick={closeCreateModal}
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>
            
            {createError && (
              <div className="mb-4 p-3 bg-arctic-error/15 border border-arctic-error/30 text-arctic-error dark:text-molten-error rounded-lg text-sm">
                {createError}
              </div>
            )}
            
            <form onSubmit={handleCreateBotConfig} className="space-y-4">
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">Client</label>
                <select 
                  className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                  value={newBotClientId}
                  onChange={(e) => setNewBotClientId(e.target.value)}
                  required
                >
                  <option value="">Select a Client</option>
                  {clients.map(c => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">Name</label>
                <input 
                  className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                  placeholder="e.g. Inbound Intake Bot"
                  type="text"
                  value={newBotName}
                  onChange={(e) => setNewBotName(e.target.value)}
                  required
                />
              </div>
              
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">Script Template</label>
                <select 
                  className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                  value={newBotScriptConfigId}
                  onChange={(e) => {
                    setNewBotScriptConfigId(e.target.value);
                    const selectedConfig = scriptConfigs.find(sc => sc.id === e.target.value);
                    if (selectedConfig) {
                      setNewBotScriptId(selectedConfig.script_id);
                      setNewBotRoute(selectedConfig.route);
                    } else {
                      setNewBotScriptId('');
                      setNewBotRoute('');
                    }
                  }}
                  required
                >
                  <option value="">Select a Template</option>
                  {scriptConfigs.filter(sc => !newBotClientId || sc.client_id === newBotClientId).map(sc => (
                    <option key={sc.id} value={sc.id}>{sc.script_id} (v{sc.version}) - {sc.route}</option>
                  ))}
                </select>
              </div>
              
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">Telephony Number</label>
                <input 
                  className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                  placeholder="e.g. +14155552671"
                  type="text"
                  value={newBotTelephonyNumber}
                  onChange={(e) => setNewBotTelephonyNumber(e.target.value)}
                  required
                />
              </div>
              
              <div>
                <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">Credits Per Minute</label>
                <input 
                  className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                  placeholder="e.g. 0.50"
                  type="number"
                  step="0.01"
                  value={newBotCreditsPerMinute}
                  onChange={(e) => setNewBotCreditsPerMinute(e.target.value)}
                  required
                />
              </div>
              
              <div className="flex justify-end gap-3 pt-2">
                <button 
                  type="button"
                  className="px-5 py-2.5 rounded-lg border border-outline-variant dark:border-[#2A345E] text-on-surface dark:text-molten-text font-label-md text-label-md hover:bg-surface-container-low dark:hover:bg-molten-surface transition-colors"
                  onClick={closeCreateModal}
                >
                  Cancel
                </button>
                <button 
                  type="submit"
                  className="px-5 py-2.5 rounded-lg bg-primary dark:bg-molten-primary text-on-primary font-label-md text-label-md shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:bg-primary-fixed-variant dark:hover:brightness-90 transition-colors"
                >
                  Create
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
