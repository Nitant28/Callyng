const clockTime = (iso) => {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: true,
    });
  } catch {
    return '';
  }
};

const formatDuration = (seconds) => {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return null;
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
};

const callEvent = (call, campaignName) => {
  const time = call.startedAt || call.createdAt;
  const leadName = call.leadName || '—';

  if (call.inProgress) {
    return {
      id: `${call.sessionCallId}-start`,
      time,
      campaign: campaignName,
      leadName,
      status: 'Dialing',
      duration: null,
    };
  }

  const o = (call.outcome || '').toString();

  if (o === 'Busy') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'Busy', duration: formatDuration(call.durationSeconds) };
  }
  if (o === 'No_Answer') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'No Answer', duration: formatDuration(call.durationSeconds) };
  }
  if (o === 'Voicemail') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'No Answer', duration: formatDuration(call.durationSeconds) };
  }
  if (o.includes('Interest') && o !== 'Not_Interested') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'Interested', duration: formatDuration(call.durationSeconds) };
  }
  if (o === 'Not_Interested') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'Not Interested', duration: formatDuration(call.durationSeconds) };
  }
  if (o === 'Callback_Requested') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'Callback Requested', duration: formatDuration(call.durationSeconds) };
  }
  if (o === 'Wrong_Requirement' || o === 'Wrong_Number') {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'Wrong Number', duration: formatDuration(call.durationSeconds) };
  }
  if (call.recordingUrl || call.hasRecording) {
    return { id: `${call.sessionCallId}-rec`, time, campaign: campaignName, leadName, status: 'Recording Saved', duration: formatDuration(call.durationSeconds) };
  }
  if (call.transcript || call.summary) {
    return { id: `${call.sessionCallId}-tx`, time, campaign: campaignName, leadName, status: 'Transcript Generated', duration: formatDuration(call.durationSeconds) };
  }
  if (call.durationSeconds > 0 && !o) {
    return { id: call.sessionCallId, time, campaign: campaignName, leadName, status: 'Answered', duration: formatDuration(call.durationSeconds) };
  }

  return {
    id: call.sessionCallId,
    time,
    campaign: campaignName,
    leadName,
    status: 'Call Ended',
    duration: formatDuration(call.durationSeconds),
  };
};

const campaignEvent = (campaign) => {
  const statusMap = {
    running: 'Campaign Started',
    paused: 'Campaign Paused',
    pausing: 'Campaign Paused',
    completed: 'Campaign Completed',
  };
  const status = statusMap[campaign.status];
  if (!status) return null;
  return {
    id: `campaign-${campaign.id}-${campaign.status}`,
    time: campaign.updatedAt || campaign.createdAt,
    campaign: campaign.title || campaign.name || 'Campaign',
    leadName: '—',
    status,
    duration: null,
  };
};

export function buildActivityEvents(calls = [], campaigns = []) {
  const campaignMap = {};
  campaigns.forEach((c) => {
    if (c?.id) campaignMap[c.id] = c.title || c.name || 'Campaign';
  });

  const events = [];

  (calls ?? []).forEach((call) => {
    const name = call.campaignId ? campaignMap[call.campaignId] : 'Campaign';
    const ev = callEvent(call, name);
    events.push({ ...ev, id: ev.id || `call-${call.sessionCallId}` });
  });

  (campaigns ?? []).forEach((c) => {
    const ev = campaignEvent(c);
    if (ev) events.push(ev);
  });

  return events
    .filter((e) => e.time)
    .sort((a, b) => new Date(b.time) - new Date(a.time))
    .map((e) => ({ ...e, clock: clockTime(e.time) }));
}

export { clockTime };
