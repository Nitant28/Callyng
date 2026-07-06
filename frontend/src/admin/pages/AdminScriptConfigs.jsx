import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import adminApi from '../../shared/api/admin';

import ScriptingGuideModal from '../components/ScriptingGuideModal';

const parseConfigJSON = (str, fallback) => {
  try {
    return JSON.parse(str || 'null') || fallback;
  } catch {
    return fallback;
  }
};

/** Returns mapping validation state for save gating and inline warnings. */
function getOutcomeMappingState(editingConfig) {
  const schema = parseConfigJSON(editingConfig?.extraction_schema, {});
  const mode = schema?.mode;
  if (mode === 'summary') {
    return { isSummaryMode: true, valid: true, unmapped: [], orphans: [], allOutcomes: [] };
  }

  let allOutcomes = [];
  if (schema?.fields) {
    const intentField = schema.fields.find((f) => f.key === 'intent_status');
    if (intentField && Array.isArray(intentField.values)) {
      allOutcomes = intentField.values;
    }
  }

  const terminal = parseConfigJSON(editingConfig?.outcome_terminal, []);
  const callback = parseConfigJSON(editingConfig?.outcome_callback, []);
  const retry = parseConfigJSON(editingConfig?.outcome_retry, []);
  const mapped = new Set([...terminal, ...callback, ...retry]);
  const unmapped = allOutcomes.filter((o) => !mapped.has(o));
  const intentSet = new Set(allOutcomes);
  const orphans = [...mapped].filter((o) => allOutcomes.length > 0 && !intentSet.has(o));

  return {
    isSummaryMode: false,
    valid: allOutcomes.length === 0 ? true : unmapped.length === 0 && orphans.length === 0,
    unmapped,
    orphans,
    allOutcomes,
    terminal,
    callback,
    retry,
  };
}

