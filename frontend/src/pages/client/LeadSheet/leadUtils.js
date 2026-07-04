export const campaignLabel = (c) => c?.title || c?.name || 'Untitled';

export const canImportToCampaign = (c) =>
  !['running', 'pausing', 'completed', 'cancelled'].includes((c?.status || '').toLowerCase());

export const parseLeadApiError = (err) => {
  if (err?.customErrorMessage) return err.customErrorMessage;
  const detail = err?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.errors) {
    const errors = detail.errors;
    if (Array.isArray(errors)) return errors.map((e) => (typeof e === 'string' ? e : e.msg || JSON.stringify(e))).join('; ');
    return String(errors);
  }
  if (Array.isArray(detail)) return detail.map((e) => e.msg || String(e)).join('; ');
  return err?.message || 'Request failed';
};

const OUTCOME_LABELS = {
  Interested: 'Interested',
  Not_Interested: 'Not Interested',
  Callback_Requested: 'Callback',
  Carrier_Failed: 'Failed',
  Early_Disconnect: 'Hung up',
  Max_Attempts_Reached: 'Max Attempts',
};

export const friendlyOutcome = (outcome, fallback = 'Unknown') => {
  const key = (outcome || '').toString().trim();
  if (!key) return fallback;
  return OUTCOME_LABELS[key] || key.replace(/_/g, ' ');
};

export const leadInitials = (name) => {
  if (!name) return '?';
  return name.split(/\s+/).map((w) => w[0]).join('').toUpperCase().slice(0, 2);
};

export const fmtDuration = (sec) => {
  if (sec == null || sec <= 0) return '—';
  const m = Math.floor(sec / 60);
  const s = Math.round(sec % 60);
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
};

export const fmtRelative = (iso) => {
  if (!iso) return '—';
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return 'Just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
};

const ANSWERED_OUTCOMES = new Set(['Interested', 'Not_Interested', 'Early_Disconnect', 'Wrong_Requirement']);
const UNANSWERED_OUTCOMES = new Set(['No_Answer', 'Busy', 'Rejected', 'Carrier_Failed']);

export const getLeadStatusDisplay = (lead) => {
  const dial = getLeadDialState(lead);
  const result = getLeadCallResult(lead);
  return {
    tone: dial.tone,
    label: dial.label,
    sub: dial.sub || result.sub || (result.label !== '—' ? result.label : null),
  };
};

/** Real-time dial queue state — shown on each lead row. */
export const getLeadDialState = (lead) => {
  const status = lead?.status;
  const attempts = lead?.attempts ?? 0;
  const max = lead?.maxAttempts ?? lead?.max_attempts ?? 3;

  if (status === 'calling') {
    return { label: 'Calling', sub: 'Live', tone: 'info', live: true };
  }
  if (status === 'callback_scheduled') {
    const at = lead.nextAttemptAt || lead.scheduledCallbackAt || lead.next_attempt_at || lead.scheduled_callback_at;
    let sub = 'Scheduled';
    if (at) {
      const diff = new Date(at) - Date.now();
      if (diff <= 0) sub = 'Due now';
      else {
        const mins = Math.ceil(diff / 60000);
        sub = mins < 60 ? `In ${mins}m` : `In ${Math.ceil(mins / 60)}h`;
      }
    }
    return { label: 'Callback', sub, tone: 'warning' };
  }
  if (status === 'pending' && attempts > 0) {
    return { label: 'Pending', sub: `Attempt ${attempts}/${max}`, tone: 'warning' };
  }
  if (status === 'pending') {
    return { label: 'Queued', sub: 'Awaiting dial', tone: 'neutral' };
  }
  if (status === 'completed') {
    return { label: 'Ended', sub: 'Call finished', tone: 'neutral' };
  }
  if (status === 'failed') {
    return { label: 'Failed', sub: attempts > 0 ? `${attempts} attempts` : null, tone: 'danger' };
  }
  return { label: (status || '—').replace(/_/g, ' '), tone: 'neutral' };
};

/** Last call connection result — answered, busy, no answer (not qualification; see Interest column). */
export const getLeadCallResult = (lead) => {
  const outcome = (lead?.outcome || '').toString();
  const status = lead?.status;

  if (status === 'calling') {
    return { label: 'In progress', tone: 'info' };
  }
  if (!outcome) {
    if (status === 'pending' || status === 'callback_scheduled') return { label: '—', tone: 'neutral' };
    if (status === 'failed') return { label: 'Unreachable', tone: 'danger' };
    return { label: '—', tone: 'neutral' };
  }
  if (outcome === 'Interested' || outcome === 'Not_Interested' || outcome === 'Wrong_Requirement') {
    return { label: 'Answered', tone: 'success' };
  }
  if (outcome === 'Callback_Requested') return { label: 'Callback requested', tone: 'warning' };
  if (outcome === 'Early_Disconnect') return { label: 'Hung up', sub: 'Answered', tone: 'warning' };
  if (UNANSWERED_OUTCOMES.has(outcome)) {
    const map = { No_Answer: 'No answer', Busy: 'Busy', Rejected: 'Declined', Carrier_Failed: 'Carrier failed' };
    return { label: map[outcome] || friendlyOutcome(outcome), tone: 'warning' };
  }
  if (ANSWERED_OUTCOMES.has(outcome)) {
    return { label: 'Answered', tone: 'success' };
  }
  return { label: friendlyOutcome(outcome), tone: 'neutral' };
};

