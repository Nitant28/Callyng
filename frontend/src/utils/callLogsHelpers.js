export function formatCallDuration(seconds) {
  if (seconds == null || seconds < 1) return '0s';
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s < 10 ? `0${s}` : s}s`;
}

export function normalizeOutcome(outcome) {
  const raw = (outcome || '').toString().trim();
  if (!raw) return '';
  const lower = raw.toLowerCase();
  if (lower === 'voicemail_detected' || lower === 'voicemail detected' || lower === 'voicemail') return 'Voicemail';
  if (lower === 'callback_requested' || lower === 'callback requested' || lower === 'callback_scheduled' || lower === 'callback scheduled') return 'Callback_Requested';
  if (lower === 'not_interested' || lower === 'not interested') return 'Not_Interested';
  if (lower === 'interested' || lower === 'interest') return 'Interested';
  if (lower === 'early_disconnect' || lower === 'early disconnect') return 'Early_Disconnect';
  if (lower === 'no_answer' || lower === 'no answer' || lower === 'cancel' || lower === 'no-answer') return 'No_Answer';
  if (lower === 'carrier_failed' || lower === 'carrier failed' || lower.includes('carrier') || lower.includes('failed')) return 'Carrier_Failed';
  if (lower === 'wrong_requirement' || lower === 'wrong requirement' || lower === 'wrong_number' || lower === 'wrong number') return 'Wrong_Requirement';
  if (lower === 'rejected') return 'Rejected';
  if (lower === 'unknown') return 'Unknown';
  return raw;
}

export function getInitials(name) {
  if (!name) return '?';
  return name
    .split(' ')
    .filter(Boolean)
    .map((p) => p[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

export function timelineGroupKey(iso) {
  if (!iso) return 'Unknown';
  const d = new Date(iso);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const callDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  if (callDay.getTime() === today.getTime()) return 'Today';
  if (callDay.getTime() === yesterday.getTime()) return 'Yesterday';
  return d.toLocaleDateString('en-US', { weekday: 'long' });
}

export function formatCallTime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}

export function groupCallsByTimeline(calls) {
  const groups = [];
  let current = null;
  calls.forEach((call) => {
    const key = timelineGroupKey(call.createdAt ?? call.created_at);
    if (!current || current.label !== key) {
      current = { label: key, calls: [] };
      groups.push(current);
    }
    current.calls.push(call);
  });
  return groups;
}

export function mapCallListRow(row) {
  return {
    sessionCallId: row.session_call_id,
    leadName: row.name || 'Unknown',
    leadPhone: row.phone || '',
    outcome: normalizeOutcome(row.outcome),
    durationSeconds: row.duration_seconds ?? 0,
    createdAt: row.created_at,
    campaignId: row.campaign_id,
    inProgress: row.in_progress === true,
  };
}

export function outcomeTone(outcome) {
  const o = (outcome || '').toLowerCase();
  if (o.includes('interest') || o === 'excellent') return 'success';
  if (o.includes('callback')) return 'info';
  if (o.includes('voicemail')) return 'info';
  if (o.includes('busy')) return 'neutral';
  if (o.includes('fail') || o.includes('carrier')) return 'danger';
  if (o.includes('no_answer') || o.includes('no answer')) return 'neutral';
  return 'neutral';
}

export function outcomeLabel(outcome) {
  if (!outcome) return 'Unknown';
  const labels = {
    Interested: 'Interested',
    Not_Interested: 'Not Interested',
    Early_Disconnect: 'Hung up early',
    Callback_Requested: 'Callback',
    No_Answer: 'No answer',
    Busy: 'Busy',
    Voicemail: 'Voicemail',
    Carrier_Failed: 'Carrier Failed',
    Unknown: 'Unknown',
  };
  return labels[outcome] || outcome.replace(/_/g, ' ');
}

export function parseCallDetail(data) {
  if (!data) return null;
  const call = { ...data };
  if (typeof call.transcript === 'string') {
    try {
      call.transcript = JSON.parse(call.transcript);
    } catch {
      call.transcript = [];
    }
  }
  if (typeof call.extraction_json === 'string') {
    try {
      call.extraction_json = JSON.parse(call.extraction_json);
    } catch {
      call.extraction_json = null;
    }
  }
  return call;
}
