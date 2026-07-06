import React, { useState, useEffect } from 'react';
import adminApi from '../../shared/api/admin';

export default function AdminWebhooks() {
  const [clients, setClients] = useState([]);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [webhooks, setWebhooks] = useState([]);
  
  // Form states
  const [formClientId, setFormClientId] = useState('');
  const [formEvent, setFormEvent] = useState('lead_qualified');
  const [formUrl, setFormUrl] = useState('');
  const [formSecret, setFormSecret] = useState('');
  
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  const fetchClients = async () => {
    try {
      const res = await adminApi.get('/internal/clients');
      const clientList = res.data.clients || res.data || [];
      setClients(clientList);
      if (clientList.length > 0) {
        setSelectedClientId(clientList[0].id);
        setFormClientId(clientList[0].id);
      }
    } catch (err) {
      console.error('Failed to fetch clients', err);
    }
  };

  useEffect(() => {
    fetchClients();
  }, []);

  const fetchWebhooks = async (clientId) => {
    try {
      setLoading(true);
      const res = await adminApi.get(`/internal/clients/${clientId}/webhooks`);
      setWebhooks(res.data.webhooks || []);
    } catch (err) {
      console.error('Failed to fetch webhooks', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (selectedClientId) {
      fetchWebhooks(selectedClientId);
    } else {
      setWebhooks([]);
    }
  }, [selectedClientId]);

  const handleUpsertWebhook = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (!formClientId || !formEvent || !formUrl || !formSecret) {
      setError('All fields are required.');
      return;
    }

    try {
      await adminApi.post('/internal/webhook-configs', {
        client_id: formClientId,
        event: formEvent,
        url: formUrl,
        secret: formSecret
      });

      setSuccessMsg('Webhook configuration upserted successfully!');
      
      // If we just upserted a webhook for the currently selected client, refresh the list
      if (formClientId === selectedClientId) {
        fetchWebhooks(selectedClientId);
      }

      // Reset url & secret fields
      setFormUrl('');
      setFormSecret('');
    } catch (err) {
      console.error('Failed to upsert webhook config', err);
      setError(err.customErrorMessage || err.message || 'Failed to upsert webhook configuration.');
    }
  };

  const handleClientChange = (e) => {
    const val = e.target.value;
    setSelectedClientId(val);
    setFormClientId(val); // Sync form client selection with view client selection by default
  };

  return (
    <div className="w-full flex flex-col gap-stack-lg">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">Webhook Integrations</h1>
        <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted mt-2">
          Configure real-time HTTP callbacks for campaign lifecycle and lead events.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
        {/* Left Side: Client Selector and Configured Webhooks List */}
        <div className="lg:col-span-2 flex flex-col gap-stack-md">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] p-stack-md rounded-lg border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none flex flex-col gap-4">
            <div>
              <label className="block font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase mb-1.5">
                Select Client to View Configured Webhooks
              </label>
              <select
                className="w-full max-w-md px-3 py-2 bg-background dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm focus:outline-none focus:border-primary dark:focus:border-molten-primary font-body-sm text-body-sm text-on-surface dark:text-molten-text"
                value={selectedClientId}
                onChange={handleClientChange}
              >
                <option value="">-- Choose Client --</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="bg-arctic-surface dark:bg-[#1A1A24] rounded-lg border border-outline-variant/50 dark:border-[#2A345E] shadow-arctic dark:shadow-none overflow-hidden">
            <div className="p-stack-md border-b border-outline-variant/50 dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1A24]/50 flex justify-between items-center">
              <h3 className="font-headline-sm text-[16px] text-on-surface dark:text-molten-text font-semibold">Configured Webhooks</h3>
              {loading && <span className="text-xs text-arctic-text-muted dark:text-molten-text-muted">Loading...</span>}
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="border-b border-outline-variant/50 dark:border-[#2A345E] bg-surface-container-low dark:bg-[#1A1A24]/50">
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Event</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Target URL</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Status</th>
                  </tr>
                </thead>
                <tbody className="font-body-sm text-body-sm">
                  {webhooks.length === 0 ? (
                    <tr>
                      <td colSpan="3" className="px-4 py-8 text-center text-on-surface-variant dark:text-molten-text-muted">
                        No webhooks configured for this client.
                      </td>
                    </tr>
                  ) : (
                    webhooks.map((wh) => (
                      <tr key={wh.id} className="border-b border-outline-variant/20 dark:border-[#2A345E]/50">
                        <td className="px-4 py-3 font-medium text-on-surface dark:text-molten-text font-mono text-xs">
                          {wh.event}
                        </td>
                        <td className="px-4 py-3 text-on-surface-variant dark:text-molten-text-muted font-mono text-xs truncate max-w-xs">
                          {wh.url}
                        </td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${wh.active ? 'bg-secondary/15 text-secondary dark:bg-molten-success/15 dark:text-molten-success font-semibold' : 'bg-surface-container-high text-on-surface-variant'}`}>
                            {wh.active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Side: Webhook Upsert Form */}
        <div className="bg-arctic-surface dark:bg-[#1A1A24] p-stack-lg rounded-lg border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none flex flex-col gap-4">
          <h3 className="font-headline-sm text-headline-sm text-on-surface dark:text-molten-text font-semibold">
            Upsert Webhook Configuration
          </h3>
          <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">
            Configure or update the endpoint URL and secret signature for the selected event.
          </p>

          {error && (
            <div className="p-3 bg-arctic-error/15 border border-arctic-error/30 text-arctic-error dark:text-molten-error rounded-lg text-sm">
              {error}
            </div>
          )}

          {successMsg && (
            <div className="p-3 bg-secondary/15 border border-secondary/30 text-secondary dark:bg-molten-success/15 dark:text-molten-success rounded-lg text-sm">
              {successMsg}
            </div>
          )}

          <form onSubmit={handleUpsertWebhook} className="space-y-4">
            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Client
              </label>
              <select
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                value={formClientId}
                onChange={(e) => setFormClientId(e.target.value)}
                required
              >
                <option value="">Select Client</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Event
              </label>
              <select
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                value={formEvent}
                onChange={(e) => setFormEvent(e.target.value)}
                required
              >
                <option value="lead_qualified">lead_qualified</option>
                <option value="lead_not_interested">lead_not_interested</option>
                <option value="lead_callback">lead_callback</option>
                <option value="lead_failed">lead_failed</option>
                <option value="campaign_completed">campaign_completed</option>
              </select>
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Target URL
              </label>
              <input
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                placeholder="https://your-domain.com/webhooks/voice"
                type="url"
                value={formUrl}
                onChange={(e) => setFormUrl(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Secret (Signature Key)
              </label>
              <input
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary focus:ring-1 focus:ring-primary dark:focus:ring-molten-primary transition-colors"
                placeholder="whsec_..."
                type="text"
                value={formSecret}
                onChange={(e) => setFormSecret(e.target.value)}
                required
              />
            </div>

            <button
              type="submit"
              className="w-full py-2.5 rounded-lg bg-primary dark:bg-molten-primary text-on-primary font-label-md text-label-md shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:bg-primary-fixed-variant dark:hover:brightness-90 transition-colors"
            >
              Upsert Webhook
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
