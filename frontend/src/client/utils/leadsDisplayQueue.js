/**
 * Enterprise dialer display state — transport-agnostic.
 *
 * Polling or WebSocket/SSE both feed the same reconcile path:
 *   snapshot | events  →  transitions  →  patch persistent slots/queues
 *
 * Active slots are permanent objects with stable slotId.
 * Reserved slots fill oldest-first (deterministic).
 * While campaign is live, reserved/active leads NEVER demote from Live
 * presentation due to page-snapshot polls (that was the flicker bug).
 * byId patches in place (identity for React.memo).
 * Side-queue membership is Map-indexed (O(1) remove) → overall O(n).
 */

export const TRANSITIONS = {
  CALL_STARTED: 'CALL_STARTED',
  CALL_FINISHED: 'CALL_FINISHED',
  CALL_FAILED: 'CALL_FAILED',
  CALL_CALLBACK: 'CALL_CALLBACK',
  CALL_CANCELLED: 'CALL_CANCELLED',
  CALL_PENDING: 'CALL_PENDING',
  STATUS_PATCH: 'STATUS_PATCH',
};

let _slotSeq = 0;
function nextSlotId() {
  _slotSeq += 1;
  return `slot-${_slotSeq}`;
}

const SIDE_KEYS = ['completedQueue', 'pendingQueue', 'callbackQueue', 'cancelledQueue'];

export function createEmptyDialerQueues() {
  return {
    /** Permanent slot objects — never rebuilt from filter(); only fields mutate. */
    activeSlots: [],
    completedQueue: [],
    pendingQueue: [],
    callbackQueue: [],
    cancelledQueue: [],
    /** id → mutable lead object (stable reference across polls) */
    byId: new Map(),
    /** id → which side queue key holds it (O(1) membership) */
    sideIndex: new Map(),
    pollVersion: 0,
    epoch: 0, // bumps on campaign restart
  };
}

const idOf = (row) => (row?.id == null ? null : String(row.id));

function terminalQueueKey(status) {
  if (status === 'callback_scheduled') return 'callbackQueue';
  if (status === 'cancelled') return 'cancelledQueue';
  if (status === 'pending') return 'pendingQueue';
  if (status === 'completed' || status === 'failed') return 'completedQueue';
  return 'pendingQueue';
}

function transitionType(fromStatus, toStatus) {
  if (toStatus === fromStatus) return TRANSITIONS.STATUS_PATCH;
  if (toStatus === 'calling') return TRANSITIONS.CALL_STARTED;
  if (toStatus === 'completed') return TRANSITIONS.CALL_FINISHED;
  if (toStatus === 'failed') return TRANSITIONS.CALL_FAILED;
  if (toStatus === 'callback_scheduled') return TRANSITIONS.CALL_CALLBACK;
  if (toStatus === 'cancelled') return TRANSITIONS.CALL_CANCELLED;
  if (toStatus === 'pending') return TRANSITIONS.CALL_PENDING;
  return TRANSITIONS.STATUS_PATCH;
}

function isActiveSlotLead(state, id) {
  return findActiveSlotIndexByLead(state, id) >= 0;
}

/**
 * Patch lead fields in place. Never lets a page/snapshot overwrite demote
 * an active/reserved slot lead away from Live presentation.
 */
export function upsertLead(state, incoming, { allowDemoteActive = false } = {}) {
  const id = idOf(incoming);
  if (!id) return null;
  const existing = state.byId.get(id);
  const inActive = isActiveSlotLead(state, id);
  if (existing) {
    if (inActive && !allowDemoteActive) {
      const slot = state.activeSlots[findActiveSlotIndexByLead(state, id)];
      const keepLive = Boolean(slot?.reserved) || existing.status === 'calling' || incoming.status === 'calling';
      const reservedFlag = Boolean(slot?.reserved) || Boolean(existing.__reservedSlot);
      Object.assign(existing, incoming);
      if (keepLive) {
        existing.status = 'calling';
        if (reservedFlag || slot?.reserved) existing.__reservedSlot = true;
        else delete existing.__reservedSlot;
      }
      return existing;
    }
    Object.assign(existing, incoming);
    if (!inActive) {
      delete existing.__reservedSlot;
      delete existing.__stickyCalling;
      delete existing.__stickySince;
    }
    return existing;
  }
  const created = { ...incoming };
  state.byId.set(id, created);
  return created;
}