const OutcomeDragDropEditor = ({ editingConfig, setEditingConfig }) => {
  const [showRawJson, setShowRawJson] = useState(false);
  const mapping = getOutcomeMappingState(editingConfig);
  const { isSummaryMode, unmapped, orphans, allOutcomes, terminal, callback, retry } = mapping;

  if (isSummaryMode) {
    return (
      <div className="mt-6 p-4 rounded-lg border border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1A24] text-xs text-on-surface-variant dark:text-molten-text-muted">
        Summary-mode schemas do not use outcome buckets. Switch extraction schema to <code>fields</code> or <code>both</code> to map intents.
      </div>
    );
  }

  if (allOutcomes.length === 0) {
    return (
      <div className="mt-6 p-4 rounded-lg border border-dashed border-outline-variant dark:border-[#2A345E] bg-surface-container-lowest dark:bg-[#1A1A24] text-xs text-on-surface-variant dark:text-molten-text-muted">
        Define an <code>intent_status</code> enum in the Extraction Schema first — its values will appear here as draggable pills.
      </div>
    );
  }

  const applyBuckets = (newTerminal, newCallback, newRetry) => {
    setEditingConfig({
      ...editingConfig,
      outcome_terminal: JSON.stringify(newTerminal, null, 2),
      outcome_callback: JSON.stringify(newCallback, null, 2),
      outcome_retry: JSON.stringify(newRetry, null, 2),
    });
  };

  const handleDragStart = (e, item, source) => {
    e.dataTransfer.setData('text/plain', JSON.stringify({ item, source }));
  };

  const handleDrop = (e, targetZone) => {
    e.preventDefault();
    const data = e.dataTransfer.getData('text/plain');
    if (!data) return;
    try {
      const { item, source } = JSON.parse(data);
      if (source === targetZone) return;

      let newTerminal = [...terminal];
      let newCallback = [...callback];
      let newRetry = [...retry];

      if (source === 'terminal') newTerminal = newTerminal.filter((i) => i !== item);
      if (source === 'callback') newCallback = newCallback.filter((i) => i !== item);
      if (source === 'retry') newRetry = newRetry.filter((i) => i !== item);

      if (targetZone === 'unmapped') {
        applyBuckets(newTerminal, newCallback, newRetry);
        return;
      }

      if (targetZone === 'terminal' && !newTerminal.includes(item)) newTerminal.push(item);
      if (targetZone === 'callback' && !newCallback.includes(item)) newCallback.push(item);
      if (targetZone === 'retry' && !newRetry.includes(item)) newRetry.push(item);

      applyBuckets(newTerminal, newCallback, newRetry);
    } catch {
      /* ignore malformed drag payload */
    }
  };

  const allowDrop = (e) => e.preventDefault();

  const Pill = ({ item, source, stale = false }) => (
    <div
      draggable
      onDragStart={(e) => handleDragStart(e, item, source)}
      title={stale ? 'Stale — not in current extraction schema' : undefined}
      className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold cursor-grab active:cursor-grabbing border m-1 shadow-sm ${
        stale
          ? 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/40'
          : 'bg-surface-container-high dark:bg-[#2A345E] text-on-surface dark:text-molten-text border-outline-variant/50'
      }`}
    >
      <span className="material-symbols-outlined text-[14px] mr-1 opacity-50">drag_indicator</span>
      {item}
      {stale && <span className="ml-1 text-[10px] uppercase tracking-wide opacity-80">stale</span>}
    </div>
  );

  const renderZone = (items, source) =>
    items.map((o) => (
      <Pill key={`${source}-${o}`} item={o} source={source} stale={!allOutcomes.includes(o)} />
    ));

  return (
    <div className="mt-6 border border-outline-variant dark:border-[#2A345E] rounded-lg p-4 bg-surface-container-lowest dark:bg-[#1A1A24]">
      <h3 className="font-bold text-sm mb-2 text-on-surface dark:text-molten-text">Outcome Routing (Drag & Drop)</h3>
      <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-4 leading-relaxed">
        <strong>What they are:</strong> map each <code>intent_status</code> value to what the dialer does after the call.<br />
        <strong>Terminal</strong> → Completed · <strong>Callback</strong> → Callback Scheduled · <strong>Retry</strong> → Pending (then Failed after max attempts).<br />
        <strong>Golden rule:</strong> every intent must appear in exactly one bucket. Drag to move (not copy).
      </p>

      {(unmapped.length > 0 || orphans.length > 0) && (
        <div className="mb-4 p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-900 dark:text-amber-200">
          {unmapped.length > 0 && <div>Unmapped intents: {unmapped.join(', ')}</div>}
          {orphans.length > 0 && <div>Stale bucket values (remove or re-add to schema): {orphans.join(', ')}</div>}
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-4">
        <div
          className="flex-1 min-h-[120px] p-3 rounded-lg border-2 border-dashed border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#141210] transition-colors hover:border-primary/50"
          onDragOver={allowDrop}
          onDrop={(e) => handleDrop(e, 'unmapped')}
        >
          <div className="text-xs font-bold mb-2 text-on-surface-variant dark:text-molten-text-muted flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-gray-400"></span> Unmapped Outcomes
          </div>
          {unmapped.length === 0 && (
            <div className="text-xs text-emerald-600 dark:text-emerald-400 font-medium italic p-2">All outcomes mapped ✓</div>
          )}
          <div className="flex flex-wrap">{unmapped.map((o) => <Pill key={o} item={o} source="unmapped" />)}</div>
        </div>

        <div className="flex-[2] flex flex-col gap-3">
          <div
            className="p-3 rounded-lg border border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#141210] transition-colors hover:border-emerald-500/50"
            onDragOver={allowDrop}
            onDrop={(e) => handleDrop(e, 'terminal')}
          >
            <div className="text-xs font-bold mb-2 text-on-surface-variant dark:text-molten-text-muted flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span> Terminal → Completed
            </div>
            <div className="flex flex-wrap min-h-[32px]">{renderZone(terminal, 'terminal')}</div>
          </div>
          <div
            className="p-3 rounded-lg border border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#141210] transition-colors hover:border-blue-500/50"
            onDragOver={allowDrop}
            onDrop={(e) => handleDrop(e, 'callback')}
          >
            <div className="text-xs font-bold mb-2 text-on-surface-variant dark:text-molten-text-muted flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-500"></span> Callback → Callback Scheduled
            </div>
            <div className="flex flex-wrap min-h-[32px]">{renderZone(callback, 'callback')}</div>
          </div>
          <div
            className="p-3 rounded-lg border border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#141210] transition-colors hover:border-amber-500/50"
            onDragOver={allowDrop}
            onDrop={(e) => handleDrop(e, 'retry')}
          >
            <div className="text-xs font-bold mb-2 text-on-surface-variant dark:text-molten-text-muted flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-amber-500"></span> Retry → Pending → Failed
            </div>
            <div className="flex flex-wrap min-h-[32px]">{renderZone(retry, 'retry')}</div>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={() => setShowRawJson((v) => !v)}
        className="mt-4 text-xs font-semibold text-primary dark:text-molten-primary hover:underline"
      >
        {showRawJson ? 'Hide raw JSON buckets' : 'View / edit raw JSON buckets'}
      </button>
      {showRawJson && (
        <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-2 mb-3">
          Untouched bucket fields save as null and fall back to system defaults. Once you drag a pill or edit raw JSON, the field is saved explicitly — use [] only if you intend an empty bucket.
        </p>
      )}
      {showRawJson && (
        <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
          {[
            ['outcome_terminal', 'Terminal'],
            ['outcome_callback', 'Callback'],
            ['outcome_retry', 'Retry'],
          ].map(([field, label]) => (
            <div key={field}>
              <label className="block text-xs font-bold mb-1 text-on-surface dark:text-molten-text">{label}</label>
              <textarea
                rows={5}
                className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-2 py-2 text-xs text-on-surface dark:text-molten-text font-mono"
                value={editingConfig[field] || ''}
                onChange={(e) => setEditingConfig({ ...editingConfig, [field]: e.target.value })}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default function AdminScriptConfigs() {
  const [configs, setConfigs] = useState([]);
  const [clients, setClients] = useState([]);
  const [search, setSearch] = useState('');
  
  // Modals
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [isCreatorOpen, setIsCreatorOpen] = useState(false);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isDeployBotOpen, setIsDeployBotOpen] = useState(false);
  const [isGuideOpen, setIsGuideOpen] = useState(false);
  
  const navigate = useNavigate();
  
  // Create form
  const [newClientId, setNewClientId] = useState('');
  const [newRoute, setNewRoute] = useState('sts');
  const [newScriptId, setNewScriptId] = useState('');
  const [createError, setCreateError] = useState('');
  
  // Editor form
  const [editingConfig, setEditingConfig] = useState(null);
  const [activeTab, setActiveTab] = useState('general');
  const [saveError, setSaveError] = useState('');
  
  // History
  const [historyConfigs, setHistoryConfigs] = useState([]);
  const [selectedHistory, setSelectedHistory] = useState(null);

  // Deploy Bot form
  const [deployTemplate, setDeployTemplate] = useState(null);
  const [deployBotName, setDeployBotName] = useState('');
  const [deployTelephonyNumber, setDeployTelephonyNumber] = useState('');
  const [deployCredits, setDeployCredits] = useState('');
  const [deployError, setDeployError] = useState('');

  // Test Call form
  const [isTestCallOpen, setIsTestCallOpen] = useState(false);
  const [testCallPhone, setTestCallPhone] = useState('');
  const [testCallTelephonyNumber, setTestCallTelephonyNumber] = useState('');
  const [testCallMetadata, setTestCallMetadata] = useState('{\n  "lead_name": "Test Lead",\n  "city": ""\n}');
  const [testCallError, setTestCallError] = useState('');
  const [testCallSuccess, setTestCallSuccess] = useState('');

  const fetchClients = async () => {
    try {
      const res = await adminApi.get('/internal/clients');
      setClients(res.data.clients || res.data || []);
    } catch (error) {
      console.error("Failed to fetch clients", error);
    }
  };

  const fetchConfigs = async () => {
    try {
      const res = await adminApi.get('/internal/script-configs?active_only=false');
      setConfigs(res.data.script_configs || []);
    } catch (error) {
      console.error("Failed to fetch script configs", error);
    }
  };

  useEffect(() => {
    fetchClients();
    fetchConfigs();
  }, []);

  const getClientName = (clientId) => {
    const c = clients.find(c => c.id === clientId);
    return c ? c.name : 'Unknown Client';
  };

  // ----------------------------------------
  // Create Flow
  // ----------------------------------------
  const openCreator = () => {
    setNewClientId('');
    setNewRoute('sts');
    setNewScriptId('');
    setCreateError('');
    setIsCreatorOpen(true);
  };

  const handleCreateTemplateLoad = async (e) => {
    e.preventDefault();
    if (!newClientId || !newScriptId) {
      setCreateError('Client and Script ID are required.');
      return;
    }
    
    try {
      const res = await adminApi.get(`/internal/script-configs/template?route=${newRoute}`);
      const template = res.data.template;
      
      // Merge user selections
      template.client_id = newClientId;
      template.script_id = newScriptId;
      template.route = newRoute;
      
      setEditingConfig({
        ...template,
        // Convert JSON objects to strings for the textareas
        extraction_schema: JSON.stringify(template.extraction_schema || {}, null, 2),
        lead_schema: JSON.stringify(template.lead_schema || {fields: []}, null, 2),
        bootstrap_messages_json: JSON.stringify(template.bootstrap_messages_json || [], null, 2),
        goodbye_markers: JSON.stringify(template.goodbye_markers || [], null, 2),
        cascade_live_tools: JSON.stringify(template.cascade_live_tools || [], null, 2),
        normalization_rules: JSON.stringify(template.normalization_rules || [], null, 2),
        outcome_event_map: JSON.stringify(template.outcome_event_map || {}, null, 2),
        outcome_terminal: JSON.stringify(template.outcome_terminal || [], null, 2),
        outcome_retry: JSON.stringify(template.outcome_retry || [], null, 2),
        outcome_callback: JSON.stringify(template.outcome_callback || [], null, 2)
      });
      
      setIsCreatorOpen(false);
      setActiveTab('general');
      setIsEditorOpen(true);
    } catch (error) {
      console.error(error);
      setCreateError('Failed to load template.');
    }
  };

  // ----------------------------------------
  // Editor Flow
  // ----------------------------------------
  const openEditor = (config) => {
    setEditingConfig({
      ...config,
      extraction_schema: JSON.stringify(config.extraction_schema || {}, null, 2),
      lead_schema: JSON.stringify(config.lead_schema || {fields: []}, null, 2),
      bootstrap_messages_json: JSON.stringify(config.bootstrap_messages_json || [], null, 2),
      goodbye_markers: JSON.stringify(config.goodbye_markers || [], null, 2),
      cascade_live_tools: JSON.stringify(config.cascade_live_tools || [], null, 2),
      normalization_rules: JSON.stringify(config.normalization_rules || [], null, 2),
      outcome_event_map: JSON.stringify(config.outcome_event_map || {}, null, 2),
      outcome_terminal: JSON.stringify(config.outcome_terminal || [], null, 2),
      outcome_retry: JSON.stringify(config.outcome_retry || [], null, 2),
      outcome_callback: JSON.stringify(config.outcome_callback || [], null, 2)
    });
    setSaveError('');
    setActiveTab('general');
    setIsEditorOpen(true);
  };

  const handleEditorChange = (key, value) => {
    setEditingConfig({ ...editingConfig, [key]: value });
  };

  const saveConfig = async () => {
    setSaveError('');

    const mapping = getOutcomeMappingState(editingConfig);
    if (!mapping.isSummaryMode && mapping.allOutcomes.length > 0 && !mapping.valid) {
      const parts = [];
      if (mapping.unmapped.length) parts.push(`unmapped: ${mapping.unmapped.join(', ')}`);
      if (mapping.orphans.length) parts.push(`stale: ${mapping.orphans.join(', ')}`);
      setSaveError(`Map every intent_status value before saving (${parts.join('; ')})`);
      setActiveTab('post-call');
      return;
    }
    
    // Parse JSON strings back to objects
    let payload = { ...editingConfig };
    const jsonFields = [
      'extraction_schema', 'lead_schema', 'bootstrap_messages_json', 
      'goodbye_markers', 'cascade_live_tools', 'normalization_rules',
      'outcome_event_map', 'outcome_terminal', 'outcome_retry', 'outcome_callback'
    ];
    
    const fieldTabMap = {
      'extraction_schema': 'post-call',
      'lead_schema': 'advanced',
      'bootstrap_messages_json': 'prompts',
      'goodbye_markers': 'advanced',
      'cascade_live_tools': 'advanced',
      'normalization_rules': 'post-call',
      'outcome_event_map': 'post-call',
      'outcome_terminal': 'post-call',
      'outcome_retry': 'post-call',
      'outcome_callback': 'post-call'
    };
    
    for (const field of jsonFields) {
      try {
        payload[field] = JSON.parse(editingConfig[field] || 'null');
      } catch (e) {
        setSaveError(`Invalid JSON in field: ${field}`);
        setActiveTab(fieldTabMap[field] || 'general');
        return;
      }
    }
    
    try {
      if (payload.id) {
        // Update
        const patchPayload = { ...payload };
        delete patchPayload.id;
        delete patchPayload.client_id;
        delete patchPayload.version;
        delete patchPayload.created_at;
        delete patchPayload.updated_at;
        
        await adminApi.patch(`/internal/script-configs/${payload.id}`, patchPayload, {
          params: { client_id: payload.client_id }
        });
      } else {
        // Create
        await adminApi.post('/internal/script-configs', payload);
      }
      
      setIsEditorOpen(false);
      fetchConfigs();
    } catch (error) {
      const detail = error.response?.data?.detail;
      let errorMsg = typeof detail === 'string' ? detail : (error.message || 'Failed to save config.');
      if (Array.isArray(detail)) {
        errorMsg = detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', ');
      }
      
      if (errorMsg.toLowerCase().includes('unmapped') || errorMsg.toLowerCase().includes('intent_status')) {
        setActiveTab('post-call');
      }
      setSaveError(errorMsg);
    }
  };

  // ----------------------------------------
  // History Flow
  // ----------------------------------------
  const openHistory = async (config) => {
    setIsHistoryOpen(true);
    setHistoryConfigs([]);
    setSelectedHistory(null);
    try {
      const res = await adminApi.get(`/internal/script-configs/${config.id}/revisions`, {
        params: { client_id: config.client_id }
      });
      setHistoryConfigs(res.data.revisions || []);
    } catch (err) {
      console.error(err);
    }
  };

  const rollbackConfig = async () => {
    if (!selectedHistory) return;
    try {
      await adminApi.post(`/internal/script-configs/${selectedHistory.script_config_id}/rollback`, {
        version: selectedHistory.version
      }, {
        params: { client_id: selectedHistory.client_id }
      });
      setIsHistoryOpen(false);
      fetchConfigs();
    } catch (error) {
      console.error(error);
      alert('Rollback failed.');
    }
  };

  // ----------------------------------------
  // Deploy Bot Flow
  // ----------------------------------------
  const openDeployBot = (config) => {
    setDeployTemplate(config);
    setDeployBotName('');
    setDeployTelephonyNumber('');
    setDeployCredits('');
    setDeployError('');
    setIsDeployBotOpen(true);
  };

  const handleDeployBot = async (e) => {
    e.preventDefault();
    setDeployError('');
    try {
      await adminApi.post('/internal/bot-configs', {
        client_id: deployTemplate.client_id,
        name: deployBotName,
        route: deployTemplate.route,
        script_id: deployTemplate.script_id,
        script_config_id: deployTemplate.id,
        telephony_number: deployTelephonyNumber,
        credits_per_minute: parseFloat(deployCredits)
      });
      setIsDeployBotOpen(false);
      navigate('/admin/bot-configs');
    } catch (error) {
      const detail = error.response?.data?.detail;
      if (Array.isArray(detail)) {
        setDeployError(detail.map(d => `${d.loc.join('.')}: ${d.msg}`).join(', '));
      } else {
        setDeployError(typeof detail === 'string' ? detail : (error.message || 'Failed to deploy bot.'));
      }
    }
  };

  const handleTestCall = async (e) => {
    e.preventDefault();
    setTestCallError('');
    setTestCallSuccess('');
    try {
      if (!editingConfig || !editingConfig.id) {
        setTestCallError("Save template first.");
        return;
      }
      let parsedMeta = {};
      try {
        parsedMeta = JSON.parse(testCallMetadata);
      } catch (err) {
        setTestCallError("Invalid JSON in metadata.");
        return;
      }
      const leadName = parsedMeta.lead_name || "Test Lead";
      
      const res = await adminApi.post(`/internal/script-configs/${editingConfig.id}/dial-test`, {
        phone: testCallPhone,
        telephony_number: testCallTelephonyNumber,
        lead_name: leadName,
        metadata: parsedMeta
      }, {
        params: { client_id: editingConfig.client_id }
      });
      setTestCallSuccess(`Dispatched successfully. Session ID: ${res.data.session_call_id}`);
      setTimeout(() => {
        setIsTestCallOpen(false);
        setTestCallSuccess('');
      }, 4000);
    } catch (error) {
      const detail = error.response?.data?.detail;
      setTestCallError(typeof detail === 'string' ? detail : (error.message || 'Failed to dispatch test call.'));
    }
  };

  const outcomeMappingState = editingConfig ? getOutcomeMappingState(editingConfig) : null;
  const saveBlockedByOutcomes =
    activeTab === 'post-call'
    && outcomeMappingState
    && !outcomeMappingState.isSummaryMode
    && outcomeMappingState.allOutcomes.length > 0
    && !outcomeMappingState.valid;

  return (
    <>
      <div className="flex justify-between items-end mb-stack-lg">
        <div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text mb-2">Script Templates</h2>
          <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted">Manage conversational logic, extraction schemas, and models for agents.</p>
        </div>
        <div className="flex gap-2 items-center">
          <input 
            type="text"
            placeholder="Search templates"
            className="px-4 py-2 bg-surface-container-lowest dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm text-on-surface dark:text-molten-text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <button 
            onClick={openCreator}
            className="px-4 py-2 rounded-lg bg-primary dark:bg-molten-primary text-white dark:text-molten-bg font-label-md text-label-md hover:brightness-110 transition-all flex items-center gap-2"
          >
            <span className="material-symbols-outlined text-[18px]">add</span> Create Template
          </button>
        </div>
      </div>

      {/* Table View */}
      <div className="bg-surface dark:bg-molten-surface rounded-lg border border-outline-variant dark:border-[#2A345E] overflow-hidden">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="bg-surface-container-lowest dark:bg-[#141210] border-b border-outline-variant dark:border-[#2A345E]">
              <th className="px-4 py-3 font-label-md text-label-md font-bold text-on-surface-variant dark:text-molten-text-muted">Script ID</th>
              <th className="px-4 py-3 font-label-md text-label-md font-bold text-on-surface-variant dark:text-molten-text-muted">Client</th>
              <th className="px-4 py-3 font-label-md text-label-md font-bold text-on-surface-variant dark:text-molten-text-muted">Route</th>
              <th className="px-4 py-3 font-label-md text-label-md font-bold text-on-surface-variant dark:text-molten-text-muted">Version</th>
              <th className="px-4 py-3 font-label-md text-label-md font-bold text-on-surface-variant dark:text-molten-text-muted">Status</th>
              <th className="px-4 py-3 text-right"></th>
            </tr>
          </thead>
          <tbody>
            {configs.filter(c => c.script_id.toLowerCase().includes(search.toLowerCase()) || getClientName(c.client_id).toLowerCase().includes(search.toLowerCase())).map((c) => (
              <tr key={c.id} className="border-b border-outline-variant dark:border-[#2A345E] hover:bg-surface-container-lowest dark:hover:bg-[#1A1A24] transition-colors">
                <td className="px-4 py-3 font-body-md text-body-md text-on-surface dark:text-molten-text">{c.script_id}</td>
                <td className="px-4 py-3 font-body-md text-body-md text-on-surface dark:text-molten-text">{getClientName(c.client_id)}</td>
                <td className="px-4 py-3 font-body-md text-body-md text-on-surface dark:text-molten-text uppercase text-xs">{c.route}</td>
                <td className="px-4 py-3 font-body-md text-body-md text-on-surface dark:text-molten-text tabular-nums">v{c.version}</td>
                <td className="px-4 py-3">
                  <span className={`px-2 py-1 rounded text-xs font-bold ${c.active ? 'bg-secondary/15 text-secondary dark:text-secondary-container' : 'bg-arctic-warning/15 text-arctic-warning'}`}>
                    {c.active ? 'ACTIVE' : 'INACTIVE'}
                  </span>
                </td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <button onClick={() => openDeployBot(c)} className="text-on-surface-variant dark:text-molten-text-muted hover:text-primary dark:hover:text-molten-primary mr-3" title="Deploy Bot from Template">
                    <span className="material-symbols-outlined text-[18px]">rocket_launch</span>
                  </button>
                  <button onClick={() => openHistory(c)} className="text-on-surface-variant dark:text-molten-text-muted hover:text-primary dark:hover:text-molten-primary mr-3" title="Version History">
                    <span className="material-symbols-outlined text-[18px]">history</span>
                  </button>
                  <button onClick={() => openEditor(c)} className="text-on-surface-variant dark:text-molten-text-muted hover:text-primary dark:hover:text-molten-primary" title="Edit Template">
                    <span className="material-symbols-outlined text-[18px]">edit</span>
                  </button>
                </td>
              </tr>
            ))}
            {configs.length === 0 && (
              <tr>
                <td colSpan="6" className="px-4 py-8 text-center text-on-surface-variant dark:text-molten-text-muted">
                  No script templates found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Creator Modal */}
      {isCreatorOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-lg shadow-2xl w-full max-w-md border border-outline-variant/50 dark:border-[#2A345E]">
            <div className="flex justify-between items-center mb-stack-md">
              <h3 className="font-headline-md text-on-surface dark:text-molten-text">New Template</h3>
              <button onClick={() => setIsCreatorOpen(false)} className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"><span className="material-symbols-outlined">close</span></button>
            </div>
            {createError && <div className="mb-4 text-arctic-error dark:text-molten-error text-sm">{createError}</div>}
            <form onSubmit={handleCreateTemplateLoad} className="space-y-4">
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Client</label>
                <select className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={newClientId} onChange={e => setNewClientId(e.target.value)} required>
                  <option value="">Select a Client</option>
                  {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Script ID (e.g. outbound_sales)</label>
                <input className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={newScriptId} onChange={e => setNewScriptId(e.target.value)} required pattern="^[a-z][a-z0-9_]*$"/>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Route</label>
                <select className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={newRoute} onChange={e => setNewRoute(e.target.value)} required>
                  <option value="sts">sts (Single Threaded Synthesizer)</option>
                  <option value="cascaded">cascaded</option>
                </select>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button type="button" onClick={() => setIsCreatorOpen(false)} className="px-4 py-2 border border-outline-variant dark:border-[#2A345E] rounded-lg text-on-surface dark:text-molten-text">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg rounded-lg">Load Boilerplate</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Deploy Bot Modal */}
      {isDeployBotOpen && deployTemplate && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-lg shadow-2xl w-full max-w-md border border-outline-variant/50 dark:border-[#2A345E]">
            <div className="flex justify-between items-center mb-stack-md">
              <h3 className="font-headline-md text-on-surface dark:text-molten-text">Deploy Bot</h3>
              <button onClick={() => setIsDeployBotOpen(false)} className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"><span className="material-symbols-outlined">close</span></button>
            </div>
            <p className="text-sm text-arctic-text-muted dark:text-molten-text-muted mb-4">
              Deploying a new bot using template <strong>{deployTemplate.script_id}</strong> for <strong>{getClientName(deployTemplate.client_id)}</strong>.
            </p>
            {deployError && <div className="mb-4 p-3 bg-arctic-error/15 border border-arctic-error/30 text-arctic-error dark:text-molten-error rounded-lg text-sm">{deployError}</div>}
            <form onSubmit={handleDeployBot} className="space-y-4">
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Bot Name</label>
                <input className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={deployBotName} onChange={e => setDeployBotName(e.target.value)} required placeholder="e.g. Sales Inbound Agent"/>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Telephony Number</label>
                <input className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={deployTelephonyNumber} onChange={e => setDeployTelephonyNumber(e.target.value)} required placeholder="e.g. +14155552671"/>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Credits Per Minute</label>
                <input type="number" step="0.01" className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={deployCredits} onChange={e => setDeployCredits(e.target.value)} required placeholder="e.g. 0.50"/>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button type="button" onClick={() => setIsDeployBotOpen(false)} className="px-4 py-2 border border-outline-variant dark:border-[#2A345E] rounded-lg text-on-surface dark:text-molten-text">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg rounded-lg shadow-[inset_0_1px_0_rgba(255,255,255,0.2)]">Deploy Agent</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Editor Modal */}
      {isEditorOpen && editingConfig && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm p-4 sm:p-6">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col border border-outline-variant/50 dark:border-[#2A345E] overflow-hidden">
            <div className="flex justify-between items-center px-6 py-4 bg-surface dark:bg-[#1C1810] border-b border-outline-variant dark:border-[#2A345E]">
              <div className="flex items-center gap-4">
                <h3 className="font-headline-md text-on-surface dark:text-molten-text truncate pr-4">
                  {editingConfig.id ? `Edit Template: ${editingConfig.script_id} (v${editingConfig.version})` : `Create Template: ${editingConfig.script_id}`}
                </h3>
                <button 
                  onClick={() => setIsGuideOpen(true)}
                  className="flex items-center gap-1.5 px-3 py-1 bg-primary/10 text-primary dark:bg-molten-primary/10 dark:text-molten-primary rounded-full text-xs font-medium hover:bg-primary/20 dark:hover:bg-molten-primary/20 transition-colors"
                >
                  <span className="material-symbols-outlined text-[16px]">menu_book</span>
                  Guide
                </button>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {saveError && !saveError.includes('intent_status') && !saveError.includes('unmapped') && !saveError.includes('stale') && <span className="text-arctic-error dark:text-molten-error text-sm max-w-[200px] md:max-w-[300px] truncate" title={saveError}>{saveError}</span>}
                <button onClick={() => setIsEditorOpen(false)} className="px-4 py-2 border border-outline-variant dark:border-[#2A345E] rounded-lg text-on-surface dark:text-molten-text hover:bg-surface-container-low dark:hover:bg-[#2A345E]">Cancel</button>
                {editingConfig.id && (
                  <button onClick={() => setIsTestCallOpen(true)} className="px-4 py-2 border border-primary dark:border-molten-primary text-primary dark:text-molten-primary rounded-lg font-bold hover:bg-primary/10 dark:hover:bg-molten-primary/10 transition-colors">
                    Test Call
                  </button>
                )}
                <button
                  onClick={saveConfig}
                  disabled={saveBlockedByOutcomes}
                  className="px-4 py-2 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Save
                </button>
              </div>
            </div>
            
            <div className="tabs-header shrink-0 px-6 bg-surface dark:bg-[#1C1810]">
              {['general', 'prompts', 'models', 'post-call', 'advanced'].map(tab => (
                <button key={tab} className={`tab-btn ${activeTab === tab ? 'active' : ''}`} onClick={() => setActiveTab(tab)}>
                  {tab.charAt(0).toUpperCase() + tab.slice(1).replace('-', ' ')}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-6 bg-surface-container-lowest dark:bg-[#141210]">
              <div className="space-y-6">
              {activeTab === 'general' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Client</label>
                      <select disabled={!!editingConfig.id} className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text opacity-70" value={editingConfig.client_id} onChange={e => handleEditorChange('client_id', e.target.value)}>
                        {clients.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}
                      </select>
                    </div>
                    <div>
                      <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Script ID</label>
                      <input type="text" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.script_id} onChange={e => handleEditorChange('script_id', e.target.value)} />
                    </div>
                    <div>
                      <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Route</label>
                      <select className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.route} onChange={e => handleEditorChange('route', e.target.value)}>
                        <option value="sts">sts</option>
                        <option value="cascaded">cascaded</option>
                      </select>
                    </div>
                    <div className="flex items-end pb-2">
                      <label className="flex items-center gap-2 cursor-pointer text-on-surface dark:text-molten-text">
                        <input type="checkbox" checked={editingConfig.active} onChange={e => handleEditorChange('active', e.target.checked)} className="rounded border-outline-variant" />
                        Active
                      </label>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'prompts' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">System Instruction Template</label>
                    <textarea rows="10" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text font-mono text-sm" value={editingConfig.system_instruction_template || ''} onChange={e => handleEditorChange('system_instruction_template', e.target.value)}></textarea>
                  </div>
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Bootstrap Messages (JSON)</label>
                    <textarea rows="5" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.bootstrap_messages_json || ''} onChange={e => handleEditorChange('bootstrap_messages_json', e.target.value)}></textarea>
                  </div>
                </div>
              )}

              {activeTab === 'models' && (
                <div className="space-y-6">
                  {editingConfig.route === 'sts' ? (
                    <div>
                      <h4 className="font-bold text-on-surface dark:text-molten-text mb-3">Gemini Realtime (STS)</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Model</label>
                          <input type="text" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.gemini_model || ''} onChange={e => handleEditorChange('gemini_model', e.target.value)} />
                        </div>
                        <div>
                          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Voice</label>
                          <input type="text" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.gemini_voice || ''} onChange={e => handleEditorChange('gemini_voice', e.target.value)} />
                        </div>
                        <div>
                          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Language</label>
                          <input type="text" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" placeholder="hi-IN" value={editingConfig.gemini_language || ''} onChange={e => handleEditorChange('gemini_language', e.target.value)} />
                        </div>
                        <div>
                          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Temperature</label>
                          <input type="number" step="0.01" min="0" max="2" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.gemini_temperature !== undefined ? editingConfig.gemini_temperature : ''} onChange={e => handleEditorChange('gemini_temperature', parseFloat(e.target.value))} />
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div>
                      <h4 className="font-bold text-on-surface dark:text-molten-text mb-3">Cascade Pipeline</h4>
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">STT Provider</label>
                          <input type="text" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.cascade_stt_provider || ''} onChange={e => handleEditorChange('cascade_stt_provider', e.target.value)} />
                        </div>
                        <div>
                          <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">LLM Model</label>
                          <input type="text" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.cascade_llm_model || ''} onChange={e => handleEditorChange('cascade_llm_model', e.target.value)} />
                        </div>
                      </div>
                    </div>
                  )}
                  <div>
                    <h4 className="font-bold text-on-surface dark:text-molten-text mb-3">VAD Settings</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Silence Duration (ms)</label>
                        <input type="number" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.vad_silence_duration_ms || ''} onChange={e => handleEditorChange('vad_silence_duration_ms', parseInt(e.target.value))} />
                      </div>
                      <div>
                        <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Prefix Padding (ms)</label>
                        <input type="number" className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.vad_prefix_padding_ms || ''} onChange={e => handleEditorChange('vad_prefix_padding_ms', parseInt(e.target.value))} />
                      </div>
                      <div>
                        <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Start Sensitivity</label>
                        <select className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.vad_start_sensitivity || 'HIGH'} onChange={e => handleEditorChange('vad_start_sensitivity', e.target.value)}>
                          <option value="LOW">LOW</option>
                          <option value="HIGH">HIGH</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">End Sensitivity</label>
                        <select className="w-full bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.vad_end_sensitivity || 'LOW'} onChange={e => handleEditorChange('vad_end_sensitivity', e.target.value)}>
                          <option value="LOW">LOW</option>
                          <option value="HIGH">HIGH</option>
                        </select>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'post-call' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Extraction Schema (JSON Schema)</label>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-2">
                      Must include an <code>intent_status</code> enum in <code>fields</code> (unless using summary-only mode). Those values drive the outcome mapper below.
                    </p>
                    <textarea rows="10" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.extraction_schema || ''} onChange={e => handleEditorChange('extraction_schema', e.target.value)}></textarea>
                  </div>
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Normalization Rules (JSON)</label>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-2">Deterministic corrections applied after AI extraction, before bucketing. Encodes reliable domain logic.</p>
                    <textarea rows="6" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.normalization_rules || ''} onChange={e => handleEditorChange('normalization_rules', e.target.value)}></textarea>
                  </div>
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Outcome Event Map (JSON)</label>
                    <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-2">Maps an <code>intent_status</code> value to the webhook event name fired to the client's automation (e.g. n8n). Example: <code>{"{"}"Interested": "lead_qualified"{"}"}</code></p>
                    <textarea rows="4" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.outcome_event_map || ''} onChange={e => handleEditorChange('outcome_event_map', e.target.value)}></textarea>
                  </div>
                  
                  <OutcomeDragDropEditor editingConfig={editingConfig} setEditingConfig={setEditingConfig} />
                  {saveError && (
                    <div className="mt-4 p-3 bg-error-container/20 border border-arctic-error/30 dark:border-molten-error/30 rounded-lg text-arctic-error dark:text-molten-error text-sm font-medium w-full">
                      {saveError}
                    </div>
                  )}
                </div>
              )}
              
              {activeTab === 'advanced' && (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Lead Schema (JSON)</label>
                    <textarea rows="5" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.lead_schema || ''} onChange={e => handleEditorChange('lead_schema', e.target.value)}></textarea>
                  </div>
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Cascade Live Tools (JSON)</label>
                    <textarea rows="5" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.cascade_live_tools || ''} onChange={e => handleEditorChange('cascade_live_tools', e.target.value)}></textarea>
                  </div>
                  <div>
                    <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Goodbye Markers (JSON)</label>
                    <textarea rows="3" className="w-full json-editor bg-surface-container-lowest dark:bg-[#1A1A24] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={editingConfig.goodbye_markers || ''} onChange={e => handleEditorChange('goodbye_markers', e.target.value)}></textarea>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
        </div>
      )}

      {/* History Modal */}
      {isHistoryOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm p-4 sm:p-6">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-xl shadow-2xl w-full max-w-5xl max-h-[85vh] flex flex-col border border-outline-variant/50 dark:border-[#2A345E] overflow-hidden">
            <div className="flex justify-between items-center px-6 py-4 border-b border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#1C1810]">
              <h3 className="font-headline-md text-on-surface dark:text-molten-text">Version History</h3>
              <button onClick={() => setIsHistoryOpen(false)} className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"><span className="material-symbols-outlined">close</span></button>
            </div>
            <div className="flex flex-1 overflow-hidden">
              {/* Sidebar with versions */}
              <div className="w-64 border-r border-outline-variant dark:border-[#2A345E] overflow-y-auto">
                {historyConfigs.map(rev => (
                  <button 
                    key={rev.id} 
                    className={`w-full text-left px-4 py-3 border-b border-outline-variant/50 dark:border-[#2A345E]/50 transition-colors ${selectedHistory?.id === rev.id ? 'bg-primary-container dark:bg-secondary-container text-on-primary dark:text-on-secondary-container' : 'hover:bg-surface-container-lowest dark:hover:bg-[#141210] text-on-surface dark:text-molten-text'}`}
                    onClick={() => setSelectedHistory(rev)}
                  >
                    <div className="font-bold">Version {rev.version}</div>
                    <div className="text-xs opacity-70 mt-1">{new Date(rev.created_at).toLocaleString()}</div>
                  </button>
                ))}
                {historyConfigs.length === 0 && <div className="p-4 text-center text-sm text-arctic-text-muted dark:text-molten-text-muted">No history found.</div>}
              </div>
              {/* Content area */}
              <div className="flex-1 flex flex-col overflow-hidden bg-surface-container-lowest dark:bg-[#141210]">
                {selectedHistory ? (
                  <>
                    <div className="p-4 border-b border-outline-variant dark:border-[#2A345E] flex justify-between items-center bg-surface dark:bg-[#1C1810]">
                      <span className="font-label-md text-on-surface dark:text-molten-text">Viewing Version {selectedHistory.version}</span>
                      <button onClick={rollbackConfig} className="px-4 py-2 bg-arctic-warning dark:bg-molten-success text-white dark:text-molten-bg rounded-lg font-bold flex items-center gap-2 text-sm shadow-md">
                        <span className="material-symbols-outlined text-[16px]">restore</span> Restore This Version
                      </button>
                    </div>
                    <div className="flex-1 overflow-auto p-4 code-block m-4 rounded-lg">
                      {typeof selectedHistory.config_snapshot === 'string' 
                        ? JSON.stringify(JSON.parse(selectedHistory.config_snapshot), null, 2)
                        : JSON.stringify(selectedHistory.config_snapshot, null, 2)}
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-arctic-text-muted dark:text-molten-text-muted">
                    Select a version to view its payload
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Test Call Modal */}
      {isTestCallOpen && (
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-on-surface/40 dark:bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg p-stack-lg shadow-2xl w-full max-w-sm border border-outline-variant/50 dark:border-[#2A345E]">
            <div className="flex justify-between items-center mb-stack-md">
              <h3 className="font-headline-md text-on-surface dark:text-molten-text">Test Dial</h3>
              <button onClick={() => setIsTestCallOpen(false)} className="text-on-surface-variant dark:text-molten-text-muted hover:bg-surface-container-low dark:hover:bg-molten-surface p-1 rounded transition-colors"><span className="material-symbols-outlined">close</span></button>
            </div>
            {testCallError && <div className="mb-4 text-arctic-error dark:text-molten-error text-sm p-2 bg-error-container/20 rounded-lg">{testCallError}</div>}
            {testCallSuccess && <div className="mb-4 text-molten-success dark:text-[#5cf7db] text-sm p-2 bg-secondary/10 rounded-lg">{testCallSuccess}</div>}
            
            <form onSubmit={handleTestCall} className="space-y-4">
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">From: Telephony Number</label>
                <input required type="text" placeholder="+1..." className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={testCallTelephonyNumber} onChange={(e) => setTestCallTelephonyNumber(e.target.value)} />
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">Your registered Plivo number (Caller ID)</p>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">To: Target Phone Number</label>
                <input required type="text" placeholder="+91..." className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text" value={testCallPhone} onChange={(e) => setTestCallPhone(e.target.value)} />
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">E.164 format, e.g. +919876543210</p>
              </div>
              <div>
                <label className="block text-sm mb-1 text-on-surface dark:text-molten-text">Lead Data (JSON)</label>
                <textarea rows="4" className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 text-on-surface dark:text-molten-text font-mono text-sm" value={testCallMetadata} onChange={(e) => setTestCallMetadata(e.target.value)}></textarea>
                <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mt-1">Include variables like lead_name, city, etc.</p>
              </div>
              <div className="flex justify-end gap-3 pt-4">
                <button type="button" onClick={() => setIsTestCallOpen(false)} className="px-4 py-2 border border-outline-variant dark:border-[#2A345E] rounded-lg text-on-surface dark:text-molten-text">Cancel</button>
                <button type="submit" className="px-4 py-2 bg-primary dark:bg-molten-primary text-white dark:text-molten-bg rounded-lg shadow-md">Dial</button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Scripting Guide Modal */}
      <ScriptingGuideModal isOpen={isGuideOpen} onClose={() => setIsGuideOpen(false)} />
    </>
  );
}
