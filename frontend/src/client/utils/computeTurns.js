/** Same turn count used in CallTranscriptDrawer / LeadDrawer analytics. */
export function computeTurnsFromTranscript(callOrTranscript) {
  let turns = callOrTranscript;
  if (typeof turns === 'number') return turns;
  if (turns && typeof turns === 'object' && !Array.isArray(turns)) {
    if (typeof turns.turn_count === 'number') return turns.turn_count;
    if (typeof turns.turns === 'number') return turns.turns;
    turns = turns.transcript;
  }
  if (typeof turns === 'string') {
    try {
      turns = JSON.parse(turns);
    } catch {
      return 0;
    }
  }
  if (!Array.isArray(turns) || turns.length === 0) return 0;

  let aiTurns = 0;
  let custTurns = 0;
  turns.forEach((t) => {
    const role = t?.role;
    if (role === 'assistant' || role === 'bot') aiTurns += 1;
    else custTurns += 1;
  });
  return aiTurns + custTurns;
}

/** Map lead_id / session_call_id → turn count from already-loaded calls. */
export function buildTurnsByLead(calls = []) {
  const byLead = new Map();
  const bySession = new Map();

  (calls || []).forEach((call) => {
    const count =
      typeof call.turn_count === 'number'
        ? call.turn_count
        : typeof call.turns === 'number'
        ? call.turns
        : computeTurnsFromTranscript(call.transcript);
    const leadId = call.lead_id != null ? String(call.lead_id) : null;
    const sessionId = call.session_call_id != null ? String(call.session_call_id) : null;
    if (leadId) {
      const prev = byLead.get(leadId) || 0;
      if (count >= prev) byLead.set(leadId, count);
    }
    if (sessionId) bySession.set(sessionId, count);
  });

  return { byLead, bySession };
}

export function getLeadTurns(lead, turnsIndex) {
  if (!lead) return 0;
  if (typeof lead.turns === 'number') return lead.turns;
  if (typeof lead.turn_count === 'number') return lead.turn_count;
  if (typeof lead.last_call_turns === 'number') return lead.last_call_turns;
  if (!turnsIndex) return 0;
  const sessionId = lead.session_call_id != null ? String(lead.session_call_id) : null;
  if (sessionId && turnsIndex.bySession.has(sessionId)) {
    return turnsIndex.bySession.get(sessionId) || 0;
  }
  const leadId = lead.id != null ? String(lead.id) : null;
  if (leadId && turnsIndex.byLead.has(leadId)) {
    return turnsIndex.byLead.get(leadId) || 0;
  }
  return 0;
}
