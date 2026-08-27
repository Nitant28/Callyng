import { useCallback, useEffect, useState } from 'react';
import clientApi from '../../../../api/client';
import {
  formatCallDuration,
  formatCallTime,
  parseCallDetail,
} from '../../../../utils/callLogsHelpers';
import AudioPlayer from './AudioPlayer';
import MetadataPanel from './MetadataPanel';
import StatusBadge from './StatusBadge';
import './TranscriptDrawer.css';

const TABS = ['Transcript', 'Summary', 'Metadata'];

const TranscriptDrawer = ({ open, call, campaignName, onClose }) => {
  const [tab, setTab] = useState('Transcript');
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [recordingUrl, setRecordingUrl] = useState(null);
  const [recordingLoading, setRecordingLoading] = useState(false);
  const [recordingError, setRecordingError] = useState(null);
  const [polling, setPolling] = useState(false);

  const sessionId = call?.sessionCallId;

  const fetchDetail = useCallback(async (spinner = true) => {
    if (!sessionId) return;
    if (spinner) setLoading(true);
    try {
      const res = await clientApi.get(`/api/calls/${sessionId}`);
      const parsed = parseCallDetail(res.data);
      setDetail(parsed);
      setPolling(parsed?.in_progress === true);
    } catch {
      setDetail(null);
      setPolling(false);
    } finally {
      if (spinner) setLoading(false);
    }
  }, [sessionId]);

  const fetchRecording = useCallback(async (id, inProgress) => {
    if (!id) return;
    setRecordingLoading(true);
    setRecordingError(null);
    try {
      const res = await clientApi.get(`/api/calls/${id}/recording/play`, { responseType: 'blob' });
      const url = URL.createObjectURL(res.data);
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
        setRecordingError(err.response?.data?.detail || 'No recording available');
      }
    } finally {
      setRecordingLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open || !sessionId) return undefined;
    fetchDetail(true);
    return () => {
      setDetail(null);
      setPolling(false);
    };
  }, [open, sessionId, fetchDetail]);

  useEffect(() => {
    if (!detail?.session_call_id) return;
    fetchRecording(detail.session_call_id, detail.in_progress);
  }, [detail?.session_call_id, detail?.in_progress, fetchRecording]);

  useEffect(() => {
    if (!polling || !open) return undefined;
    const id = setInterval(() => fetchDetail(false), 2500);
    return () => clearInterval(id);
  }, [polling, open, fetchDetail]);

  useEffect(() => {
    if (open) return;
    setRecordingUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setRecordingError(null);
    setTab('Transcript');
  }, [open]);

  if (!open || !call) return null;

  const leadName = call.leadName || detail?.name;
  const transcript = Array.isArray(detail?.transcript) ? detail.transcript : [];

  return (
    <>
      <button type="button" className="cl-drawer__backdrop" onClick={onClose} aria-label="Close" />
      <aside className={`cl-drawer ${open ? 'cl-drawer--open' : ''}`}>
        <header className="cl-drawer__header">
          <div>
            <div className="cl-drawer__title-row">
              <h2>{leadName}</h2>
              <StatusBadge outcome={detail?.outcome ?? call.outcome} inProgress={detail?.in_progress} />
            </div>
            <p className="cl-drawer__sub">
              {campaignName} · {formatCallTime(call.createdAt)} · {formatCallDuration(call.durationSeconds)}
            </p>
          </div>
          <button type="button" className="cl-drawer__close" onClick={onClose}>
            <span className="material-symbols-outlined">close</span>
          </button>
        </header>

        <div className="cl-drawer__player">
          <AudioPlayer
            src={recordingUrl}
            loading={recordingLoading}
            error={recordingError}
            downloadName={`call_${call.leadPhone || 'lead'}.mp3`}
          />
        </div>

        <nav className="cl-drawer__tabs">
          {TABS.map((t) => (
            <button
              key={t}
              type="button"
              className={tab === t ? 'cl-drawer__tab--active' : ''}
              onClick={() => setTab(t)}
            >
              {t}
            </button>
          ))}
        </nav>

        <div className="cl-drawer__body">
          {loading && (
            <div className="cl-drawer__loading">
              <span className="material-symbols-outlined cl-spin">progress_activity</span>
              Loading conversation…
            </div>
          )}

          {!loading && tab === 'Transcript' && (
            <div className="cl-drawer__chat">
              {transcript.length === 0 && (
                <p className="cl-drawer__empty-msg">No transcript captured for this call.</p>
              )}
              {transcript.map((msg, idx) => {
                const isAgent = msg.role === 'assistant' || msg.role === 'bot';
                return (
                  <div key={idx} className={`cl-bubble ${isAgent ? 'cl-bubble--agent' : 'cl-bubble--customer'}`}>
                    <span className="cl-bubble__role">{isAgent ? 'Agent' : 'Customer'}</span>
                    <div className="cl-bubble__text">{msg.content}</div>
                  </div>
                );
              })}
              {detail?.in_progress && (
                <div className="cl-bubble cl-bubble--agent">
                  <span className="cl-bubble__role">Agent</span>
                  <div className="cl-bubble__typing">
                    <span /><span /><span />
                  </div>
                </div>
              )}
            </div>
          )}

          {!loading && tab === 'Summary' && (
            <div className="cl-drawer__summary">
              {detail?.extraction_json && Object.keys(detail.extraction_json).length > 0 ? (
                Object.entries(detail.extraction_json).map(([key, val]) => (
                  <div key={key} className="cl-drawer__summary-row">
                    <span>{key}</span>
                    <strong>{String(val)}</strong>
                  </div>
                ))
              ) : (
                <p className="cl-drawer__empty-msg">No extracted lead data for this call.</p>
              )}
            </div>
          )}

          {!loading && tab === 'Metadata' && (
            <MetadataPanel
              call={detail || call}
              campaignName={campaignName}
              recordingAvailable={Boolean(recordingUrl)}
            />
          )}
        </div>
      </aside>
    </>
  );
};

export default TranscriptDrawer;