function removeFromSideQueues(state, id) {
  const key = state.sideIndex.get(id);
  if (!key) return;
  const arr = state[key];
  if (!arr) {
    state.sideIndex.delete(id);
    return;
  }
  const idx = arr.findIndex((l) => idOf(l) === id);
  if (idx >= 0) arr.splice(idx, 1);
  state.sideIndex.delete(id);
}

function prependToQueue(state, key, lead) {
  const id = idOf(lead);
  if (!id) return;
  removeFromSideQueues(state, id);
  state[key].unshift(lead);
  state.sideIndex.set(id, key);
}

function appendStable(state, key, lead) {
  const id = idOf(lead);
  if (!id) return;
  if (state.sideIndex.get(id) === key) return;
  removeFromSideQueues(state, id);
  state[key].push(lead);
  state.sideIndex.set(id, key);
}

function findActiveSlotIndexByLead(state, id) {
  return state.activeSlots.findIndex((s) => s.leadId === id);
}

/** Oldest reserved slot = lowest reservedAt (then lowest slot index). */
function findOldestReservedSlotIndex(state) {
  let best = -1;
  let bestAt = Infinity;
  for (let i = 0; i < state.activeSlots.length; i += 1) {
    const s = state.activeSlots[i];
    if (!s.reserved) continue;
    const at = s.reservedAt ?? i;
    if (at < bestAt) {
      bestAt = at;
      best = i;
    }
  }
  return best;
}

function createSlot({ leadId = null, lead = null, reserved = false, reservedAt = null } = {}) {
  return {
    slotId: nextSlotId(),
    leadId,
    lead,
    reserved,
    reservedAt,
  };
}

/** Force Live presentation on every occupied active slot (reserved or real). */
export function syncActiveSlotPresentation(state) {
  for (const slot of state.activeSlots || []) {
    if (!slot.lead) continue;
    slot.lead.status = 'calling';
    if (slot.reserved) slot.lead.__reservedSlot = true;
    else delete slot.lead.__reservedSlot;
  }
  return state;
}

/**
 * Diff previous statuses vs snapshot → transition events.
 * Transport-agnostic: same shape can come from poll or websocket payloads.
 */
export function calculateTransitions(prevById, snapshotById) {
  const transitions = [];
  const ids = new Set([...prevById.keys(), ...snapshotById.keys()]);
  for (const id of ids) {
    const prev = prevById.get(id);
    const next = snapshotById.get(id);
    if (!next && prev) continue;
    if (!prev && next) {
      transitions.push({
        type: transitionType(null, next.status),
        leadId: id,
        fromStatus: null,
        toStatus: next.status,
        lead: next,
      });
      continue;
    }
    if (prev && next && prev.status !== next.status) {
      transitions.push({
        type: transitionType(prev.status, next.status),
        leadId: id,
        fromStatus: prev.status,
        toStatus: next.status,
        lead: next,
      });
    } else if (prev && next) {
      transitions.push({
        type: TRANSITIONS.STATUS_PATCH,
        leadId: id,
        fromStatus: next.status,
        toStatus: next.status,
        lead: next,
      });
    }
  }
  return transitions;
}

function releaseSlotLeadToSide(state, slot) {
  const lead = slot.lead;
  if (!lead) return;
  const status = slot.terminalStatus || (lead.status === 'calling' ? 'completed' : lead.status);
  lead.status = status;
  delete lead.__reservedSlot;
  prependToQueue(state, terminalQueueKey(status), lead);
  slot.leadId = null;
  slot.lead = null;
  slot.reserved = false;
  slot.reservedAt = null;
  slot.terminalStatus = null;
}

/**
 * Apply transition events onto persistent slot/queue state.
 * Mutates slot objects in place — array identity of each slot object is kept.
 */
