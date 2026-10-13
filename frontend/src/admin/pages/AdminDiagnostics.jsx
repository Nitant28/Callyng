import React, { useState, useEffect, useMemo } from 'react';
import adminApi from '../../shared/api/admin';

export default function AdminDiagnostics() {
  const [health, setHealth] = useState(null);
  const [calls, setCalls] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const [reconcileCampaignId, setReconcileCampaignId] = useState('');
  const [reconcileResult, setReconcileResult] = useState(null);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [healthRes, callsRes] = await Promise.all([
        adminApi.get('/internal/health'),
        adminApi.get('/internal/calls', { params: { limit: 200 } })
      ]);
      setHealth(healthRes.data);
      setCalls(callsRes.data.calls || []);
      setError(null);
    } catch (err) {
      console.error("Diagnostics fetch error", err);
      setError("Failed to load diagnostics data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const stuckCalls = useMemo(() => {
    const now = new Date();
    return calls.filter(c => {
      if (!c.in_progress || !c.started_at) return false;
      const started = new Date(c.started_at);
      const diffMins = (now - started) / 60000;
      return diffMins > 12; // Older than 12 mins
    });
  }, [calls]);

  const failedExtractions = useMemo(() => {
    return calls.filter(c => {
      if (c.in_progress) return false;
      if (!c.campaign_id) return false;
      if (c.duration_seconds < 15) return false;
      return (!c.outcome) || (c.extraction_error !== null);
    });
  }, [calls]);

  const handleReconcile = async () => {
    if (!reconcileCampaignId) return;
    try {
      const res = await adminApi.post(`/internal/campaigns/${reconcileCampaignId}/reconcile`);
      setReconcileResult(res.data);
    } catch (err) {
      setReconcileResult({ error: err.customErrorMessage || "Failed to reconcile" });
    }
  };

  const handleReleaseStuckLeads = async (campaignId) => {
    try {
      const res = await adminApi.post(`/internal/campaigns/${campaignId}/release-stuck`);
      alert(`Released ${res.data.released} leads!`);
      fetchData();
    } catch (err) {
      alert(err.customErrorMessage || "Failed to release leads");
    }
  };

  return (
    <div className="w-full max-w-5xl mx-auto">
      <div className="flex justify-between items-end mb-stack-lg">
        <div>
          <h2 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">Diagnostics</h2>
          <p className="font-body-md text-body-md text-arctic-text-muted dark:text-molten-text-muted mt-1">System health, orphaned processes, and data reconciliation.</p>
        </div>
        <button onClick={fetchData} className="px-4 py-2 bg-surface-container-low dark:bg-[#1A1C24] border border-outline-variant dark:border-[#2A345E] rounded-lg hover:bg-surface-container dark:hover:bg-[#2A345E] transition-colors flex items-center gap-2 text-on-surface dark:text-molten-text">
          <span className="material-symbols-outlined">refresh</span>
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-6 p-4 bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error rounded-lg border border-error/30 dark:border-molten-error/30">
          {error}
        </div>
      )}

      <div className="space-y-6">
        {/* Telnyx Balance */}
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6">
          <h3 className="font-headline-sm flex items-center gap-2 mb-2 text-on-surface dark:text-molten-text">
            <span className="material-symbols-outlined text-primary dark:text-molten-primary">account_balance_wallet</span>
            Telnyx Telephony Balance
          </h3>
          <p className="text-3xl font-bold font-mono text-on-surface dark:text-molten-text">
            {(health?.telnyx_balance ?? health?.plivo_balance) !== null && (health?.telnyx_balance ?? health?.plivo_balance) !== undefined 
              ? `₹${((health?.telnyx_balance ?? health?.plivo_balance) * 80.0229).toFixed(2)} ($${(health?.telnyx_balance ?? health?.plivo_balance).toFixed(2)})` 
              : <span className="text-sm text-on-surface-variant dark:text-molten-text-muted italic">Unavailable (Check TELNYX_API_KEY in .env)</span>}
          </p>
        </div>

        {/* Stuck Calls */}
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6">
          <h3 className="font-headline-sm flex items-center gap-2 mb-4 text-arctic-warning dark:text-molten-warning">
            <span className="material-symbols-outlined">warning</span>
            Stuck Calls ({stuckCalls.length})
          </h3>
          <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-4">Calls marked as 'in_progress' but started over 12 minutes ago.</p>
          
          {stuckCalls.length > 0 ? (
            <div className="overflow-x-auto border border-outline-variant dark:border-[#2A345E] rounded-lg">
              <table className="w-full text-left text-sm text-on-surface dark:text-molten-text">
                <thead className="bg-surface-container dark:bg-[#1A1C24]">
                  <tr>
                    <th className="p-2">Session ID</th>
                    <th className="p-2">Campaign ID</th>
                    <th className="p-2">Started At</th>
                    <th className="p-2">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant dark:divide-[#2A345E]">
                  {stuckCalls.map(c => (
                    <tr key={c.session_call_id}>
                      <td className="p-2 font-mono">{c.session_call_id.substring(0,8)}</td>
                      <td className="p-2 font-mono">{c.campaign_id?.substring(0,8) || '-'}</td>
                      <td className="p-2">{new Date(c.started_at).toLocaleString()}</td>
                      <td className="p-2">
                        {c.campaign_id && (
                          <button 
                            onClick={() => handleReleaseStuckLeads(c.campaign_id)}
                            className="px-2 py-1 bg-surface-container-high dark:bg-[#2A345E] rounded hover:opacity-80 transition-opacity"
                          >
                            Release Campaign Leads
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4 bg-surface-container dark:bg-[#1A1C24] rounded-lg text-center text-sm text-on-surface-variant dark:text-molten-text-muted">No stuck calls detected in the recent logs.</div>
          )}
        </div>

        {/* Failed Extractions */}
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6">
          <h3 className="font-headline-sm flex items-center gap-2 mb-4 text-error dark:text-molten-error">
            <span className="material-symbols-outlined">error</span>
            Failed Extractions ({failedExtractions.length})
          </h3>
          <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-4">Completed calls missing an outcome or with an explicit AI extraction error.</p>
          
          {failedExtractions.length > 0 ? (
            <div className="overflow-x-auto border border-outline-variant dark:border-[#2A345E] rounded-lg">
              <table className="w-full text-left text-sm text-on-surface dark:text-molten-text">
                <thead className="bg-surface-container dark:bg-[#1A1C24]">
                  <tr>
                    <th className="p-2">Session ID</th>
                    <th className="p-2">Route</th>
                    <th className="p-2">Error</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant dark:divide-[#2A345E]">
                  {failedExtractions.map(c => (
                    <tr key={c.session_call_id}>
                      <td className="p-2 font-mono">{c.session_call_id.substring(0,8)}</td>
                      <td className="p-2">{c.route}</td>
                      <td className="p-2 text-error dark:text-molten-error font-mono text-xs">{c.extraction_error || 'Outcome is NULL'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-4 bg-surface-container dark:bg-[#1A1C24] rounded-lg text-center text-sm text-on-surface-variant dark:text-molten-text-muted">No extraction errors detected.</div>
          )}
        </div>

        {/* Reconcile */}
        <div className="bg-surface-container-lowest dark:bg-molten-surface border border-outline-variant dark:border-[#2A345E] rounded-lg p-6">
          <h3 className="font-headline-sm flex items-center gap-2 mb-4 text-on-surface dark:text-molten-text">
            <span className="material-symbols-outlined text-primary dark:text-molten-primary">sync</span>
            Campaign Counter Reconcile
          </h3>
          <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mb-4">Recalculates denormalized lead counters on a campaign from the raw leads table.</p>
          
          <div className="flex gap-2 mb-4">
            <input 
              type="text" 
              placeholder="Campaign UUID" 
              className="flex-1 p-2 border border-outline-variant dark:border-[#2A345E] rounded-lg bg-surface dark:bg-[#141210] font-mono text-sm text-on-surface dark:text-molten-text focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary focus:outline-none"
              value={reconcileCampaignId}
              onChange={e => setReconcileCampaignId(e.target.value)}
            />
            <button 
              onClick={handleReconcile}
              disabled={!reconcileCampaignId}
              className="px-4 py-2 bg-primary text-on-primary dark:bg-molten-primary rounded-lg disabled:opacity-50 transition-opacity"
            >
              Run Reconcile
            </button>
          </div>
          
          {reconcileResult && (
            <div className={`p-4 rounded-lg font-mono text-sm whitespace-pre-wrap ${reconcileResult.error ? 'bg-error-container dark:bg-molten-error/20 text-on-error-container dark:text-molten-error' : 'bg-surface-container dark:bg-[#1A1C24] text-on-surface dark:text-molten-text'}`}>
              {JSON.stringify(reconcileResult, null, 2)}
            </div>
          )}
          
          <div className="mt-4 pt-4 border-t border-outline-variant dark:border-[#2A345E]">
            <p className="text-xs text-on-surface-variant dark:text-molten-text-muted mb-2">Manual SQL Check:</p>
            <code className="block p-2 bg-surface-container dark:bg-[#1A1C24] text-on-surface dark:text-molten-text rounded text-xs select-all border border-transparent dark:border-[#2A345E]">
              SELECT status, COUNT(*) FROM leads WHERE campaign_id = '{reconcileCampaignId || '<id>'}' GROUP BY status;
            </code>
          </div>
        </div>
      </div>
    </div>
  );
}
