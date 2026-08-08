/**
 * Regression: live concurrent slots must never demote/disappear across poll gaps.
 * Run: node frontend/src/client/utils/leadsDisplayQueue.regression.mjs
 */
import {
  createEmptyDialerQueues,
  reconcileDialerQueues,
  flattenDialerQueues,
  isLiveLeadRow,
} from './leadsDisplayQueue.js';

function assert(cond, msg) {
  if (!cond) {
    console.error('FAIL:', msg);
    process.exitCode = 1;
  } else {
    console.log('ok:', msg);
  }
}

function lead(id, status, extra = {}) {
  return { id, name: `L${id}`, phone: '+917397867643', status, ...extra };
}

// Simulate concurrency=4: four live → one finishes (gap before next claim) → page says completed
let state = createEmptyDialerQueues();
let r = reconcileDialerQueues(state, {
  callingLeads: [lead('a', 'calling'), lead('b', 'calling'), lead('c', 'calling'), lead('d', 'calling')],
  pageLeads: [lead('a', 'calling'), lead('b', 'calling'), lead('c', 'calling'), lead('d', 'calling'), lead('e', 'pending')],
  isLive: true,
  concurrency: 4,
  pollVersion: 1,
});
state = r.state;
assert(state.activeSlots.length === 4, '4 active slots when 4 calling');
assert(flattenDialerQueues(state).slice(0, 4).every(isLiveLeadRow), 'top 4 are Live');

// Gap poll: a finished, not yet replaced; page shows a completed; calling = b,c,d
r = reconcileDialerQueues(state, {
  callingLeads: [lead('b', 'calling'), lead('c', 'calling'), lead('d', 'calling')],
  pageLeads: [
    lead('a', 'completed', { outcome: 'Interested' }),
    lead('b', 'calling'),
    lead('c', 'calling'),
    lead('d', 'calling'),
    lead('e', 'pending'),
  ],
  isLive: true,
  concurrency: 4,
  pollVersion: 2,
});
state = r.state;
assert(state.activeSlots.length === 4, 'still 4 slots after one finishes (reserved)');
const flat = flattenDialerQueues(state);
assert(flat.slice(0, 4).every(isLiveLeadRow), 'reserved + live still show Live badge path');
assert(flat[0].status === 'calling', 'page completed must NOT demote reserved status');
const reserved = state.activeSlots.filter((s) => s.reserved);
assert(reserved.length === 1, 'exactly one reserved slot');
assert(reserved[0].leadId === 'a', 'finished lead holds its slot');

// Empty calling gap (all four finish before next claim) — all reserved, none disappear
r = reconcileDialerQueues(state, {
  callingLeads: [],
  pageLeads: [
    lead('a', 'completed'),
    lead('b', 'completed'),
    lead('c', 'completed'),
    lead('d', 'completed'),
    lead('e', 'pending'),
  ],
  isLive: true,
  concurrency: 4,
  pollVersion: 3,
});
state = r.state;
assert(state.activeSlots.length === 4, '4 reserved slots across full claim gap');
assert(flattenDialerQueues(state).slice(0, 4).every(isLiveLeadRow), 'gap: all 4 still Live at top');

// Next claim fills oldest reserved
r = reconcileDialerQueues(state, {
  callingLeads: [lead('e', 'calling')],
  pageLeads: [
    lead('a', 'completed'),
    lead('b', 'completed'),
    lead('c', 'completed'),
    lead('d', 'completed'),
    lead('e', 'calling'),
  ],
  isLive: true,
  concurrency: 4,
  pollVersion: 4,
});
state = r.state;
assert(state.activeSlots.some((s) => s.leadId === 'e' && !s.reserved), 'new call fills reserved slot');
assert(flattenDialerQueues(state).filter(isLiveLeadRow).length >= 1, 'new live present');
assert(state.completedQueue.some((l) => l.id === 'a'), 'replaced reserved moved to completed');

if (process.exitCode) {
  console.error('Regression FAILED');
  process.exit(1);
}
console.log('Regression PASSED');