export function applyTransitions(prevState, transitions, {
  callingIds,
  isLive,
  concurrency,
} = {}) {
  const state = prevState; // mutate persistent structure
  const callingSet = new Set([...(callingIds || [])].map(String));
  const slotTarget = Math.max(0, Number(concurrency) || 0);
  let reserveClock = 0;

  for (const t of transitions) {
    upsertLead(state, t.lead, { allowDemoteActive: true });
  }

  for (const t of transitions) {
    if (t.type === TRANSITIONS.STATUS_PATCH) continue;
    const lead = state.byId.get(t.leadId);
    if (!lead) continue;
    const slotIdx = findActiveSlotIndexByLead(state, t.leadId);

    // Live call ended → reserve that exact slot (do not remove / re-sort)
    if (t.fromStatus === 'calling' && t.toStatus !== 'calling' && slotIdx >= 0) {
      const slot = state.activeSlots[slotIdx];
      if (isLive) {
        slot.lead = lead;
        slot.leadId = t.leadId;
        slot.reserved = true;
        slot.reservedAt = reserveClock;
        slot.terminalStatus = t.toStatus;
        reserveClock += 1;
        lead.status = 'calling';
        lead.__reservedSlot = true;
      } else {
        lead.status = t.toStatus;
        releaseSlotLeadToSide(state, slot);
        state.activeSlots.splice(slotIdx, 1);
      }
      continue;
    }

    if (t.type === TRANSITIONS.CALL_STARTED) {
      removeFromSideQueues(state, t.leadId);
      const existingIdx = findActiveSlotIndexByLead(state, t.leadId);
      if (existingIdx >= 0) {
        const slot = state.activeSlots[existingIdx];
        slot.lead = lead;
        slot.leadId = t.leadId;
        slot.reserved = false;
        slot.reservedAt = null;
        slot.terminalStatus = null;
        lead.status = 'calling';
        delete lead.__reservedSlot;
        continue;
      }

      // Deterministic: fill OLDEST reserved slot (not array-sort of calling list)
      const reservedIdx = findOldestReservedSlotIndex(state);
      if (reservedIdx >= 0) {
        const slot = state.activeSlots[reservedIdx];
        if (slot.lead && slot.leadId && slot.leadId !== t.leadId) {
          const finished = slot.lead;
          finished.status = slot.terminalStatus || 'completed';
          delete finished.__reservedSlot;
          prependToQueue(state, terminalQueueKey(finished.status), finished);
        }
        slot.lead = lead;
        slot.leadId = t.leadId;
        slot.reserved = false;
        slot.reservedAt = null;
        slot.terminalStatus = null;
        lead.status = 'calling';
        delete lead.__reservedSlot;
        continue;
      }

      // No reserved slot — allocate a new permanent slot object
      state.activeSlots.push(createSlot({ leadId: t.leadId, lead, reserved: false }));
      lead.status = 'calling';
      delete lead.__reservedSlot;
      continue;
    }

    if (t.toStatus !== 'calling' && slotIdx < 0) {
      if (t.type === TRANSITIONS.CALL_FINISHED || t.type === TRANSITIONS.CALL_FAILED) {
        prependToQueue(state, 'completedQueue', lead);
      } else if (t.type === TRANSITIONS.CALL_CALLBACK) {
        prependToQueue(state, 'callbackQueue', lead);
      } else if (t.type === TRANSITIONS.CALL_CANCELLED) {
        prependToQueue(state, 'cancelledQueue', lead);
      } else if (t.type === TRANSITIONS.CALL_PENDING) {
        appendStable(state, 'pendingQueue', lead);
      }
    }
  }

  // Recovery: live calling ids not yet in a slot
  for (const cid of callingSet) {
    if (findActiveSlotIndexByLead(state, cid) >= 0) continue;
    const lead = state.byId.get(cid);
    if (!lead) continue;
    lead.status = 'calling';
    delete lead.__reservedSlot;
    removeFromSideQueues(state, cid);
    const reservedIdx = findOldestReservedSlotIndex(state);
    if (reservedIdx >= 0) {
      const slot = state.activeSlots[reservedIdx];
      if (slot.lead && slot.leadId && slot.leadId !== cid) {
        const finished = slot.lead;
        finished.status = slot.terminalStatus || 'completed';
        delete finished.__reservedSlot;
        prependToQueue(state, terminalQueueKey(finished.status), finished);
      }
      slot.lead = lead;
      slot.leadId = cid;
      slot.reserved = false;
      slot.reservedAt = null;
      slot.terminalStatus = null;
    } else {
      state.activeSlots.push(createSlot({ leadId: cid, lead, reserved: false }));
    }
  }

  // Campaign not live → release reserved, keep only real calling
  if (!isLive) {
    const keep = [];
    for (const slot of state.activeSlots) {
      if (slot.reserved || !callingSet.has(String(slot.leadId))) {
        if (slot.lead) releaseSlotLeadToSide(state, slot);
        continue;
      }
      keep.push(slot); // same slot object
    }
    state.activeSlots.length = 0;
    state.activeSlots.push(...keep);
  }

  // Concurrency decreased → drop oldest reserved first, then trailing non-live slots.
  // Never drop a real in-progress calling lead while isLive.
  if (isLive && slotTarget > 0) {
    while (state.activeSlots.length > slotTarget) {
      let dropIdx = findOldestReservedSlotIndex(state);
      if (dropIdx < 0) {
        // Prefer dropping trailing slots that are NOT in the live calling set
        dropIdx = -1;
        for (let i = state.activeSlots.length - 1; i >= 0; i -= 1) {
          const s = state.activeSlots[i];
          if (!callingSet.has(String(s.leadId))) {
            dropIdx = i;
            break;
          }
        }
        if (dropIdx < 0) break; // all slots are real live calls — do not drop
      }
      const dropped = state.activeSlots.splice(dropIdx, 1)[0];
      if (dropped?.lead && (dropped.reserved || !callingSet.has(String(dropped.leadId)))) {
        releaseSlotLeadToSide(state, dropped);
      }
    }
  }

  syncActiveSlotPresentation(state);
  return state;
}

