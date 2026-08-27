/** Backend lead/call outcome values (call_logs.outcome, leads.outcome) */
export const BACKEND_INTERESTED = new Set(['Interested']);
export const BACKEND_ANSWERED = new Set([
  'Interested',
  'Not_Interested',
  'Early_Disconnect',
  'Wrong_Requirement',
  'Wrong_Number',
]);
export const BACKEND_FAILED = new Set(['Carrier_Failed', 'Rejected']);
export const BACKEND_NO_ANSWER = new Set(['No_Answer', 'Voicemail']);
export const BACKEND_BUSY = new Set(['Busy']);
export const BACKEND_CALLBACK = new Set(['Callback_Requested', 'Callback_Scheduled']);

/** Normalized (lowercase) sets used after normalizeOutcome() */
export const ACTIVE_STATUSES = new Set(['calling', 'in_progress', 'connecting', 'ringing', 'queued']);
export const INTERESTED_STATUSES = new Set(['interested']);
export const ANSWERED_STATUSES = new Set([
  'interested',
  'not_interested',
  'early_disconnect',
  'wrong_requirement',
  'answered',
]);
export const FAILED_STATUSES = new Set(['failed', 'carrier_failed', 'rejected']);
export const BUSY_STATUSES = new Set(['busy']);
export const NO_ANSWER_STATUSES = new Set(['no_answer', 'voicemail']);
export const SCHEDULED_STATUSES = new Set(['callback', 'callback_scheduled', 'callback_requested','bot_follow_up']);

export const STATUS_PRIORITY = {
  in_progress: 0,
  calling: 1,
  connecting: 2,
  ringing: 3,
  queued: 4,
  retrying: 5,
  callback: 6,
  callback_scheduled: 6,
  bot_follow_up: 6,
  pending: 7,
  interested: 8,
  answered: 9,
  not_interested: 10,
  completed: 11,
  failed: 12,
  carrier_failed: 12,
};

export const DATE_PERIODS = [
  'today',
  'yesterday',
  '2d',
  '3d',
  '7d',
  '14d',
  '30d',
  '90d',
  'custom',
];
