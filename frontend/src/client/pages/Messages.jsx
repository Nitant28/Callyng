import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import clientApi from '../../api/client';

function sortMessages(rows) {
  return [...(rows || [])].sort((a, b) => {
    const ta = new Date(a.created_at || 0).getTime();
    const tb = new Date(b.created_at || 0).getTime();
    if (ta !== tb) return ta - tb;
    return String(a.id || '').localeCompare(String(b.id || ''));
  });
}

function mergeMessages(prev, next) {
  const map = new Map();
  [...(prev || []), ...(next || [])].forEach((m) => {
    if (!m?.id) return;
    map.set(String(m.id), m);
  });
  return sortMessages([...map.values()]);
}

function initials(name, phone) {
  const raw = String(name || '').trim();
  if (raw) {
    const parts = raw.split(/\s+/).filter(Boolean);
    return ((parts[0]?.[0] || '') + (parts[1]?.[0] || '')).toUpperCase() || 'C';
  }
  const digits = String(phone || '').replace(/\D/g, '');
  return digits.slice(-2) || 'WA';
}

function formatTime(value) {
  if (!value) return '';
  try {
    return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '';
  }
}

function formatDayLabel(value) {
  if (!value) return '';
  const d = new Date(value);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  const sameDay = (a, b) =>
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
  if (sameDay(d, today)) return 'Today';
  if (sameDay(d, yesterday)) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
}

