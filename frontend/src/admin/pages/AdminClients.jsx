import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import adminApi from '../../shared/api/admin';


export default function AdminClients() {
  const [clients, setClients] = useState([]);
  const [filteredClients, setFilteredClients] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newClientName, setNewClientName] = useState('');
  const [newClientIndustry, setNewClientIndustry] = useState('other');
  const [generatedApiKey, setGeneratedApiKey] = useState(null);
  const [isCopied, setIsCopied] = useState(false);
  
  const [isRegenModalOpen, setIsRegenModalOpen] = useState(false);
  const [regenClient, setRegenClient] = useState(null);
  const [regenApiKey, setRegenApiKey] = useState(null);
  const [isRegenCopied, setIsRegenCopied] = useState(false);
  const [copiedId, setCopiedId] = useState(null);

  const navigate = useNavigate();

  const fetchClients = async () => {
    try {
      const response = await adminApi.get('/internal/clients');
      const data = response.data.clients || response.data || [];
      const mapped = data.map(client => ({
        ...client,
        balance: client.balance_credits,
        use_case: client.industry,
        status: client.active ? 'Active' : 'Suspended'
      }));
      setClients(mapped);
    } catch (error) {
      console.error("Failed to fetch clients", error);
    }
  };

  useEffect(() => {
    fetchClients();
  }, []);

  useEffect(() => {
    if (!searchQuery) {
      setFilteredClients(clients);
    } else {
      const lower = searchQuery.toLowerCase();
      setFilteredClients(clients.filter(c => 
        (c.name && c.name.toLowerCase().includes(lower)) || 
        (c.use_case && c.use_case.toLowerCase().includes(lower))
      ));
    }
  }, [searchQuery, clients]);

  const handleCreateClient = async () => {
    if (!newClientName) return;
    try {
      const response = await adminApi.post('/internal/clients', {
        name: newClientName,
        industry: newClientIndustry,
        contact_email: ""
      });
      
      const createdClient = {
        id: response.data.id,
        name: newClientName,
        industry: newClientIndustry,
        use_case: newClientIndustry,
        active: true,
        status: 'Active',
        balance_credits: 0,
        balance: 0,
        last_active: 'Just now'
      };
      
      setGeneratedApiKey(response.data.api_key);
      setClients(prev => [createdClient, ...prev]);
    } catch (error) {
      console.error("Failed to create client", error);
    }
  };

  const copyApiKey = () => {
    if (generatedApiKey) {
      navigator.clipboard.writeText(generatedApiKey);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    }
  };

  const copyRegenApiKey = () => {
    if (regenApiKey) {
      navigator.clipboard.writeText(regenApiKey);
      setIsRegenCopied(true);
      setTimeout(() => setIsRegenCopied(false), 2000);
    }
  };

  const copyClientId = (e, id) => {
    e.stopPropagation();
    navigator.clipboard.writeText(id);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleRegenerateKey = async (client) => {
    if (!window.confirm(`Regenerate API key for ${client.name}? The old key will immediately stop working.`)) return;
    try {
      const response = await adminApi.post(`/internal/clients/${client.id}/regenerate-key`);
      setRegenApiKey(response.data.api_key);
      setRegenClient(client);
      setIsRegenModalOpen(true);
    } catch (error) {
      alert("Failed to regenerate API key.");
    }
  };

  const resetModal = () => {
    setIsModalOpen(false);
    setTimeout(() => {
      setNewClientName('');
      setNewClientIndustry('other');
      setGeneratedApiKey(null);
      setIsCopied(false);
    }, 300);
  };

  const resetRegenModal = () => {
    setIsRegenModalOpen(false);
    setTimeout(() => {
      setRegenApiKey(null);
      setRegenClient(null);
      setIsRegenCopied(false);
    }, 300);
  };

  const activeCount = clients.filter(c => c.status && c.status.toLowerCase() === 'active').length;

  return (
    <>
      {/* Main Content Area */}
      <div className="w-full section">
        {/* Header */}
        <div className="flex justify-between items-end mb-stack-lg">
          <div>
            <h1 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">Client Management</h1>
            <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted mt-2">
              Manage API access, billing, and usage for enterprise partners.
            </p>
          </div>
          <button 
            className="bg-primary dark:bg-molten-primary text-on-primary font-label-md text-label-md px-6 py-2.5 rounded-lg btn-tactile hover:brightness-90 hover:-translate-y-px transition-all flex items-center gap-2" 
            onClick={() => setIsModalOpen(true)}
          >
            <span className="material-symbols-outlined text-[18px]">add</span>
            Create New Client
          </button>
        </div>

        {/* Filters & Stats (Bento Grid Style) */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-gutter mb-stack-lg section">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-md border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none">
            <p className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase">Total Clients</p>
            <p className="font-headline-md text-headline-md text-on-surface dark:text-molten-text mt-1 tabular-nums">{clients.length}</p>
          </div>
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-md border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none">
            <p className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase">Active</p>
            <p className="font-headline-md text-headline-md text-secondary dark:text-molten-success mt-1 tabular-nums">{activeCount}</p>
          </div>
          <div className="md:col-span-2 bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-md border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none flex items-center justify-between">
            <div className="relative w-full max-w-sm">
              <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline text-sm">search</span>
              <input 
                className="w-full pl-9 pr-4 py-2 bg-background dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm focus:outline-none focus:border-primary dark:focus:border-molten-primary font-body-sm text-body-sm text-on-surface dark:text-molten-text placeholder:text-outline" 
                placeholder="Filter by name or use case..." 
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <div className="flex gap-2">
              <button className="p-2 border border-outline-variant dark:border-[#2A345E] rounded-lg text-outline hover:bg-surface-container dark:hover:bg-molten-surface transition-colors">
                <span className="material-symbols-outlined text-[18px]">filter_list</span>
              </button>
            </div>
          </div>
        </div>

        {/* Data Table */}
        <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg border border-outline-variant/50 dark:border-[#2A345E] shadow-arctic dark:shadow-none overflow-hidden section">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-outline-variant/50 dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1A24]/50">
                  <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Client Name</th>
                  <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Use Case</th>
                  <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Status</th>
                  <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold text-right">Credit Balance</th>
                  <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Last Active</th>
                  <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold text-center">Actions</th>
                </tr>
              </thead>
              <tbody className="font-body-sm text-body-sm">
                {filteredClients.map((client) => {
                  const isActive = client.status && client.status.toLowerCase() === 'active';
                  const isNegative = client.balance < 0;
                  
                  return (
                    <tr 
                      key={client.id} 
                      className="border-b border-outline-variant/20 dark:border-[#2A345E]/50 table-row-hover" 
                      onClick={() => navigate(`/admin/clients/${client.id}`)}
                    >
                      <td className="px-4 py-3">
                        <div className="font-medium text-on-surface dark:text-molten-text">{client.name}</div>
                        <div className="flex items-center gap-1 mt-0.5 group/id" onClick={(e) => copyClientId(e, client.id)}>
                          <span className="font-mono text-[10px] text-on-surface-variant dark:text-molten-text-muted select-all">
                            {client.id}
                          </span>
                          <button className={`p-0.5 rounded opacity-0 group-hover/id:opacity-100 transition-opacity flex items-center justify-center ${copiedId === client.id ? 'text-secondary dark:text-molten-success' : 'text-outline hover:bg-surface-variant dark:hover:bg-[#2A345E]'}`}>
                            <span className="material-symbols-outlined text-[12px]">{copiedId === client.id ? 'check' : 'content_copy'}</span>
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-on-surface-variant dark:text-molten-text-muted">{client.use_case}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${isActive ? 'bg-secondary/15 text-secondary dark:bg-molten-success/15 dark:text-molten-success' : 'bg-arctic-error/15 text-arctic-error dark:bg-molten-error/15 dark:text-molten-error'}`}>
                          {client.status}
                        </span>
                      </td>
                      <td className={`px-4 py-3 text-right font-headline-sm text-[16px] tabular-nums ${isNegative ? 'text-arctic-error dark:text-molten-error' : 'text-on-surface dark:text-molten-text'}`}>
                        {isNegative ? '-' : ''}${Math.abs(client.balance || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className="px-4 py-3 text-on-surface-variant dark:text-molten-text-muted">{client.last_active}</td>
                      <td className="px-4 py-3 text-center" onClick={(e) => e.stopPropagation()}>
                        <button 
                          className="text-outline hover:text-primary dark:hover:text-molten-primary p-1.5 rounded hover:bg-surface-variant dark:hover:bg-[#2A345E] transition-colors"
                          onClick={() => handleRegenerateKey(client)}
                          title="Regenerate API Key"
                        >
                          <span className="material-symbols-outlined text-[18px]">key</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Create Client Modal */}
      <div 
        className={`fixed inset-0 bg-on-surface/30 dark:bg-black/60 z-[80] modal-overlay backdrop-blur-sm flex items-center justify-center p-4 ${isModalOpen ? 'open' : ''}`} 
        onClick={(e) => e.target === e.currentTarget && resetModal()}
      >
        <div className={`bg-surface dark:bg-[#1A1A24] rounded-xl border border-outline-variant/50 dark:border-[#2A345E] shadow-2xl w-full max-w-md modal flex flex-col overflow-hidden ${isModalOpen ? 'open' : ''}`}>
          <div className="p-6 border-b border-outline-variant/30 dark:border-[#2A345E] flex justify-between items-center">
            <h2 className="font-headline-sm text-headline-sm text-on-surface dark:text-molten-text">Create New Client</h2>
            <button 
              className="p-1 text-outline hover:text-on-surface dark:hover:text-molten-text rounded-full transition-colors" 
              onClick={resetModal}
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          
          <div className="p-6 space-y-5">
            {!generatedApiKey ? (
              <>
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted mb-1.5 uppercase">Client Name</label>
                  <input 
                    className="w-full px-3 py-2 bg-background dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm focus:outline-none focus:border-primary dark:focus:border-molten-primary font-body-sm text-body-sm text-on-surface dark:text-molten-text dark:shadow-[inset_0_1px_2px_rgba(0,0,0,0.3)] placeholder:text-outline" 
                    placeholder="e.g. Acme Corp" 
                    type="text"
                    value={newClientName}
                    onChange={(e) => setNewClientName(e.target.value)}
                  />
                </div>
                <div>
                  <label className="block font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted mb-1.5 uppercase">Industry</label>
                  <select 
                    className="w-full px-3 py-2 bg-background dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm focus:outline-none focus:border-primary dark:focus:border-molten-primary font-body-sm text-body-sm text-on-surface dark:text-molten-text dark:shadow-[inset_0_1px_2px_rgba(0,0,0,0.3)]"
                    value={newClientIndustry}
                    onChange={(e) => setNewClientIndustry(e.target.value)}
                  >
                    <option value="real_estate">Real Estate</option>
                    <option value="insurance">Insurance</option>
                    <option value="edtech">EdTech</option>
                    <option value="lending">Lending</option>
                    <option value="healthcare">Healthcare</option>
                    <option value="other">Other</option>
                  </select>
                </div>
              </>
            ) : (
              <div className="pt-2">
                <label className="block font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted mb-1.5 uppercase">Generated API Key</label>
                <div className="flex gap-2">
                  <div className="flex-1 bg-surface-container dark:bg-[#141210] border border-outline-variant/50 dark:border-[#2A345E] rounded-lg px-3 py-2 flex items-center overflow-hidden">
                    <span className="font-body-sm text-body-sm text-on-surface dark:text-molten-text font-mono truncate select-all">{generatedApiKey}</span>
                  </div>
                  <button 
                    className={`btn-copy bg-surface-container-high dark:bg-[#2A345E] border border-outline-variant/50 dark:border-[#424B75] px-3 py-2 rounded-lg text-on-surface-variant dark:text-molten-text flex items-center justify-center ${isCopied ? 'copied' : ''}`} 
                    onClick={copyApiKey}
                  >
                    <span className="material-symbols-outlined text-[20px]">
                      {isCopied ? 'check' : 'content_copy'}
                    </span>
                  </button>
                </div>
                <p className="font-label-sm text-[11px] text-arctic-warning dark:text-molten-warning mt-2 flex items-center gap-1">
                  <span className="material-symbols-outlined text-[14px]">warning</span>
                  Copy this key now. You won't be able to see it again.
                </p>
              </div>
            )}
          </div>
          
          <div className="p-6 pt-0 flex justify-end gap-3 mt-2">
            {generatedApiKey ? (
              <button 
                className="px-5 py-2 rounded-lg font-label-md text-label-md bg-primary dark:bg-molten-primary text-on-primary btn-tactile hover:brightness-90 transition-all w-full"
                onClick={resetModal}
              >
                Done
              </button>
            ) : (
              <>
                <button 
                  className="px-4 py-2 rounded-lg font-label-md text-label-md text-on-surface-variant dark:text-molten-text border border-outline-variant dark:border-[#2A345E] hover:bg-surface-container dark:hover:bg-molten-surface transition-colors" 
                  onClick={resetModal}
                >
                  Cancel
                </button>
                <button 
                  className="px-5 py-2 rounded-lg font-label-md text-label-md bg-primary dark:bg-molten-primary text-on-primary btn-tactile hover:brightness-90 transition-all disabled:opacity-50"
                  onClick={handleCreateClient}
                  disabled={!newClientName}
                >
                  Create Client
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Regenerate Key Modal */}
      <div 
        className={`fixed inset-0 bg-on-surface/30 dark:bg-black/60 z-[80] modal-overlay backdrop-blur-sm flex items-center justify-center p-4 ${isRegenModalOpen ? 'open' : ''}`} 
        onClick={(e) => e.target === e.currentTarget && resetRegenModal()}
      >
        <div className={`bg-surface dark:bg-[#1A1A24] rounded-xl border border-outline-variant/50 dark:border-[#2A345E] shadow-2xl w-full max-w-md modal flex flex-col overflow-hidden ${isRegenModalOpen ? 'open' : ''}`}>
          <div className="p-6 border-b border-outline-variant/30 dark:border-[#2A345E] flex justify-between items-center">
            <h2 className="font-headline-sm text-headline-sm text-on-surface dark:text-molten-text">New API Key</h2>
            <button 
              className="p-1 text-outline hover:text-on-surface dark:hover:text-molten-text rounded-full transition-colors" 
              onClick={resetRegenModal}
            >
              <span className="material-symbols-outlined">close</span>
            </button>
          </div>
          
          <div className="p-6">
            <div className="pt-2">
              <label className="block font-label-sm text-label-sm text-on-surface-variant dark:text-molten-text-muted mb-1.5 uppercase">API Key for {regenClient?.name}</label>
              <div className="flex gap-2">
                <div className="flex-1 bg-surface-container dark:bg-[#141210] border border-outline-variant/50 dark:border-[#2A345E] rounded-lg px-3 py-2 flex items-center overflow-hidden">
                  <span className="font-body-sm text-body-sm text-on-surface dark:text-molten-text font-mono truncate select-all">{regenApiKey}</span>
                </div>
                <button 
                  className={`btn-copy bg-surface-container-high dark:bg-[#2A345E] border border-outline-variant/50 dark:border-[#424B75] px-3 py-2 rounded-lg text-on-surface-variant dark:text-molten-text flex items-center justify-center ${isRegenCopied ? 'copied' : ''}`} 
                  onClick={copyRegenApiKey}
                >
                  <span className="material-symbols-outlined text-[20px]">
                    {isRegenCopied ? 'check' : 'content_copy'}
                  </span>
                </button>
              </div>
              <p className="font-label-sm text-[11px] text-arctic-warning dark:text-molten-warning mt-2 flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">warning</span>
                Copy this key now. The old key has been invalidated.
              </p>
            </div>
          </div>
          
          <div className="p-6 pt-0 flex justify-end mt-2">
            <button 
              className="px-5 py-2 rounded-lg font-label-md text-label-md bg-primary dark:bg-molten-primary text-on-primary btn-tactile hover:brightness-90 transition-all w-full"
              onClick={resetRegenModal}
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
