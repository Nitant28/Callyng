/** Same turn count used in CallTranscriptDrawer / LeadDrawer analytics. */
export function computeTurnsFromTranscript(transcript) {
  let turns = transcript;
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
    const count = computeTurnsFromTranscript(call.transcript);
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
  if (!lead || !turnsIndex) return 0;
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