function dayKey(value) {
  if (!value) return 'unknown';
  const d = new Date(value);
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

function statusTicks(status) {
  const s = String(status || '').toLowerCase();
  if (['read', 'delivered', 'received'].includes(s)) {
    return <span className="cl-wa-ticks" title={status}>✓✓</span>;
  }
  if (['sent', 'queued', 'accepted', 'pending'].includes(s)) {
    return <span className="cl-wa-ticks cl-wa-ticks--pending" title={status}>✓</span>;
  }
  if (['failed', 'error', 'undelivered'].includes(s)) {
    return <span className="cl-wa-ticks cl-wa-ticks--pending" title={status}>!</span>;
  }
  return null;
}

/**
 * Messages — professional WhatsApp-style conversation shell.
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
  const [hasMore, setHasMore] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const threadEndRef = useRef(null);
  const selectedIdRef = useRef(null);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

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

  const loadThread = useCallback(async (id, { quiet = false, offset = 0, appendOlder = false } = {}) => {
    if (!id) return;
    if (appendOlder) setLoadingOlder(true);
    else if (!quiet) setThreadLoading(true);
    try {
      const res = await clientApi.get(`/api/messages/conversations/${id}`, {
        params: { limit: 100, offset },
      });
      if (selectedIdRef.current !== id) return;
      setThread(res.data?.conversation || null);
      setHasMore(Boolean(res.data?.has_more));
      setMessages((prev) => {
        const next = res.data?.messages || [];
        if (appendOlder) return mergeMessages(next, prev);
        return quiet ? mergeMessages(prev, next) : sortMessages(next);
      });
    } catch (err) {
      if (!quiet && !appendOlder) {
        setError(err.customErrorMessage || 'Failed to load conversation.');
        setThread(null);
        setMessages([]);
      }
    } finally {
      if (appendOlder) setLoadingOlder(false);
      else if (!quiet) setThreadLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConversations();
    loadTemplates();
  }, [loadConversations, loadTemplates]);

  useEffect(() => {
    if (!selectedId || tab !== 'conversations') return undefined;
    const timer = setInterval(() => {
      loadThread(selectedId, { quiet: true });
    }, 8000);
    return () => clearInterval(timer);
  }, [selectedId, tab, loadThread]);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages.length, selectedId]);

  const openConversation = async (id) => {
    setSelectedId(id);
    setMessages([]);
    await loadThread(id);
  };

  const orderedMessages = useMemo(() => sortMessages(messages), [messages]);

  const timeline = useMemo(() => {
    const items = [];
    let lastDay = null;
    orderedMessages.forEach((m) => {
      const key = dayKey(m.created_at);
      if (key !== lastDay) {
        items.push({ type: 'day', id: `day-${key}`, label: formatDayLabel(m.created_at) });
        lastDay = key;
      }
      items.push({ type: 'message', id: m.id, message: m });
    });
    return items;
  }, [orderedMessages]);

  return (
    <div className="cl-page-container">
      <div className="cl-page-header" style={{ marginBottom: 16 }}>
        <div>
          <h1 className="cl-page-title" style={{ margin: 0 }}>Messages</h1>
          <p className="text-sm text-muted" style={{ marginTop: 4 }}>
            Follow-up conversations with full bot and client history.
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
              No templates synced yet. Templates appear after Admin connects a WhatsApp provider.
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
        <div className="cl-wa-shell">
          <aside className="cl-wa-list">
            <div className="cl-wa-list__search">
              <input
                placeholder="Search by name or phone"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="cl-wa-list__items">
              {loading ? (
                <div className="text-sm text-muted p-4">Loading conversations…</div>
              ) : conversations.length === 0 ? (
                <div className="text-sm text-muted p-4">
                  No chats yet. After an interested call, WhatsApp follow-ups appear here.
                </div>
              ) : (
                conversations.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    className={`cl-wa-list__item${selectedId === c.id ? ' is-active' : ''}`}
                    onClick={() => openConversation(c.id)}
                  >
                    <div className="cl-wa-avatar">{initials(c.customer_name, c.customer_phone)}</div>
                    <div style={{ minWidth: 0 }}>
                      <div className="cl-wa-list__name">{c.customer_name || c.customer_phone || 'Unknown'}</div>
                      <div className="cl-wa-list__preview">
                        {c.last_message_preview
                          ? String(c.last_message_preview).slice(0, 70)
                          : (c.customer_phone || 'No messages yet')}
                      </div>
                      <div className="cl-wa-list__meta">
                        {c.campaign_name || 'Campaign'}
                        {c.last_message_status ? ` · ${c.last_message_status}` : ''}
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </aside>

          <section className="cl-wa-thread">
            {!selectedId ? (
              <div className="cl-wa-empty">
                Select a conversation to view the message history.
              </div>
            ) : threadLoading ? (
              <div className="cl-wa-empty">Loading chat…</div>
            ) : (
              <>
                <div className="cl-wa-thread__header">
                  <div className="cl-wa-avatar cl-wa-avatar--sm">
                    {initials(thread?.customer_name, thread?.customer_phone)}
                  </div>
                  <div style={{ minWidth: 0 }}>
                    <div className="cl-wa-thread__title">
                      {thread?.customer_name || thread?.customer_phone || 'Customer'}
                    </div>
                    <div className="cl-wa-thread__subtitle">
                      {thread?.customer_phone}
                      {thread?.campaign_name ? ` · ${thread.campaign_name}` : ''}
                    </div>
                  </div>
                </div>

                <div className="cl-wa-thread__body">
                  {hasMore ? (
                    <div style={{ textAlign: 'center', marginBottom: 12 }}>
                      <button
                        type="button"
                        className="cl-btn cl-btn--ghost"
                        disabled={loadingOlder}
                        onClick={() => loadThread(selectedId, { appendOlder: true, offset: messages.length })}
                      >
                        {loadingOlder ? 'Loading…' : 'Load earlier messages'}
                      </button>
                    </div>
                  ) : null}
                  {timeline.length === 0 ? (
                    <div className="cl-wa-empty">No messages in this conversation yet.</div>
                  ) : (
                    timeline.map((item) => {
                      if (item.type === 'day') {
                        return (
                          <div key={item.id} className="cl-wa-day">{item.label}</div>
                        );
                      }
                      const m = item.message;
                      const dir = String(m.direction || '').toLowerCase();
                      const isClient = dir === 'incoming' || dir === 'inbound' || m.sender_role === 'customer';
                      return (
                        <div
                          key={item.id}
                          className={`cl-wa-row ${isClient ? 'cl-wa-row--client' : 'cl-wa-row--bot'}`}
                        >
                          <div className={`cl-wa-bubble ${isClient ? 'cl-wa-bubble--client' : 'cl-wa-bubble--bot'}`}>
                            <div className="cl-wa-bubble__sender">{isClient ? 'Customer' : 'Bot'}</div>
                            <div className="cl-wa-bubble__text">
                              {m.content || m.text_body || m.template_name || m.message_type || '—'}
                            </div>
                            <div className="cl-wa-bubble__meta">
                              <span>{formatTime(m.created_at)}</span>
                              {!isClient ? statusTicks(m.status) : null}
                            </div>
                          </div>
                        </div>
                      );
                    })
                  )}
                  <div ref={threadEndRef} />
                </div>

                <div className="cl-wa-thread__footer">
                  Conversation updates automatically when new messages arrive.
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
