import { useCallback, useEffect, useState } from 'react';
import clientApi from '../../../api/client';
import { fmtDuration, friendlyOutcome } from './leadUtils';

const parseJsonField = (val, fallback) => {
  if (val == null) return fallback;
  if (typeof val === 'object') return val;
  try {
    return JSON.parse(val);
  } catch {
    return fallback;
  }
};

const parseBlobError = async (err) => {
  const data = err?.response?.data;
  if (data instanceof Blob) {
    try {
      const json = JSON.parse(await data.text());
      if (typeof json?.detail === 'string') return json.detail;
    } catch {
      /* ignore */
    }
  }
  return err?.customErrorMessage || err?.response?.data?.detail || 'No recording available';
};

const normalizeTranscript = (raw) => {
  const list = parseJsonField(raw, []);
  if (!Array.isArray(list)) return [];
  return list
    .map((turn) => {
      if (!turn || typeof turn !== 'object') return null;
      const text = String(turn.content ?? turn.text ?? '').trim();
      if (!text) return null;
      return { role: turn.role || 'user', text };
    })
    .filter(Boolean);
};

const LeadCallPanel = ({ lead }) => {
  const [callData, setCallData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);

  const sessionId = lead?.sessionCallId || lead?.session_call_id || null;

  const fetchCall = useCallback(async (spinner = true) => {
    const lookupId = sessionId || lead?.id;
    if (!lookupId) return;
    if (spinner) setLoading(true);
    try {
      const res = await clientApi.get(`/api/calls/${lookupId}`);
      const call = res.data;
      if (!call?.session_call_id) {
        setCallData(null);
        setPolling(false);
        return;
      }
      call.transcript = normalizeTranscript(call.transcript);
      call.extraction_json = parseJsonField(call.extraction_json, null);
      setCallData(call);
      setPolling(call.in_progress === true || lead?.status === 'calling');
    } catch {
      setCallData(null);
      setPolling(lead?.status === 'calling');
    } finally {
      if (spinner) setLoading(false);
    }
  }, [sessionId, lead?.id, lead?.status]);

  useEffect(() => {
    if (!polling && callData?.in_progress === false) {
      const timer = setTimeout(() => fetchCall(false), 2500);
      return () => clearTimeout(timer);
    }
    return undefined;
  }, [polling, callData?.in_progress, fetchCall]);

  useEffect(() => {
    if (!lead) {
      setCallData(null);
      setPolling(false);
      return;
    }
    fetchCall(true);
  }, [lead, fetchCall]);

  useEffect(() => {
    if (!polling) return undefined;
    const interval = setInterval(() => fetchCall(false), 2500);
    return () => clearInterval(interval);
  }, [polling, fetchCall]);

  useEffect(() => {
    if (polling || !callData || callData.in_progress) return undefined;
    const timer = setTimeout(() => fetchCall(false), 2500);
    return () => clearTimeout(timer);
  }, [polling, callData?.in_progress, fetchCall]);

  const fetchRecording = useCallback(async (sid, inProgress) => {
    if (!sid) return;
    setRecordingLoading(true);
    setRecordingError(null);
    try {
      const recResp = await clientApi.get(`/api/calls/${sid}/recording/play`, {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(recResp.data);
      setRecordingUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch (err) {
      setRecordingUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return null;
      });
      if (!inProgress) {
        const message = await parseBlobError(err);
        setRecordingError(message);
      }
    } finally {
      setRecordingLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!callData?.session_call_id) return undefined;
    if (callData.in_progress) return undefined;
    if (!callData.recording_url) return undefined;
    fetchRecording(callData.session_call_id, false);
    return undefined;
  }, [callData?.session_call_id, callData?.recording_url, callData?.in_progress, fetchRecording]);

  useEffect(() => {
    if (!callData?.session_call_id || callData.in_progress) return undefined;
    if (callData.recording_url) return undefined;
    const timer = setTimeout(() => {
      fetchRecording(callData.session_call_id, false);
    }, 3000);
    return () => clearTimeout(timer);
  }, [callData?.session_call_id, callData?.recording_url, callData?.in_progress, fetchRecording]);

  useEffect(() => () => {
    setRecordingUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  if (!lead) return null;

  const hasHistory = (lead.attempts ?? 0) > 0 || lead.lastCalledAt || lead.status === 'calling';

  return (
    <section className="ls-drawer__section ls-call-panel">
      <div className="ls-drawer__section-head">
        <h3>Call recording & transcript</h3>
        {callData?.in_progress && (
          <span className="ls-call-panel__live">
            <span className="ls-call-panel__live-dot" />
            Live
          </span>
        )}
      </div>

      {!hasHistory && !loading && (
        <p className="ls-call-panel__empty">No calls yet for this lead.</p>
      )}

      {loading && (
        <div className="ls-call-panel__loading">
          <span className="material-symbols-outlined ls-call-panel__spin">progress_activity</span>
          Loading call details…
        </div>
      )}

      {!loading && callData && (
        <>
          <div className="ls-call-panel__meta">
            <span>{fmtDuration(callData.duration_seconds)}</span>
            {callData.outcome && (
              <span>{friendlyOutcome(callData.outcome)}</span>
            )}
          </div>

          <div className="ls-call-panel__audio">
            {recordingLoading && (
              <p className="ls-call-panel__muted">Loading audio…</p>
            )}
            {!recordingLoading && recordingUrl && (
              <audio controls src={recordingUrl} className="ls-call-panel__player" controlsList="nodownload" />
            )}
            {!recordingLoading && !recordingUrl && (
              <p className="ls-call-panel__muted">
                {recordingError || (callData.in_progress
                  ? 'Recording available after the call ends.'
                  : 'No recording for this call.')}
              </p>
            )}
          </div>

          <div className="ls-call-panel__transcript">
            {callData.transcript.length > 0 ? (
              callData.transcript.map((turn, idx) => {
                const isBot = turn.role === 'assistant' || turn.role === 'bot' || turn.role === 'agent';
                return (
                  <div
                    key={`${idx}-${turn.text.slice(0, 24)}`}
                    className={`ls-call-panel__bubble ${isBot ? 'ls-call-panel__bubble--bot' : 'ls-call-panel__bubble--user'}`}
                  >
                    <span className="ls-call-panel__role">{isBot ? 'Agent' : 'Lead'}</span>
                    <p>{turn.text}</p>
                  </div>
                );
              })
            ) : (
              <p className="ls-call-panel__muted">
                {callData.in_progress ? 'Transcript will appear as the call progresses…' : 'No transcript captured.'}
              </p>
            )}
          </div>

          {callData.extraction_json && Object.keys(callData.extraction_json).length > 0 && (
            <div className="ls-call-panel__extraction">
              <h4>Extraction</h4>
              <dl>
                {Object.entries(callData.extraction_json).map(([key, val]) => (
                  <div key={key}>
                    <dt>{key.replace(/_/g, ' ')}</dt>
                    <dd>{typeof val === 'object' ? JSON.stringify(val) : String(val ?? '—')}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </>
      )}

      {!loading && !callData && hasHistory && (
        <p className="ls-call-panel__muted">
          {lead.status === 'calling'
            ? 'Connecting call — details will appear shortly…'
            : 'Call details unavailable for the latest attempt.'}
        </p>
      )}
    </section>
  );
};

export default LeadCallPanel;
