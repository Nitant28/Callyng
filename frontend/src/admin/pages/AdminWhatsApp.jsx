import React, { useEffect, useState, useMemo } from 'react';
import adminApi from '../../shared/api/admin';
import AdminCustomerFilter from '../components/AdminCustomerFilter';
import { useAdminData } from '../contexts/AdminDataContext';

export default function AdminWhatsApp() {
  const { clients } = useAdminData();
  const [clientId, setClientId] = useState('');
  const [integrations, setIntegrations] = useState([]);
  const [providerCatalog, setProviderCatalog] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [testMsg, setTestMsg] = useState('');
  const [conversations, setConversations] = useState([]);
  const [n8nStatus, setN8nStatus] = useState(null);
  const [n8nWebhookUrl, setN8nWebhookUrl] = useState('');
  const [n8nSaving, setN8nSaving] = useState(false);
  const [n8nTesting, setN8nTesting] = useState(false);
  const [form, setForm] = useState({
    provider: 'stub',
    display_name: '',
    phone_number_id: '',
    business_account_id: '',
    webhook_verify_token: '',
    access_token: '',
    api_key: '',
    app_secret: '',
    status: 'inactive',
    enabled: false,
    base_url: '',
    sender_id: '',
  });

  useEffect(() => {
    adminApi.get('/internal/messages/providers')
      .then((res) => setProviderCatalog(res.data?.providers || []))
      .catch(() => {});
    adminApi.get('/internal/n8n/status')
      .then((res) => setN8nStatus(res.data || null))
      .catch(() => {});
    adminApi.get('/internal/n8n/settings')
      .then((res) => setN8nWebhookUrl(res.data?.webhook_url || res.data?.webhook_url || ''))
      .catch(() => {});
  }, []);

  const selectedProvider = useMemo(
    () => providerCatalog.find((p) => p.key === form.provider) || null,
    [providerCatalog, form.provider],
  );

  const load = async (cid) => {
    if (!cid) { setIntegrations([]); setConversations([]); return; }
    setLoading(true);
    setError('');
    try {
      const res = await adminApi.get('/internal/messages/integrations', { params: { client_id: cid } });
      setIntegrations(res.data?.integrations || []);
      const conv = await adminApi.get('/internal/messages/conversations', { params: { client_id: cid } });
      setConversations(conv.data?.conversations || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load integrations');
    } finally { setLoading(false); }
  };

  useEffect(() => { load(clientId); }, [clientId]);

  const save = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    if (!clientId) { setError('Select a client first.'); return; }
    const body = {
      client_id: clientId,
      provider: form.provider,
      display_name: form.display_name || undefined,
      phone_number_id: form.phone_number_id || undefined,
      business_account_id: form.business_account_id || undefined,
      webhook_verify_token: form.webhook_verify_token || undefined,
      access_token: form.access_token || undefined,
      api_key: form.api_key || undefined,
      app_secret: form.app_secret || undefined,
      status: form.status,
      enabled: form.enabled,
      configuration: {},
    };
    if (form.base_url) body.configuration.base_url = form.base_url;
    if (form.sender_id) body.configuration.sender_id = form.sender_id;
    try {
      await adminApi.post('/internal/messages/integrations', body);
      setSuccess('Integration saved. Secrets stored server-side — never returned.');
      setForm((f) => ({ ...f, access_token: '', api_key: '', app_secret: '' }));
      load(clientId);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Save failed');
    }
  };

  const testConnection = async (integrationId) => {
    setTestMsg('');
    try {
      const res = await adminApi.post(
        `/internal/messages/integrations/${integrationId}/test`,
        null,
        { params: { client_id: clientId } },
      );
      setTestMsg(res.data?.message || (res.data?.ok ? 'Connected' : 'Failed'));
    } catch (err) {
      setTestMsg(err.response?.data?.detail || err.message || 'Test failed');
    }
  };

  const saveN8nWebhook = async (e) => {
    e.preventDefault();
    setN8nSaving(true);
    setError('');
    setSuccess('');
    try {
      await adminApi.put('/internal/n8n/settings', {
        webhook_url: n8nWebhookUrl.trim(),
        webhook_url: n8nWebhookUrl.trim(),
      });
      setSuccess('n8n webhook URL saved.');
      const statusRes = await adminApi.get('/internal/n8n/status');
      setN8nStatus(statusRes.data || null);
    } catch (err) {
      const detail = err.response?.data?.detail;
      const msg = Array.isArray(detail)
        ? detail.map((e) => e.msg || e).join(', ')
        : (typeof detail === 'string' ? detail : (err.customErrorMessage || err.message || 'Failed to save n8n webhook'));
      setError(msg);
    } finally {
      setN8nSaving(false);
    }
  };

  const testN8nWebhook = async () => {
    setN8nTesting(true);
    setTestMsg('');
    try {
      const res = await adminApi.post('/internal/n8n/settings/test');
      setTestMsg(res.data?.ok ? 'n8n connection test passed.' : 'n8n test failed');
      const statusRes = await adminApi.get('/internal/n8n/status');
      setN8nStatus(statusRes.data || null);
    } catch (err) {
      setTestMsg(err.response?.data?.detail || err.message || 'n8n test failed');
    } finally {
      setN8nTesting(false);
    }
  };

  const inputCls = 'w-full mt-1 px-3 py-2 rounded-lg border border-outline-variant dark:border-[#2A345E] bg-surface dark:bg-[#141210] text-sm';

  return (
    <div className="admin-page">
      <div className="admin-page__header">
        <div>
          <h1 className="admin-page__title">WhatsApp / Messages</h1>
          <p className="text-sm text-on-surface-variant dark:text-molten-text-muted mt-1">
            Per-client WhatsApp provider configuration. Credentials are write-only and never returned.
          </p>
        </div>
      </div>

      <div className="mb-4">
        <AdminCustomerFilter clients={clients} value={clientId} onChange={setClientId} />
      </div>

      {error && <div className="mb-3 p-3 rounded-lg bg-error-container/20 text-error text-sm">{error}</div>}
      {success && <div className="mb-3 p-3 rounded-lg bg-primary/10 text-primary text-sm">{success}</div>}
      {testMsg && <div className="mb-3 p-3 rounded-lg border border-outline-variant text-sm">{testMsg}</div>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <form onSubmit={save} className="rounded-lg border border-outline-variant dark:border-[#2A345E] p-4 space-y-3 bg-surface-container-lowest dark:bg-[#1A1A24]">
          <h2 className="font-semibold text-on-surface dark:text-molten-text">Add / update integration</h2>

          <label className="block text-xs">
            Provider
            <select className={inputCls} value={form.provider} onChange={(e) => setForm({ ...form, provider: e.target.value })}>
              {providerCatalog.length > 0
                ? providerCatalog.map((p) => <option key={p.key} value={p.key}>{p.label}{!p.live ? ' (pending docs)' : ''}</option>)
                : <>
                    <option value="stub">Stub (dev only)</option>
                    <option value="meta_cloud">Meta Cloud</option>
                    <option value="finbite">FinBite</option>
                    <option value="wapi">Wapi</option>
                    <option value="aakashvani_managed">Aakashvani managed</option>
                    <option value="custom">Custom HTTP</option>
                  </>
              }
            </select>
          </label>

          {selectedProvider?.note && (
            <div className="text-xs text-on-surface-variant p-2 rounded-lg bg-surface-container">{selectedProvider.note}</div>
          )}

          {(selectedProvider?.fields || []).map((f) => (
            <label key={f.key} className="block text-xs">
              {f.label}
              <input
                className={inputCls}
                type={f.secret ? 'password' : 'text'}
                autoComplete={f.secret ? 'new-password' : 'off'}
                placeholder={f.secret ? '••••••••' : ''}
                value={form[f.key] || ''}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
              />
            </label>
          ))}

          <label className="inline-flex items-center gap-2 text-xs mt-1">
            <input type="checkbox" checked={form.enabled} onChange={(e) => setForm({ ...form, enabled: e.target.checked })} />
            Enabled (allow live sends)
          </label>

          <button type="submit" className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold">
            Save integration
          </button>
        </form>

        <div className="rounded-lg border border-outline-variant dark:border-[#2A345E] p-4 bg-surface-container-lowest dark:bg-[#1A1A24]">
          <h2 className="font-semibold mb-3 text-on-surface dark:text-molten-text">Configured integrations</h2>
          {loading ? (
            <div className="text-sm text-on-surface-variant">Loading…</div>
          ) : integrations.length === 0 ? (
            <div className="text-sm text-on-surface-variant">No integrations for this client.</div>
          ) : (
            <ul className="space-y-3">
              {integrations.map((row) => (
                <li key={row.id} className="p-3 rounded-lg border border-outline-variant dark:border-[#2A345E]">
                  <div className="font-medium">{row.display_name || row.provider}</div>
                  <div className="text-xs text-on-surface-variant mt-1">
                    {row.provider}
                    {' · '}{row.enabled ? 'enabled' : 'disabled'}
                    {' · '}{row.connection_status || 'untested'}
                    {' · credentials '}{row.credentials_configured ? 'set' : 'missing'}
                    {row.last_tested_at ? ` · tested ${new Date(row.last_tested_at).toLocaleString()}` : ''}
                  </div>
                  {row.last_error && (
                    <div className="text-xs text-error mt-1">{row.last_error}</div>
                  )}
                  <button
                    type="button"
                    className="mt-2 text-xs font-semibold text-primary"
                    onClick={() => testConnection(row.id)}
                  >
                    Test connection
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-6 rounded-lg border border-outline-variant dark:border-[#2A345E] p-4 bg-surface-container-lowest dark:bg-[#1A1A24]">
        <h2 className="font-semibold mb-2 text-on-surface dark:text-molten-text">N8N Follow-up Workflow</h2>
        <p className="text-xs text-on-surface-variant mb-3">
          Paste the Mega_Workflow11 production webhook once (https://n8n.bhuvisx.com/webhook/…).
          Save, then Test Connection. That URL is global: every campaign’s interested post-call lead
          uses it. Do not paste this same URL on every campaign under Admin → Webhooks — those are
          optional CRM callbacks, not the WhatsApp follow-up workflow.
        </p>
        {n8nStatus && (
          <div className="text-xs mb-3 p-2 rounded-lg bg-surface-container">
            {n8nStatus.configured ? (
              <span className="text-primary font-medium">Connected ✓</span>
            ) : (
              <span className="text-error font-medium">Not configured ✕</span>
            )}
            {n8nStatus.webhook_host ? ` · ${n8nStatus.webhook_host}` : ''}
            {n8nStatus.last_tested_at ? ` · Last tested ${new Date(n8nStatus.last_tested_at).toLocaleString()}` : ''}
            {n8nStatus.last_test_status ? ` · ${n8nStatus.last_test_status}` : ''}
          </div>
        )}
        <form onSubmit={saveN8nWebhook} className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
          <label className="flex-1 text-xs">
            N8N Follow-up Workflow Webhook URL
            <input
              className={inputCls}
              type="url"
              placeholder="https://n8n.bhuvisx.com/webhook/…"
              value={n8nWebhookUrl}
              onChange={(e) => setN8nWebhookUrl(e.target.value)}
            />
          </label>
          <button type="submit" disabled={n8nSaving} className="px-4 py-2 rounded-lg bg-primary text-white text-sm font-semibold h-fit">
            {n8nSaving ? 'Saving…' : 'Save'}
          </button>
          <button
            type="button"
            disabled={n8nTesting || !n8nWebhookUrl.trim()}
            onClick={testN8nWebhook}
            className="px-4 py-2 rounded-lg border border-outline-variant text-sm font-semibold h-fit"
          >
            {n8nTesting ? 'Testing…' : 'Test Connection'}
          </button>
        </form>
      </div>

      <div className="mt-6 rounded-lg border border-outline-variant dark:border-[#2A345E] p-4 bg-surface-container-lowest dark:bg-[#1A1A24]">
        <h2 className="font-semibold mb-3 text-on-surface dark:text-molten-text">Campaign follow-up inbox</h2>
        <p className="text-xs text-on-surface-variant mb-3">
          Messages recorded after Mega_Workflow sends WhatsApp. Scoped to the selected client.
        </p>
        {conversations.length === 0 ? (
          <div className="text-sm text-on-surface-variant">No follow-up conversations recorded yet.</div>
        ) : (
          <ul className="space-y-2">
            {conversations.map((c) => (
              <li key={c.id} className="p-3 rounded-lg border border-outline-variant dark:border-[#2A345E] text-sm">
                <div className="font-medium">{c.customer_name || 'Unknown'} · {c.customer_phone}</div>
                <div className="text-xs text-on-surface-variant mt-1">
                  {c.campaign_name || 'No campaign'}
                  {c.last_message_status ? ` · ${c.last_message_status}` : ''}
                </div>
                {c.last_message_preview ? (
                  <div className="text-xs mt-1">{String(c.last_message_preview).slice(0, 140)}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
