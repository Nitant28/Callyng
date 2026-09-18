import React, { useState, useEffect, useCallback } from 'react';
import adminApi from '../../shared/api/admin';

const DEFAULT_EVENTS = [
  'lead_qualified',
  'lead_not_interested',
  'lead_callback',
  'lead_failed',
  'campaign_completed',
];

export default function AdminWebhooks() {
  const [clients, setClients] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [events, setEvents] = useState(DEFAULT_EVENTS);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [webhooks, setWebhooks] = useState([]);

  const [formClientId, setFormClientId] = useState('');
  const [formCampaignId, setFormCampaignId] = useState('');
  const [formEvent, setFormEvent] = useState('lead_qualified');
  const [formUrl, setFormUrl] = useState('');
  const [formSecret, setFormSecret] = useState('');

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState('');
  const [deletingId, setDeletingId] = useState('');
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

  const fetchCampaignsForClient = useCallback(async (clientId) => {
    if (!clientId) {
      setCampaigns([]);
      return;
    }
    try {
      const res = await adminApi.get('/internal/campaigns', { params: { client_id: clientId } });
      setCampaigns(res.data.campaigns || []);
    } catch (err) {
      console.error('Failed to fetch campaigns', err);
      setCampaigns([]);
    }
  }, []);

  const fetchWebhooks = async (clientId) => {
    if (!clientId) {
      setWebhooks([]);
      return;
    }
    try {
      setLoading(true);
      const res = await adminApi.get(`/internal/clients/${clientId}/webhooks`);
      setWebhooks(res.data.webhooks || []);
      if (Array.isArray(res.data.events) && res.data.events.length) {
        setEvents(res.data.events);
      }
    } catch (err) {
      console.error('Failed to fetch webhooks', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchClients();
  }, []);

  useEffect(() => {
    fetchCampaignsForClient(formClientId);
  }, [formClientId, fetchCampaignsForClient]);

  useEffect(() => {
    if (selectedClientId) {
      fetchWebhooks(selectedClientId);
      // Keep upsert form aligned with the selected client so campaign list is visible.
      if (selectedClientId !== formClientId) {
        setFormClientId(selectedClientId);
        setFormCampaignId('');
      }
    } else {
      setWebhooks([]);
    }
  }, [selectedClientId]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleFilterClientChange = (clientId) => {
    setSelectedClientId(clientId);
    setFormClientId(clientId);
    setFormCampaignId('');
  };

  const handleFormClientChange = (clientId) => {
    setFormClientId(clientId);
    setFormCampaignId('');
    setSelectedClientId(clientId);
  };

  const handleUpsertWebhook = async (e) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    if (!formClientId || !formCampaignId || !formEvent || !formUrl) {
      setError('Client, campaign, event, and target URL are required.');
      return;
    }

    try {
      setSaving(true);
      const body = {
        client_id: formClientId,
        campaign_id: formCampaignId,
        event: formEvent,
        url: formUrl,
      };
      if (formSecret.trim()) {
        body.secret = formSecret.trim();
      }
      await adminApi.post('/internal/webhook-configs', body);
      setSuccessMsg('Webhook configuration saved for this campaign and event.');
      if (formClientId === selectedClientId) {
        await fetchWebhooks(selectedClientId);
      }
      setFormUrl('');
      setFormSecret('');
    } catch (err) {
      console.error('Failed to upsert webhook config', err);
      const detail = err.response?.data?.detail;
      setError(
        (typeof detail === 'string' ? detail : null)
        || err.customErrorMessage
        || err.message
        || 'Failed to upsert webhook configuration.'
      );
    } finally {
      setSaving(false);
    }
  };

  const handleTestWebhook = async (webhookId) => {
    setTestingId(webhookId);
    setError('');
    setSuccessMsg('');
    try {
      const res = await adminApi.post(`/internal/webhook-configs/${webhookId}/test`);
      setSuccessMsg(res.data?.message || 'Connected to campaign webhook');
      await fetchWebhooks(selectedClientId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        (typeof detail === 'string' ? detail : null)
        || err.message
        || 'Webhook test failed'
      );
      await fetchWebhooks(selectedClientId);
    } finally {
      setTestingId('');
    }
  };

  const handleDeleteWebhook = async (wh) => {
    const label = `${wh.campaign_name || wh.campaign_id} / ${wh.event}`;
    if (!window.confirm(`Delete webhook for ${label}?\n\n${wh.url || ''}`)) {
      return;
    }
    setDeletingId(wh.id);
    setError('');
    setSuccessMsg('');
    try {
      await adminApi.delete(`/internal/webhook-configs/${wh.id}`);
      setSuccessMsg(`Deleted webhook for ${label}.`);
      await fetchWebhooks(selectedClientId);
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(
        (typeof detail === 'string' ? detail : null)
        || err.message
        || 'Failed to delete webhook'
      );
    } finally {
      setDeletingId('');
    }
  };

  return (
    <div className="w-full flex flex-col gap-stack-lg">
      <div>
        <h1 className="font-headline-lg text-headline-lg text-on-surface dark:text-molten-text">Webhooks</h1>
        <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted mt-2">
          Configure one webhook per client, campaign, and event. There is no global follow-up URL.
        </p>
      </div>

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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-gutter">
        <div className="lg:col-span-2 flex flex-col gap-stack-md">
          <div className="bg-arctic-surface dark:bg-[#1A1A24] p-stack-md rounded-lg border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none">
            <label className="block font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase mb-1.5">
              Client (view campaigns + webhooks)
            </label>
            <select
              className="w-full max-w-md px-3 py-2 bg-background dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg text-sm focus:outline-none focus:border-primary dark:focus:border-molten-primary font-body-sm text-body-sm text-on-surface dark:text-molten-text"
              value={selectedClientId}
              onChange={(e) => handleFilterClientChange(e.target.value)}
            >
              <option value="">-- Choose Client --</option>
              {clients.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            {selectedClientId ? (
              <div className="mt-3 rounded-lg border border-outline-variant/40 dark:border-[#2A345E] p-3">
                <div className="font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase mb-2">
                  Campaigns for this client ({campaigns.length})
                </div>
                {campaigns.length === 0 ? (
                  <div className="text-sm text-on-surface-variant dark:text-molten-text-muted">
                    No campaigns for this client yet.
                  </div>
                ) : (
                  <ul className="space-y-1 max-h-40 overflow-y-auto text-sm">
                    {campaigns.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          className={`w-full text-left px-2 py-1.5 rounded ${
                            formCampaignId === c.id
                              ? 'bg-primary/15 text-primary font-medium'
                              : 'hover:bg-surface-container-high dark:hover:bg-[#2A345E]/40'
                          }`}
                          onClick={() => {
                            setFormClientId(selectedClientId);
                            setFormCampaignId(c.id);
                          }}
                        >
                          {c.name}
                          <span className="block font-mono text-[11px] opacity-70">{c.id}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="mt-2 text-xs text-arctic-text-muted dark:text-molten-text-muted">
                  Click a campaign to pre-select it in Upsert Webhook on the right.
                </p>
              </div>
            ) : null}
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
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Client</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Campaign</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Event</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Target URL</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Status</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Last Test</th>
                    <th className="px-4 py-3 font-label-sm text-label-sm text-arctic-text-muted dark:text-molten-text-muted uppercase tracking-wider font-semibold">Actions</th>
                  </tr>
                </thead>
                <tbody className="font-body-sm text-body-sm">
                  {webhooks.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="px-4 py-8 text-center text-on-surface-variant dark:text-molten-text-muted">
                        No campaign webhooks configured for this client.
                      </td>
                    </tr>
                  ) : (
                    webhooks.map((wh) => (
                      <tr key={wh.id} className="border-b border-outline-variant/20 dark:border-[#2A345E]/50 align-top">
                        <td className="px-4 py-3 text-on-surface dark:text-molten-text">{wh.client_name || '—'}</td>
                        <td className="px-4 py-3 text-on-surface dark:text-molten-text">
                          <div className="font-medium">{wh.campaign_name || '—'}</div>
                          <div className="font-mono text-[11px] text-arctic-text-muted dark:text-molten-text-muted mt-0.5">{wh.campaign_id}</div>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs text-on-surface dark:text-molten-text">{wh.event}</td>
                        <td className="px-4 py-3 text-on-surface-variant dark:text-molten-text-muted font-mono text-xs truncate max-w-xs">{wh.url}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${wh.active ? 'bg-secondary/15 text-secondary dark:bg-molten-success/15 dark:text-molten-success font-semibold' : 'bg-surface-container-high text-on-surface-variant'}`}>
                            {wh.active ? 'Enabled' : 'Disabled'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-xs text-arctic-text-muted dark:text-molten-text-muted">
                          {wh.last_tested_at ? (
                            <>
                              <div>{wh.last_test_status || '—'}</div>
                              <div>{new Date(wh.last_tested_at).toLocaleString()}</div>
                            </>
                          ) : '—'}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-2">
                            <button
                              type="button"
                              disabled={testingId === wh.id || deletingId === wh.id}
                              onClick={() => handleTestWebhook(wh.id)}
                              className="px-3 py-1.5 rounded-lg border border-outline-variant dark:border-[#2A345E] text-xs"
                            >
                              {testingId === wh.id ? 'Testing…' : 'Test'}
                            </button>
                            <button
                              type="button"
                              disabled={testingId === wh.id || deletingId === wh.id}
                              onClick={() => handleDeleteWebhook(wh)}
                              className="px-3 py-1.5 rounded-lg border border-arctic-error/40 text-arctic-error dark:border-molten-error/40 dark:text-molten-error text-xs"
                            >
                              {deletingId === wh.id ? 'Deleting…' : 'Delete'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div className="bg-arctic-surface dark:bg-[#1A1A24] p-stack-lg rounded-lg border border-outline-variant/30 dark:border-[#2A345E] shadow-arctic dark:shadow-none flex flex-col gap-4">
          <h3 className="font-headline-sm text-headline-sm text-on-surface dark:text-molten-text font-semibold">
            Upsert Webhook Configuration
          </h3>
          <p className="font-body-sm text-body-sm text-arctic-text-muted dark:text-molten-text-muted">
            Routing rule: client → campaign → event → target URL. Secret is optional and used only for HMAC signing.
          </p>

          <form onSubmit={handleUpsertWebhook} className="space-y-4">
            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Client
              </label>
              <select
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                value={formClientId}
                onChange={(e) => handleFormClientChange(e.target.value)}
                required
              >
                <option value="">Select Client</option>
                {clients.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Campaign
              </label>
              <select
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                value={formCampaignId}
                onChange={(e) => setFormCampaignId(e.target.value)}
                required
                disabled={!formClientId}
              >
                <option value="">{formClientId ? 'Select Campaign' : 'Select a client first'}</option>
                {campaigns.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name} — {c.id}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Event / Status
              </label>
              <select
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                value={formEvent}
                onChange={(e) => setFormEvent(e.target.value)}
                required
              >
                {events.map((ev) => (
                  <option key={ev} value={ev}>{ev}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Target Webhook URL
              </label>
              <input
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                placeholder="https://n8n.example.com/webhook/..."
                type="url"
                value={formUrl}
                onChange={(e) => setFormUrl(e.target.value)}
                required
              />
            </div>

            <div>
              <label className="block font-label-sm text-label-sm text-on-surface dark:text-molten-text mb-1.5 uppercase tracking-wide">
                Secret (HMAC, optional)
              </label>
              <input
                className="w-full bg-surface-container-lowest dark:bg-[#141210] border border-outline-variant dark:border-[#2A345E] rounded-lg px-3 py-2 font-body-sm text-body-sm text-on-surface dark:text-molten-text focus:outline-none focus:border-primary dark:focus:border-molten-primary"
                placeholder="Leave blank to keep existing / skip signing"
                type="password"
                autoComplete="new-password"
                value={formSecret}
                onChange={(e) => setFormSecret(e.target.value)}
              />
              <p className="mt-1 text-[11px] text-arctic-text-muted dark:text-molten-text-muted">
                Used for X-Aakashvani-Signature. Never shown in the list. Leave blank on update to preserve the current secret.
              </p>
            </div>

            <button
              type="submit"
              disabled={saving}
              className="w-full py-2.5 rounded-lg bg-primary dark:bg-molten-primary text-on-primary font-label-md text-label-md shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] hover:bg-primary-fixed-variant dark:hover:brightness-90 transition-colors"
            >
              {saving ? 'Saving…' : 'Upsert Webhook'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
