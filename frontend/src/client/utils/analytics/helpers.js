import {
  BACKEND_ANSWERED,
  BACKEND_BUSY,
  BACKEND_CALLBACK,
  BACKEND_FAILED,
  BACKEND_INTERESTED,
  BACKEND_NO_ANSWER,
} from './constants.js';

/** Prefer ended_at for completed calls so charts align with when outcomes were set. */
export const parseTimestamp = (item) => {
  const inProgress = item?.in_progress === true || item?.inProgress === true;
  const raw = inProgress
    ? (item?.started_at || item?.created_at || item?.startedAt || item?.createdAt)
    : (item?.ended_at ||
        item?.started_at ||
        item?.created_at ||
        item?.endedAt ||
        item?.startedAt ||
        item?.createdAt ||
        item?.timestamp);
  if (!raw) return null;
  const value = new Date(raw).getTime();
  return Number.isNaN(value) ? null : value;
};

export const safeNumber = (value) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
};

export const getRawOutcome = (call) => (call?.outcome || call?.status || '').toString().trim();

export const getIntentStatus = (call) =>
  (call?.extraction_json?.intent_status || call?.extractionJson?.intentStatus || '').toString().trim();

export const isCallInProgress = (call) =>
  call?.in_progress === true || call?.inProgress === true;

export const isInterestedOutcome = (call) => {
  const raw = getRawOutcome(call);
  if (BACKEND_INTERESTED.has(raw)) return true;
  if (getIntentStatus(call) === 'Interested') return true;
  if (call?.qualified === true) return true;
  return normalizeOutcome(raw, isCallInProgress(call)) === 'interested';
};

export const isAnsweredOutcome = (call) => {
  if (isCallInProgress(call)) return true;
  const raw = getRawOutcome(call);
  if (BACKEND_ANSWERED.has(raw)) return true;
  const duration = safeNumber(call?.duration_seconds ?? call?.duration);
  if (duration > 0 && raw && raw !== 'Unknown') return true;
  const norm = normalizeOutcome(raw, false);
  return ['interested', 'not_interested', 'wrong_requirement', 'early_disconnect', 'answered'].includes(norm);
};

export const normalizeOutcome = (rawOutcome, inProgress) => {
  if (inProgress === true) return 'in_progress';
  const raw = (rawOutcome || '').toString().trim();
  if (!raw) return 'completed';
  const lower = raw.toLowerCase();

  if (lower === 'calling') return 'calling';
  if (lower === 'connecting') return 'connecting';
  if (lower === 'ringing') return 'ringing';
  if (lower === 'queued') return 'queued';
  if (lower === 'retrying') return 'retrying';
  if (lower === 'interested') return 'interested';
  if (lower === 'not_interested') return 'not_interested';
  if (lower === 'no_answer' || lower === 'noanswer' || lower === 'voicemail') return 'no_answer';
  if (lower === 'busy') return 'busy';
  if (lower === 'early_disconnect' || lower === 'earlydisconnect') return 'early_disconnect';
  if (lower === 'carrier_failed' || lower === 'rejected') return 'carrier_failed';
  if (lower === 'callback_requested' || lower === 'callback_scheduled') return 'callback_scheduled';
  if (lower === 'callback') return 'callback';
  if (lower === 'pending') return 'pending';
  if (lower === 'wrong_requirement' || lower === 'wrong_number' || lower === 'wrong number') return 'wrong_requirement';
  if (lower === 'answered' || lower === 'answer') return 'answered';

  return lower.replace(/\s+/g, '_') || 'completed';
};

export const outcomeLabel = (call) => {
  if (isCallInProgress(call)) return 'Live call';
  const intent = getIntentStatus(call);
  if (intent === 'Interested') return 'Interested';
  if (intent === 'Not_Interested') return 'Not interested';
  if (intent === 'Callback_Requested') return 'Callback requested';

  const raw = getRawOutcome(call);
  if (BACKEND_INTERESTED.has(raw)) return 'Interested';
  if (raw === 'Not_Interested') return 'Not interested';
  if (BACKEND_NO_ANSWER.has(raw)) return 'No answer';
  if (BACKEND_BUSY.has(raw)) return 'Busy';
  if (BACKEND_FAILED.has(raw)) return 'Failed';
  if (BACKEND_CALLBACK.has(raw)) return 'Callback';
  if (BACKEND_ANSWERED.has(raw)) return 'Answered';
  if (raw && raw !== 'Unknown') return raw.replace(/_/g, ' ');
  return 'Call ended';
};

export const statusTone = (call) => {
  if (isCallInProgress(call)) return 'live';
  if (isInterestedOutcome(call)) return 'success';
  const raw = getRawOutcome(call);
  if (raw === 'Not_Interested') return 'muted';
  if (BACKEND_BUSY.has(raw) || BACKEND_NO_ANSWER.has(raw)) return 'warning';
  if (BACKEND_FAILED.has(raw)) return 'danger';
  if (isAnsweredOutcome(call)) return 'info';
  return 'neutral';
};

export const formatRelativeTime = (iso) => {
  if (!iso) return 'Unknown';
  const diffMs = Date.now() - new Date(iso).getTime();
  if (diffMs < 30_000) return 'Just now';
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
};

export const formatClockTime = (iso) => {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '—';
  }
};

export const getDayKey = (timestamp) => {
  const date = new Date(timestamp);
  return date.toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
};

export const getHourKey = (timestamp) => {
  const date = new Date(timestamp);
  return `${String(date.getHours()).padStart(2, '0')}:00`;
};

export const getCampaignField = (campaign = {}, field) => {
  const altField = field.replace(/_([a-z])/g, (_, char) => char.toUpperCase());
  return campaign?.[field] ?? campaign?.[altField] ?? 0;
};

export const sumCampaignField = (campaigns = [], field) =>
  (campaigns ?? []).reduce((sum, campaign) => sum + safeNumber(getCampaignField(campaign, field)), 0);

export const sortCallsForDisplay = (calls = []) =>
  [...calls].sort((a, b) => {
    const liveA = isCallInProgress(a);
    const liveB = isCallInProgress(b);
    if (liveA !== liveB) return liveA ? -1 : 1;
    return (parseTimestamp(b) ?? 0) - (parseTimestamp(a) ?? 0);
  });
