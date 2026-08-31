import { useCallback, useEffect, useState } from 'react';
import clientApi from '../../api/client';

/**
 * Messages — WhatsApp conversation shell.
 * Real provider data appears only after client WhatsApp API docs + adapter.
 */
export default function Messages() {
  const [conversations, setConversations] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [thread, setThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [threadLoading, setThreadLoading] = useState(false);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('conversations');

  const loadConversations = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await clientApi.get('/api/messages/conversations', {
        params: { search: search || undefined, limit: 50, offset: 0 },
      });
      setConversations(res.data?.conversations || []);
    } catch (err) {
      setError(err.customErrorMessage || 'Failed to load conversations.');
      setConversations([]);
    } finally {
      setLoading(false);
    }
  }, [search]);

  const loadTemplates = useCallback(async () => {
    try {
      const res = await clientApi.get('/api/messages/templates');
      setTemplates(res.data?.templates || []);
    } catch {
      setTemplates([]);
    }
  }, []);

  useEffect(() => {
    loadConversations();
    loadTemplates();
  }, [loadConversations, loadTemplates]);

  const openConversation = async (id) => {
    setSelectedId(id);
    setThreadLoading(true);
    try {
      const res = await clientApi.get(`/api/messages/conversations/${id}`);
      setThread(res.data?.conversation || null);
      setMessages(res.data?.messages || []);
    } catch (err) {
      setError(err.customErrorMessage || 'Failed to load conversation.');
      setThread(null);
      setMessages([]);
    } finally {
      setThreadLoading(false);
    }
  };

  return (
    <div className="cl-page-container">
      <div className="cl-page-header" style={{ marginBottom: 16 }}>
        <div>
          <h1 className="cl-page-title" style={{ margin: 0 }}>Messages</h1>
          <p className="text-sm text-muted" style={{ marginTop: 4 }}>
            Follow-up WhatsApp threads for your campaigns. Each conversation is a lead who received or replied to a follow-up.
          </p>
        </div>
      </div>

      <div className="cl-tabs" style={{ marginBottom: 12 }}>
        <button
          type="button"
          className={`cl-tab${tab === 'conversations' ? ' active' : ''}`}
          onClick={() => setTab('conversations')}
        >
          Conversations
        </button>
        <button
          type="button"
          className={`cl-tab${tab === 'templates' ? ' active' : ''}`}
          onClick={() => setTab('templates')}
        >
          Templates
        </button>
      </div>

      {error && (
        <div className="cl-campaign-alert" style={{ marginBottom: 12 }}>
          <div className="cl-campaign-alert__text">{error}</div>
        </div>
      )}

      {tab === 'templates' ? (
        <div className="cl-card" style={{ padding: 16 }}>
          {templates.length === 0 ? (
            <div className="text-sm text-muted py-8 text-center">
              No templates synced yet. Templates appear after Admin connects a WhatsApp provider using the client&apos;s API documentation.
            </div>
          ) : (
            <div className="space-y-3">
              {templates.map((t) => (
                <div key={t.id} className="border border-outline-variant rounded-lg p-3">
                  <div className="font-semibold">{t.name}</div>
                  <div className="text-xs text-muted">
                    {t.language || '—'} · {t.category || '—'} · {t.status}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div
          className="cl-card"
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(240px, 320px) 1fr',
            minHeight: 480,
            overflow: 'hidden',
          }}
        >
          <aside style={{ borderRight: '1px solid var(--border)', padding: 12 }}>
            <input
              className="cl-search"
              style={{ width: '100%', marginBottom: 12 }}
              placeholder="Search name or phone…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {loading ? (
              <div className="text-sm text-muted p-4">Loading…</div>
            ) : conversations.length === 0 ? (
              <div className="text-sm text-muted p-4">
                No follow-ups yet. After an interested call, WhatsApp template sends appear here for each lead.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {conversations.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => openConversation(c.id)}
                    className="text-left"
                    style={{
                      padding: '10px 12px',
                      borderRadius: 8,
                      border: 'none',
                      background: selectedId === c.id ? 'rgba(37,99,235,0.08)' : 'transparent',
                      cursor: 'pointer',
                    }}
                  >
                    <div className="font-semibold text-sm">{c.customer_name || 'Unknown'}</div>
                    <div className="text-xs text-muted">{c.customer_phone}</div>
                    <div className="text-xs text-muted">
                      {c.campaign_name || (c.campaign_id ? 'Campaign' : 'No campaign')}
                      {c.last_message_status ? ` · ${c.last_message_status}` : ''}
                    </div>
                    {c.last_message_preview ? (
                      <div className="text-xs" style={{ marginTop: 4, opacity: 0.85 }}>
                        {String(c.last_message_preview).slice(0, 80)}
                      </div>
                    ) : null}
                  </button>
                ))}
              </div>
            )}
          </aside>

          <section style={{ padding: 16 }}>
            {!selectedId ? (
              <div className="text-sm text-muted h-full flex items-center justify-center">
                Select a conversation to view messages.
              </div>
            ) : threadLoading ? (
              <div className="text-sm text-muted">Loading thread…</div>
            ) : (
              <>
                <div style={{ marginBottom: 16 }}>
                  <div className="font-semibold">{thread?.customer_name || 'Customer'}</div>
                  <div className="text-xs text-muted">
                    {thread?.customer_phone}
                    {thread?.campaign_name ? ` · ${thread.campaign_name}` : thread?.campaign_id ? ` · Campaign ${thread.campaign_id}` : ''}
                    {thread?.lead_id ? ` · Lead ${thread.lead_id}` : ''}
                  </div>
                </div>
                {messages.length === 0 ? (
                  <div className="text-sm text-muted">No messages in this conversation.</div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {messages.map((m) => (
                      <div
                        key={m.id}
                        style={{
                          alignSelf: m.direction === 'outgoing' ? 'flex-end' : 'flex-start',
                          maxWidth: '75%',
                          padding: '10px 12px',
                          borderRadius: 12,
                          background: m.direction === 'outgoing' ? 'rgba(37,99,235,0.12)' : 'rgba(15,23,42,0.06)',
                        }}
                      >
                        <div className="text-sm">{m.text_body || m.template_name || m.message_type}</div>
                        <div className="text-xs text-muted" style={{ marginTop: 4 }}>
                          {m.status}
                          {m.created_at ? ` · ${new Date(m.created_at).toLocaleString()}` : ''}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