export function buildSnapshotMaps(callingLeads = [], pageLeads = []) {
  const snapshot = new Map();
  for (const row of pageLeads || []) {
    const id = idOf(row);
    if (id) snapshot.set(id, { ...row });
  }
  for (const row of callingLeads || []) {
    const id = idOf(row);
    if (id) snapshot.set(id, { ...row, status: 'calling' });
  }
  return snapshot;
}

/**
 * Prune byId / side queues to leads still referenced by slots or the current page snapshot.
 * Prevents unbounded growth across campaigns.
 */
export function pruneDialerState(state, keepIds) {
  const keep = keepIds instanceof Set ? keepIds : new Set(keepIds || []);
  for (const slot of state.activeSlots) {
    if (slot.leadId) keep.add(String(slot.leadId));
  }
  for (const key of SIDE_KEYS) {
    state[key] = state[key].filter((l) => {
      const id = idOf(l);
      if (keep.has(id)) return true;
      state.sideIndex.delete(id);
      return false;
    });
  }
  for (const id of [...state.byId.keys()]) {
    if (!keep.has(id)) state.byId.delete(id);
  }
  return state;
}

/** Full reset — campaign stop→start or campaign id change. */
export function resetDialerQueues(prev) {
  const next = createEmptyDialerQueues();
  next.epoch = (prev?.epoch || 0) + 1;
  next.pollVersion = 0;
  return next;
}

/**
 * Transport-agnostic reconcile from a lead snapshot (poll or WS bulk).
 */