/** Qualification outcome — Interested / Not Interested for each lead row. */
export const getLeadInterestState = (lead) => {
  const outcome = (lead?.outcome || '').toString();

  if (outcome === 'Interested') {
    return { label: 'Interested', tone: 'success' };
  }
  if (outcome === 'Not_Interested') {
    return { label: 'Not Interested', tone: 'danger' };
  }
  if (outcome === 'Wrong_Requirement') {
    return { label: 'Not Interested', sub: 'Wrong fit', tone: 'danger' };
  }
  if (lead?.status === 'calling') {
    return { label: '—', sub: 'On call', tone: 'neutral' };
  }
  if (lead?.status === 'pending' || lead?.status === 'callback_scheduled') {
    return { label: '—', sub: 'Pending', tone: 'neutral' };
  }
  return { label: '—', sub: 'Not qualified', tone: 'neutral' };
};

const STATUS_RANK = {
  calling: 0,
  ringing: 1,
  connecting: 1,
  connected: 1,
  busy: 2,
  callback_scheduled: 3,
  callback: 3,
  pending: 4,
  completed: 5,
  failed: 6,
};

const leadTimestamp = (lead, ...fields) => {
  for (const field of fields) {
    const raw = lead?.[field];
    if (raw) {
      const value = new Date(raw).getTime();
      if (!Number.isNaN(value)) return value;
    }
  }
  return 0;
};

const leadWasDialed = (lead) =>
  (lead?.attempts || 0) > 0 ||
  Boolean(lead?.last_call_ended_at || lead?.lastCallEndedAt || lead?.last_attempted_at || lead?.lastAttemptedAt);

/**
 * Live dial stack: current call(s) on top, each finished call drops one row below in LIFO order.
 */
export const sortLeadsCallStack = (rows, { live = false } = {}) => {
  if (!rows?.length) return rows;

  if (!live) {
    return [...rows].sort((a, b) => {
      const ra = STATUS_RANK[a.status] ?? 9;
      const rb = STATUS_RANK[b.status] ?? 9;
      if (ra !== rb) return ra - rb;
      const ta = leadTimestamp(a, 'updated_at', 'updatedAt', 'last_call_ended_at', 'lastCallEndedAt', 'last_attempted_at', 'lastAttemptedAt', 'created_at', 'createdAt');
      const tb = leadTimestamp(b, 'updated_at', 'updatedAt', 'last_call_ended_at', 'lastCallEndedAt', 'last_attempted_at', 'lastAttemptedAt', 'created_at', 'createdAt');
      return tb - ta;
    });
  }

  return [...rows].sort((a, b) => {
    const aLive = a?.status === 'calling';
    const bLive = b?.status === 'calling';
    if (aLive !== bLive) return aLive ? -1 : 1;

    if (aLive && bLive) {
      return leadTimestamp(b, 'last_attempted_at', 'lastAttemptedAt', 'updated_at', 'updatedAt')
        - leadTimestamp(a, 'last_attempted_at', 'lastAttemptedAt', 'updated_at', 'updatedAt');
    }

    const aDialed = leadWasDialed(a);
    const bDialed = leadWasDialed(b);
    if (aDialed !== bDialed) return aDialed ? -1 : 1;

    if (aDialed && bDialed) {
      return leadTimestamp(b, 'last_call_ended_at', 'lastCallEndedAt', 'last_attempted_at', 'lastAttemptedAt', 'updated_at', 'updatedAt')
        - leadTimestamp(a, 'last_call_ended_at', 'lastCallEndedAt', 'last_attempted_at', 'lastAttemptedAt', 'updated_at', 'updatedAt');
    }

    return leadTimestamp(b, 'created_at', 'createdAt') - leadTimestamp(a, 'created_at', 'createdAt');
  });
};

/** @deprecated Use sortLeadsCallStack */
export const pinCallingLeadsFirst = (rows) => sortLeadsCallStack(rows, { live: true });

export const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'calling', label: 'Calling' },
  { value: 'callback_scheduled', label: 'Callback' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
];

export const leadsToCsv = (rows) => {
  const header = ['Name', 'Phone', 'Email', 'Company', 'Campaign', 'Status', 'Attempts', 'Last Call', 'Duration', 'Notes'];
  const lines = rows.map((r) => [
    r.name || '',
    r.phone || '',
    r.metadata?.email || '',
    r.metadata?.company || '',
    r.campaignName || '',
    r.status || '',
    r.attempts ?? 0,
    r.lastCalledAt || '',
    r.lastCallDurationSeconds ?? '',
    r.metadata?.notes || '',
  ]);
  return [header, ...lines]
    .map((row) => row.map((v) => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\n');
};