export function reconcileDialerQueues(prevState, {
  callingLeads = [],
  pageLeads = [],
  isLive = false,
  concurrency = 0,
  pollVersion,
} = {}) {
  const state = prevState || createEmptyDialerQueues();
  if (pollVersion != null && pollVersion < state.pollVersion) {
    return { state, transitions: [], ignored: true };
  }

  const snapshot = buildSnapshotMaps(callingLeads, pageLeads);
  const prevStatus = new Map();
  for (const [id, lead] of state.byId.entries()) {
    prevStatus.set(id, { status: lead.status });
  }
  // Active/reserved slots are always "calling" for transition purposes —
  // page polls must not invent a false calling→completed→drop cycle.
  for (const slot of state.activeSlots) {
    if (slot.leadId) prevStatus.set(String(slot.leadId), { status: 'calling' });
  }

  const transitions = calculateTransitions(prevStatus, snapshot);
  applyTransitions(state, transitions, {
    callingIds: (callingLeads || []).map((l) => idOf(l)).filter(Boolean),
    isLive,
    concurrency,
  });

  for (const row of pageLeads || []) {
    const id = idOf(row);
    if (!id) continue;
    // Never let page rows demote active/reserved Live presentation
    if (findActiveSlotIndexByLead(state, id) >= 0) {
      upsertLead(state, row); // preserve-live path inside upsertLead
      continue;
    }
    if (row.status === 'calling') continue;
    const lead = upsertLead(state, row);
    if (!state.sideIndex.has(id)) {
      appendStable(state, terminalQueueKey(row.status), lead);
    }
  }

  syncActiveSlotPresentation(state);

  const keepIds = new Set(snapshot.keys());
  pruneDialerState(state, keepIds);

  state.pollVersion = pollVersion != null ? pollVersion : state.pollVersion + 1;
  return { state, transitions, ignored: false };
}

/**
 * Apply discrete events (WebSocket/SSE path) without a full snapshot.
 * Same queue mutations as poll-driven transitions.
 */
export function applyDialerEvents(prevState, events, opts = {}) {
  const state = prevState || createEmptyDialerQueues();
  const transitions = (events || []).map((e) => ({
    type: e.type || transitionType(e.fromStatus, e.toStatus),
    leadId: String(e.leadId),
    fromStatus: e.fromStatus ?? null,
    toStatus: e.toStatus,
    lead: e.lead,
  }));
  applyTransitions(state, transitions, opts);
  if (opts.pollVersion != null) state.pollVersion = opts.pollVersion;
  syncActiveSlotPresentation(state);
  return { state, transitions, ignored: false };
}

/** Flatten for render — reserved slots keep the same lead object (+ flag). */
export function flattenDialerQueues(state) {
  if (!state) return [];
  syncActiveSlotPresentation(state);
  const active = [];
  for (const slot of state.activeSlots || []) {
    if (!slot.lead) continue;
    active.push(slot.lead); // same object reference
  }
  return [
    ...active,
    ...(state.completedQueue || []),
    ...(state.pendingQueue || []),
    ...(state.callbackQueue || []),
    ...(state.cancelledQueue || []),
  ];
}

export function isLiveLeadRow(lead) {
  return Boolean(lead && (lead.status === 'calling' || lead.__reservedSlot));
}

export function filterFlattenedQueue(rows, { attemptsFilter, turnsFilter, getTurns } = {}) {
  if (!rows?.length) return [];
  const active = [];
  const rest = [];
  for (const lead of rows) {
    if (isLiveLeadRow(lead)) active.push(lead);
    else rest.push(lead);
  }
  let filtered = rest;
  if (attemptsFilter) {
    filtered = filtered.filter((l) => {
      const attempts = l.attempts || 0;
      if (attemptsFilter === '1') return attempts === 1;
      if (attemptsFilter === '2') return attempts === 2;
      if (attemptsFilter === '3') return attempts === 3;
      if (attemptsFilter === '4+') return attempts >= 4;
      return true;
    });
  }
  if (turnsFilter && typeof getTurns === 'function') {
    filtered = filtered.filter((l) => {
      const turns = getTurns(l);
      if (turnsFilter === '0') return turns === 0;
      if (turnsFilter === '1-3') return turns >= 1 && turns <= 3;
      if (turnsFilter === '4-8') return turns >= 4 && turns <= 8;
      if (turnsFilter === '9+') return turns >= 9;
      return true;
    });
  }
  return [...active, ...filtered];
}

export function filterDisplayQueue(queue, opts) {
  return filterFlattenedQueue(queue, opts);
}
